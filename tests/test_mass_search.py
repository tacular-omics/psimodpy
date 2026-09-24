"""search_mass() and get_by_site() (1.1)."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from psimodpy import PsiModDatabase, PsimodError
from psimodpy._mass import POSITIONS, parse_position, parse_site, slot_matches
from psimodpy.database import _slots


def _mass(entry) -> float | None:
    return entry.diff_mono


def _brute(db: PsiModDatabase, delta, tolerance=0.01, unit="da", site=None, position=None):
    """Linear scan reference: every entry, exact window test, sorted by (|error|, mass, order)."""
    tol = tolerance if unit == "da" else abs(delta) * tolerance * 1e-6
    sq = parse_site(site, PsimodError) if site is not None else None
    pq = parse_position(position, PsimodError) if position is not None else None
    hits = []
    for i, e in enumerate(db):
        m = _mass(e)
        if m is None or not math.isfinite(m) or abs(delta - m) > tol:
            continue
        if slot_matches(_slots(e), sq, pq):
            hits.append((abs(delta - m), m, i, e, delta - m))
    hits.sort(key=lambda h: h[:3])
    return [(h[3], h[4]) for h in hits]


def _names(hits) -> list[str]:
    return [e.name for e, _ in hits]


# ---------------------------------------------------------------- hand-checked


def test_phospho_on_sty(db: PsiModDatabase) -> None:
    hits = db.search_mass(79.966, site="STY")
    assert _names(hits)[: len(["O-phospho-L-serine", "O-phospho-L-threonine", "O4'-phospho-L-tyrosine"])] == [
        "O-phospho-L-serine",
        "O-phospho-L-threonine",
        "O4'-phospho-L-tyrosine",
    ]
    entry, error = hits[0]
    assert error == pytest.approx(79.966 - 79.966331, abs=1e-5)
    assert all(abs(err) <= 0.01 for _, err in hits)
    assert [abs(err) for _, err in hits] == sorted(abs(err) for _, err in hits)


def test_oxidation_on_m(db: PsiModDatabase) -> None:
    hits = db.search_mass(15.995, site="m")
    assert "L-methionine sulfoxide" in _names(hits)
    assert all(abs(err) <= 0.01 for _, err in hits)


def test_ppm_vs_da(db: PsiModDatabase) -> None:
    # Sulfo (79.956815) is 9.5 mDa (119 ppm) from phospho: inside 0.01 Da, outside 5 ppm.
    da = _names(db.search_mass(79.966331, tolerance=0.01, site="S"))
    ppm = _names(db.search_mass(79.966331, tolerance=5, unit="PPM", site="S"))
    assert "O-sulfo-L-serine" in da
    assert "O-sulfo-L-serine" not in ppm
    assert set(ppm) < set(da)
    assert ppm[0] == ["O-phospho-L-serine", "O-phospho-L-threonine", "O4'-phospho-L-tyrosine"][0]


def test_n_terminal_acetyl_position(db: PsiModDatabase) -> None:
    assert "N-acetyl-L-alanine" in _names(db.search_mass(42.010565, site="A", position="protein n-term"))
    assert "N-acetyl-L-alanine" in _names(db.search_mass(42.010565, site="A", position="Protein N-term"))
    assert "N-acetyl-L-alanine" not in _names(db.search_mass(42.010565, site="A", position="anywhere"))


def test_psimod_n_term_matches_both_n_terminal_positions(db: PsiModDatabase) -> None:
    assert "N-acetyl-L-alanine" in _names(db.search_mass(42.010565, site="A", position="peptide n-term"))
    assert "N-acetyl-L-alanine" not in _names(db.search_mass(42.010565, site="A", position="peptide c-term"))


def test_psimod_get_by_site_is_get_by_origin(db: PsiModDatabase) -> None:
    for aa in "ACDEFGHIKLMNPQRSTVWYXUO":
        assert db.get_by_site(aa) == list(dict.fromkeys(db.get_by_origin(aa))) == db.get_by_site(aa.lower())


def test_negative_delta(db: PsiModDatabase) -> None:
    hits = db.search_mass(-17.026549, tolerance=0.001)
    assert hits
    assert all(_mass(e) < 0 for e, _ in hits)
    assert "2-pyrrolidone-5-carboxylic acid (Gln)" in _names(hits)


def test_zero_tolerance_is_exact(db: PsiModDatabase) -> None:
    target = next(e for e in db if _mass(e) is not None and _mass(e) > 1)
    hits = db.search_mass(_mass(target), tolerance=0)
    assert target in [e for e, _ in hits]
    assert all(err == 0 for _, err in hits)
    assert db.search_mass(_mass(target) + 1e-6, tolerance=0) == []


def test_no_filters_returns_every_entry_in_window(db: PsiModDatabase) -> None:
    assert db.search_mass(1e7) == []
    everything = db.search_mass(0, tolerance=1e7)
    assert len(everything) == sum(_mass(e) is not None for e in db)


def test_entries_without_mass_are_skipped(db: PsiModDatabase) -> None:
    assert any(_mass(e) is None for e in db)
    assert all(_mass(e) is not None for e, _ in db.search_mass(0, tolerance=1e7))


def test_site_n_term_query_is_valid(db: PsiModDatabase) -> None:
    hits = db.search_mass(42.010565, site="N-term")
    assert _names(hits) == _names(_brute(db, 42.010565, site="N-term"))


def test_result_is_fresh_list(db: PsiModDatabase) -> None:
    db.search_mass(79.966).clear()
    assert db.search_mass(79.966)


# ---------------------------------------------------------------- errors


@pytest.mark.parametrize("site", ["B", "J", "Z", "1", "", "  ", "S-T", "N_term", 5])
def test_unknown_site_raises(db: PsiModDatabase, site: object) -> None:
    with pytest.raises(PsimodError, match="site"):
        db.search_mass(79.966, site=site)  # type: ignore[arg-type]


@pytest.mark.parametrize("position", ["middle", "n-term", "", 3])
def test_unknown_position_raises(db: PsiModDatabase, position: object) -> None:
    with pytest.raises(PsimodError, match="position"):
        db.search_mass(79.966, position=position)  # type: ignore[arg-type]


@pytest.mark.parametrize("unit", ["mda", "", None, "ppm "[:2]])
def test_unknown_unit_raises(db: PsiModDatabase, unit: object) -> None:
    with pytest.raises(PsimodError, match="unit"):
        db.search_mass(79.966, unit=unit)  # type: ignore[arg-type]


@pytest.mark.parametrize("delta", [math.nan, math.inf, -math.inf, "79.9", None, True])
def test_bad_delta_raises(db: PsiModDatabase, delta: object) -> None:
    with pytest.raises(PsimodError, match="delta"):
        db.search_mass(delta)  # type: ignore[arg-type]


@pytest.mark.parametrize("tolerance", [-0.01, math.nan, math.inf, "0.01", None, False])
def test_bad_tolerance_raises(db: PsiModDatabase, tolerance: object) -> None:
    with pytest.raises(PsimodError, match="tolerance"):
        db.search_mass(79.966, tolerance=tolerance)  # type: ignore[arg-type]


def test_errors_are_value_errors(db: PsiModDatabase) -> None:
    with pytest.raises(ValueError):
        db.search_mass(79.966, site="B")


# ---------------------------------------------------------------- property: index == brute force

_sites = st.one_of(st.none(), st.sampled_from(["S", "STY", "K", "M", "C", "N", "Q", "X", "N-term", "C-term", "ndq"]))
_positions = st.one_of(st.none(), st.sampled_from([*POSITIONS, "Any N-term", "any c-term"]))


@given(
    delta=st.floats(min_value=-200, max_value=1500, allow_nan=False),
    tolerance=st.floats(min_value=0, max_value=5, allow_nan=False),
    site=_sites,
    position=_positions,
)
def test_matches_brute_force_da(db: PsiModDatabase, delta, tolerance, site, position) -> None:
    assert db.search_mass(delta, tolerance=tolerance, site=site, position=position) == _brute(
        db, delta, tolerance, "da", site, position
    )


@given(
    entry_index=st.integers(min_value=0, max_value=10_000),
    offset=st.floats(min_value=-0.05, max_value=0.05, allow_nan=False),
    tolerance=st.floats(min_value=0, max_value=200, allow_nan=False),
    site=_sites,
    position=_positions,
)
def test_matches_brute_force_ppm_near_real_masses(
    db: PsiModDatabase, entry_index, offset, tolerance, site, position
) -> None:
    masses = [_mass(e) for e in db if _mass(e) is not None]
    delta = masses[entry_index % len(masses)] + offset
    got = db.search_mass(delta, tolerance=tolerance, unit="ppm", site=site, position=position)
    assert got == _brute(db, delta, tolerance, "ppm", site, position)


# ---------------------------------------------------------------- get_by_site


def test_get_by_site(db: PsiModDatabase) -> None:
    s = db.get_by_site("S")
    assert s
    assert s == db.get_by_site(" s ")
    order = {id(e): i for i, e in enumerate(db)}
    assert [order[id(e)] for e in s] == sorted(order[id(e)] for e in s)
    assert ["O-phospho-L-serine", "O-phospho-L-threonine", "O4'-phospho-L-tyrosine"][0] in [e.name for e in s]
    assert len(set(map(id, s))) == len(s)


@pytest.mark.parametrize("site", ["J", "", "zz", None, 5])
def test_get_by_site_unknown_is_empty(db: PsiModDatabase, site: object) -> None:
    assert db.get_by_site(site) == []  # type: ignore[arg-type]


def test_get_by_site_returns_fresh_list(db: PsiModDatabase) -> None:
    db.get_by_site("S").clear()
    assert db.get_by_site("S")
