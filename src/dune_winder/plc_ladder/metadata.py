from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dune_winder.paths import PLC_ROOT


PROGRAM_ALIASES: dict[str, str] = {
    "MainProgram": "main",
    "Ready_State_1": "state_1_ready",
    "MoveXY_State_2_3": "state_3_move_xy",
    "MoveZ_State_4_5": "state_5_move_z",
    "Error_State_10": "state_10_error",
    "Initialize": "init",
    "motionQueue": "queued_motion",
    "HMI_Stop_Request_14": "state_14_hmi_stop",
    "UnServo_9": "state_9_unservo",
    "PID_Tension_Servo": "tension_pid",
    "EOT_Trip_11": "state_11_eot_trip",
    "Latch_UnLatch_State_6_7_8": "state_6_latch",
    "xz_move": "state_12_move_xz",
    "yz_move": "state_13_move_yz",
}


@dataclass(frozen=True)
class FieldDefinition:
    name: str
    tag_type: str | None
    data_type_name: str | None
    array_length: int = 0
    bit: int | None = None
    offset: int | None = None


@dataclass(frozen=True)
class UDTDefinition:
    name: str
    fields: tuple[FieldDefinition, ...]


@dataclass(frozen=True)
class TagDefinition:
    name: str
    fully_qualified_name: str
    tag_type: str | None
    data_type_name: str | None
    dimensions: tuple[int, ...]
    array_dimensions: int
    udt_name: str | None
    program: str | None
    value: Any = None


@dataclass(frozen=True)
class ProgramMetadata:
    name: str
    main_routine_name: str | None
    routines: tuple[str, ...]
    subroutines: tuple[str, ...]
    tags: dict[str, TagDefinition]


@dataclass(frozen=True)
class PlcMetadata:
    root: Path
    controller_tags: dict[str, TagDefinition]
    programs: dict[str, ProgramMetadata]
    udts: dict[str, UDTDefinition]

    def get_program(self, name: str) -> ProgramMetadata:
        return self.programs[str(name)]

    def get_tag_definition(
        self, name: str, program: str | None = None
    ) -> TagDefinition | None:
        if program is not None:
            program_metadata = self.programs.get(str(program))
            if program_metadata is not None:
                tag = program_metadata.tags.get(str(name))
                if tag is not None:
                    return tag
        return self.controller_tags.get(str(name))


def _field_definition(raw: dict[str, Any]) -> FieldDefinition:
    return FieldDefinition(
        name=str(raw["name"]),
        tag_type=raw.get("tag_type"),
        data_type_name=raw.get("data_type_name"),
        array_length=int(raw.get("array_length") or 0),
        bit=raw.get("bit"),
        offset=raw.get("offset"),
    )


def _udt_definition(raw: dict[str, Any]) -> UDTDefinition:
    return UDTDefinition(
        name=str(raw["name"]),
        fields=tuple(_field_definition(field) for field in raw.get("fields", [])),
    )


def _tag_definition(
    raw: dict[str, Any], default_program: str | None = None
) -> TagDefinition:
    return TagDefinition(
        name=str(raw["name"]),
        fully_qualified_name=str(raw.get("fully_qualified_name", raw["name"])),
        tag_type=raw.get("tag_type"),
        data_type_name=raw.get("data_type_name"),
        dimensions=tuple(int(value) for value in raw.get("dimensions", [])),
        array_dimensions=int(raw.get("array_dimensions") or 0),
        udt_name=raw.get("udt_name"),
        program=raw.get("program", default_program),
        value=raw.get("value"),
    )


def load_plc_metadata(
    root: str | Path,
    controller_tags_root: str | Path | None = None,
) -> PlcMetadata:
    metadata_root = Path(root)
    tags_root = (
        Path(controller_tags_root)
        if controller_tags_root is not None
        else metadata_root
    )
    controller_tags_path = tags_root / "controller_level_tags.json"

    if not controller_tags_path.exists():
        if controller_tags_root is None:
            candidate_controller_tags_path = PLC_ROOT / "controller_level_tags.json"
            if candidate_controller_tags_path.exists():
                metadata_root = PLC_ROOT
                tags_root = PLC_ROOT
                controller_tags_path = candidate_controller_tags_path

    if not controller_tags_path.exists():
        searched = [str(tags_root)]
        if controller_tags_root is None and str(PLC_ROOT) not in searched:
            searched.append(str(PLC_ROOT))
        raise FileNotFoundError(
            "controller_level_tags.json not found. Looked in: " + ", ".join(searched)
        )

    controller_payload = json.loads(controller_tags_path.read_text(encoding="utf-8"))

    udts = {
        udt.name: udt
        for udt in (_udt_definition(raw) for raw in controller_payload.get("udts", []))
    }

    controller_tags = {
        tag.name: tag
        for tag in (
            _tag_definition(raw)
            for raw in controller_payload.get("controller_level_tags", [])
        )
    }

    programs: dict[str, ProgramMetadata] = {}
    for program_path in sorted(metadata_root.glob("*/programTags.json")):
        payload = json.loads(program_path.read_text(encoding="utf-8"))
        program_name = str(payload["program_name"])

        for raw_udt in payload.get("udts", []):
            udt = _udt_definition(raw_udt)
            udts.setdefault(udt.name, udt)

        tags = {
            tag.name: tag
            for tag in (
                _tag_definition(raw, default_program=program_name)
                for raw in payload.get("program_tags", [])
            )
        }
        programs[program_name] = ProgramMetadata(
            name=program_name,
            main_routine_name=payload.get("main_routine_name"),
            routines=tuple(str(name) for name in payload.get("routines", [])),
            subroutines=tuple(str(name) for name in payload.get("subroutines", [])),
            tags=tags,
        )

    for alias, target in PROGRAM_ALIASES.items():
        if alias not in programs and target in programs:
            target_program = programs[target]
            programs[alias] = ProgramMetadata(
                name=alias,
                main_routine_name=target_program.main_routine_name,
                routines=target_program.routines,
                subroutines=target_program.subroutines,
                tags=target_program.tags,
            )

    return PlcMetadata(
        root=metadata_root,
        controller_tags=controller_tags,
        programs=programs,
        udts=udts,
    )
