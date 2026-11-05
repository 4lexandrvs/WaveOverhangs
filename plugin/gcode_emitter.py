"""Conservative G-code injection for precomputed Wave Overhangs paths.

Coordinates must already be in printer space. The geometry stage is responsible
for clipping ordinary infill and supplying the exact layer heights.
"""
import math
import re

_LAYER_CHANGE = re.compile(r"^;LAYER_CHANGE\\s*$")
_LAYER_Z = re.compile(r"^;Z:([-+0-9.eE]+)\\s*$")
_E_MODE = re.compile(r"^\\s*M(82|83)(?:\\s|$)", re.IGNORECASE)
_VOLUMETRIC = re.compile(r"^\\s*M200(?:\\s|$)", re.IGNORECASE)
_E_VALUE = re.compile(r"(?:^|\\s)E([-+0-9.eE]+)(?:\\s|$)", re.IGNORECASE)
_TOOL_CHANGE = re.compile(r"^\\s*T[1-9][0-9]*(?:\\s|$)", re.IGNORECASE)


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
    """Insert paths at exact layer markers; reject unsupported volumetric E.

    height_by_z is required for every emitted layer. The emitter intentionally
    does not guess layer height or transform object coordinates into bed space.
    """
    if not paths_by_z:
        return gcode_text, 0

    lines = gcode_text.splitlines()
    z_to_paths = [(float(z), list(paths)) for z, paths in paths_by_z.items()]
    insertions = {}
    layer_start = None
    e_mode = "absolute"
    for index, line in enumerate(lines):
        if _VOLUMETRIC.match(line):
            raise ValueError("Wave Overhangs: volumetric extrusion (M200) is not supported")
        mode_match = _E_MODE.match(line)
        if mode_match:
            e_mode = "absolute" if mode_match.group(1) == "82" else "relative"
        if _LAYER_CHANGE.match(line):
            layer_start = index
            continue
        z_match = _LAYER_Z.match(line)
        if z_match and layer_start is not None:
            active_z = float(z_match.group(1))
            match = next((paths for z, paths in z_to_paths
                          if abs(z - active_z) <= z_tolerance), None)
            if match:
                height = None
                if height_by_z:
                    height = next((v for z, v in height_by_z.items()
                                   if abs(float(z) - active_z) <= z_tolerance), None)
                if height is None or float(height) <= 0:
                    raise ValueError("Wave Overhangs: exact positive layer height is required for Z=%s" % active_z)
                block = []
                if e_mode == "absolute":
                    block.append("M83 ; Wave Overhangs: temporary relative extrusion")
                for path in match:
                    block.extend(_path_gcode(
                        path, width, float(height), filament_diameter,
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
