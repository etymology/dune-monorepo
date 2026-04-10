from __future__ import annotations

import unittest

from dune_winder.paths import PLC_ROOT
from dune_winder.sync_monoroutine_tag_values import _program_scoped_fqn
from dune_winder.sync_monoroutine_tag_values import _resolve_monoroutine_sources


class SyncMonoroutineTagValuesTests(unittest.TestCase):
  def test_program_scoped_fqn_uses_target_program_name(self):
    self.assertEqual(
      _program_scoped_fqn("monoprogram", "Z_RETRACTED_1A"),
      "Program:monoprogram.Z_RETRACTED_1A",
    )

  def test_monoroutine_source_resolution_is_unambiguous_for_current_export(self):
    resolutions, context = _resolve_monoroutine_sources(PLC_ROOT)

    self.assertEqual(context["summary"]["ambiguous"], 0)
    self.assertEqual(context["summary"]["unmatched"], 0)

    by_name = {entry["monoroutine_tag"]: entry for entry in resolutions}

    self.assertEqual(by_name["Z_RETRACTED_1A"]["status"], "matched")
    self.assertEqual(by_name["Z_RETRACTED_1A"]["source_program"], "MainProgram")
    self.assertEqual(by_name["Z_RETRACTED_1A"]["source_tag"], "Z_RETRACTED_1A")

    self.assertEqual(by_name["MQ_IssueNextPulse"]["status"], "matched")
    self.assertEqual(by_name["MQ_IssueNextPulse"]["source_program"], "motionQueue")
    self.assertEqual(by_name["MQ_IssueNextPulse"]["source_tag"], "IssueNextPulse")


if __name__ == "__main__":
  unittest.main()
