import bpy

# This file lives in <root>.core, so the root package id is everything before the last dot.
# Works for extensions (bl_ext.user_default.mbtoolkit) and legacy installs alike.
ADDON_ID = __package__.rpartition(".")[0]


def get_prefs(context=None):
    """Return the add-on preferences, or None if not available (yet)."""
    context = context or bpy.context
    addon = context.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon else None
