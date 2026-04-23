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

import bpy, struct, time, collections, os, subprocess, sys, builtins, itertools, dataclasses, typing, mathutils, re, math, bmesh
from typing import Optional, Any
from bpy.app.translations import pgettext
from contextlib import contextmanager
from bpy.app.handlers import depsgraph_update_post, load_post, persistent
from mathutils import Matrix, Vector
from math import radians, pi, ceil
from io import TextIOWrapper
from . import datamodel
from . import keyvalues3
import numpy as np

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
modifier_compatible = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'LATTICE'}
shape_types = ('MESH' , 'SURFACE', 'CURVE')
MODE_MAP = {
    "OBJECT": "OBJECT",
    "EDIT_ARMATURE": "EDIT",
    "POSE": "POSE",
    "EDIT_MESH": "EDIT",
    "SCULPT": "SCULPT",
    "VERTEX_PAINT": "VERTEX_PAINT",
    "PAINT_VERTEX": "VERTEX_PAINT",
    "PAINT_WEIGHT": "WEIGHT_PAINT",
    "WEIGHT_PAINT": "WEIGHT_PAINT",
    "PAINT_TEXTURE": "TEXTURE_PAINT",
    "TEXTURE_PAINT": "TEXTURE_PAINT"
}

exportable_types = list((*mesh_compatible, 'ARMATURE'))
exportable_types = tuple(exportable_types)

axes = (('X','X',''),('Y','Y',''),('Z','Z',''))
axes_forward = (('-X','-X',''),('-Y','-Y',''),('-Z','-Z',''),('X','X',''),('Y','Y',''),('Z','Z',''))
axes_lookup = { 'X':0, 'Y':1, 'Z':2 }
axes_lookup_source2 = { 'X':1, 'Y':2, 'Z':3 }

bonename_direction_map = {
    '.L': '.R', '_L': '_R', 'Left': 'Right', '_Left': '_Right', '.Left': '.Right', 'L_': 'R_', 'L.': 'R.', 'L ': 'R ',
    '.R': '.L', '_R': '_L', 'Right': 'Left', '_Right': '_Left', '.Right': '.Left', 'R_': 'L_', 'R.': 'L.', 'R ': 'L '
}

exportname_shortcut_keywords = {
    "vbip": "ValveBiped.Bip01"
}

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

exportname_shortcut_keywords = {
    "vbip": "ValveBiped.Bip01"
}

kitsune_data_keys: list[str] = []

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
        if scene == bpy.context.scene:
            # Export list refresh
            if time.time() - State.last_export_refresh > 0.25:
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

vertex_maps = {
    "valvesource_color":         "Color$0", # ???
    "valvesource_vertex_paint":  "VertexPaintTintColor$0",
    "valvesource_vertex_blend":  "VertexPaintBlendParams$0",
    "valvesource_vertex_blend1": "VertexPaintBlendParams1$0", # ???
}

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
                if channelbag is None:
                    return
                for fcurve in channelbag.fcurves:
                    for keyframe in fcurve.keyframe_points:
                        yield keyframe

            keyframeTimes = [kf.co.x for kf in iter_keyframes(ad.action.layers[0].strips[0].channelbag(ad.action_slot))]
            
            return ceil(max(keyframeTimes) - min(keyframeTimes)) if keyframeTimes else 0
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
            return Matrix.Rotation(-pi/2, 4, 'Y')
        case 'Y':
            return Matrix.Rotation(pi/2, 4, 'X')
        case 'Z':
            return Matrix()
        case _:
            raise AttributeError("getUpAxisMat got invalid axis argument '{}'".format(axis))
    
def getUpAxisOffsetMat(axis, offset):
    match axis.upper():
        case 'X':
            return Matrix.Translation((0, 0, offset))
        case 'Y':
            return Matrix.Translation((0, 0, offset))
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

def get_flexcontrollers(ob: bpy.types.Object) -> list[tuple[str, bool, bool, str, str, str]]:
    """Return list of (shapekey, eyelid, stereo, raw_delta, controller_name, flexgroup) from object,
    only including entries with a valid controller name. Shapekey is optional."""

    if not hasattr(ob, "vs") or not hasattr(ob.vs, "dme_flexcontrollers"):
        return []

    valid_keys = set(ob.data.shape_keys.key_blocks.keys()[1:]) if ob.data.shape_keys else set()

    result = []

    for fc in ob.vs.dme_flexcontrollers:
        controller_name = fc.controller_name.strip() if fc.controller_name and fc.controller_name.strip() else ""

        if not controller_name:
            if not fc.shapekey or fc.shapekey not in valid_keys:
                continue
            controller_name = fc.shapekey

        shapekey = fc.shapekey if fc.shapekey and fc.shapekey in valid_keys else ""

        raw = fc.raw_delta_name.strip() if fc.raw_delta_name and fc.raw_delta_name.strip() else shapekey
        delta_name = sanitize_string_for_delta(raw)

        flexgroup = fc.flexgroup if fc.flexgroup and fc.flexgroup != 'NONE' else ""

        result.append((shapekey, fc.eyelid, fc.stereo, delta_name, controller_name, flexgroup))

    return result

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
        if ob.vs.flex_controller_mode == 'BUILDER':
            flex_controllers = get_flexcontrollers(ob)
            unique_names = set(fc[4] for fc in flex_controllers)
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

def is_mesh_compatible(ob : bpy.types.Object | None) -> bool:
    return bool(ob and hasattr(ob,'type') and ob.type in mesh_compatible)

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

def update_vmdl_container(container_class: str, nodes: list[keyvalues3.KVNode] | keyvalues3.KVNode, export_path: str | None = None,
                          to_clipboard: bool = False) -> keyvalues3.KVDocument | bool:
    """
    Insert or update node(s) into a container inside a KV3 RootNode.
    Folders are overwritten if they exist; other nodes are appended.

    Args:
        container_class: _class of container (e.g., "JiggleBoneList" or "AnimConstraintList"/"ScratchArea").
        nodes: Single KVNode or list of KVNodes to insert.
        export_path: Filepath to load existing KV3 document if not clipboard.
        to_clipboard: If True, uses ScratchArea container instead of a file.

    Returns:
        KVDocument ready for writing or clipboard.
    """

    def open_and_parse_vmdl(filepath: str) -> keyvalues3.KVNode | None:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return None
        
        try:
            parser = keyvalues3.KVParser(text)
            doc = parser.parse()

            root_node = doc.roots.get("rootNode")
            if not root_node or root_node.properties.get("_class") != "RootNode":
                return None
            return root_node

        except Exception:
            return None

    if not isinstance(nodes, list):
        nodes = [nodes]

    root = None
    if to_clipboard:
        root = keyvalues3.KVNode(_class="RootNode")
    else:
        if export_path and os.path.exists(export_path):
            root = open_and_parse_vmdl(export_path)

            if root is None:
                return False
        else:
            root = keyvalues3.KVNode(_class="RootNode")

    container = root.get(_class=container_class)
    if not container:
        container = keyvalues3.KVNode(_class=container_class)
        root.add_child(container)

    for node in nodes:
        node_name = node.properties.get("name")
        if node_name:
            existing = next(
                (c for c in container.children if c.properties.get("name") == node_name and c.properties.get("_class") == node.properties.get("_class")),
                None
            )
            if existing:
                existing.children.clear()
                for child in node.children:
                    existing.add_child(child)
                continue

        container.add_child(node)

    kv_doc = keyvalues3.KVDocument()
    kv_doc.add_root("rootNode", root)
    return kv_doc

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

#   ---------------------------------
#
#   ADDITIONAL FUNCTIONS (IMPORTED DIRECTLY FROM KITSUNETOOLS)
#
#   ---------------------------------


def resolve_kitsuneresource_app(vs) -> str:
    raw      = vs.kitsuneresource_app_path.strip()
    resolved = bpy.path.abspath(raw)
    return resolved if os.path.isfile(resolved) else raw

def resolve_kitsuneresource_project_basedir(vs) -> str:
    blend_dir    = os.path.dirname(bpy.data.filepath)
    project_path = bpy.path.abspath(vs.kitsuneresource_project_path) if vs.kitsuneresource_project_path else ""
    if project_path:
        return os.path.normpath(
            os.path.join(blend_dir, project_path) if not os.path.isabs(project_path) else project_path
        )
    return blend_dir

def build_base_cmd(vs, app_path: str, config_path: str) -> list:
    flags = []
    flags.append('--log')
    
    if vs.kitsuneresource_flag_single_addon: flags.append('--single-addon')
    if vs.kitsuneresource_flag_no_mat_local: flags.append('--no-mat-local')

    if vs.kitsuneresource_flag_game_or_package == 'PACKAGE':
        flags.append('--package-files')
        if vs.kitsuneresource_flag_archive_old:
            flags.append('--archive-old-ver')

    elif vs.kitsuneresource_flag_game_or_package == 'GAME':
        flags.append('--game')

    free_tokens = vs.kitsuneresource_args.split()
    return [app_path] + flags + free_tokens + [config_path]

def run_and_report(operator, cmd: list, basedir: str) -> set:
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=basedir,
        )
    except FileNotFoundError:
        operator.report({'ERROR'}, f"Executable not found: {cmd[0]}")
        return {'CANCELLED'}
    except Exception as e:
        operator.report({'ERROR'}, str(e))
        return {'CANCELLED'}

    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    errors      = []

    for raw_line in process.stdout:  # pyright: ignore
        line = ansi_escape.sub('', raw_line.decode('utf-8', errors='replace')).rstrip()
        print(line)
        if '[ERROR]' in line:
            clean = re.sub(r'^\d{2}:\d{2}:\d{2} \| ', '', line.strip())
            clean = clean.encode('ascii', errors='replace').decode('ascii')
            errors.append(clean)

    process.wait()

    if errors:
        for err in errors:
            operator.report({'WARNING'}, err)
    else:
        operator.report({'INFO'}, "Compile finished")

    return {'FINISHED'}


#
#   CONTEXT MANAGERS
#

_undo_depth = 0

@contextmanager
def _undo_guard():
    global _undo_depth
    ctx = bpy.context

    if _undo_depth == 0:
        _undo_enabled = ctx.preferences.edit.use_global_undo
        ctx.preferences.edit.use_global_undo = False
        # bruh
        was_in_edit = ctx.mode in ('EDIT_MESH', 'EDIT_ARMATURE', 'EDIT_CURVE', 'EDIT_SURFACE', 'EDIT_METABALL', 'EDIT_TEXT', 'EDIT_LATTICE')
        active_obj = ctx.view_layer.objects.active
    else:
        was_in_edit = False
        active_obj = None

    _undo_depth += 1
    try:
        yield
    except Exception:
        _undo_depth = 0
        ctx.preferences.edit.use_global_undo = True
        raise
    finally:
        if _undo_depth > 0:
            _undo_depth -= 1
        if _undo_depth == 0:
            if was_in_edit and active_obj and active_obj.name in bpy.data.objects:
                try:
                    bpy.ops.object.mode_set(mode='OBJECT')
                    bpy.ops.ed.undo_push(message="Kitsune Operation")
                    bpy.ops.object.mode_set(mode='EDIT')
                except RuntimeError:
                    bpy.ops.ed.undo_push(message="Kitsune Operation")
            else:
                bpy.ops.ed.undo_push(message="Kitsune Operation")
            ctx.preferences.edit.use_global_undo = _undo_enabled

@contextmanager
def preserve_context_mode(obj: bpy.types.Object | None = None, mode: str = "EDIT"):
    with _undo_guard():
        ctx = bpy.context
        view_layer = ctx.view_layer
 
        prev_selected = list(view_layer.objects.selected)
        prev_active = view_layer.objects.active
        prev_mode = ctx.mode
        prev_vgroup_index = None
        prev_bone_name = None
        prev_bone_mode = None
        prev_bone_selected = None
 
        target_obj = obj or prev_active
 
        if target_obj:
            if target_obj.type == "MESH":
                prev_vgroup_index = target_obj.vertex_groups.active_index
            elif target_obj.type == "ARMATURE":
                data = target_obj.data
                if prev_mode == "EDIT_ARMATURE" and data.edit_bones.active:
                    prev_bone_name = data.edit_bones.active.name
                    prev_bone_mode = "EDIT"
                    prev_bone_selected = data.edit_bones.active.select
                elif prev_mode == "POSE" and data.bones.active:
                    prev_bone_name = data.bones.active.name
                    prev_bone_mode = "POSE"
                    prev_bone_selected = target_obj.pose.bones[prev_bone_name].bone.select
 
        if target_obj and target_obj.name in bpy.data.objects:
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except RuntimeError:
                pass
 
            view_layer.objects.active = target_obj
            target_obj.select_set(True)
 
            try:
                bpy.ops.object.mode_set(mode=mode)
            except RuntimeError:
                pass
 
        try:
            if mode == "EDIT" and target_obj and target_obj.type == "ARMATURE":
                yield target_obj.data.edit_bones
            elif mode == "POSE" and target_obj and target_obj.type == "ARMATURE":
                yield target_obj.pose.bones
            else:
                yield target_obj
        finally:
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except RuntimeError:
                pass
 
            bpy.ops.object.select_all(action="DESELECT")
            for sel in prev_selected:
                try:
                    if sel and sel.name in bpy.data.objects and sel.name in view_layer.objects:
                        sel.select_set(True)
                except ReferenceError:
                    pass
 
            if prev_active:
                try:
                    if prev_active.name in bpy.data.objects and prev_active.name in view_layer.objects:
                        view_layer.objects.active = prev_active
                except ReferenceError:
                    pass
 
            mapped_mode = MODE_MAP.get(prev_mode, "OBJECT")
            try:
                bpy.ops.object.mode_set(mode=mapped_mode)
            except RuntimeError:
                if prev_active:
                    try:
                        if prev_active.type == "ARMATURE":
                            bpy.ops.object.mode_set(mode="POSE")
                        elif prev_active.type == "MESH":
                            bpy.ops.object.mode_set(mode="OBJECT")
                    except ReferenceError:
                        pass
 
            if prev_active:
                try:
                    if prev_active.type == "MESH" and prev_vgroup_index is not None:
                        if 0 <= prev_vgroup_index < len(prev_active.vertex_groups):
                            prev_active.vertex_groups.active_index = prev_vgroup_index
                    elif prev_active.type == "ARMATURE" and prev_bone_name and prev_bone_mode:
                        data = prev_active.data
                        if mapped_mode == "EDIT" and prev_bone_mode == "EDIT":
                            edit_bone = data.edit_bones.get(prev_bone_name)
                            if edit_bone:
                                data.edit_bones.active = edit_bone
                                edit_bone.select = prev_bone_selected
                        elif mapped_mode == "POSE" and prev_bone_mode == "POSE":
                            bone = data.bones.get(prev_bone_name)
                            if bone:
                                data.bones.active = bone
                                bone.select = prev_bone_selected
                except ReferenceError:
                    pass

#
#   SCENE
#

def unhide_all(layer_col: bpy.types.LayerCollection):
    if layer_col is None:
        return

    layer_col.exclude = False
    layer_col.hide_viewport = False

    col = layer_col.collection
    col.hide_viewport = False
    col.hide_render = False

    for obj in col.objects:
        obj.hide_viewport = False
        obj.hide_render = False
        obj.hide_select = False
        
        if obj.hide_get():
            obj.hide_set(False)

    for child in layer_col.children:
        unhide_all(child)

#
#   VERTEX GROUPS
#

def compute_edgeline_island_weights(id, edgeline_vertexgroup, weight_min=0.3, weight_max=0.8):
    bm = bmesh.new()
    bm.from_mesh(id.data)

    islands = []
    verts_to_visit = set(bm.verts)

    while verts_to_visit:
        start_v = next(iter(verts_to_visit))
        island = [start_v]
        verts_to_visit.remove(start_v)
        stack = [start_v]
        while stack:
            v = stack.pop()
            for edge in v.link_edges:
                other_v = edge.other_vert(v)
                if other_v in verts_to_visit:
                    verts_to_visit.remove(other_v)
                    island.append(other_v)
                    stack.append(other_v)
        islands.append(island)

    if islands:
        island_data = []
        for island_verts in islands:
            island_set = set(island_verts)
            size = sum(f.calc_area() for v in island_verts for f in v.link_faces
                    if all(fv in island_set for fv in f.verts))
            island_data.append((island_verts, size))

        sizes = [d[1] for d in island_data]
        min_s, max_s = min(sizes), max(sizes)
        s_range = max_s - min_s

        for verts, size in island_data:
            weight = weight_max
            if s_range > 0:
                factor = (max_s - size) / s_range
                weight = weight_min + (factor * (weight_max - weight_min))
            for v in verts:
                edgeline_vertexgroup.add([v.index], weight, 'REPLACE')

    bm.free()

def limit_vertexgroup_influence(ob: bpy.types.Object, bone_names: set[str], arm: bpy.types.Object, limit: int = 4):
    """Keep only the top N weights per vertex, respecting bone_sort_order priority."""
    bones_by_name = {b.name: b for b in arm.data.bones if b.name in bone_names}
    to_remove = []

    for v in ob.data.vertices:
        groups = sorted(
            (g for g in v.groups if g.group < len(ob.vertex_groups) and ob.vertex_groups[g.group].name in bone_names),
            key=lambda g: (bones_by_name[ob.vertex_groups[g.group].name].vs.bone_sort_order, -g.weight)
        )

        for g in groups[limit:]:
            to_remove.append((g.group, v.index))

    for group_idx, vertex_idx in to_remove:
        if group_idx < len(ob.vertex_groups):
            ob.vertex_groups[group_idx].remove([vertex_idx])

def normalize_vertexgroup_weights(ob: bpy.types.Object, bone_names: set[str]):
    """Normalize remaining weights so they sum to 1.0 per vertex."""
    for v in ob.data.vertices:
        groups = [
            (ob.vertex_groups[g.group], g.weight)
            for g in v.groups
            if g.group < len(ob.vertex_groups) and ob.vertex_groups[g.group].name in bone_names
        ]

        total = sum(weight for _, weight in groups)
        if total > 0:
            for vg, weight in groups:
                vg.add([v.index], weight / total, 'REPLACE')

def normalize_object_vertexgroups(ob: bpy.types.Object, vgroup_limit: int = 4, clean_tolerance: float = 0.001):
    """Full pipeline: clean, limit, normalize."""
    arm = get_armature(ob)
    if arm is None:
        return
    
    deform_bones = [b for b in arm.data.bones if b.use_deform]
    deform_bone_names = {b.name for b in deform_bones}
    
    limit_vertexgroup_influence(ob, deform_bone_names, arm, limit=vgroup_limit)
    normalize_vertexgroup_weights(ob, deform_bone_names)
    
#
#   IMPORT
#


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

def import_hitboxes_from_content(content: str, armature : bpy.types.Object, context : bpy.types.Context, create_collection: bool = False):
    """
    Import hitboxes from text content containing $hbox lines.
    Returns (created_count, skipped_count, skipped_bones list)
    """
    
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

    hitbox_collection = None
    if create_collection:
        collection_name = f"{armature.name}_hitboxes"
        hitbox_collection = bpy.data.collections.get(collection_name)
        if not hitbox_collection:
            hitbox_collection = bpy.data.collections.new(collection_name)
            if armature.users_collection:
                armature.users_collection[0].children.link(hitbox_collection)
            else:
                context.scene.collection.children.link(hitbox_collection)
    
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
        empty.name = f"{bone.name}_hbox_{armature.name}"
        
        if hitbox_collection:
            for coll in empty.users_collection:
                coll.objects.unlink(empty)
            hitbox_collection.objects.link(empty)

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

def import_jigglebones_from_content(content: str, armature: bpy.types.Object) -> tuple[int, list[str]]:
    """
    Import jigglebones from text content containing $jigglebone definitions.
    Returns (imported_count, missing_bones_list)
    """
    imported_count = 0
    missing_bones = []
    
    # Remove comments to simplify parsing
    content = re.sub(r"//.*", "", content)
        
    bone_map = {get_bone_exportname(b): b for b in armature.data.bones}

    # A simple recursive descent parser for the QC-like key-value format.
    # It handles nested blocks and values.
    def parse_from_tokens(token_stream):
        result = {}
        tokens = list(token_stream)
        i = 0
        while i < len(tokens):
            token = tokens[i]
            
            if token == "}":
                return result

            key = token.lower()
            i += 1

            if i >= len(tokens):
                result[key] = ""
                break
            
            value_token = tokens[i]

            if value_token == "{":
                brace_depth = 1
                j = i + 1
                while j < len(tokens):
                    if tokens[j] == '{': brace_depth += 1
                    elif tokens[j] == '}': brace_depth -= 1
                    if brace_depth == 0: break
                    j += 1
                
                sub_tokens = tokens[i+1:j]
                result[key] = parse_from_tokens(iter(sub_tokens))
                i = j + 1
            else:
                values = [value_token.strip('"')]
                i += 1
                while i < len(tokens):
                    next_token = tokens[i]
                    
                    is_value = False
                    try:
                        float(next_token.strip('"'))
                        is_value = True
                    except ValueError:
                        pass
                    
                    if next_token == "{" or next_token == "}":
                        is_value = False

                    if is_value:
                        values.append(next_token.strip('"'))
                        i += 1
                    else:
                        break
                result[key] = " ".join(values)
        return result

    # Iterate through all matches of `$jigglebone "bone_name"` to find each definition.
    for match in re.finditer(r'\$jigglebone\s+"([^"]+)"', content, re.IGNORECASE):
        current_bone_name = match.group(1)
        
        # Find the start of the block for this jigglebone
        block_start_index = content.find('{', match.end())
        if block_start_index == -1:
            print(f"- Missing '{{' for jigglebone '{current_bone_name}'.")
            continue

        # Manually find the matching closing brace to extract the block content
        brace_depth = 1
        block_end_index = -1
        for i in range(block_start_index + 1, len(content)):
            if content[i] == '{':
                brace_depth += 1
            elif content[i] == '}':
                brace_depth -= 1
            
            if brace_depth == 0:
                block_end_index = i
                break
        
        if block_end_index == -1:
            print(f"QC: Unmatched '{{' for jigglebone '{current_bone_name}'.")
            continue

        block_content = content[block_start_index + 1 : block_end_index]
        
        # Tokenize and parse the extracted block
        tokens = iter(re.findall(r'"[^"]+"|\S+', block_content))
        current_jigglebone_data = parse_from_tokens(tokens)

        if not current_bone_name or not current_jigglebone_data:
            continue

        blender_bone = bone_map.get(current_bone_name)
        if not blender_bone:
            print(f"- No matching Blender bone found for '{current_bone_name}'.")
            missing_bones.append(current_bone_name)
            continue

        vs_bone = blender_bone.vs
        vs_bone.bone_is_jigglebone = True
        imported_count += 1
        
        # Apply parsed properties
        if 'is_flexible' in current_jigglebone_data:
            vs_bone.jiggle_flex_type = 'FLEXIBLE'
            flex_data = current_jigglebone_data['is_flexible']
            if isinstance(flex_data, dict):
                vs_bone.jiggle_length = float(flex_data.get('length', 0.0))
                vs_bone.jiggle_tip_mass = float(flex_data.get('tip_mass', 0.0))
                vs_bone.jiggle_yaw_stiffness = float(flex_data.get('yaw_stiffness', 0.0))
                vs_bone.jiggle_yaw_damping = float(flex_data.get('yaw_damping', 0.0))
                
                if 'yaw_constraint' in flex_data:
                    vs_bone.jiggle_has_yaw_constraint = True
                    yc_vals = [float(x) for x in flex_data['yaw_constraint'].split()]
                    vs_bone.jiggle_yaw_constraint_min = abs(math.radians(yc_vals[0]))
                    vs_bone.jiggle_yaw_constraint_max = abs(math.radians(yc_vals[1]))
                if 'yaw_friction' in flex_data:
                    vs_bone.jiggle_yaw_friction = float(flex_data['yaw_friction'])

                vs_bone.jiggle_pitch_stiffness = float(flex_data.get('pitch_stiffness', 0.0))
                vs_bone.jiggle_pitch_damping = float(flex_data.get('pitch_damping', 0.0))

                if 'pitch_constraint' in flex_data:
                    vs_bone.jiggle_has_pitch_constraint = True
                    pc_vals = [float(x) for x in flex_data['pitch_constraint'].split()]
                    vs_bone.jiggle_pitch_constraint_min = abs(math.radians(pc_vals[0]))
                    vs_bone.jiggle_pitch_constraint_max = abs(math.radians(pc_vals[1]))
                if 'pitch_friction' in flex_data:
                    vs_bone.jiggle_pitch_friction = float(flex_data['pitch_friction'])
                
                vs_bone.jiggle_allow_length_flex = 'allow_length_flex' in flex_data
                if vs_bone.jiggle_allow_length_flex and isinstance(flex_data['allow_length_flex'], dict):
                    along_data = flex_data['allow_length_flex']
                    vs_bone.jiggle_along_stiffness = float(along_data.get('along_stiffness', 0.0))
                    vs_bone.jiggle_along_damping = float(along_data.get('along_damping', 0.0))
                
                if 'angle_constraint' in flex_data:
                    vs_bone.jiggle_has_angle_constraint = True
                    vs_bone.jiggle_angle_constraint = math.radians(float(flex_data['angle_constraint']))

        elif 'is_rigid' in current_jigglebone_data:
            vs_bone.jiggle_flex_type = 'RIGID'
            rigid_data = current_jigglebone_data['is_rigid']
            if isinstance(rigid_data, dict):
                vs_bone.jiggle_length = float(rigid_data.get('length', 0.0))
                vs_bone.jiggle_tip_mass = float(rigid_data.get('tip_mass', 0.0))
        else:
            vs_bone.jiggle_flex_type = 'NONE'

        if 'has_base_spring' in current_jigglebone_data:
            vs_bone.jiggle_base_type = 'BASESPRING'
            base_data = current_jigglebone_data['has_base_spring']
            if isinstance(base_data, dict):
                vs_bone.jiggle_base_stiffness = float(base_data.get('stiffness', 0.0))
                vs_bone.jiggle_base_damping = float(base_data.get('damping', 0.0))
                vs_bone.jiggle_base_mass = int(float(base_data.get('base_mass', 0)))
                
                if 'left_constraint' in base_data:
                    vs_bone.jiggle_has_left_constraint = True
                    lc_vals = [float(x) for x in base_data['left_constraint'].split()]
                    vs_bone.jiggle_left_constraint_min = abs(lc_vals[0])
                    vs_bone.jiggle_left_constraint_max = abs(lc_vals[1])
                if 'left_friction' in base_data:
                    vs_bone.jiggle_left_friction = float(base_data['left_friction'])
                
                if 'up_constraint' in base_data:
                    vs_bone.jiggle_has_up_constraint = True
                    uc_vals = [float(x) for x in base_data['up_constraint'].split()]
                    vs_bone.jiggle_up_constraint_min = abs(uc_vals[0])
                    vs_bone.jiggle_up_constraint_max = abs(uc_vals[1])
                if 'up_friction' in base_data:
                    vs_bone.jiggle_up_friction = float(base_data['up_friction'])
                
                if 'forward_constraint' in base_data:
                    vs_bone.jiggle_has_forward_constraint = True
                    fc_vals = [float(x) for x in base_data['forward_constraint'].split()]
                    vs_bone.jiggle_forward_constraint_min = abs(fc_vals[0])
                    vs_bone.jiggle_forward_constraint_max = abs(fc_vals[1])
                if 'forward_friction' in base_data:
                    vs_bone.jiggle_forward_friction = float(base_data['forward_friction'])

        elif 'is_boing' in current_jigglebone_data:
            vs_bone.jiggle_base_type = 'BOING'
            boing_data = current_jigglebone_data['is_boing']
            if isinstance(boing_data, dict):
                vs_bone.jiggle_impact_speed = int(float(boing_data.get('impact_speed', 0)))
                vs_bone.jiggle_impact_angle = math.radians(float(boing_data.get('impact_angle', 0.0)))
                vs_bone.jiggle_damping_rate = float(boing_data.get('damping_rate', 0.0))
                vs_bone.jiggle_frequency = float(boing_data.get('frequency', 0.0))
                vs_bone.jiggle_amplitude = float(boing_data.get('amplitude', 0.0))
        else:
            vs_bone.jiggle_base_type = 'NONE'

        if 'length' in current_jigglebone_data and vs_bone.jiggle_flex_type == 'NONE':
            vs_bone.jiggle_length = float(current_jigglebone_data['length'])
        
        if vs_bone.jiggle_length > 0:
            vs_bone.use_bone_length_for_jigglebone_length = False
    
    return imported_count, missing_bones

def import_jigglebones_from_kv3(kv_doc, armature: 'bpy.types.Object') -> tuple[int, list[str]]:
    import math

    imported_count = 0
    missing_bones = []

    bone_map = {get_bone_exportname(b): b for b in armature.data.bones}

    def find_jigglebone_nodes(node):
        found = []
        if isinstance(node, keyvalues3.KVNode):
            if node.properties.get('_class') == "JiggleBone":
                found.append(node)
            for child in node.children:
                found.extend(find_jigglebone_nodes(child))
        elif isinstance(node, dict):
            for value in node.values():
                found.extend(find_jigglebone_nodes(value))
        elif isinstance(node, (list, tuple)):
            for item in node:
                found.extend(find_jigglebone_nodes(item))
        return found

    jigglebone_nodes = []
    for root_node in kv_doc.roots.values():
        jigglebone_nodes.extend(find_jigglebone_nodes(root_node))

    if not jigglebone_nodes:
        return 0, []

    for jb_node in jigglebone_nodes:
        props = jb_node.properties

        current_bone_name = props.get('jiggle_root_bone')
        if not current_bone_name:
            continue

        blender_bone = bone_map.get(current_bone_name)
        if not blender_bone:
            missing_bones.append(current_bone_name)
            continue

        vs_bone = blender_bone.vs
        vs_bone.bone_is_jigglebone = True
        imported_count += 1

        jiggle_type_int = props.get('jiggle_type')
        if jiggle_type_int == 0:
            vs_bone.jiggle_flex_type = 'RIGID'
        elif jiggle_type_int == 1:
            vs_bone.jiggle_flex_type = 'FLEXIBLE'
        else:
            vs_bone.jiggle_flex_type = 'NONE'

        vs_bone.jiggle_has_yaw_constraint = props.get('has_yaw_constraint', False)
        vs_bone.jiggle_has_pitch_constraint = props.get('has_pitch_constraint', False)
        vs_bone.jiggle_has_angle_constraint = props.get('has_angle_constraint', False)
        vs_bone.jiggle_has_base_spring = props.get('has_base_spring', False)
        vs_bone.jiggle_allow_length_flex = props.get('allow_flex_length', False)
        vs_bone.jiggle_base_type = 'BASESPRING' if vs_bone.jiggle_has_base_spring else 'NONE'

        vs_bone.jiggle_length = float(props.get('length', 0.0))
        vs_bone.jiggle_tip_mass = float(props.get('tip_mass', 0.0))
        vs_bone.use_bone_length_for_jigglebone_length = vs_bone.jiggle_length == 0.0

        vs_bone.jiggle_angle_constraint = math.radians(float(props.get('angle_limit', 0.0)))
        vs_bone.jiggle_yaw_constraint_min = math.radians(float(props.get('min_yaw', 0.0)))
        vs_bone.jiggle_yaw_constraint_max = math.radians(float(props.get('max_yaw', 0.0)))
        vs_bone.jiggle_yaw_friction = float(props.get('yaw_friction', 0.0))
        vs_bone.jiggle_pitch_constraint_min = math.radians(float(props.get('min_pitch', 0.0)))
        vs_bone.jiggle_pitch_constraint_max = math.radians(float(props.get('max_pitch', 0.0)))
        vs_bone.jiggle_pitch_friction = float(props.get('pitch_friction', 0.0))

        vs_bone.jiggle_base_mass = int(float(props.get('base_mass', 0)))
        vs_bone.jiggle_base_stiffness = float(props.get('base_stiffness', 0.0))
        vs_bone.jiggle_base_damping = float(props.get('base_damping', 0.0))

        vs_bone.jiggle_left_constraint_min = float(props.get('base_left_min', 0.0))
        vs_bone.jiggle_left_constraint_max = float(props.get('base_left_max', 0.0))
        vs_bone.jiggle_left_friction = float(props.get('base_left_friction', 0.0))
        vs_bone.jiggle_up_constraint_min = float(props.get('base_up_min', 0.0))
        vs_bone.jiggle_up_constraint_max = float(props.get('base_up_max', 0.0))
        vs_bone.jiggle_up_friction = float(props.get('base_up_friction', 0.0))
        vs_bone.jiggle_forward_constraint_min = float(props.get('base_forward_min', 0.0))
        vs_bone.jiggle_forward_constraint_max = float(props.get('base_forward_max', 0.0))
        vs_bone.jiggle_forward_friction = float(props.get('base_forward_friction', 0.0))

        vs_bone.jiggle_yaw_stiffness = float(props.get('yaw_stiffness', 0.0))
        vs_bone.jiggle_yaw_damping = float(props.get('yaw_damping', 0.0))
        vs_bone.jiggle_pitch_stiffness = float(props.get('pitch_stiffness', 0.0))
        vs_bone.jiggle_pitch_damping = float(props.get('pitch_damping', 0.0))
        vs_bone.jiggle_along_stiffness = float(props.get('along_stiffness', 0.0))
        vs_bone.jiggle_along_damping = float(props.get('along_damping', 0.0))

    return imported_count, missing_bones


#
#   GET
#

def get_hitboxes(ob : bpy.types.Object | None) -> list[bpy.types.Object | None]:
    
    armature : bpy.types.Object | None = None
    if ob is None:
        armature = get_armature()
    else:
        armature = get_armature(ob)
        
    if armature is None: return []
    
    hitboxes = []
    for ob in bpy.data.objects:
        if not ob.type == 'EMPTY': continue
        if ob.empty_display_type != 'CUBE' or not ob.vs.smd_hitbox: continue
        if ob.parent is not armature or ob.parent_type != 'BONE' or not ob.parent_bone.strip(): continue
        
        hitboxes.append(ob)
        
    return hitboxes

def get_jigglebones(ob : bpy.types.Object | None) -> list[bpy.types.Bone | None]:
    armature = None
    if ob is None:
        armature = get_armature()
    else:
        armature = get_armature(ob)
        
    if armature is None: return []
    
    return [b for b in armature.data.bones if b.vs.bone_is_jigglebone]

def get_attachments(ob : bpy.types.Object | None) -> list[bpy.types.Object | None]:
    armature = None
    if ob is None:
        armature = get_armature()
    else:
        if ob.type == 'ARMATURE':
            armature = ob
        else:
            armature = get_armature(ob)
        
    if armature is None: return []
    
    attchs = []
    for ob in bpy.data.objects:
        if ob.type != 'EMPTY' or ob.parent is None or ob.parent != armature: continue
        if ob.parent_type != 'BONE' or not ob.parent_bone.strip(): continue
        if not ob.vs.dmx_attachment: continue
        
        attchs.append(ob)
        
    return attchs

def get_armature(ob: bpy.types.Object | bpy.types.Bone | bpy.types.EditBone | bpy.types.PoseBone | None = None) -> bpy.types.Object | None:
    if isinstance(ob, bpy.types.Object):
        if ob.type == 'ARMATURE':
            return ob
        
        arm = ob.find_armature()
        if arm:
            return arm
        
        parent = ob.parent
        while parent:
            if parent.type == 'ARMATURE':
                return parent
            parent = parent.parent
        
        return None

    elif isinstance(ob, bpy.types.Bone):
        for o in bpy.data.objects:
            if o.type == 'ARMATURE' and o.data.bones.get(ob.name) == ob:
                return o

    elif isinstance(ob, bpy.types.EditBone):
        for o in bpy.data.objects:
            if o.type == 'ARMATURE' and o.data.edit_bones.get(ob.name) == ob:
                return o

    elif isinstance(ob, bpy.types.PoseBone):
        for o in bpy.data.objects:
            if o.type == 'ARMATURE' and o.pose.bones.get(ob.name) == ob:
                return o

    else:
        ctx_obj = bpy.context.active_object
        if ctx_obj:
            return get_armature(ctx_obj)
        return None

def get_selected_bones(armature : bpy.types.Object | None,
                     bone_type : str = 'BONE',
                     sort_type : str | None = 'TO_LAST',
                     exclude_active : bool = False,
                     select_all : bool = False) -> list[bpy.types.Bone | bpy.types.PoseBone | bpy.types.EditBone | None]:
    """
    Returns bones from an armature with optional selection, visibility, and sorting filters.

    Args:
        armature (bpy.types.Object): Target armature object (must be type 'ARMATURE').
        bone_type (str, optional): Type of bones to return: 'BONE', 'EDITBONE', or 'POSEBONE'. 
                                   If invalid, it is inferred from the current mode.
        sort_type (str, optional): Sorting order: 'TO_LAST' (default), 'TO_FIRST', or no sorting.
        exclude_active (bool, optional): If True, exclude the active bone from the result.
        select_all (bool, optional): If True, ignore selection and visibility filters.

    Returns:
        list[bpy.types.Bone | bpy.types.EditBone | bpy.types.PoseBone]:
            A list of bone objects based on the filters applied.

    Notes:
        - Selection is checked in OBJECT mode.
        - If any bone collections are soloed, only those bones are returned.
        - If none are soloed, only bones from visible collections are included.
    """
    if not is_armature(armature): return []
    
    if bone_type not in ['BONE', 'EDITBONE', 'POSEBONE']:
        if armature.mode == 'EDIT': bone_type = 'EDITBONE'
        elif armature.mode == 'POSE': bone_type = 'POSEBONE'
        else: bone_type = 'BONE'
        
    if sort_type is None: sort_type = ''
    
    # we can evaluate the selected bones through object mode
    with preserve_context_mode(armature, 'OBJECT'): 
        selectedBones = []
        
        armatureBones = armature.data.bones
        armatureBoneCollections = armature.data.collections_all
        
        solo_BoneCollections = [col for col in armatureBoneCollections if col.is_solo]
        
        if exclude_active and armature.data.bones.active is not None:
            active_name = armature.data.bones.active.name
            armatureBones = [b for b in armatureBones if b.name != active_name]
            
        if sort_type in ['TO_LAST', 'TO_FIRST']:
            armatureBones = sort_bone_by_hierarchy(armatureBones)
            
            if sort_type == 'TO_FIRST':
                armatureBones.reverse()
        
        for bone in armatureBones:
            if not select_all:
                if bone.hide_select or not bone.select:
                    continue
                    
                if armatureBoneCollections and bone.collections:
                    boneCollections = bone.collections
                    # If there are solo collections, skip bones not in any of them
                    if solo_BoneCollections:
                        if not any(col in solo_BoneCollections for col in boneCollections):
                            continue
                    else:
                        # If no solo mode, skip bones in hidden collections
                        if not any(col.is_visible for col in boneCollections):
                            continue

            selectedBones.append(bone.name)
    
    if bone_type == 'POSEBONE': return [armature.pose.bones.get(b) for b in selectedBones]
    if bone_type == 'EDITBONE': return [armature.data.edit_bones.get(b) for b in selectedBones]
    else: return [armature.data.bones.get(b) for b in selectedBones]

def get_collection_parent(ob, scene) -> bpy.types.Collection | None:
    for collection in scene.collection.children_recursive:
        if ob.name in collection.objects:
            return collection
    
    if ob.name in scene.collection.objects:
        return None
    
    return None

def get_valid_vertexanimation_object(ob : bpy.types.Object | None) -> bpy.types.Object | bpy.types.Collection | None:
    if not is_mesh_compatible(ob): return None
    
    collection = get_collection_parent(ob, bpy.context.scene)
    if collection is None or collection.vs.mute: return ob
    else: return collection

#
#   DATA
#

def sanitize_string(data: typing.Union[str, list], allow_unicode: bool = False) -> typing.Union[str, list]:
    if isinstance(data, list):
        return [sanitize_string(item, allow_unicode) for item in data]

    _data = data.strip()

    if State.compiler == Compiler.MODELDOC and not allow_unicode:
        _data = re.sub(r'[^a-zA-Z0-9_]+', '_', _data)
    else:
        _data = re.sub(r'[^\w.]+', '_', _data, flags=re.UNICODE)

    _data = re.sub(r'_+', '_', _data)
    _data = _data.strip('_')

    if not _data:
        return 'unnamed'

    return _data

def sanitize_string_for_delta(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9]', '', name)

def sort_bone_by_hierarchy(bones: typing.Iterable[bpy.types.Bone]) -> list[bpy.types.Bone]:
    bone_set = set(bones)
    sorted_bones = []
    visited = set()
    
    def dfs(bone):
        if bone in visited or bone not in bone_set:
            return
        visited.add(bone)
        sorted_bones.append(bone)
        
        for child in sorted(bone.children, key=lambda b: b.name):
            if child in bone_set:
                dfs(child)
    
    roots = [b for b in bone_set if b.parent is None or b.parent not in bone_set]
    
    for root in sorted(roots, key=lambda b: b.name):
        dfs(root)
    
    return sorted_bones

def get_bone_exportname(bone: bpy.types.Bone | bpy.types.PoseBone | None, for_write = False) -> str:
    """Generate the export name for a bone or posebone, respecting custom naming rules."""
    
    if bone is None: 
        return "None"
    elif not isinstance(bone, (bpy.types.Bone, bpy.types.PoseBone)):
        return bone.name if hasattr(bone, "name") else str(bone)

    data_bone = bone.bone if isinstance(bone, bpy.types.PoseBone) else bone
    armature = get_armature(data_bone)
    
    if armature is None: 
        return bone.name
    
    arm_prop = armature.data.vs
    
    if arm_prop.ignore_bone_exportnames and not for_write:
        return bone.name

    def get_bone_side(b: bpy.types.Bone) -> str:
        bone_x = b.matrix_local.to_translation().x
        return (arm_prop.bone_direction_naming_right if bone_x < 0 
                else arm_prop.bone_direction_naming_left)

    ordered_bones = sort_bone_by_hierarchy(armature.data.bones)
    name_count = collections.defaultdict(lambda: arm_prop.bone_name_startcount)
    export_names = {}

    for b in ordered_bones:
        b_side = get_bone_side(b)
        raw_name = b.vs.export_name.strip() or b.name
        raw_name = raw_name.replace("*", b_side)

        shortcut_pattern = re.compile(r"!(\w+)")
        raw_name = shortcut_pattern.sub(
            lambda match: exportname_shortcut_keywords.get(match.group(1), match.group(0)),
            raw_name
        )

        if "$" in raw_name:
            key = (raw_name, b_side)
            final_name = raw_name.replace("$", str(name_count[key])).strip()
            name_count[key] += 1
        else:
            final_name = raw_name

        final_name = sanitize_string(final_name)
        export_names[b.name] = final_name

    return export_names[data_bone.name]

def get_canonical_bonename(export_name: str) -> str:
    """Convert an exported bone name back to its canonical form:
       - Replaces directional markers with ' * '
       - Converts expanded shortcut names back to '!shortcut!' form
       - Converts underscores to spaces
       - Collapses multiple spaces into a single space
    """
    # Reverse shortcut expansion
    reversed_shortcuts = {v: k for k, v in exportname_shortcut_keywords.items()}
    for full, shortcut in reversed_shortcuts.items():
        export_name = export_name.replace(full, f"!{shortcut}!")

    for k, v in bonename_direction_map.items():
        export_name = export_name.replace(k, " * ")


    export_name = export_name.replace("_", " ")
    export_name = re.sub(r'\s+', ' ', export_name).strip()

    return export_name

def get_bone_matrix(data: bpy.types.PoseBone | mathutils.Matrix, bone: bpy.types.PoseBone | None = None,
                    rest_space : bool = False) -> mathutils.Matrix:
    """
    Returns the effective matrix of a PoseBone or matrix with applied export offsets.

    Args:
        data: PoseBone or a 4x4 Matrix.
        bone: Optional PoseBone reference (required for offset properties).
              If not provided and `data` is a PoseBone, it's automatically used.

    Returns:
        Matrix: The final transform matrix with translation and rotation offsets applied.
    """
    # Resolve matrix and bone
    if isinstance(data, bpy.types.PoseBone):
        matrix = data.matrix if not rest_space else data.bone.matrix_local
        bone = data
    elif isinstance(data, mathutils.Matrix):
        matrix = data

    if bone is None:
        return matrix

    b_props = bone.bone.vs

    # Rotation offsets
    rot_x = 0.0 if b_props.ignore_rotation_offset else b_props.export_rotation_offset_x
    rot_y = 0.0 if b_props.ignore_rotation_offset else b_props.export_rotation_offset_y
    rot_z = 0.0 if b_props.ignore_rotation_offset else b_props.export_rotation_offset_z

    rot_offset_matrix = (
        mathutils.Matrix.Rotation(rot_z, 4, 'Z') @ # type: ignore
        mathutils.Matrix.Rotation(rot_y, 4, 'Y') @ # type: ignore
        mathutils.Matrix.Rotation(rot_x, 4, 'X')  # type: ignore
    )

    # Location offsets
    loc_x = 0.0 if b_props.ignore_location_offset else b_props.export_location_offset_x
    loc_y = 0.0 if b_props.ignore_location_offset else b_props.export_location_offset_y
    loc_z = 0.0 if b_props.ignore_location_offset else b_props.export_location_offset_z

    loc_offset_matrix = mathutils.Matrix.Translation((loc_x, loc_y, loc_z))

    # Translation after rotation
    offset_matrix = loc_offset_matrix @ rot_offset_matrix

    # Apply offsets in bone space
    return matrix @ offset_matrix

def get_relative_target_matrix( slave: bpy.types.PoseBone, master: bpy.types.PoseBone | None = None, axis: str = 'XYZ',
                               mode: str = 'ROTATION', is_string: bool = False, rest_space : bool = True) -> typing.Union[list[float], str]:
    """
    Returns relative translation or rotation of `slave` to `master`.

    Args:
        slave: PoseBone - the bone to measure.
        master: PoseBone - optional reference bone. If None, uses armature space.
        axis: str - which axes to include (default: 'XYZ').
        mode: str - 'LOCATION' or 'ROTATION'.
        is_string: bool - if True, returns space-separated string.

    Returns:
        list[float] or str: relative location or rotation
    """
    try:
        # Get the matrices (pose space)
        slave_matrix = get_bone_matrix(slave, rest_space=rest_space)
        master_matrix = get_bone_matrix(master, rest_space=rest_space) if master else mathutils.Matrix.Identity(4)

        # Compute relative matrix: master → slave
        local_offset = master_matrix.inverted_safe() @ slave_matrix

        # Convert to rotation or location
        if mode.upper() == 'ROTATION':
            euler = local_offset.to_euler()
            values = [
                math.degrees(euler.x),
                math.degrees(euler.y),
                math.degrees(euler.z)
            ]
        elif mode.upper() == 'LOCATION':
            translation = local_offset.to_translation()
            values = [translation.x, translation.y, translation.z]
        else:
            raise ValueError("mode must be 'LOCATION' or 'ROTATION'")

        # Filter only selected axes
        axis_map = {'X': values[0], 'Y': values[1], 'Z': values[2]}
        result = [axis_map[a] for a in axis if a in axis_map]

        return " ".join(f"{v:.6f}" for v in result) if is_string else result

    except Exception:
        return "0.0 0.0 0.0" if is_string else [0.0, 0.0, 0.0]


#
#   BOOL
#

def is_mesh(ob : bpy.types.Object | None) -> bool:
    return ob is not None and ob.type == 'MESH'

def is_armature(ob : bpy.types.Object | None) -> bool:
    return ob is not None and ob.type == 'ARMATURE'

def is_empty(ob : bpy.types.Object | None) -> bool:
    return ob is not None and ob.type == 'EMPTY'

def is_curve(ob : bpy.types.Object | None) -> bool:
    return ob is not None and ob.type == 'CURVE'
     
#
#   OBJECT MODIFIERS
#

def op_override(operator, context_override: dict[str, Any], context: Optional[bpy.types.Context] = None,
                execution_context: Optional[str] = None, undo: Optional[bool] = None, **operator_args) -> set[str]:
    """Call a Blender operator with a context override."""
    args = []
    if execution_context is not None:
        args.append(execution_context)
    if undo is not None:
        args.append(undo)

    if context is None:
        context = bpy.context
    with context.temp_override(**context_override):
        return operator(*args, **operator_args)

def apply_modifier(mod: bpy.types.Modifier, strict: bool = False, silent=False):
    ob: bpy.types.Object | None = mod.id_data
    if ob is None or ob.type != 'MESH':
        return False
    
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)

    name = mod.name
    m_type = mod.type

    # Strict mode: deny applying if shapekeys exist
    if strict and ob.data.shape_keys:
        if not silent: 
            print(f"- Skipping {name} ({m_type}) on {ob.name}: object has shapekeys (strict mode).")
        return False

    if not strict and ob.data.shape_keys:
        if not silent: 
            print(f"- Applying modifier {name} ({m_type}) with shapekeys on {ob.name}")

        # Backup shapekeys
        shape_keys = {sk.name: [v.co.copy() for v in sk.data] 
                      for sk in ob.data.shape_keys.key_blocks}

        # Remove all shapekeys but preserve final shape
        context_override = {'object': ob, 'active_object': ob}
        op_override(bpy.ops.object.shape_key_remove, context_override, all=True, apply_mix=True)

        while ob.modifiers[0] != mod:
            bpy.ops.object.modifier_move_up(modifier=mod.name)
        bpy.ops.object.modifier_apply(modifier=mod.name)

        # Restore shapekeys only if vertex count unchanged
        if all(len(coords) == len(ob.data.vertices) for coords in shape_keys.values()):
            for sk_name, coords in shape_keys.items():
                new_sk = ob.shape_key_add(name=sk_name, from_mix=False)
                for i, coord in enumerate(coords):
                    new_sk.data[i].co = coord
            if not silent: 
                print(f"- Successfully applied {name} ({m_type}) with shapekeys preserved.")
        else:
            if not silent: 
                print(f"- Modifier {name} changed topology, shapekeys could not be restored.")

        return True

    # No shapekeys — apply normally
    while ob.modifiers[0] != mod:
        bpy.ops.object.modifier_move_up(modifier=mod.name)
    bpy.ops.object.modifier_apply(modifier=mod.name)

    if name not in ob.modifiers:
        if not silent: 
            print(f"- Pre-Applied Modifier {name} ({m_type}) for Object '{ob.name}'")
        return True
    else:
        if not silent: 
            print(f"- Failed to apply {name} ({m_type}) for Object '{ob.name}'")
        return False