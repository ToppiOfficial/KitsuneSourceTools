__all__ = [
    # items
    'ValveSource_FloatMapRemap',
    'KitsuneResourceItem',
    'PrefabItem',
    'FlexControllerItem',
    'VertexAnimation',
    'ArmatureItemEntry',
    'ProcBoneEntry',
    # mixins
    'ShapeTypeProps',
    'CurveTypeProps',
    'JiggleBoneProps',
    'ExportableProps',
    # scene
    'ValveSource_Exportable',
    'ValveSource_SceneProps',
    # object
    'ValveSource_MeshProps',
    'ValveSource_SurfaceProps',
    'ValveSource_CurveProps',
    'ValveSource_TextProps',
    'ValveSource_ObjectProps',
    # armature
    'ValveSource_BoneProps',
    'ValveSource_ArmatureProps',
    # collection
    'ValveSource_CollectionProps',
    # material
    'ValveSource_MaterialProps',
]

if "bpy" in dir():
    import importlib
    from . import items, mixins, scene, object, armature, collection, material
    for _mod in [items, mixins, scene, object, armature, collection, material]:
        importlib.reload(_mod)
else:
    from . import items, mixins, scene, object, armature, collection, material

from .items import *
from .mixins import *
from .scene import *
from .object import *
from .armature import *
from .collection import *
from .material import *
