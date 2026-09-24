"""Domain model for PSI-MOD protein modification ontology entries."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from enum import StrEnum


class SynonymType(StrEnum):
    """Synonym type labels defined in the PSI-MOD OBO file."""

    DELTA_MASS_LABEL = "DeltaMass-label"
    OMSSA_LABEL = "OMSSA-label"
    PSI_MOD_LABEL = "PSI-MOD-label"
    PSI_MOD_ALTERNATE = "PSI-MOD-alternate"
    PSI_MS_LABEL = "PSI-MS-label"
    RESID_NAME = "RESID-name"
    RESID_ALTERNATE = "RESID-alternate"
    RESID_SYSTEMATIC = "RESID-systematic"
    RESID_MISNOMER = "RESID-misnomer"
    UNIMOD_DESCRIPTION = "Unimod-description"
    UNIMOD_ALTERNATE = "Unimod-alternate"
    UNIMOD_INTERIM = "Unimod-interim"
    UNIPROT_FEATURE = "UniProt-feature"


class RelationshipType(StrEnum):
    """Complex relationship types used in PSI-MOD beyond simple is_a hierarchy."""

    DERIVES_FROM = "derives_from"
    HAS_FUNCTIONAL_PARENT = "has_functional_parent"
    CONTAINS = "contains"
    PART_OF = "part_of"


class TermSpec(StrEnum):
    """Positional specificity of a modification on the protein sequence."""

    NONE = "none"
    N_TERM = "N-term"
    C_TERM = "C-term"


class Source(StrEnum):
    """Origin classification of a modification."""

    NATURAL = "natural"
    ARTIFACT = "artifact"
    # Four entries in the OBO use "artifactual" as a variant spelling
    ARTIFACTUAL = "artifactual"
    HYPOTHETICAL = "hypothetical"
    NONE = "none"


class AminoAcid(StrEnum):
    """Single-letter amino acid codes used in PSI-MOD Origin xrefs."""

    ALA = "A"
    ARG = "R"
    ASN = "N"
    ASP = "D"
    CYS = "C"
    GLN = "Q"
    GLU = "E"
    GLY = "G"
    HIS = "H"
    ILE = "I"
    LEU = "L"
    LYS = "K"
    MET = "M"
    PHE = "F"
    PRO = "P"
    SER = "S"
    THR = "T"
    TRP = "W"
    TYR = "Y"
    VAL = "V"
    SEC = "U"  # selenocysteine
    PYL = "O"  # pyrrolysine
    ANY = "X"  # unspecified / any residue


@dataclass(frozen=True, slots=True)
class Crosslink:
    """Multi-residue or MOD-referenced modification origin.

    Each site is either an :class:`AminoAcid` value (single letter) or a
    ``"MOD:NNNNN"`` string for modifications-of-modifications.
    """

    sites: tuple[str, ...]
    """Ordered residue sites, e.g. ``("C", "C")`` for a disulfide."""


@dataclass(frozen=True, slots=True)
class Synonym:
    """A typed synonym for a PSI-MOD entry."""

    value: str
    type: SynonymType | str
    """A :class:`SynonymType`, or the raw string for a type this version does not know."""
    scope: str = "EXACT"


@dataclass(frozen=True, slots=True)
class Relationship:
    """A directed relationship from a PSI-MOD entry to another entry."""

    type: RelationshipType | str
    """A :class:`RelationshipType`, or the raw string for a type this version does not know."""
    target_id: int


@dataclass(frozen=True, slots=True)
class PsiModEntry:
    """A single term from the PSI-MOD protein modification ontology."""

    id: int
    """Numeric part of the MOD:NNNNN identifier."""

    name: str
    definition: str
    """Quoted definition text; citation block stripped."""

    synonyms: tuple[Synonym, ...]
    is_a: tuple[int, ...]
    """Parent term IDs (numeric). PSI-MOD entries can have multiple parents."""

    relationships: tuple[Relationship, ...]
    """derives_from / contains / part_of / has_functional_parent links."""

    comment: str | None

    # Mass and formula xrefs
    diff_mono: float | None
    """Monoisotopic mass difference (xref: DiffMono)."""

    diff_avg: float | None
    """Average mass difference (xref: DiffAvg)."""

    diff_formula: str | None
    """Elemental difference formula in PSI-MOD format, e.g. 'C 0 H 0 N 0 O 3 P 1'."""

    mass_mono: float | None
    """Full monoisotopic mass (xref: MassMono)."""

    mass_avg: float | None
    """Full average mass (xref: MassAvg)."""

    formula: str | None
    """Full elemental formula in PSI-MOD format. None when OBO value is 'none'."""

    # Position/context xrefs
    origin: AminoAcid | Crosslink | None
    """Residue origin. Single residues are :class:`AminoAcid`; multi-residue
    crosslinks or MOD-referenced origins are :class:`Crosslink`."""

    term_spec: TermSpec | str | None
    """Positional specificity (xref: TermSpec); the raw string if the value is not a known TermSpec."""

    source: Source | str | None
    """Modification source classification (xref: Source); the raw string if not a known Source."""

    formal_charge: int | None
    """Net formal charge as a signed integer, e.g. ``1``, ``-2`` (xref: FormalCharge)."""

    # External cross-references
    xref_unimod: str | None
    """Unimod cross-reference, e.g. 'Unimod:21#S' (xref: Unimod)."""

    xref_uniprot_ptm: str | None
    """UniProt PTM cross-reference, e.g. 'PTM-0369' (xref: uniprot.ptm)."""

    xref_gnome: str | None
    """GNOme glycan ontology cross-reference, e.g. 'GNO:G29068FM' (xref: GNOme)."""

    xref_remap: int | None
    """Replacement term ID for obsolete entries (xref: Remap). Stored as numeric ID."""

    in_slim_subset: bool
    """True if this entry belongs to the PSI-MOD-slim curated subset."""

    is_obsolete: bool
    """True if this entry is marked obsolete in the OBO file."""

    definition_ref: str = ""
    """Citation list from the def: line without brackets, e.g. 'PubMed:18688235, RESID:AA0037'."""

    @property
    def accession(self) -> str:
        """The MOD accession, e.g. "MOD:00696" (the ``accession`` field of the REST/MCP wire model)."""
        return f"MOD:{self.id:05d}"

    def get_mass(self, *, monoisotopic: bool = True) -> float | None:
        """The mass difference in Da: ``diff_mono`` (default) or, with ``monoisotopic=False``, ``diff_avg``.

        ``None`` when PSI-MOD gives no such mass for this entry.
        """
        return self.diff_mono if monoisotopic else self.diff_avg

    @property
    def dict_composition(self) -> dict[str, int] | None:
        """Parse diff_formula into {element: count}. Returns None if no formula.

        Zero counts are dropped; negative counts are kept. Isotopes are keyed like
        tacular and peptacular ("13C"), not like the OBO ("(13)C").
        """
        if self.diff_formula is None:
            return None
        from psimodpy._formula import parse_formula, to_isotope_keys

        return to_isotope_keys(parse_formula(self.diff_formula))

    @property
    def dict_formula(self) -> dict[str, int] | None:
        """Parse formula into {element: count}; zero counts dropped, isotopes keyed "13C". None if no formula."""
        if self.formula is None:
            return None
        from psimodpy._formula import parse_formula, to_isotope_keys

        return to_isotope_keys(parse_formula(self.formula))

    @property
    def proforma_formula(self) -> str | None:
        """ProForma 2.0 formula for diff_formula in Hill order, e.g. 'HO3P' or '[13C3]H4O'.

        No spaces; isotopes use ProForma bracket syntax ("[2H8]"). Returns None if no formula.
        """
        composition = self.dict_composition
        if composition is None:
            return None
        from psimodpy._formula import formula_to_proforma

        return formula_to_proforma(composition)

    @property
    def dict_diff_formula(self) -> dict[str, int] | None:
        """Deprecated alias of :attr:`dict_composition`; will be removed in 2.0."""
        warnings.warn("dict_diff_formula is deprecated; use dict_composition", DeprecationWarning, stacklevel=2)
        return self.dict_composition

    @property
    def proforma_diff_formula(self) -> str | None:
        """Deprecated alias of :attr:`proforma_formula`; will be removed in 2.0."""
        warnings.warn("proforma_diff_formula is deprecated; use proforma_formula", DeprecationWarning, stacklevel=2)
        return self.proforma_formula
