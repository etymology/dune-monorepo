from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from dune_winder.plc_ladder import RllEmitter
from dune_winder.plc_ladder.branch_simplifier import iter_pasteable_files
from dune_winder.plc_ladder.branch_simplifier import simplify_file
from dune_winder.plc_ladder.branch_simplifier import simplify_text


class PlcBranchSimplifierTests(unittest.TestCase):
  def setUp(self):
    self.emitter = RllEmitter()

  def test_expands_condition_only_branch_with_duplicate_safe_suffix(self):
    result = simplify_text(
      "CMP STATE=3 BST XIO Z_RETRACTED NXB GEQ Z_axis.ActualPosition MAX_TOLERABLE_Z BND CPT ERROR_CODE 3001 CPT NEXTSTATE 10 \n",
      routine_name="main",
      program="MoveXY_State_2_3",
    )

    self.assertTrue(result.changed)
    self.assertEqual(result.issues, ())
    self.assertEqual(
      self.emitter.emit_routine(result.routine),
      (
        "CMP STATE=3 XIO Z_RETRACTED CPT ERROR_CODE 3001 CPT NEXTSTATE 10 \n"
        "CMP STATE=3 GEQ Z_axis.ActualPosition MAX_TOLERABLE_Z CPT ERROR_CODE 3001 CPT NEXTSTATE 10 \n"
      ),
    )

  def test_expands_nested_condition_only_branches(self):
    result = simplify_text(
      "XIC trigger BST XIC A NXB BST XIC B NXB XIC C BND BND OTL done \n",
      routine_name="main",
    )

    self.assertTrue(result.changed)
    self.assertEqual(result.issues, ())
    self.assertEqual(
      self.emitter.emit_routine(result.routine),
      (
        "XIC trigger XIC A OTL done \n"
        "XIC trigger XIC B OTL done \n"
        "XIC trigger XIC C OTL done \n"
      ),
    )

  def test_flags_rungs_with_ote_suffix(self):
    result = simplify_text(
      "BST XIC A NXB XIC B BND OTE output_bit \n",
      routine_name="main",
    )

    self.assertFalse(result.changed)
    self.assertEqual(len(result.issues), 1)
    self.assertIn("OTE", result.issues[0].reason)
    self.assertEqual(
      self.emitter.emit_routine(result.routine),
      "BST XIC A NXB XIC B BND OTE output_bit \n",
    )

  def test_flags_branch_paths_with_side_effects(self):
    result = simplify_text(
      "XIC trigger BST XIC A MOV 1 target NXB XIC B BND OTL done \n",
      routine_name="main",
    )

    self.assertFalse(result.changed)
    self.assertEqual(len(result.issues), 1)
    self.assertIn("side-effect opcode MOV", result.issues[0].reason)

  def test_flags_read_write_overlap(self):
    result = simplify_text(
      "XIC trigger BST XIC A NXB XIC B BND CPT count count+1 \n",
      routine_name="main",
    )

    self.assertFalse(result.changed)
    self.assertEqual(len(result.issues), 1)
    self.assertIn("count", result.issues[0].reason)

  def test_simplify_file_rewrites_only_when_requested(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
      path = Path(tmp_dir) / "ExampleProgram" / "main" / "pasteable.rll"
      path.parent.mkdir(parents=True)
      path.write_text(
        "CMP STATE=3 BST XIO Z_RETRACTED NXB GEQ Z_axis.ActualPosition MAX_TOLERABLE_Z BND CPT ERROR_CODE 3001 CPT NEXTSTATE 10 \n",
        encoding="utf-8",
      )

      dry_run_report = simplify_file(path, write_changes=False)
      self.assertTrue(dry_run_report.changed)
      self.assertIn("BST", path.read_text(encoding="utf-8"))

      apply_report = simplify_file(path, write_changes=True)
      self.assertTrue(apply_report.changed)
      self.assertNotIn("BST", path.read_text(encoding="utf-8"))

  def test_iter_pasteable_files_discovers_recursive_targets_only(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
      root = Path(tmp_dir)
      target = root / "ExampleProgram" / "main" / "pasteable.rll"
      ignored = root / "ExampleProgram" / "main" / "other.rll"
      target.parent.mkdir(parents=True)
      target.write_text("", encoding="utf-8")
      ignored.write_text("", encoding="utf-8")

      self.assertEqual(list(iter_pasteable_files(root)), [target])


if __name__ == "__main__":
  unittest.main()
