//! Tag identifiers — passive descriptors. All cache state lives in the bus.

use std::marker::PhantomData;

use crate::capability::Capability;
use crate::snapshot::{CipType, Tier};

/// Statically-typed tag handle. `T` is the Rust value type, `C` the capability.
#[derive(Debug)]
pub struct TagId<T, C: Capability> {
    pub name: &'static str,
    pub cip: CipType,
    pub tier: Tier,
    _value: PhantomData<fn() -> T>,
    _cap: PhantomData<C>,
}

impl<T, C: Capability> TagId<T, C> {
    pub const fn new(name: &'static str, cip: CipType, tier: Tier) -> Self {
        Self {
            name,
            cip,
            tier,
            _value: PhantomData,
            _cap: PhantomData,
        }
    }

    pub fn erased(&self) -> ErasedTagId {
        ErasedTagId {
            name: self.name,
            cip: self.cip,
            tier: self.tier,
        }
    }
}

impl<T, C: Capability> Clone for TagId<T, C> {
    fn clone(&self) -> Self {
        *self
    }
}
impl<T, C: Capability> Copy for TagId<T, C> {}

/// Type-erased tag handle for collection APIs (`read_many`, `write_many`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct ErasedTagId {
    pub name: &'static str,
    pub cip: CipType,
    pub tier: Tier,
}
