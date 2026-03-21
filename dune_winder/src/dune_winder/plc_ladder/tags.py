from __future__ import annotations

import copy
import re
from dataclasses import dataclass

from .metadata import PlcMetadata
from .metadata import TagDefinition
from .metadata import UDTDefinition
from .types import default_atomic_value
from .types import make_struct_instance


_INDEX_PATTERN = re.compile(r"\[([^\]]+)\]")


@dataclass(frozen=True)
class PathSegment:
  name: str
  indexes: tuple[int | str, ...] = ()


def split_tag_path(path: str) -> tuple[PathSegment, ...]:
  segments = []
  current = []
  bracket_depth = 0

  for character in str(path):
    if character == "." and bracket_depth == 0:
      segments.append("".join(current))
      current = []
      continue
    if character == "[":
      bracket_depth += 1
    elif character == "]" and bracket_depth > 0:
      bracket_depth -= 1
    current.append(character)

  if current:
    segments.append("".join(current))

  parsed = []
  for segment in segments:
    name = segment.split("[", 1)[0]
    indexes = []
    for raw_index in _INDEX_PATTERN.findall(segment):
      text = raw_index.strip()
      indexes.append(int(text) if text.isdigit() else text)
    parsed.append(PathSegment(name=name, indexes=tuple(indexes)))

  return tuple(parsed)


class TagStore:
  def __init__(self, metadata: PlcMetadata, use_exported_values: bool = False):
    self.metadata = metadata
    self.use_exported_values = bool(use_exported_values)
    self._controller_tags = {
      name: self._seed_tag_value(definition)
      for name, definition in metadata.controller_tags.items()
    }
    self._program_tags = {
      program.name: {
        name: self._seed_tag_value(definition)
        for name, definition in program.tags.items()
      }
      for program in metadata.programs.values()
    }

  def exists(self, path: str, program: str | None = None) -> bool:
    try:
      self.get(path, program=program)
    except KeyError:
      return False
    return True

  def get(self, path: str, program: str | None = None):
    segments = split_tag_path(path)
    if not segments:
      raise KeyError(path)

    value = self._root_value(segments[0].name, program=program)
    value = self._apply_indexes(value, segments[0].indexes)

    for segment in segments[1:]:
      if not isinstance(value, dict):
        raise KeyError(path)
      value = value[segment.name]
      value = self._apply_indexes(value, segment.indexes)

    return value

  def set(self, path: str, value, program: str | None = None):
    segments = split_tag_path(path)
    if not segments:
      raise KeyError(path)

    root_container = self._root_container(segments[0].name, program=program)
    current = root_container[segments[0].name]

    if len(segments) == 1:
      root_container[segments[0].name] = self._set_with_indexes(
        current,
        segments[0].indexes,
        value,
      )
      return value

    current = self._apply_indexes(current, segments[0].indexes)
    for segment in segments[1:-1]:
      if not isinstance(current, dict):
        raise KeyError(path)
      current = current[segment.name]
      current = self._apply_indexes(current, segment.indexes)

    final_segment = segments[-1]
    if not isinstance(current, dict):
      raise KeyError(path)
    current[final_segment.name] = self._set_with_indexes(
      current[final_segment.name],
      final_segment.indexes,
      value,
    )
    return value

  def snapshot(self, program: str | None = None) -> dict[str, object]:
    if program is None:
      return copy.deepcopy(self._controller_tags)
    combined = copy.deepcopy(self._controller_tags)
    combined.update(copy.deepcopy(self._program_tags.get(str(program), {})))
    return combined

  def _root_container(self, name: str, program: str | None = None):
    if program is not None and name in self._program_tags.get(str(program), {}):
      return self._program_tags[str(program)]
    if name in self._controller_tags:
      return self._controller_tags
    raise KeyError(name)

  def _root_value(self, name: str, program: str | None = None):
    if program is not None:
      program_values = self._program_tags.get(str(program), {})
      if name in program_values:
        return program_values[name]
    if name in self._controller_tags:
      return self._controller_tags[name]
    raise KeyError(name)

  def _apply_indexes(self, value, indexes: tuple[int | str, ...]):
    current = value
    for index in indexes:
      if not isinstance(index, int):
        raise KeyError(index)
      if isinstance(current, list):
        current = current[index]
        continue
      current = bool((int(current) >> index) & 1)
    return current

  def _set_with_indexes(self, value, indexes: tuple[int | str, ...], new_value):
    if not indexes:
      return copy.deepcopy(new_value)

    current = value
    for index in indexes[:-1]:
      if not isinstance(index, int):
        raise KeyError(index)
      if isinstance(current, list):
        current = current[index]
        continue
      current = bool((int(current) >> index) & 1)
    final_index = indexes[-1]
    if not isinstance(final_index, int):
      raise KeyError(final_index)
    if isinstance(current, list):
      current[final_index] = copy.deepcopy(new_value)
      return value

    bit_value = 1 if bool(new_value) else 0
    raw_value = int(value)
    if bit_value:
      return raw_value | (1 << final_index)
    return raw_value & ~(1 << final_index)
    return value

  def _seed_tag_value(self, definition: TagDefinition):
    if definition.tag_type == "struct" and definition.udt_name is not None:
      value = self._seed_udt_value(self.metadata.udts[definition.udt_name])
    else:
      value = default_atomic_value(definition.data_type_name)

    if self.use_exported_values and definition.value is not None:
      exported = copy.deepcopy(definition.value)
      if definition.array_dimensions > 0 and definition.dimensions:
        length = int(definition.dimensions[0] or 0)
        if definition.data_type_name == "DWORD" and length == 1:
          return int(bool(exported)) if isinstance(exported, bool) else copy.deepcopy(exported)
        if isinstance(exported, list):
          if len(exported) >= length:
            return exported[:length]
          padded = list(exported)
          padded.extend(copy.deepcopy(value) for _ in range(length - len(padded)))
          return padded
        return [copy.deepcopy(exported) for _ in range(length)]
      return exported

    if definition.array_dimensions > 0 and definition.dimensions:
      length = int(definition.dimensions[0] or 0)
      if definition.data_type_name == "DWORD" and length == 1:
        return copy.deepcopy(value)
      return [copy.deepcopy(value) for _ in range(length)]

    return value

  def _seed_udt_value(self, udt: UDTDefinition):
    fields = {}
    for field in udt.fields:
      if field.data_type_name in self.metadata.udts:
        field_value = self._seed_udt_value(self.metadata.udts[field.data_type_name])
      else:
        field_value = default_atomic_value(field.data_type_name)
      if field.array_length:
        field_value = [copy.deepcopy(field_value) for _ in range(field.array_length)]
      fields[field.name] = field_value
    return make_struct_instance(udt.name, fields)
