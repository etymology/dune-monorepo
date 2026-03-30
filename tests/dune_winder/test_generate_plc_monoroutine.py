from __future__ import annotations

import unittest

from dune_winder.generate_plc_monoroutine import _build_monoroutine
from dune_winder.generate_plc_monoroutine import _build_program_tag_maps
from dune_winder.generate_plc_monoroutine import _generate_program_tags_payload
from dune_winder.generate_plc_monoroutine import _load_program_payload
from dune_winder.generate_plc_monoroutine import PROGRAM_ORDER
from dune_winder.plc_ladder import RllEmitter
from dune_winder.plc_ladder import RllParser


class GeneratePlcMonoroutineTests(unittest.TestCase):
  def test_generated_monoroutine_contains_no_jsr_and_unique_program_tags(self):
    parser = RllParser()
    program_payloads = {
      program_name: _load_program_payload(program_name)
      for program_name in PROGRAM_ORDER
    }
    rename_maps, _rename_only = _build_program_tag_maps(program_payloads)

    monoroutine = _build_monoroutine(parser, rename_maps)
    rendered = RllEmitter().emit_routine(monoroutine)

    self.assertNotIn("JSR ", rendered)
    parser.parse_routine_text("main", rendered, program="Monoroutine")

    tag_payload = _generate_program_tags_payload(program_payloads, rename_maps, rendered)
    names = [tag["name"] for tag in tag_payload["program_tags"]]
    self.assertEqual(len(names), len(set(names)))

    dimensions_by_name = {
      tag["name"]: tag.get("dimensions", [0, 0, 0])[0]
      for tag in tag_payload["program_tags"]
    }
    self.assertEqual(dimensions_by_name["INIT_Z_AXIS_STAT"], 1)
    self.assertEqual(dimensions_by_name["XY_AXIS_STAT"], 7)
    self.assertEqual(dimensions_by_name["US9_X_AXIS_STAT"], 2)
    self.assertEqual(dimensions_by_name["US9_Y_AXIS_STAT"], 2)
    self.assertEqual(dimensions_by_name["US9_Z_AXIS_STAT"], 2)
    self.assertEqual(dimensions_by_name["ERR10_X_AXIS_STAT"], 3)
    self.assertEqual(dimensions_by_name["ERR10_Y_AXIS_STAT"], 3)
    self.assertEqual(dimensions_by_name["ERR10_Z_AXIS_STAT"], 3)


if __name__ == "__main__":
  unittest.main()
