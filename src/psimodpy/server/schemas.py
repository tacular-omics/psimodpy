"""Serializers turning PsiModEntry dataclasses into JSON-friendly dicts."""

from __future__ import annotations

from typing import Any

from psimodpy.models import AminoAcid, Crosslink, PsiModEntry, Relationship, Synonym


def _serialize_origin(origin: AminoAcid | Crosslink | None) -> Any:
    if origin is None:
        return None
    if isinstance(origin, Crosslink):
        return {"type": "crosslink", "sites": list(origin.sites)}
    return {"type": "amino_acid", "code": str(origin)}


def serialize_synonym(syn: Synonym) -> dict[str, Any]:
    return {"value": syn.value, "type": str(syn.type), "scope": syn.scope}


def serialize_relationship(rel: Relationship) -> dict[str, Any]:
    return {"type": str(rel.type), "target_id": rel.target_id}


def serialize_entry(entry: PsiModEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "accession": f"MOD:{entry.id:05d}",
        "name": entry.name,
        "definition": entry.definition,
        "definition_ref": entry.definition_ref,
        "synonyms": [serialize_synonym(s) for s in entry.synonyms],
        "is_a": list(entry.is_a),
        "relationships": [serialize_relationship(r) for r in entry.relationships],
        "comment": entry.comment,
        "diff_mono": entry.diff_mono,
        "diff_avg": entry.diff_avg,
        "diff_formula": entry.diff_formula,
        "proforma_diff_formula": entry.proforma_diff_formula,
        "dict_diff_formula": entry.dict_diff_formula,
        "mass_mono": entry.mass_mono,
        "mass_avg": entry.mass_avg,
        "formula": entry.formula,
        "dict_formula": entry.dict_formula,
        "origin": _serialize_origin(entry.origin),
        "term_spec": str(entry.term_spec) if entry.term_spec else None,
        "source": str(entry.source) if entry.source else None,
        "formal_charge": entry.formal_charge,
        "xref_unimod": entry.xref_unimod,
        "xref_uniprot_ptm": entry.xref_uniprot_ptm,
        "xref_gnome": entry.xref_gnome,
        "xref_remap": entry.xref_remap,
        "in_slim_subset": entry.in_slim_subset,
        "is_obsolete": entry.is_obsolete,
    }
