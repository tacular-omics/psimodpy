"""Recompute every entry's masses from its parsed formula and compare with PSI-MOD.

The element and isotope masses come from an independent table frozen from pyteomics
(NIST); see tests/reference/generate_element_masses.py. A mismatch means either the
formula parser lost or misread a token, or the upstream OBO disagrees with itself.
The second kind are listed in the KNOWN_* tables below with the reason.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import psimodpy
from psimodpy import PsiModEntry

_TABLE = json.loads((Path(__file__).parent / "reference" / "element_masses.json").read_text())
_ELEMENTS: dict[str, dict[str, float]] = _TABLE["elements"]
_ELECTRON: float = _TABLE["electron_mass"]
_KEY_RE = re.compile(r"^(\d+)?([A-Z][a-z]?)$")

# Upstream values are rounded to 5-6 decimals, and PSI-MOD's atomic mass table is not
# the same AME release as NIST's (up to ~3e-5 Da apart for heavy elements).
MONO_TOL = 5e-5
# Average masses depend on the atomic-weight table (PSI-MOD's predates current IUPAC
# values; Fe/S/Mo clusters differ by up to ~0.03 Da); allow 0.05 Da or 1e-4 relative.
AVG_ABS_TOL = 0.05
AVG_REL_TOL = 1e-4

# (MOD id, which formula) -> reason the stated mass cannot be reproduced from it.
KNOWN_MONO_MISMATCHES: dict[tuple[int, str], str] = {
    (523, "full"): "Formula is C35H57N3O26 (935.32) but MassMono is 960.35: upstream data error",
    (577, "full"): "Formula is for one crosslinked residue, MassMono for the penta-lysine: upstream data error",
    (2105, "diff"): "DiffFormula adds O1 but DiffMono is 2 x O (31.99): upstream data error",
    (1982, "diff"): "FormalCharge 1+ but the electron is added, not removed: upstream sign error",
    (1982, "full"): "FormalCharge 1+ but the electron is added, not removed: upstream sign error",
}

# Unlabelled entries whose average mass is not the formula's average mass.
KNOWN_AVG_MISMATCHES: dict[tuple[int, str], str] = {
    **{
        key: "average mass equals the monoisotopic mass: upstream data error"
        for key in [(472, "full"), (2100, "full"), (2101, "full"), (2102, "full")]
    },
    **{
        key: "average mass ~0.06 Da high (older atomic weights?): upstream"
        for key in [(2019, "full"), (2022, "diff"), (2022, "full"), (2023, "diff"), (2024, "diff")]
    },
}


def _mass(composition: dict[str, int], kind: str) -> float:
    total = 0.0
    for token, count in composition.items():
        m = _KEY_RE.match(token)
        assert m is not None, f"formula token {token!r} is not an element or isotope"
        total += _ELEMENTS[f"{m.group(1) or ''}{m.group(2)}"][kind] * count
    return total


def _is_labelled(composition: dict[str, int]) -> bool:
    return any(token[0].isdigit() and count for token, count in composition.items())


def _cases(db: psimodpy.PsiModDatabase):
    for entry in db:
        yield entry, "diff", entry.dict_diff_formula, entry.diff_mono, entry.diff_avg
        yield entry, "full", entry.dict_formula, entry.mass_mono, entry.mass_avg


@pytest.fixture(scope="module")
def cases(db):
    return [c for c in _cases(db) if c[2] is not None]


def _expected_mono(entry: PsiModEntry, composition: dict[str, int]) -> float:
    # PSI-MOD includes the electrons for charged entries (e.g. Fe-S clusters, FormalCharge "2-").
    return _mass(composition, "mono") - (entry.formal_charge or 0) * _ELECTRON


def test_every_formula_token_is_a_known_element(cases):
    for entry, _kind, composition, _mono, _avg in cases:
        _mass(composition, "mono")  # raises on an unknown token
        assert entry.id >= 0


def test_monoisotopic_masses_match_formula(cases):
    mismatches = []
    for entry, kind, composition, mono, _avg in cases:
        if mono is None or (entry.id, kind) in KNOWN_MONO_MISMATCHES:
            continue
        calc = _expected_mono(entry, composition)
        if abs(calc - mono) > MONO_TOL:
            mismatches.append((entry.id, kind, mono, round(calc, 6)))
    assert mismatches == []


def test_known_mono_mismatches_still_mismatch(db):
    """If upstream fixes one of these, drop it from KNOWN_MONO_MISMATCHES."""
    for (mod_id, kind), reason in KNOWN_MONO_MISMATCHES.items():
        entry = db[mod_id]
        composition = entry.dict_diff_formula if kind == "diff" else entry.dict_formula
        mono = entry.diff_mono if kind == "diff" else entry.mass_mono
        assert composition is not None and mono is not None
        assert abs(_expected_mono(entry, composition) - mono) > MONO_TOL, reason


def test_average_masses_match_formula(cases):
    """Unlabelled entries: the average mass is the formula's average mass."""
    mismatches = []
    checked = 0
    for entry, kind, composition, _mono, avg in cases:
        key = (entry.id, kind)
        if avg is None or _is_labelled(composition) or key in KNOWN_MONO_MISMATCHES or key in KNOWN_AVG_MISMATCHES:
            continue
        checked += 1
        calc = _mass(composition, "avg")
        if abs(calc - avg) > max(AVG_ABS_TOL, AVG_REL_TOL * abs(avg)):
            mismatches.append((entry.id, kind, avg, round(calc, 4)))
    assert checked > 2400
    assert mismatches == []


def test_labelled_average_masses(cases):
    """Isotope-labelled entries (e.g. MOD:00402, ICAT d8): PSI-MOD states either the
    monoisotopic mass rounded to 2 decimals or the formula's average mass."""
    mismatches = []
    checked = 0
    for entry, kind, composition, mono, avg in cases:
        if avg is None or mono is None or not _is_labelled(composition):
            continue
        checked += 1
        calc = _mass(composition, "avg")
        if abs(avg - mono) > 0.01 and abs(calc - avg) > max(AVG_ABS_TOL, AVG_REL_TOL * abs(avg)):
            mismatches.append((entry.id, kind, avg, mono, round(calc, 4)))
    assert checked > 400
    assert mismatches == []


def test_known_avg_mismatches_still_mismatch(db):
    """If upstream fixes one of these, drop it from KNOWN_AVG_MISMATCHES."""
    for (mod_id, kind), reason in KNOWN_AVG_MISMATCHES.items():
        entry = db[mod_id]
        composition = entry.dict_diff_formula if kind == "diff" else entry.dict_formula
        avg = entry.diff_avg if kind == "diff" else entry.mass_avg
        assert composition is not None and avg is not None
        assert abs(_mass(composition, "avg") - avg) > AVG_ABS_TOL, reason


@pytest.mark.parametrize(
    ("mod_id", "mono"),
    [
        (7, 47.944450),  # selenium substitution for sulfur, S-1 Se1
        (46, 79.966331),  # O-phospho-L-serine, HPO3
        (402, 494.301420),  # ICAT d8: (1)H30 (2)H8 isotopes
        (1603, 1.994070),  # (14)N-2 (15)N2
    ],
)
def test_spot_values(db, mod_id, mono):
    entry = db[mod_id]
    assert entry.dict_diff_formula is not None
    assert _expected_mono(entry, entry.dict_diff_formula) == pytest.approx(mono, abs=MONO_TOL)
