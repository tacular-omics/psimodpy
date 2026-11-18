"""Tests for OBO 1.2 escape decoding on parse and escaping on write."""

from __future__ import annotations

import dataclasses
import warnings
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from psimodpy import PsiModDatabase, load, parse_obo, write_obo
from psimodpy.models import Synonym, SynonymType

_BASE = load()["MOD:00046"]
_SETTINGS = settings(deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
_ALPHABET = st.sampled_from(list('abcABC012"\\[]{}():, \n\t'))
_FREE_TEXT = st.text(_ALPHABET, min_size=1, max_size=40)

_DBXREF_ID_STRUCTURAL = frozenset({"\\", ",", '"', "{", "}"})


def _fmt_dbxref_id(raw: str) -> str:
    return "".join(f"\\{ch}" if ch in _DBXREF_ID_STRUCTURAL else ch for ch in raw)


def _fmt_dbxref_desc(raw: str) -> str:
    escaped = raw.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


@st.composite
def _dbxref_citation(draw: st.DrawFn) -> str:
    ident_raw = draw(st.text(st.sampled_from(list('abc012"\\[]{}():,\n\t ')), min_size=1, max_size=12))
    if not ident_raw.strip(" \t"):
        ident_raw = "id"
    ident_raw = ident_raw.lstrip(" \t") or "id"
    has_desc = draw(st.booleans())
    has_mod = draw(st.booleans())
    if (has_desc or has_mod) and ident_raw[-1] in (" ", "\t"):
        ident_raw = ident_raw.rstrip(" \t") or "id"
    ident = _fmt_dbxref_id(ident_raw)
    out = ident
    if has_desc:
        sep1 = draw(st.sampled_from([" ", "  ", "\t"]))
        desc_raw = draw(st.text(st.sampled_from(list('abc012"\\[]{}():, \n\t')), max_size=16))
        out += sep1 + _fmt_dbxref_desc(desc_raw)
    if has_mod:
        sep2 = draw(st.sampled_from(["", " ", "  ", "\t"]))
        mod_val = draw(st.text(st.sampled_from(list('abc012"\\[]{}():, \n\t')), max_size=10))
        out += sep2 + f"{{source={_fmt_dbxref_desc(mod_val)}}}"
    return out


@st.composite
def _ref_list(draw: st.DrawFn) -> str:
    kind = draw(st.sampled_from(["empty", "spaces", "list"]))
    if kind == "empty":
        return ""
    if kind == "spaces":
        return " " * draw(st.integers(min_value=1, max_value=5))
    items = draw(st.lists(_dbxref_citation(), min_size=1, max_size=4))
    seps = draw(
        st.lists(
            st.sampled_from([",", ", ", " , ", "\t, ", "  ,  "]),
            min_size=len(items) - 1,
            max_size=len(items) - 1,
        )
    )
    lead = " " * draw(st.integers(min_value=0, max_value=2))
    tail = " " * draw(st.integers(min_value=0, max_value=2))
    body = "".join(s + it for s, it in zip(["", *seps], items, strict=True))
    return lead + body + tail


_REF_TEXT = _ref_list()

_ALL_ESCAPES = [
    ("\\n", "\n"),
    ("\\W", " "),
    ("\\t", "\t"),
    ("\\:", ":"),
    ("\\,", ","),
    ('\\"', '"'),
    ("\\\\", "\\"),
    ("\\(", "("),
    ("\\)", ")"),
    ("\\[", "["),
    ("\\]", "]"),
    ("\\{", "{"),
    ("\\}", "}"),
]

_DBXREF_STRUCTURAL = {"\\,", '\\"', "\\\\", "\\{", "\\}"}


def test_parse_obo_decodes_an_escaped_carriage_return(tmp_path: Path) -> None:
    r"""``\r`` decodes to a carriage return, so a value holding one survives a file.

    Neither escape table lists it. The 1.4 grammar accepts a backslash before any letter, a
    carriage return cannot appear literally in a value, and fastobo writes it as ``\r``.
    """
    obo = tmp_path / "cr.obo"
    obo.write_text(
        "format-version: 1.2\n\n[Term]\nid: MOD:90901\nname: a\\rb\ncomment: c\\rd\n"
        'def: "e\\rf" [DB:g\\rh]\nsynonym: "i\\rj" EXACT PSI-MOD-label []\n',
        encoding="utf-8",
    )
    entry = parse_obo(obo)[90901]
    assert entry.name == "a\rb"
    assert entry.comment == "c\rd"
    assert entry.definition == "e\rf"
    assert entry.definition_ref == "DB:g\rh"
    assert [s.value for s in entry.synonyms] == ["i\rj"]


def test_round_trip_carriage_return_in_every_free_text_field(db: PsiModDatabase, tmp_path: Path) -> None:
    r"""A carriage return round-trips as ``\r`` and never reaches the file as a bare byte.

    A bare carriage return ends the line: the file is read in text mode, where universal
    newlines turn it into a line break, so before this the value was truncated at it in
    silence (``"a\rb"`` came back as ``"a"``) or the whole clause was dropped with a warning.
    """
    entry = dataclasses.replace(
        db["MOD:00046"],
        id=90902,
        name="a\rb",
        definition="c\rd",
        definition_ref="DB:e\rf",
        comment="g\rh",
        synonyms=(Synonym(value="i\rj", type=SynonymType.PSI_MOD_LABEL, scope="EXACT"),),
    )
    out = tmp_path / "cr_round_trip.obo"
    write_obo([entry], out)

    raw = out.read_bytes()
    assert b"\r" not in raw, "a carriage return reached the file as a bare byte"
    assert raw.count(b"\\r") == 5

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        back = parse_obo(out)[90902]
    assert back.name == entry.name
    assert back.definition == entry.definition
    assert back.definition_ref == entry.definition_ref
    assert back.comment == entry.comment
    assert [s.value for s in back.synonyms] == ["i\rj"]

    again = tmp_path / "cr_again.obo"
    write_obo([back], again)
    assert again.read_bytes() == raw


def test_round_trip_literal_backslash_r_stays_literal(db: PsiModDatabase, tmp_path: Path) -> None:
    r"""A stored backslash followed by ``r`` is written ``\\r``, so it never reads back as a return.

    The free-text fields hold the decoded value and come back identical. ``definition_ref``
    holds the escaped form, so a lone backslash in it is re-encoded once, exactly as a lone
    brace is (``DB:a}b`` becomes ``DB:a\}b``), and is then unchanged by every later round trip.
    """
    entry = dataclasses.replace(
        db["MOD:00046"],
        id=90903,
        name="a\\rb",
        definition="c\\rd",
        definition_ref="DB:e\\rf",
        comment="g\\rh",
        synonyms=(),
    )
    out = tmp_path / "literal_backslash_r.obo"
    write_obo([entry], out)
    text = out.read_text(encoding="utf-8")
    assert "name: a\\\\rb" in text
    assert "comment: g\\\\rh" in text
    assert "[DB:e\\\\rf]" in text
    back = parse_obo(out)[90903]
    assert back.name == entry.name
    assert back.definition == entry.definition
    assert back.comment == entry.comment
    assert "\r" not in back.name + back.definition + back.comment, "a literal backslash became a return"
    assert back.definition_ref == "DB:e\\\\rf"

    again = tmp_path / "literal_backslash_r_again.obo"
    write_obo([back], again)
    assert again.read_bytes() == out.read_bytes()


@pytest.mark.parametrize(("escaped", "decoded"), _ALL_ESCAPES)
def test_parse_obo_decodes_all_obo_1_2_escapes(tmp_path: Path, escaped: str, decoded: str) -> None:
    obo = tmp_path / "escapes.obo"
    obo.write_text(
        f"""format-version: 1.2

[Term]
id: MOD:99990
name: a {escaped} b
def: "def {escaped} text" [ref {escaped} 1]
synonym: "syn {escaped} val" EXACT PSI-MOD-label []
comment: cmt {escaped} end
xref: GNOme: "gn {escaped} x"
""",
        encoding="utf-8",
    )
    entry = parse_obo(obo)[99990]
    assert entry.name == f"a {decoded} b"
    assert entry.definition == f"def {decoded} text"
    expected_ref = f"ref {escaped} 1" if escaped in _DBXREF_STRUCTURAL else f"ref {decoded} 1"
    assert entry.definition_ref == expected_ref
    assert entry.synonyms[0].value == f"syn {decoded} val"
    assert entry.comment == f"cmt {decoded} end"
    assert entry.xref_gnome == f"gn {decoded} x"


def test_parse_conformant_escaped_quotes(tmp_path: Path) -> None:
    obo = tmp_path / "conformant.obo"
    obo.write_text(
        'format-version: 1.2\n\n[Term]\nid: MOD:99991\nname: quoted \\"name\\"\ndef: "A 5\\" rod" [PubMed:1]\n',
        encoding="utf-8",
    )
    entry = parse_obo(obo)[99991]
    assert entry.name == 'quoted "name"'
    assert entry.definition == 'A 5" rod'
    assert entry.definition_ref == "PubMed:1"


def test_parse_unquoted_uniprot_ptm_xref_decodes_escapes(tmp_path: Path) -> None:
    obo = tmp_path / "legacy_xref.obo"
    obo.write_text(
        "format-version: 1.2\n\n[Term]\nid: MOD:99989\nname: legacy\nxref: uniprot.ptm:PTM\\:0369\n",
        encoding="utf-8",
    )
    entry = parse_obo(obo)[99989]
    assert entry.xref_uniprot_ptm == "PTM:0369"


@pytest.mark.parametrize(
    "xref_line",
    [
        'xref: uniprot.ptm:PTM\\:0369 {source="ext"} ! note',
        'xref: uniprot.ptm:PTM\\:0369 {source="ext"}',
        "xref: uniprot.ptm:PTM\\:0369 ! note",
        'xref: uniprot.ptm:PTM\\:0369{source="ext"}',
    ],
)
def test_parse_unquoted_uniprot_ptm_xref_with_modifiers_and_comments(tmp_path: Path, xref_line: str) -> None:
    obo = tmp_path / "legacy_xref_trailing.obo"
    obo.write_text(
        f"format-version: 1.2\n\n[Term]\nid: MOD:99986\nname: legacy trailing\n{xref_line}\n",
        encoding="utf-8",
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        entry = parse_obo(obo)[99986]
    assert caught == []
    assert entry.xref_uniprot_ptm == "PTM:0369"


def test_writer_escapes_quotes_and_braces_in_free_text(db: PsiModDatabase, tmp_path: Path) -> None:
    entry = dataclasses.replace(
        db["MOD:00046"],
        id=99992,
        name='a {source="x"}',
        comment='note {flag="1"}',
        synonyms=(),
    )
    out = tmp_path / "free_text.obo"
    write_obo([entry], out)
    text = out.read_text(encoding="utf-8")
    assert r"name: a \{source=\"x\"\}" in text
    assert r"comment: note \{flag=\"1\"\}" in text
    back = parse_obo(out)[99992]
    assert back.name == 'a {source="x"}'
    assert back.comment == 'note {flag="1"}'


def test_definition_ref_boundary_spaces_round_trip(db: PsiModDatabase, tmp_path: Path) -> None:
    obo = tmp_path / "spaces.obo"
    obo.write_text(
        'format-version: 1.2\n\n[Term]\nid: MOD:99993\nname: space ref\ndef: "d" [\\WPubMed:1\\W]\n',
        encoding="utf-8",
    )
    entry = parse_obo(obo)[99993]
    assert entry.definition_ref == " PubMed:1 "

    out = tmp_path / "spaces_out.obo"
    write_obo([entry], out)
    assert r"[\WPubMed:1\W]" in out.read_text(encoding="utf-8")
    assert parse_obo(out)[99993].definition_ref == " PubMed:1 "

    spaces_only = dataclasses.replace(entry, id=99994, definition_ref="   ")
    out2 = tmp_path / "spaces_only.obo"
    write_obo([spaces_only], out2)
    assert r"[\W\W\W]" in out2.read_text(encoding="utf-8")
    assert parse_obo(out2)[99994].definition_ref == "   "


def test_definition_ref_quoted_description_preserves_syntax(tmp_path: Path) -> None:
    obo = tmp_path / "desc.obo"
    obo.write_text(
        'format-version: 1.2\n\n[Term]\nid: MOD:99985\nname: cited\ndef: "d" [PubMed:1 "paper title"]\n',
        encoding="utf-8",
    )
    entry = parse_obo(obo)[99985]
    assert entry.definition_ref == 'PubMed:1 "paper title"'

    out = tmp_path / "desc_out.obo"
    write_obo([entry], out)
    text = out.read_text(encoding="utf-8")
    assert 'def: "d" [PubMed:1 "paper title"]\n' in text
    assert parse_obo(out)[99985].definition_ref == 'PubMed:1 "paper title"'


@pytest.mark.parametrize(
    ("raw_ref", "expected_written", "expected_parsed"),
    [
        (
            'PubMed:1 "paper title" , RESID:AA0001',
            'def: "d" [PubMed:1 "paper title" , RESID:AA0001]\n',
            'PubMed:1 "paper title" , RESID:AA0001',
        ),
        (
            r'PubMed:1 "paper title"\W, RESID:AA0001',
            'def: "d" [PubMed:1 "paper title" , RESID:AA0001]\n',
            'PubMed:1 "paper title" , RESID:AA0001',
        ),
        (
            'PubMed:1 "paper title" {source="ext"} , RESID:AA0001',
            'def: "d" [PubMed:1 "paper title" {source="ext"} , RESID:AA0001]\n',
            'PubMed:1 "paper title" {source="ext"} , RESID:AA0001',
        ),
        (
            'PubMed:1 {source="ext"} , RESID:AA0001',
            'def: "d" [PubMed:1 {source="ext"} , RESID:AA0001]\n',
            'PubMed:1 {source="ext"} , RESID:AA0001',
        ),
        (
            'PubMed:1 "paper title"\t, RESID:AA0001',
            'def: "d" [PubMed:1 "paper title"\t, RESID:AA0001]\n',
            'PubMed:1 "paper title"\t, RESID:AA0001',
        ),
        (
            'PubMed:1{source="ext"}, RESID:AA0001',
            'def: "d" [PubMed:1{source="ext"}, RESID:AA0001]\n',
            'PubMed:1{source="ext"}, RESID:AA0001',
        ),
        (
            'PubMed:1 "paper title"{source="ext"}, RESID:AA0001',
            'def: "d" [PubMed:1 "paper title"{source="ext"}, RESID:AA0001]\n',
            'PubMed:1 "paper title"{source="ext"}, RESID:AA0001',
        ),
    ],
)
def test_definition_ref_whitespace_before_separator_preserves_syntax(
    tmp_path: Path, raw_ref: str, expected_written: str, expected_parsed: str
) -> None:
    obo = tmp_path / "ws_sep.obo"
    obo.write_text(
        f'format-version: 1.2\n\n[Term]\nid: MOD:99980\nname: ws sep\ndef: "d" [{raw_ref}]\n',
        encoding="utf-8",
    )
    entry = parse_obo(obo)[99980]
    assert entry.definition_ref == expected_parsed

    out = tmp_path / "ws_sep_out.obo"
    write_obo([entry], out)
    text = out.read_text(encoding="utf-8")
    assert expected_written in text
    assert parse_obo(out)[99980].definition_ref == expected_parsed


def test_definition_ref_quoted_description_with_escapes_and_modifiers(tmp_path: Path) -> None:
    obo = tmp_path / "desc_complex.obo"
    obo.write_text(
        "format-version: 1.2\n\n"
        "[Term]\n"
        "id: MOD:99984\n"
        "name: cited complex\n"
        'def: "d" [PubMed:1 "say \\"hi\\", see [1]", RESID:AA0001 "line1\\nline2" {source="ext"}]\n',
        encoding="utf-8",
    )
    entry = parse_obo(obo)[99984]
    out = tmp_path / "desc_complex_out.obo"
    write_obo([entry], out)
    text = out.read_text(encoding="utf-8")
    assert 'def: "d" [PubMed:1 "say \\"hi\\", see [1]", RESID:AA0001 "line1\\nline2" {source="ext"}]\n' in text
    assert parse_obo(out)[99984].definition_ref == entry.definition_ref


@pytest.mark.parametrize(
    ("escaped_input", "separator_input", "expected_escaped_ref", "expected_separator_ref"),
    [
        ("DB:a\\W, DB:b", "DB:a , DB:b", r"DB:a\W, DB:b", "DB:a , DB:b"),
        ('DB:a\\W "paper"', 'DB:a  "paper"', r'DB:a\W "paper"', 'DB:a  "paper"'),
        ('DB:a\\W{source="ext"}', 'DB:a {source="ext"}', r'DB:a\W{source="ext"}', 'DB:a {source="ext"}'),
        ("DB:a, \\WDB:b", "DB:a,  DB:b", r"DB:a, \WDB:b", "DB:a,  DB:b"),
        ("DB:a\\t, DB:b", "DB:a\t, DB:b", r"DB:a\t, DB:b", "DB:a\t, DB:b"),
    ],
)
def test_definition_ref_escaped_id_whitespace_distinct_from_separator(
    tmp_path: Path,
    escaped_input: str,
    separator_input: str,
    expected_escaped_ref: str,
    expected_separator_ref: str,
) -> None:
    obo = tmp_path / "ws_id_vs_sep.obo"
    obo.write_text(
        "format-version: 1.2\n\n"
        f'[Term]\nid: MOD:99978\nname: id ws\ndef: "d" [{escaped_input}]\n\n'
        f'[Term]\nid: MOD:99979\nname: sep ws\ndef: "d" [{separator_input}]\n',
        encoding="utf-8",
    )
    parsed = parse_obo(obo)
    assert parsed[99978].definition_ref == expected_escaped_ref
    assert parsed[99979].definition_ref == expected_separator_ref
    assert parsed[99978].definition_ref != parsed[99979].definition_ref

    out = tmp_path / "ws_id_vs_sep_out.obo"
    write_obo([parsed[99978], parsed[99979]], out)
    text = out.read_text(encoding="utf-8")
    assert f'def: "d" [{escaped_input}]\n' in text
    assert f'def: "d" [{separator_input}]\n' in text

    reparsed = parse_obo(out)
    assert reparsed[99978].definition_ref == expected_escaped_ref
    assert reparsed[99979].definition_ref == expected_separator_ref


@pytest.mark.parametrize(
    ("raw_ref", "expected_parsed"),
    [
        (r"DB:a\W\t\W", "DB:a \t "),
        (r"\W\t\WDB:a", " \t DB:a"),
        (r"\W\t\W", " \t "),
        ("DB:a\t\\W", "DB:a\t\\W"),
        ("\\W\tDB:a", "\\W\tDB:a"),
        (r"DB:a\t\W", "DB:a\t "),
        (r"\W\tDB:a", " \tDB:a"),
        ('DB:a "paper"\\W\\t\\W', 'DB:a "paper" \t '),
    ],
)
def test_definition_ref_mixed_boundary_whitespace_round_trip(
    tmp_path: Path, raw_ref: str, expected_parsed: str
) -> None:
    obo = tmp_path / "mixed_boundary.obo"
    obo.write_text(
        f'format-version: 1.2\n\n[Term]\nid: MOD:99977\nname: mixed boundary\ndef: "d" [{raw_ref}]\n',
        encoding="utf-8",
    )
    entry = parse_obo(obo)[99977]
    assert entry.definition_ref == expected_parsed

    out = tmp_path / "mixed_boundary_out.obo"
    write_obo([entry], out)
    assert f'def: "d" [{raw_ref}]\n' in out.read_text(encoding="utf-8")
    assert parse_obo(out)[99977].definition_ref == expected_parsed


def test_definition_ref_escaped_comma_distinct_from_list_separator(tmp_path: Path) -> None:
    obo = tmp_path / "commas.obo"
    obo.write_text(
        "format-version: 1.2\n\n"
        '[Term]\nid: MOD:99981\nname: escaped comma\ndef: "d" [DB:a\\,b]\n\n'
        '[Term]\nid: MOD:99982\nname: list comma\ndef: "d" [DB:a,b]\n\n'
        '[Term]\nid: MOD:99983\nname: escaped slash before comma\ndef: "d" [DB:a\\\\,b]\n',
        encoding="utf-8",
    )
    parsed = parse_obo(obo)
    assert parsed[99981].definition_ref == r"DB:a\,b"
    assert parsed[99982].definition_ref == "DB:a,b"
    assert parsed[99983].definition_ref == r"DB:a\\,b"

    out = tmp_path / "commas_out.obo"
    write_obo([parsed[99981], parsed[99982], parsed[99983]], out)
    text = out.read_text(encoding="utf-8")
    assert 'def: "d" [DB:a\\,b]\n' in text
    assert 'def: "d" [DB:a,b]\n' in text
    assert 'def: "d" [DB:a\\\\,b]\n' in text

    reparsed = parse_obo(out)
    assert reparsed[99981].definition_ref == r"DB:a\,b"
    assert reparsed[99982].definition_ref == "DB:a,b"
    assert reparsed[99983].definition_ref == r"DB:a\\,b"


def test_malformed_unescaped_quotes_warn_instead_of_silently_truncating(tmp_path: Path) -> None:
    obo = tmp_path / "malformed.obo"
    obo.write_text(
        """format-version: 1.2

[Term]
id: MOD:99988
name: malformed test
def: "A 5" [sic] rod" [PubMed:1]
synonym: "syn "extra" val" EXACT PSI-MOD-label []
synonym: "good" EXACT PSI-MOD-label [] trailing garbage
""",
        encoding="utf-8",
    )
    with pytest.warns(UserWarning, match="unrecognised"):
        entry = parse_obo(obo)[99988]
    assert entry.definition == ""
    assert entry.definition_ref == ""
    assert entry.synonyms == ()


def test_valid_obo_trailing_modifiers_and_comments_are_accepted(tmp_path: Path) -> None:
    obo = tmp_path / "modifiers.obo"
    obo.write_text(
        """format-version: 1.2

[Term]
id: MOD:99987
name: modifier test
def: "A 5\\" rod" [PubMed:1] {source="curated"} ! inline note
synonym: "syn \\"q\\"" EXACT PSI-MOD-label [] {scope="alt"} ! synonym note
xref: GNOme: "gn" {source="ext"} ! xref note
""",
        encoding="utf-8",
    )
    entry = parse_obo(obo)[99987]
    assert entry.definition == 'A 5" rod'
    assert entry.definition_ref == "PubMed:1"
    assert entry.synonyms == (Synonym(value='syn "q"', type=SynonymType.PSI_MOD_LABEL, scope="EXACT"),)
    assert entry.xref_gnome == "gn"


def test_round_trip_definition_with_embedded_quote_and_brackets(db: PsiModDatabase, tmp_path: Path) -> None:
    entry = dataclasses.replace(
        db["MOD:00046"],
        id=99996,
        name="quote test",
        definition='A 5" [sic] rod',
        definition_ref="PubMed:1",
        synonyms=(),
    )
    out = tmp_path / "q.obo"
    write_obo([entry], out)
    back = parse_obo(out)[99996]
    assert back.definition == 'A 5" [sic] rod'
    assert back.definition_ref == "PubMed:1"


def test_round_trip_synonym_with_quotes(db: PsiModDatabase, tmp_path: Path) -> None:
    syn = Synonym(value='syn "with" quotes', type=SynonymType.PSI_MOD_LABEL, scope="EXACT")
    entry = dataclasses.replace(
        db["MOD:00046"],
        id=99997,
        synonyms=(syn,),
    )
    out = tmp_path / "syn.obo"
    write_obo([entry], out)
    back = parse_obo(out)[99997]
    assert back.synonyms == (syn,)


def test_round_trip_double_backslash_before_n(db: PsiModDatabase, tmp_path: Path) -> None:
    entry = dataclasses.replace(
        db["MOD:00046"],
        id=99998,
        name="literal \\n sequence",
        definition="keep \\n and \\t verbatim",
        comment="path C:\\new\\tab",
        synonyms=(),
    )
    out = tmp_path / "slashes.obo"
    write_obo([entry], out)
    back = parse_obo(out)[99998]
    assert back.name == entry.name
    assert back.definition == entry.definition
    assert back.comment == entry.comment


@_SETTINGS
@given(
    name=_FREE_TEXT,
    definition=_FREE_TEXT,
    definition_ref=_REF_TEXT,
    syn_val=_FREE_TEXT,
    comment=st.one_of(st.none(), _FREE_TEXT),
    gnome=st.one_of(st.none(), _FREE_TEXT),
)
def test_hypothesis_escape_round_trip(
    tmp_path_factory: pytest.TempPathFactory,
    name: str,
    definition: str,
    definition_ref: str,
    syn_val: str,
    comment: str | None,
    gnome: str | None,
) -> None:
    syn = Synonym(value=syn_val, type=SynonymType.PSI_MOD_LABEL, scope="EXACT")
    entry = dataclasses.replace(
        _BASE,
        id=99995,
        name=name,
        definition=definition,
        definition_ref=definition_ref,
        synonyms=(syn,),
        comment=comment,
        xref_gnome=gnome,
    )
    out = tmp_path_factory.mktemp("hyp") / "rt.obo"
    write_obo([entry], out)
    back = parse_obo(out)[99995]
    assert back.name == entry.name
    assert back.definition == entry.definition
    assert back.definition_ref == entry.definition_ref
    assert back.synonyms == entry.synonyms
    assert back.comment == entry.comment
    assert back.xref_gnome == entry.xref_gnome
