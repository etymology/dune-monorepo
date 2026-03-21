"""Opt-in ladder-backed simulator entry point.

This starts as a thin compatibility wrapper so plumbing can select between the
legacy and ladder simulator engines without changing the public PLC interface.
Later commits replace the inherited behavior with the ladder runtime.
"""

from .simulated_plc import SimulatedPLC


class LadderSimulatedPLC(SimulatedPLC):
  def _statusSnapshot(self):
    status = dict(super()._statusSnapshot())
    status["simEngine"] = "LADDER"
    return status
