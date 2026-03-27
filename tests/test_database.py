"""Tests for PsiModDatabase lookup, search, and traversal."""

import pytest

from psimodpy.models import AminoAcid, Crosslink, RelationshipType


def test_get_by_id_int(db):
    entry = db.get_by_id(1)
    assert entry is not None
    assert entry.id == 1
    assert entry.name == "alkylated residue"


def test_get_by_id_mod_str(db):
    entry_int = db.get_by_id(1)
    entry_str = db.get_by_id("MOD:00001")
    assert entry_int is entry_str


def test_get_by_id_missing(db):
    assert db.get_by_id(99999) is None


def test_subscript_returns_entry(db):
    entry = db[1]
    assert entry.id == 1


def test_subscript_missing_raises(db):
    with pytest.raises(KeyError):
        _ = db[99999]


def test_get_by_name_exact(db):
    entry = db.get_by_name("alkylated residue")
    assert entry is not None
    assert entry.id == 1


def test_get_by_name_case_insensitive(db):
    lower = db.get_by_name("alkylated residue")
    upper = db.get_by_name("Alkylated Residue")
    assert lower is upper


def test_get_by_name_missing(db):
    assert db.get_by_name("not a real modification name") is None


def test_search_name_substring(db):
    results = db.search("phospho")
    names = [e.name for e in results]
    assert any("phospho" in n.lower() for n in names)


def test_search_synonym(db):
    # "Ala" is a PSI-MOD-label synonym for MOD:00010
    results = db.search("Ala")
    ids = [e.id for e in results]
    assert 10 in ids


def test_search_empty_query(db):
    results = db.search("")
    assert len(results) == len(db)


def test_search_no_match(db):
    results = db.search("zzznomatchzzz")
    assert results == []


def test_get_by_origin_single(db):
    results = db.get_by_origin("S")
    assert len(results) > 0
    for entry in results:
        assert entry.origin is not None
        if isinstance(entry.origin, AminoAcid):
            assert entry.origin == AminoAcid.SER
        else:
            assert isinstance(entry.origin, Crosslink)
            assert "S" in entry.origin.sites


def test_get_by_origin_crosslink(db):
    # MOD:00229 has origin "C, C" — should appear in get_by_origin("C")
    results = db.get_by_origin("C")
    ids = [e.id for e in results]
    assert 229 in ids


def test_get_by_origin_any(db):
    # Entries with "X" origin exist
    results = db.get_by_origin("X")
    assert len(results) > 0
    for entry in results:
        assert entry.origin is not None
        if isinstance(entry.origin, AminoAcid):
            assert entry.origin == AminoAcid.ANY
        else:
            assert isinstance(entry.origin, Crosslink)
            assert "X" in entry.origin.sites


def test_get_parents_multi(db):
    """MOD:00002 has 2 parents: MOD:00396 and MOD:00916."""
    entry = db.get_by_id(2)
    parents = db.get_parents(entry)
    parent_ids = {p.id for p in parents}
    assert parent_ids == {396, 916}


def test_get_parents_root(db):
    root = db.get_by_id(0)
    assert db.get_parents(root) == []


def test_get_children_root(db):
    root = db.get_by_id(0)
    children = db.get_children(root)
    assert len(children) > 0


def test_get_related_derives_from(db):
    """MOD:00125 derives_from MOD:01880."""
    entry = db.get_by_id(125)
    targets = db.get_related(entry, RelationshipType.DERIVES_FROM)
    assert len(targets) == 1
    assert targets[0].id == 1880


def test_get_related_contains(db):
    """MOD:00234 contains MOD:02026."""
    entry = db.get_by_id(234)
    targets = db.get_related(entry, RelationshipType.CONTAINS)
    assert len(targets) == 1
    assert targets[0].id == 2026


def test_get_related_empty(db):
    """Entry with no relationships returns empty list."""
    entry = db.get_by_id(0)
    results = db.get_related(entry, RelationshipType.DERIVES_FROM)
    assert results == []


def test_filter_no_obsolete(db):
    entries = db.filter(include_obsolete=False)
    assert all(not e.is_obsolete for e in entries)
    assert len(entries) < len(db)


def test_filter_includes_obsolete(db):
    all_entries = db.filter(include_obsolete=True)
    assert any(e.is_obsolete for e in all_entries)


def test_filter_slim_only(db):
    slim = db.filter(slim_only=True)
    assert all(e.in_slim_subset for e in slim)
    assert len(slim) == 811


def test_filter_slim_no_obsolete(db):
    entries = db.filter(slim_only=True, include_obsolete=False)
    assert all(e.in_slim_subset for e in entries)
    assert all(not e.is_obsolete for e in entries)


def test_len(db):
    assert len(db) == 2116


def test_iter_length(db):
    assert sum(1 for _ in db) == 2116


def test_iter_contains_all_ids(db):
    ids = {e.id for e in db}
    assert 0 in ids
    assert 1 in ids
    assert 99999 not in ids
