"""Run any .py file from disk, straight from the N panel."""

import os
import sys
import traceback

import bpy

from ..core.registry import register_classes, unregister_classes


class MBT_OT_script_run(bpy.types.Operator):
    bl_idname = "mbt.script_run"
    bl_label = "Run Script"
    bl_description = "Run the selected script (re-read from disk every time)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.mbt.script_path)

    def execute(self, context):
        path = os.path.abspath(bpy.path.abspath(context.scene.mbt.script_path))
        if not os.path.isfile(path):
            self.report({"ERROR"}, f"File not found: {path}")
            return {"CANCELLED"}

        with open(path, "r", encoding="utf-8") as f:
            source = f.read()

        script_dir = os.path.dirname(path)
        added = script_dir not in sys.path
        if added:
            sys.path.insert(0, script_dir)  # lets scripts import their neighbours
        try:
            exec(compile(source, path, "exec"), {"__name__": "__main__", "__file__": path})
        except Exception as exc:
            traceback.print_exc()
            self.report({"ERROR"}, f"{type(exc).__name__}: {exc} (see system console)")
            return {"CANCELLED"}
        finally:
            if added and script_dir in sys.path:
                sys.path.remove(script_dir)

        self.report({"INFO"}, f"Ran {os.path.basename(path)}")
        return {"FINISHED"}


classes = (MBT_OT_script_run,)


def draw(layout, context):
    props = context.scene.mbt
    layout.prop(props, "script_path", text="")
    layout.operator("mbt.script_run", icon="PLAY")


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
