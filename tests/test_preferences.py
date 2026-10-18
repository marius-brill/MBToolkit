"""Run in disposable --background --factory-startup Blender only."""

import importlib
from pathlib import Path
import sys
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
shared = importlib.import_module(f'{ROOT.name}.core.preferences_ui')
actions = importlib.import_module(f'{ROOT.name}.features.pie_menus.actions')
data = importlib.import_module(f'{ROOT.name}.features.pie_menus.data')
pie_ui = importlib.import_module(f'{ROOT.name}.features.pie_menus.ui')


def run():
    assert bpy.app.background
    addon.register()
    entry = bpy.context.preferences.addons.new()
    entry.module = ROOT.name
    prefs = entry.preferences
    assert 'UV' in prefs.bl_rna.properties['tab'].enum_items
    original_uv = prefs.uv_angle_threshold
    prefs.tab = 'UV'
    assert prefs.uv_angle_threshold == original_uv
    event = SimpleNamespace(type='F', ctrl=True, shift=True, alt=False, oskey=False)
    shared.apply_shortcut(prefs, 'modifier_popup_', event)
    assert prefs.modifier_popup_key == 'F' and prefs.modifier_popup_ctrl
    assert shared.shortcut_text(prefs, 'modifier_popup_') == 'Ctrl + Shift + F'
    assert bpy.ops.mbt.capture_shortcut(target='MODIFIER', clear=True) == {'FINISHED'}
    assert prefs.modifier_popup_key == 'NONE'
    for kind in ('BEVEL', 'SUBSURF', 'MIRROR', 'ARRAY', 'SOLIDIFY'):
        bpy.ops.mbt.modifier_favorite(key='object.modifier_add:'+kind, label=kind, action='TOGGLE')
    original = [f.key for f in prefs.modifier_favorites]
    assert shared.move_favorite(prefs, 0, 4)
    assert prefs.modifier_favorites[4].key == original[0]
    assert not shared.move_favorite(prefs, -1, 2)
    drag = shared.MBT_OT_reorder_favorites
    geometry = SimpleNamespace(_source=0, _origin=(15, 190), _width=100, _height=30)
    assert drag.target(geometry, 15, 190, 5) == 0
    assert drag.target(geometry, 15, 160, 5) == 4
    assert drag.target(geometry, 420, 190, 5) == 0
    assert drag.target(geometry, 15, 220, 5) == 0
    assert drag.target(geometry, 115, 160, 5) == 0  # Empty cell in the last row.
    geometry._source = 4
    assert drag.target(geometry, 315, 220, 5) == 3
    geometry._width, geometry._height = 150, 45
    assert drag.target(geometry, 465, 235, 5) == 3
    print('PASS UV tab / captured shortcut data / clear / favorite ordering / hit testing')

    bpy.ops.mbt.pie_add()
    pie = prefs.pies[prefs.pie_index]
    assert len(pie.slots) == 8
    shared.apply_shortcut(pie, '', event)
    assert pie.key == 'F' and pie.ctrl and pie.shift
    items = actions.action_items('OPERATOR')
    assert any(item[0] == 'object.shade_smooth' for item in items)
    assert any(item[0] == 'mesh.bevel' for item in items)  # Include commands unavailable in Preferences.
    menus = actions.action_items('MENU')
    assert any(item[0] == 'VIEW3D_MT_add' for item in menus)
    actions._search_items['OPERATOR'] = items
    assert bpy.ops.mbt.pie_choose_action(kind='OPERATOR', choice='object.mode_set',
        pie_index=prefs.pie_index, slot_index=0) == {'FINISHED'}
    slot = pie.slots[0]
    assert slot.idname == 'object.mode_set' and slot.label
    slot.args = "mode='EDIT'"
    assert data.parse_args(slot.args) == {'mode': 'EDIT'}
    assert data.parse_args('1') is None and data.parse_args('**{}') is None
    assert data.parse_args("mode=__import__('os')") is None
    # Invoke the options builder against a test window manager, not a modal dialog.
    built = SimpleNamespace(arguments=Builder(), pie_index=-1, slot_index=-1,
                            report=lambda *args: None)
    context = SimpleNamespace(preferences=bpy.context.preferences,
                             window_manager=SimpleNamespace(invoke_props_dialog=lambda *args, **kwargs: {'RUNNING_MODAL'}))
    assert actions.MBT_OT_pie_action_options.invoke(built, context, None) == {'RUNNING_MODAL'}
    mode = next(arg for arg in built.arguments if arg.identifier == 'mode')
    assert mode.enabled and mode.enum == 'EDIT'
    mode.enum = 'OBJECT'
    assert actions.MBT_OT_pie_action_options.execute(built, context) == {'FINISHED'}
    assert data.parse_args(slot.args)['mode'] == 'OBJECT'
    bpy.ops.mbt.pie_duplicate()
    duplicate = prefs.pies[prefs.pie_index]
    assert duplicate.name != pie.name and duplicate.key == 'NONE'
    assert duplicate.slots[0].args == slot.args
    print(f'PASS {len(items)} searchable commands / {len(menus)} menus / options / duplicate / safe argument parsing')

    class Layout:
        def row(self, **kwargs): return self
        def column(self, **kwargs): return self
        def box(self): return self
        def label(self, **kwargs): pass
        def separator(self): pass
        def template_list(self, *args, **kwargs): pass
        def prop(self, obj, name, **kwargs): assert hasattr(obj, name)
        def prop_search(self, obj, name, *args, **kwargs): assert hasattr(obj, name)
        def operator(self, idname, **kwargs):
            category, name = idname.split('.')
            assert getattr(getattr(bpy.ops, category), name).get_rna_type()
            return SimpleNamespace()
    for action in ('NONE', 'OPERATOR', 'MENU', 'PIE', 'PYTHON'):
        duplicate.slots[0].action = action
        duplicate.slots[0].advanced = True
        pie_ui.draw_prefs(Layout(), prefs)
    for tab in ('MODIFIERS', 'PIES', 'PERFORMANCE', 'ABOUT'):
        prefs.tab = tab
        type(prefs).draw(SimpleNamespace(layout=Layout(), tab=tab,
            **{name: getattr(prefs, name) for name in ('uv_angle_threshold', 'stats_timings', 'stats_tri_budget', 'stats_ms_budget',
               'modifier_popup_key', 'modifier_popup_ctrl', 'modifier_popup_shift', 'modifier_popup_alt', 'modifier_popup_oskey',
               'modifier_favorites', 'pies', 'pie_index')}), bpy.context)
    bpy.context.preferences.addons.remove(entry)
    addon.unregister()
    print('ALL PREFERENCES TESTS PASSED')


class Builder(list):
    def add(self):
        item = SimpleNamespace()
        self.append(item)
        return item
    def remove(self, index):
        del self[index]


if __name__ == '__main__':
    run()