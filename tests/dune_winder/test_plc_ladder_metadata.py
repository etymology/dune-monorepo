import unittest

from dune_winder.plc_ladder import TagStore
from dune_winder.plc_ladder import load_plc_metadata
from dune_winder.paths import PLC_ROOT


class PlcLadderMetadataTests(unittest.TestCase):
    def test_loads_controller_program_tags_and_udts(self):
        metadata = load_plc_metadata(PLC_ROOT)

        self.assertIn("STATE", metadata.controller_tags)
        self.assertIn("state_3_move_xy", metadata.programs)
        self.assertIn("MOTION_INSTRUCTION", metadata.udts)

    def test_tag_store_seeds_controller_and_program_values(self):
        metadata = load_plc_metadata(PLC_ROOT)
        tags = TagStore(metadata)

        self.assertEqual(tags.get("STATE"), 0)
        self.assertEqual(tags.get("QueueCtl.POS", program="queued_motion"), 0)
        self.assertEqual(tags.get("CurSeg.Valid", program="queued_motion"), False)

        tags.set("QueueCtl.POS", 7, program="queued_motion")
        tags.set("CurSeg.Valid", True, program="queued_motion")
        tags.set("z_axis_main_move.PC", True, program="state_5_move_z")

        self.assertEqual(tags.get("QueueCtl.POS", program="queued_motion"), 7)
        self.assertEqual(tags.get("CurSeg.Valid", program="queued_motion"), True)
        self.assertEqual(
            tags.get("z_axis_main_move.PC", program="state_5_move_z"), True
        )

    def test_program_tags_shadow_controller_tags(self):
        metadata = load_plc_metadata(PLC_ROOT)
        tags = TagStore(metadata)

        self.assertTrue(tags.exists("QueueCtl", program="queued_motion"))
        self.assertTrue(tags.exists("STATE"))
        self.assertFalse(tags.exists("QueueCtl"))


if __name__ == "__main__":
    unittest.main()
