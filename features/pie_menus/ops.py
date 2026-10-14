import bpy
from bpy.props import IntProperty, StringProperty

from ...core.addon import get_prefs
from ...core.registry import register_classes, unregister_classes
from . import runtime
from .data import SLOT_COUNT


class MBT_OT_call_pie(bpy.types.Operator):
    bl_idname = "mbt.call_pie"
    bl_label = "Call MBToolkit Pie"
    bl_options = {"INTERNAL"}

    pie_name: StringProperty()

    def invoke(self, context, event):
        runtime.active["name"] = self.pie_name
        bpy.ops.wm.call_menu_pie(name="MBT_MT_pie")
        return {"FINISHED"}


class MBT_OT_run_slot_code(bpy.types.Operator):
    bl_idname = "mbt.run_slot_code"
    bl_label = "Run Pie Code"
    bl_options = {"REGISTER", "UNDO"}

    pie_name: StringProperty()
    slot_index: IntProperty()

    def execute(self, context):
        prefs = get_prefs(context)
        pie = runtime.find_pie(prefs, self.pie_name) if prefs else None
        if pie is None or self.slot_index >= len(pie.slots):
            return {"CANCELLED"}
        try:
            exec(pie.slots[self.slot_index].code, {"bpy": bpy, "C": context})
        except Exception as exc:
            self.report({"ERROR"}, f"{type(exc).__name__}: {exc}")
            return {"CANCELLED"}
        return {"FINISHED"}


def _unique_name(prefs, base):
    names = {p.name for p in prefs.pies}
    if base not in names:
        return base
    i = 1
    while f"{base} {i}" in names:
        i += 1
    return f"{base} {i}"


def _new_pie(prefs, base="Pie"):
    pie = prefs.pies.add()
    pie.name = _unique_name(prefs, base)
    for _ in range(SLOT_COUNT):
        pie.slots.add()
    prefs.pie_index = len(prefs.pies) - 1
    return pie


def _set_slot(pie, index, action, label="", icon="", idname="", args=""):
    slot = pie.slots[index]
    slot.action, slot.label, slot.icon, slot.idname, slot.args = action, label, icon, idname, args


class MBT_OT_pie_add(bpy.types.Operator):
    bl_idname = "mbt.pie_add"
    bl_label = "Add Pie Menu"

    def execute(self, context):
        _new_pie(get_prefs(context))
        return {"FINISHED"}


class MBT_OT_pie_remove(bpy.types.Operator):
    bl_idname = "mbt.pie_remove"
    bl_label = "Remove Pie Menu"

    @classmethod
    def poll(cls, context):
        prefs = get_prefs(context)
        return bool(prefs and prefs.pies)

    def execute(self, context):
        from . import keymap

        prefs = get_prefs(context)
        prefs.pies.remove(prefs.pie_index)
        prefs.pie_index = max(0, min(prefs.pie_index, len(prefs.pies) - 1))
        keymap.rebuild()
        return {"FINISHED"}


class MBT_OT_pie_add_example(bpy.types.Operator):
    bl_idname = "mbt.pie_add_example"
    bl_label = "Add Example Pie"
    bl_description = "Add a starter pie (modes + SDF remesh). Assign a hotkey to it afterwards"

    def execute(self, context):
        pie = _new_pie(get_prefs(context), "Quick Tools")
        _set_slot(pie, 0, "OPERATOR", "Edit", "EDITMODE_HLT", "object.mode_set", "mode='EDIT'")
        _set_slot(pie, 1, "OPERATOR", "Object", "OBJECT_DATAMODE", "object.mode_set", "mode='OBJECT'")
        _set_slot(pie, 2, "OPERATOR", "Sculpt", "SCULPTMODE_HLT", "object.mode_set", "mode='SCULPT'")
        _set_slot(pie, 3, "OPERATOR", "SDF Remesh", "MOD_REMESH", "mbt.add_sdf_remesh")
        _set_slot(pie, 4, "MENU", "Add", "ADD", "VIEW3D_MT_add")
        return {"FINISHED"}


class MBT_OT_rebuild_hotkeys(bpy.types.Operator):
    bl_idname = "mbt.rebuild_hotkeys"
    bl_label = "Rebuild Hotkeys"

    def execute(self, context):
        from . import keymap

        keymap.rebuild()
        return {"FINISHED"}


classes = (
    MBT_OT_call_pie,
    MBT_OT_run_slot_code,
    MBT_OT_pie_add,
    MBT_OT_pie_remove,
    MBT_OT_pie_add_example,
    MBT_OT_rebuild_hotkeys,
)


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
