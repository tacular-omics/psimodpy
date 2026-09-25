# Changelog

## [Unreleased]

## [1.1.1] (2026-09-25)

### Added

- Browser site (`docs/index.html`): mass search. Enter a signed delta mass, a tolerance in Da or ppm (ppm is relative to a precursor mass you enter) and monoisotopic or average mass; it combines with the text search, adds a sortable Δ error column (closest first) and keeps its state in the URL (`?mass=42.0106&tol=0.01&unit=da`). Same matching rule as `search_mass()`. `scripts/test_mass_search.py` checks it headless against `search_mass()` (needs Playwright).

### Changed

- Browser site restyled to the shared tacular-omics style (plain academic layout, labelled units, light and dark themes); the footer shows the package version the data came from.
- The source distribution now contains only the source, tests and the README, changelog, citation and license files: no paper, docs, lockfile or repository tooling.

## [1.1.0] (2026-09-24)

Additive only for the Python API: nothing that worked in 1.0 changes behaviour. The MCP list tools change shape (see Changed).

### Added

- `load(cache=True)`: parse the bundled OBO once per process (one database per `include_obsolete` value) and return that same database on later `load(cache=True)` calls. The database is shared by every such caller: do not modify it. Combining `cache=True` with `source` or `refresh=True` raises `ValueError`. The default (`cache=False`) still parses anew on each call.
- `PsimodKeyError(PsimodError, KeyError)`, exported: `db[key]` raises it on a miss. It is still a `KeyError`, not a `ValueError` (so `except KeyError` and `db.get` work as before) and `args[0]` is still the key.
- `search_mass(delta, *, tolerance=0.01, tolerance_unit="da", site=None, position=None, include_obsolete=False) -> list[tuple[entry, float]]`: entries whose `diff_mono` (monoisotopic mass difference) is within `tolerance` of `delta`, as `(entry, error)` pairs with `error = delta - mass`, closest first (ties in mass, then file order). `tolerance_unit` accepts only `"da"` (exact, lowercase): ppm is not offered because a ppm window on a delta mass is ill-defined, and the keyword keeps the call shape of `tacular.tolerance` so units can be added later. Both window edges are inclusive. Entries without a mass are skipped, and so are obsolete terms unless `include_obsolete=True`. `site` is one or more residue letters (`"S"`, `"STY"`, any case; any of them matches, while `get_by_site` takes exactly one) or `"N-term"`/`"C-term"`, matched against the entry's origin residues (`origin`; crosslinks list each residue). `position` is where the residue was observed: `"anywhere"`, `"peptide n-term"`, `"peptide c-term"`, `"protein n-term"`, `"protein c-term"` (case-insensitive; `"Any N-term"`/`"Any C-term"` are aliases for the peptide ones); it is matched against PSI-MOD's N-term/C-term flag (`term_spec`), which does not say protein or peptide: an N-terminal mod matches both `"peptide n-term"` and `"protein n-term"`. Entries with no flag count as anywhere. A modification of the terminus itself matches any residue at that terminus. A sorted mass index is built on the first call, and each search is a bisect. A bad `site`, `position`, `tolerance_unit`, `delta` or `tolerance` raises `PsimodError`.
- `get_by_site(site)`: the same as `get_by_origin(site.strip().upper())` (kept), named to match unimodpy and uniprotptmpy, with each entry listed once (a `"S, S"` crosslink appears twice in `get_by_origin("S")`). It takes exactly one residue (`search_mass(site=)` takes several). Unknown or non-string input returns `[]`.
- `PsiModEntry.get_mass(*, monoisotopic=True) -> float | None`: the mass difference in Da, `diff_mono` (default) or `diff_avg` (`monoisotopic=False`), with the same keyword as tacular 2.0's `get_mass`. The old attributes stay. `search_mass` uses it.

### Changed

- `search()` is several times faster: each entry's lowercased name, definition and synonyms are joined once when the database is built, so a query is one substring test per entry instead of lowercasing every field on every call. Results and their order are unchanged (tested against the 1.0 algorithm).
- MCP server (`server` extra): `get_by_origin`, `get_children` and `get_parents` now take `limit` (default 25, 1-500) and return a page `{total, limit, truncated, items}` of summaries (`id`, `accession`, `name`, `mass_mono`, `is_obsolete`, the same shape as `search`) instead of an unbounded list of full entries. `get_by_origin("S")` was 557 KB; it is now about 3 KB (all 154 entries with `limit=500`: about 21 KB). Call `get_by_id` for the full entry. An unknown id gives an empty page (was `[]`). The REST routes are unchanged. This is the one MCP-visible break in this release; the hosted server (psimod.tacular.dev, the claude.ai PSIMOD connector) picks it up on redeploy.
- MCP server: unknown tool arguments are rejected with a tool error (were silently ignored), and the server instructions now say what ids look like and that list tools return summaries.
- `import psimodpy` no longer imports `urllib.request` (and with it `http.client`, `ssl`, `email`): it is imported when `download()` runs, saving about 30 ms at import.

## [1.0.0] (2026-09-23)

First stable release: the public API is now stable and follows semantic versioning.

### Breaking

Shared 1.0 API with unimodpy and uniprotptmpy. Deprecated names still work and emit `DeprecationWarning`; they will be removed in 2.0.

- `get_by_id` never raises: a malformed id (`"foo"`, `""`, `"MOD:abc"`) or a `bool` returns `None` (was `ValueError`; `True` used to find MOD:00001). Migration: replace `except ValueError` around `get_by_id` with an `is None` check.
- Server: a malformed id on `GET /api/entries/{id}`, `/parents`, `/children` is HTTP 404 (was 422); the MCP `get_by_id`, `get_parents`, `get_children` tools return `null` / `[]` (was a tool error).
- `dict_diff_formula` -> `dict_composition`, `proforma_diff_formula` -> `proforma_formula` (old names are deprecated aliases). Zero counts are dropped from `dict_composition` and `dict_formula`: MOD:00046 is `{"H": 1, "O": 3, "P": 1}`, was `{"C": 0, "H": 1, "N": 0, "O": 3, "P": 1}`. Migration: `comp.get(el, 0)` instead of `comp[el]`. REST/MCP entries gain `dict_composition` and `proforma_formula`. The dashboard payload (`/data.json`) key `proforma_diff_formula` is now `proforma_formula`.
- `definition_ref` has no surrounding brackets and defaults to `""`: `"ChEBI:15811, ..., Unimod:21#S"`, was `"[ChEBI:15811, ..., Unimod:21#S]"` (default `"[]"`). `write_obo` adds the brackets back. Migration: drop any `.strip("[]")`.
- `load(source=None, *, refresh=False, include_obsolete=True)`: `load(path)` replaces `load_from(path)` (deprecated); `refresh=True` downloads the latest OBO (`download(force=True)`) and loads it. `load(source, refresh=True)` raises `ValueError("pass either source or refresh=True, not both")`, as in uniprotptmpy (was: `refresh` silently ignored).
- REST/MCP entries no longer carry the deprecated duplicate fields `proforma_diff_formula` and `dict_diff_formula`. Migration: read `proforma_formula` and `dict_composition`. The Python properties `PsiModEntry.proforma_diff_formula` / `.dict_diff_formula` remain as deprecated aliases.
- Bundled PSI-MOD updated from 1.032.4 to 1.039.0 (2116 terms, 1971 non-obsolete, was 1996; 145 obsolete, was 120; 788 non-obsolete PSI-MOD-slim, was 811). Upstream now gives the neutral formula mass for charged entries (`FormalCharge` set; 170 mass values, e.g. MOD:00049 `DiffMono` 143.117890 -> 143.118438), and fixed the mass errors in MOD:00472, MOD:00523, MOD:00577, MOD:01982, MOD:02019, MOD:02022-02024, MOD:02100-02102 and MOD:02105. `xref: uniprot.ptm` is now quoted like the other xrefs; both forms are read, and `write_obo` writes the quoted form.
- `download_obo` -> `download(dest=None, *, force=False)` (old name is a deprecated alias). It now downloads to a temporary file and renames it, so a failed download never leaves a truncated cache file.
- New `psimodpy.errors`: `PsimodError`, and `PsimodParseError(PsimodError, ValueError)`, both exported. A malformed id, mass, charge or remap value in an OBO file raises `PsimodParseError` naming the file, line and entry (was a bare `ValueError`, or silently ignored for Remap).
- A duplicate id raises `PsimodError` in `parse_obo` and `PsiModDatabase(...)` (was: last entry silently replaced the first).
- Duplicate names: `get_by_name` returns the first non-obsolete entry with the name (was: the last one). PSI-MOD has two: "L-methionine (R)-sulfoxide" (MOD:00720, obsolete MOD:01966) and "desmosine" (MOD:01933, obsolete MOD:00949); both resolve to the non-obsolete term as before.
- An unknown synonym type, relationship type, TermSpec or Source from a newer PSI-MOD is kept as the raw string with a `UserWarning` (was: synonym/relationship silently dropped, TermSpec/Source set to `None`). `Synonym.type`, `Relationship.type`, `PsiModEntry.term_spec` and `.source` are now typed `Enum | str`.
- The parser warns (`UserWarning`) instead of silently dropping a `[Term]` without id or name, and a `def:`/`synonym:`/`is_a:`/`relationship:`/`xref:` line it cannot parse. Two consecutive `[Term]` headers no longer lose the first block.

### Added

- `PsiModEntry.accession`: `"MOD:00696"`, matching the REST/MCP `accession` field and uniprotptmpy's `PtmEntry.accession`.
- `PsiModDatabase(entries)` accepts any iterable of entries (was typed `list | Iterator`).
- `__version__` is in `psimodpy.__all__`.
- Server: MCP `search` validates `query` (min length 1) and `limit` (1-500), like `/api/search`. `/api/health` returns a `HealthResponse` pydantic model; dashboard rows are typed (`DashboardEntry`).
- Classifier `Development Status :: 5 - Production/Stable`.
- `PsiModDatabase.get(key, default=None)`: returns `db[key]` or `default`, never raises. `db[key]`, `db.get(key)` and `key in db` now accept the same keys and agree, as in unimodpy and uniprotptmpy.
- Tests recompute every entry's monoisotopic and average mass from its parsed formula against a frozen NIST table (pyteomics 5.0.1; generator in `tests/reference/`), plus Hypothesis property tests for the lookups. Upstream data errors found: MOD:00523, MOD:00577 and MOD:02105 masses disagreed with their formulas; MOD:01982 added the electron for its 1+ charge instead of removing it; MOD:00578 had an empty formula (all fixed in PSI-MOD 1.039.0).

### Fixed

- The parser accepts an empty xref value (`xref: DiffFormula: ""`, 58 lines in PSI-MOD 1.039.0) and treats it as absent (`None`); it used to drop the line with a `UserWarning`.
- `scripts/release_version.py sync --set X.Y.Z` also sets `date-released` in `CITATION.cff` to today (adding the field if missing).
- `get_by_name` returns `None` and `search` returns `[]` for a non-string argument (was `AttributeError`), as in unimodpy and uniprotptmpy.
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
