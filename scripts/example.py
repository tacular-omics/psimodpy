"""Demonstrate the psimodpy API with practical examples."""

from __future__ import annotations

import psimodpy
from psimodpy.models import RelationshipType, SynonymType


def print_entry(entry: psimodpy.PsiModEntry) -> None:
    obsolete_tag = " [OBSOLETE]" if entry.is_obsolete else ""
    slim_tag = " [slim]" if entry.in_slim_subset else ""
    print(f"MOD:{entry.id:05d}  {entry.name}{obsolete_tag}{slim_tag}")
    print(f"  definition    : {entry.definition}")

    if entry.synonyms:
        # Group synonyms by type for readability
        by_type: dict[str, list[str]] = {}
        for syn in entry.synonyms:
            by_type.setdefault(syn.type, []).append(syn.value)
        for syn_type, values in by_type.items():
            print(f"  {syn_type:<22}: {', '.join(values)}")

    if entry.comment:
        print(f"  comment       : {entry.comment}")

    if entry.origin is not None:
        from psimodpy.models import Crosslink
        if isinstance(entry.origin, Crosslink):
            print(f"  origin        : {', '.join(entry.origin.sites)}")
        else:
            print(f"  origin        : {entry.origin}")
    if entry.term_spec is not None:
        print(f"  term_spec     : {entry.term_spec}")
    if entry.source is not None:
        print(f"  source        : {entry.source}")
    if entry.formal_charge is not None:
        sign = "+" if entry.formal_charge > 0 else ""
        print(f"  formal_charge : {sign}{entry.formal_charge}")

    if entry.diff_mono is not None:
        print(f"  diff_mono     : {entry.diff_mono:+.6f} Da")
    if entry.diff_avg is not None:
        print(f"  diff_avg      : {entry.diff_avg:+.4f} Da")
    if entry.diff_formula is not None:
        print(f"  diff_formula  : {entry.diff_formula}")
        comp = entry.dict_diff_formula
        pf = entry.proforma_diff_formula
        if comp:
            nonzero = {k: v for k, v in comp.items() if v != 0}
            print(f"  diff_comp     : {nonzero}")
        if pf:
            print(f"  proforma      : {pf}")
    if entry.mass_mono is not None:
        print(f"  mass_mono     : {entry.mass_mono:.6f} Da")
    if entry.formula is not None:
        print(f"  formula       : {entry.formula}")

    if entry.xref_unimod is not None:
        print(f"  xref_unimod   : {entry.xref_unimod}")
    if entry.xref_uniprot_ptm is not None:
        print(f"  xref_uniprot  : {entry.xref_uniprot_ptm}")
    if entry.xref_gnome is not None:
        print(f"  xref_gnome    : {entry.xref_gnome}")
    if entry.xref_remap is not None:
        print(f"  remap         : MOD:{entry.xref_remap:05d}")

    if entry.is_a:
        print(f"  is_a          : {', '.join(f'MOD:{p:05d}' for p in entry.is_a)}")
    if entry.relationships:
        for rel in entry.relationships:
            print(f"  {rel.type:<22}: MOD:{rel.target_id:05d}")

    print()


def section(title: str) -> None:
    bar = "=" * 60
    print(f"\n{bar}")
    print(f"  {title}")
    print(f"{bar}\n")


def main() -> None:
    db = psimodpy.load()
    print(f"Loaded {len(db)} PSI-MOD entries.\n")
    print(f"  Non-obsolete : {len(db.filter(include_obsolete=False))}")
    print(f"  PSI-MOD-slim : {len(db.filter(slim_only=True))}")

    # ------------------------------------------------------------------ #
    # 1. Root entry
    # ------------------------------------------------------------------ #
    section("Root entry (MOD:00000)")
    print_entry(db[0])

    # ------------------------------------------------------------------ #
    # 2. A well-known modification: O-phospho-L-serine
    # ------------------------------------------------------------------ #
    section("A classic PTM: O-phospho-L-serine (MOD:00046)")
    print_entry(db[46])

    # ------------------------------------------------------------------ #
    # 3. Multi-parent entry
    # ------------------------------------------------------------------ #
    section("Multi-parent entry: O-glycosyl-L-serine (MOD:00002)")
    entry = db[2]
    print_entry(entry)
    print("  Parents:")
    for parent in db.get_parents(entry):
        print(f"    MOD:{parent.id:05d}  {parent.name}")
    print()

    # ------------------------------------------------------------------ #
    # 4. Modification with derives_from relationship
    # ------------------------------------------------------------------ #
    section("derives_from: hypusine (MOD:00125)")
    hypusine = db[125]
    print_entry(hypusine)
    precursors = db.get_related(hypusine, RelationshipType.DERIVES_FROM)
    if precursors:
        print("  Derives from:")
        for p in precursors:
            print(f"    MOD:{p.id:05d}  {p.name}")
    print()

    # ------------------------------------------------------------------ #
    # 5. Composite modification with contains relationship
    # ------------------------------------------------------------------ #
    section("contains: L-cysteine glutathione disulfide (MOD:00234)")
    glut = db[234]
    print_entry(glut)
    components = db.get_related(glut, RelationshipType.CONTAINS)
    if components:
        print("  Contains:")
        for c in components:
            print(f"    MOD:{c.id:05d}  {c.name}")
    print()

    # ------------------------------------------------------------------ #
    # 6. Crosslink (two-residue origin)
    # ------------------------------------------------------------------ #
    section("Crosslink origin 'C, C': MOD:00229")
    print_entry(db[229])

    # ------------------------------------------------------------------ #
    # 7. Lookup by origin — all serine modifications
    # ------------------------------------------------------------------ #
    section("get_by_origin('S') — first 5 serine modifications")
    ser_mods = db.get_by_origin("S")
    print(f"  {len(ser_mods)} modifications with origin 'S'\n")
    for entry in ser_mods[:5]:
        print(f"  MOD:{entry.id:05d}  {entry.name}")
    print()

    # ------------------------------------------------------------------ #
    # 8. Search
    # ------------------------------------------------------------------ #
    section("search('acetyl') — first 5 results")
    hits = db.search("acetyl")
    print(f"  {len(hits)} results for 'acetyl'\n")
    for entry in hits[:5]:
        print(f"  MOD:{entry.id:05d}  {entry.name}")
    print()

    # ------------------------------------------------------------------ #
    # 9. Isotopic formula parsing
    # ------------------------------------------------------------------ #
    section("Isotopic formula: diphthamide (MOD:00049)")
    print_entry(db[49])

    # ------------------------------------------------------------------ #
    # 10. Obsolete entry with remap
    # ------------------------------------------------------------------ #
    section("Obsolete entry with remap redirect")
    obsolete_with_remap = [e for e in db if e.is_obsolete and e.xref_remap is not None]
    if obsolete_with_remap:
        print_entry(obsolete_with_remap[0])
        target = db.get_by_id(obsolete_with_remap[0].xref_remap)
        if target:
            print(f"  Remapped to: MOD:{target.id:05d}  {target.name}\n")

    # ------------------------------------------------------------------ #
    # 11. Children of a node
    # ------------------------------------------------------------------ #
    section("Children of 'O-glycosylated residue' (MOD:00396) — first 5")
    parent = db[396]
    children = db.get_children(parent)
    print(f"  {len(children)} children\n")
    for child in children[:5]:
        print(f"  MOD:{child.id:05d}  {child.name}")
    print()

    # ------------------------------------------------------------------ #
    # 12. PSI-MOD-slim filter
    # ------------------------------------------------------------------ #
    section("PSI-MOD-slim subset — first 5 entries with origin 'K'")
    from psimodpy.models import AminoAcid, Crosslink
    slim_k = [
        e for e in db.filter(slim_only=True)
        if (isinstance(e.origin, AminoAcid) and e.origin == AminoAcid.LYS)
        or (isinstance(e.origin, Crosslink) and "K" in e.origin.sites)
    ]
    print(f"  {len(slim_k)} slim entries with origin 'K'\n")
    for entry in slim_k[:5]:
        print(f"  MOD:{entry.id:05d}  {entry.name}")
    print()


if __name__ == "__main__":
    main()
