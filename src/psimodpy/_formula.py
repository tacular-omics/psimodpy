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


def formula_to_hill(composition: dict[str, int]) -> str:
    """Convert an element-count dict to Hill-notation string.

    Ordering: C (and isotopic carbons) first, H (and isotopic hydrogens) second,
    then all remaining elements alphabetically. Zero counts are skipped.
    A count of 1 is omitted. Negative counts are written as e.g. "O-1".

    Examples:
        >>> formula_to_hill({"C": 3, "H": 5, "N": 1, "O": 1})
        'C3H5NO'
        >>> formula_to_hill({"C": 0, "H": -2, "O": -1})
        'H-2O-1'
        >>> formula_to_hill({"(12)C": 8, "(13)C": 4, "H": 20})
        '(12)C8(13)C4H20'
    """
    # Separate into carbon group, hydrogen group, and other
    carbon_group: list[tuple[str, int]] = []
    hydrogen_group: list[tuple[str, int]] = []
    other: list[tuple[str, int]] = []

    for element, count in composition.items():
        if count == 0:
            continue
        # Isotopic carbons: "(12)C", "(13)C", "(14)C" — contain "C" after closing paren
        # Non-isotopic carbon: "C"
        base = re.sub(r"^\(\d+\)", "", element)  # strip isotope prefix
        if base == "C":
            carbon_group.append((element, count))
        elif base == "H":
            hydrogen_group.append((element, count))
        else:
            other.append((element, count))

    # Sort each group: isotopic variants before non-isotopic, then by isotope number
    def _sort_key(ec: tuple[str, int]) -> tuple[int, str]:
        element = ec[0]
        m = re.match(r"^\((\d+)\)", element)
        isotope_num = int(m.group(1)) if m else 0
        return (isotope_num, element)

    carbon_group.sort(key=_sort_key)
    hydrogen_group.sort(key=_sort_key)
    other.sort(key=lambda ec: ec[0])

    ordered = carbon_group + hydrogen_group + other

    parts: list[str] = []
    for element, count in ordered:
        if count == 1:
            parts.append(element)
        else:
            parts.append(f"{element}{count}")

    return "".join(parts)
