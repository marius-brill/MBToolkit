"""Thin Blender UI adapters."""
import bpy
from bpy.props import EnumProperty
from ...core.registry import register_classes, unregister_classes
from .context import UVError
from .operations import run


def execute_action(operator, context, action, angle=None):
    try:
        message = run(context, action, angle)
    except (UVError, RuntimeError, ValueError) as error:
        context.scene.mbt_uv.report = str(error)
        operator.report({'WARNING'}, str(error))
        return {'CANCELLED'}
    operator.report({'INFO'}, message)
    return {'FINISHED'}


class MeshPoll:
    @classmethod
    def poll(cls, context):
        return (context.mode in {'OBJECT', 'EDIT_MESH'} and context.active_object is not None
                and context.active_object.type == 'MESH')


class MBT_OT_uv_action(MeshPoll, bpy.types.Operator):
    bl_idname = 'mbt.uv_action'
    bl_label = 'UV Suite'
    bl_description = 'Process visible selected faces; island tools expand to whole affected islands'
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(name='Action', items=tuple((key, label, description) for key, label, description in (
        ('AUTO', 'Auto UV', 'Angle seams, unwrap, normalize and validated packing'),
        ('UNWRAP', 'Unwrap', 'Use existing seams without packing'),
        ('SEAMS', 'Smart Seams', 'Segment coherent face regions and validate complete boundaries'),
        ('PACK', 'Smart Pack', 'Compare packing candidates and check pixel padding'),
        ('DENSITY', 'Set Density', 'Set pixels per meter using world-space area'),
        ('MEASURE', 'Get Density', 'Measure active target pixels per meter'),
        ('NORMALIZE', 'Normalize Density', 'Match affected island density'),
        ('INSPECT', 'Inspect UVs', 'Check overlap, collapse, winding and padding'),
        ('COUNT', 'Count Islands', 'Count UV-connected islands'),
        ('STRAIGHTEN', 'Smart Straighten', 'Quadrify regular quads or rectify a four-sided boundary'),
        ('CHAIN', 'Straighten Chain', 'Straighten one selected open edge chain per island'),
        ('QUADRIFY', 'Quadrify', 'Propagate a regular grid through all-quad topology'),
        ('RECTIFY', 'Rectify', 'Map four boundary corners to a rectangle; solve the interior'),
        ('RELAX', 'Flatten / Relax', 'Harmonic relaxation with boundary and pins fixed'),
        ('CIRCLE', 'Circle Boundary', 'Circular boundary with harmonic interior'),
        ('ORIENT', 'Orient', 'Orient longest mesh edge horizontally or vertically'),
        ('ROTATE', 'Rotate 90 Degrees', 'Rotate whole islands in pixel space'),
        ('ALIGN_U', 'Align U', 'Align selected UV vertices to a common U coordinate'),
        ('ALIGN_V', 'Align V', 'Align selected UV vertices to a common V coordinate'),
        ('INPLACE', 'Unwrap In Place', 'Preserve original island area and centroid'),
        ('IMPROVE', 'Improve Existing UVs', 'Unwrap in place then relax without packing'),
        ('SEAMS_UV', 'Seams from UVs', 'Mark target seams from UV discontinuities'),
        ('CLEAR_SEAMS', 'Clear Seams', 'Clear seams strictly inside the target'),
        ('REPAIR_SEAMS', 'Complete Seam Regions', 'Complete face-region boundaries around protected existing seams; roll back if blocked'),
        ('COMPLETE_SEAM', 'Complete Selected Seam Loop', 'Use selected edges as required face-region boundaries'),
        ('MARK_SELECTED', 'Mark Selected Seams', 'Mark selected visible mesh edges as seams'),
        ('CLEAR_SELECTED', 'Clear Selected Seams', 'Clear seams on selected visible mesh edges'),
        ('WELD', 'Weld', 'Weld selected UV splits at each mesh vertex'),
        ('SPLIT', 'Split', 'Separate selected faces from their UV neighbors'),
        ('STITCH', 'Stitch', 'Weld corresponding selected seam vertices; no rigid-island fit'),
        ('DISTRIBUTE_U', 'Distribute U', 'Distribute whole island centers horizontally'),
        ('DISTRIBUTE_V', 'Distribute V', 'Distribute whole island centers vertically'),
        ('MATCH_SIZE', 'Match Dimensions', 'Match island pixel bounds to active target bounds'),
        ('FIT', 'Fit Proportionally', 'Fit affected island group inside the first tile'),
        ('MAP_NEW', 'New UV Map', 'Create and activate a UV map on selected mesh objects'),
        ('MAP_COPY', 'Duplicate UV Map', 'Copy the active UV map on selected mesh objects'),
        ('MAP_RENAME', 'Rename UV Map', 'Rename the active UV map on selected mesh objects'),
        ('MAP_ACTIVE', 'Activate UV Map', 'Activate the named UV map on selected mesh objects'),
        ('CHECKER', 'Checker Image', 'Create/show a UV grid image without changing materials'),
        ('PIN', 'Lock Islands', 'Pin all UV nodes of affected islands; constrained packing treats them as obstacles'),
        ('UNPIN', 'Unlock Islands', 'Clear pins on whole affected islands'),
        ('MATCH_DENSITY', 'Match Active Density', 'Match the active face island density'),
        ('SELECT_ISLANDS', 'Select Islands', 'Expand the selection to whole UV islands'),
        ('SELECT_SIMILAR', 'Select Similar Topology', 'Match face counts and polygon-side counts; not geometric congruence'),
        ('SELECT_DENSITY', 'Select Density Deviations', 'Select islands outside the density tolerance'),
        ('SELECT_OVERLAP', 'Select Overlaps', 'Select faces with positive-area triangle intersections'),
        ('SELECT_DEGENERATE', 'Select Collapsed', 'Select faces with collapsed UV triangles'),
        ('SELECT_FLIPPED', 'Select Negative Winding', 'Select negative signed-area UV triangles'),
        ('SELECT_OUTSIDE', 'Select Outside Tiles', 'Select faces outside the configured tile range'))))

    def execute(self, context):
        if self.action.startswith('MAP_') or self.action == 'CHECKER':
            from .utilities import data_action
            try:
                message = data_action(context, self.action)
            except (UVError, RuntimeError, ValueError) as error:
                self.report({'WARNING'}, str(error))
                return {'CANCELLED'}
            self.report({'INFO'}, message)
            return {'FINISHED'}
        return execute_action(self, context, self.action)


class MBT_PT_uv_editor(bpy.types.Panel):
    bl_idname = 'MBT_PT_uv_editor'
    bl_label = 'UV Suite'
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'MBToolkit'

    @classmethod
    def poll(cls, context):
        return context.space_data.mode == 'UV'

    def draw(self, context):
        from . import draw
        draw(self.layout, context)


classes = (MBT_OT_uv_action, MBT_PT_uv_editor)


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)