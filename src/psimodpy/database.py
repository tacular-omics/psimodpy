"""PSI-MOD database: indexing, lookup, and graph traversal."""

from __future__ import annotations

import functools
import importlib.resources
import warnings
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

from psimodpy._mass import WHERE_ANY_C, WHERE_ANY_N, WHERE_ANYWHERE, MassIndex, Slot
from psimodpy.errors import PsimodError, PsimodKeyError
from psimodpy.models import AminoAcid, Crosslink, PsiModEntry, RelationshipType, TermSpec

# Joins the lowercased search fields of one entry. A query without this character can
# only match inside one field, so one substring test replaces one test per field.
_SEP = "\x00"


def _replacement_id(entry: PsiModEntry) -> int | None:
    """Return the one id that replaces an obsolete ``entry``, or None if there is not exactly one.

    ``replaced_by`` is the OBO tag for the replacement and ``xref: Remap`` is PSI-MOD's own
    tag for the same thing. Neither source is preferred over the other: nothing outside this
    package ranks them, so both are read and the walk continues only when they agree on a
    single id. Zero ids, several ``replaced_by`` tags (which the OBO 1.4 guide permits: "A
    single obsolete term may have more than one replaced_by tag"), or two tags naming
    different terms all leave the caller to decide, and :meth:`PsiModDatabase.resolve` stops.
    Measured 2026-11-17: no upstream stanza carries both tags, so no real file reaches the
    disagreement case.
    """
    candidates = set(entry.replaced_by)
    if entry.xref_remap is not None:
        candidates.add(entry.xref_remap)
    if len(candidates) == 1:
        return candidates.pop()
    return None


class PsiModDatabase:
    """In-memory database of PSI-MOD entries with multiple lookup strategies.

    Raises:
        PsimodError: if two entries share an id.
    """

    def __init__(
        self,
        entries: Iterable[PsiModEntry],
        *,
        header_lines: tuple[str, ...] = (),
        raw_stanza_lines: tuple[str, ...] = (),
    ) -> None:
        self._by_id: dict[int, PsiModEntry] = {}
        self._by_name_lower: dict[str, PsiModEntry] = {}
        self._by_origin: dict[str, list[PsiModEntry]] = {}
        self._children: dict[int, list[int]] = {}
        self.header_lines: tuple[str, ...] = header_lines
        self.raw_stanza_lines: tuple[str, ...] = raw_stanza_lines

        for entry in entries:
            if entry.id in self._by_id:
                raise PsimodError(f"duplicate id MOD:{entry.id:05d} ({self._by_id[entry.id].name!r}, {entry.name!r})")
            self._by_id[entry.id] = entry
            # Duplicate names: the first non-obsolete entry wins; an obsolete entry only
            # holds a name until a non-obsolete entry with the same name arrives.
            key = entry.name.lower()
            held = self._by_name_lower.get(key)
            if held is None or (held.is_obsolete and not entry.is_obsolete):
                self._by_name_lower[key] = entry

            # Index by each amino acid in origin
            if isinstance(entry.origin, AminoAcid):
                self._by_origin.setdefault(str(entry.origin), []).append(entry)
            elif isinstance(entry.origin, Crosslink):
                for site in entry.origin.sites:
                    self._by_origin.setdefault(site, []).append(entry)

        # (entry, lowercased name/definition/synonyms joined by _SEP), in id order, for search().
        self._haystacks: list[tuple[PsiModEntry, str]] = [(e, _haystack(e)) for e in self._by_id.values()]

        self._mass_index: MassIndex[PsiModEntry] | None = None

        # Build reverse is_a index after all entries are loaded
        for entry in self._by_id.values():
            for parent_id in entry.is_a:
                self._children.setdefault(parent_id, []).append(entry.id)

    # ------------------------------------------------------------------
    # Lookup by identity
    # ------------------------------------------------------------------

    def get_by_id(self, id: int | str) -> PsiModEntry | None:
        """Return the entry for the given ID, or None if not found.

        Accepts an integer (34) or a string: "34", "00034" or "MOD:00034" (prefix
        case-insensitive, surrounding whitespace ignored). Returns None for a string
        that is not an id ("foo", ""), a bool, or any other type; never raises.
        """
        if isinstance(id, bool):
            return None
        if isinstance(id, str):
            text = id.strip()
            if text[:4].upper() == "MOD:":
                text = text[4:].strip()
            if not text.isascii() or not text.isdigit():
                return None
            return self._by_id.get(int(text))
        if isinstance(id, int):
            return self._by_id.get(id)
        return None

    def resolve(self, id: int | str) -> PsiModEntry | None:
        """Follow ``xref_remap`` redirects from an obsolete term to the current term.

        Takes the same id forms as :meth:`get_by_id` and returns None for an id that is not
        in the database (or is malformed); never raises. A live term resolves to itself,
        and ``MOD:00407`` resolves to ``MOD:00599``.

        The replacement is read from the OBO ``replaced_by`` tag, of which the OBO 1.4 guide
        says the value "can safely be used to automatically reassign instances", and from
        PSI-MOD's own ``xref: Remap``. Neither is preferred: the walk continues only when the
        two name exactly one id between them. A term with several ``replaced_by`` tags, or
        with two tags that disagree, has no single replacement, so the walk stops there and
        the caller reads :attr:`~psimodpy.models.PsiModEntry.replaced_by` itself. The
        ``consider`` tag is not followed: the guide makes it a suggestion for a human expert
        to review.

        The walk stops on the last term it can reach, so it always terminates. That term is
        obsolete when the chain has no live end, in the three cases below, so check
        ``result.is_obsolete`` to tell a dead end from a live replacement:

        * an obsolete term with no redirect (``MOD:00580`` redirects to ``MOD:00579``,
          itself obsolete with none, so the result is ``MOD:00579``);
        * a redirect to an id that is not in the database: the last existing term is returned;
        * a cycle, including a term that redirects to itself (``MOD:01123``): the walk stops
          before it would revisit a term and returns the last new one reached.
        """
        entry = self.get_by_id(id)
        if entry is None:
            return None
        seen = {entry.id}
        while entry.is_obsolete:
            target = _replacement_id(entry)
            if target is None or target in seen:
                break
            nxt = self._by_id.get(target)
            if nxt is None:
                break
            seen.add(nxt.id)
            entry = nxt
        return entry

    def get_by_name(self, name: str) -> PsiModEntry | None:
        """Return the entry with the given name (case-insensitive), or None.

        PSI-MOD reuses a few names (e.g. "desmosine" is both obsolete MOD:00949 and
        MOD:01933). For a duplicate name the first non-obsolete entry in file order
        wins; an obsolete entry is returned only if no non-obsolete entry has the name.
        A non-string ``name`` returns None.
        """
        if not isinstance(name, str):
            return None
        return self._by_name_lower.get(name.lower())

    def get(self, key: object, default: PsiModEntry | None = None) -> PsiModEntry | None:
        """Return ``db[key]``, or ``default`` if it would raise. Never raises."""
        try:
            return self[key]
        except KeyError:
            return default

    def __getitem__(self, key: object) -> PsiModEntry:
        """Return the entry by id (34, "34", "00034", "MOD:00034") or, failing that, by name
        (case-insensitive). Raise PsimodKeyError (a KeyError) for a missing, malformed or
        non-int/str key."""
        entry = None
        if isinstance(key, int | str):
            entry = self.get_by_id(key)
            if entry is None and isinstance(key, str):
                entry = self.get_by_name(key)
        if entry is None:
            raise PsimodKeyError(key)
        return entry

    def __contains__(self, key: object) -> bool:
        """Return True if ``db[key]`` would succeed; never raises.

        A PsiModEntry is contained if an equal entry is stored under its id.
        """
        if isinstance(key, PsiModEntry):
            return self._by_id.get(key.id) == key
        return self.get(key) is not None

    def __len__(self) -> int:
        return len(self._by_id)

    def __iter__(self) -> Iterator[PsiModEntry]:
        return iter(self._by_id.values())

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str) -> list[PsiModEntry]:
        """Return entries whose name, definition, or any synonym contains query (case-insensitive).

        An empty query returns all entries; a non-string query returns ``[]``.
        """
        if not isinstance(query, str):
            return []
        q = query.lower()
        if not q:
            return list(self._by_id.values())
        if _SEP in q:
            # Rare: the query could span two joined fields, so test each field.
            return [e for e in self._by_id.values() if any(q in f for f in _fields(e))]
        return [entry for entry, haystack in self._haystacks if q in haystack]

    def search_mass(
        self,
        delta: float,
        *,
        tolerance: float = 0.01,
        tolerance_unit: str = "da",
        site: str | None = None,
        position: str | None = None,
        include_obsolete: bool = False,
    ) -> list[tuple[PsiModEntry, float]]:
        """Return ``(entry, error)`` pairs whose delta mass is within ``tolerance`` of ``delta``.

        The mass is the monoisotopic delta mass, ``diff_mono``.
        ``error`` is ``delta - mass`` in Da (positive when ``delta`` is heavier). Pairs are
        sorted by ``abs(error)``, ties in mass order then database order. Entries without
        ``diff_mono`` are skipped. The mass index is sorted once, on the first call, and
        searched with bisect.

        Args:
            delta: Observed monoisotopic mass shift in Da; may be negative.
            tolerance: Window half-width in Da; both edges are inclusive (with a 1e-9 relative
                slack for float rounding), and ``0`` means an exact match.
            tolerance_unit: Only ``"da"`` (the default), exact and lowercase; anything else raises.
                ppm is not offered: a ppm window on a delta mass is ill-defined (relative
                to the delta, or to the modified peptide's mass?). The keyword is kept so
                the call matches ``tacular.tolerance``; other units may be added later.
            site: Residue letter(s) the modification sits on, e.g. ``"S"`` or ``"STY"``
                (any of them), or ``"N-term"`` / ``"C-term"`` for a terminus modification.
                Several letters mean any of them (``get_by_site`` takes exactly one residue).
                Matched against ``origin`` (each residue of a crosslink); origin ``X`` matches
                only ``site="X"``. PSI-MOD has no terminus-only entries, so ``"N-term"`` finds none.
            position: Where the modified residue was observed: ``"anywhere"`` (inside the
                sequence), ``"peptide n-term"``, ``"peptide c-term"``, ``"protein n-term"``
                or ``"protein c-term"`` (case-insensitive). Keeps entries allowed there;
                a modification allowed anywhere is allowed at a terminus too. PSI-MOD's ``TermSpec`` does not
                say protein or peptide: an N-term entry matches both N-terminal positions.
            include_obsolete: If False (default), skip obsolete terms (``is_obsolete``); they
                duplicate current terms' masses. True keeps them, when the database has them
                (``load(include_obsolete=False)`` drops them at load time).

        Raises:
            PsimodError: ``delta`` or ``tolerance`` is not a finite number (or ``tolerance`` < 0),
                or ``tolerance_unit``, ``site`` or ``position`` is not one of the values above.
        """
        if self._mass_index is None:
            self._mass_index = MassIndex((e, e.get_mass(), _slots(e)) for e in self._by_id.values())
        hits = self._mass_index.search(
            delta, tolerance=tolerance, tolerance_unit=tolerance_unit, site=site, position=position, error=PsimodError
        )
        if not isinstance(include_obsolete, bool):
            raise PsimodError(f"include_obsolete must be a bool, got {include_obsolete!r}")
        return hits if include_obsolete else [hit for hit in hits if not hit[0].is_obsolete]

    def get_by_site(self, site: str) -> list[PsiModEntry]:
        """Return entries whose origin includes residue ``site`` (case-insensitive).

        Like ``get_by_origin(site.strip().upper())``, named like unimodpy's and
        uniprotptmpy's ``get_by_site``, but each entry appears once: a crosslink with
        origin ``"S, S"`` is listed twice by ``get_by_origin("S")`` and once here.
        A non-string returns ``[]``.
        Takes exactly one residue; ``search_mass(site=...)`` takes several letters (any of them).
        """
        if not isinstance(site, str):
            return []
        return list(dict.fromkeys(self.get_by_origin(site.strip().upper())))

    def get_by_origin(self, aa: str) -> list[PsiModEntry]:
        """Return all entries whose origin includes the given amino acid code.

        Crosslink entries with origin "C, C" will appear in get_by_origin("C").
        Entries with origin "X" (any) appear in get_by_origin("X").
        """
        return list(self._by_origin.get(aa, []))

    # ------------------------------------------------------------------
    # Graph traversal
    # ------------------------------------------------------------------

    def get_parents(self, entry: PsiModEntry) -> list[PsiModEntry]:
        """Return the direct parent entries (via is_a relationships)."""
        return [self._by_id[pid] for pid in entry.is_a if pid in self._by_id]

    def get_children(self, entry: PsiModEntry) -> list[PsiModEntry]:
        """Return entries that have this entry as a direct parent."""
        return [self._by_id[cid] for cid in self._children.get(entry.id, []) if cid in self._by_id]

    def get_ancestors(self, entry: PsiModEntry | int | str) -> list[PsiModEntry]:
        """Return every term reachable by following ``is_a`` upward, each once.

        Takes an entry or any id ``get_by_id`` takes. The order is breadth-first: direct parents
        first (in ``get_parents`` order), then their parents, and so on; a term reached by
        several paths appears once, at its shallowest level. A term is not its own ancestor,
        even in an ``is_a`` cycle. A root, an unknown id or a malformed id gives ``[]``.
        """
        start = self._as_entry(entry)
        if start is None:
            return []
        return self._walk(start, lambda e: e.is_a)

    def get_descendants(self, entry: PsiModEntry | int | str) -> list[PsiModEntry]:
        """Return every term reachable by following ``is_a`` downward, each once.

        Same rules as :meth:`get_ancestors`: breadth-first, direct children first (in
        ``get_children`` order), each term once, never the term itself, ``[]`` for a leaf or an
        unknown id.
        """
        start = self._as_entry(entry)
        if start is None:
            return []
        return self._walk(start, lambda e: self._children.get(e.id, ()))

    def is_descendant_of(self, entry: PsiModEntry | int | str, ancestor: PsiModEntry | int | str) -> bool:
        """Return True if ``ancestor`` is reachable from ``entry`` by following ``is_a`` upward.

        Both arguments take an entry or an id. A term is not its own descendant, so
        ``is_descendant_of(x, x)`` is False; an unknown or malformed id on either side gives False.
        """
        start = self._as_entry(entry)
        target = self._as_entry(ancestor)
        if start is None or target is None or start.id == target.id:
            return False
        return any(e.id == target.id for e in self._walk(start, lambda e: e.is_a))

    def _as_entry(self, entry: PsiModEntry | int | str) -> PsiModEntry | None:
        return entry if isinstance(entry, PsiModEntry) else self.get_by_id(entry)

    def _walk(self, start: PsiModEntry, step: Callable[[PsiModEntry], Iterable[int]]) -> list[PsiModEntry]:
        """Breadth-first walk from ``start`` over ``step`` ids; each term once, ``start`` excluded."""
        seen = {start.id}
        out: list[PsiModEntry] = []
        frontier = [start]
        while frontier:
            nxt: list[PsiModEntry] = []
            for current in frontier:
                for nid in step(current):
                    found = self._by_id.get(nid)
                    if found is not None and nid not in seen:
                        seen.add(nid)
                        out.append(found)
                        nxt.append(found)
            frontier = nxt
        return out

    def get_related(self, entry: PsiModEntry, rel_type: RelationshipType) -> list[PsiModEntry]:
        """Return entries reachable from entry via the given relationship type."""
        return [
            self._by_id[r.target_id] for r in entry.relationships if r.type == rel_type and r.target_id in self._by_id
        ]

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def filter(
        self,
        *,
        include_obsolete: bool = False,
        slim_only: bool = False,
    ) -> list[PsiModEntry]:
        """Return a filtered list of entries.

        Args:
            include_obsolete: If False (default), exclude obsolete entries.
            slim_only: If True, return only PSI-MOD-slim subset entries.
        """
        entries = list(self._by_id.values())
        if not include_obsolete:
            entries = [e for e in entries if not e.is_obsolete]
        if slim_only:
            entries = [e for e in entries if e.in_slim_subset]
        return entries

    def write_tsv(self, path: Path | str, *, delimiter: str = "\t") -> Path:
        """Serialize all entries to a tab-separated file. Pass ``delimiter=','`` for CSV."""
        from psimodpy._tabular import write_tsv

        return write_tsv(self._by_id.values(), path, delimiter=delimiter)

    def write_obo(self, path: Path | str) -> Path:
        """Serialize all entries to PSI-MOD OBO format."""
        from psimodpy._obo_writer import write_obo

        return write_obo(
            self._by_id.values(), path, header_lines=self.header_lines, raw_stanza_lines=self.raw_stanza_lines
        )


def _fields(entry: PsiModEntry) -> list[str]:
    """Return the lowercased name, definition and synonyms of ``entry``: the fields search() looks in."""
    return [entry.name.lower(), entry.definition.lower(), *(s.value.lower() for s in entry.synonyms)]


def _slots(entry: PsiModEntry) -> tuple[Slot, ...]:
    """Where ``entry`` may sit, for search_mass: its origin residues and TermSpec."""
    if entry.term_spec == TermSpec.N_TERM:
        where = WHERE_ANY_N
    elif entry.term_spec == TermSpec.C_TERM:
        where = WHERE_ANY_C
    else:
        where = WHERE_ANYWHERE
    if isinstance(entry.origin, AminoAcid):
        sites = frozenset({str(entry.origin)})
    elif isinstance(entry.origin, Crosslink):
        sites = frozenset(entry.origin.sites)
    else:
        sites = frozenset()
    return ((sites, where),)


def _haystack(entry: PsiModEntry) -> str:
    """Return ``_fields(entry)`` joined by ``_SEP``."""
    return _SEP.join(_fields(entry))


@functools.cache
def _load_bundled(include_obsolete: bool) -> PsiModDatabase:
    """Parse the bundled OBO once per ``include_obsolete`` value; backs ``load(cache=True)``."""
    return load(include_obsolete=include_obsolete)


def load(
    source: Path | str | None = None,
    *,
    refresh: bool = False,
    include_obsolete: bool = True,
    cache: bool = False,
) -> PsiModDatabase:
    """Load the PSI-MOD database.

    Args:
        source: Path to a PSI-MOD OBO file. If omitted, uses the bundled file.
        refresh: Download the latest OBO from HUPO-PSI (``download(force=True)``)
            and load that. Cannot be combined with ``source``.
        include_obsolete: If True (default), include obsolete entries. Obsolete
            entries carry xref_remap redirects useful for cross-reference resolution.
            Pass False to exclude them.
        cache: If True, parse the bundled file only once per process and return that same
            database object on every later ``load(cache=True)`` call (one per ``include_obsolete``
            value). The returned database is shared by every ``load(cache=True)`` caller in the
            process: do not modify it or reassign its attributes, such as ``header_lines``; a
            change is seen by every later caller. Only for the bundled file: cannot be combined with
            ``source`` or ``refresh``. Default False: a new database each call.

    Returns:
        A PsiModDatabase; ``header_lines`` and ``raw_stanza_lines`` are kept
        whatever ``include_obsolete`` is.

    Raises:
        ValueError: if both ``source`` and ``refresh=True`` are given, or ``cache=True``
            is combined with either.
    """
    from psimodpy.parser import parse_obo

    if cache:
        if source is not None or refresh:
            raise ValueError("cache=True only applies to the bundled file; drop source and refresh")
        return _load_bundled(include_obsolete)
    if refresh:
        if source is not None:
            raise ValueError("pass either source or refresh=True, not both")
        from psimodpy import _download

        db = parse_obo(_download.download(force=True))
    elif source is not None:
        db = parse_obo(source)
    else:
        obo_path = importlib.resources.files("psimodpy.data").joinpath("PSI-MOD.obo")
        with importlib.resources.as_file(obo_path) as path:
            db = parse_obo(Path(path))

    if not include_obsolete:
        return PsiModDatabase(
            (e for e in db if not e.is_obsolete),
            header_lines=db.header_lines,
            raw_stanza_lines=db.raw_stanza_lines,
        )
    return db


def load_from(path: Path | str) -> PsiModDatabase:
    """Deprecated alias of ``load(path)``; will be removed in 2.0."""
    warnings.warn("load_from(path) is deprecated; use load(path)", DeprecationWarning, stacklevel=2)
    return load(path)
