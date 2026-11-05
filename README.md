# WaveOverhangs for OrcaSlicer 2.5.0

A project to investigate and implement Wave Overhangs as an OrcaSlicer plugin for the **Windows 10 / OrcaSlicer 2.5.0 Release** environment.

> **Status: bootstrap / API validation.** No Wave Overhangs geometry generation is implemented yet. The first milestone is to verify the exact plugin and slicing-pipeline APIs exposed by the official OrcaSlicer 2.5.0 build. We will not claim native path modification until it is demonstrated in that build.

## Goals

- Reproduce the Wave Overhangs behavior from the reference implementation.
- Integrate with the official OrcaSlicer plugin system where its public API permits.
- Keep the workflow compatible with an unmodified OrcaSlicer 2.5.0 Release installation if technically possible.
- Clearly separate native geometry integration from any G-code post-processing fallback.

## Technical decision gate

1. Inspect the Python plugin API and runtime objects available in OrcaSlicer 2.5.0.
2. Determine whether the slicing pipeline exposes writable layer, region, and extrusion-path data.
3. If it does, implement and test geometry generation through those supported interfaces.
4. If it does not, document the smallest required native bridge and its build/deployment implications. A G-code post-processor may be evaluated as a fallback, but it is not equivalent to native geometry integration.

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
- Slicer: OrcaSlicer 2.5.0 Release
- First deliverable: a diagnostic plugin that reports the actual runtime API without modifying a print.
