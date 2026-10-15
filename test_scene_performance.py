"""Integration tests. Run ONLY in a disposable --background --factory-startup Blender."""

import contextlib
import importlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace

import bpy


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
feature = importlib.import_module(f'{ROOT.name}.features.scene_stats')
rt, ops, ui = feature.runtime, feature.ops, feature.ui
collectors = importlib.import_module(f'{ROOT.name}.features.scene_performance.collectors')


def lifecycle(function):
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        function()
    assert 'Failed' not in output.getvalue() and 'Traceback' not in output.getvalue(), output.getvalue()


def scan():
    assert bpy.ops.mbt.stats_refresh() == {'FINISHED'}
    assert rt.JOB is None and rt.SNAPSHOT['complete']
    return rt.SNAPSHOT['results']


def mesh(name, vertices, faces):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    return obj


def run():
    assert bpy.app.background, 'Tests require a disposable background process'
    for cycle in range(2):
        lifecycle(addon.register)
        assert hasattr(bpy.types.WindowManager, 'mbt_stats')
        assert all(cls.is_registered for cls in feature.classes)
        if cycle == 0:
            lifecycle(addon.unregister)
            assert not hasattr(bpy.types.WindowManager, 'mbt_stats')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    quad = mesh('Quad', [(0,0,0),(1,0,0),(1,1,0),(0,1,0)], [(0,1,2,3)])
    ngon = mesh('Ngon', [(0,0,0),(2,0,0),(3,1,0),(1,2,0),(-1,1,0)], [(0,1,2,3,4)])
    empty = mesh('EmptyMesh', [], [])
    curve_data = bpy.data.curves.new('Curve', 'CURVE')
    curve_data.dimensions = '3D'
    curve_data.bevel_depth = 0.1
    spline = curve_data.splines.new('POLY')
    spline.points.add(1)
    spline.points[0].co = (0,0,0,1)
    spline.points[1].co = (0,0,2,1)
    curve = bpy.data.objects.new('Curve', curve_data)
    bpy.context.collection.objects.link(curve)
    disabled = quad.modifiers.new('Disabled', 'BEVEL')
    disabled.show_viewport = False
    subdivision = quad.modifiers.new('Subdivision', 'SUBSURF')
    subdivision.levels = 1
    bpy.context.view_layer.update()
    before = [(m.name, m.show_viewport, m.show_render) for m in quad.modifiers]
    results = scan()
    uid = str(quad.session_uid)
    assert results[uid]['tris'] == 8, results[uid]
    assert results[str(ngon.session_uid)]['tris'] == 3
    assert results[str(empty.session_uid)]['tris'] == 0
    assert results[str(curve.session_uid)]['tris'] > 0
    assert results[str(ngon.session_uid)]['ms'] is None
    assert results[uid]['mods'][0]['ms'] is None
    assert results[uid]['mods'][1]['ms'] is not None
    assert before == [(m.name, m.show_viewport, m.show_render) for m in quad.modifiers]
    assert not rt.is_stale(bpy.context)
    print('PASS tessellation / evaluated subdivision / curves / empty meshes / native timings / visibility')

    # Conversion failure always clears the temporary mesh.
    cleared = []
    class Failing:
        type = 'MESH'
        def to_mesh(self):
            raise RuntimeError('injected conversion failure')
        def to_mesh_clear(self):
            cleared.append(True)
    try:
        collectors.evaluated_tris(Failing())
    except RuntimeError:
        pass
    assert cleared == [True]

    state = rt.state(bpy.context)
    state.index = next(i for i, row in enumerate(state.rows) if row.uid == uid)
    quad.name = 'RenamedQuad'
    bpy.context.view_layer.update()
    assert state.rows[state.index].obj == quad and state.rows[state.index].uid == uid
    assert rt.is_stale(bpy.context)
    scan()
    assert state.rows[state.index].uid == uid
    assert state.rows[state.index].name == 'RenamedQuad'
    assert bpy.ops.mbt.stats_baseline() == {'FINISHED'}
    subdivision.levels = 2
    bpy.context.view_layer.update()
    assert rt.delta(bpy.context, uid) is None
    scan()
    assert rt.delta(bpy.context, uid)['tris'] == 24
    state.search = 'renamed'
    model = rt.presentation(bpy.context)
    assert len(model['visible']) == 1 and model['tris'] == 32
    assert rt.presentation(bpy.context) is model
    state.search = ''
    state.sort = 'NAME'
    for descending in (False, True):
        state.descending = descending
        ranks = rt.presentation(bpy.context)['order']
        names = [row.name.casefold() for i, row in sorted(enumerate(state.rows), key=lambda pair: ranks[pair[0]])]
        assert names == sorted(names, reverse=descending)
    print('PASS rename identity / freshness / baseline deltas / search / cached sorting / cleanup on failure')

    # No list limit, and filtering totals do not change the captured totals.
    for i in range(150):
        obj = bpy.data.objects.new(f'InstanceMesh{i:03}', ngon.data)
        bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.update()
    start = time.perf_counter()
    scan()
    assert len(state.rows) == 154
    print(f'PASS 154-object scan: {time.perf_counter()-start:.3f}s')
    bpy.context.scene.mbt.stats_tri_budget = 10
    state.filter = 'BUDGET'
    assert rt.presentation(bpy.context)['visible'] == {
        i for i, row in enumerate(state.rows) if row.tris > 10 or row.ms > bpy.context.scene.mbt.stats_ms_budget}
    state.filter = 'ALL'

    # Explicit selected scope, geometry-only mode and comparison compatibility.
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    quad.select_set(True)
    bpy.context.view_layer.objects.active = quad
    bpy.context.scene.mbt.stats_scope = 'SELECTED'
    bpy.context.scene.mbt.stats_timings = False
    assert not rt.matches(bpy.context)
    results = scan()
    assert list(results) == [uid] and results[uid]['ms'] is None
    assert rt.comparison(bpy.context)
    bpy.context.scene.mbt.stats_scope = 'VISIBLE'
    bpy.context.scene.mbt.stats_timings = True
    scan()

    parent = bpy.data.collections.new('ScopeParent')
    child = bpy.data.collections.new('ScopeChild')
    bpy.context.scene.collection.children.link(parent)
    parent.children.link(child)
    parent.objects.link(ngon)
    child.objects.link(empty)
    bpy.context.view_layer.update()
    original_collection = bpy.context.view_layer.active_layer_collection
    bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children[parent.name]
    bpy.context.scene.mbt.stats_scope = 'COLLECTION'
    bpy.context.scene.mbt.stats_recursive = False
    assert set(scan()) == {str(ngon.session_uid)}
    bpy.context.scene.mbt.stats_recursive = True
    assert set(scan()) == {str(ngon.session_uid), str(empty.session_uid)}
    bpy.context.view_layer.active_layer_collection = original_collection
    bpy.context.scene.mbt.stats_scope = 'VISIBLE'
    scan()

    # Exercise the timer callback with a real View3D override, without touching a working UI.
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    with bpy.context.temp_override(area=area):
        rt.begin(bpy.context)
        while rt.tick() is not None:
            pass
        assert rt.SNAPSHOT['complete'] and not state.running
        state.index = next(i for i, row in enumerate(state.rows) if row.uid == uid)
        assert bpy.ops.mbt.stats_navigate(action='SELECT') == {'FINISHED'}
        assert bpy.context.view_layer.objects.active == quad
        assert bpy.ops.mbt.stats_navigate(action='FRAME') == {'FINISHED'}
        assert bpy.ops.mbt.stats_navigate(action='PROPERTIES') == {'FINISHED'}

        # Validate every draw branch, property reference, icon, and list filter without evaluation.
        icons = bpy.types.UILayout.bl_rna.functions['label'].parameters['icon'].enum_items
        class Layout:
            def row(self, **kwargs): return self
            def column(self, **kwargs): return self
            def box(self): return self
            def split(self, **kwargs): return self
            def label(self, **kwargs):
                if 'icon' in kwargs: assert kwargs['icon'] in icons, kwargs['icon']
            def prop(self, data, name, **kwargs):
                assert hasattr(data, name), name
                if 'icon' in kwargs: assert kwargs['icon'] in icons, kwargs['icon']
            def operator(self, name, **kwargs):
                if 'icon' in kwargs: assert kwargs['icon'] in icons, kwargs['icon']
                return SimpleNamespace()
            def progress(self, **kwargs): pass
            def template_list(self, *args, **kwargs): pass
        original_collect = rt.collect_object
        rt.collect_object = lambda *args: (_ for _ in ()).throw(AssertionError('Drawing evaluated geometry'))
        try:
            bpy.context.scene.mbt.stats_options = True
            ui.draw(Layout(), bpy.context)
            for row in state.rows:
                ui.MBT_UL_scene_performance.draw_item(None, bpy.context, Layout(), state,
                                                      row, 0, state, 'index')
            flags, order = ui.MBT_UL_scene_performance.filter_items(
                SimpleNamespace(bitflag_filter_item=1), bpy.context, state, 'rows')
            assert len(flags) == len(order) == len(state.rows)
            rt.begin(bpy.context)
            ui.draw(Layout(), bpy.context)
            rt.cancel()
        finally:
            rt.collect_object = original_collect
    scan()
    print('PASS recursive collections / timer callback / selection / framing / Properties / read-only drawing')

    # Preserve partial results, reject baseline and release timer on cancel.
    rt.begin(bpy.context)
    assert rt.step(bpy.context, budget=0)
    assert len(state.rows) == 1
    bpy.app.timers.register(rt.tick, first_interval=10)
    assert bpy.ops.mbt.stats_cancel() == {'FINISHED'}
    assert not rt.SNAPSHOT['complete'] and not state.running
    assert not bpy.app.timers.is_registered(rt.tick)
    assert not ops.MBT_OT_stats_baseline.poll(bpy.context)
    print('PASS scopes / geometry-only / budgets / partial cancellation / timer cleanup')

    # Recoverable per-object errors, deletion while queued and scene change cancellation.
    real_collect = rt.collect_object
    def fail(*args):
        raise RuntimeError('injected collection failure')
    rt.collect_object = fail
    try:
        scan()
        assert all(row.error for row in state.rows)
    finally:
        rt.collect_object = real_collect
    rt.begin(bpy.context)
    deleted = rt.JOB['objects'][0]
    bpy.data.objects.remove(deleted, do_unlink=True)
    while rt.step(bpy.context):
        pass
    assert any(row.error for row in state.rows)
    rt.begin(bpy.context)
    bpy.context.scene.frame_set(2)
    assert not rt.step(bpy.context)
    assert not rt.SNAPSHOT['complete']
    scan()
    saved_scene = bpy.context.window.scene
    other = bpy.data.scenes.new('OtherScene')
    bpy.context.window.scene = other
    assert not rt.matches(bpy.context)
    bpy.context.window.scene = saved_scene
    bpy.data.scenes.remove(other)
    scan()
    print('PASS per-object failures / deletion / frame cancellation / scene isolation')

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'snapshot.json'
        ops.export_snapshot(bpy.context, path, 'JSON')
        exported = json.loads(path.read_text(encoding='utf-8'))
        assert exported['metadata']['complete'] and len(exported['objects']) == len(state.rows)
        ops.export_snapshot(bpy.context, Path(directory) / 'snapshot.csv', 'CSV')
        # File browser lacks originating viewport scope; token still binds to captured data.
        token = str(rt.SNAPSHOT['captured_at'])
        ops.export_snapshot(bpy.context, path, 'JSON', capture_token=token)
    rt.reset()
    assert rt.SNAPSHOT is None and rt.BASELINE is None and len(state.rows) == 0
    rt.begin(bpy.context)
    bpy.app.timers.register(rt.tick, first_interval=10)
    lifecycle(addon.unregister)
    assert rt.JOB is None and not bpy.app.timers.is_registered(rt.tick)
    assert not hasattr(bpy.types.WindowManager, 'mbt_stats')
    assert all(callback not in handlers for handlers, callback in rt.HANDLERS)
    print('ALL SCENE PERFORMANCE TESTS PASSED')


if __name__ == '__main__':
    run()