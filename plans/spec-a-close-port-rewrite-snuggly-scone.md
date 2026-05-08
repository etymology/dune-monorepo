# Close port: dune_winder web → SolidJS + TS

## Context

The current desktop UI under `dune_winder/web/desktop/` is ~6300 lines of vanilla JS + jQuery, served raw by a Python `SimpleHTTPRequestHandler`. It works, but the architecture has accumulated friction that makes recent changes (ManualMove, PositionGraphic, APA pin segment lookup, MachineLayout) more brittle than they should be:

- **Page.js / Modules.js** is a homegrown router + dynamic loader using `$.getScript()`, `window[moduleName]` constructors, and HTML-string caching. Module dependencies are stringly-typed and ordering is ad-hoc.
- **Polling** at 100ms via `Winder.js` does a JSON.stringify diff against the previous response; periodic callbacks have no unsubscribe path and are leaked across page transitions.
- **MotorStatus is a god object** mutated in place, observed by 4+ modules with no real reactivity.
- **Errors disable the entire UI** via a counter-based `inhibitUpdates` mechanism that's easy to mis-balance.
- **Canvas in PositionGraphic** is 1000+ lines of imperative drawing with hard-coded pixel constants.
- **No build step, no types** — refactors against the 100+ command catalog are exclusively a grep exercise.

Goal: a close behavioural port (same pages, same modules, same operator workflows, same backend command vocabulary) into a typed, reactive framework so subsequent feature work — ongoing calibration, UV head, layer-Z work — lands in a codebase that fights back less. Operators should not notice the swap on day one.

**Decisions (from clarification):**

- Framework: **SolidJS + Vite + TypeScript**.
- Transport: **add WebSocket** for state push, keep REST for commands.
- Layout: **`dune_winder/web_next/` in parallel**; both UIs serve concurrently until parity, then cut over.
- Scope: **all 14 pages + 18 modules** to behaviour parity.

## High-level approach

1. Stand up `dune_winder/web_next/` as a Vite + Solid + TS project that builds to `dune_winder/web_next/dist/`.
2. Have the existing Python server mount the new build at `/next/` while the legacy UI continues to serve at `/`. Operators get a switch link in the header; we delete `/desktop/` only at cutover.
3. Generate a typed command catalog from the existing `CommandCatalog.js` (or its Python source in `src/dune_winder/api/commands.py`) and a typed REST + WS client.
4. Add a single new WebSocket endpoint (`/api/v2/state`) on the backend that pushes the same payload `process.get_ui_snapshot` returns today — at the same 100ms cadence, but server-driven. REST commands stay unchanged.
5. Port the spine (router, API client, store, theming, error UI) and one vertical slice (MachineLayout + PositionGraphic) first to validate the patterns. Then port pages in dependency order, sharing modules as we go.
6. At parity, swap default route, archive `web/desktop/`, remove the dual-mount.

## Architecture mapping (old → new)

| Old | New |
|---|---|
| `Page.js` HTML cache + lifecycle | `@solidjs/router` with route-level code splitting |
| `Modules.js` global constructors | Imported Solid components, no globals |
| `Winder.js` polling + history diff | `client/transport.ts` (REST POST) + `client/socket.ts` (WS subscribe) |
| `UiServices.js` typed wrapper + CommandCatalog | `client/commands.ts` — codegen'd from backend catalog, fully typed |
| `MotorStatus.motor` god object | Solid stores: `machineStore`, `ioStore`, `runStore`, `versionStore` |
| Periodic callbacks (no unsub) | Solid `createEffect` + automatic cleanup on unmount |
| `winder.inhibitUpdates(±1)` counter | Per-call `transport.inhibit()` returning a disposer |
| jQuery DOM mutation | Solid JSX, fine-grained reactivity |
| Canvas in `PositionGraphic.js` | SVG component; only path history stays canvas (perf) |
| jQuery-UI sliders/dialogs | Native `<input type="range">` + headless dialog primitive |
| Per-file `.css` injected dynamically | Vanilla CSS modules co-located with components, bundled by Vite |
| `winder.toggleButton` / `editField` helpers | `<ToggleButton>` / `<NumberField>` components with built-in validation |

## Project layout

```
dune_winder/web_next/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── index.html
├── src/
│   ├── main.tsx              # Solid root, router mount
│   ├── routes.tsx            # Route table (14 pages)
│   ├── client/
│   │   ├── transport.ts      # fetch wrapper for /api/v2/command + /batch
│   │   ├── socket.ts         # WS client for /api/v2/state with auto-reconnect
│   │   ├── commands.ts       # generated: typed command names + arg/return types
│   │   └── codegen.ts        # script: read backend catalog → emit commands.ts
│   ├── stores/
│   │   ├── machine.ts        # position, velocity, functional status
│   │   ├── io.ts             # binary inputs / sensors
│   │   ├── run.ts            # process state, stage, errors
│   │   ├── connection.ts     # WS connection + error inhibit reactive flag
│   │   └── version.ts
│   ├── components/           # Atoms / shared primitives
│   │   ├── ToggleButton.tsx
│   │   ├── NumberField.tsx
│   │   ├── Dialog.tsx
│   │   ├── Slider.tsx
│   │   └── ErrorBlinker.tsx
│   ├── modules/              # 1:1 port of /web/desktop/modules
│   │   ├── ManualMove.tsx
│   │   ├── PositionGraphic.tsx
│   │   ├── MotorStatus.tsx       # thin viewer; data lives in machineStore
│   │   ├── IncrementalJog.tsx
│   │   ├── RunStatus.tsx
│   │   ├── G_Code.tsx
│   │   ├── QueuedMotionPreview.tsx
│   │   ├── Sliders.tsx
│   │   ├── FullStop.tsx
│   │   ├── Time.tsx
│   │   ├── Version.tsx
│   │   ├── VersionDetails.tsx
│   │   ├── PLC_Status.tsx
│   │   ├── RecentLog.tsx
│   │   └── Overlay.tsx
│   ├── pages/                # 1:1 port of /web/desktop/pages
│   │   ├── APA.tsx
│   │   ├── MachineLayout.tsx
│   │   ├── Calibrate.tsx
│   │   ├── MachineGeometryCalibrate.tsx
│   │   ├── ZPlaneCalibrate.tsx
│   │   ├── RollerCalibrate.tsx
│   │   ├── GCodeGeneration.tsx
│   │   ├── Log.tsx
│   │   ├── Configuration.tsx
│   │   ├── IO.tsx
│   │   └── ManualMovePopup.tsx
│   ├── shell/
│   │   ├── AppShell.tsx      # header / footer / nav
│   │   └── theme.css         # global tokens, ports main.css palette
│   └── images/               # copied from web/desktop/images/
└── dist/                     # vite build output, served by Python at /next/
```

## Backend changes (minimal)

Touch points in `src/dune_winder/`:

- `src/dune_winder/threads/web_server_thread.py` — mount `dune_winder/web_next/dist/` at `/next/`. Keep existing mount.
- `src/dune_winder/library/web_server_interface.py` — add a WebSocket upgrade path at `/api/v2/state`. On accept, push `process.get_ui_snapshot` payload every 100ms. No new state computation; reuse the existing snapshot function.
- `src/dune_winder/api/commands.py` — add a `dump_catalog()` helper that emits the catalog as JSON for the codegen script. No behaviour change.

Existing `/api/v2/command` and `/api/v2/batch` endpoints are unchanged. Every command in `CommandCatalog.js` continues to work identically.

## Phasing

**Phase 0 — Scaffolding (1 PR)**
- Create `web_next/` Vite + Solid + TS skeleton; ESLint + Prettier; `npm run build` produces `dist/`.
- Wire `web_server_thread.py` to mount `/next/`. Smoke test: visit `/next/` and see "hello" page.
- Codegen script: read `CommandCatalog.js` (or `commands.py`), emit `client/commands.ts`. CI step verifies no drift.

**Phase 1 — Spine (1 PR)**
- `client/transport.ts` (REST), `client/socket.ts` (WS, with reconnect + backoff), `stores/*`.
- `AppShell` with header/footer/nav matching old `main.css` look.
- Add `/api/v2/state` WS handler in `web_server_interface.py`.
- Connection store drives the global "comms lost" UI inhibit (a single reactive `disabled` signal that any component can consume).

**Phase 2 — Vertical slice (1 PR)**
- Port `PositionGraphic` (SVG for static lines, canvas for path history).
- Port `MachineLayout` page.
- Port `MotorStatus`, `Time`, `Version`, `RunStatus`, `FullStop`, `PLC_Status` — small modules needed for shell/header.
- Acceptance: side-by-side comparison, machine running, screenshots match within reason.

**Phase 3 — Manual control (1 PR)**
- Port `ManualMove` (incl. pop-out window using `window.open` + shared store via `BroadcastChannel`).
- Port `IncrementalJog`, `Sliders`, `ManualMovePopup` page.

**Phase 4 — APA workflow (1 PR)**
- Port `G_Code`, `QueuedMotionPreview`.
- Port `APA` page (recipe load, layer select, pin segment lookup, forecast log polling).

**Phase 5 — Calibration suite (1–2 PRs)**
- Port `Calibrate`, `MachineGeometryCalibrate`, `ZPlaneCalibrate`, `RollerCalibrate`.

**Phase 6 — Operations & misc (1 PR)**
- Port `IO`, `Log`, `RecentLog`, `Configuration`, `GCodeGeneration`, `VersionDetails`, `Overlay`.

**Phase 7 — Cutover (1 PR)**
- Operator sign-off after a week of side-by-side use.
- Make `/` serve `web_next/dist/`; mount old `web/desktop/` at `/legacy/` for one release; then delete.

## Key design notes

**Reactivity contract.** Every backend-derived value lives in a Solid store. Components use `createEffect` / signal access; cleanup is automatic on unmount, fixing the periodic-callback leak in `Winder.js`.

**Error inhibit.** `connection.ts` exposes `connected: Accessor<boolean>` and `inhibit: Accessor<boolean>` (true while WS down OR while a manual `inhibit()` scope is active). `<ToggleButton>` and `<NumberField>` consume `inhibit` automatically — replaces the additive counter and the cross-cutting `winder.inhibitUpdates` calls.

**Commands.** `client/commands.ts` is generated. Each command is a typed function: `await commands.process.manualSeekXY({x, y, velocity})`. The batch endpoint is exposed as `commands.batch([...])` returning a typed tuple. No more stringly-typed `winder.call("name", {...})`.

**Pop-out windows (ManualMovePopup).** The popup is a separate Vite entry; it opens via `window.open("/next/manual-move-popup")` and shares state with the parent via `BroadcastChannel("dune-winder-state")` plus its own WS connection (cheaper than parent-proxying).

**Canvas vs SVG.** `PositionGraphic` static frame, axes, status lights, head/arm angles → SVG (declarative, easy to test). Path history (potentially thousands of segments) → canvas inside the same component, redrawn only when new points arrive.

**Behaviour parity.** No UX changes. Same buttons, same labels, same colour palette, same keyboard shortcuts. Theme port is a literal translation of `main.css` palette into CSS custom properties. Any UX change is a separate PR after cutover.

**Type discipline.** `strict: true` in tsconfig. Store shapes derived from a hand-typed `MachineSnapshot` interface that mirrors `process.get_ui_snapshot`'s output — single source of truth on the wire, validated at the WS boundary.

## Critical files

Read before starting:
- `dune_winder/web/scripts/Winder.js` — polling semantics to preserve in `socket.ts`/`transport.ts`.
- `dune_winder/web/scripts/UiServices.js` + `CommandCatalog.js` — input to codegen.
- `dune_winder/web/desktop/modules/PositionGraphic.js` — geometry math + scaling constants to lift verbatim.
- `dune_winder/web/desktop/pages/APA.js` — the most complex page, drives data-shape decisions.
- `src/dune_winder/library/web_server_interface.py` — extension point for WS.
- `src/dune_winder/threads/web_server_thread.py` — mount config.
- `src/dune_winder/api/commands.py` — backend catalog source for codegen.

To modify:
- `src/dune_winder/library/web_server_interface.py` (WS endpoint)
- `src/dune_winder/threads/web_server_thread.py` (mount `/next/`)
- `src/dune_winder/api/commands.py` (catalog dump helper)
- New: everything under `dune_winder/web_next/`

## Verification

**Per phase:**
- `npm run build` clean, `tsc --noEmit` clean, ESLint clean.
- Vitest unit tests for stores, transport, codegen output shape.
- For each ported module: a Solid Testing Library test that mounts it against a mocked transport and asserts DOM matches a snapshot of the legacy module's rendered HTML for the same input.

**End-to-end (manual, on hardware or simulator):**
1. Start backend in simulator mode; open `/` (legacy) and `/next/` (new) in two tabs.
2. For each ported page, perform the operator's standard checklist (jog, load recipe, run, e-stop, calibrate). Behaviour identical.
3. Pull the network for 10s, restore — both UIs disable controls during outage and re-enable cleanly. New UI uses WS reconnect with exponential backoff capped at 5s.
4. Run a full APA recipe end-to-end on the simulator; logs and graphics match between the two UIs.

**Cutover gate:**
- Operator sign-off after one full week of dual operation with no regression reports.
- Performance: WS keeps CPU ≤ legacy 100ms-poll baseline.
