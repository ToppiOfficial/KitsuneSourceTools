import bpy, typing, re, os, mathutils
from contextlib import contextmanager
from ..keyvalue3 import *
from typing import Literal, List
from bpy.types import UILayout

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
            return getArmature(ctx_obj)
        return None

def getArmatureMeshes(arm: bpy.types.Object | None,
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
    if arm is None: return set()
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

def getSelectedBones(armature : bpy.types.Object | None,
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
    return bool(is_mesh(ob) and getattr(ob, "material_slots", []) and any(slot.material for slot in ob.material_slots))

def draw_wrapped_text_col(
    layout: UILayout,
    text: str | list[str],
    max_chars: int = 40,
    icon: str | None = None,
    alert: bool = False,
    boxed: bool = True,
    title: str | None = None,
    scale_y: float = 0.7,
    icon_factor: float = 0.08
):
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

def draw_title_box(
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

def create_toggle_section(
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
) -> UILayout | None:
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
            class LayoutWrapper:
                def __init__(self, layout):
                    self.layout = layout
            return LayoutWrapper(content)
        return content
    
    return None

def getHitboxes(ob : bpy.types.Object | None) -> List[bpy.types.Object | None]:
    
    armature : bpy.types.Object | None = None
    if ob is None:
        armature = getArmature()
    else:
        armature = getArmature(ob)
        
    if armature is None: return []
    
    hitboxes = []
    for ob in bpy.data.objects:
        if not ob.type == 'EMPTY': continue
        if ob.empty_display_type != 'CUBE' or not ob.vs.smd_hitbox: continue
        if ob.parent is not armature or ob.parent_type != 'BONE' or not ob.parent_bone.strip(): continue
        
        hitboxes.append(ob)
        
    return hitboxes

def getJiggleBones(ob : bpy.types.Object | None) -> List[bpy.types.Bone | None]:
    armature = None
    if ob is None:
        armature = getArmature()
    else:
        armature = getArmature(ob)
        
    if armature is None: return []
    
    return [b for b in armature.data.bones if b.vs.bone_is_jigglebone]

def getBoneClothNodes(ob : bpy.types.Object | None) -> List[bpy.types.Bone | None]:
    armature = None
    if ob is None:
        armature = getArmature()
    else:
        armature = getArmature(ob)
        
    if armature is None: return []
    
    return [b for b in armature.data.bones if b.vs.bone_is_clothnode]

def getDMXAttachments(ob : bpy.types.Object | None) -> List[bpy.types.Object | None]:
    armature = None
    if ob is None:
        armature = getArmature()
    else:
        if ob.type == 'ARMATURE':
            armature = ob
        else:
            armature = getArmature(ob)
        
    if armature is None: return []
    
    attchs = []
    for ob in bpy.data.objects:
        if ob.type != 'EMPTY' or ob.parent is None or ob.parent != armature: continue
        if ob.parent_type != 'BONE' or not ob.parent_bone.strip(): continue
        if not ob.vs.dmx_attachment: continue
        
        attchs.append(ob)
        
    return attchs

def getAllMats(ob : bpy.types.Object | None) -> set[bpy.types.Material | None]:
    armature = None
    if ob is None:
        armature = getArmature()
    else:
        armature = getArmature(ob)
        
    if armature is None: return set()
    
    meshes = getArmatureMeshes(armature)
    
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
    
def create_subitem_ui(parent_column, indent_factor=0.1, indent_char='└'):
    """
    Creates an indented sub-item UI pattern.
    
    Args:
        parent_column: The parent UI column to add items to
        indent_factor: Split factor for indentation (default: 0.1)
        indent_char: Character to use for indent indicator (default: '└')
    
    Returns:
        tuple: (root_column, sub_wrapper) where:
            - root_column: Column for the main item
            - sub_wrapper: Wrapper object with add_prop() method for sub-items
    """
    root_col = parent_column.column(align=True)
    
    class SubItemWrapper:
        def __init__(self, parent, factor, char):
            self.parent = parent
            self.factor = factor
            self.char = char
        
        def prop(self, data, property, **kwargs):
            split = self.parent.split(align=True, factor=self.factor)
            split.label(text=self.char)
            split.prop(data, property, **kwargs)
    
    sub_wrapper = SubItemWrapper(root_col, indent_factor, indent_char)
    
    return root_col, sub_wrapper

def get_all_children(parent_obj):
    children = []
    for child in parent_obj.children:
        children.append(child)
        children.extend(get_all_children(child))
    return children