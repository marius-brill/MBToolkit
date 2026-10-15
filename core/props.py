"""Per-scene properties, available as `scene.mbt`."""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty

from .registry import register_classes, unregister_classes


class MBT_SceneProps(bpy.types.PropertyGroup):
    script_path: StringProperty(
        name="Script",
        description="Python script to run",
        subtype="FILE_PATH",
    )
    rename_base: StringProperty(
        name="Base Name",
        description="Selected objects become <base>_001, <base>_002, ...",
        default="Object",
    )
    stats_scope: EnumProperty(name="Scope", items=(
        ('VISIBLE', 'Visible in View Layer', 'Visible objects, respecting viewport Local View'),
        ('SELECTED', 'Selected Objects', 'Selected objects in the current view layer'),
        ('COLLECTION', 'Active Collection', 'Objects in the active collection and current view layer')))
    stats_recursive: BoolProperty(name="Include Child Collections", default=True)
    stats_timings: BoolProperty(name="Native Modifier Timings", default=True,
        description="Read timings from the last evaluated stack; diagnostic values, not frame time")
    stats_tri_budget: IntProperty(name="Triangle Budget", default=1000000, min=1)
    stats_ms_budget: FloatProperty(name="Modifier Budget (ms)", default=16.0, min=0.01,
        description="Highlight objects above this sum of modifier timings; not a frame-time budget")
    stats_options: BoolProperty(name="Options and Metric Help", default=False)


classes = (MBT_SceneProps,)


def register():
    register_classes(classes)
    bpy.types.Scene.mbt = PointerProperty(type=MBT_SceneProps)


def unregister():
    del bpy.types.Scene.mbt
    unregister_classes(classes)
