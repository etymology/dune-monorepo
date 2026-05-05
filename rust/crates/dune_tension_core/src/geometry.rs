pub struct Geometry {
    pub measurable_x_min: f64,
    pub measurable_x_max: f64,
    pub measurable_y_min: f64,
    pub measurable_y_max: f64,
    pub comb_positions: Vec<f64>,
    pub refine_search_steps: i32,
    pub refine_clearance_threshold: f64,
}

impl Geometry {
    pub fn new() -> Self {
        Geometry {
            measurable_x_min: 1050.0,
            measurable_x_max: 7015.0,
            measurable_y_min: 330.0,
            measurable_y_max: 2700.0,
            comb_positions: vec![1050.0, 2230.0, 3420.0, 4590.0, 5770.0, 7015.0],
            refine_search_steps: 300,
            refine_clearance_threshold: 400.0,
        }
    }

    pub fn is_in_bounds(&self, x: f64, y: f64) -> bool {
        x >= self.measurable_x_min
            && x <= self.measurable_x_max
            && y >= self.measurable_y_min
            && y <= self.measurable_y_max
    }

    pub fn score(&self, x: f64, y: f64) -> f64 {
        let mut min_dist = f64::INFINITY;
        for &c in &self.comb_positions {
            let dist = (x - c).abs();
            if dist < min_dist {
                min_dist = dist;
            }
        }
        let dist_y_max = (y - self.measurable_y_max).abs();
        if dist_y_max < min_dist {
            min_dist = dist_y_max;
        }
        let dist_y_min = (y - self.measurable_y_min).abs();
        if dist_y_min < min_dist {
            min_dist = dist_y_min;
        }
        min_dist
    }

    pub fn refine_position(&self, x: f64, y: f64, dx: f64, dy: f64) -> (f64, f64) {
        let mut candidates = Vec::new();
        for n in 0..self.refine_search_steps {
            let n_f = n as f64;
            let x1 = x + n_f * dx;
            let y1 = y - n_f * dy;
            let x2 = x - n_f * dx;
            let y2 = y + n_f * dy;

            if self.is_in_bounds(x1, y1) {
                candidates.push((x1, y1));
            }
            if self.is_in_bounds(x2, y2) {
                candidates.push((x2, y2));
            }
        }

        if candidates.is_empty() {
            return (x, y);
        }

        let low_candidates: Vec<(f64, f64)> = candidates
            .iter()
            .cloned()
            .filter(|&(cx, cy)| self.score(cx, cy) > self.refine_clearance_threshold)
            .collect();

        if !low_candidates.is_empty() {
            // Choose the low candidate with the lowest y value.
            return *low_candidates
                .iter()
                .min_by(|a, b| a.1.partial_cmp(&b.1).unwrap())
                .unwrap();
        }

        // Return candidate with highest score
        *candidates
            .iter()
            .max_by(|a, b| {
                self.score(a.0, a.1)
                    .partial_cmp(&self.score(b.0, b.1))
                    .unwrap()
            })
            .unwrap()
    }

    pub fn zone_lookup(&self, x: f64) -> i32 {
        let clamped_x = x.clamp(self.comb_positions[0], *self.comb_positions.last().unwrap());

        for idx in 1..self.comb_positions.len() - 1 {
            if clamped_x < self.comb_positions[idx] {
                return idx as i32;
            }
        }
        (self.comb_positions.len() - 1) as i32
    }
}
