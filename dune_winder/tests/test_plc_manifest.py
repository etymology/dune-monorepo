import json
import tempfile
import unittest
from pathlib import Path

from dune_winder.plc_manifest import compute_metadata_hash
from dune_winder.plc_manifest import compute_rllscrap_hash
from dune_winder.plc_manifest import compute_values_hash
from dune_winder.plc_manifest import PlcManifest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path, payload):
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(payload, indent=2) + "\n")


def _make_program_tags_payload(
  generated_at="2026-03-20T00:00:00+00:00",
  tag_name="TagA",
  tag_value=42,
  values_generated_at=None,
):
  tag = {
    "name": tag_name,
    "fully_qualified_name": f"Program:TestProgram.{tag_name}",
    "tag_type": "atomic",
    "data_type_name": "DINT",
  }
  if tag_value is not None:
    tag["value"] = tag_value

  payload = {
    "schema_version": 1,
    "generated_at": generated_at,
    "plc_path": "192.168.1.10",
    "program_name": "TestProgram",
    "main_routine_name": "main",
    "routines": ["main"],
    "subroutines": [],
    "udts": [],
    "program_tags": [tag],
  }
  if values_generated_at is not None:
    payload["values_generated_at"] = values_generated_at
  return payload


def _make_controller_tags_payload(
  generated_at="2026-03-20T00:00:00+00:00",
  tag_name="CtrlTag",
  tag_value=0,
  values_generated_at=None,
):
  tag = {
    "name": tag_name,
    "fully_qualified_name": tag_name,
    "tag_type": "atomic",
    "data_type_name": "BOOL",
  }
  if tag_value is not None:
    tag["value"] = tag_value

  payload = {
    "schema_version": 1,
    "generated_at": generated_at,
    "plc_path": "192.168.1.10",
    "controller": {"product_name": "TestPLC"},
    "udts": [],
    "controller_level_tags": [tag],
  }
  if values_generated_at is not None:
    payload["values_generated_at"] = values_generated_at
  return payload


# ---------------------------------------------------------------------------
# Hash function tests
# ---------------------------------------------------------------------------

class ComputeMetadataHashTests(unittest.TestCase):
  def test_returns_none_when_file_missing(self):
    self.assertIsNone(compute_metadata_hash(Path("/nonexistent/path.json")))

  def test_ignores_generated_at_change(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "programTags.json"
      _write_json(path, _make_program_tags_payload(generated_at="2026-01-01T00:00:00+00:00"))
      hash1 = compute_metadata_hash(path)

      _write_json(path, _make_program_tags_payload(generated_at="2026-06-01T00:00:00+00:00"))
      hash2 = compute_metadata_hash(path)

      self.assertEqual(hash1, hash2)

  def test_ignores_values_generated_at_change(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "programTags.json"
      _write_json(path, _make_program_tags_payload(values_generated_at="2026-01-01T00:00:00+00:00"))
      hash1 = compute_metadata_hash(path)

      _write_json(path, _make_program_tags_payload(values_generated_at="2026-06-01T00:00:00+00:00"))
      hash2 = compute_metadata_hash(path)

      self.assertEqual(hash1, hash2)

  def test_ignores_tag_value_change(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "programTags.json"
      _write_json(path, _make_program_tags_payload(tag_value=0))
      hash1 = compute_metadata_hash(path)

      _write_json(path, _make_program_tags_payload(tag_value=999))
      hash2 = compute_metadata_hash(path)

      self.assertEqual(hash1, hash2)

  def test_changes_when_tag_name_changes(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "programTags.json"
      _write_json(path, _make_program_tags_payload(tag_name="TagA"))
      hash1 = compute_metadata_hash(path)

      _write_json(path, _make_program_tags_payload(tag_name="TagB"))
      hash2 = compute_metadata_hash(path)

      self.assertNotEqual(hash1, hash2)

  def test_ignores_tag_read_error_change(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "programTags.json"
      payload1 = _make_program_tags_payload()
      _write_json(path, payload1)
      hash1 = compute_metadata_hash(path)

      payload2 = _make_program_tags_payload()
      payload2["program_tags"][0]["read_error"] = "permission denied"
      _write_json(path, payload2)
      hash2 = compute_metadata_hash(path)

      self.assertEqual(hash1, hash2)


class ComputeValuesHashTests(unittest.TestCase):
  def test_returns_none_when_file_missing(self):
    self.assertIsNone(compute_values_hash(Path("/nonexistent/path.json")))

  def test_returns_none_when_values_generated_at_absent(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "programTags.json"
      _write_json(path, _make_program_tags_payload(values_generated_at=None))
      self.assertIsNone(compute_values_hash(path))

  def test_changes_when_values_generated_at_changes(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "programTags.json"
      _write_json(path, _make_program_tags_payload(
        tag_value=42, values_generated_at="2026-01-01T00:00:00+00:00"
      ))
      hash1 = compute_values_hash(path)

      _write_json(path, _make_program_tags_payload(
        tag_value=42, values_generated_at="2026-06-01T00:00:00+00:00"
      ))
      hash2 = compute_values_hash(path)

      self.assertNotEqual(hash1, hash2)

  def test_changes_when_tag_value_changes(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "programTags.json"
      _write_json(path, _make_program_tags_payload(
        tag_value=0, values_generated_at="2026-01-01T00:00:00+00:00"
      ))
      hash1 = compute_values_hash(path)

      _write_json(path, _make_program_tags_payload(
        tag_value=999, values_generated_at="2026-01-01T00:00:00+00:00"
      ))
      hash2 = compute_values_hash(path)

      self.assertNotEqual(hash1, hash2)

  def test_stable_when_only_generated_at_changes(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "programTags.json"
      _write_json(path, _make_program_tags_payload(
        generated_at="2026-01-01T00:00:00+00:00",
        tag_value=5,
        values_generated_at="2026-01-01T12:00:00+00:00",
      ))
      hash1 = compute_values_hash(path)

      _write_json(path, _make_program_tags_payload(
        generated_at="2026-06-01T00:00:00+00:00",
        tag_value=5,
        values_generated_at="2026-01-01T12:00:00+00:00",
      ))
      hash2 = compute_values_hash(path)

      self.assertEqual(hash1, hash2)


class ComputeRllscrapHashTests(unittest.TestCase):
  def test_crlf_and_lf_produce_same_hash(self):
    with tempfile.TemporaryDirectory() as tmp:
      lf_path = Path(tmp) / "lf.rllscrap"
      crlf_path = Path(tmp) / "crlf.rllscrap"
      content = "NEQ Var 0\nJMP lbl_end\nLBL lbl_end\n"
      lf_path.write_text(content, newline="\n")
      crlf_path.write_text(content, newline="\r\n")

      self.assertEqual(compute_rllscrap_hash(lf_path), compute_rllscrap_hash(crlf_path))

  def test_differs_on_content_change(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "file.rllscrap"
      path.write_text("NEQ Var 0")
      hash1 = compute_rllscrap_hash(path)

      path.write_text("NEQ Var 1")
      hash2 = compute_rllscrap_hash(path)

      self.assertNotEqual(hash1, hash2)

  def test_empty_file_produces_stable_hash(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "empty.rllscrap"
      path.write_text("")
      hash1 = compute_rllscrap_hash(path)
      hash2 = compute_rllscrap_hash(path)

      self.assertEqual(hash1, hash2)


# ---------------------------------------------------------------------------
# PlcManifest tests
# ---------------------------------------------------------------------------

class PlcManifestLoadSaveTests(unittest.TestCase):
  def test_load_creates_empty_structure_when_manifest_absent(self):
    with tempfile.TemporaryDirectory() as tmp:
      manifest = PlcManifest(Path(tmp))
      manifest.load()

      self.assertEqual(manifest._data["schema_version"], 1)
      self.assertEqual(manifest._data["controller"], {})
      self.assertEqual(manifest._data["programs"], {})

  def test_save_creates_manifest_json(self):
    with tempfile.TemporaryDirectory() as tmp:
      plc_root = Path(tmp)
      manifest = PlcManifest(plc_root)
      manifest.load()
      manifest.save()

      self.assertTrue((plc_root / "manifest.json").exists())

  def test_save_load_roundtrip_preserves_data(self):
    with tempfile.TemporaryDirectory() as tmp:
      plc_root = Path(tmp)

      manifest1 = PlcManifest(plc_root)
      manifest1.load()
      manifest1._data["programs"]["TestProgram"] = {
        "tag_metadata": {"hash": "AAA-BBB-1234", "generated_at": "2026-01-01T00:00:00+00:00"}
      }
      manifest1.save()

      manifest2 = PlcManifest(plc_root)
      manifest2.load()
      entry = manifest2._data["programs"]["TestProgram"]["tag_metadata"]
      self.assertEqual(entry["hash"], "AAA-BBB-1234")

  def test_save_is_atomic_no_partial_write(self):
    with tempfile.TemporaryDirectory() as tmp:
      plc_root = Path(tmp)
      manifest = PlcManifest(plc_root)
      manifest.load()
      manifest.save()

      # No .tmp file should remain after save
      self.assertFalse((plc_root / "manifest.json.tmp").exists())


class PlcManifestUpdateTests(unittest.TestCase):
  def test_update_tag_metadata_writes_hash_and_generated_at(self):
    with tempfile.TemporaryDirectory() as tmp:
      plc_root = Path(tmp)
      json_path = plc_root / "TestProgram" / "programTags.json"
      _write_json(json_path, _make_program_tags_payload(generated_at="2026-03-20T00:00:00+00:00"))

      manifest = PlcManifest(plc_root)
      manifest.load()
      result = manifest.update_tag_metadata("TestProgram")

      entry = manifest._data["programs"]["TestProgram"]["tag_metadata"]
      self.assertIsNotNone(result)
      self.assertEqual(entry["hash"], result)
      self.assertEqual(entry["generated_at"], "2026-03-20T00:00:00+00:00")

  def test_update_tag_metadata_controller_uses_none_key(self):
    with tempfile.TemporaryDirectory() as tmp:
      plc_root = Path(tmp)
      _write_json(
        plc_root / "controller_level_tags.json",
        _make_controller_tags_payload(generated_at="2026-03-20T00:00:00+00:00"),
      )

      manifest = PlcManifest(plc_root)
      manifest.load()
      manifest.update_tag_metadata(None)

      self.assertIn("tag_metadata", manifest._data["controller"])

  def test_update_tag_metadata_returns_none_when_file_missing(self):
    with tempfile.TemporaryDirectory() as tmp:
      manifest = PlcManifest(Path(tmp))
      manifest.load()
      result = manifest.update_tag_metadata("NonExistentProgram")

      self.assertIsNone(result)

  def test_update_tag_values_writes_hash_and_generated_at(self):
    with tempfile.TemporaryDirectory() as tmp:
      plc_root = Path(tmp)
      json_path = plc_root / "TestProgram" / "programTags.json"
      _write_json(json_path, _make_program_tags_payload(
        tag_value=10, values_generated_at="2026-03-20T12:00:00+00:00"
      ))

      manifest = PlcManifest(plc_root)
      manifest.load()
      result = manifest.update_tag_values("TestProgram")

      entry = manifest._data["programs"]["TestProgram"]["tag_values"]
      self.assertIsNotNone(result)
      self.assertEqual(entry["hash"], result)
      self.assertEqual(entry["generated_at"], "2026-03-20T12:00:00+00:00")

  def test_update_tag_values_returns_none_when_values_generated_at_absent(self):
    with tempfile.TemporaryDirectory() as tmp:
      plc_root = Path(tmp)
      json_path = plc_root / "TestProgram" / "programTags.json"
      _write_json(json_path, _make_program_tags_payload(values_generated_at=None))

      manifest = PlcManifest(plc_root)
      manifest.load()
      result = manifest.update_tag_values("TestProgram")

      self.assertIsNone(result)
      self.assertNotIn("tag_values", manifest._data.get("programs", {}).get("TestProgram", {}))

  def test_update_rllscrap_writes_hash_hashed_at_and_file_mtime(self):
    with tempfile.TemporaryDirectory() as tmp:
      plc_root = Path(tmp)
      rllscrap = plc_root / "ProgA" / "main" / "studio_copy.rllscrap"
      rllscrap.parent.mkdir(parents=True)
      rllscrap.write_text("NEQ Var 0")

      manifest = PlcManifest(plc_root)
      manifest.load()
      result = manifest.update_rllscrap("ProgA", "main")

      entry = manifest._data["programs"]["ProgA"]["routines"]["main"]
      self.assertEqual(entry["hash"], result)
      self.assertIn("hashed_at", entry)
      self.assertIn("file_mtime", entry)


class PlcManifestScanRllscrapTests(unittest.TestCase):
  def _make_rllscrap_tree(self, plc_root):
    files = [
      plc_root / "ProgA" / "main" / "studio_copy.rllscrap",
      plc_root / "ProgA" / "Sub1" / "studio_copy.rllscrap",
      plc_root / "ProgB" / "main" / "studio_copy.rllscrap",
    ]
    for f in files:
      f.parent.mkdir(parents=True, exist_ok=True)
      f.write_text("rung content")
    return files

  def test_scan_finds_all_studio_copy_files(self):
    with tempfile.TemporaryDirectory() as tmp:
      plc_root = Path(tmp)
      self._make_rllscrap_tree(plc_root)

      manifest = PlcManifest(plc_root)
      manifest.load()
      results = manifest.scan_rllscrap()

      self.assertEqual(len(results), 3)
      locations = [(prog, rtn) for prog, rtn, _ in results]
      self.assertIn(("ProgA", "main"), locations)
      self.assertIn(("ProgA", "Sub1"), locations)
      self.assertIn(("ProgB", "main"), locations)

  def test_scan_updates_manifest_entries(self):
    with tempfile.TemporaryDirectory() as tmp:
      plc_root = Path(tmp)
      self._make_rllscrap_tree(plc_root)

      manifest = PlcManifest(plc_root)
      manifest.load()
      manifest.scan_rllscrap()

      self.assertIn("ProgA", manifest._data["programs"])
      self.assertIn("main", manifest._data["programs"]["ProgA"]["routines"])

  def test_scan_empty_directory_returns_empty_list(self):
    with tempfile.TemporaryDirectory() as tmp:
      manifest = PlcManifest(Path(tmp))
      manifest.load()
      results = manifest.scan_rllscrap()
      self.assertEqual(results, [])


# ---------------------------------------------------------------------------
# PlcManifest.status() tests
# ---------------------------------------------------------------------------

class PlcManifestStatusTests(unittest.TestCase):
  def _setup_program(self, plc_root, program_name="TestProgram", content="rung data"):
    json_path = plc_root / program_name / "programTags.json"
    _write_json(json_path, _make_program_tags_payload())
    rllscrap = plc_root / program_name / "main" / "studio_copy.rllscrap"
    rllscrap.parent.mkdir(parents=True, exist_ok=True)
    rllscrap.write_text(content)
    return json_path, rllscrap

  def _find_row(self, rows, location, category):
    return next((r for r in rows if r.location == location and r.category == category), None)

  def test_status_classifies_ok_when_hash_matches(self):
    with tempfile.TemporaryDirectory() as tmp:
      plc_root = Path(tmp)
      _, rllscrap = self._setup_program(plc_root)

      manifest = PlcManifest(plc_root)
      manifest.load()
      manifest.update_rllscrap("TestProgram", "main")
      manifest.update_tag_metadata("TestProgram")

      rows = manifest.status()

      rll_row = self._find_row(rows, "TestProgram/main", "rllscrap")
      meta_row = self._find_row(rows, "TestProgram", "tag_metadata")
      self.assertIsNotNone(rll_row)
      self.assertEqual(rll_row.state, "ok")
      self.assertIsNotNone(meta_row)
      self.assertEqual(meta_row.state, "ok")

  def test_status_classifies_modified_when_rllscrap_content_changes(self):
    with tempfile.TemporaryDirectory() as tmp:
      plc_root = Path(tmp)
      _, rllscrap = self._setup_program(plc_root)

      manifest = PlcManifest(plc_root)
      manifest.load()
      manifest.update_rllscrap("TestProgram", "main")

      rllscrap.write_text("completely different content")

      rows = manifest.status()
      row = self._find_row(rows, "TestProgram/main", "rllscrap")
      self.assertEqual(row.state, "modified")

  def test_status_classifies_modified_when_metadata_changes(self):
    with tempfile.TemporaryDirectory() as tmp:
      plc_root = Path(tmp)
      json_path, _ = self._setup_program(plc_root)

      manifest = PlcManifest(plc_root)
      manifest.load()
      manifest.update_tag_metadata("TestProgram")

      # Change a structural element (tag name)
      payload = json.loads(json_path.read_text())
      payload["program_tags"][0]["name"] = "Renamed"
      _write_json(json_path, payload)

      rows = manifest.status()
      row = self._find_row(rows, "TestProgram", "tag_metadata")
      self.assertEqual(row.state, "modified")

  def test_status_classifies_missing_when_rllscrap_deleted(self):
    with tempfile.TemporaryDirectory() as tmp:
      plc_root = Path(tmp)
      _, rllscrap = self._setup_program(plc_root)

      manifest = PlcManifest(plc_root)
      manifest.load()
      manifest.update_rllscrap("TestProgram", "main")
      rllscrap.unlink()

      rows = manifest.status()
      row = self._find_row(rows, "TestProgram/main", "rllscrap")
      self.assertEqual(row.state, "missing")

  def test_status_classifies_new_for_untracked_rllscrap(self):
    with tempfile.TemporaryDirectory() as tmp:
      plc_root = Path(tmp)
      self._setup_program(plc_root)

      # Don't scan — no entries in manifest
      manifest = PlcManifest(plc_root)
      manifest.load()

      rows = manifest.status()
      row = self._find_row(rows, "TestProgram/main", "rllscrap")
      self.assertIsNotNone(row)
      self.assertEqual(row.state, "new")

  def test_status_omits_tag_values_when_never_exported(self):
    with tempfile.TemporaryDirectory() as tmp:
      plc_root = Path(tmp)
      self._setup_program(plc_root)  # no values_generated_at in JSON

      manifest = PlcManifest(plc_root)
      manifest.load()
      manifest.update_tag_metadata("TestProgram")

      rows = manifest.status()
      values_row = self._find_row(rows, "TestProgram", "tag_values")
      # Should be absent since values have never been exported
      self.assertIsNone(values_row)

  def test_status_returns_empty_for_empty_plc_root(self):
    with tempfile.TemporaryDirectory() as tmp:
      manifest = PlcManifest(Path(tmp))
      manifest.load()
      rows = manifest.status()
      self.assertEqual(rows, [])


# ---------------------------------------------------------------------------
# Integration shim tests
# ---------------------------------------------------------------------------

class WriteSnapshotManifestIntegrationTests(unittest.TestCase):
  def test_write_plc_snapshot_creates_manifest_json(self):
    from dune_winder.plc_metadata_export import write_plc_snapshot
    snapshot = {
      "schema_version": 1,
      "generated_at": "2026-03-20T00:00:00+00:00",
      "plc_path": "192.168.1.10",
      "controller": {"product_name": "TestPLC"},
      "controller_level_tags": [
        {"name": "CtrlTag", "fully_qualified_name": "CtrlTag", "tag_type": "atomic", "data_type_name": "BOOL"}
      ],
      "controller_udts": [],
      "programs": {
        "TestProgram": {
          "program_name": "TestProgram",
          "main_routine_name": "main",
          "main_routine_name_source": "casefold_name_match",
          "routines": ["main"],
          "subroutines": [],
          "program_tags": [
            {"name": "TagA", "fully_qualified_name": "Program:TestProgram.TagA", "tag_type": "atomic", "data_type_name": "DINT"}
          ],
          "udts": [],
        }
      },
    }

    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp) / "plc"
      write_plc_snapshot(snapshot, root)

      manifest_path = root / "manifest.json"
      self.assertTrue(manifest_path.exists())
      data = json.loads(manifest_path.read_text())
      self.assertIn("controller", data)
      self.assertIn("tag_metadata", data["controller"])
      self.assertIn("TestProgram", data.get("programs", {}))
      self.assertIn("tag_metadata", data["programs"]["TestProgram"])


if __name__ == "__main__":
  unittest.main()
