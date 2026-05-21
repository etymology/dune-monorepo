###############################################################################
# Name: template_gcode_helpers.py
# Uses: Layer-agnostic helpers shared by u_/v_/xg_template_gcode.
#
# Each helper here was previously duplicated verbatim across the per-layer
# template modules. They take no layer-specific state (no pin range, no
# offset map, no labels) so they can be safely shared as plain functions.
###############################################################################

from __future__ import annotations

import re

from dune_winder.recipes import template_gcode_common


_G113_PARAMS_RE = re.compile(r"G113\s+P\w+\s*")


def _apply_strip_g113_params(lines):
    return [
        re.sub(r"\s{2,}", " ", _G113_PARAMS_RE.sub("", line)).strip() for line in lines
    ]


def _coord(axis, value):
    return template_gcode_common.coord(axis, value)


def _offset_fragment(axis, value):
    return template_gcode_common.offset_fragment(axis, value, coord_fn=_coord)


def _normalize_pin_token(token):
    normalized = str(token).strip().upper()
    if normalized.startswith("P"):
        normalized = normalized[1:]
    return normalized


def _extract_g103_segment(tokens):
    try:
        command_index = tokens.index("G103")
    except ValueError:
        return None
    if command_index + 2 >= len(tokens):
        return None
    pin_a = _normalize_pin_token(tokens[command_index + 1])
    pin_b = _normalize_pin_token(tokens[command_index + 2])
    if not pin_a or not pin_b:
        return None
    if pin_a[:1] not in ("A", "B") or pin_b[:1] not in ("A", "B"):
        return None
    return (pin_a, pin_b)


def _extract_primary_site(tokens):
    try:
        g109_index = tokens.index("G109")
        g103_index = tokens.index("G103")
    except ValueError:
        return None
    if g109_index + 2 >= len(tokens) or g103_index + 2 >= len(tokens):
        return None
    anchor_pin = _normalize_pin_token(tokens[g109_index + 1])
    orientation_token = str(tokens[g109_index + 2]).strip().upper()
    pin_a = _normalize_pin_token(tokens[g103_index + 1])
    pin_b = _normalize_pin_token(tokens[g103_index + 2])
    if not anchor_pin or not pin_a or (not pin_b):
        return None
    if (
        anchor_pin[:1] not in ("A", "B")
        or pin_a[:1] not in ("A", "B")
        or pin_b[:1] not in ("A", "B")
    ):
        return None
    return (anchor_pin, orientation_token, pin_a, pin_b)
