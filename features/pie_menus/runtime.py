"""The pie menu that gets drawn from the stored definitions."""

import bpy

from ...core.addon import get_prefs
from ...core.registry import register_classes, unregister_classes
from .data import parse_args

active = {"name": ""}  # which stored pie MBT_MT_pie should draw right now


def find_pie(prefs, name):
    for pie in prefs.pies:
        if pie.name == name:
            return pie
    return None


def _valid_icons():
    try:
        return set(bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items.keys())
    except Exception:
        return set()


ICONS = _valid_icons()


def draw_slot(pie, pie_def, slot, index):
    icon = slot.icon if slot.icon in ICONS else "NONE"
    action = slot.action
    text = slot.label or slot.idname

    if action == "NONE":
        pie.separator()
        return

    try:
        if action == "OPERATOR":
            args = parse_args(slot.args)
            if args is None:
                pie.label(text="Bad arguments", icon="ERROR")
                return
            op = pie.operator(slot.idname, text=text, icon=icon)
            for key, value in args.items():
                setattr(op, key, value)
        elif action == "MENU":
            op = pie.operator("wm.call_menu", text=text, icon=icon)
            op.name = slot.idname
        elif action == "PIE":
            op = pie.operator("mbt.call_pie", text=text, icon=icon)
            op.pie_name = slot.idname
        elif action == "PYTHON":
            op = pie.operator("mbt.run_slot_code", text=text or "Python", icon=icon)
            op.pie_name = pie_def.name
            op.slot_index = index
    except Exception:
        pie.label(text=f"Invalid: {slot.idname}", icon="ERROR")


class MBT_MT_pie(bpy.types.Menu):
    bl_idname = "MBT_MT_pie"
    bl_label = "MBToolkit"

    def draw(self, context):
        pie = self.layout.menu_pie()
        pie.operator_context = 'INVOKE_REGION_WIN'
        prefs = get_prefs(context)
        pie_def = find_pie(prefs, active["name"]) if prefs else None
        if pie_def is None:
            pie.label(text="Pie not found", icon="ERROR")
            return
        for index, slot in enumerate(pie_def.slots):
            draw_slot(pie, pie_def, slot, index)


classes = (MBT_MT_pie,)


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
