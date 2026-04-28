# Allium Specifications

**Status:** ✅ All specs CURRENT (last updated Apr 26-27, 2026)

The authoritative formal specification of the domain model for both dune_winder and dune_tension applications.

---

## Shared Infrastructure (Used by Both Apps)

### [winder-states-safety.allium](../../dune_winder/winder-states-safety.allium)

**Last updated:** 2026-04-27  
**Status:** ✅ CURRENT  
**Scope:** Winder runtime control modes, PLC state machine, safety interlocks, head transfer state, operator diagnostics, queued motion

**Key entities:**
- `RuntimeController` — main control mode (hardware/stop/wind/manual)
- `PLCController` — PLC state and transitions (init/ready/xy_jog/xy_seek/z_jog/latching/error/etc.)
- `HeadController` — head positioning and transfer coordination
- `HeadTransferState` — physical state of head and actuator (position, latch status, Z extended)
- `MotionSafetyEnvelope` — XY/Z limits, collision keepouts, transfer zones
- `QueuedMotionController` — queued motion execution state

**Key rules:** 100+ rules covering:
- Runtime mode transitions
- PLC hard interlocks (XY requires Z retracted, Z retracted, no STO, APA vertical)
- Head transfer preconditions and safety
- Queued motion validation and diagnostics
- Tension control trip behavior (wire break, overtension)

**Open questions:** 3 (non-blocking)
- Should PLC HEAD_POS = 0 during ACTUATOR_POS = 3 be exposed as distinct transient position?
- Should XZ/YZ transfer use same descriptive diagnostics as XY preflight?
- Should queued-motion state be a dedicated PLCMode or remain derived?

**Config:** 9 constants (timeouts, positions, tolerances, limits, max velocity)

---

### [head-transfer.allium](../../dune_winder/head-transfer.allium)

**Last updated:** 2026-04-27  
**Status:** ✅ CURRENT  
**Scope:** Head transfer protocol (G206 strict, G106 legacy), latch actuator state machine, Z-axis coordination, sensor fusion, safety during transfer

**Key entities:**
- `ActuatorState` — rocker position (transition_engaged / stage_latched / mid_engagement / rocker_at_fixed)
- `HeadPosition` — physical head location (stage / fixed / floating / absent)
- `TransferPreconditions` — enable conditions (Z stage present, fixed present, Z extended)
- `TransferCommand` — G206/G106 request (target side, origin, timeouts)
- `ZAxis` — external feedback (actual position)

**Key rules:** 30+ rules covering:
- G206 transfer initiation (stage→fixed, fixed→stage, same-side)
- G106 legacy transfer (less strict)
- Z extension phase with timeout
- Latching phase with actuator state observation
- Final Z positioning and state verification
- Actuator rocker mechanics (unlatch, swing, settle)
- Z-axis coordination (blocked during floating, recovery when fixed-latched)
- Transfer cancellation (PLC error, operator stop)

**Invariants:** 8 critical invariants
- ActuatorEngagementRequiresExtension (Z_EXTENDED AND Z_STAGE_PRESENT AND Z_FIXED_PRESENT)
- RockerAtFixedIsTransient (unsafe for Z withdrawal; must settle to mid_engagement)
- MidEngagementIsSafeWithdrawal (only safe Z state when fixed-latched)
- HeadPositionCoherence (exclusive latch relationship)
- G206StrictStartingState (from stage: ACTUATOR_POS=1)
- G206StrictFinalState (verify latch state after Z reaches target)
- NoZMotionWhileFloating (head unlatched = no Z movement)
- PLCLatchStateReadiness (latch is PLC state, not direct control)

**Open questions:** 3 (non-blocking)
- Should transient_engaged (state 0) be split into separate states?
- Should rocker settling timeout be defined in spec?
- Should G106 legacy protocol be formally deprecated?

**Config:** 10 constants (Z positions, thresholds, timeouts, sensor delays, recovery attempts, transfer velocity)

---

### [uv-layer-geometry.allium](../../dune_winder/uv-layer-geometry.allium)

**Last updated:** 2026-04-26  
**Status:** ✅ CURRENT  
**Scope:** Final U/V APA wire geometry (shared by winder & tension), pin systems, wire segment formulas, continuous wrap paths, endpoint edge classification

**Key entities:**
- `UvLayerFrame` — frame metadata (layer, pin count, segment/measurable ranges, edge ranges)
- `UvWireSegment` — final state of a wire segment (layer, segment number, endpoints on both sides, edge classification)
- `UvContinuousWrapPath` — ordered pin sequence for applying the continuous wire in a wrap
- `PinWrapClassification` — wrap-side normal vector (x_sign, y_sign ∈ {-1, 1})
- `UvEndpointEdgeMapping` — start/end edge classification for each segment

**Key formulas:**
- Pin wrapping: `wrap(layer, n) = 1 + ((n - 1) mod pin_count(layer))`
- Opposite-side translation: `opposite(b) = 1 + ((head.last - b) mod pin_count(layer))`
- B-side endpoints:
  - U segment s: start = wrap(U, 450 + s - 1), end = wrap(U, 350 - (s - 1))
  - V segment s: start = wrap(V, 49 + s - 1), end = wrap(V, 2350 - (s - 1))
- Wrap-side parity: XOR of layer_bit, side_bit, edge_bit

**Config:** 18 constants
- Pin counts: u=2401, v=2399
- Segment ranges: formula [1, 1151], measurable [8, 1146]
- Edge ranges: u_head [1, 400], u_bottom [401, 1200], u_foot [1201, 1601], u_top [1602, 2401]
- Edge ranges: v_head [1, 399], v_bottom [400, 1199], v_foot [1200, 1599], v_top [1600, 2399]
- Wrap count: 400 wraps (index 0–399)

**Open questions:** None

**Used by:**
- `dune_winder` — recipe generation (expand segments), motion planning (segment endpoints)
- `dune_tension` — measurement targeting (segment selection), result grouping (by endpoint edge)

---

## Application-Specific

### [tension-measurement.allium](../../dune_tension/tension-measurement.allium)

**Last updated:** 2026-04-27  
**Status:** ✅ CURRENT  
**Scope:** Wire tension measurement workflow (legacy pulse mode and streaming sweep/rescue modes), audio capture, pitch analysis, result acceptance, measurement campaign management

**Key entities:**
- `MeasurementSetup` — configuration (APA name, layer, side, confidence threshold, focus mode)
- `LayerGeometry` — measurable ranges, comb zones per layer
- `WireTarget` — individual wire (measurable/unmeasurable, nominal pose, expected frequency)
- `FocusModel` — focus plane fitting (seeded/fitted with anchors)
- `MeasurementRequest` — campaign request (mode, kind, wires, zone filter, operator, state)
- `WireMeasurement` — individual wire measurement (target, status, samples, result)
- `TensionResult` — accepted result (wire, frequency, confidence, tension derivation, timestamp, mode)
- `TensionSample` — individual sample (frequency, confidence, pose, derivation)
- `StreamingSession` — sweep/rescue campaign session (status, focus model, segments, candidates, rescue queue)
- `StreamingSegment` — motion segment during streaming (sweep or rescue, pose range, audio windows)
- `WireCandidate` — detected wire from evidence (wire number, source mode, support count, scores)
- `UploadBatch` — batch of results for external upload

**Measurement modes:**
- `legacy` — single pulse capture, manual operator selection
- `stream_sweep` — continuous sweep motion with streaming FFT/inference
- `stream_rescue` — targeted probing of weak detections

**Key rules:** 30+ rules covering:
- Request lifecycle (planned → running → completed)
- Wire target planning (classification, nominal pose, frequency hint)
- Legacy pulse workflow (capture → sample → accept/no-result)
- Streaming sweep workflow (motion → audio windows → pitch evidence → candidates)
- Candidate acceptance (direct-accept if high confidence, queue for rescue if weak)
- Rescue workflow (re-probe with focused poses)
- Summary generation (selected results, missing wires, mean/sigma/modal tension)
- Clear wires (delete results/samples, regenerate summary)
- Upload batches (pending → uploaded/failed)

**Invariants:** 6 critical invariants
- ResultHasMatchingTarget (result wire = measurement target)
- AcceptedMeasurementHasResult (accepted status implies result exists)
- SummaryUsesLatestPlausibleResults (summary reflects current results)
- MissingWiresAreExpectedButNotSelected (missing = expected but no result)
- TensionDerivedFromPitchAndLength (tension formula consistency)
- StreamingResultKeepsSessionProvenance (streaming mode tracks session)

**Open questions:** 4 (non-blocking, design decisions)
- Keep legacy mode as production workflow or fallback only?
- What confidence thresholds should be calibrated from real audio?
- Should accepted candidates be immutable or revisable during operator review?
- Should upload identity be APA/layer scoped or batch scoped?

**Config:** 11 constants
- Tension bounds: min=2.0N, max=10.0N, max_passing=8.5N, nominal=6.5N
- Streaming acceptance thresholds: support≥2, confidence≥0.7, angle_score≥0.5, focus_score≥0.5
- Measurable ranges per layer (X, G, U/V), comb zones
- Focus calibration constants (mm per focus unit, X compensation)

---

## How to Read an Allium Spec

1. **Enumerations** — Define the vocabulary (state values, layer names, etc.)
2. **Value Types** — Immutable data structures (coordinates, ranges, derivations)
3. **External Entities** — Read-only feedback from outside the system
4. **Entities** — The main objects with state and transitions
5. **Config** — Constants and parameters (usually from calibration)
6. **Given** — The entities that exist and are managed by the spec
7. **Rules** — The behavior that governs state changes and validation
8. **Surfaces** — The boundaries where system interacts with external actors
9. **Invariants** — Properties that must always hold
10. **Open Questions** — Unresolved design decisions or clarifications needed

---

## Cross-Reference: Allium ↔ Python Implementation

After Phase 0 (audit), see [`docs/exec-plans/audit-results/DOMAIN_MODEL_VERIFICATION.md`](../exec-plans/audit-results/DOMAIN_MODEL_VERIFICATION.md) for verification of Python code against these specs.

---

## Key Takeaway

**These four Allium specs define the entire domain model for both applications.** The Rust port will implement these specifications, not the Python code. Python is an implementation that may lag behind the spec or have bugs; Allium is ground truth.
