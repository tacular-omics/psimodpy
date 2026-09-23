# Copilot instructions

The canonical guide for this repo is [`CLAUDE.md`](../CLAUDE.md) (commands,
architecture, public API, server/MCP, gotchas). Read it first.

Key rules:

1. Use `just` recipes, else `uv run ...`. Never install with pip/npm; never bump the
   version, tag or publish (the tacular-omics overseer releases).
2. The core package has zero runtime dependencies. fastapi, pydantic and mcp may only
   be imported under `src/psimodpy/server/`.
3. Do not hand-edit `src/psimodpy/data/PSI-MOD.obo`; it is the bundled upstream ontology.
4. Before pushing, CI must pass: `uv run ruff check src tests`,
   `uv run ruff format --check src tests`, `uv run ty check src`, `uv run pytest tests`.
5. Keep REST routes and MCP tools in `server/app.py` in sync with each other and
   with the pydantic models in `server/models.py`.
