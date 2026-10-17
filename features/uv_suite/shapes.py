"""Topology-aware UV shape tools, operating on UV vertices rather than mesh vertices.

All candidates are staged in Python coordinates and checked before commit. No
mesh topology or permanent pin edits are needed for the harmonic interior solve.
"""
from collections import defaultdict, deque
from math import atan2, cos, sin, pi, sqrt, isfinite
from mathutils import Vector
from .context import UVError
from .geometry import connected, expand_islands, islands, triangle_area, intersection_area, bounds


class UVGraph:
    def __init__(self, state, faces, settings):
        self.state, self.faces, self.settings = state, faces, settings
        self.loops = [l for f in sorted(faces, key=lambda f: f.index) for l in f.loops]
        parent = {l: l for l in self.loops}

        def root(l):
            while parent[l] != l:
                parent[l] = parent[parent[l]]
                l = parent[l]
            return l

        def union(a, b):
            parent[root(a)] = root(b)

        for loop in self.loops:
            for other in loop.edge.link_loops:
                if other.face not in faces or other is loop or not connected(loop, other, state.layer):
                    continue
                for a in (loop, loop.link_loop_next):
                    for b in (other, other.link_loop_next):
                        if a.vert == b.vert:
                            union(a, b)
        roots = {}
        self.node = {}
        self.members = defaultdict(list)
        for loop in self.loops:
            index = roots.setdefault(root(loop), len(roots))
            self.node[loop] = index
            self.members[index].append(loop)
        self.points = {i: Vector((ls[0][state.layer].uv.x * settings.width,
                                  ls[0][state.layer].uv.y * settings.height))
                       for i, ls in self.members.items()}
        self.original = {i: p.copy() for i, p in self.points.items()}
        self.pins = {i for i, ls in self.members.items() if any(l[state.layer].pin_uv for l in ls)}
        self.adj = defaultdict(set)
        self.edge_faces = defaultdict(list)
        self.length = {}
        matrix = state.obj.matrix_world
        for face in faces:
            nodes = [self.node[l] for l in face.loops]
            if len(set(nodes)) != len(nodes):
                raise UVError('Collapsed UV topology: a face repeats a UV vertex')
            for loop in face.loops:
                a, b = self.node[loop], self.node[loop.link_loop_next]
                key = tuple(sorted((a, b)))
                self.adj[a].add(b)
                self.adj[b].add(a)
                self.edge_faces[key].append(face)
                self.length[key] = (matrix @ loop.vert.co - matrix @ loop.link_loop_next.vert.co).length
        self.boundary_edges = {key for key, fs in self.edge_faces.items() if len(fs) == 1}
        self.boundary = {i for edge in self.boundary_edges for i in edge}
        self.tris = [tuple(self.node[l] for l in tri) for tri in state.bm.calc_loop_triangles()
                     if tri[0].face in faces]
        if any(len(fs) > 2 for fs in self.edge_faces.values()):
            raise UVError('Non-manifold UV adjacency is not supported by shape tools')

    def boundary_cycle(self):
        adjacency = defaultdict(set)
        for a, b in self.boundary_edges:
            adjacency[a].add(b)
            adjacency[b].add(a)
        if not adjacency or any(len(ns) != 2 for ns in adjacency.values()):
            raise UVError('A single non-branching island boundary is required')
        start = min(adjacency)
        cycle, previous, current = [start], None, start
        while True:
            choices = sorted(adjacency[current] - ({previous} if previous is not None else set()))
            nxt = choices[0]
            if nxt == start:
                break
            if nxt in cycle:
                raise UVError('Invalid boundary cycle')
            cycle.append(nxt)
            previous, current = current, nxt
        if len(cycle) != len(adjacency):
            raise UVError('Islands with holes require cuts before rectifying')
        area = sum(self.points[cycle[i]].x * self.points[cycle[(i + 1) % len(cycle)]].y -
                   self.points[cycle[i]].y * self.points[cycle[(i + 1) % len(cycle)]].x
                   for i in range(len(cycle)))
        if area < 0:
            cycle.reverse()
        return cycle

    def solve(self, fixed):
        if len(fixed) < 2:
            raise UVError('At least two fixed UV nodes are needed for relaxation')
        # Positive inverse-world-length weights; no extra Python dependencies.
        free = sorted(set(self.points) - set(fixed))
        for _ in range(self.settings.iterations):
            updates = {}
            for i in free:
                neighbors = self.adj[i]
                weights = [(j, 1 / max(self.length[tuple(sorted((i, j)))], 1e-8)) for j in neighbors]
                total = sum(w for _, w in weights)
                updates[i] = sum((self.points[j] * w for j, w in weights), Vector((0, 0))) / total
            change = max(((p - self.points[i]).length for i, p in updates.items()), default=0)
            self.points.update(updates)
            if change < 1e-5:
                break

    def preserve_frame(self):
        old_area = sum(abs(triangle_area([self.original[i] for i in t])) for t in self.tris)
        new_area = sum(abs(triangle_area([self.points[i] for i in t])) for t in self.tris)
        if old_area <= 1e-8 or new_area <= 1e-8:
            raise UVError('Cannot preserve a collapsed island frame; unwrap first')
        old_center = sum(self.original.values(), Vector((0, 0))) / len(self.original)
        center = sum(self.points.values(), Vector((0, 0))) / len(self.points)
        scale = sqrt(old_area / new_area)
        self.points = {i: old_center + (p - center) * scale for i, p in self.points.items()}

    def validate(self, quality=True):
        if not self.tris or not all(isfinite(value) for p in self.points.values() for value in p):
            raise UVError('Candidate contains no triangles or non-finite UV coordinates')
        signs = set()
        staged = []
        for tri in self.tris:
            uv = [self.points[i] for i in tri]
            area = triangle_area(uv)
            if abs(area) < 1e-7:
                raise UVError('Shape candidate collapses a triangle')
            signs.add(area > 0)
            staged.append((bounds(uv), uv))
            # Singular-value ratio of the 3D-to-pixel triangle mapping.
            world = [self.state.obj.matrix_world @ self.members[i][0].vert.co for i in tri]
            e, f = world[1] - world[0], world[2] - world[0]
            x = e.length
            if x < 1e-10:
                raise UVError('Zero-length mesh edge')
            fx = e.dot(f) / x
            fy = sqrt(max(0, f.length_squared - fx * fx))
            if fy < 1e-10:
                raise UVError('Zero-area mesh triangle')
            a = (uv[1] - uv[0]) / x
            b = ((uv[2] - uv[0]) - a * fx) / fy
            trace = a.length_squared + b.length_squared
            determinant = (a.x * b.y - a.y * b.x) ** 2
            disc = sqrt(max(0, trace * trace - 4 * determinant))
            lo, hi = (trace - disc) / 2, (trace + disc) / 2
            if quality and (lo <= 1e-16 or sqrt(hi / lo) > self.settings.max_stretch):
                raise UVError('Shape exceeds Max Shape Anisotropy; use relax or add cuts')
        if len(signs) != 1:
            raise UVError('Shape candidate introduces a foldover')
        if len(staged) > 5000:
            raise UVError('Shape validation limited to 5000 triangles per island')
        staged.sort(key=lambda item: item[0][0])
        checks = 0
        for index, (box, tri) in enumerate(staged):
            for j in range(index + 1, len(staged)):
                other_box, other = staged[j]
                if other_box[0] >= box[2] - 1e-5:
                    break
                if other_box[1] >= box[3] - 1e-5 or other_box[3] <= box[1] + 1e-5:
                    continue
                checks += 1
                if checks > 1000000:
                    raise UVError('Shape validation budget exceeded; split the island')
                tolerance = max(1e-3, min(abs(triangle_area(tri)), abs(triangle_area(other))) * 1e-6)
                if intersection_area(tri, other) > tolerance:
                    raise UVError('Shape candidate overlaps itself')
        for i in self.pins:
            if (self.points[i] - self.original[i]).length > 1e-4:
                raise UVError('Shape would move a pinned UV; unpin it first')

    def commit(self):
        self.validate()
        for i, loops in self.members.items():
            p = self.points[i]
            for loop in loops:
                loop[self.state.layer].uv = (p.x / self.settings.width, p.y / self.settings.height)


def quadrify(graph):
    graph.boundary_cycle()
    if any(len(f.loops) != 4 for f in graph.faces):
        raise UVError('Quadrify requires an all-quad island')
    seed = min(graph.faces, key=lambda f: f.index)
    grid = dict(zip((graph.node[l] for l in seed.loops), ((0, 0), (1, 0), (1, 1), (0, 1))))
    todo = set(graph.faces) - {seed}
    while todo:
        progressed = False
        for face in sorted(todo, key=lambda f: f.index):
            nodes = [graph.node[l] for l in face.loops]
            known = next((i for i in range(4) if nodes[i] in grid and nodes[(i + 1) % 4] in grid), None)
            if known is None:
                continue
            a, b, c, d = nodes[known:] + nodes[:known]
            ax, ay = grid[a]
            bx, by = grid[b]
            dx, dy = bx - ax, by - ay
            if abs(dx) + abs(dy) != 1:
                raise UVError('Quad grid has inconsistent cycles or poles')
            proposed = {c: (bx - dy, by + dx), d: (ax - dy, ay + dx)}
            if any(i in grid and grid[i] != coord for i, coord in proposed.items()):
                raise UVError('Quad grid has inconsistent winding or cycles')
            grid.update(proposed)
            todo.remove(face)
            progressed = True
        if not progressed:
            raise UVError('Cannot propagate a regular quad grid through this island')
    if len(set(grid.values())) != len(grid):
        raise UVError('Quad grid folds onto itself; add a cut')
    columns, rows = defaultdict(list), defaultdict(list)
    for (a, b), length in graph.length.items():
        x1, y1 = grid[a]
        x2, y2 = grid[b]
        if y1 == y2:
            columns[min(x1, x2)].append(length)
        elif x1 == x2:
            rows[min(y1, y2)].append(length)
        else:
            raise UVError('Non-grid quad edge')

    def positions(values, coordinates):
        result = {min(coordinates): 0.0}
        for i in range(min(coordinates), max(coordinates)):
            if i not in values:
                raise UVError('Disconnected grid interval')
            result[i + 1] = result[i] + (1 if graph.settings.spacing == 'EVEN' else sum(values[i]) / len(values[i]))
        return result

    xs = positions(columns, [p[0] for p in grid.values()])
    ys = positions(rows, [p[1] for p in grid.values()])
    graph.points = {i: Vector((xs[x], ys[y])) for i, (x, y) in grid.items()}
    graph.preserve_frame()


def rectify(graph, circle=False):
    cycle = graph.boundary_cycle()
    if graph.pins:
        raise UVError('Rectify/circle requires unpinned islands')
    if circle:
        lengths = [graph.length[tuple(sorted((cycle[i], cycle[(i + 1) % len(cycle)])))]
                   if graph.settings.spacing == 'GEOMETRY' else 1 for i in range(len(cycle))]
        total, distance = sum(lengths), 0.0
        if total <= 1e-10:
            raise UVError('Zero-length boundary')
        for i, node in enumerate(cycle):
            angle = distance / total * 2 * pi
            graph.points[node] = Vector((cos(angle), sin(angle)))
            distance += lengths[i]
    else:
        # Use four explicitly selected boundary corners where unambiguous; else
        # choose strong, well-separated boundary turns (not bbox-coordinate keys).
        state = graph.state
        use_uv = state.use_uv
        chosen = [i for i, node in enumerate(cycle) if any(
            (l.uv_select_vert if use_uv else l.vert.select) for l in graph.members[node])]
        if len(chosen) != 4:
            turns = []
            for i, node in enumerate(cycle):
                a = graph.original[cycle[i - 1]] - graph.original[node]
                b = graph.original[cycle[(i + 1) % len(cycle)]] - graph.original[node]
                if a.length < 1e-8 or b.length < 1e-8:
                    raise UVError('Collapsed boundary; unwrap first')
                turns.append((pi - a.angle(b), i))
            chosen = []
            separation = max(1, len(cycle) // 8)
            for _, index in sorted(turns, reverse=True):
                if all(min((index - j) % len(cycle), (j - index) % len(cycle)) >= separation for j in chosen):
                    chosen.append(index)
                    if len(chosen) == 4:
                        break
        if len(chosen) != 4:
            raise UVError('Cannot infer four corners; select four boundary UV vertices')
        chosen.sort()
        sides = []
        for i, start in enumerate(chosen):
            end = chosen[(i + 1) % 4]
            segment = [cycle[j % len(cycle)] for j in range(start, end + (len(cycle) if end <= start else 0) + 1)]
            lengths = [graph.length[tuple(sorted((a, b)))] if graph.settings.spacing == 'GEOMETRY' else 1
                       for a, b in zip(segment, segment[1:])]
            sides.append((segment, lengths))
        width = (sum(sides[0][1]) + sum(sides[2][1])) / 2
        height = (sum(sides[1][1]) + sum(sides[3][1])) / 2
        corners = [Vector((0, 0)), Vector((width, 0)), Vector((width, height)), Vector((0, height))]
        for i, (segment, lengths) in enumerate(sides):
            total, distance = sum(lengths), 0.0
            if total <= 1e-10:
                raise UVError('Zero-length rectangle side')
            for j, node in enumerate(segment):
                graph.points[node] = corners[i].lerp(corners[(i + 1) % 4], distance / total)
                if j < len(lengths):
                    distance += lengths[j]
    graph.solve(graph.boundary)
    graph.preserve_frame()


def straighten_chain(graph):
    state = graph.state
    selected = set()
    for loop in graph.loops:
        is_selected = loop.uv_select_edge if state.use_uv else loop.edge.select
        if is_selected:
            selected.add(tuple(sorted((graph.node[loop], graph.node[loop.link_loop_next]))))
    adjacency = defaultdict(set)
    for a, b in selected:
        adjacency[a].add(b)
        adjacency[b].add(a)
    ends = sorted(i for i, ns in adjacency.items() if len(ns) == 1)
    if len(ends) != 2 or any(len(ns) > 2 for ns in adjacency.values()):
        raise UVError('Select one open, non-branching UV edge chain per island')
    order, previous, current = [], None, ends[0]
    while True:
        order.append(current)
        nxt = adjacency[current] - ({previous} if previous is not None else set())
        if not nxt:
            break
        previous, current = current, next(iter(nxt))
        if current in order:
            raise UVError('Closed chains need a cut')
    if len(order) != len(adjacency):
        raise UVError('Select one connected chain per island')
    axis = graph.settings.axis
    delta = graph.points[order[-1]] - graph.points[order[0]]
    horizontal = axis == 'U' or (axis == 'AUTO' and abs(delta.x) >= abs(delta.y))
    lengths = [graph.length[tuple(sorted((a, b)))] if graph.settings.spacing == 'GEOMETRY' else 1
               for a, b in zip(order, order[1:])]
    extent = sum((graph.original[b] - graph.original[a]).length for a, b in zip(order, order[1:]))
    center = (graph.points[order[0]] + graph.points[order[-1]]) / 2
    direction = Vector((1, 0) if horizontal else (0, 1))
    if direction.dot(delta) < 0:
        direction.negate()
    total, distance = sum(lengths), 0.0
    if total <= 1e-10 or extent <= 1e-8:
        raise UVError('Zero-length chain')
    for index, node in enumerate(order):
        graph.points[node] = center + direction * extent * (distance / total - 0.5)
        if index < len(lengths):
            distance += lengths[index]
    # Boundary + existing pins remain fixed while interior follows the chain.
    graph.solve(graph.boundary | graph.pins | set(order))


def orient(graph, quarter_turn=False):
    center = sum(graph.points.values(), Vector((0, 0))) / len(graph.points)
    if quarter_turn:
        angle = pi / 2
    else:
        edges = sorted(graph.length, key=lambda edge: graph.length[edge], reverse=True)
        a, b = edges[0]
        delta = graph.points[b] - graph.points[a]
        angle = -atan2(delta.y, delta.x)
        if graph.settings.axis == 'V':
            angle += pi / 2
    c, s = cos(angle), sin(angle)
    for i, point in graph.points.items():
        p = point - center
        graph.points[i] = center + Vector((c * p.x - s * p.y, s * p.x + c * p.y))


def apply(session, settings, action, automatic=False):
    expand_islands(session)
    accepted, skipped = 0, []
    staged = []
    for state in session.states:
        for group in islands(state):
            try:
                graph = UVGraph(state, group, settings)
                if action in {'QUADRIFY', 'STRAIGHTEN'}:
                    if action == 'STRAIGHTEN' and not all(len(f.loops) == 4 for f in group):
                        rectify(graph)
                    else:
                        quadrify(graph)
                elif action == 'RECTIFY':
                    rectify(graph)
                elif action == 'CIRCLE':
                    rectify(graph, circle=True)
                elif action == 'CHAIN':
                    straighten_chain(graph)
                elif action == 'RELAX':
                    graph.solve(graph.boundary | graph.pins)
                elif action in {'ORIENT', 'ROTATE'}:
                    orient(graph, action == 'ROTATE')
                else:
                    raise UVError(f'Unknown shape action: {action}')
                graph.validate()
                staged.append(graph)
                accepted += 1
            except UVError as error:
                skipped.append(f'{state.obj.name}: {error}')
                if not automatic:
                    raise
    for graph in staged:
        graph.commit()
    for state in session.states:
        state.update()
    return accepted, skipped