"""OBO format writer for PSI-MOD entries."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from psimodpy.models import AminoAcid, Crosslink, PsiModEntry

_MINIMAL_HEADER = """\
format-version: 1.2
ontology: mod
default-namespace: PSI-MOD
subsetdef: PSI-MOD-slim "subset of protein modifications"
synonymtypedef: DeltaMass-label "Label from MS DeltaMass" EXACT
synonymtypedef: OMSSA-label "Short label from OMSSA" EXACT
synonymtypedef: PSI-MOD-alternate "Alternate name curated by PSI-MOD" EXACT
synonymtypedef: PSI-MOD-label "Short label curated by PSI-MOD" EXACT
synonymtypedef: PSI-MS-label "Agreed label from MS community" RELATED
synonymtypedef: RESID-alternate "Alternate name from RESID" EXACT
synonymtypedef: RESID-misnomer "Misnomer tagged alternate name from RESID" RELATED
synonymtypedef: RESID-name "Name from RESID" EXACT
synonymtypedef: RESID-systematic "Systematic name from RESID" EXACT
synonymtypedef: Unimod-alternate "Alternate name from Unimod" RELATED
synonymtypedef: Unimod-description "Description (full_name) from Unimod" RELATED
synonymtypedef: Unimod-interim "Interim label from Unimod" RELATED
synonymtypedef: UniProt-feature "Protein feature description from UniProtKB" EXACT
idspace: uniprot.ptm https://bioregistry.io/uniprot.ptm: "UniProt Post-Translational Modification"
"""


def _fmt_origin(origin: AminoAcid | Crosslink | None) -> str:
    if origin is None:
        return "none"
    if isinstance(origin, AminoAcid):
        return str(origin)
    return ", ".join(origin.sites)


def _fmt_formal_charge(charge: int) -> str:
    if charge >= 0:
        return f"{charge}+"
    return f"{abs(charge)}-"


def _escape_boundary_spaces(text: str) -> str:
    r"""Escape leading and trailing spaces as \W so strip() does not drop them."""
    if not text:
        return text
    lead = len(text) - len(text.lstrip(" "))
    if lead == len(text):
        return r"\W" * lead
    tail = len(text) - len(text.rstrip(" "))
    core = text[lead : len(text) - tail if tail else None]
    return (r"\W" * lead) + core + (r"\W" * tail)


def _escape_free_text(text: str) -> str:
    escaped = (
        text.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace('"', '\\"')
        .replace("{", "\\{")
        .replace("}", "\\}")
    )
    return _escape_boundary_spaces(escaped)


def _escape_quoted(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")


_DBXREF_ID_STRUCTURAL = frozenset({"\\", ",", '"', "{", "}", "W", "t"})
_DBXREF_QUOTED_STRUCTURAL = frozenset({"\\", '"'})
_DBXREF_MOD_STRUCTURAL = frozenset({"\\", '"', "{", "}"})


def _escape_dbxref_id(text: str) -> str:
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":
            if i + 1 < n and text[i + 1] in _DBXREF_ID_STRUCTURAL:
                out.append(text[i : i + 2])
                i += 2
                continue
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "[":
            out.append("\\[")
        elif ch == "]":
            out.append("\\]")
        elif ch == "{":
            out.append("\\{")
        elif ch == "}":
            out.append("\\}")
        elif ch == '"':
            out.append('\\"')
        else:
            out.append(ch)
        i += 1
    return _escape_boundary_spaces("".join(out))


def _escape_dbxref_quoted(inner: str) -> str:
    out: list[str] = []
    i = 0
    n = len(inner)
    while i < n:
        ch = inner[i]
        if ch == "\\":
            if i + 1 < n and inner[i + 1] in _DBXREF_QUOTED_STRUCTURAL:
                out.append(inner[i : i + 2])
                i += 2
                continue
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == '"':
            out.append('\\"')
        else:
            out.append(ch)
        i += 1
    return f'"{"".join(out)}"'


def _escape_dbxref_mod(inner: str) -> str:
    out: list[str] = []
    i = 0
    n = len(inner)
    in_q = False
    while i < n:
        ch = inner[i]
        if ch == "\\":
            keep = _DBXREF_QUOTED_STRUCTURAL if in_q else _DBXREF_MOD_STRUCTURAL
            if i + 1 < n and inner[i + 1] in keep:
                out.append(inner[i : i + 2])
                i += 2
                continue
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == '"':
            in_q = not in_q
            out.append(ch)
        elif not in_q and ch == "[":
            out.append("\\[")
        elif not in_q and ch == "]":
            out.append("\\]")
        else:
            out.append(ch)
        i += 1
    return f"{{{''.join(out)}}}"


def _parse_citation_chunk(chunk: str) -> tuple[str, str, str | None, str, str | None, str] | None:
    if not chunk:
        return ("", "", None, "", None, "")
    n = len(chunk)
    i = 0
    while i < n:
        ch = chunk[i]
        if ch == "\\":
            if i + 1 >= n:
                return None
            i += 2
            continue
        if ch in ('"', "{", "}"):
            break
        i += 1
    if i == n:
        id_part = chunk.rstrip(" \t")
        ws_trail = chunk[len(id_part) :]
        return (id_part, "", None, "", None, ws_trail)
    if chunk[i] == "}":
        return None
    raw_id = chunk[:i]
    id_part = raw_id.rstrip(" \t")
    if not id_part:
        return None
    ws = raw_id[len(id_part) :]

    desc_inner: str | None = None
    ws1 = ""
    ws2 = ""
    mod_inner: str | None = None

    if chunk[i] == '"':
        if not ws:
            return None
        ws1 = ws
        i += 1
        start = i
        while i < n:
            if chunk[i] == "\\":
                if i + 1 >= n:
                    return None
                i += 2
                continue
            if chunk[i] == '"':
                break
            i += 1
        if i >= n:
            return None
        desc_inner = chunk[start:i]
        i += 1
        ws_start = i
        while i < n and chunk[i] in (" ", "\t"):
            i += 1
        after_ws = chunk[ws_start:i]
        if i == n:
            return (id_part, ws1, desc_inner, "", None, after_ws)
        if chunk[i] != "{":
            return None
        ws2 = after_ws
    else:
        ws2 = ws

    # Must be at '{' starting trailing modifier. Unreachable: the scan above stops only on
    # '"', '{' or '}', '}' has returned already and '"' took the branch above, so this is '{'.
    # Kept as a guard in case that scan grows another stop character.
    if chunk[i] != "{":  # pragma: no cover - 299593 generated chunks never reach it
        return None
    i += 1
    mod_start = i
    in_q = False
    while i < n:
        ch = chunk[i]
        if ch == "\\":
            if i + 1 >= n:
                return None
            i += 2
            continue
        if ch == '"':
            in_q = not in_q
        elif ch == "}" and not in_q:
            break
        i += 1
    if i >= n or in_q:
        return None
    mod_inner = chunk[mod_start:i]
    ws_trail = chunk[i + 1 :]
    if any(ch not in (" ", "\t") for ch in ws_trail):
        return None
    return (id_part, ws1, desc_inner, ws2, mod_inner, ws_trail)


def _escape_boundary_ws(ws: str) -> str:
    return "".join(r"\W" if ch == " " else r"\t" for ch in ws)


def _try_escape_citation_list(core: str) -> str | None:
    chunks: list[str] = []
    start = 0
    i = 0
    n = len(core)
    in_quotes = False
    in_braces = False
    in_brace_quotes = False
    while i < n:
        ch = core[i]
        if ch == "\\":
            if i + 1 >= n:
                return None
            i += 2
            continue
        if in_braces:
            if ch == '"':
                in_brace_quotes = not in_brace_quotes
            elif ch == "}" and not in_brace_quotes:
                in_braces = False
        elif in_quotes:
            if ch == '"':
                in_quotes = False
        else:
            if ch == '"':
                in_quotes = True
            elif ch == "{":
                in_braces = True
            elif ch == "}":
                return None
            elif ch == ",":
                chunks.append(core[start:i])
                start = i + 1
        i += 1
    if in_quotes or in_braces:
        return None
    chunks.append(core[start:])

    formatted: list[str] = []
    for raw_chunk in chunks:
        lead_len = len(raw_chunk) - len(raw_chunk.lstrip(" \t"))
        sep_ws = raw_chunk[:lead_len]
        body = raw_chunk[lead_len:]
        parsed = _parse_citation_chunk(body)
        if parsed is None:
            return None
        id_part, ws1, desc_inner, ws2, mod_inner, ws_trail = parsed
        item = _escape_dbxref_id(id_part)
        if desc_inner is not None:
            item += ws1 + _escape_dbxref_quoted(desc_inner)
        if mod_inner is not None:
            item += ws2 + _escape_dbxref_mod(mod_inner)
        formatted.append(sep_ws + item + ws_trail)
    return ",".join(formatted)


def _escape_flat_dbxref(core: str) -> str:
    return (
        core.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace('"', '\\"')
    )


def _escape_dbxref(text: str) -> str:
    if not text:
        return text
    n = len(text)
    lead_end = 0
    while lead_end < n and text[lead_end] in (" ", "\t"):
        lead_end += 1
    lead = _escape_boundary_ws(text[:lead_end])
    if lead_end == n:
        return lead
    tail_start = n
    while tail_start > lead_end and text[tail_start - 1] in (" ", "\t"):
        tail_start -= 1
    tail = _escape_boundary_ws(text[tail_start:])
    core = text[lead_end:tail_start]
    structured = _try_escape_citation_list(core)
    escaped_core = structured if structured is not None else _escape_flat_dbxref(core)
    return lead + escaped_core + tail


def _xref(key: str, value: str) -> str:
    return f'xref: {key}: "{_escape_quoted(value)}"\n'


def _write_entry(fh, entry: PsiModEntry, names: dict[int, str]) -> None:
    fh.write("[Term]\n")
    fh.write(f"id: MOD:{entry.id:05d}\n")
    fh.write(f"name: {_escape_free_text(entry.name)}\n")
    fh.write(f'def: "{_escape_quoted(entry.definition)}" [{_escape_dbxref(entry.definition_ref)}]\n')
    if entry.in_slim_subset:
        fh.write("subset: PSI-MOD-slim\n")
    for syn in entry.synonyms:
        fh.write(f'synonym: "{_escape_quoted(syn.value)}" {syn.scope} {syn.type} []\n')
    for parent_id in entry.is_a:
        suffix = f" ! {_escape_free_text(names[parent_id])}" if parent_id in names else ""
        fh.write(f"is_a: MOD:{parent_id:05d}{suffix}\n")
    for rel in entry.relationships:
        suffix = f" ! {_escape_free_text(names[rel.target_id])}" if rel.target_id in names else ""
        fh.write(f"relationship: {rel.type} MOD:{rel.target_id:05d}{suffix}\n")
    if entry.comment is not None:
        fh.write(f"comment: {_escape_free_text(entry.comment)}\n")
    if entry.diff_mono is not None:
        fh.write(_xref("DiffMono", f"{entry.diff_mono:.6f}"))
    if entry.diff_avg is not None:
        fh.write(_xref("DiffAvg", f"{entry.diff_avg:.2f}"))
    if entry.diff_formula is not None:
        fh.write(_xref("DiffFormula", entry.diff_formula))
    if entry.mass_mono is not None:
        fh.write(_xref("MassMono", f"{entry.mass_mono:.6f}"))
    if entry.mass_avg is not None:
        fh.write(_xref("MassAvg", f"{entry.mass_avg:.2f}"))
    if entry.formula is not None:
        fh.write(_xref("Formula", entry.formula))
    if entry.origin is not None:
        fh.write(_xref("Origin", _fmt_origin(entry.origin)))
    if entry.term_spec is not None:
        fh.write(_xref("TermSpec", str(entry.term_spec)))
    if entry.source is not None:
        fh.write(_xref("Source", str(entry.source)))
    if entry.formal_charge is not None:
        fh.write(_xref("FormalCharge", _fmt_formal_charge(entry.formal_charge)))
    # Keep xref_unimod last so re-parsing gives the same xref_unimod.
    unimod = [u for u in entry.xrefs_unimod if u != entry.xref_unimod]
    if entry.xref_unimod is not None:
        unimod.append(entry.xref_unimod)
    for value in unimod:
        fh.write(_xref("Unimod", value))
    if entry.xref_uniprot_ptm is not None:
        fh.write(_xref("uniprot.ptm", entry.xref_uniprot_ptm))
    if entry.xref_gnome is not None:
        fh.write(_xref("GNOme", entry.xref_gnome))
    if entry.xref_remap is not None:
        fh.write(_xref("Remap", f"MOD:{entry.xref_remap:05d}"))
    if entry.is_obsolete:
        fh.write("is_obsolete: true\n")
    # After is_obsolete, because the OBO 1.4 guide says "The replaced_by tag may only be
    # specified for obsolete terms"; written in the id order the file gave.
    for target in entry.replaced_by:
        fh.write(f"replaced_by: MOD:{target:05d}\n")
    fh.write("\n")


def write_obo(
    entries: Iterable[PsiModEntry],
    path: Path | str,
    *,
    header_lines: Iterable[str] = (),
) -> Path:
    """Write PSI-MOD entries to an OBO-format file.

    The output is suitable for re-parsing with parse_obo(). Returns the
    resolved Path.
    """
    materialized = list(entries)
    names = {e.id: e.name for e in materialized}

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        header = list(header_lines)
        if header:
            for line in header:
                fh.write(line + "\n")
            fh.write("\n")
        else:
            fh.write(_MINIMAL_HEADER)
            fh.write("\n")
        for entry in materialized:
            _write_entry(fh, entry, names)
    return out
