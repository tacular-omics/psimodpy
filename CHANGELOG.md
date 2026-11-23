# Changelog

## [Unreleased]

### Fixed

- Preserve raw non-term OBO stanzas through parsing, filtered loading and OBO export,
  so relationship definitions and unknown stanza kinds are not silently lost.

- Every `/api/*` route answers an unknown query parameter with HTTP 422 naming it and listing
  what the route accepts, instead of ignoring it and answering 200. A misspelling was the
  worst of it: `/api/entries?include_obsolet=true` returned the 1971 non-obsolete terms with
  nothing to say the caller's request for all 2116 had been dropped. The accepted names come
  from each route's own signature, so a route added later is covered without a list to
  maintain. `/` and `/data.json` keep ignoring stray parameters, because a shared dashboard
  link may carry a tracking one and hiding the page over that would be worse; the `/mcp`
  endpoint is a mounted sub-application and does not run app dependencies, so it is
  unaffected. **Who sees a difference:** a client that sends a parameter psimodpy never read
  now gets a 422 where it used to get an answer to a different question.

### Added

- `PsiModEntry.replaced_by` holds the ids from the OBO `replaced_by` tags of an obsolete term,
  and `PsiModDatabase.resolve` follows that tag when PSI-MOD's own `xref: Remap` is absent, so
  an obsolete term that names its replacement the standard way now resolves to it. The OBO 1.4
  guide says the tag "Gives a term which replaces an obsolete term" and that its value "can
  safely be used to automatically reassign instances". `write_obo` writes the tag back, after
  `is_obsolete`, because the guide allows it only on obsolete terms. The tag is also read from
  files whose terms carry several of them, but `resolve` stops at such a term, because the
  guide permits more than one and they name no single replacement; read the attribute in that
  case. The `consider` tag is still not read: the guide makes it a suggestion for a human
  expert to review, not a replacement. **Who sees a difference:** anyone loading an OBO file
  that uses `replaced_by`, which today means upstream's own `PSI-MOD.obo` (one term, MOD:00306
  to MOD:02119) and `PSI-MOD-newstyle.obo` (67 terms). The bundled ontology has none, so
  `load()` with no argument is unchanged.
- `PsiModEntry.xref_smiles` holds the `xref: Smiles` value, an OpenSMILES string for the whole
  modified residue, which was read as nothing and dropped by `write_obo`. The CV's own field
  table defines the key as "An OpenSMILES string encoding the full modified residue (residue +
  modification(s)) with `*` to indicate the backbone bonds", and it is the only key in that
  table psimodpy did not model. **Who sees a difference:** anyone loading upstream's
  `PSI-MOD.obo`, which carries 133 of these lines, or writing such a file back out, where the
  line used to disappear. The bundled snapshot carries none, so `load()` with no argument is
  unchanged. The key is matched as the CV's README and its released files spell it, `Smiles`;
  the 2025-04-03 annotation-rules PDF writes `xref: smiles:` in lower case, and no lower-case
  spelling occurs in any released file, so no second spelling is accepted. One hazard comes
  with the field and is not worked around: OpenSMILES uses a backslash as a bond symbol, and a
  backslash in an OBO value is an escape introducer, so an unescaped `C/C=C\n1cccc1` reads
  back with a newline in it. No upstream value contains a backslash today; a file that writes
  one has to escape it as `\\`, which psimodpy reads and writes correctly.
- `PsiModDatabase.get_ancestors(entry)`, `get_descendants(entry)` and `is_descendant_of(entry,
  ancestor)` follow `is_a` transitively. They take an entry or any id `get_by_id` takes and
  return each term once, breadth-first (direct parents or children first, in `get_parents` /
  `get_children` order), using a visited set so the 1194 terms with several parents are not
  revisited and an `is_a` cycle ends. A term is not its own ancestor, descendant or
  `is_descendant_of` itself; an unknown or malformed id gives `[]` / `False`. `get_parents`,
  `get_children`, `search_mass` and the REST and MCP tools are unchanged. Thanks @ritanjay.

### Fixed

- `is_obsolete` now accepts OBO 1.4 trailing comments, modifiers and whitespace after
  `true` or `false`. Previously these lines were dropped as unrecognised and an
  obsolete term could incorrectly load as active. Invalid boolean values still
  produce a warning. **Who sees a difference:** callers parsing external OBO
  files with annotated `is_obsolete` tags; the bundled PSI-MOD data is unchanged.

- OBO parser now warns about every `[Term]` line whose tag no rule handles, such as
  `consider:`, `alt_id:`, `property_value:`, `creation_date:` or a `subset:` value other than
  `PSI-MOD-slim`, instead of dropping those lines silently. One grouped warning per tag names
  the tag, how many lines carried it and the first of them, like the existing
  unrecognised-line warnings; the entry still parses. Leading whitespace is stripped before
  grouping, and lines that are not tag-shaped share one `(no tag)` warning rather than one
  warning each. A comment line is not reported: the OBO guide says lines beginning with `!`
  "are ignored by parsers". Nor is `is_obsolete: false`, which is the tag's legal default.
  **Who sees a difference:** anyone loading a file that uses tags psimodpy does not read -
  upstream's `PSI-MOD-newstyle.obo` is the case that matters, where 16,236 `property_value:`
  lines carry every mass, formula, origin and source and used to vanish without a word.
  `load()` on the bundled ontology still emits no warnings. Thanks @draarivpatel-ui.

## [1.3.0] (2026-11-16)

### Added

- `PsiModDatabase.resolve(id)` follows `xref_remap` from an obsolete term to its current
  term (`MOD:00407` gives `MOD:00599`), a live term resolves to itself and an unknown id gives
  `None`. It takes the ids `get_by_id` takes. It tracks visited ids, so a self-redirect
  (`MOD:01123`) or any longer cycle ends; a chain that dies on an obsolete term with no
  redirect (`MOD:00580` to `MOD:00579`) or redirects to an id not in the database returns the
  last term reached, so check `is_obsolete` on the result.

### Fixed

- `write_tsv` now writes a `definition_ref` column, the citation list of each definition
  (`ChEBI:15811, ..., RESID:AA0037`, as stored on `entry.definition_ref`), which it used to
  drop. It is appended after `xrefs_unimod`, so every existing column keeps its position and
  the header has 37 columns instead of 36.
- A source with no `[Term]` stanza no longer loads as an empty database. `parse_obo` (and so
  `load`) raises `PsimodParseError`, naming the file, for an HTML error page, an empty file, a
  plain-text file, a header-only file or a file with only `[Typedef]` stanzas, where it used
  to return an empty database that answered every lookup with `None` or `[]`. `download()`
  now parses the file before it renames it into place, so a 200 response carrying an error
  page, bytes that are not UTF-8 text, or a file the parser rejects for a malformed value or
  a duplicate id raises `PsimodParseError` naming the destination instead of being cached: an
  existing cache file is left untouched, no `.part` file remains, and `load(refresh=True)` no
  longer keeps returning an empty database until the cache file is deleted by hand.
  **Behaviour change:** writing an empty database with `write_obo` and reading it back now
  raises instead of returning an empty database. `PsiModDatabase([])` still constructs, and
  the bundled database still loads with 2116 entries.
- `GET /api/entries/by-name/{name}` now finds the nine modifications whose names hold a
  `/`, such as `oxazole/thiazole ring crosslinked residues` (MOD:00690). The path parameter
  matched a single segment, so those requests fell through to the MCP mount and answered a
  bare `404 Not Found` instead of the entry.
- OBO parser and writer now decode and escape OBO 1.2 escape sequences (`\n`, `\W`, `\t`,
  `\:`, `\,`, `\"`, `\\`, `\(`, `\)`, `\[`, `\]`, `\{`, `\}`) in quoted and
  free-text fields, so names, definitions, synonyms, comments and xrefs containing quotes,
  backslashes, brackets, newlines or tabs round-trip intact instead of corrupting or dropping
  values.
- An `xref:` line that carries an OBO trailing modifier (`{...}`) or a trailing `! comment` is
  no longer dropped. `xref: Unimod: "Unimod:34" ! note` was reported with a `UserWarning` and
  lost, costing the term its `xref_unimod`, `xref_remap`, `xref_uniprot_ptm` or `xref_gnome`;
  it now parses to the same value as the plain form. `def:` and `synonym:` lines already
  tolerated both. The bundled ontology carries no trailing modifier or comment on an `xref:`
  line, so only files from elsewhere were affected.

### Changed

- A `def:`, `synonym:` or `xref:` line whose quoted value holds an **unescaped** quote is now
  reported with a `UserWarning` and dropped, where it used to be silently truncated at that
  quote. A file written by psimodpy 1.2.0 or earlier that holds such a value is affected: a
  definition of `A 5" [sic] rod` was written unescaped and read back as `A 5` with a
  `definition_ref` of `sic`, and now reads back as `""` with the line named in the warning.
  Re-write the file with this version to get the escaped, re-readable form.
- `definition_ref` keeps the escapes that carry citation-list syntax (`\,` `\"` `\{` `\}`
  `\\`, and `\W`/`\t` next to a separator) and decodes only the content ones, because the
  field is one flat string in which a decoded `\,` could not be told from the comma between
  two citations. A `definition_ref` that is not a citation list is therefore re-encoded once
  into its escaped form (`DB:a}b` becomes `DB:a\}b`) and is unchanged by every later round
  trip. Genuine citation lists, which is all the ontology carries, round-trip byte for byte.

## [1.2.0] (2026-11-06)

### Changed

- `server` extra: corrected the remaining floors to the lowest versions that actually
  resolve together and pass the suite - `fastapi>=0.110.1` (was `>=0.115`) and
  `mcp>=2.0.0,<3` (was `>=2.1.1,<3`). No change to what the package does.
- `server` extra: `pydantic>=2.12,<3`. The server has always imported pydantic at module
  level and never declared it. It only arrived transitively through fastapi and mcp. The
  floor is the one mcp already requires, so nothing resolves differently: the import is
  declared instead of inherited.

### Fixed

- The TSV/CSV export kept only the first synonym of each type for an entry and dropped the
  rest: 1579 of the ontology's 7288 synonyms, across 590 entries. MOD:00014 alone has 12
  `RESID-alternate` synonyms, of which 11 were lost. Each `synonym_<type>` column now holds
  every synonym of that type, in file order, separated by `" | "`. That separator is not the
  `"; "` the other multi-value columns use, because 35 synonym values contain `"; "`
  themselves and such a column could not be split back. The columns and their order are
  unchanged.
- `server` extra: `uvicorn>=0.30` could not be installed. mcp requires `uvicorn>=0.31.1`
  on every platform but emscripten, so no resolution of the extra contained a 0.30.x, and
  `--resolution lowest-direct` silently stepped over the declared floor - the floor was
  unreachable rather than merely untested. Now `uvicorn>=0.31.1`. On emscripten, where mcp
  does not require uvicorn, this does raise the floor.
- `search_mass`: adding `position` to a query could add hits instead of removing them. The
  terminus-slot rule read `position=None` as "neither terminus is open", which made the
  least-constrained query the narrowest one. Both termini are now open for `position=None`
  and closed for `position="anywhere"`, so `position` only ever removes matches. For
  PSI-MOD data this changes no result. A slot's sites come from `origin` residues only,
  never from `N-term` or `C-term`, so the rule could not fire here - a sweep of 1140
  result sets is identical before and after. `tests/test_position_narrows.py` is the guard
  that keeps it that way, because the same mass-search module ships in unimodpy and
  uniprotptmpy, where the rule does fire.

## [1.1.3] (2026-10-26)

### Changed

- Updated development and test dependencies. No changes to the library.

## [1.1.2] (2026-10-08)

### Fixed

- Entries that list more than one Unimod xref kept only the last one (MOD:01506, MOD:01507 and MOD:01509 list both `Unimod:214` and `Unimod:889`). New `PsiModEntry.xrefs_unimod` holds every Unimod xref in file order (`()` when none). `xref_unimod` is unchanged. The TSV/CSV export gains an `xrefs_unimod` column (`; `-separated), appended as the last column so existing columns keep their positions, the REST/MCP entry model and the dashboard data gain `xrefs_unimod`, the browser site shows every Unimod xref, and `write_obo` writes them all. No other xref kind is repeated with different values in PSI-MOD.

## [1.1.1] (2026-09-25)

### Added

- Browser site (`docs/index.html`): mass search. Enter a signed delta mass, a tolerance in Da or ppm (ppm is relative to a precursor mass you enter) and monoisotopic or average mass. It combines with the text search, adds a sortable Δ error column (closest first) and keeps its state in the URL (`?mass=42.0106&tol=0.01&unit=da`). Same matching rule as `search_mass()`. `scripts/test_mass_search.py` checks it headless against `search_mass()` (needs Playwright).

### Changed

- Browser site restyled to the shared tacular-omics style (plain academic layout, labelled units, light and dark themes). The footer shows the package version the data came from.
- The source distribution now contains only the source, tests and the README, changelog, citation and license files: no paper, docs, lockfile or repository tooling.

## [1.1.0] (2026-09-24)

Additive only for the Python API: nothing that worked in 1.0 changes behaviour. The MCP list tools change shape (see Changed).

### Added

- `load(cache=True)`: parse the bundled OBO once per process (one database per `include_obsolete` value) and return that same database on later `load(cache=True)` calls. The database is shared by every such caller: do not modify it. Combining `cache=True` with `source` or `refresh=True` raises `ValueError`. The default (`cache=False`) still parses anew on each call.
- `PsimodKeyError(PsimodError, KeyError)`, exported: `db[key]` raises it on a miss. It is still a `KeyError`, not a `ValueError` (so `except KeyError` and `db.get` work as before) and `args[0]` is still the key.
- `search_mass(delta, *, tolerance=0.01, tolerance_unit="da", site=None, position=None, include_obsolete=False) -> list[tuple[entry, float]]`: entries whose `diff_mono` (monoisotopic mass difference) is within `tolerance` of `delta`, as `(entry, error)` pairs with `error = delta - mass`, closest first (ties in mass, then file order). `tolerance_unit` accepts only `"da"` (exact, lowercase): ppm is not offered because a ppm window on a delta mass is ill-defined, and the keyword keeps the call shape of `tacular.tolerance` so units can be added later. Both window edges are inclusive. Entries without a mass are skipped, and so are obsolete terms unless `include_obsolete=True`. `site` is one or more residue letters (`"S"`, `"STY"`, any case; any of them matches, while `get_by_site` takes exactly one) or `"N-term"`/`"C-term"`, matched against the entry's origin residues (`origin`; crosslinks list each residue). `position` is where the residue was observed: `"anywhere"`, `"peptide n-term"`, `"peptide c-term"`, `"protein n-term"`, `"protein c-term"` (case-insensitive; `"Any N-term"`/`"Any C-term"` are aliases for the peptide ones). It is matched against PSI-MOD's N-term/C-term flag (`term_spec`), which does not say protein or peptide: an N-terminal mod matches both `"peptide n-term"` and `"protein n-term"`. Entries with no flag count as anywhere. A modification of the terminus itself matches any residue at that terminus. A sorted mass index is built on the first call, and each search is a bisect. A bad `site`, `position`, `tolerance_unit`, `delta` or `tolerance` raises `PsimodError`.
- `get_by_site(site)`: the same as `get_by_origin(site.strip().upper())` (kept), named to match unimodpy and uniprotptmpy, with each entry listed once (a `"S, S"` crosslink appears twice in `get_by_origin("S")`). It takes exactly one residue (`search_mass(site=)` takes several). Unknown or non-string input returns `[]`.
- `PsiModEntry.get_mass(*, monoisotopic=True) -> float | None`: the mass difference in Da, `diff_mono` (default) or `diff_avg` (`monoisotopic=False`), with the same keyword as tacular 2.0's `get_mass`. The old attributes stay. `search_mass` uses it.

### Changed

- `search()` is several times faster: each entry's lowercased name, definition and synonyms are joined once when the database is built, so a query is one substring test per entry instead of lowercasing every field on every call. Results and their order are unchanged (tested against the 1.0 algorithm).
- MCP server (`server` extra): `get_by_origin`, `get_children` and `get_parents` now take `limit` (default 25, 1-500) and return a page `{total, limit, truncated, items}` of summaries (`id`, `accession`, `name`, `mass_mono`, `is_obsolete`, the same shape as `search`) instead of an unbounded list of full entries. `get_by_origin("S")` was 557 KB. It is now about 3 KB (all 154 entries with `limit=500`: about 21 KB). Call `get_by_id` for the full entry. An unknown id gives an empty page (was `[]`). The REST routes are unchanged. This is the one MCP-visible break in this release. The hosted server (psimod.tacular.dev, the claude.ai PSIMOD connector) picks it up on redeploy.
- MCP server: unknown tool arguments are rejected with a tool error (were silently ignored), and the server instructions now say what ids look like and that list tools return summaries.
- `import psimodpy` no longer imports `urllib.request` (and with it `http.client`, `ssl`, `email`): it is imported when `download()` runs, saving about 30 ms at import.

## [1.0.0] (2026-09-23)

First stable release: the public API is now stable and follows semantic versioning.

### Breaking

Shared 1.0 API with unimodpy and uniprotptmpy. Deprecated names still work and emit `DeprecationWarning`. They will be removed in 2.0.

- `get_by_id` never raises: a malformed id (`"foo"`, `""`, `"MOD:abc"`) or a `bool` returns `None` (was `ValueError`; `True` used to find MOD:00001). Migration: replace `except ValueError` around `get_by_id` with an `is None` check.
- Server: a malformed id on `GET /api/entries/{id}`, `/parents`, `/children` is HTTP 404 (was 422). The MCP `get_by_id`, `get_parents`, `get_children` tools return `null` / `[]` (was a tool error).
- `dict_diff_formula` -> `dict_composition`, `proforma_diff_formula` -> `proforma_formula` (old names are deprecated aliases). Zero counts are dropped from `dict_composition` and `dict_formula`: MOD:00046 is `{"H": 1, "O": 3, "P": 1}`, was `{"C": 0, "H": 1, "N": 0, "O": 3, "P": 1}`. Migration: `comp.get(el, 0)` instead of `comp[el]`. REST/MCP entries gain `dict_composition` and `proforma_formula`. The dashboard payload (`/data.json`) key `proforma_diff_formula` is now `proforma_formula`.
- `definition_ref` has no surrounding brackets and defaults to `""`: `"ChEBI:15811, ..., Unimod:21#S"`, was `"[ChEBI:15811, ..., Unimod:21#S]"` (default `"[]"`). `write_obo` adds the brackets back. Migration: drop any `.strip("[]")`.
- `load(source=None, *, refresh=False, include_obsolete=True)`: `load(path)` replaces `load_from(path)` (deprecated). `refresh=True` downloads the latest OBO (`download(force=True)`) and loads it. `load(source, refresh=True)` raises `ValueError("pass either source or refresh=True, not both")`, as in uniprotptmpy (was: `refresh` silently ignored).
- REST/MCP entries no longer carry the deprecated duplicate fields `proforma_diff_formula` and `dict_diff_formula`. Migration: read `proforma_formula` and `dict_composition`. The Python properties `PsiModEntry.proforma_diff_formula` / `.dict_diff_formula` remain as deprecated aliases.
- Bundled PSI-MOD updated from 1.032.4 to 1.039.0 (2116 terms, 1971 non-obsolete, was 1996; 145 obsolete, was 120; 788 non-obsolete PSI-MOD-slim, was 811). Upstream now gives the neutral formula mass for charged entries (`FormalCharge` set; 170 mass values, e.g. MOD:00049 `DiffMono` 143.117890 -> 143.118438), and fixed the mass errors in MOD:00472, MOD:00523, MOD:00577, MOD:01982, MOD:02019, MOD:02022-02024, MOD:02100-02102 and MOD:02105. `xref: uniprot.ptm` is now quoted like the other xrefs. Both forms are read, and `write_obo` writes the quoted form.
- `download_obo` -> `download(dest=None, *, force=False)` (old name is a deprecated alias). It now downloads to a temporary file and renames it, so a failed download never leaves a truncated cache file.
- New `psimodpy.errors`: `PsimodError`, and `PsimodParseError(PsimodError, ValueError)`, both exported. A malformed id, mass, charge or remap value in an OBO file raises `PsimodParseError` naming the file, line and entry (was a bare `ValueError`, or silently ignored for Remap).
- A duplicate id raises `PsimodError` in `parse_obo` and `PsiModDatabase(...)` (was: last entry silently replaced the first).
- Duplicate names: `get_by_name` returns the first non-obsolete entry with the name (was: the last one). PSI-MOD has two: "L-methionine (R)-sulfoxide" (MOD:00720, obsolete MOD:01966) and "desmosine" (MOD:01933, obsolete MOD:00949). Both resolve to the non-obsolete term as before.
- An unknown synonym type, relationship type, TermSpec or Source from a newer PSI-MOD is kept as the raw string with a `UserWarning` (was: synonym/relationship silently dropped, TermSpec/Source set to `None`). `Synonym.type`, `Relationship.type`, `PsiModEntry.term_spec` and `.source` are now typed `Enum | str`.
- The parser warns (`UserWarning`) instead of silently dropping a `[Term]` without id or name, and a `def:`/`synonym:`/`is_a:`/`relationship:`/`xref:` line it cannot parse. Two consecutive `[Term]` headers no longer lose the first block.

### Added

- `PsiModEntry.accession`: `"MOD:00696"`, matching the REST/MCP `accession` field and uniprotptmpy's `PtmEntry.accession`.
- `PsiModDatabase(entries)` accepts any iterable of entries (was typed `list | Iterator`).
- `__version__` is in `psimodpy.__all__`.
- Server: MCP `search` validates `query` (min length 1) and `limit` (1-500), like `/api/search`. `/api/health` returns a `HealthResponse` pydantic model. Dashboard rows are typed (`DashboardEntry`).
- Classifier `Development Status :: 5 - Production/Stable`.
- `PsiModDatabase.get(key, default=None)`: returns `db[key]` or `default`, never raises. `db[key]`, `db.get(key)` and `key in db` now accept the same keys and agree, as in unimodpy and uniprotptmpy.
- Tests recompute every entry's monoisotopic and average mass from its parsed formula against a frozen NIST table (pyteomics 5.0.1; generator in `tests/reference/`), plus Hypothesis property tests for the lookups. Upstream data errors found: MOD:00523, MOD:00577 and MOD:02105 masses disagreed with their formulas; MOD:01982 added the electron for its 1+ charge instead of removing it; MOD:00578 had an empty formula (all fixed in PSI-MOD 1.039.0).

### Fixed

- The parser accepts an empty xref value (`xref: DiffFormula: ""`, 58 lines in PSI-MOD 1.039.0) and treats it as absent (`None`). It used to drop the line with a `UserWarning`.
- `scripts/release_version.py sync --set X.Y.Z` also sets `date-released` in `CITATION.cff` to today (adding the field if missing).
- `get_by_name` returns `None` and `search` returns `[]` for a non-string argument (was `AttributeError`), as in unimodpy and uniprotptmpy.
- `load(include_obsolete=False)` keeps `header_lines` (was empty, so `write_obo` lost the header).
- `dict_diff_formula` and `dict_formula` key isotopes like tacular, peptacular and unimodpy (`"13C"`) instead of the OBO's `"(13)C"`, so they can be passed to `peptacular.chem_mass` and agree with `proforma_diff_formula`: MOD:00452 is now `{"13C": 3, "H": 4, "O": 1}` (265 entries with isotopes; the REST/MCP `dict_*_formula` fields change the same way). `formula_to_hill` and `formula_to_proforma` accept either key style; new helper `psimodpy._formula.to_isotope_keys`.
- `db[key]` falls back to a case-insensitive name lookup (`db["O-phospho-L-serine"]`), and raises `KeyError`, not `ValueError`, for a malformed key such as `db["foo"]`. `get_by_id("foo")` returns `None` (see Breaking). A non-int/str key (`db[34.0]`, `db[None]`) now raises `KeyError` instead of resolving or raising `TypeError`, matching `34.0 in db` being False. Id strings may have surrounding whitespace.
- Hill and ProForma formulas sort an isotope with its element: MOD:00531 is now `H-1N-1[18O]`, was `H-1[18O]N-1` (14 entries).
- `34 in db` (and `"34"`, `"00034"`, `"MOD:00034"`) is now True when `db[34]` exists: `PsiModDatabase` has a `__contains__` that accepts the same keys as `db[...]` and returns False for missing or malformed keys. `entry in db` is still True for a `PsiModEntry` equal to the one stored under its id.
- `PsiModEntry.proforma_diff_formula` now writes isotopes in ProForma 2.0 syntax (`[2H8]`, `[13C6]`) instead of PSI-MOD's `(2)H8`. This affected 265 entries, e.g. MOD:00402 is now `C22[1H30][2H8]N4O6S`. New helper `psimodpy._formula.formula_to_proforma`.

## [0.2.2] (2026-09-23)

### Fixed

- Server: a malformed id (`GET /api/entries/foo`, `/parents`, `/children`) returns HTTP 422 with a clear message instead of 500. The MCP `get_by_id`, `get_parents` and `get_children` tools return a tool error.
- Server: the bundled OBO is parsed once at import instead of twice, shortening Vercel cold starts.
- Server: `/api/health` and the OpenAPI version report `psimodpy.__version__` instead of installed package metadata.
- Removed the unused `requirements.txt`. Vercel installs through `installCommand` in `vercel.json`.

## [0.2.1] (2026-09-23)

### Added

- Releases are archived on Zenodo (`.zenodo.json`). No code changes.

## [0.2.0] (2026-09-23)

### Added

- `write_tsv` and `write_obo` writers. The OBO header round-trips, and entries keep `scope`, `definition_ref` and `header_lines`.
- Online PSI-MOD browser (GitHub Pages) with search, sort, filter and a detail view with clickable parent and child terms.
- FastAPI REST API and MCP server (`server` extra), deployable to Vercel, which also serves the browser dashboard at the root.

### Changed

- **Breaking for the `server` extra:** the MCP server was ported from FastMCP (mcp 1.x) to `MCPServer` (mcp 2.x). It now requires mcp 2.
- MCP tools return typed responses (`structuredContent` with an `outputSchema`).
- Releases publish to PyPI by trusted publishing. The version lives only in `psimodpy.__version__`, with `CITATION.cff` kept in sync.

### Fixed

- The dashboard HTML is read as UTF-8, so it loads on Windows.
- The MCP session manager is created per request, fixing session reuse errors on Vercel.

## [0.1.2] (2026-03-27)

- Packaging and build fixes.

## [0.1.1] (2026-03-27)

- Packaging fixes. Development dependencies moved to dependency groups.

## [0.1.0] (2026-03-26)

* First release on PyPI.
