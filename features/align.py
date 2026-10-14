"""Align tools: drop to ground, move to target."""

import bpy
from bpy.props import BoolProperty
from mathutils import Vector

from ..core.registry import register_classes, unregister_classes


def _has_selected_ancestor(obj, selected):
    parent = obj.parent
    while parent is not None:
        if parent in selected:
            return True
        parent = parent.parent
    return False


def _world_min_z(obj, depsgraph):
    """Lowest world-space Z of the evaluated bounding box (includes modifiers)."""
    ev = obj.evaluated_get(depsgraph)
    mw = ev.matrix_world
    return min((mw @ Vector(corner)).z for corner in ev.bound_box)


def _set_world_translation(obj, location=None, dz=0.0):
    mw = obj.matrix_world.copy()
    if location is not None:
        mw.translation = location
    mw.translation.z += dz
    obj.matrix_world = mw


class MBT_OT_to_ground(bpy.types.Operator):
    bl_idname = "mbt.to_ground"
    bl_label = "To Ground"
    bl_description = "Move selected objects along Z so the bottom of their bounding box sits on the grid floor (Z=0)"
    bl_options = {"REGISTER", "UNDO"}

    individually: BoolProperty(
        name="Individually",
        description="Drop each object to the floor on its own. Off keeps their relative heights",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        selected = set(context.selected_objects)
        movers = [o for o in selected if not _has_selected_ancestor(o, selected)]
        depsgraph = context.evaluated_depsgraph_get()
        lows = {o: _world_min_z(o, depsgraph) for o in movers}
        if self.individually:
            for obj in movers:
                _set_world_translation(obj, dz=-lows[obj])
        else:
            drop = min(lows.values())
            for obj in movers:
                _set_world_translation(obj, dz=-drop)
        return {"FINISHED"}


class MBT_OT_move_to_target(bpy.types.Operator):
    bl_idname = "mbt.move_to_target"
    bl_label = "Move to Target"
    bl_description = "Move all selected objects to the location of the active object (the one selected last)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        active = context.active_object
        return active is not None and active.select_get() and len(context.selected_objects) > 1

    def execute(self, context):
        target = context.active_object
        location = target.matrix_world.translation.copy()
        selected = set(context.selected_objects) - {target}
        for obj in selected:
            if not _has_selected_ancestor(obj, selected):
                _set_world_translation(obj, location=location)
        return {"FINISHED"}


classes = (MBT_OT_to_ground, MBT_OT_move_to_target)


def draw(layout, context):
    layout.operator("mbt.to_ground", icon="TRIA_DOWN_BAR")
    layout.operator("mbt.move_to_target", icon="PIVOT_ACTIVE")


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
