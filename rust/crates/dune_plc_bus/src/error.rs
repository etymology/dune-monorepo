use std::time::Duration;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum DriverError {
    #[error("driver not connected")]
    NotConnected,
    #[error("driver I/O failure: {0}")]
    Io(String),
    #[error("unknown tag: {0}")]
    UnknownTag(String),
    #[error("type mismatch on tag {tag}: expected {expected:?}, got {actual:?}")]
    TypeMismatch {
        tag: String,
        expected: crate::snapshot::CipType,
        actual: crate::snapshot::CipType,
    },
}

#[derive(Debug, Error)]
pub enum StaleReadError {
    #[error("tag {tag} has no fresh value within {max_age:?}")]
    StaleAfter { tag: &'static str, max_age: Duration },
    #[error("tag {tag} timed out waiting for fresh read after {timeout:?}")]
    TimedOut {
        tag: &'static str,
        timeout: Duration,
    },
    #[error("tag {tag} has no value yet (driver disconnected)")]
    NoValue { tag: &'static str },
    #[error("driver error reading {tag}: {source}")]
    Driver {
        tag: &'static str,
        #[source]
        source: DriverError,
    },
}

#[derive(Debug, Error)]
pub enum WriteFailed {
    #[error("write to {tag} timed out after {timeout:?}")]
    TimedOut {
        tag: &'static str,
        timeout: Duration,
    },
    #[error("driver error writing {tag}: {source}")]
    Driver {
        tag: &'static str,
        #[source]
        source: DriverError,
    },
    #[error("PLC rejected write to {tag}")]
    Rejected { tag: &'static str },
}
