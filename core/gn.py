"""Helpers shared by the Geometry Nodes setups."""

import bpy


def sock(sockets, name, index=0):
    """Look a socket up by name, fall back to position if a node renamed it."""
    s = sockets.get(name)
    return s if s is not None else sockets[index]


def add_node(nodes, idname, x, y, **attrs):
    node = nodes.new(idname)
    node.location = (x, y)
    for key, value in attrs.items():
        setattr(node, key, value)
    return node


def link(links, out_node, out_name, in_node, in_name, out_i=0, in_i=0):
    links.new(sock(out_node.outputs, out_name, out_i), sock(in_node.inputs, in_name, in_i))


def add_input(iface, name, socket_type, default=None, min_value=None, max_value=None, subtype=None, field=False):
    s = iface.new_socket(name, in_out="INPUT", socket_type=socket_type)
    if subtype is not None:
        s.subtype = subtype
    if min_value is not None:
        s.min_value = min_value
    if max_value is not None:
        s.max_value = max_value
    if default is not None:
        s.default_value = default
    if field:
        try:
            s.structure_type = "FIELD"
        except Exception:
            pass
    return s


def add_output(iface, name, socket_type):
    return iface.new_socket(name, in_out="OUTPUT", socket_type=socket_type)


def ensure_group(name, rev, build):
    """Reuse the node group if it is the current revision, otherwise rebuild it.
    An outdated group is kept as '<name>.old' so existing modifiers don't break."""
    ng = bpy.data.node_groups.get(name)
    if ng is not None and ng.get("mbt_rev") == rev:
        return ng
    if ng is not None:
        ng.name = f"{name}.old"
    ng = build()
    ng["mbt_rev"] = rev
    return ng


def modifier_inputs(mod):
    """Return modern input storage, or None on legacy Blender versions."""
    props = getattr(mod, 'properties', None)
    return getattr(props, 'inputs', None) if props is not None else None


def legacy_modifier_input_exists(mod, identifier):
    """Some modifier structs deliberately do not support IDProperties."""
    try:
        return identifier in mod
    except TypeError:
        return False


def set_modifier_input(mod, identifier, value):
    """Blender 5.2 moved GN modifier inputs to modifier.properties.inputs.<id>.value."""
    inputs = modifier_inputs(mod)
    if inputs is not None:
        socket_prop = getattr(inputs, identifier, None)
        if socket_prop is None or 'value' not in socket_prop.bl_rna.properties:
            raise ValueError(f'Modifier input {identifier!r} has no editable value')
        socket_prop.value = value
    else:
        try:
            mod[identifier] = value  # Blender < 5.2
        except TypeError as exc:
            raise ValueError(f'Modifier input {identifier!r} is unavailable') from exc


def add_to_selected(operator, context, group, modifier_name, values):
    """Add a GN modifier using `group` to every selected mesh that doesn't have it yet."""
    ids = {
        i.name: i.identifier
        for i in group.interface.items_tree
        if getattr(i, "item_type", "") == "SOCKET" and i.in_out == "INPUT"
    }
    added = 0
    for obj in context.selected_objects:
        if obj.type != "MESH" or modifier_name in obj.modifiers:
            continue
        mod = obj.modifiers.new(modifier_name, "NODES")
        mod.node_group = group
        for name, value in values.items():
            if name in ids:
                set_modifier_input(mod, ids[name], value)
        obj.update_tag()
        added += 1
    if not added:
        operator.report({"WARNING"}, f"Nothing added (no mesh selected, or it already has {modifier_name})")
        return False
    return True


def poll_mesh_selected(context):
    return any(o.type == "MESH" for o in context.selected_objects)
