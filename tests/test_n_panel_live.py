"""Disposable GUI smoke test. Launch with --factory-startup --python this_file."""

import importlib
from pathlib import Path
import sys
import traceback

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
manager = importlib.import_module(f'{ROOT.name}.features.n_panel')
OUTPUT = Path('C:/tmp/mbt_npanel_live_result.txt')
stage = 0


class MBT_TEST_PT_preferences(bpy.types.Panel):
    bl_label = 'Sidebar Tab Manager Smoke Test'
    bl_space_type = 'PREFERENCES'
    bl_region_type = 'WINDOW'

    def draw(self, context):
        manager.draw_preferences(self.layout, manager.get_prefs(context))


def check():
    global stage
    try:
        if stage == 0:
            addon.register()
            entry = bpy.context.preferences.addons.new()
            entry.module = ROOT.name
            prefs = entry.preferences
            prefs.n_panel_enabled = True
            manager.apply(prefs)
            bpy.utils.register_class(MBT_TEST_PT_preferences)
            bpy.context.window_manager.windows[0].screen.areas[0].type = 'PREFERENCES'
        elif stage == 1:
            prefs = manager.get_prefs()
            prefs.n_panel_tabs['MBToolkit'].visible = False
            assert not bpy.types.MBT_PT_main.poll(bpy.context)
            index = next(i for i, item in enumerate(prefs.n_panel_tabs) if item.name == 'MBToolkit')
            assert bpy.ops.mbt.n_panel(action='UP', index=index) == {'FINISHED'}
        elif stage == 2:
            prefs = manager.get_prefs()
            prefs.n_panel_tabs['MBToolkit'].visible = True
            assert bpy.types.MBT_PT_main.poll(bpy.context)
            assert bpy.ops.mbt.n_panel(action='RESET') == {'FINISHED'}
        elif stage == 3:
            bpy.utils.unregister_class(MBT_TEST_PT_preferences)
            addon.unregister()
            OUTPUT.write_text('PASS real Preferences layout draw / hide / reorder / show / reset / cleanup\n', encoding='utf-8')
            bpy.ops.wm.quit_blender()
            return None
        stage += 1
        return 1.5
    except Exception:
        OUTPUT.write_text(traceback.format_exc(), encoding='utf-8')
        bpy.ops.wm.quit_blender()
        return None


bpy.app.timers.register(check, first_interval=1.0)