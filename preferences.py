import bpy
from bpy.props import CollectionProperty, EnumProperty, IntProperty, FloatProperty, StringProperty

# Try to import pie menus - if they fail, continue without them
try:
    from .features.pie_menus import ui as pie_ui
    from .features.pie_menus.data import MBT_PieMenu
    PIE_MENUS_AVAILABLE = True
except ImportError:
    PIE_MENUS_AVAILABLE = False

from .core.registry import register_classes, unregister_classes
from .core.addon import get_prefs


class MBT_ModifierFavorite(bpy.types.PropertyGroup):
    key: StringProperty()
    label: StringProperty()


class MBT_OT_modifier_favorite(bpy.types.Operator):
    bl_idname = 'mbt.modifier_favorite'
    bl_label = 'Edit Modifier Favorites'
    key: StringProperty()
    label: StringProperty()
    action: EnumProperty(items=[(x, x.title(), '') for x in ('TOGGLE', 'UP', 'DOWN', 'REMOVE')])
    index: IntProperty()

    def execute(self, context):
        prefs = get_prefs(context)
        if prefs is None:
            return {'CANCELLED'}
        favorites = prefs.modifier_favorites
        if self.action == 'TOGGLE':
            index = next((i for i, f in enumerate(favorites) if f.key == self.key), None)
            if index is None:
                item = favorites.add()
                item.key, item.label = self.key, self.label
            else:
                favorites.remove(index)
        elif 0 <= self.index < len(favorites):
            if self.action == 'REMOVE':
                favorites.remove(self.index)
            else:
                target = self.index + (-1 if self.action == 'UP' else 1)
                if 0 <= target < len(favorites):
                    favorites.move(self.index, target)
        context.preferences.is_dirty = True
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        return {'FINISHED'}


def draw_modifier_preferences(layout, prefs):
    from .features.modifier_list import catalog, entry_key, CATEGORIES
    layout.label(text='Favorite modifiers — toolbar order:')
    for index, favorite in enumerate(prefs.modifier_favorites):
        row = layout.row(align=True)
        row.label(text=favorite.label)
        for action, icon in (('UP', 'TRIA_UP'), ('DOWN', 'TRIA_DOWN'), ('REMOVE', 'X')):
            op = row.operator('mbt.modifier_favorite', text='', icon=icon)
            op.action, op.index = action, index
    layout.label(text='Choose favorites (availability depends on the active object type):')
    entries = {}
    for obj_type in ('MESH', 'CURVE', 'VOLUME', 'GREASEPENCIL', 'POINTCLOUD', 'LATTICE'):
        for entry in catalog(obj_type):
            entries[entry_key(entry)] = entry
    favorites = {f.key for f in prefs.modifier_favorites}
    row = layout.row()
    for category in CATEGORIES:
        col = row.column(align=True)
        col.label(text=category)
        for key, entry in entries.items():
            if entry['category'] == category:
                op = col.operator('mbt.modifier_favorite', text=entry['label'],
                                  icon=entry['icon'], depress=key in favorites)
                op.key, op.label, op.action = key, entry['label'], 'TOGGLE'


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
    modifier_favorites: CollectionProperty(type=MBT_ModifierFavorite)
    pie_index: IntProperty()
    tab: EnumProperty(
        items=(("MODIFIERS", "Modifiers", ""), ("PIES", "Pie Menus", ""), ("ABOUT", "About", "")),
        default="MODIFIERS",
    )

    def draw(self, context):
        layout = self.layout
        layout.row().prop(self, "tab", expand=True)
        
        # Draw UV tools settings
        if self.tab == 'MODIFIERS':
            draw_modifier_preferences(layout, self)
        elif self.tab == "PIES" and PIE_MENUS_AVAILABLE:
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



classes = (MBT_ModifierFavorite, MBT_OT_modifier_favorite, MBT_Preferences)


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
