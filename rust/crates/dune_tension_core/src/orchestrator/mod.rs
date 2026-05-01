pub mod models;

use crate::config::TensiometerConfig;
use crate::motion::MotionController;
use crate::utils::check_stop_event;
use models::PlannedWirePose;
use pyo3::prelude::*;
use pyo3::types::PyDict;

pub struct MeasurementOrchestrator {
    pub motion: MotionController,
    pub config: TensiometerConfig,
    pub py_config: Py<PyAny>,
    pub stop_event: Option<Py<PyAny>>,
    pub wire_position_provider: Py<PyAny>,
}

impl MeasurementOrchestrator {
    pub fn new(
        motion: MotionController,
        config: TensiometerConfig,
        py_config: Py<PyAny>,
        stop_event: Option<Py<PyAny>>,
        wire_position_provider: Py<PyAny>,
    ) -> Self {
        MeasurementOrchestrator {
            motion,
            config,
            py_config,
            stop_event,
            wire_position_provider,
        }
    }

    pub fn plan_batch_measurement_pose(
        &self,
        py: Python<'_>,
        wire_number: i32,
    ) -> PyResult<Option<PlannedWirePose>> {
        if self.config.layer == "U" || self.config.layer == "V" {
            let focus = self.motion.get_focus_position(py)?;
            let pose_obj = self.wire_position_provider.call_method1(
                py,
                "get_pose",
                (self.py_config.clone_ref(py), wire_number, focus),
            )?;
            if pose_obj.is_none(py) {
                return Ok(None);
            }
            return Ok(Some(PlannedWirePose::from_py(py, pose_obj)?));
        }

        // TODO: Port plan_auto_measurement_pose for X/G
        Ok(None)
    }

    pub fn measure_auto(&self, py: Python<'_>) -> PyResult<()> {
        println!(
            "Rust Orchestrator: measure_auto starting for apa={} layer={} side={}",
            self.config.apa_name, self.config.layer, self.config.side
        );

        let summaries = py.import("dune_tension.summaries")?;
        let get_missing_wires = summaries.getattr("get_missing_wires")?;
        let wires_dict_obj = get_missing_wires.call1((self.py_config.clone_ref(py),))?;
        let wires_dict = wires_dict_obj.downcast::<PyDict>()?;

        let side_key = self.config.side.clone();
        let wires_to_measure: Vec<i32> = match wires_dict.get_item(side_key)? {
            Some(wires) => wires.extract()?,
            None => {
                println!("All wires are already measured.");
                return Ok(());
            }
        };

        if wires_to_measure.is_empty() {
            println!("All wires are already measured.");
            return Ok(());
        }

        println!("Missing wires: {:?}", wires_to_measure);

        for wire_number in wires_to_measure {
            if check_stop_event(py, &self.stop_event) {
                return Ok(());
            }

            println!("Measuring wire {}", wire_number);

            let target = self.plan_batch_measurement_pose(py, wire_number)?;
            if let Some(t) = target {
                println!(
                    "Target pose: x={}, y={}, focus={:?}",
                    t.x, t.y, t.focus_position
                );
                // self.goto_collect_wire_data(...)
            } else {
                println!("No target pose found for wire {}", wire_number);
            }
        }

        Ok(())
    }
}
