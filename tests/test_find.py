from __future__ import annotations

import pytest

import psimodpy
from psimodpy.database import PsiModDatabase


@pytest.fixture(scope="module")
def db() -> PsiModDatabase:
    return psimodpy.load()


def test_find_no_filters_excludes_obsolete(db: PsiModDatabase) -> None:
    results = db.find()
    assert all(not e.is_obsolete for e in results)
    assert len(results) > 0


def test_find_text(db: PsiModDatabase) -> None:
    results = db.find(text="phospho", limit=5)
    assert len(results) <= 5
    assert all("phospho" in e.name.lower() or "phospho" in e.definition.lower() or any("phospho" in s.value.lower() for s in e.synonyms) for e in results)


def test_find_mass_range_diff_mono(db: PsiModDatabase) -> None:
    results = db.find(mass_min=79.96, mass_max=79.98, mass_type="diff_mono")
    assert len(results) > 0
    for e in results:
        assert e.diff_mono is not None
        assert 79.96 <= e.diff_mono <= 79.98


def test_find_residues(db: PsiModDatabase) -> None:
    results = db.find(residues=["S"], limit=20)
    for e in results:
        sites = set()
        if e.origin is not None:
            from psimodpy.models import AminoAcid, Crosslink
            if isinstance(e.origin, AminoAcid):
                sites = {str(e.origin)}
            elif isinstance(e.origin, Crosslink):
                sites = set(e.origin.sites)
        assert "S" in sites


def test_find_combined_phospho_sty(db: PsiModDatabase) -> None:
    results = db.find(
        mass_min=79.96,
        mass_max=79.98,
        mass_type="diff_mono",
        residues=["S", "T", "Y"],
    )
    assert len(results) >= 3
    names = {e.name.lower() for e in results}
    assert any("phosphoserine" in n for n in names) or any("phospho-l-serine" in n for n in names)


def test_find_term_spec_invalid_returns_empty(db: PsiModDatabase) -> None:
    assert db.find(term_spec="NOPE") == []


def test_find_source_invalid_returns_empty(db: PsiModDatabase) -> None:
    assert db.find(source="NOPE") == []


def test_find_slim_only(db: PsiModDatabase) -> None:
    results = db.find(in_slim_subset=True, limit=10)
    assert all(e.in_slim_subset for e in results)


def test_find_include_obsolete(db: PsiModDatabase) -> None:
    with_obs = db.find(include_obsolete=True)
    without_obs = db.find(include_obsolete=False)
    assert len(with_obs) >= len(without_obs)


def test_find_limit(db: PsiModDatabase) -> None:
    assert len(db.find(limit=3)) == 3


def test_find_mass_skips_none(db: PsiModDatabase) -> None:
    results = db.find(mass_min=-1e9, mass_max=1e9, mass_type="diff_mono")
    assert all(e.diff_mono is not None for e in results)
