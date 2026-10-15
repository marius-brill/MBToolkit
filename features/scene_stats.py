"""Scene Performance feature entry point; results are runtime-only snapshots."""

from ..core.registry import register_classes, unregister_classes
from .scene_performance import runtime, ops, ui


classes = runtime.classes + ops.classes + ui.classes
draw = ui.draw


def register():
    register_classes(classes)
    runtime.register()


def unregister():
    runtime.unregister()
    unregister_classes(classes)