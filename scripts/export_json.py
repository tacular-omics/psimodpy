#!/usr/bin/env python3
"""Export the bundled PSI-MOD database to JSON for the GitHub Pages browser."""
import json
from pathlib import Path

import psimodpy
from psimodpy.models import Crosslink

db = psimodpy.load()

entries = []
for entry in db:
    if isinstance(entry.origin, Crosslink):
        origin = {"type": "crosslink", "sites": list(entry.origin.sites)}
    else:
        origin = str(entry.origin) if entry.origin is not None else None

    entries.append({
        "id": entry.id,
        "name": entry.name,
        "definition": entry.definition,
        "synonyms": [
            {"value": s.value, "type": str(s.type)} for s in entry.synonyms
        ],
        "is_a": list(entry.is_a),
        "relationships": [
            {"type": str(r.type), "target_id": r.target_id}
            for r in entry.relationships
        ],
        "origin": origin,
        "diff_mono": entry.diff_mono,
        "diff_avg": entry.diff_avg,
        "proforma_diff_formula": entry.proforma_diff_formula,
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
    })

out = Path("docs/data.json")
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(entries, separators=(",", ":")))
print(f"Exported {len(entries)} entries → {out}")
