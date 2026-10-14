"""Custom pie menus (data-driven, edited in the add-on preferences)."""

from . import data, keymap, ops, runtime, ui


def register():
    data.register()
    ui.register()
    ops.register()
    runtime.register()
    keymap.register()


def unregister():
    keymap.unregister()
    runtime.unregister()
    ops.unregister()
    ui.unregister()
    data.unregister()
