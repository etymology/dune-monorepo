//! Re-export of `dune_geometry::tension::Geometry`. Kept as a thin shim so
//! the rest of `dune_tension_core` (planner, lib.rs) continues to import
//! `crate::geometry::Geometry` while the implementation lives in the
//! shared `dune_geometry` crate.

pub use dune_geometry::tension::Geometry;
