//! End-to-end exercises of the bus against the in-process simulator.

use std::thread;
use std::time::Duration;

use dune_plc_bus::schema::Tags;
use dune_plc_bus::{BusConfig, SimulatedDriver, Source, TagBus, Value};

fn fresh_bus() -> (TagBus, SimulatedDriver) {
    let driver = SimulatedDriver::new();
    let bus = TagBus::new(
        Box::new(driver.clone()),
        BusConfig {
            tick: Duration::from_millis(2),
            max_batch: 14,
            default_write_timeout: Duration::from_millis(100),
            reconnect_backoff: Duration::from_millis(50),
        },
    );
    (bus, driver)
}

#[test]
fn snapshot_returns_default_before_poll() {
    let (bus, _drv) = fresh_bus();
    let s = bus.snapshot(Tags::STATE);
    assert_eq!(s.value, 0);
    assert_eq!(s.source, Source::Default);
}

#[test]
fn read_fresh_pulls_through_driver() {
    let (bus, drv) = fresh_bus();
    drv.poke("STATE", Value::Dint(7));
    bus.start();

    let snap = bus
        .read_fresh(Tags::STATE, Duration::from_millis(50), Duration::from_millis(500))
        .expect("read should succeed");
    assert_eq!(snap.value, 7);
    assert_eq!(snap.source, Source::Plc);
}

#[test]
fn write_updates_cache_with_write_echo() {
    let (bus, drv) = fresh_bus();
    bus.start();
    bus.write(Tags::STATE_REQUEST, 3, Duration::from_millis(100))
        .expect("write");
    let snap = bus.snapshot(Tags::STATE_REQUEST);
    assert_eq!(snap.value, 3);
    assert_eq!(snap.source, Source::WriteEcho);
    assert_eq!(drv.peek("STATE_REQUEST"), Some(Value::Dint(3)));
}

#[test]
fn read_fresh_returns_no_value_when_driver_failed() {
    let (bus, drv) = fresh_bus();
    drv.set_failed(true);
    bus.start();
    let err = bus
        .read_fresh(Tags::STATE, Duration::from_millis(20), Duration::from_millis(100))
        .expect_err("should fail");
    let msg = err.to_string();
    assert!(msg.contains("STATE"), "{msg}");
}

#[test]
fn read_fresh_recovers_after_failure_clears() {
    let (bus, drv) = fresh_bus();
    drv.set_failed(true);
    bus.start();
    let _ = bus.read_fresh(
        Tags::STATE,
        Duration::from_millis(20),
        Duration::from_millis(100),
    );
    drv.set_failed(false);
    drv.poke("STATE", Value::Dint(5));
    // Allow poll thread to recover.
    thread::sleep(Duration::from_millis(50));
    let snap = bus
        .read_fresh(Tags::STATE, Duration::from_millis(50), Duration::from_millis(500))
        .expect("read after recovery");
    assert_eq!(snap.value, 5);
}

#[test]
fn subscribe_increases_poll_cadence() {
    let (bus, drv) = fresh_bus();
    drv.poke("X_axis.ActualPosition", Value::Real(1.0));
    bus.subscribe(Tags::X_AXIS_ACTUALPOSITION, Duration::from_millis(10));
    bus.start();
    thread::sleep(Duration::from_millis(120));
    let n = drv.read_calls();
    // With 10 ms cadence over ~120 ms, expect at least ~5 driver reads (not just 0/1).
    assert!(n >= 4, "expected several polls, got {n}");
}

#[test]
fn metrics_count_reads_and_writes() {
    let (bus, drv) = fresh_bus();
    drv.poke("STATE", Value::Dint(1));
    bus.start();
    let _ = bus.read_fresh(
        Tags::STATE,
        Duration::from_millis(50),
        Duration::from_millis(500),
    );
    bus.write(Tags::STATE_REQUEST, 2, Duration::from_millis(100))
        .unwrap();
    let m = bus.metrics();
    assert!(m.reads() >= 1);
    assert!(m.writes() >= 1);
}
