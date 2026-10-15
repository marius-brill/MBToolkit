"""Resample open edge chains and one-quad-wide surface strips in Edit Mode.

All computation and topology operations run on a private BMesh. Only a complete
result is committed to the edit mesh; a serialized backup protects the commit.
"""

import bisect
import bpy
import bmesh
from bpy.props import IntProperty, EnumProperty, FloatProperty

from ..core.registry import register_classes, unregister_classes


def _edit_mesh_poll(context):
    return (context.mode == 'EDIT_MESH' and context.edit_object is not None
            and context.edit_object.type == 'MESH')


def _history(bm):
    for elements in (bm.verts, bm.edges, bm.faces):
        elements.index_update()
    return [(('VERT' if isinstance(e, bmesh.types.BMVert) else
              'EDGE' if isinstance(e, bmesh.types.BMEdge) else 'FACE'), e.index)
            for e in bm.select_history if e.is_valid and e.select]


def _restore_state(bm, history, active_face):
    tables = {'VERT': bm.verts, 'EDGE': bm.edges, 'FACE': bm.faces}
    for elements in tables.values():
        elements.ensure_lookup_table()
    bm.select_history.clear()
    for kind, index in history:
        elements = tables[kind]
        if index < len(elements) and elements[index].select:
            bm.select_history.add(elements[index])
    if active_face is not None and active_face < len(bm.faces):
        bm.faces.active = bm.faces[active_face]


def _transaction(context, operation):
    """Never expose partially processed components to the live edit mesh."""
    if len(context.objects_in_mode) != 1:
        raise ValueError("Resample supports one object in Edit Mode at a time")
    mesh = context.edit_object.data
    if mesh.shape_keys is not None:
        raise ValueError("Resample does not support meshes with shape keys")
    live = bmesh.from_edit_mesh(mesh)
    history = _history(live)
    active_face = live.faces.active.index if live.faces.active else None
    work = live.copy()
    backup = staged = None
    try:
        _restore_state(work, history, active_face)
        result = operation(work)
        work.normal_update()
        work.select_flush_mode()
        work.select_history.validate()
        new_history = _history(work)
        new_active = work.faces.active.index if work.faces.active else None
        # Mesh serialization carries custom data, hide flags and selection.
        staged = bpy.data.meshes.new("__mbt_resample_result")
        work.to_mesh(staged)
        backup = bpy.data.meshes.new("__mbt_resample_backup")
        live_copy = live.copy()
        try:
            live_copy.to_mesh(backup)
        finally:
            live_copy.free()
        try:
            live.clear()
            live.from_mesh(staged)
            _restore_state(live, new_history, new_active)
            bmesh.update_edit_mesh(mesh, loop_triangles=True, destructive=True)
        except Exception:
            live.clear()
            live.from_mesh(backup)
            _restore_state(live, history, active_face)
            bmesh.update_edit_mesh(mesh, loop_triangles=True, destructive=True)
            raise
        return result
    finally:
        work.free()
        for temporary in (staged, backup):
            if temporary is not None:
                bpy.data.meshes.remove(temporary)

# Reuse the established wire-chain implementation.
def ordered_chains(bm):
    edges = [e for e in bm.edges if e.select and not e.hide]
    if not edges:
        raise ValueError("Select at least one edge")
    neighbors = {}
    for e in edges:
        a, b = e.verts
        neighbors.setdefault(a, []).append(b)
        neighbors.setdefault(b, []).append(a)
    if any(len(n) > 2 for n in neighbors.values()):
        raise ValueError("Branching selections are not supported")
    unseen = set(neighbors)
    chains = []
    while unseen:
        seed = min(unseen, key=lambda v: v.index)
        component = {seed}
        stack = [seed]
        while stack:
            for v in neighbors[stack.pop()]:
                if v not in component:
                    component.add(v)
                    stack.append(v)
        ends = [v for v in component if len(neighbors[v]) == 1]
        if len(ends) != 2:
            raise ValueError("Only open edge chains are supported")
        active = bm.select_history.active
        start = active if active in ends else min(ends, key=lambda v: v.index)
        chain = [start]
        prev = None
        while True:
            nxt = [v for v in neighbors[chain[-1]] if v is not prev]
            if not nxt:
                break
            prev, current = chain[-1], nxt[0]
            chain.append(current)
        if len(chain) != len(component):
            raise ValueError("Could not order edge chain")
        chains.append(chain)
        unseen.difference_update(component)
    return chains


def interpolate(points, t, mode):
    count = len(points)
    x = max(0.0, min(float(count - 1), t * (count - 1)))
    i = min(int(x), count - 2)
    u = x - i
    p1, p2 = points[i], points[i + 1]
    if mode == 'LINEAR' or count == 2:
        return p1.lerp(p2, u)
    p0 = points[max(0, i - 1)]
    p3 = points[min(count - 1, i + 2)]
    d0 = max((p1 - p0).length, 1e-8)
    d1 = max((p2 - p1).length, 1e-8)
    d2 = max((p3 - p2).length, 1e-8)
    m1 = (p2 - p0) * (d1 / (d0 + d1)) if i > 0 else (p2 - p1)
    m2 = (p3 - p1) * (d1 / (d1 + d2)) if i + 2 < count else (p2 - p1)
    u2, u3 = u*u, u*u*u
    return ((2*u3-3*u2+1)*p1 + (u3-2*u2+u)*m1
            + (-2*u3+3*u2)*p2 + (u3-u2)*m2)


def resampled_positions(vertices, target_count, mode):
    points = [v.co.copy() for v in vertices]
    if all((p-points[0]).length < 1e-9 for p in points[1:]):
        raise ValueError("Cannot resample zero-length chain")
    steps = min(max(128, (len(points)-1)*24, target_count*12), 50000)
    samples = [interpolate(points, k/steps, mode) for k in range(steps+1)]
    distances = [0.0]
    for a, b in zip(samples, samples[1:]):
        distances.append(distances[-1] + (b-a).length)
    total = distances[-1]
    if total < 1e-9:
        raise ValueError("Curve length too small")
    result = [points[0].copy()]
    for k in range(1, target_count-1):
        d = total*k/(target_count-1)
        j = max(1, min(bisect.bisect_left(distances, d), steps))
        delta = distances[j]-distances[j-1]
        f = (d-distances[j-1])/delta if delta > 1e-12 else 0.0
        result.append(samples[j-1].lerp(samples[j], f))
    result.append(points[-1].copy())
    return result


class MBT_OT_resample_wire(bpy.types.Operator):
    """Resample open wire chains; face-connected chains support same-count redistribution"""
    bl_idname = "mbt.resample_wire"
    bl_label = "Resample Edge Chain"
    bl_options = {'REGISTER', 'UNDO'}
    count: IntProperty(name="Vertices", default=12, min=2, max=4096)
    method: EnumProperty(name="Interpolation", items=[
        ('CATMULL', "Smooth", "Cubic interpolation"),
        ('LINEAR', "Linear", "Original polyline"),
    ], default='CATMULL')

    @classmethod
    def poll(cls, context):
        return _edit_mesh_poll(context)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=280)

    def execute(self, context):
        try:
            total = _transaction(context, self._resample)
        except Exception as exc:
            if not isinstance(exc, ValueError):
                import traceback
                traceback.print_exc()
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, f"Resampled {total} chain(s) to {self.count} vertices")
        return {'FINISHED'}

    def _resample(self, bm):
        bm.verts.index_update()
        plans = []
        for chain in ordered_chains(bm):
            if any((b.co - a.co).length < 1e-8 for a, b in zip(chain, chain[1:])):
                raise ValueError("Overlapping chain vertices are unsupported")
            is_wire = all(not v.link_faces and all(e.select and not e.hide for e in v.link_edges)
                          for v in chain)
            if self.count != len(chain) and not is_wire:
                raise ValueError("Changing count requires an isolated wire chain; use Resample Surface Strip for quads")
            plans.append((chain, resampled_positions(chain, self.count, self.method)))
        for chain, positions in plans:
            if len(chain) == self.count:
                for v, p in zip(chain, positions):
                    v.co = p
            else:
                original_edges = [bm.edges.get((a,b)) for a,b in zip(chain,chain[1:])]
                # Blender 5.2's interpolation can invalidate the Python wrapper
                # when the custom-data layout is empty. There is nothing to
                # interpolate in that case, so do not call it.
                has_vertex_data = any(
                    getattr(bm.verts.layers, kind).values()
                    for kind in ('float', 'int', 'string', 'float_vector', 'color', 'float_color', 'deform')
                    if hasattr(bm.verts.layers, kind))
                new_verts = [chain[0]]
                for i, position in enumerate(positions[1:-1], 1):
                    source = i * (len(chain) - 1) / (self.count - 1)
                    index = min(int(source), len(chain) - 2)
                    vertex = bm.verts.new(position)
                    if has_vertex_data:
                        vertex.copy_from_vert_interp((chain[index], chain[index + 1]), source - index)
                    vertex.co = position
                    new_verts.append(vertex)
                new_verts.append(chain[-1])
                # Snapshot edge attributes before removing original topology.
                edge_data = []
                layers = []
                for kind in ('float', 'int', 'string', 'float_vector', 'color', 'float_color'):
                    collection = getattr(bm.edges.layers, kind, None)
                    if collection is not None:
                        layers.extend(collection.values())
                for i in range(self.count - 1):
                    index = min(int((i + 0.5) * (len(chain) - 1) / (self.count - 1)), len(original_edges) - 1)
                    source_edge = original_edges[index]
                    values = []
                    for layer in layers:
                        value = source_edge[layer]
                        values.append((layer, value.copy() if hasattr(value, 'copy') else value))
                    edge_data.append((source_edge.seam, source_edge.smooth, values))
                for vertex in new_verts:
                    vertex.select_set(True)
                for a, b, (seam, smooth, values) in zip(new_verts, new_verts[1:], edge_data):
                    edge = bm.edges.new((a, b))
                    edge.seam = seam
                    edge.smooth = smooth
                    for layer, value in values:
                        edge[layer] = value
                    edge.select_set(True)
                for edge in original_edges:
                    if edge.is_valid:
                        bm.edges.remove(edge)
                for vertex in chain[1:-1]:
                    if vertex.is_valid and not vertex.link_edges and not vertex.link_faces:
                        bm.verts.remove(vertex)
        return len(plans)



def opposite(edge, face):
    if len(face.verts) != 4 or edge not in face.edges:
        return None
    return next((e for e in face.edges if not set(e.verts).intersection(edge.verts)), None)


def trace_strip(start, faces):
    """Walk a one-quad-wide face strip from a transverse end edge."""
    edges, visited = [start], set()
    current = start
    while True:
        choices = [f for f in current.link_faces if f in faces and f not in visited]
        if not choices:
            break
        if len(choices) != 1:
            return None
        face = choices[0]
        nxt = opposite(current, face)
        if nxt is None or nxt in edges:
            return None
        visited.add(face)
        edges.append(nxt)
        current = nxt
    return edges if visited == faces else None


def selected_strips(bm, face_mode):
    if face_mode:
        faces = {f for f in bm.faces if f.select and not f.hide}
        if not faces or any(len(f.verts) != 4 for f in faces):
            raise ValueError("Select a connected strip of quad faces")
        components = []
        remaining = set(faces)
        while remaining:
            seed = min(remaining, key=lambda f: f.index)
            component, stack = {seed}, [seed]
            while stack:
                for edge in stack.pop().edges:
                    for neighbor in edge.link_faces:
                        if neighbor in faces and neighbor not in component:
                            component.add(neighbor)
                            stack.append(neighbor)
            components.append(component)
            remaining -= component
        result = []
        # Trace across opposite quad edges. Try every perimeter edge; this
        # supports even a single selected quad or a two-quad-wide band.
        for component in components:
            boundary = {e for f in component for e in f.edges
                        if sum(neighbor in component for neighbor in e.link_faces) == 1}
            candidates = []
            for edge in sorted(boundary, key=lambda e: e.index):
                path = trace_strip(edge, component)
                if path:
                    candidates.append(path)
            if not candidates:
                raise ValueError("Selection must form a one-quad-wide open strip (no branches)")
            candidates.sort(key=lambda c: (-len(c), sum(e.calc_length() for e in c) / len(c), c[0].index))
            result.append(candidates[0])
        return result

    selected = {e for e in bm.edges if e.select and not e.hide}
    if len(selected) < 2:
        raise ValueError("Select at least two parallel cross edges")
    seen_vertices = set()
    for edge in selected:
        if seen_vertices.intersection(edge.verts):
            raise ValueError("Cross edges must not share vertices")
        seen_vertices.update(edge.verts)
    adjacency = {e: set() for e in selected}
    for f in bm.faces:
        if f.hide or len(f.verts) != 4:
            continue
        chosen = [e for e in f.edges if e in selected]
        if len(chosen) == 2 and opposite(chosen[0], f) is chosen[1]:
            adjacency[chosen[0]].add(chosen[1])
            adjacency[chosen[1]].add(chosen[0])
    remaining, result = set(selected), []
    while remaining:
        seed = min(remaining, key=lambda e: e.index)
        component, stack = {seed}, [seed]
        while stack:
            for e in adjacency[stack.pop()]:
                if e not in component:
                    component.add(e)
                    stack.append(e)
        ends = [e for e in component if len(adjacency[e]) == 1]
        if (len(ends) != 2 or len(component) < 2
                or any(len(adjacency[e]) > 2 for e in component)):
            raise ValueError("Select consecutive cross edges across quad faces")
        chain, previous = [min(ends, key=lambda e: e.index)], None
        while True:
            choices = [e for e in adjacency[chain[-1]] if e is not previous]
            if not choices:
                break
            previous = chain[-1]
            chain.append(choices[0])
        result.append(chain)
        remaining -= component
    return result


def ordered_rails(cross_edges):
    """Follow two rails, checking shared quad faces at each step."""
    first = cross_edges[0]
    rails = [[first.verts[0]], [first.verts[1]]]
    for previous, edge in zip(cross_edges, cross_edges[1:]):
        # A quad between opposite edges establishes consistent orientation.
        bridge = next((f for f in previous.link_faces
                       if len(f.verts) == 4 and edge in f.edges
                       and opposite(previous, f) is edge), None)
        if bridge is None:
            raise ValueError("Cross edges must bound consecutive quad faces")
        a, b = edge.verts
        if bmesh_edge(rails[0][-1], a) and bmesh_edge(rails[1][-1], b):
            rails[0].append(a); rails[1].append(b)
        elif bmesh_edge(rails[0][-1], b) and bmesh_edge(rails[1][-1], a):
            rails[0].append(b); rails[1].append(a)
        else:
            raise ValueError("Cannot follow the strip rails")
    return rails


def bmesh_edge(a, b):
    return next((e for e in a.link_edges if b in e.verts), None)


def resample_strip(bm, cross_edges, target):
    if len(cross_edges) < 2:
        raise ValueError("Strip needs at least two cross edges")
    rails = ordered_rails(cross_edges)
    original = len(cross_edges)
    if target == original:
        return
    _prepare_connected_sides(bm, cross_edges, rails)
    # Add one or more subdivisions to every rail segment. Grid fill inserts
    # matching transverse edges into each quad face.
    if target > original:
        cuts = (target - 2) // (original - 1) + 1
        rail_edges = [bmesh_edge(a, b) for rail in rails for a, b in zip(rail, rail[1:])]
        if any(e is None for e in rail_edges):
            raise ValueError("Could not locate strip rails")
        first_face = _strip_faces(cross_edges)[0]
        outside_start = set(cross_edges[0].link_faces) - {first_face}
        bmesh.ops.subdivide_edges(bm, edges=list(set(rail_edges)), cuts=cuts, use_grid_fill=True)
        # Find the new ordered sequence by walking from the original first edge.
        # Boundary rails and the blocked start-side face leave one continuation.
        current, new_edges, seen = cross_edges[0], [cross_edges[0]], set()
        end = cross_edges[-1]
        while current is not end:
            options = []
            for f in current.link_faces:
                if len(f.verts) != 4 or f in seen or f in outside_start:
                    continue
                nxt = opposite(current, f)
                if nxt is None or nxt in new_edges:
                    continue
                options.append((f, nxt))
            if len(options) != 1:
                raise ValueError("Subdivision did not form a valid quad strip")
            f, nxt = options[0]
            seen.add(f)
            new_edges.append(nxt)
            current = nxt
            if len(new_edges) > 100000:
                raise ValueError("Strip too large")
        cross_edges = new_edges
        rails = ordered_rails(cross_edges)

    # Reduce to exactly the requested number of cross edges. For an increase,
    # subdivision gives a sufficiently dense set of candidates to redistribute.
    n = len(cross_edges)
    if target > n:
        raise ValueError("Could not create enough subdivision edges")
    if target < n:
        keep = {round(k * (n-1) / (target-1)) for k in range(target)}
        remove = [e for i, e in enumerate(cross_edges) if i not in keep]
        bmesh.ops.dissolve_edges(bm, edges=remove, use_verts=True, use_face_split=False)
        cross_edges = [e for i, e in enumerate(cross_edges) if i in keep]
        rails = ordered_rails(cross_edges)

    # Reposition intermediate vertices to evenly spaced positions along the
    # original surface profile (not just nearest surviving edge indices).
    # Captured before the first topology operation below in the calling code.
    return rails


def _strip_faces(cross_edges):
    faces = []
    for a, b in zip(cross_edges, cross_edges[1:]):
        bridges = [f for f in a.link_faces if not f.hide and len(f.verts) == 4
                   and b in f.edges and opposite(a, f) is b]
        if len(bridges) != 1:
            raise ValueError("Cross edges must bound exactly one visible quad")
        faces.append(bridges[0])
    return faces


def _prepare_connected_sides(bm, group, rails):
    """Merge the immediate side fans so rail count changes stay watertight.

    Edges between adjacent outside faces at an intermediate rail vertex are
    removed, never the outside perimeter. The resulting side n-gons can follow
    the resampled rail without dangling spokes or detached geometry.
    """
    strip = set(_strip_faces(group))
    dissolve = set()
    for rail in rails:
        for vertex in rail[1:-1]:
            outside = set(vertex.link_faces) - strip
            if any(f.hide for f in outside):
                raise ValueError('Cannot change a rail connected to hidden faces')
            for edge in vertex.link_edges:
                if edge.hide or len(edge.link_faces) > 2:
                    raise ValueError('Cannot change a rail connected to hidden or non-manifold edges')
                if not edge.link_faces:
                    raise ValueError('Cannot change a rail connected to loose edges')
                if len(edge.link_faces) == 2 and all(f in outside for f in edge.link_faces):
                    if edge.seam or edge.link_faces[0].material_index != edge.link_faces[1].material_index:
                        raise ValueError('Changing this rail would remove a side-face seam or material boundary')
                    dissolve.add(edge)
    if dissolve:
        bmesh.ops.dissolve_edges(bm, edges=list(dissolve), use_verts=False, use_face_split=False)


def _validate_strip(group, rails):
    """Validate the band without requiring disconnected boundary rails."""
    faces = set(_strip_faces(group))
    edges = {e for face in faces for e in face.edges}
    if any(e.hide or any(v.hide for v in e.verts) or len(e.link_faces) > 2 for e in edges):
        raise ValueError("Hidden or non-manifold strip geometry is unsupported")
    if len({v for rail in rails for v in rail}) != 2 * len(group):
        raise ValueError("Closed or self-connected strips are unsupported")
    return faces


def smooth_positions(points, count, smoothness=0.85):
    """Arc-length sample a shape-preserving curve with circular local tangents.

    Local circumcircle tangents provide a better round profile from sparse
    samples than the previous chord-based cubic. Noncircular shapes are
    handled locally rather than projected onto one global circle.
    """
    from mathutils import Vector
    import math
    if len(points) < 2:
        raise ValueError("At least two profile points required")
    if any((b-a).length < 1e-8 for a,b in zip(points, points[1:])):
        raise ValueError("Overlapping rail vertices are unsupported")

    def local_tangent(a, b, c):
        u, v = b-a, c-b
        lu, lv = u.length, v.length
        # Circle tangent at b: the tangent bisects the turn in angle,
        # adjusted for nonuniform chord lengths.
        ua, va = u.normalized(), v.normalized()
        direction = ua + va
        if direction.length < 1e-7:
            return (u+v)*0.5
        direction.normalize()
        return direction

    dirs = []
    for i in range(len(points)):
        if i == 0:
            if len(points) > 2:
                # Extrapolate the first tangent from the local turn angle.
                d = local_tangent(*points[:3]); chord = (points[1]-points[0]).normalized()
                turn = d.dot(chord)
                tangent = (chord*2.0*max(turn,0.1)-d)
                dirs.append(tangent.normalized() if tangent.length > 1e-8 else chord)
            else:
                dirs.append((points[1]-points[0]).normalized())
        elif i == len(points)-1:
            if len(points)>2:
                d=local_tangent(*points[-3:]); chord=(points[-1]-points[-2]).normalized()
                tangent=chord*2.0*max(d.dot(chord),0.1)-d
                dirs.append(tangent.normalized() if tangent.length>1e-8 else chord)
            else:
                dirs.append((points[-1]-points[-2]).normalized())
        else:
            dirs.append(local_tangent(points[i-1],points[i],points[i+1]))

    def sample(i,t):
        a,b=points[i],points[i+1]
        chord=b-a
        length=chord.length
        if smoothness <= 0:
            return a.lerp(b,t)
        # Scale Hermite tangents to the arc-length of a circular arc whose
        # end tangent matches the local profile; limit severe overshoots.
        d0,d1=dirs[i],dirs[i+1]
        theta=math.acos(max(-1.,min(1.,d0.dot(d1))))
        scale=min(1.35, theta/(2*math.sin(theta/2))) if theta>1e-5 else 1.0
        m0=d0*length*scale
        m1=d1*length*scale
        t2,t3=t*t,t*t*t
        cubic=((2*t3-3*t2+1)*a+(t3-2*t2+t)*m0
               +(-2*t3+3*t2)*b+(t3-t2)*m1)
        return a.lerp(cubic,smoothness)

    subdivisions=max(64,min(256,count*8))
    samples=[points[0].copy()]
    for i in range(len(points)-1):
        for j in range(1,subdivisions+1):
            samples.append(sample(i,j/subdivisions))
    cumulative=[0.0]
    for a,b in zip(samples,samples[1:]):
        cumulative.append(cumulative[-1]+(b-a).length)
    total=cumulative[-1]
    if total<1e-9:
        raise ValueError("Curve too short")
    result=[points[0].copy()]
    for k in range(1,count-1):
        target=total*k/(count-1)
        j=max(1,min(bisect.bisect_left(cumulative,target),len(samples)-1))
        width=cumulative[j]-cumulative[j-1]
        t=(target-cumulative[j-1])/width if width>1e-12 else 0.0
        result.append(samples[j-1].lerp(samples[j],t))
    result.append(points[-1].copy())
    return result


class MBT_OT_resample_surface(bpy.types.Operator):
    """Resample a quad strip to an exact number of evenly spaced cross edges"""
    bl_idname = 'mbt.resample_surface'
    bl_label = 'Resample Surface Strip'
    bl_options = {'REGISTER', 'UNDO'}
    count: IntProperty(name='Cross Edges', description='Number of cross edges including both fixed ends; faces = count minus one', default=4, min=2, max=256)
    roundness: FloatProperty(name='Roundness', description='0 samples the source polyline; 1 reconstructs a rounded profile', default=0.85, min=0.0, max=1.0)

    @classmethod
    def poll(cls, context):
        return _edit_mesh_poll(context)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=280)

    def execute(self, context):
        try:
            total = _transaction(context, lambda bm: self._resample(
                bm, context.tool_settings.mesh_select_mode[2]))
        except Exception as exc:
            if not isinstance(exc, ValueError):
                import traceback
                traceback.print_exc()
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, f'Resampled {total} strip(s) to {self.count} cross edges')
        return {'FINISHED'}

    def _resample(self, bm, face_mode):
        for elements in (bm.verts, bm.edges, bm.faces):
            elements.index_update()
        groups = selected_strips(bm, face_mode)
        plans, used = [], set()
        for group in groups:
            rails = ordered_rails(group)
            _validate_strip(group, rails)
            vertices = {v for rail in rails for v in rail}
            if used.intersection(vertices):
                raise ValueError("Selected strips must not share vertices")
            used.update(vertices)
            original = [[v.co.copy() for v in rail] for rail in rails]
            targets = [smooth_positions(pts, self.count, self.roundness) for pts in original]
            plans.append((group, rails, targets))
        for group, rails, targets in plans:
            new_rails = resample_strip(bm, group, self.count) or rails
            if any(len(rail) != self.count for rail in new_rails):
                raise ValueError('Resulting rail vertex count differs from requested count')
            for rail, coords in zip(new_rails, targets):
                for vertex, co in zip(rail[1:-1], coords[1:-1]):
                    vertex.co = co
            cross_edges = [bmesh_edge(a, b) for a, b in zip(*new_rails)]
            faces = _strip_faces(cross_edges)
            for face in faces:
                face.select_set(False)
            for face in faces:
                for edge in face.edges:
                    edge.select_set(False)
            if face_mode:
                for face in faces:
                    face.select_set(True)
                bm.faces.active = faces[0]
            else:
                for edge in cross_edges:
                    edge.select_set(True)
            bm.select_history.clear()
            bm.select_history.add(faces[0] if face_mode else cross_edges[0])
        return len(plans)


def draw(layout, context):
    ready = _edit_mesh_poll(context)
    if not ready:
        layout.label(text="Enter mesh Edit Mode to resample", icon='INFO')
    elif len(context.objects_in_mode) != 1:
        layout.label(text="Edit one mesh object at a time", icon='INFO')
        ready = False
    column = layout.column(align=True)
    column.enabled = ready
    column.operator_context = 'INVOKE_DEFAULT'
    column.operator('mbt.resample_surface', text='Resample Surface Strip', icon='MOD_SUBSURF')
    column.operator('mbt.resample_wire', text='Resample Edge Chain', icon='CURVE_PATH')


classes = (MBT_OT_resample_wire, MBT_OT_resample_surface)

def register():
    register_classes(classes)

def unregister():
    unregister_classes(classes)
