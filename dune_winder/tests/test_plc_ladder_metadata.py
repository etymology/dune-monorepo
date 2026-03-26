from pathlib import Path
import unittest

from dune_winder.plc_ladder import TagStore
from dune_winder.plc_ladder import load_plc_metadata


PLC_ROOT = Path(__file__).resolve().parents[1] / "plc"


class PlcLadderMetadataTests(unittest.TestCase):
  def test_loads_controller_program_tags_and_udts(self):
    metadata = load_plc_metadata(PLC_ROOT)

    self.assertIn("STATE", metadata.controller_tags)
    self.assertIn("MoveXY_State_2_3", metadata.programs)
    self.assertIn("MOTION_INSTRUCTION", metadata.udts)

  def test_program_tags_shadow_controller_tags(self):
    metadata = load_plc_metadata(PLC_ROOT)
    tags = TagStore(metadata)

    self.assertTrue(tags.exists("QueueCtl", program="motionQueue"))
    self.assertTrue(tags.exists("STATE"))
    self.assertFalse(tags.exists("QueueCtl"))


if __name__ == "__main__":
  unittest.main()
