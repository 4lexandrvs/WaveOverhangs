# WaveOverhangs for OrcaSlicer 2.5.0

A project to investigate and implement Wave Overhangs as an OrcaSlicer plugin for the **Windows 10 / OrcaSlicer 2.5.0 Release** environment.

> **Status: experimental geometry prototype 0.1.0.** A Python slicing-pipeline plugin now applies a sinusoidal contour displacement to unsupported perimeter sections before normal perimeter generation. This is an early contour-level approximation, not yet the original Wave Overhangs extrusion-path algorithm.

## Goals

- Reproduce the Wave Overhangs behavior from the reference implementation.
- Integrate with the official OrcaSlicer plugin system where its public API permits.
- Keep the workflow compatible with an unmodified OrcaSlicer 2.5.0 Release installation if technically possible.
- Clearly separate native geometry integration from any G-code post-processing fallback.

## Current implementation

- `plugin/WaveOverhangs.py` — first contour-level geometry prototype. It detects unsupported contour sections and adds a sinusoidal displacement before perimeter generation.
- `diagnostics/` — read-only API probes retained as development evidence; no further broad probing is planned.
- `docs/IMPLEMENTATION_NOTES.md` — algorithm boundary, prototype behavior, and next milestone.

The reference implementation emits open wavefront extrusion paths. The Python plugin API can modify slice geometry but cannot currently insert arbitrary extrusion entities. The present prototype is therefore an experimental approximation; exact parity may require a small native extrusion-path integration point.

## Planned layout

- `plugin/` — plugin entry point and UI/settings.
- `src/` — Wave Overhangs implementation.
- `diagnostics/` — API probes and runtime reports.
- `tests/` — geometry and integration tests.
- `docs/` — design notes, compatibility matrix, and installation instructions.

## Reference implementations

- [OrcaSlicer-WaveOverhangs](https://github.com/dennisklappe/OrcaSlicer-WaveOverhangs)
- [PrusaSlicer-WaveOverhangs](https://github.com/stmcculloch/PrusaSlicer-WaveOverhangs)
- [OrcaSlicer plugin development documentation](https://www.orcaslicer.com/wiki/developer_reference/plugin_development/plugin_development)

## Licensing

The reference implementation is distributed under AGPL-3.0. Before incorporating or adapting its code, preserve the applicable copyright notices and comply with the license. The repository's license file and attribution will be added before redistributing derived implementation code.

## Verified OrcaSlicer API findings

The exact source revision reported by the diagnostic log (`af2ffb8c`) includes the Python slicing-pipeline capability. Python plugins can modify slice and fill surface geometry before toolpath generation. However, the exposed extrusion tree is read-only: the Python bindings do not provide operations to insert or replace extrusion paths.

This creates a potentially simpler Python-only route: modify the slice contours at `Step.posSlice`, then let OrcaSlicer generate ordinary perimeters and infill from the changed geometry. This is a real native geometry change, not G-code rewriting. It is not yet proven that the Wave Overhangs pattern can be represented this way without unacceptable side effects; that is the next prototype target. Direct insertion/replacement of arbitrary `ExtrusionPath` objects remains unavailable in the exposed Python bindings. See [docs/API_FINDINGS.md](docs/API_FINDINGS.md) for source-level evidence and the decision gate.

The current API probe is version 0.9.0. It writes detailed, read-only JSONL reports to `%APPDATA%\\OrcaSlicer\\log\\WaveOverhangs_API_Probe_0.9.0.jsonl` and puts a compact summary into `ExecutionResult.message`, which is recorded in the main `debug_*.log`. In addition to the 0.8.0 extrusion-path inspection, version 0.9.0 inspects the runtime `SurfaceCollection` API, its mutator signatures, surface geometry and `ExPolygon` methods. It never calls mutators or changes live geometry. The slicing-pipeline capability must also be selected under **Process → Others → Slicing Pipeline Plugin** (Advanced mode) before its callback runs. The log line saying that the plugin has no registered printer-agent capabilities is normal for a plugin that does not implement a printer connection; it is not a general plugin-registration error.

## Current validation target

- OS: Windows 10
- Slicer: OrcaSlicer 2.5.0 Release (`af2ffb8c`)
- Current deliverable: contour-level geometry prototype 0.1.0; test on a disposable model before production use.
