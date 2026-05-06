"""Focused tests for `parse_anchor_to_target_command`.

Exercises the 2D legacy form (`offset=(x,y)`) and the new 3D form
(`offset=(x,y,z)`) on the semantic parser. The gcode-level round-trip in
`test_gcode_domain.py` already covers the macro lexer side; this file
covers what the consumer sees.
"""

from __future__ import annotations

import pytest

from dune_winder.uv_head_target_parts.anchor_to_target import (
    parse_anchor_to_target_command,
)
from dune_winder.uv_head_target_parts.models import UvHeadTargetError


def test_parses_no_offset() -> None:
    command = parse_anchor_to_target_command("~anchorToTarget(B1201,B2001)")
    assert command.target_offset is None
    assert command.hover is False


def test_parses_2d_offset_pads_z_to_zero() -> None:
    command = parse_anchor_to_target_command(
        "~anchorToTarget(B1201,B2001,offset=(1.25,-2.5))"
    )
    assert command.target_offset == (1.25, -2.5, 0.0)


def test_parses_3d_offset() -> None:
    command = parse_anchor_to_target_command(
        "~anchorToTarget(B1201,B2001,offset=(1.25,-2.5,0.75))"
    )
    assert command.target_offset == (1.25, -2.5, 0.75)


def test_parses_3d_offset_with_hover() -> None:
    command = parse_anchor_to_target_command(
        "~anchorToTarget(B1201,B2001,offset=(0.0,0.0,1.5),hover=True)"
    )
    assert command.target_offset == (0.0, 0.0, 1.5)
    assert command.hover is True


def test_rejects_one_value_offset() -> None:
    with pytest.raises(UvHeadTargetError, match="two or three"):
        parse_anchor_to_target_command("~anchorToTarget(B1201,B2001,offset=(1.25))")


def test_rejects_four_value_offset() -> None:
    with pytest.raises(UvHeadTargetError, match="two or three"):
        parse_anchor_to_target_command(
            "~anchorToTarget(B1201,B2001,offset=(1.0,2.0,3.0,4.0))"
        )
