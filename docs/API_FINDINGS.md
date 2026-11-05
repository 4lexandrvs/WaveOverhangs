# OrcaSlicer 2.5.0 plugin API findings

**Validation target:** OrcaSlicer source revision `af2ffb8c`, matching the build identifier reported in the user's log: `2.5.0-rc build af2ffb8c`.

This document separates facts verified in that exact source revision from conclusions for the Wave Overhangs implementation.

## 1. Plugin registration

The exact source revision contains the embedded `orca` module, `@orca.plugin`, `orca.base`, `orca.register_capability`, `orca.script.ScriptPluginCapabilityBase`, and `orca.slicing.SlicingPipelineCapabilityBase`.

The loader imports the plugin module, calls the package class's `register_capabilities()`, instantiates every registered capability, then reads its `get_name()` and `get_type()`. A plugin that registers no capabilities is rejected with the error `Plugin module did not register any capabilities`.

Source:
- [PythonPluginBridge.cpp at af2ffb8c](https://github.com/OrcaSlicer/OrcaSlicer/blob/af2ffb8c/src/slic3r/plugin/PythonPluginBridge.cpp)
- [PluginLoader.cpp at af2ffb8c](https://github.com/OrcaSlicer/OrcaSlicer/blob/af2ffb8c/src/slic3r/plugin/PluginLoader.cpp)

## 2. Slicing pipeline

The exact source revision binds `orca.slicing.SlicingPipelineCapabilityBase` and a `Step` enum. The context provides:
- `ctx.step`
- `ctx.print` and `ctx.object` during geometry steps
- `ctx.config_value(key)`
- `ctx.cancelled()`
- `ctx.gcode_path`, `ctx.host`, and `ctx.output_name` at `psGCodePostProcess`

The slicing graph references are valid only for the duration of `execute(ctx)`.

Source:
- [SlicingPipelinePluginCapability.cpp at af2ffb8c](https://github.com/OrcaSlicer/OrcaSlicer/blob/af2ffb8c/src/slic3r/plugin/pluginTypes/slicingPipeline/SlicingPipelinePluginCapability.cpp)
- [SlicingPipelinePluginCapability.hpp at af2ffb8c](https://github.com/OrcaSlicer/OrcaSlicer/blob/af2ffb8c/src/slic3r/plugin/pluginTypes/slicingPipeline/SlicingPipelinePluginCapability.hpp)

## 3. What geometry can be modified through the Python bindings

The exact source revision exposes mutable slice geometry:
- `LayerRegion.slices` and `LayerRegion.fill_surfaces` are `SurfaceCollection` objects.
- `SurfaceCollection` provides `clear()`, `set()`, and `append()`.
- A live `Surface.expolygon` can be edited through the bound geometry methods.
- `Layer.make_slices()` re-derives merged layer islands after slice edits.
- The official sample pattern edits `slices` at `Step.posSlice`; the normal perimeter-generation stage then consumes the changed geometry.

However, the exposed extrusion tree is explicitly read-only:
- `LayerRegion.perimeters` and `LayerRegion.fills` are exposed as read-only `ExtrusionEntityCollection` references.
- `ExtrusionPath.points()` returns a read-only NumPy view.
- `ExtrusionPath.width`, `height`, and `mm3_per_mm` are read-only bindings.
- The Python bindings do not expose collection operations to insert, replace, or delete extrusion entities or paths.

Source:
- [PluginHostSlicing.cpp at af2ffb8c](https://github.com/OrcaSlicer/OrcaSlicer/blob/af2ffb8c/src/slic3r/plugin/host/PluginHostSlicing.cpp)
- [Official Inset Every Slice sample](https://github.com/OrcaSlicer/OrcaSlicer/blob/af2ffb8c/sandboxes/orca_inset_plugin_any.py)
- [Official slicing-pipeline binding tests](https://github.com/OrcaSlicer/OrcaSlicer/blob/af2ffb8c/tests/slic3rutils/test_slicing_pipeline_bindings.cpp)

## 4. Consequence for Wave Overhangs

The Wave Overhangs algorithm generates wavefront polylines and uses them as extrusion toolpaths. The public Python API in `af2ffb8c` can alter slice and fill geometry before toolpath generation, but it does not expose writable extrusion-path/entity collections.

Therefore:
- A Python-only plugin can modify the native slice geometry before perimeter generation; this is explicitly supported by the bound `SurfaceCollection` mutators and the official sample.
- A Python-only plugin still cannot directly insert or replace arbitrary generated extrusion paths through the current extrusion-tree bindings.
- The first implementation experiment should be a geometry-level prototype at `Step.posSlice`: alter only the relevant overhang-facing contour segments so the normal perimeter generator produces the desired wave-shaped toolpaths.
- This approach is viable only if it preserves the intended Wave Overhangs geometry, flow, speed, cooling, wall ordering, support and neighboring-layer behavior. Those properties must be tested; they must not be assumed.
- A C++ bridge/core change is needed only if the required wave path cannot be expressed safely through slice geometry, or if exact per-path extrusion parameters/order require direct extrusion-entity control. Do not choose that route before the geometry prototype is evaluated.

## 5. Correct interpretation of the user's log

The line

```text
Python printer-agent plugin 'WaveOverhangs_API_Probe' has no registered capabilities
```

is emitted by `NetworkAgentFactory::deregister_python_plugin()` when a plugin is being deregistered from the printer-agent subsystem and that plugin has no `PrinterConnection` capabilities. It does **not** mean that the plugin has no capabilities of any type. A Wave Overhangs plugin is expected to provide `Script` and/or `SlicingPipeline`, not a printer connection. Therefore this line is normal and is not evidence of a registration failure.

Source:
- [NetworkAgentFactory.cpp at af2ffb8c](https://github.com/OrcaSlicer/OrcaSlicer/blob/af2ffb8c/src/slic3r/Utils/NetworkAgentFactory.cpp)

The original probe version 0.1.0 used `print()` for its report, so the report went to the separate `python_*.log` stream. Version 0.2.0 now also embeds the compact JSON report in `orca.ExecutionResult.success(message)`. In this source revision, the Script capability's completion message is recorded in the main debug log, and non-empty success/skipped messages from slicing-pipeline capabilities are explicitly logged by `PluginHooks.cpp`. The main debug log can therefore be used to retrieve both reports without depending on the separate Python stderr file.

## 6. Next runtime check

The current `WaveOverhangs_API_Probe.py` is version 0.9.0. It remains strictly read-only: it inspects `SurfaceCollection` mutator availability and signatures but never invokes `set()`, `append()`, `clear()`, `offset()`, or `make_slices()`.

Install the updated probe through OrcaSlicer's Plugins window. Select **Wave Overhangs Pipeline Probe** under **Process → Others → Slicing Pipeline Plugin** (Advanced mode), then slice a small model. The probe records `posSlice`, `posPerimeters`, and `posInfill` to `%APPDATA%\\OrcaSlicer\\log\\WaveOverhangs_API_Probe_0.9.0.jsonl`. The key evidence is the `surface_collections` section for `region.slices` and `region.fill_surfaces`, plus the `make_slices_api` and `ExPolygon.offset` metadata. No test geometry is changed.

Send the `posSlice` and `posPerimeters` JSONL records first. If the runtime exposes the same methods as source revision `af2ffb8c`, the next step will be a separate, deliberately small geometry prototype. Do not use the probe to test mutation; mutation will be implemented only in that separate prototype and tested on a disposable model.
