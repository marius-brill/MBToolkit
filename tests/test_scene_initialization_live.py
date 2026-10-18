"""Disposable GUI factory-startup test for panel-only deferred initialization."""
import importlib
from pathlib import Path
import sys
import time
import traceback
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
rt = importlib.import_module(f'{ROOT.name}.features.scene_performance.runtime')
ui = importlib.import_module(f'{ROOT.name}.features.scene_performance.ui')
OUTPUT = Path('C:/tmp/mbt_initialization_result.txt')
started = time.monotonic()
stage = 0


class Layout:
    def label(self, **kwargs): pass
    def operator(self, *args, **kwargs): pass


def check():
    global stage
    try:
        assert time.monotonic() - started < 15, 'Initialization timed out'
        area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(area=area, region=region):
            context = bpy.context
            if stage == 0:
                addon.register()
                area.spaces.active.show_region_ui = True
                # Reproduce the missing-timer state; panel drawing must recover it.
                bpy.app.timers.unregister(rt.controller)
                assert rt.state(context, create=False) is None
                ui.draw(Layout(), context)
                assert rt.state(context, create=False) is None, 'Draw created RNA state'
                assert bpy.app.timers.is_registered(rt.controller)
                stage = 1
            elif stage == 1:
                state = rt.state(context, create=False)
                if state is None:
                    return 0.1
                s = rt.SESSIONS[rt.editor_key(context)]
                if not s.snapshot:
                    return 0.1
                assert state.phase != 'ERROR', state.status
                OUTPUT.write_text('PASS panel-only initialization / missing controller recovery / deferred RNA creation / automatic first capture', encoding='utf-8')
                addon.unregister()
                bpy.ops.wm.quit_blender()
                return None
        return 0.1
    except Exception:
        OUTPUT.write_text(traceback.format_exc(), encoding='utf-8')
        bpy.ops.wm.quit_blender()
        return None


bpy.app.timers.register(check, first_interval=0.5)