//! Pure domain types for the DUNE winder host.
//!
//! All PLC numeric encodings live here, grounded in the Allium specs
//! (`specs/winder-states.allium`, `specs/winder-hardware-interfaces.allium`,
//! `specs/core.allium`) and the PLC tag layout under `dune_winder/plc/`.

pub mod motion;
pub mod state;
pub mod tag;
pub mod types;

pub use motion::{
    ArcSegment, CircleType, Direction, LineSegment, MotionSegment, SegType, TermType,
};
pub use state::{ActuatorPosition, MoveType, PlcMode};
pub use tag::TagPath;
pub use types::{Layer, Mm, MmPerS, MmPerS2, MmPerS3, PinName, PinSide, Vec2};
