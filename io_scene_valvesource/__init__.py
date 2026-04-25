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
from bpy.props import StringProperty, BoolProperty, EnumProperty, IntProperty, CollectionProperty, FloatProperty, PointerProperty

# Python doesn't reload package sub-modules at the same time as __init__.py!
import importlib, sys

pkg_name = __name__
# -------------------------------------------------------------------------------------
# Reload all modules that belong to this package
# -------------------------------------------------------------------------------------

for modname, module in list(sys.modules.items()):
    if modname.startswith(pkg_name + ".") and module:
        importlib.reload(module)


# -------------------------------------------------------------------------------------
# Clear out any scene update funcs hanging around, e.g. after a script reload
# -------------------------------------------------------------------------------------

for collection in [bpy.app.handlers.depsgraph_update_post, bpy.app.handlers.load_post]:
    for func in collection[:]:
        if func.__module__.startswith(pkg_name):
            collection.remove(func)

from . import datamodel, import_smd, export_smd, flex, GUI
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

def export_active_changed(self, context):
	if not context.scene.vs.export_list_active < len(context.scene.vs.export_list):
		context.scene.vs.export_list_active = len(context.scene.vs.export_list) - 1
		return

	item = get_active_exportable(context).item
	
	if type(item) == bpy.types.Collection and item.vs.mute: return
	for ob in context.scene.objects: ob.select_set(False)
	
	if type(item) == bpy.types.Collection:
		context.view_layer.objects.active = item.objects[0]
		for ob in item.objects: ob.select_set(True)
	else:
		item.select_set(True)
		context.view_layer.objects.active = item

def on_flexcontroller_index_changed(self, context):
    ob = context.active_object
    if not ob:
        return
    
    mesh : bpy.types.Object = ob if ob.type == 'MESH' else next(
        (child for child in ob.children if child.type == 'MESH'), None
    )
    if not mesh or not mesh.data.shape_keys:
        return

    items = ob.vs.dme_flexcontrollers
    idx = ob.vs.dme_flexcontrollers_index
    if idx < 0 or idx >= len(items):
        return

    shapekey_name = items[idx].shapekey
    if not shapekey_name:
        return

    key_blocks = mesh.data.shape_keys.key_blocks
    sk_idx = key_blocks.find(shapekey_name)
    if sk_idx != -1:
        mesh.active_shape_key_index = sk_idx

def update_sanitize_name(self, context):
    legal_name = re.sub(r'[^a-z0-9]', '_', self.controller_name.lower())
    
    if self.controller_name != legal_name:
        self.controller_name = legal_name

def draw_copy_bone_props(self, context):
    self.layout.operator(GUI.TOOLS_OT_CopySourceBoneProps.bl_idname)


# -------------------------------------------------------------------------------------
# Property Groups
# -------------------------------------------------------------------------------------

from bpy.types import PropertyGroup

encodings = []
for enc in datamodel.list_support()['binary']: encodings.append( (str(enc), f"Binary {enc}", '' ) )
formats = []
for version in set(x for x in [*dmx_versions_source1.values(), *dmx_versions_source2.values()] if x.format != 0):
    formats.append((version.format_enum, version.format_title, ''))
formats.sort(key = lambda f: f[0])


# -------------------------------------------------------------------------------------
# Simple Item Classes
# -------------------------------------------------------------------------------------

class PrefabItem(PropertyGroup):
    filepath: StringProperty(name="Filepath", subtype='FILE_PATH', options={'PATH_SUPPORTS_BLEND_RELATIVE'})

class FlexControllerItem(PropertyGroup):
    controller_name: StringProperty(name='Controller Name',update=update_sanitize_name)
    raw_delta_name : StringProperty(name='Delta Name')

    shapekey : StringProperty(name='ShapeKey')
    eyelid : BoolProperty(name='Eyelid')
    stereo : BoolProperty(name='Stereo')

    flexgroup : EnumProperty(name='Flex Type', items=[
        ('NONE', 'NONE', ''),
        ('EYES', 'EYES', ''),
        ('EYELID', 'EYELID', ''),
        ('BROW', 'BROW', ''),
        ('MOUTH', 'MOUTH', ''),
        ('MISC', 'MISC', ''),
        ('CHEEK', 'CHEEK', ''),
        ], default='NONE')

class VertexAnimation(PropertyGroup):
    name : StringProperty(name="Name",default="VertexAnim")
    start : IntProperty(name="Start",description=get_id("vca_start_tip"),default=0)
    end : IntProperty(name="End",description=get_id("vca_end_tip"),default=250)
    export_sequence : BoolProperty(name=get_id("vca_sequence"),description=get_id("vca_sequence_tip"),default=True)


# -------------------------------------------------------------------------------------
# Base/Utility Classes
# -------------------------------------------------------------------------------------

class ValveSource_FloatMapRemap(PropertyGroup):
    group : StringProperty(name="Group name",default="")
    min : FloatProperty(name="Min",description="Maps to 0.0",default=0.0)
    max : FloatProperty(name="Max",description="Maps to 1.0",default=1.0)


# -------------------------------------------------------------------------------------
# Mixin Classes
# -------------------------------------------------------------------------------------

class ShapeTypeProps():
    flex_stereo_sharpness : FloatProperty(name=get_id("shape_stereo_sharpness"),description=get_id("shape_stereo_sharpness_tip"),default=90,min=0,max=100,subtype='PERCENTAGE')
    flex_stereo_mode : EnumProperty(name=get_id("shape_stereo_mode"),description=get_id("shape_stereo_mode_tip"),
                                 items=tuple(list(axes) + [('VGROUP','Vertex Group',get_id("shape_stereo_mode_vgroup"))]), default='X')
    flex_stereo_vg : StringProperty(name=get_id("shape_stereo_vgroup"),description=get_id("shape_stereo_vgroup_tip"))

    bake_shapekey_as_basis_normals : BoolProperty(name=get_id("bake_shapekey_as_basis_normals"),description=get_id("bake_shapekey_as_basis_normals_tip"))
    normalize_shapekeys : BoolProperty(name='Normalize Shapekeys',description='Normalize shapekeys so their current max value is 1 and min of -1 if applicable else 0',default=True)

class CurveTypeProps():
    faces : EnumProperty(name=get_id("curve_poly_side"),description=get_id("curve_poly_side_tip"),default='FORWARD',items=(
    ('FORWARD', get_id("curve_poly_side_fwd"), ''),
    ('BACKWARD', get_id("curve_poly_side_back"), ''),
    ('BOTH', get_id("curve_poly_side_both"), '')) )

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

class KitsuneResourceItem(PropertyGroup):
    name : StringProperty(name="Name")

class ExportableProps():
    flex_controller_modes = (
        ('SIMPLE',"Simple",get_id("controllers_simple_tip")),
        ('ADVANCED',"Advanced",get_id("controllers_advanced_tip")),
        ('BUILDER',"Build",get_id("controllers_strict_tip"))
    )

    export : BoolProperty(name=get_id("scene_export"),description=get_id("use_scene_export_tip"),default=True)
    subdir : StringProperty(name=get_id("subdir"),description=get_id("subdir_tip"))
    flex_controller_mode : EnumProperty(name=get_id("controllers_mode"),description=get_id("controllers_mode_tip"),items=flex_controller_modes,default='BUILDER')
    flex_controller_source : StringProperty(name=get_id("controller_source"),description=get_id("controllers_source_tip"),subtype='FILE_PATH', options={'PATH_SUPPORTS_BLEND_RELATIVE'})

    vertex_animations : CollectionProperty(name=get_id("vca_group_props"),type=VertexAnimation)
    active_vertex_animation : IntProperty(default=-1)

    merge_vertices : BoolProperty(name='Merge Vertices on Export', default=True)

    use_toon_edgeline : BoolProperty(name="Use Toon Edge Line",default=False)
    edgeline_per_material : BoolProperty(name="Edgeline Per Material", default=False)
    base_toon_edgeline_thickness : FloatProperty(name="Thickness",default=0.15, min=0.001, soft_max=1.0, precision=3)
    toon_edgeline_vertexgroup : StringProperty(name='Vertex Group Ratio',default='')
    export_edgeline_separately : BoolProperty(name="Export Edgeline Separately", default=False)
    is_edgeline_only : BoolProperty(name='Is Edgeline Only Shell', default=False)

    non_exportable_vgroup : StringProperty(name='Non-Exportable Vertex Group', default='')
    non_exportable_vgroup_tolerance : FloatProperty(name='Non-Exportable Weight Tolerance', default=0.90, min=0.8, max=1.0, precision=2)

    show_items : BoolProperty()
    show_vertexanim_items : BoolProperty()

    generate_lods : BoolProperty(name='Generate LODs on Export', default=False)
    lod_count : IntProperty(name='LOD count', default=1,min=1,soft_max=3)
    decimate_factor : FloatProperty(name='Decimation Per LOD', default=50.0,min=0,soft_max=100,precision=2)


# -------------------------------------------------------------------------------------
# Property Classes (using mixins)
# -------------------------------------------------------------------------------------

class ValveSource_MeshProps(ShapeTypeProps,PropertyGroup):
    pass

class ValveSource_SurfaceProps(ShapeTypeProps,CurveTypeProps,PropertyGroup):
    pass

class ValveSource_CurveProps(ShapeTypeProps,CurveTypeProps,PropertyGroup):
    pass

class ValveSource_TextProps(CurveTypeProps,PropertyGroup):
    pass

class ValveSource_SceneProps(PropertyGroup):
    export_path : StringProperty(name=get_id("exportroot"),description=get_id("exportroot_tip"), subtype='DIR_PATH', options={'PATH_SUPPORTS_BLEND_RELATIVE'})
    engine_path : StringProperty(name=get_id("engine_path"),description=get_id("engine_path_tip"), subtype='DIR_PATH',update=State.onEnginePathChanged)

    dmx_encoding : EnumProperty(name=get_id("dmx_encoding"),description=get_id("dmx_encoding_tip"),items=tuple(encodings),default='2')
    dmx_format : EnumProperty(name=get_id("dmx_format"),description=get_id("dmx_format_tip"),items=tuple(formats),default='1')

    export_format : EnumProperty(name=get_id("export_format"),items=[ ('SMD', "SMD", "Studiomdl Data" ), ('DMX', "DMX", "Datamodel Exchange" ) ],default='DMX')
    up_axis : EnumProperty(name=get_id("up_axis"),items=axes,default='Z',description=get_id("up_axis_tip"))
    up_axis_offset : FloatProperty(name=get_id("up_axis_offset"),description=get_id("up_axis_tip"), soft_max=30,soft_min=-30,default=0,precision=2)
    forward_axis : EnumProperty(name=get_id("forward_axis"),items=axes_forward,default='-Y',description=get_id("up_axis_tip"))
    world_scale : FloatProperty(name=get_id("world_scale"),description=get_id("world_scale_tip"),default=1.00, precision=3, min=0.0001)
    material_path : StringProperty(name=get_id("dmx_mat_path"),description=get_id("dmx_mat_path_tip"))
    export_list_active : IntProperty(name=get_id("active_exportable"),default=0,min=0,update=export_active_changed)
    export_list : CollectionProperty(type=ValveSource_Exportable,options={'SKIP_SAVE','HIDDEN'})
    use_kv2 : BoolProperty(name="Write KeyValues2 (DEBUG)",description="Write ASCII DMX files",default=False)
    game_path : StringProperty(name=get_id("game_path"),description=get_id("game_path_tip"),subtype='DIR_PATH',update=State.onGamePathChanged)
    
    enable_gui_console : BoolProperty(name='Enable Console GUI',default=True, 
        description='Show console overlay with live progress updates. Adds ~20% processing time for visual feedback')
    
    weightlink_threshold : FloatProperty(name=get_id("weightlinkcull"),description=get_id("weightlinkcull_tip"),max=0.001,min=0.0001, default=0.0001,precision=4)
    vertex_influence_limit : IntProperty(name=get_id("maxvertexinfluence"), description=get_id("maxvertexinfluence_tip"),default=3,max=32, soft_max=8,min=1)

    smd_format : EnumProperty(name=get_id("smd_format"), items=(('SOURCE', "Source", "Source Engine (Half-Life 2)") , ("GOLDSOURCE", "GoldSrc", "GoldSrc engine (Half-Life 1)")), default="SOURCE")
    prefab_to_clipboard : BoolProperty(name=get_id("prefab_to_clipboard"), default=False, description='Copy prefab export content to clipboard instead of to a file.')
    do_not_export_edgeline : BoolProperty(name='Do Not Write Edgeline/Outline', default=False)

    kitsuneresource_app_path : StringProperty(name='Executable',subtype='FILE_PATH', options={'PATH_SUPPORTS_BLEND_RELATIVE'}, default='kitsuneresource.exe')
    kitsuneresource_config : StringProperty(name='Config',subtype='FILE_PATH', options={'PATH_SUPPORTS_BLEND_RELATIVE'}, default='previewmodel.json')
    kitsuneresource_project_path : StringProperty(name='Project Directory',subtype='DIR_PATH', options={'PATH_SUPPORTS_BLEND_RELATIVE'})
    kitsuneresource_args : StringProperty(name='Arguments', default='-exportdir "compiled"')

    
    kitsuneresource_model_entries: CollectionProperty(type=KitsuneResourceItem)
    kitsuneresource_model_entry_index: IntProperty(name="Active Entry", default=0)
    kitsuneresource_data_entries: CollectionProperty(type=KitsuneResourceItem)
    kitsuneresource_flag_single_addon: BoolProperty(name="Single Addon", default=True)
    kitsuneresource_flag_no_mat_local: BoolProperty(name="No Mat Local", default=True)
    kitsuneresource_flag_archive_old: BoolProperty(name="Archive Previous Version", default=True)

    kitsuneresource_flag_game_or_package : EnumProperty(name="Game or Package",items=[
        ('GAME', 'Game', ''),
        ('PACKAGE', 'Package', ''),
    ],default='GAME')

class ValveSource_BoneProps(JiggleBoneProps,PropertyGroup):
    export_name : StringProperty(name=get_id("exportname"), maxlen=256)

    bone_sort_order : IntProperty(name='Bone Sort Order', default=0, min=0,soft_max=4)
    
    ignore_rotation_offset : BoolProperty(name='Ignore Rotation Offsets', default=False)
    export_rotation_offset_x : FloatProperty(name='Rotation X', unit='ROTATION', default=math.radians(0), precision=4, min=-360, max=360)
    export_rotation_offset_y : FloatProperty(name='Rotation Y', unit='ROTATION', default=math.radians(0), precision=4, min=-360, max=360)
    export_rotation_offset_z : FloatProperty(name='Rotation Z', unit='ROTATION', default=math.radians(0), precision=4, min=-360, max=360)
    
    ignore_location_offset : BoolProperty(name='Ignore Location Offsets', default=True)
    export_location_offset_x : FloatProperty(name='Location X', default=0, precision=4)
    export_location_offset_y : FloatProperty(name='Location Y', default=0, precision=4)
    export_location_offset_z : FloatProperty(name='Location Z', default=0, precision=4)
    
class ValveSource_ObjectProps(ExportableProps, PropertyGroup):
    action_filter : StringProperty(name=get_id("slot_filter") if State.useActionSlots else get_id("action_filter"),description=get_id("slot_filter_tip") if State.useActionSlots else get_id("action_filter_tip"),default="*")
    triangulate : BoolProperty(name=get_id("triangulate"),description=get_id("triangulate_tip"),default=False)
    vertex_map_remaps :  CollectionProperty(name="Vertes map remaps",type=ValveSource_FloatMapRemap)
    
    dme_flexcontrollers : CollectionProperty(name='Flex Controllers', type=FlexControllerItem)
    dme_flexcontrollers_index : IntProperty(default=-1, update=on_flexcontroller_index_changed)
    
    dmx_attachment : BoolProperty(name='Is Attachment',default=False)
    smd_hitbox : BoolProperty(name='Is Hitbox',default=False)    
    smd_hitbox_group : EnumProperty(name='Hitbox Group',items=hitbox_group,default='0')

    jigglebone_prefabfile : StringProperty(name='Jigglebone Prefab',default='',subtype="FILE_PATH", options={'PATH_SUPPORTS_BLEND_RELATIVE'})
    attachment_prefabfile : StringProperty(name='Attachments Prefab',default='',subtype="FILE_PATH", options={'PATH_SUPPORTS_BLEND_RELATIVE'})
    hitbox_prefabfile : StringProperty(name='Hitbox Prefab',default='',subtype="FILE_PATH", options={'PATH_SUPPORTS_BLEND_RELATIVE'})

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

    reset_pose_per_anim : BoolProperty(name='Reset Pose Per Animation Export', description="Reset all bones to rest pose before each export to prevent pose carry-over between animations",default=True)

    action_selection : EnumProperty(name=get_id("action_selection_mode"), items=arm_modes,description=get_id("action_selection_mode_tip"),default='FILTERED')
    legacy_rotation : BoolProperty(name=get_id("bone_rot_legacy"),description=get_id("bone_rot_legacy_tip"),default=False)

    ignore_bone_exportnames : BoolProperty(name=get_id("ignore_bone_exportnames"))
    bone_direction_naming_left : StringProperty(name='Left Bone Dir', default='L')
    bone_direction_naming_right : StringProperty(name='Right Bone Dir', default='R')
    bone_name_startcount : IntProperty(name='Bone Name Starting Count', default=1, min=0, soft_max=10)

class ValveSource_CollectionProps(ExportableProps,PropertyGroup):
    mute : BoolProperty(name=get_id("group_suppress"),description=get_id("group_suppress_tip"),default=False)
    selected_item : IntProperty(default=-1, max=-1, min=-1)
    automerge : BoolProperty(name=get_id("group_merge_mech"),description=get_id("group_merge_mech_tip"),default=False)

class ValveSource_MaterialProps(PropertyGroup):
    override_dmx_export_path : StringProperty(name='Material Path', default='')

# -------------------------------------------------------------------------------------
# Register
# -------------------------------------------------------------------------------------

_classes = (
    # Base/Utility Classes
    ValveSource_FloatMapRemap,
    KitsuneResourceItem,
    
    # Simple Item Classes
    FlexControllerItem,
    VertexAnimation,
    
    # Material Classes
    ValveSource_MaterialProps,
    
    # Geometry Property Classes
    ValveSource_MeshProps,
    ValveSource_SurfaceProps,
    ValveSource_CurveProps,
    ValveSource_TextProps,
    
    # Object/Bone Property Classes
    ValveSource_BoneProps,
    ValveSource_ObjectProps,
    ValveSource_ArmatureProps,
    
    # Collection/Group Classes
    ValveSource_CollectionProps,
    
    # Exportable and Scene Classes
    ValveSource_Exportable,
    ValveSource_SceneProps,

    # KitsuneResource
    GUI.SMD_UL_KitsuneResourceEntries,
    GUI.SMD_PT_KitsuneResourceCompile,
    GUI.SMD_OT_KitsuneResourceCompile,
    GUI.SMD_OT_KitsuneResourceCompileData,
    GUI.SMD_OT_KitsuneResourceLoadEntries,
    
    # GUI - Scene
    GUI.SMD_MT_ExportChoice,
    GUI.SMD_PT_Scene,
    GUI.SMD_MT_ConfigureScene,
    
    # Properties
    GUI.SMD_UL_ExportItems,
    GUI.SMD_UL_GroupItems,
    GUI.SMD_PT_Properties,
    GUI.SMD_PT_Group,
    GUI.SMD_PT_Armature,
    GUI.SMD_PT_Bone,
    GUI.SMD_PT_BoneData,
    GUI.SMD_PT_Mesh,
    GUI.SMD_PT_Material,
    GUI.SMD_PT_Shapekey,
    GUI.SMD_PT_Vertexmap,
    GUI.SMD_PT_Vertexfloatmap,
    GUI.SMD_PT_Vertexanimations,
    GUI.SMD_PT_ToonEdgeline,
    GUI.SMD_PT_LOD,
    GUI.SMD_PT_Empty,
    GUI.SMD_PT_Curve,
    GUI.SMD_PT_All_Hitboxes,
    GUI.SMD_PT_All_Attachments,
    GUI.SMD_PT_All_Jigglebones,
    GUI.SMD_PT_Jigglebones,
    
    # Properties Operators
    GUI.SMD_UL_FlexControllers,
    GUI.SMD_MT_FlexControllerSpecials,
    GUI.SMD_OT_AutoAssignFlexGroups,
    GUI.SMD_OT_AddFlexController,
    GUI.SMD_OT_AddAllFlexControllers,
    GUI.SMD_OT_RemoveFlexController,
    GUI.SMD_OT_MoveFlexController,
    GUI.SMD_OT_SortFlexControllers,
    GUI.SMD_OT_ClearFlexControllers,
    GUI.SMD_OT_PreviewFlexController,
    GUI.SMD_OT_AddVertexMapRemap,
    GUI.SMD_UL_VertexAnimationItem,
    GUI.SMD_OT_AddVertexAnimation,
    GUI.SMD_OT_RemoveVertexAnimation,
    GUI.SMD_OT_PreviewVertexAnimation,
    GUI.SMD_OT_GenerateVertexAnimationQCSnippet,
    GUI.SMD_OT_CopyBoneExportName,
    GUI.SMD_OT_AssignBoneRotExportOffset,
    GUI.SMD_OT_CopySourceBoneProps,
    
    # Flex and Export/Import
    flex.DmxWriteFlexControllers,
    flex.AddCorrectiveShapeDrivers,
    flex.RenameShapesToMatchCorrectiveDrivers,
    flex.ActiveDependencyShapes,
    flex.InsertUUID,
    export_smd.SmdExporter, 
    export_smd.PrefabExporter, 
    import_smd.SmdImporter,
)

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    
    from . import translations
    bpy.app.translations.register(__name__,translations.translations)
    
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    bpy.types.MESH_MT_shape_key_context_menu.append(menu_func_shapekeys)
    bpy.types.TEXT_MT_edit.append(menu_func_textedit)
    bpy.types.VIEW3D_MT_bone_options_toggle.append(draw_copy_bone_props)
        
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
    bpy.types.VIEW3D_MT_bone_options_toggle.remove(draw_copy_bone_props)

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