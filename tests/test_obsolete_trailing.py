"""Regression for OBO 1.4 comments and modifiers on is_obsolete (#109)."""

import warnings

import pytest

import psimodpy


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", True),
        ("true   ", True),
        ("true ! retired 2020", True),
        ('true {x="y"}', True),
        ('true {x="y"} ! retired 2020', True),
        ("false", False),
        ("false ! note", False),
        ('false {x="y"} ! note', False),
        ("false   ", False),
    ],
)
def test_obsolete_trailing_fields(tmp_path, value, expected):
    obo = tmp_path / "test.obo"
    obo.write_text(
        'format-version: 1.4\n\n[Term]\nid: MOD:00001\nname: x\ndef: "d" [PubMed:1]\n'
        f"is_obsolete: {value}\n\n", encoding="utf-8"
    )
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        entries = list(psimodpy.parse_obo(obo))
    assert len(entries) == 1
    assert entries[0].is_obsolete is expected
    assert seen == [], [str(w.message) for w in seen]


@pytest.mark.parametrize("value", ["truish", "true nonsense", "true {x=y", "False"])
def test_malformed_obsolete_is_not_silently_accepted(tmp_path, value):
    obo = tmp_path / "test.obo"
    obo.write_text(
        'format-version: 1.4\n\n[Term]\nid: MOD:00001\nname: x\ndef: "d" [PubMed:1]\n'
        f"is_obsolete: {value}\n\n", encoding="utf-8"
    )
    with pytest.warns(UserWarning, match="unrecognised 'is_obsolete:'"):
        entry = psimodpy.parse_obo(obo)[1]
    assert entry.is_obsolete is False
