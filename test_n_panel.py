"""Run only in disposable Blender: --background --factory-startup --python this_file."""

import importlib
from pathlib import Path
import sys
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
manager = importlib.import_module(f'{ROOT.name}.features.n_panel')


class MBT_TEST_PT_first(bpy.types.Panel):
    bl_idname = 'MBT_TEST_PT_first'
    bl_label = 'First Test'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Test Alpha'
    bl_order = 20

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def draw(self, context):
        self.layout.label(text='Alpha')


class MBT_TEST_PT_child(MBT_TEST_PT_first):
    bl_idname = 'MBT_TEST_PT_child'
    bl_label = 'Child Test'
    bl_parent_id = 'MBT_TEST_PT_first'


class MBT_TEST_PT_second(bpy.types.Panel):
    bl_idname = 'MBT_TEST_PT_second'
    bl_label = 'Second Test'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Test Beta'
    bl_order = -10

    def draw(self, context):
        self.layout.label(text='Beta')


class MBT_TEST_PT_late(MBT_TEST_PT_second):
    bl_idname = 'MBT_TEST_PT_late'
    bl_label = 'Late Test'
    bl_category = 'Test Alpha'


def run():
    assert bpy.app.background
    addon.register()
    entry = bpy.context.preferences.addons.new()
    entry.module = ROOT.name
    prefs = entry.preferences
    assert 'N_PANEL' in prefs.bl_rna.properties['tab'].enum_items
    originals = {cls: (cls.__dict__.get('poll'), cls.__dict__.get('bl_order'))
                 for cls in manager.panel_classes()}
    for cls in (MBT_TEST_PT_first, MBT_TEST_PT_child, MBT_TEST_PT_second):
        bpy.utils.register_class(cls)
    assert MBT_TEST_PT_child in manager.panel_classes()
    original_poll = MBT_TEST_PT_first.__dict__['poll']
    original_child_poll = MBT_TEST_PT_child.__dict__.get('poll')
    prefs.n_panel_enabled = True
    manager.apply(prefs)
    assert prefs.n_panel_tabs[0].name == 'Item'
    names = [item.name for item in prefs.n_panel_tabs]
    assert names.index('Test Beta') < names.index('Test Alpha')
    assert MBT_TEST_PT_first.poll(SimpleNamespace(mode='OBJECT', preferences=bpy.context.preferences))
    assert not MBT_TEST_PT_first.poll(SimpleNamespace(mode='EDIT_MESH', preferences=bpy.context.preferences))
    prefs.n_panel_tabs['Test Alpha'].visible = False
    # Existing poll wrappers read visibility immediately, without unregistering.
    assert not MBT_TEST_PT_first.poll(bpy.context)
    assert MBT_TEST_PT_second.poll(bpy.context)
    assert MBT_TEST_PT_child.__dict__.get('poll') is original_child_poll
    assert bpy.ops.mbt.n_panel(action='UP', index=0) == {'CANCELLED'}
    while True:
        names = [item.name for item in prefs.n_panel_tabs]
        source = names.index('Test Alpha')
        if source < names.index('Test Beta'):
            break
        assert bpy.ops.mbt.n_panel(action='UP', index=source) == {'FINISHED'}
    assert MBT_TEST_PT_first.bl_order < MBT_TEST_PT_second.bl_order
    assert not MBT_TEST_PT_first.poll(bpy.context)
    assert getattr(MBT_TEST_PT_child, 'bl_parent_id') == MBT_TEST_PT_first.bl_idname
    print('PASS whole-tab visibility / preserved context poll / nested subclasses / tab ordering')

    bpy.utils.register_class(MBT_TEST_PT_late)
    manager._tick()
    assert not MBT_TEST_PT_late.poll(bpy.context)
    bpy.utils.unregister_class(MBT_TEST_PT_late)
    manager._tick()
    assert not MBT_TEST_PT_late.is_registered
    # Unavailable tabs stay saved and return with their old settings.
    bpy.utils.unregister_class(MBT_TEST_PT_child)
    bpy.utils.unregister_class(MBT_TEST_PT_first)
    manager._tick()
    assert not MBT_TEST_PT_first.is_registered
    assert not prefs.n_panel_tabs['Test Alpha'].visible
    bpy.utils.register_class(MBT_TEST_PT_first)
    bpy.utils.register_class(MBT_TEST_PT_child)
    manager._tick()
    assert not MBT_TEST_PT_first.poll(bpy.context)
    print('PASS newly enabled panels / disabled add-on not resurrected / saved unavailable tab')

    prefs.n_panel_enabled = False
    manager._tick()
    assert MBT_TEST_PT_first.__dict__['poll'] is original_poll
    assert MBT_TEST_PT_first.bl_order == 20
    assert MBT_TEST_PT_second.bl_order == -10
    assert 'poll' not in MBT_TEST_PT_second.__dict__
    assert not manager._originals
    for cls, snapshot in originals.items():
        assert (cls.__dict__.get('poll'), cls.__dict__.get('bl_order')) == snapshot, cls
    print('PASS disable restores original poll descriptors and panel ordering')

    prefs.n_panel_enabled = True
    manager.apply(prefs)
    assert bpy.ops.mbt.n_panel(action='RESET') == {'FINISHED'}
    assert not prefs.n_panel_enabled
    assert all(item.visible for item in prefs.n_panel_tabs)
    assert not manager._originals
    prefs.n_panel_enabled = True
    manager.apply(prefs)
    addon.unregister()
    assert MBT_TEST_PT_first.__dict__['poll'] is original_poll
    assert MBT_TEST_PT_second.bl_order == -10
    assert not manager._originals
    assert not bpy.app.timers.is_registered(manager._tick)
    for cls in (MBT_TEST_PT_child, MBT_TEST_PT_first, MBT_TEST_PT_second):
        bpy.utils.unregister_class(cls)
    bpy.context.preferences.addons.remove(entry)
    addon.register()
    addon.unregister()
    print('ALL N-PANEL TESTS PASSED')


if __name__ == '__main__':
    run()