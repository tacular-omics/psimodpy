"""Cover the DBxref escaper's structured path, its fallback, and what each one promises.

``tests/test_obo_escapes.py`` covers the escape codec through the shapes a PSI-MOD file
carries. What is left uncovered there is the writer's citation-list machinery:
`_try_escape_citation_list` recognises ``ID "description" {modifier}`` and escapes each
component by its own rules, while every input it cannot read that way falls back to
`_escape_flat_dbxref`, which escapes the string as opaque text.

The two halves make two different promises, and the tests below state both. A genuine
citation list round-trips byte for byte. Anything else is re-encoded once into its escaped,
re-readable form and is a fixed point from then on, because `definition_ref` deliberately
keeps the structural escapes (``\\,`` ``\\"`` ``\\{`` ``\\}`` ``\\\\``) that tell a citation
list's syntax from its content. See the note in `parse_obo`'s docstring.
"""

from __future__ import annotations

import dataclasses
import warnings
from pathlib import Path

import pytest

from psimodpy import PsiModDatabase, PsiModEntry, parse_obo, write_obo
from psimodpy._obo_writer import (
    _escape_dbxref,
    _escape_dbxref_id,
    _escape_dbxref_mod,
    _escape_dbxref_quoted,
    _escape_flat_dbxref,
    _parse_citation_chunk,
    _try_escape_citation_list,
)
from psimodpy.parser import _unescape_dbxref_list, _unescape_obo


def _write_read(db: PsiModDatabase, tmp_path: Path, name: str, **fields: object) -> tuple[PsiModEntry, int]:
    """Write one entry built from MOD:00046 with ``fields`` replaced, then parse it back.

    Returns the re-parsed entry and how many warnings the parse raised, so a test can assert
    both what survived and that nothing was reported as dropped.
    """
    entry = dataclasses.replace(db[46], id=99999, **fields)
    out = tmp_path / f"{name}.obo"
    write_obo([entry], out)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        parsed = parse_obo(out).get_by_id(99999)
    assert parsed is not None, f"the entry was dropped entirely: {out.read_text(encoding='utf-8')!r}"
    return parsed, len(caught)


# Citation lists the structured path reads, with the core it writes for each. The escaped core
# is asserted as well as the round trip, because a value that round-trips says nothing about
# which of the two paths produced it.
_STRUCTURED_REFS = [
    pytest.param("PubMed:1, RESID:AA0037", "PubMed:1, RESID:AA0037", id="the-shape-the-ontology-uses"),
    pytest.param("PubMed:1,,PubMed:2", "PubMed:1,,PubMed:2", id="empty-chunk-between-separators"),
    pytest.param("PubMed:1,", "PubMed:1,", id="trailing-separator-leaves-an-empty-chunk"),
    pytest.param("", "", id="no-citation-at-all"),
    pytest.param(" PubMed:1 ", "\\WPubMed:1\\W", id="boundary-spaces-around-the-whole-list"),
    pytest.param("DB:a[b]", "DB:a\\[b\\]", id="brackets-in-an-identifier"),
    pytest.param('DB:a "desc" {m=1}', 'DB:a "desc" {m=1}', id="description-and-modifier-together"),
    pytest.param("DB:a\t{m=1}", "DB:a\t{m=1}", id="tab-between-identifier-and-modifier"),
    pytest.param("DB:a {m[1]}", "DB:a {m\\[1\\]}", id="brackets-inside-a-modifier-are-escaped"),
    pytest.param('DB:a {m="v"}', 'DB:a {m="v"}', id="quoted-value-inside-a-modifier-is-left-alone"),
    pytest.param("DB:a\\,b, PubMed:1", "DB:a\\,b, PubMed:1", id="escaped-comma-is-not-a-separator"),
    pytest.param('DB:a "d\\"q\\""', 'DB:a "d\\"q\\""', id="escaped-quotes-inside-a-description"),
]


@pytest.mark.parametrize(("ref", "escaped_core"), _STRUCTURED_REFS)
def test_a_citation_list_is_escaped_per_component_and_round_trips(
    db: PsiModDatabase, tmp_path: Path, ref: str, escaped_core: str
) -> None:
    """The structured path escapes inside each component and keeps the citation syntax."""
    assert _escape_dbxref(ref) == escaped_core
    parsed, warned = _write_read(db, tmp_path, "structured", definition_ref=ref)
    assert parsed.definition_ref == ref
    assert warned == 0


# Everything the structured path refuses, or accepts but re-escapes, named by the reason. The
# second value is what one write and one parse gives back, measured on this tree.
_RE_ENCODED_REFS = [
    pytest.param("DB:a}b", "DB:a\\}b", id="brace-closes-before-it-opens"),
    pytest.param('"only a description"', '\\"only a description\\"', id="no-identifier-before-the-quote"),
    pytest.param('DB:a"desc"', 'DB:a\\"desc\\"', id="quote-not-separated-from-the-identifier"),
    pytest.param('DB:a "unterminated', 'DB:a \\"unterminated', id="description-never-closes"),
    pytest.param('DB:a "desc" junk', 'DB:a \\"desc\\" junk', id="junk-after-the-description"),
    pytest.param("DB:a {unterminated", "DB:a \\{unterminated", id="modifier-never-closes"),
    pytest.param("DB:a {m} junk", "DB:a \\{m\\} junk", id="junk-after-the-modifier"),
    pytest.param('DB:a "d\\', 'DB:a \\"d\\\\', id="backslash-ends-the-description"),
    pytest.param("DB:a {m\\", "DB:a \\{m\\\\", id="backslash-ends-the-modifier"),
    pytest.param("trailing backslash \\", "trailing backslash \\\\", id="lone-trailing-backslash"),
    pytest.param("DB:a\\zb", "DB:a\\\\zb", id="unknown-escape-in-an-identifier"),
    pytest.param('DB:a "d\\zb"', 'DB:a "d\\\\zb"', id="unknown-escape-in-a-description"),
    pytest.param("DB:a {m\\zb}", "DB:a {m\\\\zb}", id="unknown-escape-in-a-modifier"),
]


@pytest.mark.parametrize(("ref", "re_encoded"), _RE_ENCODED_REFS)
def test_a_definition_ref_that_is_not_a_citation_list_is_re_encoded_once_then_stable(
    db: PsiModDatabase, tmp_path: Path, ref: str, re_encoded: str
) -> None:
    """Such a value gains the escapes that make it re-readable, and never gains them twice.

    Nothing is lost and nothing warns: the escaped form is the same citation list, written so
    that a reader can tell its content from its syntax. The second cycle is the point of the
    test. A writer that escaped what the parser also unescapes, or the reverse, would drift
    further on every round trip instead of settling here.
    """
    first, warned_first = _write_read(db, tmp_path, "first", definition_ref=ref)
    assert first.definition_ref == re_encoded
    assert warned_first == 0
    second, warned_second = _write_read(db, tmp_path, "second", definition_ref=first.definition_ref)
    assert second.definition_ref == re_encoded, "a non-citation definition_ref must reach a fixed point"
    assert warned_second == 0


# _parse_citation_chunk is the function the fallback hangs off: a tuple of
# (identifier, whitespace, description, whitespace, modifier, trailing whitespace), or None for
# a chunk that is not a citation. The None rows are each a separate bail-out in that function.
_CHUNKS: list[tuple[str, tuple[str, str, str | None, str, str | None, str] | None]] = [
    ("", ("", "", None, "", None, "")),
    ("PubMed:1", ("PubMed:1", "", None, "", None, "")),
    ("PubMed:1  ", ("PubMed:1", "", None, "", None, "  ")),
    ('DB:a "desc"', ("DB:a", " ", "desc", "", None, "")),
    ('DB:a "desc"  ', ("DB:a", " ", "desc", "", None, "  ")),
    ("DB:a {m=1}", ("DB:a", "", None, " ", "m=1", "")),
    ('DB:a "desc" {m=1}', ("DB:a", " ", "desc", " ", "m=1", "")),
    ('DB:a {m="}"}', ("DB:a", "", None, " ", 'm="}"', "")),
    ("DB:a}b", None),
    ('"desc"', None),
    ('DB:a"desc"', None),
    ('DB:a "desc', None),
    ('DB:a "desc" junk', None),
    ("DB:a {m", None),
    ("DB:a {m} junk", None),
    ('DB:a "d\\', None),
    ("DB:a {m\\", None),
    ("DB:a\\", None),
]


@pytest.mark.parametrize(("chunk", "expected"), _CHUNKS)
def test_parse_citation_chunk_splits_a_citation_or_refuses_it(
    chunk: str, expected: tuple[str, str, str | None, str, str | None, str] | None
) -> None:
    assert _parse_citation_chunk(chunk) == expected


@pytest.mark.parametrize("ref", [param.values[0] for param in _RE_ENCODED_REFS[:10]])
def test_the_structured_path_refuses_what_the_fallback_handles(ref: str) -> None:
    """The division of labour, asserted directly rather than inferred from the output."""
    assert _try_escape_citation_list(ref) is None


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        ("PubMed:1", "PubMed:1"),
        ("DB:a\\,b", "DB:a\\,b"),
        ("DB:a\\zb", "DB:a\\\\zb"),
        ("DB:a{b", "DB:a\\{b"),
        ("DB:a}b", "DB:a\\}b"),
        ('DB:a"b', 'DB:a\\"b'),
        ("DB:a[b]", "DB:a\\[b\\]"),
        ("DB:a\nb", "DB:a\\nb"),
        (" DB:a ", "\\WDB:a\\W"),
    ],
)
def test_escape_dbxref_id_rules(raw: str, escaped: str) -> None:
    """An identifier keeps an escape that is already structural and escapes everything else."""
    assert _escape_dbxref_id(raw) == escaped


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        ("desc", '"desc"'),
        ('desc\\"q\\"', '"desc\\"q\\""'),
        ("desc\\zb", '"desc\\\\zb"'),
        ('desc"q', '"desc\\"q"'),
        ("desc\nb", '"desc\\nb"'),
        ("desc\tb", '"desc\\tb"'),
    ],
)
def test_escape_dbxref_quoted_rules(raw: str, escaped: str) -> None:
    """A description is re-quoted, and a bare quote inside it is escaped."""
    assert _escape_dbxref_quoted(raw) == escaped


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        ("m=1", "{m=1}"),
        ("m=\\{1\\}", "{m=\\{1\\}}"),
        ("m=\\zb", "{m=\\\\zb}"),
        ("m=[1]", "{m=\\[1\\]}"),
        ('m="[1]"', '{m="[1]"}'),
        ('m="a\\zb"', '{m="a\\\\zb"}'),
        ("m=1\nx", "{m=1\\nx}"),
        ("m=1\tx", "{m=1\\tx}"),
    ],
)
def test_escape_dbxref_mod_rules(raw: str, escaped: str) -> None:
    """A modifier escapes brackets outside its own quotes and leaves them alone inside."""
    assert _escape_dbxref_mod(raw) == escaped


def test_the_flat_fallback_escapes_every_structural_character() -> None:
    assert _escape_flat_dbxref('a\\b\nc\td[e]f{g}h"i') == 'a\\\\b\\nc\\td\\[e\\]f\\{g\\}h\\"i'


def test_a_whitespace_only_definition_ref_is_encoded_not_dropped() -> None:
    assert _escape_dbxref(" \t ") == "\\W\\t\\W"


@pytest.mark.parametrize(
    ("raw", "decoded"),
    [
        ("DB:a\\,b, PubMed:1", "DB:a\\,b, PubMed:1"),
        ('DB:a "d\\"q\\"", PubMed:1', 'DB:a "d\\"q\\"", PubMed:1'),
        ("DB:a {m=\\{1\\}}", "DB:a {m=\\{1\\}}"),
        ('DB:a {m="v\\"q\\""}', 'DB:a {m="v\\"q\\""}'),
        ("DB:a\\\\b", "DB:a\\\\b"),
        ("DB:a\\zb", "DB:a\\zb"),
        ("DB:a\\(1\\)", "DB:a(1)"),
        ("DB:a\\nb", "DB:a\nb"),
        ('DB:a "d\\nq"', 'DB:a "d\nq"'),
        ("DB:a {m=\\nv}", "DB:a {m=\nv}"),
        ("no backslash at all", "no backslash at all"),
    ],
)
def test_unescape_dbxref_list_keeps_the_syntax_and_decodes_the_content(raw: str, decoded: str) -> None:
    """A structural escape stays escaped, a content escape decodes, in all three positions."""
    assert _unescape_dbxref_list(raw) == decoded


@pytest.mark.parametrize(
    ("raw", "decoded"),
    [
        ("DB:a\\W, PubMed:1", "DB:a\\W, PubMed:1"),
        ('DB:a\\W "d"', 'DB:a\\W "d"'),
        ("DB:a\\W{m=1}", "DB:a\\W{m=1}"),
        ("DB:a\\t, PubMed:1", "DB:a\\t, PubMed:1"),
        ("PubMed:1,\\Wb", "PubMed:1,\\Wb"),
        ("DB:a\\Wb", "DB:a b"),
        ("DB:a\\tb", "DB:a\tb"),
        ("\\WDB:a", " DB:a"),
        ("DB:a\\W", "DB:a "),
        ("DB:a\\W\\Wb", "DB:a  b"),
        ("DB:a \\Wb", "DB:a  b"),
        ("DB:a\\W b", "DB:a  b"),
        ("DB:a\\\\Wb", "DB:a\\\\Wb"),
        # The two rows below walk the backslash run in front of a preserved pair: an even
        # run leaves the pair real, an odd one means the backslash is itself escaped.
        ("DB:a" + "\\" * 2 + "\\W\\W, PubMed:1", "DB:a" + "\\" * 2 + "\\W\\W, PubMed:1"),
        ("DB:a" + "\\" * 2 + "W\\W, PubMed:1", "DB:a" + "\\" * 2 + "W\\W, PubMed:1"),
        ('DB:a "d\\Wq"', 'DB:a "d q"'),
        ("DB:a {m=\\Wv}", "DB:a {m= v}"),
    ],
)
def test_unescape_dbxref_list_keeps_an_identifier_whitespace_escape_only_where_it_separates(
    raw: str, decoded: str
) -> None:
    r"""In an identifier, ``\W`` and ``\t`` stay escaped where decoding them would read as the
    whitespace around a separator, and decode anywhere else. Inside a description or a
    modifier they always decode, because no separator is in play there.
    """
    assert _unescape_dbxref_list(raw) == decoded


def test_unescape_obo_leaves_an_unknown_escape_alone() -> None:
    r"""``\z`` is not an OBO escape, so both characters survive, and a lone backslash too."""
    assert _unescape_obo("a\\zb") == "a\\zb"
    assert _unescape_obo("ends with a backslash \\") == "ends with a backslash \\"
    assert _unescape_obo("no backslash at all") == "no backslash at all"


def test_whitespace_only_and_empty_free_text_round_trip(db: PsiModDatabase, tmp_path: Path) -> None:
    """A comment of spaces survives as spaces, and an empty comment stays empty."""
    spaces, warned = _write_read(db, tmp_path, "spaces", comment="   ")
    assert spaces.comment == "   "
    assert warned == 0
    empty, warned = _write_read(db, tmp_path, "empty", comment="")
    assert empty.comment == ""
    assert warned == 0
