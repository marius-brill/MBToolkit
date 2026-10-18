# UV Suite

Available in the MBToolkit 3D Viewport sidebar and the UV Editor sidebar.

## Editor-specific UI

The 3D Viewport contains Auto UV, unwrap using existing seams, seam generation,
selected seam marking/clearing, contour repair, and collapsed Auto UV/seam settings.
Island editing, packing-only controls, density, diagnostics, maps and checker are
shown only in the UV Editor. Advanced sections are collapsed by default.

## Smart seam completion

Smart Seams segments face regions first, then extracts their complete boundaries.
Automatic angle cuts are initial candidates, not permanent constraints. Optional
material boundaries remain hard constraints. Extend keeps existing
seams; Rebuild replaces writable seams; Preserve changes none and validates them.
Complete Regions uses existing seams as constraints without adding angle cuts.
Complete Selected Loop additionally constrains selected edges in Edit Mode; it can
complete other existing contours in the scoped surface too. Mark/Clear Selected
remain explicit manual actions and can intentionally create open chains.

Deterministic constrained agglomeration starts with individual faces, prefers
smooth/long adjacencies and uses protected-contour tangent evidence to avoid merging
across low-angle gaps prematurely. Initial merges check member face normals against
the area-weighted region mean. A second pass re-evaluates whole shared interfaces
and joins redundant regions, updating neighboring candidates after every merge.
Its scale-independent score balances area-weighted normal coherence, a supporting
plane-residual estimate, removed boundary length, crease evidence and a per-region
cost. Long borders around small/narrow regions favor absorbing bevel strips rather
than leaving two parallel cuts. No quad-only bevel detector is required.

Region Normal Spread is now an initial subdivision and soft curvature preference,
not a maximum allowed normal turn for the final chart. Smooth curved strips can
remain together. Enclosing/back-facing region combinations are rejected to avoid
collapsing closed surfaces into a folded chart. Repair does not subdivide for curvature
and does not run the automatic simplification stage.
There is no local endpoint path search, geodesic slit, or face-tree fallback.

Before commit (and after Auto UV), full-mesh face connectivity checks every affected
seam. Interior endpoints and nonseparating bridges/slits are rejected. Actual mesh
boundaries may terminate contours; hidden/excluded faces are not valid exceptions.
Blocked closure, nonmanifold face adjacency, zero-area faces or a segmentation budget
overflow cancel and roll back all objects, seams, UVs and newly created maps.

This is a conservative heuristic, not semantic feature recognition or a globally
optimal fitted-plane solver. Simplification does not invoke trial unwraps; Auto UV
still validates its native unwrap result transactionally. Hard constraints can force small patches; ambiguous
geometry can receive extra valid boundaries. Handles/holes may still fail native
unwrap validation and require artist constraints. Exact screenshot matching needs
the original mesh; topology validation guarantees closure, not artistic intent.

To clean up seams produced by an older run, use **Rebuild**. **Extend** deliberately
protects every existing seam: Blender's seam flags do not distinguish generated
cuts from artist-authored cuts. Operation Details reports removed region interfaces.

## Unwrap results and errors

Compare Unwrap Methods may execute three native operators. Their `bpy.ops.uv.unwrap`
lines can remain in Blender's Info history; operator history is not suppressed.
The suite reports the chosen method once, and retains method-labelled rejection
reasons under Operation Details. If all candidates fail, the warning includes those
reasons and UVs are restored. The Max Shape Anisotropy setting applies to shape
editing only, not native unwrap acceptance. Collapse, non-finite UVs, foldovers,
self-overlap, invalid mesh triangles and pin movement remain rejection reasons.

## Workflows

- **Auto UV**: extend/rebuild complete surface-region seams (or validate preserved seams),
  compare native unwrap methods,
  automatically quadrify valid grids, normalize density, and pack checked candidates.
- **Unwrap**: use existing seams and the selected native method; no packing.
- **Smart Pack**: expand to whole UV islands and compare exact/convex/box
  candidates according to effort. Each starts from the same baseline.
- **Density**: switch between px/m and px/cm, get/set, match the active island, or
  normalize affected islands. Switching units never rescales UVs. World
  transforms and the scene's unit scale are included; modifiers are not evaluated.
- **Inspect**: count UV-connected islands and detect collapsed triangles,
  negative winding, triangle overlaps, out-of-tile UVs and pixel-padding failures.
- **Shape**: smart straighten, open edge-chain straighten, quadrify, rectify,
  harmonic flatten/relax, circle boundary, orient, and rotate 90 degrees. Shape
  tools validate candidates for collapse, winding consistency, self-overlap,
  excessive triangle anisotropy and pin movement before committing.
- **In-place unwrap / Improve Existing**: preserve island centroid and pixel area;
  Improve additionally runs boundary-preserving relaxation without packing.
- **Constrained Layout**: rectangle-based MaxRects search across the configured
  consecutive UDIM range. Supports rectangular images, pinned/excluded island
  obstacles, exact-density mode, and preservation of existing exact stacks.
- **Connectivity**: seams from UV borders, clear seams, weld selected mesh-vertex
  splits, and split a face region from excluded UV neighbors.
- **Transforms**: align selected UV vertices, distribute island centers, match
  pixel dimensions, and proportionally fit the group to the first configured tile.
- **Selection**: whole islands, similar topology counts, overlaps, collapsed faces,
  negative winding, out-of-tile faces and density deviations. These tools intentionally
  commit selection; other operations preserve it. Use mesh Edit Mode.
- **UV Maps**: new, duplicate (including pins), rename and activate across selected
  unique mesh datablocks in Object Mode. Checker creates/shows a color-grid image
  in existing Image Editors without modifying materials.

## Units and resolution

Density is stored canonically as pixels per meter, with a converted display
property for pixels per centimeter: 512 px/m equals 5.12 px/cm. Old saved density
values retain their meaning. Width and Height both disable property splitting and
decoration on the same row so they use matching numeric widgets.

## Packing backends

Native Shape Search compares concave, convex and AABB variants according to effort.
It remains the default for square, unconstrained tile-1001 layouts. Constrained
Layout is selected automatically for non-square images, non-default tile ranges,
fixed density, stack preservation or pinned targets. It uses conservative island
bounding rectangles and 90-degree rotations (even if Free is selected), not an
exact polygon no-fit engine. Search order variants and binary scale search retain
the best found layout; there is no guarantee of a global optimum.

Locked islands use Blender's UV pins and remain at their existing coordinates.
Excluded visible islands become obstacles in Constrained Layout. Existing stacks
are recognized by equal pixel triangle coordinates, not merely bounding boxes.
New stacks are never created automatically. Intentional stacks still appear in
generic overlap diagnostics. Preserve Density never silently shrinks UVs: failure
restores the original layout and asks for more tiles or Fit to Tiles.

Rectify accepts four selected boundary corners when unambiguous, otherwise infers
well-separated boundary turns. Quad grids require consistent all-quad topology.
Holes and irregular grid cycles require additional cuts. Chain Straighten expects
one open, non-branching selected edge chain per island. Geometry spacing uses
world-space mesh-edge lengths; Even spacing uses uniform intervals. Relax holds
the boundary and pins fixed rather than forcing arbitrary islands into rectangles.

Object Mode targets visible faces of selected editable meshes. Edit Mode targets
selected visible faces; in the UV Editor with sync disabled, UV selection further
restricts that target. Empty Edit Mode selections are rejected. Packing and density
expand to whole affected islands and reject islands partly hidden.

UV coordinates, original pin flags, selection, active object and mode are protected
by a transaction. Failure restores UV coordinates, seams and newly created maps.
Mesh topology and other UV maps are not changed. Existing operator IDs remain
registered for pie/shortcut compatibility.

## Remaining scope and limitations

- Pinned islands are obstacles during packing; density changes reject them.
- Native partial packing rejects overlap against excluded visible UVs; choose
  Constrained Layout to use those islands as obstacles. Hidden UVs are not obstacles.
- Specialized cylinder/cap and planar-region classifiers remain future work.
  Optional aggressive dual-face-tree cuts can add many seams and do not guarantee
  optimal or artistically concealed placement.
- Unwrap method search uses per-island validity and edge-scale variation as its
  ranking heuristic. It is not a full area/angle distortion energy optimizer.
- In-place unwrap preserves area and centroid, not exact original orientation,
  bounding shape or internal UV arrangement. Improve does not automatically repack.
- Similar selection matches face counts/polygon-side counts, not full graph isomorphism.
- Weld/stitch merges selected UV coordinates at shared mesh vertices. It is not
  a rigid-island seam-fitting solver. Split offsets selected boundary nodes by
  0.01 pixel to create a measurable UV discontinuity; it is not zero-offset split metadata.
- Match Dimensions intentionally permits non-uniform scaling. Align may intentionally
  collapse selected UVs: use it on edge selections, not a full island.
- Checker is an image preview, not a viewport material override. Stretch/density
  heatmaps, padding overlays, trim/custom-region packing, external packer adapters,
  persistent pack groups, and a cancellable progress UI are not implemented.
- Negative winding is diagnostic, not proof of an erroneous island.
- Exact checking has a bounded pair budget and may reject large layouts. Native
  solver calls are synchronous; there is no progress/cancellation UI yet.
- Shared mesh datablocks are processed once. Density changes reject differently
  scaled selected linked instances; make their mesh data single-user first.
- F9 re-executes using current scene settings; the UI does not expose a
  separate snapshot of workflow properties on each operator.

No upstream source code is copied or dynamically downloaded.

## Validation

Run `tests/test_uv_suite.py` only in a disposable Blender process with
`--background --factory-startup --python-exit-code 1`. It deletes test scene objects.
UI appearance and interactive undo/redo still need a live smoke test.

The focused Blender integration suite covers unit conversion/application, matching
resolution widget flags, shape tools, open chains, preserved-density UDIM packing,
locks, exact stacks, impossible-fit rollback, hidden-island protection, closed-surface
cuts, diagnostic selections, UV map duplication, legacy operators and registration.
It loads the UV modules in isolation, not unrelated MBToolkit startup features.