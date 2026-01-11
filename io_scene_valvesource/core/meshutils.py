import bpy

from .commonutils import (
    get_armature, get_armature_meshes
)

direction_map = {
            '.L': '.R', '_L': '_R', 'Left': 'Right', '_Left': '_Right', '.Left': '.Right', 'L_': 'R_', 'L.': 'R.', 'L ': 'R ',
            '.R': '.L', '_R': '_L', 'Right': 'Left', '_Right': '_Left', '.Right': '.Left', 'R_': 'L_', 'R.': 'L.', 'R ': 'L '
        }

def get_used_vertexgroups(mesh: bpy.types.Object, vertex_groups: set[int] | None = None, tolerance: float = 0.001) -> set[int]:
    """
    Return the set of vertex group indices that are actually used (weight > tolerance).
    Optionally filter by a provided set of vertex group indices.
    """
    vgroup_used = set()
    vertex_groups_set = vertex_groups if vertex_groups is None else set(vertex_groups)
    
    for mat in mesh.data.materials:
        if hasattr(mat, 'vs') and hasattr(mat.vs, 'non_exportable_vgroup'):
            vgroup_name = mat.vs.non_exportable_vgroup
            if vgroup_name and vgroup_name.strip():
                exp_vgroup = mesh.vertex_groups.get(vgroup_name.strip())
                if exp_vgroup:
                    vgroup_used.add(exp_vgroup.index)
    
    for v in mesh.data.vertices:
        for g in v.groups:
            if g.weight > tolerance and (vertex_groups_set is None or g.group in vertex_groups_set):
                vgroup_used.add(g.group)

    return vgroup_used

def remove_unused_vertexgroups(ob: bpy.types.Object | None, bones: list[bpy.types.Bone] | bpy.types.ArmatureBones | None = None, 
                        weight_limit: float = 0.001, respect_mirror: bool = True) -> dict[bpy.types.Object, list[str]] | None:
    """
    Clean vertex groups by:
      1. Removing very small weights below `weight_limit`.
      2. Removing unused vertex groups that are tied to bones.
      3. Keeping unused vertex groups that are NOT tied to bones.

    Args:
        ob: Object (mesh or armature) to clean
        bones: List of bones to consider, or None for all bones
        weight_limit: Minimum weight threshold
        respect_mirror: If True, preserve empty L/R groups when opposite side has weights

    Returns a dict mapping each mesh to the list of removed vertex group names.
    """
    if ob is None: return None
    
    removed_groups_per_mesh: dict[bpy.types.Object, list[str]] = {}

    if ob.type == 'MESH':
        meshes = [ob]
    elif ob.type == 'ARMATURE':
        meshes = get_armature_meshes(ob)
    else:
        return removed_groups_per_mesh
    
    armature = get_armature(ob)
    
    if bones is None:
        bones = list(armature.data.bones) if armature else []
    
    bone_names = {bone.name for bone in bones}

    def get_opposite_name(name: str) -> str | None:
        for left_suffix, right_suffix in direction_map.items():
            if left_suffix in name:
                return name.replace(left_suffix, right_suffix)
        return None

    def is_left_or_right(name: str) -> bool:
        return any(suffix in name for suffix in direction_map)

    for mesh in meshes:
        vgroups = mesh.vertex_groups
        if not vgroups:
            continue

        removed_groups_per_mesh[mesh] = []

        has_mirror = any(mod.type == 'MIRROR' for mod in mesh.modifiers)

        for v in mesh.data.vertices:
            groups_to_remove = []
            
            for g in v.groups:
                if g.group >= len(vgroups):
                    continue
                    
                vg_name = vgroups[g.group].name
                is_bone_group = vg_name in bone_names
                
                if is_bone_group and g.weight < weight_limit:
                    groups_to_remove.append(g.group)
            
            for idx in groups_to_remove:
                vgroups[idx].remove([v.index])

        used_groups_after_cleanup = get_used_vertexgroups(mesh, tolerance=weight_limit)
        
        vgroups_snapshot = list(vgroups)
        
        for vg in reversed(vgroups_snapshot):
            is_bone_group = vg.name in bone_names
            
            is_empty = vg.index not in used_groups_after_cleanup
            
            should_keep_for_mirror = False
            if respect_mirror and has_mirror and is_left_or_right(vg.name):
                opposite_name = get_opposite_name(vg.name)
                if opposite_name:
                    opposite_vg = vgroups.get(opposite_name)
                    if opposite_vg and opposite_vg.index in used_groups_after_cleanup:
                        should_keep_for_mirror = True
            
            if is_bone_group and is_empty and not should_keep_for_mirror:
                removed_groups_per_mesh[mesh].append(vg.name)
                vgroups.remove(vg)

    return removed_groups_per_mesh

def limit_vertexgroup_influence(ob: bpy.types.Object, bone_names: set[str], limit: int = 4):
    """Keep only the top N weights per vertex."""
    to_remove = []

    for v in ob.data.vertices:
        groups = sorted(
            (g for g in v.groups if g.group < len(ob.vertex_groups) and ob.vertex_groups[g.group].name in bone_names),
            key=lambda g: g.weight, reverse=True
        )

        for g in groups[limit:]:
            to_remove.append((g.group, v.index))

    for group_idx, vertex_idx in to_remove:
        if group_idx < len(ob.vertex_groups):
            vg = ob.vertex_groups[group_idx]
            vg.remove([vertex_idx])

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
    
    remove_unused_vertexgroups(ob, bones=deform_bones, weight_limit=clean_tolerance)
    limit_vertexgroup_influence(ob, deform_bone_names, limit=vgroup_limit)
    normalize_vertexgroup_weights(ob, deform_bone_names)
    
def get_flexcontrollers(ob : bpy.types.Object) -> list[tuple[str,bool,bool, str]]:
    """Return list of (shapekey, eyelid, stereo, raw_delta) from object,
    only including valid shapekeys on the object, excluding the Basis."""
    
    if not hasattr(ob, "vs") or not hasattr(ob.vs, "dme_flexcontrollers"):
        return []

    valid_keys = set(ob.data.shape_keys.key_blocks.keys()[1:]) if ob.data.shape_keys else set()
    
    used_names = {}
    result = []
    
    for fc in ob.vs.dme_flexcontrollers:
        if fc.shapekey not in valid_keys:
            continue
        
        raw_delta = fc.raw_delta_name.strip() if fc.raw_delta_name and fc.raw_delta_name.strip() else fc.shapekey
        
        if raw_delta in used_names:
            base_name = raw_delta
            counter = used_names[raw_delta]
            used_names[raw_delta] += 1
            raw_delta = f"{base_name}.{counter:03d}"
        else:
            used_names[raw_delta] = 1
        
        result.append((fc.shapekey, fc.eyelid, fc.stereo, raw_delta))
    
    return result
    
def get_unused_shapekeys(ob: bpy.types.Object) -> list[str]:
    """
    Remove unused shape keys (keys that don't move any vertices)
    from the given object.

    The first shape key (index 0) is treated as the basis.
    """
    if not ob or ob.type != 'MESH' or not ob.data.shape_keys:
        return []

    shape_keys = ob.data.shape_keys
    if shape_keys is None or not hasattr(shape_keys, 'key_blocks'): 
        return []

    basis = shape_keys.key_blocks[0]
    basis_coords = [v.co.copy() for v in basis.data]

    removed = []
    for key in list(shape_keys.key_blocks)[1:]:
        is_unused = True
        for i, v in enumerate(key.data):
            if (v.co - basis_coords[i]).length >= 1e-6:
                is_unused = False
                break
        
        if is_unused:
            removed.append(key.name)
            ob.shape_key_remove(key)

    if len(shape_keys.key_blocks) == 1:
        removed.append(basis.name)
        ob.shape_key_remove(basis)

    return removed

def reapply_vertexgroup_as_curve(
    arm: bpy.types.Object,
    bones: bpy.types.PoseBone | list[bpy.types.PoseBone],
    curve: bpy.types.CurveMapping,
    invert: bool = False,
    vertex_group_target: str | None = None,
    min_weight_mask: float = 0.01,
    max_weight_mask: float = 1.0,
    normalize_to_parent: bool = True,
    constant_mask: bool = False,
    weight_threshold: float = 0.001,
):
    """
    Apply a curve-based ramp to vertex weights along bones in an armature.
    
    Parameters
    ----------
    arm : bpy.types.Object
        Armature object containing the bones.
    bones : bpy.types.PoseBone | list[bpy.types.PoseBone]
        Bone or list of bones to apply the ramp to.
    curve : bpy.types.CurveMapping
        The Blender CurveMapping used to define the ramp along the bone.
    invert : bool, optional
        Flip the ramp direction along the bone axis.
    vertex_group_target : str | None, optional
        Target vertex group to receive leftover weight (residuals). If None, falls back to the bone's parent vertex group.
    min_weight_mask : float, optional
        Minimum original weight to include in the ramp. Vertices below this are ignored.
    max_weight_mask : float, optional
        Maximum original weight to include in the ramp. Vertices above this are ignored.
    normalize_to_parent : bool, optional
        Whether to scale the ramp by the original vertex weight.
    constant_mask : bool, optional
        If True, treat all eligible vertices as having full weight (1.0) before applying the ramp.
    weight_threshold : float, optional
        Minimum weight threshold when using constant_mask to avoid applying influence to noise vertices.
    """
    
    if arm.type != 'ARMATURE':
        return

    if not bones:
        print("ERROR: No bones selected.")
        return

    if isinstance(bones, bpy.types.PoseBone):
        bones = [bones]

    visible_only = getattr(bpy.context.scene.vs, "visible_mesh_only", False)
    for mesh_obj in get_armature_meshes(arm, visible_only=visible_only):
        mesh = mesh_obj.data
        mw = mesh_obj.matrix_world

        for bone in bones:
            bone_name = bone.name
            if bone_name not in mesh_obj.vertex_groups:
                continue

            vg = mesh_obj.vertex_groups[bone_name]
            if vg.lock_weight:
                continue

            head = mw @ bone.head
            tip = mw @ bone.tail
            line_vec = tip - head
            length = line_vec.length
            if length == 0:
                continue
            direction = line_vec.normalized()

            # Determine target vertex group for residuals
            target_vg = None
            if vertex_group_target:
                target_vg = mesh_obj.vertex_groups.get(vertex_group_target) or mesh_obj.vertex_groups.new(name=vertex_group_target)
            elif bone.parent:
                parent_name = bone.parent.name
                target_vg = mesh_obj.vertex_groups.get(parent_name) or mesh_obj.vertex_groups.new(name=parent_name)

            verts_to_update = []
            weights = []
            residuals = []

            for v in mesh.vertices:
                # Original weight as mask
                original_weight = next((g.weight for g in v.groups if g.group == vg.index), 0.0)
                
                if original_weight < weight_threshold:
                    continue  # skip noise
                
                if not (min_weight_mask <= original_weight <= max_weight_mask):
                    continue
                
                if constant_mask:
                    original_weight = 1.0

                world_co = mw @ v.co
                proj_len = max(0.0, (world_co - head).dot(direction))
                factor = min(proj_len / length, 1.0)
                
                factor = 1.0 - factor
                if invert:
                    factor = 1.0 - factor  # flip back to normal

                ramp_value = curve.evaluate(curve.curves[0], factor)
                ramp_weight = ramp_value * original_weight if normalize_to_parent else ramp_value

                verts_to_update.append(v.index)
                weights.append(ramp_weight)

                if target_vg:
                    residual = max(0.0, original_weight - ramp_weight)
                    residuals.append((v.index, residual))

            # Apply ramp weights
            if verts_to_update:
                vg.remove(verts_to_update)
                for v_idx, w in zip(verts_to_update, weights):
                    vg.add([v_idx], w, 'REPLACE')

            # Apply residuals to target
            if target_vg and residuals:
                for idx, w in residuals:
                    if w > 0:
                        target_vg.add([idx], w, 'ADD')
