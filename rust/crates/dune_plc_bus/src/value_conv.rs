//! Conversion between Rust value types and the dynamic `Value` carried over
//! the driver boundary. Implemented for each `T` we use as a tag value.

use crate::snapshot::{CipType, Value};

pub trait TagValue: Sized + Clone + Send + 'static {
    const CIP: CipType;
    fn to_value(self) -> Value;
    fn from_value(v: &Value) -> Option<Self>;
}

impl TagValue for bool {
    const CIP: CipType = CipType::Bool;
    fn to_value(self) -> Value {
        Value::Bool(self)
    }
    fn from_value(v: &Value) -> Option<Self> {
        match v {
            Value::Bool(b) => Some(*b),
            _ => None,
        }
    }
}

impl TagValue for i8 {
    const CIP: CipType = CipType::Sint;
    fn to_value(self) -> Value {
        Value::Sint(self)
    }
    fn from_value(v: &Value) -> Option<Self> {
        match v {
            Value::Sint(x) => Some(*x),
            _ => None,
        }
    }
}

impl TagValue for i16 {
    const CIP: CipType = CipType::Int;
    fn to_value(self) -> Value {
        Value::Int(self)
    }
    fn from_value(v: &Value) -> Option<Self> {
        match v {
            Value::Int(x) => Some(*x),
            _ => None,
        }
    }
}

impl TagValue for i32 {
    const CIP: CipType = CipType::Dint;
    fn to_value(self) -> Value {
        Value::Dint(self)
    }
    fn from_value(v: &Value) -> Option<Self> {
        match v {
            Value::Dint(x) => Some(*x),
            _ => None,
        }
    }
}

impl TagValue for f32 {
    const CIP: CipType = CipType::Real;
    fn to_value(self) -> Value {
        Value::Real(self)
    }
    fn from_value(v: &Value) -> Option<Self> {
        match v {
            Value::Real(x) => Some(*x),
            _ => None,
        }
    }
}

impl TagValue for [f32; 2] {
    const CIP: CipType = CipType::RealArray2;
    fn to_value(self) -> Value {
        Value::RealArray2(self)
    }
    fn from_value(v: &Value) -> Option<Self> {
        match v {
            Value::RealArray2(x) => Some(*x),
            _ => None,
        }
    }
}

impl TagValue for [f32; 3] {
    const CIP: CipType = CipType::RealArray3;
    fn to_value(self) -> Value {
        Value::RealArray3(self)
    }
    fn from_value(v: &Value) -> Option<Self> {
        match v {
            Value::RealArray3(x) => Some(*x),
            _ => None,
        }
    }
}
