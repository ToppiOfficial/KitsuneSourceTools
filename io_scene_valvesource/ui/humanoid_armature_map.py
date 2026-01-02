import os
import json
from typing import Set, Any

import bpy
from bpy.types import Context, Object, Operator, UILayout, UIList, Event, Constraint, BoneCollection
from bpy.props import EnumProperty, IntProperty, StringProperty, BoolProperty
from mathutils import Vector

from ..core.armatureutils import (
    preserve_context_mode,
    assign_bone_headtip_positions,
    get_armature,
    get_canonical_bonename,
    apply_current_pose_as_restpose,
    remove_bone, merge_bones
)
from ..core.boneutils import get_armature, get_canonical_bonename
from ..core.commonutils import (
    draw_title_box_layout,
    draw_wrapped_texts,
    is_armature, draw_toggleable_layout,
    get_selected_bones
)

from ..core.meshutils import get_armature
from ..flex import get_id
from ..utils import print

from .common import Tools_SubCategoryPanel

class HUMANOIDARMATUREMAP_PT_Panel(Tools_SubCategoryPanel):
    bl_label : str = 'Humanoid Armature Mapper'

    def draw(self, context : Context) -> None:
        l : UILayout = self.layout
        bx : UILayout = draw_title_box_layout(l, HUMANOIDARMATUREMAP_PT_Panel.bl_label, icon='ARMATURE_DATA')

        ob : Object | None = context.object
        if is_armature(ob): pass
        else:
            draw_wrapped_texts(bx,get_id("panel_select_armature"),max_chars=40 , icon='HELP')
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
        
        armaturemappersection = draw_toggleable_layout(col, context.scene.vs, 'show_armaturemapper_help', f'Show Help', '')
        if armaturemappersection is not None:
            draw_wrapped_texts(armaturemappersection,"When saving a bone preset, the current Blender bone name becomes the export name, and the target name is the bone that the preset will apply to when loaded. For example, if the bone name is Spine1 and the target name is Waist then Spine1 will be the export name and the JSON will look for the Waist bone on the armature and apply the preset there.  It is recommended to name the target bone based on the 'WRITE' format for Humanoid",max_chars=40 , icon='HELP',boxed=False)
            
        col = layout.column()
        col.operator(HUMANOIDARMATUREMAP_OT_LoadPreset.bl_idname)

        col = layout.column(align=False)
        row = layout.row()
        row.template_list(
            "HUMANOIDARMATUREMAP_UL_ConfigList",
            "",
            context.object.vs,
            "humanoid_armature_map_bonecollections",
            context.object.vs,
            "humanoid_armature_map_bonecollections_index",
            rows=3
        )
        row = layout.row()
        row.scale_y = 1.25
        split = row.split(factor=0.4,align=True)
        split.operator(HUMANOIDARMATUREMAP_OT_AddItem.bl_idname, icon="ADD", text=HUMANOIDARMATUREMAP_OT_AddItem.bl_label).add_type = 'SINGLE'
        split.operator(HUMANOIDARMATUREMAP_OT_AddItem.bl_idname, icon="ADD", text=HUMANOIDARMATUREMAP_OT_AddItem.bl_label + " (Selected Bones)").add_type = 'SELECTED'

        if 0 <= context.object.vs.humanoid_armature_map_bonecollections_index < len(context.object.vs.humanoid_armature_map_bonecollections):
            self.draw_bone_item_properties(context, layout)

        layout.operator(HUMANOIDARMATUREMAP_OT_WriteConfig.bl_idname, icon='FILE')

    def draw_bone_item_properties(self, context : Context, layout : UILayout) -> None:
        item = context.object.vs.humanoid_armature_map_bonecollections[context.object.vs.humanoid_armature_map_bonecollections_index]

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

    def get_bone_assignments(self, context : Context) -> dict:
        assignments = {}
        vs = context.object.vs
        
        bone_props = [
            ('armature_map_head', 'Head'),
            ('armature_map_chest', 'Chest'),
            ('armature_map_spine', 'Spine'),
            ('armature_map_pelvis', 'Pelvis'),
            ('armature_map_eye_l', 'Eye L'),
            ('armature_map_eye_r', 'Eye R'),
            ('armature_map_thigh_l', 'Thigh L'),
            ('armature_map_thigh_r', 'Thigh R'),
            ('armature_map_knee_l', 'Knee L'),
            ('armature_map_knee_r', 'Knee R'),
            ('armature_map_ankle_l', 'Ankle L'),
            ('armature_map_ankle_r', 'Ankle R'),
            ('armature_map_toe_l', 'Toe L'),
            ('armature_map_toe_r', 'Toe R'),
            ('armature_map_shoulder_l', 'Shoulder L'),
            ('armature_map_shoulder_r', 'Shoulder R'),
            ('armature_map_upperarm_l', 'UpperArm L'),
            ('armature_map_upperarm_r', 'UpperArm R'),
            ('armature_map_forearm_l', 'ForeArm L'),
            ('armature_map_forearm_r', 'ForeArm R'),
            ('armature_map_wrist_l', 'Wrist L'),
            ('armature_map_wrist_r', 'Wrist R'),
            ('armature_map_thumb_f_l', 'Thumb L'),
            ('armature_map_thumb_f_r', 'Thumb R'),
            ('armature_map_index_f_l', 'Index L'),
            ('armature_map_index_f_r', 'Index R'),
            ('armature_map_middle_f_l', 'Middle L'),
            ('armature_map_middle_f_r', 'Middle R'),
            ('armature_map_ring_f_l', 'Ring L'),
            ('armature_map_ring_f_r', 'Ring R'),
            ('armature_map_pinky_f_l', 'Pinky L'),
            ('armature_map_pinky_f_r', 'Pinky R'),
        ]
        
        for prop, label in bone_props:
            bone_name = getattr(vs, prop, "").strip()
            if bone_name:
                if bone_name not in assignments:
                    assignments[bone_name] = []
                assignments[bone_name].append(label)
        
        return assignments

    def draw_read_mode(self, context : Context, layout : UILayout) -> None:
        col = layout.column(align=False)
        
        message = [
            'This will rename bones to a standardized format.',
            'Bone map includes:\n',
            '- Core: Hips, Chest, Head\n',
            '- Arms: Shoulder, UpperArm, ForeArm, Wrist\n',
            '- Legs: Thigh, Knee, Ankle, Toe\n',
            '- Fingers: Index/Middle/Ring/LittleFinger1-3_L/R\n',
            '- Thumbs: Thumb0-2_L/R\n',
            '\nEnable "Remove Intermediate Bones" to merge bones between mapped limbs.'
        ]
        
        armaturemappersection = draw_toggleable_layout(col, context.scene.vs, 'show_armaturemapper_help', f'Show Help', '')
        if armaturemappersection is not None:
            draw_wrapped_texts(armaturemappersection,message,max_chars=40, icon='HELP',boxed=False)
        
        bone_assignments = self.get_bone_assignments(context)
        duplicates = {bone: labels for bone, labels in bone_assignments.items() if len(labels) > 1}
        
        if duplicates:
            duplicate_messages = []
            for bone, labels in duplicates.items():
                duplicate_messages.append(f"'{bone}' assigned to: {', '.join(labels)}")
            
            draw_wrapped_texts(
                layout,
                duplicate_messages,
                max_chars=40,
                icon='ERROR',
                alert=True,
                boxed=True,
                title='Duplicate Bone Assignments Detected!'
            )
        
        self.draw_humanoid_bone_mapping(context, layout, duplicates)

        layout.operator(HUMANOIDARMATUREMAP_OT_LoadConfig.bl_idname)

    def draw_humanoid_bone_mapping(self, context : Context, layout : UILayout, duplicates : dict) -> None:
        col = layout.column(align=True)
        
        bx = col.box()
        col = bx.column()

        draw_wrapped_texts(col,text='Head, Chest and Pelvis are required', icon='HELP')
        
        col = bx.column(align=True)
        self.draw_bone_prop(col, context, 'armature_map_head', "Head", duplicates)
        self.draw_bone_prop(col, context, 'armature_map_chest', "Chest", duplicates)
        self.draw_bone_prop(col, context, 'armature_map_spine', "Spine", duplicates)
        self.draw_bone_prop(col, context, 'armature_map_pelvis', "Pelvis", duplicates)

        col.separator()
        col.separator(type='LINE')
        col.separator()

        self.draw_bone_pair(col, context, 'Eye', 'armature_map_eye_l', 'armature_map_eye_r', duplicates)

        col.separator()
        col.separator(type='LINE')
        col.separator()

        col.label(text="Legs:")
        self.draw_bone_pair(col, context, 'Thigh', 'armature_map_thigh_l', 'armature_map_thigh_r', duplicates)
        self.draw_bone_pair(col, context, 'Knee', 'armature_map_knee_l', 'armature_map_knee_r', duplicates)
        self.draw_bone_pair(col, context, 'Ankle', 'armature_map_ankle_l', 'armature_map_ankle_r', duplicates)
        self.draw_bone_pair(col, context, 'Toe', 'armature_map_toe_l', 'armature_map_toe_r', duplicates)

        col.separator()
        col.separator(type='LINE')
        col.separator()

        col.label(text="Arms:")
        self.draw_bone_pair(col, context, 'Shoulder', 'armature_map_shoulder_l', 'armature_map_shoulder_r', duplicates)
        self.draw_bone_pair(col, context, 'UpperArm', 'armature_map_upperarm_l', 'armature_map_upperarm_r', duplicates)
        self.draw_bone_pair(col, context, 'ForeArm', 'armature_map_forearm_l', 'armature_map_forearm_r', duplicates)
        self.draw_bone_pair(col, context, 'Wrist', 'armature_map_wrist_l', 'armature_map_wrist_r', duplicates)

        col.separator()
        col.separator(type='LINE')
        col.separator()

        col.label(text="Fingers:")
        self.draw_bone_pair(col, context, 'Thumb', 'armature_map_thumb_f_l', 'armature_map_thumb_f_r', duplicates)
        self.draw_bone_pair(col, context, 'Index', 'armature_map_index_f_l', 'armature_map_index_f_r', duplicates)
        self.draw_bone_pair(col, context, 'Middle', 'armature_map_middle_f_l', 'armature_map_middle_f_r', duplicates)
        self.draw_bone_pair(col, context, 'Ring', 'armature_map_ring_f_l', 'armature_map_ring_f_r', duplicates)
        self.draw_bone_pair(col, context, 'Pinky', 'armature_map_pinky_f_l', 'armature_map_pinky_f_r', duplicates)

    def draw_bone_prop(self, layout : UILayout, context : Context, prop : str, text : str, duplicates : dict) -> None:
        bone_name = getattr(context.object.vs, prop, "").strip()
        layout.alert = bone_name in duplicates
        layout.prop_search(context.object.vs, prop, context.object.data, "bones", text=text)
        layout.alert = False

    def draw_bone_pair(self, layout : UILayout, context : Context, label : str, prop_l : str, prop_r : str, duplicates : dict = None) -> None:
        if duplicates is None:
            duplicates = {}
        
        row = layout.row(align=True)
        row.scale_x = 0.2
        row.label(text=f'{label} L & R')
        
        bone_l = getattr(context.object.vs, prop_l, "").strip()
        bone_r = getattr(context.object.vs, prop_r, "").strip()
        
        row.alert = bone_l in duplicates
        row.prop_search(context.object.vs, prop_l, context.object.data, "bones", text="")
        row.alert = bone_r in duplicates
        row.prop_search(context.object.vs, prop_r, context.object.data, "bones", text="")
        row.alert = False

class HUMANOIDARMATUREMAP_OT_LoadPreset(Operator):
    bl_idname : str = "humanoidarmaturemap.load_preset"
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

        items = ob.vs.humanoid_armature_map_bonecollections
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
                print(f'- Skipping {bone_name}')
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

class HUMANOIDARMATUREMAP_OT_LoadConfig(Operator):
    bl_idname: str = "humanoidarmaturemap.load_json"
    bl_label: str = "Load JSON"
    bl_options: Set = {"REGISTER", "UNDO"}

    filepath: StringProperty(subtype="FILE_PATH")

    load_options: EnumProperty(
        name="Load Options",
        description="Select which parts of the JSON to load",
        items=[
            ("EXPORT_NAME", "Export Name", "Load bone export names"),
            ("BONE_EXROTATION", "Bone Export Rotation", "Load export rotation offsets"),
            ("BONE_ROTATION", "Bone Rotation", "Load bone rotations"),
            ("CONSTRAINTS", "Constraints", "Create twist bone constraints"),
            ("TWIST_BONES", "Twist Bones", "Create twist bones"),
            ("HIERARCHY", "Hierarchy", "Update bone parent relationships"),
            ("MISSING_BONES", "Missing Bones", "Create bones that don't exist in armature"),
            ("RESCALE_BONES", "Rescale Bones", "Align bone tails to child heads based on hierarchy")
        ],
        default={"EXPORT_NAME", "BONE_EXROTATION", "BONE_ROTATION", "CONSTRAINTS", "TWIST_BONES", "HIERARCHY", "MISSING_BONES", "RESCALE_BONES"},
        options={"ENUM_FLAG"}
    )

    remove_intermediate_bones: BoolProperty(
        name="Remove Intermediate Bones",
        description="Remove bones between mapped limb bones (e.g., between UpperArm and ForeArm)",
        default=True
    )

    def draw(self, context: Context) -> None:
        layout = self.layout
        col = layout.column(align=True)
        col.label(text="Select parts to load:")
        
        box = col.box()
        box.label(text="Bone Properties:")
        subcol = box.column(align=True)
        subcol.prop_enum(self, "load_options", "EXPORT_NAME")
        subcol.prop_enum(self, "load_options", "BONE_EXROTATION")
        subcol.prop_enum(self, "load_options", "BONE_ROTATION")
        
        box = col.box()
        box.label(text="Twist Bones:")
        subcol = box.column(align=True)
        subcol.prop_enum(self, "load_options", "TWIST_BONES")
        subcol.prop_enum(self, "load_options", "CONSTRAINTS")
        
        box = col.box()
        box.label(text="Structure:")
        subcol = box.column(align=True)
        subcol.prop_enum(self, "load_options", "HIERARCHY")
        subcol.prop_enum(self, "load_options", "MISSING_BONES")
        subcol.prop_enum(self, "load_options", "RESCALE_BONES")
        
        col.separator()
        col.prop(self, "remove_intermediate_bones")

    def invoke(self, context: Context, event: Event) -> Set:
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context: Context) -> Set:
        if not self.filepath.lower().endswith(".json"):
            self.report({"ERROR"}, "Please select a JSON file")
            return {"CANCELLED"}

        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            self.report({"ERROR"}, f"Failed to load JSON: {e}")
            return {"CANCELLED"}

        bone_elements = {entry["BoneName"]: entry for entry in data}

        arm = get_armature(context.object)
        if arm is None:
            self.report({"ERROR"}, "No valid armature selected")
            return {"CANCELLED"}

        old_to_new = self._remap_humanoid_bones(arm)
        if not old_to_new:
            self.report({'WARNING'}, 'Misconfiguration of Bone Remaps!')
            return {'CANCELLED'}

        self._setup_armature(arm, bone_elements)
        self.report({"INFO"}, "Armature converted successfully.")
        return {"FINISHED"}
    
    def _apply_temp_renames_to_mapped_bones(self, arm: Object, vs_arm, bones, bone_elements: dict) -> dict:
        temp_prefix = "__MAPPED__"
        existing_prefix = "__EXISTING__"
        mapped_bones = {}
        
        # Collect all target bone names from JSON
        json_bone_names = set(bone_elements.keys())
        
        # First, rename any existing bones that conflict with JSON bone names
        for bone in bones:
            if bone.name in json_bone_names and bone.name not in [getattr(vs_arm, attr) for attr in dir(vs_arm) if attr.startswith("armature_map_")]:
                temp_name = f"{existing_prefix}{bone.name}"
                print(f"[PRE-EXISTING] Conflicting bone '{bone.name}' -> '{temp_name}'")
                bones[bone.name].name = temp_name
        
        # Then, rename all mapped bones
        for attr in dir(vs_arm):
            if not attr.startswith("armature_map_"):
                continue
            bone_name = getattr(vs_arm, attr)
            if bone_name and isinstance(bone_name, str) and bone_name in bones:
                temp_name = f"{temp_prefix}{bone_name}"
                bones[bone_name].name = temp_name
                setattr(vs_arm, attr, temp_name)
                mapped_bones[bone_name] = temp_name
                print(f"[PRE-TEMP] Mapped bone '{bone_name}' -> '{temp_name}'")
        
        return mapped_bones

    def _remap_humanoid_bones(self, arm: Object) -> dict | bool:
        vs_arm = getattr(arm, "vs", None)
        if not vs_arm:
            return False

        bones = arm.data.bones

        if not self._validate_bone_mapping(arm, vs_arm):
            return False

        # Need to load bone_elements early for conflict detection
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            bone_elements = {entry["BoneName"]: entry for entry in data}
        except:
            bone_elements = {}

        self.mapped_bones_lookup = self._apply_temp_renames_to_mapped_bones(arm, vs_arm, bones, bone_elements)

        rename_map = self._build_rename_map(vs_arm, bones)
        
        if self.remove_intermediate_bones:
            self._remove_intermediate_limb_bones(arm, vs_arm, rename_map)

        return self._apply_renames(arm, vs_arm, rename_map, bones)

    def _validate_bone_mapping(self, arm: Object, vs_arm) -> bool:
        bone_props = [attr for attr in dir(vs_arm) if attr.startswith("armature_map_")]
        bone_values = [getattr(vs_arm, prop) for prop in bone_props]
        
        if all(not v for v in bone_values):
            return True

        selected_bones = [v for v in bone_values if v and isinstance(v, str) and v in arm.data.bones]
        seen, duplicates = set(), set()
        
        for bone in selected_bones:
            if bone in seen:
                duplicates.add(bone)
            else:
                seen.add(bone)
        
        if duplicates:
            print(f"[Humanoid Rename] Conflicting assignments: {duplicates}")
            return False
        
        return True

    def _build_rename_map(self, vs_arm, bones) -> dict:
        rename_map = {}
        
        if self._is_valid_bone(vs_arm.armature_map_eye_l, bones):
            rename_map[vs_arm.armature_map_eye_l] = "Left eye"
        if self._is_valid_bone(vs_arm.armature_map_eye_r, bones):
            rename_map[vs_arm.armature_map_eye_r] = "Right eye"

        self._map_spine_chain(bones, vs_arm.armature_map_pelvis, vs_arm.armature_map_spine, vs_arm.armature_map_chest, rename_map)
        self._map_neck_chain(bones, vs_arm.armature_map_chest, vs_arm.armature_map_head, rename_map)

        limb_mappings = [
            (vs_arm.armature_map_thigh_l, "Left leg"),
            (vs_arm.armature_map_knee_l, "Left knee"),
            (vs_arm.armature_map_ankle_l, "Left ankle"),
            (vs_arm.armature_map_toe_l, "Left toe"),
            (vs_arm.armature_map_thigh_r, "Right leg"),
            (vs_arm.armature_map_knee_r, "Right knee"),
            (vs_arm.armature_map_ankle_r, "Right ankle"),
            (vs_arm.armature_map_toe_r, "Right toe"),
            (vs_arm.armature_map_shoulder_l, "Left shoulder"),
            (vs_arm.armature_map_upperarm_l, "Left arm"),
            (vs_arm.armature_map_forearm_l, "Left elbow"),
            (vs_arm.armature_map_wrist_l, "Left wrist"),
            (vs_arm.armature_map_shoulder_r, "Right shoulder"),
            (vs_arm.armature_map_upperarm_r, "Right arm"),
            (vs_arm.armature_map_forearm_r, "Right elbow"),
            (vs_arm.armature_map_wrist_r, "Right wrist"),
        ]
        
        for bone_name, target_name in limb_mappings:
            if self._is_valid_bone(bone_name, bones):
                rename_map[bone_name] = target_name

        finger_mappings = [
            (vs_arm.armature_map_index_f_l, "IndexFinger", "L"),
            (vs_arm.armature_map_middle_f_l, "MiddleFinger", "L"),
            (vs_arm.armature_map_ring_f_l, "RingFinger", "L"),
            (vs_arm.armature_map_pinky_f_l, "LittleFinger", "L"),
            (vs_arm.armature_map_thumb_f_l, "Thumb", "L"),
            (vs_arm.armature_map_index_f_r, "IndexFinger", "R"),
            (vs_arm.armature_map_middle_f_r, "MiddleFinger", "R"),
            (vs_arm.armature_map_ring_f_r, "RingFinger", "R"),
            (vs_arm.armature_map_pinky_f_r, "LittleFinger", "R"),
            (vs_arm.armature_map_thumb_f_r, "Thumb", "R"),
        ]
        
        for start_name, base, side in finger_mappings:
            if self._is_valid_bone(start_name, bones):
                self._map_finger_chain(bones, start_name, base, side, rename_map)

        return rename_map

    def _map_finger_chain(self, bones, start_name: str, base: str, side: str, rename_map: dict) -> None:
        bone = bones[start_name]
        chain = []
        start_idx = 0 if base == "Thumb" else 1
        
        while bone:
            chain.append(bone)
            bone = bone.children[0] if bone.children else None

        for i, bone in enumerate(chain):
            rename_map[bone.name] = f"{base}{i+start_idx}_{side}"

    def _collect_chain(self, bones, start_name: str, end_name: str) -> list:
        if not (self._is_valid_bone(start_name, bones) and self._is_valid_bone(end_name, bones)):
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
        return chain if not dfs(start_bone, end_bone, chain) else chain

    def _map_spine_chain(self, bones, pelvis_name: str, spine_name: str, chest_name: str, rename_map: dict) -> None:
        chain = self._collect_chain(bones, pelvis_name, chest_name)
        if len(chain) < 2:
            return

        spine_idx = None
        if self._is_valid_bone(spine_name, bones):
            for idx, bone in enumerate(chain):
                if bone.name == spine_name:
                    spine_idx = idx
                    break

        middle_count = len(chain) - 2
        names = ["Hips"]
        
        if spine_idx:
            lower_count = spine_idx - 1
            upper_count = middle_count - spine_idx
            
            if lower_count == 1:
                names.append("Lower Spine")
            elif lower_count > 1:
                names.append("Lower Spine")
                names.extend([f"Lower Spine {i+1}" for i in range(lower_count - 1)])
            
            names.append("Spine")
            
            if upper_count == 1:
                names.append("Lower Chest")
            elif upper_count > 1:
                names.append("Lower Chest")
                names.extend([f"Lower Chest {i+1}" for i in range(upper_count - 1)])
        else:
            if middle_count == 1:
                names.append("Spine")
            elif middle_count == 2:
                names.extend(["Lower Spine", "Spine"])
            elif middle_count == 3:
                names.extend(["Lower Spine", "Spine", "Lower Chest"])
            else:
                names.extend(["Lower Spine", "Spine", "Lower Chest"])
                names.extend([f"Spine_{i+1}" for i in range(middle_count - 3)])
        
        names.append("Chest")

        for bone, new_name in zip(chain, names):
            rename_map[bone.name] = new_name

    def _map_neck_chain(self, bones, chest_name: str, head_name: str, rename_map: dict) -> None:
        chain = self._collect_chain(bones, chest_name, head_name)
        if len(chain) < 2:
            return

        for i, bone in enumerate(chain[1:-1], 1):
            rename_map[bone.name] = "Neck" if i == 1 else f"Neck_{i-1}"
        rename_map[head_name] = "Head"

    def _remove_intermediate_limb_bones(self, arm: Object, vs_arm, rename_map: dict) -> None:
        prev_mode = arm.mode
        if bpy.context.object != arm:
            bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode='EDIT')

        limb_pairs = [
            (vs_arm.armature_map_thigh_l, vs_arm.armature_map_knee_l),
            (vs_arm.armature_map_knee_l, vs_arm.armature_map_ankle_l),
            (vs_arm.armature_map_thigh_r, vs_arm.armature_map_knee_r),
            (vs_arm.armature_map_knee_r, vs_arm.armature_map_ankle_r),
            (vs_arm.armature_map_upperarm_l, vs_arm.armature_map_forearm_l),
            (vs_arm.armature_map_forearm_l, vs_arm.armature_map_wrist_l),
            (vs_arm.armature_map_upperarm_r, vs_arm.armature_map_forearm_r),
            (vs_arm.armature_map_forearm_r, vs_arm.armature_map_wrist_r),
        ]

        edit_bones = arm.data.edit_bones
        
        for start_name, end_name in limb_pairs:
            if not (start_name and end_name):
                continue
            
            start_bone = edit_bones.get(start_name)
            end_bone = edit_bones.get(end_name)
            
            if not (start_bone and end_bone):
                continue

            intermediates = self._find_intermediate_bones(start_bone, end_bone)
            
            if intermediates:
                print(f"[MERGE] Removing {len(intermediates)} bones between {start_name} and {end_name}")
                
                for intermediate in intermediates:
                    merge_bones(arm, start_bone, intermediate, keep_bone=False)
                
                bones_to_remove = [bone.name for bone in intermediates]
                remove_bone(arm, bones_to_remove)

        bpy.ops.object.mode_set(mode=prev_mode)

    def _find_intermediate_bones(self, start_bone, end_bone) -> list:
        intermediates = []
        current = start_bone
        
        while current.children:
            if len(current.children) != 1:
                break
            
            child = current.children[0]
            if child == end_bone:
                break
            
            intermediates.append(child)
            current = child
        
        return intermediates

    def _apply_renames(self, arm: Object, vs_arm, rename_map: dict, bones) -> dict:
        old_to_new = {}
        for old_name, new_name in rename_map.items():
            if old_name in bones:
                bones[old_name].name = new_name
                old_to_new[old_name] = new_name

        for attr in dir(vs_arm):
            if not attr.startswith("armature_map_"):
                continue
            old_val = getattr(vs_arm, attr)
            if old_val in old_to_new:
                setattr(vs_arm, attr, old_to_new[old_val])

        return old_to_new

    def _is_valid_bone(self, name: str, bones) -> bool:
        return bool(name) and isinstance(name, str) and name in bones

    def _setup_armature(self, arm: Object, bone_elements: dict) -> None:
        with preserve_context_mode(arm, 'OBJECT'):
            if arm.animation_data is not None:
                arm.animation_data.action = None

            arm.show_in_front = True
            arm.display_type = 'WIRE'
            arm.data.show_axes = True
            
            apply_current_pose_as_restpose(arm)

            default_collection = self._ensure_default_collection(arm)
            self._prepare_pose_bones(arm, default_collection)
            self._process_bones_edit_mode(arm, bone_elements)
            self._process_bones_object_mode(arm, bone_elements)

    def _ensure_default_collection(self, arm: Object) -> BoneCollection:
        default_collection = arm.data.collections.get('Default')
        if default_collection is None:
            default_collection = arm.data.collections.new(name='Default')
        return default_collection

    def _prepare_pose_bones(self, arm: Object, default_collection: BoneCollection) -> None:
        for bone in arm.pose.bones:
            bone.rotation_mode = 'XYZ'
            bone.lock_location = [False] * 3
            bone.lock_rotation = [False] * 3
            bone.lock_rotation_w = False
            bone.lock_scale = [False] * 3
            bone.custom_shape = None
            bone.matrix_basis.identity()

            if not bone.bone.collections:
                default_collection.assign(bone.bone)

    def _process_bones_edit_mode(self, arm: Object, bone_elements: dict) -> None:
        bpy.ops.object.mode_set(mode='EDIT')

        for bone in arm.data.edit_bones:
            bone.use_connect = False

        for bone_name, bone_data in bone_elements.items():
            bone = arm.data.edit_bones.get(bone_name)
            if bone is None:
                if not self._has_children_in_json(bone_name, bone_elements):
                    print(f"[SKIP] {bone_name} is a terminal bone with no children, ignoring")
                    continue
                
                if 'MISSING_BONES' in self.load_options:
                    print(f"[SKIP] {bone_name} not found in armature, attempting to create.")
                    bone = self._write_missing_bone(arm, bone_name, None, bone_elements)
                    if bone is None:
                        continue
                else:
                    print(f"[SKIP] {bone_name} not found (MISSING_BONES disabled)")
                    continue

            if 'HIERARCHY' in self.load_options:
                self._setup_bone_parent(arm, bone, bone_name, bone_data, bone_elements)
            
            if 'RESCALE_BONES' in self.load_options:
                self._rescale_bone_to_children(arm, bone, bone_name, bone_elements)
            
            self._setup_bone_rotation(arm, bone, bone_name, bone_data)
            
            if 'TWIST_BONES' in self.load_options:
                self._setup_twist_bones(arm, bone, bone_name, bone_data)

        bpy.ops.object.mode_set(mode='OBJECT')

    def _rescale_bone_to_children(self, arm: Object, bone, bone_name: str, bone_elements: dict) -> None:
        children_in_json = [
            arm.data.edit_bones.get(check_name)
            for check_name, check_data in bone_elements.items()
            if check_data.get("ParentBone") == bone_name and arm.data.edit_bones.get(check_name)
        ]

        if not children_in_json:
            return

        target_child = None
        
        if bone_name == "Hips":
            target_child = next((c for c in children_in_json if "Spine" in c.name), None)

        if target_child:
            new_tail = target_child.head.copy()
        elif len(children_in_json) == 1:
            new_tail = children_in_json[0].head.copy()
        else:
            new_tail = sum((child.head for child in children_in_json), Vector((0, 0, 0))) / len(children_in_json)

        if (new_tail - bone.head).length < 0.001:
            return

        bone.tail = new_tail

    def _setup_bone_parent(self, arm: Object, bone, bone_name: str, bone_data: dict, bone_elements: dict) -> None:
        parent_name = bone_data.get("ParentBone")
        if parent_name:
            parent_bone = arm.data.edit_bones.get(parent_name)
            if parent_bone is None and 'MISSING_BONES' in self.load_options:
                parent_bone = self._write_missing_bone(arm, parent_name, bone_name, bone_elements)
            if parent_bone:
                bone.parent = parent_bone
        else:
            bone.parent = None

    def _setup_bone_rotation(self, arm: Object, bone, bone_name: str, bone_data: dict) -> None:
        if 'BONE_ROTATION' not in self.load_options:
            return

        rot = bone_data.get("Rotation")
        roll = bone_data.get("Roll")
        
        if rot is not None and roll is not None:
            assign_bone_headtip_positions(arm, [(bone_name, rot[0], rot[1], rot[2], roll)])
        elif roll is not None:
            assign_bone_headtip_positions(arm, [(bone_name, None, None, None, roll)])

    def _setup_twist_bones(self, arm: Object, bone, bone_name: str, bone_data: dict) -> None:
        twist_count = bone_data.get("TwistBoneCount") or (1 if bone_data.get("TwistBones") else 0)
        if twist_count <= 0:
            return

        bone = arm.data.edit_bones.get(bone_name)
        base_head = bone.head.copy()
        base_tail = bone.tail.copy()
        total_vec = base_tail - base_head

        if twist_count == 1:
            self._create_single_twist_bone(arm, bone, bone_name, base_head, total_vec)
        else:
            self._create_multiple_twist_bones(arm, bone, bone_name, base_head, total_vec, twist_count)

    def _create_single_twist_bone(self, arm: Object, bone, bone_name: str, base_head, total_vec) -> None:
        mid_point = base_head + total_vec * 0.5
        twist_name = f"{bone_name} twist 1"
        
        twistbone = arm.data.edit_bones.get(twist_name)
        if not twistbone:
            twistbone = arm.data.edit_bones.new(twist_name)
        
        twistbone.head = mid_point
        twistbone.tail = base_head + total_vec
        twistbone.roll = bone.roll
        twistbone.parent = bone

    def _create_multiple_twist_bones(self, arm: Object, bone, bone_name: str, base_head, total_vec, twist_count: int) -> None:
        segment_length = 1.0 / twist_count
        prev_bone = bone

        for i in range(twist_count):
            factor_start = i * segment_length
            factor_end = (i + 1) * segment_length

            twist_head = base_head + total_vec * factor_start
            twist_tail = base_head + total_vec * factor_end

            twist_name = f"{bone_name} twist {i+1}"
            twistbone = arm.data.edit_bones.get(twist_name)
            if not twistbone:
                twistbone = arm.data.edit_bones.new(twist_name)
            
            twistbone.head = twist_head
            twistbone.tail = twist_tail
            twistbone.roll = bone.roll
            twistbone.parent = prev_bone

            prev_bone = bone

    def _process_bones_object_mode(self, arm: Object, bone_elements: dict) -> None:
        for bone_name, bone_data in bone_elements.items():
            pb = arm.pose.bones.get(bone_name)
            if not pb:
                continue

            if 'BONE_EXROTATION' in self.load_options:
                self._apply_export_rotation(pb, bone_data)

            if 'EXPORT_NAME' in self.load_options and bone_data.get("ExportName"):
                pb.bone.vs.export_name = get_canonical_bonename(bone_data.get("ExportName"))

            if 'CONSTRAINTS' in self.load_options and 'TWIST_BONES' in self.load_options:
                self._setup_twist_constraints(arm, pb, bone_name, bone_data)

    def _apply_export_rotation(self, pb, bone_data: dict) -> None:
        export_rot = bone_data.get("ExportRotationOffset")
        if export_rot is not None:
            pb.bone.vs.ignore_rotation_offset = False
            pb.bone.vs.export_rotation_offset_x = export_rot[0]
            pb.bone.vs.export_rotation_offset_y = export_rot[1]
            pb.bone.vs.export_rotation_offset_z = export_rot[2]
        else:
            pb.bone.vs.ignore_rotation_offset = True

    def _setup_twist_constraints(self, arm: Object, pb, bone_name: str, bone_data: dict) -> None:
        twist_target = bone_data.get("TwistBones")
        twist_count = bone_data.get("TwistBoneCount") or (1 if twist_target else 0)
        
        if twist_count == 0:
            return

        twist_bones = [
            arm.pose.bones.get(f"{bone_name} twist {i+1}")
            for i in range(twist_count)
        ]

        for idx, pbtwist in enumerate(twist_bones):
            if not pbtwist:
                continue

            if 'BONE_EXROTATION' in self.load_options:
                self._apply_export_rotation(pbtwist, bone_data)

            if twist_target == pbtwist.parent.name:
                pbtwist.rotation_mode = 'XYZ'
            else:
                self._add_twist_constraint(arm, pbtwist, bone_name, twist_target, idx, twist_count)

            for col in pb.bone.collections:
                col.assign(pbtwist.bone)

    def _add_twist_constraint(self, arm: Object, pbtwist, bone_name: str, twist_target: str, idx: int, twist_count: int) -> None:
        pbtwist.rotation_mode = 'XYZ'
        influence = (idx + 1) / twist_count

        constraint_name = f"{bone_name}_twist_constraint_{idx+1}"
        twist_constraint : bpy.types.CopyRotationConstraint = pbtwist.constraints.get(constraint_name)
        
        if twist_constraint is None:
            twist_constraint = pbtwist.constraints.new('COPY_ROTATION')
            twist_constraint.name = constraint_name

        twist_constraint.target = arm
        twist_constraint.subtarget = twist_target
        twist_constraint.use_x = False
        twist_constraint.use_y = True
        twist_constraint.use_z = False
        twist_constraint.owner_space = 'LOCAL'
        twist_constraint.target_space = 'LOCAL_OWNER_ORIENT'
        twist_constraint.influence = influence
        
    def _has_children_in_json(self, bone_name: str, bone_elements: dict) -> bool:
        for check_name, check_data in bone_elements.items():
            if check_data.get("ParentBone") == bone_name:
                return True
        return False

    def _write_missing_bone(self, arm: Object, bone_name: str, child_hint: str, bone_elements: dict) -> bpy.types.EditBone | None:
        existing = arm.data.edit_bones.get(bone_name)
        if existing:
            return existing

        bone_data = bone_elements.get(bone_name)
        if not bone_data:
            print(f"[WARN] No JSON entry for '{bone_name}', skipping.")
            return None

        if not self._has_children_in_json(bone_name, bone_elements) and not child_hint:
            print(f"[SKIP] {bone_name} is a terminal bone with no children, skipping creation")
            return None

        new_bone = arm.data.edit_bones.new(bone_name)

        if child_hint:
            child_bone = arm.data.edit_bones.get(child_hint)
            if child_bone:
                new_bone.head = child_bone.head.copy()
                offset = (child_bone.tail - child_bone.head).normalized() * (child_bone.length * 0.5)
                new_bone.tail = child_bone.head + offset
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
            lookup = getattr(self, 'mapped_bones_lookup', {})
            parent_search_name = lookup.get(parent_name, parent_name)
            
            parent_bone = arm.data.edit_bones.get(parent_search_name)
            if parent_bone is None and 'MISSING_BONES' in self.load_options:
                parent_bone = self._write_missing_bone(arm, parent_name, bone_name, bone_elements)
            if parent_bone:
                new_bone.parent = parent_bone

        print(f"[CREATE] {bone_name} (Parent: {parent_name})")
        return new_bone

class HUMANOIDARMATUREMAP_OT_WriteConfig(Operator):
    bl_idname : str = "humanoidarmaturemap.write_json"
    bl_label : str = "Write Json"
    bl_options : Set = {"INTERNAL", "REGISTER"}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool(is_armature(context.object) and len(context.object.vs.humanoid_armature_map_bonecollections) > 0)

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

        with preserve_context_mode(ob, 'EDIT'):
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

class HUMANOIDARMATUREMAP_OT_RemoveItem(Operator):
    bl_idname : str = "humanoidarmaturemap.remove_item"
    bl_label : str = "Remove Bone"
    bl_options : Set = {'REGISTER', 'UNDO', 'INTERNAL'}

    index: IntProperty()

    def execute(self, context : Context) -> Set:
        coll = context.object.vs.humanoid_armature_map_bonecollections
        if 0 <= self.index < len(coll):
            coll.remove(self.index)
        return {'FINISHED'}

class HUMANOIDARMATUREMAP_OT_AddItem(Operator):
    bl_idname : str = "humanoidarmaturemap.add_item"
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

        collection = ob.vs.humanoid_armature_map_bonecollections

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

class HUMANOIDARMATUREMAP_UL_ConfigList(UIList):
    def draw_item(self, context: Context, layout: UILayout, data: Any | None, item: Any | None, icon: int | None, active_data: Any, active_property: str | None, index: int | None, flt_flag: int | None) -> None:
        if item:
            row = layout.row()
            split = row.split(factor=0.9)
            split.prop_search(item, "boneExportName", context.object.data, "bones", text="")
            split.label(text="", )
            row.operator(HUMANOIDARMATUREMAP_OT_RemoveItem.bl_idname, text="", icon="X").index = index