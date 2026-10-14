import bpy

from .addon import ADDON_ID
from .registry import register_classes, unregister_classes


class MBT_OT_open_prefs(bpy.types.Operator):
    bl_idname = "mbt.open_prefs"
    bl_label = "Add-on Customization"
    bl_description = "Open the MBToolkit preferences"

    def execute(self, context):
        bpy.ops.preferences.addon_show(module=ADDON_ID)
        return {"FINISHED"}


classes = (MBT_OT_open_prefs,)


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
