import tempfile
import unittest
from pathlib import Path

from dune_winder.plc_tag_values_export import apply_tag_values_to_payload
from dune_winder.plc_tag_values_export import iter_plc_json_files
from dune_winder.plc_tag_values_export import make_json_safe


class PlcTagValuesExportTests(unittest.TestCase):
  def test_make_json_safe_converts_nested_values(self):
    safe = make_json_safe({
      "enabled": True,
      "buffer": bytearray([1, 2, 3]),
      "nested": {"items": (1, 2.5, "x")},
    })

    self.assertEqual(safe["buffer"], [1, 2, 3])
    self.assertEqual(safe["nested"]["items"], [1, 2.5, "x"])

  def test_apply_tag_values_to_controller_payload_adds_value_fields(self):
    payload = {
      "controller_level_tags": [
        {
          "name": "TagA",
          "fully_qualified_name": "TagA",
        },
        {
          "name": "TagB",
          "fully_qualified_name": "TagB",
        },
      ]
    }

    updated = apply_tag_values_to_payload(
      payload,
      {
        "TagA": (123, None),
        "TagB": (None, "TagB: read failed"),
      },
      "2026-03-20T00:00:00+00:00",
    )

    self.assertEqual(updated["values_generated_at"], "2026-03-20T00:00:00+00:00")
    self.assertEqual(updated["controller_level_tags"][0]["value"], 123)
    self.assertNotIn("read_error", updated["controller_level_tags"][0])
    self.assertIsNone(updated["controller_level_tags"][1]["value"])
    self.assertEqual(
      updated["controller_level_tags"][1]["read_error"],
      "TagB: read failed",
    )

  def test_iter_plc_json_files_finds_controller_and_program_files(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir) / "plc"
      root.mkdir()
      (root / "controller_level_tags.json").write_text("{}")
      (root / "Camera").mkdir()
      (root / "Camera" / "programTags.json").write_text("{}")
      (root / "IgnoreMe").mkdir()
      (root / "IgnoreMe" / "not_program_tags.json").write_text("{}")

      files = iter_plc_json_files(root)

      self.assertEqual(
        files,
        [
          root / "controller_level_tags.json",
          root / "Camera" / "programTags.json",
        ],
      )
