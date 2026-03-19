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
  PULL_IN_IDS as U_PULL_IN_IDS,
  WRAP_COUNT as U_WRAP_COUNT,
  X_PULL_IN as DEFAULT_X_PULL_IN,
  Y_PULL_IN as DEFAULT_Y_PULL_IN,
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

PULL_IN_LABELS = {
  "Y_PULL_IN": "Y Pull-In",
  "X_PULL_IN": "X Pull-In",
}

PULL_IN_DEFAULTS = {
  "Y_PULL_IN": DEFAULT_Y_PULL_IN,
  "X_PULL_IN": DEFAULT_X_PULL_IN,
}

_HEADER_HASH_RE = re.compile(r"^\(\s*U-layer\s+([A-Z0-9-]+)\s*\)")


class UTemplateRecipe(TemplateRecipeBase):
  LAYER = "U"
  SERVICE_NAME = "UTemplateRecipe"
  OFFSET_IDS = U_OFFSET_IDS
  OFFSET_LABELS = OFFSET_LABELS
  PULL_IN_IDS = U_PULL_IN_IDS
  PULL_IN_LABELS = PULL_IN_LABELS
  PULL_IN_DEFAULTS = PULL_IN_DEFAULTS
  WRAP_COUNT = U_WRAP_COUNT
  DEFAULT_ROW_COUNT = DEFAULT_U_TEMPLATE_ROW_COUNT
  HEADER_HASH_RE = _HEADER_HASH_RE
  DRAFT_FILE_NAME = "U_Draft.json"
  get_recipe_file_name = staticmethod(get_u_recipe_file_name)
  write_template_file = staticmethod(write_u_template_file)

  def _normalizePullInId(self, pullInId):
    pullInId = str(pullInId).strip()
    if pullInId not in self.PULL_IN_IDS:
      raise ValueError("Unknown U pull-in: " + repr(pullInId))
    return pullInId

  def _resetExtraState(self):
    self._pullIns = dict(self.PULL_IN_DEFAULTS)

  def _loadExtraStateData(self, data):
    pullIns = data.get("pullIns", {})
    if not isinstance(pullIns, dict):
      return
    for pullInId in self.PULL_IN_IDS:
      if pullInId in pullIns:
        self._pullIns[pullInId] = float(pullIns[pullInId])

  def _extraDraftState(self):
    return {"pullIns": dict(self._pullIns)}

  def _extraPublicState(self):
    return {
      "pullIns": dict(self._pullIns),
      "pullInOrder": list(self.PULL_IN_IDS),
      "pullInLabels": dict(self.PULL_IN_LABELS),
    }

  def _generationKwargs(self):
    return {"named_inputs": dict(self._pullIns)}

  def setPullIn(self, pullInId, value):
    self._ensureDraftStateLoaded()

    _, error = self._getActiveLayer()
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    try:
      pullInId = self._normalizePullInId(pullInId)
    except ValueError as exception:
      return self._errorResult(str(exception))

    self._pullIns[pullInId] = float(value)
    self._dirty = True
    self._persistState()
    return self._okResult(
      {"pullInId": pullInId, "value": self._pullIns[pullInId]}
    )
