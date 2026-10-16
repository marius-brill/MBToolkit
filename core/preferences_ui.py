"""Shared shortcut capture and inline, grid-snapped favorite dragging."""

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty

from .addon import get_prefs


def shortcut_text(data, prefix=''):
    key = getattr(data, prefix + 'key')
    if key == 'NONE':
        return 'Click to assign shortcut'
    modifiers = [label for name, label in (('ctrl', 'Ctrl'), ('shift', 'Shift'),
                 ('alt', 'Alt'), ('oskey', 'OS')) if getattr(data, prefix + name, False)]
    return ' + '.join(modifiers + [key.replace('_', ' ').title()])


def draw_shortcut(layout, data, target='MODIFIER', index=-1):
    prefix = 'modifier_popup_' if target == 'MODIFIER' else ''
    row = layout.row(align=True)
    op = row.operator('mbt.capture_shortcut', text=shortcut_text(data, prefix), icon='EVENT_K')
    op.target, op.index = target, index
    op = row.operator('mbt.capture_shortcut', text='', icon='X')
    op.target, op.index, op.clear = target, index, True


def apply_shortcut(data, prefix, event=None):
    # Set key last so the final keymap rebuild sees the complete combination.
    for name in ('ctrl', 'shift', 'alt', 'oskey'):
        setattr(data, prefix + name, bool(getattr(event, name, False)))
    setattr(data, prefix + 'key', event.type if event else 'NONE')


class MBT_OT_capture_shortcut(bpy.types.Operator):
    bl_idname = 'mbt.capture_shortcut'
    bl_label = 'Press a Shortcut'
    bl_description = 'Click, then press a key combination; Escape cancels'
    target: EnumProperty(items=(('MODIFIER', 'Modifier Popup', ''), ('PIE', 'Pie', '')))
    index: IntProperty(default=-1)
    clear: BoolProperty(default=False)

    def _data(self, context):
        prefs = get_prefs(context)
        if prefs is None:
            return None, ''
        if self.target == 'MODIFIER':
            return prefs, 'modifier_popup_'
        return (prefs.pies[self.index], '') if 0 <= self.index < len(prefs.pies) else (None, '')

    def execute(self, context):
        data, prefix = self._data(context)
        if data is None:
            return {'CANCELLED'}
        apply_shortcut(data, prefix)
        context.preferences.is_dirty = True
        return {'FINISHED'}

    def invoke(self, context, event):
        if self.clear:
            return self.execute(context)
        if self._data(context)[0] is None:
            return {'CANCELLED'}
        self._area = context.area
        self._area.header_text_set('Press shortcut · Esc cancels · Backspace clears')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self.cancel(context)
            return {'CANCELLED'}
        if event.value != 'PRESS' or event.type in {
                'LEFT_SHIFT', 'RIGHT_SHIFT', 'LEFT_CTRL', 'RIGHT_CTRL',
                'LEFT_ALT', 'RIGHT_ALT', 'OSKEY', 'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE',
                'TIMER', 'WINDOW_DEACTIVATE'}:
            return {'RUNNING_MODAL'}
        valid = bpy.types.Event.bl_rna.properties['type'].enum_items.keys()
        if event.type not in valid:
            return {'RUNNING_MODAL'}
        data, prefix = self._data(context)
        if data is not None:
            apply_shortcut(data, prefix, None if event.type == 'BACK_SPACE' else event)
            context.preferences.is_dirty = True
        self.cancel(context)
        return {'FINISHED'}

    def cancel(self, context):
        try:
            self._area.header_text_set(None)
            self._area.tag_redraw()
        except ReferenceError:
            pass


def move_favorite(prefs, source, target):
    if 0 <= source < len(prefs.modifier_favorites) and 0 <= target < len(prefs.modifier_favorites):
        prefs.modifier_favorites.move(source, target)
        return True
    return False


_drag_sessions = []


def favorite_dragged(key):
    return any(session.key == key for session in _drag_sessions)


def draw_favorite_tiles(layout, prefs, entries):
    """Native buttons with equal, fixed widths, shared with the drag grid."""
    favorites = list(prefs.modifier_favorites)
    session = next((s for s in _drag_sessions if s._area == bpy.context.area), None)
    if session is not None and session._hover != session._source:
        favorites.insert(session._hover, favorites.pop(session._source))
    grid = layout.column(align=True)
    for start in range(0, len(favorites), 4):
        row = grid.row(align=True)
        row.alignment = 'LEFT'
        for favorite in favorites[start:start + 4]:
            tile = row.column(align=True)
            tile.ui_units_x = 8
            entry = entries.get(favorite.key)
            tile.prop(favorite, 'drag', text=favorite.label,
                      icon=entry['icon'] if entry else 'MODIFIER', toggle=True)


class MBT_OT_reorder_favorites(bpy.types.Operator):
    bl_idname = 'mbt.reorder_favorites'
    bl_label = 'Reorder Favorite'
    bl_description = 'Drag a favorite to its new position; release to finish, Escape cancels'
    bl_options = {'INTERNAL'}

    key: StringProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        prefs = get_prefs(context)
        if _drag_sessions or prefs is None or context.region is None:
            return {'CANCELLED'}
        self._original = tuple(f.key for f in prefs.modifier_favorites)
        self._source = next((i for i, f in enumerate(prefs.modifier_favorites)
                             if f.key == self.key), -1)
        if self._source < 0:
            return {'CANCELLED'}
        self._hover = self._source
        self._area, self._region, self._window = context.area, context.region, context.window
        self._origin = event.mouse_x, event.mouse_y
        # Layout units include DPI scaling; View2D accounts for Preferences zoom.
        unit = 20 * context.preferences.system.ui_scale
        x0, y0 = self._region.view2d.view_to_region(0, 0, clip=False)
        x1, y1 = self._region.view2d.view_to_region(unit, unit, clip=False)
        self._width, self._height = max(1, x1 - x0) * 8, max(1, y1 - y0)
        _drag_sessions.append(self)
        context.window_manager.modal_handler_add(self)
        self._window.cursor_modal_set('SCROLL_XY')
        self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def target(self, x, y, count):
        """Snap relative to the pressed tile, including across row boundaries."""
        col = self._source % 4 + round((x - self._origin[0]) / self._width)
        row = self._source // 4 - round((y - self._origin[1]) / self._height)
        if not 0 <= col < 4 or row < 0 or row * 4 + col >= count:
            return self._source
        return row * 4 + col

    def modal(self, context, event):
        prefs = get_prefs(context)
        if (self not in _drag_sessions or prefs is None or context.area != self._area or
                tuple(f.key for f in prefs.modifier_favorites) != self._original or
                event.type in {'ESC', 'RIGHTMOUSE', 'WINDOW_DEACTIVATE'}):
            self.cancel(context)
            return {'CANCELLED'}
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE', 'LEFTMOUSE'}:
            self._hover = self.target(event.mouse_x, event.mouse_y, len(self._original))
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                inside = (self._region.x <= event.mouse_x < self._region.x + self._region.width and
                          self._region.y <= event.mouse_y < self._region.y + self._region.height)
                if inside and self._hover != self._source:
                    move_favorite(prefs, self._source, self._hover)
                    context.preferences.is_dirty = True
                self._cleanup()
                for window in context.window_manager.windows:
                    for area in window.screen.areas:
                        area.tag_redraw()
                return {'FINISHED'}
            self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _cleanup(self):
        if self in _drag_sessions:
            _drag_sessions.remove(self)
        try:
            self._window.cursor_modal_restore()
            self._area.tag_redraw()
        except ReferenceError:
            pass

    def cancel(self, context):
        # Preview only: the collection is untouched until release.
        self._cleanup()


def cleanup():
    for session in tuple(_drag_sessions):
        session._cleanup()


classes = (MBT_OT_capture_shortcut, MBT_OT_reorder_favorites)
