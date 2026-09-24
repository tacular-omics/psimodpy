"""PSI-MOD database: indexing, lookup, and graph traversal."""

from __future__ import annotations

import importlib.resources
import warnings
from collections.abc import Iterable, Iterator
from pathlib import Path

from psimodpy.errors import PsimodError
from psimodpy.models import AminoAcid, Crosslink, PsiModEntry, RelationshipType


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
        """
        return self._by_name_lower.get(name.lower())

    def get(self, key: object, default: PsiModEntry | None = None) -> PsiModEntry | None:
        """Return ``db[key]``, or ``default`` if it would raise. Never raises."""
        try:
            return self[key]
        except KeyError:
            return default

    def __getitem__(self, key: object) -> PsiModEntry:
        """Return the entry by id (34, "34", "00034", "MOD:00034") or, failing that, by name
        (case-insensitive). Raise KeyError for a missing, malformed or non-int/str key."""
        entry = None
        if isinstance(key, int | str):
            entry = self.get_by_id(key)
            if entry is None and isinstance(key, str):
                entry = self.get_by_name(key)
        if entry is None:
            raise KeyError(key)
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

        An empty query returns all entries.
        """
        q = query.lower()
        if not q:
            return list(self._by_id.values())
        results = []
        for entry in self._by_id.values():
            if (
                q in entry.name.lower()
                or q in entry.definition.lower()
                or any(q in s.value.lower() for s in entry.synonyms)
            ):
                results.append(entry)
        return results

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


def load(
    source: Path | str | None = None,
    *,
    refresh: bool = False,
    include_obsolete: bool = True,
) -> PsiModDatabase:
    """Load the PSI-MOD database.

    Args:
        source: Path to a PSI-MOD OBO file. If omitted, uses the bundled file.
        refresh: Download the latest OBO from HUPO-PSI (``download(force=True)``)
            and load that. Ignored when ``source`` is given.
        include_obsolete: If True (default), include obsolete entries. Obsolete
            entries carry xref_remap redirects useful for cross-reference resolution.
            Pass False to exclude them.

    Returns:
        A PsiModDatabase; ``header_lines`` is kept whatever ``include_obsolete`` is.
    """
    from psimodpy.parser import parse_obo

    if source is not None:
        db = parse_obo(source)
    elif refresh:
        from psimodpy import _download

        db = parse_obo(_download.download(force=True))
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
