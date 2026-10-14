"""Triangle count and modifier cost for visible objects.

Blender does not expose its per-modifier timings (the ms shown in the modifier
panel) to Python, as far as I know, so "Profile" measures them.

Quick (default): re-evaluates each object that has modifiers once and times it.
Per-modifier: also toggles the modifiers on one by one in stack order and times each
step. Roughly (modifiers + 1) evaluations per object, so use it on selected objects.
Modifier visibility is restored afterwards.
"""

import time

import bpy
from bpy.props import BoolProperty

from ..core.registry import register_classes, unregister_classes

MESHY_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}
MAX_ROWS = 60

# object name -> {"tris": int, "ms": float | None, "mods": [(name, ms)]}
CACHE = {}


def visible_objects(context):
    return [o for o in context.view_layer.objects if o.type in MESHY_TYPES and o.visible_get()]


def _tri_count(mesh):
    for attr in ("corner_tris", "loop_triangles"):
        tris = getattr(mesh, attr, None)
        if tris is not None:
            try:
                return len(tris)
            except Exception:
                pass
    return sum(len(p.vertices) - 2 for p in mesh.polygons)


def evaluated_tris(depsgraph, obj):
    eval_obj = obj.evaluated_get(depsgraph)
    try:
        mesh = eval_obj.to_mesh()
    except RuntimeError:
        return 0
    if mesh is None:
        return 0
    try:
        return _tri_count(mesh)
    finally:
        eval_obj.to_mesh_clear()


def _time_update(context, obj):
    obj.update_tag()
    start = time.perf_counter()
    context.view_layer.update()
    return (time.perf_counter() - start) * 1000.0


def _best_time(context, obj, samples):
    return min(_time_update(context, obj) for _ in range(max(1, samples)))


def profile_object(context, obj, samples):
    mods = list(obj.modifiers)
    was_on = [m.show_viewport for m in mods]
    results = []
    try:
        for m in mods:
            m.show_viewport = False
        previous = _best_time(context, obj, samples)
        for m, enabled in zip(mods, was_on):
            if not enabled:
                results.append((m.name, 0.0))
                continue
            m.show_viewport = True
            current = _best_time(context, obj, samples)
            results.append((m.name, max(0.0, current - previous)))
            previous = current
    finally:
        for m, enabled in zip(mods, was_on):
            m.show_viewport = enabled
        obj.update_tag()
    return results


class MBT_OT_stats_refresh(bpy.types.Operator):
    bl_idname = "mbt.stats_refresh"
    bl_label = "Refresh Tris"
    bl_description = "Recount evaluated triangles of all visible objects"

    def execute(self, context):
        depsgraph = context.evaluated_depsgraph_get()
        for obj in visible_objects(context):
            entry = CACHE.setdefault(obj.name, {"tris": 0, "ms": None, "mods": []})
            entry["tris"] = evaluated_tris(depsgraph, obj)
        return {"FINISHED"}


class MBT_OT_stats_profile(bpy.types.Operator):
    bl_idname = "mbt.stats_profile"
    bl_label = "Profile"
    bl_description = "Measure how long each object takes to evaluate (one re-evaluation per object)"

    only_selected: BoolProperty(name="Selected Only", default=False)

    def execute(self, context):
        detailed = context.scene.mbt.stats_detailed
        targets = visible_objects(context)
        if self.only_selected:
            targets = [o for o in targets if o.select_get()]
        context.view_layer.update()  # flush pending changes so they don't get billed to the first object
        for obj in targets:
            entry = CACHE.setdefault(obj.name, {"tris": 0, "ms": None, "mods": []})
            if not obj.modifiers:
                entry["ms"], entry["mods"] = 0.0, []
            elif detailed:
                entry["mods"] = profile_object(context, obj, samples=1)
                entry["ms"] = sum(ms for _, ms in entry["mods"])
            else:
                entry["mods"] = []
                entry["ms"] = _time_update(context, obj)
        bpy.ops.mbt.stats_refresh()
        return {"FINISHED"}


classes = (MBT_OT_stats_refresh, MBT_OT_stats_profile)


def _fmt_tris(n):
    return f"{n / 1000:.1f}k" if n >= 10000 else str(n)


def draw(layout, context):
    props = context.scene.mbt
    row = layout.row(align=True)
    row.operator("mbt.stats_refresh", icon="FILE_REFRESH")
    row.operator("mbt.stats_profile", icon="TIME").only_selected = False
    row.operator("mbt.stats_profile", icon="RESTRICT_SELECT_OFF", text="").only_selected = True
    row = layout.row()
    row.prop(props, "stats_detailed")
    row.prop(props, "stats_show_modifiers")
    layout.row().prop(props, "stats_sort", expand=True)

    rows = []
    for name, entry in CACHE.items():
        obj = bpy.data.objects.get(name)
        if obj is not None and obj.visible_get():
            rows.append((obj, entry))
    if not rows:
        layout.label(text="Press Refresh to scan visible objects")
        return

    if props.stats_sort == "TRIS":
        rows.sort(key=lambda r: (r[1]["tris"], r[1]["ms"] or 0.0), reverse=True)
    else:
        rows.sort(key=lambda r: (r[1]["ms"] or 0.0, r[1]["tris"]), reverse=True)

    total_tris = sum(e["tris"] for _, e in rows)
    total_ms = sum(e["ms"] or 0.0 for _, e in rows)
    layout.label(text=f"{len(rows)} objects  |  {_fmt_tris(total_tris)} tris  |  {total_ms:.1f} ms")

    col = layout.column(align=True)
    for obj, entry in rows[:MAX_ROWS]:
        ms = entry["ms"]
        row = col.row(align=True)
        row.alert = bool(ms and ms > 50.0)
        row.label(text=obj.name, icon="OBJECT_DATA")
        row.label(text=_fmt_tris(entry["tris"]))
        row.label(text="-" if ms is None else f"{ms:.1f} ms")
        if props.stats_show_modifiers:
            for mod_name, mod_ms in entry["mods"]:
                sub = col.row(align=True)
                sub.label(text=f"    {mod_name}")
                sub.label(text="")
                sub.label(text=f"{mod_ms:.1f} ms")
    if len(rows) > MAX_ROWS:
        layout.label(text=f"... and {len(rows) - MAX_ROWS} more")


def register():
    register_classes(classes)


def unregister():
    CACHE.clear()
    unregister_classes(classes)
