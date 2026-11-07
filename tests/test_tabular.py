"""Tests for the PSI-MOD TSV/CSV tabular writer."""

import csv

from psimodpy import PsiModDatabase, write_tsv
from psimodpy._tabular import _FIXED_PREFIX, _FIXED_SUFFIX, _SYN_DELIM, _synonym_col


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


def test_every_entry_round_trips_its_synonyms(db: PsiModDatabase, tmp_path) -> None:
    """Per entry and per type, the cell splits back to exactly the parsed values, in order.

    Stronger than a total: a dropped, duplicated or reordered synonym fails by naming the
    entry and the column, where a sum only says the arithmetic changed. The total is still
    asserted below, recovered from the file rather than recomputed from the database, so
    this subsumes the count test it replaced.

    What it does not see is a value carrying a bare ``"|"``: that survives the ``" | "``
    split whole and compares equal. ``test_synonym_values_never_contain_the_delimiter``
    is the only guard for that case.
    """
    out = tmp_path / "out.tsv"
    write_tsv(db, out)
    rows = {row["id"]: row for row in _read_dict(out)}
    syn_cols = [col for col in next(iter(rows.values())) if col.startswith("synonym_")]

    mismatches, recovered, multi_value_cells = [], 0, 0
    for entry in db:
        row = rows[f"MOD:{entry.id:05d}"]
        expected: dict[str, list[str]] = {}
        for syn in entry.synonyms:
            expected.setdefault(_synonym_col(str(syn.type)), []).append(syn.value)
        for col in expected:
            if col not in syn_cols:
                mismatches.append((entry.id, col, "no such column", expected[col]))
        for col in syn_cols:
            got = row[col].split(_SYN_DELIM) if row[col] else []
            if got != expected.get(col, []):
                mismatches.append((entry.id, col, got, expected.get(col, [])))
            recovered += len(got)
            multi_value_cells += len(got) > 1

    assert not mismatches, f"{len(mismatches)} entry/column mismatches, first: {mismatches[:3]}"
    assert recovered == sum(len(entry.synonyms) for entry in db)
    # Not a vacuous comparison: the multi-synonym cell is the shape that used to lose values.
    assert multi_value_cells > 500, f"only {multi_value_cells} cells held more than one synonym"


def test_synonym_values_never_contain_the_delimiter(db: PsiModDatabase) -> None:
    """The only guard for a bare ``"|"`` in a value.

    Neither the round-trip comparison above nor a total sees it: ``"A|B"`` joins and splits
    back unchanged, so the recovered value compares equal and the count does not move. A
    bare pipe is lossless for this writer and would still break any consumer that splits on
    ``"|"``, so this test is deliberately stricter than the delimiter actually used.
    """
    assert [s.value for entry in db for s in entry.synonyms if _SYN_DELIM.strip() in s.value] == []


def test_all_synonyms_of_one_type_are_kept(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.tsv"
    write_tsv(db, out)
    rows = _read_dict(out)
    # MOD:00014 carries 12 RESID-alternate synonyms; only the first used to be written.
    entry = db[14]
    expected = [s.value for s in entry.synonyms if str(s.type) == "RESID-alternate"]
    row = next(r for r in rows if r["id"] == "MOD:00014")
    assert row["synonym_resid_alternate"].split(_SYN_DELIM) == expected
    assert len(expected) == 12


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


def test_xrefs_unimod_column(db: PsiModDatabase, tmp_path) -> None:
    out = tmp_path / "out.tsv"
    write_tsv(db, out)
    rows = _read_dict(out)
    row = next(r for r in rows if r["id"] == "MOD:01506")
    assert row["xrefs_unimod"] == "Unimod:214; Unimod:889"
    header = out.read_text().splitlines()[0].split("\t")
    assert header[-1] == "xrefs_unimod"  # appended last so older columns keep their positions


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
