"""Conservative bake grouping; source names and geometry are never changed."""
import re
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def stem(name):
    return re.split(r'_(?:low|high)(?:_|\.|$)', name, maxsplit=1, flags=re.I)[0]


def resolve(context, low, high):
    from .jobs import PainterError, safe_name
    groups = {obj: 'MBTBake_' + safe_name(stem(obj.name)) for obj in low}
    if len(set(groups.values())) != len(low):
        raise PainterError('Low mesh bake names collide; use unique base names before _low')
    result = {}
    depsgraph = context.evaluated_depsgraph_get()
    surfaces = {}

    def surface(obj):
        if obj not in surfaces:
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            try:
                vertices = [evaluated.matrix_world @ v.co for v in mesh.vertices]
                if not vertices or not mesh.polygons:
                    raise PainterError(f'{obj.name}: evaluated mesh has no surface for matching')
                tree = BVHTree.FromPolygons(vertices, [list(p.vertices) for p in mesh.polygons])
                minimum = Vector(tuple(min(v[i] for v in vertices) for i in range(3)))
                maximum = Vector(tuple(max(v[i] for v in vertices) for i in range(3)))
                samples = vertices[::max(1, len(vertices) // 128)][:128]
                surfaces[obj] = tree, minimum, maximum, samples
            finally:
                evaluated.to_mesh_clear()
        return surfaces[obj]

    for obj in high:
        explicit = obj.mbt_bake_target
        if explicit is not None:
            if explicit not in groups:
                raise PainterError(f'{obj.name}: Bake Target is not in the low collection')
            result[obj] = explicit
            continue
        named = [target for target in low if stem(target.name) == stem(obj.name)]
        if len(named) == 1:
            result[obj] = named[0]
            continue
        _, hmin, hmax, samples = surface(obj)
        scores = []
        for target in low:
            tree, minimum, maximum, _ = surface(target)
            diagonal = (maximum - minimum).length
            tolerance = max(diagonal * 0.1, 1e-6)
            if any(hmax[i] < minimum[i] - tolerance or hmin[i] > maximum[i] + tolerance
                   for i in range(3)):
                continue
            distances = [tree.find_nearest(point)[3] for point in samples]
            if not distances or any(distance is None for distance in distances):
                continue
            if sum(distance <= tolerance for distance in distances) / len(distances) < 0.9:
                continue
            scores.append((sum(distances) / len(distances) / max(diagonal, 1e-6), target))
        scores.sort(key=lambda item: item[0])
        if not scores or (len(scores) > 1 and scores[1][0] <= scores[0][0] * 2 + 0.01):
            raise PainterError(f'{obj.name}: ambiguous or missing low match. Select this high mesh and set Bake Target')
        result[obj] = scores[0][1]
    missing = [obj.name for obj in low if obj not in result.values()]
    if missing:
        raise PainterError('No high mesh matched: ' + ', '.join(missing))
    names = {obj: group + '_low' for obj, group in groups.items()}
    for target, group in groups.items():
        for index, obj in enumerate(obj for obj in high if result[obj] == target):
            names[obj] = group + '_high' + (f'_{index:03d}' if index else '')
    return names, result