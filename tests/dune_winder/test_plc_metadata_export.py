import json
import tempfile
import unittest
from pathlib import Path

from dune_winder.plc_metadata_export import infer_main_routine
from dune_winder.plc_metadata_export import normalize_tag_definition
from dune_winder.plc_metadata_export import split_controller_and_program_tags
from dune_winder.plc_metadata_export import write_plc_snapshot


class PlcMetadataExportTests(unittest.TestCase):
  def test_infer_main_routine_prefers_program_name_match(self):
    routine_name, source = infer_main_routine(
      "enqueueRoutine",
      ["CapSegSpeed", "enqueueRoutine"],
    )

    self.assertEqual(routine_name, "enqueueRoutine")
    self.assertEqual(source, "name_match")

  def test_infer_main_routine_returns_none_when_unresolved(self):
    routine_name, source = infer_main_routine(
      "queueProgram",
      ["CapSegSpeed", "CircleCenterForSeg"],
    )

    self.assertIsNone(routine_name)
    self.assertEqual(source, "unresolved")

  def test_split_controller_and_program_tags_separates_program_scoped_tags(self):
    controller_tags, program_tags = split_controller_and_program_tags([
      {"tag_name": "ControllerTag"},
      {"tag_name": "Program:QueueProgram.LocalTag"},
    ])

    self.assertEqual([tag["tag_name"] for tag in controller_tags], ["ControllerTag"])
    self.assertEqual(
      [tag["tag_name"] for tag in program_tags["QueueProgram"]],
      ["Program:QueueProgram.LocalTag"],
    )

  def test_normalize_tag_definition_strips_program_prefix_from_local_name(self):
    normalized = normalize_tag_definition({
      "tag_name": "Program:QueueProgram.LocalTag",
      "tag_type": "atomic",
      "data_type_name": "DINT",
      "alias": False,
      "external_access": "Read/Write",
      "dimensions": [0, 0, 0],
      "dim": 0,
    })

    self.assertEqual(normalized["name"], "LocalTag")
    self.assertEqual(normalized["program"], "QueueProgram")
    self.assertEqual(normalized["data_type_name"], "DINT")

  def test_write_plc_snapshot_creates_requested_plc_tree(self):
    snapshot = {
      "schema_version": 1,
      "generated_at": "2026-03-20T00:00:00+00:00",
      "plc_path": "192.168.1.10",
      "controller": {"product_name": "TestPLC"},
      "controller_level_tags": [
        {"name": "ControllerTag", "data_type_name": "BOOL", "tag_type": "atomic"}
      ],
      "controller_udts": [],
      "programs": {
        "enqueueRoutine": {
          "program_name": "enqueueRoutine",
          "main_routine_name": "enqueueRoutine",
          "main_routine_name_source": "name_match",
          "routines": ["enqueueRoutine", "CapSegSpeed"],
          "subroutines": ["CapSegSpeed"],
          "program_tags": [
            {
              "name": "QueueCount",
              "program": "enqueueRoutine",
              "data_type_name": "DINT",
              "tag_type": "atomic",
            }
          ],
          "udts": [],
        }
      },
    }

    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir) / "plc"

      write_plc_snapshot(snapshot, root)

      controller_path = root / "controller_level_tags.json"
      program_tags_path = root / "enqueueRoutine" / "programTags.json"
      main_rllscrap_path = root / "enqueueRoutine" / "main" / "studio_copy.rllscrap"
      subroutine_rllscrap_path = (
        root / "enqueueRoutine" / "CapSegSpeed" / "studio_copy.rllscrap"
      )

      self.assertTrue(controller_path.exists())
      self.assertTrue(program_tags_path.exists())
      self.assertTrue(main_rllscrap_path.exists())
      self.assertTrue(subroutine_rllscrap_path.exists())
      self.assertEqual(main_rllscrap_path.read_text(), "")
      self.assertEqual(subroutine_rllscrap_path.read_text(), "")

      controller_payload = json.loads(controller_path.read_text())
      self.assertEqual(controller_payload["controller_level_tags"][0]["name"], "ControllerTag")

      program_payload = json.loads(program_tags_path.read_text())
      self.assertEqual(program_payload["program_name"], "enqueueRoutine")
      self.assertEqual(program_payload["subroutines"], ["CapSegSpeed"])
