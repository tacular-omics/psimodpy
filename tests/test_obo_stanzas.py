"""Non-term OBO stanzas survive parsing, filtering and export."""

from collections import Counter
from importlib.resources import files

import pytest

from psimodpy import PsiModDatabase, PsimodParseError, load, parse_obo, write_obo


def test_bundled_export_keeps_typedefs(db: PsiModDatabase, tmp_path) -> None:
    text = db.write_obo(tmp_path / "out.obo").read_text(encoding="utf-8")
    assert text.splitlines().count("[Typedef]") == 4


def test_bundled_stanzas_round_trip(db: PsiModDatabase, tmp_path) -> None:
    original = files("psimodpy.data").joinpath("PSI-MOD.obo").read_text(encoding="utf-8")
    start = original.index("[Typedef]")
    assert db.raw_stanza_lines == tuple(original[start:].splitlines())
    out = db.write_obo(tmp_path / "roundtrip.obo")
    text = out.read_text(encoding="utf-8")
    assert Counter(line for line in text.splitlines() if line.startswith("[")) == {
        "[Term]": 2116,
        "[Typedef]": 4,
    }
    assert text.endswith("\n".join(db.raw_stanza_lines) + "\n")
    ids = ["contains", "derives_from", "has_functional_parent", "part_of"]
    positions = [text.index(f"\nid: {value}\n", text.index("[Typedef]")) for value in ids]
    assert positions == sorted(positions)
    back = parse_obo(out)
    assert list(back) == list(db)
    assert len(back) == 2116
    assert back.header_lines == db.header_lines
    assert len(back.header_lines) == 32
    assert back.raw_stanza_lines == db.raw_stanza_lines
    assert sum(len(entry.relationships) for entry in back) == 156


@pytest.mark.parametrize("ending", ["", "\n", "\n\n"])
def test_unknown_stanzas_move_after_terms_verbatim(tmp_path, ending: str) -> None:
    first = "[Typedef]\nid: first\ncomment:  keep  spaces \n\n"
    last = "[Typedef]\nid: last\n\n[Instance]\nid: sample" + ending
    source = tmp_path / "source.obo"
    source.write_text(
        "format-version: 1.2\n\n" + first + "[Term]\nid: MOD:99996\nname: test\n\n" + last,
        encoding="utf-8",
    )
    db = parse_obo(source)
    expected = tuple((first + last).splitlines())
    assert db.raw_stanza_lines == expected
    out = db.write_obo(tmp_path / "out.obo")
    text = out.read_text(encoding="utf-8")
    assert text.index("[Term]") < text.index("[Typedef]") < text.index("[Instance]")
    assert text.endswith("\n".join(expected) + "\n")
    assert parse_obo(out).raw_stanza_lines == expected


def test_load_without_obsolete_preserves_stanzas(tmp_path) -> None:
    db = load(include_obsolete=False)
    assert len(db) == 1971
    assert db.raw_stanza_lines == load().raw_stanza_lines
    back = parse_obo(db.write_obo(tmp_path / "filtered.obo"))
    assert back.raw_stanza_lines == db.raw_stanza_lines
    assert list(back) == list(db)


def test_stanzas_without_terms_still_raise(tmp_path) -> None:
    source = tmp_path / "source.obo"
    source.write_text("format-version: 1.2\n\n[Instance]\nid: example\n", encoding="utf-8")
    with pytest.raises(PsimodParseError, match=r"no \[Term\] stanza"):
        parse_obo(source)


def test_default_and_explicit_writer_stanzas(db: PsiModDatabase, tmp_path) -> None:
    assert PsiModDatabase([]).raw_stanza_lines == ()
    raw = ("[Instance]", "id: example")
    out = write_obo([next(iter(db))], tmp_path / "out.obo", raw_stanza_lines=iter(raw))
    assert parse_obo(out).raw_stanza_lines == raw
    assert "[Instance]" not in write_obo([], out).read_text(encoding="utf-8")


def test_term_after_unknown_without_blank_separator(tmp_path) -> None:
    source = tmp_path / "source.obo"
    source.write_text(
        "[Term]\nid: MOD:99996\nname: first\n[Instance]\nid: example\n[Term]\nid: MOD:99997\nname: second\n",
        encoding="utf-8",
    )
    db = parse_obo(source)
    assert [entry.id for entry in db] == [99996, 99997]
    assert db.raw_stanza_lines == ("[Instance]", "id: example")
    assert list(parse_obo(db.write_obo(tmp_path / "out.obo"))) == list(db)
