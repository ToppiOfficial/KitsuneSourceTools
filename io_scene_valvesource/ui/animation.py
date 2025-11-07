
import bpy
from bpy.types import UILayout, Context, Object, Operator, Event
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy_extras import anim_utils

from .common import Tools_SubCategoryPanel
from ..core.commonutils import (
    draw_title_box, draw_wrapped_text_col, is_armature,
    sanitizeString
)
from ..utils import get_id

class TOOLS_PT_Animation(Tools_SubCategoryPanel):
    bl_label : str = "Animation Tools"
    
    def draw(self, context : Context) -> None:
        l : UILayout = self.layout
        bx : UILayout = draw_title_box(l, TOOLS_PT_Animation.bl_label, icon='ACTION')
        
        ob : Object | None = context.object
        if is_armature(ob): pass
        else:
            draw_wrapped_text_col(bx,get_id("panel_select_armature"),max_chars=40 , icon='HELP')
            return
        
        col = bx.column()
        col.operator(TOOLS_OT_merged_animations.bl_idname, icon='ACTION_SLOT')
        col.operator(TOOLS_OT_convert_rotation_keyframes.bl_idname, icon='ACTION_SLOT')
        
class TOOLS_OT_merged_animations(Operator):
    bl_idname : str = 'tools.merged_animations'
    bl_label : str = 'Merge Slotted Animations'
    bl_options : set = {'REGISTER', 'UNDO'}

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
            new_action = bpy.data.actions.new(name=sanitizeString(self.new_action_name))
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
    bl_idname : str = 'tools.convert_rotation_keyframes'
    bl_label : str = 'Convert Rotation Keyframes'
    bl_description : str = 'Convert rotation keyframes between Euler and Quaternion in an action slot'
    bl_options : set = {'REGISTER', 'UNDO'}

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
