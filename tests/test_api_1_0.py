"""Shared 1.0 API (psimodpy / unimodpy / uniprotptmpy): errors, names, formulas, deprecations."""

from __future__ import annotations

import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

import psimodpy
from psimodpy import PsimodError, PsimodParseError
from psimodpy.database import PsiModDatabase
from psimodpy.parser import parse_obo

_HEADER = "format-version: 1.2\ndata-version: 9.9.9\n\n"

_TERM = """[Term]
id: MOD:{id:05d}
name: {name}
def: "A definition." [PubMed:1, RESID:AA0001]
{extra}
"""


def _obo(tmp_path: Path, *terms: str, header: str = _HEADER) -> Path:
    path = tmp_path / "t.obo"
    path.write_text(header + "\n".join(terms), encoding="utf-8")
    return path


def _term(id: int, name: str, extra: str = "") -> str:
    return _TERM.format(id=id, name=name, extra=extra)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_error_hierarchy():
    assert issubclass(PsimodError, Exception)
    assert issubclass(PsimodParseError, PsimodError)
    assert issubclass(PsimodParseError, ValueError)
    assert {"PsimodError", "PsimodParseError"} <= set(psimodpy.__all__)


def test_malformed_id_line_raises_parse_error_with_line(tmp_path):
    path = _obo(tmp_path, "[Term]\nid: MOD:abc\nname: x\n")
    with pytest.raises(PsimodParseError, match=r"line \d+"):
        parse_obo(path)


def test_malformed_mass_raises_parse_error_with_entry(tmp_path):
    path = _obo(tmp_path, _term(1, "x", 'xref: DiffMono: "not-a-number"'))
    with pytest.raises(PsimodParseError, match="MOD:00001"):
        parse_obo(path)


def test_malformed_formal_charge_raises_parse_error(tmp_path):
    path = _obo(tmp_path, _term(1, "x", 'xref: FormalCharge: "abc"'))
    with pytest.raises(PsimodParseError):
        parse_obo(path)


def test_block_missing_name_is_skipped_with_warning(tmp_path):
    path = _obo(tmp_path, "[Term]\nid: MOD:00001\n", _term(2, "ok"))
    with pytest.warns(UserWarning, match="MOD:00001"):
        db = parse_obo(path)
    assert [e.id for e in db] == [2]


def test_block_missing_id_is_skipped_with_warning(tmp_path):
    path = _obo(tmp_path, "[Term]\nname: orphan\n", _term(2, "ok"))
    with pytest.warns(UserWarning, match="orphan"):
        db = parse_obo(path)
    assert [e.id for e in db] == [2]


def test_unrecognised_line_syntax_warns(tmp_path):
    path = _obo(tmp_path, _term(1, "x", 'synonym: "s" EXACT PSI-MOD-label [PubMed:1]\nis_a: GO:0000001'))
    with pytest.warns(UserWarning, match="unrecognised"):
        db = parse_obo(path)
    assert db[1].synonyms == ()
    assert db[1].is_a == ()


@pytest.mark.parametrize(
    ("extra", "check"),
    [
        ('synonym: "s" EXACT New-label []', lambda e: e.synonyms[0].type == "New-label"),
        ("relationship: new_rel MOD:00002", lambda e: e.relationships[0].type == "new_rel"),
        ('xref: TermSpec: "internal"', lambda e: e.term_spec == "internal"),
        ('xref: Source: "synthetic"', lambda e: e.source == "synthetic"),
    ],
)
def test_unknown_enum_value_kept_as_raw_string_with_warning(tmp_path, extra, check):
    path = _obo(tmp_path, _term(1, "x", extra), _term(2, "y"))
    with pytest.warns(UserWarning, match="unknown"):
        db = parse_obo(path)
    assert check(db[1])


def test_bundled_obo_parses_without_warnings():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        psimodpy.load()


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------


def test_duplicate_id_raises(tmp_path):
    path = _obo(tmp_path, _term(1, "a"), _term(1, "b"))
    with pytest.raises(PsimodError, match="MOD:00001"):
        parse_obo(path)


def test_duplicate_id_in_constructor_raises(db):
    entry = db[46]
    with pytest.raises(PsimodError):
        PsiModDatabase([entry, entry])


def test_duplicate_name_first_wins(tmp_path):
    path = _obo(tmp_path, _term(1, "Same"), _term(2, "same"))
    db = parse_obo(path)
    assert db.get_by_name("same").id == 1


def test_duplicate_name_prefers_non_obsolete(tmp_path):
    path = _obo(tmp_path, _term(1, "Same", "is_obsolete: true"), _term(2, "same"), _term(3, "same"))
    db = parse_obo(path)
    assert db.get_by_name("same").id == 2


@pytest.mark.parametrize(("name", "expected"), [("L-methionine (R)-sulfoxide", 720), ("desmosine", 1933)])
def test_real_duplicate_names_resolve_to_current_term(db, name, expected):
    assert db.get_by_name(name).id == expected
    assert db[name].id == expected


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["foo", "", "MOD:abc", "  ", True, False, 34.0, None])
def test_get_by_id_invalid_returns_none(db, key):
    assert db.get_by_id(key) is None  # ty: ignore[invalid-argument-type]


def test_get_by_id_bool_is_not_an_id(db):
    assert db.get_by_id(1) is not None
    assert db.get_by_id(True) is None
    assert True not in db


# ---------------------------------------------------------------------------
# load / download / constructor
# ---------------------------------------------------------------------------


def test_load_source_path(tmp_path):
    path = _obo(tmp_path, _term(1, "x"))
    db = psimodpy.load(path)
    assert [e.id for e in db] == [1]
    assert db.header_lines[0] == "format-version: 1.2"


def test_load_exclude_obsolete_keeps_header_lines():
    db = psimodpy.load(include_obsolete=False)
    assert db.header_lines == psimodpy.load().header_lines
    assert db.header_lines
    assert len(db) == 1996


def test_load_from_source_exclude_obsolete(tmp_path):
    path = _obo(tmp_path, _term(1, "x", "is_obsolete: true"), _term(2, "y"))
    db = psimodpy.load(path, include_obsolete=False)
    assert [e.id for e in db] == [2]
    assert db.header_lines


def test_load_refresh_downloads(tmp_path):
    path = _obo(tmp_path, _term(7, "fresh"))
    with patch("psimodpy._download.download", return_value=path) as mock_download:
        db = psimodpy.load(refresh=True)
    mock_download.assert_called_once_with(force=True)
    assert [e.id for e in db] == [7]


def test_load_keyword_only_options():
    with pytest.raises(TypeError):
        psimodpy.load(None, True)  # ty: ignore[too-many-positional-arguments]


def test_load_from_is_deprecated(tmp_path):
    path = _obo(tmp_path, _term(1, "x"))
    with pytest.deprecated_call():
        db = psimodpy.load_from(path)
    assert len(db) == 1


def test_download_obo_is_deprecated_alias(tmp_path):
    cached = tmp_path / "PSI-MOD.obo"
    cached.write_text("cached")
    with pytest.deprecated_call():
        assert psimodpy.download_obo(cached) == cached


def test_download_exported():
    assert "download" in psimodpy.__all__
    assert psimodpy.download is psimodpy._download.download


def test_constructor_accepts_any_iterable(db):
    entries = (db[1], db[46])
    assert len(PsiModDatabase(entries)) == 2
    assert len(PsiModDatabase(frozenset(entries))) == 2
    assert len(PsiModDatabase({e.id: e for e in entries}.values())) == 2


def test_version_in_all():
    assert "__version__" in psimodpy.__all__


# ---------------------------------------------------------------------------
# Formulas and definition_ref
# ---------------------------------------------------------------------------


def test_dict_composition_drops_zero_counts(db):
    assert db[46].dict_composition == {"O": 3, "P": 1, "H": 1}


def test_dict_formula_drops_zero_counts(db):
    for entry in db:
        for comp in (entry.dict_composition, entry.dict_formula):
            if comp is not None:
                assert 0 not in comp.values(), entry.id


def test_proforma_formula(db):
    assert db[46].proforma_formula == "HO3P"
    assert db[452].proforma_formula == "[13C3]H4O"
    for entry in db:
        if entry.proforma_formula is not None:
            assert " " not in entry.proforma_formula


def test_deprecated_formula_aliases(db):
    entry = db[46]
    with pytest.deprecated_call():
        assert entry.dict_diff_formula == entry.dict_composition
    with pytest.deprecated_call():
        assert entry.proforma_diff_formula == entry.proforma_formula


def test_definition_ref_is_bracketless(db):
    assert db[46].definition_ref.startswith("ChEBI:15811, ")
    for entry in db:
        assert not entry.definition_ref.startswith("["), entry.id
        assert not entry.definition_ref.endswith("]"), entry.id


def test_definition_ref_default_is_empty(tmp_path):
    path = _obo(tmp_path, "[Term]\nid: MOD:00001\nname: x\n")
    assert parse_obo(path)[1].definition_ref == ""


def test_empty_definition_ref_round_trips(tmp_path):
    path = _obo(tmp_path, _term(1, "x"), '[Term]\nid: MOD:00002\nname: y\ndef: "d" []\n')
    db = parse_obo(path)
    assert db[1].definition_ref == "PubMed:1, RESID:AA0001"
    assert db[2].definition_ref == ""
    out = tmp_path / "out.obo"
    db.write_obo(out)
    text = out.read_text()
    assert 'def: "A definition." [PubMed:1, RESID:AA0001]' in text
    assert 'def: "d" []' in text
    assert parse_obo(out)[2].definition_ref == ""
