# Implementation notes

## Target and architecture

Target: unmodified OrcaSlicer 2.5.0, build revision `af2ffb8c`. The implementation is a Python slicing-pipeline plugin; it does not require a slicer fork or a custom C++ build.

The intended plugin-only pipeline is:

1. At `Step.posPrepareInfill`, after `prepare_infill` and before `make_fills`, detect unsupported regions, generate wavefront polylines, and subtract the wave-covered area from each affected `LayerRegion.fill_surfaces` collection. The normal infill generator then sees only the residual area.
2. Persist only plain numeric path data (never Orca graph references) for the export phase.
3. At `Step.psGCodePostProcess`, insert the generated paths into the exported G-code using the actual layer Z and extrusion parameters.
4. Keep the implementation opt-in and reject print modes whose coordinate or extrusion semantics are not yet supported.

The exact OrcaSlicer source confirms that `posPrepareInfill` is before `make_fills`, while `posInfill` is too late. It also confirms that `psGCodePostProcess` edits the exported G-code file in place, with `ctx.print` and `ctx.object` unavailable at that stage. The post-processed file is not reflected in the slicer's G-code preview.

## Reference algorithm and attribution

The reference generator is Janis A. Andersons' Wave Overhangs algorithm, building on Steven McCulloch's arc-overhang work and its PrusaSlicer/OrcaSlicer integrations:

- https://github.com/dennisklappe/OrcaSlicer-WaveOverhangs
- https://github.com/stmcculloch/PrusaSlicer-WaveOverhangs

The reference algorithm propagates fronts from supported anchor boundaries, clips them to the overhang region, handles narrow regions, and returns the area actually covered by generated paths. That residual-area result is essential: ordinary infill must not be generated underneath the wave paths.

The reference projects are AGPL-3.0. Any port or adaptation must preserve required copyright notices and comply with AGPL-3.0 or later. The plugin must retain clear attribution.

## OrcaSlicer API boundary

Verified against source revision `af2ffb8c`:

- `LayerRegion.fill_surfaces` is a mutable `SurfaceCollection`; its `set()`, `append()`, and `clear()` methods mutate the live slicing graph.
- `ExPolygon` exposes offset, difference, intersection, and union operations.
- `Step.posPrepareInfill` is the correct seam for modifying fill geometry before infill generation.
- `Step.psGCodePostProcess` is the exported-G-code seam.
- Extrusion entity collections remain read-only from Python, so generated wave paths must be emitted through G-code post-processing rather than inserted into the native extrusion tree.

This API boundary does **not** imply that the feature is already implemented. It defines a plugin-only route that must be completed and validated.

## Current repository status

- `plugin/gcode_emitter.py` contains a conservative emitter for already-generated, printer-space XY paths. It now requires exact layer heights and rejects volumetric extrusion (`M200`). It is a helper, not yet connected to the geometry stage.
- `plugin/WaveOverhangs.py` still contains the earlier contour-deformation experiment as legacy code, but it is disabled by default. That experiment is not Wave Overhangs and must not be enabled as a substitute.
- The wavefront geometry generator, fill-area subtraction, path persistence, and end-to-end G-code integration remain in development.
- Until those stages are connected and tested on exported G-code, this plugin is not ready for a real print.

## Supported-scope strategy

The first end-to-end validation target should be one model object, one instance, one extruder, non-volumetric extrusion, and ordinary XY bed coordinates. The plugin must explicitly skip unsupported cases rather than emit paths with guessed transforms, heights, or extrusion values. Multi-object/instance transforms, multiple tools, volumetric extrusion, and unusual firmware modes require separate validation.

## Licensing

The project is distributed under AGPL-3.0. Preserve the original algorithm's attribution and license notices in any adapted source files.
