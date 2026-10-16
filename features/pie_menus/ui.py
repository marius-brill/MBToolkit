"""Preferences UI for editing pie menus."""

import bpy

from ...core.registry import register_classes, unregister_classes
from .data import SLOT_NAMES
from ...core.preferences_ui import draw_shortcut, shortcut_text
from .actions import operator_rna

# Slot indices laid out like the pie itself (None = the middle).
GRID = ((4, 3, 5), (0, None, 1), (6, 2, 7))
DIRECTION_ICONS = {0: "TRIA_LEFT", 1: "TRIA_RIGHT", 2: "TRIA_DOWN", 3: "TRIA_UP"}


class MBT_UL_pies(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "name", text="", emboss=False, icon="MENU_PANEL")
        if item.key != "NONE":
            layout.label(text=shortcut_text(item))


def _draw_slot(box, prefs, slot, index):
    col = box.column(align=True)
    col.label(text=f'Edit slot · {SLOT_NAMES[index]}', icon=DIRECTION_ICONS.get(index, "NONE"))
    col.prop(slot, "action", text="Type")
    if slot.action == "NONE":
        return
    col.separator()
    col.prop(slot, "label")
    if slot.action == "OPERATOR":
        row = col.row(align=True)
        row.operator('mbt.pie_choose_action', text='Choose Blender Command', icon='VIEWZOOM').kind = 'OPERATOR'
        if slot.idname:
            row.operator('mbt.pie_action_options', text='Options', icon='PREFERENCES')
            try:
                col.label(text=operator_rna(slot.idname).name)
            except (AttributeError, RuntimeError, ValueError):
                col.label(text='Command unavailable', icon='ERROR')
    elif slot.action == "MENU":
        col.operator('mbt.pie_choose_action', text='Choose Blender Menu', icon='VIEWZOOM').kind = 'MENU'
        col.label(text=slot.idname or 'No menu assigned')
    elif slot.action == "PIE":
        col.prop_search(slot, "idname", prefs, "pies", text="Pie")
    elif slot.action == "PYTHON":
        col.prop(slot, "code")
    col.prop(slot, 'advanced', icon='TRIA_DOWN' if slot.advanced else 'TRIA_RIGHT', emboss=False)
    if slot.advanced:
        col.prop(slot, 'icon')
        if slot.action in {'OPERATOR', 'MENU'}:
            col.prop(slot, 'idname')
        if slot.action == 'OPERATOR':
            col.prop(slot, 'args')


def draw_prefs(layout, prefs):
    layout.use_property_split = False

    # --- pie list + hotkey -------------------------------------------------
    top = layout.box()
    row = top.row()
    row.template_list("MBT_UL_pies", "", prefs, "pies", prefs, "pie_index", rows=3)
    col = row.column(align=True)
    col.operator("mbt.pie_add", icon="ADD", text="")
    col.operator('mbt.pie_duplicate', icon='DUPLICATE', text='')
    col.operator("mbt.pie_remove", icon="REMOVE", text="")
    top.operator("mbt.pie_add_example", icon="PRESET_NEW")

    if not (0 <= prefs.pie_index < len(prefs.pies)):
        return
    pie = prefs.pies[prefs.pie_index]

    top.separator()
    top.prop(pie, 'name', text='Name')
    draw_shortcut(top, pie, target='PIE', index=prefs.pie_index)

    # --- 3x3 grid that mirrors the pie -----------------------------------
    for grid_row in GRID:
        row = layout.row(align=True)
        for index in grid_row:
            cell = row.box()
            if index is None or index >= len(pie.slots):
                cell.label(text=pie.name, icon="MENU_PANEL")
            else:
                slot = pie.slots[index]
                cell.label(text=SLOT_NAMES[index])
                op = cell.operator('mbt.pie_select_slot', text=slot.label or slot.idname or 'Empty',
                                   depress=index == pie.slot_index)
                op.index = index
    if 0 <= pie.slot_index < len(pie.slots):
        _draw_slot(layout.box(), prefs, pie.slots[pie.slot_index], pie.slot_index)


classes = (MBT_UL_pies,)


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
