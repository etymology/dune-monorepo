// write() must reject Read-only tags.
use std::time::Duration;
use dune_plc_bus::schema::Tags;
use dune_plc_bus::{BusConfig, SimulatedDriver, TagBus};

fn main() {
    let bus = TagBus::new(Box::new(SimulatedDriver::new()), BusConfig::default());
    // STATE is Read-only → write must not type-check.
    let _ = bus.write(Tags::STATE, 1, Duration::from_millis(50));
}
