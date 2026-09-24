"""Drift guard for the MCP tool schemas (shared design across tacular-omics servers).

Walks every tool's input and output schema and checks the shared vocabulary:
no retired names, the Da/ppm switch is ``*tolerance_unit``, unknown arguments are
rejected, record keys come from the library, and list tools stay bounded.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import re
from collections.abc import Iterator
from typing import Any

import pytest

pytest.importorskip("mcp")
pytest.importorskip("fastapi")

from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from psimodpy.models import PsiModEntry  # noqa: E402
from psimodpy.server.app import mcp  # noqa: E402

BANNED = re.compile(
    r"^(unit|tolerance_type|.*_tolerance_type|retention_time.*|inverse_reduced.*|"
    r"ion_mobility_.*|target_mz|scan_start_time|ce|tic|TIC|time|one_over_k0.*|"
    r"mz_begin|mz_end|window_group|monoisotopic_mz)$"
)
# Names allowed despite matching a rule above (none needed today).
ALLOWED: set[str] = set()
# Output keys that are not attributes of the library ``PsiModEntry``: the wire shape
# flattens/renames a few fields (definition_ref -> references) and adds page metadata.
MCP_ONLY_KEYS = {"references", "result", "total", "limit", "truncated", "items"}

# Minimal valid arguments per tool, used for the unknown-argument check.
MINIMAL_ARGS: dict[str, dict[str, Any]] = {
    "get_by_id": {"id": "46"},
    "get_by_name": {"name": "O-phospho-L-serine"},
    "search": {"query": "phospho"},
    "get_parents": {"id": "46"},
    "get_children": {"id": "46"},
    "get_by_origin": {"aa": "S"},
}


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def tools() -> dict[str, Any]:
    return {t.name: t for t in _run(mcp.list_tools())}


def schema_props(schema: dict[str, Any], path: str = "") -> Iterator[tuple[str, str, dict[str, Any]]]:
    """Yield ``(path, name, subschema)`` for every property, following ``$ref`` into ``$defs`` once."""
    defs = schema.get("$defs", {})
    seen: set[str] = set()

    def walk(node: Any, where: str) -> Iterator[tuple[str, str, dict[str, Any]]]:
        if not isinstance(node, dict):
            return
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[-1]
            if name not in seen:
                seen.add(name)
                yield from walk(defs.get(name, {}), f"{where}<{name}>")
        for key, sub in (node.get("properties") or {}).items():
            yield f"{where}.{key}", key, sub
            yield from walk(sub, f"{where}.{key}")
        for key in ("items", "anyOf", "oneOf", "allOf", "additionalProperties"):
            sub = node.get(key)
            for child in sub if isinstance(sub, list) else [sub]:
                yield from walk(child, where)

    yield from walk(schema, path)


def enum_values(sub: dict[str, Any]) -> set[Any]:
    """Union of ``enum``/``const`` values across ``anyOf`` (handles Optional)."""
    values: set[Any] = set()
    for node in [sub, *sub.get("anyOf", [])]:
        values |= set(node.get("enum") or ())
        if "const" in node:
            values.add(node["const"])
    return values


def _all_props(tools: dict[str, Any]) -> Iterator[tuple[str, str, str, dict[str, Any]]]:
    for name, tool in tools.items():
        for kind, schema in (("in", tool.input_schema), ("out", tool.output_schema or {})):
            for path, key, sub in schema_props(schema, name):
                yield kind, path, key, sub


def test_no_banned_names(tools: dict[str, Any]) -> None:
    bad = [f"{kind} {path}" for kind, path, key, _ in _all_props(tools) if BANNED.match(key) and key not in ALLOWED]
    assert not bad, bad


def test_tolerance_switches(tools: dict[str, Any]) -> None:
    for kind, path, key, sub in _all_props(tools):
        if kind != "in" or not key.endswith("unit") or key in ALLOWED:
            continue
        assert key == "tolerance_unit" or key.endswith("_tolerance_unit"), path
        assert enum_values(sub) <= {"da", "ppm"}, (path, enum_values(sub))


@pytest.mark.parametrize("tool", sorted(MINIMAL_ARGS))
def test_unknown_argument_rejected(tools: dict[str, Any], tool: str) -> None:
    assert set(MINIMAL_ARGS) == set(tools), "add new tools to MINIMAL_ARGS"
    _run(mcp.call_tool(tool, MINIMAL_ARGS[tool]))  # the minimal call itself is valid
    assert tools[tool].input_schema.get("additionalProperties") is False
    with pytest.raises(ToolError, match="__bogus__"):
        _run(mcp.call_tool(tool, {**MINIMAL_ARGS[tool], "__bogus__": 1}))


def _library_names() -> set[str]:
    fields = {f.name for f in dataclasses.fields(PsiModEntry)}
    return fields | {n for n in dir(PsiModEntry) if not n.startswith("_")}


def test_record_keys_match_library() -> None:
    library = _library_names() | MCP_ONLY_KEYS
    entry = _run(mcp.call_tool("get_by_id", {"id": "46"})).structured_content["result"]
    assert set(entry) - library == set()
    page = _run(mcp.call_tool("get_by_origin", {"aa": "S", "limit": 3})).structured_content
    assert set(page) - library == set()
    assert set(page["items"][0]) - library == set()


@pytest.mark.parametrize(
    ("tool", "args"),
    [("get_by_origin", {"aa": "S"}), ("get_children", {"id": "MOD:00000"}), ("get_parents", {"id": "46"})],
)
def test_list_tools_are_bounded_summaries(tool: str, args: dict[str, Any]) -> None:
    result = _run(mcp.call_tool(tool, args))
    page = result.structured_content
    assert page["limit"] == 25
    assert len(page["items"]) == min(page["total"], 25)
    assert page["truncated"] == (page["total"] > 25)
    assert all("synonyms" not in item and "references" not in item for item in page["items"])
    # One text block for the whole page, not one per item.
    assert len(result.content) == 1


def test_get_by_origin_response_size_is_bounded() -> None:
    page = _run(mcp.call_tool("get_by_origin", {"aa": "S"})).structured_content
    assert page["total"] > 100 and page["truncated"]
    assert len(json.dumps(page)) < 50_000
    full = _run(mcp.call_tool("get_by_origin", {"aa": "S", "limit": 500})).structured_content
    assert len(full["items"]) == full["total"]
    assert not full["truncated"]
    assert len(json.dumps(full)) < 50_000


@pytest.mark.parametrize("limit", [0, 501])
def test_list_tool_limit_is_validated(limit: int) -> None:
    with pytest.raises(ToolError):
        _run(mcp.call_tool("get_by_origin", {"aa": "S", "limit": limit}))
