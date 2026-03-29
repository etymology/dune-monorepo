from pathlib import Path
import json
import re
import unittest

from dune_winder.plc_ladder.parser import OPERAND_COUNTS


REPO_ROOT = Path(__file__).resolve().parents[1]
EXTENSION_ROOT = REPO_ROOT / "tools" / "vscode-plc-rll"


class VSCodeRllSyntaxTests(unittest.TestCase):
  def test_extension_declares_plc_rll_language(self):
    package = json.loads((EXTENSION_ROOT / "package.json").read_text(encoding="utf-8"))

    self.assertEqual(package["name"], "dune-winder-plc-rll")
    self.assertEqual(package["contributes"]["languages"][0]["id"], "plc-rll")
    self.assertIn(".rll", package["contributes"]["languages"][0]["extensions"])

  def test_grammar_covers_all_supported_parser_opcodes(self):
    grammar = json.loads(
      (EXTENSION_ROOT / "syntaxes" / "plc-rll.tmGrammar.json").read_text(encoding="utf-8")
    )

    opcode_patterns = [
      pattern["match"]
      for group_name in ("branchOpcodes", "instructions")
      for pattern in grammar["repository"][group_name]["patterns"]
    ]

    missing = sorted(
      opcode
      for opcode in OPERAND_COUNTS
      if not any(re.search(pattern, opcode) for pattern in opcode_patterns)
    )

    self.assertEqual(missing, [])


if __name__ == "__main__":
  unittest.main()
