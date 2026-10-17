"""Explicit selection tools; unlike transforms these intentionally commit selection."""
from math import floor
from .context import UVError
from .geometry import islands, triangles, triangle_area, intersection_area, bounds, density


def select(session, settings, action):
    if session.object_mode:
        raise UVError('Selection tools require mesh Edit Mode')
    chosen = {state: set() for state in session.states}
    if action in {'SELECT_ISLANDS', 'SELECT_SIMILAR'}:
        references = []
        for state in session.states:
            visible = {f for f in state.bm.faces if not f.hide}
            for group in islands(state, visible):
                if group & state.targets:
                    references.append((len(group), sorted(len(f.loops) for f in group)))
                    if action == 'SELECT_ISLANDS':
                        chosen[state].update(group)
        if action == 'SELECT_SIMILAR':
            for state in session.states:
                for group in islands(state, {f for f in state.bm.faces if not f.hide}):
                    if (len(group), sorted(len(f.loops) for f in group)) in references:
                        chosen[state].update(group)
    elif action == 'SELECT_DENSITY':
        for state in session.states:
            for group in islands(state, {f for f in state.bm.faces if not f.hide}):
                try:
                    actual = density(state, group, settings.width, settings.height,
                                     session.context.scene.unit_settings.scale_length)
                    if abs(actual / settings.density - 1) > settings.density_tolerance / 100:
                        chosen[state].update(group)
                except UVError:
                    chosen[state].update(group)
    else:
        records = []
        for state in session.states:
            visible = {f for f in state.bm.faces if not f.hide}
            for tri, face in triangles(state, visible, settings.width, settings.height):
                area = triangle_area(tri)
                box = bounds(tri)
                if action == 'SELECT_DEGENERATE' and abs(area) < 1e-8:
                    chosen[state].add(face)
                elif action == 'SELECT_FLIPPED' and area < -1e-8:
                    chosen[state].add(face)
                elif action == 'SELECT_OUTSIDE':
                    tx, ty = floor((box[0] + 1e-4) / settings.width), floor((box[1] + 1e-4) / settings.height)
                    tile = 1001 + tx + ty * 10
                    if (not (0 <= tx < 10 and ty >= 0 and settings.tile_start <= tile < settings.tile_start + settings.tile_count)
                            or box[2] > (tx + 1) * settings.width + 1e-4
                            or box[3] > (ty + 1) * settings.height + 1e-4):
                        chosen[state].add(face)
                elif action == 'SELECT_OVERLAP':
                    records.append((box, tri, state, face))
        if action == 'SELECT_OVERLAP':
            checks = 0
            records.sort(key=lambda item: item[0][0])
            for index, (box, tri, state, face) in enumerate(records):
                for j in range(index + 1, len(records)):
                    other_box, other, other_state, other_face = records[j]
                    if other_box[0] >= box[2] - 1e-5:
                        break
                    if other_box[1] >= box[3] - 1e-5 or other_box[3] <= box[1] + 1e-5:
                        continue
                    checks += 1
                    if checks > 2000000:
                        raise UVError('Overlap selection budget exceeded; hide unrelated geometry')
                    tolerance = max(1e-3, min(abs(triangle_area(tri)), abs(triangle_area(other))) * 1e-6)
                    if intersection_area(tri, other) > tolerance:
                        chosen[state].add(face)
                        chosen[other_state].add(other_face)
    count = 0
    for state, faces in chosen.items():
        original_faces = dict(state.faces)
        for vertex in state.bm.verts:
            vertex.select = False
        for edge in state.bm.edges:
            edge.select = False
        for face in state.bm.faces:
            if state.use_uv:
                # Keep mesh visibility selection; only UV selection changes.
                face.select = original_faces[face]
            else:
                face.select_set(face in faces)
            for loop in face.loops:
                loop.uv_select_vert = face in faces
                loop.uv_select_edge = face in faces
        state.commit_selection = True
        count += len(faces)
        state.update()
    return count