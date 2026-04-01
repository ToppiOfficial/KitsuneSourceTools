
import bpy
from bpy.types import UILayout, Context, Operator, Event
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy_extras import anim_utils

from .common import KITSUNE_PT_ToolSubPanel
from ..kitsunetools.commonutils import (
    draw_wrapped_texts, is_armature
    )
from ..kitsunetools.armatureutils import copy_target_armature_visualpose
from ..kitsunetools.boneutils import get_bone_exportname
from ..utils import get_id

class TOOLS_PT_Animation(KITSUNE_PT_ToolSubPanel):
    bl_label = "Animation"
    
    def draw(self, context : Context) -> None:
        layout = self.layout
        bx = layout.box()
        
        ob  = context.active_object
        if is_armature(ob): pass
        else:
            draw_wrapped_texts(bx,get_id("panel_select_armature"),max_chars=40 , icon='HELP')
            return
        
        col = bx.column()
        col.operator(TOOLS_OT_merge_animation_slots.bl_idname, icon='ACTION_SLOT')
        col.operator(TOOLS_OT_merge_two_actions.bl_idname, icon='ACTION_SLOT')
        col.operator(TOOLS_OT_convert_rotation_keyframes.bl_idname, icon='ACTION_SLOT')
        col.operator(TOOLS_OT_propagate_pose_offset.bl_idname, icon='ACTION_SLOT')
        col.operator(TOOLS_OT_copy_bone_keyframes.bl_idname, icon='ACTION_SLOT')
        col.operator(TOOLS_OT_Make_Proportion_Animation.bl_idname, icon='ACTION_SLOT')
        col.operator(TOOLS_OT_delete_action_slot.bl_idname, icon='TRASH')
        
class TOOLS_OT_merge_animation_slots(Operator):
    bl_idname = 'kitsunetools.merged_animations'
    bl_label = 'Merge Slotted Animations'
    bl_options = {'REGISTER', 'UNDO'}

    action_1: StringProperty(
        name="First Action",
        description="First Action to merge (base)"
    )
    slot_1: StringProperty(
        name="First Slot",
        description="Slot from first action"
    )
    action_2: StringProperty(
        name="Second Action",
        description="Second Action to merge (added)"
    )
    slot_2: StringProperty(
        name="Second Slot",
        description="Slot from second action"
    )
    new_action_name: StringProperty(
        name="New Action Name",
        description="Name for the merged action",
        default="MergedAction"
    )
    use_existing_action: BoolProperty(
        name="Use Existing Action",
        description="Merge into an existing action instead of creating a new one",
        default=False
    )
    existing_action: StringProperty(
        name="Existing Action",
        description="Existing action to merge into"
    )
    new_slot_name: StringProperty(
        name="New Slot Name",
        description="Name for the merged slot",
        default="MergedSlot"
    )
    use_fake_user: BoolProperty(
        name="Fake User",
        description="Assign fake user to the new action",
        default=True
    )

    def invoke(self, context : Context, event : Event) -> set:
        if bpy.data.actions:
            self.action_1 = bpy.data.actions[0].name
            self.action_2 = bpy.data.actions[0].name
            self.existing_action = bpy.data.actions[0].name
            
            act1 = bpy.data.actions.get(self.action_1)
            if act1 and act1.slots:
                self.slot_1 = act1.slots[0].name_display
            
            act2 = bpy.data.actions.get(self.action_2)
            if act2 and act2.slots:
                self.slot_2 = act2.slots[0].name_display
        
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context : Context) -> None:
        layout : UILayout = self.layout
        
        box : UILayout = layout.box()
        box.label(text="First Animation:", icon='ACTION')
        
        row = box.row()
        row.prop_search(self, "action_1", bpy.data, "actions", text="Action")
        
        act1 = bpy.data.actions.get(self.action_1)
        if act1 and act1.slots:
            row = box.row()
            row.prop_search(self, "slot_1", act1, "slots", text="Slot")
        else:
            row = box.row()
            row.label(text="No slots available", icon='ERROR')
        
        box = layout.box()
        box.label(text="Second Animation:", icon='ACTION')
        
        row = box.row()
        row.prop_search(self, "action_2", bpy.data, "actions", text="Action")
        
        act2 = bpy.data.actions.get(self.action_2)
        if act2 and act2.slots:
            row = box.row()
            row.prop_search(self, "slot_2", act2, "slots", text="Slot")
        else:
            row = box.row()
            row.label(text="No slots available", icon='ERROR')
        
        layout.separator()
        box = layout.box()
        box.label(text="Output:", icon='FILE_NEW')
        box.prop(self, "use_existing_action")
        
        if self.use_existing_action:
            row = box.row()
            row.prop_search(self, "existing_action", bpy.data, "actions", text="Action")
        else:
            box.prop(self, "new_action_name")
            box.prop(self, "use_fake_user")
        
        box.prop(self, "new_slot_name")

    def execute(self, context : Context) -> set:
        act1 = bpy.data.actions.get(self.action_1)
        act2 = bpy.data.actions.get(self.action_2)

        if not act1 or not act2:
            self.report({'ERROR'}, "One or both actions not found")
            return {'CANCELLED'}

        slot1 = next((s for s in act1.slots if s.name_display == self.slot_1), None)
        slot2 = next((s for s in act2.slots if s.name_display == self.slot_2), None)

        if not slot1 or not slot2:
            self.report({'ERROR'}, "One or both slots not found")
            return {'CANCELLED'}

        if act1 == act2 and slot1 == slot2:
            self.report({'ERROR'}, "Cannot merge the same action slot with itself")
            return {'CANCELLED'}

        if self.use_existing_action:
            new_action = bpy.data.actions.get(self.existing_action)
            if not new_action:
                self.report({'ERROR'}, "Existing action not found")
                return {'CANCELLED'}
        else:
            new_action = bpy.data.actions.new(name=self.new_action_name)
            if self.use_fake_user:
                new_action.use_fake_user = True

        new_slot = new_action.slots.new(id_type='OBJECT', name=self.new_slot_name)

        if not new_action.layers:
            layer = new_action.layers.new(name="Layer")
        else:
            layer = new_action.layers[0]
        
        strip = layer.strips[0] if layer.strips else layer.strips.new(type='KEYFRAME')
        new_channelbag = strip.channelbags.new(slot=new_slot)

        def copy_fcurve_data(source_fcurve, target_channelbag):
            new_fcurve = target_channelbag.fcurves.new(
                data_path=source_fcurve.data_path,
                index=source_fcurve.array_index
            )
            for kp in source_fcurve.keyframe_points:
                new_fcurve.keyframe_points.insert(frame=kp.co.x, value=kp.co.y, options={'FAST'})
            return new_fcurve

        channelbag1 = anim_utils.action_get_channelbag_for_slot(act1, slot1)
        if channelbag1:
            for fcurve in channelbag1.fcurves: # type: ignore
                copy_fcurve_data(fcurve, new_channelbag)

        channelbag2 = anim_utils.action_get_channelbag_for_slot(act2, slot2)
        if channelbag2:
            for fcurve2 in channelbag2.fcurves: # type: ignore
                match = None
                for fcurve1 in new_channelbag.fcurves:
                    if (fcurve1.data_path == fcurve2.data_path and 
                        fcurve1.array_index == fcurve2.array_index):
                        match = fcurve1
                        break

                if match:
                    existing = {kp.co.x: kp.co.y for kp in match.keyframe_points}
                    for kp in fcurve2.keyframe_points:
                        frame = kp.co.x
                        value = kp.co.y
                        if frame in existing:
                            new_val = existing[frame] + value
                            match.keyframe_points.insert(frame=frame, value=new_val, options={'REPLACE'})
                        else:
                            match.keyframe_points.insert(frame=frame, value=value, options={'FAST'})
                else:
                    copy_fcurve_data(fcurve2, new_channelbag)

        self.report({'INFO'}, f"Merged '{act1.name}:{slot1.name_display}' + '{act2.name}:{slot2.name_display}' into '{new_action.name}:{new_slot.name_display}'")
        return {'FINISHED'}

class TOOLS_OT_convert_rotation_keyframes(Operator):
    bl_idname = 'kitsunetools.convert_rotation_keyframes'
    bl_label = 'Convert Rotation Keyframes'
    bl_description = 'Convert rotation keyframes between Euler and Quaternion in an action slot'
    bl_options = {'REGISTER', 'UNDO'}

    action_name: StringProperty(
        name="Action",
        description="Action containing the slot to convert"
    )
    slot_name: StringProperty(
        name="Slot",
        description="Action slot to convert"
    )
    conversion_mode: EnumProperty(
        name="Convert To",
        description="Target rotation mode",
        items=[
            ('QUATERNION', "Quaternion", "Convert Euler rotations to Quaternion"),
            ('XYZ', "Euler XYZ", "Convert Quaternion to Euler XYZ"),
            ('XZY', "Euler XZY", "Convert Quaternion to Euler XZY"),
            ('YXZ', "Euler YXZ", "Convert Quaternion to Euler YXZ"),
            ('YZX', "Euler YZX", "Convert Quaternion to Euler YZX"),
            ('ZXY', "Euler ZXY", "Convert Quaternion to Euler ZXY"),
            ('ZYX', "Euler ZYX", "Convert Quaternion to Euler ZYX"),
        ],
        default='QUATERNION'
    )

    def invoke(self, context : Context, event : Event) -> set:
        if bpy.data.actions:
            self.action_name = bpy.data.actions[0].name
            act = bpy.data.actions.get(self.action_name)
            if act and act.slots:
                self.slot_name = act.slots[0].name_display
        
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context : Context) -> None:
        layout = self.layout
        
        box = layout.box()
        box.label(text="Source:", icon='ACTION')
        row = box.row()
        row.prop_search(self, "action_name", bpy.data, "actions", text="Action")
        
        act = bpy.data.actions.get(self.action_name)
        if act and act.slots:
            row = box.row()
            row.prop_search(self, "slot_name", act, "slots", text="Slot")
        else:
            row = box.row()
            row.label(text="No slots available", icon='ERROR')
        
        layout.separator()
        box = layout.box()
        box.label(text="Conversion:", icon='FILE_REFRESH')
        box.prop(self, "conversion_mode")

    def execute(self, context : Context) -> set:
        from bpy_extras import anim_utils
        from mathutils import Euler, Quaternion
        
        action = bpy.data.actions.get(self.action_name)
        if not action:
            self.report({'ERROR'}, "Action not found")
            return {'CANCELLED'}

        slot = next((s for s in action.slots if s.name_display == self.slot_name), None)
        if not slot:
            self.report({'ERROR'}, "Slot not found")
            return {'CANCELLED'}

        channelbag = anim_utils.action_get_channelbag_for_slot(action, slot)
        if not channelbag:
            self.report({'ERROR'}, "No animation data in slot")
            return {'CANCELLED'}

        is_to_quat = self.conversion_mode == 'QUATERNION'
        
        rotation_fcurves = {}
        for fcurve in channelbag.fcurves: # type: ignore
            if 'rotation_euler' in fcurve.data_path or 'rotation_quaternion' in fcurve.data_path:
                base_path = fcurve.data_path.rsplit('.', 1)[0]
                if base_path not in rotation_fcurves:
                    rotation_fcurves[base_path] = []
                rotation_fcurves[base_path].append(fcurve)
        
        if not rotation_fcurves:
            self.report({'WARNING'}, "No rotation keyframes found in this slot")
            return {'CANCELLED'}

        for base_path, fcurves in rotation_fcurves.items():
            current_is_quat = 'rotation_quaternion' in fcurves[0].data_path
            
            if (current_is_quat and is_to_quat) or (not current_is_quat and not is_to_quat):
                continue

            frames = set()
            for fc in fcurves:
                for kp in fc.keyframe_points:
                    frames.add(kp.co.x)
            frames = sorted(frames)

            converted_data = {}
            for frame in frames:
                if current_is_quat:
                    quat_values = [0.0] * 4
                    for fc in fcurves:
                        idx = fc.array_index
                        for kp in fc.keyframe_points:
                            if abs(kp.co.x - frame) < 0.001:
                                quat_values[idx] = kp.co.y
                                break
                    
                    quat = Quaternion(quat_values)
                    euler = quat.to_euler(self.conversion_mode)
                    converted_data[frame] = [euler.x, euler.y, euler.z]
                else:
                    euler_values = [0.0] * 3
                    for fc in fcurves:
                        idx = fc.array_index
                        for kp in fc.keyframe_points:
                            if abs(kp.co.x - frame) < 0.001:
                                euler_values[idx] = kp.co.y
                                break
                    
                    euler = Euler(euler_values, 'XYZ')
                    quat = euler.to_quaternion()
                    converted_data[frame] = [quat.w, quat.x, quat.y, quat.z]

            for fc in fcurves:
                channelbag.fcurves.remove(fc)

            new_prop = 'rotation_quaternion' if is_to_quat else 'rotation_euler'
            new_path = f"{base_path}.{new_prop}"
            num_channels = 4 if is_to_quat else 3
            
            new_fcurves = []
            for i in range(num_channels):
                new_fc = channelbag.fcurves.new(data_path=new_path, index=i)
                new_fcurves.append(new_fc)
            
            for frame, values in converted_data.items():
                for i, value in enumerate(values):
                    new_fcurves[i].keyframe_points.insert(frame=frame, value=value, options={'FAST'})

        target_type = "Quaternion" if is_to_quat else self.conversion_mode
        self.report({'INFO'}, f"Converted rotation keyframes to {target_type} in '{action.name}:{slot.name_display}'")
        return {'FINISHED'}

class TOOLS_OT_merge_two_actions(Operator):
    bl_idname = 'kitsunetools.merge_two_actions'
    bl_label = 'Merge Two Actions'
    bl_options = {'REGISTER', 'UNDO'}

    action_1: StringProperty(
        name="First Action",
        description="First action to merge"
    )
    action_2: StringProperty(
        name="Second Action",
        description="Second action to merge"
    )
    new_action_name: StringProperty(
        name="New Action Name",
        description="Name for the merged action",
        default="MergedAction"
    )
    use_existing_action: BoolProperty(
        name="Use Existing Action",
        description="Merge into an existing action instead of creating a new one",
        default=False
    )
    existing_action: StringProperty(
        name="Existing Action",
        description="Existing action to merge into"
    )
    do_not_merge_matching_names: BoolProperty(
        name="Do Not Merge Matching Names",
        description="Keep slots with identical names separate (appends .001, .002)",
        default=False
    )
    
    rename_legacy_slots: BoolProperty(
        name="Rename Legacy Slots",
        description="Rename slots named 'Legacy Slot' to the action's name",
        default=True
    )
    
    use_fake_user: BoolProperty(
        name="Fake User",
        description="Assign fake user to the new action",
        default=True
    )

    def invoke(self, context : Context, event : Event) -> set:
        if bpy.data.actions:
            self.action_1 = bpy.data.actions[0].name
            self.action_2 = bpy.data.actions[0].name
            self.existing_action = bpy.data.actions[0].name
        
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context : Context) -> None:
        layout : UILayout = self.layout
        
        box = layout.box()
        box.label(text="Source Actions:", icon='ACTION')
        box.prop_search(self, "action_1", bpy.data, "actions", text="Action 1")
        box.prop_search(self, "action_2", bpy.data, "actions", text="Action 2")
        
        layout.separator()
        
        box = layout.box()
        box.label(text="Output:", icon='FILE_NEW')
        box.prop(self, "use_existing_action")
        
        if self.use_existing_action:
            box.prop_search(self, "existing_action", bpy.data, "actions", text="Action")
        else:
            box.prop(self, "new_action_name")
            box.prop(self, "use_fake_user")
        
        layout.separator()
        
        box = layout.box()
        box.label(text="Options:", icon='PREFERENCES')
        box.prop(self, "do_not_merge_matching_names")
        box.prop(self, "rename_legacy_slots")

    def execute(self, context : Context) -> set:
        act1 = bpy.data.actions.get(self.action_1)
        act2 = bpy.data.actions.get(self.action_2)
        
        if not act1 or not act2:
            self.report({'ERROR'}, "One or both actions not found")
            return {'CANCELLED'}
        
        if act1 == act2:
            self.report({'ERROR'}, "Cannot merge an action with itself")
            return {'CANCELLED'}
        
        if self.use_existing_action:
            target_action = bpy.data.actions.get(self.existing_action)
            if not target_action:
                self.report({'ERROR'}, "Existing action not found")
                return {'CANCELLED'}
        else:
            target_action = bpy.data.actions.new(name=self.new_action_name)
            if self.use_fake_user:
                target_action.use_fake_user = True
        
        if not target_action.layers:
            layer = target_action.layers.new(name="Layer")
        else:
            layer = target_action.layers[0]
        
        if not layer.strips:
            strip = layer.strips.new(type='KEYFRAME')
        else:
            strip = layer.strips[0]
        
        slot_groups = self._group_slots_by_name([act1, act2])
        
        merged_count = 0
        for slot_name, slot_list in slot_groups.items():
            if self.do_not_merge_matching_names and len(slot_list) > 1:
                for idx, (action, slot) in enumerate(slot_list):
                    unique_name = f"{slot_name}.{idx+1:03d}" if idx > 0 else slot_name
                    self._create_slot_copy(target_action, strip, action, slot, unique_name)
                    merged_count += 1
            else:
                if len(slot_list) > 1:
                    self._merge_slots(target_action, strip, slot_list, slot_name)
                else:
                    self._create_slot_copy(target_action, strip, slot_list[0][0], slot_list[0][1], slot_name)
                merged_count += 1
        
        self.report({'INFO'}, f"Merged '{act1.name}' + '{act2.name}' into '{target_action.name}' ({merged_count} slots)")
        return {'FINISHED'}

    def _group_slots_by_name(self, actions: list[bpy.types.Action]) -> dict[str, list[tuple[bpy.types.Action, bpy.types.ActionSlot]]]:
        """Groups slots by their display name across both actions"""
        slot_groups = {}
        
        use_legacy_replacement = self.rename_legacy_slots
        
        for action in actions:
            for slot in action.slots:
                name = slot.name_display
                
                if use_legacy_replacement and name.lower() == "legacy slot":
                    name = action.name

                slot_groups.setdefault(name, []).append((action, slot))
        
        return slot_groups

    def _create_slot_copy(self, target_action: bpy.types.Action, strip: bpy.types.ActionStrip, 
                         source_action: bpy.types.Action, source_slot: bpy.types.ActionSlot, 
                         new_slot_name: str) -> bpy.types.ActionSlot:
        """Creates a new slot and copies fcurves from source"""
        new_slot = target_action.slots.new(id_type='OBJECT', name=new_slot_name)
        new_channelbag = strip.channelbags.new(slot=new_slot)
        
        source_channelbag = anim_utils.action_get_channelbag_for_slot(source_action, source_slot)
        if source_channelbag:
            for fcurve in source_channelbag.fcurves:
                self._copy_fcurve(fcurve, new_channelbag)
        
        return new_slot

    def _merge_slots(self, target_action: bpy.types.Action, strip: bpy.types.ActionStrip,
                    slot_list: list[tuple[bpy.types.Action, bpy.types.ActionSlot]], 
                    merged_slot_name: str) -> None:
        """Merges multiple slots with the same name into one slot"""
        new_slot = target_action.slots.new(id_type='OBJECT', name=merged_slot_name)
        new_channelbag = strip.channelbags.new(slot=new_slot)
        
        for action, slot in slot_list:
            source_channelbag = anim_utils.action_get_channelbag_for_slot(action, slot)
            if not source_channelbag:
                continue
            
            for source_fcurve in source_channelbag.fcurves:
                existing_fcurve = self._find_matching_fcurve(new_channelbag, source_fcurve)
                
                if existing_fcurve:
                    self._merge_fcurve_keyframes(existing_fcurve, source_fcurve)
                else:
                    self._copy_fcurve(source_fcurve, new_channelbag)

    def _find_matching_fcurve(self, channelbag: bpy.types.ActionChannelbag, 
                             fcurve: bpy.types.FCurve) -> bpy.types.FCurve | None:
        """Finds fcurve with matching data_path and array_index"""
        for existing in channelbag.fcurves:
            if existing.data_path == fcurve.data_path and existing.array_index == fcurve.array_index:
                return existing
        return None

    def _copy_fcurve(self, source_fcurve: bpy.types.FCurve, 
                    target_channelbag: bpy.types.ActionChannelbag) -> bpy.types.FCurve:
        """Copies fcurve data to target channelbag"""
        new_fcurve = target_channelbag.fcurves.new(
            data_path=source_fcurve.data_path,
            index=source_fcurve.array_index
        )
        for kp in source_fcurve.keyframe_points:
            new_fcurve.keyframe_points.insert(frame=kp.co.x, value=kp.co.y, options={'FAST'})
        return new_fcurve

    def _merge_fcurve_keyframes(self, target_fcurve: bpy.types.FCurve, 
                               source_fcurve: bpy.types.FCurve) -> None:
        """Adds keyframes from source to target, summing values at existing frames"""
        existing_frames = {kp.co.x: kp.co.y for kp in target_fcurve.keyframe_points}
        
        for kp in source_fcurve.keyframe_points:
            frame = kp.co.x
            value = kp.co.y
            
            if frame in existing_frames:
                new_value = existing_frames[frame] + value
                target_fcurve.keyframe_points.insert(frame=frame, value=new_value, options={'REPLACE'})
            else:
                target_fcurve.keyframe_points.insert(frame=frame, value=value, options={'FAST'})
                
class TOOLS_OT_delete_action_slot(Operator):
    bl_idname = 'kitsunetools.delete_action_slot'
    bl_label = 'Delete Action Slot'
    bl_description = 'Delete a slot from the current object\'s action'
    bl_options = {'REGISTER', 'UNDO'}

    slot_name: StringProperty(
        name="Slot to Delete",
        description="Name of the slot to delete"
    )

    @classmethod
    def poll(cls, context : Context) -> bool:
        obj = context.active_object
        if not obj or not obj.animation_data or not obj.animation_data.action:
            return False
        return len(obj.animation_data.action.slots) > 0

    def invoke(self, context : Context, event : Event) -> set:
        obj = context.active_object
        action = obj.animation_data.action
        
        if action and action.slots:
            self.slot_name = action.slots[0].name_display
        
        return context.window_manager.invoke_props_dialog(self, width=350)

    def draw(self, context : Context) -> None:
        layout = self.layout
        obj = context.active_object
        action = obj.animation_data.action
        
        box = layout.box()
        box.label(text=f"Action: {action.name}", icon='ACTION')
        
        row = box.row()
        row.prop_search(self, "slot_name", action, "slots", text="Slot")

    def execute(self, context : Context) -> set:
        obj = context.active_object
        action = obj.animation_data.action
        
        if not action:
            self.report({'ERROR'}, "No action found on current object")
            return {'CANCELLED'}
        
        slot = next((s for s in action.slots if s.name_display == self.slot_name), None)
        
        if not slot:
            self.report({'ERROR'}, f"Slot '{self.slot_name}' not found")
            return {'CANCELLED'}
        
        slot_name = slot.name_display
        slot_index = next(i for i, s in enumerate(action.slots) if s == slot)
        
        action.slots.remove(slot)
        
        self.report({'INFO'}, f"Deleted slot '{slot_name}' from action '{action.name}'")
        return {'FINISHED'}
    
class TOOLS_OT_propagate_pose_offset(Operator):
    bl_idname = 'kitsunetools.propagate_pose_offset'
    bl_label = 'Propagate Pose Offset to Keyframes'
    bl_description = 'Apply current pose offset to all keyframes in the action slot'
    bl_options = {'REGISTER', 'UNDO'}

    action_name: StringProperty(
        name="Action",
        description="Action containing the slot"
    )
    slot_name: StringProperty(
        name="Slot",
        description="Action slot to modify"
    )
    selected_bones_only: BoolProperty(
        name="Selected Bones Only",
        description="Only apply offset to selected bones",
        default=True
    )

    @classmethod
    def poll(cls, context : Context) -> bool:
        obj = context.active_object
        return bool(obj and is_armature(obj) and 
                context.selected_pose_bones and
                obj.animation_data and 
                obj.animation_data.action)

    def invoke(self, context : Context, event : Event) -> set:
        obj = context.active_object
        if obj.animation_data and obj.animation_data.action:
            action = obj.animation_data.action
            self.action_name = action.name
            if action.slots:
                self.slot_name = action.slots[0].name_display
        
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context : Context) -> None:
        layout = self.layout
        
        box = layout.box()
        box.label(text="Source:", icon='ACTION')
        box.prop_search(self, "action_name", bpy.data, "actions", text="Action")
        
        act = bpy.data.actions.get(self.action_name)
        if act and act.slots:
            box.prop_search(self, "slot_name", act, "slots", text="Slot")
        else:
            box.label(text="No slots available", icon='ERROR')
        
        layout.separator()
        box = layout.box()
        box.label(text="Options:", icon='PREFERENCES')
        box.prop(self, "selected_bones_only")

    def execute(self, context : Context) -> set:
        from mathutils import Matrix, Vector, Euler, Quaternion
        
        obj = context.active_object
        current_frame = context.scene.frame_current
        
        action = bpy.data.actions.get(self.action_name)
        if not action:
            self.report({'ERROR'}, "Action not found")
            return {'CANCELLED'}

        slot = next((s for s in action.slots if s.name_display == self.slot_name), None)
        if not slot:
            self.report({'ERROR'}, "Slot not found")
            return {'CANCELLED'}

        channelbag = anim_utils.action_get_channelbag_for_slot(action, slot)
        if not channelbag:
            self.report({'ERROR'}, "No animation data in slot")
            return {'CANCELLED'}

        bones_to_process = context.selected_pose_bones if self.selected_bones_only else obj.pose.bones
        
        if not bones_to_process:
            self.report({'WARNING'}, "No bones to process")
            return {'CANCELLED'}

        modified_bones = 0
        
        for pose_bone in bones_to_process:
            bone_path = f'pose.bones["{pose_bone.name}"]'
            
            offset_location = None
            offset_rotation = None
            offset_scale = None
            
            loc_fcurves = [fc for fc in channelbag.fcurves 
                          if fc.data_path == f'{bone_path}.location']
            rot_euler_fcurves = [fc for fc in channelbag.fcurves 
                                if fc.data_path == f'{bone_path}.rotation_euler']
            rot_quat_fcurves = [fc for fc in channelbag.fcurves 
                               if fc.data_path == f'{bone_path}.rotation_quaternion']
            scale_fcurves = [fc for fc in channelbag.fcurves 
                            if fc.data_path == f'{bone_path}.scale']
            
            if loc_fcurves:
                current_loc = Vector(pose_bone.location)
                keyframed_loc = Vector([0, 0, 0])
                for fc in loc_fcurves:
                    keyframed_loc[fc.array_index] = fc.evaluate(current_frame)
                offset_location = current_loc - keyframed_loc
            
            if rot_euler_fcurves:
                current_rot = pose_bone.rotation_euler.copy()
                keyframed_rot = Euler([0, 0, 0], pose_bone.rotation_mode)
                for fc in rot_euler_fcurves:
                    keyframed_rot[fc.array_index] = fc.evaluate(current_frame)
                offset_rotation = current_rot.to_matrix() @ keyframed_rot.to_matrix().inverted()
            
            elif rot_quat_fcurves:
                current_rot = pose_bone.rotation_quaternion.copy()
                keyframed_rot = Quaternion([1, 0, 0, 0])
                for fc in rot_quat_fcurves:
                    keyframed_rot[fc.array_index] = fc.evaluate(current_frame)
                offset_rotation = current_rot.to_matrix() @ keyframed_rot.to_matrix().inverted()
            
            if scale_fcurves:
                current_scale = Vector(pose_bone.scale)
                keyframed_scale = Vector([1, 1, 1])
                for fc in scale_fcurves:
                    keyframed_scale[fc.array_index] = fc.evaluate(current_frame)
                offset_scale = Vector([current_scale[i] / keyframed_scale[i] if keyframed_scale[i] != 0 else 1 
                                      for i in range(3)])
            
            if not any([offset_location, offset_rotation, offset_scale]):
                continue
            
            if offset_location:
                for fc in loc_fcurves:
                    for kp in fc.keyframe_points:
                        kp.co.y += offset_location[fc.array_index]
            
            if offset_rotation:
                if rot_euler_fcurves:
                    frames = set()
                    for fc in rot_euler_fcurves:
                        for kp in fc.keyframe_points:
                            frames.add(kp.co.x)
                    
                    for frame in frames:
                        old_euler = Euler([0, 0, 0], pose_bone.rotation_mode)
                        for fc in rot_euler_fcurves:
                            for kp in fc.keyframe_points:
                                if abs(kp.co.x - frame) < 0.001:
                                    old_euler[fc.array_index] = kp.co.y
                                    break
                        
                        new_matrix = offset_rotation @ old_euler.to_matrix()
                        new_euler = new_matrix.to_euler(pose_bone.rotation_mode)
                        
                        for fc in rot_euler_fcurves:
                            for kp in fc.keyframe_points:
                                if abs(kp.co.x - frame) < 0.001:
                                    kp.co.y = new_euler[fc.array_index]
                                    break
                
                elif rot_quat_fcurves:
                    frames = set()
                    for fc in rot_quat_fcurves:
                        for kp in fc.keyframe_points:
                            frames.add(kp.co.x)
                    
                    for frame in frames:
                        old_quat = Quaternion([1, 0, 0, 0])
                        for fc in rot_quat_fcurves:
                            for kp in fc.keyframe_points:
                                if abs(kp.co.x - frame) < 0.001:
                                    old_quat[fc.array_index] = kp.co.y
                                    break
                        
                        new_matrix = offset_rotation @ old_quat.to_matrix()
                        new_quat = new_matrix.to_quaternion()
                        
                        for fc in rot_quat_fcurves:
                            for kp in fc.keyframe_points:
                                if abs(kp.co.x - frame) < 0.001:
                                    kp.co.y = new_quat[fc.array_index]
                                    break
            
            if offset_scale:
                for fc in scale_fcurves:
                    for kp in fc.keyframe_points:
                        kp.co.y *= offset_scale[fc.array_index]
            
            modified_bones += 1
        
        if modified_bones > 0:
            self.report({'INFO'}, f"Applied pose offset to {modified_bones} bone(s)")
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "No keyframes found for selected bones")
            return {'CANCELLED'}
        
class TOOLS_OT_copy_bone_keyframes(Operator):
    bl_idname = 'kitsunetools.copy_bone_keyframes'
    bl_label = 'Copy Bone Keyframes'
    bl_description = 'Copy keyframes from one bone to another (source bone name from action data)'
    bl_options = {'REGISTER', 'UNDO'}

    action_name: StringProperty(
        name="Action",
        description="Action containing the keyframes"
    )
    slot_name: StringProperty(
        name="Slot",
        description="Action slot to copy from"
    )
    source_bone_name: StringProperty(
        name="Source Bone Name",
        description="Exact name of the bone to copy keyframes from (as it appears in action data)"
    )
    copy_location: BoolProperty(
        name="Copy Location",
        description="Copy location keyframes",
        default=True
    )
    copy_rotation: BoolProperty(
        name="Copy Rotation",
        description="Copy rotation keyframes",
        default=True
    )
    copy_scale: BoolProperty(
        name="Copy Scale",
        description="Copy scale keyframes",
        default=True
    )
    replace_existing: BoolProperty(
        name="Replace Existing",
        description="Replace existing keyframes on target bone",
        default=False
    )

    @classmethod
    def poll(cls, context : Context) -> bool:
        obj = context.active_object
        if not (obj and is_armature(obj) and context.selected_pose_bones):
            return False
        if len(context.selected_pose_bones) != 1:
            return False
        if not (obj.animation_data and obj.animation_data.action):
            return False
        action = obj.animation_data.action
        if not action.slots:
            return False
        return True

    def invoke(self, context : Context, event : Event) -> set:
        obj = context.active_object
        action = obj.animation_data.action
        
        self.action_name = action.name
        
        if hasattr(obj.animation_data, 'action_slot') and obj.animation_data.action_slot:
            self.slot_name = obj.animation_data.action_slot.name_display
        elif action.slots:
            self.slot_name = action.slots[0].name_display
        
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context : Context) -> None:
        layout = self.layout
        
        obj = context.active_object
        target_bone = context.selected_pose_bones[0]
        
        box = layout.box()
        box.label(text="Source:", icon='ACTION')
        
        row = box.row()
        row.enabled = False
        row.prop_search(self, "action_name", bpy.data, "actions", text="Action")
        
        act = bpy.data.actions.get(self.action_name)
        if act and act.slots:
            row = box.row()
            row.enabled = False
            row.prop_search(self, "slot_name", act, "slots", text="Slot")
        
        box.separator()
        box.prop(self, "source_bone_name", icon='BONE_DATA')
        
        layout.separator()
        box = layout.box()
        box.label(text="Copy Options:", icon='PREFERENCES')
        row = box.row()
        row.prop(self, "copy_location")
        row.prop(self, "copy_rotation")
        row.prop(self, "copy_scale")
        box.prop(self, "replace_existing")
        
        layout.separator()
        info_box = layout.box()
        info_box.label(text=f"Target: {target_bone.name}", icon='BONE_DATA')

    def execute(self, context : Context) -> set:
        obj = context.active_object
        target_bone = context.selected_pose_bones[0]
        
        if not self.source_bone_name:
            self.report({'ERROR'}, "Source bone name not specified")
            return {'CANCELLED'}
        
        action = bpy.data.actions.get(self.action_name)
        if not action:
            self.report({'ERROR'}, "Action not found")
            return {'CANCELLED'}

        slot = next((s for s in action.slots if s.name_display == self.slot_name), None)
        if not slot:
            self.report({'ERROR'}, "Slot not found")
            return {'CANCELLED'}

        channelbag = anim_utils.action_get_channelbag_for_slot(action, slot)
        if not channelbag:
            self.report({'ERROR'}, "No animation data in slot")
            return {'CANCELLED'}

        source_path = f'pose.bones["{self.source_bone_name}"]'
        target_path = f'pose.bones["{target_bone.name}"]'
        
        source_fcurves = [fc for fc in channelbag.fcurves if fc.data_path.startswith(source_path)]
        
        if not source_fcurves:
            self.report({'ERROR'}, f"No keyframes found for bone '{self.source_bone_name}'")
            return {'CANCELLED'}
        
        properties_to_copy = []
        if self.copy_location:
            properties_to_copy.append('location')
        if self.copy_rotation:
            properties_to_copy.extend(['rotation_euler', 'rotation_quaternion'])
        if self.copy_scale:
            properties_to_copy.append('scale')
        
        copied_count = 0
        
        for source_fc in source_fcurves:
            prop_name = source_fc.data_path.split('.')[-1]
            
            if prop_name not in properties_to_copy:
                continue
            
            target_data_path = f'{target_path}.{prop_name}'
            
            if self.replace_existing:
                existing_fc = next((fc for fc in channelbag.fcurves 
                                  if fc.data_path == target_data_path and 
                                  fc.array_index == source_fc.array_index), None)
                if existing_fc:
                    channelbag.fcurves.remove(existing_fc)
            
            new_fc = channelbag.fcurves.new(
                data_path=target_data_path,
                index=source_fc.array_index
            )
            
            for kp in source_fc.keyframe_points:
                new_fc.keyframe_points.insert(frame=kp.co.x, value=kp.co.y, options={'FAST'})
            
            copied_count += 1
        
        if copied_count > 0:
            self.report({'INFO'}, f"Copied {copied_count} fcurve(s) from '{self.source_bone_name}' to '{target_bone.name}'")
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "No keyframes matched the selected copy options")
            return {'CANCELLED'}
        
class TOOLS_OT_Make_Proportion_Animation(Operator):
    bl_idname = 'tools.create_proportion_actions'
    bl_label = 'Create Delta Proportion Pose'
    bl_options = {'REGISTER', 'UNDO'}

    ProportionName: StringProperty(name='Proportion Slot Name', default='proportion')
    ReferenceName: StringProperty(name='Reference Slot Name', default='reference')
    KeepNonCopiedKeyframes: BoolProperty(
        name='Keep Non-Copied Keyframes',
        description='Preserve existing keyframes for bones that do not match between armatures',
        default=True
    )

    @classmethod
    def poll(cls, context : Context) -> bool:
        ob  = context.active_object
        return bool(
            context.mode == 'OBJECT'
            and is_armature(ob)
            and {o for o in context.selected_objects if o != context.active_object}
        )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context : Context) -> set:
        currArm : bpy.types.Object | None = context.active_object
        if currArm is None: return {'CANCELLED'}
        
        otherArms = {o for o in context.selected_objects if o.type == 'ARMATURE'}
        otherArms.discard(currArm)

        if not self.ReferenceName.strip() or not self.ProportionName.strip():
            return {'CANCELLED'}

        last_pose_state = currArm.data.pose_position
        currArm.data.pose_position = 'REST'
        context.scene.frame_set(0)
        context.view_layer.update()

        for arm in otherArms:
            if arm.animation_data is None:
                arm.animation_data_create()

            action_name = "proportion-delta"
            action = bpy.data.actions.get(action_name)
            if action is None:
                action = bpy.data.actions.new(action_name)
            action.use_fake_user = True

            if not self.KeepNonCopiedKeyframes:
                actionslots = list(action.slots)
                for slot in actionslots:
                    action.slots.remove(slot)

            for pb in arm.pose.bones:
                pb.matrix_basis.identity()

            slot_ref = self._get_or_create_slot(action, self.ReferenceName)
            slot_prop = self._get_or_create_slot(action, self.ProportionName)

            if len(action.layers) == 0:
                layer = action.layers.new("BaseLayer")
            else:
                layer = action.layers[0]

            if len(layer.strips) == 0:
                strip = layer.strips.new(type='KEYFRAME')
            else:
                strip = layer.strips[0]

            matched_bones = self._get_matching_bones(currArm, arm)

            if self.KeepNonCopiedKeyframes:
                self._clear_keyframes_for_bones(action, layer, strip, slot_ref, matched_bones)

            arm.animation_data.action = action
            arm.animation_data.action_slot = slot_ref

            try:
                copy_target_armature_visualpose(currArm, arm, copy_type='ANGLES')
                for pbone in arm.pose.bones:
                    if not self.KeepNonCopiedKeyframes or pbone.name in matched_bones:
                        pbone.keyframe_insert(data_path="location", group=pbone.name) # type: ignore
                        pbone.keyframe_insert(data_path="rotation_quaternion", group=pbone.name) # type: ignore
                        pbone.keyframe_insert(data_path="rotation_euler", group=pbone.name) # type: ignore

            except Exception as e:
                self.report({'ERROR'}, str(e))
                return {'CANCELLED'}

            context.view_layer.update()

            if self.KeepNonCopiedKeyframes:
                self._clear_keyframes_for_bones(action, layer, strip, slot_prop, matched_bones)

            arm.animation_data.action_slot = slot_prop

            try:
                copy_target_armature_visualpose(currArm, arm, copy_type='ANGLES')
                copy_target_armature_visualpose(currArm, arm, copy_type='ORIGIN')

                for pbone in arm.pose.bones:
                    if not self.KeepNonCopiedKeyframes or pbone.name in matched_bones:
                        pbone.keyframe_insert(data_path="location", group=pbone.name) # type: ignore
                        pbone.keyframe_insert(data_path="rotation_quaternion", group=pbone.name) # type: ignore
                        pbone.keyframe_insert(data_path="rotation_euler", group=pbone.name) # type: ignore
            except Exception as e:
                self.report({'ERROR'}, str(e))
                return {'CANCELLED'}    

            arm.animation_data.action_slot = slot_ref
            context.view_layer.update()
                
        currArm.data.pose_position = last_pose_state
        return {'FINISHED'}

    def _get_or_create_slot(self, action: bpy.types.Action, slot_name: str) -> bpy.types.ActionSlot:
        """Gets existing slot or creates new one with given name"""
        for slot in action.slots:
            if slot.name_display == slot_name:
                return slot
        return action.slots.new(id_type='OBJECT', name=slot_name)

    def _clear_keyframes_for_bones(self, action: bpy.types.Action, layer: bpy.types.ActionLayer, 
                                   strip: bpy.types.ActionStrip, slot: bpy.types.ActionSlot, 
                                   bone_names: set[str]) -> None:
        """Removes keyframes only for specified bones in the given slot"""
        channelbag = strip.channelbag(slot)
        if not channelbag:
            return
        
        fcurves_to_remove = []
        for fcurve in channelbag.fcurves:
            for bone_name in bone_names:
                if f'pose.bones["{bone_name}"]' in fcurve.data_path:
                    fcurves_to_remove.append(fcurve)
                    break
        
        for fcurve in fcurves_to_remove:
            channelbag.fcurves.remove(fcurve)

    def _get_matching_bones(self, source_arm: bpy.types.Object, target_arm: bpy.types.Object) -> set[str]:
        """Returns set of bone names that exist in both armatures or match via export names"""
        matched_bones = set()
        source_bones = {get_bone_exportname(b, for_write=True): b.name for b in source_arm.data.bones}
        source_bones.update({b.name: b.name for b in source_arm.data.bones})
        
        for target_bone in target_arm.data.bones:
            target_export = get_bone_exportname(target_bone, for_write=True)
            if target_bone.name in source_bones or target_export in source_bones:
                matched_bones.add(target_bone.name)
        
        return matched_bones