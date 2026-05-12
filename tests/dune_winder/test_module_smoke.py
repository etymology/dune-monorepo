"""Smoke imports for runtime modules previously absent from the test suite.

These tests guard against ImportError regressions (typos, circular imports,
missing dependencies). For modules with simple-enough surfaces, a constructor
or one-method test is included alongside the import.
"""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import pytest


THREAD_MODULES = [
    "dune_winder.threads.control_thread",
    "dune_winder.threads.web_server_thread",
    "dune_winder.threads.camera_thread",
    "dune_winder.threads.ui_server_thread",
]

CORE_MODULES = [
    "dune_winder.core.recipe_service",
    "dune_winder.core.runtime_state_service",
    "dune_winder.core.stop_mode",
    "dune_winder.core.wind_mode",
    "dune_winder.core.process_context",
    "dune_winder.core.io_log",
    "dune_winder.core.hardware_mode",
    "dune_winder.core.low_level_io",
    "dune_winder.core.apa_base",
]

IO_MODULES = [
    "dune_winder.io.devices.shadow_plc",
    "dune_winder.io.devices.io_device",
    "dune_winder.io.controllers.camera",
    "dune_winder.io.primitives.io_point",
    "dune_winder.io.primitives.digital_io",
    "dune_winder.io.primitives.digital_output",
    "dune_winder.io.primitives.analog_input",
    "dune_winder.io.primitives.analog_output",
    "dune_winder.io.primitives.motor",
    "dune_winder.io.primitives.plc_input",
]

GEOMETRY_MODULES = [
    "dune_winder.geometry.primitives.box",
    "dune_winder.geometry.primitives.line",
    "dune_winder.geometry.primitives.segment",
    "dune_winder.machine.geometry.apa",
    "dune_winder.machine.geometry.factory",
    "dune_winder.machine.geometry.layer",
    "dune_winder.machine.geometry.layer_functions",
    "dune_winder.machine.geometry.machine",
    "dune_winder.machine.geometry.u",
    "dune_winder.machine.geometry.v",
    "dune_winder.machine.geometry.x",
    "dune_winder.machine.geometry.g",
    "dune_winder.machine.geometry.gx",
    "dune_winder.machine.geometry.uv",
    "dune_winder.machine.geometry.uv_tangency",
]

UV_HEAD_TARGET_MODULES = [
    "dune_winder.uv_head_target_parts.alternating",
    "dune_winder.uv_head_target_parts.anchor_to_target",
    "dune_winder.uv_head_target_parts.constants",
    "dune_winder.uv_head_target_parts.geometry2d",
    "dune_winder.uv_head_target_parts.head_target",
    "dune_winder.uv_head_target_parts.models",
    "dune_winder.uv_head_target_parts.pin_layout",
    "dune_winder.uv_head_target_parts.recipe_sites",
    "dune_winder.uv_head_target_parts.runtime",
]

QUEUED_MOTION_MODULES = [
    "dune_winder.queued_motion.diagnostics",
    "dune_winder.queued_motion.filleted_path",
    "dune_winder.queued_motion.jerk_limits",
]

LIBRARY_MODULES = [
    "dune_winder.library.array_to_csv",
    "dune_winder.library.logged_state_machine",
    "dune_winder.library.system_semaphore",
    "dune_winder.library.time_source",
    "dune_winder.library.version",
]

API_MODULES = [
    "dune_winder.api.registry",
    "dune_winder.api.types",
]

RECIPE_MODULES = [
    "dune_winder.recipes.line_offset_overrides",
    "dune_winder.recipes.template_gcode_common",
    "dune_winder.recipes.template_gcode_foot_pauses",
    "dune_winder.recipes.template_gcode_transfers",
    "dune_winder.recipes.template_recipe_base",
]


@pytest.mark.parametrize(
    "module_name",
    THREAD_MODULES
    + CORE_MODULES
    + IO_MODULES
    + GEOMETRY_MODULES
    + UV_HEAD_TARGET_MODULES
    + QUEUED_MOTION_MODULES
    + LIBRARY_MODULES
    + API_MODULES
    + RECIPE_MODULES,
)
def test_module_imports_without_error(module_name):
    importlib.import_module(module_name)


def test_recipe_service_returns_empty_recipe_metadata_without_workspace():
    from dune_winder.core.recipe_service import RecipeService

    service = RecipeService(
        workspaceGetter=lambda: None,
        workspaceSetter=lambda _ws: None,
        workspaceDirectory="/tmp/workspace",
        workspaceCalibrationDirectory="/tmp/workspace/calibration",
    )

    assert service.getRecipeName() == ""
    assert service.getRecipeLayer() is None
    assert service.getRecipePeriod() is None
    assert service.getWrapSeekLine(0) is None


def test_recipe_service_delegates_to_workspace_when_present():
    from dune_winder.core.recipe_service import RecipeService

    workspace = MagicMock()
    workspace.getRecipe.return_value = "U-layer.gc"
    workspace.getLayer.return_value = "U"
    workspace.getRecipePeriod.return_value = 7
    workspace.getWrapSeekLine.return_value = 42

    service = RecipeService(
        workspaceGetter=lambda: workspace,
        workspaceSetter=lambda _ws: None,
        workspaceDirectory="/tmp/workspace",
        workspaceCalibrationDirectory="/tmp/workspace/calibration",
    )

    assert service.getRecipeName() == "U-layer.gc"
    assert service.getRecipeLayer() == "U"
    assert service.getRecipePeriod() == 7
    assert service.getWrapSeekLine(3) == 42
    workspace.getWrapSeekLine.assert_called_once_with(3)


def test_runtime_state_service_returns_workspace_dict_when_loaded():
    from dune_winder.core.runtime_state_service import RuntimeStateService

    workspace = MagicMock()
    workspace.toDictionary.return_value = {"recipe": "X.gc"}

    service = RuntimeStateService(
        io=MagicMock(),
        headCompensation=MagicMock(),
        workspaceGetter=lambda: workspace,
        workspaceStateReader=lambda: {"unused": True},
    )

    assert service.getWorkspaceState() == {"recipe": "X.gc"}


def test_runtime_state_service_falls_back_to_state_reader_when_no_workspace():
    from dune_winder.core.runtime_state_service import RuntimeStateService

    service = RuntimeStateService(
        io=MagicMock(),
        headCompensation=MagicMock(),
        workspaceGetter=lambda: None,
        workspaceStateReader=lambda: {"persisted": True},
    )

    assert service.getWorkspaceState() == {"persisted": True}


def test_stop_mode_exposes_substate_classes():
    from dune_winder.core.stop_mode import StopMode

    assert hasattr(StopMode, "Idle")


def test_wind_mode_exposes_substate_constants():
    from dune_winder.core.wind_mode import WindMode

    assert WindMode.SubStates.IDLE == 0
    assert WindMode.SubStates.HEAD_TRANSFER == 1
