"""Per-scene properties, available as `scene.mbt`."""

import bpy
from bpy.props import BoolProperty, EnumProperty, PointerProperty, StringProperty

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
    stats_show_modifiers: BoolProperty(
        name="Show Modifiers",
        description="Show the per-modifier cost under each object",
        default=False,
    )
    stats_sort: EnumProperty(
        name="Sort",
        items=(("TRIS", "Triangles", "Most triangles first"), ("PERF", "Performance", "Slowest first")),
        default="TRIS",
    )
    stats_detailed: BoolProperty(
        name="Per-modifier",
        description="Measure every modifier separately. Much slower than the quick per-object measurement",
        default=False,
    )


classes = (MBT_SceneProps,)


def register():
    register_classes(classes)
    bpy.types.Scene.mbt = PointerProperty(type=MBT_SceneProps)


def unregister():
    del bpy.types.Scene.mbt
    unregister_classes(classes)
