"""SDF remesh: Mesh to SDF Grid -> Mean -> Grid to Mesh.

The result has no material index data, so every face uses the object's material slot 0.
"""

import bpy

from ...core import gn
from ...core.registry import register_classes, unregister_classes

GROUP_NAME = "SDFremesh"
MODIFIER_NAME = "SDFremesh"
REV = 2

DEFAULTS = {"Density": 0.01, "Smoothing Iterations": 2, "Decimate Adaptivity": 0.001}


def _build():
    ng = bpy.data.node_groups.new(GROUP_NAME, "GeometryNodeTree")
    iface = ng.interface
    gn.add_input(iface, "Geometry", "NodeSocketGeometry")
    gn.add_input(iface, "Density", "NodeSocketFloat", DEFAULTS["Density"], min_value=0.0001, subtype="DISTANCE")
    gn.add_input(iface, "Smoothing Iterations", "NodeSocketInt", DEFAULTS["Smoothing Iterations"], min_value=0)
    gn.add_input(iface, "Decimate Adaptivity", "NodeSocketFloat", DEFAULTS["Decimate Adaptivity"], 0.0, 1.0)
    gn.add_output(iface, "Geometry", "NodeSocketGeometry")

    nodes, links = ng.nodes, ng.links
    gi = gn.add_node(nodes, "NodeGroupInput", -400, 0)
    to_sdf = gn.add_node(nodes, "GeometryNodeMeshToSDFGrid", -100, 100)
    mean = gn.add_node(nodes, "GeometryNodeSDFGridMean", 200, 200)
    to_mesh = gn.add_node(nodes, "GeometryNodeGridToMesh", 500, 100)
    shade = gn.add_node(nodes, "GeometryNodeSetShadeSmooth", 800, 100, domain="FACE")
    go = gn.add_node(nodes, "NodeGroupOutput", 1100, 100)

    gn.sock(to_sdf.inputs, "Band Width", 2).default_value = 3
    gn.sock(mean.inputs, "Width", 1).default_value = 1

    L = lambda *a, **k: gn.link(links, *a, **k)
    L(gi, "Geometry", to_sdf, "Mesh")
    L(gi, "Density", to_sdf, "Voxel Size", in_i=1)
    L(to_sdf, "SDF Grid", mean, "Grid")
    L(gi, "Smoothing Iterations", mean, "Iterations", in_i=2)
    L(mean, "Grid", to_mesh, "Grid")
    L(gi, "Density", to_mesh, "Threshold", in_i=1)  # as in the reference setup
    L(gi, "Decimate Adaptivity", to_mesh, "Adaptivity", in_i=2)
    L(to_mesh, "Mesh", shade, "Mesh")
    L(shade, "Mesh", go, "Geometry")
    return ng


def get_group():
    return gn.ensure_group(GROUP_NAME, REV, _build)


class MBT_OT_add_sdf_remesh(bpy.types.Operator):
    bl_idname = "mbt.add_sdf_remesh"
    bl_label = "Add SDF Remesh"
    bl_description = "Add the SDFremesh modifier to the selected meshes (uses material slot 0)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return gn.poll_mesh_selected(context)

    def execute(self, context):
        ok = gn.add_to_selected(self, context, get_group(), MODIFIER_NAME, DEFAULTS)
        return {"FINISHED"} if ok else {"CANCELLED"}


classes = (MBT_OT_add_sdf_remesh,)


def draw(layout, context):
    layout.operator("mbt.add_sdf_remesh", icon="MOD_REMESH")


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
