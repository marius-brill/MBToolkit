"""DynaBool: crease by angle -> subdivision -> optional SDF remesh, in one node group."""

import bpy

from ...core import gn
from ...core.registry import register_classes, unregister_classes

GROUP_NAME = "DynaBool"
MODIFIER_NAME = "DynaBool"
REV = 1

DEFAULTS = {
    "Crease Angle": 50.0,
    "SubD Level": 2,
    "Remesh": True,
    "Voxel Size": 0.008,
    "Smooth Iterations": 1,
}


def _build():
    ng = bpy.data.node_groups.new(GROUP_NAME, "GeometryNodeTree")
    iface = ng.interface
    gn.add_input(iface, "Geometry", "NodeSocketGeometry")
    gn.add_input(iface, "Crease Angle", "NodeSocketFloat", DEFAULTS["Crease Angle"], 0.0, 180.0)
    gn.add_input(iface, "SubD Level", "NodeSocketInt", DEFAULTS["SubD Level"], 0, 11)
    gn.add_input(iface, "Remesh", "NodeSocketBool", DEFAULTS["Remesh"])
    gn.add_input(iface, "Voxel Size", "NodeSocketFloat", DEFAULTS["Voxel Size"], min_value=0.0001)
    gn.add_input(iface, "Smooth Iterations", "NodeSocketInt", DEFAULTS["Smooth Iterations"], min_value=0)
    gn.add_output(iface, "Geometry", "NodeSocketGeometry")

    nodes, links = ng.nodes, ng.links
    A = lambda idname, x, y, **kw: gn.add_node(nodes, idname, x, y, **kw)
    L = lambda *a, **k: gn.link(links, *a, **k)

    gi = A("NodeGroupInput", -800, 0)
    go = A("NodeGroupOutput", 2000, 200)

    # Crease / SubD
    edge_angle = A("GeometryNodeInputMeshEdgeAngle", -500, -250)
    to_deg = A("ShaderNodeMath", -300, -250, operation="DEGREES")
    cmp = A("FunctionNodeCompare", -100, -250, data_type="FLOAT", operation="GREATER_EQUAL")
    store = A("GeometryNodeStoreNamedAttribute", 150, 0, data_type="FLOAT", domain="EDGE")
    store.inputs["Name"].default_value = "crease_edge"
    store.inputs["Value"].default_value = 1.0
    clamp = A("ShaderNodeClamp", 150, -250, clamp_type="MINMAX")
    clamp.inputs["Min"].default_value = 0.0
    clamp.inputs["Max"].default_value = 11.0
    named = A("GeometryNodeInputNamedAttribute", 150, -450, data_type="FLOAT")
    named.inputs["Name"].default_value = "crease_edge"
    subd = A("GeometryNodeSubdivisionSurface", 450, 0)

    L(edge_angle, "Unsigned Angle", to_deg, "Value")
    links.new(to_deg.outputs[0], cmp.inputs[0])
    links.new(gi.outputs["Crease Angle"], cmp.inputs[1])
    links.new(cmp.outputs[0], store.inputs["Selection"])
    L(gi, "Geometry", store, "Geometry")
    links.new(gi.outputs["SubD Level"], clamp.inputs[0])
    L(store, "Geometry", subd, "Mesh")
    links.new(clamp.outputs[0], subd.inputs["Level"])
    links.new(named.outputs[0], subd.inputs["Edge Crease"])

    # Remesh
    to_sdf = A("GeometryNodeMeshToSDFGrid", 800, 100)
    gn.sock(to_sdf.inputs, "Band Width", 2).default_value = 3
    mean = A("GeometryNodeSDFGridMean", 1100, 200)
    gn.sock(mean.inputs, "Width", 1).default_value = 1
    to_mesh = A("GeometryNodeGridToMesh", 1400, 100)
    gn.sock(to_mesh.inputs, "Threshold", 1).default_value = 0.01
    gn.sock(to_mesh.inputs, "Adaptivity", 2).default_value = 0.0
    shade = A("GeometryNodeSetShadeSmooth", 1700, 100, domain="FACE")
    switch = A("GeometryNodeSwitch", 1850, 300, input_type="GEOMETRY")

    L(subd, "Mesh", to_sdf, "Mesh")
    L(gi, "Voxel Size", to_sdf, "Voxel Size", in_i=1)
    L(to_sdf, "SDF Grid", mean, "Grid")
    L(gi, "Smooth Iterations", mean, "Iterations", in_i=2)
    L(mean, "Grid", to_mesh, "Grid")
    L(to_mesh, "Mesh", shade, "Mesh")

    # Remesh toggle: False = subdivided mesh, True = remeshed
    L(gi, "Remesh", switch, "Switch")
    L(subd, "Mesh", switch, "False", in_i=1)
    L(shade, "Mesh", switch, "True", in_i=2)
    L(switch, "Output", go, "Geometry")
    return ng


def get_group():
    return gn.ensure_group(GROUP_NAME, REV, _build)


class MBT_OT_add_dynabool(bpy.types.Operator):
    bl_idname = "mbt.add_dynabool"
    bl_label = "DynaBool"
    bl_description = "Add the DynaBool modifier (crease by angle, subdivision, SDF remesh) to the selected meshes"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return gn.poll_mesh_selected(context)

    def execute(self, context):
        ok = gn.add_to_selected(self, context, get_group(), MODIFIER_NAME, DEFAULTS)
        return {"FINISHED"} if ok else {"CANCELLED"}


classes = (MBT_OT_add_dynabool,)


def draw(layout, context):
    layout.operator("mbt.add_dynabool", icon="MOD_SUBSURF")


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
