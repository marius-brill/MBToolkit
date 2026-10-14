"""Rename all selected objects to basename_001, basename_002, ..."""

import bpy

from ..core.registry import register_classes, unregister_classes


class MBT_OT_rename_incremental(bpy.types.Operator):
    bl_idname = "mbt.rename_incremental"
    bl_label = "Rename Selected"
    bl_description = "Rename selected objects to <base>_001, <base>_002, ... (ordered by current name)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        base = context.scene.mbt.rename_base.strip()
        if not base:
            self.report({"ERROR"}, "Enter a base name first")
            return {"CANCELLED"}

        objs = sorted(context.selected_objects, key=lambda o: o.name)
        selected = {o.name for o in objs}
        taken = {o.name for o in bpy.data.objects if o.name not in selected}

        # Pass 1: park everything on temp names so targets can't collide with each other.
        for i, obj in enumerate(objs):
            obj.name = f"__mbt_tmp_{i}"

        # Pass 2: assign final names, skipping numbers used by unselected objects.
        n = 1
        for obj in objs:
            while f"{base}_{n:03d}" in taken:
                n += 1
            obj.name = f"{base}_{n:03d}"
            n += 1

        self.report({"INFO"}, f"Renamed {len(objs)} objects")
        return {"FINISHED"}


classes = (MBT_OT_rename_incremental,)


def draw(layout, context):
    layout.prop(context.scene.mbt, "rename_base", text="")
    layout.operator("mbt.rename_incremental", icon="SORTALPHA")


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
