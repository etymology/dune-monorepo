//! `dune_plc_bus` — typed, freshness-aware tag bus for the dune winder PLC.
//!
//! See `plans/propose-a-rewrite-of-melodic-dream.md` (Part 1) for the design
//! rationale. Phase A: bus + simulated driver + capability/freshness types.
//! PyO3 bindings and consumer migration land in follow-up changes.

pub mod bus;
pub mod capability;
pub mod driver;
pub mod drivers;
pub mod error;
pub mod metrics;
pub mod snapshot;
pub mod tag;
pub mod value_conv;

pub use bus::{BusConfig, TagBus, WriteOutcome};
pub use capability::{Capability, Read, Readable, ReadWrite, Writable, Write};
pub use driver::{Health, PlcDriver};
pub use drivers::SimulatedDriver;
pub use error::{DriverError, StaleReadError, WriteFailed};
pub use metrics::Metrics;
pub use snapshot::{CipType, Snapshot, Source, Tier, Value};
pub use tag::{ErasedTagId, TagId};
pub use value_conv::TagValue;

pub mod schema {
    include!(concat!(env!("OUT_DIR"), "/schema_generated.rs"));
}

#[cfg(feature = "pyo3")]
pub mod python;
