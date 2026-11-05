# Wavefront propagation core for the Wave Overhangs OrcaSlicer plugin.
#
# Algorithm lineage:
#   Wave overhang generation: Janis A. Andersons (andersonsjanis)
#   Builds on arc-overhang algorithm by Steven McCulloch (stmcculloch)
#   PrusaSlicer integration: Steven McCulloch
#   OrcaSlicer port: Dennis Klappe (dennisklappe)
#   Reference: https://github.com/dennisklappe/OrcaSlicer-WaveOverhangs
# Licensed under AGPL-3.0-or-later. This Python adaptation retains attribution.
#
# This first Python port implements geometric wavefront propagation and its
# covered-area result. Smart bridge selection, narrow-neck splitting, corner
# tapering and ZigZag joining are deliberately not represented as implemented.

import math


def _union(items):
    # The binding exposes a binary union. Fold by subtracting already-kept
    # components from each incoming polygon to avoid duplicating disjoint pieces.
    result = []
    for item in items:
        pending = [item]
        for existing in result:
            next_pending = []
            for candidate in pending:
                next_pending.extend(candidate.diff_ex(existing))
            pending = next_pending
            if not pending:
                break
        result.extend(pending)
    return result


def _intersection(subjects, clips):
    result = []
    for subject in subjects:
        for clip in clips:
            result.extend(subject.intersection_ex(clip))
    return _union(result)


def _difference(subjects, clips):
    result = list(subjects)
    for clip in clips:
        next_result = []
        for subject in result:
            next_result.extend(subject.diff_ex(clip))
        result = next_result
        if not result:
            break
    return result


def _offset_union(items, distance):
    expanded = []
    for item in items:
        expanded.extend(item.offset(int(round(distance))))
    return _union(expanded)


def _area(items):
    return sum(float(item.area()) for item in items)


def _point_inside(point, polygons):
    return any(poly.contains(point) for poly in polygons)


def _clip_ring_to_region(ring, clip_region, sample_step, point_factory):
    """Clip a closed polygon ring to an ExPolygon region by segment sampling.

    The Python bindings expose polygon booleans but not the native intersection_pl
    helper. Sampling is conservative and bounded by sample_step. Returned paths
    are open polylines, split wherever the ring leaves the clip region.
    """
    points = list(ring.points)
    if len(points) < 3:
        return []
    paths = []
    current = []
    for index, start in enumerate(points):
        end = points[(index + 1) % len(points)]
        dx = float(end.x - start.x)
        dy = float(end.y - start.y)
        length = math.hypot(dx, dy)
        steps = max(1, int(math.ceil(length / max(1.0, sample_step))))
        for step in range(steps):
            t0 = step / steps
            t1 = (step + 1) / steps
            ax = float(start.x) + dx * t0
            ay = float(start.y) + dy * t0
            bx = float(start.x) + dx * t1
            by = float(start.y) + dy * t1
            midpoint = point_factory(int(round((ax + bx) * 0.5)),
                                     int(round((ay + by) * 0.5)))
            if _point_inside(midpoint, clip_region):
                a = (int(round(ax)), int(round(ay)))
                b = (int(round(bx)), int(round(by)))
                if not current:
                    current.append(a)
                elif current[-1] != a:
                    if len(current) >= 2:
                        paths.append(current)
                    current = [a]
                if current[-1] != b:
                    current.append(b)
            elif current:
                if len(current) >= 2:
                    paths.append(current)
                current = []
    if len(current) >= 2:
        paths.append(current)
    return paths


def generate_wavefronts(subject, lower_slices, spacing, line_width,
                        seed_reach, point_factory, max_iterations=160,
                        min_area_growth=0.0):
    """Generate anchored offset fronts for one fill surface.

    All geometric distances are in Orca scaled integer units. Returns
    (paths, covered_expolygons). Paths contain scaled XY coordinate pairs;
    covered_expolygons is the area to subtract from ordinary infill.

    This is the core propagation stage of the reference algorithm. It deliberately
    leaves advanced bridgeability heuristics and optional patterns for later ports.
    """
    if not lower_slices or spacing <= 0 or line_width <= 0 or seed_reach <= 0:
        return [], []

    lower_union = _union(lower_slices)
    overhang = _difference([subject], lower_union)
    if not overhang:
        return [], []

    # Seed from the strip of the overhang adjacent to material in the layer below.
    expanded_lower = _offset_union(lower_union, seed_reach)
    seeds = _intersection(overhang, expanded_lower)
    if not seeds:
        return [], []

    # Keep generated fronts away from the physical overhang edge by half a line.
    trim_distance = max(1, int(round(line_width * 0.5)))
    trim_region = []
    for piece in overhang:
        trim_region.extend(piece.offset(-trim_distance))
    if not trim_region:
        trim_region = overhang

    sample_step = max(1.0, min(float(spacing) * 0.25, float(line_width) * 0.5))
    accumulated = seeds
    accumulated_area = _area(accumulated)
    paths = []

    for _ in range(max(1, int(max_iterations))):
        grown = _offset_union(accumulated, spacing)
        next_region = _intersection(grown, overhang)
        if not next_region:
            break

        next_area = _area(next_region)
        if next_area <= accumulated_area + max(0.0, float(min_area_growth)):
            break

        for piece in next_region:
            for ring in [piece.contour] + list(piece.holes):
                paths.extend(_clip_ring_to_region(
                    ring, trim_region, sample_step, point_factory
                ))

        accumulated = next_region
        accumulated_area = next_area

    if not paths:
        return [], []

    # The final accumulated wavefront envelope is removed from normal infill.
    return paths, _union(accumulated)


def subtract_covered(subject, covered):
    """Return subject minus generated wavefront coverage."""
    return _difference([subject], covered)
