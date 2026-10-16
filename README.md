# MBToolkit

Personal hard surface workflow toolkit for Blender 5.2+.

## Layout

```
mbtoolkit/
  blender_manifest.toml      extension manifest (version, min Blender)
  __init__.py                explicit imports and ordered _modules registration list
  preferences.py             AddonPreferences (stores pie menu definitions)
  core/                      addon id/prefs access, class registry helper, scene props, shared operators
  features/
    pie_menus/               data (prefs storage), runtime (the pie), ops, keymap, ui (prefs editor)
    script_runner.py
    geonodes/               sdf_remesh, crease_by_angle, dynabool (node groups built from code)
    align.py
    rename.py
    resample.py               open wire chains and quad surface strips
    scene_stats.py
  ui/panels.py               N panel
```

Each feature module exposes `classes`, `register()/unregister()` and, if it has N panel UI, a `draw(layout, context)`.

## Adding a feature

1. Create `features/<name>.py` with operators and `register()/unregister()`.
2. Import the feature in the root `__init__.py` and add its module object to `_modules`, before `panels`. Register property groups before their consumers.
3. Expose `draw(layout, context)` and call it from a `_SubPanel` subclass in `ui/panels.py`; add that panel to its `classes` tuple.
4. Use `MBT_OT_*` classes, `mbt.*` operator IDs, and the helpers in `core/registry.py`. Unregistration runs in reverse order.

Registration is explicit, not automatic. Pie-menu property types and UI/operators register before preferences; keymaps register after preferences. Features and sidebar panels register afterwards and unregister in reverse order.

## Installation Instructions

### Method 1: Development with VS Code (Recommended)
1. Install the "Blender Development" extension for VS Code (by Jacques Lucke)
2. Open this folder in VS Code
3. Run the command "Blender: Start" and select this folder
4. This symlinks the add-on into Blender and reloads on save

### Method 2: Manual Installation via Blender Preferences
1. Close Blender completely
2. Navigate to your Blender addons directory:
   - Windows: `C:\Users\<YourUsername>\AppData\Roaming\Blender Foundation\Blender\5.2\scripts\addons`
   - macOS: `/Users/<YourUsername>/Library/Application Support/Blender/5.2/scripts/addons`
   - Linux: `/home/<YourUsername>/.config/blender/5.2/scripts/addons`
3. Copy the entire `mbtoolkit` folder into this directory
4. Start Blender
5. Go to Edit > Preferences > Add-ons
6. Search for "MBToolkit" 
7. Enable the add-on by checking the box next to it

### Method 3: Using Blender's Extension System (Blender 5.2+)
1. Open Blender 5.2+
2. Go to Edit > Preferences > Add-ons > Get Extensions
3. Click on "Repositories" tab
4. Add this folder as a local extension repository
5. Find MBToolkit in the list and install it

## Troubleshooting

### If you don't see the N panel:
1. Make sure the addon is enabled in Edit > Preferences > Add-ons
2. Open the 3D Viewport sidebar with N; Resample requires mesh Edit Mode
3. The N panel should appear on the right side of the 3D viewport
4. Look for a tab labeled "MBToolkit" - if it's not there, try restarting Blender

### Common Issues:
- Check the tool's required mode; Resample runs in mesh Edit Mode
- Check that all required modules are properly imported
- Verify that your Blender version matches the requirements (5.2+)
- Make sure no other add-ons are conflicting with MBToolkit

### If problems persist:
1. Check the System Console (Window > Toggle System Console)
2. Look for error messages when loading the add-on
3. Try reinstalling the add-on
4. Ensure all Python dependencies are properly installed

## Features

- **Align Tools**: Drop objects to ground or move to target location
- **Incremental Rename**: Rename selected objects with a base name and sequential numbering
- **Scene Performance**: Scoped geometry/modifier diagnostics, searchable results, cancellable scans, baseline comparison and export.
- **Script Runner**: Execute external Python scripts directly from the N panel
- **Resample**: Resample open edge chains and one-quad-wide quad strips in its own sidebar section
- **Pie Menu Editor**: Custom pie menu creator setup. Can clone from GitHub.
- **Clean Up Mesh**: Can clone from GitHub


## Modifier List

The **Properties editor > Modifiers (wrench tab)** has a fixed, headerless favorites toolbar and compact modifier list above Blender's native settings. It is not a separate collapsible panel or an N-panel section. Selection follows the context object, including pinned Properties objects. Drawing never initializes or modifies datablocks.

- Rename modifiers and use the small cage, Edit Mode, viewport, and render buttons on the right of each row. The old separate visibility overview box has been removed.
- **Add Modifier** opens a category-column menu overview for editable supported objects in Object Mode. Selecting an entry uses normal menu dismissal rather than leaving an operator-properties popup open. Compatible entries are derived from the installed Blender menu definitions, including explicit built-in node assets. Native category asset catalogs remain accessible within the popup. Missing external assets may still report Blender's own availability error.
- **Preferences > Add-ons > MBToolkit > Modifiers:** select favorites by category and reorder/remove them in the list above. Favorites appear as icon buttons above the stack; incompatible favorites are disabled. Use Blender's Save Preferences if automatic preference saving is disabled. The gear button opens MBToolkit preferences.
- Favorites use labeled, icon-and-name buttons at approximately three times normal row height, arranged in two columns rather than squeezed into a single icon strip.
- The row pin stores the modifier's **distance from the bottom**: last stays last, second-last stays second-last, and so on. Newly added modifiers are placed above a pinned tail. Pins use persistent modifier IDs and survive renaming. Previous exact-index records are converted once using the current modifier positions, outside drawing. Adding through the toolbar immediately restores pins; external changes are corrected on a deferred safe update. Multiple pins preserve unlocked modifiers' relative order. When a stack becomes too short, pins use the nearest available slots while retaining their requested bottom offsets.
- The up/down controls beside the list reorder the selected modifier among unpinned slots and preserve selection. Unpin a modifier before moving it. Each row's X deletes that modifier, including pinned modifiers, and removes stale pin records. Reorder/delete require an editable Object Mode object and support undo; Blender's own modifier restrictions still apply.
- Disable native Pin to Last before using bottom-relative pins. Native ordering restrictions can prevent restoration; conflicts are reported in the UI/console and are not endlessly retried for the same stack state. Updates are deferred during renders. Undo/redo and file-load notifications rebuild enforcement state; actual interactive undo timing requires a UI smoke test.
- Full native modifier settings remain available in the same wrench tab; the list does not replace Blender's built-in modifier panels or change editor pins.
- Linked/read-only objects are inspection-only. Individual read-only controls are disabled; the Add button is unavailable in unsupported contexts.
- The native Modifier Properties draw function is temporarily replaced so there is one Add button and no movable list header. It is restored on disable. Other add-ons that replace the same native draw function may conflict; MBToolkit will not overwrite a later replacement during cleanup.

## Scene Performance

Open **3D Viewport > Sidebar > MBToolkit > Scene Performance** in Object Mode.

- Choose **Visible in View Layer**, **Selected Objects**, or **Active Collection**, then **Scan**. Collection scope optionally includes child collections; selected/collection scopes can include hidden objects but stay within the current view layer. Visible scope respects viewport Local View.
- Scans read evaluated mesh triangles and optionally native last-evaluation modifier timings. They never toggle modifier visibility or alter the stack. A scan is not a forced cold-cache benchmark. Timings are diagnostic, not object/frame/render time; parallel modifier execution can make them unreliable. No frame-time or FPS claim is made from their sum.
- Triangle totals are **per-object evaluated mesh** counts. Shared meshes count for each object; collection instances and Geometry Nodes instances are not expanded, and non-mesh components are not converted into an invented total. Objects with modifiers but unsupported mesh output can still show modifier timings. A dash means disabled, unavailable, or unmeasured; measured zero remains distinct.
- Search, sort, reverse order, and filter by budget, errors, missing timing, or stale results. Triangle/timing budgets and metric help are under **Options and Metric Help**. All rows are accessible in the scrollable list; filtered totals are separate from the captured totals.
- Clicking a row only chooses the inspector. Use **Select**, **Frame**, or the wrench button to navigate explicitly. Hidden/unselectable objects are not unhidden. The wrench uses an existing unpinned Properties editor and never changes editor pins. These actions require Object Mode.
- Interactive scans run in time-bounded main-thread batches. **Cancel** preserves partial results. One expensive dependency-graph evaluation or mesh conversion cannot be interrupted mid-call. Background scans run synchronously for automation. Editing the scene, changing frame/scope, entering Edit Mode, or starting a render stops a running scan at its next safe boundary.
- Snapshots include scene/view-layer/scope/frame/method metadata and use session object identities rather than names. Scene changes conservatively mark data stale. Renaming does not retarget a result to a different object. File loads and undo/redo clear transient snapshots and baselines; results are not saved into the blend file.
- **Set Baseline** requires a complete fresh scan. After changes, scan again to see active-object triangle and modifier-time deltas, plus percentages when the baseline value is nonzero. Comparisons require the same scope, frame, method, and object identities; partial/stale snapshots do not show deltas. Only one current snapshot and one baseline are retained per Blender session.
- **Export** writes the whole captured scope, not just the filtered rows. JSON includes modifier details; CSV includes object summaries and capture metadata. Partial/stale/error states are preserved. Exported data contains no Blender datablock references.

### Scene Performance validation

Run `test_scene_performance.py` in a **disposable background Blender process with `--factory-startup --python-exit-code 1`**. It creates/deletes objects and must never be run in a working scene. Run `test_registration.py` separately for the existing Modifier List/Resample regression suite. Interactive appearance, sidebar widths, Local View, file picking, and actual UI responsiveness still need a viewport smoke test.

## Resample

Open **3D Viewport > Sidebar > MBToolkit > Resample** and enter Edit Mode on one mesh object.

- **Resample Edge Chain:** select an open edge chain. Choose the target vertex count and Linear or Smooth interpolation. Changing count requires isolated wire geometry. Face-connected chains support same-count redistribution only. Endpoints stay fixed.
- **Resample Surface Strip:** select consecutive, non-touching cross edges in Edge Select mode, or a one-quad-wide open band of quad faces in Face Select mode. Cross Edges includes both fixed ends: 4 cross edges produces 3 quads. Roundness 0 samples the original polyline; higher values smooth the profile. When a single face has an ambiguous direction, the shorter transverse edges are preferred.
- Both tools support multiple independent selected components. Settings appear in a dialog and in Adjust Last Operation (F9).
- Closed loops, branching selections, degenerate segments, shape-key meshes, and multi-object Edit Mode are rejected. Connected strip rails are supported: same-count resampling moves existing shared vertices without rebuilding topology. Count changes merge immediate side-face fans into n-gons and resample their shared boundary, keeping the mesh attached and the outer perimeter fixed. This intentionally removes side-face spokes; it does not preserve an all-quad surrounding mesh. Hidden/non-manifold side connections, loose spokes, and merges across marked seams or material boundaries are rejected with a specific message. UVs and other attributes on merged faces follow Blender's dissolve/interpolation rules.
- Operations are staged on a private BMesh. Failure before commit leaves the edit mesh untouched; a serialized backup restores it if commit fails. Existing BMesh-supported custom data is carried through serialization; subdivision/dissolution uses Blender's interpolation rules, not exact preservation of removed UV seams or arbitrary per-face values. New wire elements interpolate vertex data and copy edge data from their source segment.

### Validation

Run the existing `verify_structure.py` using Python for syntax checks or Blender for import checks. Run `test_registration.py` in a **disposable background Blender process with `--factory-startup --python-exit-code 1`**. It creates/deletes test objects and must not be run in a working scene.

The integration tests exercise registration cycles, count changes, selection, interpolation, custom data, invalid inputs, and injected failure recovery. Interactive panel appearance, dialogs, F9, and undo/redo still require a UI smoke test.


## Features

- **Align Tools**: Drop objects to ground or move to target location
- **Incremental Rename**: Rename selected objects with a base name and sequential numbering
- **Scene Performance**: Monitor triangle count and modifier evaluation times. Can clone from GitHub
-> need to be able to select meshes from list
-> look into performance cost of live updating
- **Script Runner**: Execute external Python scripts directly from the N panel
- **Pie Menu Editor**: Custom pie menu creator setup. Can clone from GitHub
- **Clean Up Mesh**: Can clone from GitHub

## Future Features Ideas

- **Focus**: Machin3Tools type focus with hotkey on object or multiple objects. Can clone from GitHub
- **Double Click Select**: Bind ctrl + l (select linked by type) to double click
- **Resample Mesh**: Like the existing addon. Could be technically complex
- **Automatic Unwrap**: Heavy on math and complex operations could be difficult. Maybe clone from existing from GitHub as base
- **Modifier List**: Change modifier stack to list view with favorites. Can clone from GitHub
- **Smart Face**: Can clone from GitHub
- **Boolean Tools**: General setup. Might clone from HardOps
