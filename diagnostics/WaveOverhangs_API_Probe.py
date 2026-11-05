# /// script
# requires-python = ">=3.12"
#
# [tool.orcaslicer.plugin]
# name = "Wave Overhangs (API Probe)"
# description = "Read-only diagnostic for OrcaSlicer 2.5.0 plugin and slicing-pipeline APIs."
# author = "WaveOverhangs contributors"
# version = "0.3.0"
# ///

import inspect
import json
import traceback
import orca


def _safe_repr(value, limit=350):
    try:
        text = repr(value)
    except Exception as exc:
        text = "<repr failed: {}>".format(exc)
    return text if len(text) <= limit else text[:limit] + "..."


def _safe_type(value):
    try:
        cls = type(value)
        return "{}.{}".format(cls.__module__, cls.__qualname__)
    except Exception as exc:
        return "<type failed: {}>".format(exc)


def _safe_dir(value):
    if value is None:
        return []
    try:
        return sorted(name for name in dir(value) if not name.startswith("__"))
    except Exception as exc:
        return ["<dir failed: {}>".format(exc)]


def _safe_getattr(value, name):
    try:
        result = getattr(value, name)
        return "<callable>" if callable(result) else _safe_repr(result)
    except Exception as exc:
        return "<unavailable: {}>".format(exc)


def _descriptor_hints(value, names):
    """Read class descriptors only; do not assign to or mutate runtime objects."""
    result = {}
    try:
        cls = type(value)
        for name in names:
            descriptor = inspect.getattr_static(cls, name, None)
            if descriptor is None:
                continue
            item = {"descriptor_type": _safe_type(descriptor)}
            if isinstance(descriptor, property):
                item["property_has_setter"] = descriptor.fset is not None
                item["property_has_deleter"] = descriptor.fdel is not None
            result[name] = item
    except Exception as exc:
        result["<inspection_error>"] = str(exc)
    return result


def _inspect_object(value, candidate_attrs, depth=0):
    if value is None:
        return {"is_none": True}
    result = {
        "type": _safe_type(value),
        "repr": _safe_repr(value),
        "symbols": _safe_dir(value)[:100],
        "attributes": {},
    }
    for name in candidate_attrs:
        try:
            member = getattr(value, name)
            if callable(member):
                result["attributes"][name] = "<callable>"
            else:
                result["attributes"][name] = _safe_repr(member)
        except Exception as exc:
            result["attributes"][name] = "<unavailable: {}>".format(exc)
    result["descriptor_hints"] = _descriptor_hints(value, candidate_attrs)
    return result


def _inspect_collection(value, item_attrs, label, max_items=2):
    if value is None:
        return {"label": label, "is_none": True}
    result = {
        "label": label,
        "type": _safe_type(value),
        "repr": _safe_repr(value),
        "symbols": _safe_dir(value)[:100],
        "length": _safe_getattr(value, "__len__"),
        "mutation_method_hints": [
            name for name in ("append", "extend", "insert", "add", "set",
                              "clear", "pop", "remove", "erase")
            if callable(getattr(value, name, None))
        ],
        "sample": [],
    }
    try:
        iterator = iter(value)
        for index in range(max_items):
            try:
                item = next(iterator)
            except StopIteration:
                break
            result["sample"].append({
                "index": index,
                "item": _inspect_object(item, item_attrs),
            })
    except Exception as exc:
        result["iteration_error"] = "{}: {}".format(type(exc).__name__, exc)
    return result


_LAYER_ATTRS = (
    "id", "layer_id", "print_z", "height", "slice_z", "regions",
    "layer_regions", "perimeters", "fills", "slices", "lslices",
    "lslices_ex", "support_fills", "support_islands",
)
_REGION_ATTRS = (
    "id", "region_id", "perimeters", "fills", "thin_fills",
    "fill_surfaces", "slices", "slices_ex",
)
_PATH_ATTRS = (
    "role", "width", "height", "mm3_per_mm", "flow", "is_loop",
    "points", "polyline", "polygon", "first_point", "last_point",
    "reverse", "clone",
)
_OBJECT_ATTRS = (
    "id", "name", "layers", "support_layers", "model_object",
    "layer_count", "bounding_box", "instances",
)


def _inspect_layers(owner, attr_name, max_layers=2):
    try:
        collection = getattr(owner, attr_name)
    except Exception as exc:
        return {"label": attr_name, "access_error": str(exc)}
    layers = _inspect_collection(collection, _LAYER_ATTRS, attr_name, max_layers)
    for sample in layers.get("sample", []):
        layer = sample.get("item", {})
        # Inspect region collections and common geometry collections on sampled layers.
        raw_layer = None
        try:
            raw_layer = next(iter(collection)) if len(layers.get("sample", [])) == 1 else None
        except Exception:
            pass
        # The sample's attributes already record repr/type; collection details are
        # gathered separately below without invoking arbitrary methods.
        attrs = layer.get("attributes", {})
        nested = {}
        for nested_name in ("regions", "layer_regions", "perimeters", "fills",
                            "slices", "lslices", "lslices_ex"):
            try:
                candidate = getattr(raw_layer, nested_name) if raw_layer is not None else None
                if candidate is not None and not callable(candidate):
                    nested[nested_name] = _inspect_collection(
                        candidate, _REGION_ATTRS if nested_name in ("regions", "layer_regions")
                        else _PATH_ATTRS, nested_name, 2
                    )
            except Exception as exc:
                nested[nested_name] = {"access_error": str(exc)}
        if nested:
            layer["nested_collections"] = nested
    return layers


def _inspect_pipeline_geometry(ctx, step):
    result = {}
    try:
        print_obj = getattr(ctx, "print", None)
    except Exception:
        print_obj = None
    try:
        object_obj = getattr(ctx, "object", None)
    except Exception:
        object_obj = None

    if print_obj is not None:
        try:
            objects = getattr(print_obj, "objects")
            result["print_objects"] = _inspect_collection(
                objects, _OBJECT_ATTRS, "print.objects", 2
            )
        except Exception as exc:
            result["print_objects"] = {"access_error": str(exc)}

    if object_obj is not None:
        result["current_object"] = _inspect_object(object_obj, _OBJECT_ATTRS)
        for name in ("layers", "support_layers"):
            result[name] = _inspect_layers(object_obj, name, 2)

    # Report the runtime geometry API types exposed by orca.host, not just names.
    host = getattr(orca, "host", None)
    if host is not None:
        result["geometry_type_symbols"] = [
            name for name in _safe_dir(host)
            if any(token in name.lower() for token in (
                "layer", "region", "extrusion", "polygon", "expolygon", "surface"
            ))
        ]
        for type_name in ("Layer", "LayerRegion", "ExtrusionPath",
                          "ExtrusionEntity", "ExtrusionLoop"):
            cls = getattr(host, type_name, None)
            if cls is not None:
                result.setdefault("host_type_details", {})[type_name] = {
                    "type": _safe_type(cls),
                    "symbols": _safe_dir(cls)[:100],
                }
    return result


def _result_message(marker, report, limit=11500):
    payload = json.dumps(report, ensure_ascii=False, separators=(",", ":"), default=str)
    message = marker + " " + payload
    if len(message) <= limit:
        return message
    compact = {
        "truncated": True,
        "original_message_chars": len(message),
        "report_preview": payload[:limit - 180],
    }
    return marker + " " + json.dumps(compact, ensure_ascii=False, separators=(",", ":"))


_PIPELINE_REPORTED_STEPS = set()
_GEOMETRY_STEPS = ("posSlice", "posPerimeters", "posInfill")


class WaveOverhangsApiReport(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "Wave Overhangs API Report"

    def get_default_config(self):
        return {
            "enabled": False,
            "pattern": "smart",
            "line_spacing": 0.35,
            "print_speed": 2.0,
            "flow_mm3_per_mm": 0.16,
            "fan_speed": 100,
            "floor_layers": 2,
        }

    def execute(self):
        report = {
            "plugin": "Wave Overhangs API Probe",
            "plugin_version": "0.3.0",
            "orca_version": _safe_getattr(orca, "__version__"),
            "orca_type": _safe_type(orca),
            "orca_module_symbols": _safe_dir(orca),
            "slicing_module_symbols": _safe_dir(getattr(orca, "slicing", None)),
            "host_module_symbols": _safe_dir(getattr(orca, "host", None)),
        }
        try:
            slicing = getattr(orca, "slicing", None)
            step_enum = getattr(slicing, "Step", None) if slicing else None
            if step_enum is not None:
                report["slicing_step_values"] = [
                    {"name": name, "value": _safe_getattr(step_enum, name)}
                    for name in _safe_dir(step_enum)
                ]
            host = getattr(orca, "host", None)
            if host is not None and callable(getattr(host, "model", None)):
                try:
                    model = host.model()
                    report["model_access"] = "available"
                    report["model_type"] = _safe_type(model)
                    report["model_symbols"] = _safe_dir(model)
                    report["model_objects"] = _safe_getattr(model, "objects")
                except Exception as exc:
                    report["model_access"] = "not ready or denied: {}".format(exc)
            report["saved_config"] = json.loads(self.get_config())
            message = _result_message("[WAVE_OVERHANGS_API_PROBE]", report)
            print(message)
            return orca.ExecutionResult.success(message)
        except Exception as exc:
            details = traceback.format_exc()
            message = _result_message(
                "[WAVE_OVERHANGS_API_PROBE_ERROR]",
                {"error": str(exc), "traceback": details},
            )
            print(message)
            return orca.ExecutionResult.failure(
                orca.PluginResult.RecoverableError, message, details
            )


class WaveOverhangsPipelineProbe(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self):
        return "Wave Overhangs Pipeline Probe"

    def execute(self, ctx):
        try:
            step = _safe_getattr(ctx, "step")
            step_key = str(step)
            report = {
                "plugin": "Wave Overhangs Pipeline Probe",
                "plugin_version": "0.3.0",
                "context_type": _safe_type(ctx),
                "step": step,
                "context_symbols": _safe_dir(ctx),
                "print_type": _safe_type(getattr(ctx, "print", None)),
                "object_type": _safe_type(getattr(ctx, "object", None)),
                "gcode_path": _safe_getattr(ctx, "gcode_path"),
                "output_name": _safe_getattr(ctx, "output_name"),
                "cancelled": _safe_getattr(ctx, "cancelled"),
            }
            config_value = getattr(ctx, "config_value", None)
            if callable(config_value):
                report["config_values"] = {}
                for key in ("layer_height", "wall_loops", "detect_overhang_wall"):
                    try:
                        report["config_values"][key] = _safe_repr(config_value(key))
                    except Exception as exc:
                        report["config_values"][key] = "<error: {}>".format(exc)

            if step_key not in _PIPELINE_REPORTED_STEPS:
                _PIPELINE_REPORTED_STEPS.add(step_key)
                if any(token in step_key for token in _GEOMETRY_STEPS):
                    report["geometry_inspection"] = _inspect_pipeline_geometry(ctx, step)
                message = _result_message("[WAVE_OVERHANGS_PIPELINE_PROBE]", report)
            else:
                message = "Wave Overhangs pipeline probe observed step {} (details already logged).".format(step)

            print(message)
            return orca.ExecutionResult.success(message)
        except Exception as exc:
            details = traceback.format_exc()
            message = _result_message(
                "[WAVE_OVERHANGS_PIPELINE_PROBE_ERROR]",
                {"error": str(exc), "traceback": details},
            )
            print(message)
            return orca.ExecutionResult.failure(
                orca.PluginResult.RecoverableError, message, details
            )


@orca.plugin
class WaveOverhangsPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(WaveOverhangsApiReport)
        orca.register_capability(WaveOverhangsPipelineProbe)
