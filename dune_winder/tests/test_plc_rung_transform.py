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

  def test_transform_text_leaves_numeric_bracket_lists_unchanged(self):
    source = "Values[1,2,3];[XIC A,XIC B]"

    result = transform_text(source)

    self.assertEqual(result, "Values[1 2 3]\nBST XIC A NXB XIC B BND ")

  def test_transform_text_converts_non_numeric_bracket_lists(self):
    source = "[Alpha,Beta,Gamma]"

    result = transform_text(source)

    self.assertEqual(result, "BST Alpha NXB Beta NXB Gamma BND ")

  def test_transform_text_applies_bracketed_condition_rewrite_before_flattening(self):
    source = "Prefix [XIC CurIssued,XIO QueueFault] Suffix"

    result = transform_text(source)

    self.assertEqual(result, "Prefix BST XIC CurIssued NXB XIO QueueFault BND Suffix")

  def test_transform_text_converts_function_style_conditions_inside_brackets(self):
    source = (
      "   XIC(QueueStopRequest)[XIC(CurIssued),XIC(NextIssued),"
      "XIC(X_Y.MovePendingStatus)]ONS(QueueStopReqONS)"
    )

    result = transform_text(source)

    self.assertEqual(
      result,
      "XIC QueueStopRequest BST XIC CurIssued NXB XIC NextIssued "
      "NXB XIC X_Y.MovePendingStatus BND ONS QueueStopReqONS ",
    )

  def test_transform_text_splits_bracket_lists_only_on_top_level_commas(self):
    source = "[EQU(CurSeg.SegType,1),EQU(CurSeg.SegType,2)]"

    result = transform_text(source)

    self.assertEqual(
      result,
      "BST EQU CurSeg.SegType 1 NXB EQU CurSeg.SegType 2 BND ",
    )

  def test_transform_text_supports_nested_bracketed_conditions(self):
    source = (
      "[[XIO(Z_RETRACTED),GEQ(Z_axis.ActualPosition,MAX_TOLERABLE_Z)]"
      "CPT(ERROR_CODE,3001),XIC(Z_RETRACTED)]NOP"
    )

    result = transform_text(source)

    self.assertEqual(
      result,
      "BST BST XIO Z_RETRACTED NXB GEQ Z_axis.ActualPosition MAX_TOLERABLE_Z "
      "BND CPT ERROR_CODE 3001 NXB XIC Z_RETRACTED BND NOP",
    )

  def test_transform_file_writes_output_file(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      input_path = Path(temp_dir) / "input.txt"
      output_path = Path(temp_dir) / "output.txt"
      input_path.write_text("[XIC A,XIC B];")

      transform_file(input_path, output_path)

      self.assertEqual(output_path.read_text(), "BST XIC A NXB XIC B BND \n")
