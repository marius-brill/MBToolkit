"""Hotkeys for the pie menus. Rebuilt whenever a pie's key settings change."""

import bpy

from ...core.addon import get_prefs

_items = []  # (keymap, keymap_item) pairs we own


def clear():
    for km, kmi in _items:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    _items.clear()


def rebuild():
    clear()
    kc = bpy.context.window_manager.keyconfigs.addon
    prefs = get_prefs()
    if kc is None or prefs is None:  # background mode, or prefs not ready yet
        return
    km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
    for pie in prefs.pies:
        if pie.key == "NONE":
            continue
        kmi = km.keymap_items.new("mbt.call_pie", pie.key, "PRESS", ctrl=pie.ctrl, shift=pie.shift, alt=pie.alt)
        kmi.properties.pie_name = pie.name
        _items.append((km, kmi))


def _delayed_init():
    rebuild()
    return None  # run once


def register():
    # Preferences are not reliably readable while register() is still running.
    bpy.app.timers.register(_delayed_init, first_interval=0.2)


def unregister():
    if bpy.app.timers.is_registered(_delayed_init):
        bpy.app.timers.unregister(_delayed_init)
    clear()
