#  Copyright (c) 2014 Tom Edwards contact@steamreview.org
#
# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

import bpy, math
from typing import Set
from bpy.props import StringProperty, BoolProperty, EnumProperty, IntProperty, CollectionProperty, FloatProperty, PointerProperty

# Python doesn't reload package sub-modules at the same time as __init__.py!
import importlib, sys

pkg_name = __name__

# Reload all modules that belong to this package (including subpackages like .core, .utils, etc.)
for modname, module in list(sys.modules.items()):
    if modname.startswith(pkg_name + ".") and module:
        importlib.reload(module)

# Clear out any scene update funcs hanging around, e.g. after a script reload
for collection in [bpy.app.handlers.depsgraph_update_post, bpy.app.handlers.load_post]:
    for func in collection[:]:
        if func.__module__.startswith(pkg_name):
            collection.remove(func)

from . import datamodel, import_smd, export_smd, flex, GUI
from .core import armatureutils, boneutils, commonutils, meshutils, objectutils, networkutils
from .ui import developer, common, humanoid_armature_map, objectdata, properties, texture_convert, valvemodel, animation, vertexgroup, armature, mesh, bone
from .utils import *

class ValveSource_Exportable(bpy.types.PropertyGroup):
    ob_type : StringProperty()
    icon : StringProperty()
    obj : PointerProperty(type=bpy.types.Object)
    collection : PointerProperty(type=bpy.types.Collection)

    @property
    def item(self) -> bpy.types.Object | bpy.types.Collection: return self.obj or self.collection

    @property
    def session_uid(self): return self.item.session_uid

def menu_func_import(self, context):
    self.layout.operator(import_smd.SmdImporter.bl_idname, text=get_id("import_menuitem", True))

def menu_func_export(self, context):
    self.layout.menu("SMD_MT_ExportChoice", text=get_id("export_menuitem"))

def menu_func_shapekeys(self,context):
    self.layout.operator(flex.ActiveDependencyShapes.bl_idname, text=get_id("activate_dependency_shapes",True), icon='SHAPEKEY_DATA')

def menu_func_textedit(self,context):
    self.layout.operator(flex.InsertUUID.bl_idname)
    
#
# Property Groups
#
from bpy.types import PropertyGroup

encodings = []
for enc in datamodel.list_support()['binary']: encodings.append( (str(enc), f"Binary {enc}", '' ) )
formats = []
for version in set(x for x in [*dmx_versions_source1.values(), *dmx_versions_source2.values()] if x.format != 0):
    formats.append((version.format_enum, version.format_title, ''))
formats.sort(key = lambda f: f[0])

_relativePathOptions : Set = {'PATH_SUPPORTS_BLEND_RELATIVE'} if bpy.app.version >= (4,5,0) else set()

class ValveSource_PrefabItem(PropertyGroup):
    filepath: StringProperty(name="Filepath", subtype='FILE_PATH', options=_relativePathOptions)

class TextureConversionItem(PropertyGroup):
    name: StringProperty(name="Name", default="TexturesItem")
    enforce_white_b_ch_normal : BoolProperty(name='Force White on Blue Channel')
    
    diffuse_map: StringProperty(name='Color Map')
    
    alpha_map: StringProperty(name='Alpha Map')
    alpha_map_ch: EnumProperty(name='Channel', items=pbr_to_phong_channels)
    invert_alpha_map : BoolProperty(name='Invert Alpha Map', default=False)
    
    skin_map: StringProperty(name='Skin Map')
    skin_map_ch: EnumProperty(name='Channel', items=pbr_to_phong_channels)
    skin_map_gamma: FloatProperty(name='Gamma Correction', soft_min=0, soft_max=10, default=1)
    skin_map_contrast: FloatProperty(name='Contrast', soft_min=-100, soft_max=100, default=0)
    invert_skin_map : BoolProperty(name='Invert Skin Map', default=False)
    
    metal_map: StringProperty(name='Metal Map')
    metal_map_ch: EnumProperty(name='Channel', items=pbr_to_phong_channels)
    invert_metal_map : BoolProperty(name='Invert Metal Map', default=False)
    
    roughness_map: StringProperty(name='Roughness Map')
    roughness_map_ch: EnumProperty(name='Channel', items=pbr_to_phong_channels)
    invert_roughness_map : BoolProperty(name='Invert Roughness Map', default=False)
    
    ambientocclu_map: StringProperty(name='AO Map')
    ambientocclu_strength: IntProperty(name='AO Map Strength', default=80, min=0, max=100)
    ambientocclu_map_ch: EnumProperty(name='Channel', items=pbr_to_phong_channels)
    invert_ambientocclu_map : BoolProperty(name='Invert AO Map', default=False)
    
    emissive_map: StringProperty(name='Emissive Map')
    emissive_map_ch: EnumProperty(name='Channel', items=pbr_to_phong_channels)
    
    normal_map: StringProperty(name='Normal Map')
    normal_map_type: EnumProperty(name='Normal Map Type', items=[
        ('DEF', 'Default', ''),
        ('RED', 'Red', 'The normal map is a red-type normal map'),
        ('YELLOW', 'Yellow', 'The normal map is a yellow-type normal map that simply requires invert to all channel'),
        ('OPENGL', 'OpenGL', 'The normal map is a OpenGL type that requires the green channel to be inverted'),
    ])
    
    color_alpha_mode: EnumProperty(
        name="Color Alpha Channel",
        description="Controls metal map application to the color texture",
        items=[
            ('NONE', "None", "No metal map modification"),
            ('ALPHA', "Alpha Only", "Adds metal map to alpha channel for use with $color2 (Not Recommended)"),
            ('RGB_ALPHA', "RGB", "Bakes metal contrast into RGB and adds metal map to alpha"),
        ],default='RGB_ALPHA')
    
    is_npr : BoolProperty(name='Is NPR')
    
    adjust_for_albedoboost: BoolProperty(name='Adjust for AlbedoBoost', default=False)
    albedoboost_factor: FloatProperty(name='AlbedoBoost Factor', default=1.4, min=0.0, soft_max=2, max=5, precision=4)
    
class ValveSource_SceneProps(PropertyGroup):
    export_path : StringProperty(name=get_id("exportroot"),description=get_id("exportroot_tip"), subtype='DIR_PATH', options=_relativePathOptions)
    qc_compile : BoolProperty(name=get_id("qc_compileall"),description=get_id("qc_compileall_tip"),default=False)
    qc_path : StringProperty(name=get_id("qc_path"),description=get_id("qc_path_tip"),default="//*.qc",subtype="FILE_PATH", options=_relativePathOptions)
    engine_path : StringProperty(name=get_id("engine_path"),description=get_id("engine_path_tip"), subtype='DIR_PATH',update=State.onEnginePathChanged)
    
    dmx_encoding : EnumProperty(name=get_id("dmx_encoding"),description=get_id("dmx_encoding_tip"),items=tuple(encodings),default='2')
    dmx_format : EnumProperty(name=get_id("dmx_format"),description=get_id("dmx_format_tip"),items=tuple(formats),default='1')
    
    export_format : EnumProperty(name=get_id("export_format"),items=[ ('SMD', "SMD", "Studiomdl Data" ), ('DMX', "DMX", "Datamodel Exchange" ) ],default='DMX')
    up_axis : EnumProperty(name=get_id("up_axis"),items=axes,default='Z',description=get_id("up_axis_tip"))
    up_axis_offset : FloatProperty(name=get_id("up_axis_offset"),description=get_id("up_axis_tip"), soft_max=30,soft_min=-30,default=0,precision=2)
    forward_axis : EnumProperty(name=get_id("forward_axis"),items=axes_forward,default='-Y',description=get_id("up_axis_tip"))
    material_path : StringProperty(name=get_id("dmx_mat_path"),description=get_id("dmx_mat_path_tip"))
    export_list_active : IntProperty(name=get_id("active_exportable"),default=-1,get=lambda self: -1,set=lambda self, context: None)
    export_list : CollectionProperty(type=ValveSource_Exportable,options={'SKIP_SAVE','HIDDEN'})
    use_kv2 : BoolProperty(name="Write KeyValues2 (DEBUG)",description="Write ASCII DMX files",default=False)
    game_path : StringProperty(name=get_id("game_path"),description=get_id("game_path_tip"),subtype='DIR_PATH',update=State.onGamePathChanged)
    
    enable_gui_console : BoolProperty(
        name='Enable Console GUI',
        default=True, 
        description='Show console overlay with live progress updates. Adds ~20% processing time for visual feedback'
    )
    
    weightlink_threshold : FloatProperty(name=get_id("weightlinkcull"),description=get_id("weightlinkcull_tip"),max=0.001,min=0.0001, default=0.0001,precision=4)
    vertex_influence_limit : IntProperty(name=get_id("maxvertexinfluence"), description=get_id("maxvertexinfluence_tip"),default=3,max=32, soft_max=8,min=1)

    smd_format : EnumProperty(name=get_id("smd_format"), items=(('SOURCE', "Source", "Source Engine (Half-Life 2)") , ("GOLDSOURCE", "GoldSrc", "GoldSrc engine (Half-Life 1)")), default="SOURCE")

    merge_bone_options_parent: EnumProperty(
        name='Merge to Parent Options',
        description='Options for merging bones to parent',
        items=[
            ('DEFAULT', 'Default', 'Merge bones and remove target bone and weights', 'NONE', 0),
            ('KEEP_BONE', 'Keep Bone', 'Keep target bone but merge weights', 'BONE_DATA', 1),
            ('KEEP_BOTH', 'Keep Both', 'Keep target bone and original weights', 'COPYDOWN', 2),
            ('SNAP_PARENT', 'Snap Parent Tip', 'Re-align parent tip when merging to parent', 'SNAP_ON', 3),
        ],default='DEFAULT')

    merge_bone_options_active: EnumProperty(
        name='Merge to Active Options',
        description='Options for merging bones to active',
        items=[
            ('DEFAULT', 'Default', 'Merge bones and remove target bone and weights', 'NONE', 0),
            ('KEEP_BONE', 'Keep Bone', 'Keep target bone but merge weights', 'BONE_DATA', 1),
            ('KEEP_BOTH', 'Keep Both', 'Keep target bone and original weights', 'COPYDOWN', 2),
            ('CENTRALIZE', 'Centralize', 'Centralize bone position between source and target', 'PIVOT_MEDIAN', 3),
        ],default='DEFAULT')
    
    visible_mesh_only : BoolProperty(name='Visible Meshes Only', default=False)
    defineArmatureCategory : EnumProperty(name='Define Armature Category',items=[('LOAD', 'Load', ''),('WRITE', 'Write', ''),])
    
    smd_prefabs : CollectionProperty(type=ValveSource_PrefabItem)
    smd_prefabs_index : IntProperty(default=-1)
    smd_materials_index : IntProperty(get=lambda self: -1,set=lambda self, context: None,default=-1)
    
    pbr_items : CollectionProperty(type=TextureConversionItem) # deprecated
    texture_conversion_items : CollectionProperty(type=TextureConversionItem)
    texture_conversion_active_index : IntProperty(default=0)
    texture_conversion_export_path: StringProperty(name="Default Export Path", subtype='DIR_PATH', options=_relativePathOptions)
    
    texture_conversion_mode: EnumProperty(
        name="Conversion Mode",
        items=[
            ('PHONG', "to Phong", "Convert PBR to Source Engine Phong (PseudoPBR)"),
            ('PBR', "to SourcePBR", "Convert to simple PBR format (_color, _mrao, _normal)")
        ],default='PHONG')
    
    for entry in toggle_show_ops:
        if isinstance(entry, list):
            for _name in entry:
                exec(f"{_name} : BoolProperty(name='{_name.replace('_', ' ').title()}', options={{'SKIP_SAVE'}})")
        else:
            exec(f"{entry} : BoolProperty(name='{entry.replace('_', ' ').title()}', options={{'SKIP_SAVE'}})")

class ValveSource_VertexAnimation(PropertyGroup):
    name : StringProperty(name="Name",default="VertexAnim")
    start : IntProperty(name="Start",description=get_id("vca_start_tip"),default=0)
    end : IntProperty(name="End",description=get_id("vca_end_tip"),default=250)
    export_sequence : BoolProperty(name=get_id("vca_sequence"),description=get_id("vca_sequence_tip"),default=True)

class FlexControllerItem(PropertyGroup):
    expand_option : BoolProperty(name='Show Options', default=False)
    shapekey : StringProperty(name='ShapeKey')
    raw_delta_name : StringProperty(name='Export Name')

    eyelid : BoolProperty(name='Eyelid')
    stereo : BoolProperty(name='Stereo')

class ExportableProps():
    flex_controller_modes = (
        ('SIMPLE',"Simple",get_id("controllers_simple_tip")),
        ('ADVANCED',"Advanced",get_id("controllers_advanced_tip")),
        ('SPECIFIC',"Specific",get_id("controllers_strict_tip"))
    )

    export : BoolProperty(name=get_id("scene_export"),description=get_id("use_scene_export_tip"),default=True)
    subdir : StringProperty(name=get_id("subdir"),description=get_id("subdir_tip"))
    flex_controller_mode : EnumProperty(name=get_id("controllers_mode"),description=get_id("controllers_mode_tip"),items=flex_controller_modes,default='SPECIFIC')
    flex_controller_source : StringProperty(name=get_id("controller_source"),description=get_id("controllers_source_tip"),subtype='FILE_PATH', options=_relativePathOptions)

    vertex_animations : CollectionProperty(name=get_id("vca_group_props"),type=ValveSource_VertexAnimation)
    active_vertex_animation : IntProperty(default=-1)

    show_items : BoolProperty()
    show_vertexanim_items : BoolProperty()
    
class ValveSource_FloatMapRemap(PropertyGroup):
    group : StringProperty(name="Group name",default="")
    min : FloatProperty(name="Min",description="Maps to 0.0",default=0.0)
    max : FloatProperty(name="Max",description="Maps to 1.0",default=1.0)

class HumanoidArmatureMap(PropertyGroup):
    boneExportName : StringProperty(
        name='Bone',
        description="The original bone name in the source armature. Used when writing JSON for retargeting."
    )

    boneName : StringProperty(
        name='Target Name',
        description="The target name that this bone should be mapped to during retargeting. When loading JSON, any bone matching this name will be treated as the original bone."
    )
    
    writeRotation : EnumProperty(name='Write Rotation', items=[
        ('NONE', 'Do Not Write', ''),
        ('ROTATION', 'Rotation', ''),
        ('ROLL', 'Roll Only', '')
    ], default='ROLL')
    
    writeTwistBone : BoolProperty(name='Write TwistBone', default=False)
    twistBoneTarget : StringProperty(name='TwistBone Target Bone')
    twistBoneCount : IntProperty(name='TwistBone Count', default=1, min=1, soft_max=5)
    writeExportRotationOffset : BoolProperty(name='Write Export Rotation Offset', default=True)
    parentBone : StringProperty(name='Parent Bone', default='', description='Overwrite Parent bone on JSON parse')

class ValveSource_ObjectProps(ExportableProps, PropertyGroup,):
    action_filter : StringProperty(name=get_id("slot_filter") if State.useActionSlots else get_id("action_filter"),description=get_id("slot_filter_tip") if State.useActionSlots else get_id("action_filter_tip"),default="*")
    triangulate : BoolProperty(name=get_id("triangulate"),description=get_id("triangulate_tip"),default=False)
    vertex_map_remaps :  CollectionProperty(name="Vertes map remaps",type=ValveSource_FloatMapRemap)
    
    dme_flexcontrollers : CollectionProperty(name='Flex Controllers', type=FlexControllerItem)
    dme_flexcontrollers_index : IntProperty(default=-1)
    
    dmx_attachment : BoolProperty(name='DMX Attachment',default=False)
    smd_hitbox : BoolProperty(name='SMD Hitbox',default=False)    
    smd_hitbox_group : EnumProperty(name='Hitbox Group',items=hitbox_group,default='0')
    
    humanoid_armature_map_bonecollections : CollectionProperty(name='JSON Bone Collection',type=HumanoidArmatureMap)
    humanoid_armature_map_bonecollections_index : IntProperty()
    
    armature_map_pelvis : StringProperty(name="Pelvis")
    armature_map_chest  : StringProperty(name="Chest")
    armature_map_spine  : StringProperty(name="Spine")
    armature_map_head   : StringProperty(name="Head")
    armature_map_thigh_l : StringProperty(name="Left Thigh")
    armature_map_ankle_l : StringProperty(name="Left Ankle")
    armature_map_toe_l   : StringProperty(name="Left Toe")
    armature_map_thigh_r : StringProperty(name="Right Thigh")
    armature_map_ankle_r : StringProperty(name="Right Ankle")
    armature_map_toe_r   : StringProperty(name="Right Toe")
    armature_map_shoulder_l : StringProperty(name="Left Shoulder")
    armature_map_wrist_l    : StringProperty(name="Left Wrist")
    armature_map_index_f_l  : StringProperty(name="Left Index Finger")
    armature_map_middle_f_l : StringProperty(name="Left Middle Finger")
    armature_map_ring_f_l   : StringProperty(name="Left Ring Finger")
    armature_map_pinky_f_l  : StringProperty(name="Left Pinky Finger")
    armature_map_thumb_f_l  : StringProperty(name="Left Thumb Finger")
    armature_map_shoulder_r : StringProperty(name="Right Shoulder")
    armature_map_wrist_r    : StringProperty(name="Right Wrist")
    armature_map_index_f_r  : StringProperty(name="Right Index Finger")
    armature_map_middle_f_r : StringProperty(name="Right Middle Finger")
    armature_map_ring_f_r   : StringProperty(name="Right Ring Finger")
    armature_map_pinky_f_r  : StringProperty(name="Right Pinky Finger")
    armature_map_thumb_f_r  : StringProperty(name="Right Thumb Finger")
    armature_map_eye_l  : StringProperty(name="Left Eye")
    armature_map_eye_r  : StringProperty(name="Right Eye")
    
    armature_map_upperarm_l: StringProperty(name="Left Upper Arm",)
    armature_map_upperarm_r: StringProperty(name="Right Upper Arm",)
    armature_map_forearm_l: StringProperty(name="Left Fore Arm",)
    armature_map_forearm_r: StringProperty(name="Right Fore Arm",)
    armature_map_knee_l: StringProperty(name="Left Knee",)
    armature_map_knee_r: StringProperty(name="Right Knee",)

class ValveSource_ArmatureProps(PropertyGroup):
    implicit_zero_bone : BoolProperty(name=get_id("dummy_bone"),default=True,description=get_id("dummy_bone_tip"))
    arm_modes = (
        ('CURRENT',get_id("action_slot_current"),get_id("action_slot_selection_current_tip")),
        ('FILTERED',get_id("slot_filter"),get_id("slot_filter_tip")),
        ('FILTERED_ACTIONS',get_id("action_filter"),get_id("action_selection_filter_tip")),
    ) if State.useActionSlots else (
        ('CURRENT',get_id("action_selection_current"),get_id("action_selection_current_tip")),
        ('FILTERED',get_id("action_filter"),get_id("action_selection_filter_tip"))		
    )
    action_selection : EnumProperty(name=get_id("action_selection_mode"), items=arm_modes,description=get_id("action_selection_mode_tip"),default='CURRENT')
    legacy_rotation : BoolProperty(name=get_id("bone_rot_legacy"),description=get_id("bone_rot_legacy_tip"),default=False)

    ignore_bone_exportnames : BoolProperty(name=get_id("ignore_bone_exportnames"))
    bone_direction_naming_left : StringProperty(name='Left Bone Dir', default='L')
    bone_direction_naming_right : StringProperty(name='Right Bone Dir', default='R')
    bone_name_startcount : IntProperty(name='Bone Name Starting Count', default=1, min=0, soft_max=10)

class ValveSource_CollectionProps(ExportableProps,PropertyGroup):
    mute : BoolProperty(name=get_id("group_suppress"),description=get_id("group_suppress_tip"),default=False)
    selected_item : IntProperty(default=-1, max=-1, min=-1)
    automerge : BoolProperty(name=get_id("group_merge_mech"),description=get_id("group_merge_mech_tip"),default=False)

class ShapeTypeProps():
    flex_stereo_sharpness : FloatProperty(name=get_id("shape_stereo_sharpness"),description=get_id("shape_stereo_sharpness_tip"),default=90,min=0,max=100,subtype='PERCENTAGE')
    flex_stereo_mode : EnumProperty(name=get_id("shape_stereo_mode"),description=get_id("shape_stereo_mode_tip"),
                                 items=tuple(list(axes) + [('VGROUP','Vertex Group',get_id("shape_stereo_mode_vgroup"))]), default='X')
    flex_stereo_vg : StringProperty(name=get_id("shape_stereo_vgroup"),description=get_id("shape_stereo_vgroup_tip"))

class CurveTypeProps():
    faces : EnumProperty(name=get_id("curve_poly_side"),description=get_id("curve_poly_side_tip"),default='FORWARD',items=(
    ('FORWARD', get_id("curve_poly_side_fwd"), ''),
    ('BACKWARD', get_id("curve_poly_side_back"), ''),
    ('BOTH', get_id("curve_poly_side_both"), '')) )

class ValveSource_MeshProps(ShapeTypeProps,PropertyGroup):
    bake_shapekey_as_basis_normals : BoolProperty(name=get_id("bake_shapekey_as_basis_normals"),description=get_id("bake_shapekey_as_basis_normals_tip"))
    normalize_shapekeys : BoolProperty(name='Normalize Shapekeys',description='Normalize shapekeys so their current max value is 1 and min of -1 if applicable else 0',default=True)

class ValveSource_SurfaceProps(ShapeTypeProps,CurveTypeProps,PropertyGroup):
    pass
class ValveSource_CurveProps(ShapeTypeProps,CurveTypeProps,PropertyGroup):
    pass
class ValveSource_TextProps(CurveTypeProps,PropertyGroup):
    pass

class JiggleBoneProps():
    bone_is_jigglebone : BoolProperty(name='Bone is JiggleBone', default=False)
    use_bone_length_for_jigglebone_length : BoolProperty(name="Use Bone's Length for JiggleBone Length", default=True)
    
    jiggle_flex_type : EnumProperty(name='Flexible Type', items=[('FLEXIBLE', 'Flexible', ''), ('RIGID', 'Rigid', ''), ('NONE', 'None', '')], default='FLEXIBLE')
    
    jiggle_length : FloatProperty(name='Length', description='Rest length of the jigglebone segment', default=0, min=0, precision=4)
    jiggle_tip_mass : FloatProperty(name='Tip Mass', description='Mass at the end of the jigglebone affecting inertia and movement', precision=2, default=0, min=0, max=1000)
    jiggle_yaw_stiffness : FloatProperty(name='Yaw Stiffness', description='Spring strength resisting yaw rotation', default=100, min=0, soft_max=1000, precision=4)
    jiggle_yaw_damping : FloatProperty(name='Yaw Damping', description='Resistance that slows down yaw motion over time', default=0, min=0, soft_max=20, precision=4)
    jiggle_pitch_stiffness : FloatProperty(name='Pitch Stiffness', description='Spring strength resisting pitch rotation', default=100, min=0, soft_max=1000, precision=4)
    jiggle_pitch_damping : FloatProperty(name='Pitch Damping', description='Resistance that slows down pitch motion over time', default=0, min=0, soft_max=20, precision=4)

    jiggle_allow_length_flex : BoolProperty(name='Allow Length Flex', description='Allow the jigglebone to stretch and compress along its length', default=False)
    jiggle_along_stiffness : FloatProperty(name='Along Stiffness', description='Spring strength along the bone length when flexing is enabled', default=100, min=0, soft_max=1000, precision=4)
    jiggle_along_damping : FloatProperty(name='Along Damping', description='Damping along the bone length when flexing is enabled', default=0, min=0, soft_max=20, precision=4)

    jiggle_base_type : EnumProperty(name='Base Type', items=[('BASESPRING', 'Has Base Spring', ''), ('BOING', 'Is Boing', ''), ('NONE', 'None', '')], default='NONE')

    jiggle_base_stiffness : FloatProperty(name='Base Stiffness', description='Spring stiffness at the base of the jigglebone', default=100, min=0, soft_max=1000, precision=4)
    jiggle_base_damping : FloatProperty(name='Base Damping', description='Damping at the base spring of the jigglebone', default=0, min=0, soft_max=100, precision=4)
    jiggle_base_mass : IntProperty(name='Base Mass', description='Mass applied at the jigglebone base', default=0, min=0)

    jiggle_has_left_constraint : BoolProperty(name='Side Constraint', description='Enable side constraints to limit sideways motion', default=False)
    jiggle_left_constraint_min : FloatProperty(name='Min Side Constraint', description='Minimum sideways offset allowed', unit='LENGTH', default=0.0, min=0, soft_max=15, precision=2)
    jiggle_left_constraint_max : FloatProperty(name='Max Side Constraint', description='Maximum sideways offset allowed', unit='LENGTH', default=0.0, min=0, soft_max=15, precision=2)
    jiggle_left_friction : FloatProperty(name='Side Friction', description='Friction applied when sliding against side constraint', precision=3, default=0.0, min=0, soft_max=20.0)

    jiggle_has_up_constraint : BoolProperty(name='Up Constraint', description='Enable vertical up/down constraint', default=False)
    jiggle_up_constraint_min : FloatProperty(name='Min Up Constraint', description='Minimum upward displacement allowed', unit='LENGTH', default=0.0, min=0, soft_max=15, precision=2)
    jiggle_up_constraint_max : FloatProperty(name='Max Up Constraint', description='Maximum upward displacement allowed', unit='LENGTH', default=0.0, min=0, soft_max=15, precision=2)
    jiggle_up_friction : FloatProperty(name='Up Friction', description='Friction applied when sliding against upward constraint', precision=3, default=0.0, min=0, soft_max=20.0)

    jiggle_has_forward_constraint : BoolProperty(name='Forward Constraint', description='Enable forward/backward constraint', default=False)
    jiggle_forward_constraint_min : FloatProperty(name='Min Forward Constraint', description='Minimum forward displacement allowed', unit='LENGTH', default=0.0, min=0, soft_max=15, precision=2)
    jiggle_forward_constraint_max : FloatProperty(name='Max Forward Constraint', description='Maximum forward displacement allowed', unit='LENGTH', default=0.0, min=0, soft_max=15, precision=2)
    jiggle_forward_friction : FloatProperty(name='Forward Friction', description='Friction applied when sliding against forward constraint', precision=3, default=0.0, min=0, soft_max=20.0)

    jiggle_has_yaw_constraint : BoolProperty(name='Yaw Constraint', description='Enable yaw rotation constraint', default=False)
    jiggle_yaw_constraint_min : FloatProperty(name='Min Yaw Constraint', description='Minimum yaw rotation allowed', unit='ROTATION', default=0.0, min=0, soft_max=360, precision=2)
    jiggle_yaw_constraint_max : FloatProperty(name='Max Yaw Constraint', description='Maximum yaw rotation allowed', unit='ROTATION', default=0.0, min=0, soft_max=360, precision=2)
    jiggle_yaw_friction : FloatProperty(name='Yaw Friction', description='Friction applied during yaw constraint motion', precision=3, default=0.0, min=0, soft_max=20.0)

    jiggle_has_pitch_constraint : BoolProperty(name='Pitch Constraint', description='Enable pitch rotation constraint', default=False)
    jiggle_pitch_constraint_min : FloatProperty(name='Min Pitch Constraint', description='Minimum pitch rotation allowed', unit='ROTATION', default=0.0, min=0, soft_max=360, precision=2)
    jiggle_pitch_constraint_max : FloatProperty(name='Max Pitch Constraint', description='Maximum pitch rotation allowed', unit='ROTATION', default=0.0, min=0, soft_max=360, precision=2)
    jiggle_pitch_friction : FloatProperty(name='Pitch Friction', description='Friction applied during pitch constraint motion', precision=3, default=0.0, min=0, soft_max=20.0)

    jiggle_has_angle_constraint : BoolProperty(name='Angle Constraint', description='Enable overall angular rotation limit', default=False)
    jiggle_angle_constraint : FloatProperty(name='Angular Constraint', description='Maximum total angular displacement allowed', precision=3, unit='ROTATION', default=0.0, min=0, soft_max=360)

    jiggle_impact_speed : IntProperty(name='Impact Speed', min=0, soft_max=1000)
    jiggle_impact_angle : FloatProperty(name='Impact Angle', precision=3, unit='ROTATION', default=0.0, min=0, soft_max=360)
    jiggle_damping_rate : FloatProperty(name='Damping Rate', precision=3, default=0.0, min=0, soft_max=10)
    jiggle_frequency : FloatProperty(name='Frequency', precision=3, default=0.0, min=0, soft_max=1000)
    jiggle_amplitude : FloatProperty(name='Amplitude', precision=3, default=0.0, min=0, soft_max=1000)

class ValveSource_BoneProps(JiggleBoneProps,PropertyGroup):
    export_name : StringProperty(name=get_id("exportname"), maxlen=256)
    
    ignore_rotation_offset : BoolProperty(name='Ignore Rotation Offsets', default=False)
    export_rotation_offset_x : FloatProperty(name='Rotation X', unit='ROTATION', default=math.radians(0), precision=4, min=-360, max=360)
    export_rotation_offset_y : FloatProperty(name='Rotation Y', unit='ROTATION', default=math.radians(0), precision=4, min=-360, max=360)
    export_rotation_offset_z : FloatProperty(name='Rotation Z', unit='ROTATION', default=math.radians(0), precision=4, min=-360, max=360)
    
    ignore_location_offset : BoolProperty(name='Ignore Location Offsets', default=True)
    export_location_offset_x : FloatProperty(name='Location X', default=0, precision=4)
    export_location_offset_y : FloatProperty(name='Location Y', default=0, precision=4)
    export_location_offset_z : FloatProperty(name='Location Z', default=0, precision=4)
    
class ValveSource_MaterialProps(PropertyGroup):
    override_dmx_export_path : StringProperty(name='Material Path', default='')
    do_not_export_faces : BoolProperty(name='Do Not Export Faces (By Material)', default=False)
    do_not_export_faces_vgroup : BoolProperty(name='Do Not Export Faces (By Vertex Groups)', default=False)
    non_exportable_vgroup : StringProperty(name='Vertex Group Filter', default='non_exportable_face')
    do_not_export_faces_vgroup_tolerance : FloatProperty(name='Do Not Export Face Tolerance', default=0.95, min=0.8, max=1, precision=2)

_classes = (
    ValveSource_FloatMapRemap,
    FlexControllerItem,
    HumanoidArmatureMap,
    ValveSource_PrefabItem,
    TextureConversionItem,

    ValveSource_Exportable,
    ValveSource_SceneProps,
    ValveSource_VertexAnimation,
    ValveSource_ObjectProps,
    ValveSource_ArmatureProps,
    ValveSource_CollectionProps,
    ValveSource_MeshProps,
    ValveSource_SurfaceProps,
    ValveSource_CurveProps,
    ValveSource_TextProps,
    ValveSource_BoneProps,
    ValveSource_MaterialProps,
    
    GUI.SMD_MT_ExportChoice,
    GUI.SMD_PT_Scene,
    GUI.SMD_MT_ConfigureScene,
    GUI.SMD_UL_ExportItems,
    GUI.SMD_OT_ShowExportCollection,
    GUI.SMD_OT_ShowVertexAnimation,
    GUI.SMD_UL_GroupItems,
    GUI.SMD_OT_LaunchHLMV,
    GUI.SMD_PT_Object_Config,
    GUI.SMD_PT_Scene_QC_Complie,
    
    GUI.SMD_OT_AddPrefab,
    GUI.SMD_OT_RemovePrefab,
    GUI.SMD_UL_Prefabs,
    
    properties.SMD_PT_ContextObject,
    
    # MESH PANEL
    properties.DME_UL_FlexControllers,
    properties.DME_OT_AddFlexController,
    properties.DME_OT_RemoveFlexController,
    properties.DME_OT_ClearFlexControllers,
    properties.DME_OT_PreviewFlexController,
    properties.SMD_OT_AddVertexMapRemap,
    properties.SMD_UL_VertexAnimationItem,
    properties.SMD_OT_AddVertexAnimation,
    properties.SMD_OT_RemoveVertexAnimation,
    properties.SMD_OT_PreviewVertexAnimation,
    properties.SMD_OT_GenerateVertexAnimationQCSnippet,

    valvemodel.VALVEMODEL_PT_PANEL,
    valvemodel.VALVEMODEL_OT_FixAttachment,
    valvemodel.VALVEMODEL_OT_ExportJiggleBone,
    valvemodel.VALVEMODEL_OT_CreateProportionActions,
    valvemodel.VALVEMODEL_OT_ExportConstraintProportion,
    valvemodel.VALVEMODEL_OT_ExportHitBox,
    valvemodel.VALVEMODEL_OT_FixHitBox,
    valvemodel.VALVEMODEL_OT_AddHitbox,
    valvemodel.VALVEMODEL_OT_CopyJiggleBoneProperties,
    
    common.TOOLS_PT_PANEL,
    
    objectdata.OBJECT_PT_Translate_Panel,
    objectdata.OBJECT_OT_Translate_Object_Process,
    objectdata.OBJECT_OT_Translate_Object,
    objectdata.OBJECT_OT_Apply_Transform,

    armature.TOOLS_PT_Armature,
    armature.TOOLS_OT_ApplyCurrentPoseAsRestPose,
    armature.TOOLS_OT_CleanUnWeightedBones,
    armature.TOOLS_OT_MergeArmatures,
    armature.TOOLS_OT_CopyVisPosture,
    
    bone.TOOLS_PT_Bone,
    bone.TOOLS_OT_MergeBones,
    bone.TOOLS_OT_ReAlignBones,
    bone.TOOLS_OT_CopyTargetRotation,
    bone.TOOLS_OT_SubdivideBone,
    bone.TOOLS_OT_AssignBoneRotExportOffset,
    bone.TOOLS_OT_FlipBone,
    bone.TOOLS_OT_CreateCenterBone,
    bone.TOOLS_OT_SplitActiveWeightLinear,

    mesh.TOOLS_PT_Mesh,
    mesh.TOOLS_OT_CleanShapeKeys,
    mesh.TOOLS_OT_SelectShapekeyVets,
    mesh.TOOLS_OT_RemoveUnusedVertexGroups,
    mesh.TOOLS_OT_AddToonEdgeLine,

    vertexgroup.TOOLS_PT_VertexGroup,
    vertexgroup.TOOLS_OT_WeightMath,
    vertexgroup.TOOLS_OT_SwapVertexGroups,
    vertexgroup.TOOLS_OT_curve_ramp_weights,

    animation.TOOLS_PT_Animation,
    animation.TOOLS_OT_merge_animation_slots,
    animation.TOOLS_OT_merge_two_actions,
    animation.TOOLS_OT_convert_rotation_keyframes,
    animation.TOOLS_OT_delete_action_slot,
    
    humanoid_armature_map.HUMANOIDARMATUREMAP_PT_Panel,
    humanoid_armature_map.HUMANOIDARMATUREMAP_UL_ConfigList,
    humanoid_armature_map.HUMANOIDARMATUREMAP_OT_AddItem,
    humanoid_armature_map.HUMANOIDARMATUREMAP_OT_RemoveItem,
    humanoid_armature_map.HUMANOIDARMATUREMAP_OT_WriteConfig,
    humanoid_armature_map.HUMANOIDARMATUREMAP_OT_LoadConfig,
    humanoid_armature_map.HUMANOIDARMATUREMAP_OT_LoadPreset,
    
    texture_convert.TEXTURECONVERSION_UL_ItemList,
    texture_convert.TEXTURECONVERSION_OT_AddItem,
    texture_convert.TEXTURECONVERSION_OT_RemoveItem,
    texture_convert.TEXTURECONVERSION_OT_ProcessItem,
    texture_convert.TEXTURECONVERSION_OT_ConvertItem,
    texture_convert.TEXTURECONVERSION_OT_ConvertAllItems,
    texture_convert.TEXTURECONVERSION_OT_Convert_Legacy_PBR_Items,
    texture_convert.TEXTURECONVERSION_PT_Panel,
    
    developer.DEVELOPER_PT_PANEL,
    developer.DEVELOPER_OT_ImportLegacyData,
    
    flex.DmxWriteFlexControllers,
    flex.AddCorrectiveShapeDrivers,
    flex.RenameShapesToMatchCorrectiveDrivers,
    flex.ActiveDependencyShapes,
    flex.InsertUUID,
    export_smd.SMD_OT_Compile, 
    export_smd.SmdExporter, 
    import_smd.SmdImporter)

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    
    from . import translations
    bpy.app.translations.register(__name__,translations.translations)
    
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    bpy.types.MESH_MT_shape_key_context_menu.append(menu_func_shapekeys)
    bpy.types.TEXT_MT_edit.append(menu_func_textedit)
        
    try: bpy.ops.wm.addon_disable('EXEC_SCREEN',module="io_smd_tools")
    except: pass
    
    def make_pointer(prop_type):
        return PointerProperty(name=get_id("settings_prop"),type=prop_type)
        
    bpy.types.Scene.vs = make_pointer(ValveSource_SceneProps)
    bpy.types.Object.vs = make_pointer(ValveSource_ObjectProps)
    bpy.types.Armature.vs = make_pointer(ValveSource_ArmatureProps)
    bpy.types.Collection.vs = make_pointer(ValveSource_CollectionProps)
    bpy.types.Mesh.vs = make_pointer(ValveSource_MeshProps)
    bpy.types.SurfaceCurve.vs = make_pointer(ValveSource_SurfaceProps)
    bpy.types.Curve.vs = make_pointer(ValveSource_CurveProps)
    bpy.types.Text.vs = make_pointer(ValveSource_TextProps)
    bpy.types.Bone.vs = make_pointer(ValveSource_BoneProps)
    bpy.types.Material.vs = make_pointer(ValveSource_MaterialProps)

    State.hook_events()

def unregister():
    State.unhook_events()

    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.types.MESH_MT_shape_key_context_menu.remove(menu_func_shapekeys)
    bpy.types.TEXT_MT_edit.remove(menu_func_textedit)

    bpy.app.translations.unregister(__name__)
    
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.vs
    del bpy.types.Object.vs
    del bpy.types.Armature.vs
    del bpy.types.Collection.vs
    del bpy.types.Mesh.vs
    del bpy.types.SurfaceCurve.vs
    del bpy.types.Curve.vs
    del bpy.types.Text.vs
    del bpy.types.Bone.vs
    del bpy.types.Material.vs

if __name__ == "__main__":
    register()