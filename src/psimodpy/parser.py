"""OBO file parser for PSI-MOD protein modification ontology."""

from __future__ import annotations

import re
import warnings
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from psimodpy.errors import PsimodParseError
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
_DEF_RE = re.compile(r'^def:\s+"(.*?)"\s+\[([^\]]*)\]')
_SYNONYM_RE = re.compile(r'^synonym:\s+"(.+?)"\s+(\w+)\s+(\S+)\s+\[\]')
_IS_A_RE = re.compile(r"^is_a:\s+MOD:(\d+)")
_RELATIONSHIP_RE = re.compile(r"^relationship:\s+(\S+)\s+MOD:(\d+)")
_XREF_RE = re.compile(r'^xref:\s+([^:]+):\s+"(.*?)"$')
_XREF_UNIPROT_RE = re.compile(r"^xref:\s+(uniprot\.ptm):(\S+)$")
_SUBSET_SLIM_RE = re.compile(r"^subset:\s+PSI-MOD-slim")


class _Issues:
    """Collects recoverable problems during one parse and reports them as grouped warnings."""

    def __init__(self) -> None:
        self.unknown: dict[tuple[str, str], list[int]] = {}
        self.unrecognised: dict[str, list[tuple[int, str]]] = {}

    def enum_value[E: StrEnum](self, enum: type[E], field: str, value: str, lineno: int) -> E | str:
        """Return ``enum(value)``, or ``value`` itself (recorded for a warning) if it is not a member."""
        try:
            return enum(value)
        except ValueError:
            self.unknown.setdefault((field, value), []).append(lineno)
            return value

    def line(self, key: str, lineno: int, line: str) -> None:
        self.unrecognised.setdefault(key, []).append((lineno, line))

    def warn(self, path: Path) -> None:
        for (field, value), lines in self.unknown.items():
            warnings.warn(
                f"{path}: unknown {field} {value!r} kept as a plain string ({len(lines)} occurrence(s), "
                f"first at line {lines[0]}); psimodpy may need an update",
                UserWarning,
                stacklevel=3,
            )
        for key, lines in self.unrecognised.items():
            lineno, text = lines[0]
            warnings.warn(
                f"{path}: {len(lines)} unrecognised {key!r} line(s) dropped; first at line {lineno}: {text!r}",
                UserWarning,
                stacklevel=3,
            )


def _convert[T](convert: Callable[[str], T], value: str, field: str, where: str) -> T:
    try:
        return convert(value)
    except (ValueError, IndexError):
        raise PsimodParseError(f"{where}: malformed {field} {value!r}") from None


def _parse_float(value: str | None, field: str, where: str) -> float | None:
    if value is None or value == "none":
        return None
    return _convert(float, value, field, where)


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
    if not mod_str.startswith("MOD:"):
        raise ValueError(mod_str)
    return int(mod_str[4:])


def _build_entry(block: list[tuple[int, str]], path: Path, issues: _Issues) -> PsiModEntry | None:
    """Parse the numbered OBO lines of one [Term] block into a PsiModEntry.

    Returns None (with a warning) for a block without an id or name. Raises
    PsimodParseError for a malformed id, mass, charge or remap value.
    """
    entry_id: int | None = None
    name: str | None = None
    definition: str = ""
    definition_ref: str = ""
    synonyms: list[Synonym] = []
    is_a: list[int] = []
    relationships: list[Relationship] = []
    comment: str | None = None
    in_slim_subset: bool = False
    is_obsolete: bool = False
    xrefs: dict[str, tuple[str, int]] = {}
    xref_uniprot_ptm: str | None = None

    for lineno, line in block:
        if line.startswith("id: "):
            if line.startswith("id: MOD:"):
                token = line[8:].split(maxsplit=1)
                entry_id = _convert(int, token[0] if token else "", "id", f"{path}, line {lineno}")
        elif line.startswith("name: "):
            name = line[6:]
        elif line.startswith("def: "):
            m = _DEF_RE.match(line)
            if m:
                definition = m.group(1)
                definition_ref = m.group(2).strip()
            else:
                issues.line("def:", lineno, line)
        elif line.startswith("synonym: "):
            m = _SYNONYM_RE.match(line)
            if m:
                value, scope, type_str = m.group(1), m.group(2), m.group(3)
                syn_type = issues.enum_value(SynonymType, "synonym type", type_str, lineno)
                synonyms.append(Synonym(value=value, type=syn_type, scope=scope))
            else:
                issues.line("synonym:", lineno, line)
        elif line.startswith("is_a: "):
            m = _IS_A_RE.match(line)
            if m:
                is_a.append(int(m.group(1)))
            else:
                issues.line("is_a:", lineno, line)
        elif line.startswith("relationship: "):
            m = _RELATIONSHIP_RE.match(line)
            if m:
                rel_type = issues.enum_value(RelationshipType, "relationship type", m.group(1), lineno)
                relationships.append(Relationship(type=rel_type, target_id=int(m.group(2))))
            else:
                issues.line("relationship:", lineno, line)
        elif _SUBSET_SLIM_RE.match(line):
            in_slim_subset = True
        elif line.startswith("comment: "):
            comment = line[9:]
        elif line == "is_obsolete: true":
            is_obsolete = True
        elif line.startswith("xref: "):
            # Pre-1.039 uniprot.ptm form, unquoted with no space: "xref: uniprot.ptm:PTM-0369"
            m = _XREF_UNIPROT_RE.match(line)
            if m:
                xref_uniprot_ptm = m.group(2)
                continue
            # Standard xref: KEY: "VALUE"; an empty value ("") means no value, like an absent xref
            m = _XREF_RE.match(line)
            if m:
                if m.group(2):
                    xrefs[m.group(1)] = (m.group(2), lineno)
            else:
                issues.line("xref:", lineno, line)

    if entry_id is None or name is None:
        first = block[0][0] if block else 0
        label = f"MOD:{entry_id:05d}" if entry_id is not None else f"name {name!r}"
        missing = "name" if entry_id is not None else "id"
        warnings.warn(
            f"{path}: [Term] at line {first - 1} ({label}) has no {missing}; skipped", UserWarning, stacklevel=3
        )
        return None

    def raw(key: str) -> str | None:
        return xrefs[key][0] if key in xrefs else None

    def where(key: str) -> str:
        return f"{path}, line {xrefs[key][1]} (MOD:{entry_id:05d})"

    def number(key: str) -> float | None:
        return _parse_float(raw(key), key, where(key)) if key in xrefs else None

    def enum_xref[E: StrEnum](enum: type[E], key: str) -> E | str | None:
        if key not in xrefs:
            return None
        value, lineno = xrefs[key]
        return issues.enum_value(enum, key, value, lineno)

    return PsiModEntry(
        id=entry_id,
        name=name,
        definition=definition,
        synonyms=tuple(synonyms),
        is_a=tuple(is_a),
        relationships=tuple(relationships),
        comment=comment,
        diff_mono=number("DiffMono"),
        diff_avg=number("DiffAvg"),
        diff_formula=_parse_str_or_none(raw("DiffFormula")),
        mass_mono=number("MassMono"),
        mass_avg=number("MassAvg"),
        formula=_parse_str_or_none(raw("Formula")),
        origin=_parse_origin(xrefs["Origin"][0]) if "Origin" in xrefs else None,
        term_spec=enum_xref(TermSpec, "TermSpec"),
        source=enum_xref(Source, "Source"),
        formal_charge=(
            _convert(_parse_formal_charge, xrefs["FormalCharge"][0], "FormalCharge", where("FormalCharge"))
            if "FormalCharge" in xrefs
            else None
        ),
        xref_unimod=raw("Unimod"),
        xref_uniprot_ptm=raw("uniprot.ptm") or xref_uniprot_ptm,
        xref_gnome=raw("GNOme"),
        xref_remap=_convert(_parse_mod_id, xrefs["Remap"][0], "Remap", where("Remap")) if "Remap" in xrefs else None,
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

    Raises:
        PsimodParseError: for a malformed id, mass, charge or remap value (the message
            names the file, line and entry).
        PsimodError: if two terms share an id.

    Recoverable problems are reported with ``warnings.warn`` and do not abort the
    load: a [Term] without an id or name is skipped; an unknown synonym type,
    relationship type, TermSpec or Source is kept as a plain string; and a line
    whose syntax is not recognised is dropped.
    """
    from psimodpy.database import PsiModDatabase

    path = Path(path)
    issues = _Issues()
    entries: list[PsiModEntry] = []
    header_lines: list[str] = []
    current_block: list[tuple[int, str]] = []
    in_term = False
    past_header = False

    def flush() -> None:
        entry = _build_entry(current_block, path, issues)
        if entry is not None:
            entries.append(entry)

    with path.open(encoding="utf-8") as fh:
        for lineno, raw_line in enumerate(fh, start=1):
            line = raw_line.rstrip("\n").rstrip("\r")

            if line == "[Term]":
                if in_term and current_block:
                    flush()
                in_term = True
                past_header = True
                current_block = []
                continue

            if line.startswith("["):
                # End of a term block when another stanza starts
                if in_term and current_block:
                    flush()
                in_term = False
                past_header = True
                current_block = []
                continue

            if in_term:
                if line == "":
                    # Blank line ends the current block
                    if current_block:
                        flush()
                    in_term = False
                    current_block = []
                else:
                    current_block.append((lineno, line))
            elif not past_header:
                header_lines.append(line)

    # Handle last block if file doesn't end with blank line
    if in_term and current_block:
        flush()

    issues.warn(path)
    while header_lines and header_lines[-1] == "":
        header_lines.pop()
    return PsiModDatabase(entries, header_lines=tuple(header_lines))
