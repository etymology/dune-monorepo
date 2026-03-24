# Web UI Hardening Plan

Status: Draft
Date: 2026-03-20

This document captures a practical improvement plan for the `web/` UI with the
goal of improving operator experience, reliability, and maintainability without
requiring a rewrite-first approach.

## Summary

The current web app is usable, but it still carries several high-risk traits
from the legacy shell:

- aggressive global polling,
- coarse error handling during connection loss,
- runtime HTML/CSS/script injection for page loading,
- split desktop/mobile routing,
- loose static file serving,
- minimal frontend-specific automated coverage.

The most important recommendation is to stabilize state transport and operator
feedback first, then modernize the shell in phases.

## Current Observations

Key hotspots identified during review:

- `web/Scripts/Winder.js`
  - polling loop runs every `100 ms`,
  - periodic failures invalidate all cached values,
  - connection loss disables the full main UI region at once.
- `web/Scripts/Modules.js` and `web/Scripts/Page.js`
  - pages/modules are loaded dynamically by injecting scripts, styles, and HTML
    at runtime,
  - module creation depends on globals and implicit load order.
- `web/Desktop/main.js`
  - load failures surface through blocking `alert(...)` calls.
- `web/index.html` and `web/Mobile/main.js`
  - mobile behavior depends on user-agent sniffing,
  - the mobile shell still loads desktop page modules.
- `src/dune_winder/threads/web_server_thread.py` and
  `src/dune_winder/library/web_server_interface.py`
  - the server exposes the `web/` directory directly as a static root.
- `tests/test_web_api_v2.py`
  - backend API coverage exists,
  - no dedicated JS/browser automation was found for the frontend shell.

There is already a useful building block available for a better state model:
`process.get_ui_snapshot`. It is registered in the API and already used by
`web/Desktop/Modules/MotorStatus.js`.

## Goals

- Make operator state clearer during normal use, reconnects, and faults.
- Reduce UI fragility caused by load order, globals, and page injection.
- Improve the safety and clarity of high-risk operator actions.
- Keep existing workflows working while the UI is modernized incrementally.
- Add enough automated coverage that frontend regressions are caught before use
  on the machine.

## Phased Plan

### Phase 1: Stabilize Runtime State And Error Handling

Focus on reliability first, not visual redesign.

- Expand `process.get_ui_snapshot` into the primary shared operator-state feed
  for status widgets and machine-state panels.
- Replace most per-widget polling with one shared client that:
  - polls a consolidated snapshot,
  - tracks `connected`, `stale`, `updating`, and `error` states,
  - uses adaptive backoff instead of a fixed `100 ms` loop,
  - restores widgets cleanly after reconnect.
- Replace full-page disable behavior with targeted status presentation:
  - connection banner,
  - stale-data indicator,
  - per-panel retry/recovery messaging,
  - explicit pending state for actions in flight.
- Standardize command error presentation so pages show inline errors instead of
  relying on alerts or silent failures.

### Phase 2: Improve Operator UX And Guardrails

Once the state model is stable, clean up the highest-friction workflows.

- Add consistent inline feedback for command execution:
  - pending,
  - success,
  - recoverable error,
  - connection error.
- Improve risky or expert-only controls:
  - gate raw manual G-code behind an advanced mode,
  - add clearer warnings around disruptive actions,
  - show disabled reasons instead of only disabling controls.
- Rework popup-dependent flows where possible into in-page panels or drawers.
- Keep operator attention on the current job by making status, faults, and
  machine readiness visible without needing modal interactions.

### Phase 3: Modernize The Shell

After the system is more stable, simplify the frontend architecture.

- Replace runtime script/html injection with bundled JS modules.
- Introduce one app shell with:
  - explicit routing,
  - page/module lifecycle boundaries,
  - a shared typed command client,
  - explicit state ownership for each page.
- Collapse the desktop/mobile split into a responsive shell with compact layout
  modes instead of user-agent redirects.
- Remove implicit global singletons where possible and make module dependencies
  explicit.

This phase should be incremental. The first migrations should target the
highest-churn screens such as `APA`, `ManualMove`, and shared status modules.

### Phase 4: Deployment Hygiene And Observability

- Serve only a curated static build/public directory rather than the full
  working `web/` directory.
- Remove temporary artifacts and non-asset files from the published static
  root.
- Add asset versioning or cache-busting appropriate for the chosen bundling
  approach.
- Add frontend error logging and basic operational diagnostics so failures are
  easier to debug outside the browser console.

## Public Interface Expectations

The current typed command API should remain the compatibility baseline:

- `POST /api/v2/command`
- `POST /api/v2/batch`

Recommended API direction:

- Keep existing command names stable during the UI migration.
- Prefer expanding `process.get_ui_snapshot` over adding many more narrowly
  scoped polling commands.
- If live update needs become more demanding later, consider a push model
  only after the snapshot contract is clearly defined and stable.

## Test Plan

### Keep Existing Coverage

- Preserve the current Python-side API and web-thread tests.
- Continue using simulator-backed backend tests as the baseline contract checks.

### Add Frontend Coverage

- Add unit tests for:
  - command client behavior,
  - snapshot polling/backoff logic,
  - status formatting and error-state transitions.
- Add browser smoke tests against the simulator for:
  - page load,
  - recipe selection,
  - start/stop/step actions,
  - manual move interactions,
  - calibration page load and basic actions,
  - reconnect/connection-loss handling.

### Acceptance Criteria

- Temporary network faults do not leave the UI in a confusing or permanently
  disabled state.
- The main operator pages no longer depend on alert-driven failure handling.
- State-heavy panels use a shared snapshot client rather than many unrelated
  poll loops.
- The mobile experience no longer depends on user-agent redirection.
- The published static root contains only intentional web assets.
- There is at least one automated browser-level smoke suite that runs against
  simulated hardware/API behavior.

## Suggested Implementation Order

1. Build the shared snapshot/status client and migrate the most visible status
   panels.
2. Replace alert-style error handling and add inline command feedback.
3. Tighten manual move / advanced operator controls.
4. Introduce the new shell structure and migrate high-churn pages one by one.
5. Add browser smoke coverage.
6. Clean up static asset publishing and deployment behavior.

## Assumptions

- The app primarily runs on a trusted internal network.
- Preserving existing machine workflows is more important than refreshing the
  visual design immediately.
- A phased migration is preferred over a rewrite.

If those assumptions change, authentication/authorization and stricter operator
role separation should move much earlier in the plan.
