use std::sync::atomic::{AtomicU64, Ordering};

#[derive(Default, Debug)]
pub struct Metrics {
    pub reads_total: AtomicU64,
    pub reads_failed: AtomicU64,
    pub writes_total: AtomicU64,
    pub writes_failed: AtomicU64,
    pub stale_read_errors: AtomicU64,
    pub batch_count: AtomicU64,
    pub coalesced_reads: AtomicU64,
    pub coalesced_writes: AtomicU64,
}

impl Metrics {
    pub fn reads(&self) -> u64 {
        self.reads_total.load(Ordering::Relaxed)
    }
    pub fn writes(&self) -> u64 {
        self.writes_total.load(Ordering::Relaxed)
    }
    pub fn stale_errors(&self) -> u64 {
        self.stale_read_errors.load(Ordering::Relaxed)
    }
    pub fn batches(&self) -> u64 {
        self.batch_count.load(Ordering::Relaxed)
    }
    pub fn coalesced_reads(&self) -> u64 {
        self.coalesced_reads.load(Ordering::Relaxed)
    }
    pub fn coalesced_writes(&self) -> u64 {
        self.coalesced_writes.load(Ordering::Relaxed)
    }

    pub fn inc(counter: &AtomicU64) {
        counter.fetch_add(1, Ordering::Relaxed);
    }

    pub fn add(counter: &AtomicU64, n: u64) {
        counter.fetch_add(n, Ordering::Relaxed);
    }
}
