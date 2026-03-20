import tempfile
import unittest
from pathlib import Path

from convert_plc_rllscrap import DEFAULT_ROUTINE_DIR
from convert_plc_rllscrap import build_argument_parser
from convert_plc_rllscrap import convert_directory
from convert_plc_rllscrap import iter_rllscrap_files


class ConvertPlcRllscrapTests(unittest.TestCase):
  def test_default_argument_points_to_repo_root_plc_routines(self):
    parser = build_argument_parser()

    args = parser.parse_args([])

    self.assertEqual(args.routine_dir, DEFAULT_ROUTINE_DIR)
    self.assertEqual(args.routine_dir.name, "plc_routines")

  def test_iter_rllscrap_files_discovers_recursive_studio_copy_files_only(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      target = root / "mainRoutine" / "studio_copy.rllscrap"
      ignored = root / "mainRoutine" / "other_name.rllscrap"
      target.parent.mkdir(parents=True)
      target.write_text("[XIC A,XIC B];")
      ignored.write_text("[XIC C,XIC D];")

      results = list(iter_rllscrap_files(root))

      self.assertEqual(results, [target])

  def test_convert_directory_writes_pasteable_output_next_to_studio_copy(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      routine_dir = root / "mainRoutine"
      input_path = routine_dir / "studio_copy.rllscrap"
      output_path = routine_dir / "pasteable.rll"
      routine_dir.mkdir(parents=True)
      input_path.write_text("[XIC A,XIC B];")

      converted = convert_directory(root)

      self.assertEqual(converted, 1)
      self.assertEqual(output_path.read_text(), "BST XIC A NXB XIC B BND \n")
