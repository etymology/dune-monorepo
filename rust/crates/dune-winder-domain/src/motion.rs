use crate::types::{Mm, MmPerS, MmPerS2, MmPerS3, Vec2};
use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Error, PartialEq, Eq)]
#[error("invalid {kind} numeric code: {value} (allowed: {allowed})")]
pub struct InvalidCode {
    pub kind: &'static str,
    pub value: i32,
    pub allowed: &'static str,
}

/// PLC `MotionSeg.SegType` (SINT). Validated by the queued-motion ladder
/// to be exactly 1 (line) or 2 (arc).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum SegType {
    Line,
    Arc,
}

impl SegType {
    pub const fn code(self) -> i8 {
        match self {
            SegType::Line => 1,
            SegType::Arc => 2,
        }
    }
}

impl TryFrom<i8> for SegType {
    type Error = InvalidCode;
    fn try_from(value: i8) -> Result<Self, InvalidCode> {
        match value {
            1 => Ok(SegType::Line),
            2 => Ok(SegType::Arc),
            other => Err(InvalidCode {
                kind: "SegType",
                value: other.into(),
                allowed: "1 (line) | 2 (arc)",
            }),
        }
    }
}

impl From<SegType> for i8 {
    fn from(seg: SegType) -> i8 {
        seg.code()
    }
}

/// PLC `MotionSeg.TermType` (SINT). Ladder validates `0..=6`. Termination
/// types correspond to motion-controller termination behaviour; the PLC is
/// authoritative for what each numeric means.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct TermType(i8);

impl TermType {
    pub const MIN: i8 = 0;
    pub const MAX: i8 = 6;

    pub const fn code(self) -> i8 {
        self.0
    }
}

impl TryFrom<i8> for TermType {
    type Error = InvalidCode;
    fn try_from(value: i8) -> Result<Self, InvalidCode> {
        if (Self::MIN..=Self::MAX).contains(&value) {
            Ok(Self(value))
        } else {
            Err(InvalidCode {
                kind: "TermType",
                value: value.into(),
                allowed: "0..=6",
            })
        }
    }
}

impl From<TermType> for i8 {
    fn from(t: TermType) -> i8 {
        t.0
    }
}

/// PLC `MotionSeg.CircleType` (DINT). Ladder validates `0..=3`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct CircleType(i32);

impl CircleType {
    pub const MIN: i32 = 0;
    pub const MAX: i32 = 3;

    pub const fn code(self) -> i32 {
        self.0
    }
}

impl TryFrom<i32> for CircleType {
    type Error = InvalidCode;
    fn try_from(value: i32) -> Result<Self, InvalidCode> {
        if (Self::MIN..=Self::MAX).contains(&value) {
            Ok(Self(value))
        } else {
            Err(InvalidCode {
                kind: "CircleType",
                value,
                allowed: "0..=3",
            })
        }
    }
}

impl From<CircleType> for i32 {
    fn from(c: CircleType) -> i32 {
        c.0
    }
}

/// PLC `MotionSeg.Direction` (DINT). Ladder validates `0..=3`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Direction(i32);

impl Direction {
    pub const MIN: i32 = 0;
    pub const MAX: i32 = 3;

    pub const fn code(self) -> i32 {
        self.0
    }
}

impl TryFrom<i32> for Direction {
    type Error = InvalidCode;
    fn try_from(value: i32) -> Result<Self, InvalidCode> {
        if (Self::MIN..=Self::MAX).contains(&value) {
            Ok(Self(value))
        } else {
            Err(InvalidCode {
                kind: "Direction",
                value,
                allowed: "0..=3",
            })
        }
    }
}

impl From<Direction> for i32 {
    fn from(d: Direction) -> i32 {
        d.0
    }
}

/// Common motion parameters shared by line and arc segments. Field types
/// mirror the PLC `MotionSeg` UDT: `XY[2]`, `Speed`, `Accel`, `Decel`,
/// `JerkAccel`, `JerkDecel` are all REAL; `Seq` is DINT.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct LineSegment {
    pub end: Vec2,
    pub speed: MmPerS,
    pub accel: MmPerS2,
    pub decel: MmPerS2,
    pub jerk_accel: MmPerS3,
    pub jerk_decel: MmPerS3,
    pub term_type: TermType,
    pub seq: i32,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct ArcSegment {
    pub end: Vec2,
    pub via_center: Vec2,
    pub circle_type: CircleType,
    pub direction: Direction,
    pub speed: MmPerS,
    pub accel: MmPerS2,
    pub decel: MmPerS2,
    pub jerk_accel: MmPerS3,
    pub jerk_decel: MmPerS3,
    pub term_type: TermType,
    pub seq: i32,
}

/// A planned motion segment, in domain form. The `winder-plc` crate is
/// responsible for byte-blob encoding into the PLC `MotionSeg` UDT (offsets
/// per `dune_winder/plc/queued_motion/programTags.json`).
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum MotionSegment {
    Line(LineSegment),
    Arc(ArcSegment),
}

impl MotionSegment {
    pub const fn seg_type(&self) -> SegType {
        match self {
            MotionSegment::Line(_) => SegType::Line,
            MotionSegment::Arc(_) => SegType::Arc,
        }
    }

    pub const fn end(&self) -> Vec2 {
        match self {
            MotionSegment::Line(l) => l.end,
            MotionSegment::Arc(a) => a.end,
        }
    }

    pub const fn seq(&self) -> i32 {
        match self {
            MotionSegment::Line(l) => l.seq,
            MotionSegment::Arc(a) => a.seq,
        }
    }
}

/// A pose for absolute motion targets. `None` on an axis means "do not
/// command this axis". Mirrors `core.allium#MachinePose` minus focus.
#[derive(Debug, Clone, Copy, PartialEq, Default, Serialize, Deserialize)]
pub struct MachinePose {
    pub x: Option<Mm>,
    pub y: Option<Mm>,
    pub z: Option<Mm>,
}
