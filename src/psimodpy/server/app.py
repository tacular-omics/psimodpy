"""FastAPI app exposing the psimodpy database as REST and MCP."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.routing import APIRoute
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field

import psimodpy
from psimodpy.models import PsiModEntry as _Entry
from psimodpy.server.dashboard import dashboard_entries
from psimodpy.server.models import (
    EntryListResponse,
    HealthResponse,
    OriginResponse,
    PsiModEntry,
    PsiModSummary,
    SearchResponse,
    SummaryPage,
    to_psimod_entry,
    to_psimod_summary,
    to_summary_page,
)

_db = psimodpy.load()
_PACKAGE = "psimodpy"


# Render dashboard payload once at import time, reusing the database parsed above.
_DATA_JSON = json.dumps(dashboard_entries(_db), separators=(",", ":")).encode()


# Locate the static dashboard. On Vercel the function bundle includes ``docs/``
# (see vercel.json includeFiles); locally it lives at the repo root.
def _load_dashboard_html() -> str | None:
    for candidate in (
        Path.cwd() / "docs" / "index.html",
        Path(__file__).resolve().parents[3] / "docs" / "index.html",
    ):
        try:
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8")
        except OSError:
            continue
    return None


_DASHBOARD_HTML = _load_dashboard_html()


# ---------------------------------------------------------------------------
# MCP server (mounted at /, exposes its own /mcp route)
# ---------------------------------------------------------------------------


_Limit = Annotated[int, Field(ge=1, le=500)]


def _build_mcp() -> MCPServer:
    mcp = MCPServer(
        _PACKAGE,
        instructions=(
            'Query the PSI-MOD protein modification ontology. Ids look like "MOD:00046" or "46". '
            "search, get_parents, get_children and get_by_origin return bounded summaries; "
            "call get_by_id for a full entry."
        ),
    )

    @mcp.tool()
    def get_by_id(id: str) -> PsiModEntry | None:
        """Look up a PSI-MOD entry by ID. Accepts ``"46"`` or ``"MOD:00046"``; null if unknown or malformed."""
        entry = _db.get_by_id(id)
        return to_psimod_entry(entry) if entry else None

    @mcp.tool()
    def get_by_name(name: str) -> PsiModEntry | None:
        """Look up a PSI-MOD entry by exact name (case-insensitive)."""
        entry = _db.get_by_name(name)
        return to_psimod_entry(entry) if entry else None

    @mcp.tool()
    def search(query: Annotated[str, Field(min_length=1)], limit: _Limit = 25) -> list[PsiModSummary]:
        """Full-text search over names, definitions, and synonyms.

        ``query`` must be non-empty. Returns up to ``limit`` (1-500) lightweight
        summaries.  Call ``get_by_id`` on any returned ``id`` to fetch the full entry.
        """
        return [to_psimod_summary(e) for e in _db.search(query)[:limit]]

    @mcp.tool()
    def get_parents(id: str, limit: _Limit = 25) -> SummaryPage:
        """Return direct ``is_a`` parents of the given entry as summaries.

        At most ``limit`` (1-500) items; ``total`` and ``truncated`` say whether more
        exist.  Unknown or malformed ``id`` gives an empty page.  Call ``get_by_id``
        on a returned ``id`` for the full entry.
        """
        entry = _db.get_by_id(id)
        return to_summary_page(_db.get_parents(entry) if entry else [], limit)

    @mcp.tool()
    def get_children(id: str, limit: _Limit = 25) -> SummaryPage:
        """Return entries with the given entry as a direct ``is_a`` parent, as summaries.

        At most ``limit`` (1-500) items; ``total`` and ``truncated`` say whether more
        exist.  Unknown or malformed ``id`` gives an empty page.  Call ``get_by_id``
        on a returned ``id`` for the full entry.
        """
        entry = _db.get_by_id(id)
        return to_summary_page(_db.get_children(entry) if entry else [], limit)

    @mcp.tool()
    def get_by_origin(aa: str, limit: _Limit = 25) -> SummaryPage:
        """Return entries whose origin includes the given single-letter amino acid code, as summaries.

        ``aa`` is case-sensitive (``"S"``, not ``"s"``).  At most ``limit`` (1-500)
        items; ``total`` and ``truncated`` say whether more exist.  Call ``get_by_id``
        on a returned ``id`` for the full entry.
        """
        return to_summary_page(_db.get_by_origin(aa), limit)

    # The SDK's argument models silently drop unknown arguments; a misspelled or
    # renamed argument must fail instead of being ignored (same patch as peptacular).
    for tool in mcp._tool_manager.list_tools():
        tool.fn_metadata.arg_model.model_config["extra"] = "forbid"
        tool.fn_metadata.arg_model.model_rebuild(force=True)
        tool.parameters = tool.fn_metadata.arg_model.model_json_schema()

    return mcp


# Module-level instance for inspection / re-export.
mcp = _build_mcp()


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------


# Vercel doesn't fire ASGI lifespan events, and StreamableHTTPSessionManager.run()
# can only be called once per instance, so we build a fresh MCPServer per request.
class _MCPWrapper:
    async def __call__(self, scope, receive, send) -> None:
        m = _build_mcp()
        http_app = m.streamable_http_app(
            stateless_http=True,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
        async with m.session_manager.run():
            await http_app(scope, receive, send)


def _declared_query_params(route: APIRoute) -> frozenset[str]:
    """The query-parameter names ``route`` itself declares.

    Taken from the route's own parsed signature rather than from a list kept here, so a
    route added later is covered without touching this function and a renamed parameter
    cannot drift out of step with the check.
    """
    return frozenset(field.alias for field in route.dependant.query_params)


# The dashboard and its payload are opened in a browser, where a shared link may carry a
# tracking parameter, and answering 422 would hide the page over something harmless. The
# API routes are machine-facing, where ignoring a parameter is the worse failure: before
# this, `/api/entries?include_obsolet=true` answered 200 with the 1971 non-obsolete terms
# and no hint that the caller had asked for all 2116 and been refused in silence.
_UNVALIDATED_QUERY_PATHS = frozenset({"/", "/data.json"})


def _reject_unknown_query_params(request: Request) -> None:
    """422 for a query parameter the matched route does not declare.

    Registered once as an app-wide dependency, so every API route gets it and no route
    carries its own copy. A mounted sub-application does not run the parent app's
    dependencies, so the MCP endpoint at ``/mcp`` is unaffected.
    """
    route = request.scope.get("route")
    if not isinstance(route, APIRoute) or route.path in _UNVALIDATED_QUERY_PATHS:
        return
    accepted = _declared_query_params(route)
    unknown = sorted(set(request.query_params) - accepted)
    if not unknown:
        return
    names = ", ".join(repr(name) for name in unknown)
    allowed = ", ".join(sorted(accepted)) if accepted else "no query parameters"
    raise HTTPException(
        status_code=422,
        detail=f"unknown query parameter{'s' if len(unknown) > 1 else ''} {names}; {route.path} accepts: {allowed}",
    )


app = FastAPI(
    title="psimodpy API",
    description="REST + MCP interface to the PSI-MOD ontology.",
    version=psimodpy.__version__,
    dependencies=[Depends(_reject_unknown_query_params)],
)


def _rest_lookup(id: str) -> _Entry:
    """Return the entry for ``id``; HTTP 404 if it is unknown or not a PSI-MOD id."""
    entry = _db.get_by_id(id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No entry for id={id!r}")
    return entry


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> str:
    if _DASHBOARD_HTML is None:
        raise HTTPException(status_code=404, detail="Dashboard not bundled with deployment")
    return _DASHBOARD_HTML


@app.get("/data.json", include_in_schema=False)
def dashboard_data() -> Response:
    return Response(
        content=_DATA_JSON,
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True, package=_PACKAGE, version=psimodpy.__version__, count=len(_db))


@app.get("/api/entries", response_model=EntryListResponse)
def list_entries(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_obsolete: bool = Query(False),
) -> EntryListResponse:
    entries = [e for e in _db if include_obsolete or not e.is_obsolete]
    page = entries[offset : offset + limit]
    return EntryListResponse(
        total=len(entries),
        limit=limit,
        offset=offset,
        items=[to_psimod_entry(e) for e in page],
    )


@app.get("/api/entries/{id}", response_model=PsiModEntry)
def get_entry(id: str) -> PsiModEntry:
    entry = _rest_lookup(id)
    return to_psimod_entry(entry)


@app.get("/api/entries/by-name/{name:path}", response_model=PsiModEntry)
def get_entry_by_name(name: str) -> PsiModEntry:
    entry = _db.get_by_name(name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No entry for name={name!r}")
    return to_psimod_entry(entry)


@app.get("/api/entries/{id}/parents", response_model=list[PsiModEntry])
def get_entry_parents(id: str) -> list[PsiModEntry]:
    entry = _rest_lookup(id)
    return [to_psimod_entry(p) for p in _db.get_parents(entry)]


@app.get("/api/entries/{id}/children", response_model=list[PsiModEntry])
def get_entry_children(id: str) -> list[PsiModEntry]:
    entry = _rest_lookup(id)
    return [to_psimod_entry(c) for c in _db.get_children(entry)]


@app.get("/api/by-origin/{aa}", response_model=OriginResponse)
def get_entries_by_origin(aa: str) -> OriginResponse:
    entries = _db.get_by_origin(aa)
    return OriginResponse(
        origin=aa,
        count=len(entries),
        items=[to_psimod_entry(e) for e in entries],
    )


@app.get("/api/search", response_model=SearchResponse)
def search_entries(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=500),
) -> SearchResponse:
    results = _db.search(q)
    return SearchResponse(
        query=q,
        total=len(results),
        limit=limit,
        items=[to_psimod_summary(e) for e in results[:limit]],
    )


# Mount MCP at the root; its inner app exposes /mcp.
app.mount("/", _MCPWrapper())
