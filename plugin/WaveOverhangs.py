# /// script
# requires-python = ">=3.12"
#
# [tool.orcaslicer.plugin]
# name = "Wave Overhangs"
# description = "Experimental wave-shaped contour treatment on unsupported perimeter sections."
# author = "WaveOverhangs contributors"
# version = "0.1.0"
# type = "slicing-pipeline"
# ///
"""
Wave Overhangs — first geometry prototype for OrcaSlicer 2.5.0.

This is deliberately a contour-level prototype, not a port of the original
WaveOverhangs extrusion-path generator. It detects unsupported portions of
each layer contour (current slice minus the previous layer) and applies a
sinusoidal displacement only to contour samples inside those portions.

The result is written back through SurfaceCollection.set(); OrcaSlicer then
generates the perimeter toolpaths normally.

The original WaveOverhangs algorithm and its authorship are documented in
docs/IMPLEMENTATION_NOTES.md. This prototype is an independent, deliberately
smaller experiment and does not copy the original C++ implementation.
"""
import json
import math

import orca


_DEFAULTS = {
    "enabled": True,
    "amplitude_mm": 0.12,
    "period_mm": 1.20,
    "sample_step_fraction": 0.125,
    "probe_mm": 0.04,
}


def _config(capability):
    try:
        raw = json.loads(capability.get_config())
    except (AttributeError, TypeError, ValueError):
        raw = {}
    cfg = dict(_DEFAULTS)
    if isinstance(raw, dict):
        cfg.update(raw)
    cfg["enabled"] = bool(cfg["enabled"])
    for key in ("amplitude_mm", "period_mm", "sample_step_fraction",
                "probe_mm"):
        cfg[key] = float(cfg[key])
    if cfg["amplitude_mm"] < 0:
        cfg["amplitude_mm"] = 0.0
    if cfg["period_mm"] <= 0:
        cfg["period_mm"] = _DEFAULTS["period_mm"]
    cfg["sample_step_fraction"] = min(0.5, max(0.04, cfg["sample_step_fraction"]))
    cfg["probe_mm"] = max(0.0, cfg["probe_mm"])
    return cfg


def _subtract_all(subjects, cutters):
    """Return subjects minus the union of cutters, using the bound binary op."""
    result = list(subjects)
    for cutter in cutters:
        next_result = []
        for subject in result:
            next_result.extend(subject.diff_ex(cutter))
        result = next_result
        if not result:
            break
    return result


def _inside_any(point, polygons):
    for polygon in polygons:
        if polygon.contains(point):
            return True
    return False


def _wave_contour(contour, unsupported, amplitude, period, sample_step, probe):
    """Build a densified contour; displace only samples over unsupported area."""
    src = contour.points
    if len(src) < 3:
        return None

    out = orca.host.Polygon()
    travelled = 0.0
    changed = False

    for index, start in enumerate(src):
        end = src[(index + 1) % len(src)]
        dx = float(end.x - start.x)
        dy = float(end.y - start.y)
        length = math.hypot(dx, dy)
        if length <= 0.0:
            continue

        steps = max(1, int(math.ceil(length / sample_step)))
        # For both CCW outer contours and CW holes, material lies to the left
        # of the directed edge; the right-hand normal points out of the material.
        outward_x = dy / length
        outward_y = -dx / length
        inward_x = -outward_x
        inward_y = -outward_y

        for step in range(steps):
            t = step / steps
            x = float(start.x) + dx * t
            y = float(start.y) + dy * t

            # Probe just inside the printed material so points on the boolean
            # boundary are not dependent on the host's boundary-inclusion rule.
            probe_point = orca.host.Point(
                int(round(x + inward_x * probe)),
                int(round(y + inward_y * probe)),
            )
            displacement = 0.0
            if _inside_any(probe_point, unsupported):
                phase = (travelled + length * t) / period
                displacement = amplitude * math.sin(2.0 * math.pi * phase)
                if abs(displacement) > 0.5:
                    changed = True

            out.append(orca.host.Point(
                int(round(x + outward_x * displacement)),
                int(round(y + outward_y * displacement)),
            ))

        travelled += length

    if not changed or out.size() < 3 or not out.is_valid():
        return None
    return out


def _clone_expolygon(expolygon):
    """Copy a live graph-owned ExPolygon before a collection mutation invalidates refs."""
    return orca.host.ExPolygon(expolygon.contour, list(expolygon.holes))


def _wave_expolygon(expolygon, lower_slices, cfg, scale):
    unsupported = _subtract_all([expolygon], lower_slices)
    if not unsupported:
        return None

    period = cfg["period_mm"] * scale
    amplitude = cfg["amplitude_mm"] * scale
    sample_step = max(1.0, period * cfg["sample_step_fraction"])
    probe = cfg["probe_mm"] * scale

    if expolygon.contour.area() <= 0:
        return None
    if expolygon.contour.size() < 3:
        return None

    unsupported_area = sum(poly.area() for poly in unsupported)
    if unsupported_area <= 0:
        return None

    contour = _wave_contour(
        expolygon.contour, unsupported, amplitude, period, sample_step, probe
    )
    if contour is None:
        return None

    holes = list(expolygon.holes)
    candidate = orca.host.ExPolygon(contour, holes)
    if not candidate.is_valid():
        return None
    return candidate


class WaveOverhangsPipeline(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self):
        return "Wave Overhangs"

    def get_default_config(self):
        return _DEFAULTS

    def execute(self, ctx):
        if ctx.step != orca.slicing.Step.posSlice or ctx.object is None:
            return orca.ExecutionResult.success()

        cfg = _config(self)
        if not cfg["enabled"] or cfg["amplitude_mm"] <= 0:
            return orca.ExecutionResult.success("Wave Overhangs: disabled")

        scale = 1.0 / float(orca.slicing.unscale(1))
        layers = ctx.object.layers()
        if len(layers) < 2:
            return orca.ExecutionResult.success("Wave Overhangs: fewer than two layers")

        changed_regions = 0
        changed_surfaces = 0
        for layer_index in range(1, len(layers)):
            if ctx.cancelled():
                break

            layer = layers[layer_index]
            lower_slices = list(layers[layer_index - 1].lslices())
            if not lower_slices:
                continue

            layer_changed = False
            for region in layer.regions():
                collection = region.slices
                surfaces = list(collection.surfaces)
                if not surfaces:
                    continue

                by_type = {}
                region_changed = False
                for surface in surfaces:
                    original = surface.expolygon
                    replacement = _wave_expolygon(original, lower_slices, cfg, scale)
                    by_type.setdefault(surface.surface_type, []).append(
                        replacement if replacement is not None else _clone_expolygon(original)
                    )
                    if replacement is not None:
                        region_changed = True
                        changed_surfaces += 1

                if not region_changed:
                    continue

                items = list(by_type.items())
                first_type, first_expolygons = items[0]
                collection.set(first_expolygons, first_type)
                for surface_type, expolygons in items[1:]:
                    collection.append(expolygons, surface_type)

                changed_regions += 1
                layer_changed = True

            if layer_changed:
                layer.make_slices()

        return orca.ExecutionResult.success(
            "Wave Overhangs 0.1.0: reshaped {} surface(s) in {} region(s)".format(
                changed_surfaces, changed_regions
            )
        )


@orca.plugin
class WaveOverhangsPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(WaveOverhangsPipeline)
