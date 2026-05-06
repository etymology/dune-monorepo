//! Cached values, freshness, and CIP value model.

use std::time::{Duration, Instant};

/// CIP wire types we care about.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum CipType {
    Bool,
    Sint,
    Int,
    Dint,
    Real,
    RealArray2,
    RealArray3,
}

/// Polling tier. Determines default cadence; subscribers can demand fresher.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Tier {
    Critical,
    High,
    Normal,
    Slow,
    OnDemand,
}

impl Tier {
    pub fn default_period(self) -> Option<Duration> {
        match self {
            Tier::Critical => Some(Duration::from_millis(20)),
            Tier::High => Some(Duration::from_millis(50)),
            Tier::Normal => Some(Duration::from_millis(200)),
            Tier::Slow => Some(Duration::from_millis(1000)),
            Tier::OnDemand => None,
        }
    }
}

/// Where a cached value came from.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Source {
    /// Default value installed at bus construction; never seen the wire.
    Default,
    /// Confirmed by a successful PLC read.
    Plc,
    /// Optimistic local update following a successful write; awaits poll confirmation.
    WriteEcho,
    /// Last-known value, but driver is currently failed; do not trust.
    Stale,
}

/// Untyped cached value with provenance.
#[derive(Debug, Clone)]
pub struct Snapshot<T> {
    pub value: T,
    pub at: Instant,
    pub sequence: u64,
    pub source: Source,
}

impl<T> Snapshot<T> {
    pub fn age(&self) -> Duration {
        Instant::now().duration_since(self.at)
    }

    pub fn is_fresh_within(&self, max_age: Duration) -> bool {
        matches!(self.source, Source::Plc | Source::WriteEcho) && self.age() <= max_age
    }
}

/// Dynamic value carried across the driver boundary.
#[derive(Debug, Clone, PartialEq)]
pub enum Value {
    Bool(bool),
    Sint(i8),
    Int(i16),
    Dint(i32),
    Real(f32),
    RealArray2([f32; 2]),
    RealArray3([f32; 3]),
}

impl Value {
    pub fn cip_type(&self) -> CipType {
        match self {
            Value::Bool(_) => CipType::Bool,
            Value::Sint(_) => CipType::Sint,
            Value::Int(_) => CipType::Int,
            Value::Dint(_) => CipType::Dint,
            Value::Real(_) => CipType::Real,
            Value::RealArray2(_) => CipType::RealArray2,
            Value::RealArray3(_) => CipType::RealArray3,
        }
    }
}
