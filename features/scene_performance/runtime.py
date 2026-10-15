"""Transient, scoped snapshots and a cancellable main-thread scan job."""

import copy
import time

import bpy
from bpy.app.handlers import persistent
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       IntProperty, PointerProperty, StringProperty)

from .collectors import MESH_TYPES, collect_object


class MBT_StatsRow(bpy.types.PropertyGroup):
    name: StringProperty()
    uid: StringProperty()
    obj: PointerProperty(type=bpy.types.Object)
    tris: IntProperty(default=-1)
    ms: FloatProperty(default=-1)
    error: StringProperty()


class MBT_StatsState(bpy.types.PropertyGroup):
    rows: CollectionProperty(type=MBT_StatsRow)
    index: IntProperty(default=0, min=0)
    running: BoolProperty(default=False)
    stale: BoolProperty(default=False)
    status: StringProperty(default='Choose a scope and scan to begin')
    progress: FloatProperty(default=0, min=0, max=1, subtype='FACTOR')
    search: StringProperty(name='Search', description='Filter captured object names')
    sort: EnumProperty(name='Sort', items=(('TRIS', 'Triangles', ''),
                       ('PERF', 'Modifier time', ''), ('NAME', 'Name', '')), default='TRIS')
    descending: BoolProperty(name='Descending', default=True)
    filter: EnumProperty(name='Filter', items=(('ALL', 'All results', ''),
                         ('BUDGET', 'Over budget', ''), ('ERROR', 'Errors', ''),
                         ('UNMEASURED', 'No timing', ''), ('STALE', 'Stale results', '')))


classes = (MBT_StatsRow, MBT_StatsState)
SNAPSHOT = None
BASELINE = None
JOB = None
_collecting = False
_revision = 0
_presentation_key = None
_presentation = None
_comparison_key = None
_comparison_warning = ''


def state(context):
    return context.window_manager.mbt_stats


def context_key(context):
    # Local View changes the meaning of "visible" and belongs to the capture scope.
    space = context.space_data
    local = (getattr(space, 'local_view', None)
             if context.scene.mbt.stats_scope == 'VISIBLE' else None)
    return (str(context.scene.session_uid), context.view_layer.as_pointer(),
            local.as_pointer() if local else 0)


def scope_signature(context):
    props = context.scene.mbt
    collection = context.collection if props.stats_scope == 'COLLECTION' else None
    return (context_key(context), props.stats_scope,
            str(collection.session_uid) if collection else None,
            props.stats_recursive if collection else None)


def matches(context):
    return SNAPSHOT is not None and SNAPSHOT['signature'] == scope_signature(context)


def targets(context):
    props = context.scene.mbt
    if props.stats_scope == 'SELECTED':
        objects = context.selected_objects
    elif props.stats_scope == 'COLLECTION':
        collection = context.collection
        objects = collection.all_objects if props.stats_recursive else collection.objects
    else:
        objects = context.visible_objects
    layer = context.view_layer.objects
    return sorted((obj for obj in objects if obj.name in layer
                   and (obj.type in MESH_TYPES or len(obj.modifiers) > 0)),
                  key=lambda obj: (obj.name.casefold(), obj.session_uid))


def redraw(wm):
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _changed():
    global _revision, _presentation_key
    _revision += 1
    _presentation_key = None


def is_stale(context):
    return (state(context).stale or (matches(context)
            and SNAPSHOT['frame'] != context.scene.frame_current))


def presentation(context):
    """Cache O(n) filtering/sorting/totals; draw_item only reads a single row."""
    global _presentation, _presentation_key
    ui = state(context)
    props = context.scene.mbt
    key = (_revision, ui.search, ui.sort, ui.descending, ui.filter,
           props.stats_tri_budget, props.stats_ms_budget, is_stale(context))
    if key == _presentation_key:
        return _presentation
    rows = ui.rows
    indices = []
    search = ui.search.casefold().strip()
    for index, row in enumerate(rows):
        budget = row.tris > props.stats_tri_budget or row.ms > props.stats_ms_budget
        if search and search not in row.name.casefold():
            continue
        if ((ui.filter == 'BUDGET' and not budget) or (ui.filter == 'ERROR' and not row.error)
                or (ui.filter == 'UNMEASURED' and row.ms >= 0)
                or (ui.filter == 'STALE' and not is_stale(context))):
            continue
        indices.append(index)
    # Unavailable values remain last in either direction. Tie-break by name/identity.
    def sort_key(index):
        row = rows[index]
        value = row.tris if ui.sort == 'TRIS' else row.ms
        return (value < 0, -value if ui.descending else value, row.name.casefold(), row.uid)
    if ui.sort == 'NAME':
        ordered = sorted(range(len(rows)), key=lambda i: (rows[i].name.casefold(), rows[i].uid),
                         reverse=ui.descending)
    else:
        ordered = sorted(range(len(rows)), key=sort_key)
    order = [0] * len(rows)
    for rank, index in enumerate(ordered):
        order[index] = rank
    _presentation = {'visible': set(indices), 'order': order,
                     'tris': sum(max(0, rows[i].tris) for i in indices),
                     'errors': sum(bool(row.error) for row in rows),
                     'total_tris': sum(max(0, row.tris) for row in rows)}
    _presentation_key = key
    return _presentation


def active_result(context):
    ui = state(context)
    if not matches(context) or not 0 <= ui.index < len(ui.rows):
        return None, None
    row = ui.rows[ui.index]
    return row, SNAPSHOT['results'].get(row.uid)


def begin(context, timings=True):
    global SNAPSHOT, JOB
    if JOB is not None:
        raise RuntimeError('A scene scan is already running')
    if context.mode != 'OBJECT' or bpy.app.is_job_running('RENDER'):
        raise RuntimeError('Scan requires Object Mode and no active render')
    objects = targets(context)
    ui = state(context)
    active_uid = ui.rows[ui.index].uid if 0 <= ui.index < len(ui.rows) else None
    ui.rows.clear()
    ui.index = 0
    ui.stale = False
    ui.running = True
    ui.progress = 0
    ui.status = f'Scanning 0 / {len(objects)} objects'
    SNAPSHOT = {'signature': scope_signature(context), 'frame': context.scene.frame_current,
                'scene': context.scene.name, 'view_layer': context.view_layer.name,
                'scope': context.scene.mbt.stats_scope, 'captured_at': time.time(),
                'method': 'native_last_evaluation' if timings else 'geometry_only',
                'complete': False, 'results': {}, 'target_uids': [str(o.session_uid) for o in objects]}
    JOB = {'objects': objects, 'position': 0, 'wm': context.window_manager,
           'window': context.window, 'area': context.area, 'signature': SNAPSHOT['signature'],
           'frame': context.scene.frame_current, 'timings': timings, 'active_uid': active_uid,
           'cancel_reason': '', 'started': time.perf_counter()}
    _changed()
    return JOB


def finish(reason=''):
    global JOB
    if JOB is None:
        return
    job = JOB
    ui = job['wm'].mbt_stats
    count = job['position']
    SNAPSHOT['complete'] = not reason
    SNAPSHOT['duration'] = time.perf_counter() - job['started']
    SNAPSHOT['stop_reason'] = reason
    ui.running = False
    ui.progress = count / max(1, len(job['objects'])) if reason else 1
    errors = sum(bool(row.error) for row in ui.rows)
    ui.status = (f'{reason} · {count}/{len(job["objects"])} captured' if reason else
                 f'Ready · {count} objects · {errors} errors · {SNAPSHOT["duration"]:.2f}s')
    if job['active_uid']:
        ui.index = next((i for i, row in enumerate(ui.rows) if row.uid == job['active_uid']), 0)
    JOB = None
    _changed()
    redraw(job['wm'])


def step(context, budget=0.025):
    global _collecting
    job = JOB
    if job is None:
        return False
    if (job['cancel_reason'] or scope_signature(context) != job['signature']
            or context.scene.frame_current != job['frame'] or context.mode != 'OBJECT'
            or bpy.app.is_job_running('RENDER')):
        state(context).stale = True
        finish(job['cancel_reason'] or 'Context changed; scan stopped')
        return False
    deadline = time.perf_counter() + budget
    try:
        _collecting = True
        # Never keep a dependency graph or evaluated datablock between ticks.
        depsgraph = context.evaluated_depsgraph_get()
        while job['position'] < len(job['objects']):
            obj = job['objects'][job['position']]
            try:
                result = collect_object(depsgraph, obj, job['timings'])
            except (RuntimeError, ReferenceError, TypeError, ValueError) as exc:
                try:
                    uid, name = str(obj.session_uid), obj.name
                except ReferenceError:
                    uid, name = SNAPSHOT['target_uids'][job['position']], '<deleted object>'
                    obj = None
                result = {'uid': uid, 'name': name, 'tris': None, 'ms': None,
                          'mods': [], 'error': str(exc)}
            SNAPSHOT['results'][result['uid']] = result
            row = state(context).rows.add()
            row.name, row.uid, row.obj = result['name'], result['uid'], obj
            row.tris = result['tris'] if result['tris'] is not None else -1
            row.ms = result['ms'] if result['ms'] is not None else -1
            row.error = result['error']
            job['position'] += 1
            if time.perf_counter() >= deadline:
                break
    finally:
        _collecting = False
    ui = state(context)
    ui.progress = job['position'] / max(1, len(job['objects']))
    ui.status = f'Scanning {job["position"]} / {len(job["objects"])} objects'
    _changed()
    if job['position'] == len(job['objects']):
        finish()
        return False
    redraw(job['wm'])
    return True


def tick():
    if JOB is None:
        return None
    try:
        window, area = JOB['window'], JOB['area']
        if window not in tuple(bpy.context.window_manager.windows) or area not in tuple(window.screen.areas):
            finish('Scan editor closed')
            return None
        with bpy.context.temp_override(window=window, area=area):
            return 0.02 if step(bpy.context) else None
    except Exception as exc:
        finish(f'Scan stopped: {exc}')
        return None


def cancel():
    finish('Cancelled; partial results')
    if bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)


def set_baseline(context):
    global BASELINE
    if not matches(context) or not SNAPSHOT['complete'] or is_stale(context):
        raise RuntimeError('Capture a complete, fresh snapshot before setting a baseline')
    BASELINE = copy.deepcopy(SNAPSHOT)


def comparison(context):
    global _comparison_key, _comparison_warning
    if BASELINE is None or not matches(context):
        return 'No matching baseline'
    key = (_revision, id(BASELINE))
    if key == _comparison_key:
        return _comparison_warning
    _comparison_key = key
    if (BASELINE['signature'] != SNAPSHOT['signature'] or BASELINE['frame'] != SNAPSHOT['frame']
            or BASELINE['method'] != SNAPSHOT['method']
            or set(BASELINE['target_uids']) != set(SNAPSHOT['target_uids'])):
        _comparison_warning = 'Baseline scope, targets, frame or method differs'
    else:
        _comparison_warning = ''
    return _comparison_warning


def delta(context, uid):
    if comparison(context) or not SNAPSHOT['complete'] or is_stale(context):
        return None
    old = BASELINE['results'].get(uid)
    new = SNAPSHOT['results'].get(uid)
    if not old or not new or old['error'] or new['error']:
        return None
    return {key: new[key] - old[key] if new[key] is not None and old[key] is not None else None
            for key in ('tris', 'ms')}


@persistent
def invalidate(*args):
    if _collecting:
        return
    if JOB is not None:
        JOB['cancel_reason'] = 'Scene changed; scan stopped'
    changed = False
    for wm in bpy.data.window_managers:
        if hasattr(wm, 'mbt_stats') and SNAPSHOT is not None and not wm.mbt_stats.stale:
            wm.mbt_stats.stale = True
            changed = True
    if changed:
        _changed()


@persistent
def reset(*args):
    global SNAPSHOT, BASELINE
    cancel()
    SNAPSHOT = BASELINE = None
    for wm in bpy.data.window_managers:
        if hasattr(wm, 'mbt_stats'):
            ui = wm.mbt_stats
            ui.rows.clear()
            ui.index = 0
            ui.running = ui.stale = False
            ui.progress = 0
            ui.status = 'Choose a scope and scan to begin'
    _changed()


HANDLERS = ((bpy.app.handlers.depsgraph_update_post, invalidate),
            (bpy.app.handlers.frame_change_post, invalidate),
            (bpy.app.handlers.undo_post, reset), (bpy.app.handlers.redo_post, reset),
            (bpy.app.handlers.load_pre, reset), (bpy.app.handlers.load_post, reset))


def register():
    bpy.types.WindowManager.mbt_stats = PointerProperty(type=MBT_StatsState, options={'SKIP_SAVE'})
    for handlers, callback in HANDLERS:
        if callback not in handlers:
            handlers.append(callback)
    reset()


def unregister():
    reset()
    for handlers, callback in HANDLERS:
        if callback in handlers:
            handlers.remove(callback)
    del bpy.types.WindowManager.mbt_stats