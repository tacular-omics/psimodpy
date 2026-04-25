"""OBO file parser for PSI-MOD protein modification ontology."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from psimodpy.database import PsiModDatabase

# Compiled regexes (module-level, compiled once)
_DEF_RE = re.compile(r'^def:\s+"(.+?)"\s+\[([^\]]*)\]')
_SYNONYM_RE = re.compile(r'^synonym:\s+"(.+?)"\s+(\w+)\s+(\S+)\s+\[\]')
_IS_A_RE = re.compile(r"^is_a:\s+MOD:(\d+)")
_RELATIONSHIP_RE = re.compile(r"^relationship:\s+(\S+)\s+MOD:(\d+)")
_XREF_RE = re.compile(r'^xref:\s+([^:]+):\s+"(.+?)"$')
_XREF_UNIPROT_RE = re.compile(r"^xref:\s+(uniprot\.ptm):(\S+)$")
_SUBSET_SLIM_RE = re.compile(r"^subset:\s+PSI-MOD-slim")


def _parse_float(value: str | None) -> float | None:
    if value is None or value == "none":
        return None
    return float(value)


def _parse_str_or_none(value: str | None) -> str | None:
    if value is None or value == "none":
        return None
    return value


def _parse_formal_charge(value: str) -> int:
    """Parse '1+' → 1, '2-' → -2."""
    if value.endswith("+"):
        return int(value[:-1])
    if value.endswith("-"):
        return -int(value[:-1])
    return int(value)


def _parse_origin(value: str) -> AminoAcid | Crosslink | None:
    """Parse an Origin xref value into a typed representation.

    - ``"none"`` → ``None``
    - Single letter code → :class:`AminoAcid`
    - Comma-separated, multi-residue, or MOD reference → :class:`Crosslink`
    """
    if value == "none":
        return None
    parts = [p.strip() for p in value.split(",")]
    if len(parts) == 1:
        try:
            return AminoAcid(parts[0])
        except ValueError:
            # MOD:NNNNN reference or unrecognised code
            return Crosslink(sites=(parts[0],))
    return Crosslink(sites=tuple(parts))


def _parse_mod_id(mod_str: str) -> int:
    """Parse 'MOD:NNNNN' to int."""
    return int(mod_str[4:])


def _build_entry(block: list[str]) -> PsiModEntry | None:
    """Parse a list of OBO lines for one [Term] block into a PsiModEntry."""
    entry_id: int | None = None
    name: str | None = None
    definition: str = ""
    definition_ref: str = "[]"
    synonyms: list[Synonym] = []
    is_a: list[int] = []
    relationships: list[Relationship] = []
    comment: str | None = None
    in_slim_subset: bool = False
    is_obsolete: bool = False
    xrefs: dict[str, str] = {}
    xref_uniprot_ptm: str | None = None

    for line in block:
        if line.startswith("id: MOD:"):
            entry_id = int(line[8:].split()[0])
        elif line.startswith("name: "):
            name = line[6:]
        elif line.startswith("def: "):
            m = _DEF_RE.match(line)
            if m:
                definition = m.group(1)
                definition_ref = f"[{m.group(2)}]"
        elif line.startswith("synonym: "):
            m = _SYNONYM_RE.match(line)
            if m:
                value, scope, type_str = m.group(1), m.group(2), m.group(3)
                try:
                    synonyms.append(Synonym(value=value, type=SynonymType(type_str), scope=scope))
                except ValueError:
                    pass  # unknown synonym type — skip
        elif line.startswith("is_a: "):
            m = _IS_A_RE.match(line)
            if m:
                is_a.append(int(m.group(1)))
        elif line.startswith("relationship: "):
            m = _RELATIONSHIP_RE.match(line)
            if m:
                rel_type_str, target_id_str = m.group(1), m.group(2)
                try:
                    relationships.append(
                        Relationship(
                            type=RelationshipType(rel_type_str),
                            target_id=int(target_id_str),
                        )
                    )
                except ValueError:
                    pass  # unknown relationship type — skip
        elif _SUBSET_SLIM_RE.match(line):
            in_slim_subset = True
        elif line.startswith("comment: "):
            comment = line[9:]
        elif line == "is_obsolete: true":
            is_obsolete = True
        elif line.startswith("xref: "):
            # Try uniprot.ptm special case first (no space before value)
            m = _XREF_UNIPROT_RE.match(line)
            if m:
                xref_uniprot_ptm = m.group(2)
                continue
            # Standard xref: KEY: "VALUE"
            m = _XREF_RE.match(line)
            if m:
                xrefs[m.group(1)] = m.group(2)

    if entry_id is None or name is None:
        return None

    # Parse TermSpec
    term_spec: TermSpec | None = None
    if "TermSpec" in xrefs:
        try:
            term_spec = TermSpec(xrefs["TermSpec"])
        except ValueError:
            pass

    # Parse Source
    source: Source | None = None
    if "Source" in xrefs:
        try:
            source = Source(xrefs["Source"])
        except ValueError:
            pass

    # Parse Remap (obsolete redirect)
    xref_remap: int | None = None
    if "Remap" in xrefs:
        try:
            xref_remap = _parse_mod_id(xrefs["Remap"])
        except (ValueError, IndexError):
            pass

    return PsiModEntry(
        id=entry_id,
        name=name,
        definition=definition,
        synonyms=tuple(synonyms),
        is_a=tuple(is_a),
        relationships=tuple(relationships),
        comment=comment,
        diff_mono=_parse_float(xrefs.get("DiffMono")),
        diff_avg=_parse_float(xrefs.get("DiffAvg")),
        diff_formula=_parse_str_or_none(xrefs.get("DiffFormula")),
        mass_mono=_parse_float(xrefs.get("MassMono")),
        mass_avg=_parse_float(xrefs.get("MassAvg")),
        formula=_parse_str_or_none(xrefs.get("Formula")),
        origin=_parse_origin(xrefs["Origin"]) if "Origin" in xrefs else None,
        term_spec=term_spec,
        source=source,
        formal_charge=_parse_formal_charge(xrefs["FormalCharge"]) if "FormalCharge" in xrefs else None,
        xref_unimod=xrefs.get("Unimod"),
        xref_uniprot_ptm=xref_uniprot_ptm,
        xref_gnome=xrefs.get("GNOme"),
        xref_remap=xref_remap,
        in_slim_subset=in_slim_subset,
        is_obsolete=is_obsolete,
        definition_ref=definition_ref,
    )


def parse_obo(path: Path | str) -> PsiModDatabase:
    """Parse a PSI-MOD OBO file and return a PsiModDatabase.

    Args:
        path: Path to the OBO file (str or Path).

    Returns:
        A PsiModDatabase populated with all parsed entries.
    """
    from psimodpy.database import PsiModDatabase

    path = Path(path)
    entries: list[PsiModEntry] = []
    header_lines: list[str] = []
    current_block: list[str] = []
    in_term = False
    past_header = False

    with path.open(encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\n").rstrip("\r")

            if line == "[Term]":
                in_term = True
                past_header = True
                current_block = []
                continue

            if line.startswith("[") and line != "[Term]":
                # End of a term block when another stanza starts
                if in_term and current_block:
                    entry = _build_entry(current_block)
                    if entry is not None:
                        entries.append(entry)
                in_term = False
                past_header = True
                current_block = []
                continue

            if in_term:
                if line == "":
                    # Blank line ends the current block
                    entry = _build_entry(current_block)
                    if entry is not None:
                        entries.append(entry)
                    in_term = False
                    current_block = []
                else:
                    current_block.append(line)
            elif not past_header:
                header_lines.append(line)

    # Handle last block if file doesn't end with blank line
    if in_term and current_block:
        entry = _build_entry(current_block)
        if entry is not None:
            entries.append(entry)

    return PsiModDatabase(entries, header_lines=tuple(header_lines))
