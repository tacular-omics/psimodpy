# psimodpy

[![CI](https://github.com/tacular-omics/psimodpy/actions/workflows/ci.yml/badge.svg)](https://github.com/tacular-omics/psimodpy/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/psimodpy)](https://pypi.org/project/psimodpy/)
[![Python](https://img.shields.io/pypi/pyversions/psimodpy)](https://pypi.org/project/psimodpy/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22926360.svg)](https://doi.org/10.5281/zenodo.22926360)

psimodpy wraps the [PSI-MOD](https://github.com/HUPO-PSI/psi-mod-CV) protein
modification ontology in a typed Python API, so proteomics tooling can look
up modifications by ID, name, mass, or amino acid without writing an OBO
parser or re-deriving elemental formulas by hand. It ships with the full
ontology bundled in, so it works fully offline.

## Highlights

- **Bundled, offline data** — 2,116 PSI-MOD terms shipped with the package; no network calls needed
- **Zero core dependencies** — pure Python, `pip install` and go
- **Typed, immutable models** with `py.typed` (PEP 561) for IDE autocomplete and static checking
- **Rich lookups** — by numeric ID, `MOD:NNNNN` accession, exact name, free-text search, amino-acid origin, or ontology parent/child relationships
- **Formula and mass helpers** computed for you (elemental composition dicts, ProForma-style formula strings)
- **Round-trip export** to TSV/CSV and back to OBO
- **[Online browser](https://tacular-omics.github.io/psimodpy/)** — search, sort, and inspect every term with clickable parent/child links, no install required
- **Optional local FastAPI + [MCP](https://modelcontextprotocol.io) server** (`pip install psimodpy[server]`) to expose the database over HTTP or to LLM tools

## Install

```bash
pip install psimodpy
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add psimodpy
```

Requires Python 3.12+. No third-party dependencies for the core package.

## Quick Example

```python
import psimodpy

db = psimodpy.load()          # bundled PSI-MOD database, no download needed
print(len(db))                # 2116

# Lookup by numeric ID or "MOD:NNNNN" accession
entry = db[46]
print(entry.name)             # O-phospho-L-serine
print(entry.origin)           # S
print(entry.diff_mono)        # 79.966331
print(entry.dict_composition)  # {'H': 1, 'O': 3, 'P': 1}
print(entry.proforma_formula)   # HO3P

# Lookup by exact name (case-insensitive)
same_entry = db.get_by_name("O-phospho-L-serine")

# Full-text search across names, definitions, and synonyms
hits = db.search("phospho")
print(len(hits))              # 99

# Every modification known to occur on a given amino acid
ser_mods = db.get_by_origin("S")
print(len(ser_mods))          # 154

# Entries whose monoisotopic mass difference is within 0.01 Da of 79.966, on S, T or Y
for entry, error in db.search_mass(79.966, site="STY")[:3]:
    print(entry.name, round(error, 4))   # O-phospho-L-serine -0.0003 ...
db.search_mass(42.010565, site="A", position="protein n-term")  # [(N-acetyl-L-alanine, ~0.0)]
```

## More

<details>
<summary>Filtering, TSV/CSV export, OBO round-trip</summary>

```python
# Filter obsolete or non-slim terms
slim = db.filter(slim_only=True, include_obsolete=False)

# Write every entry to TSV (or CSV)
db.write_tsv("psimod.tsv")
db.write_tsv("psimod.csv", delimiter=",")

# Round-trip back to PSI-MOD OBO format
db.write_obo("out/psi-mod.obo")
db2 = psimodpy.parse_obo("out/psi-mod.obo")  # identical entry count and fields
```

</details>

<details>
<summary>Local HTTP API and MCP server (<code>pip install psimodpy[server]</code>)</summary>

```bash
pip install psimodpy[server]
uvicorn psimodpy.server.app:app --reload
```

This starts a FastAPI app exposing the database as both a JSON REST API
(`GET /api/entries/{id}`, `/api/search`, `/api/by-origin/{aa}`, `/api/entries/{id}/parents`, …)
and an [MCP](https://modelcontextprotocol.io) endpoint at `POST /mcp` with
`get_by_id`, `get_by_name`, `search`, `get_parents`, `get_children`, and
`get_by_origin` tools, for pointing LLM clients directly at PSI-MOD:

```bash
claude mcp add psi-mod http://localhost:8000/mcp --transport http
```

</details>

<details>
<summary>Full API reference</summary>

| Function | Description |
|----------|-------------|
| `psimodpy.load(source=None, *, refresh=False, include_obsolete=True, cache=False)` | Load the bundled PSI-MOD database, an OBO file (`source`), or the latest release (`refresh=True`). `cache=True` parses the bundled file once and returns the same (read-only) database on later calls. |
| `psimodpy.parse_obo(path)` | Parse an OBO file into a database. |
| `psimodpy.download(dest=None, *, force=False)` | Download the latest OBO file from GitHub. |
| `psimodpy.write_tsv(entries, path, *, delimiter)` | Write entries to a TSV (or CSV) file. |
| `psimodpy.write_obo(entries, path, *, header_lines)` | Write entries back to PSI-MOD OBO format. |

**`PsiModDatabase`**: `db[id]`, `get_by_id`, `get_by_name`, `search`, `get_by_origin`,
`get_by_site`, `search_mass`, `get_parents`, `get_children`, `get_related`, `filter`,
`write_tsv`, `write_obo`, `header_lines`.

`search_mass(delta, *, tolerance=0.01, unit="da", site=None, position=None,
include_obsolete=False)` returns `(entry, delta - diff_mono)` pairs within `tolerance` Da
(edges inclusive), closest first; `site` may list several residues (`"STY"`), while
`get_by_site(site)` takes exactly one.

**`PsiModEntry`** fields: `id`, `name`, `definition`, `definition_ref`, `synonyms`, `is_a`,
`relationships`, `origin`, `diff_mono`, `diff_avg`, `diff_formula`, `mass_mono`, `mass_avg`,
`formula`, `term_spec`, `source`, `formal_charge`, `xref_unimod`, `xref_uniprot_ptm`,
`xref_gnome`, `xref_remap`, `in_slim_subset`, `is_obsolete`, plus computed
`accession` (`"MOD:00046"`), `dict_composition`, `dict_formula`, `proforma_formula`.

**Errors**: `PsimodError`, `PsimodParseError` (also a `ValueError`) for malformed OBO input, and
`PsimodKeyError` (also a `KeyError`) from `db[key]` on a miss. `get_by_id` returns `None` for an
unknown or malformed id; only `db[key]` raises.

**Data types**: `AminoAcid`, `Crosslink`, `Synonym` / `SynonymType`, `Relationship` /
`RelationshipType`, `TermSpec`, `Source`.

</details>

See [`CHANGELOG.md`](https://github.com/tacular-omics/psimodpy/blob/main/CHANGELOG.md)
for release history.

## Data Source

Term data comes from the [HUPO-PSI PSI-MOD controlled vocabulary](https://github.com/HUPO-PSI/psi-mod-CV),
maintained by the HUPO Proteomics Standards Initiative. See that repository
for the ontology's own license and citation guidance.

## Related Projects

Part of the `tacular-omics` family of proteomics PTM-vocabulary packages:

| Package | Description |
|---------|-------------|
| [unimodpy](https://github.com/tacular-omics/unimodpy) | Parse and query the UNIMOD mass spectrometry modifications database |
| [uniprotptmpy](https://github.com/tacular-omics/uniprotptmpy) | Parse and query the UniProt PTM controlled vocabulary |
| [tacular](https://github.com/tacular-omics/tacular) | Broader MS-proteomics lookup library (amino acids, elements, fragment-ion masses) that bundles its own copies of PSI-MOD alongside UNIMOD, RESID, XLMOD, GNOme, and UniProt-PTM; the base library for peptacular and paftacular |

## Citation

If psimodpy is useful in your research, please cite it — see
[`CITATION.cff`](https://github.com/tacular-omics/psimodpy/blob/main/CITATION.cff)
or use the "Cite this repository" button on GitHub. Releases are archived on
Zenodo (DOI badge above).

## License

[MIT](LICENSE)
