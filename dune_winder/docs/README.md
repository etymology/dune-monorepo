# Documentation

This directory contains reference documentation, architecture notes, and active
planning docs for the dune_winder project.

## Subdirectories

| Directory | Contents |
| --- | --- |
| [architecture/](architecture/) | How the current system works — architecture, protocols, and implementation reference |
| [recipes/](recipes/) | Recipe layer specs and G-code reference for U, V, X, and G layers |
| [planning/](planning/) | Active design docs and improvement backlog for future work |
| [Chicago PLC and recipes/](Chicago%20PLC%20and%20recipes/) | Historical materials shared with the controls group; PLC project files, calibration spreadsheets |
| [is8200/](is8200/) | Calibration camera (In-Sight 8200) documentation and configuration snapshots |
| [rockwell/](rockwell/) | Rockwell PLC ladder logic and motion control reference manuals — useful context when working on PLC code |

## Architecture

| File | Description |
| --- | --- |
| [architecture/plc-communication.md](architecture/plc-communication.md) | Python-to-PLC tag protocol, poll loop, direct motion, queue handshake |
| [architecture/plc-ladder-workflow.md](architecture/plc-ladder-workflow.md) | Studio 5000 copy/paste workflow, `plc/` layout, metadata export tools |
| [architecture/plc-ladder-simulator.md](architecture/plc-ladder-simulator.md) | Ladder-backed simulator assumptions and known simplifications |
| [architecture/circle-line-queue.md](architecture/circle-line-queue.md) | Mixed MCLM/MCCM queue implementation, UDT contract, PLC tags |
| [architecture/waypoint-path-planning.md](architecture/waypoint-path-planning.md) | Waypoint GUI planner, biarc tessellation, live position overlay |
| [architecture/filleted-polygon.md](architecture/filleted-polygon.md) | Filleted polygon path planner — `filleted_polygon_segments()` algorithm |
| [architecture/gcode-domain.md](architecture/gcode-domain.md) | G-code domain package layout (`model`, `parser`, `renderer`, `runtime`) |

## Recipes

| File | Description |
| --- | --- |
| [recipes/uv-gcode-reference.md](recipes/uv-gcode-reference.md) | G-code commands emitted by U/V generators; P-parameter reference |
| [recipes/template-language.md](recipes/template-language.md) | Mini-language used by U/V/XG recipe scripts (`emit`, `transfer`, `if`) |
| [recipes/u-layer.md](recipes/u-layer.md) | U layer recipe loop specification |
| [recipes/v-layer.md](recipes/v-layer.md) | V layer recipe loop specification |
| [recipes/xg-layer.md](recipes/xg-layer.md) | X/G layer recipe specification with camera-based wire positioning |

## Planning

| File | Description |
| --- | --- |
| [planning/architecture-backlog.md](planning/architecture-backlog.md) | Outstanding architectural improvements (P2, P3, P0 proposals, feature backlog) |
| [planning/plc-ladder-port.md](planning/plc-ladder-port.md) | Python PLC ladder port spec — phases 3-4 still outstanding |
| [planning/plc-architecture-proposals.md](planning/plc-architecture-proposals.md) | PLC/winder contract improvement proposals (contract package, manifest, tag registry) |
| [planning/webui-hardening.md](planning/webui-hardening.md) | Web UI reliability and modernization plan — phases 1-3 not yet complete |
