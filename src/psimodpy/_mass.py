"""Delta-mass search shared by ``search_mass``: a sorted mass index searched with bisect.

The same module ships in psimodpy, unimodpy and uniprotptmpy; only the database decides
how an entry maps to a mass and to *slots* (where the modification may sit).

A slot is ``(sites, where)``: ``sites`` is a set of one-letter residue codes, or the
terminus names ``"N-term"`` / ``"C-term"`` for a modification of the terminus itself
(any residue); ``where`` is one of the ``WHERE_*`` constants below.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Iterable

RESIDUES = frozenset("ACDEFGHIKLMNOPQRSTUVWXY")
"""Residue letters ``site`` accepts: the 20 standard, U (Sec), O (Pyl) and X (any)."""

N_TERM = "N-term"
C_TERM = "C-term"

# Where the data allows a modification.
WHERE_ANYWHERE = "anywhere"
WHERE_ANY_N = "any-n"  # any N-terminus, protein or peptide
WHERE_ANY_C = "any-c"
WHERE_PROTEIN_N = "protein-n"  # protein N-terminus only
WHERE_PROTEIN_C = "protein-c"

# ``position`` (where the modified residue was observed) -> the slot positions allowed there.
_ALLOWED: dict[str, frozenset[str]] = {
    "anywhere": frozenset({WHERE_ANYWHERE}),
    "peptide n-term": frozenset({WHERE_ANYWHERE, WHERE_ANY_N}),
    "peptide c-term": frozenset({WHERE_ANYWHERE, WHERE_ANY_C}),
    "protein n-term": frozenset({WHERE_ANYWHERE, WHERE_ANY_N, WHERE_PROTEIN_N}),
    "protein c-term": frozenset({WHERE_ANYWHERE, WHERE_ANY_C, WHERE_PROTEIN_C}),
}
_POSITION_ALIASES = {"any n-term": "peptide n-term", "any c-term": "peptide c-term"}
_TERMINUS_AT = {
    "peptide n-term": N_TERM,
    "protein n-term": N_TERM,
    "peptide c-term": C_TERM,
    "protein c-term": C_TERM,
}
POSITIONS = tuple(_ALLOWED)
"""Values ``position`` accepts (case-insensitive; ``"Any N-term"``/``"Any C-term"`` also work)."""

type Slot = tuple[frozenset[str], str]
type SiteQuery = tuple[bool, frozenset[str]]  # (is a terminus query, sites)


def parse_site(site: object, error: type[Exception]) -> SiteQuery:
    """Parse ``site``: residue letters (``"S"``, ``"sty"``) or ``"N-term"`` / ``"C-term"``."""
    if not isinstance(site, str):
        raise error(f"site must be a str, got {type(site).__name__}")
    text = site.strip()
    lowered = text.lower()
    if lowered in ("n-term", "c-term"):
        return True, frozenset({N_TERM if lowered == "n-term" else C_TERM})
    letters = frozenset(text.upper())
    unknown = sorted(letters - RESIDUES)
    if not text or unknown:
        raise error(f"unknown site {site!r}: use residue letters ({''.join(sorted(RESIDUES))}), 'N-term' or 'C-term'")
    return False, letters


def parse_position(position: object, error: type[Exception]) -> str:
    """Normalise ``position`` to a key of ``_ALLOWED``."""
    key = position.strip().lower() if isinstance(position, str) else None
    key = _POSITION_ALIASES.get(key, key) if key is not None else None
    if key not in _ALLOWED:
        raise error(f"unknown position {position!r}: use one of {', '.join(repr(p) for p in POSITIONS)}")
    return key


def slot_matches(slots: tuple[Slot, ...], site: SiteQuery | None, position: str | None) -> bool:
    """True if one slot allows the modification at ``site`` observed at ``position``.

    A terminus slot (``"N-term"``) matches a residue query only when ``position`` puts
    the residue at that terminus: any residue can be there.
    """
    if site is None and position is None:
        return True
    allowed = _ALLOWED[position] if position is not None else None
    terminus = _TERMINUS_AT.get(position) if position is not None else None
    for sites, where in slots:
        if allowed is not None and where not in allowed:
            continue
        if site is None:
            return True
        is_terminus, wanted = site
        if sites & wanted or (not is_terminus and terminus is not None and terminus in sites):
            return True
    return False


class MassIndex[E]:
    """Entries sorted by monoisotopic delta mass; built once, searched with bisect."""

    def __init__(self, rows: Iterable[tuple[E, float | None, tuple[Slot, ...]]]) -> None:
        # Sort by (mass, original order): equal masses keep database order.
        kept = sorted(
            (
                (mass, i, entry, slots)
                for i, (entry, mass, slots) in enumerate(rows)
                if mass is not None and math.isfinite(mass)
            ),
            key=lambda row: (row[0], row[1]),
        )
        self.masses: list[float] = [row[0] for row in kept]
        self.entries: list[E] = [row[2] for row in kept]
        self.slots: list[tuple[Slot, ...]] = [row[3] for row in kept]

    def search(
        self,
        delta: float,
        *,
        tolerance: float,
        unit: str,
        site: str | None,
        position: str | None,
        error: type[Exception],
    ) -> list[tuple[E, float]]:
        """Return ``(entry, delta - mass)`` pairs within tolerance, closest first."""
        if isinstance(delta, bool) or not isinstance(delta, int | float) or not math.isfinite(delta):
            raise error(f"delta must be a finite number, got {delta!r}")
        if isinstance(tolerance, bool) or not isinstance(tolerance, int | float) or not tolerance >= 0:
            raise error(f"tolerance must be a number >= 0, got {tolerance!r}")
        if not math.isfinite(tolerance):
            raise error(f"tolerance must be finite, got {tolerance!r}")
        # Only Da: a ppm window on a delta mass is ill-defined (ppm of the delta, or of the
        # peptide?). Adding a unit later is additive; loosening then tightening is not.
        if not isinstance(unit, str) or unit != "da":
            raise error(f"unknown unit {unit!r}: only 'da' is supported")
        tol = float(tolerance)
        site_query = parse_site(site, error) if site is not None else None
        position_key = parse_position(position, error) if position is not None else None

        # Widen the window by a hair so a mass exactly on the edge (79.976331 - 79.966331 is
        # 0.010000000000005 in floats) is inside: the edges are inclusive.
        slack = 1e-9 * max(1.0, abs(delta))
        lo = bisect.bisect_left(self.masses, delta - tol - slack)
        hi = bisect.bisect_right(self.masses, delta + tol + slack)
        hits = [
            (self.entries[i], delta - self.masses[i])
            for i in range(lo, hi)
            if abs(delta - self.masses[i]) <= tol + slack and slot_matches(self.slots[i], site_query, position_key)
        ]
        hits.sort(key=lambda hit: abs(hit[1]))  # stable: ties stay in mass, then database, order
        return hits
