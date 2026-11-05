"""Adding ``position`` to a ``search_mass`` query must narrow the result set, never widen it.

Stated as a subset invariant over a sweep of queries, because the failure mode is silent:
a filter that adds hits gives a wrong answer the caller has no reason to doubt.

For PSI-MOD the fix this guards is a behavioural no-op, and these tests are what keeps it
one. ``_slots`` builds ``sites`` from ``origin`` residues only, never from ``"N-term"`` /
``"C-term"``, so the terminus-slot clause in ``slot_matches`` -- the clause that used to
widen -- cannot fire on this data at all. The sweep below is byte-identical before and
after the fix: the same sweep one delta wider (1140 result sets, 531 of them non-empty)
is unchanged in every set, with 0 widening queries both before and after.
The guard matters because ``_mass.py`` is kept byte-identical across psimodpy, unimodpy
and uniprotptmpy, where it does fire: unimodpy measured 175 widening queries of 960.
"""

from __future__ import annotations

import pytest

from psimodpy import PsiModDatabase
from psimodpy._mass import POSITIONS
from psimodpy.database import _slots

_DELTAS = (0.984016, 14.015650, 15.994915, 28.031300, 42.010565, 57.021464, 79.966331, 114.042927, -17.026549)
_SITES = (None, "S", "T", "Y", "K", "C", "M", "Q", "N", "E", "A", "D", "R", "W", "X", "N-term", "C-term", "ST", "STY")


def _ids(hits) -> set[int]:
    return {entry.id for entry, _ in hits}


@pytest.mark.parametrize("position", POSITIONS)
def test_position_only_removes_hits(db: PsiModDatabase, position: str) -> None:
    widened, non_empty = [], 0
    for delta in _DELTAS:
        for site in _SITES:
            without = _ids(db.search_mass(delta, tolerance=0.02, site=site))
            non_empty += bool(without)
            with_position = _ids(db.search_mass(delta, tolerance=0.02, site=site, position=position))
            extra = with_position - without
            if extra:
                widened.append((delta, site, sorted(extra)[:5]))
    assert not widened, f"position={position!r} added hits for {len(widened)} queries: {widened[:5]}"
    # Not a vacuous sweep: the baselines have to find something for the subset claim to say anything.
    assert non_empty >= 90, f"only {non_empty} of {len(_DELTAS) * len(_SITES)} baseline queries found anything"


def test_no_slot_site_is_a_terminus(db: PsiModDatabase) -> None:
    """Why the fix is a no-op here: no PSI-MOD entry sits on a terminus *regardless of residue*.

    ``term_spec`` gives 180 N-term and 99 C-term entries, but that sets the slot's ``where``,
    not its ``sites``; ``sites`` always comes from ``origin``. So the terminus-slot clause in
    ``slot_matches`` is unreachable on this data, and ``site="N-term"`` finds nothing.
    """
    terminus_slotted = [e.id for e in db if any(s in ("N-term", "C-term") for sites, _ in _slots(e) for s in sites)]
    assert terminus_slotted == []
    assert db.search_mass(42.010565, site="N-term") == []


def test_a_terminus_term_spec_narrows_with_position(db: PsiModDatabase) -> None:
    """MOD:00050 is N-acetyl-L-alanine: origin A, ``term_spec`` N-term, +42.010565.

    A residue query finds it with no position and at either N-terminus, and loses it at
    "anywhere" -- an alanine inside the sequence is not the protein's first residue.
    """
    entry = db["MOD:00050"]
    assert (entry.origin, str(entry.term_spec)) == ("A", "N-term")
    assert 50 in _ids(db.search_mass(42.010565, site="A"))
    for position in ("peptide n-term", "protein n-term"):
        assert 50 in _ids(db.search_mass(42.010565, site="A", position=position)), position
    for position in ("anywhere", "peptide c-term", "protein c-term"):
        assert 50 not in _ids(db.search_mass(42.010565, site="A", position=position)), position
