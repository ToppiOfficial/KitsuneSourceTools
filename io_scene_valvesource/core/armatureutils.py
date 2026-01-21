import bpy
import typing
from mathutils import Matrix
from .boneutils import *

from .objectutils import (
    op_override, apply_armature_to_mesh_without_shape_keys,
    apply_armature_to_mesh_with_shapekeys, reevaluate_bone_parented_empty_matrix
    )

from .commonutils import (
    get_armature_meshes, unselect_all, preserve_context_mode, 
    unhide_all_objects, is_armature, selfreport, report)

from .meshutils import (
    get_used_vertexgroups,
)

from contextlib import contextmanager
from mathutils import Vector

filter_exclude_vertexgroup_names = [
    "Hips", 'Lower Spine', 'Spine', 'Lower Chest', 'Chest', 'Neck', 'Head',
    'Left shoulder', 'Left arm', 'Left elbow', 'Left wrist', 'Left leg', 'Left knee', 'Left ankle',
    'Right shoulder', 'Right arm', 'Right elbow', 'Right wrist', 'Right leg', 'Right knee', 'Right ankle',
    'Left eye', 'Right eye'
]

@contextmanager
def preserve_armature_state(*armatures: bpy.types.Object, reset_pose=True, reset_action=True):
    """
    Temporarily reset one or multiple armatures, then restore them on exit.

    Example:
        with PreserveArmatureState(arm1, arm2, reset_pose=True):
            # both arm1 and arm2 are clean
            ...
        # <-- all states restored (if still existing)

    Notes:
        - Deleted armatures are skipped during restore.
        - Deleted bones or bone collections are skipped.
        - Renamed bones are NOT restored (they are treated as new bones).
    """
    ctx = bpy.context
    undo_enabled = ctx.preferences.edit.use_global_undo
    ctx.preferences.edit.use_global_undo = False

    try:
        states = {}
        armature_names = []

        for armature in armatures:
            if armature.type != 'ARMATURE':
                raise TypeError(f"{armature.name} is not an armature")

            armature_names.append(armature.name)

            state = {
                "pose_position": getattr(armature.data, "pose_position", "POSE"),
                "edit_mirror_x": getattr(armature.data, "use_mirror_x", False),
                "pose_mirror_x": getattr(armature.pose, "use_mirror_x", False),
                "action": armature.animation_data.action if armature.animation_data else None,
                "bones": {},
                "bone_collections": {},
                "pose_bones": {},
                "pose_was_reset": bool(reset_pose),
            }

            for bone in armature.data.bones:
                state["bones"][bone.name] = bone.hide
                bone.hide = False

            for bcoll in getattr(armature.data, "collections", []):
                state["bone_collections"][bcoll.name] = {
                    "is_visible": getattr(bcoll, "is_visible", True),
                    "is_solo": getattr(bcoll, "is_solo", False),
                }
                bcoll.is_visible = True
                bcoll.is_solo = False

            if reset_pose:
                for pbone in armature.pose.bones:
                    pb_state = {
                        "location": pbone.location.copy(),
                        "scale": pbone.scale.copy(),
                        "rotation_mode": pbone.rotation_mode,
                    }
                    if pbone.rotation_mode == 'QUATERNION':
                        pb_state["rotation"] = pbone.rotation_quaternion.copy()
                    elif pbone.rotation_mode == 'AXIS_ANGLE':
                        pb_state["rotation"] = pbone.rotation_axis_angle[:]
                    else:
                        pb_state["rotation"] = pbone.rotation_euler.copy()

                    state["pose_bones"][pbone.name] = pb_state

                for pbone in armature.pose.bones:
                    pbone.matrix_basis.identity()

            if hasattr(armature.data, "use_mirror_x"):
                armature.data.use_mirror_x = False
            if hasattr(armature.pose, "use_mirror_x"):
                armature.pose.use_mirror_x = False
            if armature.animation_data and reset_action:
                armature.animation_data.action = None

            states[armature.name] = state

        ctx.preferences.edit.use_global_undo = undo_enabled

        try:
            yield armatures
        finally:
            ctx.preferences.edit.use_global_undo = False

            for armature_name in armature_names:
                if armature_name not in bpy.data.objects:
                    continue 
                armature = bpy.data.objects[armature_name]
                state = states.get(armature.name, {})

                if "pose_position" in state:
                    armature.data.pose_position = state["pose_position"]
                if "edit_mirror_x" in state and hasattr(armature.data, "use_mirror_x"):
                    armature.data.use_mirror_x = state["edit_mirror_x"]
                if "pose_mirror_x" in state and hasattr(armature.pose, "use_mirror_x"):
                    armature.pose.use_mirror_x = state["pose_mirror_x"]

                if reset_action and state.get("action"):
                    if armature.animation_data is None:
                        armature.animation_data_create()
                    armature.animation_data.action = state["action"]

                for bone_name, hidden in state.get("bones", {}).items():
                    bone = armature.data.bones.get(bone_name)
                    if bone:
                        bone.hide = hidden

                for bcoll_name, values in state.get("bone_collections", {}).items():
                    bcoll = next((c for c in armature.data.collections if c.name == bcoll_name), None)
                    if not bcoll:
                        continue
                    bcoll.is_visible = values.get("is_visible", True)
                    bcoll.is_solo = values.get("is_solo", False)

                if state.get("pose_was_reset", False):
                    for name, values in state.get("pose_bones", {}).items():
                        pbone = armature.pose.bones.get(name)
                        if not pbone:
                            continue
                        pbone.location = values["location"]
                        pbone.scale = values["scale"]
                        pbone.rotation_mode = values["rotation_mode"]
                        if pbone.rotation_mode == 'QUATERNION':
                            pbone.rotation_quaternion = values["rotation"]
                        elif pbone.rotation_mode == 'AXIS_ANGLE':
                            pbone.rotation_axis_angle = values["rotation"]
                        else:
                            pbone.rotation_euler = values["rotation"]

            ctx.preferences.edit.use_global_undo = undo_enabled
    except:
        ctx.preferences.edit.use_global_undo = undo_enabled
        raise

@selfreport
def apply_current_pose_as_restpose(armature: bpy.types.Object | None) -> bool:
    if armature is None: return False
    
    with preserve_armature_state(armature, reset_pose=False):
        try:
            with unhide_all_objects():
                mesh_objs = get_armature_meshes(armature)
                selected_objects = bpy.context.selected_objects
                active_object = bpy.context.view_layer.objects.active
                
                objects_to_transform = set()
                objects_to_transform.add(armature)
                
                for ob in armature.children:
                    if ob.type not in {"EMPTY", "CURVE"}:
                        objects_to_transform.add(ob)
                
                for mesh_obj in mesh_objs:
                    objects_to_transform.add(mesh_obj)
                
                empty_snapshot = {}
                for obj in armature.children:
                    if obj.type == 'EMPTY' and obj.parent_type == 'BONE':
                        empty_snapshot[obj.name] = {
                            'location': obj.matrix_world.to_translation().copy(),
                            'rotation_matrix': obj.matrix_world.to_3x3().copy(),
                            'scale': obj.matrix_world.to_scale().copy()
                        }
                
                bpy.ops.object.select_all(action='DESELECT')
                for ob in objects_to_transform:
                    try:
                        ob.select_set(True)
                    except RuntimeError:
                        continue

                bpy.ops.object.transform_apply(location=True, scale=True, rotation=True)
                bpy.ops.object.mode_set(mode='POSE')

                for mesh_obj in mesh_objs:
                    me = mesh_obj.data
                    if not me:
                        continue

                    if me.shape_keys and me.shape_keys.key_blocks:
                        key_blocks = me.shape_keys.key_blocks
                        if len(key_blocks) == 1:
                            original_basis_name = key_blocks[0].name
                            mesh_obj.shape_key_remove(key_blocks[0])
                            apply_armature_to_mesh_without_shape_keys(armature, mesh_obj)
                            mesh_obj.shape_key_add(name=original_basis_name)
                        else:
                            apply_armature_to_mesh_with_shapekeys(armature, mesh_obj, bpy.context)
                    else:
                        apply_armature_to_mesh_without_shape_keys(armature, mesh_obj)

                op_override(bpy.ops.pose.armature_apply, {'active_object': armature})
                bpy.ops.object.mode_set(mode='OBJECT')

                fixed_count = reevaluate_bone_parented_empty_matrix(
                    armature=armature,
                    preserve_rotation=True,
                    pre_transform_snapshot=empty_snapshot
                )
                if fixed_count > 0:
                    report('INFO', f"Fixed {fixed_count} empty object(s)")

                bpy.ops.object.select_all(action='DESELECT')
                for obj in selected_objects:
                    try:
                        obj.select_set(True)
                    except RuntimeError:
                        continue
                bpy.context.view_layer.objects.active = active_object

            return True

        except Exception as e:
            report('ERROR', 'Failed to apply armature pose: {}'.format(str(e)))
            return False

        finally:
            bpy.context.view_layer.update()
            bpy.context.view_layer.depsgraph.update()
            return True

@selfreport
def apply_current_pose_shapekey(armature: bpy.types.Object | None, shapekey_name : str = "") -> bool:
    if not is_armature(armature): return False
    
    meshes = get_armature_meshes(armature)
    if not meshes: return False
    
    success_count = 0
    posebones = set()

    for pbone in armature.pose.bones:
        # Subtracting identity from the matrix; a rest bone results in a zero matrix
        diff_matrix = pbone.matrix_basis - Matrix.Identity(4)
        
        # Sum the absolute values of all 16 slots in the 4x4 matrix
        total_diff = sum(abs(val) for row in diff_matrix for val in row)

        if total_diff > 1e-4:
            posebones.add(pbone.name)
    
    with preserve_context_mode(armature, 'OBJECT'):
        with unhide_all_objects():
            bpy.ops.object.select_all(action='DESELECT')
            
            for mesh in meshes:
                arm_mod = next((mod for mod in mesh.modifiers if mod.type == 'ARMATURE' and mod.object == armature), None)
                
                if not arm_mod:
                    report('WARNING', "Mesh {mesh.name} has no Armature modifier for {armature.name}")
                    continue
                
                original_shapekey_values = {}
                used_vgroup_names = get_used_vertexgroups(mesh, return_names=True)
                
                if mesh.data.shape_keys and mesh.data.shape_keys.key_blocks:
                    for sk in mesh.data.shape_keys.key_blocks:
                        original_shapekey_values[sk.name] = sk.value
                        sk.value = 0
                
                try:
                    mesh.select_set(True)
                    context_override = {'object': mesh, 'active_object': mesh, 'selected_objects': [mesh]}
                    
                    ret = op_override(bpy.ops.object.modifier_apply_as_shapekey, context_override, keep_modifier=True, modifier=arm_mod.name)
                    
                    if 'FINISHED' in ret:
                        if mesh.data.shape_keys:
                            new_key = mesh.data.shape_keys.key_blocks[-1]

                            if posebones.isdisjoint(used_vgroup_names):
                                mesh.shape_key_remove(new_key)
                                
                                if not len(mesh.data.shape_keys.key_blocks) > 1:
                                    mesh.shape_key_remove(mesh.data.shape_keys.key_blocks[0])
                            else:
                                success_count += 1
                                pose_name = shapekey_name if shapekey_name else 'Pose_Shape'
                                new_key.name = pose_name
                            
                    else:
                        report('ERROR', f"Failed to apply modifier for {mesh.name}")
                    
                    mesh.select_set(False)
                    
                except Exception as e:
                    report('ERROR', f"Error processing {mesh.name}: {str(e)}")
                    mesh.select_set(False)
                    
                finally:
                    for sk_name, sk_value in original_shapekey_values.items():
                        if sk_name in mesh.data.shape_keys.key_blocks:
                            mesh.data.shape_keys.key_blocks[sk_name].value = sk_value
    
    return success_count > 0

def copy_target_armature_visualpose(base_armature: bpy.types.Object,
                       target_armature: bpy.types.Object,
                       copy_type='ANGLES') -> bool:
    
    if not is_armature(base_armature) or not is_armature(target_armature):
        return False
    
    base_bones = {get_bone_exportname(b, for_write=True): b for b in base_armature.data.bones}
    base_bones.update({b.name: b for b in base_armature.data.bones})
    target_bones = list(target_armature.data.bones)

    with preserve_context_mode(base_armature, "POSE"):
        with preserve_armature_state(base_armature, target_armature, reset_pose=False, reset_action=False):
            bpy.ops.pose.select_all(action='DESELECT')
            
            copy_op = bpy.ops.pose.copy_pose_vis_loc if copy_type == 'ORIGIN' else bpy.ops.pose.copy_pose_vis_rot

            for b in target_bones:
                export_name = get_bone_exportname(b, for_write=True)
                target_bone = base_bones.get(export_name) or base_bones.get(b.name)
                if not target_bone:
                    continue

                base_armature.data.bones.active = target_bone
                b.select = target_bone.select = True
                copy_op()
                b.select = target_bone.select = False

    return True

def merge_armatures(source_arm: bpy.types.Object, target_arm: bpy.types.Object, match_posture=True) -> tuple[bool, list[str]]:
    if not source_arm or not target_arm:
        return False, ['No Objects']

    if source_arm.type != 'ARMATURE' or target_arm.type != 'ARMATURE':
        return False, ['Object(s) are not armature(s)']

    print(f"Merging '{target_arm.name}' into '{source_arm.name}'...")
    error_logs = []

    with preserve_armature_state(source_arm, target_arm, reset_pose=True) and unhide_all_objects():
        try:
            target_meshes = get_armature_meshes(target_arm)
            print(f"  Found {len(target_meshes)} mesh(es) attached to target armature")

            if match_posture:
                copied_rot = copy_target_armature_visualpose(source_arm, target_arm, 'ANGLES')
                copied_pos = copy_target_armature_visualpose(source_arm, target_arm, 'ORIGIN')
                if not copied_rot and not copied_pos:
                    return False, ['Error matching and applying posture for {} armature'.format(target_arm.name)]
                print("  Matched target posture to source")

            apply_current_pose_as_restpose(target_arm)
            print("  Applied pose as rest pose")

            source_bone_names = {b.name for b in source_arm.data.bones}
            source_export_map = {get_bone_exportname(b): b.name for b in source_arm.data.bones if get_bone_exportname(b)}

            bone_name_map = {}
            renamed_count = 0
            for target_bone in target_arm.data.bones:
                old_name = target_bone.name

                if old_name in source_bone_names:
                    target_bone.name += ".temp_merge"
                    bone_name_map[target_bone.name] = old_name
                    renamed_count += 1
                    continue

                target_export = get_bone_exportname(target_bone)
                matched_source_name = source_export_map.get(target_export)

                if matched_source_name:
                    new_name = matched_source_name + ".temp_merge"
                    target_bone.name = new_name
                    renamed_count += 1
                
                bone_name_map[target_bone.name] = old_name

            if renamed_count > 0:
                print(f"  Prepared {renamed_count} bone(s) for merging")

            stored_parents = {}
            for ob in target_arm.children:
                stored_parents[ob.name] = {
                    'parent_type': ob.parent_type,
                    'parent_bone': ob.parent_bone
                }

            stored_constraints = []
            for pb in target_arm.pose.bones:
                for con in pb.constraints:
                    if getattr(con, 'target', None) == target_arm:
                        stored_constraints.append({
                            'owner': pb.name,
                            'constraint': con.name,
                            'subtarget': getattr(con, 'subtarget', None)
                        })

            unselect_all()
            for ob in target_meshes:
                if not ob.select_get():
                    ob.select_set(True)
                if not ob.visible_get():
                    ob.select_set(True)

            bpy.ops.object.transform_apply(rotation=True, location=True, scale=True)
            unselect_all()

            source_arm.select_set(True)
            target_arm.select_set(True)
            bpy.context.view_layer.objects.active = source_arm
            bpy.ops.object.join()
            print("  Joined armatures")

            bpy.ops.object.mode_set(mode="EDIT")

            bones_to_remove = set()
            for bone in source_arm.data.edit_bones:
                if ".temp_merge" in bone.name:
                    orig_name = bone.name.removesuffix(".temp_merge")
                    source_bone = source_arm.data.edit_bones.get(orig_name)
                    if source_bone:
                        for child in bone.children:
                            child.parent = source_bone
                    bones_to_remove.add(bone)
            
            for bone in bones_to_remove:
                source_arm.data.edit_bones.remove(bone)

            if len(bones_to_remove) > 0:
                print(f"  Merged {len(bones_to_remove)} duplicate bone(s)")

            bpy.ops.object.mode_set(mode="OBJECT")

            for ob_name, info in stored_parents.items():
                ob = bpy.data.objects.get(ob_name)
                if not ob:
                    continue
                ob.parent = source_arm
                ob.parent_type = info['parent_type']
                if info['parent_type'] == 'BONE' and info['parent_bone']:
                    mapped_bone = bone_name_map.get(info['parent_bone'])
                    if mapped_bone and mapped_bone in source_arm.data.bones:
                        ob.parent_bone = mapped_bone

            for con_info in stored_constraints:
                owner_name = bone_name_map.get(con_info['owner'])
                if not owner_name:
                    continue
                owner_bone = source_arm.pose.bones.get(owner_name)
                if not owner_bone:
                    continue
                con = owner_bone.constraints.get(con_info['constraint'])
                if not con:
                    continue
                con.target = source_arm
                if con_info['subtarget']:
                    mapped_subtarget = bone_name_map.get(con_info['subtarget'])
                    if mapped_subtarget and mapped_subtarget in source_arm.data.bones:
                        con.subtarget = mapped_subtarget

            for ob in target_meshes:
                for mod in ob.modifiers:
                    if mod.type == 'ARMATURE' and mod.object != source_arm:
                        mod.object = source_arm
                ob.parent = source_arm

            vg_cleaned = 0
            for mesh in target_meshes:
                if mesh.vertex_groups:
                    for vg in mesh.vertex_groups:
                        if ".temp_merge" in vg.name:
                            vg.name = vg.name.removesuffix(".temp_merge")
                            vg_cleaned += 1
            
            if vg_cleaned > 0:
                print(f"  Merged {vg_cleaned} vertex group(s)")

            print(f"Successfully merged '{target_arm.name}' into '{source_arm.name}'")
            return True, error_logs

        except Exception as e:
            error_msg = f"Merge failed: {str(e)}"
            print(error_msg)
            return False, [error_msg]

        finally:
            bpy.context.view_layer.update()
            bpy.context.view_layer.depsgraph.update()

def merge_bones(armature: bpy.types.Object, source: typing.Optional[bpy.types.Bone], 
                target: typing.Union[bpy.types.Bone, typing.Iterable[bpy.types.Bone]], 
                keep_bone: bool = False,  visible_mesh_only: bool = False, 
                keep_original_weight: bool = False,  centralize_bone: bool = False) -> tuple[set[str], list[tuple[str, str]], set[str]]:
    """
    Merges bones by transferring vertex weights, constraints, and reparenting children.

    This function can operate on a single target bone or an iterable of target bones.
    It's recursive when handling an iterable of targets to correctly determine the
    parent for merging in sequence.

    Args:
        armature: The armature object.
        source: The bone to merge into. If None, it's determined from the target's parent.
        target: A single bone or an iterable of bones to be merged.
        keep_bone: If True, the target bone is not removed after merging.
        visible_mesh_only: If True, only visible meshes are considered for weight merging.
        keep_original_weight: If True, weights are copied, not moved. Implies keep_bone=True.
        centralize_bone: If True, prepares data for bone centralization.

    Returns:
        A tuple containing:
        - A set of names of bones that were removed.
        - A list of (source, target) name pairs for centralization.
        - A set of names of vertex groups that were processed.
    """
    def _find_valid_parent(bone: bpy.types.Bone, bones_to_remove: set[str]) -> typing.Optional[bpy.types.Bone]:
        """
        Finds the first parent of a bone that is not in the set of bones to be removed.
        """
        parent = bone.parent
        while parent and parent.name in bones_to_remove:
            parent = parent.parent
        return parent

    def _merge_vertex_groups(source_bone: bpy.types.Bone,target_bone: bpy.types.Bone,processed_groups: set[str],):
        """
        Merges vertex weights from the target bone's group to the source bone's group
        on all meshes associated with the armature.
        """
        for mesh in get_armature_meshes(armature):
            if visible_mesh_only and not mesh.visible_get():
                continue

            vgs = mesh.vertex_groups
            target_group = vgs.get(target_bone.name)
            if not target_group:
                continue

            source_group = vgs.get(source_bone.name)
            if not source_group:
                source_group = vgs.new(name=source_bone.name)
            
            target_group_index = target_group.index

            # Optimized loop to gather vertex weights
            weights_to_add = []
            for v in mesh.data.vertices:
                for g in v.groups:
                    if g.group == target_group_index:
                        weights_to_add.append((v.index, g.weight))
                        break  # Vertex found in group, move to the next vertex

            if not weights_to_add:
                if not keep_original_weight:
                    vgs.remove(target_group)
                continue
                
            for vertex_index, weight in weights_to_add:
                source_group.add([vertex_index], weight, 'ADD')

            processed_groups.add(target_bone.name)

            if not keep_original_weight:
                vgs.remove(target_group)

    def _update_constraints(old_target: str, new_target: str):
        """
        Updates bone constraints that target `old_target` to point to `new_target`.
        """
        if not armature.pose:
            return
            
        for pose_bone in armature.pose.bones:
            for constraint in pose_bone.constraints:
                if hasattr(constraint, "subtarget") and constraint.subtarget == old_target:
                    constraint.subtarget = new_target

    bones_to_remove = set()
    merged_pairs = []
    processed_groups = set()

    if not keep_bone:
        keep_original_weight = False

    # Handle multiple targets recursively
    if isinstance(target, typing.Iterable) and not isinstance(target, (str, bpy.types.Bone)):
        for entry in target:
            # Determine source for this entry, respecting prior merges in this run
            entry_source = source or _find_valid_parent(entry, bones_to_remove)
            if not entry_source:
                continue

            # Recursive call for each target in the iterable
            res_rem, res_pairs, res_proc = merge_bones(
                armature, entry_source, entry, keep_bone,
                visible_mesh_only, keep_original_weight, centralize_bone
            )
            bones_to_remove.update(res_rem)
            merged_pairs.extend(res_pairs)
            processed_groups.update(res_proc)
        
        return bones_to_remove, merged_pairs, processed_groups

    # Handle a single target
    # If source is not provided, find the first valid parent that is not scheduled for removal
    if source is None:
        source = _find_valid_parent(target, bones_to_remove)
        if not source:
            # Cannot merge if there is no parent to merge into
            return set(), [], set()

    _merge_vertex_groups(source, target, processed_groups)

    if not keep_bone:
        _update_constraints(target.name, source.name)
        bones_to_remove.add(target.name)

    if centralize_bone:
        merged_pairs.append((source.name, target.name))

    return bones_to_remove, merged_pairs, processed_groups

def remove_bone(arm: bpy.types.Object, bone: typing.Union[str, typing.Iterable[str]], 
                source: str | None = None, match_parent_to_head: bool = False,
                match_parent_to_head_tolerance: float = 3e-5) -> None:
    
    def _find_final_tail(edit_bone, bones_to_remove, tolerance):
        current = edit_bone
        
        while current.children:
            next_child = None
            for child in current.children:
                if child.name in bones_to_remove and (child.head - current.tail).length <= tolerance:
                    next_child = child
                    break
            
            if next_child:
                current = next_child
            else:
                break
        
        return current.tail

    def _adjust_parent_tail(edit_bone, tolerance, bones_to_remove):
        parent = edit_bone.parent
        parent.use_connect = False
        
        if len(parent.children) == 1:
            tail_position = _find_final_tail(edit_bone, bones_to_remove, tolerance)
            parent.tail = tail_position
        elif len(parent.children) > 1:
            for child in edit_bone.children:
                if (child.head - edit_bone.tail).length <= tolerance:
                    tail_position = _find_final_tail(edit_bone, bones_to_remove, tolerance)
                    parent.tail = tail_position
                    break

    def _remove_single_bone(arm, bone_name, source, match_parent_to_head, tolerance, bones_to_remove):
        edit_bone = arm.data.edit_bones.get(bone_name)
        if not edit_bone:
            return

        edit_bone.use_connect = False
        
        for child in edit_bone.children:
            child.use_connect = False

        if match_parent_to_head and edit_bone.parent:
            _adjust_parent_tail(edit_bone, tolerance, bones_to_remove)

        if source:
            source_bone = arm.data.edit_bones.get(source)
            if source_bone:
                for child in edit_bone.children:
                    child.parent = source_bone

        arm.data.edit_bones.remove(edit_bone)

    if not is_armature(arm):
        return

    with preserve_armature_state(arm,reset_pose=False):
        bones_to_remove = {bone} if isinstance(bone, str) else set(bone)
        
        if isinstance(bone, str):
            _remove_single_bone(arm, bone, source, match_parent_to_head, match_parent_to_head_tolerance, bones_to_remove)
        elif isinstance(bone, typing.Iterable):
            for entry in bone:
                _remove_single_bone(arm, entry, source, match_parent_to_head, match_parent_to_head_tolerance, bones_to_remove)

def centralize_bone_pairs(arm: bpy.types.Object, pairs: list, min_length: float = 1e-4):
    """
    For each (source, target) in pairs:
    - Centers source bone's head and tail between itself and the target's head/tail.
    - Ensures the resulting bone has at least `min_length`, otherwise skips adjustment.
    """
    if not is_armature(arm):
        return

    with preserve_context_mode(arm, "EDIT") as edit_bones:
        with preserve_armature_state(arm,reset_pose=False):
            for src_name, tgt_name in pairs:
                if src_name not in edit_bones or tgt_name not in edit_bones:
                    continue

                src_bone = edit_bones[src_name] # type: ignore
                tgt_bone = edit_bones[tgt_name] # type: ignore

                mid_head = (src_bone.head + tgt_bone.head) * 0.5
                mid_tail = (src_bone.tail + tgt_bone.tail) * 0.5

                if (mid_tail - mid_head).length < min_length:
                    direction = (
                        (src_bone.tail - src_bone.head).normalized()
                        if (src_bone.tail - src_bone.head).length > 0
                        else mathutils.Vector((0, 0, 1))
                    )
                    mid_tail = mid_head + direction * min_length

                src_bone.head = mid_head
                src_bone.tail = mid_tail

def assign_bone_headtip_positions(arm, bone_data: list[tuple]):
    """
    Rotate multiple bones based on given transform tuples.

    bone_data format:
        [
            (bone_name_or_editbone, x, y, z, roll),
            (bone_name_or_editbone, x, y, z, roll),
            ...
        ]

    If x, y, z are None → skip rotation but still apply roll if provided.
    """
    arm = get_armature(arm)
    if arm is None:
        return []

    rotated_bones = []

    for bone_entry in bone_data:
        bone_ref, x, y, z, roll = bone_entry

        if isinstance(bone_ref, bpy.types.EditBone):
            bone = bone_ref
        else:
            bone = arm.data.edit_bones.get(bone_ref if isinstance(bone_ref, str) else bone_ref.name)

        if bone is None:
            continue

        initial_distance = (bone.tail - bone.head).length
        bone.use_connect = False

        if None not in (x, y, z):
            relative_tail_pos = Vector([x, y, z])
            head_world_pos = arm.matrix_world @ bone.head
            new_tail_world_pos = head_world_pos + relative_tail_pos
            new_tail_local_pos = arm.matrix_world.inverted() @ new_tail_world_pos
            bone.tail = new_tail_local_pos

            new_distance = (bone.tail - bone.head).length
            if new_distance != initial_distance:
                direction = (bone.tail - bone.head).normalized()
                bone.tail = bone.head + direction * initial_distance

        if roll is not None:
            bone.roll = roll

        rotated_bones.append(bone)

    return rotated_bones

@selfreport
def subdivide_bone(bone: typing.Union[bpy.types.EditBone, list],
                   subdivisions: int = 2,
                   falloff: int = 10,
                   smoothness: float = 0.0,
                   min_weight_cap: float = 0.001,
                   weights_only: bool = False,
                   force_locked: bool = False):
    """
    Split a bone using Blender's native subdivide with automatic weight distribution.
    
    Args:
        bone: EditBone or list of EditBones to split
        subdivisions: Number of segments to split the bone into (minimum 2)
        falloff: Power factor for weight falloff curve (higher = sharper transitions)
        smoothness: Weight smoothing amount (0 = no smoothing, higher = smoother transitions)
        min_weight_cap: Minimum weight threshold below which weights are discarded
        weights_only: If True, only redistribute weights without creating new bones
        force_locked: If True, modify weights even if vertex groups are locked
    """
    
    def get_bone_chain(original_bone, eb):
        chain = []
        current = original_bone
        while current:
            chain.append(current)
            children = [b for b in eb if b.parent == current and b.use_connect]
            current = children[0] if children else None
        return chain
    
    def find_existing_chain(bone, base_name, subdivisions, eb):
        bone_chain = []
        
        for i in range(1, subdivisions + 1):
            target_index = str(i)
            matched_bone = None

            for b in eb.values():
                if base_name in b.name and target_index in b.name:
                    matched_bone = b
                    break

            if matched_bone:
                bone_chain.append(matched_bone)
            else:
                report('WARNING', f"Expected bone with '{base_name}' and index {i} not found for weights_only mode")
                return None
        
        return bone_chain
    
    def collect_vertex_data(meshes, old_bone_name, force_locked, arm_matrix, bone_head, bone_tail):
        all_vertex_data = []
        bone_vec = bone_tail - bone_head
        bone_length_sq = bone_vec.length_squared
        
        for mesh in meshes:
            if old_bone_name not in mesh.vertex_groups:
                continue
            
            vg_old = mesh.vertex_groups[old_bone_name]
            if not force_locked and vg_old.lock_weight:
                report('INFO', f"Skipping mesh '{mesh.name}': vertex group '{old_bone_name}' is locked")
                continue
                
            mesh_matrix = mesh.matrix_world
            
            for vert in mesh.data.vertices:
                for group in vert.groups:
                    if group.group == vg_old.index:
                        pos_world = mesh_matrix @ vert.co
                        vec_to_vert = pos_world - bone_head
                        
                        t = vec_to_vert.dot(bone_vec) / bone_length_sq if bone_length_sq > 0 else 0
                        t = max(0.0, min(1.0, t))
                        
                        all_vertex_data.append({
                            'mesh': mesh,
                            'vert_index': vert.index,
                            'weight': group.weight,
                            't': t
                        })
        
        return all_vertex_data
    
    def create_vertex_groups(meshes, old_bone_name, bone_chain, force_locked):
        mesh_vg_map = {}
        
        for mesh in meshes:
            if old_bone_name not in mesh.vertex_groups:
                continue
            
            vg_old = mesh.vertex_groups[old_bone_name]
            if not force_locked and vg_old.lock_weight:
                continue
            
            vg_list = []
            for new_bone in bone_chain:
                if new_bone.name in mesh.vertex_groups:
                    vg_list.append(mesh.vertex_groups[new_bone.name])
                else:
                    vg_list.append(mesh.vertex_groups.new(name=new_bone.name))
            
            mesh_vg_map[mesh] = vg_list
        
        return mesh_vg_map
    
    def apply_smoothing(influences, smooth_amount):
        smoothed = influences.copy()
        
        for _ in range(int(smooth_amount)):
            temp = []
            for i in range(len(smoothed)):
                kernel_sum = smoothed[i]
                kernel_count = 1.0
                
                if i > 0:
                    kernel_sum += smoothed[i - 1]
                    kernel_count += 1.0
                if i < len(smoothed) - 1:
                    kernel_sum += smoothed[i + 1]
                    kernel_count += 1.0
                
                temp.append(kernel_sum / kernel_count)
            smoothed = temp
        
        fractional = smooth_amount - int(smooth_amount)
        if fractional > 0.0:
            temp = []
            for i in range(len(smoothed)):
                kernel_sum = smoothed[i]
                kernel_count = 1.0
                
                if i > 0:
                    kernel_sum += smoothed[i - 1]
                    kernel_count += 1.0
                if i < len(smoothed) - 1:
                    kernel_sum += smoothed[i + 1]
                    kernel_count += 1.0
                
                temp.append(kernel_sum / kernel_count)
            
            smoothed = [s * (1.0 - fractional) + t * fractional for s, t in zip(smoothed, temp)]
        
        return smoothed
    
    def distribute_weights(all_vertex_data, mesh_vg_map, num_bones, falloff_power, smooth_amount, min_weight):
        vertex_weights = {}
        vertices_to_clear = set()
        
        for data in all_vertex_data:
            t = data['t']
            mesh = data['mesh']
            vert_index = data['vert_index']
            weight = data['weight']
            vg_list = mesh_vg_map[mesh]
            
            segment_centers = [(i + 0.5) / num_bones for i in range(num_bones)]
            influences = [(1.0 - abs(t - center)) ** falloff_power if abs(t - center) < 1.0 else 0.0 
                         for center in segment_centers]
            
            if smooth_amount > 0.0:
                influences = apply_smoothing(influences, smooth_amount)
            
            total = sum(influences)
            if total == 0.0:
                continue
            
            normalized = [inf / total for inf in influences]
            filtered = [w if w * weight >= min_weight else 0.0 for w in normalized]
            
            total_filtered = sum(filtered)
            if total_filtered > 0.0:
                filtered = [w / total_filtered for w in filtered]
            
            vertices_to_clear.add((mesh, vert_index, vg_list[0]))
            
            if (mesh, vert_index) not in vertex_weights:
                vertex_weights[(mesh, vert_index)] = []
            
            for i, w_norm in enumerate(filtered):
                final_w = weight * w_norm
                if final_w >= min_weight:
                    vertex_weights[(mesh, vert_index)].append((vg_list[i], final_w))
        
        return vertex_weights, vertices_to_clear
    
    def apply_weights(vertex_weights, vertices_to_clear, meshes, old_bone_name, bone_chain, force_locked):
        for mesh, vert_index, vg in vertices_to_clear:
            vg.remove([vert_index])
        
        for (mesh, vert_index), weights in vertex_weights.items():
            for vg, final_w in weights:
                vg.add([vert_index], final_w, 'REPLACE')
        
        bone_names = {b.name for b in bone_chain}
        for mesh in meshes:
            if old_bone_name in mesh.vertex_groups and old_bone_name not in bone_names:
                vg_old = mesh.vertex_groups[old_bone_name]
                if force_locked or not vg_old.lock_weight:
                    mesh.vertex_groups.remove(vg_old)
    
    if bpy.context.object.mode != 'EDIT':
        return
    
    subdivisions = max(2, subdivisions)
    
    if isinstance(bone, list):
        for b in bone:
            subdivide_bone(b, subdivisions, falloff, smoothness, min_weight_cap, weights_only, force_locked)
        return
    
    arm = get_armature(bone)
    if not arm:
        return
    
    meshes = get_armature_meshes(arm, visible_only=bpy.context.scene.vs.visible_mesh_only)
    if not meshes:
        return
    
    armature_mirror_x = arm.data.use_mirror_x
    pose_mirror_x = arm.pose.use_mirror_x
    
    try:
        arm.data.use_mirror_x = False
        arm.pose.use_mirror_x = False
        
        old_bone_name = bone.name
        bone_head = arm.matrix_world @ bone.head.copy()
        bone_tail = arm.matrix_world @ bone.tail.copy()
        eb = arm.data.edit_bones
        
        if weights_only:
            bone_chain = find_existing_chain(bone, old_bone_name, subdivisions, eb)
            if not bone_chain:
                return
        else:
            eb.active = bone
            bpy.ops.armature.select_all(action='DESELECT')
            bone.select = True
            bone.select_head = True
            bone.select_tail = True
            
            bpy.ops.armature.subdivide(number_cuts=subdivisions - 1)
            bone_chain = get_bone_chain(bone, eb)
        
        if len(bone_chain) != subdivisions:
            report('WARNING', f"Expected {subdivisions} bones but got {len(bone_chain)}")
        
        all_vertex_data = collect_vertex_data(meshes, old_bone_name, force_locked, arm.matrix_world, bone_head, bone_tail)
        mesh_vg_map = create_vertex_groups(meshes, old_bone_name, bone_chain, force_locked)
        vertex_weights, vertices_to_clear = distribute_weights(all_vertex_data, mesh_vg_map, len(bone_chain), falloff, smoothness, min_weight_cap)
        apply_weights(vertex_weights, vertices_to_clear, meshes, old_bone_name, bone_chain, force_locked)   
        
    except Exception as e:
        report('ERROR', f"Failed to subdivide bone '{bone.name}': {e}")
    
    finally:
        arm.data.use_mirror_x = armature_mirror_x
        arm.pose.use_mirror_x = pose_mirror_x
                
def remove_empty_bonecollections(armature: bpy.types.Object) -> tuple[bool, int]:
    "Remove empty bone collections from armature"
    if not is_armature: return False, 0

    bonecollections : bpy.types.BoneCollection = armature.data.collections
    if bonecollections is None or len(bonecollections) == 0: return True, 0
    
    collection_to_remove = set()
    removed_collection_count = 0
    
    for bonecoll in bonecollections:
        if hasattr(bonecoll, "bones") and len(bonecoll.bones) > 0: continue
        collection_to_remove.add(bonecoll)
        
    for col in collection_to_remove:
        armature.data.collections.remove(col)
        removed_collection_count += 1
    
    return True, removed_collection_count