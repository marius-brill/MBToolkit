"""Two-process test; requires BLENDER_USER_CONFIG pointing to a disposable directory.

Run --background --factory-startup --python this_file -- write, then run
--background --python this_file -- read, using the same temporary config path.
"""

import importlib
import os
from pathlib import Path
import sys

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
assert 'mbt_npanel_test_config' in os.environ.get('BLENDER_USER_CONFIG', ''), 'Use disposable config only'
mode = sys.argv[sys.argv.index('--') + 1]
if mode == 'write':
    addon_utils.enable(ROOT.name, default_set=True)
else:
    addon_utils.enable(ROOT.name, default_set=False)
manager = importlib.import_module(f'{ROOT.name}.features.n_panel')
prefs = manager.get_prefs()
assert prefs is not None
if mode == 'write':
    prefs.n_panel_enabled = True
    manager.apply(prefs)
    prefs.n_panel_tabs['MBToolkit'].visible = False
    index = next(i for i, item in enumerate(prefs.n_panel_tabs) if item.name == 'MBToolkit')
    prefs.n_panel_tabs.move(index, 1)
    bpy.ops.wm.save_userpref()
    print('PASS saved sidebar settings to disposable preferences')
else:
    assert prefs.n_panel_enabled
    assert not prefs.n_panel_tabs['MBToolkit'].visible
    assert prefs.n_panel_tabs[1].name == 'MBToolkit'
    manager._tick()
    assert not bpy.types.MBT_PT_main.poll(bpy.context)
    print('PASS sidebar visibility and ordering loaded and reapplied in a new Blender process')
addon_utils.disable(ROOT.name, default_set=False)