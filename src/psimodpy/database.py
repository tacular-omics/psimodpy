"""PSI-MOD database: indexing, lookup, and graph traversal."""

from __future__ import annotations

import functools
import importlib.resources
import warnings
from collections.abc import Iterable, Iterator
from pathlib import Path

from psimodpy._mass import WHERE_ANY_C, WHERE_ANY_N, WHERE_ANYWHERE, MassIndex, Slot
from psimodpy.errors import PsimodError, PsimodKeyError
from psimodpy.models import AminoAcid, Crosslink, PsiModEntry, RelationshipType, TermSpec

# Joins the lowercased search fields of one entry. A query without this character can
# only match inside one field, so one substring test replaces one test per field.
_SEP = "\x00"


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
    ) -> None:
        self._by_id: dict[int, PsiModEntry] = {}
        self._by_name_lower: dict[str, PsiModEntry] = {}
        self._by_origin: dict[str, list[PsiModEntry]] = {}
        self._children: dict[int, list[int]] = {}
        self.header_lines: tuple[str, ...] = header_lines

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
        unit: str = "da",
        site: str | None = None,
        position: str | None = None,
    ) -> list[tuple[PsiModEntry, float]]:
        """Return ``(entry, error)`` pairs whose delta mass is within ``tolerance`` of ``delta``.

        The mass is the monoisotopic delta mass, ``diff_mono``.
        ``error`` is ``delta - mass`` in Da (positive when ``delta`` is heavier). Pairs are
        sorted by ``abs(error)``, ties in mass order then database order. Entries without
        ``diff_mono`` are skipped. The mass index is sorted once, on the first call, and
        searched with bisect.

        Args:
            delta: Observed monoisotopic mass shift in Da; may be negative.
            tolerance: Window half-width, inclusive; ``0`` means an exact match.
            unit: ``"da"`` (default) or ``"ppm"`` (parts per million of ``abs(delta)``).
            site: Residue letter(s) the modification sits on, e.g. ``"S"`` or ``"STY"``
                (any of them), or ``"N-term"`` / ``"C-term"`` for a terminus modification.
                Matched against ``origin`` (each residue of a crosslink); origin ``X`` matches
                only ``site="X"``. PSI-MOD has no terminus-only entries, so ``"N-term"`` finds none.
            position: Where the modified residue was observed: ``"anywhere"`` (inside the
                sequence), ``"peptide n-term"``, ``"peptide c-term"``, ``"protein n-term"``
                or ``"protein c-term"`` (case-insensitive). Keeps entries allowed there;
                a modification allowed anywhere is allowed at a terminus too. PSI-MOD's ``TermSpec`` does not
                say protein or peptide: an N-term entry matches both N-terminal positions.

        Raises:
            PsimodError: ``delta`` or ``tolerance`` is not a finite number (or ``tolerance`` < 0),
                or ``unit``, ``site`` or ``position`` is not one of the values above.
        """
        if self._mass_index is None:
            self._mass_index = MassIndex((e, e.diff_mono, _slots(e)) for e in self._by_id.values())
        return self._mass_index.search(
            delta, tolerance=tolerance, unit=unit, site=site, position=position, error=PsimodError
        )

    def get_by_site(self, site: str) -> list[PsiModEntry]:
        """Return entries whose origin includes residue ``site`` (case-insensitive).

        Like ``get_by_origin(site.strip().upper())``, named like unimodpy's and
        uniprotptmpy's ``get_by_site``, but each entry appears once: a crosslink with
        origin ``"S, S"`` is listed twice by ``get_by_origin("S")`` and once here.
        A non-string returns ``[]``.
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

        return write_obo(self._by_id.values(), path, header_lines=self.header_lines)


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
        A PsiModDatabase; ``header_lines`` is kept whatever ``include_obsolete`` is.

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
        return PsiModDatabase((e for e in db if not e.is_obsolete), header_lines=db.header_lines)
    return db


def load_from(path: Path | str) -> PsiModDatabase:
    """Deprecated alias of ``load(path)``; will be removed in 2.0."""
    warnings.warn("load_from(path) is deprecated; use load(path)", DeprecationWarning, stacklevel=2)
    return load(path)
