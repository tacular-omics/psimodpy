# Changelog

## [Unreleased]

### Breaking

Shared 1.0 API with unimodpy and uniprotptmpy. Deprecated names still work and emit `DeprecationWarning`; they will be removed in 2.0.

- `get_by_id` never raises: a malformed id (`"foo"`, `""`, `"MOD:abc"`) or a `bool` returns `None` (was `ValueError`; `True` used to find MOD:00001). Migration: replace `except ValueError` around `get_by_id` with an `is None` check.
- Server: a malformed id on `GET /api/entries/{id}`, `/parents`, `/children` is HTTP 404 (was 422); the MCP `get_by_id`, `get_parents`, `get_children` tools return `null` / `[]` (was a tool error).
- `dict_diff_formula` -> `dict_composition`, `proforma_diff_formula` -> `proforma_formula` (old names are deprecated aliases). Zero counts are dropped from `dict_composition` and `dict_formula`: MOD:00046 is `{"H": 1, "O": 3, "P": 1}`, was `{"C": 0, "H": 1, "N": 0, "O": 3, "P": 1}`. Migration: `comp.get(el, 0)` instead of `comp[el]`. REST/MCP entries gain `dict_composition` and `proforma_formula`; `dict_diff_formula`/`proforma_diff_formula` stay as deprecated duplicate fields. The dashboard payload (`/data.json`) key `proforma_diff_formula` is now `proforma_formula`.
- `definition_ref` has no surrounding brackets and defaults to `""`: `"ChEBI:15811, ..., Unimod:21#S"`, was `"[ChEBI:15811, ..., Unimod:21#S]"` (default `"[]"`). `write_obo` adds the brackets back. Migration: drop any `.strip("[]")`.
- `load(source=None, *, refresh=False, include_obsolete=True)`: `load(path)` replaces `load_from(path)` (deprecated); `refresh=True` downloads the latest OBO (`download(force=True)`) and loads it.
- `download_obo` -> `download(dest=None, *, force=False)` (old name is a deprecated alias). It now downloads to a temporary file and renames it, so a failed download never leaves a truncated cache file.
- New `psimodpy.errors`: `PsimodError`, and `PsimodParseError(PsimodError, ValueError)`, both exported. A malformed id, mass, charge or remap value in an OBO file raises `PsimodParseError` naming the file, line and entry (was a bare `ValueError`, or silently ignored for Remap).
- A duplicate id raises `PsimodError` in `parse_obo` and `PsiModDatabase(...)` (was: last entry silently replaced the first).
- Duplicate names: `get_by_name` returns the first non-obsolete entry with the name (was: the last one). PSI-MOD has two: "L-methionine (R)-sulfoxide" (MOD:00720, obsolete MOD:01966) and "desmosine" (MOD:01933, obsolete MOD:00949); both resolve to the non-obsolete term as before.
- An unknown synonym type, relationship type, TermSpec or Source from a newer PSI-MOD is kept as the raw string with a `UserWarning` (was: synonym/relationship silently dropped, TermSpec/Source set to `None`). `Synonym.type`, `Relationship.type`, `PsiModEntry.term_spec` and `.source` are now typed `Enum | str`.
- The parser warns (`UserWarning`) instead of silently dropping a `[Term]` without id or name, and a `def:`/`synonym:`/`is_a:`/`relationship:`/`xref:` line it cannot parse. Two consecutive `[Term]` headers no longer lose the first block.

### Added

- `PsiModDatabase(entries)` accepts any iterable of entries (was typed `list | Iterator`).
- `__version__` is in `psimodpy.__all__`.
- Server: MCP `search` validates `query` (min length 1) and `limit` (1-500), like `/api/search`. `/api/health` returns a `HealthResponse` pydantic model; dashboard rows are typed (`DashboardEntry`).
- Classifier `Development Status :: 5 - Production/Stable`.
- `PsiModDatabase.get(key, default=None)`: returns `db[key]` or `default`, never raises. `db[key]`, `db.get(key)` and `key in db` now accept the same keys and agree, as in unimodpy and uniprotptmpy.
- Tests recompute every entry's monoisotopic and average mass from its parsed formula against a frozen NIST table (pyteomics 5.0.1; generator in `tests/reference/`), plus Hypothesis property tests for the lookups. Upstream data errors found: MOD:00523, MOD:00577 and MOD:02105 masses disagree with their formulas; MOD:01982 adds the electron for its 1+ charge instead of removing it; MOD:00578 has an empty formula.

### Fixed

- `load(include_obsolete=False)` keeps `header_lines` (was empty, so `write_obo` lost the header).
- `dict_diff_formula` and `dict_formula` key isotopes like tacular, peptacular and unimodpy (`"13C"`) instead of the OBO's `"(13)C"`, so they can be passed to `peptacular.chem_mass` and agree with `proforma_diff_formula`: MOD:00452 is now `{"13C": 3, "H": 4, "O": 1}` (265 entries with isotopes; the REST/MCP `dict_*_formula` fields change the same way). `formula_to_hill` and `formula_to_proforma` accept either key style; new helper `psimodpy._formula.to_isotope_keys`.
- `db[key]` falls back to a case-insensitive name lookup (`db["O-phospho-L-serine"]`), and raises `KeyError`, not `ValueError`, for a malformed key such as `db["foo"]`; `get_by_id("foo")` returns `None` (see Breaking). A non-int/str key (`db[34.0]`, `db[None]`) now raises `KeyError` instead of resolving or raising `TypeError`, matching `34.0 in db` being False. Id strings may have surrounding whitespace.
- Hill and ProForma formulas sort an isotope with its element: MOD:00531 is now `H-1N-1[18O]`, was `H-1[18O]N-1` (14 entries).
- `34 in db` (and `"34"`, `"00034"`, `"MOD:00034"`) is now True when `db[34]` exists: `PsiModDatabase` has a `__contains__` that accepts the same keys as `db[...]` and returns False for missing or malformed keys. `entry in db` is still True for a `PsiModEntry` equal to the one stored under its id.
- `PsiModEntry.proforma_diff_formula` now writes isotopes in ProForma 2.0 syntax (`[2H8]`, `[13C6]`) instead of PSI-MOD's `(2)H8`; this affected 265 entries, e.g. MOD:00402 is now `C22[1H30][2H8]N4O6S`. New helper `psimodpy._formula.formula_to_proforma`.

## [0.2.2] (2026-09-23)

### Fixed

- Server: a malformed id (`GET /api/entries/foo`, `/parents`, `/children`) returns HTTP 422 with a clear message instead of 500; the MCP `get_by_id`, `get_parents` and `get_children` tools return a tool error.
- Server: the bundled OBO is parsed once at import instead of twice, shortening Vercel cold starts.
- Server: `/api/health` and the OpenAPI version report `psimodpy.__version__` instead of installed package metadata.
- Removed the unused `requirements.txt`; Vercel installs through `installCommand` in `vercel.json`.

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
