# Implementation notes

## Target and architecture

Target: unmodified OrcaSlicer 2.5.0, source/build revision af2ffb8c. The implementation is a Python slicing-pipeline plugin; it does not require a slicer fork or custom C++ build.

The plugin connects two pipeline stages:

1. Step.posPrepareInfill: after prepare_infill and before make_fills. The plugin examines internal non-bridge fill surfaces, detects unsupported portions, generates anchored offset wavefronts, and subtracts the wave-covered envelope from LayerRegion.fill_surfaces.
2. Step.psGCodePostProcess: edits the exported G-code file in place and inserts saved numeric XY paths at matching physical layer Z moves.

The Orca geometry graph is not retained between callbacks. Only plain numeric XY paths and layer heights are kept by the capability instance.

## Reference algorithm and attribution

The port is based on the original Wave Overhangs implementation:

- Wave overhang generation: Janis A. Andersons
- Arc-overhang algorithm: Steven McCulloch
- PrusaSlicer integration: Steven McCulloch
- OrcaSlicer port: Dennis Klappe
- Reference: https://github.com/dennisklappe/OrcaSlicer-WaveOverhangs

The adaptation retains attribution and is distributed under AGPL-3.0-or-later.

## Implemented in the current development build

### Geometry and pipeline

- Internal fill surfaces only. External surfaces, top/bottom skins, and native bridge surfaces are left to Orca. The explicit is_bridge() exclusion is required because Orca's is_internal() also returns true for stInternalBridge.
- Unsupported geometry is approximated as current internal fill surface minus the previous layer's merged slices.
- Anchor geometry is formed from the lower layer with configurable seed reach (default 0.55 mm).
- Wavefronts propagate through repeated polygon offsets at configured spacing.
- Candidate wave regions use Smart Bridgeability selection:
  - at least 20% of overhang area outside the anchor-region convex hull, OR
  - minimum unsupported-boundary projection cost at least 20% of measured perimeter;
  - regions with holes always qualify.
- Unsupported boundary segments are sampled against expanded anchors; this approximates the reference's exact boundary-difference operation.
- Narrow wave-cover necks are split using morphology: erode, regrow disconnected cores independently, and clip to the original region. The narrow connecting material remains available to ordinary infill.
- Seed contours are approximated as a narrow band around the boundary of slightly expanded lower-layer anchors. This is not the reference's exact open ClipperZ polyline extraction.
- Wavefront contours are clipped to an inset overhang boundary. Fully-inside segments retain original vertices; boundary-crossing segments use bounded point sampling.
- The covered envelope is subtracted from the original fill surface before ordinary infill generation.
- Object-space XY paths are transformed to printer/world XY using PrintObject.trafo().
- The plugin stores only numeric paths/heights between callbacks.

### G-code output

- Inserts paths after a physical G0/G1/G2/G3 Z move matching the layer's ;LAYER_CHANGE and ;Z: markers.
- Computes E from a rounded-bead cross-section and filament area.
- Restores E mode, absolute E coordinate, XY position, and previous feedrate after insertion.
- Requires a known XY position at the insertion point and a matching layer height.
- Rejects M200 volumetric extrusion, T1+ tool changes, G91 relative XYZ motion, invalid extrusion dimensions, and unknown XY state.
- Limits the current integration to one print object, one printable instance, one extruder, planar XY transforms, and non-volumetric extrusion.

## Approximations and missing reference features

- The reference's Z-aware Clipper open-polyline seed extraction is not exposed by the Python bindings currently used. A narrow polygon band is reconstructed using ExPolygon offsets and boolean differences. Tight concavities and nearby anchor islands may differ.
- Unsupported-boundary classification is sampled rather than using the original exact Clipper line difference.
- Polyline clipping is approximated by bounded segment sampling rather than the native intersection_pl helper.
- Narrow-neck splitting is a morphology-based approximation, not the exact reference slit construction.
- ZigZag joining, Smart path orientation, corner-aware spacing taper, and remaining reference tuning behavior are not implemented.
- Native bridge surfaces are excluded; the Smart Bridgeability heuristic is used to select among eligible internal-fill overhang regions, not to replace Orca's native bridge surfaces.

## OrcaSlicer API boundary

Verified against source revision af2ffb8c:

- LayerRegion.fill_surfaces is a mutable SurfaceCollection; set(), append(), and clear() mutate the live slicing graph.
- ExPolygon exposes offset, difference, intersection, and binary union operations.
- Step.posPrepareInfill runs before make_fills(), so fill-surface edits affect subsequent ordinary infill.
- Step.psGCodePostProcess is an export/post-process hook. ctx.print and ctx.object are unavailable there; ctx.gcode_path is used to edit the exported file.
- Extrusion entity collections are read-only from Python, so generated paths are emitted through G-code post-processing.
- Orca's G-code preview does not include paths injected after slicing.

## Runtime constraints and safety

- Feature is disabled by default. Enable only for disposable test exports.
- One print object and exactly one printable model instance are supported.
- Multi-tool prints, volumetric extrusion (M200), relative XYZ motion (G91), and non-planar transforms are unsupported.
- Exact layer heights, a matching physical Z-axis move, and known XY position at that move are required.
- Default filament diameter is 1.75 mm; configure 2.85 mm systems explicitly.
- Printer-specific start/end G-code, pressure advance, firmware retraction, and all modal command combinations have not been validated.
- Post-processed paths are not reflected in Orca's preview.

These restrictions do not imply production readiness. Do not print with this development build until runtime geometry and exported G-code have been inspected on disposable models and representative physical tests have passed.

## Repository structure and test scope

- plugin/WaveOverhangs.py is the single-file runtime entry point. The geometry core and G-code emitter are inlined because Orca's single-file plugin loader does not automatically add the plugin directory to sys.path.
- plugin/wavefront_engine.py is a standalone copy of the geometric core for development and unit tests; the runtime plugin does not import it.
- plugin/gcode_emitter.py is a standalone helper mirroring the runtime emitter; the runtime plugin does not import it.
- tests/test_wavefront_clipping.py covers sampled clipping, Smart Bridgeability numeric criteria, bridge-surface filtering, and mocked narrow-neck splitting.
- tests/test_gcode_emitter.py covers the standalone emitter's insertion and state restoration behavior. It does not directly test the inlined runtime emitter.
- GitHub Actions compiles plugin/tests and runs unittest discovery under Python 3.12.
- These tests do not execute Orca's native geometry bindings and are not a substitute for runtime validation.

## Validation roadmap

1. Runtime baseline: confirm plugin registration in stock OrcaSlicer 2.5.0 with enabled=false; prove disabled mode leaves output unchanged.
2. Geometry: run a controlled set of overhang, hole, narrow-neck, nearby-anchor, concavity, and negative-control models. Verify fill_surfaces mutation, path placement, and absence of duplicate/missing infill.
3. Algorithm parity: investigate exact polyline/Clipper bindings; replace seed and boundary approximations where possible; port ZigZag joining, Smart orientation, exact slit construction, and corner-aware spacing taper; compare against reference fixtures.
4. G-code hardening: test the inlined emitter, E accounting, G92, retractions, tool changes, start/end scripts, firmware modes, pressure advance, travel, and fail-closed behavior.
5. Compatibility: add multi-object, multi-instance, multi-tool, volumetric, and non-planar support only with dedicated implementation and tests.
6. Release readiness: complete end-to-end runtime and supervised physical tests, publish supported printer/profile matrix, installation/rollback instructions, and known limitations.

The full reference project remains the source of truth for algorithm parity. The current code is a partial plugin-only port, not a feature-complete or production-validated implementation.
