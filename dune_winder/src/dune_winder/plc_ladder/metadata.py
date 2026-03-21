from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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

  def get_tag_definition(self, name: str, program: str | None = None) -> TagDefinition | None:
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


def _tag_definition(raw: dict[str, Any], default_program: str | None = None) -> TagDefinition:
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


def load_plc_metadata(root: str | Path) -> PlcMetadata:
  metadata_root = Path(root)
  controller_payload = json.loads(
    (metadata_root / "controller_level_tags.json").read_text(encoding="utf-8")
  )

  udts = {
    udt.name: udt
    for udt in (
      _udt_definition(raw)
      for raw in controller_payload.get("udts", [])
    )
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

  return PlcMetadata(
    root=metadata_root,
    controller_tags=controller_tags,
    programs=programs,
    udts=udts,
  )
