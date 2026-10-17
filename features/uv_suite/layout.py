"""Conservative MaxRects layout backend in pixel space.

Uses island bounding rectangles, not an exact polygon no-fit solver. This backend
trades coverage for predictable rectangular tiles, obstacles and fixed density.
"""
from math import floor
from mathutils import Vector
from .context import UVError
from .geometry import bounds, expand_islands, islands, pixel, triangles, triangle_area


def tile_offset(number):
    index = number - 1001
    return index % 10, index // 10


def intersects(a, b):
    return a[0] < b[2] - 1e-6 and a[2] > b[0] + 1e-6 and a[1] < b[3] - 1e-6 and a[3] > b[1] + 1e-6


def subtract(free, used):
    result = []
    for rect in free:
        if not intersects(rect, used):
            result.append(rect)
            continue
        x, y, r, t = rect
        a, b, c, d = used
        if x < a < r:
            result.append((x, y, a, t))
        if x < c < r:
            result.append((c, y, r, t))
        if y < b < t:
            result.append((x, y, r, b))
        if y < d < t:
            result.append((x, d, r, t))
    # MaxRects splits may overlap; eliminate contained free rectangles.
    unique = list(dict.fromkeys(result))
    return [rect for i, rect in enumerate(unique) if not any(
        i != j and other[0] <= rect[0] and other[1] <= rect[1] and
        other[2] >= rect[2] and other[3] >= rect[3]
        for j, other in enumerate(unique))]


def pack(session, settings):
    expand_islands(session)
    width, height, gap, border = settings.width, settings.height, settings.gap, settings.border
    if width <= 2 * border or height <= 2 * border:
        raise UVError('Tile border leaves no packing space')
    tiles = [settings.tile_start + i for i in range(settings.tile_count)]
    if tiles[-1] > 2000:
        raise UVError('Requested UDIM range exceeds tile 2000')
    entries, obstacles = [], []
    for state in session.states:
        if not state.layer:
            continue
        for group in islands(state, {f for f in state.bm.faces if not f.hide}):
            loops = [l for f in group for l in f.loops]
            points = [pixel(l, state.layer, width, height) for l in loops]
            box = bounds(points)
            if box[2] - box[0] < 1e-6 or box[3] - box[1] < 1e-6:
                if group & state.targets:
                    raise UVError('Collapsed island: unwrap before packing')
                continue
            entry = dict(state=state, faces=group, loops=loops, points=points, box=box, partners=[])
            if not group & state.targets or any(l[state.layer].pin_uv for l in loops):
                obstacles.append(entry)
            else:
                entries.append(entry)
    # Exact existing stacks only: equal pixel triangles at equal coordinates.
    # Never infer topology correspondence from bounding box alone.
    if settings.preserve_stacks:
        seen, representatives = {}, []
        for entry in entries:
            signature = tuple(sorted(tuple(sorted((round(p.x, 3), round(p.y, 3)) for p in tri))
                                     for tri, _ in triangles(entry['state'], entry['faces'], width, height)))
            if signature in seen:
                seen[signature]['partners'].append(entry)
            else:
                seen[signature] = entry
                representatives.append(entry)
        entries = representatives
    if len(entries) > 2000:
        raise UVError('Constrained packing is limited to 2000 movable islands per operation')
    initial = {}
    for tile in tiles:
        tx, ty = tile_offset(tile)
        # Occupied rectangles reserve gap on their positive axes. Let the outer
        # bin extend by gap so tile border and inter-island gap stay independent.
        initial[tile] = [(tx * width + border, ty * height + border,
                          (tx + 1) * width - border + gap,
                          (ty + 1) * height - border + gap)]
    for obstacle in obstacles:
        a, b, c, d = obstacle['box']
        reserved = (a - gap, b - gap, c + gap, d + gap)
        for tile in tiles:
            initial[tile] = subtract(initial[tile], reserved)
    orders = [sorted(entries, key=lambda e: (e['box'][2] - e['box'][0]) * (e['box'][3] - e['box'][1]), reverse=True)]
    if settings.effort != 'FAST':
        orders.append(sorted(entries, key=lambda e: max(e['box'][2] - e['box'][0], e['box'][3] - e['box'][1]), reverse=True))
    if settings.effort == 'THOROUGH':
        orders.append(sorted(entries, key=lambda e: e['box'][3] - e['box'][1], reverse=True))

    def attempt(scale, order):
        free = {tile: list(rects) for tile, rects in initial.items()}
        placements = []
        for entry in order:
            box = entry['box']
            w, h = (box[2] - box[0]) * scale, (box[3] - box[1]) * scale
            choices = []
            for tile, rectangles in free.items():
                for rect in rectangles:
                    for rotate in ((False, True) if settings.rotation != 'NONE' else (False,)):
                        rw, rh = (h, w) if rotate else (w, h)
                        dw, dh = rect[2] - rect[0] - rw - gap, rect[3] - rect[1] - rh - gap
                        if dw >= -1e-5 and dh >= -1e-5:
                            choices.append(((min(dw, dh), max(dw, dh), tile, rect[1], rect[0]),
                                            tile, rect, rotate, rw, rh))
            if not choices:
                return None
            _, tile, rect, rotate, rw, rh = min(choices, key=lambda item: item[0])
            used = (rect[0], rect[1], rect[0] + rw + gap, rect[1] + rh + gap)
            free[tile] = subtract(free[tile], used)
            if len(free[tile]) > 20000:
                raise UVError('Constrained packing free-space budget exceeded')
            placements.append((entry, Vector((rect[0], rect[1])), rotate, scale))
        return placements

    best, best_scale = None, -1
    if not entries:
        raise UVError('No movable islands: pinned and excluded islands remain fixed')
    for order in orders:
        if settings.pack_scale == 'KEEP':
            placements = attempt(1, order)
            if placements is not None:
                best, best_scale = placements, 1
                break
        else:
            smallest = min(min(e['box'][2] - e['box'][0], e['box'][3] - e['box'][1]) for e in entries)
            lo, hi = 0.0, max(width, height) / max(smallest, 1e-6) * 2
            for _ in range(28):
                mid = (lo + hi) / 2
                placements = attempt(mid, order)
                if placements is None:
                    hi = mid
                else:
                    lo = mid
                    if mid > best_scale:
                        best, best_scale = placements, mid
    if best is None:
        raise UVError('Islands do not fit at the requested density; add tiles or use Fit to Tiles')
    # Independent rectangle postcondition checks before committing any UVs.
    placed_boxes = []
    for entry, origin, rotate, scale in best:
        box = entry['box']
        w, h = (box[2] - box[0]) * scale, (box[3] - box[1]) * scale
        if rotate:
            w, h = h, w
        rect = (origin.x, origin.y, origin.x + w, origin.y + h)
        if any(intersects((rect[0] - gap + 1e-3, rect[1] - gap + 1e-3,
                           rect[2] + gap - 1e-3, rect[3] + gap - 1e-3), other) for other in placed_boxes):
            raise UVError('Constrained layout failed its spacing check')
        if any(intersects((rect[0] - gap + 1e-3, rect[1] - gap + 1e-3,
                           rect[2] + gap - 1e-3, rect[3] + gap - 1e-3), e['box']) for e in obstacles):
            raise UVError('Constrained layout intersects an obstacle')
        tx, ty = floor((rect[0] + 1e-3) / width), floor((rect[1] + 1e-3) / height)
        if (1001 + tx + 10 * ty not in tiles or rect[0] < tx * width + border - 1e-3 or
            rect[1] < ty * height + border - 1e-3 or rect[2] > (tx + 1) * width - border + 1e-3 or
            rect[3] > (ty + 1) * height - border + 1e-3):
            raise UVError('Constrained layout failed tile-border check')
        placed_boxes.append(rect)
    covered = 0
    for entry, origin, rotate, scale in best:
        box = entry['box']
        for partner in [entry] + entry['partners']:
            for loop, p in zip(partner['loops'], partner['points']):
                local = (p - Vector((box[0], box[1]))) * scale
                if rotate:
                    local = Vector(((box[3] - box[1]) * scale - local.y, local.x))
                uv = origin + local
                loop[partner['state'].layer].uv = (uv.x / width, uv.y / height)
        covered += sum(abs(triangle_area(tri)) for tri, _ in triangles(entry['state'], entry['faces'], width, height))
    for state in session.states:
        state.update()
    return covered / (width * height * len(tiles))