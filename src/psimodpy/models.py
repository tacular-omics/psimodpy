"""Domain model for PSI-MOD protein modification ontology entries."""

from __future__ import annotations

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
    type: SynonymType


@dataclass(frozen=True, slots=True)
class Relationship:
    """A directed relationship from a PSI-MOD entry to another entry."""

    type: RelationshipType
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

    term_spec: TermSpec | None
    """Positional specificity (xref: TermSpec)."""

    source: Source | None
    """Modification source classification (xref: Source)."""

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

    @property
    def dict_diff_formula(self) -> dict[str, int] | None:
        """Parse diff_formula into {element: count}. Returns None if no formula."""
        if self.diff_formula is None:
            return None
        from psimodpy._formula import parse_formula

        return parse_formula(self.diff_formula)

    @property
    def dict_formula(self) -> dict[str, int] | None:
        """Parse formula into {element: count}. Returns None if no formula."""
        if self.formula is None:
            return None
        from psimodpy._formula import parse_formula

        return parse_formula(self.formula)

    @property
    def proforma_diff_formula(self) -> str | None:
        """Hill-notation string for diff_formula, e.g. 'C2H2O'. Returns None if no formula."""
        composition = self.dict_diff_formula
        if composition is None:
            return None
        from psimodpy._formula import formula_to_hill

        return formula_to_hill(composition)
