"""Transactional mesh access. UV tools never change mesh topology."""

import bpy
import bmesh


class UVError(RuntimeError):
    pass


def uv_selected(loop, layer):
    return loop.uv_select_vert


def set_uv_selected(loop, layer, value):
    loop.uv_select_vert = value
    loop.uv_select_edge = value


class MeshState:
    def __init__(self, obj, context, object_mode):
        self.obj = obj
        self.bm = bmesh.from_edit_mesh(obj.data)
        bm = self.bm
        bm.faces.index_update()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        self.layer = bm.loops.layers.uv.active
        self.created = False
        self.commit_pins = False
        self.commit_selection = False
        self.vertices = [(v, v.select) for v in bm.verts]
        self.edges = [(e, e.select, e.seam) for e in bm.edges]
        self.faces = [(f, f.select) for f in bm.faces]
        self.active_face = bm.faces.active
        self.history = list(bm.select_history)
        self.loops = [(l, l.uv_select_vert, l.uv_select_edge,
                       l[self.layer].uv.copy() if self.layer else None,
                       l[self.layer].pin_uv if self.layer else False)
                      for f in bm.faces for l in f.loops]
        use_uv = (not object_mode and context.area is not None
                  and context.area.type == 'IMAGE_EDITOR'
                  and not context.tool_settings.use_uv_select_sync)
        self.use_uv = use_uv
        self.targets = {f for f in bm.faces if not f.hide and
                        (object_mode or ((f.select or
                         (context.tool_settings.mesh_select_mode[1] and any(e.select for e in f.edges))) and
                         (not use_uv or any(uv_selected(l, self.layer) for l in f.loops))))}

    def ensure_uv(self):
        if self.layer is None:
            self.layer = self.bm.loops.layers.uv.new('UVMap')
            self.created = True
            # Adding loop custom data invalidates BMLoop Python wrappers.
            self.loops = [(l, l.uv_select_vert, l.uv_select_edge, None, False)
                          for f in self.bm.faces for l in f.loops]
        return self.layer

    def update(self):
        bmesh.update_edit_mesh(self.obj.data, loop_triangles=False, destructive=False)

    def restore(self, rollback):
        saved_selection = None
        if self.commit_selection and not rollback:
            saved_selection = ([(v, v.select) for v in self.bm.verts],
                               [(e, e.select) for e in self.bm.edges],
                               [(f, f.select) for f in self.bm.faces],
                               [(l, l.uv_select_vert, l.uv_select_edge)
                                for f in self.bm.faces for l in f.loops])
        if rollback:
            for edge, _, seam in self.edges:
                edge.seam = seam
            if self.created:
                selection = [(selected, edge_selected) for _, selected, edge_selected, _, _ in self.loops]
                self.bm.loops.layers.uv.remove(self.layer)
                self.layer = None
                self.loops = [(l, selected, edge_selected, None, False)
                              for l, (selected, edge_selected) in zip(
                                  (l for f in self.bm.faces for l in f.loops), selection)]
            elif self.layer:
                for loop, _, _, uv, pin in self.loops:
                    loop[self.layer].uv = uv
                    loop[self.layer].pin_uv = pin
        for vert, selected in self.vertices:
            vert.select = selected
        for edge, selected, _ in self.edges:
            edge.select = selected
        for face, selected in self.faces:
            face.select = selected
        for loop, selected, edge_selected, _, pin in self.loops:
            loop.uv_select_vert = selected
            loop.uv_select_edge = edge_selected
            if self.layer and (rollback or not self.commit_pins):
                loop[self.layer].pin_uv = pin
        self.bm.faces.active = self.active_face
        self.bm.select_history.clear()
        for element in self.history:
            self.bm.select_history.add(element)
        if saved_selection:
            verts, edges, faces, loops = saved_selection
            for element, selected in verts + edges + faces:
                element.select = selected
            for loop, selected, edge_selected in loops:
                loop.uv_select_vert = selected
                loop.uv_select_edge = edge_selected
        self.update()


class UVSession:
    """Restore selection always; roll back coordinates, maps and seams on error."""
    def __init__(self, context, create=False):
        self.context = context
        self.create = create
        self.states = []
        self.object_mode = context.mode == 'OBJECT'
        self.active = context.view_layer.objects.active
        self.selected = list(context.selected_objects)
        self.sync = context.tool_settings.use_uv_select_sync
        self.mesh_mode = tuple(context.tool_settings.mesh_select_mode)
        self.uv_mode = context.tool_settings.uv_select_mode

    def __enter__(self):
        context = self.context
        if context.mode not in {'OBJECT', 'EDIT_MESH'}:
            raise UVError('Use Object Mode or mesh Edit Mode')
        candidates = (context.selected_objects if self.object_mode
                      else context.objects_in_mode_unique_data)
        objects = [o for o in candidates if o.type == 'MESH' and o.is_editable
                   and o.data.is_editable and o.visible_get()]
        if not objects:
            raise UVError('Select an editable mesh')
        try:
            if self.object_mode:
                for obj in self.selected:
                    obj.select_set(False)
                for obj in objects:
                    obj.select_set(True)
                context.view_layer.objects.active = objects[0]
                bpy.ops.object.mode_set(mode='EDIT')
            seen = set()
            for obj in objects:
                if obj.data.as_pointer() in seen:
                    continue
                seen.add(obj.data.as_pointer())
                state = MeshState(obj, context, self.object_mode)
                self.states.append(state)
                if state.targets:
                    if self.create:
                        state.ensure_uv()
                    elif state.layer is None:
                        raise UVError(f'{obj.name}: no active UV map; unwrap first')
            if not any(s.targets for s in self.states):
                raise UVError('Select visible faces or UVs; empty selection never means all')
            return self
        except Exception:
            self.__exit__(True, None, None)
            raise

    def select_targets(self):
        settings = self.context.tool_settings
        settings.use_uv_select_sync = False
        settings.mesh_select_mode = (False, False, True)
        settings.uv_select_mode = 'VERTEX'
        for state in self.states:
            for vert in state.bm.verts:
                vert.select = False
            for edge in state.bm.edges:
                edge.select = False
            for face in state.bm.faces:
                face.select = False
            for face in state.bm.faces:
                face.select_set(face in state.targets)
                for loop in face.loops:
                    set_uv_selected(loop, state.layer, face in state.targets)
            state.update()

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            # Changing sync/select modes can flush selection: restore them first.
            settings = self.context.tool_settings
            settings.use_uv_select_sync = self.sync
            settings.mesh_select_mode = self.mesh_mode
            settings.uv_select_mode = self.uv_mode
            errors = []
            for state in self.states:
                try:
                    state.restore(bool(exc_type))
                except Exception as error:
                    errors.append(error)
            if errors:
                raise UVError(f'UV state restoration failed: {errors[0]}')
        finally:
            settings = self.context.tool_settings
            settings.use_uv_select_sync = self.sync
            settings.mesh_select_mode = self.mesh_mode
            settings.uv_select_mode = self.uv_mode
            if self.object_mode and self.context.mode == 'EDIT_MESH':
                bpy.ops.object.mode_set(mode='OBJECT')
                for obj in self.context.selected_objects:
                    obj.select_set(False)
                for obj in self.selected:
                    obj.select_set(True)
                self.context.view_layer.objects.active = self.active
        return False