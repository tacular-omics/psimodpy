"""Shared test fixtures for psimodpy tests."""

import pytest

import psimodpy


@pytest.fixture(scope="session")
def db() -> psimodpy.PsiModDatabase:
    """Session-scoped fixture: load the bundled PSI-MOD database once."""
    return psimodpy.load()
