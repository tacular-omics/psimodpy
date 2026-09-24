# psimodpy: Claude Code guide

## Project overview

psimodpy is a typed Python library for the HUPO-PSI
[PSI-MOD](https://github.com/HUPO-PSI/psi-mod-CV) protein modification ontology.
It parses the OBO file into frozen dataclasses and indexes them for lookup by ID,
`MOD:NNNNN` accession, name, free-text search, amino-acid origin and `is_a`
parents/children. The full ontology (`src/psimodpy/data/PSI-MOD.obo`, 2116 terms,
1971 non-obsolete) is bundled, so the core package works offline and has **no
runtime dependencies**.

The optional `server` extra (`fastapi`, `uvicorn`, `mcp>=2.1.1,<3`) adds a REST API
plus an MCP endpoint, deployed on Vercel at <https://psimod.tacular.dev>. A static
browser dashboard (`docs/index.html`) is served at `/` there and on GitHub Pages
(<https://tacular-omics.github.io/psimodpy/>).

Place in tacular-omics: tier 0, no sibling dependencies. Downstream users are
`peff_digest` and `peff_uniprot_fetcher` (not in the workspace). Sister packages
with the same shape: `unimodpy`, `uniprotptmpy`. `tacular` bundles its own
independent copy of PSI-MOD and does not import psimodpy.

## Commands

```bash
just install          # uv sync
just test             # uv run pytest tests            (265 tests, ~10 s)
just lint             # uv run ruff check src
just format           # ruff isort fix + ruff format on src (mutates files)
just ty               # uv run ty check src
just check            # lint + ty + test
just build            # uv build, then list the .obo files inside the wheel
just check-version    # python scripts/release_version.py check
just                  # default: lint, format, check, test
```

CI (`.github/workflows/ci.yml`) is stricter than the justfile: it runs
`ruff check src tests`, `ruff format --check src tests`, `ty check src`, the
version check, pytest on 3.12/3.13/3.14 + macOS + Windows, a `lowest-direct`
resolution job, and a wheel check that `PSI-MOD.obo` is inside the wheel.
Run `uv run ruff check src tests && uv run ruff format --check src tests` before
pushing.

Server, locally (needs the `server` extra; `uv sync --extra server` or `--all-extras`):

```bash
uv run uvicorn psimodpy.server.app:app --reload    # http://127.0.0.1:8000, docs at /docs
claude mcp add psi-mod http://localhost:8000/mcp --transport http
```

Dashboard data for GitHub Pages: `uv run --extra server python scripts/export_json.py`
writes `docs/data.json` (the Pages workflow does this; `docs/data.json` is not committed).

## Architecture

```
src/psimodpy/
  __init__.py        public re-exports + __version__ (version source of truth)
  models.py          frozen dataclasses (PsiModEntry, Synonym, Relationship, Crosslink)
                     and StrEnums (AminoAcid, SynonymType, RelationshipType, TermSpec, Source)
  parser.py          parse_obo(): line-based OBO reader -> PsiModDatabase; keeps header lines
  errors.py          PsimodError, PsimodParseError(PsimodError, ValueError), PsimodKeyError(PsimodError, KeyError)
  database.py        PsiModDatabase (indexes by id, lowercase name, origin, reverse is_a),
                     load(source=None, *, refresh, include_obsolete, cache); load_from deprecated
  _formula.py        parse_formula("C 0 H 1 O 3 P 1") -> dict; formula_to_hill(dict) -> "HO3P"
  _tabular.py        write_tsv(): fixed columns + one synonym_<type> column per type seen
  _obo_writer.py     write_obo(): round-trips through parse_obo
  _download.py       download(): fetch latest OBO from HUPO-PSI GitHub to ~/.cache/psimodpy
                     (download_obo deprecated alias)
  data/PSI-MOD.obo   bundled ontology (force-included in wheel and sdist)
  server/            optional; imports fastapi/pydantic/mcp at module import
    app.py           FastAPI app + MCPServer tools (see below)
    models.py        pydantic wire models + to_psimod_entry / to_psimod_summary converters
    references.py    parse_definition_ref(): "[PubMed:1, RESID:AA0037]" -> list[Reference]
    dashboard.py     dashboard_entries(): JSON payload for docs/index.html
api/index.py         Vercel entry point; re-exports psimodpy.server.app:app
vercel.json          installCommand `uv pip install '.[server]'`; one Python function
                     (api/index.py, maxDuration 10 s, includeFiles docs/**). No rewrites:
                     the Vercel Python runtime routes every path to the FastAPI app itself
docs/index.html      static browser; fetches relative data.json (Pages file, or the /data.json route on Vercel)
scripts/             example.py (API tour), export_json.py (docs/data.json),
                     release_version.py (shared release helper; canonical copy in workspace templates/)
```

Data flow: `load()` -> `parse_obo(bundled path)` -> `PsiModDatabase`. The server
calls `psimodpy.load()` once at import (obsolete terms included) and serves from it.

### HTTP server (`psimodpy.server.app:app`)

| method, path | returns |
|---|---|
| `GET /` | dashboard HTML (404 if `docs/index.html` is not found; not in OpenAPI) |
| `GET /data.json` | dashboard payload, `Cache-Control: public, max-age=3600` |
| `GET /api/health` | `{ok, package, version, count}` |
| `GET /api/entries?limit=50&offset=0&include_obsolete=false` | `EntryListResponse`; limit 1-500; **excludes obsolete by default** |
| `GET /api/entries/{id}` | `PsiModEntry`; `46` or `MOD:00046`; 404 if unknown or malformed |
| `GET /api/entries/by-name/{name}` | exact name, case-insensitive; 404 if unknown |
| `GET /api/entries/{id}/parents` | direct `is_a` parents |
| `GET /api/entries/{id}/children` | direct `is_a` children |
| `GET /api/by-origin/{aa}` | `OriginResponse`; `aa` is case-sensitive (`S`, not `s`) |
| `GET /api/search?q=...&limit=50` | `SearchResponse` of `PsiModSummary`; `q` required |
| `POST /mcp` | MCP streamable HTTP (stateless) |
| `GET /docs`, `/redoc`, `/openapi.json` | FastAPI defaults |

### MCP server

There is no stdio entry point. MCP is only served over HTTP at `/mcp` by the same
FastAPI app (locally via uvicorn, remotely at `https://psimod.tacular.dev/mcp`).
`_MCPWrapper` builds a fresh `MCPServer` per request (stateless, DNS-rebinding
protection off) because Vercel fires no ASGI lifespan events and
`StreamableHTTPSessionManager.run()` can run only once per instance. Module-level
`psimodpy.server.mcp` exists for inspection and tests.

Tools (return pydantic models, so clients get `structuredContent` + `outputSchema`):
`get_by_id(id)`, `get_by_name(name)`, `search(query, limit=25)` (summaries; query min length 1, limit 1-500),
`get_parents(id)`, `get_children(id)`, `get_by_origin(aa)`.

## Public API

From `psimodpy/__init__.py` (`__all__`):

- Mass search (1.1): `db.search_mass(delta, *, tolerance=0.01, unit="da", site=None, position=None)` over `diff_mono`, returns `(entry, delta - mass)` closest first; `db.get_by_site(site)`. The index and site/position rules live in `_mass.py`, identical in psimodpy, unimodpy and uniprotptmpy: keep the three copies in sync.
- Loading: `load(source=None, *, refresh=False, include_obsolete=True, cache=False)`, `parse_obo(path)`,
  `download(dest=None, *, force=False)`; deprecated `load_from(path)`, `download_obo`.
- Errors: `PsimodError`, `PsimodParseError`, `PsimodKeyError`.
- Writing: `write_tsv(entries, path, *, delimiter="\t")`,
  `write_obo(entries, path, *, header_lines=())`.
- Database: `PsiModDatabase` with `db[id]` (PsimodKeyError, a KeyError), `get_by_id`, `get_by_name`,
  `search`, `get_by_origin`, `get_parents`, `get_children`, `get_related(entry, rel_type)`,
  `filter(*, include_obsolete=False, slim_only=False)`, `write_tsv`, `write_obo`,
  `header_lines`, `len()`, iteration.
- Models: `PsiModEntry` (computed `dict_composition`, `dict_formula`, `proforma_formula`;
  deprecated `dict_diff_formula`, `proforma_diff_formula`), `Synonym`, `Relationship`, `Crosslink`.
- Enums: `AminoAcid`, `SynonymType`, `RelationshipType`, `TermSpec`, `Source`.
- `__version__`.

## Conventions

- Python >= 3.12, `from __future__ import annotations`, full type hints, `py.typed` shipped.
- Domain models are `@dataclass(frozen=True, slots=True)`; string enums are `StrEnum`.
  Field docs are bare string literals under the field.
- Docstrings: short one-liners, Google style (`Args:`, `Returns:`) when needed.
- Ruff: line length 120, rules E, W, F, I, B, UP.
- The core package must stay dependency-free. Anything needing fastapi/pydantic/mcp
  goes under `server/`; do not import `server` from core modules.
- Lookups return `None` for "not found"; only `db[id]` raises (`KeyError`).
- Tests: `tests/test_<module>.py`, session-scoped `db` fixture in `tests/conftest.py`.
  Server tests use `fastapi.testclient.TestClient` (`httpx` is in the dev group).

## Gotchas

- IDs are stored as `int`. `get_by_id` accepts `46`, `"46"` or `"MOD:00046"`; a
  malformed id (`"foo"`, `""`, a bool) returns `None`. The server answers HTTP 404
  (`/api/entries/{id}`, `/parents`, `/children`) and MCP `null` / `[]`.
- Duplicate ids raise `PsimodError`. Duplicate names (PSI-MOD has two: desmosine,
  L-methionine (R)-sulfoxide): the first non-obsolete entry wins `get_by_name`.
- `load()` includes obsolete terms (2116); `filter()` and `GET /api/entries` exclude
  them by default (1971). Obsolete terms carry `xref_remap` (replacement id).
- `get_by_origin` is exact and case-sensitive on single-letter codes. Crosslinks
  (`Crosslink(sites=("C", "C"))`) are indexed under each site; `"X"` means any residue.
- PSI-MOD formulas are space-separated with isotopes as `(13)C`, e.g.
  `"C 0 H 1 N 0 O 3 P 1"`; zero counts are dropped from `dict_composition`,
  `dict_formula` and the ProForma string.
- `Source.ARTIFACTUAL` exists because four OBO entries use that spelling.
- `definition_ref` is the citation list without brackets (`"PubMed:..., RESID:..."`,
  default `""`); the OBO writer adds the brackets back, the server splits it into `references`.
- Unknown upstream enum values (synonym type, relationship type, TermSpec, Source) are
  kept as plain strings with a `UserWarning`, so a new PSI-MOD release still loads.
- `/api/health` reports `psimodpy.__version__`, not installed package metadata.
- The server parses the OBO once at import and passes that database to
  `dashboard_entries(db)`; keep it that way, Vercel `maxDuration` is 10 s.
- `download()` does not replace the bundled data; pass its path to `load()` or use `load(refresh=True)`.
- `just format` rewrites files; CI only checks formatting.
- Vercel: without `installCommand` the runtime installs from `pyproject.toml`/`uv.lock`
  with no extras and every request fails with `ModuleNotFoundError: fastapi`. A
  catch-all rewrite to `/api/index` makes every request 404. Keep both as they are.

## Releasing

Only the tacular-omics overseer bumps versions or publishes. See `just --list`
(`set-version`, `sync-version`, `check-version`). The version lives only in
`src/psimodpy/__init__.py` (`__version__`, read by `[tool.hatch.version]`);
`scripts/release_version.py sync` copies it to `CITATION.cff`. Changelog:
`CHANGELOG.md`. A GitHub release triggers `publish.yml` (PyPI trusted publishing);
Zenodo archives releases (`.zenodo.json`). Vercel deploys through its Git
integration (config is `vercel.json`; nothing in `.github/workflows`).

## Workspace note

This repo is also developed inside the tacular-omics uv workspace
(`~/Repos/tacular-omics/packages/psimodpy`); there `uv run` uses the shared `.venv`
and root `uv.lock`, not this repo's `uv.lock`. See the workspace CLAUDE.md.
