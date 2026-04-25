"""Tabular (TSV/CSV) writer for PSI-MOD entries."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from psimodpy.models import AminoAcid, Crosslink, PsiModEntry, Synonym, SynonymType

_FIXED_PREFIX: tuple[str, ...] = (
    "id",
    "name",
    "definition",
    "comment",
    "diff_mono",
    "diff_avg",
    "diff_formula",
    "mass_mono",
    "mass_avg",
    "formula",
    "origin",
    "term_spec",
    "source",
    "formal_charge",
    "xref_unimod",
    "xref_uniprot_ptm",
    "xref_gnome",
    "xref_remap",
    "in_slim_subset",
    "is_obsolete",
)

_FIXED_SUFFIX: tuple[str, ...] = ("is_a", "relationships")

_SUB_DELIM = "; "


def _synonym_types(entries: Iterable[PsiModEntry]) -> list[SynonymType]:
    """Return sorted unique SynonymType values found across entries."""
    seen: set[SynonymType] = set()
    for e in entries:
        for s in e.synonyms:
            seen.add(s.type)
    return sorted(seen, key=lambda t: t.value)


def _synonym_col(syn_type: SynonymType) -> str:
    return "synonym_" + syn_type.value.lower().replace("-", "_")


def _cell(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _fmt_origin(origin: AminoAcid | Crosslink | None) -> str:
    if origin is None:
        return ""
    if isinstance(origin, AminoAcid):
        return str(origin)
    return ", ".join(origin.sites)


def _fmt_formal_charge(charge: int | None) -> str:
    if charge is None:
        return ""
    if charge >= 0:
        return f"{charge}+"
    return f"{abs(charge)}-"


def build_columns(entries: Iterable[PsiModEntry]) -> tuple[str, ...]:
    """Build the full TSV column header for the given entries."""
    syn_cols = tuple(_synonym_col(t) for t in _synonym_types(entries))
    return _FIXED_PREFIX + syn_cols + _FIXED_SUFFIX


def to_row(entry: PsiModEntry, syn_types: list[SynonymType]) -> list[str]:
    """Flatten a PsiModEntry to a list of column values."""
    syn_by_type: dict[SynonymType, str] = {}
    for s in entry.synonyms:
        if s.type not in syn_by_type:
            syn_by_type[s.type] = s.value

    return [
        f"MOD:{entry.id:05d}",
        entry.name,
        entry.definition,
        _cell(entry.comment),
        _cell(entry.diff_mono),
        _cell(entry.diff_avg),
        _cell(entry.diff_formula),
        _cell(entry.mass_mono),
        _cell(entry.mass_avg),
        _cell(entry.formula),
        _fmt_origin(entry.origin),
        _cell(entry.term_spec),
        _cell(entry.source),
        _fmt_formal_charge(entry.formal_charge),
        _cell(entry.xref_unimod),
        _cell(entry.xref_uniprot_ptm),
        _cell(entry.xref_gnome),
        f"MOD:{entry.xref_remap:05d}" if entry.xref_remap is not None else "",
        "1" if entry.in_slim_subset else "0",
        "1" if entry.is_obsolete else "0",
        *(syn_by_type.get(t, "") for t in syn_types),
        _SUB_DELIM.join(f"MOD:{pid:05d}" for pid in entry.is_a),
        _SUB_DELIM.join(f"{r.type}:MOD:{r.target_id:05d}" for r in entry.relationships),
    ]


def write_tsv(
    entries: Iterable[PsiModEntry],
    path: Path | str,
    *,
    delimiter: str = "\t",
) -> Path:
    """Write PSI-MOD entries to a tab-separated file.

    Pass ``delimiter=","`` to emit CSV instead. Returns the resolved Path.
    """
    materialized = list(entries)
    syn_types = _synonym_types(materialized)
    header = _FIXED_PREFIX + tuple(_synonym_col(t) for t in syn_types) + _FIXED_SUFFIX

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=delimiter, lineterminator="\n")
        writer.writerow(header)
        for entry in materialized:
            writer.writerow(to_row(entry, syn_types))
    return out
