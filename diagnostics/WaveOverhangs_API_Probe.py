# /// script
# requires-python = ">=3.12"
#
# [tool.orcaslicer.plugin]
# name = "Wave Overhangs (API Probe)"
# description = "Read-only diagnostic for OrcaSlicer 2.5.0 plugin and slicing-pipeline APIs."
# author = "WaveOverhangs contributors"
# version = "0.5.0"
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


def _inspect_extrusion_entities(region_obj, attr_name):
    try:
        collection = _resolve_collection(region_obj, attr_name)
        result = _inspect_collection(
            collection,
            ("role", "width", "height", "mm3_per_mm", "points", "paths"),
            attr_name,
            3,
        )
        for entity_sample in result.get("sample", []):
            try:
                entity = collection[entity_sample["index"]]
            except Exception:
                continue
            try:
                paths = _resolve_collection(entity, "paths")
            except Exception:
                paths = None
            if paths is not None:
                entity_sample["path_collection"] = _inspect_collection(
                    paths,
                    ("role", "width", "height", "mm3_per_mm", "points"),
                    "paths",
                    3,
                )
            try:
                points = _resolve_collection(entity, "points")
            except Exception:
                points = None
            if points is not None:
                entity_sample["point_collection"] = {
                    "type": _safe_type(points),
                    "length": _safe_length(points),
                    "sample": [],
                }
                try:
                    for point_index, point in enumerate(points):
                        if point_index >= 5:
                            break
                        entity_sample["point_collection"]["sample"].append({
                            "index": point_index,
                            "type": _safe_type(point),
                            "repr": _safe_repr(point, 180),
                            "symbols": _safe_dir(point)[:30],
                        })
                except Exception as point_exc:
                    entity_sample["point_collection"]["iteration_error"] = str(point_exc)
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


def _write_diagnostic_report(report, reset=False):
    """Write full JSONL diagnostics to the OS temporary directory."""
    path = os.path.join(os.environ.get("APPDATA", tempfile.gettempdir()),
                        "OrcaSlicer", "log", "WaveOverhangs_API_Probe_0.5.0.jsonl")
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
        "plugin_version": "0.5.0",
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
            "plugin_version": "0.4.1",
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
                "plugin_version": "0.4.1",
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
