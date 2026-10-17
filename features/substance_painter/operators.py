"""UI adapters for the Blender half of the Painter workflow."""
import json
import bpy
from bpy.props import EnumProperty
from ...core.registry import register_classes, unregister_classes
from . import jobs, materials
from . import bridge, runtime
from ...core.addon import get_prefs


class MBT_OT_painter_assign(bpy.types.Operator):
    bl_idname = 'mbt.painter_assign'
    bl_label = 'Move Selected Meshes to Bake Collection'
    bl_description = 'Move selected meshes out of their existing collections into this bake collection'
    bl_options = {'REGISTER', 'UNDO'}
    role: EnumProperty(items=(('LOW', 'Low Poly', ''), ('HIGH', 'High Poly', '')))

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        settings = context.scene.mbt_painter
        objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        attribute = 'low_collection' if self.role == 'LOW' else 'high_collection'
        opposite = settings.high_collection if self.role == 'LOW' else settings.low_collection
        collection = getattr(settings, attribute)
        if collection is not None and (collection == opposite or
                (opposite and (collection in opposite.children_recursive or opposite in collection.children_recursive))):
            self.report({'WARNING'}, 'Low/high collections must be separate, not nested')
            return {'CANCELLED'}
        if any(obj.library or obj.data.library or any(c.library for c in obj.users_collection)
               or len(obj.users_scene) > 1 for obj in objects):
            self.report({'WARNING'}, 'Cannot move linked meshes or meshes shared across scenes')
            return {'CANCELLED'}
        if collection is not None and collection.library:
            self.report({'WARNING'}, 'Choose a local collection')
            return {'CANCELLED'}
        if collection is None:
            collection = bpy.data.collections.new('MBT_' + self.role.title())
            context.scene.collection.children.link(collection)
            setattr(settings, attribute, collection)
        for obj in objects:
            if obj.name not in collection.objects:
                collection.objects.link(obj)
            for previous in tuple(obj.users_collection):
                if previous != collection:
                    previous.objects.unlink(obj)
        return {'FINISHED'}


class MBT_OT_painter_action(bpy.types.Operator):
    bl_idname = 'mbt.painter_action'
    bl_label = 'Painter Workflow'
    bl_description = 'Validate, prepare FBX and JSON files, or import manually exported textures; does not run Painter'
    action: EnumProperty(items=(('VALIDATE', 'Validate Setup', ''),
        ('PREPARE', 'Prepare Bake Job', ''), ('IMPORT', 'Import Maps / Update Material', '')))

    @classmethod
    def poll(cls, context):
        return context.scene is not None and not runtime.busy()

    def execute(self, context):
        try:
            if self.action == 'VALIDATE':
                low, high = jobs.validate(context)
                from .matching import resolve
                resolve(context, low, high)
                message = f'Valid setup: {len(low)} low / {len(high)} high meshes; all pairs resolved'
            elif self.action == 'PREPARE':
                message = jobs.prepare(context)
            else:
                message = materials.import_maps(context)
        except (jobs.PainterError, OSError, RuntimeError, json.JSONDecodeError) as error:
            context.scene.mbt_painter.report = str(error)
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        context.scene.mbt_painter.report = message
        self.report({'INFO'}, message)
        return {'FINISHED'}


class MBT_OT_painter_connect(bpy.types.Operator):
    bl_idname = 'mbt.painter_connect'
    bl_label = 'Painter Connection'
    bl_description = 'Connect locally or launch Painter with remote scripting; never closes an open project'
    action: EnumProperty(items=(('DETECT', 'Detect Executable', ''), ('TEST', 'Test Connection', ''),
                               ('CONNECT', 'Launch / Connect', ''), ('SEND', 'Send to Painter', ''),
                               ('EXPORT', 'Export from Painter / Import', 'Export current job textures and update Blender materials'),
                               ('BAKE', 'Bake Current Job', 'Bake the matching open job, save, export and import'),
                               ('BAKE_NEW', 'Bake New Project', 'Prepare, create project, bake, save, export and import'),
                               ('AUTO', 'Bake', 'Refresh meshes, create or update the associated Painter project, bake and import textures')))

    @classmethod
    def poll(cls, context):
        return context.scene is not None and not runtime.busy()

    def execute(self, context):
        try:
            if self.action == 'DETECT':
                prefs = get_prefs(context)
                path = bridge.detect_executable()
                if prefs is None or not path:
                    raise jobs.PainterError('Painter not found in standard locations; choose the executable manually')
                prefs.painter_executable = path
                context.preferences.is_dirty = True
                context.scene.mbt_painter.report = 'Detected: ' + path
            else:
                runtime.start(context, self.action)
        except (jobs.PainterError, OSError, RuntimeError, json.JSONDecodeError) as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


class MBT_OT_painter_new_project(bpy.types.Operator):
    bl_idname = 'mbt.painter_new_project'
    bl_label = 'New Project Next Bake'
    bl_description = 'Forget the project association; existing project files are kept. Close the old project in Painter yourself'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and not runtime.busy()

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        context.scene.mbt_painter.project_file = ''
        context.scene.mbt_painter.last_job = ''
        context.scene.mbt_painter.report = 'Next Bake creates a new project. Close the previous project in Painter first.'
        return {'FINISHED'}


class MBT_OT_painter_cancel(bpy.types.Operator):
    bl_idname = 'mbt.painter_cancel'
    bl_label = 'Cancel Bake'
    bl_description = 'Request cancellation; waits for Painter to confirm baking has ended'

    @classmethod
    def poll(cls, context):
        return runtime.busy() and runtime._cancel is not None

    def execute(self, context):
        runtime.cancel()
        return {'FINISHED'}


classes = (MBT_OT_painter_assign, MBT_OT_painter_action, MBT_OT_painter_connect,
           MBT_OT_painter_new_project, MBT_OT_painter_cancel)


def register():
    register_classes(classes)


def unregister():
    runtime.cleanup()
    unregister_classes(classes)