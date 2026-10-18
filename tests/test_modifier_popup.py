"""Disposable GUI integration test: blender --factory-startup --python this_file.

Opens an in-viewport popup, checks no new window is created, and quits Blender.
Never run this script in a working Blender session.
"""

import importlib
from pathlib import Path
import sys
import tempfile
import traceback

import bpy

ROOT = Path(__file__).resolve().parents[1]
RESULT = Path(tempfile.gettempdir()) / 'mbt_modifier_popup_result.txt'
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
feature = importlib.import_module(f'{ROOT.name}.features.modifier_list')


def finish():
    try:
        assert not bpy.app.background
        addon.register()
        entry = bpy.context.preferences.addons.new()
        entry.module = ROOT.name
        feature.rebuild_keymap()
        assert len(feature._keymap_items) == 1
        item = feature._keymap_items[0][1]
        assert item.type == 'W' and item.shift and item.active
        window = bpy.context.window_manager.windows[0]
        area = next(area for area in window.screen.areas if area.type == 'VIEW_3D')
        original = {w.as_pointer() for w in bpy.context.window_manager.windows}
        with bpy.context.temp_override(window=window, area=area):
            bpy.context.object.modifiers.new('PopupTest', 'BEVEL')
            assert bpy.ops.mbt.modifier_popup('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
        new = [w for w in bpy.context.window_manager.windows if w.as_pointer() not in original]
        assert not new
        assert area.type == 'VIEW_3D'
        # Let Blender redraw the real popup before terminating.
        bpy.app.timers.register(success, first_interval=1.0)
    except Exception:
        RESULT.write_text(traceback.format_exc(), encoding='utf-8')
        bpy.ops.wm.quit_blender()
    return None


def success():
    RESULT.write_text('PASS actual viewport popup / Shift W binding / no new window / original viewport preserved', encoding='utf-8')
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(finish, first_interval=1.0)
print(f'Modifier popup test result: {RESULT}', flush=True)