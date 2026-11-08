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

psimodpy has one optional extra, `server` (`fastapi`, `uvicorn`, `mcp`, `pydantic`), and it
is not part of the dev group. `just install` runs `uv sync --all-extras`, so it installs the
extra and you get the whole test suite from that one command. A plain `uv sync` does not, and
no single number in a test run tells you which of the two you ran:

`tests/test_server.py` and `tests/test_mcp_vocabulary.py` call `pytest.importorskip` at module
scope, so without that extra their tests are not collected at all and the suite is still green.
Three things to read rather than the summary line's individual numbers, if you need to know
whether they ran:

- `uv pip list | grep -iE 'fastapi|mcp'` shows what is installed, which is the environment
  itself rather than what `pyproject.toml` declares.
- `uv run pytest tests -rs` prints the reason for every skip, naming the two modules as
  `could not import 'fastapi'` and `could not import 'mcp'`.
- The summary line does answer it once you subtract. Add up every outcome pytest reports
  (passed, failed, skipped, xfailed, xpassed, errors), leave out any subtest count, and
  subtract the number of tests collected, or the `selected` count if you deselected
  anything. The difference is the number of files skipped at collection, so it counts the
  two modules above when the extra is missing and is zero once it is installed.

Do not read the skip count as the signal. A module skipped at import counts once however many
tests it contains, so installing the extras makes the skip count go **down** while the number
of tests that actually ran goes up.

Install the commit hooks once per clone with `uvx pre-commit install`. On every
commit they run `ruff check`, `ruff format --check` and a few file checks
(`uvx pre-commit run --all-files` runs them on everything). Type checks and
tests are not in the hooks. Run `just check` for those.

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
- Do not change the version number. The maintainers set it when releasing.
- CI must pass: lint, type check, tests on Python 3.12 to 3.14, and the wheel build.

## CLAUDE.md and AI agents

`CLAUDE.md` is the maintained developer guide: commands, architecture,
conventions and known gotchas. `AGENTS.md` points other coding agents to it.
Read it before a larger change, and update it in the same pull request when your
change makes part of it wrong. AI-assisted contributions are welcome. You are
responsible for reviewing and testing what you submit.
