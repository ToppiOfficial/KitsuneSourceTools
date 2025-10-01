import bpy, typing, re, os
from contextlib import contextmanager
from ..keyvalue3 import *
from typing import Literal, TypedDict, cast

def UnselectAll():
    for ob in bpy.data.objects:
        if ob.select_get():
            ob.select_set(False)

def HideObject(ob, val=True):
    if hasattr(ob, 'hide_set'):
        ob.hide_set(val)
    elif hasattr(ob, 'hide'):
        ob.hide = val

def sanitizeString(data : str):
    
    if isinstance(data, list):
        for item in data:
            sanitizeString(item) 
        return data
    
    _data = data.strip()
    _data = re.sub(r'[^a-zA-Z0-9_.]+', '_', _data)
    _data = re.sub(r'_+', '_', _data)
    _data = _data.strip('_')
    return _data

def getArmature(ob: bpy.types.Object | bpy.types.Bone | bpy.types.EditBone | bpy.types.PoseBone | None = None) -> bpy.types.Object | None:
    if isinstance(ob, bpy.types.Object):
        if ob.type == 'ARMATURE':
            return ob
        else:
            return ob.find_armature()

    elif isinstance(ob, bpy.types.Bone):
        for o in bpy.data.objects:
            if o.type == 'ARMATURE' and ob in o.data.bones.values():
                return o

    elif isinstance(ob, bpy.types.EditBone):
        for o in bpy.data.objects:
            if o.type == 'ARMATURE' and ob in o.data.edit_bones.values():
                return o

    elif isinstance(ob, bpy.types.PoseBone):
        for o in bpy.data.objects:
            if o.type == 'ARMATURE' and ob in o.pose.bones.values():
                return o

    else:
        ctx_obj = bpy.context.object
        if ctx_obj:
            if ctx_obj.type == 'ARMATURE':
                return ctx_obj
            else:
                arm = ctx_obj.find_armature()
                if arm is not None: return arm
        return None

def getArmatureMeshes(arm: bpy.types.Object,
                      visible_only: bool = False,
                      viewlayer_only: bool = True,
                      strict_visibility: bool = True ) -> set[bpy.types.Object]:
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
    objects = bpy.context.view_layer.objects if viewlayer_only else bpy.data.objects

    return {
        ob for ob in objects
        if ob.type == 'MESH'
        and (not visible_only or not (ob.visible_get() if strict_visibility else ob.hide_get()))
        and any(mod.type == 'ARMATURE' and mod.object == arm for mod in ob.modifiers)
    }
    
def sortBonesByHierachy(bones: typing.Iterable[bpy.types.Bone]):
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

def getSelectedBones(armature : bpy.types.Object,
                     bone_type : str = 'BONE',
                     sort_type : str = 'TO_LAST',
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
    if armature.type != 'ARMATURE': return []
    
    if bone_type not in ['BONE', 'EDITBONE', 'POSEBONE']:
        if armature.mode == 'EDIT': bone_type = 'EDITBONE'
        elif armature.mode == 'POSE': bone_type = 'POSEBONE'
        else: bone_type = 'BONE'
        
    if sort_type is None: sort_type = ''
    
    # we can evaluate the selected bones through object mode
    with PreserveContextMode(armature, 'OBJECT'): 
        selectedBones = []
        
        armatureBones = armature.data.bones
        armatureBoneCollections = armature.data.collections_all
        
        solo_BoneCollections = [col for col in armatureBoneCollections if col.is_solo]
        
        if exclude_active and armature.data.bones.active is not None:
            active_name = armature.data.bones.active.name
            armatureBones = [b for b in armatureBones if b.name != active_name]
            
        if sort_type in ['TO_LAST', 'TO_FIRST']:
            armatureBones = sortBonesByHierachy(armatureBones)
            
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

def is_mesh(ob) -> bool:
    return ob is not None and ob.type == 'MESH'

def is_armature(ob) -> bool:
    return ob is not None and ob.type == 'ARMATURE'

def is_empty(ob) -> bool:
    return ob is not None and ob.type == 'EMPTY'

def is_curve(ob) -> bool:
    return ob is not None and ob.type == 'CURVE'

def has_materials(ob : bpy.types.Object) -> bool:
    return bool(ob and getattr(ob, "material_slots", []) and any(slot.material for slot in ob.material_slots))

def draw_wrapped_text_col(
    layout,
    text: str,
    max_chars: int = 32,
    icon: str | None = None,
    alert: bool = False,
    boxed: bool = True,
    title: str | None = None
):
    words = text.split()
    lines = []
    current_line = []
    current_len = 0

    for word in words:
        if current_len + len(word) + (1 if current_line else 0) > max_chars:
            lines.append(" ".join(current_line))
            current_line = [word]
            current_len = len(word)
        else:
            current_line.append(word)
            current_len += len(word) + (1 if current_line else 0)

    if current_line:
        lines.append(" ".join(current_line))

    col = layout.column(align=True)
    col.scale_y = 0.8
    col.alert = alert
    container = col.box() if boxed else col

    if title:
        title_row = container.row(align=True)
        if icon:
            title_row.label(text=title, icon=icon)
        else:
            title_row.label(text=title)
        col_lines = container.column(align=True)
    else:
        if icon:
            split = container.split(factor=0.08,)
            split.label(icon=icon)
            col_lines = split.column(align=True)
        else:
            col_lines = container.column(align=True)

    for line in lines:
        col_lines.label(text=line)

def draw_title_box(layout, text: str, icon: str = 'NONE'):
    box = layout.box()
    row = box.row()
    row.label(text=text, icon=icon)
    return box

ModeType = Literal[
    "OBJECT",
    "EDIT",
    "POSE",
    "SCULPT",
    "VERTEX_PAINT",
    "WEIGHT_PAINT",
    "TEXTURE_PAINT"
]

# Blender’s mode name mapping (context.mode -> operator arg)
MODE_MAP: dict[str, ModeType] = {
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

# This is just solves the requirement to be on a specific mode to use a certain function but still need to preserve the
# current context the user is in.
# NOTE : This code is horribly slow to be used in loop conditions !!
@contextmanager
def PreserveContextMode(obj: bpy.types.Object | None = None, mode: ModeType = "EDIT"):
    ctx = bpy.context
    view_layer = ctx.view_layer
    
    prev_selected = list(view_layer.objects.selected)
    prev_active = view_layer.objects.active
    prev_mode = ctx.mode

    target_obj = obj or prev_active
    prev_vgroup_index = None
    prev_bone_name = None

    if target_obj:
        if target_obj.type == "MESH":
            prev_vgroup_index = target_obj.vertex_groups.active_index
        elif target_obj.type == "ARMATURE":
            data = target_obj.data
            if data.bones.active:
                prev_bone_name = data.bones.active.name
            elif prev_mode == "EDIT_ARMATURE" and data.edit_bones.active:
                prev_bone_name = data.edit_bones.active.name

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

        mapped_mode : ModeType = MODE_MAP.get(prev_mode, "OBJECT")
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

            elif prev_active.type == "ARMATURE" and prev_bone_name:
                data = prev_active.data

                if mapped_mode == "EDIT":
                    edit_bone = data.edit_bones.get(prev_bone_name)
                    if edit_bone:
                        data.edit_bones.active = edit_bone
                else:
                    bone = data.bones.get(prev_bone_name)
                    if bone:
                        data.bones.active = bone
                        
def openVMDL(filepath: str) -> KVNode | None:
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
            root = openVMDL(export_path)

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