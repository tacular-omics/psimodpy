"""FastAPI app exposing the psimodpy database as REST and MCP."""

from __future__ import annotations

from contextlib import asynccontextmanager
from importlib.metadata import version as _pkg_version

from fastapi import FastAPI, HTTPException, Query
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

import psimodpy
from psimodpy.server.schemas import serialize_entry

_db = psimodpy.load()
_PACKAGE = "psimodpy"
_VERSION = _pkg_version(_PACKAGE)


# ---------------------------------------------------------------------------
# MCP server (mounted at /, exposes its own /mcp route)
# ---------------------------------------------------------------------------

mcp = FastMCP(
    _PACKAGE,
    instructions="Query the PSI-MOD protein modification ontology.",
    stateless_http=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@mcp.tool()
def get_by_id(id: str) -> dict | None:
    """Look up a PSI-MOD entry by ID. Accepts ``"46"`` or ``"MOD:00046"``."""
    entry = _db.get_by_id(id)
    return serialize_entry(entry) if entry else None


@mcp.tool()
def get_by_name(name: str) -> dict | None:
    """Look up a PSI-MOD entry by exact name (case-insensitive)."""
    entry = _db.get_by_name(name)
    return serialize_entry(entry) if entry else None


@mcp.tool()
def search(query: str, limit: int = 25) -> list[dict]:
    """Full-text search over names, definitions, and synonyms. Returns up to ``limit`` results."""
    return [serialize_entry(e) for e in _db.search(query)[:limit]]


@mcp.tool()
def get_parents(id: str) -> list[dict]:
    """Return direct ``is_a`` parents of the given entry."""
    entry = _db.get_by_id(id)
    if entry is None:
        return []
    return [serialize_entry(p) for p in _db.get_parents(entry)]


@mcp.tool()
def get_children(id: str) -> list[dict]:
    """Return entries with the given entry as a direct ``is_a`` parent."""
    entry = _db.get_by_id(id)
    if entry is None:
        return []
    return [serialize_entry(c) for c in _db.get_children(entry)]


@mcp.tool()
def get_by_origin(aa: str) -> list[dict]:
    """Return entries whose origin includes the given single-letter amino acid code."""
    return [serialize_entry(e) for e in _db.get_by_origin(aa)]


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(_: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="psimodpy API",
    description="REST + MCP interface to the PSI-MOD ontology.",
    version=_VERSION,
    lifespan=_lifespan,
)


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "package": _PACKAGE,
        "version": _VERSION,
        "count": len(_db),
    }


@app.get("/api/entries")
def list_entries(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_obsolete: bool = Query(False),
) -> dict:
    entries = [e for e in _db if include_obsolete or not e.is_obsolete]
    page = entries[offset : offset + limit]
    return {
        "total": len(entries),
        "limit": limit,
        "offset": offset,
        "items": [serialize_entry(e) for e in page],
    }


@app.get("/api/entries/{id}")
def get_entry(id: str) -> dict:
    entry = _db.get_by_id(id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No entry for id={id!r}")
    return serialize_entry(entry)


@app.get("/api/entries/by-name/{name}")
def get_entry_by_name(name: str) -> dict:
    entry = _db.get_by_name(name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No entry for name={name!r}")
    return serialize_entry(entry)


@app.get("/api/entries/{id}/parents")
def get_entry_parents(id: str) -> list[dict]:
    entry = _db.get_by_id(id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No entry for id={id!r}")
    return [serialize_entry(p) for p in _db.get_parents(entry)]


@app.get("/api/entries/{id}/children")
def get_entry_children(id: str) -> list[dict]:
    entry = _db.get_by_id(id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No entry for id={id!r}")
    return [serialize_entry(c) for c in _db.get_children(entry)]


@app.get("/api/by-origin/{aa}")
def get_entries_by_origin(aa: str) -> dict:
    entries = _db.get_by_origin(aa)
    return {"origin": aa, "count": len(entries), "items": [serialize_entry(e) for e in entries]}


@app.get("/api/search")
def search_entries(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    results = _db.search(q)
    return {
        "query": q,
        "total": len(results),
        "limit": limit,
        "items": [serialize_entry(e) for e in results[:limit]],
    }


# Mount MCP at the root; its inner app exposes /mcp.
app.mount("/", mcp.streamable_http_app())
