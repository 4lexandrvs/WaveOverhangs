# Wave Overhangs for OrcaSlicer 2.5.0

A plugin-only Python implementation of anchored wavefront extrusion for unsupported overhang regions in **unmodified OrcaSlicer 2.5.0**. No slicer fork or custom C++ build is required.

**Development build:** 0.3.0-dev · **Status:** experimental · **Default:** disabled

> **Not production-ready.** End-to-end runtime validation in OrcaSlicer 2.5.0 is not complete. Keep the feature disabled for normal work. Enable it only for disposable test exports, inspect the exported G-code, and do not print with it until the validation roadmap is complete.

## What the plugin does

The implementation connects two OrcaSlicer slicing-pipeline hooks:

1. **Step.posPrepareInfill** — examines internal fill surfaces before ordinary infill paths are generated. It detects unsupported portions, computes anchored wavefront paths, and subtracts the area claimed by those paths from LayerRegion.fill_surfaces.
2. **Step.psGCodePostProcess** — inserts saved numeric XY paths into the exported G-code at matching layer Z moves.

This is a plugin-only workaround for the Python API boundary: Orca exposes mutable fill-surface geometry, but native extrusion-entity collections are read-only from Python. The plugin changes the geometry used by ordinary infill and emits the additional extrusion moves during G-code post-processing.

**Preview limitation:** post-processed paths are written to the exported G-code after slicing. They are not represented in OrcaSlicer's toolpath/G-code preview. The exported file, not the preview, is the authoritative artifact to inspect.

## Implemented

The following items exist in the current development code. “Implemented” means present in code; it does not mean verified on a printer.

### Pipeline integration and geometry

- Registers a SlicingPipelineCapabilityBase capability using Orca's Python plugin API.
- Uses posPrepareInfill to modify live fill_surfaces before make_fills.
- Uses the previous layer's merged slices as the support reference.
- Restricts candidates to internal fill surfaces. External surfaces, top/bottom skins, and native bridge surfaces are left to Orca. The explicit bridge check matters because Orca's Surface::is_internal() also includes stInternalBridge.
- Computes unsupported geometry as the current internal fill surface minus the previous layer's merged slices.
- Builds an anchor region from lower-layer geometry, with configurable reach to account for the inset between external walls and infill.
- Propagates wavefronts through repeated polygon offsets at configurable spacing.
- Clips generated contour paths to an inset boundary. Fully-inside contour segments retain their vertices; boundary-crossing segments are clipped using bounded point sampling.
- Calculates the wave-covered envelope and subtracts it from the original fill surface so ordinary infill does not intentionally occupy the same area.
- Transforms generated XY coordinates from object space into printer/world space using the object's transform matrix.
- Keeps only plain numeric paths and layer heights between pipeline callbacks; it does not retain Orca's temporary geometry graph.

### Wavefront selection and topology

- **Smart Bridgeability selection:** wave generation is allowed when either (a) at least 20% of the overhang area lies outside the anchor-region convex hull or (b) the minimum unsupported-boundary projection cost is at least 20% of the measured perimeter. Regions with holes always qualify. If neither metric reaches its threshold, wave generation is skipped.
- Approximates unsupported boundary segments by sampling the overhang boundary against expanded anchors. This is not the original native Clipper line-difference operation.
- Splits narrow wave-cover necks morphologically: erodes the candidate region, regrows disconnected cores independently, and clips them to the source region. Thin connecting material is left for ordinary infill.
- Reconstructs a narrow seed band around the boundary of slightly expanded lower-layer anchors. This approximates the reference implementation's open ClipperZ seed contours; it is not an exact extraction of those open polylines.

### G-code emission and safety checks

- Inserts generated paths after the physical Z move associated with a matching ;LAYER_CHANGE / ;Z: pair.
- Calculates extrusion from a rounded-bead cross-section and filament cross-sectional area.
- Handles absolute and relative E modes for inserted paths and restores the prior E mode, absolute E coordinate, XY position, and feedrate.
- Requires a known XY position at the layer Z move and a matching layer height.
- Rejects unsupported cases rather than guessing: volumetric extrusion (M200), additional tools (T1+), relative XYZ motion (G91), unknown XY position at the insertion point, and invalid extrusion dimensions.
- Limits the initial integration to one print object, one printable model instance, one extruder, planar XY transforms, and non-volumetric extrusion.
- Uses conservative defaults: the feature is disabled unless explicitly enabled.

## Current configuration

Defaults in plugin/WaveOverhangs.py:

| Setting | Default | Purpose |
|---|---:|---|
| enabled | false | Opt-in safety switch |
| line_spacing_mm | 0.35 | Wavefront spacing |
| line_width_mm | 0.42 | Emitted extrusion width |
| seed_reach_mm | 0.55 | Reach of the lower-layer anchor region |
| minimum_wave_width_mm | 0.70 | Morphological narrow-neck threshold |
| max_iterations | 160 | Maximum wave propagation iterations |
| min_area_growth_mm2 | 0.01 | Stop threshold for negligible area growth |
| filament_diameter_mm | 1.75 | Filament diameter used for E calculation |
| travel_speed_mm_min | 7200 | Travel speed for inserted paths |
| print_speed_mm_min | 1800 | Print speed for inserted paths |

For a 2.85 mm filament system, configure the filament diameter accordingly before even a disposable export test. These values are development defaults, not validated print recommendations.

## Known limitations and approximations

- **No Orca runtime validation yet.** CI and helper tests do not prove that the live plugin loads, mutates Orca geometry correctly, or produces safe printer-specific G-code.
- **Seed generation is approximate.** The reference uses Z-aware Clipper open-polyline clipping. The Python bindings used here do not expose that exact operation; the current code constructs a narrow polygon band using offsets and boolean differences. Tight concavities and nearby anchor islands can differ from the reference.
- **Boundary classification and clipping are sampled.** Sampling can move endpoints or miss very small geometric features, depending on resolution and local geometry.
- **Not a complete reference port.** ZigZag joining, Smart path orientation, corner-aware spacing taper, exact slit construction, and remaining reference tuning behavior are not implemented.
- **G-code modal coverage is incomplete.** Printer start/end scripts, firmware-specific commands, pressure advance, firmware retraction, unusual modal sequences, and every possible command combination have not been validated.
- **Preview mismatch:** injected paths do not appear in Orca's preview.
- **Restricted print setups:** multiple objects/instances, multi-tool prints, volumetric extrusion, relative XYZ movement, and non-planar transforms are not supported.
- The inlined code in plugin/WaveOverhangs.py is the runtime implementation. plugin/wavefront_engine.py and plugin/gcode_emitter.py are standalone development/test copies; they are not imported by the single-file plugin at runtime.

## How to test

### 1. Run repository checks

Requires Python 3.12:

~~~bash
python -m compileall -q plugin tests
python -m unittest discover -s tests -p "test_*.py" -v
~~~

GitHub Actions runs these same compile and unit-test steps on pushes and pull requests. These tests cover standalone helpers and mocked geometry cases; they do **not** execute Orca's native geometry bindings or the inlined plugin emitter.

### 2. Confirm plugin loading with the safe default

- Use a clean test profile in stock OrcaSlicer 2.5.0.
- Install/load the single-file plugin plugin/WaveOverhangs.py using Orca's plugin interface.
- Leave enabled = false.
- Slice a small model and inspect Orca's debug log for the capability's disabled/success message.
- Confirm that the slice and exported G-code are unchanged.

Do not enable the feature until the plugin can be loaded reliably with the safe default.

### 3. Prepare a controlled test-model set

Use separate small models or one carefully designed test plate with these cases:

1. A wide, simple unsupported shelf with a broad anchor edge.
2. An overhang with a narrow connecting neck and two wider lobes.
3. An overhang containing a hole.
4. Several nearby but separate lower-layer anchor islands.
5. A tight concavity and a very narrow overhang.
6. A model with no relevant overhang as a negative control.

Use one object, one printable instance, one tool, ordinary absolute XY movement, and non-volumetric extrusion. Keep the same printer, filament, process profile, orientation, layer height, and infill settings across comparisons.

### 4. Enable only for a disposable export

- Duplicate the test profile/project so the normal profile remains untouched.
- Set enabled = true for the plugin.
- Start with one simple model and conservative speeds.
- Slice and export to a new G-code file. Do not overwrite a known-good file.
- Record plugin messages: generated paths, affected layers, changed fill surfaces, and paths inserted during post-processing.
- If the plugin reports a skipped/unsupported setup or insertion failure, treat that as a failed test, not as a successful empty result.

### 5. Inspect the exported G-code

Search for TYPE:Wave Overhangs. For every inserted group, verify:

- It occurs at the intended layer and physical Z height.
- XY coordinates are inside the intended overhang and do not cross the model boundary.
- Ordinary infill does not also fill the area claimed by the wave paths.
- Extrusion values are positive and plausible for configured line width, layer height, and filament diameter.
- Travel moves do not cross sensitive regions in a way that causes collisions or visible defects.
- Original E mode, E coordinate, XY position, and feedrate are restored before normal G-code resumes.
- No inserted paths appear on unrelated layers.

Because Orca's preview does not include these post-processed paths, inspect the **exported G-code itself** with a suitable G-code viewer or text parser. Do not rely on the slicer preview as proof.

### 6. Compare and validate

For each model, export a baseline file with the plugin disabled and a test file with it enabled. Compare affected layers and confirm that the expected infill area was replaced rather than duplicated or removed unintentionally.

Only after geometry and G-code inspection should a small physical test be considered. Begin with a disposable calibration piece, monitor the first layers, and stop if extrusion, travel, adhesion, or toolhead behavior is abnormal. Never use an unvalidated development build for a valuable print.

## Roadmap

The roadmap is ordered by dependency and risk. A later phase must not be treated as complete merely because earlier helper tests pass.

### Phase 0 — Establish a reproducible Orca runtime baseline
- [ ] Confirm installation and capability registration in stock OrcaSlicer 2.5.0.
- [ ] Capture the exact Orca build identifier and plugin configuration used for each test.
- [ ] Confirm disabled mode leaves the slice and G-code unchanged.
- [ ] Add a reproducible disposable test project and retain its baseline G-code/logs.

**Exit criteria:** plugin loads consistently; safe default is confirmed; baseline artifacts can be reproduced.

### Phase 1 — Validate geometry mutation and wave generation
- [ ] Run the plugin on the controlled model set.
- [ ] Verify fill_surfaces changes are visible to the subsequent infill stage.
- [ ] Check for missing infill, duplicate infill, holes, self-intersections, edge leakage, and disconnected components.
- [ ] Compare anchor bands and seed behavior against the reference implementation.
- [ ] Quantify the effect of sampling resolution and seed epsilon on narrow/tight geometry.
- [ ] Add regression fixtures for every runtime geometry failure found.
- [ ] Add an optional SVG/JSON diagnostic export for overhang regions, expanded anchors, seed bands, wavefronts, covered areas, and residual infill geometry.

**Exit criteria:** repeatable geometry results on the supported one-object test envelope, with no unexplained loss or overlap of infill.

### Phase 2 — Bring the algorithm closer to the reference
- [ ] Replace sampled unsupported-boundary classification with an exact/native operation if an appropriate Orca Python binding is available; otherwise document and bound the approximation.
- [ ] Investigate exposed polyline/Clipper bindings and replace the polygon-band seed approximation with true open seed contours if possible.
- [ ] Port exact narrow-neck/slit construction and compare topology with the current morphology approximation.
- [ ] Implement ZigZag joining and Smart path orientation.
- [ ] Implement corner-aware spacing taper.
- [ ] Port remaining reference parameters and edge cases.
- [ ] Build differential geometry tests against the reference implementation on shared input fixtures.

**Exit criteria:** each ported feature has a reference comparison and explicit error bounds; remaining deviations are documented.

### Phase 3 — Harden G-code post-processing
- [ ] Test the inlined runtime emitter directly; current helper tests do not exercise it.
- [ ] Validate E accounting across absolute/relative E mode changes, G92, retractions, tool changes, and layer transitions.
- [ ] Validate start/end G-code and printer-specific modal behavior for explicitly supported printer profiles.
- [ ] Check travel routing, collision risk, pressure advance, firmware retraction, and speed/acceleration interactions.
- [ ] Add fail-closed detection for any unsupported command or state that could corrupt extrusion.
- [ ] Add automated before/after G-code invariants and parser-based regression tests.

**Exit criteria:** no state leakage or unexplained extrusion changes across the supported G-code corpus; unsupported modes reliably abort insertion.

### Phase 4 — Expand supported print configurations
- [ ] Multiple print objects and sequential printing.
- [ ] Multiple model instances and per-instance transforms.
- [ ] Multi-tool and tool-change-aware extrusion accounting.
- [ ] Volumetric extrusion and additional firmware modes, only if implemented and tested.
- [ ] Non-planar/belt/tilted coordinate transforms, only with a suitable path representation.
- [ ] Wider printer/profile compatibility matrix.

**Exit criteria:** each added configuration has dedicated tests and an explicit support declaration.

### Phase 5 — Release readiness
- [ ] Complete end-to-end Orca runtime validation on the declared supported matrix.
- [ ] Complete supervised physical test prints on representative geometries.
- [ ] Document known defects, configuration requirements, installation, rollback, and troubleshooting.
- [ ] Decide whether to keep the feature opt-in or change the default only after sufficient evidence.
- [ ] Tag a release only when the supported envelope and limitations are clear.

**Exit criteria:** reproducible runtime evidence, validated G-code, successful physical tests, and a release checklist signed off.

## Repository layout

| Path | Role |
|---|---|
| plugin/WaveOverhangs.py | Single-file Orca plugin entry point; contains the inlined runtime geometry engine and G-code post-processor |
| plugin/wavefront_engine.py | Standalone copy of the wavefront core for development and helper tests |
| plugin/gcode_emitter.py | Standalone G-code emitter helper for isolated tests |
| tests/test_wavefront_clipping.py | Tests sampled clipping, Smart Bridgeability numeric criteria, bridge-surface filtering, and mocked narrow-neck splitting |
| tests/test_gcode_emitter.py | Tests standalone G-code insertion, E-mode restoration, and rejection of unsupported modes |
| diagnostics/ | Read-only Orca API probes and captured API evidence |
| docs/API_FINDINGS.md | Findings about the OrcaSlicer 2.5.0 Python plugin API |
| docs/IMPLEMENTATION_NOTES.md | Technical architecture, API constraints, and implementation details |
| .github/workflows/python-checks.yml | Compile and unit-test workflow |

## Algorithm lineage and license

The port is based on the original Wave Overhangs work and related arc-overhang research:

- Wave overhang generation: Janis A. Andersons
- Arc-overhang algorithm: Steven McCulloch
- PrusaSlicer integration: Steven McCulloch
- OrcaSlicer port: Dennis Klappe — [OrcaSlicer-WaveOverhangs](https://github.com/dennisklappe/OrcaSlicer-WaveOverhangs)
- Related reference: [PrusaSlicer-WaveOverhangs](https://github.com/stmcculloch/PrusaSlicer-WaveOverhangs)

This adaptation retains attribution and is licensed under **AGPL-3.0-or-later**.


## Technical design details

This section records the implementation decisions and API constraints in one place so the repository can be understood from its root README without having to reconstruct the design from commit history.

### Why the plugin uses two pipeline hooks

OrcaSlicer 2.5.0 exposes mutable polygonal fill surfaces to Python, but does not expose writable native extrusion-entity collections. The plugin therefore separates the operation into two stages:

- **Geometry stage — `posPrepareInfill`:** determine which part of an eligible internal fill surface is unsupported, generate the wave paths as numeric coordinates, and remove the area covered by those paths from the fill surfaces consumed by the later infill generator.
- **Export stage — `psGCodePostProcess`:** locate the physical layer Z move in the finished G-code and insert the saved paths as extrusion moves.

The geometry objects belong to Orca's temporary slicing graph and are not kept after the callback. Only ordinary Python numeric values (XY point arrays and layer heights) are retained for the export callback. This avoids depending on native geometry objects after their valid pipeline stage.

This is deliberately a plugin-only compromise. It avoids a slicer fork, but it also means the generated paths are absent from the slicer's preview and that geometry replacement and G-code insertion must be validated independently.

### Geometry processing, in execution order

1. **Check the supported job envelope.** The current implementation accepts one print object, one printable model instance, one extruder, planar XY transforms, ordinary XYZ positioning, and non-volumetric extrusion. Unsupported configurations are rejected rather than silently approximated.
2. **Transform coordinates.** XY coordinates are converted from object space into print/world space using the print object's transform. Transforms in which XY depends on Z or Z depends on XY are rejected.
3. **Select candidate surfaces.** Only internal, non-bridge fill surfaces are considered. External walls, top/bottom skins, and native bridge surfaces remain under Orca's control. The explicit bridge exclusion is important: Orca's `Surface::is_internal()` classification also includes `stInternalBridge`.
4. **Find unsupported area.** For a current internal fill surface, the unsupported portion is approximated by subtracting the previous layer's merged slices from the current surface.
5. **Build anchors.** Lower-layer geometry is expanded by the configured anchor reach. This compensates for the gap between the lower layer's printable footprint and the inset internal infill region.
6. **Apply Smart Bridgeability selection.** Eligible overhang regions are filtered using the criteria below. This is a heuristic port, not a replacement for Orca's native bridge detection.
7. **Construct seed bands.** The current implementation derives a narrow polygon band around slightly expanded lower-layer anchor boundaries. This approximates the reference's open ClipperZ seed polylines; it does not reproduce their exact topology or source/target path IDs.
8. **Propagate wavefronts.** Repeated polygon offsets advance the wavefronts at the configured line spacing, bounded by the maximum iteration count and minimum area-growth stop condition.
9. **Clip paths.** Wave contours are clipped to an inset overhang boundary. Segments wholly inside the clipping region retain their original vertices; segments crossing the boundary are clipped with bounded point sampling.
10. **Split narrow necks.** The candidate covered region is eroded and regrown as independent components. A narrow connection that disappears during erosion is not bridged back into the wave region; it remains available to ordinary infill.
11. **Remove duplicate infill coverage.** The resulting wave-covered envelope is subtracted from the original fill surface. The live `SurfaceCollection` is rebuilt using its mutator methods so the later `make_fills` stage sees the residual fill area.
12. **Save export data.** Generated XY paths and their exact layer heights are stored as plain numeric data for the post-processing stage.

### Smart Bridgeability heuristic

The implementation uses the following OR condition for an eligible internal-fill overhang region:

- The fraction of overhang area outside the convex hull of its anchor regions is at least **20%**; or
- The minimum unsupported-boundary projection cost divided by the measured perimeter is at least **20%**; or
- The region contains one or more holes (holes always qualify).

If neither numeric criterion reaches its threshold and the region has no holes, wave generation is skipped.

The projection-cost calculation tests candidate directions derived from unsupported boundary segments. For each candidate direction it sums the absolute projection of the unsupported segments and selects the minimum cost. No unsupported segments yields zero cost. The current plugin approximates the unsupported segments by sampling the overhang boundary against expanded anchors; the reference implementation uses a more exact Clipper-based boundary operation. The thresholds and metric are therefore implemented, but their input geometry is not yet bit-for-bit equivalent to the reference.

### Narrow-neck handling

The current morphology-based split is intended to avoid allowing a thin bridge between two broad regions to make the entire connected shape eligible for wave coverage:

- Erode the candidate region by approximately half the configured minimum wave width.
- Treat disconnected eroded cores independently.
- Regrow each core and clip it to the original candidate region.
- Leave material that does not belong to a surviving core for ordinary infill.

This is an approximation of the reference's slit/narrow-neck handling, not an exact port of its construction. The default threshold is `minimum_wave_width_mm = 0.70`.

### G-code insertion and state restoration

The export hook groups generated paths by layer height and searches for the matching `;LAYER_CHANGE` / `;Z:` metadata and corresponding physical Z movement. It inserts the wave extrusion after that physical move, rather than relying on the comment alone.

For each inserted path, the emitter calculates filament E from a rounded-bead cross-section and the configured filament cross-sectional area. It tracks and restores the relevant modal state:

- absolute or relative E mode;
- absolute E coordinate, using the appropriate mode changes and `G92` restoration where required;
- current XY position;
- previous feedrate.

The implementation fails closed for detected unsupported states including `M200` volumetric extrusion, tool changes to T1 or higher, `G91` relative XYZ motion, unknown XY at the insertion point, missing exact layer height, and invalid extrusion dimensions. This list is not proof that every printer-specific G-code sequence is handled safely; the runtime emitter still needs direct testing against real Orca exports and supported printer start/end scripts.

## OrcaSlicer API findings verified for the target build

**Validation target:** OrcaSlicer 2.5.0 source/build revision `af2ffb8c`.

The following are source/API findings, not claims that the live plugin has completed end-to-end runtime validation:

- The embedded Python API exposes `orca.slicing.SlicingPipelineCapabilityBase`, the slicing `Step` enum, and capability registration.
- The plugin loader expects a module to register at least one capability. A message that a Python printer-agent plugin has no `PrinterConnection` capability is not, by itself, evidence that a slicing-pipeline plugin failed to register; these are different capability types.
- `Step.posPrepareInfill` runs after `prepare_infill` and before `make_fills`. Changes to the live `LayerRegion.fill_surfaces` at this stage can therefore affect subsequent ordinary infill generation.
- `LayerRegion.fill_surfaces` and `LayerRegion.slices` are exposed as mutable `SurfaceCollection` instances. The collection mutators include `clear()`, `set()`, and `append()`. Mutating a Python list returned by a getter is not a substitute for calling the native collection mutators.
- Bound `ExPolygon` geometry exposes polygon offset and boolean operations used by the plugin, including intersection, difference, and union-related operations.
- `Step.psGCodePostProcess` is an export/post-processing hook. At that stage `ctx.print` and `ctx.object` are not available; `ctx.gcode_path` is the file path used to edit the exported G-code.
- Native extrusion entity collections are read-only through the Python bindings. The plugin therefore cannot simply append a native `ExtrusionPath` to Orca's extrusion tree.
- G-code injected after slicing is not reflected in Orca's toolpath/G-code preview.

Useful source references for the target revision:

- [PythonPluginBridge.cpp](https://github.com/OrcaSlicer/OrcaSlicer/blob/af2ffb8c/src/slic3r/plugin/PythonPluginBridge.cpp)
- [PluginLoader.cpp](https://github.com/OrcaSlicer/OrcaSlicer/blob/af2ffb8c/src/slic3r/plugin/PluginLoader.cpp)
- [SlicingPipelinePluginCapability.cpp](https://github.com/OrcaSlicer/OrcaSlicer/blob/af2ffb8c/src/slic3r/plugin/pluginTypes/slicingPipeline/SlicingPipelinePluginCapability.cpp)
- [SlicingPipelinePluginCapability.hpp](https://github.com/OrcaSlicer/OrcaSlicer/blob/af2ffb8c/src/slic3r/plugin/pluginTypes/slicingPipeline/SlicingPipelinePluginCapability.hpp)
- [PluginHostSlicing.cpp](https://github.com/OrcaSlicer/OrcaSlicer/blob/af2ffb8c/src/slic3r/plugin/host/PluginHostSlicing.cpp)
- [Official Inset Every Slice sample](https://github.com/OrcaSlicer/OrcaSlicer/blob/af2ffb8c/sandboxes/orca_inset_plugin_any.py)
- [Official slicing-pipeline binding tests](https://github.com/OrcaSlicer/OrcaSlicer/blob/af2ffb8c/tests/slic3rutils/test_slicing_pipeline_bindings.cpp)

For a deeper record of the source investigation, see [docs/API_FINDINGS.md](docs/API_FINDINGS.md). The implementation-level notes remain in [docs/IMPLEMENTATION_NOTES.md](docs/IMPLEMENTATION_NOTES.md).

## Debugging and diagnostic evidence

When investigating plugin loading or runtime behavior, distinguish the main Orca debug log from Python's separate stdout/stderr log stream. Earlier probe versions used `print()`, which wrote the report to a separate `python_*.log` file. The API probe was later changed to include its compact JSON report in `orca.ExecutionResult.success(message)`, which is recorded in the main debug log for the relevant plugin execution path.

A log entry stating that a Python printer-agent plugin has no registered `PrinterConnection` capability can be normal for a plugin that is intended to register a slicing-pipeline capability. Diagnose registration using the plugin's actual capability type and its execution messages, not that printer-agent line in isolation.

The read-only `WaveOverhangs_API_Probe` is intended to inspect API availability and runtime object metadata. Its safe probe mode does not invoke geometry mutators such as `set()`, `append()`, `clear()`, `offset()`, or `make_slices()`. Do not treat a read-only API probe as proof that the production plugin's geometry mutation works.

## Test coverage: what current CI proves and what it does not

The repository checks currently provide three kinds of evidence:

1. **Syntax/import compilation:** Python source files compile under the CI Python version.
2. **Standalone unit tests:** geometry helper behavior, sampled clipping, Smart Bridgeability numeric criteria, bridge-surface filtering, mocked narrow-neck splitting, and standalone G-code emitter behavior.
3. **Source/API investigation:** OrcaSlicer 2.5.0 source revision `af2ffb8c` was inspected to establish which hooks and mutable geometry operations are exposed.

Current CI does **not** prove:

- that the plugin installs and registers correctly in a running OrcaSlicer GUI;
- that the inlined runtime geometry engine successfully mutates native Orca `SurfaceCollection` objects;
- that the inlined runtime G-code emitter behaves identically to the standalone helper;
- that the generated toolpaths are geometrically or thermally suitable for a particular printer/material;
- that the inserted paths are collision-free or produce a successful physical print.

The standalone files `plugin/wavefront_engine.py` and `plugin/gcode_emitter.py` intentionally mirror code inlined in `plugin/WaveOverhangs.py`. They are test/development copies, not runtime imports. A test passing in one of those files must not be described as direct runtime-plugin coverage.

## Current support matrix

| Capability or setup | Current status |
|---|---|
| Stock OrcaSlicer 2.5.0 plugin architecture | Targeted by source/API investigation; live runtime validation still pending |
| Single print object | Intended supported envelope; runtime validation pending |
| One printable model instance | Intended supported envelope; runtime validation pending |
| One extruder | Intended supported envelope; runtime validation pending |
| Planar XY object transform | Supported by current transform checks; runtime validation pending |
| Internal non-bridge fill surfaces | Implemented candidate filter |
| Native bridge surfaces, external walls, top/bottom skins | Deliberately left to Orca |
| Smart Bridgeability selection | Implemented heuristic; sampled input geometry |
| Narrow-neck split | Implemented morphology approximation |
| Exact reference open-polyline seed extraction | Not implemented; polygon-band approximation used |
| ZigZag joining, Smart path orientation, corner taper | Not implemented |
| Multiple objects or instances | Unsupported |
| Multi-tool / T1+ | Rejected |
| Volumetric extrusion / M200 | Rejected |
| Relative XYZ / G91 | Rejected |
| Non-planar transforms | Rejected |
| Orca preview of injected paths | Not available; inspect exported G-code |

## Project status and release policy

The codebase is an experimental, partial plugin-only port. There are meaningful implemented components—pipeline integration, internal-fill overhang detection, anchored offset propagation, Smart Bridgeability selection, morphology-based narrow-neck splitting, residual-fill subtraction, and G-code insertion—but algorithm parity and runtime safety are not established.

The feature remains disabled by default. Keep it disabled for normal slicing. Use disposable test projects and exports while validating it. Do not print with the feature enabled until the live Orca runtime, exported G-code, and supervised physical test phases have passed.

