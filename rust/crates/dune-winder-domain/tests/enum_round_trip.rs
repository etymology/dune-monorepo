//! Round-trip and total-knowledge property tests for PLC-coded enums.
//!
//! For each enum:
//! 1. Every defined variant round-trips through its numeric encoding.
//! 2. Every numeric value in `i32`/`i8` either decodes to a defined variant
//!    *or* errors cleanly — never panics, never silently maps to a wrong
//!    variant.
//! 3. The set of accepted codes is exactly the spec-listed set.

use dune_winder_domain::motion::{CircleType, Direction, SegType, TermType};
use dune_winder_domain::state::{ActuatorPosition, MoveType, PlcMode};
use proptest::prelude::*;
use std::collections::HashSet;

#[test]
fn plc_mode_known_codes_match_spec() {
    let expected: HashSet<i32> = [0, 1, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
        .into_iter()
        .collect();
    let actual: HashSet<i32> = PlcMode::ALL.iter().map(|m| m.code()).collect();
    assert_eq!(actual, expected);
}

#[test]
fn move_type_known_codes_match_plc_ladder() {
    // Confirmed against `dune_winder/plc/enqueueRoutineStateful` — only these
    // numeric values appear in `CMP(MOVE_TYPE=N)` rungs.
    let expected: HashSet<i32> = [0, 1, 2, 4, 5, 8, 9, 11].into_iter().collect();
    let actual: HashSet<i32> = MoveType::ALL.iter().map(|m| m.code()).collect();
    assert_eq!(actual, expected);
}

#[test]
fn actuator_position_known_codes_match_spec() {
    let expected: HashSet<i32> = (0..=3).collect();
    let actual: HashSet<i32> = ActuatorPosition::ALL.iter().map(|p| p.code()).collect();
    assert_eq!(actual, expected);
}

proptest! {
    #[test]
    fn plc_mode_round_trips_for_every_known_code(mode in plc_mode_strategy()) {
        let code: i32 = mode.into();
        let decoded = PlcMode::try_from(code).expect("known code should decode");
        prop_assert_eq!(decoded, mode);
    }

    #[test]
    fn plc_mode_unknown_code_errors_cleanly(value in any::<i32>()) {
        let known: HashSet<i32> = PlcMode::ALL.iter().map(|m| m.code()).collect();
        match PlcMode::try_from(value) {
            Ok(m) => prop_assert!(known.contains(&m.code())),
            Err(e) => prop_assert!(!known.contains(&value), "unexpected error for known code {}: {}", value, e),
        }
    }

    #[test]
    fn move_type_round_trips_for_every_known_code(mt in move_type_strategy()) {
        let code: i32 = mt.into();
        let decoded = MoveType::try_from(code).expect("known code should decode");
        prop_assert_eq!(decoded, mt);
    }

    #[test]
    fn move_type_unknown_code_errors_cleanly(value in any::<i32>()) {
        let known: HashSet<i32> = MoveType::ALL.iter().map(|m| m.code()).collect();
        match MoveType::try_from(value) {
            Ok(m) => prop_assert!(known.contains(&m.code())),
            Err(e) => prop_assert!(!known.contains(&value), "unexpected error for known code {}: {}", value, e),
        }
    }

    #[test]
    fn actuator_position_round_trips(pos in actuator_position_strategy()) {
        let code: i32 = pos.into();
        let decoded = ActuatorPosition::try_from(code).expect("known code should decode");
        prop_assert_eq!(decoded, pos);
    }

    #[test]
    fn actuator_position_unknown_code_errors_cleanly(value in any::<i32>()) {
        let known: HashSet<i32> = ActuatorPosition::ALL.iter().map(|p| p.code()).collect();
        match ActuatorPosition::try_from(value) {
            Ok(p) => prop_assert!(known.contains(&p.code())),
            Err(e) => prop_assert!(!known.contains(&value), "unexpected error for known code {}: {}", value, e),
        }
    }

    #[test]
    fn seg_type_round_trips(value in 1i8..=2) {
        let seg = SegType::try_from(value).expect("known seg type");
        let back: i8 = seg.into();
        prop_assert_eq!(back, value);
    }

    #[test]
    fn seg_type_rejects_invalid(value in any::<i8>().prop_filter("not a valid seg code", |v| !(1..=2).contains(v))) {
        prop_assert!(SegType::try_from(value).is_err());
    }

    #[test]
    fn term_type_round_trips(value in 0i8..=6) {
        let t = TermType::try_from(value).expect("known term type");
        let back: i8 = t.into();
        prop_assert_eq!(back, value);
    }

    #[test]
    fn term_type_rejects_invalid(value in any::<i8>().prop_filter("not a valid term code", |v| !(0..=6).contains(v))) {
        prop_assert!(TermType::try_from(value).is_err());
    }

    #[test]
    fn circle_type_round_trips(value in 0i32..=3) {
        let c = CircleType::try_from(value).expect("known circle type");
        let back: i32 = c.into();
        prop_assert_eq!(back, value);
    }

    #[test]
    fn circle_type_rejects_invalid(value in any::<i32>().prop_filter("not a valid circle code", |v| !(0..=3).contains(v))) {
        prop_assert!(CircleType::try_from(value).is_err());
    }

    #[test]
    fn direction_round_trips(value in 0i32..=3) {
        let d = Direction::try_from(value).expect("known direction");
        let back: i32 = d.into();
        prop_assert_eq!(back, value);
    }

    #[test]
    fn direction_rejects_invalid(value in any::<i32>().prop_filter("not a valid direction code", |v| !(0..=3).contains(v))) {
        prop_assert!(Direction::try_from(value).is_err());
    }
}

fn plc_mode_strategy() -> impl Strategy<Value = PlcMode> {
    proptest::sample::select(PlcMode::ALL.to_vec())
}

fn move_type_strategy() -> impl Strategy<Value = MoveType> {
    proptest::sample::select(MoveType::ALL.to_vec())
}

fn actuator_position_strategy() -> impl Strategy<Value = ActuatorPosition> {
    proptest::sample::select(ActuatorPosition::ALL.to_vec())
}
