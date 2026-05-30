__all__ = ['ValveSource_MaterialProps']

import bpy
from bpy.props import StringProperty
from ..utils import get_id


class ValveSource_MaterialProps(bpy.types.PropertyGroup):
    override_dmx_export_path : StringProperty(name='Material Path', description=get_id("prop_override_dmx_export_path_tip"), default='')
