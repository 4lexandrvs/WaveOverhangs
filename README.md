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

## Current validation target

- OS: Windows 10
- Slicer: OrcaSlicer 2.5.0 Release
- First deliverable: a diagnostic plugin that reports the actual runtime API without modifying a print.
