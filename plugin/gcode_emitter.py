"""G-code emission helpers for Wave Overhangs.

This module only emits paths that have already been generated and validated by
the geometry engine. It deliberately does not guess layer/object transforms or
derive geometry from G-code.
"""
import math
import re


_LAYER_CHANGE = re.compile(r"^;LAYER_CHANGE\\s*$")
_LAYER_Z = re.compile(r"^;Z:([-+0-9.eE]+)\\s*$")
_E_MODE = re.compile(r"^\\s*M(82|83)(?:\\s|$)", re.IGNORECASE)


def _fmt(value):
    return ("%.5f" % float(value)).rstrip("0").rstrip(".")


def _path_gcode(path, width, height, filament_diameter, travel_speed, print_speed):
    points = [(float(p[0]), float(p[1])) for p in path]
    if len(points) < 2:
        return []

    filament_area = math.pi * (filament_diameter * 0.5) ** 2
    if filament_area <= 0 or width <= 0 or height <= 0:
        raise ValueError("Wave Overhangs: width, height and filament diameter must be positive")

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


def inject_layer_paths(gcode_text, paths_by_z, width=0.42, height_by_z=None,
                       filament_diameter=1.75, travel_speed=7200.0,
                       print_speed=1800.0, z_tolerance=0.015):
    """Insert relative-E wave paths into matching ;LAYER_CHANGE / ;Z: blocks.

    paths_by_z maps layer Z (mm) to an iterable of XY polylines (mm).
    The caller must supply print-space coordinates and ensure that ordinary
    infill has already been clipped away from the wave-covered area.
    """
    if not paths_by_z:
        return gcode_text, 0

    lines = gcode_text.splitlines()
    z_to_paths = [(float(z), list(paths)) for z, paths in paths_by_z.items()]
    insertions = {}
    active_z = None
    layer_start = None
    e_mode = "absolute"
    for index, line in enumerate(lines):
        mode_match = _E_MODE.match(line)
        if mode_match:
            e_mode = "absolute" if mode_match.group(1) == "82" else "relative"
        if _LAYER_CHANGE.match(line):
            layer_start = index
            active_z = None
            continue
        z_match = _LAYER_Z.match(line)
        if z_match and layer_start is not None:
            active_z = float(z_match.group(1))
            match = next((paths for z, paths in z_to_paths
                          if abs(z - active_z) <= z_tolerance), None)
            if match:
                height = (height_by_z.get(active_z) if height_by_z else None)
                if height is None:
                    height = 0.2
                block = []
                if e_mode == "absolute":
                    block.append("M83 ; Wave Overhangs: temporary relative extrusion")
                for path in match:
                    block.extend(_path_gcode(
                        path, width, height, filament_diameter,
                        travel_speed, print_speed
                    ))
                if e_mode == "absolute":
                    block.append("M82 ; Wave Overhangs: restore absolute extrusion")
                insertions[index + 1] = block
            layer_start = None

    if not insertions:
        return gcode_text, 0

    output = []
    inserted_paths = 0
    for index, line in enumerate(lines):
        output.append(line)
        block = insertions.get(index + 1)
        if block:
            output.extend(block)
            inserted_paths += sum(1 for item in block if item == ";TYPE:Wave Overhangs")
    ending = "\\n" if gcode_text.endswith("\\n") else ""
    return "\\n".join(output) + ending, inserted_paths
