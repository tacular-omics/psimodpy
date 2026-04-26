"""HTTP API and MCP server for psimodpy.

Optional install: ``pip install psimodpy[server]``.

Run locally::

    uvicorn psimodpy.server.app:app --reload

Endpoints:
    GET  /api/health
    GET  /api/entries
    GET  /api/entries/{id}
    GET  /api/entries/by-name/{name}
    GET  /api/entries/{id}/parents
    GET  /api/entries/{id}/children
    GET  /api/by-origin/{aa}
    GET  /api/search?q=...
    POST /mcp                          (Model Context Protocol)
"""

from psimodpy.server.app import app, mcp

__all__ = ["app", "mcp"]
