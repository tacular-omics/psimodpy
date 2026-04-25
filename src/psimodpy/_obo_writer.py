"""OBO format writer for PSI-MOD entries."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from psimodpy.models import AminoAcid, Crosslink, PsiModEntry

_MINIMAL_HEADER = """\
format-version: 1.2
ontology: mod
default-namespace: PSI-MOD
subsetdef: PSI-MOD-slim "subset of protein modifications"
synonymtypedef: DeltaMass-label "Label from MS DeltaMass" EXACT
synonymtypedef: OMSSA-label "Short label from OMSSA" EXACT
synonymtypedef: PSI-MOD-alternate "Alternate name curated by PSI-MOD" EXACT
synonymtypedef: PSI-MOD-label "Short label curated by PSI-MOD" EXACT
synonymtypedef: PSI-MS-label "Agreed label from MS community" RELATED
synonymtypedef: RESID-alternate "Alternate name from RESID" EXACT
synonymtypedef: RESID-misnomer "Misnomer tagged alternate name from RESID" RELATED
synonymtypedef: RESID-name "Name from RESID" EXACT
synonymtypedef: RESID-systematic "Systematic name from RESID" EXACT
synonymtypedef: Unimod-alternate "Alternate name from Unimod" RELATED
synonymtypedef: Unimod-description "Description (full_name) from Unimod" RELATED
synonymtypedef: Unimod-interim "Interim label from Unimod" RELATED
synonymtypedef: UniProt-feature "Protein feature description from UniProtKB" EXACT
idspace: uniprot.ptm https://bioregistry.io/uniprot.ptm: "UniProt Post-Translational Modification"
"""


def _fmt_origin(origin: AminoAcid | Crosslink | None) -> str:
    if origin is None:
        return "none"
    if isinstance(origin, AminoAcid):
        return str(origin)
    return ", ".join(origin.sites)


def _fmt_formal_charge(charge: int) -> str:
    if charge >= 0:
        return f"{charge}+"
    return f"{abs(charge)}-"


def _xref(key: str, value: str) -> str:
    return f'xref: {key}: "{value}"\n'


def _write_entry(fh, entry: PsiModEntry, names: dict[int, str]) -> None:
    fh.write("[Term]\n")
    fh.write(f"id: MOD:{entry.id:05d}\n")
    fh.write(f"name: {entry.name}\n")
    fh.write(f'def: "{entry.definition}" {entry.definition_ref}\n')
    if entry.in_slim_subset:
        fh.write("subset: PSI-MOD-slim\n")
    for syn in entry.synonyms:
        fh.write(f'synonym: "{syn.value}" {syn.scope} {syn.type} []\n')
    for parent_id in entry.is_a:
        suffix = f" ! {names[parent_id]}" if parent_id in names else ""
        fh.write(f"is_a: MOD:{parent_id:05d}{suffix}\n")
    for rel in entry.relationships:
        suffix = f" ! {names[rel.target_id]}" if rel.target_id in names else ""
        fh.write(f"relationship: {rel.type} MOD:{rel.target_id:05d}{suffix}\n")
    if entry.comment is not None:
        fh.write(f"comment: {entry.comment}\n")
    if entry.diff_mono is not None:
        fh.write(_xref("DiffMono", f"{entry.diff_mono:.6f}"))
    if entry.diff_avg is not None:
        fh.write(_xref("DiffAvg", f"{entry.diff_avg:.2f}"))
    if entry.diff_formula is not None:
        fh.write(_xref("DiffFormula", entry.diff_formula))
    if entry.mass_mono is not None:
        fh.write(_xref("MassMono", f"{entry.mass_mono:.6f}"))
    if entry.mass_avg is not None:
        fh.write(_xref("MassAvg", f"{entry.mass_avg:.2f}"))
    if entry.formula is not None:
        fh.write(_xref("Formula", entry.formula))
    if entry.origin is not None:
        fh.write(_xref("Origin", _fmt_origin(entry.origin)))
    if entry.term_spec is not None:
        fh.write(_xref("TermSpec", str(entry.term_spec)))
    if entry.source is not None:
        fh.write(_xref("Source", str(entry.source)))
    if entry.formal_charge is not None:
        fh.write(_xref("FormalCharge", _fmt_formal_charge(entry.formal_charge)))
    if entry.xref_unimod is not None:
        fh.write(_xref("Unimod", entry.xref_unimod))
    if entry.xref_uniprot_ptm is not None:
        fh.write(f"xref: uniprot.ptm:{entry.xref_uniprot_ptm}\n")
    if entry.xref_gnome is not None:
        fh.write(_xref("GNOme", entry.xref_gnome))
    if entry.xref_remap is not None:
        fh.write(_xref("Remap", f"MOD:{entry.xref_remap:05d}"))
    if entry.is_obsolete:
        fh.write("is_obsolete: true\n")
    fh.write("\n")


def write_obo(
    entries: Iterable[PsiModEntry],
    path: Path | str,
    *,
    header_lines: Iterable[str] = (),
) -> Path:
    """Write PSI-MOD entries to an OBO-format file.

    The output is suitable for re-parsing with parse_obo(). Returns the
    resolved Path.
    """
    materialized = list(entries)
    names = {e.id: e.name for e in materialized}

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        header = list(header_lines)
        if header:
            for line in header:
                fh.write(line + "\n")
            fh.write("\n")
        else:
            fh.write(_MINIMAL_HEADER)
            fh.write("\n")
        for entry in materialized:
            _write_entry(fh, entry, names)
    return out
