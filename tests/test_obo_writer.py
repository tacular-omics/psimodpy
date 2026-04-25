"""Tests for the PSI-MOD OBO round-trip writer."""

import pytest

import psimodpy
from psimodpy import PsiModDatabase, parse_obo, write_obo


def test_write_produces_file(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.obo"
    write_obo(db, out, header_lines=db.header_lines)
    assert out.exists()
    assert out.stat().st_size > 0


def test_round_trip_entry_count(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.obo"
    write_obo(db, out, header_lines=db.header_lines)
    db2 = parse_obo(out)
    assert len(db2) == len(db)


def test_round_trip_name(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.obo"
    write_obo(db, out, header_lines=db.header_lines)
    db2 = parse_obo(out)
    assert db2[46].name == db[46].name


def test_round_trip_definition(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.obo"
    write_obo(db, out, header_lines=db.header_lines)
    db2 = parse_obo(out)
    assert db2[46].definition == db[46].definition


def test_round_trip_definition_ref(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.obo"
    write_obo(db, out, header_lines=db.header_lines)
    db2 = parse_obo(out)
    assert db2[46].definition_ref == db[46].definition_ref


def test_round_trip_masses(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.obo"
    write_obo(db, out, header_lines=db.header_lines)
    db2 = parse_obo(out)
    e1, e2 = db[46], db2[46]
    assert e1.diff_mono == pytest.approx(e2.diff_mono, rel=1e-5)
    assert e1.diff_avg == pytest.approx(e2.diff_avg, rel=1e-4)


def test_round_trip_synonyms_with_scope(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.obo"
    write_obo(db, out, header_lines=db.header_lines)
    db2 = parse_obo(out)
    e1, e2 = db[10], db2[10]
    assert len(e1.synonyms) == len(e2.synonyms)
    for s1, s2 in zip(
        sorted(e1.synonyms, key=lambda s: s.value),
        sorted(e2.synonyms, key=lambda s: s.value),
    ):
        assert s1.value == s2.value
        assert s1.type == s2.type
        assert s1.scope == s2.scope


def test_round_trip_is_a(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.obo"
    write_obo(db, out, header_lines=db.header_lines)
    db2 = parse_obo(out)
    assert db2[1].is_a == db[1].is_a


def test_round_trip_multi_parent(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.obo"
    write_obo(db, out, header_lines=db.header_lines)
    db2 = parse_obo(out)
    assert set(db2[2].is_a) == set(db[2].is_a)


def test_round_trip_relationships(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.obo"
    write_obo(db, out, header_lines=db.header_lines)
    db2 = parse_obo(out)
    e1, e2 = db[125], db2[125]
    assert {(r.type, r.target_id) for r in e1.relationships} == {
        (r.type, r.target_id) for r in e2.relationships
    }


def test_round_trip_slim_subset(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.obo"
    write_obo(db, out, header_lines=db.header_lines)
    db2 = parse_obo(out)
    assert db2[2].in_slim_subset == db[2].in_slim_subset
    assert db2[4].in_slim_subset == db[4].in_slim_subset


def test_round_trip_obsolete(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.obo"
    write_obo(db, out, header_lines=db.header_lines)
    db2 = parse_obo(out)
    assert db2[4].is_obsolete is True
    assert db2[46].is_obsolete is False


def test_round_trip_uniprot_ptm_xref(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.obo"
    write_obo(db, out, header_lines=db.header_lines)
    db2 = parse_obo(out)
    assert db2[35].xref_uniprot_ptm == db[35].xref_uniprot_ptm


def test_round_trip_formal_charge(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.obo"
    write_obo(db, out, header_lines=db.header_lines)
    db2 = parse_obo(out)
    assert db2[49].formal_charge == db[49].formal_charge


def test_round_trip_remap(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.obo"
    write_obo(db, out, header_lines=db.header_lines)
    db2 = parse_obo(out)
    remapped = [e for e in db if e.xref_remap is not None]
    for e in remapped:
        e2 = db2.get_by_id(e.id)
        assert e2 is not None
        assert e2.xref_remap == e.xref_remap


def test_stored_header_lines_preserved(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.obo"
    write_obo(db, out, header_lines=db.header_lines)
    db2 = parse_obo(out)
    assert db2.header_lines == db.header_lines


def test_minimal_header_when_no_header_lines(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.obo"
    write_obo(db, out)  # no header_lines arg
    content = out.read_text(encoding="utf-8")
    assert content.startswith("format-version:")


def test_creates_parent_directory(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "nested" / "out.obo"
    write_obo(db, out, header_lines=db.header_lines)
    assert out.exists()


def test_database_method_returns_path(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.obo"
    result = db.write_obo(out)
    assert result == out
    assert out.exists()


def test_database_method_round_trip(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.obo"
    db.write_obo(out)
    db2 = parse_obo(out)
    assert len(db2) == len(db)
    assert db2[46].name == db[46].name
