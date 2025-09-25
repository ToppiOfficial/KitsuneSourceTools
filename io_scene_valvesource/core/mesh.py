import bpy
from .common import getArmature, getArmatureMeshes

direction_map = {
            '.L': '.R', '_L': '_R', 'Left': 'Right', '_Left': '_Right', '.Left': '.Right', 'L_': 'R_', 'L.': 'R.', 'L ': 'R ',
            '.R': '.L', '_R': '_L', 'Right': 'Left', '_Right': '_Left', '.Right': '.Left', 'R_': 'L_', 'R.': 'L.', 'R ': 'L '
        }

def get_used_vertex_groups(mesh: bpy.types.Object, vertex_groups: set[int] | None = None, tolerance: float = 0.001) -> set[int]:
    """
    Return the set of vertex group indices that are actually used (weight > tolerance).
    Optionally filter by a provided set of vertex group indices.
    """
    vgroup_used = set()
    vertex_groups_set = vertex_groups if vertex_groups is None else set(vertex_groups)

    for v in mesh.data.vertices:
        
        for g in v.groups:
            if g.weight > tolerance and (vertex_groups_set is None or g.group in vertex_groups_set):
                vgroup_used.add(g.group)

    return vgroup_used

def clean_vertex_groups(ob: bpy.types.Object, bones: set[bpy.types.Bone] = None, 
                        weight_limit: float = 0.001) -> dict[bpy.types.Object, list[str]]:
    """
    Clean vertex groups by:
      1. Removing very small weights below `weight_limit`.
      2. Removing unused vertex groups.

    Returns a dict mapping each mesh to the list of removed vertex group names.
    """
    removed_groups_per_mesh: dict[bpy.types.Object, list[str]] = {}

    if not ob:
        return removed_groups_per_mesh

    if ob.type == 'MESH':
        meshes = [ob]
    elif ob.type == 'ARMATURE':
        meshes = getArmatureMeshes(ob)
    else:
        return removed_groups_per_mesh
    
    armature = getArmature(ob)
    
    if bones is None:
        bones = armature.data.bones
    else: bones = bones

    def is_left_or_right(name: str) -> bool:
        name_lower = name.lower()
        return any(kw.lower() in name_lower for kw in direction_map)

    for mesh in meshes:
        vgroups = mesh.vertex_groups
        if not vgroups:
            continue

        removed_groups_per_mesh[mesh] = []

        has_mirror = any(mod.type == 'MIRROR' for mod in mesh.modifiers)
        used_groups = get_used_vertex_groups(mesh) if mesh.type == 'MESH' else set()

        for v in mesh.data.vertices:
            
            remove_indices = [
                g.group for g in v.groups 
                if g.group < len(vgroups) and vgroups[g.group].name in bones and g.weight < weight_limit
            ]
            for idx in remove_indices:
                vgroups[idx].remove([v.index])

        for idx, vg in reversed(list(enumerate(vgroups))):
            if idx not in used_groups and not (has_mirror and is_left_or_right(vg.name)):
                removed_groups_per_mesh[mesh].append(vg.name)
                vgroups.remove(vg)

    return removed_groups_per_mesh

def limit_vertex_groups(ob: bpy.types.Object, bones: set[bpy.types.Bone], limit: int = 4):
    """Keep only the top N weights per vertex."""
    to_remove = []

    for v in ob.data.vertices:
        groups = sorted(
            (g for g in v.groups if g.group < len(ob.vertex_groups) and ob.vertex_groups[g.group].name in bones),
            key=lambda g: g.weight, reverse=True
        )

        for g in groups[limit:]:
            to_remove.append((g.group, v.index))

    for group_idx, vertex_idx in to_remove:
        if group_idx < len(ob.vertex_groups):
            vg = ob.vertex_groups[group_idx]
            vg.remove([vertex_idx])

def normalize_vertex_weights(ob: bpy.types.Object, bones: set[bpy.types.Bone]):
    """Normalize remaining weights so they sum to 1.0 per vertex."""
    for v in ob.data.vertices:
        groups = [
            (ob.vertex_groups[g.group], g.weight)
            for g in v.groups
            if g.group < len(ob.vertex_groups) and ob.vertex_groups[g.group].name in bones
        ]

        total = sum(weight for _, weight in groups)
        if total > 0:
            for vg, weight in groups:
                vg.add([v.index], weight / total, 'REPLACE')

def normalize_weights(ob: bpy.types.Object, vgroup_limit: int = 4, clean_tolerance: float = 0.001):
    """Full pipeline: clean, limit, normalize."""
    if not ob or ob.type != 'MESH':
        return
    
    arm = getArmature(ob)
    if not arm:
        return
    
    bones = arm.data.bones
    
    # Only run cleaning if threshold > 0
    if clean_tolerance > 0:
        clean_vertex_groups(ob, weight_limit=clean_tolerance)

    # Only run limiting if limit > 0
    if vgroup_limit > 0:
        limit_vertex_groups(ob, bones, limit=vgroup_limit)

    normalize_vertex_weights(ob, bones)
    
def get_flexcontrollers(ob):
    """Return list of (shapekey, eyelid, stereo, min, max) from object,
    only including valid shapekeys on the object, excluding the Basis."""
    
    if not hasattr(ob, "vs") or not hasattr(ob.vs, "dme_flexcontrollers"):
        return []

    # Exclude basis (index 0)
    valid_keys = set(ob.data.shape_keys.key_blocks.keys()[1:]) if ob.data.shape_keys else set()

    return [
        (fc.shapekey, fc.eyelid, fc.stereo, fc.dme_min, fc.dme_max)
        for fc in ob.vs.dme_flexcontrollers
        if fc.shapekey in valid_keys
    ]
    
def get_unused_shape_keys(ob: bpy.types.Object) -> list[str]:
    """
    Remove unused shape keys (keys that don't move any vertices)
    from the given object.

    The first shape key (index 0) is treated as the basis.
    """
    if not ob or ob.type != 'MESH' or not ob.data.shape_keys:
        return []

    shape_keys = ob.data.shape_keys
    if len(shape_keys.key_blocks) < 2:
        return []

    basis = shape_keys.key_blocks[0]

    basis_coords = [v.co.copy() for v in basis.data]

    removed = []
    for key in list(shape_keys.key_blocks)[1:]:
        if all((v.co - basis_coords[i]).length < 1e-6 for i, v in enumerate(key.data)):
            removed.append(key.name)
            ob.shape_key_remove(key)

    if len(shape_keys.key_blocks) == 1:
        removed.append(basis.name)
        ob.shape_key_remove(basis)

    return removed

def convert_weight_to_curve_ramp(
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
    for mesh_obj in getArmatureMeshes(arm, visible_only=visible_only):
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
