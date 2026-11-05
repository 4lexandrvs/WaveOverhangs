# /// script
# requires-python = ">=3.12"
#
# [tool.orcaslicer.plugin]
# name = "Wave Overhangs"
# description = "Anchored wavefront extrusion paths for unsupported regions."
# author = "WaveOverhangs contributors"
# version = "0.3.0-dev"
# type = "slicing-pipeline"
# ///
"""Wave Overhangs Python plugin for OrcaSlicer 2.5.0.

The geometry stage runs at posPrepareInfill: it generates anchored wavefronts
and removes their covered envelope from fill_surfaces before make_fills().
The export stage inserts the saved paths at psGCodePostProcess.

The wavefront propagation is adapted from:
  Wave overhang generation: Janis A. Andersons (andersonsjanis)
  Arc-overhang algorithm: Steven McCulloch (stmcculloch)
  PrusaSlicer integration: Steven McCulloch
  OrcaSlicer port: Dennis Klappe (dennisklappe)
Reference: https://github.com/dennisklappe/OrcaSlicer-WaveOverhangs
AGPL-3.0-or-later.
"""

import json
import math
import os
import re

import orca
from wavefront_engine import generate_wavefronts, subtract_covered


_DEFAULTS = {
    # Kept opt-in until the first runtime G-code validation is completed.
    "enabled": False,
    "line_spacing_mm": 0.35,
    "line_width_mm": 0.42,
    "seed_reach_mm": 0.12,
    "max_iterations": 160,
    "min_area_growth_mm2": 0.01,
    "filament_diameter_mm": 1.75,
    "travel_speed_mm_min": 7200.0,
    "print_speed_mm_min": 1800.0,
}

_LAYER_CHANGE = re.compile(r"^;LAYER_CHANGE\s*$")
_LAYER_Z = re.compile(r"^;Z:([-+0-9.eE]+)\s*$")
_E_MODE = re.compile(r"^\s*M(82|83)(?:\s|$)", re.IGNORECASE)
_E_VALUE = re.compile(r"(?:^|\s)E([-+0-9.eE]+)(?:\s|$)", re.IGNORECASE)
_F_VALUE = re.compile(r"(?:^|\s)F([-+0-9.eE]+)(?:\s|$)", re.IGNORECASE)
_VOLUMETRIC = re.compile(r"^\s*M200(?:\s|$)", re.IGNORECASE)
_TOOL_CHANGE = re.compile(r"^\s*T[1-9][0-9]*(?:\s|$)", re.IGNORECASE)


def _config(capability):
    try:
        raw = json.loads(capability.get_config())
    except (AttributeError, TypeError, ValueError):
        raw = {}
    cfg = dict(_DEFAULTS)
    if isinstance(raw, dict):
        cfg.update(raw)
    cfg["enabled"] = bool(cfg["enabled"])
    for key in ("line_spacing_mm", "line_width_mm", "seed_reach_mm",
                "min_area_growth_mm2", "filament_diameter_mm",
                "travel_speed_mm_min", "print_speed_mm_min"):
        cfg[key] = float(cfg[key])
    cfg["max_iterations"] = max(1, min(1000, int(cfg["max_iterations"])))
    if cfg["line_spacing_mm"] <= 0 or cfg["line_width_mm"] <= 0:
        cfg["enabled"] = False
    if cfg["seed_reach_mm"] <= 0 or cfg["filament_diameter_mm"] <= 0:
        cfg["enabled"] = False
    return cfg


def _fmt(value):
    return ("%.5f" % float(value)).rstrip("0").rstrip(".")


def _path_gcode(path, width, height, filament_diameter, travel_speed, print_speed):
    points = [(float(p[0]), float(p[1])) for p in path]
    if len(points) < 2:
        return []
    filament_area = math.pi * (filament_diameter * 0.5) ** 2
    if filament_area <= 0 or width <= 0 or height <= 0:
        raise ValueError("Wave Overhangs: invalid extrusion dimensions")
    out = [
        ";TYPE:Wave Overhangs",
        "G0 X%s Y%s F%s" % (_fmt(points[0][0]), _fmt(points[0][1]), _fmt(travel_speed)),
    ]
    for a, b in zip(points, points[1:]):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length <= 1e-7:
            continue
        e_delta = width * height * length / filament_area
        out.append("G1 X%s Y%s E%s F%s" % (
            _fmt(b[0]), _fmt(b[1]), _fmt(e_delta), _fmt(print_speed)
        ))
    return out


def _inject_gcode(source, paths_by_z, heights_by_z, cfg):
    if not paths_by_z:
        return source, 0

    lines = source.splitlines()
    insertions = {}
    layer_start = None
    e_mode = "absolute"
    absolute_e = 0.0
    last_feedrate = None
    relative_xyz = False

    for index, line in enumerate(lines):
        command = line.split(";", 1)[0].strip()
        if _VOLUMETRIC.match(command):
            raise ValueError("Wave Overhangs: volumetric extrusion (M200) is not supported")
        if _TOOL_CHANGE.match(command):
            raise ValueError("Wave Overhangs: multiple-tool G-code is not supported")
        upper = command.upper()
        if upper.startswith("G91"):
            relative_xyz = True
        elif upper.startswith("G90"):
            relative_xyz = False
        if relative_xyz and command:
            raise ValueError("Wave Overhangs: relative XY motion (G91) is not supported")

        mode_match = _E_MODE.match(command)
        if mode_match:
            e_mode = "absolute" if mode_match.group(1) == "82" else "relative"

        f_match = _F_VALUE.search(command)
        if f_match:
            last_feedrate = float(f_match.group(1))

        e_match = _E_VALUE.search(command)
        if e_match:
            value = float(e_match.group(1))
            if upper.startswith("G92"):
                absolute_e = value
            elif upper.startswith(("G0", "G1", "G2", "G3")):
                absolute_e = value if e_mode == "absolute" else absolute_e + value

        if _LAYER_CHANGE.match(line):
            layer_start = index
            continue

        z_match = _LAYER_Z.match(line)
        if z_match and layer_start is not None:
            active_z = float(z_match.group(1))
            paths = next((v for z, v in paths_by_z.items()
                          if abs(float(z) - active_z) <= 0.015), None)
            if paths:
                height = next((v for z, v in heights_by_z.items()
                               if abs(float(z) - active_z) <= 0.015), None)
                if height is None or float(height) <= 0:
                    raise ValueError("Wave Overhangs: exact layer height is missing")
                block = []
                if e_mode == "absolute":
                    block.append("M83 ; Wave Overhangs: temporary relative extrusion")
                for path in paths:
                    block.extend(_path_gcode(
                        path, cfg["line_width_mm"], float(height),
                        cfg["filament_diameter_mm"], cfg["travel_speed_mm_min"],
                        cfg["print_speed_mm_min"]
                    ))
                if e_mode == "absolute":
                    block.append("M82 ; Wave Overhangs: restore absolute extrusion")
                    block.append("G92 E%s ; Wave Overhangs: restore absolute E coordinate" % _fmt(absolute_e))
                if last_feedrate is not None:
                    block.append("G1 F%s ; Wave Overhangs: restore feedrate" % _fmt(last_feedrate))
                insertions[index + 1] = block
            layer_start = None

    if not insertions:
        return source, 0

    output = []
    count = 0
    for index, line in enumerate(lines):
        output.append(line)
        block = insertions.get(index + 1)
        if block:
            output.extend(block)
            count += sum(1 for item in block if item == ";TYPE:Wave Overhangs")
    ending = "\n" if source.endswith("\n") else ""
    return "\n".join(output) + ending, count


def _transform_xy(matrix, x_mm, y_mm):
    # PrintObject/model-instance matrices are 4x4 affine transforms in mm.
    return (
        float(matrix[0][0]) * x_mm + float(matrix[0][1]) * y_mm + float(matrix[0][3]),
        float(matrix[1][0]) * x_mm + float(matrix[1][1]) * y_mm + float(matrix[1][3]),
    )


def _append_collection(collection, grouped):
    collection.clear()
    first = True
    for surface_type, expolygons in grouped:
        if not expolygons:
            continue
        if first:
            collection.set(expolygons, surface_type)
            first = False
        else:
            collection.append(expolygons, surface_type)


class WaveOverhangsPipeline(orca.slicing.SlicingPipelineCapabilityBase):
    def __init__(self):
        super().__init__()
        self._paths_by_z = {}
        self._heights_by_z = {}
        self._generation_message = "Wave Overhangs: no paths generated"

    def get_name(self):
        return "Wave Overhangs"

    def get_default_config(self):
        return _DEFAULTS

    def execute(self, ctx):
        cfg = _config(self)
        if not cfg["enabled"]:
            return orca.ExecutionResult.success("Wave Overhangs: disabled (safe default)")

        if ctx.step == orca.slicing.Step.posPrepareInfill:
            return self._prepare_infill(ctx, cfg)
        if ctx.step == orca.slicing.Step.psGCodePostProcess:
            return self._post_process(ctx, cfg)
        return orca.ExecutionResult.success()

    def _prepare_infill(self, ctx, cfg):
        self._paths_by_z = {}
        self._heights_by_z = {}

        if ctx.object is None or ctx.print is None:
            return orca.ExecutionResult.success("Wave Overhangs: no active PrintObject")

        # The initial export integration is deliberately limited to one object
        # and one printable instance; otherwise per-object sequential G-code
        # ordering and duplicate-instance transforms need a separate mapper.
        if len(ctx.print.objects()) != 1:
            return orca.ExecutionResult.success("Wave Overhangs: skipped; only one print object is supported")
        model_object = ctx.object.model_object()
        if model_object.instance_count() != 1:
            return orca.ExecutionResult.success("Wave Overhangs: skipped; exactly one model instance is required")
        instance = model_object.instance(0)
        if not instance.is_printable():
            return orca.ExecutionResult.success("Wave Overhangs: skipped; model instance is not printable")
        matrix = instance.matrix()

        scale = 1.0 / float(orca.slicing.unscale(1))
        spacing = int(round(cfg["line_spacing_mm"] * scale))
        width = int(round(cfg["line_width_mm"] * scale))
        seed_reach = int(round(cfg["seed_reach_mm"] * scale))
        min_area_growth = (cfg["min_area_growth_mm2"] * scale * scale)

        layers = ctx.object.layers()
        if len(layers) < 2:
            return orca.ExecutionResult.success("Wave Overhangs: fewer than two layers")

        generated_paths = 0
        changed_surfaces = 0
        for layer_index in range(1, len(layers)):
            if ctx.cancelled():
                break
            layer = layers[layer_index]
            lower_slices = list(layers[layer_index - 1].lslices())
            if not lower_slices:
                continue

            z = float(layer.print_z)
            self._heights_by_z[z] = float(layer.height)
            layer_paths = self._paths_by_z.setdefault(z, [])

            for region in layer.regions():
                collection = region.fill_surfaces
                surfaces = list(collection.surfaces)
                if not surfaces:
                    continue

                grouped = []
                for surface in surfaces:
                    surface_type = surface.surface_type
                    subject = surface.expolygon
                    paths, covered = generate_wavefronts(
                        subject, lower_slices, spacing, width, seed_reach,
                        orca.host.Point, cfg["max_iterations"], min_area_growth
                    )
                    if paths:
                        # Transform from object coordinates to printer/world XY.
                        for path in paths:
                            layer_paths.append([
                                _transform_xy(
                                    matrix,
                                    float(orca.slicing.unscale(point[0])),
                                    float(orca.slicing.unscale(point[1]))
                                )
                                for point in path
                            ])
                        residual = []
                        for piece in covered:
                            residual.extend(subject.diff_ex(piece))
                        grouped.append((surface_type, residual))
                        generated_paths += len(paths)
                        changed_surfaces += 1
                    else:
                        grouped.append((
                            surface_type,
                            [orca.host.ExPolygon(subject.contour, list(subject.holes))]
                        ))

                if changed_surfaces:
                    _append_collection(collection, grouped)

            if not self._paths_by_z.get(z):
                self._paths_by_z.pop(z, None)
                self._heights_by_z.pop(z, None)

        self._generation_message = (
            "Wave Overhangs: generated {} wavefront paths on {} layers; "
            "{} fill surfaces changed".format(
                generated_paths, len(self._paths_by_z), changed_surfaces
            )
        )
        return orca.ExecutionResult.success(self._generation_message)

    def _post_process(self, ctx, cfg):
        if not self._paths_by_z:
            return orca.ExecutionResult.success("Wave Overhangs: no pending wavefront paths")
        path = str(ctx.gcode_path)
        if not path or not os.path.isfile(path):
            return orca.ExecutionResult.success("Wave Overhangs: G-code path is unavailable")
        with open(path, "r", encoding="utf-8", newline="") as handle:
            original = handle.read()
        updated, count = _inject_gcode(
            original, self._paths_by_z, self._heights_by_z, cfg
        )
        if count:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(updated)
        return orca.ExecutionResult.success(
            "Wave Overhangs: inserted {} wavefront paths into exported G-code".format(count)
        )


@orca.plugin
class WaveOverhangsPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(WaveOverhangsPipeline)
