import bpy

class OBJECT_UL_simple_modifier_list(bpy.types.UIList):
    """Custom UIList to display object modifiers cleanly"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "name", text="", emboss=False, icon='MODIFIER')
            layout.prop(item, "show_viewport", text="")

def draw(layout, context):
    """Drawing function called by your main UI panel module"""
    obj = context.active_object
    scene = context.scene

    if not obj:
        layout.label(text="No active object")
        return

    # Index in der Szene speichern statt direkt im Objekt-Datenblock
    if "mbt_active_modifier_index" not in scene:
        scene["mbt_active_modifier_index"] = 0

    # 1. Draw the Modifier List UIList
    row = layout.row()
    row.template_list(
        "OBJECT_UL_simple_modifier_list", 
        "", 
        obj, 
        "modifiers", 
        scene, 
        '["mbt_active_modifier_index"]', 
        rows=4
    )

    # 2. Add quick management buttons next to the list
    col = row.column(align=True)
    col.operator("object.modifier_add", icon='ADD', text="")
    
    # Make sure an active modifier exists before drawing its settings
    idx = scene.get("mbt_active_modifier_index", 0)
    if obj.modifiers and 0 <= idx < len(obj.modifiers):
        layout.separator()
        active_mod = obj.modifiers[idx]
        box = layout.box()
        box.template_modifier(active_mod)

# Registration
classes = (
    OBJECT_UL_simple_modifier_list,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)