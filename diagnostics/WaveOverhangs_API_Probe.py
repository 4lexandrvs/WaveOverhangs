# /// script
# requires-python = ">=3.12"
#
# [tool.orcaslicer.plugin]
# name = "Wave Overhangs (API Probe)"
# description = "Read-only diagnostic for OrcaSlicer 2.5.0 plugin and slicing-pipeline APIs."
# author = "WaveOverhangs contributors"
# version = "0.2.0"
# ///

import json
import traceback
import orca


def _safe_repr(value, limit=500):
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


def _result_message(marker, report, limit=9000):
    """Put the report in ExecutionResult.message, which OrcaSlicer records in debug_*.log."""
    payload = json.dumps(report, ensure_ascii=False, separators=(",", ":"), default=str)
    message = marker + " " + payload
    if len(message) <= limit:
        return message
    # Preserve the report's structure and identify truncation rather than silently
    # returning a misleading partial JSON document.
    compact = {
        "truncated": True,
        "original_message_chars": len(message),
        "report_preview": payload[:limit - 180],
    }
    return marker + " " + json.dumps(compact, ensure_ascii=False, separators=(",", ":"))


_PIPELINE_REPORTED_STEPS = set()


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
            "plugin_version": "0.2.0",
            "orca_version": _safe_getattr(orca, "__version__"),
            "orca_type": _safe_type(orca),
            "orca_module_symbols": _safe_dir(orca),
            "slicing_module_type": "not available",
            "slicing_module_symbols": [],
            "slicing_step_values": [],
            "host_module_type": "not available",
            "host_module_symbols": [],
            "model_access": "not attempted",
        }
        try:
            slicing = getattr(orca, "slicing", None)
            report["slicing_module_type"] = _safe_type(slicing)
            report["slicing_module_symbols"] = _safe_dir(slicing)
            step_enum = getattr(slicing, "Step", None) if slicing else None
            if step_enum is not None:
                report["slicing_step_values"] = [
                    {"name": name, "value": _safe_getattr(step_enum, name)}
                    for name in _safe_dir(step_enum)
                ]

            host = getattr(orca, "host", None)
            report["host_module_type"] = _safe_type(host)
            report["host_module_symbols"] = _safe_dir(host)
            if host is not None and callable(getattr(host, "model", None)):
                try:
                    model = host.model()
                    report["model_access"] = "available"
                    report["model_type"] = _safe_type(model)
                    report["model_symbols"] = _safe_dir(model)
                    report["model_objects_method"] = _safe_getattr(model, "objects")
                except Exception as exc:
                    report["model_access"] = "not ready or denied: {}".format(exc)

            report["saved_config"] = json.loads(self.get_config())
            message = _result_message("[WAVE_OVERHANGS_API_PROBE]", report)
            # Keep print as a secondary route; the authoritative copy is in message.
            print(message)
            return orca.ExecutionResult.success(message)
        except Exception as exc:
            details = traceback.format_exc()
            error_report = {"error": str(exc), "traceback": details}
            message = _result_message("[WAVE_OVERHANGS_API_PROBE_ERROR]", error_report)
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
                "plugin_version": "0.2.0",
                "context_type": _safe_type(ctx),
                "step": step,
                "context_symbols": _safe_dir(ctx),
                "print_is_none": _safe_getattr(ctx, "print") == "None",
                "object_is_none": _safe_getattr(ctx, "object") == "None",
                "print_symbols": _safe_dir(getattr(ctx, "print", None)),
                "object_symbols": _safe_dir(getattr(ctx, "object", None)),
                "gcode_path": _safe_getattr(ctx, "gcode_path"),
                "host": _safe_getattr(ctx, "host"),
                "output_name": _safe_getattr(ctx, "output_name"),
                "config_value": _safe_getattr(ctx, "config_value"),
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

            # Emit one detailed record per distinct slicing step to keep the log useful.
            if step_key not in _PIPELINE_REPORTED_STEPS:
                _PIPELINE_REPORTED_STEPS.add(step_key)
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
