"""Disposable GUI test; run --factory-startup --enable-event-simulate --python this_file."""

import importlib
from pathlib import Path
import sys
import traceback

import bpy

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
shared = importlib.import_module(f'{ROOT.name}.core.preferences_ui')
OUTPUT = Path('C:/tmp/mbt_preferences_live_result.txt')
stage = 0
window = area = region = prefs = None


def send(kind, value='PRESS', x=None, y=None, **kwargs):
    window.event_simulate(type=kind, value=value,
        x=int(region.x + (x if x is not None else region.width/2)),
        y=int(region.y + (y if y is not None else region.height/2)), **kwargs)


def check():
    global stage, window, area, region, prefs
    try:
        if stage == 0:
            addon.register()
            entry = bpy.context.preferences.addons.new()
            entry.module = ROOT.name
            prefs = entry.preferences
            window = bpy.context.window_manager.windows[0]
            area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
            region = next(r for r in area.regions if r.type == 'WINDOW')
            for kind in ('BEVEL', 'SUBSURF', 'MIRROR', 'ARRAY', 'SOLIDIFY'):
                bpy.ops.mbt.modifier_favorite(key='object.modifier_add:'+kind, label=kind, action='TOGGLE')
            with bpy.context.temp_override(window=window, area=area, region=region):
                assert bpy.ops.mbt.capture_shortcut('INVOKE_DEFAULT', target='MODIFIER') == {'RUNNING_MODAL'}
            send('F', ctrl=True, shift=True)
        elif stage == 1:
            assert prefs.modifier_popup_key == 'F' and prefs.modifier_popup_ctrl and prefs.modifier_popup_shift
            with bpy.context.temp_override(window=window, area=area, region=region):
                assert bpy.ops.mbt.reorder_favorites('INVOKE_DEFAULT', key=prefs.modifier_favorites[0].key) == {'RUNNING_MODAL'}
        elif stage == 2:
            drag = shared._drag_sessions[0]
            x, y = drag._origin[0] - region.x, drag._origin[1] - region.y
            send('MOUSEMOVE', value='NOTHING', x=x, y=y-drag._height)
            send('LEFTMOUSE', value='RELEASE', x=x, y=y-drag._height)
        elif stage == 3:
            assert prefs.modifier_favorites[4].label == 'BEVEL'
            assert not shared._drag_sessions
        elif stage == 4:
            assert not shared._drag_sessions
            with bpy.context.temp_override(window=window, area=area, region=region):
                bpy.ops.mbt.reorder_favorites('INVOKE_DEFAULT', key=prefs.modifier_favorites[0].key)
            drag = shared._drag_sessions[0]
            x, y = drag._origin[0] - region.x, drag._origin[1] - region.y
            send('MOUSEMOVE', value='NOTHING', x=x+drag._width, y=y)
        elif stage == 5:
            assert shared._drag_sessions[0]._hover == 1
            assert prefs.modifier_favorites[0].label == 'SUBSURF'
            send('ESC')
        elif stage == 6:
            assert prefs.modifier_favorites[0].label == 'SUBSURF'
            assert not shared._drag_sessions
            OUTPUT.write_text('PASS real shortcut event capture / inline simulated drag reorder / release finishes / Escape leaves original order\n', encoding='utf-8')
            addon.unregister()
            bpy.ops.wm.quit_blender()
            return None
        stage += 1
        return 0.6
    except Exception:
        OUTPUT.write_text(traceback.format_exc(), encoding='utf-8')
        bpy.ops.wm.quit_blender()
        return None


bpy.app.timers.register(check, first_interval=1.0)