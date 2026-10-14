"""Crease by angle: stores a crease value on edges sharper than the threshold."""

from math import pi, radians

import bpy

from ...core import gn
from ...core.registry import register_classes, unregister_classes

GROUP_NAME = "CreaseByAngle"
MODIFIER_NAME = "CreaseByAngle"
REV = 1

DEFAULTS = {"Threshold": radians(30.0), "Value": 1.0, "Attribute": "crease_edge"}


def _build():
    ng = bpy.data.node_groups.new(GROUP_NAME, "GeometryNodeTree")
    iface = ng.interface
    gn.add_input(iface, "Geometry", "NodeSocketGeometry")
    gn.add_input(iface, "Threshold", "NodeSocketFloat", DEFAULTS["Threshold"], 0.0, pi, subtype="ANGLE")
    gn.add_input(iface, "Value", "NodeSocketFloat", DEFAULTS["Value"], 0.0, 1.0, field=True)
    gn.add_input(iface, "Attribute", "NodeSocketString", DEFAULTS["Attribute"])
    gn.add_output(iface, "Geometry", "NodeSocketGeometry")

    nodes, links = ng.nodes, ng.links
    gi = gn.add_node(nodes, "NodeGroupInput", -600, 0)
    angle = gn.add_node(nodes, "GeometryNodeInputMeshEdgeAngle", -350, 150)
    cmp = gn.add_node(nodes, "FunctionNodeCompare", -100, 150, data_type="FLOAT", operation="GREATER_EQUAL")
    named = gn.add_node(nodes, "GeometryNodeInputNamedAttribute", -350, -150, data_type="FLOAT")
    add = gn.add_node(nodes, "ShaderNodeMath", 150, 50, operation="ADD")
    store = gn.add_node(nodes, "GeometryNodeStoreNamedAttribute", 450, 0, data_type="FLOAT", domain="EDGE")
    go = gn.add_node(nodes, "NodeGroupOutput", 750, 0)

    L = lambda *a, **k: gn.link(links, *a, **k)
    L(angle, "Unsigned Angle", cmp, "A")  # float A/B are the first two inputs
    links.new(gi.outputs["Threshold"], cmp.inputs[1])
    links.new(cmp.outputs[0], add.inputs[0])
    L(gi, "Attribute", named, "Name")
    links.new(named.outputs[0], add.inputs[1])
    L(gi, "Attribute", store, "Name", in_i=2)  # the reference left this one as a typed-in name
    links.new(add.outputs[0], store.inputs["Selection"])
    L(gi, "Value", store, "Value", in_i=3)
    L(gi, "Geometry", store, "Geometry")
    L(store, "Geometry", go, "Geometry")
    return ng


def get_group():
    return gn.ensure_group(GROUP_NAME, REV, _build)


class MBT_OT_add_crease_by_angle(bpy.types.Operator):
    bl_idname = "mbt.add_crease_by_angle"
    bl_label = "Add Crease by Angle"
    bl_description = "Add the CreaseByAngle modifier to the selected meshes"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return gn.poll_mesh_selected(context)

    def execute(self, context):
        ok = gn.add_to_selected(self, context, get_group(), MODIFIER_NAME, DEFAULTS)
        return {"FINISHED"} if ok else {"CANCELLED"}


classes = (MBT_OT_add_crease_by_angle,)


def draw(layout, context):
    layout.operator("mbt.add_crease_by_angle", icon="MOD_EDGESPLIT")


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
