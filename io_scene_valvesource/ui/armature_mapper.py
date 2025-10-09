import os
import json
from typing import Set, Any

import bpy
from bpy.types import Context, Object, Operator, UILayout, UIList, Event, Constraint, BoneCollection
from bpy.props import EnumProperty, IntProperty, StringProperty
from mathutils import Vector

from ..core.armatureutils import (
    PreserveContextMode,
    assignBoneAngles,
    getArmature,
    getCanonicalBoneName,
)
from ..core.boneutils import getArmature, getCanonicalBoneName
from ..core.commonutils import (
    draw_title_box,
    draw_wrapped_text_col,
    is_armature,
)

from ..core.armatureutils import (
    applyCurrPoseAsRest
)

from ..core.meshutils import getArmature
from ..flex import get_id
from ..utils import print

from .common import Tools_SubCategoryPanel

class ARMATUREMAPPER_PT_ArmatureMapper(Tools_SubCategoryPanel):
    bl_label : str = 'Armature Mapper'

    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        bx : UILayout = draw_title_box(l, ARMATUREMAPPER_PT_ArmatureMapper.bl_label, icon='ARMATURE_DATA')

        ob : Object | None = context.object
        if is_armature(ob): pass
        else:
            draw_wrapped_text_col(bx,get_id("panel_select_armature"),max_chars=40 , icon='HELP')
            return

        col = bx.column()
        row = bx.row(align=True)
        row.prop(context.scene.vs, 'defineArmatureCategory', expand=True)

        if context.scene.vs.defineArmatureCategory == 'WRITE':
            self.draw_write_mode(context, bx)
        else:
            self.draw_read_mode(context, bx)

    def draw_write_mode(self, context : Context, layout : UILayout) -> None:
        col = layout.column(align=False)
        draw_wrapped_text_col(col,"When saving a bone preset, the current Blender bone name becomes the export name, and the target name is the bone that the preset will apply to when loaded. For example, if the bone name is Spine1 and the target name is Waist then Spine1 will be the export name and the JSON will look for the Waist bone on the armature and apply the preset there.  It is recommended to name the target bone based on the 'WRITE' format for Humanoid",max_chars=40 , icon='HELP')
        col = layout.column()
        col.operator(ARMATUREMAPPER_OT_LoadPreset.bl_idname)

        col = layout.column(align=False)
        row = layout.row()
        row.template_list(
            "ARMATUREMAPPER_UL_BoneList",
            "",
            context.object.vs,
            "armature_map_bonecollections",
            context.object.vs,
            "armature_map_bonecollections_index",
            rows=3
        )
        row = layout.row()
        row.scale_y = 1.25
        split = row.split(factor=0.4,align=True)
        split.operator(ARMATUREMAPPER_OT_AddItem.bl_idname, icon="ADD", text=ARMATUREMAPPER_OT_AddItem.bl_label).add_type = 'SINGLE'
        split.operator(ARMATUREMAPPER_OT_AddItem.bl_idname, icon="ADD", text=ARMATUREMAPPER_OT_AddItem.bl_label + " (Selected Bones)").add_type = 'SELECTED'

        if 0 <= context.object.vs.armature_map_bonecollections_index < len(context.object.vs.armature_map_bonecollections):
            self.draw_bone_item_properties(context, layout)

        layout.operator(ARMATUREMAPPER_OT_WriteJson.bl_idname, icon='FILE')

    def draw_bone_item_properties(self, context : Context, layout : UILayout) -> None:
        item = context.object.vs.armature_map_bonecollections[context.object.vs.armature_map_bonecollections_index]

        col = layout.column(align=True)
        col.prop(item, "boneExportName")
        col.alert = not bool(item.boneName.strip())
        col.prop(item, "boneName")
        col.alert = False
        col.prop(item, "parentBone")
        col.row().prop(item, "writeRotation", expand=True)
        col.prop(item, "writeExportRotationOffset")
        col.prop(item, "writeTwistBone")
        if item.writeTwistBone:
            col.prop(item, "twistBoneTarget")
            col.prop(item, "twistBoneCount", slider=True)

    def draw_read_mode(self, context : Context, layout : UILayout) -> None:
        col = layout.column(align=False)
        
        draw_wrapped_text_col(col,'This will rename the bones to match a similar VRChat-style rig. The bone map includes Left and Right shoulder, arm, elbow, wrist, thigh,knee, ankle, and toe, as well as a central chain of Hips → Lower Spine → Spine → Lower Chest → Chest → Neck → Head. Finger bones follow the format Index/Middle/RingLittleFingers1–3_L/R and Thumb0–2_L/R.',max_chars=40, icon='HELP')
        
        self.draw_humanoid_bone_mapping(context, layout)

        layout.operator(ARMATUREMAPPER_OT_LoadJson.bl_idname)

    def draw_humanoid_bone_mapping(self, context : Context, layout : UILayout) -> None:
        col = layout.column(align=True)
        
        bx = col.box()
        col = bx.column()

        draw_wrapped_text_col(col,text='Head, Chest and Pelvis are required to have inputs', icon='HELP')
        
        col = bx.column(align=True)
        col.prop_search(context.object.vs, 'armature_map_head',   context.object.data, "bones", text="Head")
        col.prop_search(context.object.vs, 'armature_map_chest',  context.object.data, "bones", text="Chest")
        col.prop_search(context.object.vs, 'armature_map_pelvis', context.object.data, "bones", text="Pelvis")

        col.separator()
        col.separator(type='LINE')
        col.separator()

        self.draw_bone_pair(col, context, 'Eye', 'armature_map_eye_l', 'armature_map_eye_r')

        col.separator()
        col.separator(type='LINE')
        col.separator()

        self.draw_bone_pair(col, context, 'Thigh', 'armature_map_thigh_l', 'armature_map_thigh_r')
        self.draw_bone_pair(col, context, 'Ankle', 'armature_map_ankle_l', 'armature_map_ankle_r')
        self.draw_bone_pair(col, context, 'Toe', 'armature_map_toe_l', 'armature_map_toe_r')

        col.separator()
        col.separator(type='LINE')
        col.separator()

        self.draw_bone_pair(col, context, 'Shoulder', 'armature_map_shoulder_l', 'armature_map_shoulder_r')
        self.draw_bone_pair(col, context, 'Wrist', 'armature_map_wrist_l', 'armature_map_wrist_r')

        col.separator()
        col.separator(type='LINE')
        col.separator()

        self.draw_bone_pair(col, context, 'Thumb', 'armature_map_thumb_f_l', 'armature_map_thumb_f_r')
        self.draw_bone_pair(col, context, 'Index', 'armature_map_index_f_l', 'armature_map_index_f_r')
        self.draw_bone_pair(col, context, 'Middle', 'armature_map_middle_f_l', 'armature_map_middle_f_r')
        self.draw_bone_pair(col, context, 'Ring', 'armature_map_ring_f_l', 'armature_map_ring_f_r')
        self.draw_bone_pair(col, context, 'Pinky', 'armature_map_pinky_f_l', 'armature_map_pinky_f_r')

    def draw_bone_pair(self, layout : UILayout, context : Context, label : str, prop_l : str, prop_r : str) -> None:
        row = layout.row(align=True)
        row.scale_x = 0.2
        row.label(text=f'{label} L & R')
        row.prop_search(context.object.vs, prop_l, context.object.data, "bones", text="")
        row.prop_search(context.object.vs, prop_r, context.object.data, "bones", text="")

class ARMATUREMAPPER_OT_LoadPreset(Operator):
    bl_idname : str = "armaturemapper.load_preset"
    bl_label : str = "Load Preset"
    bl_options : Set = {"INTERNAL", "REGISTER"}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    @classmethod
    def poll(cls, context : Context) -> bool:
        return is_armature(context.object)

    def invoke(self, context : Context, event : Event) -> Set:
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context : Context) -> Set:
        if not self.filepath:
            self.report({'ERROR'}, "No file selected")
            return {'CANCELLED'}

        if not self.filepath.lower().endswith(".json"):
            self.report({'ERROR'}, "File must be a .json")
            return {'CANCELLED'}

        if not os.path.exists(self.filepath):
            self.report({'ERROR'}, "File does not exist")
            return {'CANCELLED'}

        ob : Object | None = context.object

        with open(self.filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        items = ob.vs.armature_map_bonecollections
        items.clear()

        bone_names = {b.name for b in ob.data.bones}

        for boneData in data:
            bone_name = boneData.get("BoneName", "")
            export_name = boneData.get("ExportName", "")
            parent_bone = boneData.get("ParentBone", "")
            rotation = boneData.get("Rotation", None)
            roll = boneData.get("Roll", None)
            export_rot_offset = boneData.get("ExportRotationOffset", None)
            twist_bone = boneData.get("TwistBones", None)
            twist_bonecount = boneData.get("TwistBoneCount", None)

            if export_name not in bone_names:
                continue

            new_item = items.add()
            new_item.boneExportName = export_name
            new_item.boneName = bone_name

            new_item.parentBone = parent_bone if parent_bone else ""

            if rotation is not None:
                new_item.writeRotation = 'ROTATION'
            elif roll is not None:
                new_item.writeRotation = 'ROLL'
            else:
                new_item.writeRotation = 'NONE'

            if export_rot_offset:
                new_item.writeExportRotationOffset = True

            if twist_bone:
                new_item.writeTwistBone = True
                new_item.twistBoneTarget = twist_bone
                new_item.twistBoneCount = twist_bonecount

        self.report({'INFO'}, f"Loaded preset from: {self.filepath} ({len(items)} items)")
        return {'FINISHED'}

class ARMATUREMAPPER_OT_LoadJson(Operator):
    bl_idname : str = "armaturemapper.load_json"
    bl_label : str = "Load JSON"
    bl_options : Set = {"REGISTER", "UNDO"}

    filepath: StringProperty(subtype="FILE_PATH")

    load_options: EnumProperty(
        name="Load Options",
        description="Select which parts of the JSON to load",
        items=[
            ("EXPORT_NAME", "Export Name", ""),
            ("BONE_EXROTATION", "Bone Export Rotation", ""),
            ("BONE_ROTATION", "Bone Rotation", ""),
            ("CONSTRAINTS", "Constraints", "")
        ],
        default={"EXPORT_NAME", "BONE_EXROTATION", "BONE_ROTATION", "CONSTRAINTS"}, # type: ignore
        options={"ENUM_FLAG"}
    )

    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        col = l.column(align=True)
        col.label(text="Select parts to load:")
        col.prop(self, "load_options")

    def invoke(self, context : Context, event : Event) -> Set:
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context : Context) -> Set:

        json_path = self.filepath

        if not json_path.lower().endswith(".json"):
            self.report({"ERROR"}, "Please select a JSON file")
            return {"CANCELLED"}

        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        boneElems = {entry["BoneName"]: entry for entry in data}

        arm : Object | None = getArmature(context.object)
        if arm is None:
            self.report({"ERROR"}, "No valid armature selected")
            return {"CANCELLED"}

        def remapped_humanoid_armature_bones(arm: Object):
            vs_arm = getattr(arm, "vs", None)
            if not vs_arm:
                return False

            bones = arm.data.bones
            rename_map = {}

            def is_valid_bone(name: str) -> bool:
                return bool(name) and isinstance(name, str) and name in arm.data.bones.keys()

            # Conflict check
            bone_props = [attr for attr in dir(vs_arm) if attr.startswith("armature_map_")]
            bone_values = [getattr(vs_arm, prop) for prop in bone_props]
            if all(not v for v in bone_values):
                return True
            selected_bones = [v for v in bone_values if is_valid_bone(v)]
            seen, duplicates = set(), set()
            for b in selected_bones:
                if b in seen:
                    duplicates.add(b)
                else:
                    seen.add(b)
            if duplicates:
                print(f"[Humanoid Rename] Conflicting assignments: {duplicates}")
                return False

            # Helpers
            def collect_chain(start_name, end_name):
                if not (is_valid_bone(start_name) and is_valid_bone(end_name)):
                    return []

                start_bone = bones[start_name]
                end_bone = bones[end_name]

                def dfs(bone, target, path):
                    path.append(bone)
                    if bone == target:
                        return True
                    for child in bone.children:
                        if dfs(child, target, path):
                            return True
                    path.pop()
                    return False

                chain = []
                if dfs(start_bone, end_bone, chain):
                    return chain
                return []

            def realign_chain_tails(chain):
                if 'BONE_ROTATION' in self.load_options:
                    if len(chain) < 2:
                        return
                    prev_mode = arm.mode
                    if bpy.context.object != arm:
                        bpy.context.view_layer.objects.active = arm
                    bpy.ops.object.mode_set(mode='EDIT')

                    edit_bones = arm.data.edit_bones
                    for i in range(len(chain) - 1):
                        a = edit_bones.get(chain[i].name)
                        b = edit_bones.get(chain[i + 1].name)
                        if a and b:
                            a.tail = b.head

                    bpy.ops.object.mode_set(mode=prev_mode)

            def build_torso_chain(pelvis_name, chest_name):
                chain = collect_chain(pelvis_name, chest_name)
                if len(chain) < 2:
                    return
                names = ["Hips"]
                middle_count = len(chain) - 2
                if middle_count == 1:
                    names.append("Spine")
                elif middle_count == 2:
                    names.extend(["Lower Spine", "Spine"])
                elif middle_count == 3:
                    names.extend(["Lower Spine", "Spine", "Lower Chest"])
                elif middle_count > 3:
                    names.extend(["Lower Spine", "Spine", "Lower Chest"])
                    names.extend([f"Spine_{i+1}" for i in range(middle_count - 3)])
                names.append("Chest")

                for bone, new_name in zip(chain, names):
                    rename_map[bone.name] = new_name

                realign_chain_tails(chain)

            def build_neck_chain(chest_name, head_name):
                chain = collect_chain(chest_name, head_name)
                if len(chain) < 2:
                    return
                for i, bone in enumerate(chain[1:-1], 1):
                    rename_map[bone.name] = "Neck" if i == 1 else f"Neck_{i-1}"
                rename_map[head_name] = "Head"

                realign_chain_tails(chain)

            def build_chain_mapping(start_name, end_name, base_names, side=None):
                chain = collect_chain(start_name, end_name)
                if not chain:
                    return
                target_count = len(base_names)
                for i, bone in enumerate(chain):
                    idx = min(i, target_count - 1)
                    name = base_names[idx]
                    if side == "L":
                        new_name = f"Left {name}"
                    elif side == "R":
                        new_name = f"Right {name}"
                    else:
                        new_name = name
                    if len(chain) > target_count and i >= target_count:
                        new_name += f"_{i - target_count + 1}"
                    rename_map[bone.name] = new_name

                realign_chain_tails(chain)

            def build_finger_mapping(start_name, base, side, start_index=1):
                if not is_valid_bone(start_name):
                    return
                bone = bones[start_name]
                chain = []
                while bone:
                    chain.append(bone)
                    bone = bone.children[0] if bone.children else None
                for i, bone in enumerate(chain):
                    rename_map[bone.name] = f"{base}{i+start_index}_{side}"

                realign_chain_tails(chain)

            # Eyes
            if is_valid_bone(vs_arm.armature_map_eye_l):
                rename_map[vs_arm.armature_map_eye_l] = "Left eye"
            if is_valid_bone(vs_arm.armature_map_eye_r):
                rename_map[vs_arm.armature_map_eye_r] = "Right eye"

            # Hips to Chest
            build_torso_chain(vs_arm.armature_map_pelvis, vs_arm.armature_map_chest)

            # Neck to Head
            if is_valid_bone(vs_arm.armature_map_chest) and is_valid_bone(vs_arm.armature_map_head):
                build_neck_chain(vs_arm.armature_map_chest, vs_arm.armature_map_head)

            # Legs
            build_chain_mapping(vs_arm.armature_map_thigh_l, vs_arm.armature_map_ankle_l,
                                ["leg", "knee", "ankle"], side="L")
            if is_valid_bone(vs_arm.armature_map_toe_l):
                rename_map[vs_arm.armature_map_toe_l] = "Left toe"

            build_chain_mapping(vs_arm.armature_map_thigh_r, vs_arm.armature_map_ankle_r,
                                ["leg", "knee", "ankle"], side="R")
            if is_valid_bone(vs_arm.armature_map_toe_r):
                rename_map[vs_arm.armature_map_toe_r] = "Right toe"

            # Arms
            build_chain_mapping(vs_arm.armature_map_shoulder_l, vs_arm.armature_map_wrist_l,
                                ["shoulder", "arm", "elbow", "wrist"], side="L")
            build_chain_mapping(vs_arm.armature_map_shoulder_r, vs_arm.armature_map_wrist_r,
                                ["shoulder", "arm", "elbow", "wrist"], side="R")

            # Fingers
            build_finger_mapping(vs_arm.armature_map_index_f_l, "IndexFinger", "L", start_index=1)
            build_finger_mapping(vs_arm.armature_map_middle_f_l, "MiddleFinger", "L", start_index=1)
            build_finger_mapping(vs_arm.armature_map_ring_f_l, "RingFinger", "L", start_index=1)
            build_finger_mapping(vs_arm.armature_map_pinky_f_l, "LittleFinger", "L", start_index=1)
            build_finger_mapping(vs_arm.armature_map_thumb_f_l, "Thumb", "L", start_index=0)

            build_finger_mapping(vs_arm.armature_map_index_f_r, "IndexFinger", "R", start_index=1)
            build_finger_mapping(vs_arm.armature_map_middle_f_r, "MiddleFinger", "R", start_index=1)
            build_finger_mapping(vs_arm.armature_map_ring_f_r, "RingFinger", "R", start_index=1)
            build_finger_mapping(vs_arm.armature_map_pinky_f_r, "LittleFinger", "R", start_index=1)
            build_finger_mapping(vs_arm.armature_map_thumb_f_r, "Thumb", "R", start_index=0)

            old_to_new = {}
            for old_name, new_name in rename_map.items():
                if old_name in bones:
                    bones[old_name].name = new_name
                    old_to_new[old_name] = new_name

            # Update properties with new names
            for attr in dir(vs_arm):
                if not attr.startswith("armature_map_"):
                    continue
                old_val = getattr(vs_arm, attr)
                if old_val in old_to_new:
                    setattr(vs_arm, attr, old_to_new[old_val])

            return old_to_new

        def writeMissingBone(bone_name: str, child_hint: str | None = None):
            """Create a missing bone and its parent if needed.
            child_hint = existing child bone name (used to position the new bone)."""

            existing = arm.data.edit_bones.get(bone_name)
            if existing:
                return existing

            bone_data = boneElems.get(bone_name)
            if not bone_data:
                print(f"[WARN] No JSON entry for '{bone_name}', skipping.")
                return None

            new_bone = arm.data.edit_bones.new(bone_name)

            if child_hint:
                child_bone = arm.data.edit_bones.get(child_hint)
                if child_bone:
                    new_bone.head = child_bone.head.copy()
                    new_bone.tail = child_bone.head + (child_bone.tail - child_bone.head).normalized() * (child_bone.length * 0.5)

                    child_bone.parent = new_bone

                    for col in child_bone.collections:
                        col.assign(new_bone)
                else:
                    new_bone.head = Vector((0, 0, 0))
                    new_bone.tail = Vector((0, 0.1, 0))
            else:
                new_bone.head = Vector((0, 0, 0))
                new_bone.tail = Vector((0, 0.1, 0))

            parent_name = bone_data.get("ParentBone")
            if parent_name and parent_name != bone_name:
                parent_bone = arm.data.edit_bones.get(parent_name) or writeMissingBone(parent_name, child_hint=bone_name)
                if parent_bone:
                    new_bone.parent = parent_bone

            print(f"[CREATE] {bone_name} (Parent: {parent_name})")
            return new_bone

        bone_remapped = remapped_humanoid_armature_bones(arm)
        if not bone_remapped:
            self.report({'WARNING'}, 'Misconfiguration of Bone Remaps!')
            return {'CANCELLED'}

        with PreserveContextMode(arm, 'OBJECT'):
            if arm.animation_data is not None:
                arm.animation_data.action = None

            arm.show_in_front = True
            arm.display_type = 'WIRE'
            arm.data.show_axes = True
            
            applyCurrPoseAsRest(arm)

            default_collection : BoneCollection | None = arm.data.collections.get('Default') # type: ignore
            if default_collection is None:
                if len(arm.data.collections) == 0:
                    default_collection = arm.data.collections.new(name='Default')
                else:
                    default_collection = arm.data.collections[0]

            for bone in arm.pose.bones:
                bone.rotation_mode = 'XYZ'
                bone.lock_location = [False for coord in bone.lock_rotation]
                bone.lock_rotation = [False for coord in bone.lock_rotation]
                bone.lock_rotation_w = False
                bone.lock_scale = [False for coord in bone.lock_scale]

                if len(bone.bone.collections) == 0:
                    default_collection.assign(bone.bone)

            if arm.data.collections_all is None:
                default_collection : BoneCollection = arm.data.collections.new(name='default')

            for pb in arm.pose.bones:
                pb.custom_shape = None
                pb.matrix_basis.identity()

                if pb.bone.collections is None:
                    default_collection.assign(arm.data.bones.get(pb.name))

            bpy.ops.object.mode_set(mode='EDIT')

            for bone in arm.data.edit_bones:
                bone.use_connect = False

            for bone_name, bone_data in boneElems.items():
                bone = arm.data.edit_bones.get(bone_name)

                if bone is None:
                    print(f"[SKIP] {bone_name} not found in armature, Attempt to create.")
                    continue

                parent_name = bone_data.get("ParentBone")
                if parent_name and arm.data.edit_bones.get(parent_name) is None:
                    writeMissingBone(parent_name, child_hint=bone_name)
                else:
                    bone = arm.data.edit_bones.get(bone_name)
                    if parent_name:
                        bone.parent = arm.data.edit_bones.get(parent_name)
                    else: bone.parent = None

                if 'BONE_ROTATION' in self.load_options:
                    rot = bone_data.get("Rotation")
                    roll = bone_data.get("Roll")
                    if rot is not None and roll is not None:
                        rotatedbones = assignBoneAngles(arm, [(bone_name, rot[0], rot[1], rot[2], roll)])
                    elif rot is None and roll is not None:
                        rotatedbones = assignBoneAngles(arm, [(bone_name, None, None, None, roll)])

                    bone = arm.data.edit_bones.get(bone_name)

                    twist_count = bone_data.get("TwistBoneCount")
                    twist_target = bone_data.get("TwistBones")

                    if twist_count is None and twist_target:
                        twist_count = 1

                    if twist_count and twist_count > 0:
                        base_head = bone.head.copy()
                        base_tail = bone.tail.copy()
                        total_vec = base_tail - base_head

                        prev_bone = bone

                        if twist_count == 1:
                            mid_point = base_head + total_vec * 0.5

                            twist_head = mid_point
                            twist_tail = base_tail

                            twist_name = f"{bone_name} twist 1"
                            twistbone = arm.data.edit_bones.get(twist_name)
                            if twistbone:
                                twistbone.head = twist_head
                                twistbone.tail = twist_tail
                                twistbone.roll = bone.roll
                                twistbone.parent = prev_bone
                            else:
                                twistbone = arm.data.edit_bones.new(twist_name)
                                twistbone.head = twist_head
                                twistbone.tail = twist_tail
                                twistbone.roll = bone.roll
                                twistbone.parent = prev_bone

                        else:
                            segment_count = twist_count
                            segment_length = 1.0 / segment_count

                            for i in range(segment_count):
                                factor_start = i * segment_length
                                factor_end = (i + 1) * segment_length

                                twist_head = base_head + total_vec * factor_start
                                twist_tail = base_head + total_vec * factor_end

                                twist_name = f"{bone_name} twist {i+1}"
                                twistbone = arm.data.edit_bones.get(twist_name)
                                if twistbone:
                                    twistbone.head = twist_head
                                    twistbone.tail = twist_tail
                                    twistbone.roll = bone.roll
                                    twistbone.parent = prev_bone
                                else:
                                    twistbone = arm.data.edit_bones.new(twist_name)
                                    twistbone.head = twist_head
                                    twistbone.tail = twist_tail
                                    twistbone.roll = bone.roll
                                    twistbone.parent = prev_bone

                                prev_bone = bone


            bpy.ops.object.mode_set(mode='OBJECT')

            for bone_name, bone_data in boneElems.items():
                pb = arm.pose.bones.get(bone_name)

                if 'BONE_EXROTATION' in self.load_options:
                    if pb:
                        if bone_data.get("ExportRotationOffset") is not None:
                            pb.bone.vs.ignore_rotation_offset = False
                            pb.bone.vs.export_rotation_offset_x = bone_data.get("ExportRotationOffset")[0]
                            pb.bone.vs.export_rotation_offset_y = bone_data.get("ExportRotationOffset")[1]
                            pb.bone.vs.export_rotation_offset_z = bone_data.get("ExportRotationOffset")[2]
                        else:
                            pb.bone.vs.ignore_rotation_offset = True

                if 'EXPORT_NAME' in self.load_options and pb and bone_data.get("ExportName") is not None:
                    pb.bone.vs.export_name = getCanonicalBoneName(bone_data.get("ExportName"))

                if 'CONSTRAINTS' in self.load_options:
                    twist_target = bone_data.get("TwistBones")
                    twist_count = bone_data.get("TwistBoneCount") or 0

                    if twist_count == 0 and twist_target:
                        twist_count = 1

                    twist_bones = [
                        arm.pose.bones.get(f"{bone_name} twist {i+1}".strip())
                        for i in range(twist_count)
                        if arm.pose.bones.get(f"{bone_name} twist {i+1}".strip())
                    ]

                    for idx, pbtwist in enumerate(twist_bones):
                        if not pbtwist:
                            continue

                        offset = bone_data.get("ExportRotationOffset")
                        if offset is not None:
                            pbtwist.bone.vs.ignore_rotation_offset = False
                            pbtwist.bone.vs.export_rotation_offset_x = offset[0]
                            pbtwist.bone.vs.export_rotation_offset_y = offset[1]
                            pbtwist.bone.vs.export_rotation_offset_z = offset[2]
                        else:
                            pbtwist.bone.vs.ignore_rotation_offset = True

                        if twist_target == pbtwist.parent.name:
                            pbtwist.rotation_mode = 'XYZ'
                        else:
                            pbtwist.rotation_mode = 'XYZ'
                            influence = (idx + 1) / twist_count

                            twist_constraint_name : str = f"{bone_name}_twist_constraint_{idx+1}"
                            twist_constraint: Constraint | None = pbtwist.constraints.get(twist_constraint_name) # type: ignore
                            if twist_constraint is None:
                                twist_constraint : Constraint = pbtwist.constraints.new('COPY_ROTATION')
                                twist_constraint.name = twist_constraint_name

                            twist_constraint.target = arm
                            twist_constraint.subtarget = twist_target
                            twist_constraint.use_x = False
                            twist_constraint.use_y = True
                            twist_constraint.use_z = False
                            twist_constraint.owner_space = 'LOCAL'
                            twist_constraint.target_space = 'LOCAL'
                            twist_constraint.influence = influence

                        for col in pb.bone.collections:
                            col.assign(pbtwist.bone)

        self.report({"INFO"}, "Armature Converted successfully.")
        return {"FINISHED"}

class ARMATUREMAPPER_OT_WriteJson(Operator):
    bl_idname : str = "armaturemapper.write_json"
    bl_label : str = "Write Json"
    bl_options : Set = {"INTERNAL", "REGISTER"}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool(is_armature(context.object) and len(context.object.vs.armature_map_bonecollections) > 0)

    def sortItemsByBoneHierarchy(self, ob, items):
        """Return a list of items sorted by bone parent hierarchy."""
        item_bone_map = {}
        for item in items:
            bone = ob.data.bones.get(item.boneExportName)
            if bone:
                item_bone_map[item] = bone

        sorted_items = []
        visited = set()

        def dfs(bone):
            if bone in visited:
                return
            visited.add(bone)
            for itm, b in item_bone_map.items():
                if b == bone:
                    sorted_items.append(itm)
                    break
            for child in bone.children:
                dfs(child)

        for bone in ob.data.bones:
            if bone.parent is None:
                dfs(bone)

        return sorted_items

    def execute(self, context : Context) -> Set:
        if not self.filepath:
            self.report({'ERROR'}, "No file path set")
            return {'CANCELLED'}

        if not self.filepath.lower().endswith(".json"):
            self.report({'ERROR'}, "File must have a .json extension")
            return {'CANCELLED'}

        ob : Object | None = context.object
        items = ob.vs.armature_map_bonecollections
        skipped_count = 0

        # Build item_map with original collection index
        item_map = {i.boneExportName: (i, idx) for idx, i in enumerate(items)}

        # Sort items by hierarchy (parents first)
        sorted_items = self.sortItemsByBoneHierarchy(ob, items)
        sorted_items.reverse()  # children-first processing

        bone_entries = []

        with PreserveContextMode(ob, 'EDIT'):
            # First pass: build entries without ParentBone
            for item in sorted_items:
                if not item.boneName.strip():
                    skipped_count += 1
                    continue

                bone = ob.data.bones.get(item.boneExportName)
                if not bone:
                    skipped_count += 1
                    continue

                editbone = ob.data.edit_bones.get(item.boneExportName)
                ebone_roll = editbone.roll if editbone else 0.0

                boneDict = {
                    "BoneName": item.boneName,
                    "ExportName": item.boneExportName
                }

                if item.writeRotation == 'ROTATION':
                    tail_offset = bone.tail_local - bone.head_local
                    boneDict['Rotation'] = [tail_offset.x, tail_offset.y, tail_offset.z]
                    boneDict['Roll'] = ebone_roll
                elif item.writeRotation == 'ROLL':
                    boneDict['Roll'] = ebone_roll

                if item.writeExportRotationOffset and not bone.vs.ignore_rotation_offset:
                    boneDict['ExportRotationOffset'] = [
                        bone.vs.export_rotation_offset_x,
                        bone.vs.export_rotation_offset_y,
                        bone.vs.export_rotation_offset_z
                    ]

                if item.writeTwistBone:
                    twist_name = item.twistBoneTarget.strip() or (
                        item_map.get(bone.parent.name, (None, 0))[0].boneName
                        if bone.parent and bone.parent.name in item_map else None
                    )
                    if twist_name:
                        boneDict['TwistBones'] = twist_name
                        boneDict['TwistBoneCount'] = item.twistBoneCount

                bone_entries.append(boneDict)

        # Second pass: assign ParentBone properly
        exportname_to_bonename = {i.boneExportName: i.boneName for i in items if i.boneName.strip()}

        for b_entry in bone_entries:
            item = item_map[b_entry['ExportName']][0]
            bone = ob.data.bones.get(item.boneExportName)

            if item.parentBone.strip():  # use property if set
                b_entry['ParentBone'] = item.parentBone
            elif bone and bone.parent:
                parent_item = item_map.get(bone.parent.name)
                if parent_item and parent_item[0].boneName.strip():
                    b_entry['ParentBone'] = parent_item[0].boneName
                else:
                    b_entry['ParentBone'] = bone.parent.name

        # Sort bone_entries to match original collection order
        bone_entries.sort(key=lambda b: item_map[b['ExportName']][1])

        # Write JSON
        if bone_entries:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(bone_entries, f, indent=4)
            self.report({'INFO'}, f"Exported JSON to: {self.filepath} | Skipped {skipped_count} bone(s)")
        else:
            self.report({'WARNING'}, f"No bones exported. Skipped {skipped_count} bone(s)")

        return {'FINISHED'}


    def invoke(self, context : Context, event : Event) -> Set:
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class ARMATUREMAPPER_OT_RemoveItem(Operator):
    bl_idname : str = "armaturemapper.remove_item"
    bl_label : str = "Remove Bone"
    bl_options : Set = {'REGISTER', 'UNDO', 'INTERNAL'}

    index: IntProperty()

    def execute(self, context : Context) -> Set:
        coll = context.object.vs.armature_map_bonecollections
        if 0 <= self.index < len(coll):
            coll.remove(self.index)
        return {'FINISHED'}

class ARMATUREMAPPER_OT_AddItem(Operator):
    bl_idname : str = "armaturemapper.add_item"
    bl_label : str = "Add Bone"
    bl_options : Set = {'REGISTER', 'UNDO', 'INTERNAL'}

    add_type: bpy.props.EnumProperty(items=[
        ('SELECTED', 'Selected', 'Add all selected bones'),
        ('SINGLE', 'Single', 'Add an empty item')
    ])

    def execute(self, context : Context) -> Set:
        ob : Object | None = context.object
        if not ob or ob.type != 'ARMATURE':
            self.report({'ERROR'}, "Active object must be an armature")
            return {'CANCELLED'}

        collection = ob.vs.armature_map_bonecollections

        if self.add_type == 'SINGLE':
            collection.add()
            return {'FINISHED'}

        if context.mode != 'POSE':
            self.report({'ERROR'}, "Must be in Pose mode to add selected bones")
            return {'CANCELLED'}

        existing_names = {item.boneExportName for item in collection if hasattr(item, "boneExportName")}
        skipped = 0

        for pb in context.selected_pose_bones:
            if pb.name in existing_names:
                skipped += 1
                continue
            item = collection.add()
            if 'boneExportName' in item.bl_rna.properties:
                item.boneExportName = pb.name

        if skipped > 0:
            self.report({'INFO'}, f"Skipped {skipped} already existing bone(s)")

        return {'FINISHED'}

class ARMATUREMAPPER_UL_BoneList(UIList):
    def draw_item(self, context: Context, layout: UILayout, data: Any | None, item: Any | None, icon: int | None, active_data: Any, active_property: str | None, index: int | None, flt_flag: int | None) -> None:
        if item:
            row = layout.row()
            split = row.split(factor=0.9)
            split.prop_search(item, "boneExportName", context.object.data, "bones", text="")
            split.label(text="", )
            row.operator(ARMATUREMAPPER_OT_RemoveItem.bl_idname, text="", icon="X").index = index