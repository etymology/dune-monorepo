use pyo3::prelude::*;

pub struct MotionController {
    pub motion_service: Py<PyAny>,
    pub goto_xy_func: Py<PyAny>,
    pub get_current_xy_position: Py<PyAny>,
    pub focus_wiggle_func: Py<PyAny>,
    pub focus_position_getter: Py<PyAny>,
    pub focus_range_getter: Py<PyAny>,
    pub focus_mm_per_quarter_us: f64,
    pub focus_x_mm_per_quarter_us: f64,
    pub use_manual_focus: bool,
    pub manual_focus_target: Option<i32>,
    pub layer: String,
}

impl MotionController {
    pub fn new(
        motion_service: Py<PyAny>,
        goto_xy_func: Py<PyAny>,
        get_current_xy_position: Py<PyAny>,
        focus_wiggle_func: Py<PyAny>,
        focus_position_getter: Py<PyAny>,
        focus_range_getter: Py<PyAny>,
        use_manual_focus: bool,
        manual_focus_target: Option<i32>,
        layer: String,
    ) -> Self {
        let focus_mm_per_quarter_us = 20.0 / 4000.0;
        let focus_x_mm_per_quarter_us = focus_mm_per_quarter_us / 3.0f64.sqrt();

        MotionController {
            motion_service,
            goto_xy_func,
            get_current_xy_position,
            focus_wiggle_func,
            focus_position_getter,
            focus_range_getter,
            focus_mm_per_quarter_us,
            focus_x_mm_per_quarter_us,
            use_manual_focus,
            manual_focus_target,
            layer,
        }
    }

    pub fn clone_with_gil(&self, py: Python<'_>) -> Self {
        MotionController {
            motion_service: self.motion_service.clone_ref(py),
            goto_xy_func: self.goto_xy_func.clone_ref(py),
            get_current_xy_position: self.get_current_xy_position.clone_ref(py),
            focus_wiggle_func: self.focus_wiggle_func.clone_ref(py),
            focus_position_getter: self.focus_position_getter.clone_ref(py),
            focus_range_getter: self.focus_range_getter.clone_ref(py),
            focus_mm_per_quarter_us: self.focus_mm_per_quarter_us,
            focus_x_mm_per_quarter_us: self.focus_x_mm_per_quarter_us,
            use_manual_focus: self.use_manual_focus,
            manual_focus_target: self.manual_focus_target,
            layer: self.layer.clone(),
        }
    }

    pub fn focus_wiggle_x_sign(&self) -> f64 {
        if self.layer == "U" {
            -1.0
        } else {
            1.0
        }
    }

    pub fn focus_to_x_delta_mm(&self, delta_focus_units: f64) -> f64 {
        delta_focus_units * self.focus_x_mm_per_quarter_us * self.focus_wiggle_x_sign()
    }

    pub fn get_focus_position(&self, py: Python<'_>) -> PyResult<i32> {
        let res = self.focus_position_getter.call0(py)?;
        res.extract::<i32>(py)
    }

    pub fn get_focus_bounds(&self, py: Python<'_>) -> PyResult<(i32, i32)> {
        let res = match self.focus_range_getter.call0(py) {
            Ok(res) => res,
            Err(_) => return Ok((4000, 8000)),
        };
        if res.is_none(py) {
            return Ok((4000, 8000));
        }
        let bounds = match res.extract::<(i32, i32)>(py) {
            Ok(b) => b,
            Err(_) => return Ok((4000, 8000)),
        };
        if bounds.0 > bounds.1 {
            return Ok((4000, 8000));
        }
        Ok(bounds)
    }

    pub fn clamp_focus_position(&self, py: Python<'_>, focus_position: i32) -> PyResult<i32> {
        let (low, high) = self.get_focus_bounds(py)?;
        Ok(focus_position.clamp(low, high))
    }

    pub fn active_focus_target(
        &self,
        py: Python<'_>,
        focus_target: Option<i32>,
    ) -> PyResult<Option<i32>> {
        if self.use_manual_focus {
            if let Some(target) = self.manual_focus_target {
                return Ok(Some(self.clamp_focus_position(py, target)?));
            } else {
                let current = self.get_focus_position(py)?;
                return Ok(Some(self.clamp_focus_position(py, current)?));
            }
        }
        if let Some(target) = focus_target {
            return Ok(Some(self.clamp_focus_position(py, target)?));
        }
        Ok(None)
    }

    pub fn apply_focus_wiggle_with_x_compensation(
        &self,
        py: Python<'_>,
        delta_focus: f64,
    ) -> PyResult<Option<f64>> {
        let commanded_delta = delta_focus as i32;
        self.focus_wiggle_func.call1(py, (commanded_delta,))?;
        if commanded_delta == 0 {
            return Ok(None);
        }

        let delta_x_mm = self.focus_to_x_delta_mm(commanded_delta as f64);

        let (cur_x, cur_y) = match self.get_current_xy_position.call0(py) {
            Ok(res) => res.extract::<(f64, f64)>(py)?,
            Err(e) => return Err(e),
        };

        let new_x = (cur_x + delta_x_mm * 10.0).round() / 10.0;

        let moved = match self.goto_xy_func.call1(py, (new_x, cur_y)) {
            Ok(res) => res.extract::<bool>(py).unwrap_or(false),
            Err(e) => return Err(e),
        };

        if !moved {
            return Ok(None);
        }

        let compensated_x = match self.get_current_xy_position.call0(py) {
            Ok(res) => res.extract::<(f64, f64)>(py)?.0,
            Err(_) => new_x,
        };

        Ok(Some(compensated_x))
    }

    pub fn goto_xy_with_reset_recovery(
        &self,
        py: Python<'_>,
        x_target: f64,
        y_target: f64,
        _context: &str,
    ) -> PyResult<bool> {
        let args = (x_target, y_target);

        let moved = match self.goto_xy_func.call1(py, args) {
            Ok(res) => res.extract::<bool>(py).unwrap_or(false),
            Err(_) => false,
        };

        if moved {
            return Ok(true);
        }

        let _ = self.motion_service.call_method0(py, "reset_plc");

        let retry = match self.goto_xy_func.call1(py, args) {
            Ok(res) => res.extract::<bool>(py).unwrap_or(false),
            Err(_) => false,
        };

        Ok(retry)
    }

    pub fn move_to_measurement_pose(
        &self,
        py: Python<'_>,
        x_target: f64,
        y_target: f64,
        focus_target: Option<i32>,
    ) -> PyResult<bool> {
        if let Some(clamped_focus) = self.active_focus_target(py, focus_target)? {
            let current_focus = self.get_focus_position(py)?;
            let delta_focus = clamped_focus - current_focus;
            if delta_focus != 0 {
                self.apply_focus_wiggle_with_x_compensation(py, delta_focus as f64)?;
            }
        }
        self.goto_xy_with_reset_recovery(py, x_target, y_target, "Measurement pose")
    }
}
