"""PSI-MOD database: indexing, lookup, and graph traversal."""

from __future__ import annotations

import importlib.resources
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Literal

from psimodpy.models import (
    AminoAcid,
    Crosslink,
    PsiModEntry,
    RelationshipType,
    Source,
    TermSpec,
)

MassType = Literal["diff_mono", "diff_avg", "mass_mono", "mass_avg"]


class PsiModDatabase:
    """In-memory database of PSI-MOD entries with multiple lookup strategies."""

    def __init__(
        self,
        entries: list[PsiModEntry] | Iterator[PsiModEntry],
        *,
        header_lines: tuple[str, ...] = (),
    ) -> None:
        self._by_id: dict[int, PsiModEntry] = {}
        self._by_name_lower: dict[str, PsiModEntry] = {}
        self._by_origin: dict[str, list[PsiModEntry]] = {}
        self._children: dict[int, list[int]] = {}
        self.header_lines: tuple[str, ...] = header_lines

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
        """Return all entries whose origin includes the given amino acid code."""
        return list(self._by_origin.get(aa, []))

    def find(
        self,
        *,
        text: str | None = None,
        mass_min: float | None = None,
        mass_max: float | None = None,
        mass_type: MassType = "diff_mono",
        residues: Sequence[str] | None = None,
        term_spec: str | None = None,
        source: str | None = None,
        in_slim_subset: bool | None = None,
        include_obsolete: bool = False,
        limit: int | None = None,
    ) -> list[PsiModEntry]:
        """Fine-grained AND-combined search across multiple fields.

        All filters are optional; ``None`` values are skipped.  ``residues`` is
        matched (case-sensitive single letters) against the entry's origin.
        For :class:`Crosslink` origins, an entry matches if any site is in the
        residue set.  ``mass_type`` selects which mass field to range-filter on.
        ``term_spec`` and ``source`` accept the OBO string values
        (e.g. ``"N-term"``, ``"natural"``).
        """
        text_q = text.lower() if text is not None else None
        residue_set = {r.upper() for r in residues} if residues else None

        ts_value: TermSpec | None = None
        if term_spec is not None:
            try:
                ts_value = TermSpec(term_spec)
            except ValueError:
                return []

        src_value: Source | None = None
        if source is not None:
            try:
                src_value = Source(source)
            except ValueError:
                return []

        results: list[PsiModEntry] = []
        for entry in self._by_id.values():
            if not include_obsolete and entry.is_obsolete:
                continue

            if text_q is not None and not (
                text_q in entry.name.lower()
                or text_q in entry.definition.lower()
                or any(text_q in s.value.lower() for s in entry.synonyms)
            ):
                continue

            if mass_min is not None or mass_max is not None:
                mass = getattr(entry, mass_type, None)
                if mass is None:
                    continue
                if mass_min is not None and mass < mass_min:
                    continue
                if mass_max is not None and mass > mass_max:
                    continue

            if residue_set is not None:
                sites = _origin_sites(entry)
                if not sites or sites.isdisjoint(residue_set):
                    continue

            if ts_value is not None and entry.term_spec != ts_value:
                continue

            if src_value is not None and entry.source != src_value:
                continue

            if in_slim_subset is not None and entry.in_slim_subset != in_slim_subset:
                continue

            results.append(entry)
            if limit is not None and len(results) >= limit:
                break

        return results

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
        """Return a filtered list of entries."""
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


def _origin_sites(entry: PsiModEntry) -> set[str]:
    if entry.origin is None:
        return set()
    if isinstance(entry.origin, AminoAcid):
        return {str(entry.origin)}
    return set(entry.origin.sites)


def load(*, include_obsolete: bool = True) -> PsiModDatabase:
    """Load the bundled PSI-MOD database."""
    from psimodpy.parser import parse_obo

    pkg_data = importlib.resources.files("psimodpy.data")
    obo_path = pkg_data.joinpath("PSI-MOD.obo")
    with importlib.resources.as_file(obo_path) as path:
        db = parse_obo(Path(path))

    if not include_obsolete:
        return PsiModDatabase(e for e in db if not e.is_obsolete)
    return db


def load_from(path: Path | str) -> PsiModDatabase:
    """Load PSI-MOD database from a custom OBO file path."""
    from psimodpy.parser import parse_obo

    return parse_obo(path)
