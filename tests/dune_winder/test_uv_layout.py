from __future__ import annotations

from dune_winder.library.Geometry.location import Location
from dune_winder.library.serializable_location import SerializableLocation
from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.geometry.uv_calibration import (
  build_nominal_uv_calibration,
  normalize_layer_calibration_to_absolute,
)
from dune_winder.machine.geometry.uv_layout import get_uv_layout


def test_uv_layout_exposes_expected_pin_counts_and_bootstrap_sets():
  u_layout = get_uv_layout("U")
  v_layout = get_uv_layout("V")

  assert u_layout.pin_max == 2401
  assert v_layout.pin_max == 2399
  assert u_layout.bootstrap_pins == (
    1, 200, 400, 401, 806, 1200, 1201, 1400, 1601, 1602, 1995, 2401
  )
  assert v_layout.bootstrap_pins == (
    1, 200, 399, 400, 805, 1199, 1200, 1399, 1599, 1600, 1993, 2399
  )


def test_uv_layout_translate_pin_uses_exact_opposite_family_mapping():
  u_layout = get_uv_layout("U")
  v_layout = get_uv_layout("V")

  assert u_layout.translate_pin("B401", target_family="A") == "A2401"
  assert u_layout.translate_pin("A401", target_family="B") == "B2401"
  assert v_layout.translate_pin("B400", target_family="A") == "A2399"
  assert v_layout.translate_pin("A2399", target_family="B") == "B400"


def test_uv_layout_wire_endpoints_and_wrap_orientation_match_shared_examples():
  u_layout = get_uv_layout("U")
  v_layout = get_uv_layout("V")

  assert u_layout.wire_endpoints(1151, family="B") == ("B1600", "B1601")
  assert u_layout.wire_endpoints(1151, family="A") == ("A1202", "A1201")
  assert v_layout.wire_endpoints(8, family="B") == ("B56", "B2343")
  assert v_layout.wire_endpoints(8, family="A") == ("A344", "A456")
  assert u_layout.wrap_orientation("A401").as_tuple == ("plus", "minus")
  assert v_layout.wrap_orientation("B1600").as_tuple == ("plus", "minus")


def test_uv_layout_board_lookup_and_nominal_positions_are_machine_space():
  u_layout = get_uv_layout("U")

  board_pin = u_layout.board_lookup("A", "bottom", 1, 1)
  nominal = u_layout.nominal_positions()

  assert board_pin.pin_name == "A2401"
  assert board_pin.physical_pin == 401
  assert nominal["B1"].x == 570.0
  assert nominal["B1"].y == 2455.0
  assert nominal["B1"].y > nominal["A1"].y


def test_uv_calibration_normalization_handles_relative_and_absolute_uv_styles():
  relative = LayerCalibration(layer="U")
  relative.offset = SerializableLocation(100.0, 200.0, 0.0)
  relative.setPinLocation("A1", Location(10.0, 20.0, 145.0))
  relative.setPinLocation("B1", Location(30.0, 40.0, 270.0))

  absolute = LayerCalibration(layer="V")
  absolute.offset = SerializableLocation(0.0, 0.0, 0.0)
  absolute.setPinLocation("A1", Location(110.0, 220.0, 150.0))
  absolute.setPinLocation("B1", Location(130.0, 240.0, 265.0))

  normalized_relative = normalize_layer_calibration_to_absolute(relative, "U")
  normalized_absolute = normalize_layer_calibration_to_absolute(absolute, "V")

  assert normalized_relative.offset == SerializableLocation(0.0, 0.0, 0.0)
  assert normalized_relative.getPinLocation("A1") == Location(110.0, 220.0, 145.0)
  assert normalized_relative.getPinLocation("B1") == Location(130.0, 240.0, 270.0)
  assert normalized_absolute.getPinLocation("A1") == Location(110.0, 220.0, 150.0)
  assert normalized_absolute.getPinLocation("B1") == Location(130.0, 240.0, 265.0)


def test_build_nominal_uv_calibration_matches_layout_nominal_positions():
  layout = get_uv_layout("V")
  calibration = build_nominal_uv_calibration("V")
  nominal = layout.nominal_positions()

  assert calibration.offset == SerializableLocation(0.0, 0.0, 0.0)
  assert calibration.getPinLocation("A1") == Location(
    nominal["A1"].x,
    nominal["A1"].y,
    nominal["A1"].z,
  )
  assert calibration.getPinLocation("B1") == Location(
    nominal["B1"].x,
    nominal["B1"].y,
    nominal["B1"].z,
  )


def test_named_pins_derived_from_side_ranges():
  u_np = get_uv_layout("U").named_pins
  v_np = get_uv_layout("V").named_pins

  assert u_np == {
    "bottom_foot_end": 1200,
    "bottom_head_end": 401,
    "top_foot_end": 1602,
    "top_head_end": 2401,
    "foot_bottom_end": 1201,
    "foot_top_end": 1601,
    "head_bottom_end": 400,
    "head_top_end": 1,
  }
  assert v_np == {
    "bottom_foot_end": 1199,
    "bottom_head_end": 400,
    "top_foot_end": 1600,
    "top_head_end": 2399,
    "foot_bottom_end": 1200,
    "foot_top_end": 1599,
    "head_bottom_end": 399,
    "head_top_end": 1,
  }


def test_wrap_pin_wraps_into_valid_range():
  u_layout = get_uv_layout("U")
  v_layout = get_uv_layout("V")

  assert u_layout.wrap_pin(1) == 1
  assert u_layout.wrap_pin(2401) == 2401
  assert u_layout.wrap_pin(2402) == 1
  assert u_layout.wrap_pin(0) == 2401
  assert u_layout.wrap_pin(-1) == 2400

  assert v_layout.wrap_pin(1) == 1
  assert v_layout.wrap_pin(2399) == 2399
  assert v_layout.wrap_pin(2400) == 1
  assert v_layout.wrap_pin(0) == 2399
  assert v_layout.wrap_pin(-1) == 2398


def test_b_to_a_pin_number_matches_recipe_formula():
  u_layout = get_uv_layout("U")
  v_layout = get_uv_layout("V")

  assert u_layout.b_to_a_pin_number(400) == 1
  assert u_layout.b_to_a_pin_number(1) == 400
  assert u_layout.b_to_a_pin_number(401) == 2401

  assert v_layout.b_to_a_pin_number(399) == 1
  assert v_layout.b_to_a_pin_number(1) == 399
  assert v_layout.b_to_a_pin_number(400) == 2399
