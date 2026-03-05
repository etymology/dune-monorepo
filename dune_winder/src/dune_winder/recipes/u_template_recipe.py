###############################################################################
# Name: UTemplateRecipe.py
# Uses: Manage U-layer template parameters and recipe generation.
# Date: 2026-03-04
###############################################################################

import re

from dune_winder.recipes.template_recipe_base import TemplateRecipeBase
from dune_winder.recipes.u_template_gcode import (
  DEFAULT_U_TEMPLATE_ROW_COUNT,
  OFFSET_IDS as U_OFFSET_IDS,
  WRAP_COUNT as U_WRAP_COUNT,
  get_u_recipe_file_name,
  write_u_template_file,
)


OFFSET_LABELS = {
  "top_b_foot_end": "Top B / foot end",
  "top_a_foot_end": "Top A / foot end",
  "bottom_a_head_end": "Bottom A / head end",
  "bottom_b_head_end": "Bottom B / head end",
  "head_b_corner": "Head B",
  "head_a_corner": "Head A",
  "top_a_head_end": "Top A / head end",
  "top_b_head_end": "Top B / head end",
  "bottom_b_foot_end": "Bottom B / foot end",
  "bottom_a_foot_end": "Bottom A / foot end",
  "foot_a_corner": "Foot A",
  "foot_b_corner": "Foot B",
}

_HEADER_HASH_RE = re.compile(r"^\(\s*U-layer\s+([A-Z0-9-]+)\s*\)")


class UTemplateRecipe(TemplateRecipeBase):
  LAYER = "U"
  SERVICE_NAME = "UTemplateRecipe"
  OFFSET_IDS = U_OFFSET_IDS
  OFFSET_LABELS = OFFSET_LABELS
  WRAP_COUNT = U_WRAP_COUNT
  DEFAULT_ROW_COUNT = DEFAULT_U_TEMPLATE_ROW_COUNT
  HEADER_HASH_RE = _HEADER_HASH_RE
  DRAFT_FILE_NAME = "U_Draft.json"
  get_recipe_file_name = staticmethod(get_u_recipe_file_name)
  write_template_file = staticmethod(write_u_template_file)
