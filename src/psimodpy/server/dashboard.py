"""Build the data payload consumed by the static dashboard."""

from __future__ import annotations

from typing import TypedDict

import psimodpy
from psimodpy.database import PsiModDatabase
from psimodpy.models import Crosslink


class DashboardSynonym(TypedDict):
    value: str
    type: str


class DashboardRelationship(TypedDict):
    type: str
    target_id: int


class DashboardCrosslink(TypedDict):
    type: str
    sites: list[str]


class DashboardEntry(TypedDict):
    id: int
    name: str
    definition: str
    comment: str | None
    synonyms: list[DashboardSynonym]
    is_a: list[int]
    relationships: list[DashboardRelationship]
    origin: str | DashboardCrosslink | None
    diff_mono: float | None
    diff_avg: float | None
    proforma_formula: str | None
    mass_mono: float | None
    mass_avg: float | None
    term_spec: str | None
    source: str | None
    formal_charge: int | None
    xref_unimod: str | None
    xref_uniprot_ptm: str | None
    xref_gnome: str | None
    xref_remap: int | None
    in_slim_subset: bool
    is_obsolete: bool


def dashboard_entries(db: PsiModDatabase | None = None) -> list[DashboardEntry]:
    """Return one JSON-ready dict per entry; loads the bundled database if ``db`` is None."""
    if db is None:
        db = psimodpy.load()
    entries: list[DashboardEntry] = []
    for entry in db:
        origin: str | DashboardCrosslink | None
        if isinstance(entry.origin, Crosslink):
            origin = {"type": "crosslink", "sites": list(entry.origin.sites)}
        else:
            origin = str(entry.origin) if entry.origin is not None else None

        entries.append(
            {
                "id": entry.id,
                "name": entry.name,
                "definition": entry.definition,
                "comment": entry.comment,
                "synonyms": [{"value": s.value, "type": str(s.type)} for s in entry.synonyms],
                "is_a": list(entry.is_a),
                "relationships": [{"type": str(r.type), "target_id": r.target_id} for r in entry.relationships],
                "origin": origin,
                "diff_mono": entry.diff_mono,
                "diff_avg": entry.diff_avg,
                "proforma_formula": entry.proforma_formula,
                "mass_mono": entry.mass_mono,
                "mass_avg": entry.mass_avg,
                "term_spec": str(entry.term_spec) if entry.term_spec is not None else None,
                "source": str(entry.source) if entry.source is not None else None,
                "formal_charge": entry.formal_charge,
                "xref_unimod": entry.xref_unimod,
                "xref_uniprot_ptm": entry.xref_uniprot_ptm,
                "xref_gnome": entry.xref_gnome,
                "xref_remap": entry.xref_remap,
                "in_slim_subset": entry.in_slim_subset,
                "is_obsolete": entry.is_obsolete,
            }
        )
    return entries
