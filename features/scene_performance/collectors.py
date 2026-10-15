"""Read-only geometry and native modifier diagnostics. No evaluated IDs escape."""

import math


MESH_TYPES = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}


def tri_count(mesh):
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def evaluated_tris(evaluated):
    if evaluated.type not in MESH_TYPES:
        return None
    try:
        mesh = evaluated.to_mesh()
        return tri_count(mesh) if mesh is not None else None
    finally:
        evaluated.to_mesh_clear()


def collect_object(depsgraph, obj, timings=True):
    """Capture scalar values only; execution_time is seconds on evaluated modifiers."""
    evaluated = obj.evaluated_get(depsgraph)
    modifiers = []
    if timings:
        for modifier in evaluated.modifiers:
            enabled = modifier.show_viewport
            seconds = getattr(modifier, 'execution_time', None)
            ms = (seconds * 1000.0 if enabled and seconds is not None
                  and math.isfinite(seconds) and seconds >= 0 else None)
            modifiers.append({'uid': modifier.persistent_uid, 'name': modifier.name,
                              'enabled': enabled, 'ms': ms})
    enabled = [modifier for modifier in modifiers if modifier['enabled']]
    total = (sum(modifier['ms'] for modifier in enabled)
             if enabled and all(modifier['ms'] is not None for modifier in enabled) else None)
    return {'uid': str(obj.session_uid), 'name': obj.name, 'type': obj.type,
            'tris': evaluated_tris(evaluated), 'ms': total, 'mods': modifiers, 'error': ''}