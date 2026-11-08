# Contributing to psimodpy

Bug reports, fixes and new features are welcome. Use the
[issue tracker](https://github.com/tacular-omics/psimodpy/issues) for bugs and
questions, with a minimal example and the psimodpy and Python versions. Report
security problems privately as described in [SECURITY.md](SECURITY.md).

## Development setup

You need Python 3.12 or newer, [uv](https://docs.astral.sh/uv/) and
[just](https://just.systems/).

```bash
git clone https://github.com/tacular-omics/psimodpy.git
cd psimodpy
just install
```

`just --list` shows the other recipes.

`just install` runs `uv sync`, which installs the core package and the dev group but not
the optional `server` extra. The server and MCP tests guard on `pytest.importorskip` at
module scope, so without that extra they are never collected: `uv run pytest tests`
collects 362 tests rather than 402, and the 40 that are missing (25 in
`tests/test_server.py`, 15 in `tests/test_mcp_vocabulary.py`) are reported as 2 skips
rather than 40, one per module, and only if you pass `-rs`. A green summary therefore says
nothing about the server. If your change touches anything under `src/psimodpy/server/`,
install the extras as well:

```bash
uv sync --all-extras
```

Install the commit hooks once per clone with `uvx pre-commit install`. On every
commit they run `ruff check`, `ruff format --check` and a few file checks
(`uvx pre-commit run --all-files` runs them on everything). Type checks and
tests are not in the hooks; run `just check` for those.

## Running checks

CI runs these on every pull request. Run them before you push:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run ty check src
uv run pytest tests            # fast default run
RUN_SLOW=1 HYPOTHESIS_PROFILE=thorough uv run pytest tests   # full run, as CI does
python scripts/release_version.py check
```

## Pull requests

- Branch from `main` and keep each pull request to one change.
- Add tests for new behaviour and fixed bugs.
- Add a line under `## [Unreleased]` in `CHANGELOG.md` for user-visible changes.
- Do not change the version number; the maintainers set it when releasing.
- CI must pass: lint, type check, tests on Python 3.12 to 3.14, and the wheel build.

## CLAUDE.md and AI agents

`CLAUDE.md` is the maintained developer guide: commands, architecture,
conventions and known gotchas. `AGENTS.md` points other coding agents to it.
Read it before a larger change, and update it in the same pull request when your
change makes part of it wrong. AI-assisted contributions are welcome; you are
responsible for reviewing and testing what you submit.
