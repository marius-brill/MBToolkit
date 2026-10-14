"""
UV tools for MBToolkit addon.
Includes seam marking, connectivity analysis, straightening, and packing operations.
"""

import bpy
import bmesh
from bpy.props import FloatProperty
from math import degrees

from ..core.registry import register_classes, unregister_classes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_edit_mode(context):
    """Make sure the active mesh object is in edit mode."""
    obj = context.active_object
    if obj is None or obj.type != 'MESH':
        return False
    if obj.mode != 'EDIT':
        bpy.ops.object.mode_set(mode='EDIT')
    return True


def _target_faces(bm):
    """Selected faces, or all faces if nothing is selected."""
    selected = [f for f in bm.faces if f.select]
    return selected if selected else list(bm.faces)


def _uv_close(a, b, eps=1e-5):
    return (a - b).length_squared < eps * eps


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def mark_seams_by_angle(context, angle_threshold=70.0):
    """Mark seams where the angle between adjacent faces exceeds threshold (degrees)."""
    if not _ensure_edit_mode(context):
        return {'CANCELLED'}

    obj = context.active_object
    bm = bmesh.from_edit_mesh(obj.data)
    if not bm.faces:
        return {'CANCELLED'}

    faces = _target_faces(bm)
    seen = set()
    for face in faces:
        for edge in face.edges:
            if edge.index in seen:
                continue
            seen.add(edge.index)
            if len(edge.link_faces) != 2:
                continue
            # calc_face_angle returns radians (angle between the two face normals)
            angle = degrees(edge.calc_face_angle(0.0))
            if angle > angle_threshold:
                edge.seam = True

    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    return {'FINISHED'}


def find_connected_components(context):
    """Count UV islands (connected components in UV space) among target faces."""
    if not _ensure_edit_mode(context):
        return -1

    obj = context.active_object
    bm = bmesh.from_edit_mesh(obj.data)
    uv_layer = bm.loops.layers.uv.active
    if uv_layer is None:
        return -1

    faces = _target_faces(bm)
    face_set = set(faces)
    visited = set()
    islands = 0

    for start in faces:
        if start in visited:
            continue
        islands += 1
        stack = [start]
        visited.add(start)
        while stack:
            face = stack.pop()
            for loop in face.loops:
                other = loop.link_loop_radial_next
                if other is loop:
                    continue
                nface = other.face
                if nface in visited or nface not in face_set:
                    continue
                # Shared edge: UVs must coincide at both ends to be the same island
                if (_uv_close(loop[uv_layer].uv, other.link_loop_next[uv_layer].uv) and
                        _uv_close(loop.link_loop_next[uv_layer].uv, other[uv_layer].uv)):
                    visited.add(nface)
                    stack.append(nface)
    return islands


def straighten_uvs(context):
    """Straighten selected UVs using Blender's built-in align operator."""
    if not _ensure_edit_mode(context):
        return {'CANCELLED'}

    obj = context.active_object
    bm = bmesh.from_edit_mesh(obj.data)
    if bm.loops.layers.uv.active is None:
        return {'CANCELLED'}

    try:
        # Only selected UVs are affected; with UV sync off, select everything first
        if not context.tool_settings.use_uv_select_sync:
            for f in bm.faces:
                if f.select:
                    for l in f.loops:
                        l[bm.loops.layers.uv.active].select = True
                        l[bm.loops.layers.uv.active].select_edge = True
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        bpy.ops.uv.align(axis='ALIGN_AUTO')
    except Exception as e:
        print(f"[MBToolkit] Straighten failed: {e}")
        return {'CANCELLED'}
    return {'FINISHED'}


def pack_uvs(context):
    """Pack UVs, optionally via UVPackmaster 3 if installed."""
    if not _ensure_edit_mode(context):
        return {'CANCELLED'}

    try:
        bpy.ops.uv.pack_islands(rotate=True, margin=0.001)
        return {'FINISHED'}
    except Exception as e:
        print(f"[MBToolkit] Built-in pack failed: {e}")

    try:
        if hasattr(bpy.ops, 'uvpackmaster3'):
            bpy.ops.uvpackmaster3.pack()
            return {'FINISHED'}
    except Exception as e2:
        print(f"[MBToolkit] UVPackmaster pack failed: {e2}")

    return {'CANCELLED'}


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class _MeshPollMixin:
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'


class MBT_OT_mark_seams_by_angle(_MeshPollMixin, bpy.types.Operator):
    bl_idname = "mbt.mark_seams_by_angle"
    bl_label = "Mark Seams by Angle"
    bl_description = "Mark seams based on angle threshold between adjacent faces"
    bl_options = {"REGISTER", "UNDO"}

    angle_threshold: FloatProperty(
        name="Angle",
        description="Edges sharper than this angle become seams",
        default=70.0, min=0.0, max=180.0,
    )

    def execute(self, context):
        return mark_seams_by_angle(context, self.angle_threshold)


class MBT_OT_find_connectivity(_MeshPollMixin, bpy.types.Operator):
    bl_idname = "mbt.find_connectivity"
    bl_label = "Find Connectivity"
    bl_description = "Count connected UV islands"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        count = find_connected_components(context)
        if count < 0:
            self.report({'WARNING'}, "No active UV map")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Found {count} UV islands")
        return {'FINISHED'}


class MBT_OT_straighten_uvs(_MeshPollMixin, bpy.types.Operator):
    bl_idname = "mbt.straighten_uvs"
    bl_label = "Straighten UVs"
    bl_description = "Straighten selected UVs"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        return straighten_uvs(context)


class MBT_OT_pack_uvs(_MeshPollMixin, bpy.types.Operator):
    bl_idname = "mbt.pack_uvs"
    bl_label = "Pack UVs"
    bl_description = "Pack UV islands"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        return pack_uvs(context)


classes = (
    MBT_OT_mark_seams_by_angle,
    MBT_OT_find_connectivity,
    MBT_OT_straighten_uvs,
    MBT_OT_pack_uvs,
)


def draw(layout, context):
    """Draw UV tools in the UI."""
    layout.operator("mbt.mark_seams_by_angle", icon="MOD_SMOOTH")
    layout.operator("mbt.find_connectivity", icon="CON_TRACKTO")
    layout.operator("mbt.straighten_uvs", icon="DRIVER_DISTANCE")
    layout.operator("mbt.pack_uvs", icon="PACKAGE")


def register():
    """Register UV tools classes."""
    register_classes(classes)


def unregister():
    """Unregister UV tools classes."""
    unregister_classes(classes)