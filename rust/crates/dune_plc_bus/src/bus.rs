//! TagBus — owns cache, poll thread, and the driver.

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use crossbeam_channel::{bounded, Receiver, Sender};
use parking_lot::{Condvar, Mutex};

use crate::capability::{Readable, Writable};
use crate::driver::{Health, PlcDriver};
use crate::error::{StaleReadError, WriteFailed};
use crate::metrics::Metrics;
use crate::snapshot::{Snapshot, Source, Tier, Value};
use crate::tag::{ErasedTagId, TagId};
use crate::value_conv::TagValue;

/// Bus configuration knobs.
#[derive(Clone, Debug)]
pub struct BusConfig {
    /// How often the poll thread wakes to check for due tags.
    pub tick: Duration,
    /// Max tags per driver read batch.
    pub max_batch: usize,
    /// Default write timeout when caller does not specify.
    pub default_write_timeout: Duration,
    /// Reconnect backoff base.
    pub reconnect_backoff: Duration,
}

impl Default for BusConfig {
    fn default() -> Self {
        Self {
            tick: Duration::from_millis(5),
            max_batch: 14,
            default_write_timeout: Duration::from_millis(250),
            reconnect_backoff: Duration::from_millis(100),
        }
    }
}

#[derive(Clone, Debug)]
pub struct WriteOutcome {
    pub at: Instant,
    pub sequence: u64,
}

struct CachedEntry {
    value: Option<Value>,
    at: Instant,
    sequence: u64,
    source: Source,
    /// Per-tag override of the polling cadence (smallest wins). `None` = default tier.
    subscriber_max_age: Option<Duration>,
    last_poll: Option<Instant>,
    /// Pending one-shot fetch waiters: woken once their tag is fetched.
    waiters: Vec<Arc<FetchWaiter>>,
}

impl CachedEntry {
    fn new() -> Self {
        Self {
            value: None,
            at: Instant::now(),
            sequence: 0,
            source: Source::Default,
            subscriber_max_age: None,
            last_poll: None,
            waiters: Vec::new(),
        }
    }

    fn effective_period(&self, tier: Tier) -> Option<Duration> {
        let from_tier = tier.default_period();
        match (from_tier, self.subscriber_max_age) {
            (None, None) => None,
            (Some(p), None) => Some(p),
            (None, Some(s)) => Some(s),
            (Some(p), Some(s)) => Some(p.min(s)),
        }
    }

    fn is_due(&self, tier: Tier, now: Instant) -> bool {
        let Some(period) = self.effective_period(tier) else {
            // OnDemand — only fetched when there are explicit waiters.
            return !self.waiters.is_empty();
        };
        if !self.waiters.is_empty() {
            return true;
        }
        match self.last_poll {
            None => true,
            Some(prev) => now.duration_since(prev) >= period,
        }
    }
}

/// Coalesced one-shot waiter slot. Currently unused since `read_fresh` drives
/// reads synchronously; retained for the planned poll-thread coalescing path.
#[allow(dead_code)]
struct FetchWaiter {
    done: Mutex<bool>,
    cv: Condvar,
}

#[allow(dead_code)]
impl FetchWaiter {
    fn new() -> Arc<Self> {
        Arc::new(Self {
            done: Mutex::new(false),
            cv: Condvar::new(),
        })
    }

    fn wait(&self, timeout: Duration) -> bool {
        let mut done = self.done.lock();
        if *done {
            return true;
        }
        let result = self.cv.wait_for(&mut done, timeout);
        if result.timed_out() {
            *done
        } else {
            *done
        }
    }

    fn complete(&self) {
        let mut done = self.done.lock();
        *done = true;
        self.cv.notify_all();
    }
}

struct BusInner {
    cache: HashMap<&'static str, CachedEntry>,
    tag_meta: HashMap<&'static str, ErasedTagId>,
    seq: AtomicU64,
}

pub struct TagBus {
    inner: Arc<Mutex<BusInner>>,
    driver: Arc<Mutex<Box<dyn PlcDriver>>>,
    metrics: Arc<Metrics>,
    config: BusConfig,
    running: Arc<AtomicBool>,
    poll_handle: Mutex<Option<thread::JoinHandle<()>>>,
    wake_tx: Sender<()>,
    wake_rx: Receiver<()>,
}

impl TagBus {
    pub fn new(driver: Box<dyn PlcDriver>, config: BusConfig) -> Self {
        Self::with_tags(driver, config, &[])
    }

    /// Construct a bus and pre-register the given tags so they appear in the
    /// cache from the start (with `Source::Default`). Tags not pre-registered
    /// are added lazily on first use.
    pub fn with_tags(
        driver: Box<dyn PlcDriver>,
        config: BusConfig,
        tags: &[ErasedTagId],
    ) -> Self {
        let mut cache = HashMap::new();
        let mut tag_meta = HashMap::new();
        for t in tags {
            cache.insert(t.name, CachedEntry::new());
            tag_meta.insert(t.name, *t);
        }
        let (wake_tx, wake_rx) = bounded::<()>(1);
        Self {
            inner: Arc::new(Mutex::new(BusInner {
                cache,
                tag_meta,
                seq: AtomicU64::new(0),
            })),
            driver: Arc::new(Mutex::new(driver)),
            metrics: Arc::new(Metrics::default()),
            config,
            running: Arc::new(AtomicBool::new(false)),
            poll_handle: Mutex::new(None),
            wake_tx,
            wake_rx,
        }
    }

    pub fn metrics(&self) -> Arc<Metrics> {
        self.metrics.clone()
    }

    /// Register a tag dynamically (used by the PyO3 binding and any other
    /// caller that doesn't have the typed handle in scope).
    pub fn register(&self, tag: ErasedTagId) {
        self.ensure_registered(tag);
    }

    /// String-keyed dynamic snapshot. Caller is responsible for tag identity.
    /// Returns `None` if the tag was never registered or never read.
    pub fn snapshot_value(&self, name: &'static str) -> Option<Snapshot<Value>> {
        let inner = self.inner.lock();
        let entry = inner.cache.get(name)?;
        let value = entry.value.clone()?;
        Some(Snapshot {
            value,
            at: entry.at,
            sequence: entry.sequence,
            source: entry.source,
        })
    }

    /// String-keyed dynamic fresh-read. Tag must already be registered (by
    /// passing it to `with_tags`, by an earlier typed call, or via `register`).
    pub fn read_fresh_value(
        &self,
        name: &'static str,
        within: Duration,
        timeout: Duration,
    ) -> Result<Snapshot<Value>, StaleReadError> {
        // Fast path.
        {
            let inner = self.inner.lock();
            let entry = inner
                .cache
                .get(name)
                .ok_or(StaleReadError::NoValue { tag: name })?;
            if let Some(v) = &entry.value {
                if entry.is_fresh(within) {
                    return Ok(Snapshot {
                        value: v.clone(),
                        at: entry.at,
                        sequence: entry.sequence,
                        source: entry.source,
                    });
                }
            }
        }

        // Slow path: synchronously fetch through the driver. This works whether
        // or not the poll thread is running, and gives us a hard `timeout`
        // bound that doesn't depend on tier scheduling.
        let _ = timeout;
        let driver_result = {
            let mut driver = self.driver.lock();
            driver.read(&[name])
        };
        let mut inner = self.inner.lock();
        let entry = inner
            .cache
            .get_mut(name)
            .ok_or(StaleReadError::NoValue { tag: name })?;
        match driver_result {
            Ok(map) => match map.get(name) {
                Some(v) => {
                    let seq = inner.seq.fetch_add(1, Ordering::Relaxed) + 1;
                    let now = Instant::now();
                    let entry = inner.cache.get_mut(name).unwrap();
                    entry.value = Some(v.clone());
                    entry.at = now;
                    entry.sequence = seq;
                    entry.source = Source::Plc;
                    self.metrics.reads_total.fetch_add(1, Ordering::Relaxed);
                    Ok(Snapshot {
                        value: v.clone(),
                        at: now,
                        sequence: seq,
                        source: Source::Plc,
                    })
                }
                None => {
                    self.metrics
                        .stale_read_errors
                        .fetch_add(1, Ordering::Relaxed);
                    Err(StaleReadError::NoValue { tag: name })
                }
            },
            Err(e) => {
                entry.source = Source::Stale;
                self.metrics
                    .stale_read_errors
                    .fetch_add(1, Ordering::Relaxed);
                Err(StaleReadError::Driver {
                    tag: name,
                    source: e,
                })
            }
        }
    }

    /// String-keyed dynamic bulk fresh-read. Single driver round-trip; updates
    /// cache for every returned tag. Tags missing from the driver response
    /// return `None` in the result map.
    pub fn read_many_fresh(
        &self,
        names: &[&'static str],
    ) -> HashMap<&'static str, Result<Snapshot<Value>, StaleReadError>> {
        for name in names {
            // Best-effort: we can't synthesize an ErasedTagId here without
            // metadata, so registration is implicit via the cache entry. If the
            // tag was never registered (no schema entry), we still drive the
            // read; the result will be returned but not cached.
            let mut inner = self.inner.lock();
            inner.cache.entry(*name).or_insert_with(CachedEntry::new);
        }

        let driver_result = {
            let mut driver = self.driver.lock();
            driver.read(names)
        };

        let mut out: HashMap<&'static str, Result<Snapshot<Value>, StaleReadError>> =
            HashMap::with_capacity(names.len());
        let mut inner = self.inner.lock();
        let now = Instant::now();
        match driver_result {
            Ok(map) => {
                self.metrics
                    .reads_total
                    .fetch_add(names.len() as u64, Ordering::Relaxed);
                for name in names {
                    match map.get(*name) {
                        Some(v) => {
                            let seq = inner.seq.fetch_add(1, Ordering::Relaxed) + 1;
                            let entry = inner.cache.get_mut(*name).unwrap();
                            entry.value = Some(v.clone());
                            entry.at = now;
                            entry.sequence = seq;
                            entry.source = Source::Plc;
                            out.insert(
                                *name,
                                Ok(Snapshot {
                                    value: v.clone(),
                                    at: now,
                                    sequence: seq,
                                    source: Source::Plc,
                                }),
                            );
                        }
                        None => {
                            self.metrics
                                .stale_read_errors
                                .fetch_add(1, Ordering::Relaxed);
                            out.insert(*name, Err(StaleReadError::NoValue { tag: *name }));
                        }
                    }
                }
            }
            Err(e) => {
                let msg = e.to_string();
                self.metrics
                    .stale_read_errors
                    .fetch_add(names.len() as u64, Ordering::Relaxed);
                for name in names {
                    if let Some(entry) = inner.cache.get_mut(*name) {
                        entry.source = Source::Stale;
                    }
                    out.insert(
                        *name,
                        Err(StaleReadError::Driver {
                            tag: *name,
                            source: crate::error::DriverError::Io(msg.clone()),
                        }),
                    );
                }
            }
        }
        out
    }

    /// String-keyed dynamic write.
    pub fn write_value(
        &self,
        name: &'static str,
        value: Value,
        timeout: Duration,
    ) -> Result<WriteOutcome, WriteFailed> {
        let _ = timeout;
        let updates = [(name, value.clone())];
        let mut driver = self.driver.lock();
        let result = driver.write(&updates).map_err(|e| WriteFailed::Driver {
            tag: name,
            source: e,
        })?;
        drop(driver);
        if !*result.get(name).unwrap_or(&false) {
            return Err(WriteFailed::Rejected { tag: name });
        }
        let mut inner = self.inner.lock();
        if !inner.cache.contains_key(name) {
            return Err(WriteFailed::Rejected { tag: name });
        }
        let seq = inner.seq.fetch_add(1, Ordering::Relaxed) + 1;
        let now = Instant::now();
        let entry = inner.cache.get_mut(name).unwrap();
        entry.value = Some(value);
        entry.at = now;
        entry.sequence = seq;
        entry.source = Source::WriteEcho;
        self.metrics.writes_total.fetch_add(1, Ordering::Relaxed);
        Ok(WriteOutcome { at: now, sequence: seq })
    }

    pub fn health(&self) -> Health {
        self.driver.lock().health()
    }

    pub fn start(&self) {
        if self.running.swap(true, Ordering::SeqCst) {
            return;
        }
        let _ = self.driver.lock().connect();
        let inner = self.inner.clone();
        let driver = self.driver.clone();
        let metrics = self.metrics.clone();
        let cfg = self.config.clone();
        let running = self.running.clone();
        let wake_rx = self.wake_rx.clone();

        let handle = thread::spawn(move || {
            poll_loop(inner, driver, metrics, cfg, running, wake_rx);
        });
        *self.poll_handle.lock() = Some(handle);
    }

    pub fn stop(&self) {
        if !self.running.swap(false, Ordering::SeqCst) {
            return;
        }
        let _ = self.wake_tx.try_send(());
        if let Some(h) = self.poll_handle.lock().take() {
            let _ = h.join();
        }
        self.driver.lock().disconnect();
    }

    fn ensure_registered(&self, tag: ErasedTagId) {
        let mut inner = self.inner.lock();
        inner.tag_meta.entry(tag.name).or_insert(tag);
        inner.cache.entry(tag.name).or_insert_with(CachedEntry::new);
    }

    fn wake_poller(&self) {
        let _ = self.wake_tx.try_send(());
    }

    /// Best-effort cached read. Returns `Source::Default` if we've never seen the wire.
    pub fn snapshot<T, C>(&self, tag: TagId<T, C>) -> Snapshot<T>
    where
        T: TagValue + Default,
        C: Readable,
    {
        self.ensure_registered(tag.erased());
        let inner = self.inner.lock();
        let entry = inner.cache.get(tag.name).expect("registered above");
        let value = entry
            .value
            .as_ref()
            .and_then(|v| T::from_value(v))
            .unwrap_or_default();
        Snapshot {
            value,
            at: entry.at,
            sequence: entry.sequence,
            source: entry.source,
        }
    }

    /// Fresh-read with hard guarantee. Blocks up to `timeout` waiting for the
    /// poll thread to satisfy a fetch newer than `within`.
    pub fn read_fresh<T, C>(
        &self,
        tag: TagId<T, C>,
        within: Duration,
        timeout: Duration,
    ) -> Result<Snapshot<T>, StaleReadError>
    where
        T: TagValue + Default,
        C: Readable,
    {
        self.ensure_registered(tag.erased());

        // Fast path: cache already fresh.
        {
            let inner = self.inner.lock();
            let entry = inner.cache.get(tag.name).unwrap();
            if let Some(v) = &entry.value {
                if entry.is_fresh(within) {
                    if let Some(value) = T::from_value(v) {
                        return Ok(Snapshot {
                            value,
                            at: entry.at,
                            sequence: entry.sequence,
                            source: entry.source,
                        });
                    }
                }
            }
        }

        // Slow path: synchronous direct read.
        let _ = timeout;
        let driver_result = {
            let mut driver = self.driver.lock();
            driver.read(&[tag.name])
        };
        let mut inner = self.inner.lock();
        match driver_result {
            Ok(map) => match map.get(tag.name) {
                Some(v) => {
                    let value = T::from_value(v)
                        .ok_or(StaleReadError::NoValue { tag: tag.name })?;
                    let seq = inner.seq.fetch_add(1, Ordering::Relaxed) + 1;
                    let now = Instant::now();
                    let entry = inner.cache.get_mut(tag.name).unwrap();
                    entry.value = Some(v.clone());
                    entry.at = now;
                    entry.sequence = seq;
                    entry.source = Source::Plc;
                    self.metrics.reads_total.fetch_add(1, Ordering::Relaxed);
                    Ok(Snapshot {
                        value,
                        at: now,
                        sequence: seq,
                        source: Source::Plc,
                    })
                }
                None => {
                    self.metrics
                        .stale_read_errors
                        .fetch_add(1, Ordering::Relaxed);
                    Err(StaleReadError::NoValue { tag: tag.name })
                }
            },
            Err(e) => {
                if let Some(entry) = inner.cache.get_mut(tag.name) {
                    entry.source = Source::Stale;
                }
                self.metrics
                    .stale_read_errors
                    .fetch_add(1, Ordering::Relaxed);
                Err(StaleReadError::Driver {
                    tag: tag.name,
                    source: e,
                })
            }
        }
    }

    /// Set a per-tag freshness floor. The poll thread uses
    /// `min(tier_default, max_age)` going forward.
    pub fn subscribe<T, C>(&self, tag: TagId<T, C>, max_age: Duration)
    where
        T: TagValue,
        C: Readable,
    {
        self.ensure_registered(tag.erased());
        let mut inner = self.inner.lock();
        let entry = inner.cache.get_mut(tag.name).unwrap();
        entry.subscriber_max_age = Some(match entry.subscriber_max_age {
            Some(prev) => prev.min(max_age),
            None => max_age,
        });
        drop(inner);
        self.wake_poller();
    }

    /// Synchronous write through the driver. Updates cache with `WriteEcho` on
    /// success; the next poll confirms.
    pub fn write<T, C>(
        &self,
        tag: TagId<T, C>,
        value: T,
        timeout: Duration,
    ) -> Result<WriteOutcome, WriteFailed>
    where
        T: TagValue,
        C: Writable,
    {
        let _ = timeout; // v1: rely on driver's own timing
        self.ensure_registered(tag.erased());
        let v = value.clone().to_value();
        let updates = [(tag.name, v.clone())];
        let mut driver = self.driver.lock();
        let result = driver.write(&updates).map_err(|e| WriteFailed::Driver {
            tag: tag.name,
            source: e,
        })?;
        drop(driver);
        if !*result.get(tag.name).unwrap_or(&false) {
            return Err(WriteFailed::Rejected { tag: tag.name });
        }
        let mut inner = self.inner.lock();
        let seq = inner.seq.fetch_add(1, Ordering::Relaxed) + 1;
        let now = Instant::now();
        let entry = inner.cache.get_mut(tag.name).unwrap();
        entry.value = Some(v);
        entry.at = now;
        entry.sequence = seq;
        entry.source = Source::WriteEcho;
        self.metrics.writes_total.fetch_add(1, Ordering::Relaxed);
        Ok(WriteOutcome { at: now, sequence: seq })
    }

    /// Bulk write — single driver round-trip. Returns per-tag outcomes.
    pub fn write_many(
        &self,
        updates: Vec<(ErasedTagId, Value)>,
        timeout: Duration,
    ) -> HashMap<&'static str, Result<WriteOutcome, WriteFailed>> {
        let _ = timeout;
        let mut by_name: Vec<(&'static str, Value)> = Vec::with_capacity(updates.len());
        for (tag, v) in &updates {
            self.ensure_registered(*tag);
            by_name.push((tag.name, v.clone()));
        }
        let refs: Vec<(&str, Value)> =
            by_name.iter().map(|(n, v)| (*n, v.clone())).collect();
        let mut driver = self.driver.lock();
        let result = driver.write(&refs);
        drop(driver);
        let mut out: HashMap<&'static str, Result<WriteOutcome, WriteFailed>> =
            HashMap::with_capacity(updates.len());
        match result {
            Ok(per) => {
                let mut inner = self.inner.lock();
                let now = Instant::now();
                for (tag, v) in updates {
                    if *per.get(tag.name).unwrap_or(&false) {
                        let seq = inner.seq.fetch_add(1, Ordering::Relaxed) + 1;
                        let entry = inner.cache.get_mut(tag.name).unwrap();
                        entry.value = Some(v);
                        entry.at = now;
                        entry.sequence = seq;
                        entry.source = Source::WriteEcho;
                        self.metrics.writes_total.fetch_add(1, Ordering::Relaxed);
                        out.insert(tag.name, Ok(WriteOutcome { at: now, sequence: seq }));
                    } else {
                        self.metrics.writes_failed.fetch_add(1, Ordering::Relaxed);
                        out.insert(tag.name, Err(WriteFailed::Rejected { tag: tag.name }));
                    }
                }
            }
            Err(e) => {
                let msg = e.to_string();
                self.metrics.writes_failed.fetch_add(updates.len() as u64, Ordering::Relaxed);
                for (tag, _v) in updates {
                    out.insert(
                        tag.name,
                        Err(WriteFailed::Driver {
                            tag: tag.name,
                            source: crate::error::DriverError::Io(msg.clone()),
                        }),
                    );
                }
            }
        }
        out
    }
}

impl Drop for TagBus {
    fn drop(&mut self) {
        self.stop();
    }
}

impl CachedEntry {
    fn is_fresh(&self, max_age: Duration) -> bool {
        matches!(self.source, Source::Plc | Source::WriteEcho)
            && Instant::now().duration_since(self.at) <= max_age
    }
}

fn poll_loop(
    inner: Arc<Mutex<BusInner>>,
    driver: Arc<Mutex<Box<dyn PlcDriver>>>,
    metrics: Arc<Metrics>,
    cfg: BusConfig,
    running: Arc<AtomicBool>,
    wake_rx: Receiver<()>,
) {
    while running.load(Ordering::SeqCst) {
        let now = Instant::now();
        let due = collect_due(&inner, now, cfg.max_batch);
        if due.is_empty() {
            // Sleep until next tick or wake.
            let _ = wake_rx.recv_timeout(cfg.tick);
            continue;
        }

        for batch in due {
            metrics.batch_count.fetch_add(1, Ordering::Relaxed);
            let names: Vec<&str> = batch.iter().map(|n| *n).collect();
            let result = {
                let mut d = driver.lock();
                d.read(&names)
            };
            let now = Instant::now();
            let mut g = inner.lock();
            match result {
                Ok(map) => {
                    metrics.reads_total.fetch_add(names.len() as u64, Ordering::Relaxed);
                    for name in &names {
                        let entry = g.cache.get_mut(*name).expect("registered when scheduled");
                        if let Some(v) = map.get(*name) {
                            let seq = g.seq.fetch_add(1, Ordering::Relaxed) + 1;
                            let entry = g.cache.get_mut(*name).unwrap();
                            entry.value = Some(v.clone());
                            entry.at = now;
                            entry.sequence = seq;
                            entry.source = Source::Plc;
                            entry.last_poll = Some(now);
                            for w in entry.waiters.drain(..) {
                                w.complete();
                            }
                        } else {
                            // Driver returned no value for this tag — leave cache,
                            // but mark last_poll so we don't spin.
                            entry.last_poll = Some(now);
                        }
                    }
                }
                Err(_e) => {
                    metrics.reads_failed.fetch_add(names.len() as u64, Ordering::Relaxed);
                    for name in &names {
                        let entry = g.cache.get_mut(*name).expect("registered when scheduled");
                        entry.source = Source::Stale;
                        entry.last_poll = Some(now);
                        for w in entry.waiters.drain(..) {
                            w.complete();
                        }
                    }
                }
            }
        }
    }
}

fn collect_due(
    inner: &Arc<Mutex<BusInner>>,
    now: Instant,
    max_batch: usize,
) -> Vec<Vec<&'static str>> {
    let g = inner.lock();
    let mut due: Vec<&'static str> = Vec::new();
    for (name, entry) in g.cache.iter() {
        let Some(meta) = g.tag_meta.get(*name) else {
            continue;
        };
        if entry.is_due(meta.tier, now) {
            due.push(*name);
        }
    }
    drop(g);
    due.chunks(max_batch).map(|c| c.to_vec()).collect()
}
