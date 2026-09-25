"""Property tests: `[]`, `get` and `in` agree for every key form, and never crash."""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import psimodpy

_DB = psimodpy.load()
_IDS = sorted(e.id for e in _DB)
_NAMES = [e.name for e in _DB]
# Example count comes from the Hypothesis profile (tests/conftest.py): 50 by default, 300 thorough.
_SETTINGS = settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])


def _id_forms(n: int) -> st.SearchStrategy[object]:
    return st.sampled_from([n, str(n), f"{n:05d}", f"MOD:{n:05d}", f"mod:{n:05d}", f"MOD:{n}", f" MOD:{n:05d} "])


_existing = st.sampled_from(_IDS).flatmap(_id_forms)
_names = st.sampled_from(_NAMES).flatmap(lambda s: st.sampled_from([s, s.upper(), s.lower()]))
_junk = st.one_of(
    st.integers(min_value=-(10**6), max_value=10**6).flatmap(_id_forms),
    st.text(max_size=20),
    st.text(max_size=8).map(lambda s: f"MOD:{s}"),
    st.none(),
    st.floats(allow_nan=False),
    st.tuples(st.integers()),
)
_keys = st.one_of(_existing, _names, _junk)


def _getitem(key: object):
    try:
        return _DB[key]  # ty: ignore[invalid-argument-type]
    except KeyError:
        return None


@_SETTINGS
@given(_keys)
def test_contains_getitem_and_get_agree(key):
    entry = _DB.get(key)  # never raises
    assert _getitem(key) is entry
    assert (key in _DB) is (entry is not None)


@_SETTINGS
@given(_existing)
def test_every_id_form_resolves(key):
    assert _DB.get(key) is not None


@_SETTINGS
@given(st.sampled_from(_IDS))
def test_entry_ids_round_trip(n):
    entry = _DB[n]
    assert _DB[f"MOD:{n:05d}"] is entry
    assert entry in _DB


@_SETTINGS
@given(st.text(max_size=30))
def test_search_never_crashes(query):
    results = _DB.search(query)
    assert isinstance(results, list)
    assert all(r in _DB for r in results)


def test_len_matches_iteration():
    assert len(_DB) == len(list(_DB)) == len(set(_IDS))


@pytest.mark.parametrize("key", [True, False])
def test_bool_keys_behave_like_ints(key):
    # bool is an int subclass; keep it consistent rather than special-cased.
    assert _getitem(key) is _DB.get(key)
