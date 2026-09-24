"""PSI-MOD formula string parsing and Hill-notation conversion.

PSI-MOD formula format: element-count pairs separated by spaces, with isotopes
in parentheses before the element symbol. Elements are in strict alphabetical
order (not CAS/Hill order). Counts can be zero or negative in difference formulas.

Examples:
    "C 3 H 5 N 1 O 1"
    "C 0 H 0 N 0 O 3 P 1"
    "(12)C 8 (13)C 4 H 20 (14)N 1 (15)N 1 O 2"
    "C 0 H -2 N 0 O -1"
"""

from __future__ import annotations

import re

# Matches either "(12)C" or "C" followed by whitespace and an integer count (may be negative).
_TOKEN_RE = re.compile(r"(\(\d+\)[A-Za-z]+|[A-Za-z]+)\s+(-?\d+)")
# An isotope key in either style: PSI-MOD "(13)C" or tacular/ProForma "13C".
_ISOTOPE_RE = re.compile(r"^(?:\((\d+)\)|(\d+))([A-Za-z]+)$")


def _split_isotope(element: str) -> tuple[int, str]:
    """Return (isotope number or 0, element symbol) for "C", "(13)C" or "13C"."""
    m = _ISOTOPE_RE.match(element)
    if m is None:
        return 0, element
    return int(m.group(1) or m.group(2)), m.group(3)


def to_isotope_keys(composition: dict[str, int]) -> dict[str, int]:
    """Rename PSI-MOD isotope keys to the tacular/peptacular style: "(13)C" -> "13C".

    Examples:
        >>> to_isotope_keys({"(13)C": 3, "H": 4, "O": 1})
        {'13C': 3, 'H': 4, 'O': 1}
    """
    result: dict[str, int] = {}
    for element, count in composition.items():
        iso, symbol = _split_isotope(element)
        key = f"{iso}{symbol}" if iso else element
        result[key] = result.get(key, 0) + count
    return result


def parse_formula(formula: str) -> dict[str, int]:
    """Parse a PSI-MOD formula string into {element_token: count}.

    Zero counts are included. Negative counts are preserved.

    Examples:
        >>> parse_formula("C 3 H 5 N 1 O 1")
        {'C': 3, 'H': 5, 'N': 1, 'O': 1}
        >>> parse_formula("(12)C 8 (13)C 4 H 20")
        {'(12)C': 8, '(13)C': 4, 'H': 20}
    """
    result: dict[str, int] = {}
    for element, count in _TOKEN_RE.findall(formula):
        result[element] = int(count)
    return result


def _hill_order(composition: dict[str, int]) -> list[tuple[str, int]]:
    """Return non-zero (element, count) pairs in Hill order (C, H, then alphabetical)."""
    # Separate into carbon group, hydrogen group, and other
    carbon_group: list[tuple[str, int]] = []
    hydrogen_group: list[tuple[str, int]] = []
    other: list[tuple[str, int]] = []

    for element, count in composition.items():
        if count == 0:
            continue
        # Isotopic carbons: "(13)C" or "13C"; non-isotopic carbon: "C"
        base = _split_isotope(element)[1]
        if base == "C":
            carbon_group.append((element, count))
        elif base == "H":
            hydrogen_group.append((element, count))
        else:
            other.append((element, count))

    # Sort each group: isotopic variants before non-isotopic, then by isotope number
    def _sort_key(ec: tuple[str, int]) -> tuple[int, str]:
        return (_split_isotope(ec[0])[0], ec[0])

    carbon_group.sort(key=_sort_key)
    hydrogen_group.sort(key=_sort_key)
    # Alphabetical by element symbol, so an isotope sorts with its element: N, (15)N, O, (18)O
    other.sort(key=lambda ec: _split_isotope(ec[0])[::-1])

    return carbon_group + hydrogen_group + other


def formula_to_hill(composition: dict[str, int]) -> str:
    """Convert an element-count dict to Hill-notation string.

    Ordering: C (and isotopic carbons) first, H (and isotopic hydrogens) second,
    then all remaining elements alphabetically. Zero counts are skipped.
    A count of 1 is omitted. Negative counts are written as e.g. "O-1".
    Isotopes keep the PSI-MOD "(13)C" prefix; use formula_to_proforma for ProForma.

    Examples:
        >>> formula_to_hill({"C": 3, "H": 5, "N": 1, "O": 1})
        'C3H5NO'
        >>> formula_to_hill({"C": 0, "H": -2, "O": -1})
        'H-2O-1'
        >>> formula_to_hill({"(12)C": 8, "(13)C": 4, "H": 20})
        '(12)C8(13)C4H20'
    """
    return "".join(element if count == 1 else f"{element}{count}" for element, count in _hill_order(composition))


def formula_to_proforma(composition: dict[str, int]) -> str:
    """Convert an element-count dict to a ProForma 2.0 formula string.

    Same ordering and count rules as formula_to_hill, but isotopes use ProForma
    bracket syntax with the count inside the brackets: "(2)H" or "2H" x8 becomes "[2H8]".

    Examples:
        >>> formula_to_proforma({"C": 3, "H": 5, "N": 1, "O": 1})
        'C3H5NO'
        >>> formula_to_proforma({"(12)C": 8, "(13)C": 4, "H": 20})
        '[12C8][13C4]H20'
        >>> formula_to_proforma({"(13)C": 1, "(12)C": -1})
        '[12C-1][13C]'
    """
    parts: list[str] = []
    for element, count in _hill_order(composition):
        suffix = "" if count == 1 else str(count)
        iso, symbol = _split_isotope(element)
        parts.append(f"[{iso}{symbol}{suffix}]" if iso else f"{element}{suffix}")
    return "".join(parts)
