"""Tests for error handling edge cases."""

import pytest

import psimodpy
from psimodpy.database import PsiModDatabase


def test_empty_database():
    db = PsiModDatabase([])
    assert len(db) == 0
    assert list(db) == []
    assert db.get_by_id(1) is None
    assert db.get_by_name("anything") is None
    assert db.search("test") == []


def test_get_by_id_plain_string(db):
    entry = db.get_by_id("1")
    assert entry is not None
    assert entry.id == 1


def test_load_from_nonexistent_raises():
    with pytest.raises(FileNotFoundError):
        psimodpy.load_from("/nonexistent/path.obo")
