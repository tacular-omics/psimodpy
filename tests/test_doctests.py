"""Execute every docstring example in the package.

A ``>>>`` example is the only documentation the suite can keep honest, so the walk below
must reach every module: a module nobody imports has examples nobody runs.
"""

from __future__ import annotations

import doctest
import importlib
import importlib.util
import pkgutil
from types import ModuleType

import psimodpy

# Measured 2026-11-08 on this tree: 10 core modules, 5 under psimodpy.server, and 9
# examples, all of them in psimodpy._formula. Raise these when you add modules or
# examples; never lower one without saying why in the commit message.
MIN_CORE_MODULES = 10
MIN_SERVER_MODULES = 5
MIN_EXAMPLES = 9

# psimodpy.server imports fastapi, pydantic and mcp at module import (server/__init__.py
# line 21 imports server.app), so nothing under it can be imported without the `server`
# extra. It is excluded BY NAME, and only when that extra is absent: with the extra
# installed, which is what `just install` and every CI job do, these five modules are
# imported and their examples run like any other. The excluded names are still counted,
# because pkgutil never yields the children of a package it could not import, so a module
# that vanished from server/ would otherwise be invisible in both environments.
_SERVER = "psimodpy.server"
_SERVER_REQUIRES = ("fastapi", "mcp", "pydantic")


def _installed(module: str) -> bool:
    """Return True if ``module`` can be located, without importing it."""
    try:
        return importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:
        return False


def _submodules(name: str, search_paths: list[str]) -> list[tuple[str, bool]]:
    """Return ``(dotted name, is a package)`` for the direct children of one package."""
    return [(child, ispkg) for _finder, child, ispkg in pkgutil.iter_modules(search_paths, prefix=f"{name}.")]


def _server_subtree() -> list[str]:
    """Return the names under ``psimodpy.server``, read off disk without importing any of them."""
    spec = importlib.util.find_spec(_SERVER)
    if spec is None or spec.submodule_search_locations is None:
        raise AssertionError(f"{_SERVER} is not an importable package")
    paths = list(spec.submodule_search_locations)
    return [_SERVER, *(child for child, _ispkg in _submodules(_SERVER, paths))]


def _import(name: str, ispkg: bool) -> ModuleType:
    """Import one module, re-raising an ImportError with the name the walk was entering.

    A diagnosis guard, not a correctness one: the module floor below already catches the
    drop, because it is asserted against the names the walk discovered. What this adds is
    the dotted name of the module that broke and, for a package, the fact that nothing
    under it was reached -- the bare ImportError names only the dependency that was
    missing, so with a subpackage you would read "No module named 'fastapi'" and have to
    infer the rest from the traceback.

    It cannot see a module that ``psimodpy/__init__.py`` imports itself: that one fails
    while this test module is being imported, before the walk starts. Both branches were
    measured on 2026-11-08; see the commit message.
    """
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        reached = ", so none of its submodules were seen" if ispkg else ""
        raise AssertionError(f"walking into {name} failed{reached}: {exc!r}") from exc


def _collect(package: ModuleType, imported: list[ModuleType], skipped: list[str]) -> None:
    """Import every module under ``package``, depth first. An ImportError fails the test."""
    for name, ispkg in _submodules(package.__name__, list(package.__path__)):
        if name == _SERVER and not all(_installed(dep) for dep in _SERVER_REQUIRES):
            skipped.extend(_server_subtree())
            continue
        module = _import(name, ispkg)
        imported.append(module)
        if ispkg:
            _collect(module, imported, skipped)


def test_docstring_examples() -> None:
    imported: list[ModuleType] = [psimodpy]
    skipped: list[str] = []
    _collect(psimodpy, imported, skipped)

    names = {module.__name__ for module in imported}
    core = {name for name in names if name != _SERVER and not name.startswith(f"{_SERVER}.")}
    server = len(names) - len(core) + len(skipped)
    assert len(core) >= MIN_CORE_MODULES, f"the module walk found only {len(core)} core modules: {sorted(core)}"
    assert server >= MIN_SERVER_MODULES, f"only {server} server modules were imported or skipped by name"

    attempted = failed = 0
    for module in imported:
        result = doctest.testmod(module, verbose=False)
        attempted += result.attempted
        failed += result.failed

    # Every example lives in a core module today, so this floor holds with or without the
    # extra. Split it by environment if an example is ever added under psimodpy.server.
    assert failed == 0, f"{failed} of {attempted} docstring examples failed"
    assert attempted >= MIN_EXAMPLES, f"only {attempted} examples ran, expected at least {MIN_EXAMPLES}"
