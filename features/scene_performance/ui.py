"""Cached-results-only drawing; no evaluation or Blender datablock mutation."""

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
        pass

    def filter_items(self, context, data, propname):
        # UIList uses this hook for ordering even though no filtering is exposed.
        indices = rt.presentation(context)['indices']
        order = [0] * len(indices)
        for rank, index in enumerate(indices):
            order[index] = rank
        return [], order

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname,
                  index=0, flt_flag=0):
        row = layout.row(align=True)
        row.alert = (bool(item.error) or item.tris > rt.setting(context, 'stats_tri_budget')
                     or item.ms > rt.setting(context, 'stats_ms_budget'))
        split = row.split(factor=0.55, align=True)
        op = split.operator('mbt.stats_activate', text=item.name,
                            icon='ERROR' if item.error else 'OBJECT_DATA',
                            emboss=False, depress=item.selected)
        op.uid = item.uid
        numbers = split.row(align=True)
        numbers.label(text=fmt_tris(item.tris))
        numbers.label(text='—' if item.ms < 0 else f'{item.ms:.2f}')


def draw(layout, context):
    rt.watch(context)
    props = context.scene.mbt
    ui = rt.state(context, create=False)
    if ui is None:
        layout.label(text='Initializing viewport session…')
        layout.operator('mbt.stats_initialize', icon='FILE_REFRESH')
        return
    settings = layout.column(align=True)
    settings.enabled = not ui.running
    settings.prop(props, 'stats_scope', text='')
    if props.stats_scope == 'COLLECTION':
        settings.prop(props, 'stats_recursive')
    row = layout.row(align=True)
    row.prop(ui, 'auto', text='Auto', toggle=True)
    row.operator('mbt.stats_refresh', icon='FILE_REFRESH')
    if ui.running:
        row.operator('mbt.stats_cancel', text='', icon='CANCEL')
        layout.progress(factor=ui.progress, type='BAR', text=ui.status)
    else:
        layout.label(text=ui.status, icon='ERROR' if ui.phase == 'ERROR' else 'INFO')
    model = rt.presentation(context)
    header = layout.row(align=True)
    header.label(text=f'{len(ui.rows)} objects · {fmt_tris(model["total_tris"])} tris')
    sort = header.row(align=True)
    sort.prop_enum(ui, 'sort', 'TRIS')
    sort.prop_enum(ui, 'sort', 'PERF')
    header = layout.row(align=True)
    header.label(text='Object')
    header.label(text='Tris / Mod. ms')
    layout.template_list('MBT_UL_scene_performance', ui.name, ui, 'rows', ui, 'index', rows=7, maxrows=14)
    if not ui.rows:
        layout.label(text='No objects in this scope')
    active, result = rt.active_result(context)
    if active is None or result is None:
        return
    box = layout.box()
    row = box.row(align=True)
    row.label(text=active.obj.name if active.obj else active.name, icon='OBJECT_DATA')
    row.operator('mbt.stats_properties', text='', icon='MODIFIER')
    if active.error:
        box.label(text=active.error, icon='ERROR')
        return
    for modifier in result['mods']:
        row = box.row(align=True)
        row.label(text=modifier['name'], icon='MODIFIER')
        value = modifier['ms']
        row.label(text='Disabled' if not modifier['enabled'] else '—' if value is None else f'{value:.2f}')


classes = (MBT_UL_scene_performance,)