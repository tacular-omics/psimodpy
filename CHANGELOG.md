# Changelog

## [Unreleased]

### Fixed

- Server: a malformed id (`GET /api/entries/foo`, `/parents`, `/children`) returns HTTP 422 with a clear message instead of 500; the MCP `get_by_id`, `get_parents` and `get_children` tools return a tool error.
- Server: the bundled OBO is parsed once at import instead of twice, shortening Vercel cold starts.
- Server: `/api/health` and the OpenAPI version report `psimodpy.__version__` instead of installed package metadata.
- Removed the unused `requirements.txt`; Vercel installs through `installCommand` in `vercel.json`.
- `34 in db` (and `"34"`, `"00034"`, `"MOD:00034"`) is now True when `db[34]` exists: `PsiModDatabase` has a `__contains__` that accepts the same keys as `db[...]` and returns False for missing or malformed keys, instead of comparing against entries.
- `PsiModEntry.proforma_diff_formula` now writes isotopes in ProForma 2.0 syntax (`[2H8]`, `[13C6]`) instead of PSI-MOD's `(2)H8`; this affected 265 entries, e.g. MOD:00402 is now `C22[1H30][2H8]N4O6S`. New helper `psimodpy._formula.formula_to_proforma`.

## [0.2.1] (2026-09-23)

### Added

- Releases are archived on Zenodo (`.zenodo.json`); no code changes.

## [0.2.0] (2026-09-23)

### Added

- `write_tsv` and `write_obo` writers; the OBO header round-trips, and entries keep `scope`, `definition_ref` and `header_lines`.
- Online PSI-MOD browser (GitHub Pages) with search, sort, filter and a detail view with clickable parent and child terms.
- FastAPI REST API and MCP server (`server` extra), deployable to Vercel, which also serves the browser dashboard at the root.

### Changed

- **Breaking for the `server` extra:** the MCP server was ported from FastMCP (mcp 1.x) to `MCPServer` (mcp 2.x); it now requires mcp 2.
- MCP tools return typed responses (`structuredContent` with an `outputSchema`).
- Releases publish to PyPI by trusted publishing; the version lives only in `psimodpy.__version__`, with `CITATION.cff` kept in sync.

### Fixed

- The dashboard HTML is read as UTF-8, so it loads on Windows.
- The MCP session manager is created per request, fixing session reuse errors on Vercel.

## [0.1.2] (2026-03-27)

- Packaging and build fixes.

## [0.1.1] (2026-03-27)

- Packaging fixes; development dependencies moved to dependency groups.

## [0.1.0] (2026-03-26)

* First release on PyPI.
