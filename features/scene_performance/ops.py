"""Explicit scan, navigation, baseline and export actions."""

import csv
import json
from pathlib import Path

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from . import runtime as rt


class MBT_OT_stats_refresh(bpy.types.Operator):
    bl_idname = 'mbt.stats_refresh'
    bl_label = 'Scan'
    bl_description = 'Capture evaluated mesh triangles and native modifier timings without changing modifier visibility'

    @classmethod
    def poll(cls, context):
        return rt.JOB is None and context.mode == 'OBJECT' and not bpy.app.is_job_running('RENDER')

    def execute(self, context):
        try:
            rt.begin(context, context.scene.mbt.stats_timings)
            if bpy.app.background:
                while rt.step(context):
                    pass
            else:
                bpy.app.timers.register(rt.tick, first_interval=0.01)
        except (RuntimeError, ReferenceError, ValueError) as exc:
            rt.cancel()
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class MBT_OT_stats_cancel(bpy.types.Operator):
    bl_idname = 'mbt.stats_cancel'
    bl_label = 'Cancel Scan'
    bl_description = 'Stop between objects and keep partial results'

    @classmethod
    def poll(cls, context):
        return rt.JOB is not None

    def execute(self, context):
        rt.cancel()
        return {'FINISHED'}


class MBT_OT_stats_baseline(bpy.types.Operator):
    bl_idname = 'mbt.stats_baseline'
    bl_label = 'Set Baseline'
    bl_description = 'Store a complete fresh snapshot for same-scope, same-frame comparisons this session'

    @classmethod
    def poll(cls, context):
        return (rt.JOB is None and rt.matches(context) and rt.SNAPSHOT['complete']
                and not rt.is_stale(context))

    def execute(self, context):
        try:
            rt.set_baseline(context)
        except RuntimeError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        rt.redraw(context.window_manager)
        return {'FINISHED'}


class MBT_OT_stats_navigate(bpy.types.Operator):
    bl_idname = 'mbt.stats_navigate'
    bl_label = 'Navigate to Diagnostic Object'
    bl_description = 'Select, frame, or inspect the captured object; list selection alone does not change scene selection'
    bl_options = {'UNDO'}
    action: EnumProperty(items=(('SELECT', 'Select', ''), ('FRAME', 'Frame', ''),
                               ('PROPERTIES', 'Modifier Properties', '')))

    @classmethod
    def poll(cls, context):
        row, _ = rt.active_result(context)
        return rt.JOB is None and context.mode == 'OBJECT' and row is not None and row.obj is not None

    def execute(self, context):
        row, _ = rt.active_result(context)
        obj = row.obj if row else None
        if obj is None or str(obj.session_uid) != row.uid or obj.name not in context.view_layer.objects:
            self.report({'WARNING'}, 'Object no longer belongs to this view layer; rescan')
            return {'CANCELLED'}
        viewport = context.space_data if context.area and context.area.type == 'VIEW_3D' else None
        if not obj.visible_get(view_layer=context.view_layer, viewport=viewport) or obj.hide_select:
            self.report({'WARNING'}, 'Object is hidden or selection is disabled; visibility was left unchanged')
            return {'CANCELLED'}
        if self.action == 'FRAME' and (context.area is None or context.area.type != 'VIEW_3D'):
            self.report({'WARNING'}, 'Frame requires a 3D Viewport')
            return {'CANCELLED'}
        properties = [area for area in context.screen.areas if area.type == 'PROPERTIES']
        if self.action == 'PROPERTIES' and not properties:
            self.report({'WARNING'}, 'No Properties editor is available in this window')
            return {'CANCELLED'}
        for selected in context.selected_objects:
            selected.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        if self.action == 'FRAME':
            region = next((region for region in context.area.regions if region.type == 'WINDOW'), None)
            if region is None:
                return {'CANCELLED'}
            with context.temp_override(region=region):
                bpy.ops.view3d.view_selected(use_all_regions=False)
        elif self.action == 'PROPERTIES':
            area = next((area for area in properties if not area.spaces.active.use_pin_id), None)
            if area is None:
                self.report({'INFO'}, 'Properties editors are pinned; pins were left unchanged')
            else:
                try:
                    area.spaces.active.context = 'MODIFIER'
                except TypeError:
                    self.report({'WARNING'}, 'This object has no modifier context')
        return {'FINISHED'}


def export_snapshot(context, filepath, format, capture_token=''):
    """Export scalar data only; callable independently of the file picker."""
    # File-browser context has no originating viewport Local View/collection.
    # An invocation token binds the export to the exact snapshot instead.
    valid = (rt.SNAPSHOT is not None and capture_token == str(rt.SNAPSHOT['captured_at'])
             if capture_token else rt.matches(context))
    if not valid or rt.JOB is not None:
        raise ValueError('Scan the current scope before exporting')
    snapshot = rt.SNAPSHOT
    metadata = {key: value for key, value in snapshot.items() if key not in {'results', 'signature'}}
    metadata['stale'] = rt.is_stale(context)
    metadata['metric_notes'] = ('Per-object evaluated mesh triangles; not instance-expanded or unique geometry. '
                                'Native last-evaluation modifier timings are diagnostic, not frame time; '
                                'parallel execution may make timings unreliable. Null means unavailable.')
    results = list(snapshot['results'].values())
    if format == 'JSON':
        with open(filepath, 'w', encoding='utf-8') as handle:
            json.dump({'metadata': metadata, 'objects': results}, handle, indent=2, allow_nan=False)
    else:
        with open(filepath, 'w', encoding='utf-8', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(('name', 'uid', 'type', 'evaluated_mesh_triangles', 'native_modifier_ms',
                             'error', 'frame', 'scene', 'view_layer', 'scope', 'method', 'captured_at',
                             'complete', 'stale', 'metric_notes'))
            for result in results:
                def safe(value):
                    # Protect names/errors when imported into a spreadsheet.
                    return "'" + value if isinstance(value, str) and value.startswith(('=', '+', '-', '@', '\t', '\r')) else value
                writer.writerow([safe(value) for value in (
                    result['name'], result['uid'], result.get('type', ''), result['tris'], result['ms'],
                    result['error'], snapshot['frame'], snapshot['scene'], snapshot['view_layer'],
                    snapshot['scope'], snapshot['method'], snapshot['captured_at'], snapshot['complete'],
                    metadata['stale'], metadata['metric_notes'])])


class MBT_OT_stats_export(bpy.types.Operator):
    bl_idname = 'mbt.stats_export'
    bl_label = 'Export Snapshot'
    bl_description = 'Export the entire captured scope with partial/error/stale metadata, not just filtered rows'
    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default='*.json;*.csv', options={'HIDDEN'})
    check_existing: BoolProperty(default=True, options={'HIDDEN'})
    capture_token: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    format: EnumProperty(name='Format', items=(('JSON', 'JSON', 'Full snapshot and modifier details'),
                                             ('CSV', 'CSV', 'Object summary with metadata')))

    @classmethod
    def poll(cls, context):
        return rt.SNAPSHOT is not None and rt.JOB is None

    def invoke(self, context, event):
        if not rt.matches(context):
            self.report({'WARNING'}, 'Scan this scope before exporting')
            return {'CANCELLED'}
        self.capture_token = str(rt.SNAPSHOT['captured_at'])
        self.filepath = 'scene_performance.json'
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def check(self, context):
        suffix = '.' + self.format.lower()
        if Path(self.filepath).suffix.lower() != suffix:
            self.filepath = str(Path(self.filepath).with_suffix(suffix))
            return True
        return False

    def execute(self, context):
        if not self.filepath:
            self.report({'WARNING'}, 'Choose an export path')
            return {'CANCELLED'}
        try:
            export_snapshot(context, bpy.path.abspath(self.filepath), self.format, self.capture_token)
        except (OSError, ValueError, TypeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, 'Scene performance snapshot exported')
        return {'FINISHED'}


classes = (MBT_OT_stats_refresh, MBT_OT_stats_cancel, MBT_OT_stats_baseline,
           MBT_OT_stats_navigate, MBT_OT_stats_export)