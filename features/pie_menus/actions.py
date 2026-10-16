"""Search registered Blender actions and edit scalar operator options without execution."""

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       IntProperty, StringProperty)

from ...core.addon import get_prefs
from .data import parse_args


def selected_slot(context, pie_index=-1, slot_index=-1):
    prefs = get_prefs(context)
    if prefs is None:
        return None
    index = prefs.pie_index if pie_index < 0 else pie_index
    if not 0 <= index < len(prefs.pies):
        return None
    pie = prefs.pies[index]
    index = pie.slot_index if slot_index < 0 else slot_index
    return pie.slots[index] if 0 <= index < len(pie.slots) else None


def operator_rna(idname):
    category, name = idname.split('.', 1)
    return getattr(getattr(bpy.ops, category), name).get_rna_type()


def action_items(kind):
    items = []
    if kind == 'OPERATOR':
        for category in dir(bpy.ops):
            for name in dir(getattr(bpy.ops, category)):
                idname = f'{category}.{name}'
                try:
                    rna = operator_rna(idname)
                    items.append((idname, f'{rna.name}  ·  {idname}', rna.description or idname))
                except (AttributeError, RuntimeError, ValueError):
                    continue
    else:
        for name in dir(bpy.types):
            cls = getattr(bpy.types, name)
            if isinstance(cls, type) and issubclass(cls, bpy.types.Menu) and cls != bpy.types.Menu:
                items.append((getattr(cls, 'bl_idname', '') or name,
                              f'{getattr(cls, "bl_label", name)}  ·  {name}', name))
    return sorted(items, key=lambda item: item[1].casefold())


_search_items = {'OPERATOR': [], 'MENU': []}


def _choices(self, context):
    return _search_items[self.kind]


class MBT_OT_pie_choose_action(bpy.types.Operator):
    bl_idname = 'mbt.pie_choose_action'
    bl_label = 'Choose Blender Action'
    bl_property = 'choice'
    kind: EnumProperty(items=(('OPERATOR', 'Command', ''), ('MENU', 'Menu', '')))
    choice: EnumProperty(items=_choices)
    pie_index: IntProperty(default=-1)
    slot_index: IntProperty(default=-1)

    def invoke(self, context, event):
        _search_items[self.kind] = action_items(self.kind)
        prefs = get_prefs(context)
        self.pie_index = prefs.pie_index
        self.slot_index = prefs.pies[prefs.pie_index].slot_index
        context.window_manager.invoke_search_popup(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        slot = selected_slot(context, self.pie_index, self.slot_index)
        if slot is None or not self.choice:
            return {'CANCELLED'}
        slot.action, slot.idname, slot.args = self.kind, self.choice, ''
        slot.label = (operator_rna(self.choice).name if self.kind == 'OPERATOR' else
                      next((item[1].split('  ·  ')[0] for item in _search_items['MENU']
                            if item[0] == self.choice), self.choice))
        context.preferences.is_dirty = True
        return {'FINISHED'}


_enum_strings = {}


def _argument_choices(self, context):
    try:
        prop = operator_rna(self.operator_id).properties[self.identifier]
        key = (self.operator_id, self.identifier)
        _enum_strings[key] = [(item.identifier, item.name, item.description)
                              for item in prop.enum_items]
        return _enum_strings[key]
    except (KeyError, AttributeError, RuntimeError, ValueError):
        return []


class MBT_PieArgument(bpy.types.PropertyGroup):
    identifier: StringProperty()
    label: StringProperty()
    kind: StringProperty()
    operator_id: StringProperty()
    enabled: BoolProperty(name='Override', default=False)
    boolean: BoolProperty()
    integer: IntProperty()
    number: FloatProperty()
    text: StringProperty()
    enum: EnumProperty(items=_argument_choices)


FIELDS = {'BOOLEAN': 'boolean', 'INT': 'integer', 'FLOAT': 'number', 'STRING': 'text', 'ENUM': 'enum'}


class MBT_OT_pie_action_options(bpy.types.Operator):
    bl_idname = 'mbt.pie_action_options'
    bl_label = 'Command Options'
    arguments: CollectionProperty(type=MBT_PieArgument)
    pie_index: IntProperty(default=-1)
    slot_index: IntProperty(default=-1)
    _remaining = None

    def invoke(self, context, event):
        prefs = get_prefs(context)
        self.pie_index = prefs.pie_index
        self.slot_index = prefs.pies[prefs.pie_index].slot_index
        slot = selected_slot(context, self.pie_index, self.slot_index)
        values = parse_args(slot.args)
        if values is None:
            self.report({'WARNING'}, 'Fix invalid Advanced arguments first')
            return {'CANCELLED'}
        try:
            properties = operator_rna(slot.idname).properties
        except (AttributeError, ValueError, RuntimeError):
            return {'CANCELLED'}
        self.arguments.clear()
        self._remaining = dict(values)
        for prop in properties:
            if (prop.identifier == 'rna_type' or prop.type not in FIELDS or prop.is_hidden
                    or getattr(prop, 'is_array', False) or getattr(prop, 'is_enum_flag', False)):
                continue
            arg = self.arguments.add()
            arg.identifier, arg.label, arg.kind = prop.identifier, prop.name, prop.type
            arg.operator_id = slot.idname
            value = values.get(prop.identifier, prop.default)
            try:
                setattr(arg, FIELDS[prop.type], value)
                arg.enabled = prop.identifier in values
                self._remaining.pop(prop.identifier, None)
            except (TypeError, ValueError):
                self.arguments.remove(len(self.arguments)-1)
        return context.window_manager.invoke_props_dialog(self, width=460)

    def draw(self, context):
        self.layout.label(text='Enable an override to store it; unchecked values use Blender defaults')
        for arg in self.arguments:
            row = self.layout.row(align=True)
            row.prop(arg, 'enabled', text='')
            value = row.row()
            value.enabled = arg.enabled
            value.prop(arg, FIELDS[arg.kind], text=arg.label)
        if not self.arguments:
            self.layout.label(text='No simple options; use Advanced for complex arguments')

    def execute(self, context):
        slot = selected_slot(context, self.pie_index, self.slot_index)
        if slot is None:
            return {'CANCELLED'}
        values = dict(self._remaining or {})
        for arg in self.arguments:
            if arg.enabled:
                values[arg.identifier] = getattr(arg, FIELDS[arg.kind])
        slot.args = ', '.join(f'{name}={value!r}' for name, value in values.items())
        context.preferences.is_dirty = True
        return {'FINISHED'}


class MBT_OT_pie_select_slot(bpy.types.Operator):
    bl_idname = 'mbt.pie_select_slot'
    bl_label = 'Edit Pie Slot'
    index: IntProperty(min=0, max=7)

    def execute(self, context):
        prefs = get_prefs(context)
        prefs.pies[prefs.pie_index].slot_index = self.index
        return {'FINISHED'}


classes = (MBT_PieArgument, MBT_OT_pie_choose_action, MBT_OT_pie_action_options, MBT_OT_pie_select_slot)