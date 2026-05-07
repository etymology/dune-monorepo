use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Error, PartialEq, Eq)]
#[error("unknown PLC numeric code: {kind} = {value}")]
pub struct UnknownCode {
    pub kind: &'static str,
    pub value: i32,
}

/// PLC `STATE` / `STATE_REQUEST` / `NEXTSTATE` numeric encoding.
///
/// Numeric values are authoritative per `specs/winder-states.allium#PLCMode`
/// and the checked-in PLC routine directories under `dune_winder/plc/state_*`.
/// Codes 2 and 4 are intentionally absent.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PlcMode {
    Init,
    Ready,
    XySeek,
    ZSeek,
    Latching,
    LatchHoming,
    LatchRelease,
    Unservo,
    Error,
    EotTrip,
    XzSeek,
    YzSeek,
    HmiStop,
}

impl PlcMode {
    pub const fn code(self) -> i32 {
        match self {
            PlcMode::Init => 0,
            PlcMode::Ready => 1,
            PlcMode::XySeek => 3,
            PlcMode::ZSeek => 5,
            PlcMode::Latching => 6,
            PlcMode::LatchHoming => 7,
            PlcMode::LatchRelease => 8,
            PlcMode::Unservo => 9,
            PlcMode::Error => 10,
            PlcMode::EotTrip => 11,
            PlcMode::XzSeek => 12,
            PlcMode::YzSeek => 13,
            PlcMode::HmiStop => 14,
        }
    }

    pub const ALL: [PlcMode; 13] = [
        PlcMode::Init,
        PlcMode::Ready,
        PlcMode::XySeek,
        PlcMode::ZSeek,
        PlcMode::Latching,
        PlcMode::LatchHoming,
        PlcMode::LatchRelease,
        PlcMode::Unservo,
        PlcMode::Error,
        PlcMode::EotTrip,
        PlcMode::XzSeek,
        PlcMode::YzSeek,
        PlcMode::HmiStop,
    ];
}

impl TryFrom<i32> for PlcMode {
    type Error = UnknownCode;

    fn try_from(value: i32) -> Result<Self, UnknownCode> {
        match value {
            0 => Ok(PlcMode::Init),
            1 => Ok(PlcMode::Ready),
            3 => Ok(PlcMode::XySeek),
            5 => Ok(PlcMode::ZSeek),
            6 => Ok(PlcMode::Latching),
            7 => Ok(PlcMode::LatchHoming),
            8 => Ok(PlcMode::LatchRelease),
            9 => Ok(PlcMode::Unservo),
            10 => Ok(PlcMode::Error),
            11 => Ok(PlcMode::EotTrip),
            12 => Ok(PlcMode::XzSeek),
            13 => Ok(PlcMode::YzSeek),
            14 => Ok(PlcMode::HmiStop),
            _ => Err(UnknownCode {
                kind: "PlcMode",
                value,
            }),
        }
    }
}

impl From<PlcMode> for i32 {
    fn from(mode: PlcMode) -> i32 {
        mode.code()
    }
}

/// Legacy `MOVE_TYPE` reset-path encoding. Each non-zero value triggers a
/// pre-canned `STATE_REQUEST` write in the PLC's reset routine. Numeric
/// values are confirmed against `dune_winder/plc/enqueueRoutineStateful`
/// and `state_*/` ladder routines.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MoveType {
    /// Cleared / no command pending.
    None,
    /// 1 → STATE_REQUEST=2 (legacy reset → ready handshake).
    LegacyResetReady,
    /// 2 → STATE_REQUEST=3 (xy_seek).
    LegacyXySeek,
    /// 4 → STATE_REQUEST=5 (z_seek).
    LegacyZSeek,
    /// 5 → STATE_REQUEST=6 (latching).
    LegacyLatching,
    /// 8 → STATE_REQUEST=9 (unservo).
    LegacyUnservo,
    /// 9 → NEXTSTATE=0 (force re-init).
    LegacyForceInit,
    /// 11 → AbortQueue + NEXTSTATE=14 (HMI stop / queued abort).
    AbortHmiStop,
}

impl MoveType {
    pub const fn code(self) -> i32 {
        match self {
            MoveType::None => 0,
            MoveType::LegacyResetReady => 1,
            MoveType::LegacyXySeek => 2,
            MoveType::LegacyZSeek => 4,
            MoveType::LegacyLatching => 5,
            MoveType::LegacyUnservo => 8,
            MoveType::LegacyForceInit => 9,
            MoveType::AbortHmiStop => 11,
        }
    }

    pub const ALL: [MoveType; 8] = [
        MoveType::None,
        MoveType::LegacyResetReady,
        MoveType::LegacyXySeek,
        MoveType::LegacyZSeek,
        MoveType::LegacyLatching,
        MoveType::LegacyUnservo,
        MoveType::LegacyForceInit,
        MoveType::AbortHmiStop,
    ];
}

impl TryFrom<i32> for MoveType {
    type Error = UnknownCode;

    fn try_from(value: i32) -> Result<Self, UnknownCode> {
        match value {
            0 => Ok(MoveType::None),
            1 => Ok(MoveType::LegacyResetReady),
            2 => Ok(MoveType::LegacyXySeek),
            4 => Ok(MoveType::LegacyZSeek),
            5 => Ok(MoveType::LegacyLatching),
            8 => Ok(MoveType::LegacyUnservo),
            9 => Ok(MoveType::LegacyForceInit),
            11 => Ok(MoveType::AbortHmiStop),
            _ => Err(UnknownCode {
                kind: "MoveType",
                value,
            }),
        }
    }
}

impl From<MoveType> for i32 {
    fn from(move_type: MoveType) -> i32 {
        move_type.code()
    }
}

/// PLC `ACTUATOR_POS` rocker encoding (single rocker, three sensor-derived
/// stable positions plus a transition). Per
/// `specs/winder-states.allium#ActuatorPosition` (mirrored to `enum`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ActuatorPosition {
    /// 0: TOP=0, MID=0, Z_STAGE_LATCHED not yet asserted.
    TransitionEngaged,
    /// 1: Z_STAGE_LATCHED sensor asserted (stable).
    StageLatched,
    /// 2: TOP=1, MID=1 — safe withdrawal point.
    MidEngagement,
    /// 3: TOP=1, MID=0 — rocker pushed to fixed side.
    RockerAtFixed,
}

impl ActuatorPosition {
    pub const fn code(self) -> i32 {
        match self {
            ActuatorPosition::TransitionEngaged => 0,
            ActuatorPosition::StageLatched => 1,
            ActuatorPosition::MidEngagement => 2,
            ActuatorPosition::RockerAtFixed => 3,
        }
    }

    pub const ALL: [ActuatorPosition; 4] = [
        ActuatorPosition::TransitionEngaged,
        ActuatorPosition::StageLatched,
        ActuatorPosition::MidEngagement,
        ActuatorPosition::RockerAtFixed,
    ];
}

impl TryFrom<i32> for ActuatorPosition {
    type Error = UnknownCode;

    fn try_from(value: i32) -> Result<Self, UnknownCode> {
        match value {
            0 => Ok(ActuatorPosition::TransitionEngaged),
            1 => Ok(ActuatorPosition::StageLatched),
            2 => Ok(ActuatorPosition::MidEngagement),
            3 => Ok(ActuatorPosition::RockerAtFixed),
            _ => Err(UnknownCode {
                kind: "ActuatorPosition",
                value,
            }),
        }
    }
}

impl From<ActuatorPosition> for i32 {
    fn from(pos: ActuatorPosition) -> i32 {
        pos.code()
    }
}
