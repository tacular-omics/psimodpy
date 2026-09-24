"""Entry.get_mass() (1.1)."""

from __future__ import annotations

import inspect

import pytest

from psimodpy import PsiModDatabase


def test_get_mass_matches_fields(db: PsiModDatabase) -> None:
    for entry in db:
        assert entry.get_mass() == entry.diff_mono
        assert entry.get_mass(monoisotopic=True) == entry.diff_mono
        assert entry.get_mass(monoisotopic=False) == entry.diff_avg


def test_get_mass_is_keyword_only(db: PsiModDatabase) -> None:
    entry = next(iter(db))
    params = inspect.signature(entry.get_mass).parameters
    assert params["monoisotopic"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["monoisotopic"].default is True
    with pytest.raises(TypeError):
        entry.get_mass(False)  # type: ignore[misc]


def test_some_entries_have_no_mass(db: PsiModDatabase) -> None:
    assert any(e.get_mass() is None for e in db)
    assert any(e.get_mass() is not None for e in db)


def test_search_mass_uses_get_mass(db: PsiModDatabase) -> None:
    for entry, error in db.search_mass(79.966331, tolerance=0.02):
        mass = entry.get_mass()
        assert mass is not None
        assert error == 79.966331 - mass
