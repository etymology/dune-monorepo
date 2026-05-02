//! `PlcDriver` trait — pure I/O, no state.

use std::collections::HashMap;
use std::time::Instant;

use crate::error::DriverError;
use crate::snapshot::Value;

#[derive(Debug, Clone)]
pub struct Health {
    pub connected: bool,
    pub last_ok: Option<Instant>,
    pub last_error: Option<String>,
    pub consecutive_failures: u32,
}

impl Default for Health {
    fn default() -> Self {
        Self {
            connected: false,
            last_ok: None,
            last_error: None,
            consecutive_failures: 0,
        }
    }
}

pub trait PlcDriver: Send {
    fn connect(&mut self) -> Result<(), DriverError>;
    fn disconnect(&mut self);
    fn health(&self) -> Health;
    fn read(&mut self, names: &[&str]) -> Result<HashMap<String, Value>, DriverError>;
    fn write(&mut self, updates: &[(&str, Value)]) -> Result<HashMap<String, bool>, DriverError>;
}
