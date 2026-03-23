from __future__ import annotations

import argparse

from dune_winder.io.devices.ladder_simulated_plc import LadderSimulatedPLC


def _advance(plc: LadderSimulatedPLC, scans: int = 1):
  for _ in range(scans):
    plc.read("STATE")


def _advance_until(plc: LadderSimulatedPLC, predicate, limit: int = 200):
  for _ in range(limit):
    plc.read("STATE")
    if predicate():
      return True
  return False


def _snapshot(plc: LadderSimulatedPLC):
  return {
    "STATE": plc.get_tag("STATE"),
    "NEXTSTATE": plc.get_tag("NEXTSTATE"),
    "MOVE_TYPE": plc.get_tag("MOVE_TYPE"),
    "ERROR_CODE": plc.get_tag("ERROR_CODE"),
    "MASTER_Z_GO": plc.get_tag("MASTER_Z_GO"),
    "STATE5_IND": plc.get_tag("STATE5_IND"),
    "prepare_to_move": plc.get_tag("prepare_to_move"),
    "wait_for_mso": plc.get_tag("wait_for_mso"),
    "trigger_z_move": plc.get_tag("trigger_z_move"),
    "Z_drive": plc.get_tag("Z_axis.DriveEnableStatus"),
    "z_move_ip": plc.get_tag("z_axis_main_move.IP"),
    "z_move_pc": plc.get_tag("z_axis_main_move.PC"),
    "z_move_success": plc.get_tag("z_move_success"),
    "Z_position": plc.get_tag("Z_axis.ActualPosition"),
  }


def _case_seek_success():
  plc = LadderSimulatedPLC("SIM")
  plc.write(("Z_POSITION", 43.0))
  plc.write(("Z_SPEED", 100.0))
  plc.write(("MOVE_TYPE", plc.MOVE_SEEK_Z))
  _advance_until(plc, lambda: plc.get_tag("STATE") == plc.STATE_READY)
  return plc


def _case_blocked_tension_gate():
  plc = LadderSimulatedPLC("SIM")
  plc.set_tag("tension_stable_tolerance", 0.0)
  plc.write(("Z_POSITION", 43.0))
  plc.write(("Z_SPEED", 100.0))
  plc.write(("MOVE_TYPE", plc.MOVE_SEEK_Z))
  _advance(plc, 10)
  return plc


def _case_blocked_master_z_go():
  plc = LadderSimulatedPLC("SIM")
  plc.set_tag("MACHINE_SW_STAT[15]", 0, override=True)
  plc.set_tag("MACHINE_SW_STAT[17]", 0, override=True)
  plc.write(("Z_POSITION", 43.0))
  plc.write(("Z_SPEED", 100.0))
  plc.write(("MOVE_TYPE", plc.MOVE_SEEK_Z))
  _advance(plc, 3)
  return plc


def _case_blocked_axis_enable():
  plc = LadderSimulatedPLC("SIM")
  plc.set_tag("check_tension_stable", False)
  plc.set_tag("APA_IS_VERTICAL", False, override=True)
  plc.write(("Z_POSITION", 43.0))
  plc.write(("Z_SPEED", 100.0))
  plc.write(("MOVE_TYPE", plc.MOVE_SEEK_Z))
  _advance(plc, 10)
  return plc


def _case_completion_stuck_state5():
  plc = LadderSimulatedPLC("SIM")
  plc.set_tag("check_tension_stable", False)
  plc.write(("Z_POSITION", 43.0))
  plc.write(("Z_SPEED", 10.0))
  plc.write(("MOVE_TYPE", plc.MOVE_SEEK_Z))
  _advance_until(plc, lambda: plc.get_tag("z_axis_main_move.IP"))
  plc.set_tag("check_tension_stable", True)
  plc.set_tag("tension_stable_tolerance", 0.0)
  _advance_until(plc, lambda: plc.get_tag("z_axis_main_move.PC"))
  _advance(plc, 5)
  return plc


def _case_jog_oscillation():
  plc = LadderSimulatedPLC("SIM")
  plc.write(("Z_SPEED", 100.0))
  plc.write(("Z_DIR", 0))
  plc.write(("MOVE_TYPE", plc.MOVE_JOG_Z))
  _advance(plc, 6)
  return plc


CASES = {
  "seek_success": _case_seek_success,
  "blocked_tension_gate": _case_blocked_tension_gate,
  "blocked_master_z_go": _case_blocked_master_z_go,
  "blocked_axis_enable": _case_blocked_axis_enable,
  "completion_stuck_state5": _case_completion_stuck_state5,
  "jog_oscillation": _case_jog_oscillation,
}


def main():
  parser = argparse.ArgumentParser(description="Diagnose Z move ladder paths in the ladder simulator.")
  parser.add_argument(
    "--case",
    choices=["all", *CASES.keys()],
    default="all",
    help="Run one diagnostic case or all cases.",
  )
  args = parser.parse_args()

  names = list(CASES) if args.case == "all" else [args.case]
  for name in names:
    plc = CASES[name]()
    print(f"[{name}]")
    for key, value in _snapshot(plc).items():
      print(f"{key}={value}")
    print()


if __name__ == "__main__":
  main()
