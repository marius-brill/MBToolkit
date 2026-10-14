# MBToolkit

Personal hard surface workflow toolkit for Blender 5.2+.

## Layout

```
mbtoolkit/
  blender_manifest.toml      extension manifest (version, min Blender)
  __init__.py                MODULES list: add new features here
  preferences.py             AddonPreferences (stores pie menu definitions)
  core/                      addon id/prefs access, class registry helper, scene props, shared operators
  features/
    pie_menus/               data (prefs storage), runtime (the pie), ops, keymap, ui (prefs editor)
    script_runner.py
    geonodes/               sdf_remesh, crease_by_angle, dynabool (node groups built from code)
    align.py
    rename.py
    scene_stats.py
  ui/panels.py               N panel
```

Each feature module exposes `classes`, `register()/unregister()` and, if it has N panel UI, a `draw(layout, context)`.

## Adding a feature

1. Create `features/<name>.py` with operators and `register()/unregister()`.
2. Add `"features.<name>"` to `MODULES` in `__init__.py` (before `preferences` if it adds property groups used by prefs).
3. Draw it from a panel in `ui/panels.py`.

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
2. In the 3D Viewport, ensure you're in Object Mode (not Edit Mode)
3. The N panel should appear on the right side of the 3D viewport
4. Look for a tab labeled "MBToolkit" - if it's not there, try restarting Blender

### Common Issues:
- Ensure Blender is running in Object Mode (not Edit Mode)
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
- **Scene Performance**: Monitor triangle count and modifier evaluation times. Can clone from GitHub.
- **Script Runner**: Execute external Python scripts directly from the N panel
- **Pie Menu Editor**: Custom pie menu creator setup. Can clone from GitHub.
- **Clean Up Mesh**: Can clone from GitHub


## Future Features Ideas

- **Focus**: Machin3Tools type focus with hotkey on object or multiple objects. Can clone from GitHub.
- **Resample Mesh**: Like the existing addon. Could be technically complex
- **Automatic Unwrap**: Heavy on math and complex operations could be difficult. Maybe clone from existing from GitHub as base
- **Modifier List**: Change modifier stack to list view with favorites. Can clone from GitHub
- **Smart Face**: Can clone from GitHub
- **Boolean Tools**: General setup. Might clone from HardOps