"""Snapshot-only drawing: no geometry evaluation or datablock mutation."""

from datetime import datetime

import bpy

from . import runtime as rt


def fmt_tris(value):
    if value < 0:
        return '—'
    if value >= 1000000:
        return f'{value / 1000000:.2f}M'
    return f'{value / 1000:.1f}k' if value >= 10000 else str(value)


class MBT_UL_scene_performance(bpy.types.UIList):
    def draw_filter(self, context, layout):
        pass  # Filters live above the list and use a single cached presentation.

    def filter_items(self, context, data, propname):
        model = rt.presentation(context)
        return ([self.bitflag_filter_item if i in model['visible'] else 0
                 for i in range(len(getattr(data, propname)))], model['order'])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname,
                  index=0, flt_flag=0):
        props = context.scene.mbt
        row = layout.row(align=True)
        row.alert = bool(item.error) or item.tris > props.stats_tri_budget or item.ms > props.stats_ms_budget
        row.label(text=item.name, icon='ERROR' if item.error else 'OBJECT_DATA')
        numbers = row.split(factor=0.5, align=True)
        numbers.label(text=fmt_tris(item.tris))
        numbers.label(text='—' if item.ms < 0 else f'{item.ms:.2f}')


def draw(layout, context):
    props = context.scene.mbt
    ui = rt.state(context)
    settings = layout.column(align=True)
    settings.enabled = not ui.running
    settings.prop(props, 'stats_scope', text='')
    if props.stats_scope == 'COLLECTION':
        settings.prop(props, 'stats_recursive')
    row = layout.row(align=True)
    row.operator('mbt.stats_refresh', icon='FILE_REFRESH')
    if ui.running:
        row.operator('mbt.stats_cancel', text='', icon='CANCEL')
        layout.progress(factor=ui.progress, type='BAR', text=ui.status)
    else:
        layout.label(text=ui.status, icon='INFO')
    layout.prop(props, 'stats_options', icon='TRIA_DOWN' if props.stats_options else 'TRIA_RIGHT', emboss=False)
    if props.stats_options:
        box = layout.box()
        box.prop(props, 'stats_timings')
        box.prop(props, 'stats_tri_budget')
        box.prop(props, 'stats_ms_budget')
        box.label(text='Triangles: evaluated mesh per object.')
        box.label(text='Instances are not expanded; not unique geometry.')
        box.label(text='Timings: native last evaluation, not frame time.')
        box.label(text='Parallel execution may make timings unreliable.')
        box.label(text='— means disabled, unavailable or not measured.')
    if not rt.matches(context):
        if rt.SNAPSHOT is not None:
            layout.label(text='Scope changed — scan to capture this scope', icon='INFO')
        return
    snapshot = rt.SNAPSHOT
    if rt.is_stale(context):
        warning = layout.row()
        warning.alert = True
        warning.label(text='Scene changed — rescan for current values', icon='ERROR')
    captured = datetime.fromtimestamp(snapshot['captured_at']).strftime('%H:%M:%S')
    layout.label(text=f'Frame {snapshot["frame"]} · Captured {captured}')
    layout.prop(ui, 'search', text='', icon='VIEWZOOM')
    row = layout.row(align=True)
    row.prop(ui, 'sort', text='')
    row.prop(ui, 'descending', text='', icon='SORT_DESC' if ui.descending else 'SORT_ASC', toggle=True)
    row.prop(ui, 'filter', text='')
    model = rt.presentation(context)
    layout.label(text=f'{len(ui.rows)} captured · {fmt_tris(model["total_tris"])} mesh tris')
    if len(model['visible']) != len(ui.rows):
        layout.label(text=f'{len(model["visible"])} shown · {fmt_tris(model["tris"])} filtered tris')
    header = layout.row(align=True)
    header.label(text='Object')
    header.label(text='Tris / Mod. ms')
    layout.template_list('MBT_UL_scene_performance', '', ui, 'rows', ui, 'index', rows=7, maxrows=14)
    if not model['visible']:
        layout.label(text='No results match the filters')
    row = layout.row(align=True)
    row.operator('mbt.stats_baseline', icon='BOOKMARKS')
    row.operator('mbt.stats_export', text='Export', icon='EXPORT')
    if rt.BASELINE is not None:
        warning = rt.comparison(context)
        layout.label(text=warning or 'Baseline ready · deltas below', icon='INFO')
    active, result = rt.active_result(context)
    if active is None or result is None:
        return
    box = layout.box()
    box.label(text=active.obj.name if active.obj else active.name, icon='OBJECT_DATA')
    row = box.row(align=True)
    for action, label, icon in (('SELECT', 'Select', 'RESTRICT_SELECT_OFF'),
                                ('FRAME', 'Frame', 'VIEWZOOM'), ('PROPERTIES', '', 'MODIFIER')):
        row.operator('mbt.stats_navigate', text=label, icon=icon).action = action
    if active.error:
        box.label(text=active.error, icon='ERROR')
        return
    changes = rt.delta(context, active.uid)
    if changes is not None:
        old = rt.BASELINE['results'][active.uid]
        for key, label in (('tris', 'Tris'), ('ms', 'Modifier ms')):
            value = changes[key]
            if value is not None:
                percent = f' ({value / old[key] * 100:+.1f}%)' if old[key] else ''
                box.label(text=f'{label} Δ {value:+.2f}{percent}')
    elif rt.BASELINE is not None and not rt.comparison(context):
        box.label(text='Rescan completely for a fresh comparison', icon='INFO')
    if not result['mods']:
        box.label(text='No modifier timings captured')
    else:
        box.label(text='Native modifier timings (ms)')
        for modifier in result['mods']:
            row = box.row(align=True)
            row.label(text=modifier['name'], icon='MODIFIER')
            value = modifier['ms']
            row.label(text='Disabled' if not modifier['enabled'] else '—' if value is None else f'{value:.2f}')


classes = (MBT_UL_scene_performance,)