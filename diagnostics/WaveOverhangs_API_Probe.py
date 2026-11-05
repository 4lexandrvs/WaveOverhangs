# /// script
# requires-python = ">=3.12"
#
# [tool.orcaslicer.plugin]
# name = "Wave Overhangs (API Probe)"
# description = "Read-only diagnostic for OrcaSlicer 2.5.0 plugin and slicing-pipeline APIs."
# author = "WaveOverhangs contributors"
# version = "0.8.0"
# ///

import inspect
import json
import os
import tempfile
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


def _resolve_collection(owner, attr_name):
    """Read a collection attribute; call zero-argument pybind methods when needed."""
    value = getattr(owner, attr_name)
    if callable(value):
        value = value()
    return value


def _safe_length(value):
    try:
        return len(value)
    except Exception as exc:
        return "<unavailable: {}>".format(exc)


def _inspect_collection(value, item_attrs, label, max_items=2):
    if value is None:
        return {"label": label, "is_none": True}
    result = {
        "label": label,
        "type": _safe_type(value),
        "repr": _safe_repr(value),
        "symbols": _safe_dir(value)[:100],
        "length": _safe_length(value),
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


def _inspect_callable_api(owner, method_name, sample_limit=4):
    """Inspect and call known read-only collection accessors; never invoke mutators."""
    try:
        method = getattr(owner, method_name)
    except Exception as exc:
        return {"access_error": "{}: {}".format(type(exc).__name__, exc)}
    if not callable(method):
        return {"value": _safe_repr(method)}
    item = {
        "callable": True,
        "type": _safe_type(method),
        "repr": _safe_repr(method),
        "doc": _safe_repr(getattr(method, "__doc__", None), 900),
    }
    try:
        item["signature"] = str(inspect.signature(method))
    except Exception as exc:
        item["signature_error"] = "{}: {}".format(type(exc).__name__, exc)
    try:
        value = method()
        item["call_succeeded"] = True
        item["return_type"] = _safe_type(value)
        item["return_repr"] = _safe_repr(value)
        item["return_symbols"] = _safe_dir(value)[:100]
        item["return_length"] = _safe_length(value)
        if isinstance(value, (list, tuple)):
            item["return_sample"] = [
                _inspect_object(v, _PATH_ATTRS) for v in value[:sample_limit]
            ]
        elif value is not None and method_name == "flatten_paths":
            item["return_sample"] = _inspect_collection(
                value, _PATH_ATTRS, method_name, sample_limit
            )
    except Exception as exc:
        item["call_succeeded"] = False
        item["call_error"] = "{}: {}".format(type(exc).__name__, exc)
    return item


def _inspect_points(path_obj, max_points=8):
    """Read point coordinates and descriptors without changing any geometry."""
    try:
        points_method = getattr(path_obj, "points")
        if not callable(points_method):
            return {"access_error": "ExtrusionPath.points is not callable"}
        points = points_method()
        result = {
            "type": _safe_type(points),
            "repr": _safe_repr(points),
            "length": _safe_length(points),
            "symbols": _safe_dir(points)[:60],
            "descriptor_hints": _descriptor_hints(points, ("x", "y")),
            "sample": [],
        }
        try:
            for index, point in enumerate(points[:max_points]):
                result["sample"].append({
                    "index": index,
                    "point": _inspect_object(point, ("x", "y")),
                })
        except Exception as exc:
            result["sample_error"] = "{}: {}".format(type(exc).__name__, exc)
        return result
    except Exception as exc:
        return {"access_error": "{}: {}".format(type(exc).__name__, exc)}


def _inspect_value_accessor(owner, attr_name, item_attrs=(), sample_limit=4):
    """Inspect a property or zero-argument accessor and its returned value."""
    try:
        value = getattr(owner, attr_name)
        was_callable = callable(value)
        if was_callable:
            value = value()
        result = {
            "access_succeeded": True,
            "access_kind": "method_call" if was_callable else "property",
            "value_type": _safe_type(value),
            "value_repr": _safe_repr(value),
            "value_length": _safe_length(value),
            "value_symbols": _safe_dir(value)[:80],
            "descriptor_hints": _descriptor_hints(owner, (attr_name,)),
        }
        if isinstance(value, (list, tuple)):
            result["sample"] = [
                _inspect_object(item, item_attrs)
                for item in value[:sample_limit]
            ]
            # Inspecting a separate shallow copy is safe; no mutation is performed.
            try:
                snapshot = list(value)
                result["snapshot_type"] = _safe_type(snapshot)
                result["snapshot_length"] = len(snapshot)
                result["snapshot_is_accessor_result"] = snapshot is value
                result["snapshot_same_item_refs"] = all(
                    a is b for a, b in zip(snapshot, value)
                )
            except Exception as exc:
                result["snapshot_error"] = str(exc)
        return result
    except Exception as exc:
        return {"access_succeeded": False,
                "access_error": "{}: {}".format(type(exc).__name__, exc)}


def _inspect_extrusion_entities(region_obj, attr_name):
    try:
        collection = _resolve_collection(region_obj, attr_name)
        result = _inspect_collection(
            collection,
            ("role", "width", "height", "mm3_per_mm", "points", "paths"),
            attr_name,
            3,
        )
        result["descriptor_hints"] = _descriptor_hints(
            collection, ("entities", "role")
        )
        result["read_only_accessors"] = {
            "size": _inspect_callable_api(collection, "size"),
            "role": _inspect_value_accessor(collection, "role"),
            "entities": _inspect_value_accessor(
                collection, "entities", ("role", "width", "height",
                                         "mm3_per_mm", "points", "paths")
            ),
            "flatten_paths": _inspect_callable_api(collection, "flatten_paths"),
        }
        # Inspect the returned Python containers, but never mutate them.
        for method_name in ("entities", "flatten_paths"):
            accessor = result["read_only_accessors"].get(method_name, {})
            if accessor.get("access_succeeded") and accessor.get("value_type") == "builtins.list":
                try:
                    returned = getattr(collection, method_name)
                    if callable(returned):
                        returned = returned()
                    expanded = _inspect_collection(
                        returned, ("role", "width", "height", "mm3_per_mm",
                                   "points", "paths"), method_name, 4
                    )
                    if method_name == "entities":
                        for sample_item in expanded.get("sample", []):
                            try:
                                entity = returned[sample_item["index"]]
                                sample_item["paths_accessor"] = _inspect_value_accessor(
                                    entity, "paths",
                                    ("role", "width", "height", "mm3_per_mm", "points"),
                                    4
                                )
                            except Exception as exc:
                                sample_item["paths_accessor_error"] = str(exc)
                    if method_name == "flatten_paths":
                        for sample_item in expanded.get("sample", []):
                            try:
                                path = returned[sample_item["index"]]
                                sample_item["points_detail"] = _inspect_points(path)
                            except Exception as exc:
                                sample_item["points_detail_error"] = str(exc)
                    result[method_name + "_expanded"] = expanded
                except Exception as exc:
                    result[method_name + "_expanded_error"] = str(exc)
        return result
    except Exception as exc:
        return {"access_error": "{}: {}".format(type(exc).__name__, exc)}


def _inspect_layers(owner, attr_name, max_layers=2):
    try:
        collection = _resolve_collection(owner, attr_name)
    except Exception as exc:
        return {"label": attr_name, "access_error": str(exc)}
    result = {
        "label": attr_name,
        "type": _safe_type(collection),
        "repr": _safe_repr(collection),
        "symbols": _safe_dir(collection)[:100],
        "length": _safe_length(collection),
        "sample": [],
    }
    try:
        iterator = iter(collection)
        for index in range(max_layers):
            try:
                layer_obj = next(iterator)
            except StopIteration:
                break
            sample = {
                "index": index,
                "item": _inspect_object(layer_obj, _LAYER_ATTRS),
                "nested_collections": {},
            }
            for nested_name in ("regions", "layer_regions", "perimeters", "fills",
                                "slices", "lslices", "lslices_ex"):
                try:
                    candidate = _resolve_collection(layer_obj, nested_name)
                    if candidate is None:
                        continue
                    item_attrs = (_REGION_ATTRS if nested_name in ("regions", "layer_regions")
                                  else _PATH_ATTRS)
                    inspected = _inspect_collection(candidate, item_attrs, nested_name, 2)
                    sample["nested_collections"][nested_name] = inspected
                    if nested_name in ("regions", "layer_regions"):
                        for region_sample in inspected.get("sample", []):
                            try:
                                region_obj = candidate[region_sample["index"]]
                            except Exception:
                                region_obj = None
                            if region_obj is not None:
                                region_sample["extrusion_collections"] = {
                                    collection_name: _inspect_extrusion_entities(
                                        region_obj, collection_name
                                    )
                                    for collection_name in ("perimeters", "fills")
                                }
                except Exception as exc:
                    sample["nested_collections"][nested_name] = {
                        "access_error": str(exc)
                    }
            result["sample"].append(sample)
    except Exception as exc:
        result["iteration_error"] = "{}: {}".format(type(exc).__name__, exc)
    return result

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
            objects = _resolve_collection(print_obj, "objects")
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
                          "ExtrusionEntity", "ExtrusionLoop", "ExtrusionMultiPath",
                          "ExtrusionEntityCollection", "Point", "Polyline"):
            cls = getattr(host, type_name, None)
            if cls is not None:
                class_info = {
                    "type": _safe_type(cls),
                    "symbols": _safe_dir(cls)[:100],
                    "doc": _safe_repr(getattr(cls, "__doc__", None), 1200),
                }
                try:
                    class_info["constructor_signature"] = str(inspect.signature(cls))
                except Exception as exc:
                    class_info["constructor_signature_error"] = "{}: {}".format(
                        type(exc).__name__, exc
                    )
                result.setdefault("host_type_details", {})[type_name] = class_info
                if type_name in ("Point", "ExtrusionPath", "ExtrusionLoop",
                                 "ExtrusionMultiPath", "ExtrusionEntityCollection"):
                    class_info["property_descriptor_hints"] = _descriptor_hints(
                        cls, ("x", "y", "points", "paths", "entities",
                              "role", "width", "height", "mm3_per_mm")
                    )
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


def _write_diagnostic_report(report, reset=False):
    """Write full JSONL diagnostics to the OS temporary directory."""
    path = os.path.join(os.environ.get("APPDATA", tempfile.gettempdir()),
                        "OrcaSlicer", "log", "WaveOverhangs_API_Probe_0.8.0.jsonl")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        mode = "w" if reset else "a"
        with open(path, mode, encoding="utf-8") as stream:
            stream.write(json.dumps(report, ensure_ascii=False, separators=(",", ":"), default=str))
            stream.write("\n")
        return path, None
    except Exception as exc:
        return path, "{}: {}".format(type(exc).__name__, exc)


def _compact_log_summary(report, report_path, write_error):
    geometry = report.get("geometry_inspection", {})
    summary = {
        "plugin_version": "0.8.0",
        "step": report.get("step"),
        "context_type": report.get("context_type"),
        "print_type": report.get("print_type"),
        "object_type": report.get("object_type"),
        "geometry_keys": sorted(geometry.keys()),
        "report_file": report_path,
    }
    for key in ("layers", "support_layers", "print_objects"):
        collection = geometry.get(key, {})
        if isinstance(collection, dict):
            summary[key] = {
                "type": collection.get("type"),
                "length": collection.get("length"),
                "sample_count": len(collection.get("sample", [])),
                "iteration_error": collection.get("iteration_error"),
            }
    if write_error:
        summary["report_file_error"] = write_error
    return summary


_PIPELINE_REPORTED_STEPS = set()
_DIAGNOSTIC_FILE_INITIALIZED = False
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
            "plugin_version": "0.8.0",
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
                "plugin_version": "0.8.0",
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

            is_geometry_step = any(token in step_key for token in _GEOMETRY_STEPS)
            if is_geometry_step:
                global _DIAGNOSTIC_FILE_INITIALIZED
                report["geometry_inspection"] = _inspect_pipeline_geometry(ctx, step)
                reset_file = not _DIAGNOSTIC_FILE_INITIALIZED
                report_path, write_error = _write_diagnostic_report(report, reset=reset_file)
                _DIAGNOSTIC_FILE_INITIALIZED = True
                summary = _compact_log_summary(report, report_path, write_error)
                message = "[WAVE_OVERHANGS_API_PROBE_SUMMARY] " + json.dumps(
                    summary, ensure_ascii=False, separators=(",", ":")
                )
            elif step_key not in _PIPELINE_REPORTED_STEPS:
                message = _result_message("[WAVE_OVERHANGS_PIPELINE_PROBE]", report, limit=4500)
            else:
                message = "Wave Overhangs pipeline probe observed step {}.".format(step)
            _PIPELINE_REPORTED_STEPS.add(step_key)

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
