#!/usr/bin/env python3
"""Export the bundled PSI-MOD database to JSON for the GitHub Pages browser."""
import json
from pathlib import Path

import psimodpy
from psimodpy.server.dashboard import dashboard_entries

entries = dashboard_entries()

out = Path("docs/data.json")
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(entries, separators=(",", ":")))
print(f"Exported {len(entries)} entries → {out}")

# Package version for the page footer (the Vercel app serves /api/health instead).
meta = out.parent / "meta.json"
meta.write_text(json.dumps({"package": "psimodpy", "version": psimodpy.__version__}))
print(f"Wrote {meta}")
