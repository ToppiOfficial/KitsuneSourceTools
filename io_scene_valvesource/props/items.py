__all__ = [
    'ValveSource_FloatMapRemap',
    'KitsuneResourceItem',
    'PrefabItem',
    'FlexControllerItem',
    'DmeFlexRuleItem',
    'VertexAnimation',
    'ArmatureItemEntry',
    'ProcBoneEntry',
]

import bpy, re
from bpy.props import (StringProperty, BoolProperty, EnumProperty, IntProperty,
                       FloatProperty, FloatVectorProperty, PointerProperty)
from ..utils import get_id
from .. import procbones_sim as _procbones_sim


def update_sanitize_name(self, context):
    legal_name = re.sub(r'[^a-z0-9]', '_', self.controller_name.lower())
    if self.controller_name != legal_name:
        self.controller_name = legal_name


def _proc_entry_invalidate_cache(self, context):
    arm_ob = context.object
    if arm_ob and arm_ob.type == 'ARMATURE':
        _procbones_sim.invalidate_proc_cache(arm_ob.name)
    else:
        _procbones_sim._proc_trigger_cache.clear()


class ValveSource_FloatMapRemap(bpy.types.PropertyGroup):
    group : StringProperty(name="Group name", description=get_id("prop_float_map_group_tip"), default="")
    min : FloatProperty(name="Min", description="Maps to 0.0", default=0.0)
    max : FloatProperty(name="Max", description="Maps to 1.0", default=1.0)


class KitsuneResourceItem(bpy.types.PropertyGroup):
    name       : StringProperty(name="Name")
    export     : BoolProperty(name="Export", description=get_id("prop_kr_entry_export_tip"), default=True)
    entry_type : EnumProperty(
        description=get_id("prop_kr_entry_type_tip"),
        items=[('MODEL', "Model", ""), ('DATA', "Data", "")],
        default='MODEL'
    )


class PrefabItem(bpy.types.PropertyGroup):
    filepath: StringProperty(name="Filepath", description=get_id("prop_prefab_filepath_tip"), subtype='FILE_PATH', options={'PATH_SUPPORTS_BLEND_RELATIVE'})


class FlexControllerItem(bpy.types.PropertyGroup):
    controller_name: StringProperty(name='Controller Name', description=get_id("prop_controller_name_tip"), update=update_sanitize_name)
    raw_delta_name : StringProperty(name='Delta Name', description=get_id("prop_delta_name_tip"))
    shapekey : StringProperty(name='ShapeKey', description=get_id("prop_flexctrl_shapekey_tip"))
    eyelid : BoolProperty(name='Eyelid', description=get_id("prop_eyelid_tip"))
    stereo : BoolProperty(name='Stereo', description=get_id("prop_stereo_tip"))
    flexgroup : EnumProperty(name='Flex Type', description=get_id("prop_flex_type_tip"), items=[
        ('NONE', 'NONE', ''),
        ('EYES', 'EYES', ''),
        ('EYELID', 'EYELID', ''),
        ('BROW', 'BROW', ''),
        ('MOUTH', 'MOUTH', ''),
        ('MISC', 'MISC', ''),
        ('CHEEK', 'CHEEK', ''),
    ], default='NONE')
    flex_min : FloatProperty(name='Flex Min', description=get_id("prop_flex_min_tip"), default=0.0, soft_min=-1.0, soft_max=1.0, precision=3)
    flex_max : FloatProperty(name='Flex Max', description=get_id("prop_flex_max_tip"), default=1.0, soft_min=0.0, soft_max=2.0, precision=3)


class DmeFlexRuleItem(bpy.types.PropertyGroup):
    rule_type: EnumProperty(
        name="Rule Type",
        description=get_id("prop_dme_flex_rule_type_tip"),
        items=[
            ('EXPRESSION',  "Expression",  get_id("prop_dme_flex_rule_expression_tip")),
            ('PASSTHROUGH', "Pass Through", get_id("prop_dme_flex_rule_passthrough_tip")),
            ('LOCALVAR',    "Local Var",    get_id("prop_dme_flex_rule_localvar_tip")),
            ('DOMINATION',  "Domination",   get_id("prop_dme_flex_rule_domination_tip")),
            ('CORRECTIVE',  "Corrective",   get_id("prop_dme_flex_rule_corrective_tip")),
        ],
        default='EXPRESSION',
    )
    name: StringProperty(name="Name", description=get_id("prop_dme_flex_rule_name_tip"))
    expression: StringProperty(name="Expression", description=get_id("prop_dme_flex_rule_expr_tip"))
    components: StringProperty(name="Components", description=get_id("prop_dme_corrective_components_tip"))
    dominator_names: StringProperty(name="Dominators", description=get_id("prop_dme_dominator_names_tip"))
    suppressed_names: StringProperty(name="Suppressed", description=get_id("prop_dme_suppressed_names_tip"))


class VertexAnimation(bpy.types.PropertyGroup):
    name : StringProperty(name="Name", description=get_id("prop_vertex_anim_name_tip"), default="VertexAnim")
    start : IntProperty(name="Start", description=get_id("vca_start_tip"), default=0)
    end : IntProperty(name="End", description=get_id("vca_end_tip"), default=250)
    export_sequence : BoolProperty(name=get_id("vca_sequence"), description=get_id("vca_sequence_tip"), default=True)


class ArmatureItemEntry(bpy.types.PropertyGroup):
    obj : PointerProperty(type=bpy.types.Object)
    bone_name : StringProperty()


class ProcBoneEntry(bpy.types.PropertyGroup):
    proc_type : EnumProperty(
        name=get_id('prop_proc_bone_type'),
        description=get_id('prop_proc_bone_type_tip'),
        items=[
            ('TRIGGER', "Trigger", "Action-driven pose blending",  'ACTION',      0),
            ('LOOKAT',  "LookAt",  "Aim toward a target bone",     'CON_TRACKTO', 1),
        ],
        default='TRIGGER',
    )
    helper_bone : StringProperty(name=get_id('prop_proc_bone_helper'), description=get_id('prop_proc_bone_helper_tip'))
    driver_bone : StringProperty(name=get_id('prop_proc_bone_driver'), description=get_id('prop_proc_bone_driver_tip'))
    action : PointerProperty(name=get_id('prop_proc_bone_action'), description=get_id('prop_proc_bone_action_tip'), type=bpy.types.Action, update=_proc_entry_invalidate_cache)
    action_slot_name : StringProperty(name=get_id('prop_proc_bone_slot'), description=get_id('prop_proc_bone_slot_tip'), update=_proc_entry_invalidate_cache)
    _lookat_axes = [
        ('+X', "+X", "Positive X",  1),
        ('+Y', "+Y", "Positive Y",  2),
        ('+Z', "+Z", "Positive Z",  4),
        ('-X', "-X", "Negative X",  8),
        ('-Y', "-Y", "Negative Y", 16),
        ('-Z', "-Z", "Negative Z", 32),
    ]
    lookat_aim_axis : EnumProperty(
        name=get_id('prop_proc_bone_lookat_aim_axis'),
        description=get_id('prop_proc_bone_lookat_aim_axis_tip'),
        items=_lookat_axes, default={'+X'}, options={'ENUM_FLAG'},
    )
    lookat_up_axis : EnumProperty(
        name=get_id('prop_proc_bone_lookat_up_axis'),
        description=get_id('prop_proc_bone_lookat_up_axis_tip'),
        items=_lookat_axes, default={'+Z'}, options={'ENUM_FLAG'},
    )
    lookat_offset : FloatVectorProperty(
        name=get_id('prop_proc_bone_lookat_offset'),
        description=get_id('prop_proc_bone_lookat_offset_tip'),
        size=3, default=(0.0, 0.0, 0.0),
        subtype='XYZ',
    )
