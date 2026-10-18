"""Editor-session integration tests; disposable --background --factory-startup ONLY."""
import contextlib
import importlib
import io
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
rt = importlib.import_module(f'{ROOT.name}.features.scene_performance.runtime')
ui = importlib.import_module(f'{ROOT.name}.features.scene_performance.ui')
collectors = importlib.import_module(f'{ROOT.name}.features.scene_performance.collectors')


def lifecycle(function):
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        function()
    assert 'Traceback' not in output.getvalue() and 'Failed' not in output.getvalue(), output.getvalue()


def scan(context):
    rt.start_scan(context)
    while rt.scan_step(context):
        pass
    return rt.session(context).snapshot['results']


def mesh(name, vertices, faces):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    return obj


def run():
    assert bpy.app.background
    for _ in range(2):
        lifecycle(addon.register)
        assert hasattr(bpy.types.WindowManager, 'mbt_stats_sessions')
        lifecycle(addon.unregister)
        assert not hasattr(bpy.types.WindowManager, 'mbt_stats_sessions')
    lifecycle(addon.register)
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(area=area, region=region):
        context = bpy.context
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        quad = mesh('Quad', [(0,0,0),(1,0,0),(1,1,0),(0,1,0)], [(0,1,2,3)])
        ngon = mesh('Ngon', [(0,0,0),(2,0,0),(3,1,0),(1,2,0),(-1,1,0)], [(0,1,2,3,4)])
        empty = mesh('Empty', [], [])
        disabled = quad.modifiers.new('Disabled', 'BEVEL')
        disabled.show_viewport = False
        subdivision = quad.modifiers.new('Subdivision', 'SUBSURF')
        subdivision.levels = 1
        bpy.context.view_layer.update()
        results = scan(context)
        s, state = rt.session(context), rt.state(context)
        uid = str(quad.session_uid)
        assert results[uid]['tris'] == 8
        assert results[str(ngon.session_uid)]['tris'] == 3
        assert results[str(empty.session_uid)]['tris'] == 0
        assert results[uid]['mods'][0]['ms'] is None
        assert results[uid]['mods'][1]['ms'] is not None
        assert not disabled.show_viewport and subdivision.show_viewport
        assert s.requested == s.committed
        assert state.auto
        print('PASS evaluated triangles / native timings / disabled modifiers / empty mesh / lifecycle')

        cleared = []
        class Failing:
            type = 'MESH'
            def to_mesh(self): raise RuntimeError('injected')
            def to_mesh_clear(self): cleared.append(True)
        try:
            collectors.evaluated_tris(Failing())
            assert False
        except RuntimeError:
            pass
        assert cleared == [True]

        # Selection is independent of manual/dirty/scanning state and index mutations.
        state.auto = False
        quad.select_set(True)
        ngon.select_set(True)
        context.view_layer.objects.active = quad
        rt.sync_selection(context)
        assert state.rows[state.index].obj == quad and ngon.select_get()
        context.view_layer.objects.active = ngon
        rt.mark_dirty(s, 'Test stale selection')
        rt.sync_selection(context)
        assert state.rows[state.index].obj == ngon and quad.select_get()
        state.index = s.row_indices[uid]
        assert context.view_layer.objects.active == ngon  # No RNA selection callback.
        rt.reconcile_list_input(context, s)
        assert s.selection_command == (uid, False)
        s.selection_command = None
        rt.queue_selection(context, uid)
        rt.apply_selection(context, s)
        assert context.view_layer.objects.active == quad and not ngon.select_get()
        rt.queue_selection(context, str(ngon.session_uid), extend=True)
        rt.apply_selection(context, s)
        assert ngon.select_get() and quad.select_get()
        quad.hide_select = True
        rt.queue_selection(context, uid)
        assert not rt.apply_selection(context, s)
        assert context.view_layer.objects.active == ngon
        quad.hide_select = False
        for obj in context.view_layer.objects: obj.select_set(False)
        rt.sync_selection(context)
        assert state.index == -1
        print('PASS viewport-to-list / explicit activation / multi-select / stale manual selection / locks / deselect all')

        for criterion, attr in (('TRIS', 'tris'), ('PERF', 'ms')):
            state.sort = criterion
            model = rt.presentation(context)
            assert rt.presentation(context) is model
            values = [getattr(state.rows[i], attr) for i in model['indices']]
            measured = [v for v in values if v >= 0]
            assert measured == sorted(measured, reverse=True)
            assert values[:len(measured)] == measured

        # Reproduce the old cancellation loop: soft changes must NOT prevent commits.
        for index in range(80):
            obj = bpy.data.objects.new(f'Extra {index}', ngon.data)
            context.collection.objects.link(obj)
        context.view_layer.update()
        rt.start_scan(context, automatic=True)
        original_job = s.job
        original_snapshot = s.snapshot
        while s.job:
            rt.request_refresh(context, 'Soft change between batches')
            rt.scan_step(context, budget=0, limit=1)
            if s.job:
                assert s.job is original_job and s.snapshot is original_snapshot
        assert s.snapshot is not original_snapshot
        assert s.requested > s.committed
        assert len(state.rows) == 83
        scan(context)
        assert s.requested == s.committed
        print('PASS legacy starvation regression / multi-batch atomic commit / follow-up revision / shared meshes')

        # Idle reconciliation never converts meshes; maximum wait prevents debounce starvation.
        state.auto = True
        area.spaces.active.show_region_ui = True
        real_collect = rt.collect_object
        rt.collect_object = lambda *args: (_ for _ in ()).throw(AssertionError('Idle recollected mesh'))
        try:
            for _ in range(5):
                assert not rt.reconcile(context, s)
        finally:
            rt.collect_object = real_collect
        rt.mark_dirty(s, 'Continuous activity')
        s.first_dirty = time.monotonic() - rt.MAX_WAIT - 1
        s.last_dirty = time.monotonic()
        assert rt.reconcile(context, s) and s.job is not None
        rt.cancel_scan(context)

        # Scope/frame changes are hard boundaries; soft changes never are.
        rt.start_scan(context, automatic=True)
        context.scene.frame_set(2)
        assert not rt.scan_step(context) and s.job is None and s.snapshot is None
        quad.select_set(True)
        context.scene.mbt.stats_scope = 'SELECTED'
        result = scan(context)
        assert set(result) == {uid}
        context.scene.mbt.stats_scope = 'VISIBLE'
        scan(context)
        rt.start_scan(context)
        rt.scan_step(context, budget=0, limit=1)
        rt.cancel_scan(context, partial=True)
        assert not s.snapshot['complete'] and len(state.rows) == 1
        print('PASS idle no evaluation / maximum debounce / hard rebind / selected scope / explicit partial cancel')

        real_collect = rt.collect_object
        rt.collect_object = lambda *args: (_ for _ in ()).throw(RuntimeError('Injected collection failure'))
        try:
            scan(context)
            assert all(row.error for row in state.rows)
        finally:
            rt.collect_object = real_collect
        scan(context)
        # Per-editor storage, not the global WindowManager row list.
        other = next(a for a in context.screen.areas if a != area)
        old_type = other.type
        other.type = 'VIEW_3D'
        other_region = next(r for r in other.regions if r.type == 'WINDOW')
        with context.temp_override(area=other, region=other_region):
            second = rt.session(bpy.context)
            second_ui = rt.state(bpy.context)
            assert second.key != s.key and second_ui.name != state.name
            scan(bpy.context)
            second_ui.sort = 'PERF'
        assert len(state.rows) == 83
        other.type = old_type
        rt.controller()
        assert second.key not in rt.SESSIONS
        assert s.key in rt.SESSIONS
        print('PASS object failures / editor-owned rows / editor retirement')

        # Freshness uses the owning view layer and Local View, not another editor.
        for obj in context.view_layer.objects: obj.select_set(False)
        quad.select_set(True)
        context.view_layer.objects.active = quad
        bpy.ops.view3d.localview(frame_selected=False)
        assert set(scan(context)) == {uid}
        bpy.ops.view3d.localview(frame_selected=False)
        assert len(scan(context)) == 83
        quad.name = 'Renamed Quad'
        context.view_layer.update()
        rt.observe(context, s, force=True)
        scan(context)
        assert s.snapshot['results'][uid]['name'] == 'Renamed Quad'
        saved_layer = context.window.view_layer
        layer = context.scene.view_layers.new('Test layer')
        context.window.view_layer = layer
        rt.observe(context, s)
        assert s.snapshot is None
        scan(context)
        context.window.view_layer = saved_layer
        context.scene.view_layers.remove(layer)
        scan(context)
        print('PASS Local View / rename identity / view-layer rebind')

        # The draw path must not evaluate, select, or create Blender properties.
        class Layout:
            def row(self, **kwargs): return self
            def column(self, **kwargs): return self
            def split(self, **kwargs): return self
            def box(self): return self
            def label(self, **kwargs): pass
            def prop(self, data, name, **kwargs): assert hasattr(data, name)
            def prop_enum(self, data, name, value): assert value in data.bl_rna.properties[name].enum_items
            def operator(self, name, **kwargs): return SimpleNamespace()
            def progress(self, **kwargs): pass
            def template_list(self, *args, **kwargs): pass
        rt.collect_object = lambda *args: (_ for _ in ()).throw(AssertionError('draw evaluated mesh'))
        try:
            before = (context.view_layer.objects.active, len(state.rows), s.commits)
            ui.draw(Layout(), context)
            for row in state.rows:
                ui.MBT_UL_scene_performance.draw_item(None, context, Layout(), state, row, 0, state, 'index')
            assert before == (context.view_layer.objects.active, len(state.rows), s.commits)
        finally:
            rt.collect_object = real_collect
        print('PASS cached drawing / no evaluation or selection mutations')

        before = len(rt.TRACE)
        rt.restore()
        assert not rt.SESSIONS and len(context.window_manager.mbt_stats_sessions) == 0
        assert len(rt.TRACE) >= before
        scan(context)
        lifecycle(addon.unregister)
        assert not rt.SESSIONS and not bpy.app.timers.is_registered(rt.controller)
        assert all(callback not in handlers for handlers, callback in rt.HANDLERS)
    print('ALL SCENE PERFORMANCE SESSION TESTS PASSED')


if __name__ == '__main__':
    run()