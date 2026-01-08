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

import bpy, struct, time, collections, os, subprocess, sys, builtins, itertools, dataclasses, typing, mathutils
from bpy.app.translations import pgettext
from bpy.app.handlers import depsgraph_update_post, load_post, persistent
from mathutils import Matrix, Vector
from math import radians, pi, ceil
from io import TextIOWrapper
from . import datamodel

intsize = struct.calcsize("i")
floatsize = struct.calcsize("f")

rx90 = Matrix.Rotation(radians(90),4,'X')
ry90 = Matrix.Rotation(radians(90),4,'Y')
rz90 = Matrix.Rotation(radians(90),4,'Z')
ryz90 = ry90 @ rz90

rx90n = Matrix.Rotation(radians(-90),4,'X')
ry90n = Matrix.Rotation(radians(-90),4,'Y')
rz90n = Matrix.Rotation(radians(-90),4,'Z')

mat_BlenderToSMD = ry90 @ rz90 # for legacy support only

epsilon = Vector([0.0001] * 3)

implicit_bone_name = "blender_implicit"

# SMD types
REF = 0x1 # $body, $model, $bodygroup->studio (if before a $body or $model), $bodygroup, $lod->replacemodel
PHYS = 0x3 # $collisionmesh, $collisionjoints
ANIM = 0x4 # $sequence, $animation
FLEX = 0x6 # $model VTA

mesh_compatible = ('MESH', 'TEXT', 'FONT', 'SURFACE', 'META', 'CURVE')
shape_types = ('MESH' , 'SURFACE', 'CURVE')

exportable_types = list((*mesh_compatible, 'ARMATURE'))
exportable_types = tuple(exportable_types)

axes = (('X','X',''),('Y','Y',''),('Z','Z',''))
axes_forward = (('-X','-X',''),('-Y','-Y',''),('-Z','-Z',''),('X','X',''),('Y','Y',''),('Z','Z',''))
axes_lookup = { 'X':0, 'Y':1, 'Z':2 }
axes_lookup_source2 = { 'X':1, 'Y':2, 'Z':3 }

pbr_to_phong_channels = [
    ('GREY', 'Greyscale', 'The image is a greyscale mask. (Only the red channel is used)'),
    ('R', 'Red', ''),
    ('G', 'Green', ''),
    ('B', 'Blue', ''),
    ('A', 'Alpha', ''),
]

hitbox_group = [
    ('0', 'Generic', 'the default group of hitboxes, appears White in HLMV'),
    ('1', 'Head', 'Used for human NPC heads and to define where the player sits on the vehicle.mdl, appears Red in HLMV'),
    ('2', 'Chest', 'Used for human NPC midsection and chest, appears Green in HLMV'),
    ('3', 'Stomach', 'Used for human NPC stomach and pelvis, appears Yellow in HLMV'),
    ('4', 'Left Arm', 'Used for human Left Arm, appears Deep Blue in HLMV'),
    ('5', 'Right Arm', 'Used for human Right Arm, appears Bright Violet in HLMV'),
    ('6', 'Left Leg', 'Used for human Left Leg, appears Bright Cyan in HLMV'),
    ('7', 'Right Leg', 'Used for human Right Leg, appears White like the default group in HLMV (Orange in Garry\'s Mod'),
    ('8', 'Neck', 'Used for human neck (to fix penetration to head from behind), appears Orange in HLMV (In all games since CS:GO)'),
]

toggle_show_ops = [
    "show_jigglebones",
    "show_hitboxes",
    "show_attachments",
    "show_materials",
    "show_armaturemapper_help",
    "show_prefab_help",
    "show_exportable_help",
    "show_pbrphong_help",
    "show_clothnodes",
    "show_objectwarnings",
    ['show_smdobject', 'show_smdmesh', 'show_smdcurve', 'show_smdbone', 'show_smdmaterials', 'show_smdempty'],
    ['show_flex','show_vertexmap','show_floatmaps', 'show_vertexanimation'],
    'show_smdarmature',
    ['show_smdattachments', 'show_smdjigglebone', 'show_smdanimation', 'show_smdhitbox'],
    'show_valvemodel_operators'
]

class ExportFormat:
    SMD = 1
    DMX = 2

class Compiler:
    UNKNOWN = 0
    STUDIOMDL = 1 # Source 1
    RESOURCECOMPILER = 2 # Source 2
    MODELDOC = 3 # Source 2 post-Alyx

@dataclasses.dataclass(frozen = True)
class dmx_version:
    encoding : int
    format : int
    title : str = dataclasses.field(default="Unnamed", hash=False, compare=False)

    compiler : int = Compiler.STUDIOMDL

    @property
    def format_enum(self): return str(self.format) + ("_modeldoc" if self.compiler == Compiler.MODELDOC else "")
    @property
    def format_title(self): return f"Model {self.format}" + (" (ModelDoc)" if self.compiler == Compiler.MODELDOC else "")

dmx_versions_source1 = {
'Ep1': dmx_version(0,0, "Half-Life 2: Episode One"),
'Source2007': dmx_version(2,1, "Source 2007"),
'Source2009': dmx_version(2,1, "Source 2009"),
'Garrysmod': dmx_version(2,1, "Garry's Mod"),
'Orangebox': dmx_version(5,18, "OrangeBox / Source MP"),
'nmrih': dmx_version(2,1, "No More Room In Hell"),
}

dmx_versions_source1.update({version.title:version for version in [
dmx_version(2,1, 'Team Fortress 2'),
dmx_version(0,0, 'Left 4 Dead'), # wants model 7, but it's not worth working out what that is when L4D2 in far more popular and SMD export works
dmx_version(4,15, 'Left 4 Dead 2'),
dmx_version(5,18, 'Alien Swarm'),
dmx_version(5,18, 'Portal 2'),
dmx_version(5,18, 'Source Filmmaker'),
# and now back to 2/1 for some reason...
dmx_version(2,1, 'Half-Life 2'),
dmx_version(2,1, 'Source SDK Base 2013 Singleplayer'),
dmx_version(2,1, 'Source SDK Base 2013 Multiplayer'),
]})

dmx_versions_source2 = {
'dota2': dmx_version(9,22, "Dota 2", Compiler.RESOURCECOMPILER),
'steamtours': dmx_version(9,22, "SteamVR", Compiler.RESOURCECOMPILER),
'hlvr': dmx_version(9,22, "Half-Life: Alyx", Compiler.MODELDOC), # format is still declared as 22, but modeldoc introduces breaking changes
'cs2': dmx_version(9,22, 'Counter-Strike 2', Compiler.MODELDOC),
}

def getAllDataNameTranslations(string : str) -> set[str]:
    if not bpy.app.translations.locales:
        return { string } # Blender was compiled without translations
    
    translations = set()
        
    view_prefs = bpy.context.preferences.view
    user_language = view_prefs.language
    user_dataname_translate = view_prefs.use_translate_new_dataname
        
    try:
        view_prefs.use_translate_new_dataname = True
        for language in bpy.app.translations.locales:
            if language == "hr_HR" and bpy.app.version < (4,5,3):
                continue # enabling Croatian generates a C error message in the console, and it's very sparsely translated anyway
            try:
                view_prefs.language = language
                translations.add(bpy.app.translations.pgettext_data(string))
            except:
                pass
    finally:
        view_prefs.language = user_language
        view_prefs.use_translate_new_dataname = user_dataname_translate
    
    return translations

class _StateMeta(type): # class properties are not supported below Python 3.9, so we use a metaclass instead
    def __init__(cls, *args, **kwargs):
        cls._exportableObjects = set()
        cls.last_export_refresh = 0
        cls._engineBranch = None
        cls._gamePathValid = False
        cls._use_action_slots = bpy.app.version >= (4,4,0)
        cls._legacySlotTranslations = getAllDataNameTranslations("Legacy Slot")

    @property
    def exportableObjects(cls) -> set[int]: return cls._exportableObjects

    @property
    def engineBranch(cls) -> dmx_version | None: return cls._engineBranch

    @property
    def datamodelEncoding(cls): return cls._engineBranch.encoding if cls._engineBranch else int(bpy.context.scene.vs.dmx_encoding)

    @property
    def datamodelFormat(cls): return cls._engineBranch.format if cls._engineBranch else int(bpy.context.scene.vs.dmx_format.split("_")[0])

    @property
    def engineBranchTitle(cls): return cls._engineBranch.title if cls._engineBranch else None

    @property
    def compiler(cls): return cls._engineBranch.compiler if cls._engineBranch else Compiler.MODELDOC if "modeldoc" in bpy.context.scene.vs.dmx_format else Compiler.UNKNOWN

    @property
    def exportFormat(cls): return ExportFormat.DMX if bpy.context.scene.vs.export_format == 'DMX' and cls.datamodelEncoding != 0 else ExportFormat.SMD

    @property
    def gamePath(cls):
        return cls._rawGamePath if cls._gamePathValid else None

    @property
    def useActionSlots(cls): return cls._use_action_slots

    @property
    def legacySlotNames(cls): return cls._legacySlotTranslations

    @property
    def _rawGamePath(cls):
        if bpy.context.scene.vs.game_path:
            return os.path.abspath(os.path.join(bpy.path.abspath(bpy.context.scene.vs.game_path),''))
        else:
            return os.getenv('vproject')

class State(metaclass=_StateMeta):
    @classmethod
    def update_scene(cls, scene : bpy.types.Scene | None = None):
        scene = scene or bpy.context.scene
        assert(scene)
        cls._exportableObjects = set([ob.session_uid for ob in scene.objects if ob.type in exportable_types and not (ob.type == 'CURVE' and ob.data.bevel_depth == 0 and ob.data.extrude == 0)])
        make_export_list(scene)
        cls.last_export_refresh = time.time()
    
    @staticmethod
    @persistent
    def _onDepsgraphUpdate(scene : bpy.types.Scene):
        if scene == bpy.context.scene and time.time() - State.last_export_refresh > 0.25:
            State.update_scene(scene)

    @staticmethod
    @persistent
    def _onLoad(_):
        State.update_scene()
        State._updateEngineBranch()
        State._validateGamePath()

    @classmethod
    def hook_events(cls):
        if not cls.update_scene in depsgraph_update_post:
            depsgraph_update_post.append(cls._onDepsgraphUpdate)
            load_post.append(cls._onLoad)

    @classmethod
    def unhook_events(cls):
        if cls.update_scene in depsgraph_update_post:
            depsgraph_update_post.remove(cls._onDepsgraphUpdate)
            load_post.remove(cls._onLoad)

    @staticmethod
    def onEnginePathChanged(props,context):
        if props == context.scene.vs:
            State._updateEngineBranch()

    @classmethod
    def _updateEngineBranch(cls):
        try:
            cls._engineBranch = getEngineBranch()
        except:
            cls._engineBranch = None

    @staticmethod
    def onGamePathChanged(props,context):
        if props == context.scene.vs:
            State._validateGamePath()

    @classmethod
    def _validateGamePath(cls):
        if cls._rawGamePath:
            for anchor in ["gameinfo.txt", "addoninfo.txt", "gameinfo.gi"]:
                if os.path.exists(os.path.join(cls._rawGamePath,anchor)):
                    cls._gamePathValid = True
                    return
        cls._gamePathValid = False

def print(*args, newline=True, debug_only=False):
    if not debug_only or bpy.app.debug_value > 0:
        builtins.print(" ".join([str(a) for a in args]).encode(sys.getdefaultencoding()).decode(sys.stdout.encoding or sys.getdefaultencoding()), end= "\n" if newline else "", flush=True)

def get_id(str_id: str, format_string: bool = False, data: bool = False) -> str:
    from . import translations
    out = translations.ids.get(str_id, "")
    if out is None:
        return ""
    if format_string or (data and bpy.context.preferences.view.use_translate_new_dataname):
        return typing.cast(str, pgettext(out))
    else:
        return out

def get_active_exportable(context = None):
    if not context: context = bpy.context
    
    if not context.scene.vs.export_list_active < len(context.scene.vs.export_list):
        return None

    return context.scene.vs.export_list[context.scene.vs.export_list_active]

class BenchMarker:
    def __init__(self,indent = 0, prefix = None):
        self._indent = indent * 4
        self._prefix = "{}{}".format(" " * self._indent,prefix if prefix else "")
        self.quiet = bpy.app.debug_value <= 0
        self.reset()

    def reset(self):
        self._last = self._start = time.time()
        
    def report(self,label = None, threshold = 0.0):
        now = time.time()
        elapsed = now - self._last
        if threshold and elapsed < threshold: return

        if not self.quiet:
            prefix = "{} {}:".format(self._prefix, label if label else "")
            pad = max(0, 10 - len(prefix) + self._indent)
            print("{}{}{:.4f}".format(prefix," " * pad, now - self._last))
        self._last = now

    def current(self):
        return time.time() - self._last
    def total(self):
        return time.time() - self._start

def smdBreak(line):
    line = line.rstrip('\n')
    return line == "end" or line == ""
    
def smdContinue(line):
    return line.startswith("//")

def getDatamodelQuat(blender_quat):
    return datamodel.Quaternion([blender_quat[1], blender_quat[2], blender_quat[3], blender_quat[0]])

def getEngineBranch() -> dmx_version | None:
    if not bpy.context.scene.vs.engine_path: return None
    path = os.path.abspath(bpy.path.abspath(bpy.context.scene.vs.engine_path))

    # Source 2: search for executable name
    engine_path_files = set(name[:-4] if name.endswith(".exe") else name for name in os.listdir(path))
    if "resourcecompiler" in engine_path_files: # Source 2
        for executable,dmx_version in dmx_versions_source2.items():
            if executable in engine_path_files:
                return dmx_version

    # Source 1 SFM special case
    if path.lower().find("sourcefilmmaker") != -1:
        return dmx_versions_source1["Source Filmmaker"] # hack for weird SFM folder structure, add a space too
    
    # Source 1 standard: use parent dir's name
    name = os.path.basename(os.path.dirname(bpy.path.abspath(path))).title().replace("Sdk","SDK")
    return dmx_versions_source1.get(name)

def getCorrectiveShapeSeparator(): return '__' if State.compiler == Compiler.MODELDOC else '_'

vertex_maps = ["valvesource_vertex_paint", "valvesource_vertex_blend", "valvesource_vertex_blend1"]

# Per vertex Source 2 DMX maps
vertex_float_maps = [
    "cloth_enable",
    "cloth_animation_attract",
    "cloth_animation_force_attract",
    "cloth_goal_strength",
    "cloth_goal_strength_v2",
    "cloth_goal_damping",
    "cloth_drag",
    "cloth_drag_v2",
    "cloth_mass",
    "cloth_gravity",
    "cloth_gravity_z",
    "cloth_collision_radius",
    "cloth_ground_collision",
    "cloth_ground_friction",
    "cloth_use_rods",
    "cloth_make_rods",
    "cloth_anchor_free_rotate",
    "cloth_volumetric",
    "cloth_suspenders",
    "cloth_bend_stiffness",
    "cloth_stray_radius_inv",
    "cloth_stray_radius",
    "cloth_stray_radius_stretchiness",
    "cloth_antishrink",
    "cloth_shear_resistance",
    "cloth_stretch",
    "cloth_friction"

    # TODO add way to set up groups manually
    # cloth_collision_layer_%d - 0 through 15
    # cloth_vertex_set_%s - name
]

def findDmxClothVertexGroups(ob):
    groups = []
    for vgroup in ob.vertex_groups:
        if vgroup.name in vertex_float_maps:
            groups.append(vgroup)

        elif vgroup.name.startswith("cloth_collision_layer_"):
            for n in range(16):
                if vgroup.name == f"cloth_collision_layer_{n}":
                    groups.append(vgroup)
                    break

        elif vgroup.name.startswith("cloth_vertex_set_"):
            groups.append(vgroup)

    return groups

def getDmxKeywords(format_version):
    if format_version >= 22:
        return {
          'pos': "position$0", 'norm': "normal$0", 'wrinkle':"wrinkle$0",
          'balance':"balance$0", 'weight':"blendweights$0", 'weight_indices':"blendindices$0"
          }
    else:
        return { 'pos': "positions", 'norm': "normals", 'wrinkle':"wrinkle",
          'balance':"balance", 'weight':"jointWeights", 'weight_indices':"jointIndices" }

def count_exports(context):
    num = 0
    for exportable in context.scene.vs.export_list:
        item = exportable.item
        if item and item.vs.export and (type(item) != bpy.types.Collection or not item.vs.mute):
            num += 1
    return num

def animationLength(ad : bpy.types.AnimData):
    if ad.action:
        if State.useActionSlots:			
            def iter_keyframes(channelbag : bpy.types.ActionChannelbag):
                for fcurve in channelbag.fcurves:
                    for keyframe in fcurve.keyframe_points:
                        yield keyframe

            keyframeTimes = [kf.co.x for kf in iter_keyframes(ad.action.layers[0].strips[0].channelbag(ad.action_slot))]
            
            return ceil(max(keyframeTimes) - min(keyframeTimes))
        else:
            return ceil(ad.action.frame_range[1] - ad.action.frame_range[0])
    elif not State.useActionSlots:
        strips = [strip.frame_end for track in ad.nla_tracks if not track.mute for strip in track.strips]
        if strips:
            return ceil(max(strips))
    
    return 0
    
def getFileExt(flex=False):
    if State.datamodelEncoding != 0 and bpy.context.scene.vs.export_format == 'DMX':
        return ".dmx"
    else:
        if flex: return ".vta"
        else: return ".smd"

def isWild(in_str):
    wcards = [ "*", "?", "[", "]" ]
    for char in wcards:
        if in_str.find(char) != -1: return True

# rounds to 6 decimal places, converts between "1e-5" and "0.000001", outputs str
def getSmdFloat(fval):
    return "{:.6f}".format(float(fval))
def getSmdVec(iterable):
    return " ".join([getSmdFloat(val) for val in iterable])

def appendExt(path,ext):
    if not path.lower().endswith("." + ext) and not path.lower().endswith(".dmx"):
        path += "." + ext
    return path

def printTimeMessage(start_time,name,job,type="SMD"):
    elapsedtime = int(time.time() - start_time)
    if elapsedtime == 1:
        elapsedtime = "1 second"
    elif elapsedtime > 1:
        elapsedtime = str(elapsedtime) + " seconds"
    else:
        elapsedtime = "under 1 second"

    print(type,name,"{}ed in".format(job),elapsedtime,"\n")

def PrintVer(in_seq,sep="."):
        rlist = list(in_seq[:])
        rlist.reverse()
        out = ""
        for val in rlist:
            try:
                if int(val) == 0 and not len(out):
                    continue
            except ValueError:
                continue
            out = "{}{}{}".format(str(val),sep if sep else "",out) # NB last value!
        if out.count(sep) == 1:
            out += "0" # 1.0 instead of 1
        return out.rstrip(sep)

def getUpAxisMat(axis):
    match axis.upper():
        case 'X':
            return Matrix.Rotation(pi/2, 4, 'Y')
        case 'Y':
            return Matrix.Rotation(pi/2, 4, 'X')
        case 'Z':
            return Matrix()
        case _:
            raise AttributeError("getUpAxisMat got invalid axis argument '{}'".format(axis))
    
def getUpAxisOffsetMat(axis, offset):
    """
    Offset position along the up axis direction
    
    Args:
        axis: The up axis ('X', 'Y', or 'Z')
        offset: Float value - positive moves up, negative moves down
    
    Returns:
        Matrix: Translation matrix along the up axis
    """
    match axis.upper():
        case 'X':
            return Matrix.Translation((offset, 0, 0))
        case 'Y':
            return Matrix.Translation((0, offset, 0))
        case 'Z':
            return Matrix.Translation((0, 0, offset))
        case _:
            raise AttributeError("getUpAxisOffsetMat got invalid axis argument '{}'".format(axis))
    
def getForwardAxisMat(axis: str) -> Matrix:
    """Return a rotation matrix that orients an object to face the specified forward direction."""
    match axis.upper():
        case 'X':
            return Matrix.Rotation(-pi / 2, 4, 'Z')
        case 'Y':
            return Matrix.Rotation(pi, 4, 'Z')
        case '-Y':
            return Matrix()
        case 'Z':
            return Matrix.Rotation(-pi / 2, 4, 'X')
        case '-X':
            return Matrix.Rotation(pi / 2, 4, 'Z')
        case '-Z':
            return Matrix.Rotation(pi / 2, 4, 'X')
        case _:
            raise AttributeError(f"getForwardAxisMat got invalid axis argument '{axis}'")

def MakeObjectIcon(object,prefix=None,suffix=None):
    if not (prefix or suffix):
        raise TypeError("A prefix or suffix is required")

    if object.type == 'TEXT':
        type = 'FONT'
    else:
        type = object.type

    out = ""
    if prefix:
        out += prefix
    out += type
    if suffix:
        out += suffix
    return out

def getObExportName(ob):
    return ob.name

def removeObject(obj):
    d = obj.data
    type = obj.type

    if type == "ARMATURE":
        for child in obj.children:
            if child.type == 'EMPTY':
                removeObject(child)

    for collection in obj.users_collection:
        collection.objects.unlink(obj)
    if obj.users == 0:
        if type == 'ARMATURE' and obj.animation_data:
            obj.animation_data.action = None # avoid horrible Blender bug that leads to actions being deleted

        bpy.data.objects.remove(obj)
        if d and d.users == 0:
            if type == 'MESH':
                bpy.data.meshes.remove(d)
            if type == 'ARMATURE':
                bpy.data.armatures.remove(d)

    return None if d else type
    
def select_only(ob):
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='OBJECT')
    if bpy.context.selected_objects:
        bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)

def hasShapes(id, valid_only = True):
    def _test(id_):
        return bool(id_.type in shape_types and id_.data.shape_keys and len(id_.data.shape_keys.key_blocks))
    
    if type(id) == bpy.types.Collection:
        for _ in [ob for ob in id.objects if ob.vs.export and (not valid_only or ob.session_uid in State.exportableObjects) and _test(ob)]:
            return True
        return False
    else:
        return _test(id)

def countShapes(*objects):
    from .core.meshutils import get_flexcontrollers
    
    num_shapes = 0
    num_correctives = 0
    flattened_objects = []

    for ob in objects:
        if isinstance(ob, bpy.types.Collection):
            flattened_objects.extend(ob.objects)
        elif hasattr(ob, '__iter__'):
            flattened_objects.extend(ob)
        else:
            flattened_objects.append(ob)

    for ob in [o for o in flattened_objects if o.vs.export and hasShapes(o)]:
        if ob.vs.flex_controller_mode == 'SPECIFIC':
            flex_controllers = get_flexcontrollers(ob)
            unique_names = set(fc[0] for fc in flex_controllers)
            num_shapes += len(unique_names)
        else:
            if ob.data.shape_keys:
                for shape in ob.data.shape_keys.key_blocks[1:]:
                    if getCorrectiveShapeSeparator() in shape.name:
                        num_correctives += 1
                    else:
                        num_shapes += 1

    return num_shapes, num_correctives

def hasCurves(id):
    def _test(id_):
        return id_.type in ['CURVE','SURFACE','FONT']

    if type(id) == bpy.types.Collection:
        for _ in [ob for ob in id.objects if ob.vs.export and ob.session_uid in State.exportableObjects and _test(ob)]:
            return True
        return False
    else:
        return _test(id)

def valvesource_vertex_maps(id) -> set[str]:
    """Returns all vertex colour maps which are recognised by the Tools."""
    def test(id_):
        if hasattr(id_.data,"vertex_colors"):
            return set(id_.data.vertex_colors.keys()).intersection(vertex_maps)
        else:
            return set()

    if type(id) == bpy.types.Collection:
        return set(itertools.chain(*(test(ob) for ob in id.objects)))
    elif id.type == 'MESH':
        return test(id)
    else:
        return set()

def actionSlotsForFilter(obj : bpy.types.Object):
    assert(State.useActionSlots)
    from fnmatch import fnmatch
    if not obj.animation_data:
        return list()
    return list([slot for slot in obj.animation_data.action_suitable_slots if fnmatch(slot.name_display, obj.vs.action_filter)] if obj.vs.action_filter else obj.animation_data.action_suitable_slots)

def actionsForFilter(filter):
    import fnmatch
    return list([action for action in bpy.data.actions if action.users and fnmatch.fnmatch(action.name, filter)])

def actionSlotExportName(animData : bpy.types.AnimData):
    """For use only when exporting a single action slot"""
    assert(State.useActionSlots)
    slot_name = animData.action_slot.name_display
    return animData.action.name if slot_name in State.legacySlotNames else slot_name

def shouldExportGroup(group):
    return group.vs.export and not group.vs.mute

def hasFlexControllerSource(source):
    return bpy.data.texts.get(source) or os.path.exists(bpy.path.abspath(source))

def channelBagForNewActionSlot(obj : bpy.types.Object, name : str):
    assert(State.useActionSlots)
    ad = obj.animation_data_create()
    if not ad.action:
        ad.action = bpy.data.actions.new(obj.name)
    slot = ad.action.slots.new(id_type='OBJECT', name=name)
    ad.action_slot = slot

    layer = ad.action.layers.new(name) if not ad.action.layers else ad.action.layers[0]
    strip = layer.strips.new(type='KEYFRAME') if not layer.strips else layer.strips[0]
    return typing.cast(bpy.types.ActionChannelbag, strip.channelbag(slot, ensure=True))

def getExportablesForObject(ob):
    # objects can be reallocated between yields, so capture the ID locally
    ob_session_uid = ob.session_uid
    seen = set()

    while len(seen) < len(bpy.context.scene.vs.export_list):
        # Handle the exportables list changing between yields by re-evaluating the whole thing
        for exportable in bpy.context.scene.vs.export_list:
            if not exportable.item:
                continue # Observed only in Blender release builds without a debugger attached

            if exportable.session_uid in seen:
                continue
            seen.add(exportable.session_uid)

            if exportable.ob_type == 'COLLECTION' and not exportable.item.vs.mute and any(collection_item.session_uid == ob_session_uid for collection_item in exportable.item.objects):
                yield exportable
                break

            if exportable.session_uid == ob_session_uid:
                yield exportable
                break

# How to handle the selected object appearing in multiple collections?
# How to handle an armature with animation only appearing within a collection?
def getSelectedExportables():
    seen = set()
    for ob in bpy.context.selected_objects:
        for exportable in getExportablesForObject(ob):
            if not exportable.name in seen:
                seen.add(exportable.name)
                yield exportable

    if len(seen) == 0 and bpy.context.active_object:
        for exportable in getExportablesForObject(bpy.context.active_object):
            yield exportable

def make_export_list(scene : bpy.types.Scene):
    scene.vs.export_list.clear()
    
    def makeDisplayName(item,name=None):
        return os.path.join(item.vs.subdir if item.vs.subdir != "." else "", (name if name else item.name) + getFileExt())
    
    if State.exportableObjects:		
        ungrouped_object_ids = State.exportableObjects.copy()
        
        groups_sorted = bpy.data.collections[:]
        groups_sorted.sort(key=lambda g: g.name.lower())
        
        scene_groups = []
        for group in groups_sorted:
            valid = False
            for obj in [obj for obj in group.objects if obj.session_uid in State.exportableObjects]:
                if not group.vs.mute and obj.type != 'ARMATURE' and obj.session_uid in ungrouped_object_ids:
                    ungrouped_object_ids.remove(obj.session_uid)
                valid = True
            if valid:
                scene_groups.append(group)
                
        for g in scene_groups:
            i = scene.vs.export_list.add()
            if g.vs.mute:
                i.name = "{} {}".format(g.name,pgettext(get_id("exportables_group_mute_suffix",True)))
            else:
                i.name = makeDisplayName(g)
            i.collection = g
            i.ob_type = "COLLECTION"
            i.icon = "GROUP"
        
        ungrouped_objects = list(ob for ob in scene.objects if ob.session_uid in ungrouped_object_ids)
        ungrouped_objects.sort(key=lambda s: s.name.lower())
        for ob in ungrouped_objects:
            if ob.type == 'FONT':
                ob.vs.triangulate = True # preserved if the user converts to mesh
            
            i_name = i_type = i_icon = None
            if ob.type == 'ARMATURE':
                ad = ob.animation_data
                if ad:
                    if State.useActionSlots:
                        i_icon = i_type = "ACTION_SLOT"
                        if ob.data.vs.action_selection != 'CURRENT':
                            export_slots = ob.data.vs.action_selection == 'FILTERED'
                            exportables_count = len(actionSlotsForFilter(ob) if export_slots else actionsForFilter(ob.vs.action_filter))
                            if not export_slots or (ob.vs.action_filter and ob.vs.action_filter != "*"):
                                i_name = get_id("exportables_arm_filter_result",True).format(ob.vs.action_filter,exportables_count)
                            else:
                                i_name = get_id("exportables_arm_no_slot_filter",True).format(exportables_count, ob.name)
                        elif ad.action_slot:
                            i_name = makeDisplayName(ob, actionSlotExportName(ad))
                    else:
                        i_icon = i_type = "ACTION"
                        if ob.data.vs.action_selection == 'FILTERED':
                            i_name = get_id("exportables_arm_filter_result",True).format(ob.vs.action_filter,len(actionsForFilter(ob.vs.action_filter)))
                        elif ad.action:
                            i_name = makeDisplayName(ob,ad.action.name)
                        elif len(ad.nla_tracks):
                            i_name = makeDisplayName(ob)
                            i_icon = "NLA"
            else:
                i_name = makeDisplayName(ob)
                i_icon = MakeObjectIcon(ob,prefix="OUTLINER_OB_")
                i_type = "OBJECT"
            if i_name:
                i = scene.vs.export_list.add()
                i.name = i_name
                i.ob_type = i_type
                i.icon = i_icon
                i.obj = ob

class Logger:
    def __init__(self):
        self.log_warnings = []
        self.log_errors = []
        self.startTime = time.time()

    def warning(self, *string):
        message = " ".join(str(s) for s in string)
        print(" WARNING:",message)
        self.log_warnings.append(message)

    def error(self, *string):
        message = " ".join(str(s) for s in string)
        print(" ERROR:",message)
        self.log_errors.append(message)
    
    def list_errors(self, menu, context):
        l = menu.layout
        if len(self.log_errors):
            for msg in self.log_errors:
                l.label(text="{}: {}".format(pgettext("Error").upper(), msg))
            l.separator()
        if len(self.log_warnings):
            for msg in self.log_warnings:
                l.label(text="{}: {}".format(pgettext("Warning").upper(), msg))

    def elapsed_time(self):
        return round(time.time() - self.startTime, 1)

    def errorReport(self,message):
        if len(self.log_errors) or len(self.log_warnings):
            message += get_id("exporter_report_suffix",True).format(len(self.log_errors),len(self.log_warnings))
            if not bpy.app.background:
                bpy.context.window_manager.popup_menu(self.list_errors,title=get_id("exporter_report_menu"))
            
            print("{} Errors and {} Warnings".format(len(self.log_errors),len(self.log_warnings)))
            for msg in self.log_errors: print("Error:",msg)
            for msg in self.log_warnings: print("Warning:",msg)
        
        self.report({'INFO'},message)
        print(message)

class SmdInfo:
    isDMX = 0 # version number, or 0 for SMD
    a : bpy.types.Object | None = None
    m : bpy.types.Object | None = None
    shapes = None
    g : bpy.types.Collection | None = None # Group being exported
    file : TextIOWrapper
    jobType = None
    startTime = 0.0
    in_block_comment = False
    rotMode = 'EULER' # for creating keyframes during import
    shapeNames : dict | None = None
    
    def __init__(self, jobName : str):
        self.jobName = jobName
        self.upAxis = bpy.context.scene.vs.up_axis
        self.amod = {} # Armature modifiers
        self.materials_used = set() # printed to the console for users' benefit

        # DMX stuff
        self.attachments = []
        self.meshes = []
        self.parent_chain = []
        self.dmxShapes = collections.defaultdict(list)
        self.boneTransformIDs = {}

        self.frameData = []
        self.bakeInfo = []

        # boneIDs contains the ID-to-name mapping of *this* SMD's bones.
        # - Key: integer ID
        # - Value: bone name (storing object itself is not safe)
        self.boneIDs = {}
        self.boneNameToID = {} # for convenience during export
        self.phantomParentIDs = {} # for bones in animation SMDs but not the ref skeleton

class QcInfo:
    startTime = 0
    ref_mesh = None # for VTA import
    a = None
    origin = None
    upAxis = 'Z'
    upAxisMat = None
    numSMDs = 0
    makeCamera = False
    in_block_comment = False
    jobName = ""
    root_filedir = ""
    
    def __init__(self):
        self.imported_smds = []
        self.vars = {}
        self.dir_stack = []

    def cd(self):
        return os.path.join(self.root_filedir,*self.dir_stack)
        
class KeyFrame:
    def __init__(self):
        self.frame = None
        self.pos = self.rot = False
        self.matrix = Matrix()

class SMD_OT_LaunchHLMV(bpy.types.Operator):
    bl_idname = "smd.launch_hlmv"
    bl_label = get_id("launch_hlmv")
    bl_description = get_id("launch_hlmv_tip")

    @classmethod
    def poll(cls,context):
        return bool(context.scene.vs.engine_path)
        
    def execute(self,context) -> set:
        args = [os.path.normpath(os.path.join(bpy.path.abspath(context.scene.vs.engine_path),"hlmv"))]
        if context.scene.vs.game_path:
            args.extend(["-game",os.path.normpath(bpy.path.abspath(context.scene.vs.game_path))])
        subprocess.Popen(args)
        return {'FINISHED'}
    
def enum_shapekey_items(self, context):
    ob = context.object
    if not ob or not ob.data.shape_keys:
        return []
    return [(sk.name, sk.name, "") for sk in ob.data.shape_keys.key_blocks]

def enum_bones(self,context):
    ob = context.object
    if not ob or not ob.data.bones:
        return[]
    return [(bone.name, bone.name, "") for bone in ob.data.bones]

def get_filepath(path: str | None):
    if not path or not isinstance(path, str):
        raise ValueError(f"Invalid path: {path!r}")

    path = path.replace("\\", "/")
    path = path.replace("//..", "//../")

    export_path = bpy.path.abspath(path)
    if not export_path:
        raise ValueError(f"bpy.path.abspath() failed to resolve: {path!r}")

    filename = os.path.basename(export_path)
    root, ext = os.path.splitext(filename)
    return export_path, filename, ext


def get_smd_prefab_enum(self, context):
    prefabs = context.scene.vs.smd_prefabs
    items = []
    for i, p in enumerate(prefabs):
        filepath = str(p.filepath)
        if filepath:
            filepath = bpy.path.abspath(filepath)
        label = os.path.basename(filepath) or f"Prefab {i+1}"
        items.append((str(i), label, ""))
    return items


def parse_hitbox_line(line: str):
    """Parse a $hbox line and return hitbox data dict or None. Returns None for capsule hitboxes."""
    import re
    
    pattern = r'\$hbox\s+(\d+)\s+"([^"]+)"\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?'
    match = re.match(pattern, line.strip())
    
    if not match:
        return None
    
    group = int(match.group(1))
    bone_name = match.group(2)
    min_x, min_y, min_z = float(match.group(3)), float(match.group(4)), float(match.group(5))
    max_x, max_y, max_z = float(match.group(6)), float(match.group(7)), float(match.group(8))
    scale = match.group(9) # capsule htibox is not supported for now. TODO
    
    if scale is not None:
        scale_value = float(scale)
        if scale_value != -1.0:
            return None
    
    return {
        'group': group,
        'bone': bone_name,
        'min': mathutils.Vector((min_x, min_y, min_z)),
        'max': mathutils.Vector((max_x, max_y, max_z))
    }

def import_hitboxes_from_content(content: str, armature : bpy.types.Object, context : bpy.types.Context):
    """
    Import hitboxes from text content containing $hbox lines.
    Returns (created_count, skipped_count, skipped_bones list)
    """
    from .core.boneutils import get_bone_exportname, get_bone_matrix
    
    hitboxes = []
    for line in content.split('\n'):
        if line.strip().startswith('$hbox'):
            parsed = parse_hitbox_line(line)
            if parsed:
                hitboxes.append(parsed)
    
    if not hitboxes:
        return (0, 0, [])
    
    created_count = 0
    skipped_count = 0
    skipped_bones = []
    
    previous_mode = armature.mode
    if previous_mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    
    for hb_data in hitboxes:
        bone_name = hb_data['bone']
        
        bone = None
        for b in armature.data.bones:
            if get_bone_exportname(b) == bone_name:
                bone = b
                break
        
        if not bone:
            skipped_bones.append(bone_name)
            skipped_count += 1
            continue
        
        min_point = hb_data['min']
        max_point = hb_data['max']
        
        center = (min_point + max_point) / 2
        half_extents = (max_point - min_point) / 2
        
        bpy.ops.object.empty_add(type='CUBE', location=(0, 0, 0))
        empty = context.active_object
        empty.name = f"hbox_{bone.name}"
        
        empty.parent = armature
        empty.parent_type = 'BONE'
        empty.parent_bone = bone.name
        
        pose_bone = armature.pose.bones[bone.name]
        
        bone_matrix_no_offset = bone.matrix_local
        bone_matrix_world_no_offset = armature.matrix_world @ bone_matrix_no_offset
        
        bone_matrix_with_offset = get_bone_matrix(pose_bone, rest_space=True)
        offset_only = bone_matrix_no_offset.inverted() @ bone_matrix_with_offset
        
        local_center = offset_only @ center
        world_center = bone_matrix_world_no_offset @ local_center
        
        empty.matrix_world.translation = world_center
        empty.rotation_euler = (0, 0, 0)
        
        avg_scale = (half_extents.x + half_extents.y + half_extents.z) / 3
        empty.empty_display_size = avg_scale
        
        scale_factor = offset_only.to_3x3() @ half_extents
        if avg_scale > 0.0001:
            empty.scale = mathutils.Vector((
                scale_factor.x / avg_scale,
                scale_factor.y / avg_scale,
                scale_factor.z / avg_scale
            ))
        
        empty.vs.smd_hitbox = True
        empty.vs.smd_hitbox_group = str(hb_data['group'])
        
        created_count += 1
    
    if previous_mode != 'OBJECT':
        armature.select_set(True)
        context.view_layer.objects.active = armature
        bpy.ops.object.mode_set(mode=previous_mode)
    
    return (created_count, skipped_count, skipped_bones)