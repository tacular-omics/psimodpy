# psimodpy

[![CI](https://github.com/tacular-omics/psimodpy/actions/workflows/ci.yml/badge.svg)](https://github.com/tacular-omics/psimodpy/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/psimodpy)](https://pypi.org/project/psimodpy/)
[![Python](https://img.shields.io/pypi/pyversions/psimodpy)](https://pypi.org/project/psimodpy/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Python library for parsing and querying the [PSI-MOD](https://github.com/HUPO-PSI/psi-mod-CV) protein modification ontology.

- Zero dependencies
- Bundled PSI-MOD data (2,116 entries) — works offline out of the box
- Typed, immutable data models (`py.typed` / PEP 561)
- TSV/CSV export and round-trip OBO writer

## Online Viewer
#### [Click Me!](https://tacular-omics.github.io/psimodpy/)

## Installation

```bash
pip install psimodpy
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add psimodpy
```

Requires Python 3.12+. No third-party dependencies.

## Quick Start

```python
import psimodpy

# Load the bundled PSI-MOD database
db = psimodpy.load()

# Lookup by ID
entry = db[46]  # O-phospho-L-serine
print(entry.name)       # "O-phospho-L-serine"
print(entry.diff_mono)  # 79.966331
print(entry.origin)     # AminoAcid.SER

# Lookup by name (case-insensitive)
entry = db.get_by_name("O-phospho-L-serine")

# Also accepts MOD:NNNNN format
entry = db.get_by_id("MOD:00046")

# Search across names, definitions, and synonyms
results = db.search("phospho")

# Find all modifications for an amino acid
ser_mods = db.get_by_origin("S")

# Filter entries
slim = db.filter(slim_only=True, include_obsolete=False)

# Formula parsing
print(entry.dict_diff_formula)      # {'C': 0, 'H': 0, 'N': 0, 'O': 3, 'P': 1}
print(entry.proforma_diff_formula)  # 'O3P'
```

## Exporting to TSV/CSV

```python
# Write all entries to a tab-separated file
db.write_tsv("psimod.tsv")

# Or CSV
db.write_tsv("psimod.csv", delimiter=",")

# Standalone function
from psimodpy import write_tsv
write_tsv(db, "psimod.tsv")
```

The TSV includes one row per entry. Dynamic synonym columns (e.g. `synonym_psi_mod_label`,
`synonym_omssa_label`) are added for each `SynonymType` found in the data.

## Writing back to OBO format

```python
# Round-trip: write entries back to PSI-MOD OBO format
db.write_obo("out/psi-mod.obo")

# Re-parse — identical entry count and field values
db2 = psimodpy.parse_obo("out/psi-mod.obo")

# Standalone function; pass original header lines for a faithful round-trip
from psimodpy import write_obo
write_obo(db, "out/psi-mod.obo", header_lines=db.header_lines)
```

## API Overview

### Loading

| Function | Description |
|----------|-------------|
| `psimodpy.load()` | Load the bundled PSI-MOD database. |
| `psimodpy.load_from(path)` | Load from a custom OBO file. |
| `psimodpy.parse_obo(path)` | Parse an OBO file into a database. |
| `psimodpy.download_obo()` | Download the latest OBO file from GitHub. |
| `psimodpy.write_tsv(entries, path, *, delimiter)` | Write entries to a TSV (or CSV) file. |
| `psimodpy.write_obo(entries, path, *, header_lines)` | Write entries back to PSI-MOD OBO format. |

### PsiModDatabase

| Method | Description |
|--------|-------------|
| `db[id]` | Lookup by ID (int or `"MOD:00046"`), raises `KeyError`. |
| `db.get_by_id(id)` | Lookup by ID, returns `None` if missing. |
| `db.get_by_name(name)` | Case-insensitive name lookup. |
| `db.search(query)` | Full-text search in names, definitions, synonyms. |
| `db.get_by_origin(aa)` | Find entries by amino acid origin. |
| `db.get_parents(entry)` | Direct parent entries (is_a hierarchy). |
| `db.get_children(entry)` | Direct child entries. |
| `db.get_related(entry, type)` | Follow relationship edges (derives_from, contains, etc.). |
| `db.filter(...)` | Filter by obsolete/slim status. |
| `db.write_tsv(path, *, delimiter)` | Write all entries to a TSV (or CSV) file. |
| `db.write_obo(path)` | Write all entries back to OBO format. |
| `db.header_lines` | Original header lines from the parsed OBO file. |

### PsiModEntry

Each entry provides: `id`, `name`, `definition`, `definition_ref`, `synonyms`, `is_a`, `relationships`,
`origin`, `diff_mono`, `diff_avg`, `diff_formula`, `mass_mono`, `mass_avg`, `formula`,
`term_spec`, `source`, `formal_charge`, `xref_unimod`, `xref_uniprot_ptm`, `xref_gnome`,
`xref_remap`, `in_slim_subset`, `is_obsolete`.

Computed properties: `dict_diff_formula`, `dict_formula`, `proforma_diff_formula`.

Each `Synonym` has: `value`, `type` (`SynonymType`), `scope` (e.g. `"EXACT"`, `"RELATED"`).

### Data Types

- `AminoAcid` — single-letter amino acid codes
- `Crosslink` — multi-residue or MOD-referenced origins
- `Synonym` / `SynonymType` — typed synonyms
- `Relationship` / `RelationshipType` — directed relationships
- `TermSpec` — positional specificity
- `Source` — modification origin

## Development

```bash
just install   # install dependencies with uv
just lint      # ruff check
just format    # ruff format
just ty        # ty type check
just test      # pytest
just check     # lint + type check + test
```

## Related Projects

| Package | Description |
|---------|-------------|
| [unimodpy](https://github.com/tacular-omics/unimodpy) | Parse and query the UNIMOD mass spectrometry modifications database |
| [uniprotptmpy](https://github.com/tacular-omics/uniprotptmpy) | Parse and query the UniProt PTM controlled vocabulary |

## License

[MIT](LICENSE)
