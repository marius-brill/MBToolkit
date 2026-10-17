"""Focused UV transforms and transactional UV-map management."""
import bpy
from mathutils import Vector
from .context import UVError
from .geometry import bounds, expand_islands, islands, pixel


def selected_loops(state):
    return [l for f in state.targets for l in f.loops if
            (l.uv_select_vert if state.use_uv else l.vert.select)]


def align(session, settings, action):
    component = 0 if action == 'ALIGN_U' else 1
    for state in session.states:
        loops = selected_loops(state)
        if len(loops) < 2:
            raise UVError('Select at least two UV vertices to align')
        if any(l[state.layer].pin_uv for l in loops):
            raise UVError('Alignment would move pinned UVs')
        value = sum(l[state.layer].uv[component] for l in loops) / len(loops)
        for loop in loops:
            loop[state.layer].uv[component] = value
        state.update()


def weld(session, settings, split=False):
    for state in session.states:
        if split:
            # Selected-face boundary is represented as a real UV discontinuity,
            # not just a mesh seam flag. Translate a tiny explicit pixel offset.
            vertices = {v for f in state.targets for v in f.verts
                        if any(other not in state.targets for other in v.link_faces)}
            loops = [l for f in state.targets for l in f.loops if l.vert in vertices]
            if not loops:
                raise UVError('Select a face region with excluded UV neighbors to split')
            if any(l[state.layer].pin_uv for l in loops):
                raise UVError('Split would move pinned UVs')
            for loop in loops:
                loop[state.layer].uv.x += 0.01 / settings.width
        else:
            by_vertex = {}
            for loop in selected_loops(state):
                by_vertex.setdefault(loop.vert, []).append(loop)
            changed = False
            for loops in by_vertex.values():
                points = [l[state.layer].uv.copy() for l in loops]
                if len(points) < 2 or all((p - points[0]).length < 1e-8 for p in points):
                    continue
                pins = [l[state.layer].uv.copy() for l in loops if l[state.layer].pin_uv]
                if pins and any((p - pins[0]).length > 1e-6 for p in pins):
                    raise UVError('Cannot weld conflicting pinned UV vertices')
                target = pins[0] if pins else sum(points, Vector((0, 0))) / len(points)
                for loop in loops:
                    loop[state.layer].uv = target
                changed = True
            if not changed:
                raise UVError('Select UV splits sharing mesh vertices to weld/stitch')
        state.update()


def transform(session, settings, action):
    expand_islands(session)
    entries = []
    for state in session.states:
        for group in islands(state):
            loops = [l for f in group for l in f.loops]
            if any(l[state.layer].pin_uv for l in loops):
                raise UVError('Transform would move a pinned island')
            points = [pixel(l, state.layer, settings.width, settings.height) for l in loops]
            box = bounds(points)
            center = Vector(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2))
            entries.append((state, loops, points, box, center))
    if not entries:
        raise UVError('No affected islands')
    if action.startswith('DISTRIBUTE'):
        axis = 0 if action.endswith('U') else 1
        entries.sort(key=lambda entry: entry[4][axis])
        low, high = entries[0][4][axis], entries[-1][4][axis]
        for index, entry in enumerate(entries):
            delta = Vector((0, 0))
            delta[axis] = low + (high - low) * index / max(1, len(entries) - 1) - entry[4][axis]
            write(entry, [p + delta for p in entry[2]], settings)
    elif action == 'MATCH_SIZE':
        active = next((e for e in entries if e[0].obj == session.active and
                       e[0].bm.faces.active in e[0].targets and e[0].bm.faces.active in
                       {l.face for l in e[1]}), entries[0])
        target_width, target_height = active[3][2] - active[3][0], active[3][3] - active[3][1]
        for entry in entries:
            w, h = entry[3][2] - entry[3][0], entry[3][3] - entry[3][1]
            if min(w, h) < 1e-8:
                raise UVError('Cannot match collapsed island dimensions')
            write(entry, [entry[4] + Vector(((p.x - entry[4].x) * target_width / w,
                                            (p.y - entry[4].y) * target_height / h)) for p in entry[2]], settings)
    elif action == 'FIT':
        from .layout import tile_offset
        box = bounds([p for entry in entries for p in entry[2]])
        w, h = box[2] - box[0], box[3] - box[1]
        if min(w, h) < 1e-8:
            raise UVError('Cannot fit a collapsed layout')
        scale = min((settings.width - 2 * settings.border) / w,
                    (settings.height - 2 * settings.border) / h)
        if scale <= 0:
            raise UVError('Border leaves no usable space')
        tx, ty = tile_offset(settings.tile_start)
        origin = Vector((tx * settings.width + (settings.width - w * scale) / 2,
                         ty * settings.height + (settings.height - h * scale) / 2))
        for entry in entries:
            write(entry, [origin + (p - Vector((box[0], box[1]))) * scale for p in entry[2]], settings)
    for state in session.states:
        state.update()


def write(entry, points, settings):
    state, loops = entry[:2]
    for loop, p in zip(loops, points):
        loop[state.layer].uv = (p.x / settings.width, p.y / settings.height)


def data_action(context, action):
    settings = context.scene.mbt_uv
    if action == 'CHECKER':
        name = f'MBT UV Grid {settings.width}x{settings.height}'
        image = bpy.data.images.get(name)
        if image is None:
            image = bpy.data.images.new(name, width=settings.width, height=settings.height)
            image.generated_type = 'COLOR_GRID'
        shown = 0
        for area in context.screen.areas if context.screen else []:
            if area.type == 'IMAGE_EDITOR':
                area.spaces.active.image = image
                shown += 1
        return f'UV checker ready in {shown} image editors; materials unchanged'
    if context.mode != 'OBJECT':
        raise UVError('UV map management requires Object Mode')
    objects = [obj for obj in context.selected_objects if obj.type == 'MESH' and obj.data.is_editable]
    meshes = list({obj.data.as_pointer(): obj.data for obj in objects}.values())
    if not meshes:
        raise UVError('Select editable mesh objects')
    name = settings.map_name.strip()
    if not name:
        raise UVError('Enter a UV map name')
    for mesh in meshes:
        if action in {'MAP_COPY', 'MAP_RENAME'} and not mesh.uv_layers.active:
            raise UVError(f'{mesh.name}: no active UV map')
        if action == 'MAP_ACTIVE' and name not in mesh.uv_layers:
            raise UVError(f'{mesh.name}: UV map {name!r} not found')
        if action in {'MAP_NEW', 'MAP_COPY', 'MAP_RENAME'} and name in mesh.uv_layers:
            raise UVError(f'{mesh.name}: UV map {name!r} already exists')
    snapshots = [(mesh, mesh.uv_layers.active_index,
                  [(layer.name, [(tuple(data.uv), data.pin_uv) for data in layer.data], layer.active_render)
                   for layer in mesh.uv_layers]) for mesh in meshes]
    try:
        for mesh in meshes:
            if action in {'MAP_NEW', 'MAP_COPY'}:
                active = mesh.uv_layers.active
                points = [(tuple(data.uv), data.pin_uv) for data in active.data] if active and action == 'MAP_COPY' else None
                layer = mesh.uv_layers.new(name=name, do_init=False)
                if points:
                    for data, (point, pin) in zip(layer.data, points):
                        data.uv = point
                        data.pin_uv = pin
                mesh.uv_layers.active_index = len(mesh.uv_layers) - 1
            elif action == 'MAP_RENAME':
                mesh.uv_layers.active.name = name
            else:
                mesh.uv_layers.active_index = list(mesh.uv_layers.keys()).index(name)
    except Exception:
        for mesh, index, layers in snapshots:
            # No topology changes: reconstruct UV layer coordinates and render flag.
            for layer in list(mesh.uv_layers):
                mesh.uv_layers.remove(layer)
            for layer_name, points, render in layers:
                layer = mesh.uv_layers.new(name=layer_name, do_init=False)
                for data, (point, pin) in zip(layer.data, points):
                    data.uv = point
                    data.pin_uv = pin
                layer.active_render = render
            if layers:
                mesh.uv_layers.active_index = index
        raise
    return f'{action.replace("MAP_", "").title()}: {len(meshes)} mesh datablocks'