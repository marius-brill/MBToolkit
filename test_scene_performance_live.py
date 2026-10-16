"""Disposable GUI test: --factory-startup --enable-event-simulate --python this_file.

Exercises actual viewport hit selection, list activation, multiple editor sessions,
multi-batch changes and scheduled reconciliation. Never run in a working process.
"""
import importlib
import json
from pathlib import Path
import sys
import time
import traceback
import tempfile

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Quaternion, Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
rt = importlib.import_module(f'{ROOT.name}.features.scene_performance.runtime')
OUTPUT = Path('C:/tmp/mbt_scene_live_result.txt')
TRACE = Path('C:/tmp/mbt_scene_live_trace.json')
started = time.monotonic()
stage = 0
objects = []
editor = None
baseline = 0
click = None


def check():
    global stage, baseline, click, editor
    try:
        assert time.monotonic() - started < 70, f'Timed out stage {stage}'
        if stage == 7:
            window = bpy.context.window_manager.windows[0]
            area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
            region = next(r for r in area.regions if r.type == 'WINDOW')
            editor = window, area, region
        window, area, region = editor
        with bpy.context.temp_override(window=window, area=area, region=region):
            context = bpy.context
            s, ui = rt.session(context), rt.state(context)
            if stage == 0:
                if not s.snapshot or s.requested != s.committed: return 0.15
                assert len(ui.rows) == 102
                baseline = s.commits
                ui.auto = False
                # Deliberately activate object A BEFORE clicking object B.
                for obj in context.view_layer.objects: obj.select_set(False)
                objects[0].select_set(True)
                context.view_layer.objects.active = objects[0]
                click = location_3d_to_region_2d(region, area.spaces.active.region_3d, objects[1].location)
                assert click is not None
                window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=int(region.x+click.x), y=int(region.y+click.y))
                stage = 10
                return 0.3
            elif stage == 10:
                window.event_simulate(type='LEFTMOUSE', value='PRESS', x=int(region.x+click.x), y=int(region.y+click.y))
                window.event_simulate(type='LEFTMOUSE', value='RELEASE', x=int(region.x+click.x), y=int(region.y+click.y))
                # Route Blender's native viewport hit-test at the same coordinates too;
                # OS focus can prevent simulated mouse events reaching a new window.
                bpy.ops.view3d.select(location=(int(click.x), int(click.y)))
                stage = 1
            elif stage == 1:
                if context.view_layer.objects.active != objects[1] or ui.index < 0 or ui.rows[ui.index].obj != objects[1]:
                    return 0.15
                assert s.commits == baseline  # Selection in manual mode performs no scans.
                bpy.ops.mbt.stats_activate(uid=str(objects[0].session_uid))
                stage = 2
            elif stage == 2:
                if context.view_layer.objects.active != objects[0] or ui.index < 0 or ui.rows[ui.index].obj != objects[0]: return 0.15
                ui.auto = True
                objects[0].modifiers.new('Subdivision', 'SUBSURF').levels = 2
                context.view_layer.update()
                stage = 3
            elif stage == 3:
                # Force changes between scheduled batches; must still publish progress.
                if s.job and s.job['position'] > 0:
                    rt.request_refresh(context, 'Live soft change during multi-batch scan')
                    stage = 4
                return 0.02
            elif stage == 4:
                result = s.snapshot['results'].get(str(objects[0].session_uid)) if s.snapshot else None
                if not result or result['tris'] != 192 or s.requested != s.committed: return 0.15
                assert s.commits > baseline
                stage = 5
                baseline = s.commits
                return 1.0
            elif stage == 5:
                assert s.commits == baseline, 'Idle auto repeatedly recollects'
                # Independent editor gets its own view-layer context and row collection.
                second = next(a for a in context.screen.areas if a != area and a.type == 'PROPERTIES')
                second.type = 'VIEW_3D'
                second.spaces.active.show_region_ui = True
                second_region = next(r for r in second.regions if r.type == 'WINDOW')
                with context.temp_override(area=second, region=second_region):
                    rt.watch(bpy.context)
                stage = 6
            elif stage == 6:
                if len(rt.SESSIONS) < 2 or any(not item.snapshot for item in rt.SESSIONS.values()): return 0.15
                assert len({item.key for item in rt.SESSIONS.values()}) == 2
                bpy.ops.wm.window_new()
                new_window = next(w for w in context.window_manager.windows if w != window)
                new_area = next(a for a in new_window.screen.areas if a.type == 'VIEW_3D')
                new_region = next(r for r in new_area.regions if r.type == 'WINDOW')
                with context.temp_override(window=new_window, area=new_area, region=new_region):
                    other = rt.session(bpy.context)
                    assert other.key != s.key
                    bpy.ops.wm.window_close()
                # Save/load in this disposable process proves timer and subscription recovery.
                path = str(Path(tempfile.gettempdir()) / 'mbt_scene_session_test.blend')
                bpy.ops.wm.save_as_mainfile(filepath=path)
                stage = 7
                bpy.ops.wm.open_mainfile(filepath=path)
                return 0.3
            elif stage == 7:
                if not s.snapshot or s.requested != s.committed: return 0.15
                assert bpy.app.timers.is_registered(rt.controller)
                assert len(ui.rows) == 102
                TRACE.write_text(json.dumps(rt.diagnostics(), indent=2), encoding='utf-8')
                OUTPUT.write_text('PASS native viewport hit-selection / manual list sync / explicit list activation / multi-batch soft change commits / eventual freshness / idle no scans / independent editors / multiple windows / file-load recovery\n', encoding='utf-8')
                addon.unregister()
                bpy.ops.wm.quit_blender()
                return None
        return 0.15
    except Exception:
        OUTPUT.write_text(traceback.format_exc(), encoding='utf-8')
        TRACE.write_text(json.dumps(rt.diagnostics(), indent=2), encoding='utf-8')
        bpy.ops.wm.quit_blender()
        return None


def setup():
    global editor
    try:
        assert not bpy.app.background
        addon.register()
        window = bpy.context.window_manager.windows[0]
        area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        editor = window, area, region
        with bpy.context.temp_override(window=window, area=area, region=region):
            for obj in list(bpy.data.objects): bpy.data.objects.remove(obj, do_unlink=True)
            for x in (-3, 3):
                bpy.ops.mesh.primitive_cube_add(location=(x, 0, 0))
                objects.append(bpy.context.object)
            for index in range(100):
                obj = bpy.data.objects.new(f'Extra {index}', objects[0].data)
                obj.location = (100+index*3, 0, 0)
                bpy.context.collection.objects.link(obj)
            area.spaces.active.show_region_ui = True
            view = area.spaces.active.region_3d
            view.view_rotation = Quaternion((1, 0, 0, 0))
            view.view_perspective = 'ORTHO'
            view.view_distance = 25
            view.view_location = Vector((0,0,0))
            rt.watch(bpy.context)
        bpy.app.timers.register(check, first_interval=0.2, persistent=True)
    except Exception:
        OUTPUT.write_text(traceback.format_exc(), encoding='utf-8')
        bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(setup, first_interval=0.5)