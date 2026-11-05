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
- A Python-only plugin can implement diagnostics and can prototype geometry-level transformations.
- A Python-only plugin cannot directly reproduce the native Wave Overhangs operation of replacing/adding generated extrusion paths with controlled path attributes using the exposed bindings.
- A geometry-only workaround would not be equivalent without proving that the ordinary perimeter/fill generator can produce the required wave paths and preserve the required flow, speed, cooling, and support behavior.
- Exact native integration requires an additional host-side API/bridge that can insert generated extrusion entities at the correct slicing stage, or a change to OrcaSlicer's C++ core. This is not yet a final build decision; first we will validate the installed runtime and test the minimum safe pipeline hook.

## 5. Correct interpretation of the user's log

The line

```text
Python printer-agent plugin 'WaveOverhangs_API_Probe' has no registered capabilities
```

is emitted by `NetworkAgentFactory::deregister_python_plugin()` when a plugin is being deregistered from the printer-agent subsystem and that plugin has no `PrinterConnection` capabilities. It does **not** mean that the plugin has no capabilities of any type. A Wave Overhangs plugin is expected to provide `Script` and/or `SlicingPipeline`, not a printer connection. Therefore this line is normal and is not evidence of a registration failure.

Source:
- [NetworkAgentFactory.cpp at af2ffb8c](https://github.com/OrcaSlicer/OrcaSlicer/blob/af2ffb8c/src/slic3r/Utils/NetworkAgentFactory.cpp)

The main session log did not contain the probe's custom markers. That alone does not prove the script did not run: the official plugin documentation routes Python `print()` output and tracebacks to a separate `python_*.log` file.

## 6. Next runtime check

The existing `WaveOverhangs_API_Probe.py` defines a script capability and a slicing-pipeline capability in one module. Its source structure is consistent with the API in `af2ffb8c`.

A new minimal `Plugin_Load_Probe.py` is provided separately. It deliberately imports only `orca` and registers only one Script capability. This isolates module import and capability registration from the slicing API. Its markers distinguish:
1. module import;
2. package registration;
3. capability `on_load()`;
4. manual `execute()`.

Install this single `.py` file as a local plugin through OrcaSlicer's Plugins window, confirm the capability appears, and click Run. Then collect the corresponding `python_*.log` file from `data_dir()/log/` and, if the plugin is not shown or reports an error, the Plugins dialog's Diagnostics details as well.
