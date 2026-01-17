import bpy, typing, re, os
from bpy.types import UILayout
from functools import wraps
import inspect

from contextlib import contextmanager
from ..keyvalue3 import *
from ..utils import mesh_compatible
from .objectutils import get_bugged_transform_objects

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
    "TEXTURE_PAINT": "TEXTURE_PAINT"
    }

# ------------------------------------------------
#
# CONTEXT MANAGEMENT
#
# ------------------------------------------------

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

    # Save + unhide
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
        # Restore
        restore_layer_collection_visibility(original_visibility)
        for name, state in original_obj_visibility.items():
            if name not in bpy.data.objects:
                continue
            obj = bpy.data.objects[name]
            obj.hide_set(state["hide"])
            obj.hide_viewport = state["hide_viewport"]

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
            try:
                if sel and sel.name in bpy.data.objects:
                    sel.select_set(True)
            except ReferenceError:
                pass

        if prev_active:
            try:
                if prev_active.name in bpy.data.objects:
                    view_layer.objects.active = prev_active
            except ReferenceError:
                pass

        mapped_mode : str = MODE_MAP.get(prev_mode, "OBJECT")
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

# ------------------------------------------------
#
# OPERATIONS
#
# ------------------------------------------------

def sanitize_string(data: typing.Union[str, list]) -> typing.Union[str, list]:
    
    if isinstance(data, list):
        return [sanitize_string(item) for item in data]
    
    _data = data.strip()
    _data = re.sub(r'[^\w.]+', '_', _data, flags=re.UNICODE)
    _data = re.sub(r'_+', '_', _data)
    _data = _data.strip('_')
    
    if not _data:
        return 'unnamed'
    
    return _data

def unselect_all() -> None:
    for ob in bpy.data.objects:
        if ob.select_get():
            ob.select_set(False)

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

def update_vmdl_container(container_class: str, nodes: list[KVNode] | KVNode, export_path: str | None = None,
                          to_clipboard: bool = False) -> KVDocument | bool:
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
            root = open_and_parse_vmdl(export_path)

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

# ------------------------------------------------
#
# CHECK UTILITIES
#
# ------------------------------------------------

def is_valid_string(name: str) -> bool:
    if not name or not name.strip():
        return False
    
    name = name.strip()
    
    for char in name:
        if not (char.isalnum() or char in (' ', '_', '.')):
            return False
    
    return True

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
                        
def open_and_parse_vmdl(filepath: str) -> KVNode | None:
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

# ------------------------------------------------
#
# GET UTILITIES
#
# ------------------------------------------------

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
                        if not all(col.is_visible for col in boneCollections):
                            continue

            selectedBones.append(bone.name)
    
    if bone_type == 'POSEBONE': return [armature.pose.bones.get(b) for b in selectedBones]
    if bone_type == 'EDITBONE': return [armature.data.edit_bones.get(b) for b in selectedBones]
    else: return [armature.data.bones.get(b) for b in selectedBones]

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

def get_dmxattachments(ob : bpy.types.Object | None) -> list[bpy.types.Object | None]:
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

def has_selected_bones(armature : bpy.types.Object | None) -> bool:
    if not is_armature(armature): return False
    
    if bpy.context.mode in 'EDIT_ARMATURE': return (any([bone.select for bone in armature.data.edit_bones]))
    else: return any([bone.select for bone in armature.data.bones])

# ------------------------------------------------
#
# LAYOUT UTILITIES
#
# ------------------------------------------------

def draw_wrapped_texts(layout: UILayout, text: str | list[str], max_chars: int = 40, 
                       icon: str | None = None, alert: bool = False, boxed: bool = True,
                       title: str | None = None, scale_y: float = 0.7, icon_factor: float = 0.08,
                       exclude_endspacer = False,) -> None:
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

def draw_title_box_layout(layout: UILayout, text: str, icon: str = 'NONE',
                          align: bool = False, alert: bool = False,
                          scale_y: float = 1.0) -> UILayout:
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

# ------------------------------------------------
#
# DECORATOR UTILITIES
#
# ------------------------------------------------

_report_buffer = []
_nesting_level = 0

def report(level, message):
    _report_buffer.append((level, message))

def selfreport(func=None, debug=False):
    
    def _find_operator_in_stack():
        for frame_info in inspect.stack():
            frame_locals = frame_info.frame.f_locals
            if 'self' in frame_locals:
                obj = frame_locals['self']
                if isinstance(obj, bpy.types.Operator):
                    return obj
        return None
    
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            global _report_buffer, _nesting_level
            
            _nesting_level += 1
            is_outermost = (_nesting_level == 1)
            
            if is_outermost:
                _report_buffer.clear()
            
            operator = _find_operator_in_stack()
            if debug:
                print(f"DEBUG: Found operator: {operator}, nesting level: {_nesting_level}")
            
            try:
                result = f(*args, **kwargs)
            except Exception as e:
                report('ERROR', f"Exception in {f.__name__}: {str(e)}")
                raise
            finally:
                _nesting_level -= 1
                
                if is_outermost:
                    if debug:
                        print(f"DEBUG: Buffer has {len(_report_buffer)} reports")
                    if operator:
                        for level, message in _report_buffer:
                            operator.report({level}, message)
                        _report_buffer.clear()
            
            return result
        
        return wrapper
    
    if func is None:
        return decorator
    else:
        return decorator(func)

def flush_reports(operator):
    for level, message in _report_buffer:
        operator.report({level}, message)
    _report_buffer.clear()