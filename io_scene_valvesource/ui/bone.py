import bpy
from bpy.props import FloatProperty, BoolProperty, IntProperty, EnumProperty
from bpy.types import UILayout, Context, Operator, Object, Event
from typing import Set
from mathutils import Vector

from ..core.commonutils import(
    is_armature, is_mesh, draw_title_box, draw_wrapped_text_col,
    getArmature, PreserveContextMode, getSelectedBones,
)

from ..core.armatureutils import(
    split_bone, PreserveArmatureState, removeBone, mergeBones, CentralizeBonePairs
)

from ..utils import get_id
from .common import Tools_SubCategoryPanel

class TOOLS_PT_Bone(Tools_SubCategoryPanel):
    bl_label: str = "Bone Tools"

    def draw(self, context: Context) -> None:
        layout = self.layout
        bx = draw_title_box(layout, TOOLS_PT_Bone.bl_label, icon='BONE_DATA')
        
        armature = getArmature(context.object)
        
        if not (is_armature(armature) or is_mesh(armature)):
            draw_wrapped_text_col(bx, get_id("panel_select_armature"), max_chars=40, icon='HELP')
            return
        
        scene_vs = context.scene.vs
        
        main_col = bx.column(align=False)
        
        # Bone Merging Section
        merge_box = draw_title_box(main_col, text='Bone Merging', icon='AUTOMERGE_ON', align=True)
        
        merge_row = merge_box.row(align=True)
        merge_row.scale_y = 1.3
        merge_row.operator(TOOLS_OT_MergeBones.bl_idname, text='To Active').mode = 'TO_ACTIVE'
        merge_row.operator(TOOLS_OT_MergeBones.bl_idname, text='To Parent').mode = 'TO_PARENT'
        
        merge_box.separator(factor=0.5)
        
        options_col = merge_box.column(align=True)
        options_col.scale_y = 0.9
        options_col.label(text='Merge Mode')
        options_col.prop(scene_vs, 'merge_bone_options',expand=True)
        options_col.prop(scene_vs, 'visible_mesh_only')
        
        main_col.separator()
        
        # Bone Alignment Section
        align_box = draw_title_box(main_col, text='Bone Alignment', icon='ORIENTATION_VIEW', align=True)
        
        align_box.operator(TOOLS_OT_ReAlignBones.bl_idname, icon='ALIGN_JUSTIFY', text='Re-Align Bones')
        
        align_box.separator(factor=0.5)
        
        copy_row = align_box.row(align=True)
        copy_row.scale_y = 1.3
        copy_row.operator(TOOLS_OT_CopyTargetRotation.bl_idname, text='From Active').copy_source = 'ACTIVE'
        copy_row.operator(TOOLS_OT_CopyTargetRotation.bl_idname, text='From Parent').copy_source = 'PARENT'
        
        align_box.separator(factor=0.5)
        
        axis_col = align_box.column(align=True)
        axis_col.scale_y = 0.9
        axis_col.label(text='Exclude Axis:')
        axis_col.prop(scene_vs, 'alignment_exclude_axes', expand=True)
        
        main_col.separator()
        
        # Bone Modifiers Section
        mod_box = draw_title_box(main_col, text='Bone Modifiers', icon='MODIFIER', align=True)
        mod_box.operator(TOOLS_OT_SplitBone.bl_idname, icon='MOD_SUBSURF', text='Split Bone').weights_only = False
        
class TOOLS_OT_CopyTargetRotation(Operator):
    bl_idname : str = "tools.copy_target_bone_rotation"
    bl_label : str = "Copy Parent/Active Rotation"
    bl_options : Set = {'REGISTER', 'UNDO'}

    copy_source: EnumProperty(
        name="Copy From",
        description="Choose which bone to copy orientation from",
        items=[
            ('PARENT', "Parent", "Copy rotation from parent bone"),
            ('ACTIVE', "Active", "Copy rotation from active bone"),
        ],
        default='PARENT'
    )

    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool((is_armature(context.object) or is_mesh(context.object)) and context.object.mode in ['WEIGHT_PAINT', 'EDIT', 'POSE'])

    def execute(self, context : Context) -> Set:
        vs_sce = context.scene.vs

        error = 0
        with PreserveContextMode(context.object, 'OBJECT'):
            bones = {}
            for ob in context.selected_objects:
                if not ob.visible_get() or ob.type != 'ARMATURE': continue
                for b in getSelectedBones(ob, sort_type='TO_FIRST', bone_type='BONE'):
                    bones[b.name] = ob

            for bone_name, armature in bones.items():
                try:
                    bpy.context.view_layer.objects.active = armature
                    bpy.ops.object.mode_set(mode='EDIT')
                    active_bone = context.active_bone
                    
                    editbone = armature.data.edit_bones.get(bone_name)
                    if self.copy_source == 'PARENT':
                        reference_bone = editbone.parent
                    else: 
                        reference_bone = active_bone if active_bone else None

                    if not reference_bone:
                        continue

                    editbone.use_connect = False

                    ref_head_world = armature.matrix_world @ reference_bone.head
                    ref_tail_world = armature.matrix_world @ reference_bone.tail

                    ref_direction = (ref_tail_world - ref_head_world).normalized()

                    original_head_world = armature.matrix_world @ editbone.head
                    new_head_local = armature.matrix_world.inverted() @ original_head_world
                    editbone.head = new_head_local

                    original_length = (editbone.tail - editbone.head).length
                

                    if 'EXCLUDE_X' in vs_sce.alignment_exclude_axes:
                        ref_direction.x = (editbone.tail - editbone.head).normalized().x 
                    if 'EXCLUDE_Y' in vs_sce.alignment_exclude_axes:
                        ref_direction.y = (editbone.tail - editbone.head).normalized().y 
                    if 'EXCLUDE_Z' in vs_sce.alignment_exclude_axes:
                        ref_direction.z = (editbone.tail - editbone.head).normalized().z 

                    ref_direction.normalize()
                    editbone.tail = editbone.head + (ref_direction * original_length)

                    if 'EXCLUDE_ROLL' not in vs_sce.alignment_exclude_axes:
                        editbone.roll = reference_bone.roll
                    if 'EXCLUDE_SCALE' not in vs_sce.alignment_exclude_axes:
                        editbone.length = reference_bone.length

                except Exception as e:
                    print(f'Failed to re-orient bone: {e}')
                    error += 1
                    continue

        if error == 0:
            self.report({'INFO'}, "Orientation copied successfully")
        else:
            self.report({'WARNING'}, f"Copied with {error} errors")

        return {"FINISHED"}

class TOOLS_OT_ReAlignBones(Operator):
    bl_idname : str = 'tools.realign_bone'
    bl_label : str = 'ReAlign Bones'
    bl_options : Set = {'REGISTER', 'UNDO'}
    
    alignment_mode: EnumProperty(
        name="Alignment Mode",
        description="Choose how to align the bone tail",
        items=[
            ('AVERAGE_ALL', "Average All", "Align to average position of all children"),
            ('ONLY_SINGLE_CHILD', "Only Single Child", "Align only if there is a single child bone")
        ],
        default='ONLY_SINGLE_CHILD'
    )

    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool((is_armature(context.object) or is_mesh(context.object)) and context.object.mode in ['WEIGHT_PAINT', 'EDIT', 'POSE'])
        
    def draw(self, context : Context) -> None:
        layout = self.layout
        layout.prop(self, "alignment_mode")

    def realign_bone_tail(self, bone, exclude_x=False, exclude_y=False, exclude_z=False, exclude_roll=False):
        child_positions = [child.head for child in bone.children]
        original_bone_roll = bone.roll

        new_tail = None

        if child_positions:
            if self.alignment_mode == 'AVERAGE_ALL':
                avg_position = sum(child_positions, Vector((0, 0, 0))) / len(child_positions)
                new_tail = Vector((
                    bone.tail.x if exclude_x else avg_position.x,
                    bone.tail.y if exclude_y else avg_position.y,
                    bone.tail.z if exclude_z else avg_position.z
                ))

            elif self.alignment_mode == 'ONLY_SINGLE_CHILD' and len(child_positions) == 1:
                child_position = child_positions[0]
                new_tail = Vector((
                    bone.tail.x if exclude_x else child_position.x,
                    bone.tail.y if exclude_y else child_position.y,
                    bone.tail.z if exclude_z else child_position.z
                ))
                
            if new_tail:
                if all([exclude_x, exclude_y, exclude_z]):
                    if self.alignment_mode == 'AVERAGE_ALL':
                        avg_vec = sum((pos - bone.head for pos in child_positions), Vector((0,0,0))) / len(child_positions)
                        bone.length = avg_vec.length
                    elif self.alignment_mode == 'ONLY_SINGLE_CHILD' and len(child_positions) == 1:
                        vec_to_child = child_positions[0] - bone.head
                        bone.length = vec_to_child.length
                else:
                    bone.tail = new_tail

                if not exclude_roll:
                    bone.align_roll(bone.tail - bone.head)
                else:
                    bone.roll = original_bone_roll

    def execute(self, context : Context) -> Set:
        armature = getArmature(context.object)

        if not armature:
            self.report({'WARNING'}, "No armature selected")
            return {'CANCELLED'}

        vs_sce = context.scene.vs
        
        with PreserveContextMode(armature, 'EDIT'):
            selectedbones = getSelectedBones(armature,'BONE','TO_FIRST')
            
            editbones = []
            for bone in selectedbones:
                armatureid = bone.id_data
                editbones.append(armatureid.edit_bones.get(bone.name))
            
            if editbones is None: 
                self.report({'WARNING'}, "No Bones Selected")
                return {'CANCELLED'}
                
            for bone in editbones:
                self.realign_bone_tail(bone,
                                    exclude_x= ('EXCLUDE_X' in vs_sce.alignment_exclude_axes),
                                    exclude_y= ('EXCLUDE_Y' in vs_sce.alignment_exclude_axes),
                                    exclude_z= ('EXCLUDE_Z' in vs_sce.alignment_exclude_axes),
                                    exclude_roll= ('EXCLUDE_ROLL' in vs_sce.alignment_exclude_axes)
                                    )
        self.report({'INFO'}, "Bones realigned successfully")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
class TOOLS_OT_SplitBone(Operator):
    bl_idname : str = 'tools.split_bone'
    bl_label : str = 'Split Bone'
    bl_options : Set = {'REGISTER', 'UNDO'}
    
    subdivisions: IntProperty(
        name='Subdivisions', 
        min=2, 
        max=20, 
        default=2,
        description='Number of segments to split the bone into'
    )
    
    minweight : FloatProperty(
        name='Min Weight', min=0.001,max = 0.01, default=0.001, precision=3)
    
    falloff : IntProperty(
        name='Falloff', min=5, max=20, default=10)
    
    weights_only: BoolProperty(
        name='Weights Only',default=False)
    
    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool((is_armature(context.object) or is_mesh(context.object)) and context.object.mode in ["EDIT", "POSE", "WEIGHT_PAINT"])
    
    def invoke(self, context : Context, event : Event) -> Set:
        ob : Object | None = context.object
        if ob.mode in ['POSE', 'WEIGHT_PAINT']:
            if any([b for b in getArmature(context.object).data.bones if b.select]):
                return context.window_manager.invoke_props_dialog(self)
        elif ob.mode == 'EDIT':
            if any([b for b in getArmature(context.object).data.edit_bones if b.select]):
                return context.window_manager.invoke_props_dialog(self)
        return {'CANCELLED'}

    def draw(self, context : Context) -> None:
        layout = self.layout
        col = layout.column(align=True)
        col.prop(self, 'subdivisions')
        col.prop(self, 'minweight')
        col.prop(self, 'falloff')

    def execute(self, context : Context) -> Set:
        arm = getArmature(context.object)
        
        if arm is None: return {'CANCELLED'}
        
        constraint_data = []
        
        with PreserveArmatureState(arm), PreserveContextMode(context.object, 'OBJECT'):
            context.view_layer.objects.active = arm
            
            bones = getSelectedBones(arm, bone_type='POSEBONE')
            boneNames = [b.name for b in getSelectedBones(arm, bone_type='BONE')]
            
            if bones is None or boneNames is None:
                return {'CANCELLED'}

            if not self.weights_only:
                for bone in bones:
                    for con in bone.constraints:
                        data = {
                            'original_bone': bone.name,
                            'type': con.type,
                            'name': con.name,
                            'properties': {}
                        }
                        for prop in con.bl_rna.properties:
                            if prop.is_readonly or prop.identifier in {'rna_type', 'name', 'type'}:
                                continue
                            try:
                                val = getattr(con, prop.identifier)
                                data['properties'][prop.identifier] = val
                            except Exception as e:
                                print(f"Error getting property {prop.identifier}: {e}")
                        constraint_data.append(data)
            
            bpy.ops.object.mode_set(mode='EDIT')
            bones = [arm.data.edit_bones.get(b) for b in boneNames]
            split_bone(bones, self.subdivisions, weights_only=self.weights_only,min_weight_cap=self.minweight, falloff=self.falloff )
            
            if not self.weights_only:
                bpy.ops.object.mode_set(mode='OBJECT')

                for data in constraint_data:
                    base_name = data['original_bone']

                    for pb in arm.pose.bones:
                        if pb.name.startswith(base_name):
                            new_con = pb.constraints.new(type=data['type'])
                            new_con.name = data['name']

                            for prop, val in data['properties'].items():
                                try:
                                    setattr(new_con, prop, val)
                                except Exception as e:
                                    print(f"Failed to set {prop} on constraint '{new_con.name}' for bone '{pb.name}': {e}")

        return {'FINISHED'}

class TOOLS_OT_MergeBones(Operator):
    bl_idname: str = 'tools.merge_bones'
    bl_label: str = 'Merge Bones'
    bl_options: Set = {'REGISTER', 'UNDO'}
    
    mode: EnumProperty(items=[
        ('TO_PARENT', 'To Parent', ''),
        ('TO_ACTIVE', 'To Active', '')
    ])
    
    @classmethod
    def poll(cls, context: Context) -> bool:
        ob: Object | None = context.object
        arm = ob if is_armature(ob) else getArmature(ob) if is_mesh(ob) else None
        
        if arm is None or arm.mode not in ['WEIGHT_PAINT', 'POSE', 'EDIT']:
            return False

        bones = (arm.data.edit_bones if arm.mode == 'EDIT' else arm.data.bones)
        return any(b.select and not b.hide for b in bones)
    
    def execute(self, context: Context) -> Set:
        if context.mode == 'PAINT_WEIGHT':
            armatures = {getArmature(context.object)}
        else:
            armatures = {getArmature(ob) for ob in context.selected_objects if getArmature(ob)}
            
        vs_sce = context.scene.vs
        bones_to_remove_map = {}
        vgroups_processed_map = {}

        with PreserveContextMode(mode='OBJECT'):
            for arm in armatures:
                bpy.context.view_layer.objects.active = arm
                
                if self.mode == 'TO_ACTIVE':
                    result = self._merge_to_active(arm, context, vs_sce)
                else:
                    result = self._merge_to_parent(arm, vs_sce)
                
                if result:
                    bones_to_remove_map[arm] = result[0]
                    vgroups_processed_map[arm] = result[1]

            bpy.ops.object.mode_set(mode='EDIT')
            
            for arm, bones_to_remove in bones_to_remove_map.items():
                snap_parent = (self.mode == 'TO_PARENT' and 
                             vs_sce.merge_bone_options == 'SNAP_PARENT')
                source = context.active_bone.name if self.mode == 'TO_ACTIVE' else None
                
                removeBone(arm, bones_to_remove, 
                          match_parent_to_head=snap_parent,
                          source=source)

        total_merged = sum(len(vg) for vg in vgroups_processed_map.values())
        self.report({'INFO'}, f'{total_merged} Weights merged')
        return {'FINISHED'}
    
    def _merge_to_active(self, arm, context, vs_sce):
        sel_bones = getSelectedBones(arm, 'BONE', sort_type='TO_FIRST', exclude_active=True)
        if not sel_bones:
            return None

        if not context.active_bone:
            self.report({'WARNING'}, 'No active selected bone')
            return None

        keep_bone = vs_sce.merge_bone_options in ['KEEP_BONE', 'KEEP_BOTH']
        keep_weight = vs_sce.merge_bone_options == 'KEEP_BOTH'
        centralize = vs_sce.merge_bone_options == 'CENTRALIZE'

        if centralize:
            bones_to_remove, merged_pairs, vgroups_processed = mergeBones(
                arm, context.active_bone, sel_bones,
                keep_bone=False,
                visible_mesh_only=vs_sce.visible_mesh_only,
                keep_original_weight=False,
                centralize_bone=True
            )
            CentralizeBonePairs(arm, merged_pairs)
        else:
            bones_to_remove, vgroups_processed = mergeBones(
                arm, context.active_bone, sel_bones,
                keep_bone=keep_bone,
                visible_mesh_only=vs_sce.visible_mesh_only,
                keep_original_weight=keep_weight,
                centralize_bone=False
            )

        return bones_to_remove, vgroups_processed
    
    def _merge_to_parent(self, arm, vs_sce):
        sel_bones = getSelectedBones(arm, sort_type='TO_FIRST', 
                                     bone_type='BONE', exclude_active=False)
        if not sel_bones:
            return None
        
        keep_bone = vs_sce.merge_bone_options in ['KEEP_BONE', 'KEEP_BOTH']
        keep_weight = vs_sce.merge_bone_options == 'KEEP_BOTH'
        
        bones_to_remove, vgroups_processed = mergeBones(
            arm, None, sel_bones,
            keep_bone=keep_bone,
            visible_mesh_only=vs_sce.visible_mesh_only,
            keep_original_weight=keep_weight,
            centralize_bone=False
        )
        
        return bones_to_remove, vgroups_processed