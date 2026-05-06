// snapshot() must reject Write-only tags.
use std::time::Duration;
use dune_plc_bus::schema::Tags;
use dune_plc_bus::{BusConfig, SimulatedDriver, TagBus};

fn main() {
    let bus = TagBus::new(Box::new(SimulatedDriver::new()), BusConfig::default());
    // STATE_REQUEST_ID is Write-only → snapshot must not type-check.
    let _ = bus.snapshot(Tags::STATE_REQUEST_ID);
    let _ = Duration::from_millis(0);
}
