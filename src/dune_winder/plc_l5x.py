"""Read rung text from the per-routine L5X exports under ``winder/plc/``.

``plc-acd-export`` writes one ``<routine>_Routine_RLL.L5X`` per routine
straight from the ACD. The paren-dialect rung text in each ``<Rung>``'s
CDATA is the single source of truth for the ``.rung`` projection and the
ladder simulator. It supersedes the old ``studio_copy.rllscrap``
intermediary, which held the same text joined with three spaces.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_RUNG_RE = re.compile(
    r'<Rung\s+Number="(?P<number>\d+)"\s+Type="(?P<type>[^"]+)">\s*'
    r"<Text>(?P<body>.*?)</Text>",
    re.DOTALL,
)


@dataclass(frozen=True)
class L5xRung:
    number: int
    rung_type: str  # "N" normal, "e" pending edit
    text: str  # paren-dialect rung text, trailing ';' included


def _decode_cdata(body: str) -> str:
    """Invert ``acd_export_l5x._cdata``: unwrap the CDATA section(s)."""
    text = body.strip()
    text = text.removeprefix("<![CDATA[").removesuffix("]]>")
    return text.replace("]]]]><![CDATA[>", "]]>")


def read_l5x_rungs(l5x_path: Path) -> list[L5xRung]:
    """The rungs of a routine L5X in display order (empty for non-RLL/empty)."""
    raw = Path(l5x_path).read_text(encoding="utf-8-sig", errors="replace")
    return [
        L5xRung(int(m["number"]), m["type"], _decode_cdata(m["body"]))
        for m in _RUNG_RE.finditer(raw)
    ]


def routine_paren_text(l5x_path: Path) -> str:
    """Rung text joined the way Studio's clipboard / the old .rllscrap did."""
    return "   ".join(rung.text for rung in read_l5x_rungs(l5x_path))
