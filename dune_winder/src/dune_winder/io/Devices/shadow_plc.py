"""Shadow PLC mode: runs two LadderSimulatedPLC backends alongside the real
ControllogixPLC and logs logic-tag mismatches for simulator validation.

Three mismatch categories are written to ``shadow_plc_errors.log``:
  SHADOW_AST_MISMATCH   — real PLC disagrees with the AST executor
  SHADOW_IMP_MISMATCH   — real PLC disagrees with the imperative/Pythonic executor
  SHADOW_CROSS_MISMATCH — AST and imperative executors disagree with each other

All comparison work is dispatched to a single background thread so the real-
time poll cycle is never blocked.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .plc import PLC

_logger = logging.getLogger("dune_winder.shadow_plc")


def _values_match(a: Any, b: Any) -> bool:
  """Tolerant equality: float within 1e-4, everything else exact."""
  if isinstance(a, float) or isinstance(b, float):
    try:
      return abs(float(a) - float(b)) < 1e-4
    except (TypeError, ValueError):
      return False
  return a == b


class ShadowPLC(PLC):
  """Decorator that wraps a real PLC and runs two shadow simulators in parallel.

  The real PLC is the sole source of truth for all reads/writes.  Shadow
  simulators receive mirrored writes and, at the end of each poll cycle,
  have their physics inputs synchronised from the real PLC values before
  one ladder scan is executed.  Logic tag outputs are then compared and
  discrepancies logged.
  """

  # ------------------------------------------------------------------ #
  # Physics tags that are driven by hardware, not by ladder logic.
  # Synced FROM the real PLC INTO both shadow sims before each shadow
  # scan loop.  MACHINE_SW_STAT bits are included here because they come
  # from physical sensors in MainProgram/main — the shadow's
  # _sync_builtin_inputs() can only approximate them from positions.
  # Injecting them directly is more accurate and removes false positives.
  # ------------------------------------------------------------------ #
  _PHYSICS_TAGS = (
    [
      "X_axis.ActualPosition",
      "X_axis.ActualVelocity",
      "X_axis.CommandAcceleration",
      "X_axis.CoordinatedMotionStatus",
      "X_axis.DriveEnableStatus",
      "X_axis.ModuleFault",
      "X_axis.PhysicalAxisFault",
      "Y_axis.ActualPosition",
      "Y_axis.ActualVelocity",
      "Y_axis.CommandAcceleration",
      "Y_axis.CoordinatedMotionStatus",
      "Y_axis.DriveEnableStatus",
      "Y_axis.ModuleFault",
      "Y_axis.PhysicalAxisFault",
      "Z_axis.ActualPosition",
      "Z_axis.ActualVelocity",
      "Z_axis.CommandAcceleration",
      "Z_axis.CoordinatedMotionStatus",
      "Z_axis.DriveEnableStatus",
      "Z_axis.ModuleFault",
      "Z_axis.PhysicalAxisFault",
      "X_Y.MovePendingStatus",
      "X_Y.MovePendingQueueFullStatus",
      "X_Y.PhysicalAxisFault",
      "xz.MovePendingStatus",
      "xz.MovePendingQueueFullStatus",
      "xz.PhysicalAxisFault",
      "HEAD_POS",
      "ACTUATOR_POS",
      "tension",
      "v_xyz",
      "tension_motor_cv",
    ]
    + [f"MACHINE_SW_STAT[{i}]" for i in range(32)]
  )

  # ------------------------------------------------------------------ #
  # Logic tags compared after each shadow scan loop.
  # Motion instruction outputs, axis-drive fields, and MACHINE_SW_STAT
  # are deliberately excluded — those are hardware inputs, not outputs
  # of the ladder logic being validated.
  # ------------------------------------------------------------------ #
  _COMPARE_TAGS = [
    "STATE",
    "NEXTSTATE",
    "ERROR_CODE",
    "MOVE_TYPE",
    "QueueCount",
    "CurIssued",
    "NextIssued",
    "QueueFault",
    "FaultCode",
    "MotionFault",
  ]

  # Maximum number of shadow scan iterations per poll cycle.  The real
  # PLC runs at ~10 ms; Python polls at ~100 ms → up to ~10 real scans
  # per Python cycle.  15 gives a small headroom for transient bursts.
  _MAX_CATCHUP_SCANS = 15

  # ------------------------------------------------------------------
  def __init__(self, ipAddress: str, real, shadow_ast, shadow_imp):
    """
    Args:
      ipAddress:  Address string (passed through to real PLC; stored for
                  identification only).
      real:       ControllogixPLC instance — all external reads/writes go here.
      shadow_ast: LadderSimulatedPLC(routine_backend="ast")
      shadow_imp: LadderSimulatedPLC(routine_backend="imperative")
    """
    self._real = real
    self._shadow_ast = shadow_ast
    self._shadow_imp = shadow_imp

    self._cycle_lock = threading.Lock()
    self._pending_reads: dict[str, Any] = {}
    self._cycle_active = False

    self._executor = ThreadPoolExecutor(
      max_workers=1,
      thread_name_prefix="shadow_plc",
    )
    self._pending_future = None

    self._setup_file_handler()
    self._check_manifest_freshness()

  # ------------------------------------------------------------------ #
  # PLC abstract interface
  # ------------------------------------------------------------------ #

  def initialize(self) -> bool:
    return self._real.initialize()

  def isNotFunctional(self) -> bool:
    return self._real.isNotFunctional()

  def read(self, tag):
    """Read from real PLC; accumulate values for end-of-cycle comparison."""
    result = self._real.read(tag)
    if result is not None:
      with self._cycle_lock:
        for item in result:
          # result items are [name, value] (pycomm3 Tag objects or lists)
          self._pending_reads[str(item[0])] = item[1]
    return result

  def write(self, tag, data=None, typeName=None):
    """Write to real PLC; mirror the same write to both shadow sims."""
    result = self._real.write(tag, data, typeName)
    for shadow in (self._shadow_ast, self._shadow_imp):
      try:
        shadow.write(tag, data, typeName)
      except Exception:
        pass  # shadow write failures are non-fatal
    return result

  # ------------------------------------------------------------------ #
  # Scan-cycle hooks (detected by PLC.Tag.pollAll)
  # ------------------------------------------------------------------ #

  def begin_scan_cycle(self):
    """Called before the first batch read of a poll cycle."""
    with self._cycle_lock:
      self._pending_reads = {}
      self._cycle_active = True

  def end_scan_cycle(self):
    """Called after the last batch read.  Fires the background comparison."""
    with self._cycle_lock:
      if not self._cycle_active:
        return
      snapshot = dict(self._pending_reads)
      self._cycle_active = False

    # Skip this cycle if the previous comparison is still running to avoid
    # a growing backlog during sustained high-rate winding.
    if self._pending_future is not None and not self._pending_future.done():
      _logger.debug("Shadow: skipping cycle (previous comparison still running)")
      return

    self._pending_future = self._executor.submit(self._shadow_compare, snapshot)

  # ------------------------------------------------------------------ #
  # Background comparison logic
  # ------------------------------------------------------------------ #

  def _shadow_compare(self, snapshot: dict[str, Any]):
    try:
      for shadow in (self._shadow_ast, self._shadow_imp):
        self._sync_physics(shadow, snapshot)
        with shadow._lock:
          self._run_to_stable(shadow)
      self._compare_and_log(snapshot)
    except Exception:
      _logger.exception("Shadow scan failed; skipping this cycle")

  def _run_to_stable(self, shadow) -> None:
    """Run shadow scans until MOVE_TYPE clears and STATE stops changing.

    The real PLC may process a command write and complete a state
    transition within a single ~10 ms scan.  Running multiple shadow
    scans per Python poll cycle lets the shadow catch up with those
    rapid real-PLC transitions, reducing timing-window false positives.

    Caller must already hold shadow._lock.
    """
    prev_state = None
    for _ in range(self._MAX_CATCHUP_SCANS):
      shadow._apply_scan(advance_runtime=True)
      move_type = int(shadow._ctx.get_value("MOVE_TYPE"))
      state = int(shadow._ctx.get_value("STATE"))
      if move_type == 0 and state == prev_state:
        break
      prev_state = state

  def _sync_physics(self, shadow, snapshot: dict[str, Any]):
    """Inject hardware-driven tag values directly into the shadow tag store.

    Uses _ctx.set_value() rather than shadow.write() to bypass write
    side-effects (e.g. writing MOVE_TYPE triggers state transitions;
    writing HEAD_POS runs actuator validation).  MACHINE_SW_STAT bits
    are synced here rather than being approximated by
    _sync_builtin_inputs(), which removes the largest class of false
    positives from the comparison.
    """
    with shadow._lock:
      for tag_name in self._PHYSICS_TAGS:
        if tag_name in snapshot:
          try:
            shadow._ctx.set_value(tag_name, snapshot[tag_name])
          except Exception:
            pass  # unknown tag in this shadow instance — skip silently

  def _compare_and_log(self, snapshot: dict[str, Any]):
    """Read both shadows' post-scan values and log any mismatches."""
    ast_vals: dict[str, Any] = {}
    imp_vals: dict[str, Any] = {}

    with self._shadow_ast._lock:
      for tag in self._COMPARE_TAGS:
        try:
          ast_vals[tag] = self._shadow_ast._readTagValue(tag)
        except Exception:
          ast_vals[tag] = None

    with self._shadow_imp._lock:
      for tag in self._COMPARE_TAGS:
        try:
          imp_vals[tag] = self._shadow_imp._readTagValue(tag)
        except Exception:
          imp_vals[tag] = None

    n = 0
    for tag in self._COMPARE_TAGS:
      real = snapshot.get(tag)
      if real is None:
        continue  # tag not polled this cycle

      ast = ast_vals[tag]
      imp = imp_vals[tag]

      if not _values_match(real, ast):
        _logger.warning(
          "SHADOW_AST_MISMATCH tag=%s real=%r ast=%r", tag, real, ast
        )
        n += 1

      if not _values_match(real, imp):
        _logger.warning(
          "SHADOW_IMP_MISMATCH tag=%s real=%r imp=%r", tag, real, imp
        )
        n += 1

      if not _values_match(ast, imp):
        _logger.warning(
          "SHADOW_CROSS_MISMATCH tag=%s ast=%r imp=%r", tag, ast, imp
        )
        n += 1

    if n:
      _logger.info("Shadow cycle: %d mismatch(es)", n)
    else:
      _logger.debug("Shadow cycle: OK")

  # ------------------------------------------------------------------ #
  # Initialisation helpers
  # ------------------------------------------------------------------ #

  def _setup_file_handler(self):
    h = logging.FileHandler(
      "shadow_plc_errors.log", mode="a", encoding="utf-8"
    )
    h.setLevel(logging.WARNING)
    h.setFormatter(
      logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    _logger.addHandler(h)
    if not _logger.level:
      _logger.setLevel(logging.DEBUG)

  def _check_manifest_freshness(self):
    """Warn if any .rllscrap files have changed since the .rll files were
    last generated.  Advisory only — never prevents shadow from starting."""
    try:
      from dune_winder.plc_manifest import PlcManifest

      plc_root = self._shadow_ast._PLC_ROOT
      manifest = PlcManifest(plc_root)
      manifest.load()
      stale = [
        row
        for row in manifest.status()
        if row.category == "rllscrap"
        and row.state in ("modified", "missing", "new")
      ]
      for row in stale:
        _logger.warning(
          "Shadow: stale rllscrap for %s (state=%s) — "
          "shadow comparison may not reflect the current PLC program; "
          "run plc-rung-transform-hs to regenerate .rll files",
          row.location,
          row.state,
        )
      if not stale:
        _logger.info("Shadow: manifest OK — all rllscrap files are current")
    except Exception:
      _logger.debug(
        "Shadow: manifest check skipped (manifest not available)",
        exc_info=True,
      )
