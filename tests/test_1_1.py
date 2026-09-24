"""1.1 additions: precomputed search, ``load(cache=True)``, lazy urllib, typed lookup errors."""

from __future__ import annotations

import dataclasses
import subprocess
import sys

import pytest
from hypothesis import given
from hypothesis import strategies as st

import psimodpy
from psimodpy import PsiModDatabase, PsimodError, PsimodKeyError, PsimodParseError, load
from psimodpy.database import _load_bundled


def _old_search(db: PsiModDatabase, query: object) -> list:
    """The 1.0 search() algorithm, kept verbatim as the reference for equivalence tests."""
    if not isinstance(query, str):
        return []
    q = query.lower()
    if not q:
        return list(db)
    results = []
    for entry in db:
        if (
            q in entry.name.lower()
            or q in entry.definition.lower()
            or any(q in s.value.lower() for s in entry.synonyms)
        ):
            results.append(entry)
    return results


# ---------------------------------------------------------------- search


def _queries(db: PsiModDatabase) -> list[str]:
    qs = [
        "",
        " ",
        "phospho",
        "PHOSPHO",
        "Phospho",
        "acetyl",
        "methyl",
        "-",
        "(",
        "l-",
        "xyz-no-match",
        "\x00",
        "a\x00b",
    ]
    for i, entry in enumerate(db):
        if i % 7:
            continue
        name = entry.name
        qs += [name, name.upper(), name[:3], name[len(name) // 2 :], name[1:-1]]
        if entry.synonyms:
            qs.append(entry.synonyms[0].value[:5])
        if entry.definition:
            qs.append(entry.definition[-6:])
    return qs


def test_search_matches_1_0_algorithm_on_bundled_data(db: PsiModDatabase) -> None:
    for q in _queries(db):
        assert db.search(q) == _old_search(db, q), q


@pytest.mark.parametrize("query", [None, 1, b"phospho", ["phospho"]])
def test_search_non_str_query_still_empty(db: PsiModDatabase, query: object) -> None:
    assert db.search(query) == []  # type: ignore[arg-type]


@given(st.text(max_size=6))
def test_search_matches_1_0_algorithm_property(db: PsiModDatabase, query: str) -> None:
    assert db.search(query) == _old_search(db, query)


def test_search_does_not_match_across_fields(db: PsiModDatabase) -> None:
    entry = next(iter(db))
    small = PsiModDatabase([entry])
    a, b = entry.name.lower(), entry.definition.lower()
    spanning = a[-2:] + b[:2]
    assert small.search(spanning) == _old_search(small, spanning)
    assert small.search(a[-2:] + "\x00" + b[:2]) == []


def test_search_with_nul_in_a_field_and_query(db: PsiModDatabase) -> None:
    entry = dataclasses.replace(next(iter(db)), name="odd\x00name")
    small = PsiModDatabase([entry])
    assert small.search("d\x00n") == [entry] == _old_search(small, "d\x00n")
    assert small.search("odd") == [entry]


def test_search_returns_fresh_list(db: PsiModDatabase) -> None:
    first = db.search("phospho")
    first.clear()
    assert db.search("phospho")


# ---------------------------------------------------------------- load(cache=True)


def test_load_cache_returns_one_shared_database() -> None:
    _load_bundled.cache_clear()
    a = load(cache=True)
    b = load(cache=True)
    assert a is b
    assert len(a) == len(load())


def test_load_default_is_uncached() -> None:
    assert load() is not load()
    assert load() is not load(cache=True)


def test_load_cache_clear_reparses() -> None:
    a = load(cache=True)
    _load_bundled.cache_clear()
    assert load(cache=True) is not a


def test_load_cache_rejects_source_and_refresh(tmp_path) -> None:
    with pytest.raises(ValueError, match="cache=True"):
        load(tmp_path / "x", cache=True)
    with pytest.raises(ValueError, match="cache=True"):
        load(refresh=True, cache=True)


def test_load_cache_is_keyed_by_include_obsolete() -> None:
    full = load(cache=True)
    current = load(cache=True, include_obsolete=False)
    assert full is not current
    assert current is load(cache=True, include_obsolete=False)
    assert len(current) < len(full)
    assert not any(e.is_obsolete for e in current)


# ---------------------------------------------------------------- lazy urllib


def test_import_does_not_import_urllib_request() -> None:
    code = "import sys, psimodpy; assert 'urllib.request' not in sys.modules, 'urllib.request imported'"
    subprocess.run([sys.executable, "-c", code], check=True)


def test_download_module_urllib_attribute_resolves_lazily() -> None:
    import urllib.request

    from psimodpy import _download

    assert _download.urllib is urllib
    assert _download.urllib.request is urllib.request
    with pytest.raises(AttributeError):
        _download.no_such_attribute  # noqa: B018


# ---------------------------------------------------------------- errors


def test_error_base_is_value_error() -> None:
    assert issubclass(PsimodError, ValueError)
    assert issubclass(PsimodError, Exception)
    assert issubclass(PsimodParseError, PsimodError)
    assert issubclass(PsimodParseError, ValueError)


def test_key_error_hierarchy() -> None:
    assert issubclass(PsimodKeyError, PsimodError)
    assert issubclass(PsimodKeyError, KeyError)
    assert issubclass(PsimodKeyError, LookupError)
    assert psimodpy.PsimodKeyError is PsimodKeyError
    assert "PsimodKeyError" in psimodpy.__all__


@pytest.mark.parametrize("key", ["no-such-entry-xyz", 99999999, "", 1.5, None])
def test_getitem_miss_raises_typed_key_error(db: PsiModDatabase, key: object) -> None:
    with pytest.raises(PsimodKeyError) as info:
        db[key]  # type: ignore[index]
    assert info.value.args == (key,)
    assert str(info.value) == str(KeyError(key))


def test_getitem_miss_caught_by_except_key_error(db: PsiModDatabase) -> None:
    try:
        db["no-such-entry-xyz"]
    except KeyError as exc:
        caught: BaseException = exc
    assert isinstance(caught, PsimodKeyError)


def test_getitem_miss_caught_by_except_pkg_error(db: PsiModDatabase) -> None:
    try:
        db["no-such-entry-xyz"]
    except PsimodError as exc:
        caught: BaseException = exc
    assert isinstance(caught, KeyError)


def test_get_and_contains_still_never_raise(db: PsiModDatabase) -> None:
    sentinel = object()
    assert db.get("no-such-entry-xyz", sentinel) is sentinel  # type: ignore[arg-type]
    assert "no-such-entry-xyz" not in db
