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
    assert len(slim) == 788


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


@pytest.mark.parametrize("key", [34, "34", "00034", "MOD:00034", "mod:00034"])
def test_contains_accepts_every_getitem_key(db, key):
    assert key in db
    assert db[key].id == 34


@pytest.mark.parametrize("key", [99999, "MOD:99999", "foo", "MOD:abc", "", None, 3.5, (34,)])
def test_contains_missing_or_malformed_is_false(db, key):
    assert key not in db


def test_contains_entry_object(db):
    import dataclasses

    entry = db[34]
    assert entry in db
    assert dataclasses.replace(entry) in db  # equal copy, same id
    assert dataclasses.replace(entry, name="not in the ontology") not in db
    assert dataclasses.replace(entry, id=99999) not in db


# ------------------------------------------------------------------
# Uniform lookup: [] / get / in agree, and match unimodpy and uniprotptmpy
# ------------------------------------------------------------------


@pytest.mark.parametrize("key", [34, "34", "00034", "MOD:00034", "mod:00034", " MOD:00034 "])
def test_get_accepts_every_id_form(db, key):
    assert db.get(key) is db[34]


@pytest.mark.parametrize("key", [99999, "MOD:99999", "foo", "MOD:abc", "", None, 3.5, 34.0, (34,), [34]])
def test_get_missing_or_malformed_returns_default(db, key):
    assert db.get(key) is None
    sentinel = object()
    assert db.get(key, sentinel) is sentinel


@pytest.mark.parametrize("key", ["foo", "MOD:abc", "", None, 34.0, (34,), [34]])
def test_getitem_malformed_raises_keyerror(db, key):
    with pytest.raises(KeyError):
        db[key]


def test_getitem_falls_back_to_name(db):
    entry = db[46]
    assert db[entry.name] is entry
    assert db[entry.name.upper()] is entry
    assert entry.name.upper() in db
    assert db.get(entry.name) is entry


def test_get_by_id_non_int_or_str_returns_none(db):
    assert db.get_by_id(34.0) is None  # ty: ignore[invalid-argument-type]
    assert db.get_by_id(None) is None  # ty: ignore[invalid-argument-type]


def test_resolve_follows_redirect(db):
    assert db.get_by_id(407).is_obsolete
    assert db.resolve(407) is db.get_by_id(599)
    assert db.resolve("MOD:00407") is db.get_by_id(599)
    assert not db.resolve(407).is_obsolete


def test_resolve_live_and_unknown(db):
    assert db.resolve(1) is db.get_by_id(1)
    assert db.resolve("MOD:00001") is db.get_by_id(1)
    assert db.resolve(99999) is None
    assert db.resolve("foo") is None
    assert db.resolve(True) is None


def test_resolve_self_redirect_terminates(db):
    entry = db.get_by_id(1123)
    assert entry.xref_remap == 1123
    assert db.resolve(1123) is entry


def test_resolve_dead_chain_returns_last_obsolete_term(db):
    assert db.get_by_id(580).xref_remap == 579
    end = db.resolve(580)
    assert end is db.get_by_id(579)
    assert end.is_obsolete and end.xref_remap is None


def test_resolve_every_obsolete_term_terminates(db):
    obsolete = [entry for entry in db if entry.is_obsolete]
    assert len(obsolete) > 0
    assert sum(1 for entry in obsolete if entry.xref_remap is not None) > 0
    for entry in obsolete:
        assert db.resolve(entry.id) is not None


def test_resolve_cycle_terminates(db):
    import dataclasses

    from psimodpy.database import PsiModDatabase

    base = db.get_by_id(1)
    a = dataclasses.replace(base, id=90001, is_obsolete=True, xref_remap=90002)
    b = dataclasses.replace(base, id=90002, name="b", is_obsolete=True, xref_remap=90001)
    cyc = PsiModDatabase([a, b])
    assert cyc.resolve(90001) is b
    assert cyc.resolve(90002) is a


def test_resolve_redirect_to_missing_id_returns_last_existing_term(db):
    import dataclasses

    from psimodpy.database import PsiModDatabase

    a = dataclasses.replace(db.get_by_id(1), id=90001, is_obsolete=True, xref_remap=99999)
    assert PsiModDatabase([a]).resolve(90001) is a


# ----------------------------------------------------------------------
# Transitive is_a queries
# ----------------------------------------------------------------------


def _naive_ancestor_ids(db, entry):
    """Reference implementation: recursive union, no ordering."""
    out = set()
    for p in db.get_parents(entry):
        out.add(p.id)
        out |= _naive_ancestor_ids(db, p)
    return out


def test_bundled_is_a_shape(db):
    """The figures the transitive queries were sized against."""
    roots = [e for e in db if not db.get_parents(e)]
    assert len(roots) == 147
    assert sum(1 for e in db if len(e.is_a) > 1) == 1194

    def depth(e):
        return 1 + max((depth(p) for p in db.get_parents(e)), default=-1)

    assert max(depth(e) for e in db) == 9


def test_every_parent_is_an_ancestor_and_roots_have_none(db):
    for entry in db:
        ancestor_ids = {a.id for a in db.get_ancestors(entry)}
        assert {p.id for p in db.get_parents(entry)} <= ancestor_ids
        assert entry.id not in ancestor_ids
        if not db.get_parents(entry):
            assert db.get_ancestors(entry) == []


def test_ancestors_match_naive_recursion_and_are_unique(db):
    for entry in db:
        ids = [a.id for a in db.get_ancestors(entry)]
        assert len(ids) == len(set(ids))
        assert set(ids) == _naive_ancestor_ids(db, entry)


def test_two_parent_term_lists_each_ancestor_once(db):
    ancestors = db.get_ancestors(2)  # parents 396 and 916 share ancestors
    ids = [a.id for a in ancestors]
    assert ids[:2] == [396, 916]
    assert len(ids) == len(set(ids))
    assert ids == [a.id for a in db.get_ancestors(db[2])]  # id and entry agree


def test_ancestors_order_is_breadth_first(db):
    entry = db[2]
    ids = [a.id for a in db.get_ancestors(entry)]
    level1 = [p.id for p in db.get_parents(entry)]
    assert ids[: len(level1)] == level1


def test_descendants_mirror_ancestors(db):
    for entry in db:
        descendants = db.get_descendants(entry)
        ids = [d.id for d in descendants]
        assert len(ids) == len(set(ids))
        assert entry.id not in ids
        assert [c.id for c in db.get_children(entry)] == ids[: len(db.get_children(entry))]
    root = db[0]
    for d in db.get_descendants(root):
        assert root.id in {a.id for a in db.get_ancestors(d)}


def test_is_descendant_of(db):
    parent = db.get_parents(db[2])[0]
    grand = db.get_ancestors(db[2])[-1]
    assert db.is_descendant_of(2, parent.id)
    assert db.is_descendant_of("MOD:00002", grand)
    assert not db.is_descendant_of(parent.id, 2)
    assert not db.is_descendant_of(2, 2)


def test_transitive_unknown_ids(db):
    assert db.get_ancestors(99999) == []
    assert db.get_descendants("foo") == []
    assert db.get_ancestors(True) == []
    assert not db.is_descendant_of(99999, 2)
    assert not db.is_descendant_of(2, 99999)


def test_transitive_queries_terminate_on_a_cycle(db):
    from dataclasses import replace

    from psimodpy import PsiModDatabase

    a = replace(db[1], id=9001, is_a=(9002,))
    b = replace(db[1], id=9002, is_a=(9001,))
    cyc = PsiModDatabase([a, b])
    assert [e.id for e in cyc.get_ancestors(9001)] == [9002]
    assert [e.id for e in cyc.get_descendants(9001)] == [9002]
    assert cyc.is_descendant_of(9001, 9002) and cyc.is_descendant_of(9002, 9001)
    assert not cyc.is_descendant_of(9001, 9001)
