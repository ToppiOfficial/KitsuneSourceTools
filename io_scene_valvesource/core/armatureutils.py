import bpy, math
from .boneutils import *
from .objectutils import op_override, apply_armature_to_mesh_without_shape_keys, apply_armature_to_mesh_with_shapekeys
from .commonutils import getArmatureMeshes, UnselectAll, HideObject, PreserveContextMode
from .sceneutils import ExposeAllObjects
from contextlib import contextmanager
from mathutils import Vector

unweightedBoneFilters = [ "Hips", 'Lower Spine', 'Spine', 'Lower Chest', 'Chest', 'Neck', 'Head',
                         'Left shoulder', 'Left arm', 'Left elbow', 'Left wrist', 'Left leg', 'Left knee', 'Left ankle',
                         'Right shoulder', 'Right arm', 'Right elbow', 'Right wrist', 'Right leg', 'Right knee', 'Right ankle',
                         'Left eye', 'Right eye']

@contextmanager
def PreserveArmatureState(*armatures: bpy.types.Object, reset_pose=True):
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
    states = {}
    armature_names = []

    # Save state
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
        if armature.animation_data:
            armature.animation_data.action = None

        states[armature.name] = state

    try:
        yield armatures
    finally:
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

            if state.get("action"):
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

def applyCurrPoseAsRest(armature: bpy.types.Object | None) -> bool:
    if armature is None: return False
    
    with PreserveArmatureState(armature, reset_pose=False):
        try:
            with ExposeAllObjects():
                mesh_objs = getArmatureMeshes(armature)
                selected_objects = bpy.context.selected_objects
                active_object = bpy.context.view_layer.objects.active
                
                objects_to_transform = set()
                objects_to_transform.add(armature)
                
                for ob in armature.children:
                    if ob.type not in {"EMPTY", "CURVE"}:
                        objects_to_transform.add(ob)
                
                for mesh_obj in mesh_objs:
                    objects_to_transform.add(mesh_obj)
                
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

                bpy.ops.object.select_all(action='DESELECT')
                for obj in selected_objects:
                    try:
                        obj.select_set(True)
                    except RuntimeError:
                        continue
                bpy.context.view_layer.objects.active = active_object

            return True

        except Exception as e:
            print("applyCurrPoseAsRest failed:", e)
            return False

        finally:
            bpy.context.view_layer.update()
            bpy.context.view_layer.depsgraph.update()
            return True

def copyArmatureVisualPose(base_armature: bpy.types.Object,
                       target_armature: bpy.types.Object,
                       copy_type='ANGLES'):
    if not base_armature or not target_armature:
        return False
    
    bpy.ops.object.select_all(action='DESELECT')
    base_armature.select_set(True)
    target_armature.select_set(True)
    bpy.context.view_layer.objects.active = base_armature

    base_bones = {getBoneExportName(b, for_write=True): b for b in base_armature.data.bones}
    base_bones.update({b.name: b for b in base_armature.data.bones})

    target_bones = list(target_armature.data.bones)

    for bone in base_armature.data.bones:
        bone.select = False
    for bone in target_armature.data.bones:
        bone.select = False

    bpy.ops.object.mode_set(mode='POSE')

    bpy.context.view_layer.objects.active = base_armature
    bpy.ops.pose.select_all(action='DESELECT')

    bpy.context.view_layer.objects.active = target_armature
    bpy.ops.pose.select_all(action='DESELECT')

    bpy.context.view_layer.objects.active = base_armature

    # Store original hide states
    original_bone_states = {b: b.hide for b in base_armature.data.bones}
    original_bone_states.update({b: b.hide for b in target_armature.data.bones})

    # Store collection states (solo + visible)
    original_collection_states = {
        col: (col.is_solo, col.is_visible)
        for col in base_armature.data.collections
    }
    original_collection_states.update({
        col: (col.is_solo, col.is_visible)
        for col in target_armature.data.collections
    })

    try:
        for b in original_bone_states:
            b.hide = False
        for col in original_collection_states:
            col.is_solo = False
            col.is_visible = True

        for b in target_bones:
            export_name = getBoneExportName(b, for_write=True)
            target_bone = base_bones.get(export_name) or base_bones.get(b.name)
            if not target_bone:
                continue

            base_armature.data.bones.active = target_bone
            b.select = target_bone.select = True

            if copy_type == 'ORIGIN':
                bpy.ops.pose.copy_pose_vis_loc()
            else:
                bpy.ops.pose.copy_pose_vis_rot()

            b.select = target_bone.select = False

    finally:
        for b, h in original_bone_states.items():
            b.hide = h
        for c, (solo_state, visible_state) in original_collection_states.items():
            c.is_solo = solo_state
            c.is_visible = visible_state

        bpy.ops.object.mode_set(mode='OBJECT')

    return True

def mergeArmatures(source_arm: bpy.types.Object, target_arm: bpy.types.Object, match_posture=True) -> bool:
    if not source_arm or not target_arm:
        return False
    if source_arm.type != 'ARMATURE' or target_arm.type != 'ARMATURE':
        return False

    with PreserveArmatureState(source_arm, target_arm, reset_pose=True):
        try:
            target_meshes = getArmatureMeshes(target_arm)

            if match_posture:
                copied_rot = copyArmatureVisualPose(source_arm, target_arm, 'ANGLES')
                copied_pos = copyArmatureVisualPose(source_arm, target_arm, 'ORIGIN')
                if not copied_rot and not copied_pos:
                    print('ERROR MATCHING POSTURE!')
                    return False
                
            applied_restpose = applyCurrPoseAsRest(target_arm)

            source_arm_bones = [b.name for b in source_arm.data.bones]

            bone_name_map = {}
            for target_bone in target_arm.data.bones:
                old_name = target_bone.name
                if target_bone.name in source_arm_bones:
                    target_bone.name += ".temp_merge"
                    bone_name_map[target_bone.name] = old_name
                    continue

                target_export = getBoneExportName(target_bone)
                matched_source_name = None
                for src_name in source_arm_bones:
                    src_bone = source_arm.data.bones[src_name]
                    src_export = getBoneExportName(src_bone)
                    if src_export == target_export:
                        matched_source_name = src_bone.name
                        break

                if matched_source_name:
                    new_name = matched_source_name
                    if new_name in source_arm_bones:
                        new_name += ".temp_merge"
                    target_bone.name = new_name
                bone_name_map[target_bone.name] = old_name

            stored_parents = {}
            for ob in bpy.data.objects:
                if ob.parent == target_arm:
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

            UnselectAll()
            for ob in target_meshes:
                if not ob.select_get():
                    ob.select_set(True)
                if not ob.visible_get():
                    HideObject(ob, False)
                ob.select_set(True)

            bpy.ops.object.transform_apply(rotation=True, location=True, scale=True)
            UnselectAll()

            HideObject(source_arm, False)
            HideObject(target_arm, False)
            source_arm.select_set(True)
            target_arm.select_set(True)
            bpy.context.view_layer.objects.active = source_arm
            bpy.ops.object.join()

            bpy.ops.object.mode_set(mode="EDIT")

            bones_to_remove = set()
            for bone in source_arm.data.edit_bones:
                if ".temp_merge" in bone.name:
                    orig_name = bone.name.replace(".temp_merge", "")
                    source_bone = source_arm.data.edit_bones.get(orig_name)
                    if source_bone:
                        for child in bone.children:
                            child.parent = source_bone
                    bones_to_remove.add(bone)
            for bone in bones_to_remove:
                source_arm.data.edit_bones.remove(bone)

            bpy.ops.object.mode_set(mode="OBJECT")

            for ob_name, info in stored_parents.items():
                ob = bpy.data.objects.get(ob_name)
                if not ob:
                    continue
                ob.parent = source_arm
                ob.parent_type = info['parent_type']
                if info['parent_type'] == 'BONE' and info['parent_bone']:
                    mapped_bone = bone_name_map.get(info['parent_bone'], info['parent_bone'])
                    if mapped_bone in source_arm.data.bones:
                        ob.parent_bone = mapped_bone

            for con_info in stored_constraints:
                owner_name = bone_name_map.get(con_info['owner'], con_info['owner'])
                owner_bone = source_arm.pose.bones.get(owner_name)
                if not owner_bone:
                    continue
                con = owner_bone.constraints.get(con_info['constraint'])
                if not con:
                    continue
                con.target = source_arm
                if con_info['subtarget']:
                    mapped_subtarget = bone_name_map.get(con_info['subtarget'], con_info['subtarget'])
                    if mapped_subtarget in source_arm.data.bones:
                        con.subtarget = mapped_subtarget

            for ob in target_meshes:
                for mod in ob.modifiers:
                    if mod.type == 'ARMATURE' and mod.object != source_arm:
                        mod.object = source_arm
                ob.parent = source_arm

            for mesh in target_meshes:
                if mesh.vertex_groups:
                    for vg in mesh.vertex_groups:
                        vg.name = vg.name.replace(".temp_merge", "")

            return True

        except Exception as e:
            print("merge_armatures failed:", e)
            return False

        finally:
            bpy.context.view_layer.update()
            bpy.context.view_layer.depsgraph.update()

def mergeBones(
    armature: bpy.types.Object,
    source,
    target,
    keep_bone=False,
    visible_mesh_only=False,
    keep_original_weight=False,
    centralize_bone=False
):
    bones_to_remove = set()
    merged_pairs = [] 
    processed_groups = set()

    if not keep_bone:
        keep_original_weight = False

    if isinstance(target, typing.Iterable) and not isinstance(target, str):
        for entry in target:
            entry_source = source
            if entry_source is None:
                parent = entry.parent
                while parent and parent.name in bones_to_remove:
                    parent = parent.parent
                entry_source = parent

            if not entry_source:
                continue

            result = mergeBones(
                armature, entry_source, entry, keep_bone,
                visible_mesh_only, keep_original_weight, centralize_bone
            )

            if centralize_bone:
                br, pairs, *rest = result
                groups = rest[0] if rest else set()

                bones_to_remove.update(br)
                merged_pairs.extend(pairs)
                processed_groups.update(groups)
            else:
                br, *rest = result
                groups = rest[0] if rest else set()

                bones_to_remove.update(br)
                processed_groups.update(groups)

        return (bones_to_remove, merged_pairs, processed_groups) if centralize_bone else (bones_to_remove, processed_groups)

    if source is None:
        parent = target.parent
        while parent and parent.name in bones_to_remove:
            parent = parent.parent
        source = parent
        if not source:
            return (bones_to_remove, merged_pairs, processed_groups) if centralize_bone else (bones_to_remove, processed_groups)

    for child in getArmatureMeshes(armature):
        if visible_mesh_only and not child.visible_get():
            continue

        source_group = child.vertex_groups.get(source.name)
        if not source_group:
            source_group = child.vertex_groups.new(name=source.name)

        target_group = child.vertex_groups.get(target.name)
        if target_group:
            weights = {
                v.index: target_group.weight(v.index)
                for v in child.data.vertices
                if target_group.index in [g.group for g in v.groups]
            }
            for vertex_index, weight in weights.items():
                source_group.add([vertex_index], weight, 'ADD')

            processed_groups.add(target.name)

            if not keep_original_weight:
                child.vertex_groups.remove(target_group)

    if not keep_bone:
        if armature.pose:
            for pbone in armature.pose.bones:
                for constraint in pbone.constraints:
                    if hasattr(constraint, "subtarget") and constraint.subtarget == target.name:
                        constraint.subtarget = source.name

        bones_to_remove.add(target.name)

    if centralize_bone:
        merged_pairs.append((source.name, target.name))
        return bones_to_remove, merged_pairs, processed_groups
    else:
        return bones_to_remove, processed_groups

def removeBone(
    arm: bpy.types.Object | None,
    bone: typing.Union[str, typing.Iterable[str]],
    source: str | None = None,
    match_parent_to_head: bool = False,
    match_parent_to_head_tolerance: float = 3e-5
):
    if arm is None or arm.type != 'ARMATURE':
        return

    original_symmetry = arm.data.use_mirror_x
    arm.data.use_mirror_x = False

    if isinstance(bone, str):
        edit_bone = arm.data.edit_bones.get(bone)
        if edit_bone:
            edit_bone.use_connect = False

            if edit_bone.children:
                for child in edit_bone.children:
                    child.use_connect = False

            if match_parent_to_head and edit_bone.parent:
                parent = edit_bone.parent
                edit_bone.use_connect = False
                parent.use_connect = False
                if len(parent.children) == 1:
                    parent.tail = edit_bone.tail
                elif len(parent.children) > 1:
                    for cbone in edit_bone.children:
                        if (cbone.head - edit_bone.tail).length <= match_parent_to_head_tolerance:
                            parent.tail = edit_bone.tail
                            break

            if source:
                source_bone = arm.data.edit_bones.get(source)
                if source_bone:
                    for child in edit_bone.children:
                        child.parent = source_bone

            arm.data.edit_bones.remove(edit_bone)

    elif isinstance(bone, typing.Iterable):
        for entry in bone:
            removeBone(arm, entry, source, match_parent_to_head=match_parent_to_head)

    arm.data.use_mirror_x = original_symmetry

def CentralizeBonePairs(arm: bpy.types.Object, pairs: list, min_length: float = 1e-4):
    """
    For each (source, target) in pairs:
    - Centers source bone's head and tail between itself and the target's head/tail.
    - Ensures the resulting bone has at least `min_length`, otherwise skips adjustment.
    """
    if not arm or arm.type != 'ARMATURE':
        return

    with PreserveContextMode(arm, "EDIT") as edit_bones:
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

def assignBoneAngles(arm, bone_data: list[tuple]):
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
    arm = getArmature(arm)
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

#smoothness is broken af, keep it at 0.5!
def split_bone(bone: typing.Union[bpy.types.EditBone, list],
               subdivisions: int = 2,
               smoothness: float = 0.5,
               falloff : int = 10,
               min_weight_cap : float = 0.001,
               weights_only: bool = False):
    
    if bpy.context.object.mode != 'EDIT':
        return

    subdivisions = max(2, subdivisions)
    smoothness = min(max(smoothness, 0.0), 1)
    min_weight = min_weight_cap
    falloff_power = falloff

    if isinstance(bone, bpy.types.EditBone):
        arm = getArmature(bone)
        if not arm:
            return
        meshes = getArmatureMeshes(arm)
        if not meshes:
            return

        head, tail = bone.head, bone.tail
        collections = bone.collections
        base_name = bone.name
        old_bone_name = bone.name
        
        eb = arm.data.edit_bones
        bone_chain = []
        
        if weights_only:
            # Only process weights - expect bones to already exist
            for i in range(1, subdivisions + 1):
                target_index = str(i)
                matched_bone = None

                for bone in eb.values(): # type: ignore
                    # Match if base_name is in the name and the number appears somewhere after it
                    if base_name in bone.name and target_index in bone.name:
                        matched_bone = bone
                        break

                if matched_bone:
                    bone_chain.append(matched_bone)
                else:
                    print(f"Warning: Expected bone with '{base_name}' and index {i} not found for weights_only mode")
                    return
        else:
            for i in range(1, subdivisions + 1):
                t_start = (i - 1) / subdivisions
                t_end = i / subdivisions
                
                new_bone = eb.new(name=f"{base_name}{i}")
                new_bone.head = head.lerp(tail, t_start)
                new_bone.tail = head.lerp(tail, t_end)
                new_bone.roll = bone.roll
                
                if i == 1:
                    new_bone.parent = bone.parent
                else:
                    new_bone.parent = bone_chain[i - 2]
                
                bone_chain.append(new_bone)
                
                if collections:
                    for col in collections:
                        col.assign(new_bone)
            
            # Reassign children to nearest bone
            for child in bone.children:
                child_head = child.head
                closest_bone = bone_chain[0]
                min_dist = (child_head - closest_bone.tail).length
                
                for new_bone in bone_chain[1:]:
                    dist = (child_head - new_bone.tail).length
                    if dist < min_dist:
                        min_dist = dist
                        closest_bone = new_bone
                
                child.parent = closest_bone
                child.use_connect = False
            
            eb.remove(eb[old_bone_name])
        
        # Handle vertex groups - projection-based approach
        arm_matrix = arm.matrix_world
        head_world = arm_matrix @ head
        tail_world = arm_matrix @ tail
        bone_vec = tail_world - head_world
        bone_length_sq = bone_vec.length_squared
        
        # Collect all vertices from all meshes first for consistent evaluation
        all_vertex_data = []
        
        for mesh in meshes:
            if old_bone_name not in mesh.vertex_groups:
                continue
                
            vg_old = mesh.vertex_groups[old_bone_name]
            mesh_matrix = mesh.matrix_world
            
            for vert in mesh.data.vertices:
                for group in vert.groups:
                    if group.group == vg_old.index:
                        pos_world = mesh_matrix @ vert.co
                        
                        # Project vertex onto bone axis to get normalized position (0 to 1)
                        vec_to_vert = pos_world - head_world
                        if bone_length_sq > 0:
                            t = vec_to_vert.dot(bone_vec) / bone_length_sq
                        else:
                            t = 0
                        
                        t = max(0.0, min(1.0, t))
                        
                        all_vertex_data.append({
                            'mesh': mesh,
                            'vert_index': vert.index,
                            'weight': group.weight,
                            't': t
                        })
        
        mesh_vg_map = {}
        for mesh in meshes:
            if old_bone_name not in mesh.vertex_groups:
                continue
            
            vg_new_list = []
            for new_bone in bone_chain:
                vg_new_list.append(mesh.vertex_groups.new(name=new_bone.name))
            mesh_vg_map[mesh] = vg_new_list
        
        
        for data in all_vertex_data:
            t = max(0.0, min(1.0, data['t']))
            mesh = data['mesh']
            vert_index = data['vert_index']
            weight = data['weight']

            vg_list = mesh_vg_map[mesh]
            segment_centers = [(i + 0.5) / subdivisions for i in range(subdivisions)]

            influences = []
            for center in segment_centers:
                dist = abs(t - center)
                influences.append((1.0 - dist) ** falloff_power if dist < 1.0 else 0.0)

            total = sum(influences)
            if total == 0.0:
                continue

            # Normalize, clamp small weights, and renormalize again
            normalized_weights = [inf / total for inf in influences]

            # Zero out anything below min_weight
            filtered_weights = [w if w * weight >= min_weight else 0.0 for w in normalized_weights]

            # Optional: renormalize after filtering (so total stays ~1.0)
            total_filtered = sum(filtered_weights)
            if total_filtered > 0.0:
                filtered_weights = [w / total_filtered for w in filtered_weights]

            for i, w_norm in enumerate(filtered_weights):
                final_w = weight * w_norm
                if final_w >= min_weight:
                    vg_list[i].add([vert_index], final_w, 'REPLACE')

        for mesh in meshes:
            if old_bone_name in mesh.vertex_groups:
                mesh.vertex_groups.remove(mesh.vertex_groups[old_bone_name])

    elif isinstance(bone, list):
        if len(bone) == 1:
            split_bone(bone[0], subdivisions, smoothness, falloff, min_weight_cap, weights_only)
        else:
            for b in bone:
                split_bone(b, subdivisions, smoothness, falloff, min_weight_cap, weights_only)