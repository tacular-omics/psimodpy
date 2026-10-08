"""Property tests: `[]`, `get` and `in` agree for every key form, and never crash."""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import psimodpy
from psimodpy import PsiModEntry
from psimodpy.models import AminoAcid, Crosslink

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


# Origin sites that name another entry but are not its canonical accession. Upstream data
# errors in the bundled PSI-MOD OBO, kept so a new one still fails the test.
KNOWN_NONCANONICAL_ORIGINS = {
    # MOD:01465 and MOD:01907: `xref: Origin: "MOD:001464"` (six digits); means MOD:01464.
    (1465, "MOD:001464"),
    (1907, "MOD:001464"),
}


def _expected_name_holder(entries: list[PsiModEntry]) -> PsiModEntry:
    """Documented rule for a reused name: the first non-obsolete entry, else the first."""
    return next((e for e in entries if not e.is_obsolete), entries[0])


def test_every_entry_resolves_by_every_key():
    """Every entry, not a sample, comes back from every lookup the API offers.

    Catches: an id parser that misreads a zero-padded, prefixed, lowercase or padded form
    for some ids; the name index keeping a later duplicate or an obsolete entry instead of
    the documented holder (MOD:00720/01966, MOD:00949/01933 share names); an origin index
    that drops a crosslink's second site; a parser that mangles a MOD-referenced origin.
    """
    by_name: dict[str, list[PsiModEntry]] = {}
    for entry in _DB:
        by_name.setdefault(entry.name.lower(), []).append(entry)

    failures = []
    seen_known = set()
    for entry in _DB:
        n = entry.id
        for key in (
            n,
            str(n),
            f"{n:05d}",
            entry.accession,
            entry.accession.lower(),
            f"MOD:{n}",
            f" {entry.accession} ",
        ):
            if _DB.get_by_id(key) is not entry or _DB.get(key) is not entry or key not in _DB:
                failures.append(f"{entry.accession}: id key {key!r}")
        holder = _expected_name_holder(by_name[entry.name.lower()])
        for name in (entry.name, entry.name.upper(), entry.name.lower()):
            if _DB.get_by_name(name) is not holder or _DB[name] is not holder:
                failures.append(f"{entry.accession}: name {name!r} -> {_DB.get_by_name(name)}")
        if entry not in _DB:
            failures.append(f"{entry.accession}: entry not `in` db")
        sites = (
            (str(entry.origin),)
            if isinstance(entry.origin, AminoAcid)
            else entry.origin.sites
            if isinstance(entry.origin, Crosslink)
            else ()
        )
        for site in sites:
            if entry not in _DB.get_by_origin(site):
                failures.append(f"{entry.accession}: missing from get_by_origin({site!r})")
            if len(site) == 1 and entry not in _DB.get_by_site(site.lower()):
                failures.append(f"{entry.accession}: missing from get_by_site({site.lower()!r})")
            if (n, site) in KNOWN_NONCANONICAL_ORIGINS:
                seen_known.add((n, site))
            elif site.startswith("MOD:"):
                target = _DB.get_by_id(site)
                if target is None or target.accession != site:
                    failures.append(f"{entry.accession}: origin {site!r} is not an entry's accession")
    # A known row upstream has fixed: drop it so the list stays honest.
    failures += [f"known exception gone upstream: {row}" for row in KNOWN_NONCANONICAL_ORIGINS - seen_known]
    assert not failures, f"{len(failures)} lookup failures:\n" + "\n".join(failures[:50])


def test_parent_child_links_are_symmetric():
    """Over every entry: each is_a/relationship target exists, and get_parents/get_children mirror each other.

    Catches: get_parents silently dropping a parent id the parser misread (it filters
    unknown ids), a reverse index that misses entries listed before their parent, and a
    child listed twice or under the wrong parent.
    """
    failures = []
    for entry in _DB:
        for target in (*entry.is_a, *(r.target_id for r in entry.relationships)):
            if _DB.get_by_id(target) is None:
                failures.append(f"{entry.accession}: link to missing MOD:{target:05d}")
        parents = _DB.get_parents(entry)
        if [p.id for p in parents] != list(entry.is_a):
            failures.append(f"{entry.accession}: get_parents {[p.id for p in parents]} != is_a {entry.is_a}")
        for parent in parents:
            if _DB.get_children(parent).count(entry) != entry.is_a.count(parent.id):
                failures.append(f"{entry.accession}: not a child of its parent {parent.accession}")
        for child in _DB.get_children(entry):
            if entry.id not in child.is_a:
                failures.append(f"{entry.accession}: child {child.accession} does not list it in is_a")
    assert not failures, f"{len(failures)} graph failures:\n" + "\n".join(failures[:50])


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
