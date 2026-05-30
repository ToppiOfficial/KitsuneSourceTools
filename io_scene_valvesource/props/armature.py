__all__ = ['ValveSource_BoneProps', 'ValveSource_ArmatureProps']

import bpy, math
from bpy.props import (StringProperty, BoolProperty, EnumProperty, IntProperty,
                       FloatProperty, CollectionProperty)
from ..utils import get_id
from .items import ProcBoneEntry, ArmatureItemEntry, _proc_entry_invalidate_cache
from .mixins import JiggleBoneProps


class ValveSource_BoneProps(JiggleBoneProps, bpy.types.PropertyGroup):
    export_name : StringProperty(name=get_id("exportname"), description=get_id("exportname_tip"), maxlen=256)

    bone_sort_order : IntProperty(name=get_id('prop_bone_sort_order'), description=get_id('prop_bone_sort_order_tip'), default=0, min=0, soft_max=4)

    ignore_rotation_offset : BoolProperty(name=get_id('prop_ignore_rotation_offset'), description=get_id('prop_ignore_rotation_offset_tip'), default=False)
    export_rotation_offset_x : FloatProperty(name=get_id('prop_rotation_x'), description=get_id('prop_rotation_x_tip'), unit='ROTATION', default=math.radians(0), precision=4, min=-360, max=360)
    export_rotation_offset_y : FloatProperty(name=get_id('prop_rotation_y'), description=get_id('prop_rotation_y_tip'), unit='ROTATION', default=math.radians(0), precision=4, min=-360, max=360)
    export_rotation_offset_z : FloatProperty(name=get_id('prop_rotation_z'), description=get_id('prop_rotation_z_tip'), unit='ROTATION', default=math.radians(0), precision=4, min=-360, max=360)

    ignore_location_offset : BoolProperty(name=get_id('prop_ignore_location_offset'), description=get_id('prop_ignore_location_offset_tip'), default=True)
    export_location_offset_x : FloatProperty(name=get_id('prop_location_x'), description=get_id('prop_location_x_tip'), default=0, precision=4)
    export_location_offset_y : FloatProperty(name=get_id('prop_location_y'), description=get_id('prop_location_y_tip'), default=0, precision=4)
    export_location_offset_z : FloatProperty(name=get_id('prop_location_z'), description=get_id('prop_location_z_tip'), default=0, precision=4)

    proc_tolerance : FloatProperty(
        name=get_id('prop_pose_bone_proc_tolerance'),
        description=get_id('prop_pose_bone_proc_tolerance_tip'),
        default=math.pi / 2, min=0.01, max=math.pi, subtype='ANGLE', precision=2,
        update=_proc_entry_invalidate_cache,
    )


class ValveSource_ArmatureProps(bpy.types.PropertyGroup):
    implicit_zero_bone : BoolProperty(name=get_id("dummy_bone"), default=True, description=get_id("dummy_bone_tip"))
    arm_modes = (
        ('CURRENT', get_id("action_slot_current"), get_id("action_slot_selection_current_tip")),
        ('FILTERED', get_id("slot_filter"), get_id("slot_filter_tip")),
        ('FILTERED_ACTIONS', get_id("action_filter"), get_id("action_selection_filter_tip")),
    )

    reset_pose_per_anim : BoolProperty(name=get_id('prop_reset_pose_per_anim'), description=get_id('prop_reset_pose_per_anim_tip'), default=True)

    action_selection : EnumProperty(name=get_id("action_selection_mode"), items=arm_modes, description=get_id("action_selection_mode_tip"), default='FILTERED')

    arm_hitbox_entries : CollectionProperty(type=ArmatureItemEntry)
    arm_hitbox_index : IntProperty(default=-1)
    arm_attachment_entries : CollectionProperty(type=ArmatureItemEntry)
    arm_attachment_index : IntProperty(default=-1)
    arm_jigglebone_entries : CollectionProperty(type=ArmatureItemEntry)
    arm_jigglebone_index : IntProperty(default=-1)

    ignore_bone_exportnames : BoolProperty(name=get_id("ignore_bone_exportnames"), description=get_id("ignore_bone_exportnames_tip"))
    bone_direction_naming_left : StringProperty(name=get_id('prop_bone_dir_left'), description=get_id('prop_bone_dir_left_tip'), default='L')
    bone_direction_naming_right : StringProperty(name=get_id('prop_bone_dir_right'), description=get_id('prop_bone_dir_right_tip'), default='R')
    bone_name_startcount : IntProperty(name=get_id('prop_bone_name_startcount'), description=get_id('prop_bone_name_startcount_tip'), default=1, min=0, soft_max=10)

    proc_bones       : CollectionProperty(type=ProcBoneEntry)
    proc_bones_index : IntProperty(default=-1)
