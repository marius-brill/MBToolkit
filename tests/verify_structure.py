"""Verify syntax with Python and actual module imports inside Blender."""

import ast
import importlib
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    files = list(root.rglob('*.py'))
    for path in files:
        ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    print(f'PASS syntax: {len(files)} Python files')
    try:
        import bpy
    except ImportError:
        print('Blender unavailable: import/registration tests require Blender Python')
        return
    sys.path.insert(0, str(root.parent))
    addon = importlib.import_module(root.name)
    assert addon._modules[-1].__name__.endswith('.preferences')
    assert any(key == 'resample' and not default
               for key, label, default, paths in addon.feature_manager.FEATURES)
    assert not any(module.__name__.startswith(root.name + '.features.') for module in addon._modules)
    for module in addon._modules:
        assert callable(module.register) and callable(module.unregister), module.__name__
        print(f'PASS module: {module.__name__}')
    print('ALL STRUCTURE CHECKS PASSED')


if __name__ == '__main__':
    main()