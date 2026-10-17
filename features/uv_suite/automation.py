"""Bounded unwrap-method search and in-place layout preservation."""
from collections import deque
from math import log, sqrt
import bpy
from mathutils import Vector
from .context import UVError
from .geometry import islands, triangle_area, triangles


def seam_regions(state):
    remaining = set(state.targets)
    result = []
    while remaining:
        start = min(remaining, key=lambda f: f.index)
        remaining.remove(start)
        group, queue = {start}, deque([start])
        while queue:
            face = queue.popleft()
            for edge in face.edges:
                if edge.seam or len(edge.link_faces) != 2:
                    continue
                for other in edge.link_faces:
                    if other in remaining:
                        remaining.remove(other)
                        group.add(other)
                        queue.append(other)
        result.append(group)
    return result


def unwrap(session, settings, inplace=False):
    from .operations import coordinates, restore_coordinates, update, native
    baseline = coordinates(session)
    pins = {loop: loop[layer].uv.copy() for loop, layer, _ in baseline if loop[layer].pin_uv}
    frames = []
    if inplace:
        for state in session.states:
            for group in islands(state):
                loops = [l for f in group for l in f.loops]
                center = sum((l[state.layer].uv for l in loops), Vector((0, 0))) / len(loops)
                area = sum(abs(triangle_area(tri)) for tri, _ in triangles(state, group, settings.width, settings.height))
                frames.append((state, group, loops, center, area))
    methods = [settings.method]
    if settings.unwrap_search:
        methods.extend(method for method in ('ANGLE_BASED', 'CONFORMAL', 'MINIMUM_STRETCH') if method not in methods)
    session.select_targets()
    best, best_score, reasons = None, float('inf'), []
    best_method = None
    for method in methods:
        restore_coordinates(baseline)
        update(session)
        try:
            native(bpy.ops.uv.unwrap, method=method, margin=0, correct_aspect=False,
                   fill_holes=True, iterations=30)
            for state in session.states:
                for group in islands(state):
                    loops = [l for f in group for l in f.loops]
                    if any(l[state.layer].pin_uv for l in loops):
                        continue
                    center = sum((l[state.layer].uv for l in loops), Vector((0, 0))) / len(loops)
                    for loop in loops:
                        uv = loop[state.layer].uv
                        uv.x = center.x + (uv.x - center.x) * settings.height / settings.width
            # Validate per island so overlap between not-yet-packed islands is
            # not confused with a foldover/self-overlap within an island.
            from .shapes import UVGraph
            score = 0.0
            for state in session.states:
                for group in islands(state):
                    graph = UVGraph(state, group, settings)
                    graph.validate(quality=False)
                    lengths = [(graph.points[a] - graph.points[b]).length / max(length, 1e-10)
                               for (a, b), length in graph.length.items()]
                    mean = sum(log(max(length, 1e-12)) for length in lengths) / len(lengths)
                    score += sum((log(max(length, 1e-12)) - mean) ** 2 for length in lengths)
            if any((loop[layer].uv - pins[loop]).length > 1e-6
                   for loop, layer, _ in baseline if loop in pins):
                raise UVError('Unwrap moved a pinned UV')
            if score < best_score:
                best, best_score = coordinates(session), score
                best_method = method
        except (UVError, RuntimeError) as error:
            reasons.append(f'{method}: {error}')
    settings.details = '\n'.join(reasons)
    if best is None:
        raise UVError('Unwrap failed; UVs restored. ' + '; '.join(reasons))
    restore_coordinates(best)
    if inplace:
        for state, group, loops, center, area in frames:
            if any(l[state.layer].pin_uv for l in loops):
                continue
            current_area = sum(abs(triangle_area(tri)) for tri, _ in triangles(state, group, settings.width, settings.height))
            if area <= 1e-8 or current_area <= 1e-8:
                raise UVError('In-place unwrap requires a non-collapsed original UV island')
            current = sum((l[state.layer].uv for l in loops), Vector((0, 0))) / len(loops)
            scale = sqrt(area / current_area)
            for loop in loops:
                loop[state.layer].uv = center + (loop[state.layer].uv - current) * scale
    update(session)
    return f'{best_method.replace("_", " ").title()} chosen from {len(methods)} method(s)'