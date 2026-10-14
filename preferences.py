import bpy
from bpy.props import CollectionProperty, EnumProperty, IntProperty, FloatProperty

# Try to import pie menus - if they fail, continue without them
try:
    from .features.pie_menus import ui as pie_ui
    from .features.pie_menus.data import MBT_PieMenu
    PIE_MENUS_AVAILABLE = True
except ImportError:
    PIE_MENUS_AVAILABLE = False

from .core.registry import register_classes, unregister_classes


class MBT_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__  # root package = add-on id

    # UV tools settings
    uv_angle_threshold: FloatProperty(
        name="UV Angle Threshold",
        description="Angle threshold for marking seams in UV tools (degrees)",
        default=70.0,
        min=0.0,
        max=180.0,
        step=1.0
    )

    pies: CollectionProperty(type=MBT_PieMenu)
    pie_index: IntProperty()
    tab: EnumProperty(
        items=(("PIES", "Pie Menus", ""), ("ABOUT", "About", "")),
        default="PIES",
    )

    def draw(self, context):
        layout = self.layout
        layout.row().prop(self, "tab", expand=True)
        
        # Draw UV tools settings
        if self.tab == "PIES" and PIE_MENUS_AVAILABLE:
            pie_ui.draw_prefs(layout, self)
        elif self.tab == "PIES":
            layout.label(text="Pie menus not available")
        else:
            layout.label(text="MBToolkit - personal hard surface workflow toolkit")
            layout.operator("mbt.rebuild_hotkeys", icon="FILE_REFRESH")
            
            # Add UV tools settings section
            layout.separator()
            layout.label(text="UV Tools Settings:")
            layout.prop(self, "uv_angle_threshold")



classes = (MBT_Preferences,)


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
