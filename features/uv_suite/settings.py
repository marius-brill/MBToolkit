"""Saved UV workflow settings; no runtime cache is stored in the blend file."""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from ...core.registry import register_classes, unregister_classes


def density_get(self):
    return self.density / (100 if self.density_unit == 'CM' else 1)


def density_set(self, value):
    self.density = value * (100 if self.density_unit == 'CM' else 1)


def preset_changed(self, context):
    if self.preset == 'CUSTOM':
        return
    self.method = 'CONFORMAL' if self.preset == 'HARD' else 'MINIMUM_STRETCH'
    self.auto_shape = self.preset == 'HARD'
    self.angle = 66 if self.preset == 'HARD' else 100
    self.seams = 'EXTEND' if self.preset != 'EXISTING' else 'PRESERVE'
    self.unwrap_search = True


class MBT_UVSettings(bpy.types.PropertyGroup):
    preset: EnumProperty(name='Preset', items=(('HARD', 'Hard Surface', 'Angle seams and automatic quad grids'),
        ('ORGANIC', 'Organic', 'Stretch-aware unwrap without forced rectangularization'),
        ('EXISTING', 'Existing Seams', 'Use the existing cuts without rebuilding them'),
        ('CUSTOM', 'Custom', 'Keep custom settings')), default='CUSTOM', update=preset_changed)
    width: IntProperty(name='Width', default=2048, min=32, max=65536)
    height: IntProperty(name='Height', default=2048, min=32, max=65536)
    gap: FloatProperty(name='Island Gap (px)', default=8, min=0, max=1024)
    border: FloatProperty(name='Tile Border (px)', default=8, min=0, max=1024)
    method: EnumProperty(name='Unwrap', items=(
        ('ANGLE_BASED', 'Angle Based', 'General surfaces'),
        ('CONFORMAL', 'Conformal', 'Regular hard-surface topology'),
        ('MINIMUM_STRETCH', 'Minimum Stretch', 'Iterative distortion reduction')))
    seams: EnumProperty(name='Seams', items=(
        ('EXTEND', 'Extend', 'Keep existing seams and derive complete surface-region boundaries'),
        ('PRESERVE', 'Preserve', 'Use existing seams without adding cuts'),
        ('REBUILD', 'Rebuild', 'Replace seams inside the selected region')))
    angle: FloatProperty(name='Seam Angle', default=66, min=1, max=179,
                         description='Crease evidence in degrees; automatic cuts may be removed when redundant')
    rotation: EnumProperty(name='Rotation', items=(
        ('ANY', 'Free', 'Allow arbitrary rotation'),
        ('CARDINAL', '90 Degrees', 'Allow quarter turns'),
        ('NONE', 'None', 'Keep orientation')))
    effort: EnumProperty(name='Packing Effort', items=(
        ('FAST', 'Fast', 'One exact-shape candidate'),
        ('BALANCED', 'Balanced', 'Compare exact and convex candidates'),
        ('THOROUGH', 'Thorough', 'Compare exact, convex and box candidates')),
        default='BALANCED')
    density: FloatProperty(name='Density (px/m)', default=512, min=0.001, max=1000000)
    density_unit: EnumProperty(name='Units', items=(('M', 'px/m', 'Pixels per meter'),
                                                  ('CM', 'px/cm', 'Pixels per centimeter')))
    density_tolerance: FloatProperty(name='Density Tolerance (%)', default=10, min=0, max=100)
    density_display: FloatProperty(name='Density', get=density_get, set=density_set,
                                   min=0.00001, max=1000000, precision=3)
    axis: EnumProperty(name='Direction', items=(('AUTO', 'Auto', 'Infer direction'),
                                               ('U', 'Horizontal', 'Along image X'),
                                               ('V', 'Vertical', 'Along image Y')))
    spacing: EnumProperty(name='Spacing', items=(('GEOMETRY', 'Geometry', 'Use world-space edge lengths'),
                                                ('EVEN', 'Even', 'Uniform grid spacing')))
    iterations: IntProperty(name='Relax Iterations', default=80, min=1, max=1000)
    max_stretch: FloatProperty(name='Max Shape Anisotropy', default=8, min=1.01, max=1000,
                               description='Reject shape candidates with excessive triangle anisotropy')
    auto_shape: BoolProperty(name='Auto Straighten Quad Grids', default=True)
    material_seams: BoolProperty(name='Material Boundaries', default=False)
    region_angle: FloatProperty(name='Region Normal Spread', default=35, min=1, max=75,
                                description='Initial region spread and soft curvature preference; simplification can join curved regions beyond this angle')
    show_auto: BoolProperty(name='Auto UV Settings', default=False)
    show_seam_options: BoolProperty(name='Seam Options', default=False)
    show_shape: BoolProperty(name='Shape Settings', default=False)
    show_layout: BoolProperty(name='Layout Settings', default=False)
    show_diagnostics: BoolProperty(name='Select & Diagnose', default=False)
    show_maps: BoolProperty(name='UV Maps & Checker', default=False)
    details: StringProperty(name='Last Operation Details', default='')
    show_details: BoolProperty(name='Operation Details', default=False)
    unwrap_search: BoolProperty(name='Compare Unwrap Methods', default=True)
    pack_backend: EnumProperty(name='Packer', items=(('NATIVE', 'Native Shape Search', 'Concave native solver'),
                                                    ('RECT', 'Constrained Layout', 'Rectangular fit, locks, stacks and tiles')))
    pack_scale: EnumProperty(name='Scale', items=(('FIT', 'Fit to Tiles', 'Allow common scaling'),
                                                 ('KEEP', 'Preserve Density', 'Do not scale islands')))
    preserve_stacks: BoolProperty(name='Preserve Existing Stacks', default=False)
    tile_start: IntProperty(name='First UDIM', default=1001, min=1001, max=1990)
    tile_count: IntProperty(name='Tile Count', default=1, min=1, max=100)
    map_name: StringProperty(name='UV Map', default='UVMap')
    report: StringProperty(name='Last Result', default='')


classes = (MBT_UVSettings,)


def register():
    register_classes(classes)
    bpy.types.Scene.mbt_uv = PointerProperty(type=MBT_UVSettings)


def unregister():
    del bpy.types.Scene.mbt_uv
    unregister_classes(classes)