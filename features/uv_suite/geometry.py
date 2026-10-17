"""UV connectivity, pixel-space measurements and conservative layout checks."""

from math import floor, isfinite, sqrt
from mathutils import Vector
from .context import UVError

EPS = 1e-8


def connected(loop, other, layer):
    """Compare UV endpoints by mesh vertex, including inconsistent face winding."""
    a = {loop.vert: loop[layer].uv,
         loop.link_loop_next.vert: loop.link_loop_next[layer].uv}
    b = {other.vert: other[layer].uv,
         other.link_loop_next.vert: other.link_loop_next[layer].uv}
    return a.keys() == b.keys() and all((a[v] - b[v]).length_squared < 1e-12 for v in a)


def islands(state, faces=None):
    remaining = set(state.targets if faces is None else faces)
    result = []
    while remaining:
        start = min(remaining, key=lambda f: f.index)
        remaining.remove(start)
        group, stack = {start}, [start]
        while stack:
            face = stack.pop()
            for loop in face.loops:
                for other in loop.edge.link_loops:
                    if other.face in remaining and connected(loop, other, state.layer):
                        remaining.remove(other.face)
                        group.add(other.face)
                        stack.append(other.face)
        result.append(group)
    return result


def expand_islands(session):
    for state in session.states:
        if not state.targets:
            continue
        visible = {f for f in state.bm.faces if not f.hide}
        state.targets = set().union(*(g for g in islands(state, visible) if g & state.targets))
        # A visible subset of an island must not drag a hidden portion with it.
        for group in islands(state, set(state.bm.faces)):
            if group & state.targets and any(f.hide for f in group):
                raise UVError('An affected island includes hidden faces; reveal it first')


def cross(a, b):
    return a.x * b.y - a.y * b.x


def triangle_area(points):
    return cross(points[1] - points[0], points[2] - points[0]) * 0.5


def pixel(loop, layer, width, height):
    uv = loop[layer].uv
    return Vector((uv.x * width, uv.y * height))


def triangles(state, faces, width, height):
    return [(tuple(pixel(l, state.layer, width, height) for l in tri), tri[0].face)
            for tri in state.bm.calc_loop_triangles() if tri[0].face in faces]


def density(state, faces, width, height, unit_scale):
    area_uv = area_world = 0.0
    matrix = state.obj.matrix_world
    for tri in state.bm.calc_loop_triangles():
        if tri[0].face not in faces:
            continue
        uv = [pixel(l, state.layer, width, height) for l in tri]
        co = [matrix @ l.vert.co for l in tri]
        area_uv += abs(triangle_area(uv))
        area_world += (co[1] - co[0]).cross(co[2] - co[0]).length * 0.5 * unit_scale ** 2
    if area_world <= EPS or area_uv <= EPS:
        raise UVError('Cannot measure density on zero-area geometry or collapsed UVs')
    return sqrt(area_uv / area_world)


def bounds(points):
    return (min(p.x for p in points), min(p.y for p in points),
            max(p.x for p in points), max(p.y for p in points))


def intersection_area(a, b):
    """Convex clipping, to distinguish true overlap from touching triangle edges."""
    output = list(a)
    orientation = 1 if triangle_area(b) >= 0 else -1
    for i in range(3):
        origin, end = b[i], b[(i + 1) % 3]
        edge = end - origin
        source, output = output, []
        if not source:
            break
        previous = source[-1]
        dp = orientation * cross(edge, previous - origin)
        for current in source:
            dc = orientation * cross(edge, current - origin)
            if (dc >= 0) != (dp >= 0):
                output.append(previous + (current - previous) * (dp / (dp - dc)))
            if dc >= 0:
                output.append(current)
            previous, dp = current, dc
    if len(output) < 3:
        return 0.0
    return abs(sum(cross(output[i], output[(i + 1) % len(output)])
                   for i in range(len(output)))) * 0.5


def point_segment_distance(p, a, b):
    delta = b - a
    if delta.length_squared <= EPS:
        return (p - a).length
    t = max(0.0, min(1.0, (p - a).dot(delta) / delta.length_squared))
    return (p - (a + t * delta)).length


def segment_distance(a, b, c, d):
    ab, cd = b - a, d - c
    det = cross(ab, cd)
    if abs(det) > EPS:
        t, u = cross(c - a, cd) / det, cross(c - a, ab) / det
        if 0 <= t <= 1 and 0 <= u <= 1:
            return 0.0
    return min(point_segment_distance(a, c, d), point_segment_distance(b, c, d),
               point_segment_distance(c, a, b), point_segment_distance(d, a, b))


def inspect(session, settings, padding=False):
    width, height = settings.width, settings.height
    report = dict(islands=0, triangles=0, degenerate=0, flipped=0,
                  outside=0, overlaps=0, gap_violations=0, border_violations=0)
    records, boundaries = [], []
    for state in session.states:
        if not state.targets:
            continue
        for group in islands(state):
            report['islands'] += 1
            segments = []
            for face in group:
                for loop in face.loops:
                    if not any(o.face in group and o is not loop and
                               connected(loop, o, state.layer) for o in loop.edge.link_loops):
                        segments.append((pixel(loop, state.layer, width, height),
                                         pixel(loop.link_loop_next, state.layer, width, height)))
            boundaries.append(segments)
        for tri, face in triangles(state, state.targets, width, height):
            if not all(isfinite(x) for p in tri for x in p):
                raise UVError('Non-finite UV coordinates detected')
            report['triangles'] += 1
            area = triangle_area(tri)
            report['degenerate'] += abs(area) < EPS
            report['flipped'] += area < -EPS
            box = bounds(tri)
            tx = floor((box[0] + 1e-4) / width)
            ty = floor((box[1] + 1e-4) / height)
            tile = 1001 + tx + 10 * ty
            allowed = (0 <= tx <= 9 and ty >= 0 and
                       settings.tile_start <= tile < settings.tile_start + settings.tile_count)
            report['outside'] += (not allowed or box[2] > (tx + 1) * width + 1e-4 or
                                  box[3] > (ty + 1) * height + 1e-4)
            border = settings.border
            report['border_violations'] += (not allowed or box[0] < tx * width + border - 1e-3 or
                                            box[1] < ty * height + border - 1e-3 or
                                            box[2] > (tx + 1) * width - border + 1e-3 or
                                            box[3] > (ty + 1) * height - border + 1e-3)
            records.append((box, tri))
    # Sweep broad phase. Refuse excessive exact checks rather than claiming success.
    records.sort(key=lambda r: r[0][0])
    checks = 0
    for i, (box, tri) in enumerate(records):
        for j in range(i + 1, len(records)):
            other_box, other = records[j]
            if other_box[0] >= box[2] - 1e-5:
                break
            if other_box[1] >= box[3] - 1e-5 or other_box[3] <= box[1] + 1e-5:
                continue
            checks += 1
            if checks > 2000000:
                raise UVError('Exact validation budget exceeded; process a smaller selection')
            # mathutils vectors are float32; pixel-space clipping at 2K/8K
            # needs a relative area tolerance for shared triangulation edges.
            tolerance = max(1e-3, min(abs(triangle_area(tri)), abs(triangle_area(other))) * 1e-6)
            report['overlaps'] += intersection_area(tri, other) > tolerance
    if padding and settings.gap > 0:
        margin = settings.gap - 1e-3
        for i, segments in enumerate(boundaries):
            for other_segments in boundaries[i + 1:]:
                violation = False
                for a, b in segments:
                    for c, d in other_segments:
                        if (max(a.x, b.x) + margin < min(c.x, d.x) or
                            max(c.x, d.x) + margin < min(a.x, b.x) or
                            max(a.y, b.y) + margin < min(c.y, d.y) or
                            max(c.y, d.y) + margin < min(a.y, b.y)):
                            continue
                        checks += 1
                        if checks > 2000000:
                            raise UVError('Padding validation budget exceeded; pack fewer islands')
                        if segment_distance(a, b, c, d) < margin:
                            violation = True
                            break
                    if violation:
                        break
                report['gap_violations'] += violation
    return report