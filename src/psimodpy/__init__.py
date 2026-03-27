"""psimodpy — Python library for the PSI-MOD protein modification ontology."""

from psimodpy._download import download_obo
from psimodpy.database import PsiModDatabase, load, load_from
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
    "load",
    "load_from",
    "parse_obo",
    "download_obo",
]
