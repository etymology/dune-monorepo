//! Phantom-typed capability markers.
//!
//! `TagId<T, Cap>` carries its capability in the type system. The bus exposes
//! `snapshot` / `read_fresh` only on capabilities implementing `Readable`, and
//! `write` / `write_async` only on those implementing `Writable`. Misuse fails
//! to compile.

use std::marker::PhantomData;

#[derive(Debug)]
pub struct Read(PhantomData<()>);
#[derive(Debug)]
pub struct Write(PhantomData<()>);
#[derive(Debug)]
pub struct ReadWrite(PhantomData<()>);

mod sealed {
    pub trait Sealed {}
    impl Sealed for super::Read {}
    impl Sealed for super::Write {}
    impl Sealed for super::ReadWrite {}
}

pub trait Capability: sealed::Sealed {
    const CAN_READ: bool;
    const CAN_WRITE: bool;
}

impl Capability for Read {
    const CAN_READ: bool = true;
    const CAN_WRITE: bool = false;
}
impl Capability for Write {
    const CAN_READ: bool = false;
    const CAN_WRITE: bool = true;
}
impl Capability for ReadWrite {
    const CAN_READ: bool = true;
    const CAN_WRITE: bool = true;
}

pub trait Readable: Capability {}
impl Readable for Read {}
impl Readable for ReadWrite {}

pub trait Writable: Capability {}
impl Writable for Write {}
impl Writable for ReadWrite {}
