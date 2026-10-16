"""Explicit scan/cancel and modifier-inspector actions."""

import bpy
from bpy.props import StringProperty, BoolProperty

from . import runtime as rt


class MBT_OT_stats_refresh(bpy.types.Operator):
    bl_idname = 'mbt.stats_refresh'
    bl_label = 'Scan'
    bl_description = 'Refresh evaluated triangles and native modifier timings for the full scope'

    @classmethod
    def poll(cls, context):
        return (context.area is not None and context.area.type == 'VIEW_3D'
                and (rt.editor_key(context) not in rt.SESSIONS or rt.session(context).job is None)
                and context.mode == 'OBJECT' and not bpy.app.is_job_running('RENDER'))

    def execute(self, context):
        try:
            rt.start_scan(context)
            if bpy.app.background:
                while rt.scan_step(context):
                    pass
            else:
                rt.ensure_controller()
        except (RuntimeError, ReferenceError, ValueError) as exc:
            rt.cancel_scan(context)
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class MBT_OT_stats_cancel(bpy.types.Operator):
    bl_idname = 'mbt.stats_cancel'
    bl_label = 'Cancel Scan'
    bl_description = 'Stop scanning and switch to manual updates'

    @classmethod
    def poll(cls, context):
        return (context.area is not None and context.area.type == 'VIEW_3D'
                and rt.editor_key(context) in rt.SESSIONS and rt.session(context).job is not None)

    def execute(self, context):
        rt.state(context).auto = False
        rt.cancel_scan(context, partial=True)
        return {'FINISHED'}


class MBT_OT_stats_properties(bpy.types.Operator):
    bl_idname = 'mbt.stats_properties'
    bl_label = 'Modifier Properties'
    bl_description = 'Inspect the active object in an existing unpinned Properties editor'

    @classmethod
    def poll(cls, context):
        row, _ = rt.active_result(context)
        return context.mode == 'OBJECT' and row is not None and row.obj is not None

    def execute(self, context):
        row, _ = rt.active_result(context)
        if row is None or row.obj is None:
            self.report({'WARNING'}, 'Object is hidden, unavailable, or selection is disabled')
            return {'CANCELLED'}
        area = next((area for area in context.screen.areas if area.type == 'PROPERTIES'
                     and not area.spaces.active.use_pin_id), None)
        if area is None:
            self.report({'WARNING'}, 'No unpinned Properties editor is available')
            return {'CANCELLED'}
        try:
            area.spaces.active.context = 'MODIFIER'
        except TypeError:
            self.report({'WARNING'}, 'This object has no modifier context')
            return {'CANCELLED'}
        return {'FINISHED'}


class MBT_OT_stats_activate(bpy.types.Operator):
    bl_idname = 'mbt.stats_activate'
    bl_label = 'Activate Object'
    bl_description = 'Select this object in the owning viewport; Shift adds to selection'
    uid: StringProperty()
    extend: BoolProperty(default=False)

    def invoke(self, context, event):
        self.extend = event.shift
        return self.execute(context)

    def execute(self, context):
        rt.queue_selection(context, self.uid, self.extend)
        return {'FINISHED'}


class MBT_OT_stats_initialize(bpy.types.Operator):
    bl_idname = 'mbt.stats_initialize'
    bl_label = 'Initialize Viewport Session'
    bl_description = 'Recreate this viewport session and restart the update controller'

    def execute(self, context):
        rt.session(context)
        rt.state(context)
        rt.ensure_controller()
        context.area.tag_redraw()
        return {'FINISHED'}


classes = (MBT_OT_stats_refresh, MBT_OT_stats_cancel, MBT_OT_stats_properties,
           MBT_OT_stats_activate, MBT_OT_stats_initialize)