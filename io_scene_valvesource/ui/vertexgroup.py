import bpy
from bpy.props import FloatProperty, BoolProperty, StringProperty
from bpy.types import UILayout, Context, Object, Operator, PoseBone
from typing import Set

from .common import Tools_SubCategoryPanel
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

class TOOLS_PT_VertexGroup(Tools_SubCategoryPanel):
    bl_label : str = "Vertex Group"
    
    def draw(self, context : Context) -> None:
        l : UILayout = self.layout
        bx : UILayout = draw_title_box_layout(l, TOOLS_PT_VertexGroup.bl_label, icon='GROUP_VERTEX')
        
        ob : Object | None = context.object
        if (is_mesh(ob) and ob.mode == 'WEIGHT_PAINT') or (is_armature(ob) and ob.mode == 'POSE'): pass
        else:
            draw_wrapped_texts(bx,get_id("panel_select_mesh_vgroup"),max_chars=40 , icon='HELP')
            return
        
        col = bx.column()
        col.prop(context.scene.vs, 'visible_mesh_only')
        col.operator(TOOLS_OT_WeightMath.bl_idname, icon='LINENUMBERS_ON')
        col.operator(TOOLS_OT_SwapVertexGroups.bl_idname,icon='AREA_SWAP')
        col.operator(TOOLS_OT_SplitActiveWeightLinear.bl_idname,icon='SPLIT_VERTICAL')
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

class TOOLS_OT_WeightMath(Operator):
    bl_idname : str = "tools.weight_math"
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
    bl_idname : str = 'tools.swap_vertex_group'
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
    bl_idname : str = 'tools.curve_ramp_weights'
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

class TOOLS_OT_SplitActiveWeightLinear(Operator):
    bl_idname : str = 'tools.split_active_weights_linear'
    bl_label : str = 'Split Active Weights Linearly'
    bl_options : Set = {'REGISTER', 'UNDO'}

    smoothness: FloatProperty(
        name="Smoothness",
        description="Smoothness of the weight split (0 = hard cut, 1 = full smooth blend)",
        min=0.0, max=1.0,
        default=0.6
    )

    @classmethod
    def poll(cls, context : Context) -> bool:
        ob : Object | None = context.object
        if ob is None: return False
        if ob.mode not in ['WEIGHT_PAINT', 'POSE']: return False
        
        return bool(get_armature(ob))
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def get_vgroup_index(self, mesh, name):
        for i, vg in enumerate(mesh.vertex_groups):
            if vg.name == name:
                return i
        return None

    def clamp(self, x, a, b):
        return max(a, min(x, b))

    def remap(self, value, minval, maxval):
        if maxval - minval == 0:
            return 0.5
        return (value - minval) / (maxval - minval)

    def project_point_onto_line(self, p, a, b):
        ap = p - a
        ab = b - a
        ab_len_sq = ab.length_squared
        if ab_len_sq == 0.0:
            return 0.0
        return self.clamp(ap.dot(ab) / ab_len_sq, 0.0, 1.0)

    def execute(self, context : Context) -> Set:
        arm = get_armature(context.object)
        
        bones = get_selected_bones(arm,sort_type=None,bone_type='BONE',exclude_active=True)
        active_bone = arm.data.bones.active
        
        if not bones or len(bones) != 2 or not active_bone:
            self.report({'WARNING'}, "Select 3 bones: 2 others and 1 active (middle split point).")
            return {'CANCELLED'}
        
        og_arm_pose_mode = arm.data.pose_position
        arm.data.pose_position = 'REST'
        bpy.context.view_layer.update()

        bone1 = arm.pose.bones.get(bones[0].name)
        bone2 = arm.pose.bones.get(bones[1].name)
        active = active_bone

        bone1_name = bone1.name
        bone2_name = bone2.name
        active_name = active.name

        arm_matrix = arm.matrix_world
        p1 = arm_matrix @ ((bone1.head + bone1.tail) * 0.5)
        p2 = arm_matrix @ ((bone2.head + bone2.tail) * 0.5)

        meshes = get_armature_meshes(arm, visible_only=context.scene.vs.visible_mesh_only)

        for mesh in meshes:
            vg_active = self.get_vgroup_index(mesh, active_name)
            vg1 = mesh.vertex_groups.get(bone1_name)
            if vg1 is None:
                vg1 = mesh.vertex_groups.new(name=bone1_name)

            vg2 = mesh.vertex_groups.get(bone2_name)
            if vg2 is None:
                vg2 = mesh.vertex_groups.new(name=bone2_name)

            if vg_active is None or vg1 is None or vg2 is None:
                continue

            vtx_weights = {}
            for v in mesh.data.vertices:
                for g in v.groups:
                    if g.group == vg_active:
                        vtx_weights[v.index] = g.weight
                        break

            for vidx, weight in vtx_weights.items():
                vertex = mesh.data.vertices[vidx]
                world_pos = mesh.matrix_world @ vertex.co

                t = self.project_point_onto_line(world_pos, p1, p2)

                # THIS WAS BACKWARDS BEFORE
                if self.smoothness == 0.0:
                    w1 = weight if t < 0.5 else 0.0
                    w2 = weight if t >= 0.5 else 0.0
                else:
                    s = self.smoothness
                    edge0 = 0.5 - s * 0.5
                    edge1 = 0.5 + s * 0.5
                    smooth_t = self.remap(t, edge0, edge1)
                    smooth_t = self.clamp(smooth_t, 0.0, 1.0)
                    w1 = weight * (1.0 - smooth_t)
                    w2 = weight * smooth_t

                vg1.add([vidx], w1, 'ADD')
                vg2.add([vidx], w2, 'ADD')

            mesh.vertex_groups.remove(mesh.vertex_groups[vg_active])
            mesh.vertex_groups.active = vg1
        
        with preserve_context_mode(arm, 'EDIT'):
            remove_bone(arm,active_bone.name)
            arm.data.edit_bones.active = arm.data.edit_bones.get(bones[0].name)
        
        arm.data.pose_position = og_arm_pose_mode

        self.report({'INFO'}, f"Split {active_name} between {bone1_name} and {bone2_name}")
        return {'FINISHED'} 

