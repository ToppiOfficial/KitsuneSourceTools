import bpy, typing, re
from contextlib import contextmanager

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

def getArmature(ob: bpy.types.Object | bpy.types.Bone = None) -> bpy.types.Object | None:
    if isinstance(ob, bpy.types.Object):
        if ob.type == 'ARMATURE':
            return ob
        
        elif ob.type == 'MESH':
            for mod in ob.modifiers:
                if mod.type == 'ARMATURE':
                    if mod.object is None: continue
                    return mod.object
                
    elif isinstance(ob, bpy.types.Bone):
        for o in bpy.data.objects:
            if o.type == 'ARMATURE':
                if ob in o.data.bones.values():
                    return o
    else:
        ob = bpy.context.object
        if ob:
            if ob.type == 'MESH':
                return get_armature(ob)
            elif ob.type == 'ARMATURE':
                return ob
        else:
            return None

def getArmatureMeshes(
    arm: bpy.types.Object,
    visible_only: bool = False,
    viewlayer_only: bool = True,
    strict_visibility: bool = True
) -> set[bpy.types.Object]:
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

def getBones(
    arm: bpy.types.Object,
    sorted: bool = False,
    bonetype: str = "BONE",
    exclude_active: bool = False,
    select_all: bool = False,
    reverse_sort: bool = False,
    visible_only: bool = True
) -> list[typing.Union[bpy.types.Bone, bpy.types.EditBone, bpy.types.PoseBone]]:
    """
    Retrieve bones from an armature with optional filtering and sorting.
    Works consistently for BONE, EDITBONE, and POSEBONE types.
    """
    if not arm or arm.type != 'ARMATURE':
        return []

    og_mode = arm.mode

    def is_visible(b: bpy.types.Bone) -> bool:
        if b.hide:
            return False
        if not b.collections:
            return True

        arm = b.id_data  # the Armature datablock
        any_solo = any(col.is_solo for col in arm.collections_all)

        if any_solo:
            # Only collections with solo are visible
            return any(col.is_solo for col in b.collections)
        else:
            # No solo, fall back to visibility
            return any(col.is_visible for col in b.collections)

    sel_bones = []

    if bonetype == "EDITBONE":
        bpy.ops.object.mode_set(mode='OBJECT') 
        bpy.context.view_layer.update()
            
        visible_names = [
            b.name for b in arm.data.bones
            if (select_all or b.select) and (not visible_only or is_visible(b))
        ]
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.context.view_layer.update()
        sel_bones = [arm.data.edit_bones[name] for name in visible_names if name in arm.data.edit_bones]
        bpy.ops.object.mode_set(mode=og_mode)
        bpy.context.view_layer.update()

    elif bonetype == "POSEBONE":
        sel_bones = [
            b for b in arm.pose.bones
            if (select_all or b.bone.select) and (not visible_only or is_visible(b.bone))
        ]

    else:  # "BONE"
        sel_bones = [
            b for b in arm.data.bones
            if (select_all or b.select) and (not visible_only or is_visible(b))
        ]

    if sorted:
        sel_bones = sortBonesByHierachy(sel_bones)

    if exclude_active:
        active_bone = None
        if bonetype == "BONE":
            active_bone = arm.data.bones.active
        elif bonetype == "EDITBONE":
            active_bone = arm.data.edit_bones.active
        elif bonetype == "POSEBONE" and arm.data.bones.active:
            active_bone = arm.pose.bones.get(arm.data.bones.active.name)
        if active_bone and active_bone in sel_bones:
            sel_bones.remove(active_bone)

    if reverse_sort:
        sel_bones.reverse()

    return sel_bones

def is_mesh(ob):
    return ob is not None and ob.type == 'MESH'

def is_armature(ob):
    return ob is not None and ob.type == 'ARMATURE'

def is_empty(ob):
    return ob is not None and ob.type == 'EMPTY'

def is_curve(ob):
    return ob is not None and ob.type == 'CURVE'

def has_materials(ob):
    return ob and getattr(ob, "material_slots", []) and any(slot.material for slot in ob.material_slots)

def draw_wrapped_text_col(
    layout,
    text: str,
    max_chars: int = 32,
    icon: str | None = None,
    alert: bool = False,
    boxed: bool = True
):
    """Draw wrapped text based on character length. Optional icon and box."""
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

    col = layout.column()
    col.alert = alert

    # choose container based on boxed flag
    container = col.box() if boxed else col

    if icon:
        split = container.split(factor=0.08)
        split.label(icon=icon)
        col_lines = split.column(align=True)
    else:
        col_lines = container.column(align=True)

    for line in lines:
        col_lines.label(text=line)


# Blender’s mode name mapping (context.mode → operator arg)
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
    "TEXTURE_PAINT": "TEXTURE_PAINT",
}

@contextmanager
def PreserveContextMode(obj: bpy.types.Object, mode: str = "EDIT"):
    """
    Temporarily switch `obj` to the given mode and restore full context after.

    Preserves:
        - Selection
        - Active object
        - Active mode
        - Active vertex group
        - Active bone (pose/edit/data)

    Notes:
        - Deleted objects are skipped during restore.
        - Deleted or renamed bones/vertex groups are not restored.
        - Mode restore may fallback to OBJECT/POSE if original mode is invalid.
    """
    ctx = bpy.context
    view_layer = ctx.view_layer

    prev_selected = list(view_layer.objects.selected)
    prev_active = view_layer.objects.active
    prev_mode = ctx.mode

    prev_vgroup_index = None
    prev_bone_name = None

    if obj:
        if obj.type == "MESH":
            prev_vgroup_index = obj.vertex_groups.active_index
        elif obj.type == "ARMATURE":
            data = obj.data
            if data.bones.active:
                prev_bone_name = data.bones.active.name
            elif prev_mode == "EDIT_ARMATURE" and data.edit_bones.active:
                prev_bone_name = data.edit_bones.active.name

    # --- Switch to target object and mode ---
    if obj and obj.name in bpy.data.objects:
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass

        view_layer.objects.active = obj
        obj.select_set(True)

        try:
            bpy.ops.object.mode_set(mode=mode)
        except RuntimeError:
            pass

    # --- Yield appropriate data ---
    try:
        if mode == "EDIT" and obj and obj.type == "ARMATURE":
            yield obj.data.edit_bones
        elif mode == "POSE" and obj and obj.type == "ARMATURE":
            yield obj.pose.bones
        else:
            yield obj
    finally:
        # --- Restore mode back to OBJECT before restoring state ---
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass

        # --- Restore selection ---
        bpy.ops.object.select_all(action="DESELECT")
        for sel in prev_selected:
            if sel and sel.name in bpy.data.objects:
                sel.select_set(True)

        # --- Restore active ---
        if prev_active and prev_active.name in bpy.data.objects:
            view_layer.objects.active = prev_active

        # --- Restore mode ---
        mapped_mode = MODE_MAP.get(prev_mode, "OBJECT")
        try:
            bpy.ops.object.mode_set(mode=mapped_mode)
        except RuntimeError:
            if prev_active and prev_active.type == "ARMATURE":
                bpy.ops.object.mode_set(mode="POSE")
            elif prev_active and prev_active.type == "MESH":
                bpy.ops.object.mode_set(mode="OBJECT")

        # --- Restore sub-data ---
        if prev_active:
            if prev_active.type == "MESH" and prev_vgroup_index is not None:
                if 0 <= prev_vgroup_index < len(prev_active.vertex_groups):
                    prev_active.vertex_groups.active_index = prev_vgroup_index

            elif prev_active.type == "ARMATURE" and prev_bone_name:
                data = prev_active.data
                bone = (
                    data.edit_bones.get(prev_bone_name)
                    if mapped_mode == "EDIT"
                    else data.bones.get(prev_bone_name)
                )
                if bone:
                    data.bones.active = bone
