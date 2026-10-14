bl_info = {
    "name": "MBToolkit",
    "author": "Your Name",
    "version": (0, 2, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > MBToolkit",
    "description": "Personal hard surface workflow toolkit",
    "category": "3D View",
}

"""
MBToolkit - personal hard surface workflow toolkit.

Every feature lives in its own module and exposes register()/unregister().
To add a feature: create the module, add its dotted name to MODULES below.
Order matters: property groups must register before anything that uses them.
"""

# Direct approach with proper error handling
try:
    # Import all modules directly
    from .core import props, ops
    from .features import script_runner, align, rename, scene_stats, geonodes, uv_tools, clean_up, modifier_list
    from .ui import panels
    
    # Register everything
    _modules = [props, ops, script_runner, align, rename, scene_stats, geonodes, uv_tools, clean_up, modifier_list, panels]
    
    def register():
        """Register all addon modules"""
        for mod in _modules:
            if hasattr(mod, 'register'):
                try:
                    mod.register()
                except Exception as e:
                    print(f"Failed to register {mod.__name__}: {e}")
                    import traceback
                    traceback.print_exc()

    def unregister():
        """Unregister all addon modules"""
        for mod in reversed(_modules):
            if hasattr(mod, 'unregister'):
                try:
                    mod.unregister()
                except Exception as e:
                    print(f"Failed to unregister {mod.__name__}: {e}")
                    import traceback
                    traceback.print_exc()

except ImportError as e:
    print(f"Failed to import addon modules: {e}")
    import traceback
    traceback.print_exc()
except Exception as e:
    print(f"Unexpected error in __init__.py: {e}")
    import traceback
    traceback.print_exc()
