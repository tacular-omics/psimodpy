# psimodpy

[![CI](https://github.com/tacular-omics/psimodpy/actions/workflows/ci.yml/badge.svg)](https://github.com/tacular-omics/psimodpy/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/psimodpy)](https://pypi.org/project/psimodpy/)
[![Python](https://img.shields.io/pypi/pyversions/psimodpy)](https://pypi.org/project/psimodpy/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Python library for parsing and querying the [PSI-MOD](https://github.com/HUPO-PSI/psi-mod-CV) protein modification ontology.

- Zero core dependencies
- Bundled PSI-MOD data (2,116 entries) — works offline out of the box
- Typed, immutable data models (`py.typed` / PEP 561)
- TSV/CSV export and round-trip OBO writer
- Optional FastAPI / [Model Context Protocol](https://modelcontextprotocol.io) server (`pip install psimodpy[server]`)

## Online Viewer
#### [Click Me!](https://tacular-omics.github.io/psimodpy/)

The same database is also reachable as a hosted REST + MCP service — see
[HTTP API and MCP Server](#http-api-and-mcp-server) below.

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

## HTTP API and MCP Server

The optional `[server]` extra ships a FastAPI app that exposes the same
database over a JSON REST API *and* over the
[Model Context Protocol](https://modelcontextprotocol.io) so language-model
tools can query PSI-MOD directly.

```bash
pip install psimodpy[server]
uvicorn psimodpy.server.app:app --reload
```

### REST endpoints

| Method & path | Returns |
|---------------|---------|
| `GET /api/health` | Service metadata and entry count. |
| `GET /api/entries?limit=&offset=&include_obsolete=` | Paginated full entries. |
| `GET /api/entries/{id}` | One full entry by ID (`46` or `MOD:00046`). |
| `GET /api/entries/by-name/{name}` | One full entry by exact name. |
| `GET /api/entries/{id}/parents` | Direct `is_a` parents. |
| `GET /api/entries/{id}/children` | Direct `is_a` children. |
| `GET /api/by-origin/{aa}` | Entries with the given amino-acid origin. |
| `GET /api/search?q=&limit=` | Search hits as lightweight summaries. |

Full entry payloads include `references` parsed from `definition_ref` into
`{type, accession, value}` objects and a typed `origin` object (either
`{type: "amino_acid", code}` or `{type: "crosslink", sites}`). Search
responses contain just `{id, accession, name, mass_mono, is_obsolete}` to
keep token cost low; call `/api/entries/{id}` on any hit for the full
record.

### MCP server

The same FastAPI app mounts an MCP endpoint at `POST /mcp` with these tools:

| Tool | Purpose |
|------|---------|
| `get_by_id(id)` | Look up a single entry. |
| `get_by_name(name)` | Exact name lookup. |
| `search(query, limit=25)` | Full-text search returning summaries. |
| `get_parents(id)` | Direct `is_a` parents of an entry. |
| `get_children(id)` | Direct `is_a` children of an entry. |
| `get_by_origin(aa)` | Entries with the given amino-acid origin. |

Tool responses use MCP's structured-output mechanism: the server emits an
`outputSchema` per tool in `tools/list` and returns both `structuredContent`
(typed Pydantic instance) and `content` (text fallback) on `tools/call`, so
LLM clients can parse the response without re-reading the JSON string.

Configure your MCP-aware client to point at `http://localhost:8000/mcp`
(or wherever you deploy the app). Example with the Anthropic CLI:

```bash
claude mcp add psi-mod http://localhost:8000/mcp --transport http
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
