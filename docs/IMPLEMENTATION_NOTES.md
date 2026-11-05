# Implementation notes

## Reference algorithm and integration boundary

The reference implementation is Janis A. Andersons' Wave Overhangs algorithm, building on Steven McCulloch's arc-overhang work and its PrusaSlicer/OrcaSlicer integrations. The OrcaSlicer port is maintained by Dennis Klappe:

- https://github.com/dennisklappe/OrcaSlicer-WaveOverhangs
- https://github.com/stmcculloch/PrusaSlicer-WaveOverhangs

The reference generator creates wavefront polylines as **extrusion paths** and returns residual area for the slicer's infill pipeline. OrcaSlicer 2.5.0's public Python plugin bindings do not expose writable extrusion-entity collections. They do expose mutable slice SurfaceCollections before perimeter generation.

That means a Python plugin cannot yet reproduce the original algorithm faithfully: it cannot inject the original open wavefront paths or assign their per-path extrusion parameters. A native slicer change or a future host API extension is required for exact parity.

## Prototype 0.1.0

plugin/WaveOverhangs.py is an independent contour-level experiment:

1. Runs at Step.posSlice, before perimeter generation.
2. For each layer after the first, computes unsupported geometry as the current region surface minus the previous layer's merged slices.
3. Samples the current outer contour and applies a sinusoidal normal displacement only where a point just inside the contour falls in that unsupported geometry.
4. Replaces the affected region's surfaces through SurfaceCollection.set/append, then calls Layer.make_slices().
5. Leaves supported contour sections unchanged and lets OrcaSlicer generate ordinary perimeters.

This creates a wavy perimeter on unsupported contour sections; it is **not** the original internal wavefront path algorithm. It is intended to test the geometry route and visual behavior, not to claim feature parity.

### Initial parameters

- amplitude: 0.12 mm
- period: 1.20 mm
- contour sample spacing: period × 0.125
- inside probe: 0.04 mm

The values are conservative starting points and will be tuned against a disposable test model. If the resulting contours self-intersect, produce poor transitions, or alter supported geometry, the prototype must be revised before broader use.

## How to try it

1. Install plugin/WaveOverhangs.py through OrcaSlicer's Plugins window.
2. Select **Wave Overhangs** under **Process → Others → Slicing Pipeline Plugin** (Advanced mode).
3. Slice a small disposable model with a simple overhang.
4. Inspect the perimeter preview and the completion message. The plugin modifies slice geometry during slicing; do not use it on a production job until its output has been visually checked.

## Next implementation milestone

The immediate target is a controlled geometry test and refinement of the contour treatment. In parallel, the exact Wave Overhangs route requires an extrusion-path insertion API or a minimal native integration point. The project should prefer that native route if contour deformation cannot preserve the reference algorithm's intended paths, flow, ordering, and infill interaction.

## Licensing and attribution

The reference projects are AGPL-3.0. This prototype is independently written and does not copy their C++ implementation. Any future port or adaptation of reference source must retain its copyright notices and comply with AGPL-3.0 or later as applicable.
