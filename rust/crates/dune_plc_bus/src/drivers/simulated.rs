//! In-process simulator. Used by tests and the bench setup.
//!
//! Holds a tag → Value map under a mutex. `read` returns whatever's set;
//! `write` stores. Connection failure can be injected via `set_failed`.
//!
//! This is *not* a port of the full `simulated_plc.py` ladder semantics — that
//! port lands in a follow-up so the existing `G206TransferLadderTests` can run
//! against the new bus. For Phase A bring-up, the simple store is enough to
//! exercise scheduling, coalescing, and freshness.

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

use parking_lot::Mutex;

use crate::driver::{Health, PlcDriver};
use crate::error::DriverError;
use crate::snapshot::Value;

#[derive(Default)]
struct Inner {
    store: HashMap<String, Value>,
    failed: bool,
    health: Health,
    read_calls: u64,
    write_calls: u64,
}

#[derive(Clone, Default)]
pub struct SimulatedDriver {
    inner: Arc<Mutex<Inner>>,
}

impl SimulatedDriver {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn preload<I>(&self, entries: I)
    where
        I: IntoIterator<Item = (String, Value)>,
    {
        let mut g = self.inner.lock();
        for (k, v) in entries {
            g.store.insert(k, v);
        }
    }

    pub fn set_failed(&self, failed: bool) {
        let mut g = self.inner.lock();
        g.failed = failed;
        if failed {
            g.health.connected = false;
            g.health.consecutive_failures = g.health.consecutive_failures.saturating_add(1);
            g.health.last_error = Some("injected failure".into());
        } else {
            g.health.connected = true;
            g.health.consecutive_failures = 0;
            g.health.last_error = None;
        }
    }

    pub fn read_calls(&self) -> u64 {
        self.inner.lock().read_calls
    }

    pub fn write_calls(&self) -> u64 {
        self.inner.lock().write_calls
    }

    pub fn poke(&self, name: &str, value: Value) {
        self.inner.lock().store.insert(name.to_string(), value);
    }

    pub fn peek(&self, name: &str) -> Option<Value> {
        self.inner.lock().store.get(name).cloned()
    }
}

impl PlcDriver for SimulatedDriver {
    fn connect(&mut self) -> Result<(), DriverError> {
        let mut g = self.inner.lock();
        if g.failed {
            return Err(DriverError::NotConnected);
        }
        g.health.connected = true;
        g.health.last_ok = Some(Instant::now());
        Ok(())
    }

    fn disconnect(&mut self) {
        let mut g = self.inner.lock();
        g.health.connected = false;
    }

    fn health(&self) -> Health {
        self.inner.lock().health.clone()
    }

    fn read(&mut self, names: &[&str]) -> Result<HashMap<String, Value>, DriverError> {
        let mut g = self.inner.lock();
        if g.failed {
            g.health.consecutive_failures = g.health.consecutive_failures.saturating_add(1);
            return Err(DriverError::Io("driver failed".into()));
        }
        g.read_calls += 1;
        let mut out = HashMap::with_capacity(names.len());
        for name in names {
            if let Some(v) = g.store.get(*name).cloned() {
                out.insert((*name).to_string(), v);
            }
        }
        g.health.last_ok = Some(Instant::now());
        g.health.consecutive_failures = 0;
        Ok(out)
    }

    fn write(&mut self, updates: &[(&str, Value)]) -> Result<HashMap<String, bool>, DriverError> {
        let mut g = self.inner.lock();
        if g.failed {
            g.health.consecutive_failures = g.health.consecutive_failures.saturating_add(1);
            return Err(DriverError::Io("driver failed".into()));
        }
        g.write_calls += 1;
        let mut out = HashMap::with_capacity(updates.len());
        for (name, v) in updates {
            g.store.insert((*name).to_string(), v.clone());
            out.insert((*name).to_string(), true);
        }
        g.health.last_ok = Some(Instant::now());
        g.health.consecutive_failures = 0;
        Ok(out)
    }
}
