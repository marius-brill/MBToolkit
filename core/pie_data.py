"""Property groups that store pie menu definitions in the add-on preferences."""

import ast

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, StringProperty, IntProperty

from .registry import register_classes, unregister_classes

SLOT_COUNT = 8
# Blender fills pie slots in this order.
SLOT_NAMES = ("Left", "Right", "Bottom", "Top", "Top Left", "Top Right", "Bottom Left", "Bottom Right")

ACTION_ITEMS = (
    ("NONE", "Empty", "Leave this slot empty"),
    ("OPERATOR", "Operator", "Run a Blender operator, e.g. object.mode_set"),
    ("MENU", "Menu", "Open a Blender menu by its id, e.g. VIEW3D_MT_add"),
    ("PIE", "Pie Menu", "Open another MBToolkit pie menu"),
    ("PYTHON", "Python", "Run a single line of Python"),
)


def _key_items():
    try:
        items = bpy.types.Event.bl_rna.properties["type"].enum_items
        return [(i.identifier, i.name, "") for i in items]
    except Exception:
        return [("NONE", "None", ""), ("Q", "Q", ""), ("W", "W", ""), ("E", "E", "")]


KEY_ITEMS = _key_items()  # must stay referenced for the lifetime of the enum


def parse_args(text):
    """'mode=\"EDIT\", use_x=True' -> {'mode': 'EDIT', 'use_x': True}. Returns None on error."""
    text = text.strip()
    if not text:
        return {}
    try:
        tree = ast.parse(f"f({text})", mode="eval")
        if tree.body.args or any(kw.arg is None for kw in tree.body.keywords):
            return None
        return {kw.arg: ast.literal_eval(kw.value) for kw in tree.body.keywords}
    except Exception:
        return None


def _hotkey_changed(self, context):
    from .feature_manager import is_enabled
    if is_enabled('pie_menus'):
        from ..features.pie_menus import keymap
        keymap.rebuild()


class MBT_PieSlot(bpy.types.PropertyGroup):
    action: EnumProperty(name="Action", items=ACTION_ITEMS, default="NONE")
    label: StringProperty(name="Label")
    icon: StringProperty(name="Icon", description="Blender icon id, e.g. EDITMODE_HLT")
    idname: StringProperty(name="ID", description="Operator id, menu id or pie name depending on the action")
    args: StringProperty(name="Arguments", description="Operator arguments, e.g. mode='EDIT'")
    code: StringProperty(name="Code", description="One line of Python. 'bpy' and 'C' (context) are available")
    advanced: BoolProperty(name='Advanced', default=False)


class MBT_PieMenu(bpy.types.PropertyGroup):
    name: StringProperty(name="Name", default="Pie", update=_hotkey_changed)
    key: EnumProperty(name="Key", items=KEY_ITEMS, default="NONE", update=_hotkey_changed)
    ctrl: BoolProperty(name="Ctrl", update=_hotkey_changed)
    shift: BoolProperty(name="Shift", update=_hotkey_changed)
    alt: BoolProperty(name="Alt", update=_hotkey_changed)
    oskey: BoolProperty(name='OS Key', update=_hotkey_changed)
    slot_index: IntProperty(default=0, min=0, max=7)
    slots: CollectionProperty(type=MBT_PieSlot)


classes = (MBT_PieSlot, MBT_PieMenu)


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
