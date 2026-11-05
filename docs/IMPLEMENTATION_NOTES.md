# Implementation notes

## Target and architecture

Target: unmodified OrcaSlicer 2.5.0, build revision af2ffb8c. The implementation is a Python slicing-pipeline plugin; it does not require a slicer fork or a custom C++ build.

The plugin now connects two real OrcaSlicer pipeline seams:

1. Step.posPrepareInfill: after prepare_infill and before make_fills. The plugin calculates unsupported portions of each fill surface, generates anchored offset wavefronts, and subtracts the final wave-covered envelope from LayerRegion.fill_surfaces.
2. Step.psGCodePostProcess: after the classic post-process scripts, the plugin injects the saved numeric XY paths into the exported G-code at matching layer Z markers.

The geometry graph is never retained between callbacks. Only plain numeric XY paths and layer heights are kept by the capability instance.

## Reference algorithm and attribution

The port is based on the core propagation structure of the original Wave Overhangs implementation:

- Wave overhang generation: Janis A. Andersons (andersonsjanis)
- Arc-overhang algorithm: Steven McCulloch (stmcculloch)
- PrusaSlicer integration: Steven McCulloch
- OrcaSlicer port: Dennis Klappe (dennisklappe)
- Reference source: https://github.com/dennisklappe/OrcaSlicer-WaveOverhangs

The Python implementation retains attribution and is distributed under AGPL-3.0-or-later.

### Ported in the current development build

- Process internal non-bridge fill surfaces only; top/bottom skin and both native bridge surface types remain under OrcaSlicer's native strategy. Orca's `Surface::is_internal()` also returns true for `stInternalBridge`, so the plugin explicitly checks `is_bridge()`.
- Determine overhang geometry as current fill surface minus the lower layer's merged slices.
- Form an anchor band by intersecting the overhang with an expanded lower-layer region (default reach 0.55 mm to account for the fill inset from external walls).
- Split narrow wave-cover necks by an erosion/regrowth topology pass (default minimum width 0.70 mm), keeping resulting cores separate and leaving removed neck material to ordinary infill.
- Propagate fronts independently in each resulting component by repeated polygon offsets at the configured wave spacing, clipped to that component.
- Clip generated contour segments to an inset boundary so paths do not run directly along the overhang edge.
- Return the final accumulated envelope as covered geometry.
- Subtract that envelope from the original fill surface before normal infill generation.
- Emit the generated paths through the exported-G-code post-process hook.

### Not yet ported from the full reference implementation

- Smart bridgeability heuristics and bridge-aware region selection within ordinary internal fill. Native bridge surfaces are explicitly excluded, but the reference heuristic that chooses between wave paths and ordinary bridge treatment for other overhangs is not ported.
- Reference-style closest-boundary slit construction (currently approximated by morphology-based erosion/regrowth; exact slit geometry is not yet ported).
- ZigZag path joining and Smart path orientation.
- Corner-aware spacing taper.
- All reference tuning parameters and exact C++ geometry helpers.

The Python port also approximates the reference polyline clipping operation by bounded segment sampling because the Python bindings do not expose the native intersection_pl helper. This can introduce small endpoint/shape deviations and requires runtime geometry validation.

## OrcaSlicer API boundary

Verified against source revision af2ffb8c:

- LayerRegion.fill_surfaces is a mutable SurfaceCollection; set(), append(), and clear() mutate the live slicing graph.
- ExPolygon exposes offset, difference, intersection, and binary union operations.
- Step.posPrepareInfill is before make_fills, so fill-surface edits cascade into ordinary infill.
- Step.psGCodePostProcess edits the exported G-code file in place. ctx.print and ctx.object are unavailable in that callback.
- Extrusion entity collections are read-only from Python, so generated wave paths are emitted through G-code post-processing.

## Safety restrictions in this build

- Feature is disabled by default. Enable it only for disposable test exports.
- Only one print object and one printable model instance are accepted.
- Additional tools, volumetric extrusion (M200), and relative XY motion (G91) are rejected by the G-code emitter.
- Exact layer heights, a matching physical Z-axis move, and a known XY position at that move are required.
- The emitter restores absolute E coordinates, XY position, and the previous feedrate after each inserted group.
- The default filament diameter is 1.75 mm; it must be changed in plugin settings for a 2.85 mm filament system.
- Post-processed G-code is not reflected in OrcaSlicer's G-code preview.
- The plugin does not yet validate printer-specific start/end G-code, pressure advance, firmware retraction, or every possible modal command.

These restrictions are not a claim of production readiness. Do not print with this development build until the generated geometry and exported G-code have been inspected on a disposable model and the resulting print has been validated.

## Current repository status

- plugin/WaveOverhangs.py contains the plugin entry point, pre-infill geometry integration, and G-code post-processing.
- The wavefront core is inlined in the entry point because OrcaSlicer's single-file plugin loader does not automatically add the plugin directory to Python's module search path.
- plugin/wavefront_engine.py is a standalone copy of the geometric core for development/reference; the entry point currently uses its inlined version.
- plugin/gcode_emitter.py is retained as an independently testable helper, while the plugin currently uses an inlined emitter to avoid sibling-module import assumptions.
- tests/test_gcode_emitter.py tests the standalone helper; it does not yet exercise the inlined plugin emitter.
- tests/test_wavefront_clipping.py covers the standalone polyline clipping helper. Neither test suite has been run in this environment, and neither substitutes for Orca runtime geometry validation.
- No runtime test against OrcaSlicer has yet been completed.

## Next validation steps

1. Install the plugin with enabled=false and confirm it loads.
2. Enable it for a disposable single-object, single-instance, single-extruder, non-volumetric print.
3. Confirm the pipeline log reports generated paths and changed fill surfaces.
4. Export G-code and verify that each path appears at the intended Z, with no duplicate normal infill under the covered envelope.
5. Inspect extrusion amounts, travel moves, XY transforms, layer transitions, and print preview limitations.
6. Compare a small test print with the unmodified slice before expanding support to multiple objects, instances, tools, and advanced patterns.

The full reference project remains the source of truth for algorithm parity. The current code is a first plugin-only core port, not yet a feature-complete port.
