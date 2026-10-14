"""Preferences UI for editing pie menus."""

import bpy

from ...core.registry import register_classes, unregister_classes
from .data import SLOT_NAMES

# Slot indices laid out like the pie itself (None = the middle).
GRID = ((4, 3, 5), (0, None, 1), (6, 2, 7))
DIRECTION_ICONS = {0: "TRIA_LEFT", 1: "TRIA_RIGHT", 2: "TRIA_DOWN", 3: "TRIA_UP"}


class MBT_UL_pies(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "name", text="", emboss=False, icon="MENU_PANEL")
        if item.key != "NONE":
            mods = ("Ctrl+" if item.ctrl else "") + ("Shift+" if item.shift else "") + ("Alt+" if item.alt else "")
            layout.label(text=mods + item.key)


def _draw_slot(box, prefs, slot, index):
    col = box.column(align=True)
    col.label(text=SLOT_NAMES[index], icon=DIRECTION_ICONS.get(index, "NONE"))
    col.prop(slot, "action", text="")
    if slot.action == "NONE":
        return
    col.separator()
    col.prop(slot, "label")
    col.prop(slot, "icon")
    if slot.action == "OPERATOR":
        col.prop(slot, "idname", text="Operator")
        col.prop(slot, "args")
    elif slot.action == "MENU":
        col.prop(slot, "idname", text="Menu ID")
    elif slot.action == "PIE":
        col.prop_search(slot, "idname", prefs, "pies", text="Pie")
    elif slot.action == "PYTHON":
        col.prop(slot, "code")


def draw_prefs(layout, prefs):
    layout.use_property_split = False

    # --- pie list + hotkey -------------------------------------------------
    top = layout.box()
    row = top.row()
    row.template_list("MBT_UL_pies", "", prefs, "pies", prefs, "pie_index", rows=3)
    col = row.column(align=True)
    col.operator("mbt.pie_add", icon="ADD", text="")
    col.operator("mbt.pie_remove", icon="REMOVE", text="")
    top.operator("mbt.pie_add_example", icon="PRESET_NEW")

    if not (0 <= prefs.pie_index < len(prefs.pies)):
        return
    pie = prefs.pies[prefs.pie_index]

    top.separator()
    row = top.row(align=True)
    row.prop(pie, "key", text="Hotkey")
    row.prop(pie, "ctrl", toggle=True)
    row.prop(pie, "shift", toggle=True)
    row.prop(pie, "alt", toggle=True)
    top.label(text="Works in the 3D Viewport: hold the key, release over a slot.", icon="INFO")

    # --- 3x3 grid that mirrors the pie -----------------------------------
    for grid_row in GRID:
        row = layout.row(align=True)
        for index in grid_row:
            cell = row.box()
            if index is None or index >= len(pie.slots):
                cell.label(text=pie.name, icon="MENU_PANEL")
            else:
                _draw_slot(cell, prefs, pie.slots[index], index)


classes = (MBT_UL_pies,)


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
