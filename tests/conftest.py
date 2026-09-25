"""Shared test fixtures for psimodpy tests.

Fast by default. Opt in to the rest with:

- ``--run-slow`` or ``RUN_SLOW=1``: run tests marked ``slow`` (full-data sweeps, subprocess launches).
- ``HYPOTHESIS_PROFILE=thorough``: 300 Hypothesis examples per property instead of 50.

CI sets both.
"""

import os

import pytest
from hypothesis import HealthCheck, settings

import psimodpy

settings.register_profile("default", max_examples=50, deadline=None)
settings.register_profile("thorough", max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--run-slow", action="store_true", default=False, help="also run tests marked slow")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-slow") or os.environ.get("RUN_SLOW", "") not in ("", "0"):
        return
    skip = pytest.mark.skip(reason="slow: run with --run-slow or RUN_SLOW=1")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def db() -> psimodpy.PsiModDatabase:
    """Session-scoped fixture: load the bundled PSI-MOD database once."""
    return psimodpy.load()
