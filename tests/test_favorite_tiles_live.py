"""Disposable GUI test of native tile press dispatch in Preferences."""
import importlib
from pathlib import Path
import sys
import traceback

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
shared = importlib.import_module(f'{ROOT.name}.core.preferences_ui')
OUTPUT = Path('C:/tmp/mbt_favorite_tiles_live_result.txt')
stage = 0
scan_y = None


class MBT_PT_test_tiles(bpy.types.Panel):
    bl_label = 'Favorite tiles test'
    bl_space_type = 'PREFERENCES'
    bl_region_type = 'WINDOW'

    def draw(self, context):
        shared.draw_favorite_tiles(self.layout, prefs, {})


def send(kind, value='PRESS', x=100, y=100):
    window.event_simulate(type=kind, value=value, x=int(region.x+x), y=int(region.y+y))


def check():
    global stage, window, area, region, prefs, scan_y
    try:
        if stage == 0:
            if '--scaled' in sys.argv:
                bpy.context.preferences.view.ui_scale = 1.5
            addon.register()
            entry = bpy.context.preferences.addons.new()
            entry.module = ROOT.name
            prefs = entry.preferences
            for kind in ('BEVEL', 'ARRAY', 'MIRROR', 'SOLIDIFY', 'TRIANGULATE'):
                bpy.ops.mbt.modifier_favorite(key=kind, label=kind, action='TOGGLE')
            bpy.utils.register_class(MBT_PT_test_tiles)
            window = bpy.context.window_manager.windows[0]
            area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
            area.type = 'PREFERENCES'
            bpy.context.preferences.active_section = 'INTERFACE'
            region = next(r for r in area.regions if r.type == 'WINDOW')
            scan_y = region.height - 30
            stage = 1
        elif stage == 1:
            if shared._drag_sessions:
                drag = shared._drag_sessions[0]
                assert drag._source == 0
                x, y = drag._origin[0]-region.x, drag._origin[1]-region.y
                send('MOUSEMOVE', 'NOTHING', x, y-drag._height)
                stage = 2
            else:
                if scan_y < 10:
                    raise AssertionError('Native tile press never started drag')
                send('LEFTMOUSE', 'RELEASE', 100, scan_y+6)
                send('MOUSEMOVE', 'NOTHING', 100, scan_y)
                send('LEFTMOUSE', 'PRESS', 100, scan_y)
                scan_y -= 6
        elif stage == 2:
            drag = shared._drag_sessions[0]
            assert drag._hover == 4, (drag._hover, drag._height)
            x, y = drag._origin[0]-region.x, drag._origin[1]-region.y
            send('LEFTMOUSE', 'RELEASE', x, y-drag._height)
            stage = 3
        else:
            assert not shared._drag_sessions
            assert prefs.modifier_favorites[4].label == 'BEVEL'
            OUTPUT.write_text('PASS native Preferences tile press / drag preview / release reorder\n')
            bpy.ops.wm.quit_blender()
            return None
        return 0.15
    except Exception:
        OUTPUT.write_text(traceback.format_exc())
        bpy.ops.wm.quit_blender()
        return None


bpy.app.timers.register(check, first_interval=1)