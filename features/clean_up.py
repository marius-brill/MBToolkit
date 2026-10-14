"""Clean up mesh geometry by removing doubles, degenerate geometry, and loose elements."""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty
import bmesh
from mathutils.geometry import distance_point_to_plane
from mathutils import Vector
import math

from ..core.registry import register_classes, unregister_classes
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty
import bmesh
from mathutils.geometry import distance_point_to_plane
from mathutils import Vector
import math

class MBT_OT_clean_up(bpy.types.Operator):
    bl_idname = "mbt.clean_up"
    bl_label = "MBToolkit: Clean Up"
    bl_options = {'REGISTER', 'UNDO'}

    remove_doubles: BoolProperty(name="Remove Doubles", default=True)
    dissolve_degenerate: BoolProperty(name="Dissolve Degenerate", default=True)
    distance: FloatProperty(name="Merge Distance", default=0.0001, min=0, step=0.01, precision=4)

    recalc_normals: BoolProperty(name="Recalculate Normals", default=True)
    flip_normals: BoolProperty(name="Flip Normals", default=False)

    delete_loose: BoolProperty(name="Delete Loose", default=True)
    delete_loose_verts: BoolProperty(name="Delete Loose Verts", default=True)
    delete_loose_edges: BoolProperty(name="Delete Loose Edges", default=True)
    delete_loose_faces: BoolProperty(name="Delete Loose Faces", default=False)

    dissolve_redundant: BoolProperty(name="Dissolve Redundant", default=True)
    dissolve_redundant_verts: BoolProperty(name="Dissolve Redundant Verts", default=True)
    dissolve_redundant_edges: BoolProperty(name="Dissolve Redundant Edges", default=False)
    dissolve_redundant_angle: FloatProperty(name="Dissolve Redundnat Angle", default=179.999, min=0, max=180, step=0.1, precision=6)

    select: BoolProperty(name="Select", default=True)
    select_type: EnumProperty(name="Select", items=[("NON-MANIFOLD", "Non-Manifold", "Non-Manifold edges"),
                                                    ("NON-PLANAR", "Non-Planar", "Non-Planar faces"),
                                                    ("TRIS", "Tris", "Triangular faces"),
                                                    ("NGONS", "Ngons", "Ngonal faces")], default="NON-MANIFOLD")
    planar_threshold: FloatProperty(name="Non-Planar Face Threshold", default=0.001, min=0, step=0.0001, precision=6)

    view_selected: BoolProperty(name="View Selected", default=False)

    @classmethod
    def poll(cls, context):
        return context.mode in ("EDIT_MESH", "OBJECT")

    def invoke(self, context, event):
        self.coords = Vector((event.mouse_region_x, event.mouse_region_y)) + Vector((10, 20))
        return self.execute(context)

    def execute(self, context):
        # Store the original mode
        original_mode = context.mode
        
        # If we're in OBJECT mode, switch to EDIT mode
        if original_mode == "OBJECT":
            bpy.ops.object.mode_set(mode='EDIT')
    def execute(self, context):
        sel = {obj for obj in context.selected_objects if obj.type == 'MESH' and obj.mode == 'EDIT'} | {context.active_object}

        removed = {}

        for obj in sel:
            bm, elementcounts = self.clean_up(obj)

            if self.select:
                self.select_geometry(bm)

            cleanedcounts = self.get_element_counts(bm)
            bmesh.update_edit_mesh(obj.data)

            if elementcounts != cleanedcounts:
                removed[obj] = (elementcounts[0] - cleanedcounts[0], elementcounts[1] - cleanedcounts[1], elementcounts[2] - cleanedcounts[2])

        if self.select and self.view_selected:
            bpy.ops.view3d.view_selected('INVOKE_DEFAULT', use_all_regions=False)

        if removed:
            verts = 0
            edges = 0
            faces = 0

            for counts in removed.values():
                verts += counts[0]
                edges += counts[1]
                faces += counts[2]

            text = f"Removed:{' Verts: ' + str(verts) if verts else ''}{' Edges: ' + str(edges) if edges else ''}{' Faces: ' + str(faces) if faces else ''}"

            extreme = any([c >= 10 for c in [verts, edges, faces]])
            # bpy.ops.machin3.draw_label(text=text, coords=self.coords, center=False, color=yellow if extreme else white, time=get_prefs().HUD_fade_clean_up, alpha=1)
        else:
            text = "Nothing to remove."
            # bpy.ops.machin3.draw_label(text=text, coords=self.coords, center=False, color=green, time=get_prefs().HUD_fade_clean_up, alpha=0.5)

        # self.report({'INFO'}, text)

        return {'FINISHED'}

    def clean_up(self, active):
        if active.mode == 'OBJECT':
            bpy.ops.object.mode_set(mode='EDIT')

        
        bm = bmesh.from_edit_mesh(active.data)
        bm.normal_update()
        bm.verts.ensure_lookup_table()

        elementcounts = self.get_element_counts(bm)

        if self.remove_doubles:
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=self.distance)

        if self.dissolve_degenerate:
            bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=self.distance)

        if self.delete_loose:
            self.delete_loose_geometry(bm)

        if self.dissolve_redundant:
            self.dissolve_redundant_geometry(bm)

        if self.recalc_normals:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

            if self.flip_normals:
                for f in bm.faces:
                    f.normal_flip()
        return bm, elementcounts

    def get_element_counts(self, bm):
        '''
        return tuple of vertcount, edgecount and facecount
        '''
        return len(bm.verts), len(bm.edges), len(bm.faces)

    def delete_loose_geometry(self, bm):
        if self.delete_loose_verts:
            loose_verts = [v for v in bm.verts if not v.link_edges]
            bmesh.ops.delete(bm, geom=loose_verts, context="VERTS")

        if self.delete_loose_edges:
            loose_edges = [e for e in bm.edges if not e.link_faces]
            bmesh.ops.delete(bm, geom=loose_edges, context="EDGES")

        if self.delete_loose_faces:
            loose_faces = [f for f in bm.faces if all([not e.is_manifold for e in f.edges])]
            bmesh.ops.delete(bm, geom=loose_faces, context="FACES")

    def dissolve_redundant_geometry(self, bm):
        '''
        dissolve redundant verts on straight edges
        dissolve redundant edges on flat faces
        '''

        if self.dissolve_redundant_edges:
            manifold_edges = [e for e in bm.edges if e.is_manifold]

            redundant_edges = []

            for e in manifold_edges:
                angle = math.degrees(e.calc_face_angle(0))

                if angle < 180 - self.dissolve_redundant_angle:
                    redundant_edges.append(e)

            bmesh.ops.dissolve_edges(bm, edges=redundant_edges, use_verts=False)

            # dissolving with use_verts enabled can cause problems in som cases, so it's better to check the left over edges for 2 edged verts, and remove those in a separate step
            two_edged_verts = {v for e in redundant_edges if e.is_valid for v in e.verts if len(v.link_edges) == 2}
            bmesh.ops.dissolve_verts(bm, verts=list(two_edged_verts))

        # also run vert removal after edge removal to ensure verts from symmetry center lines get removed properly
        if self.dissolve_redundant_verts:
            two_edged_verts = [v for v in bm.verts if len(v.link_edges) == 2]

            redundant_verts = []

            for v in two_edged_verts:
                e1 = v.link_edges[0]
                e2 = v.link_edges[1]

                vector1 = e1.other_vert(v).co - v.co
                vector2 = e2.other_vert(v).co - v.co

                angle = min(math.degrees(vector1.angle(vector2)), 180)

                if self.dissolve_redundant_angle < angle:
                    redundant_verts.append(v)

            bmesh.ops.dissolve_verts(bm, verts=redundant_verts)

    def select_geometry(self, bm):
        for f in bm.faces:
            f.select = False

        bm.select_flush(False)

        if self.select_type == "NON-MANIFOLD":
            edges = [e for e in bm.edges if not e.is_manifold]

            for e in edges:
                e.select = True

        elif self.select_type == "NON-PLANAR":
            faces = [f for f in bm.faces if len(f.verts) > 3]

            for f in faces:
                distances = [distance_point_to_plane(v.co, f.calc_center_median(), f.normal) for v in f.verts]

                if any([d for d in distances if abs(d) > self.planar_threshold]):
                    f.select_set(True)

        elif self.select_type == "TRIS":
            faces = [f for f in bm.faces if len(f.verts) == 3]

            for f in faces:
                f.select = True

        elif self.select_type == "NGONS":
            faces = [f for f in bm.faces if len(f.verts) > 4]

            for f in faces:
                f.select = True


classes = (MBT_OT_clean_up,)


def draw(layout, context):
    layout.operator("mbt.clean_up", icon="TRIA_DOWN_BAR")


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
