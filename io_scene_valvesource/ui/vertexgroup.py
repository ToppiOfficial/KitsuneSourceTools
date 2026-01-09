import bpy, bmesh
from bpy.props import FloatProperty, BoolProperty, StringProperty
from bpy.types import UILayout, Context, Object, Operator, PoseBone
from typing import Set
from mathutils import Vector

from .common import ToolsCategoryPanel
from ..core.commonutils import (
    draw_title_box_layout, draw_wrapped_texts,
    is_armature, is_mesh, get_armature, get_armature_meshes,
    get_selected_bones, preserve_context_mode
)
from ..core.armatureutils import (
    remove_bone, preserve_armature_state
)
from ..core.meshutils import (
    reapply_vertexgroup_as_curve
)

from ..utils import get_id

from .bone import TOOLS_OT_SubdivideBone

class TOOLS_PT_VertexGroup(ToolsCategoryPanel):
    bl_label : str = "Vertex Group Tools"
    
    def draw(self, context : Context) -> None:
        l : UILayout = self.layout
        bx : UILayout = draw_title_box_layout(l, TOOLS_PT_VertexGroup.bl_label, icon='GROUP_VERTEX')
        
        vgroup_mode = False
        
        ob : Object | None = context.object
        if (is_mesh(ob) and ob.mode == 'WEIGHT_PAINT') or (is_armature(ob) and ob.mode == 'POSE'): vgroup_mode = True
        else:
            draw_wrapped_texts(bx,get_id("panel_select_mesh_vgroup"),max_chars=40 , icon='HELP')
            vgroup_mode = False
            
        def draw_multi_ob_weightmode(col : UILayout):
            col2 = col.column()
            col2.scale_y = 1.5
            if ob.get("is_temp_weight_paint"):
                col2.operator(TOOLS_OT_multi_weight_paint_finish.bl_idname)
                col2.operator(TOOLS_OT_multi_weight_paint_cancel.bl_idname)
            else:
                col2.operator(TOOLS_OT_multi_weight_paint_start.bl_idname)
        
        if vgroup_mode:
            col = bx.column(align=True)
            
            draw_multi_ob_weightmode(col)
            
            col.prop(context.scene.vs, 'visible_mesh_only')
            col.operator(TOOLS_OT_WeightMath.bl_idname, icon='LINENUMBERS_ON')
            col.operator(TOOLS_OT_SwapVertexGroups.bl_idname,icon='AREA_SWAP')
            col.operator(TOOLS_OT_SubdivideBone.bl_idname, icon='MOD_SUBSURF', text=TOOLS_OT_SubdivideBone.bl_label + " (Weights Only)").weights_only = True
            
            if context.object.mode == 'WEIGHT_PAINT':
                col = bx.column(align=True)
                tool_settings = context.tool_settings
                brush = tool_settings.weight_paint.brush
                
                col.operator(TOOLS_OT_curve_ramp_weights.bl_idname)
                row = col.row(align=True)
                    
                col.template_curve_mapping(brush, "curve", brush=False)
                row = col.row(align=True)
                row.operator("brush.curve_preset", icon='SMOOTHCURVE', text="").shape = 'SMOOTH'
                row.operator("brush.curve_preset", icon='SPHERECURVE', text="").shape = 'ROUND'
                row.operator("brush.curve_preset", icon='ROOTCURVE', text="").shape = 'ROOT'
                row.operator("brush.curve_preset", icon='SHARPCURVE', text="").shape = 'SHARP'
                row.operator("brush.curve_preset", icon='LINCURVE', text="").shape = 'LINE'
                row.operator("brush.curve_preset", icon='NOCURVE', text="").shape = 'MAX'
            
        if(is_mesh(ob) and ob.mode == 'OBJECT'):
            col = bx.column(align=True)
            draw_multi_ob_weightmode(col)

class TOOLS_OT_WeightMath(Operator):
    bl_idname : str = "kitsunetools.weight_math"
    bl_label : str = "Weight Math"
    bl_options : Set = {'REGISTER', 'UNDO'}

    operation: bpy.props.EnumProperty(
        name="Operation",
        description="Math operation to apply",
        items=[
            ('ADD', "Add", "Add other bones to active"),
            ('SUBTRACT', "Subtract", "Subtract sum of others from active"),
            ('MULTIPLY', "Multiply", "Multiply active by sum of others"),
            ('DIVIDE', "Divide", "Divide active by sum of others"),
        ],
        default='SUBTRACT'
    )

    @classmethod
    def poll(cls, context : Context) -> bool:
        ob = context.active_object
        return bool((is_mesh(ob) or is_armature(ob)) and ob.mode in {'POSE', 'WEIGHT_PAINT'} and get_armature(ob).select_get())
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context : Context) -> Set:
        
        arm = get_armature(context.object)
        meshes = get_armature_meshes(arm, visible_only=getattr(context.scene.vs, 'visible_mesh_only', False))
        
        if not meshes:
            self.report({'WARNING'}, "No meshes bound to armature")
            return {'CANCELLED'}

        curr_bone = arm.data.bones.active
        if not curr_bone:
            self.report({'WARNING'}, "No active bone")
            return {'CANCELLED'}
        selected_bones = [b for b in arm.data.bones if b.select]
        if len(selected_bones) < 2:
            self.report({'WARNING'}, "Select at least 2 bones")
            return {'CANCELLED'}

        active_name = curr_bone.name
        other_names = [b.name for b in selected_bones if b != curr_bone]
        
        prev_mode = arm.mode
        
        for mesh in meshes:

            vg_active = mesh.vertex_groups.get(active_name)
            if not vg_active:
                continue

            vg_others = [mesh.vertex_groups.get(n) for n in other_names if mesh.vertex_groups.get(n)]
            if not vg_others:
                continue

            for v in mesh.data.vertices:
                try:
                    w_active = vg_active.weight(v.index)
                except RuntimeError:
                    w_active = 0.0

                w_sum = 0.0
                for vg in vg_others:
                    try:
                        w_sum += vg.weight(v.index)
                    except RuntimeError:
                        pass

                if self.operation == 'ADD':
                    new_w = w_active + w_sum
                elif self.operation == 'SUBTRACT':
                    new_w = w_active - w_sum
                elif self.operation == 'MULTIPLY':
                    new_w = w_active * w_sum
                elif self.operation == 'DIVIDE':
                    new_w = w_active / w_sum if w_sum != 0 else w_active
                else:
                    new_w = w_active

                new_w = max(0.0, min(1.0, new_w))
                vg_active.add([v.index], new_w, 'REPLACE')

        return {'FINISHED'}
    
class TOOLS_OT_SwapVertexGroups(Operator):
    bl_idname : str = 'kitsunetools.swap_vertex_group'
    bl_label : str = 'Swap Vertex Group'
    bl_options : Set = {'REGISTER', 'UNDO'}
    
    def execute(self,context : Context) -> Set:
        arm = get_armature(context.object)
        currBone = arm.data.bones.active
        bones = get_selected_bones(arm, sort_type=None, exclude_active= True)
        
        if len(bones) != 1:
            self.report({'WARNING'}, "Only select 2 VertexGroups/Bones")
            return {'CANCELLED'}
        
        otherBone = bones[0]
        
        if currBone.id_data != otherBone.id_data:
            self.report({'WARNING'}, "Bones selected are not in the same armature")
            return {'CANCELLED'}
        
        meshes = get_armature_meshes(arm, visible_only=getattr(context.scene.vs, 'visible_mesh_only', False))
        
        if not meshes:
            self.report({'WARNING'}, "Armature doesn't have any Meshes")
            return {'CANCELLED'}
        
        for mesh in meshes:        
            group1 = mesh.vertex_groups.get(currBone.name)
            group2 = mesh.vertex_groups.get(otherBone.name)
            
            if group1 is None:
                group1 = mesh.vertex_groups.new(name=currBone.name)
            if group2 is None:
                group2 = mesh.vertex_groups.new(name=otherBone.name)
            
            weights1 = {v.index: group1.weight(v.index) for v in mesh.data.vertices if group1.index in [g.group for g in v.groups]}
            weights2 = {v.index: group2.weight(v.index) for v in mesh.data.vertices if group2.index in [g.group for g in v.groups]}

            for vertex_index in weights1.keys():
                group2.add([vertex_index], weights1[vertex_index], 'REPLACE')
            
            for vertex_index in weights2.keys():
                group1.add([vertex_index], weights2[vertex_index], 'REPLACE')

            for vertex_index in weights1.keys():
                group1.remove([vertex_index])
            for vertex_index in weights2.keys():
                group2.remove([vertex_index])

            for vertex_index, weight in weights2.items():
                group1.add([vertex_index], weight, 'REPLACE')
            for vertex_index, weight in weights1.items():
                group2.add([vertex_index], weight, 'REPLACE')
        
        self.report({'INFO'}, f"{currBone.name} and {otherBone.name} vertex froup swapped")
        return {'FINISHED'}
    
class TOOLS_OT_curve_ramp_weights(Operator):
    bl_idname : str = 'kitsunetools.curve_ramp_weights'
    bl_label : str = 'Curve Ramp Bone Weights'
    bl_options : Set = {'REGISTER', 'UNDO'}
    
    min_weight_mask: FloatProperty(name="Min Weight Mask", default=0.001, min=0.001, max=0.9, precision=4)
    max_weight_mask: FloatProperty(name="Max Weight Mask", default=1.0, min=0.01, max=1.0, precision=4)
    invert_ramp: BoolProperty(name="Invert Ramp Direction", default=False)
    normalize_to_parent: BoolProperty(name="Normalize Weight", default=True)
    constant_mask: BoolProperty(name="Ignore Vertex Value Mask", default=False)
    
    vertex_group_target: StringProperty(
        name="Target Vertex Group",
        description="Vertex group to receive residuals",
        default=""
    )
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context : Context) -> None:
        layout = self.layout

        col = layout.column(align=True)
        col.label(text="Weight Mask:")
        col.prop(self, "min_weight_mask", slider=True)
        col.prop(self, "max_weight_mask", slider=True)

        col.separator()
        col.label(text="Options:")
        row = col.row(align=True)
        col.prop(self, "invert_ramp", toggle=True)
        row.prop(self, "constant_mask", toggle=True)
        row.prop(self, "normalize_to_parent", toggle=True)

        col.separator()
        col.label(text="Target Vertex Group:")
        
        armature = get_armature(context.object)
        if armature:
            col.prop_search(
                self,
                "vertex_group_target",
                armature.data,
                "bones",
                text=""
            )
        else:
            col.prop_search(
                self,
                "vertex_group_target",
                context.object,
                "vertex_groups",
                text=""
            )
            
        col = layout.column(align=True)
        tool_settings = context.tool_settings
        brush = tool_settings.weight_paint.brush
        row = col.row(align=True)
            
        col.template_curve_mapping(brush, "curve", brush=False)
        row = col.row(align=True)
        row.operator("brush.curve_preset", icon='SMOOTHCURVE', text="").shape = 'SMOOTH'
        row.operator("brush.curve_preset", icon='SPHERECURVE', text="").shape = 'ROUND'
        row.operator("brush.curve_preset", icon='ROOTCURVE', text="").shape = 'ROOT'
        row.operator("brush.curve_preset", icon='SHARPCURVE', text="").shape = 'SHARP'
        row.operator("brush.curve_preset", icon='LINCURVE', text="").shape = 'LINE'
        row.operator("brush.curve_preset", icon='NOCURVE', text="").shape = 'MAX'
    
    def execute(self, context : Context) -> Set:
        arm_obj = get_armature(context.object)
            
        if arm_obj is None:
            return {'CANCELLED'}
        
        if arm_obj.select_get():
            selected_bones : list[PoseBone | None] = get_selected_bones(arm_obj, bone_type='POSEBONE', sort_type='TO_FIRST') # type: ignore
        else:
            selected_bones : list[PoseBone | None] = [arm_obj.pose.bones.get(context.object.vertex_groups.active.name)]
            
        if not selected_bones:
            self.report({'ERROR'}, "No bones selected.")
            return {'CANCELLED'}
        
        og_arm_pose_mode = arm_obj.data.pose_position
        arm_obj.data.pose_position = 'REST'
        bpy.context.view_layer.update()
        
        with preserve_context_mode(context.object,'WEIGHT_PAINT'), preserve_armature_state(arm_obj):
            for bone in selected_bones:
                target_vg = self.vertex_group_target if self.vertex_group_target else None
                curve = context.tool_settings.weight_paint.brush.curve

                reapply_vertexgroup_as_curve(
                    arm=arm_obj,
                    bones=[bone],   # type: ignore
                    curve=curve,
                    invert=self.invert_ramp,
                    vertex_group_target=target_vg,
                    min_weight_mask=self.min_weight_mask,
                    max_weight_mask=self.max_weight_mask,
                    normalize_to_parent=self.normalize_to_parent,
                    constant_mask=self.constant_mask,
                )
        
        arm_obj.data.pose_position = og_arm_pose_mode
        bpy.context.view_layer.update()
        
        self.report({'INFO'}, f'Processed {len(selected_bones)} Bones')
        return {'FINISHED'}

class TOOLS_OT_multi_weight_paint_start(bpy.types.Operator):
    bl_idname = "tools.multi_weight_paint_start"
    bl_label = "Start Multi-Object Weight Paint"
    bl_description = "Prepare selected meshes for multi-object weight painting"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context) -> bool:
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        return context.mode == 'OBJECT' and len(selected_meshes) > 1
    
    def execute(self, context) -> set:
        original_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not original_meshes:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}
        
        armature = None
        for obj in context.selected_objects:
            if obj.type == 'ARMATURE':
                armature = obj
                break
        
        if not armature:
            for obj in original_meshes:
                for mod in obj.modifiers:
                    if mod.type == 'ARMATURE' and mod.object:
                        armature = mod.object
                        break
                if armature:
                    break
        
        bpy.ops.object.select_all(action='DESELECT')
        
        duplicated_meshes = []
        original_names = []
        
        for obj in original_meshes:
            vg_name = f"__temp_id_vg_{obj.name}"
            id_vg = obj.vertex_groups.new(name=vg_name)
            all_verts = [v.index for v in obj.data.vertices]
            id_vg.add(all_verts, 1.0, 'REPLACE')
            obj["__temp_id_vg_name"] = vg_name

            obj.select_set(True)
            context.view_layer.objects.active = obj
            bpy.ops.object.duplicate()
            
            dup_obj = context.active_object
            dup_obj.name = f"temp_wgt_{obj.name}"
            dup_obj["original_mesh"] = obj.name

            for mod in list(dup_obj.modifiers):
                if mod.type != 'ARMATURE':
                    dup_obj.modifiers.remove(mod)
            
            duplicated_meshes.append(dup_obj)
            original_names.append(obj.name)
            
            obj.select_set(False)
            dup_obj.select_set(False)
            obj.hide_set(True)
        
        for obj in duplicated_meshes:
            obj.select_set(True)
        
        context.view_layer.objects.active = duplicated_meshes[0]
        bpy.ops.object.join()
        
        combined_obj = context.active_object
        combined_obj.name = "temp_wgt_combined"
        combined_obj["is_temp_weight_paint"] = True
        combined_obj["original_meshes"] = original_names
        
        if armature:
            armature.select_set(True)
        
        context.view_layer.objects.active = combined_obj
        
        bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
        
        self.report({'INFO'}, f"Combined {len(original_meshes)} meshes for weight painting")
        return {'FINISHED'}

class TOOLS_OT_multi_weight_paint_finish(bpy.types.Operator):
    bl_idname = "tools.multi_weight_paint_finish"
    bl_label = "Finish Multi-Object Weight Paint"
    bl_description = "Transfer weights back to original meshes and cleanup"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context) -> bool:
        ob = context.active_object
        return bool(is_mesh(ob) and ob.get("is_temp_weight_paint"))
    
    def execute(self, context) -> set:
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        combined_obj = context.active_object
        original_names = combined_obj.get("original_meshes", [])
        
        if not original_names:
            self.report({'WARNING'}, "No original mesh data found")
            return {'CANCELLED'}
        
        original_meshes = []
        for name in original_names:
            obj = bpy.data.objects.get(name)
            if obj:
                original_meshes.append(obj)
                obj.hide_set(False)
        
        if not original_meshes:
            self.report({'WARNING'}, "Original meshes not found")
            return {'CANCELLED'}
        
        bpy.ops.object.select_all(action='DESELECT')
        
        for target_obj in original_meshes:
            vg_name = target_obj.get("__temp_id_vg_name")
            if not vg_name or not combined_obj.vertex_groups.get(vg_name):
                self.report({'WARNING'}, f"Object {target_obj.name} missing ID vertex group. Skipping.")
                continue

            # Create a temporary object with only the relevant part of the mesh
            context.view_layer.objects.active = combined_obj
            combined_obj.select_set(True)
            bpy.ops.object.duplicate()
            temp_source_obj = context.active_object
            combined_obj.select_set(False)
            
            try:
                vg_index = temp_source_obj.vertex_groups[vg_name].index
                
                bm = bmesh.new()
                bm.from_mesh(temp_source_obj.data)
                
                deform_layer = bm.verts.layers.deform.verify()
                
                verts_to_delete = [v for v in bm.verts if vg_index not in v[deform_layer]]
                
                bmesh.ops.delete(bm, geom=verts_to_delete, context='VERTS')
                
                bm.to_mesh(temp_source_obj.data)
                bm.free()
                temp_source_obj.data.update()

                # Transfer weights using this new temp object
                if "DataTransfer" in target_obj.modifiers:
                    target_obj.modifiers.remove(target_obj.modifiers["DataTransfer"])

                mod = target_obj.modifiers.new(name="DataTransfer", type='DATA_TRANSFER')
                mod.object = temp_source_obj
                mod.use_vert_data = True
                mod.data_types_verts = {'VGROUP_WEIGHTS'}
                mod.vert_mapping = 'TOPOLOGY'
                
                override = context.copy()
                override['object'] = target_obj
                override['modifier'] = mod
                with context.temp_override(**override):
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                
                self.report({'INFO'}, f"Successfully transferred weights to {target_obj.name} using Topology.")

            except Exception as e:
                self.report({'ERROR'}, f"Failed to transfer weights to {target_obj.name}: {e}")

            finally:
                # Cleanup the temporary source object
                bpy.data.objects.remove(temp_source_obj, do_unlink=True)

            # Cleanup the ID vertex group
            vg = target_obj.vertex_groups.get(vg_name)
            if vg:
                target_obj.vertex_groups.remove(vg)
            if "__temp_id_vg_name" in target_obj:
                del target_obj["__temp_id_vg_name"]

        # Final cleanup of the main combined object
        bpy.ops.object.select_all(action='DESELECT')
        combined_obj.select_set(True)
        context.view_layer.objects.active = combined_obj
        bpy.ops.object.delete()
        
        if original_meshes:
            for obj in original_meshes:
                obj.select_set(True)
            context.view_layer.objects.active = original_meshes[0]
        
        self.report({'INFO'}, f"Weight transfer completed for {len(original_meshes)} meshes")
        return {'FINISHED'}


class TOOLS_OT_multi_weight_paint_cancel(bpy.types.Operator):
    bl_idname = "tools.multi_weight_paint_cancel"
    bl_label = "Cancel"
    bl_description = "Discard changes and cleanup"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context) -> bool:
        ob = context.active_object
        return bool(is_mesh(ob) and ob.get("is_temp_weight_paint"))

    def execute(self, context) -> set:
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        combined_obj = context.active_object
        original_names = combined_obj.get("original_meshes", [])

        if not original_names:
            self.report({'WARNING'}, "No original mesh data found")
            return {'CANCELLED'}

        original_meshes = []
        for name in original_names:
            obj = bpy.data.objects.get(name)
            if obj:
                original_meshes.append(obj)
                obj.hide_set(False)
                obj.select_set(True)

        bpy.ops.object.select_all(action='DESELECT')
        combined_obj.select_set(True)
        context.view_layer.objects.active = combined_obj
        bpy.ops.object.delete()

        if original_meshes:
            for obj in original_meshes:
                obj.select_set(True)
            context.view_layer.objects.active = original_meshes[0]
        else:
            self.report({'WARNING'}, "Original meshes not found, please unhide them from the outliner manually")

        self.report({'INFO'}, "Cancelled multi-object weight paint. Changes discarded.")
        return {'FINISHED'}
    