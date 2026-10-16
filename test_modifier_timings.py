"""Disposable integration tests: blender --background --factory-startup --python this_file."""

import importlib
import math
from pathlib import Path
import sys
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
feature = importlib.import_module(f'{ROOT.name}.features.modifier_list')


def run():
    assert bpy.app.background, 'Run only in a disposable background Blender process'
    addon.register()
    try:
        obj = bpy.context.object
        bevel = obj.modifiers.new('Timing Bevel', 'BEVEL')
        subsurf = obj.modifiers.new('Timing Subdivision', 'SUBSURF')
        subsurf.levels = 2
        bpy.context.view_layer.update()
        graph = bpy.context.evaluated_depsgraph_get()
        key = feature._timing_key(bpy.context.scene, bpy.context.view_layer, obj)
        assert key in feature._modifier_timings, 'Geometry update did not capture timings'
        values = feature._modifier_timings[key]
        evaluated = obj.evaluated_get(graph)
        for modifier in evaluated.modifiers:
            assert values[modifier.persistent_uid] == modifier.execution_time * 1000
            assert math.isfinite(values[modifier.persistent_uid])
        assert feature._timing_label(bpy.context, obj, bevel).endswith(' ms')

        class Layout:
            def __init__(self):
                self.events = []
            def row(self, **kwargs):
                return self
            def label(self, **kwargs):
                self.events.append(('label', kwargs))
            def prop(self, data, name, **kwargs):
                self.events.append(('prop', name))
            def operator(self, *args, **kwargs):
                return SimpleNamespace()

        # Drawing reads the cache only; it must never collect/evaluate timings.
        original_capture = feature._capture_timings
        def forbidden(*args):
            raise AssertionError('Drawing collected timings')
        feature._capture_timings = forbidden
        try:
            layout = Layout()
            for unused in range(3):
                feature.MBT_UL_modifiers.draw_item(SimpleNamespace(layout_type='DEFAULT'),
                    bpy.context, layout, obj, bevel, 0, obj, feature.INDEX_PROPERTY)
            assert layout.events[0] == ('label', {'text': feature._timing_label(bpy.context, obj, bevel)})
            assert layout.events[1] == ('prop', 'name')
        finally:
            feature._capture_timings = original_capture
        assert feature._modifier_timings[key] is values
        feature._capture_timings(graph, [obj])
        assert feature._modifier_timings[key] is values, 'Unchanged values replaced the cache'

        # Pure transform updates must not collect timings.
        feature._capture_timings = lambda graph, objects: (_ for _ in ()).throw(
            AssertionError('Transform update collected timings')) if list(objects) else None
        try:
            feature._timings_changed(bpy.context.scene, SimpleNamespace(mode='VIEWPORT', updates=[
                SimpleNamespace(id=obj, is_updated_geometry=False)]))
        finally:
            feature._capture_timings = original_capture

        bevel.show_viewport = False
        assert feature._timing_label(bpy.context, obj, bevel) == '— ms'
        bpy.context.view_layer.update()
        assert feature._modifier_timings[key][bevel.persistent_uid] is None
        bevel.show_viewport = True
        bpy.context.view_layer.update()
        assert feature._modifier_timings[key][bevel.persistent_uid] is not None
        uid = subsurf.persistent_uid
        obj.modifiers.remove(subsurf)
        bpy.context.view_layer.update()
        assert uid not in feature._modifier_timings[key]

        # A dependent object must be refreshed when its input geometry changes.
        target = bpy.data.objects.new('Timing Dependency', bpy.data.meshes.new('Timing Input'))
        bpy.context.collection.objects.link(target)
        target.data.from_pydata([(0, 0, 0)], [], [])
        dependency = obj.modifiers.new('Dependency', 'SHRINKWRAP')
        dependency.target = target
        bpy.context.view_layer.update()
        captured = []
        def record(graph, objects):
            objects = list(objects)
            captured.extend(value.session_uid for value in objects)
            original_capture(graph, objects)
        feature._capture_timings = record
        try:
            target.data.vertices[0].co.x = 2
            target.data.update()
            bpy.context.view_layer.update()
            assert obj.session_uid in captured, 'Dependent object timing was not refreshed'
        finally:
            feature._capture_timings = original_capture

        feature._reset_locks()
        assert not feature._modifier_timings
        assert bpy.app.timers.is_registered(feature._init_timings)
        assert feature._init_timings() is None
        assert key in feature._modifier_timings
        bpy.data.objects.remove(obj, do_unlink=True)
        feature._enforce_pending()
        assert key not in feature._modifier_timings
        print('PASS native milliseconds / leftmost labels / cache-only drawing / change-driven updates / dependency updates / disabled and removed modifiers / reset and cleanup')
    finally:
        addon.unregister()
    assert not feature._modifier_timings
    assert feature._timings_changed not in bpy.app.handlers.depsgraph_update_post
    assert feature._frame_timings_changed not in bpy.app.handlers.frame_change_post
    assert not bpy.app.timers.is_registered(feature._init_timings)
    print('ALL MODIFIER TIMING TESTS PASSED')


if __name__ == '__main__':
    run()