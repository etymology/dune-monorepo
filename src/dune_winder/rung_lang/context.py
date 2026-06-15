"""Donor-L5X harvesting and new-tag synthesis (the import context shell).

An importable routine L5X needs the machine-state context Studio exported
with it: axis parameter blocks, UDTs, module references, existing
controller/program tags. None of that is authored here - it is copied
verbatim from the **donor**, a Studio "Export Routine" snapshot checked
in at ``winder/plc/ACD/donors/<program>/<routine>_Routine_RLL.L5X``.

This module performs text surgery on the donor (never re-serialising the
XML, so Studio sees byte-identical context):

- replace the ``Use="Target"`` routine's ``<RLLContent>`` with freshly
  emitted rungs,
- insert a synthesized ``<Tag>`` element (zeroed data, right DataType)
  into the program-scope ``<Tags Use="Context">`` block for every new
  ``local`` - which is what makes new tags arrive with the import, the
  capability the old paste loop never had.

Never synthesizes AxisParameters, UDT layouts, or module config.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import ast as rast


class ContextError(ValueError):
    pass


def donor_path(plc_root: Path, program: str, routine: str) -> Path:
    return plc_root / "ACD" / "donors" / program / f"{routine}_Routine_RLL.L5X"


def load_donor(plc_root: Path, program: str, routine: str) -> str:
    path = donor_path(plc_root, program, routine)
    if not path.exists():
        raise ContextError(
            f"no donor L5X at {path}.\n"
            "Create it once from Studio 5000: right-click the routine ->"
            " Export Routine..., save to that path, and check it in."
            " plc-acd-export does not produce donors; they carry the full"
            " tag/axis context only Studio can emit."
        )
    return path.read_text(encoding="utf-8-sig")


# ---------------------------------------------------------------------------
# Tag synthesis
# ---------------------------------------------------------------------------

_L5X_TYPES = {
    "bool": "BOOL",
    "int": "INT",
    "dint": "DINT",
    "real": "REAL",
    "motion": "MOTION_INSTRUCTION",
    "timer": "TIMER",
    "counter": "COUNTER",
}

_MOTION_MEMBERS = (
    ("FLAGS", "DINT", "0"),
    ("EN", "BOOL", "0"),
    ("DN", "BOOL", "0"),
    ("ER", "BOOL", "0"),
    ("PC", "BOOL", "0"),
    ("IP", "BOOL", "0"),
    ("AC", "BOOL", "0"),
    ("ACCEL", "BOOL", "0"),
    ("DECEL", "BOOL", "0"),
    ("TrackingMaster", "BOOL", "0"),
    ("CalculatedDataAvailable", "BOOL", "0"),
    ("ERR", "INT", "0"),
    ("STATUS", "SINT", "0"),
    ("STATE", "SINT", "0"),
    ("SEGMENT", "DINT", "0"),
    ("EXERR", "SINT", "0"),
)


def _struct_xml(name: str, data_type: str, l5k: str, members: tuple) -> list[str]:
    lines = [
        f'<Tag Name="{name}" TagType="Base" DataType="{data_type}"'
        ' Constant="false" ExternalAccess="Read/Write">',
        '<Data Format="L5K">',
        f"<![CDATA[{l5k}]]>",
        "</Data>",
        '<Data Format="Decorated">',
        f'<Structure DataType="{data_type}">',
    ]
    for member, mtype, value in members:
        radix = ' Radix="Decimal"' if mtype != "BOOL" else ""
        lines.append(
            f'<DataValueMember Name="{member}" DataType="{mtype}"{radix} Value="{value}"/>'
        )
    lines += ["</Structure>", "</Data>", "</Tag>"]
    return lines


def synthesize_tag_xml(decl: rast.TagDecl) -> list[str]:
    """A zeroed ``<Tag>`` element for a new program-scoped local.

    Patterns copied from Studio's own donor exports (BOOL/TIMER/
    MOTION_INSTRUCTION blocks in winder/plc/ACD/donors/).
    """
    data_type = _L5X_TYPES[decl.type or "bool"]

    if data_type == "MOTION_INSTRUCTION":
        return _struct_xml(decl.name, data_type, "[0,0,0,0,0,0,0,0,0]", _MOTION_MEMBERS)
    if data_type == "TIMER":
        preset = decl.preset_ms or 0
        members = (
            ("PRE", "DINT", str(preset)),
            ("ACC", "DINT", "0"),
            ("EN", "BOOL", "0"),
            ("TT", "BOOL", "0"),
            ("DN", "BOOL", "0"),
        )
        return _struct_xml(decl.name, data_type, f"[0,{preset},0]", members)
    if data_type == "COUNTER":
        preset = decl.preset_ms or 0
        members = (
            ("PRE", "DINT", str(preset)),
            ("ACC", "DINT", "0"),
            ("CU", "BOOL", "0"),
            ("CD", "BOOL", "0"),
            ("DN", "BOOL", "0"),
            ("OV", "BOOL", "0"),
            ("UN", "BOOL", "0"),
        )
        return _struct_xml(decl.name, data_type, f"[0,{preset},0]", members)

    # atomic
    if decl.dims:
        if data_type != "BOOL":
            values = ",".join(["0"] * decl.dims)
            l5k = f"[{values}]"
        else:
            l5k = "[" + ",".join(["2#0"] * decl.dims) + "]"
        lines = [
            f'<Tag Name="{decl.name}" TagType="Base" DataType="{data_type}"'
            f' Dimensions="{decl.dims}" Radix="Decimal" Constant="false"'
            ' ExternalAccess="Read/Write">',
            '<Data Format="L5K">',
            f"<![CDATA[{l5k}]]>",
            "</Data>",
            '<Data Format="Decorated">',
            f'<Array DataType="{data_type}" Dimensions="{decl.dims}" Radix="Decimal">',
        ]
        lines += [f'<Element Index="[{i}]" Value="0"/>' for i in range(decl.dims)]
        lines += ["</Array>", "</Data>", "</Tag>"]
        return lines

    return [
        f'<Tag Name="{decl.name}" TagType="Base" DataType="{data_type}"'
        ' Radix="Decimal" Constant="false" ExternalAccess="Read/Write">',
        '<Data Format="L5K">',
        "<![CDATA[0]]>",
        "</Data>",
        '<Data Format="Decorated">',
        f'<DataValue DataType="{data_type}" Radix="Decimal" Value="0"/>',
        "</Data>",
        "</Tag>",
    ]


# ---------------------------------------------------------------------------
# Donor surgery
# ---------------------------------------------------------------------------

_TAG_OPEN_RE = re.compile(r'<Tag Name="([^"]+)"')


def insert_program_tags(donor: str, program: str, new_tags: list[rast.TagDecl]) -> str:
    """Insert synthesized tags into the program-scope Tags block, keeping
    Studio's alphabetical order."""
    if not new_tags:
        return donor
    program_open = donor.find(f'<Program Use="Context" Name="{program}"')
    if program_open == -1:
        raise ContextError(f"donor has no Program context for {program!r}")
    tags_open = donor.find('<Tags Use="Context">', program_open)
    tags_close = donor.find("</Tags>", tags_open)
    if tags_open == -1 or tags_close == -1:
        raise ContextError('donor has no program-scope <Tags Use="Context"> block')
    block = donor[tags_open:tags_close]

    for decl in sorted(new_tags, key=lambda d: d.name.lower()):
        if f'<Tag Name="{decl.name}"' in block:
            continue  # already present (e.g. re-compile after import)
        xml = "\r\n".join(synthesize_tag_xml(decl)) + "\r\n"
        # insert before the first existing tag that sorts after the new one
        insert_at = len(block)
        for match in _TAG_OPEN_RE.finditer(block):
            if match.group(1).lower() > decl.name.lower():
                insert_at = match.start()
                break
        block = block[:insert_at] + xml + block[insert_at:]

    return donor[:tags_open] + block + donor[tags_close:]


def replace_target_rungs(donor: str, routine: str, rung_texts: list[str]) -> str:
    target = donor.find(f'<Routine Use="Target" Name="{routine}"')
    if target == -1:
        raise ContextError(f'donor has no Use="Target" routine {routine!r}')
    content_open = donor.find("<RLLContent>", target)
    content_close = donor.find("</RLLContent>", content_open)
    if content_open == -1 or content_close == -1:
        raise ContextError("donor target routine has no <RLLContent>")
    lines = []
    for i, text in enumerate(rung_texts):
        lines += [
            f'<Rung Number="{i}" Type="N">',
            "<Text>",
            f"<![CDATA[{text}]]>",
            "</Text>",
            "</Rung>",
        ]
    body = "\r\n" + "\r\n".join(lines) + "\r\n"
    return donor[: content_open + len("<RLLContent>")] + body + donor[content_close:]


def build_import_l5x(
    plc_root: Path,
    program: str,
    routine: str,
    rung_texts: list[str],
    new_tags: list[rast.TagDecl],
) -> str:
    donor = load_donor(plc_root, program, routine)
    donor = insert_program_tags(donor, program, new_tags)
    donor = replace_target_rungs(donor, routine, rung_texts)
    return donor


def write_import_l5x(path: Path, content: str) -> None:
    path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
