import unittest

from dune_winder.queued_motion.queue_client_3d_arc import (
  DIR_3D_LONGEST,
  DIR_3D_SHORTEST,
  DIR_3D_SHORTEST_FULL,
  MotionArc3DSegment,
  MotionArc3DQueueClient,
  validate_arc3d_segment,
)


class MotionQueue3DArcTests(unittest.TestCase):
  def _valid_segment(self):
    return MotionArc3DSegment(
      seq=100,
      x=0.0,
      y=100.0,
      z=0.0,
      via_center_x=0.0,
      via_center_y=0.0,
      via_center_z=0.0,
      direction=DIR_3D_SHORTEST,
    )

  def test_validate_arc_accepts_valid_segment(self):
    seg = self._valid_segment()
    validate_arc3d_segment(seg, start_xyz=(100.0, 0.0, 0.0))

  def test_validate_arc_rejects_full_direction_modes(self):
    seg = MotionArc3DSegment(
      seq=100,
      x=0.0,
      y=100.0,
      z=0.0,
      via_center_x=0.0,
      via_center_y=0.0,
      via_center_z=0.0,
      direction=DIR_3D_SHORTEST_FULL,
    )
    with self.assertRaises(ValueError):
      validate_arc3d_segment(seg, start_xyz=(100.0, 0.0, 0.0))

  def test_validate_arc_rejects_full_circle_start_equals_end(self):
    seg = MotionArc3DSegment(
      seq=100,
      x=100.0,
      y=0.0,
      z=0.0,
      via_center_x=0.0,
      via_center_y=0.0,
      via_center_z=0.0,
      direction=DIR_3D_LONGEST,
    )
    with self.assertRaises(ValueError):
      validate_arc3d_segment(seg, start_xyz=(100.0, 0.0, 0.0))

  def test_validate_arc_rejects_radius_mismatch(self):
    seg = MotionArc3DSegment(
      seq=100,
      x=0.0,
      y=100.0,
      z=5.0,
      via_center_x=0.0,
      via_center_y=0.0,
      via_center_z=0.0,
      direction=DIR_3D_SHORTEST,
    )
    with self.assertRaises(ValueError):
      validate_arc3d_segment(seg, start_xyz=(100.0, 0.0, 0.0))

  def test_validate_arc_rejects_collinear_geometry(self):
    seg = MotionArc3DSegment(
      seq=100,
      x=-100.0,
      y=0.0,
      z=0.0,
      via_center_x=0.0,
      via_center_y=0.0,
      via_center_z=0.0,
      direction=DIR_3D_SHORTEST,
    )
    with self.assertRaises(ValueError):
      validate_arc3d_segment(seg, start_xyz=(100.0, 0.0, 0.0))

  def test_validate_arc_rejects_jerk_outside_percent_range(self):
    with self.subTest("jerk_accel"):
      seg = MotionArc3DSegment(
        seq=100,
        x=0.0,
        y=100.0,
        z=0.0,
        via_center_x=0.0,
        via_center_y=0.0,
        via_center_z=0.0,
        direction=DIR_3D_SHORTEST,
        jerk_accel=0.0,
      )
      with self.assertRaises(ValueError):
        validate_arc3d_segment(seg, start_xyz=(100.0, 0.0, 0.0))

    with self.subTest("jerk_decel"):
      seg = MotionArc3DSegment(
        seq=100,
        x=0.0,
        y=100.0,
        z=0.0,
        via_center_x=0.0,
        via_center_y=0.0,
        via_center_z=0.0,
        direction=DIR_3D_SHORTEST,
        jerk_decel=101.0,
      )
      with self.assertRaises(ValueError):
        validate_arc3d_segment(seg, start_xyz=(100.0, 0.0, 0.0))

  def test_segment_to_udt_uses_xyz_arrays(self):
    seg = self._valid_segment()
    udt = MotionArc3DQueueClient._segment_to_udt(seg)

    self.assertIn("XYZ", udt)
    self.assertIn("ViaCenter", udt)
    self.assertEqual(len(udt["XYZ"]), 3)
    self.assertEqual(len(udt["ViaCenter"]), 3)
    self.assertEqual(udt["SegType"], 2)
    self.assertEqual(udt["CircleType"], 1)

  def test_xy_interlock_blocks_when_xy_queue_active(self):
    motion = MotionArc3DQueueClient("SIM")
    motion._try_read_one = lambda _tag: 1  # type: ignore[assignment]

    with self.assertRaises(RuntimeError):
      motion._assert_xy_idle("test")


if __name__ == "__main__":
  unittest.main()
