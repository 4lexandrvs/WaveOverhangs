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
# This standalone core implements geometric wavefront propagation, narrow-neck
# splitting, and its covered-area result. Smart bridge selection, corner tapering
# and ZigZag joining are deliberately not represented as implemented.

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

    Fully-inside segments retain their original endpoints; only boundary-crossing
    segments are sampled. This keeps straight wavefronts compact in exported G-code.
    """
    points = list(ring.points)
    if len(points) < 3:
        return []
    paths = []
    current = []

    def flush():
        nonlocal current
        if len(current) >= 2:
            paths.append(current)
        current = []

    def append_segment(a, b):
        if not current:
            current.append(a)
        elif current[-1] != a:
            flush()
            current.append(a)
        if current[-1] != b:
            current.append(b)

    for index, start in enumerate(points):
        end = points[(index + 1) % len(points)]
        ax, ay = float(start.x), float(start.y)
        bx, by = float(end.x), float(end.y)
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)

        # Fast path: preserve the native segment if it stays inside the inset.
        probes = (0.0, 0.25, 0.5, 0.75, 1.0)
        fully_inside = True
        for t in probes:
            probe = point_factory(int(round(ax + dx * t)),
                                  int(round(ay + dy * t)))
            if not _point_inside(probe, clip_region):
                fully_inside = False
                break
        if fully_inside:
            append_segment((int(round(ax)), int(round(ay))),
                           (int(round(bx)), int(round(by))))
            continue

        steps = max(1, int(math.ceil(length / max(1.0, sample_step))))
        for step in range(steps):
            t0 = step / steps
            t1 = (step + 1) / steps
            sx = ax + dx * t0
            sy = ay + dy * t0
            ex = ax + dx * t1
            ey = ay + dy * t1
            midpoint = point_factory(int(round((sx + ex) * 0.5)),
                                     int(round((sy + ey) * 0.5)))
            if _point_inside(midpoint, clip_region):
                append_segment((int(round(sx)), int(round(sy))),
                               (int(round(ex)), int(round(ey))))
            else:
                flush()

    flush()
    return paths



def split_narrow_necks(region, minimum_width):
    """Split a wave-cover region at necks narrower than minimum_width.

    This is a morphology-based Python approximation of the reference slit
    splitter: erode the region, keep the disconnected cores separate, then
    regrow each core and clip it to the original region. The removed neck
    material remains available to ordinary infill.
    """
    half_width = max(1, int(round(float(minimum_width) * 0.5)))
    if half_width <= 1:
        return [region]
    cores = list(region.offset(-half_width))
    if len(cores) <= 1:
        return [region]

    pieces = []
    for core in cores:
        for grown in core.offset(half_width):
            pieces.extend(grown.intersection_ex(region))

    # Keep components disjoint without a union operation that would reconnect
    # them across a neck that the erosion deliberately separated.
    disjoint = []
    for piece in pieces:
        pending = [piece]
        for kept in disjoint:
            next_pending = []
            for candidate in pending:
                next_pending.extend(candidate.diff_ex(kept))
            pending = next_pending
        disjoint.extend(pending)
    return disjoint if len(disjoint) > 1 else [region]


def unsupported_boundary_projection_cost(segments):
    """Return the minimum unsupported-boundary projection over candidate normals.

    Each segment is (x1, y1, x2, y2). This mirrors
    BridgeDetector::detect_bridging_direction: segment normals are candidate
    directions, and each candidate accumulates abs(dot(segment, normal)).
    """
    candidates = {}
    usable = []
    for segment in segments:
        x1, y1, x2, y2 = (float(value) for value in segment)
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            continue
        nx, ny = -dy / length, dx / length
        angle_key = math.ceil(math.atan2(ny, nx) * 1000.0)
        candidates.setdefault(angle_key, (nx, ny))
        usable.append((dx, dy))
    if not usable:
        return 0.0
    return min(
        sum(abs(dx * nx + dy * ny) for dx, dy in usable)
        for nx, ny in candidates.values()
    )


def smart_bridgeability_allows(overhang_area, outside_hull_area,
                               unsupported_distance=0.0, perimeter=0.0,
                               has_holes=False, threshold=0.20):
    """Apply both Smart Bridgeability tests from the reference implementation.

    Hole-bearing regions always qualify. Otherwise waves are generated when
    either >= threshold of the area lies outside the anchor convex hull, or
    the minimum unsupported-boundary projection is >= threshold of perimeter.
    """
    if has_holes:
        return True
    area = float(overhang_area)
    if area <= 0:
        return False
    outside_ratio = float(outside_hull_area) / area
    perimeter = float(perimeter)
    unsupported_ratio_reached = (
        perimeter > 0 and float(unsupported_distance) >= threshold * perimeter
    )
    return outside_ratio >= threshold or unsupported_ratio_reached


def generate_wavefronts(subject, lower_slices, spacing, line_width,
                        seed_reach, point_factory, max_iterations=160,
                        min_area_growth=0.0, minimum_wave_width=0):
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
    # Approximate the reference's tiny source-contour expansion (<= 0.05 mm).
    seed_epsilon = max(1, min(int(round(float(spacing) * 0.25)),
                              int(round(float(seed_reach) * 0.05))))
    trim_distance = max(1, int(round(line_width * 0.5)))
    sample_step = max(1.0, min(float(spacing) * 0.25, float(line_width) * 0.5))
    paths = []
    covered = []

    for original_piece in overhang:
        wave_pieces = split_narrow_necks(original_piece, minimum_wave_width)
        for wave_piece in wave_pieces:
            # Start from a narrow band around the expanded-anchor contour,
            # approximating the reference's open ClipperZ wave seeds.
            anchor_overlap = _intersection([wave_piece], expanded_lower)
            if not anchor_overlap:
                continue
            eroded_anchors = _offset_union(expanded_lower, -2 * seed_epsilon)
            inner_overlap = (_intersection([wave_piece], eroded_anchors)
                             if eroded_anchors else [])
            seeds = _difference(anchor_overlap, inner_overlap)
            if not seeds:
                seeds = anchor_overlap
            trim_region = list(wave_piece.offset(-trim_distance))
            if not trim_region:
                continue
            accumulated = seeds
            accumulated_area = _area(accumulated)
            piece_paths = []
            for _ in range(max(1, int(max_iterations))):
                grown = _offset_union(accumulated, spacing)
                next_region = _intersection(grown, [wave_piece])
                if not next_region:
                    break
                next_area = _area(next_region)
                if next_area <= accumulated_area + max(0.0, float(min_area_growth)):
                    break
                for piece in next_region:
                    for ring in [piece.contour] + list(piece.holes):
                        piece_paths.extend(_clip_ring_to_region(
                            ring, trim_region, sample_step, point_factory
                        ))
                accumulated = next_region
                accumulated_area = next_area
            if piece_paths:
                paths.extend(piece_paths)
                covered.extend(accumulated)

    if not paths:
        return [], []
    return paths, _union(covered)


def subtract_covered(subject, covered):
    """Return subject minus generated wavefront coverage."""
    return _difference([subject], covered)
