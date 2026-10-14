"""Geometry Nodes setups that get built from code and added as modifiers."""

from . import crease_by_angle, dynabool, sdf_remesh

_modules = (sdf_remesh, crease_by_angle, dynabool)


def register():
    for m in _modules:
        m.register()


def unregister():
    for m in reversed(_modules):
        m.unregister()
