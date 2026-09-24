"""psimodpy — Python library for the PSI-MOD protein modification ontology."""

from psimodpy._download import download, download_obo
from psimodpy._obo_writer import write_obo
from psimodpy._tabular import write_tsv
from psimodpy.database import PsiModDatabase, load, load_from
from psimodpy.errors import PsimodError, PsimodParseError
from psimodpy.models import (
    AminoAcid,
    Crosslink,
    PsiModEntry,
    Relationship,
    RelationshipType,
    Source,
    Synonym,
    SynonymType,
    TermSpec,
)
from psimodpy.parser import parse_obo

__all__ = [
    "AminoAcid",
    "Crosslink",
    "PsiModEntry",
    "Synonym",
    "SynonymType",
    "Relationship",
    "RelationshipType",
    "TermSpec",
    "Source",
    "PsiModDatabase",
    "PsimodError",
    "PsimodParseError",
    "load",
    "load_from",
    "parse_obo",
    "download",
    "download_obo",
    "write_obo",
    "write_tsv",
    "__version__",
]

__version__ = "0.2.2"
