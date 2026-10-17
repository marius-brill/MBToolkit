"""Native-solver orchestration with checked results and transactional rollback."""

from math import isfinite
import bpy
from mathutils import Vector
from .context import UVError, UVSession
from .geometry import density, expand_islands, inspect, islands, triangle_area, triangles


def native(operator, **kwargs):
    result = operator(**kwargs)
    if result != {'FINISHED'}:
        raise UVError(f'{operator.idname()} did not finish')


def coordinates(session):
    return [(loop, state.layer, loop[state.layer].uv.copy())
            for state in session.states for face in state.targets for loop in face.loops]


def restore_coordinates(snapshot):
    for loop, layer, uv in snapshot:
        loop[layer].uv = uv


def update(session):
    for state in session.states:
        state.update()


def mark_seams(session, settings, angle=None):
    from .seams import smart
    return smart(session, settings, angle=angle)


def normalize(session, settings, target=None):
    expand_islands(session)
    # One datablock cannot represent different world-scale densities at once.
    for state in session.states:
        reference = state.obj.matrix_world.to_scale()
        for obj in session.selected:
            if obj.type == 'MESH' and obj.data == state.obj.data:
                scale = obj.matrix_world.to_scale()
                if any(abs(abs(scale[i]) - abs(reference[i])) > 1e-6 for i in range(3)):
                    raise UVError('Linked instances have different scales; make mesh data single-user for density')
    unit_scale = session.context.scene.unit_settings.scale_length
    measured = []
    for state in session.states:
        for group in islands(state):
            loops = [l for f in group for l in f.loops]
            if any(l[state.layer].pin_uv for l in loops):
                raise UVError('Density changes would move pinned UVs; unpin the affected islands')
            value = density(state, group, settings.width, settings.height, unit_scale)
            measured.append((state, loops, value))
    if not measured:
        raise UVError('No UV islands to measure')
    # Geometric mean keeps normalization independent of island enumeration.
    if target is None:
        from math import exp, log
        target = exp(sum(log(v) for _, _, v in measured) / len(measured))
    for state, loops, value in measured:
        center = sum((l[state.layer].uv for l in loops), Vector((0, 0))) / len(loops)
        for loop in loops:
            loop[state.layer].uv = center + (loop[state.layer].uv - center) * (target / value)
    update(session)


def pack(session, settings):
    """Dispatch constrained layouts or compare native shape-packing candidates.

    Each candidate starts from the same baseline. Exact checks, not native margin
    assumptions, decide acceptance. Constraints use the rectangle-layout backend.
    """
    if (settings.pack_backend == 'RECT' or settings.pack_scale == 'KEEP' or settings.preserve_stacks
            or settings.tile_start != 1001 or settings.tile_count != 1
            or settings.width != settings.height):
        from .layout import pack as constrained_pack
        return constrained_pack(session, settings)
    expand_islands(session)
    snapshot = coordinates(session)
    if any(loop[layer].pin_uv for loop, layer, _ in snapshot):
        from .layout import pack as constrained_pack
        return constrained_pack(session, settings)
    side = min(settings.width, settings.height) - 2 * settings.border
    if side <= 0 or settings.gap >= side:
        raise UVError('Gap or border is too large for the texture resolution')
    session.select_targets()
    shapes = ['CONCAVE']
    if settings.effort != 'FAST':
        shapes.append('CONVEX')
    if settings.effort == 'THOROUGH':
        shapes.append('AABB')
    best, best_score = None, -1
    last_reason = ''
    for shape in shapes:
        for multiplier in (1.05, 1.6, 2.5):
            restore_coordinates(snapshot)
            # Preserve shape in pixel space even for non-square images.
            for loop, layer, uv in snapshot:
                loop[layer].uv = (uv.x * settings.width / side, uv.y * settings.height / side)
            # Move the common centroid to tile 1001 before closest-UDIM packing.
            center = sum((l[layer].uv for l, layer, _ in snapshot), Vector((0, 0))) / len(snapshot)
            for loop, layer, _ in snapshot:
                loop[layer].uv += Vector((0.5, 0.5)) - center
            update(session)
            native(bpy.ops.uv.pack_islands, udim_source='CLOSEST_UDIM',
                   rotate=settings.rotation != 'NONE',
                   rotate_method=settings.rotation if settings.rotation != 'NONE' else 'ANY',
                   scale=True, merge_overlap=False, margin_method='ADD',
                   margin=min(0.45, settings.gap / side * multiplier),
                   pin=False, shape_method=shape)
            # Native closest-UDIM choice can differ between islands; require a
            # common output tile, then translate the whole layout to tile 1001.
            points = [l[layer].uv.copy() for l, layer, _ in snapshot]
            min_x, min_y = min(p.x for p in points), min(p.y for p in points)
            from math import floor
            offset = Vector((floor(min_x + 1e-6), floor(min_y + 1e-6)))
            for loop, layer, _ in snapshot:
                uv = loop[layer].uv - offset
                loop[layer].uv = ((settings.width - side) / (2 * settings.width) + uv.x * side / settings.width,
                                  (settings.height - side) / (2 * settings.height) + uv.y * side / settings.height)
            update(session)
            report = inspect(session, settings, padding=True)
            invalid = [k for k in ('degenerate', 'outside', 'overlaps', 'gap_violations',
                                   'border_violations') if report[k]]
            if invalid:
                last_reason = ', '.join(invalid)
                continue
            score = sum(abs(triangle_area(tri)) for state in session.states
                        for tri, _ in triangles(state, state.targets, settings.width, settings.height))
            if isfinite(score) and score > best_score:
                best_score, best = score, coordinates(session)
            break
    if best is None:
        raise UVError(f'No valid packing candidate ({last_reason}); original UVs restored')
    restore_coordinates(best)
    update(session)
    # Partial packing must not collide with any unselected visible UV geometry.
    original = [s.targets for s in session.states]
    try:
        for state in session.states:
            if state.layer:
                state.targets = {f for f in state.bm.faces if not f.hide}
        full = inspect(session, settings)
        if full['overlaps']:
            raise UVError('Packed layout overlaps excluded UVs; select the full layout or move excluded islands')
    finally:
        for state, targets in zip(session.states, original):
            state.targets = targets
    return best_score / (settings.width * settings.height)


def run(context, action, angle=None):
    settings = context.scene.mbt_uv
    settings.details = ''
    create = action in {'AUTO', 'UNWRAP', 'SEAMS', 'REPAIR_SEAMS', 'COMPLETE_SEAM', 'MARK_SELECTED', 'CLEAR_SELECTED'}
    with UVSession(context, create=create) as session:
        if action == 'SEAMS':
            added, regions = mark_seams(session, settings, angle)
            message = f'Region seams: {added} edges added; {regions} patches; boundaries validated'
        elif action in {'REPAIR_SEAMS', 'COMPLETE_SEAM'}:
            from .seams import repair
            added, unresolved = repair(session, settings, selected=action == 'COMPLETE_SEAM')
            message = f'Region completion: {added} edges added; boundaries validated'
        elif action in {'MARK_SELECTED', 'CLEAR_SELECTED'}:
            from .seams import selected_seams
            count = selected_seams(session, action == 'MARK_SELECTED')
            message = f'{count} selected seam edges updated'
        elif action in {'AUTO', 'UNWRAP', 'INPLACE', 'IMPROVE'}:
            unresolved = 0
            if action == 'AUTO':
                mark_seams(session, settings)
            from .automation import unwrap as smart_unwrap
            if action in {'INPLACE', 'IMPROVE'}:
                expand_islands(session)
            unwrap_result = smart_unwrap(session, settings, inplace=action in {'INPLACE', 'IMPROVE'})
            if action == 'AUTO':
                accepted, skipped = 0, []
                if settings.auto_shape:
                    from .shapes import apply
                    accepted, skipped = apply(session, settings, 'QUADRIFY', automatic=True)
                pinned = {s: s.targets for s in session.states}
                skipped_pins = 0
                try:
                    for state in session.states:
                        movable = []
                        for group in islands(state):
                            if any(l[state.layer].pin_uv for f in group for l in f.loops):
                                skipped_pins += 1
                            else:
                                movable.append(group)
                        state.targets = set().union(*movable) if movable else set()
                    if any(s.targets for s in session.states):
                        normalize(session, settings)
                finally:
                    for state, targets in pinned.items():
                        state.targets = targets
                occupancy = pack(session, settings)
                message = (f'Auto UV complete; {occupancy:.1%} coverage; {accepted} grids; '
                            f'{len(skipped)} shape skips; region boundaries validated; {unwrap_result}')
            elif action == 'IMPROVE':
                from .shapes import apply
                count, skipped = apply(session, settings, 'RELAX', automatic=True)
                message = f'Improved in place; {count} relaxed islands; {len(skipped)} skipped; {unwrap_result}'
            else:
                message = f'Unwrapped selected faces (no packing); {unwrap_result}'
        elif action in {'STRAIGHTEN', 'QUADRIFY', 'RECTIFY', 'CHAIN', 'RELAX', 'CIRCLE', 'ORIENT', 'ROTATE'}:
            from .shapes import apply
            count, _ = apply(session, settings, action)
            message = f'{action.title()}: {count} whole islands processed'
        elif action in {'SEAMS_UV', 'CLEAR_SEAMS'}:
            from .geometry import connected
            for state in session.states:
                for edge in state.bm.edges:
                    if not edge.link_faces or not all(f in state.targets for f in edge.link_faces):
                        continue
                    if action == 'CLEAR_SEAMS':
                        edge.seam = False
                    else:
                        loops = list(edge.link_loops)
                        edge.seam = len(loops) != 2 or not connected(loops[0], loops[1], state.layer)
                state.update()
            message = 'Seams updated from UV boundaries' if action == 'SEAMS_UV' else 'Target seams cleared'
        elif action in {'ALIGN_U', 'ALIGN_V'}:
            from .utilities import align
            align(session, settings, action)
            message = 'Selected UV vertices aligned; inspect for intentional collapse'
        elif action in {'WELD', 'STITCH', 'SPLIT'}:
            from .utilities import weld
            weld(session, settings, split=action == 'SPLIT')
            message = 'UV splits updated; mesh topology unchanged'
        elif action in {'DISTRIBUTE_U', 'DISTRIBUTE_V', 'MATCH_SIZE', 'FIT'}:
            from .utilities import transform
            transform(session, settings, action)
            message = f'{action.replace("_", " ").title()}: whole islands updated'
        elif action in {'PIN', 'UNPIN'}:
            expand_islands(session)
            for state in session.states:
                for face in state.targets:
                    for loop in face.loops:
                        loop[state.layer].pin_uv = action == 'PIN'
                # Explicit pin action commits pins, unlike temporary solver pins.
                state.commit_pins = True
                state.update()
            message = 'Whole affected islands locked' if action == 'PIN' else 'Whole affected islands unlocked'
        elif action.startswith('SELECT_'):
            from .selection import select
            count = select(session, settings, action)
            message = f'{action.replace("_", " ").title()}: {count} faces'
        elif action == 'MATCH_DENSITY':
            expand_islands(session)
            active = next((s for s in session.states if s.obj == session.active and s.targets), None)
            if active is None:
                raise UVError('Active object must have affected UV faces')
            reference = next((g for g in islands(active) if active.active_face in g), None)
            reference = reference or islands(active)[0]
            target = density(active, reference, settings.width, settings.height,
                             context.scene.unit_settings.scale_length)
            normalize(session, settings, target)
            message = f'Matched active island density: {target:.3f} px/m'
        elif action == 'PACK':
            occupancy = pack(session, settings)
            message = f'Packed whole affected islands; {occupancy:.1%} tile coverage'
        elif action in {'DENSITY', 'NORMALIZE'}:
            normalize(session, settings, settings.density if action == 'DENSITY' else None)
            message = 'Island density updated (whole affected islands)'
        elif action == 'MEASURE':
            expand_islands(session)
            active = next((s for s in session.states if s.obj == context.active_object and s.targets), None)
            active = active or next(s for s in session.states if s.targets)
            settings.density = density(active, active.targets, settings.width, settings.height,
                                       context.scene.unit_settings.scale_length)
            unit = 'px/cm' if settings.density_unit == 'CM' else 'px/m'
            message = f'Measured {settings.density_display:.3f} {unit} on active target'
        elif action in {'INSPECT', 'COUNT'}:
            report = inspect(session, settings, padding=action == 'INSPECT')
            message = (f"{report['islands']} islands; {report['degenerate']} collapsed; "
                       f"{report['flipped']} negative-winding triangles; {report['overlaps']} overlaps; "
                       f"{report['outside']} outside; {report['gap_violations']} gap pairs; "
                       f"{report['border_violations']} border triangles")
        else:
            raise UVError(f'Unknown UV action: {action}')
        if action in {'AUTO', 'SEAMS', 'REPAIR_SEAMS', 'COMPLETE_SEAM'}:
            from .seams import validate
            for state in session.states:
                validate(state)
    settings.report = message
    return message