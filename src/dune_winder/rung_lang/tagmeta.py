"""Tag scope/type lookup backed by the exported tag JSONs.

``plc-acd-export`` writes ``controller_level_tags.json`` and per-program
``programTags.json``; this module answers, for a base tag name seen in a
routine: which scope is it (program shadows controller, as in Logix),
what is its data type, and - for timers/counters - what preset the last
export read from the controller.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TagMeta:
    controller: dict[str, dict] = field(default_factory=dict)
    programs: dict[str, dict[str, dict]] = field(default_factory=dict)
    routines: dict[str, list[str]] = field(default_factory=dict)
    main_routine: dict[str, str] = field(default_factory=dict)

    def scope(self, program: str, base: str) -> str | None:
        """'program' | 'controller' | None (unknown)."""
        if base in self.programs.get(program, {}):
            return "program"
        if base in self.controller:
            return "controller"
        return None

    def entry(self, program: str, base: str) -> dict | None:
        scope = self.scope(program, base)
        if scope == "program":
            return self.programs[program][base]
        if scope == "controller":
            return self.controller[base]
        return None

    def data_type(self, program: str, base: str) -> str | None:
        entry = self.entry(program, base)
        return entry.get("data_type_name") if entry else None

    def preset_ms(self, program: str, base: str) -> int | None:
        entry = self.entry(program, base)
        if not entry:
            return None
        value = entry.get("value")
        if isinstance(value, dict) and isinstance(value.get("PRE"), (int, float)):
            return int(value["PRE"])
        return None

    def timer_counter_values(self, program: str, base: str) -> tuple[str, str] | None:
        entry = self.entry(program, base)
        if not entry:
            return None
        value = entry.get("value")
        if not isinstance(value, dict):
            return None
        pre = value.get("PRE")
        acc = value.get("ACC")
        if not isinstance(pre, (int, float)) or not isinstance(acc, (int, float)):
            return None
        return (_format_logix_number(pre), _format_logix_number(acc))

    def program_routines(self, program: str) -> list[str]:
        return self.routines.get(program, [])


def load_tag_meta(plc_root: Path) -> TagMeta:
    meta = TagMeta()
    controller_path = plc_root / "controller_level_tags.json"
    if controller_path.exists():
        payload = json.loads(controller_path.read_text(encoding="utf-8"))
        meta.controller = {
            tag["name"]: tag for tag in payload.get("controller_level_tags", [])
        }
    for tags_path in sorted(plc_root.glob("*/programTags.json")):
        payload = json.loads(tags_path.read_text(encoding="utf-8"))
        program = payload.get("program_name", tags_path.parent.name)
        meta.programs[program] = {
            tag["name"]: tag for tag in payload.get("program_tags", [])
        }
        meta.routines[program] = list(payload.get("routines", []))
        if payload.get("main_routine_name"):
            meta.main_routine[program] = payload["main_routine_name"]
    return meta


def _format_logix_number(value: int | float) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
