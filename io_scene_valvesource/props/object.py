__all__ = [
    'ValveSource_MeshProps',
    'ValveSource_SurfaceProps',
    'ValveSource_CurveProps',
    'ValveSource_TextProps',
    'ValveSource_ObjectProps',
]

import bpy
from bpy.props import (StringProperty, BoolProperty, EnumProperty, IntProperty,
                       CollectionProperty, FloatProperty, PointerProperty)
from ..utils import get_id, hitbox_group
from .items import FlexControllerItem, DmeFlexRuleItem, VertexAnimation, ValveSource_FloatMapRemap
from .mixins import ShapeTypeProps, CurveTypeProps, ExportableProps
from .scene import on_flexcontroller_index_changed


class ValveSource_MeshProps(ShapeTypeProps, bpy.types.PropertyGroup):
    pass


class ValveSource_SurfaceProps(ShapeTypeProps, CurveTypeProps, bpy.types.PropertyGroup):
    pass


class ValveSource_CurveProps(ShapeTypeProps, CurveTypeProps, bpy.types.PropertyGroup):
    pass


class ValveSource_TextProps(CurveTypeProps, bpy.types.PropertyGroup):
    pass


class ValveSource_ObjectProps(ExportableProps, bpy.types.PropertyGroup):
    mesh_type : EnumProperty(
        name="Mesh Type",
        description="Controls export role and feature availability for this mesh",
        items=[
            ('DEFAULT',    "Default",    "Standard export with all features"),
            ('COLLISION',  "Collision",  "Physics mesh: no materials, no post-process, max 1 bone influence per vertex"),
            ('CLOTHPROXY', "Cloth Proxy", "Cloth proxy: no materials, cloth DMX attributes, min 4–max 8 bone influences, DMX format required"),
        ],
        default='DEFAULT',
    )
    action_filter : StringProperty(name=get_id("slot_filter"), description=get_id("slot_filter_tip"), default="*")
    triangulate : BoolProperty(name=get_id("triangulate"), description=get_id("triangulate_tip"), default=False)
    vertex_map_remaps : CollectionProperty(name="Vertes map remaps", type=ValveSource_FloatMapRemap)

    dme_flexcontrollers : CollectionProperty(name='Flex Controllers', type=FlexControllerItem)
    dme_flexcontrollers_index : IntProperty(default=-1, update=on_flexcontroller_index_changed)
    dme_flex_rules : CollectionProperty(name='Flex Rules', type=DmeFlexRuleItem)
    dme_flex_rules_index : IntProperty(default=-1)

    dmx_attachment : BoolProperty(name=get_id('prop_dmx_attachment'), description=get_id('prop_dmx_attachment_tip'), default=False)
    smd_hitbox : BoolProperty(name=get_id('prop_smd_hitbox'), description=get_id('prop_smd_hitbox_tip'), default=False)
    smd_hitbox_group : EnumProperty(name=get_id('prop_smd_hitbox_group'), description=get_id('prop_smd_hitbox_group_tip'), items=hitbox_group, default='0')

    jigglebone_prefabfile : StringProperty(name=get_id('prop_jigglebone_prefabfile'), description=get_id('prop_jigglebone_prefabfile_tip'), default='', subtype="FILE_PATH", options={'PATH_SUPPORTS_BLEND_RELATIVE'})
    attachment_prefabfile : StringProperty(name=get_id('prop_attachment_prefabfile'), description=get_id('prop_attachment_prefabfile_tip'), default='', subtype="FILE_PATH", options={'PATH_SUPPORTS_BLEND_RELATIVE'})
    hitbox_prefabfile : StringProperty(name=get_id('prop_hitbox_prefabfile'), description=get_id('prop_hitbox_prefabfile_tip'), default='', subtype="FILE_PATH", options={'PATH_SUPPORTS_BLEND_RELATIVE'})
    procedural_prefabfile : StringProperty(name=get_id('prop_procedural_prefabfile'), description=get_id('prop_procedural_prefabfile_tip'), default='', subtype="FILE_PATH", options={'PATH_SUPPORTS_BLEND_RELATIVE'})
