"""Destructive UV integration tests. ONLY disposable --background --factory-startup."""
import importlib
from pathlib import Path
import sys
import bpy
import bmesh

sys.stdout.reconfigure(line_buffering=True)
print('START UV SUITE TESTS', flush=True)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
# Load only the UV feature. Importing the complete addon also initializes unrelated
# features and makes this focused solver test depend on their startup behavior.
import types
for name, directory in ((ROOT.name, ROOT), (f'{ROOT.name}.features', ROOT / 'features'),
                        (f'{ROOT.name}.core', ROOT / 'core')):
    package = types.ModuleType(name)
    package.__path__ = [str(directory)]
    sys.modules[name] = package
suite = importlib.import_module(f'{ROOT.name}.features.uv_suite')
operations = importlib.import_module(f'{ROOT.name}.features.uv_suite.operations')
geometry = importlib.import_module(f'{ROOT.name}.features.uv_suite.geometry')
UVSession = importlib.import_module(f'{ROOT.name}.features.uv_suite.context').UVSession
UVError = importlib.import_module(f'{ROOT.name}.features.uv_suite.context').UVError


def reset():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def cube(name='Cube'):
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.object
    obj.name = name
    return obj


def snapshot(obj):
    return (tuple(tuple(v.co) for v in obj.data.vertices),
            tuple((tuple(p.vertices), p.material_index) for p in obj.data.polygons),
            tuple(e.use_seam for e in obj.data.edges),
            tuple((layer.name, tuple(tuple(uv.uv) for uv in layer.data)) for layer in obj.data.uv_layers))


def main():
    print('Register suite', flush=True)
    suite.register()
    settings = bpy.context.scene.mbt_uv
    reset()
    obj = cube()
    obj.data.uv_layers.new(name='Untouched')
    obj.data.uv_layers.active_index = 0
    untouched = tuple(tuple(uv.uv) for uv in obj.data.uv_layers[1].data)
    before = snapshot(obj)
    print('Run auto cube', flush=True)
    # Box/no-rotation smoke path isolates packing from expensive arbitrary-angle search.
    settings.rotation = 'NONE'
    settings.effort = 'FAST'
    operations.run(bpy.context, 'AUTO')
    assert bpy.context.mode == 'OBJECT'
    assert snapshot(obj)[:2] == before[:2]
    assert tuple(tuple(uv.uv) for uv in obj.data.uv_layers[1].data) == untouched
    with UVSession(bpy.context) as session:
        report = geometry.inspect(session, settings, padding=True)
        assert report['islands'] == 6, report
        assert not any(report[k] for k in ('degenerate', 'outside', 'overlaps', 'gap_violations', 'border_violations')), report
    print('PASS auto cube, padding, topology, unrelated UV map')
    operations.run(bpy.context, 'DENSITY')
    with UVSession(bpy.context) as session:
        for state in session.states:
            for island in geometry.islands(state):
                assert abs(geometry.density(state, island, settings.width, settings.height, 1) - settings.density) < 0.01
    print('PASS world-space density')
    value = settings.density
    settings.density_unit = 'CM'
    assert abs(settings.density_display - value / 100) < 1e-5
    settings.density_display = 6.4
    assert abs(settings.density - 640) < 1e-3
    settings.density_unit = 'M'
    assert abs(settings.density_display - 640) < 1e-3
    print('PASS px/m and px/cm round-trip without unit drift')
    settings.width, settings.height = 2048, 1024
    operations.run(bpy.context, 'PACK')
    print('PASS rectangular texture packing')
    stable = snapshot(obj)
    try:
        with UVSession(bpy.context) as session:
            state = session.states[0]
            state.bm.edges[0].seam = not state.bm.edges[0].seam
            next(iter(state.targets)).loops[0][state.layer].uv = (99, 99)
            raise UVError('Injected failure')
    except UVError:
        pass
    assert snapshot(obj) == stable
    assert bpy.context.mode == 'OBJECT'
    print('PASS injected rollback')
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    for f in bm.faces:
        f.select_set(False)
    bmesh.update_edit_mesh(obj.data)
    try:
        operations.run(bpy.context, 'PACK')
        raise AssertionError('Empty selection was accepted')
    except UVError:
        pass
    assert bpy.context.mode == 'EDIT_MESH'
    bpy.ops.object.mode_set(mode='OBJECT')
    assert snapshot(obj) == stable
    print('PASS empty edit selection preservation')
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    layer = bm.loops.layers.uv.active
    bm.faces.ensure_lookup_table()
    for face in bm.faces:
        face.select_set(True)
    bm.faces[0].loops[0][layer].pin_uv = True
    bmesh.update_edit_mesh(obj.data)
    pinned = bm.faces[0].loops[0][layer].uv.copy()
    operations.run(bpy.context, 'PACK')
    assert bm.faces[0].loops[0][layer].pin_uv
    assert (bm.faces[0].loops[0][layer].uv - pinned).length < 1e-6
    bpy.ops.object.mode_set(mode='OBJECT')
    print('PASS constrained packing preserves pinned island')
    reset()
    a = cube('A')
    b = cube('B')
    a.select_set(True)
    b.location.x = 4
    operations.run(bpy.context, 'AUTO')
    assert set(bpy.context.selected_objects) == {a, b}
    assert bpy.context.active_object == b
    print('PASS multi-object auto UV and active/selection restoration')
    reset()
    obj = cube()
    obj.data.uv_layers.remove(obj.data.uv_layers.active)
    try:
        with UVSession(bpy.context, create=True):
            raise UVError('Rollback newly created map')
    except UVError:
        pass
    assert not obj.data.uv_layers
    print('PASS created-map rollback')
    settings.rotation = 'ANY'
    settings.effort = 'BALANCED'
    operations.run(bpy.context, 'AUTO')
    print('PASS default free-rotation balanced packing')
    shape_tests(settings)
    suite.unregister()
    suite.register()
    suite.unregister()
    assert not hasattr(bpy.types.Scene, 'mbt_uv')
    print('ALL UV SUITE TESTS PASSED')


def grid():
    reset()
    vertices = [(x, y, 0.15 * x * y) for y in range(3) for x in range(4)]
    faces = [(y * 4 + x, y * 4 + x + 1, (y + 1) * 4 + x + 1, (y + 1) * 4 + x)
             for y in range(2) for x in range(3)]
    mesh = bpy.data.meshes.new('UVGrid')
    mesh.from_pydata(vertices, [], faces)
    obj = bpy.data.objects.new('UVGrid', mesh)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    layer = mesh.uv_layers.new()
    for polygon in mesh.polygons:
        for index in polygon.loop_indices:
            co = mesh.vertices[mesh.loops[index].vertex_index].co
            layer.data[index].uv = (0.1 + co.x * 0.15 + co.y * 0.025, 0.1 + co.y * 0.2 + 0.02 * co.x * co.x)
    return obj


def shape_tests(settings):
    for action in ('QUADRIFY', 'RECTIFY', 'RELAX', 'CIRCLE', 'ORIENT', 'ROTATE', 'INPLACE', 'IMPROVE'):
        obj = grid()
        before = snapshot(obj)[:2]
        operations.run(bpy.context, action)
        assert snapshot(obj)[:2] == before
        with UVSession(bpy.context) as session:
            report = geometry.inspect(session, settings)
            assert report['degenerate'] == 0 and report['overlaps'] == 0, (action, report)
        print('PASS shape', action)
    obj = grid()
    bpy.context.tool_settings.mesh_select_mode = (False, True, False)
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    for face in bm.faces:
        face.select_set(False)
    for edge in bm.edges:
        edge.select_set(False)
    for edge in bm.edges:
        if all(abs(v.co.y) < 1e-6 for v in edge.verts):
            edge.select_set(True)
    # Select faces for target scoping, then retain only the bottom chain edges.
    for face in bm.faces:
        face.select = True
    for edge in bm.edges:
        edge.select = all(abs(v.co.y) < 1e-6 for v in edge.verts)
    for vert in bm.verts:
        vert.select = abs(vert.co.y) < 1e-6
    bmesh.update_edit_mesh(obj.data)
    operations.run(bpy.context, 'CHAIN')
    bpy.ops.object.mode_set(mode='OBJECT')
    print('PASS open edge-chain straightening')
    settings.pack_backend = 'RECT'
    settings.pack_scale = 'KEEP'
    settings.tile_start = 1011
    settings.tile_count = 2
    operations.run(bpy.context, 'PACK')
    assert min(data.uv.y for data in obj.data.uv_layers.active.data) >= 1
    print('PASS UDIM constrained layout with preserved density')
    from mathutils import Vector
    a = [Vector(p) for p in ((0, 0), (1, 0), (0, 1))]
    b = [Vector(p) for p in ((0.1, 0.1), (1.1, 0.1), (0.1, 1.1))]
    assert geometry.intersection_area(a, b) > 0.1
    # No remaining map/UI operations require edit mode.
    utilities = importlib.import_module(f'{ROOT.name}.features.uv_suite.utilities')
    settings.map_name = 'Duplicate'
    source = [tuple(data.uv) for data in obj.data.uv_layers.active.data]
    utilities.data_action(bpy.context, 'MAP_COPY')
    assert source == [tuple(data.uv) for data in obj.data.uv_layers.active.data]
    print('PASS UV map duplication')
    settings.tile_start, settings.tile_count = 1001, 1
    settings.pack_scale = 'FIT'
    advanced_tests(settings)


def advanced_tests(settings):
    obj = grid()
    operations.run(bpy.context, 'PIN')
    assert all(data.pin_uv for data in obj.data.uv_layers.active.data)
    operations.run(bpy.context, 'UNPIN')
    assert not any(data.pin_uv for data in obj.data.uv_layers.active.data)
    print('PASS lock/unlock island persistence')
    settings.density_unit = 'CM'
    settings.density_display = 5
    operations.run(bpy.context, 'DENSITY')
    with UVSession(bpy.context) as session:
        value = geometry.density(session.states[0], session.states[0].targets,
                                 settings.width, settings.height, 1)
        assert abs(value - 500) < 0.02
    print('PASS density application in px/cm')
    # Oversized fixed-density layout must fail without changing coordinates.
    for data in obj.data.uv_layers.active.data:
        data.uv *= 100
    stable = snapshot(obj)
    settings.pack_scale = 'KEEP'
    try:
        operations.run(bpy.context, 'PACK')
        raise AssertionError('Oversized fixed-density layout accepted')
    except UVError:
        pass
    assert snapshot(obj) == stable
    print('PASS impossible density fit rollback')
    settings.pack_scale = 'FIT'
    obj = grid()
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    for face in bm.faces:
        face.select_set(True)
    bm.faces[0].hide_set(True)
    bmesh.update_edit_mesh(obj.data)
    try:
        operations.run(bpy.context, 'QUADRIFY')
        raise AssertionError('Partly hidden island accepted')
    except UVError:
        pass
    bpy.ops.object.mode_set(mode='OBJECT')
    print('PASS hidden-island protection')
    # Preserve an existing exact stack across separate mesh objects.
    obj = grid()
    duplicate = bpy.data.objects.new('StackPartner', obj.data.copy())
    bpy.context.collection.objects.link(duplicate)
    duplicate.select_set(True)
    settings.preserve_stacks = True
    operations.run(bpy.context, 'PACK')
    assert all((a.uv - b.uv).length < 1e-6 for a, b in zip(
        obj.data.uv_layers.active.data, duplicate.data.uv_layers.active.data))
    print('PASS exact existing stack preservation')
    settings.preserve_stacks = False
    reset()
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=6)
    sphere = bpy.context.object
    for edge in sphere.data.edges:
        edge.use_seam = False
    settings.seams = 'EXTEND'
    settings.auto_shape = False
    operations.run(bpy.context, 'AUTO')
    assert any(edge.use_seam for edge in sphere.data.edges)
    print('PASS closed-surface automatic topology cuts')
    # UI layout contract: both resolution props must inherit identical flags.
    class Layout:
        def __init__(self, records):
            self.records = records
            self.use_property_split = True
            self.use_property_decorate = True

        def row(self, **kwargs):
            return Layout(self.records)

        def box(self):
            return Layout(self.records)

        def prop(self, owner, name, **kwargs):
            self.records.append((name, self.use_property_split, self.use_property_decorate))

        def operator(self, *args, **kwargs):
            records = self.records
            # Query real registered RNA: a recording-only mock previously let
            # nonexistent enum identifiers pass even though Blender draw crashes.
            action_values = {item.identifier for item in
                             bpy.ops.mbt.uv_action.get_rna_type().properties['action'].enum_items}

            class Button:
                def __setattr__(self, name, value):
                    if name == 'action':
                        assert value in action_values, f'Unregistered UV button action: {value}'
                        records.append(('ACTION', value))

            records.append(('OPERATOR', args[0]))
            return Button()

        def label(self, **kwargs):
            pass

    records = []
    settings.show_auto = True
    settings.show_shape = True
    settings.show_layout = True
    settings.show_diagnostics = True
    settings.show_maps = True
    context_3d = types.SimpleNamespace(scene=bpy.context.scene, area=types.SimpleNamespace(type='VIEW_3D'))
    suite.draw(Layout(records), context_3d)
    assert ('ACTION', 'SEAMS') in records
    width = next(item[1:] for item in records if item[0] == 'width')
    height = next(item[1:] for item in records if item[0] == 'height')
    assert width == height == (False, False)
    forbidden = {'STRAIGHTEN', 'QUADRIFY', 'RECTIFY', 'RELAX', 'PACK', 'DENSITY', 'MAP_NEW', 'SELECT_OVERLAP'}
    assert not any(item[0] == 'ACTION' and item[1] in forbidden for item in records)
    assert ('OPERATOR', 'mbt.pack_uvs') not in records
    records = []
    context_uv = types.SimpleNamespace(scene=bpy.context.scene, area=types.SimpleNamespace(type='IMAGE_EDITOR'))
    suite.draw(Layout(records), context_uv)
    assert all(('ACTION', action) in records for action in forbidden - {'PACK'})
    assert ('OPERATOR', 'mbt.pack_uvs') in records
    print('PASS consistent resolution widget layout contract')
    print('PASS UV-only tools absent in 3D Viewport and present in UV Editor')
    obj = grid()
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    for face in bm.faces:
        face.select_set(True)
    layer = bm.loops.layers.uv.active
    for face in bm.faces:
        for loop in face.loops:
            loop[layer].uv.x += 4
    bmesh.update_edit_mesh(obj.data)
    operations.run(bpy.context, 'SELECT_OUTSIDE')
    assert all(face.select for face in bm.faces)
    operations.run(bpy.context, 'SELECT_ISLANDS')
    assert all(face.select for face in bm.faces)
    bpy.ops.object.mode_set(mode='OBJECT')
    print('PASS diagnostic selection commits intentionally')
    # Check all operator IDs (including legacy wrappers) through registration.
    compatibility = importlib.import_module(f'{ROOT.name}.features.uv_tools')
    from_registry = compatibility.classes
    for cls in from_registry:
        bpy.utils.register_class(cls)
    assert bpy.ops.mbt.uv_action(action='PIN') == {'FINISHED'}
    assert bpy.ops.mbt.uv_action(action='UNPIN') == {'FINISHED'}
    assert bpy.ops.mbt.uv_action(action='SEAMS') == {'FINISHED'}
    assert bpy.ops.mbt.straighten_uvs() == {'FINISHED'}
    for cls in reversed(from_registry):
        bpy.utils.unregister_class(cls)
    print('PASS operator and legacy straighten integration')
    for action in ('DISTRIBUTE_U', 'DISTRIBUTE_V', 'MATCH_SIZE', 'FIT', 'MATCH_DENSITY',
                   'SEAMS_UV', 'CLEAR_SEAMS'):
        obj = grid()
        operations.run(bpy.context, action)
        print('PASS utility', action)
    # Bad all-quad assumptions must fail safely on triangulated topology.
    obj = grid()
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bmesh.update_edit_mesh(obj.data)
    bpy.ops.object.mode_set(mode='OBJECT')
    stable = snapshot(obj)
    try:
        operations.run(bpy.context, 'QUADRIFY')
        raise AssertionError('Triangulated island accepted by quadrify')
    except UVError:
        pass
    assert snapshot(obj) == stable
    print('PASS unsupported shape rollback')
    seam_tests(settings)


def seam_tests(settings):
    from math import cos, sin, pi
    # Closed cylindrical side grid: a partly marked circumferential ring with
    # low-angle gaps must close, not turn down a diagonal toward a boundary.
    reset()
    count = 12
    mesh = bpy.data.meshes.new('SeamRing')
    mesh.from_pydata([(cos(2 * pi * i / count), sin(2 * pi * i / count), z)
                     for z in (0, 1, 2) for i in range(count)], [],
                    [(z * count + i, z * count + (i + 1) % count,
                      (z + 1) * count + (i + 1) % count, (z + 1) * count + i)
                     for z in range(2) for i in range(count)])
    obj = bpy.data.objects.new('SeamRing', mesh)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    mesh.uv_layers.new()
    for edge in mesh.edges:
        a, b = edge.vertices
        edge.use_seam = (count <= a < 2 * count and count <= b < 2 * count and
                         set((a % count, b % count)) != {3, 4} and
                         set((a % count, b % count)) != {4, 5})
    result = operations.run(bpy.context, 'REPAIR_SEAMS')
    ring = [e for e in mesh.edges if all(count <= v < 2 * count for v in e.vertices)]
    assert all(e.use_seam for e in ring), result
    assert sum(e.use_seam for e in mesh.edges) == count, result
    stable = snapshot(obj)
    operations.run(bpy.context, 'REPAIR_SEAMS')
    assert snapshot(obj) == stable
    print('PASS contour gap closes ring without spurious branches; idempotent')
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(mesh)
    for face in bm.faces:
        face.select_set(True)
    # Triangulate after opening the same two-edge gap. Geometry scoring must
    # continue the contour instead of relying on the quad-only opposite rule.
    for edge in bm.edges:
        if all(abs(v.co.z - 1) < 1e-5 for v in edge.verts):
            if any(abs(v.co.x + 0.5) < 1e-5 and abs(v.co.y - 0.8660254) < 1e-5 for v in edge.verts):
                edge.seam = False
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bmesh.update_edit_mesh(mesh)
    bpy.ops.object.mode_set(mode='OBJECT')
    message = operations.run(bpy.context, 'REPAIR_SEAMS')
    ring = [e for e in mesh.edges if all(abs(mesh.vertices[v].co.z - 1) < 1e-5 for v in e.vertices)]
    assert all(e.use_seam for e in ring), message
    assert sum(e.use_seam for e in mesh.edges) == count, message
    print('PASS triangulated contour completion rejects diagonal detours')
    # Scope protection: an endpoint next to a hidden face stays unresolved/untouched.
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(mesh)
    for face in bm.faces:
        face.select_set(True)
    ring_bm = [e for e in bm.edges if all(abs(v.co.z - 1) < 1e-5 for v in e.verts)]
    ring_bm[0].seam = False
    ring_bm[0].link_faces[0].hide_set(True)
    bmesh.update_edit_mesh(mesh)
    before = {e: e.seam for e in bm.edges}
    try:
        operations.run(bpy.context, 'REPAIR_SEAMS')
        raise AssertionError('Blocked contour committed')
    except UVError:
        pass
    assert all(e.seam == seam for e, seam in before.items())
    bpy.ops.object.mode_set(mode='OBJECT')
    print('PASS seam repair respects hidden geometry and selection boundaries')
    # Strict validator catches bridge/slit edges even without degree-one ends.
    seams = importlib.import_module(f'{ROOT.name}.features.uv_suite.seams')
    with UVSession(bpy.context) as session:
        state = session.states[0]
        for face in state.bm.faces:
            face.hide_set(False)
        state.targets = set(state.bm.faces)
        for edge in state.bm.edges:
            edge.seam = False
        middle = [e for e in state.bm.edges if all(abs(v.co.z - 1) < 1e-5 for v in e.verts)]
        middle[0].seam = True
        try:
            seams.validate(state)
            raise AssertionError('Interior slit accepted')
        except UVError:
            pass
        for edge in state.bm.edges:
            edge.seam = all(abs(v.co.z - 1) < 1e-5 for v in edge.verts)
        bridge = next(e for e in state.bm.edges if
                      abs(e.verts[0].co.z - e.verts[1].co.z) > 0.5)
        bridge.seam = True
        try:
            seams.validate(state)
            raise AssertionError('Nonseparating boundary-to-loop bridge accepted')
        except UVError:
            pass
    print('PASS strict interior slit and nonseparating bridge validation')
    reset()
    obj = cube('RegisteredRegionSeams')
    settings.seams = 'REBUILD'
    assert bpy.ops.mbt.uv_action(action='SEAMS') == {'FINISHED'}
    stable = snapshot(obj)
    assert bpy.ops.mbt.uv_action(action='SEAMS') == {'FINISHED'}
    assert snapshot(obj) == stable
    with UVSession(bpy.context) as session:
        for state in session.states:
            seams.validate(state)
    settings.seams = 'EXTEND'
    print('PASS registered Smart Seams closed surface and repeat execution')
    # An L-shaped material patch has concave and right-angle contour turns. No
    # edge selection is needed, and every interface must be extracted exactly.
    reset()
    mesh = bpy.data.meshes.new('TurningRegion')
    size = 6
    mesh.from_pydata([(x, y, 0) for y in range(size + 1) for x in range(size + 1)], [],
                     [(y * (size + 1) + x, y * (size + 1) + x + 1,
                       (y + 1) * (size + 1) + x + 1, (y + 1) * (size + 1) + x)
                      for y in range(size) for x in range(size)])
    obj = bpy.data.objects.new('TurningRegion', mesh)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    for face in mesh.polygons:
        x, y = face.index % size, face.index // size
        face.material_index = int((x == 2 and 1 <= y <= 4) or (y == 1 and 2 <= x <= 4))
    settings.material_seams = True
    assert bpy.ops.mbt.uv_action(action='SEAMS') == {'FINISHED'}
    with UVSession(bpy.context) as session:
        state = session.states[0]
        seams.validate(state)
        assert all(e.seam == (e.link_faces[0].material_index != e.link_faces[1].material_index)
                   for e in state.bm.edges if len(e.link_faces) == 2)
    stable = snapshot(obj)
    assert bpy.ops.mbt.uv_action(action='SEAMS') == {'FINISHED'}
    assert snapshot(obj) == stable
    settings.material_seams = False
    print('PASS automatic concave turning contour without edge selection')
    seam_simplification_tests(settings)
    # A nonmanifold adjacency must cancel through the registered UI operator.
    reset()
    mesh = bpy.data.meshes.new('NonmanifoldRegions')
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1)], [],
                     [(0, 1, 2), (1, 0, 3), (0, 1, 4)])
    obj = bpy.data.objects.new('NonmanifoldRegions', mesh)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    stable = snapshot(obj)
    assert bpy.ops.mbt.uv_action(action='SEAMS') == {'CANCELLED'}
    assert snapshot(obj) == stable
    print('PASS registered nonmanifold cancellation and created UV-map rollback')
    # Unwrap validity must not inherit the stricter shape anisotropy threshold.
    obj = grid()
    settings.max_stretch = 1.01
    message = operations.run(bpy.context, 'UNWRAP')
    assert 'chosen from' in message
    settings.max_stretch = 8
    print('PASS unwrap quality independent of shape threshold and chosen-method summary')
    # Failed native calls produce method-labelled reasons and rollback.
    stable = snapshot(obj)
    original_native = operations.native

    def fail(*args, **kwargs):
        raise RuntimeError('Injected native unwrap failure')

    operations.native = fail
    try:
        try:
            operations.run(bpy.context, 'UNWRAP')
            raise AssertionError('Failed unwrap accepted')
        except UVError as error:
            assert 'UVs restored' in str(error) and 'ANGLE_BASED' in str(error)
            assert 'Injected native unwrap failure' in settings.details
    finally:
        operations.native = original_native
    assert snapshot(obj) == stable
    print('PASS unwrap failure diagnostics and rollback')


def seam_simplification_tests(settings):
    """Geometric proxies for the screenshot corrections, not the original mesh."""
    from math import cos, sin, radians
    seams = importlib.import_module(f'{ROOT.name}.features.uv_suite.seams')

    def profile_mesh(profile, scale=1, triangulate=False, reverse=False):
        reset()
        count = len(profile)
        vertices = [(x * scale, y * scale, z * scale)
                    for z in (0, 4) for x, y in profile]
        faces = [(i, i + 1, count + i + 1, count + i) for i in range(count - 1)]
        if reverse:
            faces.reverse()
        mesh = bpy.data.meshes.new('SeamSimplification')
        mesh.from_pydata(vertices, [], faces)
        obj = bpy.data.objects.new('SeamSimplification', mesh)
        bpy.context.collection.objects.link(obj)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        if triangulate:
            bm = bmesh.new()
            bm.from_mesh(mesh)
            bmesh.ops.triangulate(bm, faces=list(bm.faces))
            bm.to_mesh(mesh)
            bm.free()
        return obj

    def seam_keys(obj, scale):
        return {tuple(sorted(tuple(round(c / scale, 5) for c in obj.data.vertices[v].co)
                             for v in edge.vertices)) for edge in obj.data.edges if edge.use_seam}

    original_mode = settings.seams
    settings.seams = 'REBUILD'
    # A 90-degree bend with a narrow 45-degree bevel must not yield a detached
    # strip between two parallel seams. Compare geometry, not edge indices.
    profile = [(-2, 0), (0, 0), (0.08, 0.08), (0.08, 2)]
    baseline = None
    for scale, triangulate, reverse in ((1, False, False), (10, False, True),
                                       (0.1, True, True)):
        obj = profile_mesh(profile, scale, triangulate, reverse)
        assert bpy.ops.mbt.uv_action(action='SEAMS') == {'FINISHED'}
        keys = seam_keys(obj, scale)
        assert len(keys) <= 1, ('Redundant parallel bevel cuts', keys)
        if baseline is None:
            baseline = keys
        assert keys == baseline, ('Triangulation/order/scale changed seam placement', keys, baseline)
        with UVSession(bpy.context) as session:
            seams.validate(session.states[0])
        stable = snapshot(obj)
        assert bpy.ops.mbt.uv_action(action='SEAMS') == {'FINISHED'}
        assert snapshot(obj) == stable
    print('PASS bevel strip absorption; scale, face-order, triangulation and repeat stability')
    # Smooth 120-degree cylindrical patch: normal spread alone must not cut it
    # into numerous strips. It is open on its actual mesh boundaries.
    profile = [(cos(radians(i * 15)), sin(radians(i * 15))) for i in range(9)]
    obj = profile_mesh(profile)
    assert bpy.ops.mbt.uv_action(action='SEAMS') == {'FINISHED'}
    assert sum(e.use_seam for e in obj.data.edges) <= 1
    print('PASS coherent curved transition avoids normal-spread oversegmentation')
    # Existing valid boundary remains protected in Extend, even if simplification
    # would remove it in Rebuild.
    obj = profile_mesh([(-2, 0), (0, 0), (0.08, 0.08), (0.08, 2)])
    for edge in obj.data.edges:
        a, b = (obj.data.vertices[v].co for v in edge.vertices)
        edge.use_seam = abs(a.x) < 1e-6 and abs(b.x) < 1e-6
    protected = seam_keys(obj, 1)
    assert protected
    settings.seams = 'EXTEND'
    assert bpy.ops.mbt.uv_action(action='SEAMS') == {'FINISHED'}
    assert protected <= seam_keys(obj, 1)
    print('PASS simplification preserves artist seams in Extend')
    # A planar triangle fan is topology, not seam evidence.
    reset()
    mesh = bpy.data.meshes.new('FanWithoutSpokes')
    mesh.from_pydata([(0, 0, 0), (-2, -1, 0), (2, -1, 0), (2, 1, 0), (-2, 1, 0)], [],
                     [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 1)])
    obj = bpy.data.objects.new('FanWithoutSpokes', mesh)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    settings.seams = 'REBUILD'
    assert bpy.ops.mbt.uv_action(action='SEAMS') == {'FINISHED'}
    assert not any(e.use_seam for e in mesh.edges)
    with UVSession(bpy.context) as session:
        state = session.states[0]
        # Artificial initial labels exercise whole-interface cleanup independently
        # of seeding. Protecting even one shared edge blocks the entire merge.
        faces = sorted(state.targets, key=lambda f: f.index)
        initial = {faces[0]: faces[:2], faces[2]: faces[2:]}
        writable = {e for e in state.bm.edges if seams.eligible(state, e)}
        cuts, patches, merges = seams.simplify_regions(initial, writable, set(), settings, radians(66))
        assert not cuts and patches == 1 and merges == 1
        shared = next(e for e in writable if
                      (e.link_faces[0] in faces[:2]) != (e.link_faces[1] in faces[:2]))
        cuts, patches, merges = seams.simplify_regions(initial, writable, {shared}, settings, radians(66))
        assert shared in cuts and patches == 2 and merges == 0
    settings.seams = original_mode
    print('PASS planar triangle fan has no generated spoke seams')
    print('PASS whole-interface cleanup and protected-interface rejection')


if __name__ == '__main__':
    import tempfile
    import traceback
    log = Path(tempfile.gettempdir()) / 'mbt_uv_integration.log'
    with log.open('w', encoding='utf-8', buffering=1) as output:
        import faulthandler
        faulthandler.dump_traceback_later(20, file=output)
        old = sys.stdout
        sys.stdout = output
        try:
            main()
        except Exception:
            traceback.print_exc(file=output)
            raise
        finally:
            faulthandler.cancel_dump_traceback_later()
            sys.stdout = old