"""Native Modifier Properties, favorites, overview and bottom-relative pins."""

from types import SimpleNamespace
from functools import lru_cache
import bpy
from bpy.app.handlers import persistent
from bpy.props import CollectionProperty, IntProperty, StringProperty, BoolProperty, EnumProperty

from ..core.addon import get_prefs
from ..core.registry import register_classes, unregister_classes

INDEX_PROPERTY = 'mbt_modifier_index'
SUPPORTED_TYPES = {'MESH', 'CURVE', 'CURVES', 'FONT', 'SURFACE', 'LATTICE',
                   'VOLUME', 'POINTCLOUD', 'GREASEPENCIL', 'EMPTY'}
CATEGORIES = ('Edit', 'Generate', 'Deform', 'Normals', 'Physics', 'Color')
_native_draw = None
_native_panel = None
_busy = False
_blocked = set()


def _editable(obj):
    return obj is not None and obj.is_editable


def _get_index(obj):
    return next((i for i, m in enumerate(obj.modifiers) if m == obj.modifiers.active), 0)


def _set_index(obj, index):
    if _editable(obj) and 0 <= index < len(obj.modifiers):
        try:
            obj.modifiers.active = obj.modifiers[index]
        except (AttributeError, TypeError, ValueError, RuntimeError):
            pass


class MBT_ModifierLock(bpy.types.PropertyGroup):
    uid: IntProperty()
    index: IntProperty(min=0)
    from_bottom: BoolProperty(default=False)


def _migrate_locks(obj):
    for lock in obj.mbt_modifier_locks:
        if not lock.from_bottom:
            modifier = next((m for m in obj.modifiers if m.persistent_uid == lock.uid), None)
            if modifier is not None:
                lock.index = len(obj.modifiers) - 1 - list(obj.modifiers).index(modifier)
            lock.from_bottom = True


def _signature(obj):
    return (obj.session_uid, tuple((m.persistent_uid, m.use_pin_to_last) for m in obj.modifiers),
            tuple((p.uid, p.index, p.from_bottom) for p in obj.mbt_modifier_locks))


def enforce_locks(obj):
    """Build one target permutation, retaining the unlocked modifiers' order."""
    if not _editable(obj) or not obj.mbt_modifier_locks:
        return
    _migrate_locks(obj)
    mods = list(obj.modifiers)
    by_uid = {m.persistent_uid: m for m in mods}
    for i in reversed(range(len(obj.mbt_modifier_locks))):
        if obj.mbt_modifier_locks[i].uid not in by_uid:
            obj.mbt_modifier_locks.remove(i)
    if not mods:
        return
    signature = _signature(obj)
    if signature in _blocked:
        return
    target = [None] * len(mods)
    locked = set()
    for lock in sorted(obj.mbt_modifier_locks, key=lambda p: (p.index, p.uid)):
        if lock.uid in locked:
            continue
        desired = max(0, len(mods)-1-lock.index)
        available = [i for i, item in enumerate(target) if item is None]
        slot = min(available, key=lambda i: (abs(i-desired), i))
        target[slot] = by_uid[lock.uid]
        locked.add(lock.uid)
    remaining = iter(m for m in mods if m.persistent_uid not in locked)
    target = [m if m is not None else next(remaining) for m in target]
    try:
        if any(m.use_pin_to_last for m in mods) and target != mods:
            raise ValueError('Native pin-to-last conflicts with bottom-relative pins')
        for index, modifier in enumerate(target):
            current = list(obj.modifiers).index(modifier)
            if current != index:
                obj.modifiers.move(current, index)
        if list(obj.modifiers) != target:
            raise ValueError('Blender rejected the requested modifier order')
    except (RuntimeError, ValueError, TypeError) as exc:
        _blocked.add(_signature(obj))
        print(f'MBToolkit: cannot enforce modifier locks on {obj.name}: {exc}')


def _enforce_pending():
    global _busy
    if _busy or bpy.app.is_job_running('RENDER'):
        return 0.2
    _busy = True
    try:
        for obj in tuple(bpy.data.objects):
            try:
                enforce_locks(obj)
            except (ReferenceError, RuntimeError, TypeError, ValueError) as exc:
                print(f'MBToolkit: modifier lock update skipped: {exc}')
    finally:
        _busy = False
    return None


@persistent
def _stack_changed(*args):
    if not _busy and not bpy.app.timers.is_registered(_enforce_pending):
        bpy.app.timers.register(_enforce_pending, first_interval=0.05)


@persistent
def _reset_locks(*args):
    _blocked.clear()
    _stack_changed()


class _Catalog:
    """Read installed native menu definitions without hardcoding compatibility."""
    def __init__(self, category, output):
        self.category, self.output = category, output

    def operator(self, idname, **kwargs):
        entry = {'category': self.category, 'operator': idname, 'args': {},
                 'label': kwargs.get('text', ''), 'icon': kwargs.get('icon', 'MODIFIER')}
        self.output.append(entry)

        class Arguments:
            def __setattr__(self, name, value):
                entry['args'][name] = value
        return Arguments()

    def template_modifier_asset_menu_items(self, **kwargs):
        # Dynamic catalogs are drawn directly in the real overview popup.
        pass


@lru_cache(maxsize=16)
def catalog(obj_type):
    from bl_ui import properties_data_modifier as native
    output = []
    for category in CATEGORIES:
        cls = getattr(native, 'OBJECT_MT_modifier_add_' + category.lower())
        proxy = SimpleNamespace(layout=_Catalog(category, output), bl_label=cls.bl_label,
                                operator_modifier_add=cls.operator_modifier_add,
                                operator_modifier_add_asset=cls.operator_modifier_add_asset)
        cls.draw(proxy, SimpleNamespace(object=SimpleNamespace(type=obj_type)))
    if obj_type in {'EMPTY', 'MESH', 'CURVE', 'CURVES', 'FONT', 'VOLUME', 'POINTCLOUD', 'GREASEPENCIL'}:
        output.append({'category': 'Generate', 'operator': 'object.modifier_add',
                       'args': {'type': 'NODES'}, 'label': 'Geometry Nodes', 'icon': 'GEOMETRY_NODES'})
    return output


def entry_key(entry):
    return entry['operator'] + ':' + str(entry['args'].get('type', entry['args'].get('relative_asset_identifier', '')))


def _add_button(layout, entry, obj, text=None):
    op = layout.operator('mbt.modifier_add', text=entry['label'] if text is None else text,
                         icon=entry['icon'])
    op.key = entry_key(entry)
    op.object_name = obj.name


class MBT_OT_modifier_add(bpy.types.Operator):
    bl_idname = 'mbt.modifier_add'
    bl_label = 'Add Modifier'
    bl_options = {'REGISTER', 'UNDO'}
    key: StringProperty()
    object_name: StringProperty()

    def execute(self, context):
        obj = bpy.data.objects.get(self.object_name)
        if not _editable(obj) or obj.mode != 'OBJECT' or obj.name not in context.view_layer.objects:
            self.report({'WARNING'}, 'Target must be an editable Object Mode object in this view layer')
            return {'CANCELLED'}
        entry = next((e for e in catalog(obj.type) if entry_key(e) == self.key), None)
        if entry is None:
            self.report({'WARNING'}, 'Modifier is unavailable for this object')
            return {'CANCELLED'}
        try:
            with context.temp_override(object=obj, active_object=obj, selected_objects=[obj],
                                       selected_editable_objects=[obj]):
                op = bpy.ops.object.modifier_add if entry['operator'] == 'object.modifier_add' else bpy.ops.object.modifier_add_node_group
                result = op('EXEC_DEFAULT', **entry['args'])
            enforce_locks(obj)
            return result
        except (RuntimeError, TypeError, ValueError) as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}


class MBT_OT_modifier_add_menu(bpy.types.Operator):
    bl_idname = 'mbt.modifier_add_menu'
    bl_label = 'Add Modifier'
    bl_description = 'All compatible modifiers arranged by category'

    @classmethod
    def poll(cls, context):
        obj = context.object
        return context.window is not None and _editable(obj) and obj.type in SUPPORTED_TYPES and obj.mode == 'OBJECT'

    def invoke(self, context, event):
        return bpy.ops.wm.call_menu(name='MBT_MT_modifier_overview')

    def execute(self, context):
        return bpy.ops.wm.call_menu(name='MBT_MT_modifier_overview')


class MBT_MT_modifier_overview(bpy.types.Menu):
    bl_idname = 'MBT_MT_modifier_overview'
    bl_label = 'Add Modifier'

    def draw(self, context):
        obj = context.object
        if obj is None:
            return
        entries = catalog(obj.type)
        self.layout.operator_context = 'EXEC_DEFAULT'
        columns = self.layout.row()
        for category in CATEGORIES:
            items = [e for e in entries if e['category'] == category]
            if not items:
                continue
            col = columns.column(align=True)
            col.ui_units_x = 13
            col.label(text=category)
            for entry in items:
                _add_button(col, entry, obj)
            col.template_modifier_asset_menu_items(catalog_path=category)


class MBT_OT_modifier_lock(bpy.types.Operator):
    bl_idname = 'mbt.modifier_lock'
    bl_label = 'Lock Modifier Position'
    bl_description = 'Keep this modifier at its current distance from the bottom (last, second-last, etc.)'
    bl_options = {'REGISTER', 'UNDO'}
    uid: IntProperty()

    def execute(self, context):
        obj = context.object
        if not _editable(obj):
            return {'CANCELLED'}
        _migrate_locks(obj)
        for i, lock in enumerate(obj.mbt_modifier_locks):
            if lock.uid == self.uid:
                obj.mbt_modifier_locks.remove(i)
                _blocked.clear()
                return {'FINISHED'}
        modifier = next((m for m in obj.modifiers if m.persistent_uid == self.uid), None)
        if modifier is None:
            return {'CANCELLED'}
        if any(m.use_pin_to_last for m in obj.modifiers):
            self.report({'WARNING'}, 'Disable native Pin to Last before using bottom-relative pins')
            return {'CANCELLED'}
        enforce_locks(obj)
        lock = obj.mbt_modifier_locks.add()
        lock.uid = self.uid
        lock.index = len(obj.modifiers)-1-list(obj.modifiers).index(modifier)
        lock.from_bottom = True
        _blocked.clear()
        return {'FINISHED'}


class MBT_OT_modifier_manage(bpy.types.Operator):
    bl_idname = 'mbt.modifier_manage'
    bl_label = 'Manage Modifier'
    bl_options = {'REGISTER', 'UNDO'}
    uid: IntProperty()
    action: EnumProperty(items=[(x, x.title(), '') for x in ('UP', 'DOWN', 'DELETE')])

    def execute(self, context):
        obj = context.object
        if not _editable(obj) or obj.mode != 'OBJECT':
            self.report({'WARNING'}, 'Requires an editable object in Object Mode')
            return {'CANCELLED'}
        enforce_locks(obj)
        modifier = next((m for m in obj.modifiers if m.persistent_uid == self.uid), None)
        if modifier is None:
            return {'CANCELLED'}
        try:
            if self.action == 'DELETE':
                with context.temp_override(object=obj, active_object=obj, selected_objects=[obj],
                                           selected_editable_objects=[obj]):
                    result = bpy.ops.object.modifier_remove(modifier=modifier.name, use_selected_objects=False)
                enforce_locks(obj)
                return result
            locked = {p.uid for p in obj.mbt_modifier_locks}
            if self.uid in locked:
                self.report({'WARNING'}, 'Unpin this modifier before moving it')
                return {'CANCELLED'}
            mods = list(obj.modifiers)
            available = [i for i, m in enumerate(mods) if m.persistent_uid not in locked]
            index = mods.index(modifier)
            position = available.index(index) + (-1 if self.action == 'UP' else 1)
            if not 0 <= position < len(available):
                return {'CANCELLED'}
            obj.modifiers.move(index, available[position])
            enforce_locks(obj)
            obj.modifiers.active = modifier
            return {'FINISHED'}
        except (RuntimeError, TypeError, ValueError) as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}


def _draw_property(layout, obj, modifier, name, **kwargs):
    if name in modifier.bl_rna.properties:
        row = layout.row(align=True)
        row.enabled = _editable(obj) and not modifier.is_property_readonly(name)
        row.prop(modifier, name, **kwargs)


class MBT_UL_modifiers(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0, flt_flag=0):
        if item is None:
            return
        if self.layout_type == 'GRID':
            layout.label(text='', icon='MODIFIER')
            return
        row = layout.row(align=True)
        _draw_property(row, data, item, 'name', text='', emboss=False, icon='MODIFIER')
        buttons = row.row(align=True)
        buttons.alignment = 'RIGHT'
        for name, icon in (('show_on_cage', 'MESH_DATA'), ('show_in_editmode', 'EDITMODE_HLT'),
                           ('show_viewport', 'RESTRICT_VIEW_OFF'), ('show_render', 'RESTRICT_RENDER_OFF')):
            _draw_property(buttons, data, item, name, text='', icon=icon, toggle=True)
        buttons.enabled = _editable(data)
        pinned = any(p.uid == item.persistent_uid for p in data.mbt_modifier_locks)
        buttons.operator('mbt.modifier_lock', text='', icon='PINNED' if pinned else 'UNPINNED',
                         depress=pinned).uid = item.persistent_uid
        delete = buttons.row(align=True)
        delete.enabled = _editable(data) and data.mode == 'OBJECT'
        op = delete.operator('mbt.modifier_manage', text='', icon='X')
        op.uid, op.action = item.persistent_uid, 'DELETE'


def draw(layout, context):
    obj = context.object
    if obj is None:
        return
    prefs = get_prefs(context)
    row = layout.row(align=True)
    if prefs is not None:
        entries = {entry_key(e): e for e in catalog(obj.type)}
        flow = row.column_flow(columns=2, align=True)
        for favorite in prefs.modifier_favorites:
            sub = flow.row(align=True)
            sub.scale_y = 3.0
            entry = entries.get(favorite.key)
            sub.enabled = entry is not None and _editable(obj) and obj.mode == 'OBJECT'
            if entry:
                _add_button(sub, entry, obj)
            else:
                sub.label(text=favorite.label, icon='MODIFIER')
    row.operator('mbt.open_prefs', text='', icon='PREFERENCES')
    layout.operator_context = 'INVOKE_DEFAULT'
    layout.operator('mbt.modifier_add_menu', icon='ADD')
    stack = layout.row()
    stack.template_list('MBT_UL_modifiers', '', obj, 'modifiers', obj, INDEX_PROPERTY, rows=4)
    controls = stack.column(align=True)
    active = obj.modifiers.active
    locked = {p.uid for p in obj.mbt_modifier_locks}
    for action, icon in (('UP', 'TRIA_UP'), ('DOWN', 'TRIA_DOWN')):
        sub = controls.row(align=True)
        sub.enabled = (_editable(obj) and obj.mode == 'OBJECT' and active is not None
                       and active.persistent_uid not in locked)
        op = sub.operator('mbt.modifier_manage', text='', icon=icon)
        op.uid, op.action = active.persistent_uid if active else 0, action
    if not _editable(obj):
        layout.label(text='Read-only object', icon='INFO')
    elif obj.mbt_modifier_locks and _signature(obj) in _blocked:
        layout.label(text='Position lock conflicts with native stack restrictions', icon='ERROR')


def _draw_native(self, context):
    draw(self.layout, context)
    self.layout.template_modifiers()


classes = (MBT_ModifierLock, MBT_UL_modifiers, MBT_OT_modifier_add,
           MBT_MT_modifier_overview, MBT_OT_modifier_add_menu, MBT_OT_modifier_lock, MBT_OT_modifier_manage)


def register():
    global _native_panel, _native_draw
    register_classes(classes)
    bpy.types.Object.mbt_modifier_index = IntProperty(get=_get_index, set=_set_index, min=0, options={'SKIP_SAVE'})
    bpy.types.Object.mbt_modifier_locks = CollectionProperty(type=MBT_ModifierLock)
    from bl_ui.properties_data_modifier import DATA_PT_modifiers
    _native_panel = DATA_PT_modifiers
    _native_draw = DATA_PT_modifiers.draw
    DATA_PT_modifiers.draw = _draw_native
    bpy.app.handlers.depsgraph_update_post.append(_stack_changed)
    for handlers in (bpy.app.handlers.load_post, bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        handlers.append(_reset_locks)
    _stack_changed()


def unregister():
    global _native_panel, _native_draw
    if _native_panel is not None and _native_panel.draw is _draw_native:
        _native_panel.draw = _native_draw
    _native_panel = _native_draw = None
    for handlers, callback in ((bpy.app.handlers.depsgraph_update_post, _stack_changed),
                              (bpy.app.handlers.load_post, _reset_locks),
                              (bpy.app.handlers.undo_post, _reset_locks),
                              (bpy.app.handlers.redo_post, _reset_locks)):
        if callback in handlers:
            handlers.remove(callback)
    if bpy.app.timers.is_registered(_enforce_pending):
        bpy.app.timers.unregister(_enforce_pending)
    _blocked.clear()
    catalog.cache_clear()
    del bpy.types.Object.mbt_modifier_locks
    del bpy.types.Object.mbt_modifier_index
    unregister_classes(classes)