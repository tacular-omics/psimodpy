"""Parse PSI-MOD ``definition_ref`` strings into structured citation lists.

PSI-MOD encodes citations as a bracketed, comma-separated list of
``PREFIX:ACCESSION`` tokens, e.g.
``"[PubMed:18688235, RESID:AA0037, Unimod:21#S]"``.  This parser turns that
blob into typed :class:`psimodpy.server.models.Reference` instances so LLM
consumers don't have to.
"""

from __future__ import annotations

from psimodpy.server.models import Reference

_URL_PREFIXES = ("URL", "URI", "http", "https")


def parse_definition_ref(raw: str | None) -> list[Reference]:
    """Split a PSI-MOD definition_ref blob into typed Reference objects.

    The input may be empty, ``"[]"``, or a bracketed list.  Tokens of the
    form ``URL:...`` or ``URI:...`` become ``Reference(type=<prefix>,
    value=<rest>)`` since their suffix is not a stable accession; everything
    else becomes ``Reference(type=<prefix>, accession=<rest>)``.  Accession
    suffixes like ``Unimod:21#S`` are kept intact.
    """
    if not raw:
        return []
    inner = raw.strip()
    if inner.startswith("["):
        inner = inner[1:]
    if inner.endswith("]"):
        inner = inner[:-1]
    if not inner.strip():
        return []
    refs: list[Reference] = []
    for raw_token in inner.split(","):
        token = raw_token.strip()
        if not token:
            continue
        prefix, sep, suffix = token.partition(":")
        if not sep:
            refs.append(Reference(type="Misc", value=token))
            continue
        if prefix in _URL_PREFIXES:
            refs.append(Reference(type=prefix, value=suffix))
        else:
            refs.append(Reference(type=prefix, accession=suffix))
    return refs
