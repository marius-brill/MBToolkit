"""Blender-side Painter preparation and manual texture round-trip."""
from . import settings, operators


def register():
    settings.register()
    operators.register()


def unregister():
    operators.unregister()
    settings.unregister()


def draw(layout, context):
    props = context.scene.mbt_painter
    layout.label(text='Substance Painter — Blender Setup')
    for role, attribute in (('LOW', 'low_collection'), ('HIGH', 'high_collection')):
        row = layout.row(align=True)
        row.prop(props, attribute)
        row.operator('mbt.painter_assign', text='', icon='ADD').role = role
    layout.prop(props, 'project_name')
    layout.prop(props, 'output_dir')
    layout.prop(props, 'project_template')
    layout.prop(props, 'resolution')
    box = layout.box()
    box.label(text='Requested Bake Maps')
    box.prop(props, 'bake_maps')
    box.prop(props, 'front_distance')
    box.prop(props, 'rear_distance')
    box.prop(props, 'relative_distance')
    box.prop(props, 'antialiasing')
    if 'ID' in props.bake_maps:
        box.prop(props, 'id_source')
    box.label(text='Matching: By Mesh Name')
    active = context.active_object
    if active and active.type == 'MESH':
        box.prop(active, 'mbt_bake_target')
    box.label(text='Unassigned: automatic name / surface matching')
    layout.prop(props, 'normal_format')
    layout.prop(props, 'replace_materials')
    connection = layout.column(align=True)
    from . import runtime
    connection.enabled = not runtime.busy()
    connection.scale_y = 1.5
    connection.operator('mbt.painter_connect', text='Bake', icon='RENDER_STILL').action = 'AUTO'
    if runtime.busy():
        layout.operator('mbt.painter_cancel', icon='CANCEL')
    layout.prop(props, 'advanced', icon='TRIA_DOWN' if props.advanced else 'TRIA_RIGHT', emboss=False)
    if props.advanced:
        advanced = layout.column()
        advanced.enabled = not runtime.busy()
        advanced.prop(props, 'export_config')
        advanced.operator('mbt.painter_connect', text='Update Textures (No Bake)', icon='IMPORT').action = 'EXPORT'
        advanced.operator('mbt.painter_new_project', text='New Project Next Bake', icon='FILE_NEW')
        row = advanced.row(align=True)
        row.operator('mbt.painter_connect', text='Test Connection').action = 'TEST'
        row.operator('mbt.painter_connect', text='Launch / Connect').action = 'CONNECT'
        advanced.operator('mbt.painter_action', text='Validate').action = 'VALIDATE'
        advanced.operator('mbt.painter_action', text='Retry Material Import').action = 'IMPORT'
    if props.report:
        box = layout.box()
        # Wrap long reports to remain readable in a narrow sidebar.
        import textwrap
        for line in textwrap.wrap(props.report, width=42):
            box.label(text=line)