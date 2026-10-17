"""Constrained face-region segmentation and strict seam-boundary validation.

Seams are extracted from complete region labels, never grown from endpoints.
Conservative agglomeration is followed by whole-interface simplification. Only
artist/material constraints are permanent; automatic crease seeds are evidence.
"""
from math import cos, radians
from collections import deque
from .context import UVError


def simplify_regions(members, writable, protected, settings, threshold):
    """Remove whole interfaces using a scale-independent geometric objective.

    Initial labels are deliberately conservative. Automatic crease seeds are not
    protected here: only user/material constraints prohibit a merge. All scores
    have area units, making the decision independent of uniform mesh scale.
    """
    groups = {key: set(faces) for key, faces in members.items()}
    owner = {face: key for key, faces in groups.items() for face in faces}
    areas = {f: f.calc_area() for f in owner}
    centers = {f: f.calc_center_median() for f in owner}
    tolerance = max(1 - cos(radians(min(85, settings.region_angle * 2))), 0.05)
    work = 0
    ordered_edges = sorted(writable, key=lambda e: e.index)

    def measure(faces):
        nonlocal work
        work += len(faces)
        if work > 10000000:
            raise UVError('Region simplification budget exceeded; process separate mesh components')
        first = next(iter(faces))
        zero = first.normal * 0
        area = sum(areas[f] for f in faces)
        normal = sum((f.normal * areas[f] for f in faces), zero)
        coherence = normal.length / area
        direction = normal.normalized()
        center = sum((centers[f] * areas[f] for f in faces), zero) / area
        radius = sum(areas[f] * (centers[f] - center).length_squared for f in faces)
        residual = sum(areas[f] * (centers[f] - center).dot(direction) ** 2 for f in faces)
        # Plane residual is supporting evidence only; curved charts are allowed.
        energy = area * ((1 - coherence) / tolerance +
                         0.2 * residual / max(radius, area * 1e-12))
        return area, energy, coherence, center, direction

    stats = {key: measure(faces) for key, faces in groups.items()}
    merges = 0
    while True:
        work += len(ordered_edges)
        if work > 10000000:
            raise UVError('Region simplification budget exceeded; process separate mesh components')
        interfaces = {}
        blocked = set()
        for edge in ordered_edges:
            a, b = (owner[f] for f in edge.link_faces)
            if a == b:
                continue
            pair = frozenset((a, b))
            interfaces.setdefault(pair, []).append(edge)
            if edge in protected:
                blocked.add(pair)
        best = None
        for pair, edges in interfaces.items():
            if pair in blocked:
                continue
            a, b = sorted(pair, key=lambda key: tuple(stats[key][3]))
            merged = groups[a] | groups[b]
            area, energy, coherence, center, direction = measure(merged)
            # Do not collapse an enclosing surface into a single folded chart.
            if coherence < 0.45 or any(f.normal.dot(direction) < -0.05 for f in merged):
                continue
            local_scale = min(stats[a][0], stats[b][0]) ** 0.5
            length = sum(e.calc_length() for e in edges)
            support = sum(e.calc_length() * min(4, (e.calc_face_angle(0) /
                          max(threshold, 1e-6)) ** 2) for e in edges)
            # Small/narrow regions gain more from removing a long shared border.
            reward = local_scale * (0.65 * length - 0.6 * support)
            reward += 0.08 * min(stats[a][0], stats[b][0])
            gain = reward - (energy - stats[a][1] - stats[b][1])
            rank = (gain / area, tuple(center), tuple(stats[a][3]))
            if gain > area * 1e-8 and (best is None or rank > best[0]):
                best = (rank, a, b, merged, (area, energy, coherence, center, direction))
        if best is None:
            break
        _, a, b, merged, measured = best
        groups[a] = merged
        stats[a] = measured
        del groups[b], stats[b]
        for face in merged:
            owner[face] = a
        merges += 1
    cuts = {e for e in writable if owner[e.link_faces[0]] != owner[e.link_faces[1]]}
    return cuts, len(groups), merges


def eligible(state, edge):
    return (not edge.hide and len(edge.link_faces) == 2 and
            all(f in state.targets and not f.hide for f in edge.link_faces))


def seam_graph(state):
    return {v: [e for e in v.link_edges if e.seam] for v in state.bm.verts}


def validate(state, affected=None):
    """Every scoped seam must separate face components in the full cut mesh.

    This rejects slit endpoints AND bridges between otherwise closed loops. Only
    actual mesh boundaries may terminate seams; scope boundaries are not exemptions.
    """
    affected = state.targets if affected is None else affected
    edges = {e for f in affected for e in f.edges if e.seam}
    vertices = {v for e in edges for v in e.verts}
    graph = seam_graph(state)
    dangling = [v for v in vertices if len(graph[v]) == 1 and
                not any(e.is_boundary for e in v.link_edges)]
    if dangling:
        raise UVError(f'{state.obj.name}: {len(dangling)} interior seam endpoints; '
                      'cannot commit an open contour. Reveal/select the full surface and retry')
    remaining = set(state.bm.faces)
    labels, index = {}, 0
    while remaining:
        start = remaining.pop()
        labels[start] = index
        stack = [start]
        while stack:
            for edge in stack.pop().edges:
                if edge.seam or len(edge.link_faces) != 2:
                    continue
                for other in edge.link_faces:
                    if other in remaining:
                        remaining.remove(other)
                        labels[other] = index
                        stack.append(other)
        index += 1
    invalid = [e for e in edges if len(e.link_faces) > 2 or
               (len(e.link_faces) == 2 and labels[e.link_faces[0]] == labels[e.link_faces[1]])]
    if invalid:
        raise UVError(f'{state.obj.name}: {len(invalid)} seam edges do not separate surface regions; '
                      'full region boundary is blocked by hidden/excluded or non-manifold geometry')
    return index


def segment(state, settings, generate=True, selected=False, angle=None):
    bm = state.bm
    bm.faces.index_update()
    bm.edges.index_update()
    faces = set(state.targets)
    if not faces:
        return 0, 0
    if any(f.calc_area() < 1e-12 for f in faces):
        raise UVError(f'{state.obj.name}: zero-area faces prevent reliable surface segmentation')
    relevant = {e for f in faces for e in f.edges}
    if any(len(e.link_faces) > 2 for e in relevant):
        raise UVError(f'{state.obj.name}: non-manifold face adjacency; repair the mesh first')
    writable = {e for e in relevant if eligible(state, e)}
    before = {e for e in relevant if e.seam}
    required = set() if generate and settings.seams == 'REBUILD' else before & writable
    if selected:
        chosen = {e for e in writable if e.select}
        if not chosen:
            raise UVError('Select the intended contour edges in mesh Edge Select mode')
        # Selected missing edges are hard constraints, not only existing seams.
        required |= chosen
    threshold = radians(settings.angle if angle is None else angle)
    if generate and settings.material_seams:
        required |= {e for e in writable if len({f.material_index for f in e.link_faces}) > 1}
    protected = set(required)
    if generate:
        required |= {e for e in writable if e.calc_face_angle(0) >= threshold or
                     (settings.material_seams and len({f.material_index for f in e.link_faces}) > 1)}
    # Existing cuts on the scope perimeter cannot change, but their incident target
    # faces remain constrained by the final full-mesh boundary validator.
    parent = {f: f for f in faces}
    members = {f: [f] for f in faces}
    normals = {f: f.normal.copy() * f.calc_area() for f in faces}
    forbidden = {f: set() for f in faces}
    for edge in required:
        a, b = edge.link_faces
        forbidden[a].add(b)
        forbidden[b].add(a)

    def root(face):
        while parent[face] != face:
            parent[face] = parent[parent[face]]
            face = parent[face]
        return face

    # Limit normal spread against the complete region mean, not just each adjacent
    # face, so gradual curvature cannot flood-fill around a closed object.
    spread = cos(radians(settings.region_angle)) if generate else -1.0
    # Grow coherent patches out from both sides of protected cuts before merging
    # remote ambiguous faces. This closes low-angle gaps without prematurely
    # joining the two sides through an unmarked portion of the boundary.
    distances = {f: 0 for e in required for f in e.link_faces}
    tangents = {}
    for edge in sorted(required, key=lambda e: e.index):
        for face in edge.link_faces:
            tangents.setdefault(face, (edge.verts[1].co - edge.verts[0].co).normalized())
    queue = deque(sorted(distances, key=lambda f: f.index))
    while queue:
        face = queue.popleft()
        for edge in face.edges:
            if edge not in writable or edge in required:
                continue
            for other in edge.link_faces:
                if other not in distances:
                    distances[other] = distances[face] + 1
                    tangents[other] = tangents[face]
                    queue.append(other)
    def boundary_alignment(edge):
        direction = (edge.verts[1].co - edge.verts[0].co).normalized()
        return max((abs(direction.dot(tangents[f])) for f in edge.link_faces if f in tangents), default=0)

    candidates = sorted(writable - required,
                        key=lambda e: (round(boundary_alignment(e), 5),
                                       round(e.calc_face_angle(0), 6), -e.calc_length(), e.index))
    checks = 0
    for edge in candidates:
        a, b = (root(f) for f in edge.link_faces)
        if a == b or b in forbidden[a]:
            continue
        normal = normals[a] + normals[b]
        if normal.length < 1e-12:
            continue
        direction = normal.normalized()
        combined = members[a] + members[b]
        checks += len(combined)
        if checks > 10000000:
            raise UVError('Surface segmentation budget exceeded; process separate mesh components')
        if any(f.normal.dot(direction) < spread for f in combined):
            continue
        if len(members[a]) < len(members[b]):
            a, b = b, a
        blocked = (forbidden[a] | forbidden[b]) - {a, b}
        for other in blocked:
            forbidden[other].discard(a)
            forbidden[other].discard(b)
            forbidden[other].add(a)
        parent[b] = a
        members[a] = combined
        normals[a] = normal
        forbidden[a] = blocked
        del members[b], normals[b], forbidden[b]
    cuts = {e for e in writable if root(e.link_faces[0]) != root(e.link_faces[1])}
    patches = len(members)
    if generate:
        cuts, patches, merges = simplify_regions(members, writable, protected, settings, threshold)
        settings.details += f'{state.obj.name}: {merges} redundant region interfaces removed; {patches} patches\n'
    if not protected <= cuts:
        raise UVError('Surface segmentation violated a protected seam constraint')
    # Stage complete labels before assigning seam flags. Rebuild may remove only
    # writable old seams; Extend/Repair never delete a manual cut.
    for edge in writable:
        edge.seam = edge in cuts
    validate(state)
    return len(cuts - before), patches


def smart(session, settings, generate=True, selected=False, angle=None):
    if selected and session.object_mode:
        raise UVError('Use mesh Edit Mode and select the intended contour edges')
    if generate and settings.seams == 'PRESERVE':
        for state in session.states:
            validate(state)
        return 0, 0
    added = regions = 0
    for state in session.states:
        count, patches = segment(state, settings, generate, selected, angle)
        added += count
        regions += patches
    # Validate every object before updating any edit mesh; UVSession rolls back
    # all staged flags if one object fails.
    for state in session.states:
        validate(state)
    for state in session.states:
        state.update()
    return added, regions


def repair(session, settings, selected=False):
    added, _ = smart(session, settings, generate=False, selected=selected)
    return added, 0


def selected_seams(session, marked):
    changed = 0
    if session.object_mode:
        raise UVError('Use mesh Edit Mode and select seam edges')
    for state in session.states:
        for edge in state.bm.edges:
            if edge.select and not edge.hide and all(not f.hide and f in state.targets for f in edge.link_faces):
                changed += edge.seam != marked
                edge.seam = marked
        state.update()
    return changed