"""End-to-end MCP + REST shape tests for the psimodpy server.

The MCP tests deliberately *don't* enter ``TestClient`` as a context manager,
so no ASGI lifespan events fire.  This mirrors how Vercel's serverless
runtime invokes the app — every request is a cold ASGI call — and catches
regressions in our per-request session lifecycle handling alongside
structural guarantees about the new typed responses.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("mcp")

from fastapi.testclient import TestClient  # noqa: E402

from psimodpy.server.app import app  # noqa: E402
from psimodpy.server.models import PsiModEntry, PsiModSummary  # noqa: E402
from psimodpy.server.references import parse_definition_ref  # noqa: E402

_MCP_HEADERS = {"accept": "application/json, text/event-stream"}
_INIT_PARAMS = {
    "protocolVersion": "2025-06-18",
    "capabilities": {},
    "clientInfo": {"name": "pytest", "version": "0"},
}


def _parse_sse(body: str) -> dict[str, Any]:
    for line in body.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    raise AssertionError(f"no data: line in SSE body: {body!r}")


def _mcp(client: TestClient, method: str, params: dict | None = None, *, req_id: int = 1) -> dict[str, Any]:
    payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
    r = client.post("/mcp", json=payload, headers=_MCP_HEADERS)
    assert r.status_code == 200, f"{method} returned {r.status_code}: {r.text}"
    return _parse_sse(r.text)


@pytest.fixture
def mcp_client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# References parser
# ---------------------------------------------------------------------------


def test_parse_definition_ref_handles_bracketed_list() -> None:
    refs = parse_definition_ref("[PubMed:18688235, RESID:AA0037, Unimod:21#S]")
    assert [(r.type, r.accession) for r in refs] == [
        ("PubMed", "18688235"),
        ("RESID", "AA0037"),
        ("Unimod", "21#S"),
    ]


def test_parse_definition_ref_empty_returns_empty_list() -> None:
    assert parse_definition_ref("") == []
    assert parse_definition_ref(None) == []
    assert parse_definition_ref("[]") == []


def test_parse_definition_ref_unbracketed_input_still_parses() -> None:
    refs = parse_definition_ref("PubMed:1234")
    assert [(r.type, r.accession) for r in refs] == [("PubMed", "1234")]


# ---------------------------------------------------------------------------
# tools/list — outputSchema is emitted for every tool
# ---------------------------------------------------------------------------


def test_tools_list_includes_output_schema(mcp_client: TestClient) -> None:
    _mcp(mcp_client, "initialize", _INIT_PARAMS)
    resp = _mcp(mcp_client, "tools/list", req_id=2)
    tools = {t["name"]: t for t in resp["result"]["tools"]}
    assert set(tools) == {
        "get_by_id",
        "get_by_name",
        "search",
        "get_parents",
        "get_children",
        "get_by_origin",
    }
    for name, tool in tools.items():
        assert tool.get("outputSchema"), f"{name} is missing outputSchema"


# ---------------------------------------------------------------------------
# tools/call — both content and structuredContent
# ---------------------------------------------------------------------------


def test_get_by_id_returns_structured_content(mcp_client: TestClient) -> None:
    _mcp(mcp_client, "initialize", _INIT_PARAMS)
    resp = _mcp(
        mcp_client,
        "tools/call",
        {"name": "get_by_id", "arguments": {"id": "46"}},
        req_id=2,
    )
    result = resp["result"]
    assert result["content"], "text fallback content missing"
    assert result["content"][0]["type"] == "text"
    sc = result["structuredContent"]
    entry = sc["result"]
    assert entry is not None
    PsiModEntry.model_validate(entry)
    assert entry["accession"] == "MOD:00046"
    assert isinstance(entry["references"], list)
    assert entry["references"], "MOD:00046 should have parsed references"
    assert entry["references"][0]["type"] in {"PubMed", "RESID", "ChEBI", "OMSSA", "DeltaMass", "Unimod"}


def test_get_by_id_missing_returns_null_result(mcp_client: TestClient) -> None:
    _mcp(mcp_client, "initialize", _INIT_PARAMS)
    resp = _mcp(
        mcp_client,
        "tools/call",
        {"name": "get_by_id", "arguments": {"id": "9999999"}},
        req_id=2,
    )
    sc = resp["result"]["structuredContent"]
    assert sc == {"result": None}


def test_search_returns_summaries_not_full_entries(mcp_client: TestClient) -> None:
    _mcp(mcp_client, "initialize", _INIT_PARAMS)
    resp = _mcp(
        mcp_client,
        "tools/call",
        {"name": "search", "arguments": {"query": "phospho", "limit": 3}},
        req_id=2,
    )
    items = resp["result"]["structuredContent"]["result"]
    assert isinstance(items, list)
    assert items, "search should return at least one match for 'phospho'"
    for item in items:
        PsiModSummary.model_validate(item)
        assert "synonyms" not in item
        assert "references" not in item
        assert "is_a" not in item


# ---------------------------------------------------------------------------
# REST shape
# ---------------------------------------------------------------------------


def test_rest_get_entry_shape_matches_pydantic() -> None:
    with TestClient(app) as client:
        r = client.get("/api/entries/46")
        assert r.status_code == 200
        PsiModEntry.model_validate(r.json())


def test_rest_search_returns_summaries() -> None:
    with TestClient(app) as client:
        r = client.get("/api/search", params={"q": "phospho", "limit": 2})
        assert r.status_code == 200
        body = r.json()
        assert {"query", "total", "limit", "items"} <= set(body)
        for item in body["items"]:
            PsiModSummary.model_validate(item)


# ---------------------------------------------------------------------------
# Malformed IDs, health version, import cost
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/api/entries/foo", "/api/entries/foo/parents", "/api/entries/foo/children", "/api/entries/MOD:abc"],
)
def test_rest_malformed_id_returns_404(path: str) -> None:
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get(path)
    assert r.status_code == 404
    assert "No entry" in r.json()["detail"]


@pytest.mark.parametrize(("tool", "expected"), [("get_by_id", None), ("get_parents", []), ("get_children", [])])
def test_mcp_malformed_id_returns_empty_result(mcp_client: TestClient, tool: str, expected: object) -> None:
    _mcp(mcp_client, "initialize", _INIT_PARAMS)
    resp = _mcp(mcp_client, "tools/call", {"name": tool, "arguments": {"id": "foo"}}, req_id=2)
    result = resp["result"]
    assert not result.get("isError")
    assert result["structuredContent"] == {"result": expected}


@pytest.mark.parametrize("arguments", [{"query": ""}, {"query": "phospho", "limit": 0}, {"query": "a", "limit": 501}])
def test_mcp_search_rejects_out_of_range_arguments(mcp_client: TestClient, arguments: dict) -> None:
    _mcp(mcp_client, "initialize", _INIT_PARAMS)
    resp = _mcp(mcp_client, "tools/call", {"name": "search", "arguments": arguments}, req_id=2)
    assert resp["result"]["isError"] is True


def test_mcp_search_schema_is_bounded() -> None:
    import asyncio

    from psimodpy.server.app import mcp

    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    props = tools["search"].input_schema["properties"]
    assert props["query"]["minLength"] == 1
    assert props["limit"]["minimum"] == 1
    assert props["limit"]["maximum"] == 500


def test_rest_entry_uses_1_0_formula_names() -> None:
    body = TestClient(app).get("/api/entries/46").json()
    assert body["proforma_formula"] == "HO3P"
    assert body["dict_composition"] == {"H": 1, "O": 3, "P": 1}
    assert body["is_a"]


def test_health_reports_dunder_version(monkeypatch: pytest.MonkeyPatch) -> None:
    import psimodpy

    monkeypatch.setattr(psimodpy, "__version__", "9.9.9-test")
    r = TestClient(app).get("/api/health")
    assert r.status_code == 200
    assert r.json()["version"] == "9.9.9-test"


def test_server_import_parses_obo_once() -> None:
    import subprocess
    import sys

    code = (
        "import psimodpy.parser as p\n"
        "calls = []\n"
        "orig = p.parse_obo\n"
        "def counting(*a, **k):\n"
        "    calls.append(1)\n"
        "    return orig(*a, **k)\n"
        "p.parse_obo = counting\n"
        "import psimodpy.server.app\n"
        "print(len(calls))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip().splitlines()[-1] == "1"


def test_health_is_a_pydantic_model() -> None:
    from psimodpy.server.app import health
    from psimodpy.server.models import HealthResponse

    assert isinstance(health(), HealthResponse)
