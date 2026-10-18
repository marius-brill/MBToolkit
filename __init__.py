bl_info = {
    "name": "MBToolkit",
    "author": "Marius Brill",
    "version": (0, 3, 0),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > MBToolkit",
    "description": "Personal hard surface workflow toolkit",
    "category": "3D View",
}

"""
MBToolkit - personal hard surface workflow toolkit.

Every feature lives in its own module and exposes register()/unregister().
To add a feature: add its lazy module path to core.feature_manager.FEATURES.
Order matters: property groups must register before anything that uses them.
"""

from .core import props, ops, feature_manager, pie_data
from . import preferences
from .ui import panels

_modules = (props, ops, pie_data, preferences)


def register():
    for module in _modules:
        module.register()
    feature_manager.register()
    panels.register()


def unregister():
    feature_manager.unregister()
    panels.unregister()
    for module in reversed(_modules):
        module.unregister()
