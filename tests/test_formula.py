"""Tests for PSI-MOD formula parsing and Hill notation conversion."""

from psimodpy._formula import formula_to_hill, parse_formula


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
    def test_dict_diff_formula_phospho(self):
        """MOD:00046 DiffFormula 'C 0 H 0 N 0 O 3 P 1' → dict includes P:1."""
        import psimodpy

        db = psimodpy.load()
        entry = db.get_by_id(46)
        comp = entry.dict_diff_formula
        assert comp is not None
        assert comp["P"] == 1
        assert comp["O"] == 3

    def test_proforma_diff_formula_phospho(self):
        """MOD:00046 proforma_diff_formula should be 'O3P'."""
        import psimodpy

        db = psimodpy.load()
        entry = db.get_by_id(46)
        pf = entry.proforma_diff_formula
        assert pf is not None
        assert "O3" in pf
        assert "P" in pf

    def test_dict_diff_formula_none_when_missing(self):
        """Root entry (MOD:00000) has no diff_formula → dict_diff_formula is None."""
        import psimodpy

        db = psimodpy.load()
        root = db.get_by_id(0)
        assert root.dict_diff_formula is None

    def test_dict_formula_isotopic(self):
        """Isotopic formula entries return correct dict."""
        import psimodpy

        db = psimodpy.load()
        isotopic = [e for e in db if e.formula and "(12)C" in e.formula]
        assert len(isotopic) > 0
        comp = isotopic[0].dict_formula
        assert comp is not None
        assert "(12)C" in comp
