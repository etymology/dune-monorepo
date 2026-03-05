###############################################################################
# Name: RecipeTemplateLanguage.py
# Uses: Shared mini-language runtime for template G-Code generation.
# Date: 2026-03-05
###############################################################################

from __future__ import annotations

import re
from dataclasses import dataclass


class RecipeTemplateLanguageError(ValueError):
  pass


@dataclass(frozen=True)
class TemplateInstruction:
  action: str
  value: str
  condition: str | None = None


_INTERPOLATION_RE = re.compile(r"\$\{([^{}]+)\}")
_CONDITIONAL_RE = re.compile(
  r"^if\s+(.+?):\s*(emit|emit_head_restart|transition)\s+(.+)$"
)

_SAFE_EVAL_GLOBALS = {
  "__builtins__": {},
  "abs": abs,
  "int": int,
  "float": float,
  "max": max,
  "min": min,
  "round": round,
}


def compile_template_script(script_lines):
  instructions = []
  for line_number, raw_line in enumerate(script_lines, start=1):
    line = str(raw_line).strip()
    if not line or line.startswith("#"):
      continue

    conditional = _CONDITIONAL_RE.match(line)
    if conditional:
      instructions.append(
        TemplateInstruction(
          action=conditional.group(2),
          value=conditional.group(3).strip(),
          condition=conditional.group(1).strip(),
        )
      )
      continue

    if line.startswith("emit_head_restart "):
      instructions.append(
        TemplateInstruction(action="emit_head_restart", value=line[18:].strip())
      )
      continue

    if line.startswith("emit "):
      instructions.append(TemplateInstruction(action="emit", value=line[5:].strip()))
      continue

    if line.startswith("transition "):
      instructions.append(
        TemplateInstruction(action="transition", value=line[11:].strip())
      )
      continue

    raise RecipeTemplateLanguageError(
      "Invalid template statement at line "
      + str(line_number)
      + ": "
      + repr(raw_line)
    )

  return tuple(instructions)


def _evaluate_expression(expression, environment):
  try:
    return eval(expression, _SAFE_EVAL_GLOBALS, environment)
  except Exception as exception:
    raise RecipeTemplateLanguageError(
      "Failed to evaluate expression: " + repr(expression)
    ) from exception


def render_template_text(template_text, environment):
  def replace(match):
    value = _evaluate_expression(match.group(1), environment)
    if value is None:
      return ""
    return str(value)

  return " ".join(_INTERPOLATION_RE.sub(replace, str(template_text)).split())


def execute_template_script(
  instructions,
  *,
  environment,
  output_lines,
  line_builder,
  transitions,
  emit_callback=None,
):
  for instruction in instructions:
    if instruction.condition is not None:
      condition_value = _evaluate_expression(instruction.condition, environment)
      if not bool(condition_value):
        continue

    if instruction.action in ("emit", "emit_head_restart"):
      rendered = render_template_text(instruction.value, environment)
      line = line_builder(*rendered.split(" "))
      if emit_callback is None:
        output_lines.append(line)
      else:
        emit_callback(output_lines, line, instruction.action)
      continue

    if instruction.action == "transition":
      if instruction.value not in transitions:
        raise RecipeTemplateLanguageError(
          "Unknown transition action: " + repr(instruction.value)
        )
      transitions[instruction.value](output_lines)
      continue

    raise RecipeTemplateLanguageError(
      "Unsupported template action: " + repr(instruction.action)
    )
