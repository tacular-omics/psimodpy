"""Tests for PSI-MOD formula parsing and Hill notation conversion."""

import re

from psimodpy._formula import formula_to_hill, formula_to_proforma, parse_formula


class TestParseFormula:
    def test_simple(self):
        result = parse_formula("C 3 H 5 N 1 O 1")
        assert result == {"C": 3, "H": 5, "N": 1, "O": 1}

    def test_single_element(self):
        assert parse_formula("O 1") == {"O": 1}

    def test_with_zeros(self):
        result = parse_formula("C 0 H 0 N 0 O 3 P 1")
        assert result["C"] == 0
        assert result["O"] == 3
        assert result["P"] == 1

    def test_negative_count(self):
        result = parse_formula("C 0 H -2 N 0 O -1")
        assert result["H"] == -2
        assert result["O"] == -1

    def test_isotopic_simple(self):
        result = parse_formula("(12)C 8 (13)C 4 H 20")
        assert result == {"(12)C": 8, "(13)C": 4, "H": 20}

    def test_isotopic_mixed(self):
        result = parse_formula("(12)C 1 (13)C 9 H 17 N 3 O 3")
        assert result["(12)C"] == 1
        assert result["(13)C"] == 9
        assert result["H"] == 17

    def test_isotopic_nitrogen(self):
        result = parse_formula("(14)N 1 (15)N 1 O 2")
        assert result["(14)N"] == 1
        assert result["(15)N"] == 1
        assert result["O"] == 2

    def test_large_formula(self):
        result = parse_formula("C 40 H 66 N 2 O 29")
        assert result["C"] == 40
        assert result["N"] == 2

    def test_empty_string(self):
        assert parse_formula("") == {}


class TestFormulaToHill:
    def test_simple_hill_order(self):
        result = formula_to_hill({"C": 3, "H": 5, "N": 1, "O": 1})
        assert result == "C3H5NO"

    def test_count_one_omitted(self):
        result = formula_to_hill({"C": 1, "H": 2, "O": 1})
        assert result == "CH2O"

    def test_zero_counts_skipped(self):
        result = formula_to_hill({"C": 0, "H": 2, "O": 1})
        assert result == "H2O"

    def test_all_zeros(self):
        result = formula_to_hill({"C": 0, "H": 0, "N": 0})
        assert result == ""

    def test_negative_count(self):
        result = formula_to_hill({"H": -2, "O": -1})
        assert result == "H-2O-1"

    def test_no_carbon_alphabetical(self):
        result = formula_to_hill({"N": 1, "O": 3, "P": 1})
        assert result == "NO3P"

    def test_isotopic_carbon_first(self):
        result = formula_to_hill({"(12)C": 8, "(13)C": 4, "H": 20})
        assert result.startswith("(12)C8(13)C4H20")

    def test_isotopic_heavy_before_light(self):
        # (12)C has isotope number 12, (13)C has 13 — (12)C sorts first
        result = formula_to_hill({"(13)C": 4, "(12)C": 8, "H": 2})
        assert result.index("(12)C") < result.index("(13)C")

    def test_isotope_sorts_with_its_element(self):
        # Hill order is alphabetical by element symbol; an isotope sorts with its element.
        assert formula_to_hill({"H": -1, "N": -1, "(18)O": 1}) == "H-1N-1(18)O"
        assert formula_to_hill({"(15)N": 1, "N": 1, "O": 1, "(18)O": 1}) == "N(15)NO(18)O"

    def test_empty_composition(self):
        assert formula_to_hill({}) == ""

    def test_round_trip(self):
        original = "C 3 H 5 N 1 O 1"
        parsed = parse_formula(original)
        hill = formula_to_hill(parsed)
        # Parse from the PSI-MOD format; Hill output should have same counts
        assert "C3" in hill
        assert "H5" in hill
        assert "N" in hill
        assert "O" in hill


class TestFormulaOnEntries:
    def test_dict_composition_phospho(self):
        """MOD:00046 DiffFormula 'C 0 H 0 N 0 O 3 P 1' → dict includes P:1."""
        import psimodpy

        db = psimodpy.load()
        entry = db.get_by_id(46)
        comp = entry.dict_composition
        assert comp is not None
        assert comp["P"] == 1
        assert comp["O"] == 3

    def test_proforma_formula_phospho(self):
        """MOD:00046 proforma_formula should be 'O3P'."""
        import psimodpy

        db = psimodpy.load()
        entry = db.get_by_id(46)
        pf = entry.proforma_formula
        assert pf is not None
        assert "O3" in pf
        assert "P" in pf

    def test_dict_composition_none_when_missing(self):
        """Root entry (MOD:00000) has no diff_formula → dict_composition is None."""
        import psimodpy

        db = psimodpy.load()
        root = db.get_by_id(0)
        assert root.dict_composition is None

    def test_dict_formula_isotopic(self):
        """Isotopic formula entries return correct dict."""
        import psimodpy

        db = psimodpy.load()
        isotopic = [e for e in db if e.formula and "(12)C" in e.formula]
        assert len(isotopic) > 0
        comp = isotopic[0].dict_formula
        assert comp is not None
        assert "12C" in comp

    def test_dict_formulas_use_tacular_isotope_keys(self, db):
        """Isotopes are keyed "13C" (tacular/peptacular/unimodpy style), not PSI-MOD's "(13)C"."""
        assert db[452].dict_composition == {"13C": 3, "H": 4, "O": 1}
        for entry in db:
            for comp in (entry.dict_composition, entry.dict_formula):
                assert not any(k.startswith("(") for k in comp or {}), entry.id

    def test_hill_and_proforma_accept_both_key_styles(self):
        assert formula_to_proforma({"13C": 4, "12C": 8, "H": 20}) == "[12C8][13C4]H20"
        assert formula_to_proforma({"H": -1, "N": -1, "18O": 1}) == "H-1N-1[18O]"
        assert formula_to_hill({"(13)C": 4, "(12)C": 8, "H": 20}) == "(12)C8(13)C4H20"


# ProForma 2.0 formula: isotopes as "[13C2]" (count, possibly negative, inside the brackets),
# plain elements as "C2" / "H-2".
_PROFORMA_TOKEN_RE = re.compile(r"\[(\d+)([A-Z][a-z]?)(-?\d+)?\]|([A-Z][a-z]?)(-?\d+)?")
_PROFORMA_FORMULA_RE = re.compile(r"^(?:\[\d+[A-Z][a-z]?(?:-?[1-9]\d*)?\]|[A-Z][a-z]?(?:-?[1-9]\d*)?)*$")


def _parse_proforma(formula: str) -> dict[str, int]:
    """Parse a ProForma formula back into element keys ('13C', 'H')."""
    assert _PROFORMA_FORMULA_RE.fullmatch(formula), formula
    result: dict[str, int] = {}
    for iso, iso_el, iso_n, el, n in _PROFORMA_TOKEN_RE.findall(formula):
        key = f"{iso}{iso_el}" if iso else el
        count = iso_n if iso else n
        result[key] = result.get(key, 0) + (int(count) if count else 1)
    return result


class TestFormulaToProforma:
    def test_plain_matches_hill(self):
        assert formula_to_proforma({"C": 3, "H": 5, "N": 1, "O": 1}) == "C3H5NO"
        assert formula_to_proforma({"C": 0, "H": -2, "O": -1}) == "H-2O-1"

    def test_isotopes_use_brackets(self):
        assert formula_to_proforma({"(12)C": 8, "(13)C": 4, "H": 20}) == "[12C8][13C4]H20"

    def test_isotope_count_one_and_negative(self):
        assert formula_to_proforma({"(13)C": 1, "(12)C": -1}) == "[12C-1][13C]"

    def test_mod_00402_deuterium(self, db):
        formula = db[402].proforma_formula
        assert formula is not None
        assert "(" not in formula
        assert "[2H8]" in formula

    def test_every_entry_parses_and_round_trips(self, db):
        checked = 0
        for entry in db:
            for composition in (entry.dict_composition, entry.dict_formula):
                if composition is None:
                    continue
                formula = formula_to_proforma(composition)
                assert _parse_proforma(formula) == {k: v for k, v in composition.items() if v != 0}, entry.id
                checked += 1
            if entry.proforma_formula is not None:
                assert _PROFORMA_FORMULA_RE.fullmatch(entry.proforma_formula), entry.id
        assert checked > 1000
