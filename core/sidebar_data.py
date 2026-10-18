"""Sidebar preference storage without the optional manager runtime."""

import sys
import bpy
from bpy.props import BoolProperty
from .addon import ADDON_ID


def changed(self, context):
    module = sys.modules.get(f'{ADDON_ID}.features.n_panel')
    if module is not None and module._running:
        module.changed(self, context)
    elif context is not None:
        context.preferences.is_dirty = True


class MBT_NPanelTab(bpy.types.PropertyGroup):
    visible: BoolProperty(name='Visible', default=True, update=changed,
        description='Show this entire sidebar tab, preserving its normal context checks')