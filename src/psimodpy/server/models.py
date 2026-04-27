"""Pydantic response models for the psimodpy REST + MCP server.

These models are the single source of truth for the wire shape returned by
both transports.  Keeping them here lets tests import the schema directly
and lets FastMCP derive ``outputSchema`` automatically.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from psimodpy.models import AminoAcid as _AminoAcid
from psimodpy.models import Crosslink as _Crosslink
from psimodpy.models import PsiModEntry as _PsiModEntry
from psimodpy.models import Relationship as _Relationship
from psimodpy.models import Synonym as _Synonym


class Reference(BaseModel):
    """A single citation parsed from ``definition_ref``."""

    type: str
    accession: str | None = None
    value: str | None = None


class Synonym(BaseModel):
    value: str
    type: str
    scope: str


class Relationship(BaseModel):
    type: str
    target_id: int


class AminoAcidOrigin(BaseModel):
    type: Literal["amino_acid"] = "amino_acid"
    code: str


class CrosslinkOrigin(BaseModel):
    type: Literal["crosslink"] = "crosslink"
    sites: list[str]


class PsiModEntry(BaseModel):
    """Full PSI-MOD ontology entry."""

    id: int
    accession: str
    name: str
    definition: str | None
    references: list[Reference]
    synonyms: list[Synonym]
    is_a: list[int]
    relationships: list[Relationship]
    comment: str | None
    diff_mono: float | None
    diff_avg: float | None
    diff_formula: str | None
    proforma_diff_formula: str | None
    dict_diff_formula: dict[str, int] | None
    mass_mono: float | None
    mass_avg: float | None
    formula: str | None
    dict_formula: dict[str, int] | None
    origin: AminoAcidOrigin | CrosslinkOrigin | None
    term_spec: str | None
    source: str | None
    formal_charge: int | None
    xref_unimod: str | None
    xref_uniprot_ptm: str | None
    xref_gnome: str | None
    xref_remap: int | None
    in_slim_subset: bool
    is_obsolete: bool


class PsiModSummary(BaseModel):
    """Compact entry shape returned by ``search`` and similar list endpoints."""

    id: int
    accession: str
    name: str
    mass_mono: float | None
    is_obsolete: bool


class EntryListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[PsiModEntry]


class SearchResponse(BaseModel):
    query: str
    total: int
    limit: int
    items: list[PsiModSummary] = Field(
        description="Lightweight summaries; call get_by_id for the full record.",
    )


class OriginResponse(BaseModel):
    origin: str
    count: int
    items: list[PsiModEntry]


# ---------------------------------------------------------------------------
# Converters from domain dataclasses to Pydantic models
# ---------------------------------------------------------------------------


def _synonym(s: _Synonym) -> Synonym:
    return Synonym(value=s.value, type=str(s.type), scope=s.scope)


def _relationship(r: _Relationship) -> Relationship:
    return Relationship(type=str(r.type), target_id=r.target_id)


def _origin(o: _AminoAcid | _Crosslink | None) -> AminoAcidOrigin | CrosslinkOrigin | None:
    if o is None:
        return None
    if isinstance(o, _Crosslink):
        return CrosslinkOrigin(sites=list(o.sites))
    return AminoAcidOrigin(code=str(o))


def to_psimod_entry(entry: _PsiModEntry) -> PsiModEntry:
    # Local import to avoid an import cycle: references.py imports models.py.
    from psimodpy.server.references import parse_definition_ref

    return PsiModEntry(
        id=entry.id,
        accession=f"MOD:{entry.id:05d}",
        name=entry.name,
        definition=entry.definition or None,
        references=parse_definition_ref(entry.definition_ref),
        synonyms=[_synonym(s) for s in entry.synonyms],
        is_a=list(entry.is_a),
        relationships=[_relationship(r) for r in entry.relationships],
        comment=entry.comment,
        diff_mono=entry.diff_mono,
        diff_avg=entry.diff_avg,
        diff_formula=entry.diff_formula,
        proforma_diff_formula=entry.proforma_diff_formula,
        dict_diff_formula=entry.dict_diff_formula,
        mass_mono=entry.mass_mono,
        mass_avg=entry.mass_avg,
        formula=entry.formula,
        dict_formula=entry.dict_formula,
        origin=_origin(entry.origin),
        term_spec=str(entry.term_spec) if entry.term_spec else None,
        source=str(entry.source) if entry.source else None,
        formal_charge=entry.formal_charge,
        xref_unimod=entry.xref_unimod,
        xref_uniprot_ptm=entry.xref_uniprot_ptm,
        xref_gnome=entry.xref_gnome,
        xref_remap=entry.xref_remap,
        in_slim_subset=entry.in_slim_subset,
        is_obsolete=entry.is_obsolete,
    )


def to_psimod_summary(entry: _PsiModEntry) -> PsiModSummary:
    return PsiModSummary(
        id=entry.id,
        accession=f"MOD:{entry.id:05d}",
        name=entry.name,
        mass_mono=entry.mass_mono,
        is_obsolete=entry.is_obsolete,
    )
