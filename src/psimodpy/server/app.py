"""FastAPI app exposing the psimodpy database as REST and MCP."""

from __future__ import annotations

import json
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import cast

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

import psimodpy
from psimodpy.database import MassType
from psimodpy.server.dashboard import dashboard_entries
from psimodpy.server.models import (
    EntryListResponse,
    OriginResponse,
    PsiModEntry,
    PsiModSummary,
    SearchResponse,
    to_psimod_entry,
    to_psimod_summary,
)

_db = psimodpy.load()
_PACKAGE = "psimodpy"
_VERSION = _pkg_version(_PACKAGE)

_VALID_MASS_TYPES = {"diff_mono", "diff_avg", "mass_mono", "mass_avg"}

_DATA_JSON = json.dumps(dashboard_entries(), separators=(",", ":")).encode()


def _load_dashboard_html() -> str | None:
    for candidate in (
        Path.cwd() / "docs" / "index.html",
        Path(__file__).resolve().parents[3] / "docs" / "index.html",
    ):
        try:
            if candidate.is_file():
                return candidate.read_text()
        except OSError:
            continue
    return None


_DASHBOARD_HTML = _load_dashboard_html()


def _split_residues(residues: str | None) -> list[str] | None:
    if residues is None:
        return None
    parts = [r.strip() for r in residues.split(",") if r.strip()]
    return parts or None


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------


def _build_mcp() -> FastMCP:
    mcp = FastMCP(
        _PACKAGE,
        instructions="Query the PSI-MOD protein modification ontology.",
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    @mcp.tool()
    def get_by_id(id: str) -> PsiModEntry | None:
        """Look up a PSI-MOD entry by ID. Accepts ``"46"`` or ``"MOD:00046"``."""
        entry = _db.get_by_id(id)
        return to_psimod_entry(entry) if entry else None

    @mcp.tool()
    def get_by_name(name: str) -> PsiModEntry | None:
        """Look up a PSI-MOD entry by exact name (case-insensitive)."""
        entry = _db.get_by_name(name)
        return to_psimod_entry(entry) if entry else None

    @mcp.tool()
    def search(query: str, limit: int = 25) -> list[PsiModSummary]:
        """Full-text search over names, definitions, and synonyms."""
        return [to_psimod_summary(e) for e in _db.search(query)[:limit]]

    @mcp.tool()
    def find(
        text: str | None = None,
        mass_min: float | None = None,
        mass_max: float | None = None,
        mass_type: str = "diff_mono",
        residues: list[str] | None = None,
        term_spec: str | None = None,
        source: str | None = None,
        in_slim_subset: bool | None = None,
        include_obsolete: bool = False,
        limit: int = 25,
    ) -> list[PsiModSummary]:
        """Fine-grained AND-combined search.

        Filters: ``text`` (substring over name/def/synonyms), ``mass_min``/
        ``mass_max`` on the column named by ``mass_type`` (``diff_mono``,
        ``diff_avg``, ``mass_mono``, or ``mass_avg``), ``residues`` against
        the entry origin, ``term_spec`` (``"none"|"N-term"|"C-term"``),
        ``source`` (``"natural"|"artifact"|"hypothetical"``), and
        ``in_slim_subset``.  Returns up to ``limit`` summaries.
        """
        mt = mass_type if mass_type in _VALID_MASS_TYPES else "diff_mono"
        results = _db.find(
            text=text,
            mass_min=mass_min,
            mass_max=mass_max,
            mass_type=cast(MassType, mt),
            residues=residues,
            term_spec=term_spec,
            source=source,
            in_slim_subset=in_slim_subset,
            include_obsolete=include_obsolete,
            limit=limit,
        )
        return [to_psimod_summary(e) for e in results]

    @mcp.tool()
    def get_parents(id: str) -> list[PsiModEntry]:
        """Return direct ``is_a`` parents of the given entry."""
        entry = _db.get_by_id(id)
        if entry is None:
            return []
        return [to_psimod_entry(p) for p in _db.get_parents(entry)]

    @mcp.tool()
    def get_children(id: str) -> list[PsiModEntry]:
        """Return entries with the given entry as a direct ``is_a`` parent."""
        entry = _db.get_by_id(id)
        if entry is None:
            return []
        return [to_psimod_entry(c) for c in _db.get_children(entry)]

    @mcp.tool()
    def get_by_origin(aa: str) -> list[PsiModEntry]:
        """Return entries whose origin includes the given single-letter amino acid code."""
        return [to_psimod_entry(e) for e in _db.get_by_origin(aa)]

    return mcp


mcp = _build_mcp()


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------


class _MCPWrapper:
    async def __call__(self, scope, receive, send) -> None:
        m = _build_mcp()
        http_app = m.streamable_http_app()
        async with m.session_manager.run():
            await http_app(scope, receive, send)


app = FastAPI(
    title="psimodpy API",
    description="REST + MCP interface to the PSI-MOD ontology.",
    version=_VERSION,
)


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


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "package": _PACKAGE,
        "version": _VERSION,
        "count": len(_db),
    }


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
    entry = _db.get_by_id(id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No entry for id={id!r}")
    return to_psimod_entry(entry)


@app.get("/api/entries/by-name/{name}", response_model=PsiModEntry)
def get_entry_by_name(name: str) -> PsiModEntry:
    entry = _db.get_by_name(name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No entry for name={name!r}")
    return to_psimod_entry(entry)


@app.get("/api/entries/{id}/parents", response_model=list[PsiModEntry])
def get_entry_parents(id: str) -> list[PsiModEntry]:
    entry = _db.get_by_id(id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No entry for id={id!r}")
    return [to_psimod_entry(p) for p in _db.get_parents(entry)]


@app.get("/api/entries/{id}/children", response_model=list[PsiModEntry])
def get_entry_children(id: str) -> list[PsiModEntry]:
    entry = _db.get_by_id(id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No entry for id={id!r}")
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


@app.get("/api/find", response_model=list[PsiModSummary])
def find_entries(
    text: str | None = Query(None),
    mass_min: float | None = Query(None),
    mass_max: float | None = Query(None),
    mass_type: str = Query("diff_mono", pattern="^(diff_mono|diff_avg|mass_mono|mass_avg)$"),
    residues: str | None = Query(None, description="Comma-separated residue codes"),
    term_spec: str | None = Query(None),
    source: str | None = Query(None),
    in_slim_subset: bool | None = Query(None),
    include_obsolete: bool = Query(False),
    limit: int = Query(50, ge=1, le=500),
) -> list[PsiModSummary]:
    results = _db.find(
        text=text,
        mass_min=mass_min,
        mass_max=mass_max,
        mass_type=cast(MassType, mass_type),
        residues=_split_residues(residues),
        term_spec=term_spec,
        source=source,
        in_slim_subset=in_slim_subset,
        include_obsolete=include_obsolete,
        limit=limit,
    )
    return [to_psimod_summary(e) for e in results]


app.mount("/", _MCPWrapper())
