"""Ladder-backed simulator that executes only the Monoroutine program.

The Monoroutine is a single self-contained routine that inlines the logic of
all ensemble PLC programs.  It lives in ``dune_winder/plc_monoroutine/`` as a
parallel development branch separate from the ensemble under
``dune_winder/plc/``.

Key differences from ``LadderSimulatedPLC``:

* Only one routine is loaded and executed each scan cycle.
* ``CapSegSpeed`` is inlined in the ladder via JMP/LBL labels; no Python JSR
  override is registered.
* ``QueueCtl`` is program-scoped to ``Monoroutine`` (not ``motionQueue``), so
  the bootstrap uses the correct program scope.
"""

from __future__ import annotations

from dune_winder.paths import MONOROUTINE_PLC_ROOT
from dune_winder.paths import PLC_ROOT
from dune_winder.plc_ladder import load_plc_metadata

from .ladder_simulated_plc import LadderSimulatedPLC


class MonoroutineLadderSimulatedPLC(LadderSimulatedPLC):
    """LadderSimulatedPLC variant backed by the single Monoroutine routine."""

    _PLC_ROOT = MONOROUTINE_PLC_ROOT
    _CONTROLLER_TAGS_ROOT = PLC_ROOT
    _LATCH_PROGRAM = "Monoroutine"

    _SCAN_ORDER = (("Monoroutine", "main"),)
    _ROUTINES_TO_LOAD = _SCAN_ORDER

    # -----------------------------------------------------------------------
    def _load_metadata(self):
        return load_plc_metadata(
            self._PLC_ROOT,
            controller_tags_root=self._CONTROLLER_TAGS_ROOT,
        )

    # -----------------------------------------------------------------------
    def _register_jsr_targets(self):
        # CapSegSpeed is inlined in the monoroutine via JMP/LBL; no JSR targets
        # are needed.
        pass

    # -----------------------------------------------------------------------
    def _bootstrap_tags(self):
        super()._bootstrap_tags()
        # super() initialises QueueCtl scoped to "motionQueue"; the monoroutine
        # scopes QueueCtl to "Monoroutine" instead.
        self._ctx.set_value("QueueCtl.POS", 0, program="Monoroutine")
        self._ctx.set_value("QueueCtl.EM", True, program="Monoroutine")
        self._ctx.set_value("QueueCtl.DN", False, program="Monoroutine")

    # -----------------------------------------------------------------------
    def _apply_scan(self, advance_runtime: bool = True):
        if advance_runtime:
            self._executor.advance_runtime(self._ctx)
            self._cycle = self._ctx.scan_count

        self._sync_builtin_inputs()
        routine = self._routines.get(("Monoroutine", "main"))
        if routine is not None:
            self._execute_loaded_callable(routine, self._ctx)
        self._apply_logic_overrides()
        self._apply_latch_stub()
        self._apply_compatibility_state()

    # -----------------------------------------------------------------------
    def _writeTag(self, tagName, value):
        if tagName == "STATE_REQUEST":
            requestedState = int(value)
            self._ctx.set_value("STATE_REQUEST", requestedState)
            moveType = self._STATE_REQUEST_TO_MOVE_TYPE.get(requestedState)
            if requestedState == self.STATE_EOT:
                self._pending_state_request = requestedState
                self._pending_state_request_started = False
                return
            if moveType is not None:
                self._pending_state_request = requestedState
                self._pending_state_request_started = False
                return super()._writeTag("MOVE_TYPE", moveType)
            return
        return super()._writeTag(tagName, value)
