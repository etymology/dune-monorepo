import unittest

from dune_winder.library.RecipeTemplateLanguage import (
  RecipeTemplateLanguageError,
  compile_template_script,
  execute_template_script,
  render_template_text,
)


def _line_builder(*parts):
  return " ".join(part for part in parts if part)


class RecipeTemplateLanguageTests(unittest.TestCase):
  def test_render_template_text_interpolates_and_normalizes_whitespace(self):
    rendered = render_template_text(
      "G109 PB${1200 + wrap} ${optional} PXY",
      {"wrap": 3, "optional": None},
    )
    self.assertEqual(rendered, "G109 PB1203 PXY")

  def test_execute_template_script_emits_conditionals_and_transitions(self):
    script = compile_template_script(
      (
        "# comment",
        "emit START ${value}",
        "if is_enabled: emit ENABLED",
        "if is_enabled: transition to_end",
      )
    )

    lines = []

    execute_template_script(
      script,
      environment={"value": 5, "is_enabled": True},
      output_lines=lines,
      line_builder=_line_builder,
      transitions={"to_end": lambda output: output.append("TRANSITION")},
    )

    self.assertEqual(lines, ["START 5", "ENABLED", "TRANSITION"])

  def test_execute_template_script_supports_emit_head_restart(self):
    script = compile_template_script(
      (
        "emit X100",
        "emit_head_restart X200",
      )
    )

    lines = []

    execute_template_script(
      script,
      environment={},
      output_lines=lines,
      line_builder=_line_builder,
      transitions={},
      emit_callback=lambda output, line, action: output.append((line, action)),
    )

    self.assertEqual(
      lines,
      [("X100", "emit"), ("X200", "emit_head_restart")],
    )

  def test_compile_template_script_rejects_unknown_statements(self):
    with self.assertRaises(RecipeTemplateLanguageError):
      compile_template_script(("bogus instruction",))


if __name__ == "__main__":
  unittest.main()
