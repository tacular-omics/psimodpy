"""PSI-MOD database: indexing, lookup, and graph traversal."""

from __future__ import annotations

import importlib.resources
from collections.abc import Iterator
from pathlib import Path

from psimodpy.models import AminoAcid, Crosslink, PsiModEntry, RelationshipType


class PsiModDatabase:
    """In-memory database of PSI-MOD entries with multiple lookup strategies."""

    def __init__(self, entries: list[PsiModEntry] | Iterator[PsiModEntry]) -> None:
        self._by_id: dict[int, PsiModEntry] = {}
        self._by_name_lower: dict[str, PsiModEntry] = {}
        self._by_origin: dict[str, list[PsiModEntry]] = {}
        self._children: dict[int, list[int]] = {}

        for entry in entries:
            self._by_id[entry.id] = entry
            self._by_name_lower[entry.name.lower()] = entry

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

        Accepts an integer (34) or a string in MOD:NNNNN format ("MOD:00034").
        """
        if isinstance(id, str):
            # Accept "MOD:00034" or plain "34"
            if id.upper().startswith("MOD:"):
                id = int(id[4:])
            else:
                id = int(id)
        return self._by_id.get(id)

    def get_by_name(self, name: str) -> PsiModEntry | None:
        """Return the entry with the given name (case-insensitive), or None."""
        return self._by_name_lower.get(name.lower())

    def __getitem__(self, id: int | str) -> PsiModEntry:
        """Return entry by ID; raise KeyError if not found."""
        entry = self.get_by_id(id)
        if entry is None:
            raise KeyError(id)
        return entry

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
            self._by_id[r.target_id]
            for r in entry.relationships
            if r.type == rel_type and r.target_id in self._by_id
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


def load(*, include_obsolete: bool = True) -> PsiModDatabase:
    """Load the bundled PSI-MOD database.

    Args:
        include_obsolete: If True (default), include obsolete entries. Obsolete
            entries carry xref_remap redirects useful for cross-reference resolution.
            Pass False to exclude them.

    Returns:
        A PsiModDatabase populated from the bundled PSI-MOD.obo file.
    """
    from psimodpy.parser import parse_obo

    pkg_data = importlib.resources.files("psimodpy.data")
    obo_path = pkg_data.joinpath("PSI-MOD.obo")
    # importlib.resources returns a Traversable; write to a temp path if needed
    with importlib.resources.as_file(obo_path) as path:
        db = parse_obo(Path(path))

    if not include_obsolete:
        return PsiModDatabase(e for e in db if not e.is_obsolete)
    return db


def load_from(path: Path | str) -> PsiModDatabase:
    """Load PSI-MOD database from a custom OBO file path."""
    from psimodpy.parser import parse_obo

    return parse_obo(path)
