import tempfile
import unittest
from pathlib import Path

from dune_winder.plc_rung_transform import transform_file
from dune_winder.plc_rung_transform import transform_text


class PlcRungTransformTests(unittest.TestCase):
  def test_transform_text_converts_bracketed_conditions_and_normalizes_spacing(self):
    source = "   [XIC QueueFault,XIC MoveA.ER ,XIC MoveB.ER ];  XIC (SomeTag,OtherTag)"

    result = transform_text(source)

    self.assertEqual(
      result,
      "BST XIC QueueFault NXB XIC MoveA.ER NXB XIC MoveB.ER BND \n"
      "XIC SomeTag OtherTag ",
    )

  def test_transform_text_quotes_command_arguments_that_contain_spaces(self):
    source = "MCS(X_Y,gui_stop,All,Yes,2000,Units per sec2,Yes,1000,Units per sec3)"

    result = transform_text(source)

    self.assertEqual(
      result,
      'MCS X_Y gui_stop All Yes 2000 "Units per sec2" Yes 1000 "Units per sec3" ',
    )

  def test_transform_file_writes_output_file(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      input_path = Path(temp_dir) / "input.txt"
      output_path = Path(temp_dir) / "output.txt"
      input_path.write_text("[XIC A,XIC B];")

      transform_file(input_path, output_path)

      self.assertEqual(output_path.read_text(), "BST XIC A NXB XIC B BND \n")
