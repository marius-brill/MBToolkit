"""N panel (3D Viewport sidebar, tab 'MBToolkit')."""

import bpy

from ..core.registry import register_classes, unregister_classes
from ..features import align, rename, scene_stats, script_runner, geonodes, resample


class MBT_PT_main(bpy.types.Panel):
    bl_idname = "MBT_PT_main"
    bl_label = "MBToolkit"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MBToolkit"

    def draw(self, context):
        self.layout.operator("mbt.open_prefs", icon="PREFERENCES")


class _SubPanel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MBToolkit"
    bl_parent_id = "MBT_PT_main"


class MBT_PT_script_runner(_SubPanel, bpy.types.Panel):
    bl_idname = "MBT_PT_script_runner"
    bl_label = "Script Runner"

    def draw(self, context):
        script_runner.draw(self.layout, context)


class MBT_PT_tools(_SubPanel, bpy.types.Panel):
    bl_idname = "MBT_PT_tools"
    bl_label = "Tools"

    def draw(self, context):
        layout = self.layout

        layout.separator()
        layout.label(text="Incremental Rename")
        rename.draw(layout, context)
        
        layout.separator()
        layout.label(text="Clean Up")
        layout.operator("mbt.clean_up", icon="TRIA_DOWN_BAR")


class MBT_PT_align(_SubPanel, bpy.types.Panel):
    bl_idname = "MBT_PT_align"
    bl_label = "Align"

    def draw(self, context):
        align.draw(self.layout, context)


class MBT_PT_resample(_SubPanel, bpy.types.Panel):
    bl_idname = "MBT_PT_resample"
    bl_label = "Resample"

    def draw(self, context):
        resample.draw(self.layout, context)


class MBT_PT_low_to_high(_SubPanel, bpy.types.Panel):
    bl_idname = "MBT_PT_low_to_high"
    bl_label = "Low to High"

    def draw(self, context):
        try:
            from ..features.geonodes import dynabool, crease_by_angle, sdf_remesh
            dynabool.draw(self.layout, context)
            crease_by_angle.draw(self.layout, context)
            sdf_remesh.draw(self.layout, context)
        except ImportError:
            pass  # Skip if geonodes modules are not available


class MBT_PT_uv(_SubPanel, bpy.types.Panel):
    bl_idname = "MBT_PT_uv"
    bl_label = "UV"

    def draw(self, context):
        layout = self.layout
        # Add UV related operators here
        layout.label(text="UV Tools")
        # Placeholder for future UV functionality
        try:
            from ..features import uv_tools
            uv_tools.draw(self.layout, context)
        except ImportError:
            pass  # Skip if geonodes modules are not available


class MBT_PT_bake(_SubPanel, bpy.types.Panel):
    bl_idname = "MBT_PT_bake"
    bl_label = "Bake"

    def draw(self, context):
        layout = self.layout
        # Add bake related operators here
        layout.label(text="Bake Tools")
        # Placeholder for future bake functionality


class MBT_PT_scene_stats(_SubPanel, bpy.types.Panel):
    bl_idname = "MBT_PT_scene_stats"
    bl_label = "Scene Performance"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        scene_stats.draw(self.layout, context)


# Classes order determines order in n-panel
classes = (
    MBT_PT_main,
    MBT_PT_tools,
    MBT_PT_align,
    MBT_PT_resample,
    MBT_PT_script_runner,
    MBT_PT_low_to_high,
    MBT_PT_uv,
    MBT_PT_bake,
    MBT_PT_scene_stats,
)


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)