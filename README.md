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

This adaptation retains attribution and is licensed under **AGPL-3.0-or-later**. See [LICENSE](LICENSE).
