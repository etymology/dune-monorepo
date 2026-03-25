import os


VALID_PLC_MODES = ("REAL", "SIM")
VALID_PLC_SIM_ENGINES = ("LEGACY", "LADDER")


def normalize_plc_mode(plcMode):
  mode = str(plcMode).strip().upper()
  if mode not in VALID_PLC_MODES:
    raise ValueError("PLC mode must be REAL or SIM.")
  return mode


def normalize_plc_sim_engine(plcSimEngine):
  engine = str(plcSimEngine).strip().upper()
  if engine not in VALID_PLC_SIM_ENGINES:
    raise ValueError(
      "PLC simulator engine must be LEGACY or LADDER."
    )
  return engine


def resolve_plc_sim_engine(configuredEngine="LEGACY", envOverride=None):
  override = envOverride
  if override is None:
    override = os.environ.get("PLC_SIM_ENGINE")
  source = override if override is not None else configuredEngine
  return normalize_plc_sim_engine(source)


def create_sim_plc_backend(plcAddress="SIM", plcSimEngine="LEGACY"):
  engine = normalize_plc_sim_engine(plcSimEngine)
  if engine == "LADDER":
    from dune_winder.io.devices.ladder_simulated_plc import LadderSimulatedPLC

    return LadderSimulatedPLC(plcAddress)

  from dune_winder.io.devices.simulated_plc import SimulatedPLC

  return SimulatedPLC(plcAddress)


def create_shadow_plc_backend(plcAddress):
  """Wrap a real ControllogixPLC with two shadow LadderSimulatedPLC backends."""
  from dune_winder.io.devices.controllogix_plc import ControllogixPLC
  from dune_winder.io.devices.ladder_simulated_plc import LadderSimulatedPLC
  from dune_winder.io.devices.shadow_plc import ShadowPLC

  real = ControllogixPLC(plcAddress)
  shadow_ast = LadderSimulatedPLC("SHADOW_AST", routine_backend="ast")
  shadow_imp = LadderSimulatedPLC("SHADOW_IMP", routine_backend="imperative")
  return ShadowPLC(plcAddress, real, shadow_ast, shadow_imp)


def create_plc_backend(
  plcAddress, plcMode="REAL", plcSimEngine="LEGACY", plcShadowMode=False
):
  mode = normalize_plc_mode(plcMode)
  if mode == "SIM":
    return create_sim_plc_backend(plcAddress, plcSimEngine=plcSimEngine)

  if plcShadowMode:
    return create_shadow_plc_backend(plcAddress)

  from dune_winder.io.devices.controllogix_plc import ControllogixPLC

  return ControllogixPLC(plcAddress)


def create_plc_backend_for_path(path, plcSimEngine="LEGACY"):
  if str(path).strip().upper() == "SIM":
    return create_sim_plc_backend("SIM", plcSimEngine=plcSimEngine)
  return create_plc_backend(path, plcMode="REAL", plcSimEngine=plcSimEngine)
