"""Exceptions raised by psimodpy."""

from __future__ import annotations


class PsimodError(Exception):
    """Base class for psimodpy errors, e.g. a duplicate id while building a database."""


class PsimodParseError(PsimodError, ValueError):
    """Malformed PSI-MOD OBO input. The message names the line or entry at fault."""


class PsimodKeyError(PsimodError, KeyError):
    """``db[key]`` found no entry. Also a ``KeyError`` (not a ``ValueError``); ``args[0]`` is the key looked up."""
