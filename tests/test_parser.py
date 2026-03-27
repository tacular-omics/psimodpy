"""Tests for OBO file parsing."""

import pytest

import psimodpy
from psimodpy.models import AminoAcid, Crosslink, RelationshipType, Source, SynonymType, TermSpec


def test_total_term_count(db):
    assert len(db) == 2116


def test_obsolete_count(db):
    obsolete = [e for e in db if e.is_obsolete]
    assert len(obsolete) == 120


def test_slim_count(db):
    slim = [e for e in db if e.in_slim_subset]
    assert len(slim) == 811


# --- Root entry ---

def test_root_entry_name(db):
    root = db.get_by_id(0)
    assert root is not None
    assert root.name == "protein modification"


def test_root_entry_no_parents(db):
    root = db.get_by_id(0)
    assert root.is_a == ()


def test_root_entry_in_slim(db):
    root = db.get_by_id(0)
    assert root.in_slim_subset is True


def test_root_entry_no_masses(db):
    root = db.get_by_id(0)
    assert root.diff_mono is None
    assert root.diff_avg is None
    assert root.mass_mono is None
    assert root.formula is None


# --- Single-parent entry ---

def test_single_parent(db):
    entry = db.get_by_id(1)
    assert entry is not None
    assert entry.is_a == (1156,)


# --- Multi-parent entry (MOD:00002 has 2 parents) ---

def test_multi_parent(db):
    entry = db.get_by_id(2)
    assert entry is not None
    assert set(entry.is_a) == {396, 916}


# --- Relationships ---

def test_derives_from_relationship(db):
    """MOD:00125 (hypusine) derives_from MOD:01880."""
    entry = db.get_by_id(125)
    assert entry is not None
    derives = [r for r in entry.relationships if r.type == RelationshipType.DERIVES_FROM]
    assert len(derives) == 1
    assert derives[0].target_id == 1880


def test_contains_relationship(db):
    """MOD:00234 (L-cysteine glutathione disulfide) contains MOD:02026."""
    entry = db.get_by_id(234)
    assert entry is not None
    contains = [r for r in entry.relationships if r.type == RelationshipType.CONTAINS]
    assert len(contains) == 1
    assert contains[0].target_id == 2026


# --- Origin / crosslinks ---

def test_crosslink_origin_cc(db):
    """MOD:00229 has origin 'C, C' (disulfide crosslink)."""
    entry = db.get_by_id(229)
    assert entry is not None
    assert isinstance(entry.origin, Crosslink)
    assert entry.origin.sites == ("C", "C")


def test_single_origin_is_amino_acid(db):
    """MOD:00046 has origin 'S' — should be AminoAcid.SER."""
    entry = db.get_by_id(46)
    assert entry.origin == AminoAcid.SER


def test_mod_ref_origin_is_crosslink(db):
    """Entries with a MOD:NNNNN origin are returned as Crosslink."""
    mod_ref_entries = [
        e for e in db
        if isinstance(e.origin, Crosslink) and any(s.startswith("MOD:") for s in e.origin.sites)
    ]
    assert len(mod_ref_entries) > 0


# --- Float xrefs ---

def test_diff_mono_float(db):
    """MOD:00046 (O-phospho-L-serine) has DiffMono 79.966331."""
    entry = db.get_by_id(46)
    assert entry is not None
    assert entry.diff_mono == pytest.approx(79.966331, rel=1e-5)


def test_mass_mono_float(db):
    entry = db.get_by_id(35)
    assert entry is not None
    assert entry.mass_mono == pytest.approx(130.037842, rel=1e-5)


# --- "none" sentinel → Python None ---

def test_none_formula_sentinel(db):
    """MOD:00436 (first GNOme entry) has Formula: 'none' → formula is None."""
    entry = db.get_by_id(436)
    assert entry is not None
    assert entry.formula is None


# --- Isotopic formula ---

def test_isotopic_diff_formula_preserved(db):
    """Isotope notation in DiffFormula is preserved as-is."""
    # Find any entry with an isotopic diff formula
    isotopic = [e for e in db if e.diff_formula and "(12)C" in e.diff_formula]
    assert len(isotopic) > 0
    # Check that the raw string is not mangled
    assert "(12)C" in isotopic[0].diff_formula


# --- Typed synonyms ---

def test_synonyms_typed(db):
    """MOD:00010 (L-alanine residue) has a PSI-MOD-label synonym 'Ala'."""
    entry = db.get_by_id(10)
    assert entry is not None
    psi_mod_labels = [s for s in entry.synonyms if s.type == SynonymType.PSI_MOD_LABEL]
    assert any(s.value == "Ala" for s in psi_mod_labels)


def test_synonym_resid_name(db):
    """MOD:00035 has a RESID-name typed synonym."""
    entry = db.get_by_id(35)
    assert entry is not None
    resid_names = [s for s in entry.synonyms if s.type == SynonymType.RESID_NAME]
    assert len(resid_names) > 0


# --- Obsolete entries ---

def test_obsolete_flag(db):
    """MOD:00004 is marked obsolete."""
    entry = db.get_by_id(4)
    assert entry is not None
    assert entry.is_obsolete is True


def test_non_obsolete_flag(db):
    """MOD:00002 is not obsolete."""
    entry = db.get_by_id(2)
    assert entry.is_obsolete is False


# --- Remap xref on obsolete entry ---

def test_remap_xref_is_int(db):
    """Entries with a Remap xref have xref_remap set to an int."""
    remapped = [e for e in db if e.xref_remap is not None]
    assert len(remapped) > 0
    for e in remapped:
        assert isinstance(e.xref_remap, int)


# --- External xrefs ---

def test_xref_uniprot_ptm(db):
    """MOD:00035 has xref_uniprot_ptm == 'PTM-0369'."""
    entry = db.get_by_id(35)
    assert entry is not None
    assert entry.xref_uniprot_ptm == "PTM-0369"


def test_xref_gnome(db):
    """MOD:00436 has a GNOme cross-reference."""
    entry = db.get_by_id(436)
    assert entry is not None
    assert entry.xref_gnome is not None
    assert entry.xref_gnome.startswith("GNO:")


def test_formal_charge(db):
    """MOD:00049 (diphthamide) has a formal charge of '1+' → int 1."""
    entry = db.get_by_id(49)
    assert entry is not None
    assert entry.formal_charge == 1


def test_formal_charge_negative(db):
    """Negative charges are stored as negative ints."""
    neg_entries = [e for e in db if e.formal_charge is not None and e.formal_charge < 0]
    assert len(neg_entries) > 0


def test_slim_subset_flag(db):
    """MOD:00002 is in the PSI-MOD-slim subset."""
    entry = db.get_by_id(2)
    assert entry.in_slim_subset is True


# --- Source enum ---

def test_source_natural(db):
    """MOD:00002 has source 'natural'."""
    entry = db.get_by_id(2)
    assert entry.source == Source.NATURAL


def test_source_artifact(db):
    """Some entry has source 'artifact'."""
    artifacts = [e for e in db if e.source == Source.ARTIFACT]
    assert len(artifacts) > 0


# --- TermSpec enum ---

def test_term_spec_none(db):
    """MOD:00002 has TermSpec 'none'."""
    entry = db.get_by_id(2)
    assert entry.term_spec == TermSpec.NONE


def test_term_spec_n_term(db):
    """Some entry has TermSpec 'N-term'."""
    n_term_entries = [e for e in db if e.term_spec == TermSpec.N_TERM]
    assert len(n_term_entries) > 0


# --- Unimod xref ---

def test_xref_unimod(db):
    """MOD:00046 has xref_unimod 'Unimod:21'."""
    entry = db.get_by_id(46)
    assert entry is not None
    assert entry.xref_unimod == "Unimod:21"


def test_xref_unimod_count(db):
    """Many entries have a Unimod cross-reference."""
    unimod_refs = [e for e in db if e.xref_unimod is not None]
    assert len(unimod_refs) > 100


# --- parse_obo accepts both str and Path ---

def test_parse_obo_str_path(tmp_path):
    import importlib.resources
    import shutil

    pkg_data = importlib.resources.files("psimodpy.data")
    with importlib.resources.as_file(pkg_data.joinpath("PSI-MOD.obo")) as src:
        dest = tmp_path / "PSI-MOD.obo"
        shutil.copy(src, dest)

    db_str = psimodpy.parse_obo(str(dest))
    db_path = psimodpy.parse_obo(dest)
    assert len(db_str) == len(db_path) == 2116
