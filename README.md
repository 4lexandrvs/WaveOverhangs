# WaveOverhangs for OrcaSlicer 2.5.0

A Python slicing-pipeline plugin for unmodified OrcaSlicer 2.5.0. The implementation is experimental and remains disabled by default until runtime G-code validation is complete.

## Current development build: 0.3.0-dev

The plugin now connects the two required pipeline stages:

- At posPrepareInfill it detects unsupported fill-surface regions, propagates anchored offset wavefronts, and subtracts the wave-covered envelope from ordinary infill geometry.
- At psGCodePostProcess it injects the generated XY paths into the exported G-code at their layer Z values.

The wavefront core is adapted from the original implementation by Janis A. Andersons, based on Steven McCulloch's arc-overhang algorithm and integrated into OrcaSlicer by Dennis Klappe:
https://github.com/dennisklappe/OrcaSlicer-WaveOverhangs

The adaptation preserves attribution and is licensed under AGPL-3.0-or-later.

## Implemented in this development build

- Anchoring band derived from the lower layer's geometry.
- Initial processing is restricted to internal fill surfaces; top/bottom skins and bridge surfaces keep OrcaSlicer's native strategy.
- Repeated polygon-offset propagation at configurable wave spacing.
- Wavefront path extraction and clipping to an inset overhang boundary.
- Covered-area calculation and subtraction from fill_surfaces before infill generation.
- Export-stage G-code insertion with layer-height matching.
- Rounded-bead extrusion-volume calculation and conservative checks for unsupported extrusion modes and print setups.

## Not yet implemented / not production-ready

- Full Smart bridgeability heuristics.
- Narrow-neck splitting, ZigZag joining, and corner-aware spacing taper from the reference.
- Exact native polyline clipping; the Python port uses bounded segment sampling.
- Full validation of all printer start/end scripts, firmware modes, pressure advance, and retraction behavior.
- Multi-object, multi-instance, and multi-tool support.

The current supported test envelope is one print object, one printable instance, one extruder, non-volumetric extrusion, and absolute XY motion. Unsupported cases are skipped or rejected rather than guessed.

## Safety

The feature is disabled by default. Enable it only for disposable test exports. Do not use this development build for a real print until the generated paths and modified G-code have been inspected and validated on a test model.

Post-processed G-code is not reflected in OrcaSlicer's G-code preview.

## Repository layout

- plugin/WaveOverhangs.py — plugin entry point, geometry integration, and G-code post-processing.
- plugin/wavefront_engine.py — standalone copy of the geometric core for development.
- plugin/gcode_emitter.py — standalone G-code emitter helper.
- tests/ — helper tests.
- diagnostics/ — read-only API probes retained as development evidence.
- docs/IMPLEMENTATION_NOTES.md — architecture, algorithm port status, and validation requirements.

## Reference implementations

- https://github.com/dennisklappe/OrcaSlicer-WaveOverhangs
- https://github.com/stmcculloch/PrusaSlicer-WaveOverhangs

## License

AGPL-3.0-or-later. See LICENSE.
