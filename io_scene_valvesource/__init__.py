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
import importlib, sys, pkgutil

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

ADDONVER = 264
ADDONDEVSTATE = 'ALPHA'

def format_version(ver: int = ADDONVER) -> tuple[str, str]:
    if ver < 10:
        version_str = f"0.{ver}"
    elif ver < 100:
        major = ver // 10
        minor = ver % 10
        version_str = f"{major}.{minor}"
    else:
        major = ver // 100
        minor = (ver % 100) // 10
        patch = ver % 10
        version_str = f"{major}.{minor}.{patch}"
    
    return version_str, ADDONDEVSTATE.lower()

from . import datamodel, import_smd, export_smd, flex, GUI, iconloader
from .core import armatureutils, boneutils, commonutils, meshutils, objectutils, sceneutils, networkutils
from .ui import developer, armature_mapper, common, objectdata, properties, valvemodel, animation, vertexgroup, armature, mesh, bone, pseudopbr
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

class KitsuneTool_PBRMapsToPhongItem(PropertyGroup):
    name: StringProperty(name="Item Name", default="PBR Item")
    
    diffuse_map: StringProperty(name='Color Map')
    
    skin_map: StringProperty(name='Skin Map')
    skin_map_ch: EnumProperty(name='Channel', items=pbr_to_phong_channels)
    skin_map_gamma: FloatProperty(name='Gamma Correction', soft_min=0, soft_max=10, default=1)
    skin_map_contrast: FloatProperty(name='Contrast', soft_min=-100, soft_max=100, default=0)
    
    metal_map: StringProperty(name='Metal Map')
    metal_map_ch: EnumProperty(name='Channel', items=pbr_to_phong_channels)
    
    roughness_map: StringProperty(name='Roughness Map')
    roughness_map_ch: EnumProperty(name='Channel', items=pbr_to_phong_channels)
    
    ambientocclu_map: StringProperty(name='AO Map')
    ambientocclu_strength: IntProperty(name='AO Map Strength', default=80, min=0, max=100)
    ambientocclu_map_ch: EnumProperty(name='Channel', items=pbr_to_phong_channels)
    
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
            ('ALPHA', "Alpha Only", "Adds metal map to alpha channel for use with $color2"),
            ('RGB_ALPHA', "RGB + Alpha", "Bakes metal contrast into RGB and adds metal map to alpha"),
        ],
        default='RGB_ALPHA'
    )

    export_path: StringProperty(name="Export Path", subtype='DIR_PATH', options=_relativePathOptions)

class KitsuneTool_PanelProps():
    visible_mesh_only : BoolProperty(name='Visible Meshes Only', default=False)
    
    merge_bone_options: EnumProperty(
        name='Merge Options',
        description='Options for merging bones',
        items=[
            ('DEFAULT', 'Default', 'Merge bones and remove target bone and weights', 'NONE', 0),
            ('KEEP_BONE', 'Keep Bone', 'Keep target bone but merge weights', 'BONE_DATA', 1),
            ('KEEP_BOTH', 'Keep Both', 'Keep target bone and original weights', 'COPYDOWN', 2),
            ('CENTRALIZE', 'Centralize', 'Centralize bone position between source and target', 'PIVOT_MEDIAN', 3),
            ('SNAP_PARENT', 'Snap Parent Tip', 'Re-align parent tip when merging to parent', 'SNAP_ON', 4),
        ],
        default='DEFAULT'
    )
    
    alignment_exclude_axes: EnumProperty(
            name="Exclude Axes",
            description="Exclude specific axes from modification",
            options={'ENUM_FLAG'},
            items=[
                ('EXCLUDE_X', "X", "Exclude X axis modification"),
                ('EXCLUDE_Y', "Y", "Exclude Y axis modification"),
                ('EXCLUDE_Z', "Z", "Exclude Z axis modification"),
                ('EXCLUDE_ROLL', "Roll", "Exclude roll modification"),
                ('EXCLUDE_SCALE', "Scale", "Exclude scale modification"),
            ],default={'EXCLUDE_SCALE', 'EXCLUDE_ROLL'}
        )
    
    defineArmatureCategory : EnumProperty(name='Define Armature Category', items=[
        ('LOAD', 'Load', ''),
        ('WRITE', 'Write', ''),
    ])
    
    smd_prefabs : CollectionProperty(type=ValveSource_PrefabItem)
    smd_prefabs_index : IntProperty(default=-1)
    smd_materials_index : IntProperty(get=lambda self: -1,set=lambda self, context: None,default=-1)
    
    pbr_items : CollectionProperty(type=KitsuneTool_PBRMapsToPhongItem)
    pbr_active_index : IntProperty(default=0)
    
    for entry in toggle_show_ops:
        if isinstance(entry, list):
            for _name in entry:
                exec(f"{_name} : BoolProperty(name='{_name.replace('_', ' ').title()}', options={{'SKIP_SAVE'}})")
        else:
            exec(f"{entry} : BoolProperty(name='{entry.replace('_', ' ').title()}', options={{'SKIP_SAVE'}})")
            
    propagate_enabled: BoolProperty(
        name="Enable Property Propagation",
        description="When enabled, property changes automatically sync to all selected objects and bones",
        default=True
    )

    propagate_include_active: BoolProperty(
        name="Include Active Object",
        default=True
    )
    
    pbr_to_phong_export_path: StringProperty(name="Default Export Path", subtype='DIR_PATH', options=_relativePathOptions)
        
class ValveSource_SceneProps(KitsuneTool_PanelProps, PropertyGroup):
    export_path : StringProperty(name=get_id("exportroot"),description=get_id("exportroot_tip"), subtype='DIR_PATH', options=_relativePathOptions)
    qc_compile : BoolProperty(name=get_id("qc_compileall"),description=get_id("qc_compileall_tip"),default=False)
    qc_path : StringProperty(name=get_id("qc_path"),description=get_id("qc_path_tip"),default="//*.qc",subtype="FILE_PATH", options=_relativePathOptions)
    engine_path : StringProperty(name=get_id("engine_path"),description=get_id("engine_path_tip"), subtype='DIR_PATH',update=State.onEnginePathChanged)
    
    dmx_encoding : EnumProperty(name=get_id("dmx_encoding"),description=get_id("dmx_encoding_tip"),items=tuple(encodings),default='2')
    dmx_format : EnumProperty(name=get_id("dmx_format"),description=get_id("dmx_format_tip"),items=tuple(formats),default='1')
    
    export_format : EnumProperty(name=get_id("export_format"),items=( ('SMD', "SMD", "Studiomdl Data" ), ('DMX', "DMX", "Datamodel Exchange" ) ),default='DMX')
    up_axis : EnumProperty(name=get_id("up_axis"),items=axes,default='Z',description=get_id("up_axis_tip"))
    up_axis_offset : FloatProperty(name=get_id("up_axis_offset"),description=get_id("up_axis_tip"), soft_max=30,soft_min=-30,default=0,precision=2)
    forward_axis : EnumProperty(name=get_id("forward_axis"),items=axes_forward,default='-Y',description=get_id("up_axis_tip"))
    material_path : StringProperty(name=get_id("dmx_mat_path"),description=get_id("dmx_mat_path_tip"))
    export_list_active : IntProperty(name=get_id("active_exportable"),default=-1,get=lambda self: -1,set=lambda self, context: None)
    export_list : CollectionProperty(type=ValveSource_Exportable,options={'SKIP_SAVE','HIDDEN'})
    use_kv2 : BoolProperty(name="Write KeyValues2 (DEBUG)",description="Write ASCII DMX files",default=False)
    game_path : StringProperty(name=get_id("game_path"),description=get_id("game_path_tip"),subtype='DIR_PATH',update=State.onGamePathChanged)

    weightlink_threshold : FloatProperty(name=get_id("weightlinkcull"),description=get_id("weightlinkcull_tip"),max=0.001,min=0.0001, default=0.0001,precision=4)
    vertex_influence_limit : IntProperty(name=get_id("maxvertexinfluence"), description=get_id("maxvertexinfluence_tip"),default=4,max=32, soft_max=8,min=1)

    smd_format : EnumProperty(name=get_id("smd_format"), items=(('SOURCE', "Source", "Source Engine (Half-Life 2)") , ("GOLDSOURCE", "GoldSrc", "GoldSrc engine (Half-Life 1)")), default="SOURCE")

class ValveSource_VertexAnimation(PropertyGroup):
    name : StringProperty(name="Name",default="VertexAnim")
    start : IntProperty(name="Start",description=get_id("vca_start_tip"),default=0)
    end : IntProperty(name="End",description=get_id("vca_end_tip"),default=250)
    export_sequence : BoolProperty(name=get_id("vca_sequence"),description=get_id("vca_sequence_tip"),default=True)

class StrictShapekeyItem(PropertyGroup):
    expand_option : BoolProperty(name='Show Options', default=False)
    shapekey : StringProperty(name='shapekey')
    eyelid : BoolProperty(name='Eyelid')
    stereo : BoolProperty(name='Stereo')

class ExportableProps():
    flex_controller_modes = (
        ('SIMPLE',"Simple",get_id("controllers_simple_tip")),
        ('ADVANCED',"Advanced",get_id("controllers_advanced_tip")),
        ('STRICT',"Strict",get_id("controllers_strict_tip"))
    )

    export : BoolProperty(name=get_id("scene_export"),description=get_id("use_scene_export_tip"),default=True)
    subdir : StringProperty(name=get_id("subdir"),description=get_id("subdir_tip"))
    flex_controller_mode : EnumProperty(name=get_id("controllers_mode"),description=get_id("controllers_mode_tip"),items=flex_controller_modes,default='STRICT')
    flex_controller_source : StringProperty(name=get_id("controller_source"),description=get_id("controllers_source_tip"),subtype='FILE_PATH', options=_relativePathOptions)

    vertex_animations : CollectionProperty(name=get_id("vca_group_props"),type=ValveSource_VertexAnimation)
    active_vertex_animation : IntProperty(default=-1)
    reset_pose_per_anim : BoolProperty(name='Reset Pose Per Action', description='Reset the pose of the armature for every animation to be exported',default=True)
    
    show_items : BoolProperty()
    show_vertexanim_items : BoolProperty()
    
class ValveSource_FloatMapRemap(PropertyGroup):
    group : StringProperty(name="Group name",default="")
    min : FloatProperty(name="Min",description="Maps to 0.0",default=0.0)
    max : FloatProperty(name="Max",description="Maps to 1.0",default=1.0)

class RotationOffset():
    ignore_rotation_offset : BoolProperty(name='Ignore Rotation Offsets', default=False, update=sceneutils.make_update('ignore_rotation_offset'))
    export_rotation_offset_x : FloatProperty(name='Rotation X', unit='ROTATION', default=math.radians(0), precision=4, min=-360, max=360, update=sceneutils.make_update('export_rotation_offset_x'))
    export_rotation_offset_y : FloatProperty(name='Rotation Y', unit='ROTATION', default=math.radians(0), precision=4, min=-360, max=360, update=sceneutils.make_update('export_rotation_offset_y'))
    export_rotation_offset_z : FloatProperty(name='Rotation Z', unit='ROTATION', default=math.radians(0), precision=4, min=-360, max=360, update=sceneutils.make_update('export_rotation_offset_z'))

class LocationOffset():
    ignore_location_offset : BoolProperty(name='Ignore Location Offsets', default=True, update=sceneutils.make_update('ignore_location_offset'))
    export_location_offset_x : FloatProperty(name='Location X', default=0, precision=4, update=sceneutils.make_update('export_location_offset_x'))
    export_location_offset_y : FloatProperty(name='Location Y', default=0, precision=4, update=sceneutils.make_update('export_location_offset_y'))
    export_location_offset_z : FloatProperty(name='Location Z', default=0, precision=4, update=sceneutils.make_update('export_location_offset_z'))

class ArmatureMapperKeyValue(PropertyGroup):
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
    
class ArmatureMapperProps():
    armature_map_pelvis : bpy.props.StringProperty(name="Pelvis")
    armature_map_chest  : bpy.props.StringProperty(name="Chest")
    armature_map_head   : bpy.props.StringProperty(name="Head")
    armature_map_thigh_l : bpy.props.StringProperty(name="Left Thigh")
    armature_map_ankle_l : bpy.props.StringProperty(name="Left Ankle")
    armature_map_toe_l   : bpy.props.StringProperty(name="Left Toe")
    armature_map_thigh_r : bpy.props.StringProperty(name="Right Thigh")
    armature_map_ankle_r : bpy.props.StringProperty(name="Right Ankle")
    armature_map_toe_r   : bpy.props.StringProperty(name="Right Toe")
    armature_map_shoulder_l : bpy.props.StringProperty(name="Left Shoulder")
    armature_map_wrist_l    : bpy.props.StringProperty(name="Left Wrist")
    armature_map_index_f_l  : bpy.props.StringProperty(name="Left Index Finger")
    armature_map_middle_f_l : bpy.props.StringProperty(name="Left Middle Finger")
    armature_map_ring_f_l   : bpy.props.StringProperty(name="Left Ring Finger")
    armature_map_pinky_f_l  : bpy.props.StringProperty(name="Left Pinky Finger")
    armature_map_thumb_f_l  : bpy.props.StringProperty(name="Left Thumb Finger")
    armature_map_shoulder_r : bpy.props.StringProperty(name="Right Shoulder")
    armature_map_wrist_r    : bpy.props.StringProperty(name="Right Wrist")
    armature_map_index_f_r  : bpy.props.StringProperty(name="Right Index Finger")
    armature_map_middle_f_r : bpy.props.StringProperty(name="Right Middle Finger")
    armature_map_ring_f_r   : bpy.props.StringProperty(name="Right Ring Finger")
    armature_map_pinky_f_r  : bpy.props.StringProperty(name="Right Pinky Finger")
    armature_map_thumb_f_r  : bpy.props.StringProperty(name="Right Thumb Finger")
    armature_map_eye_l  : bpy.props.StringProperty(name="Left Eye")
    armature_map_eye_r  : bpy.props.StringProperty(name="Right Eye")

class ValveSource_ObjectProps(ExportableProps,ArmatureMapperProps, PropertyGroup,):
    action_filter : StringProperty(name=get_id("slot_filter") if State.useActionSlots else get_id("action_filter"),description=get_id("slot_filter_tip") if State.useActionSlots else get_id("action_filter_tip"))
    triangulate : BoolProperty(name=get_id("triangulate"),description=get_id("triangulate_tip"),default=False)
    vertex_map_remaps :  CollectionProperty(name="Vertes map remaps",type=ValveSource_FloatMapRemap)
    
    dme_flexcontrollers : CollectionProperty(name='Flex Controllers', type=StrictShapekeyItem)
    dme_flexcontrollers_index : IntProperty(default=-1,get=lambda self: -1,set=lambda self, context: None)
    
    dmx_attachment : BoolProperty(name='DMX Attachment',default=False, update=sceneutils.make_update('dmx_attachment'))
    smd_hitbox : BoolProperty(name='SMD Hitbox',default=False, update=sceneutils.make_update('smd_hitbox'))    
    smd_hitbox_group : EnumProperty(name='Hitbox Group',items=hitbox_group,default='0', update=sceneutils.make_update('smd_hitbox_group'))
    
    armature_map_bonecollections : CollectionProperty(name='JSON Bone Collection',type=ArmatureMapperKeyValue)
    armature_map_bonecollections_index : IntProperty()

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
class ValveSource_BoneCollectionProps(PropertyGroup):
    pass

class JiggleBoneProps():
    bone_is_jigglebone : BoolProperty(name='Bone is JiggleBone', default=False, update=sceneutils.make_update('bone_is_jigglebone'))
    use_bone_length_for_jigglebone_length : BoolProperty(name="Use Bone's Length for JiggleBone Length", default=True, update=sceneutils.make_update('use_bone_length_for_jigglebone_length'))
    
    jiggle_flex_type : EnumProperty(name='Flexible Type', items=[('FLEXIBLE', 'Flexible', ''), ('RIGID', 'Rigid', ''), ('NONE', 'None', '')], default='FLEXIBLE', update=sceneutils.make_update('jiggle_flex_type'))
    
    jiggle_length : FloatProperty(name='Length', description='Rest length of the jigglebone segment', default=0, min=0, precision=4, update=sceneutils.make_update('jiggle_length'))
    jiggle_tip_mass : FloatProperty(name='Tip Mass', description='Mass at the end of the jigglebone affecting inertia and movement', precision=2, default=0, min=0, max=1000, update=sceneutils.make_update('jiggle_tip_mass'))
    jiggle_yaw_stiffness : FloatProperty(name='Yaw Stiffness', description='Spring strength resisting yaw rotation', default=100, min=0, soft_max=1000, precision=4, update=sceneutils.make_update('jiggle_yaw_stiffness'))
    jiggle_yaw_damping : FloatProperty(name='Yaw Damping', description='Resistance that slows down yaw motion over time', default=0, min=0, soft_max=20, precision=4, update=sceneutils.make_update('jiggle_yaw_damping'))
    jiggle_pitch_stiffness : FloatProperty(name='Pitch Stiffness', description='Spring strength resisting pitch rotation', default=100, min=0, soft_max=1000, precision=4, update=sceneutils.make_update('jiggle_pitch_stiffness'))
    jiggle_pitch_damping : FloatProperty(name='Pitch Damping', description='Resistance that slows down pitch motion over time', default=0, min=0, soft_max=20, precision=4, update=sceneutils.make_update('jiggle_pitch_damping'))

    jiggle_allow_length_flex : BoolProperty(name='Allow Length Flex', description='Allow the jigglebone to stretch and compress along its length', default=False, update=sceneutils.make_update('jiggle_allow_length_flex'))
    jiggle_along_stiffness : FloatProperty(name='Along Stiffness', description='Spring strength along the bone length when flexing is enabled', default=100, min=0, soft_max=1000, precision=4, update=sceneutils.make_update('jiggle_along_stiffness'))
    jiggle_along_damping : FloatProperty(name='Along Damping', description='Damping along the bone length when flexing is enabled', default=0, min=0, soft_max=20, precision=4, update=sceneutils.make_update('jiggle_along_damping'))

    jiggle_base_type : EnumProperty(name='Base Type', items=[('BASESPRING', 'Has Base Spring', ''), ('BOING', 'Is Boing', ''), ('NONE', 'None', '')], default='NONE', update=sceneutils.make_update('jiggle_base_type'))

    jiggle_base_stiffness : FloatProperty(name='Base Stiffness', description='Spring stiffness at the base of the jigglebone', default=100, min=0, soft_max=1000, precision=4, update=sceneutils.make_update('jiggle_base_stiffness'))
    jiggle_base_damping : FloatProperty(name='Base Damping', description='Damping at the base spring of the jigglebone', default=0, min=0, soft_max=100, precision=4, update=sceneutils.make_update('jiggle_base_damping'))
    jiggle_base_mass : IntProperty(name='Base Mass', description='Mass applied at the jigglebone base', default=0, min=0, update=sceneutils.make_update('jiggle_base_mass'))

    jiggle_has_left_constraint : BoolProperty(name='Side Constraint', description='Enable side constraints to limit sideways motion', default=False, update=sceneutils.make_update('jiggle_has_left_constraint'))
    jiggle_left_constraint_min : FloatProperty(name='Min Side Constraint', description='Minimum sideways offset allowed', unit='LENGTH', default=0.0, min=0, soft_max=15, precision=2, update=sceneutils.make_update('jiggle_left_constraint_min'))
    jiggle_left_constraint_max : FloatProperty(name='Max Side Constraint', description='Maximum sideways offset allowed', unit='LENGTH', default=0.0, min=0, soft_max=15, precision=2, update=sceneutils.make_update('jiggle_left_constraint_max'))
    jiggle_left_friction : FloatProperty(name='Side Friction', description='Friction applied when sliding against side constraint', precision=3, default=0.0, min=0, soft_max=20.0, update=sceneutils.make_update('jiggle_left_friction'))

    jiggle_has_up_constraint : BoolProperty(name='Up Constraint', description='Enable vertical up/down constraint', default=False, update=sceneutils.make_update('jiggle_has_up_constraint'))
    jiggle_up_constraint_min : FloatProperty(name='Min Up Constraint', description='Minimum upward displacement allowed', unit='LENGTH', default=0.0, min=0, soft_max=15, precision=2, update=sceneutils.make_update('jiggle_up_constraint_min'))
    jiggle_up_constraint_max : FloatProperty(name='Max Up Constraint', description='Maximum upward displacement allowed', unit='LENGTH', default=0.0, min=0, soft_max=15, precision=2, update=sceneutils.make_update('jiggle_up_constraint_max'))
    jiggle_up_friction : FloatProperty(name='Up Friction', description='Friction applied when sliding against upward constraint', precision=3, default=0.0, min=0, soft_max=20.0, update=sceneutils.make_update('jiggle_up_friction'))

    jiggle_has_forward_constraint : BoolProperty(name='Forward Constraint', description='Enable forward/backward constraint', default=False, update=sceneutils.make_update('jiggle_has_forward_constraint'))
    jiggle_forward_constraint_min : FloatProperty(name='Min Forward Constraint', description='Minimum forward displacement allowed', unit='LENGTH', default=0.0, min=0, soft_max=15, precision=2, update=sceneutils.make_update('jiggle_forward_constraint_min'))
    jiggle_forward_constraint_max : FloatProperty(name='Max Forward Constraint', description='Maximum forward displacement allowed', unit='LENGTH', default=0.0, min=0, soft_max=15, precision=2, update=sceneutils.make_update('jiggle_forward_constraint_max'))
    jiggle_forward_friction : FloatProperty(name='Forward Friction', description='Friction applied when sliding against forward constraint', precision=3, default=0.0, min=0, soft_max=20.0, update=sceneutils.make_update('jiggle_forward_friction'))

    jiggle_has_yaw_constraint : BoolProperty(name='Yaw Constraint', description='Enable yaw rotation constraint', default=False, update=sceneutils.make_update('jiggle_has_yaw_constraint'))
    jiggle_yaw_constraint_min : FloatProperty(name='Min Yaw Constraint', description='Minimum yaw rotation allowed', unit='ROTATION', default=0.0, min=0, soft_max=360, precision=2, update=sceneutils.make_update('jiggle_yaw_constraint_min'))
    jiggle_yaw_constraint_max : FloatProperty(name='Max Yaw Constraint', description='Maximum yaw rotation allowed', unit='ROTATION', default=0.0, min=0, soft_max=360, precision=2, update=sceneutils.make_update('jiggle_yaw_constraint_max'))
    jiggle_yaw_friction : FloatProperty(name='Yaw Friction', description='Friction applied during yaw constraint motion', precision=3, default=0.0, min=0, soft_max=20.0, update=sceneutils.make_update('jiggle_yaw_friction'))

    jiggle_has_pitch_constraint : BoolProperty(name='Pitch Constraint', description='Enable pitch rotation constraint', default=False, update=sceneutils.make_update('jiggle_has_pitch_constraint'))
    jiggle_pitch_constraint_min : FloatProperty(name='Min Pitch Constraint', description='Minimum pitch rotation allowed', unit='ROTATION', default=0.0, min=0, soft_max=360, precision=2, update=sceneutils.make_update('jiggle_pitch_constraint_min'))
    jiggle_pitch_constraint_max : FloatProperty(name='Max Pitch Constraint', description='Maximum pitch rotation allowed', unit='ROTATION', default=0.0, min=0, soft_max=360, precision=2, update=sceneutils.make_update('jiggle_pitch_constraint_max'))
    jiggle_pitch_friction : FloatProperty(name='Pitch Friction', description='Friction applied during pitch constraint motion', precision=3, default=0.0, min=0, soft_max=20.0, update=sceneutils.make_update('jiggle_pitch_friction'))

    jiggle_has_angle_constraint : BoolProperty(name='Angle Constraint', description='Enable overall angular rotation limit', default=False, update=sceneutils.make_update('jiggle_has_angle_constraint'))
    jiggle_angle_constraint : FloatProperty(name='Angular Constraint', description='Maximum total angular displacement allowed', precision=3, unit='ROTATION', default=0.0, min=0, soft_max=360, update=sceneutils.make_update('jiggle_angle_constraint'))

    jiggle_impact_speed : IntProperty(name='Impact Speed', min=0, soft_max=1000, update=sceneutils.make_update('jiggle_impact_speed'))
    jiggle_impact_angle : FloatProperty(name='Impact Angle', precision=3, unit='ROTATION', default=0.0, min=0, soft_max=360, update=sceneutils.make_update('jiggle_impact_angle'))
    jiggle_damping_rate : FloatProperty(name='Damping Rate', precision=3, default=0.0, min=0, soft_max=10, update=sceneutils.make_update('jiggle_damping_rate'))
    jiggle_frequency : FloatProperty(name='Frequency', precision=3, default=0.0, min=0, soft_max=1000, update=sceneutils.make_update('jiggle_frequency'))
    jiggle_amplitude : FloatProperty(name='Amplitude', precision=3, default=0.0, min=0, soft_max=1000, update=sceneutils.make_update('jiggle_amplitude'))
    
class ClothNodeProps():
    bone_is_clothnode : BoolProperty(name='Bone is Cloth Node', default=False, update=sceneutils.make_update('bone_is_clothnode'))
    cloth_goal_strength : FloatProperty(name='Goal Strength', default=0.6,min=0,max=1.0, precision=4, update=sceneutils.make_update('cloth_goal_strength'))
    cloth_goal_damping : FloatProperty(name='Goal Damping', default=0,min=0,max=1.0, precision=4, update=sceneutils.make_update('cloth_goal_damping'))
    cloth_mass : FloatProperty(name='Mass', default=1,min=0.001,soft_max=1000.0, precision=4, update=sceneutils.make_update('cloth_mass'))
    cloth_gravity : FloatProperty(name='Gravity', default=1.0,max=1.0,precision=4, update=sceneutils.make_update('cloth_gravity'))
    cloth_lock_translation : BoolProperty(name='Lock Translation', default=True, update=sceneutils.make_update('cloth_lock_translation'))
    cloth_static : BoolProperty(name='Static', default=False, update=sceneutils.make_update('cloth_static'))
    cloth_allow_rotation : BoolProperty(name='Allow Rotation', default=False, update=sceneutils.make_update('cloth_allow_rotation'))
    cloth_collision_radius : FloatProperty(name='Collision Radius', min=0,soft_max=20,precision=2, update=sceneutils.make_update('cloth_collision_radius'))
    cloth_friction : FloatProperty(name='Friction', min=0,soft_max=20,precision=4, update=sceneutils.make_update('cloth_friction'))
    
    cloth_transform_alignment : EnumProperty(name='Axis Alignment', items=[
        ('AUTO', 'Auto-detect', ''),
        ('XAXIS', 'Align X Along Chain', ''),
        ('TAIL', 'Tail End of Rope', ''),
    ], default='XAXIS', update=sceneutils.make_update('cloth_transform_alignment'))
    
    cloth_stray_radius : FloatProperty(name='Stray Radius', min=0,soft_max=100,default=0, precision=4, update=sceneutils.make_update('cloth_stray_radius'))
    cloth_has_world_collision : BoolProperty(name='Has World Collision', default=False, update=sceneutils.make_update('cloth_has_world_collision'))
    
    cloth_collision_layer: EnumProperty(
        name="Collision Layer",
        items=[
            ('LAYER0', "Collision Layer 0", ""),
            ('LAYER1', "Collision Layer 1", ""),
            ('LAYER2', "Collision Layer 2", ""),
            ('LAYER3', "Collision Layer 3", ""),
        ],
        default={'LAYER0', 'LAYER1', 'LAYER2', 'LAYER3'},
        options={'ENUM_FLAG'}, update=sceneutils.make_update('cloth_collision_layer')
    )
    
    cloth_make_spring : BoolProperty(name='Make Spring Between Parent and Child', default=True, update=sceneutils.make_update('cloth_make_spring'))
    
    cloth_generate_tip : BoolProperty(name='Generate Tip Node', default=False, update=sceneutils.make_update('cloth_generate_tip'))
    cloth_tip_goal_strength : FloatProperty(name='Goal Stength (Tip)', default=0.6,max=1.0,min=0, precision=4, update=sceneutils.make_update('cloth_tip_goal_strength'))
    cloth_tip_mass : FloatProperty(name='Mass (Tip)', default=1,min=0.001,soft_max=1000.0, precision=4, update=sceneutils.make_update('cloth_tip_mass'))
    cloth_tip_gravity : FloatProperty(name='Gravity (Tip)', default=1.0,max=1.0,precision=4, update=sceneutils.make_update('cloth_tip_gravity'))
    
class ValveSource_BoneProps(LocationOffset,RotationOffset,JiggleBoneProps, ClothNodeProps,PropertyGroup):
    export_name : StringProperty(name=get_id("exportname"))
    
class ValveSource_MaterialProps(PropertyGroup):
    override_dmx_export_path : StringProperty(name='Material Path', default='')
    do_not_export_faces : BoolProperty(name='Do Not Export Faces (By Material)', default=False)
    do_not_export_faces_vgroup : BoolProperty(name='Do Not Export Faces (By Vertex Groups)', default=False)
    non_exportable_vgroup : StringProperty(name='Vertex Group Filter', default='non_exportable_face')

_classes = (
    ValveSource_FloatMapRemap,
    StrictShapekeyItem,
    ArmatureMapperKeyValue,
    ValveSource_PrefabItem,
    KitsuneTool_PBRMapsToPhongItem,

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
    ValveSource_BoneCollectionProps,
    
    GUI.SMD_MT_ExportChoice,
    GUI.SMD_PT_Scene,
    GUI.SMD_MT_ConfigureScene,
    GUI.SMD_UL_ExportItems,
    GUI.SMD_OT_ShowExportCollection,
    GUI.SMD_OT_ShowVertexAnimation,
    GUI.SMD_UL_GroupItems,
    GUI.SMD_UL_VertexAnimationItem,
    GUI.SMD_OT_AddVertexAnimation,
    GUI.SMD_OT_RemoveVertexAnimation,
    GUI.SMD_OT_PreviewVertexAnimation,
    GUI.SMD_OT_GenerateVertexAnimationQCSnippet,
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
    properties.SMD_OT_AddVertexMapRemap,
    
    valvemodel.VALVEMODEL_PT_PANEL,
    valvemodel.VALVEMODEL_OT_FixAttachment,
    valvemodel.VALVEMODEL_OT_ExportJiggleBone,
    valvemodel.VALVEMODEL_OT_CreateProportionActions,
    valvemodel.VALVEMODEL_OT_ExportConstraintProportion,
    valvemodel.VALVEMODEL_OT_ExportHitBox,
    valvemodel.VALVEMODEL_OT_FixHitBox,
    valvemodel.VALVEMODEL_OT_AddHitbox,
    
    common.TOOLS_PT_PANEL,
    
    objectdata.OBJECT_PT_translate_panel,
    objectdata.OBJECT_OT_translate_names,
    objectdata.OBJECT_OT_apply_transform,

    armature.TOOLS_PT_Armature,
    armature.TOOLS_OT_ApplyCurrentPoseAsRestPose,
    armature.TOOLS_OT_CleanUnWeightedBones,
    armature.TOOLS_OT_MergeArmatures,
    armature.TOOLS_OT_CopyVisPosture,
    
    bone.TOOLS_PT_Bone,
    bone.TOOLS_OT_MergeBones,
    bone.TOOLS_OT_ReAlignBones,
    bone.TOOLS_OT_CopyTargetRotation,
    bone.TOOLS_OT_SplitBone,
    bone.TOOLS_OT_CreateCenterBone,

    mesh.TOOLS_PT_Mesh,
    mesh.TOOLS_OT_CleanShapeKeys,
    mesh.TOOLS_OT_SelectShapekeyVets,
    mesh.TOOLS_OT_RemoveUnusedVertexGroups,
    mesh.TOOLS_OT_AddToonEdgeLine,

    vertexgroup.TOOLS_PT_VertexGroup,
    vertexgroup.TOOLS_OT_WeightMath,
    vertexgroup.TOOLS_OT_SwapVertexGroups,
    vertexgroup.TOOLS_OT_curve_ramp_weights,
    vertexgroup.TOOLS_OT_SplitActiveWeightLinear,

    animation.TOOLS_PT_Animation,
    animation.TOOLS_OT_merged_animations,
    animation.TOOLS_OT_convert_rotation_keyframes,
    
    armature_mapper.ARMATUREMAPPER_PT_ArmatureMapper,
    armature_mapper.ARMATUREMAPPER_UL_BoneList,
    armature_mapper.ARMATUREMAPPER_OT_AddItem,
    armature_mapper.ARMATUREMAPPER_OT_RemoveItem,
    armature_mapper.ARMATUREMAPPER_OT_WriteJson,
    armature_mapper.ARMATUREMAPPER_OT_LoadJson,
    armature_mapper.ARMATUREMAPPER_OT_LoadPreset,
    
    pseudopbr.PSEUDOPBR_UL_PBRToPhongList,
    pseudopbr.PSEUDOPBR_OT_AddPBRItem,
    pseudopbr.PSEUDOPBR_OT_RemovePBRItem,
    pseudopbr.PSEUDOPBR_OT_ConvertPBRItem,
    pseudopbr.PSEUDOPBR_OT_ConvertAllPBRItems,
    pseudopbr.PSEUDOPBR_PT_PBRtoPhong,
    
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
    iconloader.load_other_icons()
    
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
    bpy.types.BoneCollection.vs = make_pointer(ValveSource_BoneCollectionProps)

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
    del bpy.types.BoneCollection.vs
    
    iconloader.unload_icons()

if __name__ == "__main__":
    register()