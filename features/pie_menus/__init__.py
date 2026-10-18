"""Custom pie menus (data-driven, edited in the add-on preferences)."""

def register():
    from . import keymap, ops, runtime, ui
    ui.register()
    ops.register()
    runtime.register()
    keymap.register()


def unregister():
    from . import keymap, ops, runtime, ui
    keymap.unregister()
    runtime.unregister()
    ops.unregister()
    ui.unregister()
