"""Tests for the PSI-MOD TSV/CSV tabular writer."""

import csv

import psimodpy
from psimodpy import PsiModDatabase, write_tsv
from psimodpy._tabular import _FIXED_PREFIX, _FIXED_SUFFIX


def _read(path, delimiter="\t"):
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh, delimiter=delimiter))


def _read_dict(path, delimiter="\t"):
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=delimiter))


def test_header_fixed_columns(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.tsv"
    write_tsv(db, out)
    header = tuple(_read(out)[0])
    for col in _FIXED_PREFIX + _FIXED_SUFFIX:
        assert col in header


def test_row_count(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.tsv"
    write_tsv(db, out)
    rows = _read(out)
    assert len(rows) == len(db) + 1


def test_id_format(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.tsv"
    write_tsv(db, out)
    rows = _read_dict(out)
    assert rows[0]["id"].startswith("MOD:")
    assert len(rows[0]["id"]) == 9  # "MOD:" + 5 digits


def test_entry_scalars(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.tsv"
    write_tsv(db, out)
    rows = _read_dict(out)
    row = next(r for r in rows if r["id"] == "MOD:00046")
    assert row["name"] == "O-phospho-L-serine"
    assert float(row["diff_mono"]) == 79.966331


def test_synonym_columns_present(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.tsv"
    write_tsv(db, out)
    header = _read(out)[0]
    assert "synonym_psi_mod_label" in header
    assert "synonym_omssa_label" in header


def test_synonym_values_populated(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.tsv"
    write_tsv(db, out)
    rows = _read_dict(out)
    row = next(r for r in rows if r["id"] == "MOD:00010")
    assert row["synonym_psi_mod_label"] == "Ala"


def test_is_a_format(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.tsv"
    write_tsv(db, out)
    rows = _read_dict(out)
    row = next(r for r in rows if r["id"] == "MOD:00001")
    assert "MOD:" in row["is_a"]


def test_multi_parent_is_a(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.tsv"
    write_tsv(db, out)
    rows = _read_dict(out)
    row = next(r for r in rows if r["id"] == "MOD:00002")
    parents = row["is_a"].split("; ")
    assert len(parents) == 2


def test_relationships_format(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.tsv"
    write_tsv(db, out)
    rows = _read_dict(out)
    # MOD:00125 derives_from MOD:01880
    row = next(r for r in rows if r["id"] == "MOD:00125")
    assert "derives_from:MOD:01880" in row["relationships"]


def test_slim_subset_flag(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.tsv"
    write_tsv(db, out)
    rows = _read_dict(out)
    slim_row = next(r for r in rows if r["id"] == "MOD:00002")
    assert slim_row["in_slim_subset"] == "1"


def test_obsolete_flag(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.tsv"
    write_tsv(db, out)
    rows = _read_dict(out)
    obs_row = next(r for r in rows if r["id"] == "MOD:00004")
    assert obs_row["is_obsolete"] == "1"


def test_formal_charge_format(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.tsv"
    write_tsv(db, out)
    rows = _read_dict(out)
    row = next(r for r in rows if r["id"] == "MOD:00049")
    assert row["formal_charge"] == "1+"


def test_xref_uniprot_ptm(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.tsv"
    write_tsv(db, out)
    rows = _read_dict(out)
    row = next(r for r in rows if r["id"] == "MOD:00035")
    assert row["xref_uniprot_ptm"] == "PTM-0369"


def test_optional_fields_empty_not_none(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.tsv"
    write_tsv(db, out)
    rows = _read_dict(out)
    for row in rows:
        assert "None" not in row.values()


def test_csv_delimiter(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.csv"
    write_tsv(db, out, delimiter=",")
    rows = _read_dict(out, delimiter=",")
    assert len(rows) == len(db)
    assert any(r["id"] == "MOD:00046" for r in rows)


def test_creates_parent_directory(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "nested" / "out.tsv"
    write_tsv(db, out)
    assert out.exists()


def test_database_method_returns_path(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.tsv"
    result = db.write_tsv(out)
    assert result == out
    assert out.exists()


def test_database_method_csv(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.csv"
    db.write_tsv(out, delimiter=",")
    rows = _read_dict(out, delimiter=",")
    assert len(rows) == len(db)
