# Substance Painter — Blender-controlled workflow

## Primary workflow: one Bake button

Choose low/high collections and an output folder, then press **Bake**. The button
validates inputs and material replacement policy, resolves bake pairs, exports fresh
evaluated meshes, connects/launches Painter, creates or opens the associated project,
reloads existing project geometry preserving strokes, bakes, saves, exports textures,
and imports Blender materials. An unrelated open project is never closed/replaced.
The job JSON is internal and is no longer shown in the panel.

The collection **+** buttons now MOVE selected meshes: link the destination first,
then remove other collection memberships. Linked inputs, nested low/high collections,
and objects shared across scenes are rejected. Parenting/transforms are unchanged.

Matching is **By Mesh Name**. Existing `_low`/`_high` base names take priority;
otherwise evaluated world-space bounding boxes and sampled surface distances suggest
confident matches. Ambiguous, distant, and unmatched inputs block Bake. Select a high
mesh and set **Bake Target** to explicitly choose its low mesh. Resolved targets are
stored as object pointers. Only temporary export names change (`MBTBake_*_low/high`).
One high mesh can target one low mesh; several highs can target the same low mesh.
Pairing across several low meshes is not automatic. One texture set per low remains.

Optional `.spt` project templates come from Painter preferences or the scene override,
and apply only on creation. Resolution/normal settings override the template.
Existing-project normal-format or low-membership changes require **Advanced > New
Project Next Bake**. That action preserves files and does not close Painter.
Source object IDs preserve import targets and texture-set/export names across renames.
Save the blend file to persist the project association. Missing internal data is an
error rather than a reason to guess which Painter project to modify.

Texture export defaults to the inline **MBToolkit Blender PBR** definition; no preset
installation is necessary. Advanced **Custom Export Mapping** accepts a JSON file:

```json
{
  "preset": "resource://starter_assets/PBR%20MetalRough",
  "channels": {
    "base_color": "{texture_set}_BaseColor.png",
    "roughness": "{texture_set}_Roughness.png",
    "metallic": "{texture_set}_Metallic.png",
    "normal": "{texture_set}_Normal.png"
  }
}
```

Use the actual installed preset resource URL and its exact output filenames. Required
channels are base_color, roughness, metallic, normal; ao is optional. Only unpacked
PNG maps are supported. Configure the preset's normal convention to match Blender's
setting. Existence/output compatibility is confirmed by Painter during export;
the add-on validates mapping structure before baking. Packed-channel import is not
implemented. **Update Textures (No Bake)** handles painting-only updates.

`tests/test_painter_workflow.py` covers moves, grouping, ambiguity, refreshed snapshots,
project reuse, template/mapping preflight and controlled asynchronous reload handling.
It runs with the same disposable background Blender invocation as the other tests.

### Legacy action/API reference

The older operators below remain available to scripts, but are not the main panel flow.

Open **3D View > Sidebar > MBToolkit > Bake**.

1. Choose low/high collections, or select meshes and use the **+** beside each field.
   Assignment moves objects out of their previous collections.
   Child collections are included. Low/high inputs must not overlap.
2. Use Object Mode. Inputs must be local, visible meshes in the current view layer.
   Low-poly meshes need non-collapsed UVs in the single 0–1 tile.
3. Set a project name, output folder, resolution, requested bake maps, and normal format.
   A relative output folder requires a saved blend file.
4. **Validate** checks the setup. **Prepare Bake Job** makes a unique job folder
   containing `low.fbx`, `high.fbx`, `job.json`, and `textures/`.
5. Alternatively use **Send to Painter** to prepare a new job, connect/launch Painter,
   create a project from the low FBX, verify texture-set names, and save its `.spp`.
   Painter must have no project open. Sending alone does not bake.
   Use **Bake New Project** instead for prepare → create → bake → save → export → import,
   or **Bake Current Job** to bake the matching open project using its saved snapshots.
6. Click **Import Maps / Update Material**. Enable **Replace Existing Materials**
   only if you want all existing slots replaced. Otherwise existing artist materials
   are protected. Integration-owned material graphs are rebuilt on reimport, so do
   not put custom edits inside them. Unrelated materials are not deleted.

## Current contract

- The local **MBT PBR — Unpacked PNG** layout is a filename contract, **not** a
  bundled or automatically installed Painter export preset.
- Each low object exports with one temporary material/texture set. Its actual
  exported material name and expected filenames are recorded in the manifest.
  Original per-face material splits are intentionally flattened in the export copy.
  High-poly material assignments and mesh color attributes remain in the snapshots
   for ID-baker configuration.
- Texture filenames are `<texture_set>_BaseColor.png`, `_Roughness.png`,
  `_Metallic.png`, `_Normal.png`, and `_AO.png`.
- At least one shader map must exist for every target before import proceeds.
  Missing maps are reported; AO alone cannot produce a shader import.
- Base Color uses sRGB. Scalar maps and normals use Non-Color. Normals connect
  through a tangent-space Normal Map node; DirectX green is inverted if requested.
  AO is loaded as an unconnected inspection node, not multiplied into Base Color.
- An explicit UV Map node uses the UV layer captured when preparing the job.
- Meshes export as evaluated, triangulated snapshots using viewport modifiers and
  world transforms. Source objects, selection, visibility, modifiers and materials
  are not changed during preparation. Geometry Nodes instances must be realized.
- Import targets the original object names in the current scene. Renaming objects
  or UV layers after preparation requires preparing another job.
- One active setup per scene; settings persist in the blend file. Earlier manifests
  can be chosen in the Job Manifest field. Every preparation gets a new directory;
  delete old job folders yourself when no longer needed.
- JSON schema version 1 records requested bake maps separately from returned PBR
   textures. Legacy preparation uses `match_method: ALWAYS`; the unified Bake action
   uses `BY_NAME`. Custom cages are not implemented.

## Automated baking

- Select Normal, AO, Curvature, Position, Thickness, World Space Normal and/or ID.
  Only selected bakers are enabled; Curvature uses the high mesh (From Mesh).
- Front/Rear Distance control projection. Relative distances are bounding-box
  fractions; absolute distances use Painter scene units (centimeters).
- Antialiasing offers None, 2×2 (Supersampling 4x) and 4×4 (Supersampling 16x).
  ID supports Material Color or Vertex Color from the high-poly snapshot.
- Projection is distance-based, with all high geometry used for each low texture
  set. Use separate jobs where unrelated high meshes would interfere.
- **Bake Current Job** updates bake settings in the selected manifest but does
  not re-export geometry. Prepare a new job after mesh changes.
- Progress uses Painter's asynchronous bake events. Only a confirmed successful
  bake followed by a successful save proceeds to export and main-thread import.
- **Cancel Bake** requests cooperative cancellation. It cannot interrupt an
  in-flight save/export HTTP request; cancellation during export skips material
  import but retains successfully recorded texture paths. Cancellation during
  project creation waits for that request and prevents subsequent baking.
- The bake/save polling window is 30 minutes. Timeout or lost communication is
  an uncertain result, not proof that Painter stopped. No automatic retry or
  export/import follows; inspect Painter before retrying.

Not implemented: installed Painter preset discovery, custom presets, packed
channels, UDIMs, custom cages and mesh-name matching. **Prepare is not Bake.**

## Export from Painter / Import

After manually baking/painting, keep the saved job project open in Painter and
select its matching `job.json` in Blender. Click **Export from Painter / Import**.
The action connects only (it does not launch Painter), verifies the open `.spp`
path and texture sets, and exports our inline unpacked PBR PNG layout. No separate
Painter plugin or project repository is required: the worker runs inside Painter,
while Blender orchestrates the request and imports materials on its main thread.

Each export uses a fresh `textures/export_*` directory. Painter's returned paths
are checked for required channels and existing files before atomically updating
the manifest. The material importer then uses those paths. Existing-material
protection still applies; if import is blocked, enable replacement only if intended
and use **Import Maps / Update Material** without exporting again. Old exports are
retained and can be deleted manually.

Exports include Base Color, Roughness, Metallic, mixed tangent-space Normal in the
job's convention, and mixed AO when available. Baking is NOT triggered. This is
the fixed MBT layout, not arbitrary installed/custom export presets. Painter export
warnings may indicate missing unbaked sources; inspect the exported maps.

Manual import still uses exact manifest paths, but missing-map errors now list the
active job, expected filenames, searched folders and files found (up to 30 names).
Simply putting differently named PNGs in the same directory does not map channels.
Automatic filename guessing/channel remapping is not implemented.

Export configuration/identity checks and manifest recording have automated tests.
Live bake, save, export and Blender material import have passed on a disposable
512-pixel cube job with Painter 11.0.3 and Blender 5.2. This verifies the basic
round trip, not production assets or every map/ID/antialiasing combination.

## Painter connection

In **MBToolkit Preferences > Painter**, use **Detect** or choose the executable.
The default local port is 60041. **Test Connection** never launches Painter;
**Launch / Connect** and **Send to Painter** can launch it with
`--enable-remote-scripting`. Custom ports are connect-only.

The client tries IPv4 `127.0.0.1` and IPv6 `::1` loopback using Adobe's `/run.json`
protocol. Painter 11.0.3 on this machine listens on IPv6 loopback only.
Launch removes the inherited `OCIO` environment override for the Painter child
process only; Blender and the system environment are not modified.
Remote scripting executes code: keep the port firewalled and use a trusted machine.
The add-on does not control which interfaces Painter's own server binds to.
It never closes/replaces an open Painter project. Project creation refuses to
overwrite an existing `.spp`; a successful bake intentionally saves the matching
open job in place.
If Painter is already running without remote scripting, save/close it yourself
and relaunch using the button. Complete any startup/license dialogs manually.

Network requests run off Blender's UI thread. Export preparation remains synchronous.
Startup and project creation have bounded waits. A timeout does not terminate Painter
or retry project creation; inspect Painter before trying again. Disabling the add-on
requests cooperative cancellation of a running bake but cannot undo requests
already sent to Painter. Failed sends keep their prepared job folder for inspection.
Connection/bake results appear in Last Result; successful exports update exact
texture paths in the manifest.

Local installation detected during development: Painter 11.0.3. Live connection
and low-FBX project creation now work after adding IPv6 loopback support. The live
test exposed premature saving before edition state; saving now waits until both
edition state and not-busy are true. An initial test cube project was left open;
the corrected create/save cycle has also passed its live test.
The reported Python API version is not the Painter application version.

Progress displays the actual stage and elapsed seconds while connecting, validating
remote Python/API availability, creating, and waiting to save. Connection failures
and script failures are reported separately; completion/failure releases busy state.

## Tests

See `tests/README.md` for the test inventory and safe execution examples.

Run `tests/test_substance_painter.py` using Blender 5.2 with
`--background --factory-startup --python-exit-code 1 --python <absolute-test-path>`.
The script is destructive and must not run inside an existing working session.

`tests/test_painter_bridge.py` tests the transport and controlled Painter API behavior.
Appending `-- --live` explicitly opts into launching Painter and creating a cube
project in a retained temporary folder. It skips creation if a project is open,
never closes Painter, and leaves a successfully created test project open.

`tests/test_painter_baking.py` adds controlled configuration, event cleanup, bake failure,
cancellation, timeout, save gating and success-chain tests. `-- --live` opts into
baking a disposable test project, saving, exporting, then verifying Blender
material import. It may reuse an open project only when its parent directory has
the `MBToolkit_Painter_Live_` prefix; do not use that prefix for personal projects.
Run tests in a separate background Blender process, never a working session.