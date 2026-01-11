import bpy, typing, re, os, mathutils
from typing import List
from bpy.types import UILayout

from contextlib import contextmanager
from ..keyvalue3 import *
from ..utils import mesh_compatible

MODE_MAP: dict[str, str] = {
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
    "TEXTURE_PAINT": "TEXTURE_PAINT",
}

def unselect_all() -> None:
    for ob in bpy.data.objects:
        if ob.select_get():
            ob.select_set(False)

def hide_objects(ob : bpy.types.Object | None, val=True) -> None:
    if hasattr(ob, 'hide_set'):
        ob.hide_set(val)
    elif hasattr(ob, 'hide'):
        ob.hide = val

@contextmanager
def unhide_all_objects():
    """
    Temporarily unhide all objects and collections in the view layer.
    Restores original visibility afterwards.

    Notes:
        - Only restores objects/collections that were hidden before.
        - Deleted objects/collections are skipped safely.
    """
    view_layer = bpy.context.view_layer
    root_layer_coll = view_layer.layer_collection

    original_visibility = {}
    original_obj_visibility = {}

    def store_layer_collection_visibility(layer_coll, vis):
        vis[layer_coll] = {
            "exclude": layer_coll.exclude,
            "hide_viewport": layer_coll.hide_viewport,
        }
        for child in layer_coll.children:
            store_layer_collection_visibility(child, vis)

    def restore_layer_collection_visibility(vis):
        for layer_coll, state in vis.items():
            if layer_coll:
                layer_coll.exclude = state["exclude"]
                layer_coll.hide_viewport = state["hide_viewport"]

    def unhide_all_layer_collections(layer_coll):
        layer_coll.exclude = False
        layer_coll.hide_viewport = False
        for child in layer_coll.children:
            unhide_all_layer_collections(child)

    # --- Save + unhide ---
    store_layer_collection_visibility(root_layer_coll, original_visibility)

    for obj in bpy.data.objects:
        original_obj_visibility[obj.name] = {
            "hide": obj.hide_get(),
            "hide_viewport": obj.hide_viewport,
        }
        obj.hide_set(False)
        obj.hide_viewport = False

    unhide_all_layer_collections(root_layer_coll)

    try:
        yield
    finally:
        # --- Restore ---
        restore_layer_collection_visibility(original_visibility)
        for name, state in original_obj_visibility.items():
            if name not in bpy.data.objects:
                continue
            obj = bpy.data.objects[name]
            obj.hide_set(state["hide"])
            obj.hide_viewport = state["hide_viewport"]

def sanitize_string(data: str):
    
    if isinstance(data, list):
        return [sanitize_string(item) for item in data]
    
    _data = data.strip()
    _data = re.sub(r'[^\w.]+', '_', _data, flags=re.UNICODE)
    _data = re.sub(r'_+', '_', _data)
    _data = _data.strip('_')
    
    if not _data:
        return 'unnamed'
    
    return _data

def is_valid_string(name: str) -> bool:
    if not name or not name.strip():
        return False
    
    name = name.strip()
    
    for char in name:
        if not (char.isalnum() or char in (' ', '_', '.')):
            return False
    
    return True

def sort_bone_by_hierachy(bones: typing.Iterable[bpy.types.Bone]) -> list[bpy.types.Bone]:
    sorted_bones = []
    visited = set()
    bone_set = set(bones)
    
    def dfs(bone):
        if bone not in visited and bone in bone_set:
            visited.add(bone)
            sorted_bones.append(bone)
            for child in bone.children:
                if child in bone_set:
                    dfs(child)

    for bone in bones:
        dfs(bone)
        
    return sorted_bones

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
            armatureBones = sort_bone_by_hierachy(armatureBones)
            
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
                        if not all(col.is_visible for col in boneCollections):
                            continue

            selectedBones.append(bone.name)
    
    if bone_type == 'POSEBONE': return [armature.pose.bones.get(b) for b in selectedBones]
    if bone_type == 'EDITBONE': return [armature.data.edit_bones.get(b) for b in selectedBones]
    else: return [armature.data.bones.get(b) for b in selectedBones]

def is_mesh(ob : bpy.types.Object | None) -> bool:
    return ob is not None and ob.type == 'MESH'

def is_armature(ob : bpy.types.Object | None) -> bool:
    return ob is not None and ob.type == 'ARMATURE'

def is_empty(ob : bpy.types.Object | None) -> bool:
    return ob is not None and ob.type == 'EMPTY'

def is_curve(ob : bpy.types.Object | None) -> bool:
    return ob is not None and ob.type == 'CURVE'

def is_mesh_compatible(ob : bpy.types.Object | None) -> bool:
    return bool(ob and hasattr(ob,'type') and ob.type in mesh_compatible)

def has_materials(ob : bpy.types.Object | None) -> bool:
    return bool(is_mesh(ob) and getattr(ob, "material_slots", []) and any(slot.material for slot in ob.material_slots))

@contextmanager
def preserve_context_mode(obj: bpy.types.Object | None = None, mode : str = "EDIT"):
    ctx = bpy.context
    view_layer = ctx.view_layer
    
    prev_selected = list(view_layer.objects.selected)
    prev_active = view_layer.objects.active
    prev_mode = ctx.mode

    target_obj = obj or prev_active
    prev_vgroup_index = None
    prev_bone_name = None
    prev_bone_mode = None
    prev_bone_selected = None

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
            if sel and sel.name in bpy.data.objects:
                sel.select_set(True)

        if prev_active and prev_active.name in bpy.data.objects:
            view_layer.objects.active = prev_active

        mapped_mode : str = MODE_MAP.get(prev_mode, "OBJECT")
        try:
            bpy.ops.object.mode_set(mode=mapped_mode)
        except RuntimeError:
            if prev_active and prev_active.type == "ARMATURE":
                bpy.ops.object.mode_set(mode="POSE")
            elif prev_active and prev_active.type == "MESH":
                bpy.ops.object.mode_set(mode="OBJECT")

        if prev_active:
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
                        
def open_vmdl(filepath: str) -> KVNode | None:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    
    try:
        parser = KVParser(text)
        doc = parser.parse()

        root_node = doc.roots.get("rootNode")
        if not root_node or root_node.properties.get("_class") != "RootNode":
            return None
        return root_node

    except Exception:
        return None

def update_vmdl_container(container_class: str, nodes: list[KVNode] | KVNode, export_path: str | None = None, to_clipboard: bool = False) -> KVDocument | bool:
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
    if not isinstance(nodes, list):
        nodes = [nodes]

    root = None
    if to_clipboard:
        root = KVNode(_class="RootNode")
    else:
        if export_path and os.path.exists(export_path):
            root = open_vmdl(export_path)

            if root is None:
                return False
        else:
            root = KVNode(_class="RootNode")

    container = root.get(_class=container_class)
    if not container:
        container = KVNode(_class=container_class)
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

    kv_doc = KVDocument()
    kv_doc.add_root("rootNode", root)
    return kv_doc

# GET UTILITIES

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
            if o.type == 'ARMATURE' and ob.name in o.data.bones:
                return o

    elif isinstance(ob, bpy.types.EditBone):
        for o in bpy.data.objects:
            if o.type == 'ARMATURE' and ob.name in o.data.edit_bones:
                return o

    elif isinstance(ob, bpy.types.PoseBone):
        for o in bpy.data.objects:
            if o.type == 'ARMATURE' and ob.name in o.pose.bones:
                return o

    else:
        ctx_obj = bpy.context.object
        if ctx_obj:
            return get_armature(ctx_obj)
        return None

def get_armature_meshes(arm: bpy.types.Object | None,
                      visible_only: bool = False,
                      viewlayer_only: bool = True,
                      strict_visibility: bool = True) -> set[bpy.types.Object]:
    """
    Get meshes using the given armature.
    
    Args:
        arm: The armature object.
        visible_only: If True, filter out hidden objects.
        viewlayer_only: If True, only search in current view layer.
        strict_visibility: 
            - True: use ob.visible_get() (full scene visibility check).
            - False: use ob.hide_get() (manual object hide only).
    """
    if arm is None: 
        return set()
    
    if viewlayer_only:
        view_layer = bpy.context.view_layer
        valid_objects = set(view_layer.objects)
    else:
        valid_objects = set(bpy.data.objects)
    
    result = set()
    
    for ob in valid_objects:
        if ob.type != 'MESH':
            continue
        
        if not any(mod.type == 'ARMATURE' and mod.object == arm for mod in ob.modifiers):
            continue
        
        if visible_only:
            if viewlayer_only:
                layer_collection = view_layer.layer_collection
                if not is_object_visible_in_viewlayer(ob, layer_collection):
                    continue
            
            if strict_visibility:
                if not ob.visible_get():
                    continue
            else:
                if ob.hide_get():
                    continue
        
        result.add(ob)
    
    return result

def is_object_visible_in_viewlayer(obj: bpy.types.Object, layer_collection: bpy.types.LayerCollection) -> bool:
    """Check if object is visible in the view layer (not excluded from collections)."""
    
    def find_collection_in_layer(obj_collection, layer_col):
        if obj_collection.name == layer_col.collection.name:
            return layer_col
        
        for child in layer_col.children:
            result = find_collection_in_layer(obj_collection, child)
            if result:
                return result
        return None
    
    for collection in obj.users_collection:
        layer_col = find_collection_in_layer(collection, layer_collection)
        
        if layer_col and not layer_col.exclude and not layer_col.hide_viewport:
            return True
    
    return False
    
def get_hitboxes(ob : bpy.types.Object | None) -> List[bpy.types.Object | None]:
    
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

def get_jigglebones(ob : bpy.types.Object | None) -> List[bpy.types.Bone | None]:
    armature = None
    if ob is None:
        armature = get_armature()
    else:
        armature = get_armature(ob)
        
    if armature is None: return []
    
    return [b for b in armature.data.bones if b.vs.bone_is_jigglebone]

def get_dmxattachments(ob : bpy.types.Object | None) -> List[bpy.types.Object | None]:
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

def get_all_materials(ob : bpy.types.Object | None) -> set[bpy.types.Material | None]:
    armature = None
    if ob is None:
        armature = get_armature()
    else:
        armature = get_armature(ob)
        
    if armature is None: return set()
    
    meshes = get_armature_meshes(armature)
    
    if meshes is None: return set()
    
    mats = set()
    
    for mesh in meshes:
      for mat in mesh.data.materials:
          mats.add(mat)
          
    return mats  

def get_unparented_hitboxes() -> List[str]:
    """Returns list of hitbox empties without bone parent"""
    unparented = []
    
    for obj in bpy.data.objects:
        if obj.type != 'EMPTY' or obj.empty_display_type != 'CUBE':
            continue
        
        if not obj.vs.smd_hitbox:
            continue
        
        if not obj.parent or obj.parent.type != 'ARMATURE' or obj.parent_type != 'BONE' or not obj.parent_bone.strip():
            unparented.append(obj.name)
    
    return unparented

def get_unparented_attachments() -> List[str]:
    """Returns list of attachment empties without bone parent"""
    unparented = []
    
    for obj in bpy.data.objects:
        if obj.type != 'EMPTY':
            continue
        
        if not obj.vs.dmx_attachment:
            continue
        
        if not obj.parent or obj.parent.type != 'ARMATURE' or obj.parent_type != 'BONE' or not obj.parent_bone.strip():
            unparented.append(obj.name)
    
    return unparented

def get_bugged_hitboxes() -> List[str]:
    """Returns list of hitbox empties with world-space matrix bug"""
    bugged = []
    
    for obj in bpy.data.objects:
        if obj.type != 'EMPTY' or obj.empty_display_type != 'CUBE':
            continue
        
        if not obj.vs.smd_hitbox_group:
            continue
        
        if not obj.parent or obj.parent.type != 'ARMATURE' or obj.parent_type != 'BONE':
            continue
        
        armature = obj.parent
        bone_name = obj.parent_bone
        
        if bone_name not in armature.pose.bones:
            continue
        
        pose_bone = armature.pose.bones[bone_name]
        bone_tip_matrix = armature.matrix_world @ pose_bone.matrix @ mathutils.Matrix.Translation((0, pose_bone.length, 0))
        
        local_matrix = bone_tip_matrix.inverted() @ obj.matrix_world
        local_location = local_matrix.to_translation()
        
        if local_location.length > 0.001 and (abs(obj.location.x) < 0.001 and abs(obj.location.y) < 0.001 and abs(obj.location.z) < 0.001):
            bugged.append(obj.name)
    
    return bugged

def get_bugged_attachments() -> List[str]:
    """Returns list of attachment empties with world-space matrix bug"""
    bugged = []
    
    for obj in bpy.data.objects:
        if obj.type != 'EMPTY':
            continue
        
        if not obj.vs.dmx_attachment:
            continue
        
        if not obj.parent or obj.parent.type != 'ARMATURE' or obj.parent_type != 'BONE':
            continue
        
        armature = obj.parent
        bone_name = obj.parent_bone
        
        if bone_name not in armature.pose.bones:
            continue
        
        pose_bone = armature.pose.bones[bone_name]
        bone_tip_matrix = armature.matrix_world @ pose_bone.matrix @ mathutils.Matrix.Translation((0, pose_bone.length, 0))
        
        local_matrix = bone_tip_matrix.inverted() @ obj.matrix_world
        local_location = local_matrix.to_translation()
        
        if local_location.length > 0.001 and (abs(obj.location.x) < 0.001 and abs(obj.location.y) < 0.001 and abs(obj.location.z) < 0.001):
            bugged.append(obj.name)
    
    return bugged

def get_object_path(obj, view_layer) -> str:
    if obj is None:
        return "None"
    
    def find_collection_path(collections, target_obj, path=[]):
        for col in collections:
            if target_obj.name in col.objects:
                return path + [col.name]
            
            result = find_collection_path(col.children, target_obj, path + [col.name])
            if result:
                return result
        return None
    
    col_path = find_collection_path([view_layer.layer_collection.collection], obj)
    
    if col_path:
        return f"{view_layer.name} > {' > '.join(col_path)} > {obj.name}"
    else:
        return f"{view_layer.name} > {obj.name}"
    
def get_all_child_objects(parent_obj : bpy.types.Object) -> list[bpy.types.Object]:
    children = []
    for child in parent_obj.children:
        children.append(child)
        children.extend(get_all_child_objects(child))
    return children

def get_rotated_hitboxes():
    rotated = []
    rotation_threshold = 0.0001
    
    for obj in bpy.data.objects:
        if obj.type != 'EMPTY' or obj.empty_display_type != 'CUBE':
            continue
        
        if not hasattr(obj, 'vs') or not hasattr(obj.vs, 'smd_hitbox'):
            continue
        
        if not obj.vs.smd_hitbox:
            continue
        
        if (abs(obj.rotation_euler.x) > rotation_threshold or
            abs(obj.rotation_euler.y) > rotation_threshold or
            abs(obj.rotation_euler.z) > rotation_threshold):
            rotated.append(obj.name)
    
    return rotated

def get_collection_parent(ob, scene) -> bpy.types.Collection | None:
    for collection in scene.collection.children_recursive:
        if ob.name in collection.objects:
            return collection
    
    if ob.name in scene.collection.objects:
        return None
    
    return None

def get_valid_vertexanimation_object(ob : bpy.types.Object | None, use_rigid_world : bool = False) -> bpy.types.Object | bpy.types.Collection | None:
    if not is_mesh_compatible(ob): return None
    
    collection = get_collection_parent(ob, bpy.context.scene)
    if collection is None or collection.vs.mute: return ob
    else: return collection

def has_selected_bones(armature : bpy.types.Object | None) -> bool:
    if not is_armature(armature): return False
    
    if bpy.context.mode in 'EDIT_ARMATURE': return (any([bone.select for bone in armature.data.edit_bones]))
    else: return any([bone.select for bone in armature.data.bones])

# LAYOUT UTILITIES

def draw_wrapped_texts(
    layout: UILayout,
    text: str | list[str],
    max_chars: int = 40,
    icon: str | None = None,
    alert: bool = False,
    boxed: bool = True,
    title: str | None = None,
    scale_y: float = 0.7,
    icon_factor: float = 0.08,
    exclude_endspacer = False,
) -> None:
    """
    Draw text with automatic word wrapping in a column layout.
    Preserves paragraph breaks and handles both string and list inputs.
    
    Args:
        layout: Blender UILayout to draw into
        text: Text content as string or list of strings
        max_chars: Maximum characters per line before wrapping
        icon: Optional icon to display
        alert: Whether to highlight with alert styling
        boxed: Whether to wrap content in a box
        title: Optional title text to display above content
        scale_y: Vertical scale factor for text rows
        icon_factor: Width factor for icon column (when title is None)
    """
    if isinstance(text, list):
        text = '\n'.join(text)
    
    lines = []
    for paragraph in text.split('\n'):
        if not paragraph:
            lines.append('')
            continue
        
        words = paragraph.split()
        line = []
        length = 0
        
        for word in words:
            word_len = len(word)
            space = 1 if line else 0
            
            if length + word_len + space > max_chars:
                lines.append(' '.join(line))
                line = [word]
                length = word_len
            else:
                line.append(word)
                length += word_len + space
        
        if line:
            lines.append(' '.join(line))
    
    col = layout.column(align=True)
    col.scale_y = scale_y
    col.alert = alert
    container = col.box() if boxed else col
    
    if title:
        title_row = container.row(align=True)
        title_row.label(text=title, icon=icon or 'NONE')
        text_col = container.column(align=True)
    elif icon:
        split = container.split(factor=icon_factor)
        split.label(icon=icon)
        text_col = split.column(align=True)
    else:
        text_col = container.column(align=True)
    
    for line in lines:
        text_col.label(text=line)
    
    if not exclude_endspacer: 
        layout.separator(factor=0.125)

def draw_title_box_layout(
    layout: UILayout,
    text: str,
    icon: str = 'NONE',
    align: bool = False,
    alert: bool = False,
    scale_y: float = 1.0
) -> UILayout:
    """
    Create a box with a title row and return the box for further content.
    
    Args:
        layout: Blender UILayout to draw into
        text: Title text to display
        icon: Icon to display next to title
        align: Whether to align column content
        alert: Whether to highlight with alert styling
        scale_y: Vertical scale factor for the box
        
    Returns:
        UILayout box for adding additional content
    """
    box = layout.box()
    
    if align:
        box = box.column(align=True)
    
    if alert:
        box.alert = True
    
    box.scale_y = scale_y
    row = box.row()
    row.label(text=text, icon=icon)
    
    return box

def draw_listing_layout(parent_column, indent_factor=0.1, indent_char='└'):
    """
    Creates an indented sub-item UI pattern.
    
    Args:
        parent_column: The parent UI column to add items to
        indent_factor: Split factor for indentation (default: 0.1)
        indent_char: Character to use for indent indicator (default: '└')
    
    Returns:
        tuple: (root_column, sub_wrapper) where:
            - root_column: Column for the main item
            - sub_wrapper: Wrapper that provides column(), row(), label(), etc. for sub-items
    """
    root_col = parent_column.column(align=True)
    
    class SubItemWrapper:
        def __init__(self, parent, factor, char):
            self.parent = parent
            self.factor = factor
            self.char = char
        
        def _create_layout(self, layout_method, **kwargs):
            split = self.parent.split(align=True, factor=self.factor)
            split.label(text=self.char)
            return getattr(split, layout_method)(**kwargs)
        
        def column(self, **kwargs):
            return self._create_layout('column', **kwargs)
        
        def row(self, **kwargs):
            return self._create_layout('row', **kwargs)
        
        def split(self, **kwargs):
            return self._create_layout('split', **kwargs)
        
        def box(self, **kwargs):
            return self._create_layout('box', **kwargs)
        
        def label(self, **kwargs):
            split = self.parent.split(align=True, factor=self.factor)
            split.label(text=self.char)
            split.label(**kwargs)
        
        def prop(self, data, property, **kwargs):
            split = self.parent.split(align=True, factor=self.factor)
            split.label(text=self.char)
            split.prop(data, property, **kwargs)
    
    sub_wrapper = SubItemWrapper(root_col, indent_factor, indent_char)
    
    return root_col, sub_wrapper

class LayoutWrapper:
    def __init__(self, layout):
        self.layout = layout

def draw_toggleable_layout(
    layout: UILayout,
    data,
    prop_name: str,
    show_text: str,
    hide_text: str = "",
    alert: bool = False,
    align: bool = False,
    icon: str | None = None,
    icon_value: int = 0,
    wrapper: bool = False,
    boxed: bool = True,
    emboss: bool = False,
    depress : bool = False,
    toggle_scale_y: float = 1.0,
    enabled : bool = True,
    icon_outside: bool = False
) -> UILayout | LayoutWrapper | None:
    """
    Create a collapsible section with a toggle operator.
    Returns the layout if expanded, None if collapsed.
    
    Args:
        layout: Blender UILayout to draw into
        data: Data object containing the property
        prop_name: Name of the boolean property controlling visibility
        show_text: Text to display when section is collapsed
        hide_text: Text to display when expanded (defaults to show_text)
        alert: Whether to highlight with alert styling
        align: Whether to align column content
        icon: String icon identifier
        icon_value: Integer icon value (alternative to icon)
        wrapper: Return a wrapper object instead of direct layout
        boxed: Whether to wrap in a box
        emboss: Whether to emboss the toggle button
        toggle_scale_y: Vertical scale factor for toggle button only
        enabled: Whether the section is enabled
        icon_outside: Whether to place icon outside the box (left side)
        
    Returns:
        UILayout if section is expanded, None if collapsed
        If wrapper=True, returns object with .layout attribute
    """
    # If icon should be outside, only use it for the toggle row
    if icon_outside and (icon is not None or icon_value != 0):
        toggle_row = layout.row(align=True)
        if icon_value != 0:
            toggle_row.label(text='', icon_value=icon_value)
        else:
            toggle_row.label(text='', icon=icon)
        container = toggle_row.box() if boxed else toggle_row.column()
    else:
        container = layout.box() if boxed else layout.column()
    
    container.enabled = enabled
    
    if alert:
        container.alert = True
    
    if align:
        container = container.column(align=True)
    
    is_active = getattr(data, prop_name)
    display_text = (hide_text or show_text) if is_active else show_text
    toggle_icon = 'TRIA_DOWN' if is_active else 'TRIA_RIGHT'
    
    # Only show icon inside if not placing it outside
    if (icon is not None or icon_value != 0) and not icon_outside:
        row = container.row(align=True)
        row.scale_y = toggle_scale_y
        if icon_value != 0:
            row.label(text='', icon_value=icon_value)
        else:
            row.label(text='', icon=icon)
        row.operator(
            f"kitsunetoggle.{prop_name}",
            icon=toggle_icon,
            text=display_text,
            emboss=emboss,
            depress=depress
        )
    else:
        row = container.row()
        row.scale_y = toggle_scale_y
        row.operator(
            f"kitsunetoggle.{prop_name}",
            icon=toggle_icon,
            text=display_text,
            emboss=emboss,
            depress=depress
        )
    
    if is_active:
        # If icon is outside, create content in the main layout (not in toggle_row)
        if icon_outside and (icon is not None or icon_value != 0):
            content_container = layout.box() if boxed else layout.column()
            content = content_container.column()
        else:
            content = container.column()
            
        if wrapper:
            return LayoutWrapper(content)
        return content
    
    return None
