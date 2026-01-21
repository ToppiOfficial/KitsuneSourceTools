import bpy, re
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from bpy.types import Context, Operator, Object
from typing import Set

from ..core.commonutils import (
    is_armature, is_mesh, draw_title_box_layout, draw_wrapped_texts,
    get_armature, get_armature_meshes, preserve_context_mode,
    get_selected_bones, unselect_all, has_selected_bones
)

from ..core.meshutils import (
    remove_unused_vertexgroups
)

from ..core.armatureutils import (
    apply_current_pose_as_restpose, remove_bone, filter_exclude_vertexgroup_names,
    merge_armatures, copy_target_armature_visualpose, remove_empty_bonecollections,
    apply_current_pose_shapekey
)

from ..utils import get_id
from .common import KITSUNE_PT_ToolsPanel, ShowConsole

class TOOLS_PT_Armature(KITSUNE_PT_ToolsPanel):
    bl_label : str = "Armature Tools"
    
    def draw(self, context : Context) -> None:
        layout = self.layout
        bx = layout.box()
        
        if is_armature(context.object) or is_mesh(context.object): pass
        else:
            draw_wrapped_texts(bx,get_id("panel_select_armature"),max_chars=40 , icon='HELP')
            return
        
        col = bx.column(align=True)
        col.label(text='Apply Pose As Rest Pose')
        in_pose = bool(context.mode == 'POSE')
        
        row = col.row(align=True)
        row.scale_y = 1.5
        row.operator(TOOLS_OT_Apply_Current_Pose_As_RestPose.bl_idname,icon='POSE_HLT',text='Entire Armature').selected_only = False
        
        op_col = row.column(align=True)
        op_col.enabled = has_selected_bones(context.object) and in_pose
        op_col.operator(TOOLS_OT_Apply_Current_Pose_As_RestPose.bl_idname,icon='POSE_HLT', text='Selected Bones').selected_only = True
        
        row = col.row(align=True)
        row.scale_y = 1
        row.enabled = in_pose
        row.operator(TOOLS_OT_Apply_Current_Pose_As_Shapekey.bl_idname,icon='SHAPEKEY_DATA')
        
        col = bx.column()
        col.label(text='Multi-Armature Tools')
        
        col.operator(TOOLS_OT_MergeArmatures.bl_idname,icon='AUTOMERGE_ON')
        col.operator(TOOLS_OT_CleanUnWeightedBones.bl_idname,icon='GROUP_BONE')
        
        col = bx.column(align=True)
        col.operator(TOOLS_OT_CopyVisPosture.bl_idname,icon='POSE_HLT',text=f'{TOOLS_OT_CopyVisPosture.bl_label} (LOCATION)').copy_type = 'ORIGIN'
        col.operator(TOOLS_OT_CopyVisPosture.bl_idname,icon='POSE_HLT',text=f'{TOOLS_OT_CopyVisPosture.bl_label} (ROTATION)').copy_type = 'ANGLES'
 
# ------------------------------------------------------------------
#
#   Applying current pose
#
# ------------------------------------------------------------------
 
class Apply_Pose_Base:
    def execute(self, context : Context) -> Set:
        
        has_shapekey_prop = hasattr(self, 'as_shapekey')
        
        with preserve_context_mode(None, 'OBJECT'):
            armatures : Set[Object | None] = {get_armature(o) for o in context.selected_objects}
            
            success_count = 0
            
            for armature in armatures:
                if has_shapekey_prop: success = apply_current_pose_shapekey(armature=armature, shapekey_name=self.shapekey_name.strip())
                else:
                    if self.selected_only:
                        selected_bones = get_selected_bones(armature=armature, bone_type='POSEBONE')
                        
                        for posebone in armature.pose.bones:
                            if posebone.name in {pb.name for pb in selected_bones}: continue
                            posebone.matrix_basis.identity()
                    
                    success = apply_current_pose_as_restpose(armature=armature)
                    
                if success: success_count += 1
                
        if success_count > 0:
            if len(armatures) == 1: message = 'Applied as Rest Pose'
            else: message = f'Applied {len(armatures)} Armatures as Rest Pose'

            if not has_shapekey_prop: bpy.ops.object.mode_set(mode='OBJECT')
            
            self.report({'INFO'}, message)
            return {'FINISHED'}

        else:
            return {'CANCELLED'}

class TOOLS_OT_Apply_Current_Pose_As_RestPose(Apply_Pose_Base, Operator):
    bl_idname : str = "kitsunetools.apply_pose_as_restpose"
    bl_label : str = "Apply Pose As Restpose"
    bl_options : Set = {'REGISTER', 'UNDO'}
    
    selected_only : BoolProperty(name='Selected Only', default=False)
    
    @classmethod
    def poll(cls, context):
        return is_armature(context.object)
    
    def draw(self, context):
        layout = self.layout

class TOOLS_OT_Apply_Current_Pose_As_Shapekey(Apply_Pose_Base, Operator):
    bl_idname : str = "kitsunetools.apply_pose_as_shapekey"
    bl_label : str = "Apply Pose As Shapekey"
    bl_options : Set = {'REGISTER', 'UNDO'}
    
    as_shapekey : BoolProperty(default=True) # this should always be True
    shapekey_name : StringProperty(name='Shapekey Name')
    
    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool(is_armature(context.object) and context.mode in {'POSE', 'OBJECT'})
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=150)
        
    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'shapekey_name')

# ------------------------------------------------------------------

class TOOLS_OT_CleanUnWeightedBones(Operator):
    bl_idname: str = 'kitsunetools.clean_unweighted_bones'
    bl_label: str = 'Clean Unweighted Bones'
    bl_options: Set = {'REGISTER', 'UNDO'}
    
    cleaning_mode: EnumProperty(
        name='Cleaning Mode',
        description='How to handle animated and constrained bones',
        items=[
            ('RESPECT_ANIMATION', 'Respect Animation Rigging', 
             'Preserve bones with keyframes, constraints, drivers, or that are constraint targets'),
            ('HIERARCHY_ONLY', 'Respect Hierarchy', 
             'Only preserve bones with weighted children, ignoring animation'),
            ('FULL_CLEAN', 'Full Clean', 
             'Remove all unweighted bones regardless of animation or hierarchy')
        ],
        default='RESPECT_ANIMATION'
    )
    
    remove_empty_vertex_groups: BoolProperty(
        name='Remove Empty Vertex Groups',
        description='Also remove vertex groups with no weights',
        default=True
    )
    
    weight_threshold: FloatProperty(
        name='Weight Threshold',
        description='Remove weights below this value',
        default=0.001,
        min=0.0001,
        max=0.1,
        precision=4
    )
    
    preserve_deform_bones: BoolProperty(
        name='Preserve Deform Bones',
        description='Keep bones marked as deform even if unweighted',
        default=False
    )
    
    remove_unused_bonecollections : BoolProperty(name='Remove Unused Bone Collections', default=True)

    respect_mirror : BoolProperty(name='Respect Mirror', default=True)
    
    @classmethod
    def poll(cls, context: Context) -> bool:
        return bool(is_armature(context.object) and context.mode in {'POSE', 'OBJECT'})
        
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400)
    
    def draw(self, context: Context) -> None:
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        col = layout.column(align=True)
        col.prop(self, 'cleaning_mode')
        
        col.separator()
        
        col.prop(self, 'preserve_deform_bones')
        col.prop(self, 'respect_mirror')
        col.prop(self, 'remove_unused_bonecollections')
        col.prop(self, 'remove_empty_vertex_groups')
        
        subcol = col.column(align=True)
        subcol.enabled = self.remove_empty_vertex_groups
        subcol.prop(self, 'weight_threshold', slider=True)
        
        if self.cleaning_mode == 'FULL_CLEAN':
            col.separator()
            box = layout.box()
            row = box.row()
            row.alert = True
            row.label(text='WARNING: May break rigs with IK/constraints!', icon='ERROR')
            
    def is_excluded_bone(self, bone_name) -> bool:
        if bone_name in filter_exclude_vertexgroup_names:
            return True
        
        twist_pattern = re.compile(r'.+ twist( \d+)?$', re.IGNORECASE)
        return bool(twist_pattern.match(bone_name))

    def execute(self, context: Context) -> Set:
        armatures: Set[Object | None] = {get_armature(ob) for ob in context.selected_objects}
        
        total_vgroups_removed = 0
        total_bones_removed = 0
        total_collection_removed = 0
        
        for armature in armatures:
            bones = armature.pose.bones
            meshes = get_armature_meshes(armature)
            bones_with_children = self.get_bones_with_parented_objects(armature)

            if not meshes and not bones_with_children:
                self.report({'WARNING'}, f"Armature '{armature.name}' has no meshes or parented objects.")
                continue

            if not bones:
                self.report({'WARNING'}, f"Armature '{armature.name}' has no bones.")
                continue

            if self.remove_empty_vertex_groups and meshes:
                removed_vgroups = remove_unused_vertexgroups(
                    armature, 
                    armature.data.bones,
                    weight_limit=self.weight_threshold,
                    respect_mirror=self.respect_mirror
                )
                total_vgroups_removed += sum(len(vgs) for vgs in removed_vgroups.values())

            remaining_vgroups = {
                mesh: set(vg.name for vg in mesh.vertex_groups)
                for mesh in meshes
            }

            constraint_targets = self.get_constraint_targets(armature)
            constraint_owners = self.get_constraint_owners(armature)

            while True:
                bones_to_remove = set()
                for b in bones:
                    if self.should_preserve_bone(
                        armature, b, meshes, remaining_vgroups, 
                        constraint_targets, constraint_owners, bones_with_children
                    ):
                        continue
                    
                    if not self.is_excluded_bone(b.name):
                        bones_to_remove.add(b.name)

                if bones_to_remove:
                    with preserve_context_mode(armature, 'EDIT'):
                        remove_bone(armature, bones_to_remove)
                        
                        total_bones_removed += len(bones_to_remove)
                        bones = armature.pose.bones
                        
                        remaining_vgroups = {
                            mesh: set(vg.name for vg in mesh.vertex_groups)
                            for mesh in meshes
                        }
                        
                        constraint_targets = self.get_constraint_targets(armature)
                        constraint_owners = self.get_constraint_owners(armature)
                        bones_with_children = self.get_bones_with_parented_objects(armature)
                else:
                    
                    if self.remove_unused_bonecollections:
                        success, total_collection_removed = remove_empty_bonecollections(armature)

                    break

        if total_bones_removed == 0 and total_vgroups_removed == 0 and total_collection_removed == 0:
            self.report({'INFO'}, 'No bones or vertex groups to remove.')
        else:
            self.report({'INFO'}, f'{total_bones_removed} bones removed, {total_collection_removed} bone collections removed, and {total_vgroups_removed} empty vertex groups cleaned.')
        return {'FINISHED'}

    def should_preserve_bone(self, armature : Object, bone : bpy.types.PoseBone, meshes : list[Object], remaining_vgroups, constraint_targets, constraint_owners, bones_with_children) -> bool:
        if self.preserve_deform_bones and bone.bone.use_deform:
            return True
        
        has_weight = any(bone.name in remaining_vgroups[mesh] for mesh in meshes)
        if has_weight:
            return True
        
        if bone.name in bones_with_children:
            return True
        
        if self.cleaning_mode == 'FULL_CLEAN':
            return False
        
        if self.cleaning_mode == 'HIERARCHY_ONLY':
            return self.has_weighted_descendants(bone, meshes, remaining_vgroups, bones_with_children)
        
        if self.cleaning_mode == 'RESPECT_ANIMATION':
            if self.bone_has_animation(armature, bone.name):
                return True
            
            if bone.name in constraint_targets or bone.name in constraint_owners:
                return True
            
            if self.has_animated_or_constrained_descendants(
                armature, bone, meshes, remaining_vgroups, constraint_targets, constraint_owners, bones_with_children
            ):
                return True
        
        return False

    def has_weighted_descendants(self, bone : bpy.types.PoseBone, meshes : list[Object], remaining_vgroups, bones_with_children) -> bool:
        for child in bone.children:
            if any(child.name in remaining_vgroups[mesh] for mesh in meshes):
                return True
            if child.name in bones_with_children:
                return True
            if self.has_weighted_descendants(child, meshes, remaining_vgroups, bones_with_children):
                return True
        return False

    def has_animated_or_constrained_descendants(self, armature : Object, bone : bpy.types.PoseBone, meshes : list[Object], remaining_vgroups, constraint_targets, constraint_owners, bones_with_children) -> bool:
        for child in bone.children:
            if any(child.name in remaining_vgroups[mesh] for mesh in meshes):
                return True
            
            if child.name in bones_with_children:
                return True
            
            if self.bone_has_animation(armature, child.name):
                return True
            
            if child.name in constraint_targets or child.name in constraint_owners:
                return True
            
            if self.has_animated_or_constrained_descendants(
                armature, child, meshes, remaining_vgroups, constraint_targets, constraint_owners, bones_with_children
            ):
                return True
        return False

    def bone_has_animation(self, armature : Object, bone_name : str) -> bool:
        bone = armature.pose.bones.get(bone_name)
        if not bone:
            return False

        for action in bpy.data.actions:
            for fcurve in action.fcurves:
                if fcurve.data_path.startswith(f'pose.bones["{bone_name}"]'):
                    if any(kw in fcurve.data_path for kw in ('location', 'rotation', 'scale')):
                        if len(fcurve.keyframe_points) > 1:
                            return True

        if armature.animation_data and armature.animation_data.drivers:
            bone_path = f'pose.bones["{bone_name}"]'
            for driver in armature.animation_data.drivers:
                if driver.data_path.startswith(bone_path):
                    if any(kw in driver.data_path for kw in ('location', 'rotation', 'scale')):
                        return True

        return False

    def get_constraint_targets(self, armature : Object) -> Set:
        targets = set()
        for bone in armature.pose.bones:
            for constraint in bone.constraints:
                target = getattr(constraint, 'target', None)
                if target == armature:
                    subtarget = getattr(constraint, 'subtarget', None)
                    if subtarget:
                        targets.add(subtarget)
                    
                    if constraint.type == 'IK':
                        pole_target = getattr(constraint, 'pole_target', None)
                        pole_subtarget = getattr(constraint, 'pole_subtarget', None)
                        if pole_target == armature and pole_subtarget:
                            targets.add(pole_subtarget)
        return targets

    def get_constraint_owners(self, armature : Object) -> Set:
        owners = set()
        for bone in armature.pose.bones:
            if bone.constraints:
                owners.add(bone.name)
        return owners

    def get_bones_with_parented_objects(self, armature : Object) -> Set:
        bones_with_children = set()
        for obj in bpy.data.objects:
            if obj.parent == armature and obj.parent_type == 'BONE' and obj.parent_bone:
                bones_with_children.add(obj.parent_bone)
        return bones_with_children
    
class TOOLS_OT_MergeArmatures(Operator, ShowConsole):
    bl_idname : str = "kitsunetools.merge_armatures"
    bl_label : str = "Merge Armatures"
    bl_options : Set = {'REGISTER', 'UNDO'}
    
    match_posture : BoolProperty(name='Match Visual Pose', default=True)
    
    clean_bones : BoolProperty(name='Clean Bones', default=True)
    
    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool(is_armature(context.object) and {ob for ob in context.selected_objects if is_armature(ob) and ob != context.object})
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.prop(self, 'match_posture')
        row.prop(self, 'clean_bones')
    
    def execute(self, context : Context) -> Set:
        active_object = context.object
        original_active = context.view_layer.objects.active
        
        if active_object is None: return {'CANCELLED'}
        
        armatures_to_merge = [ob for ob in context.selected_objects if ob != active_object and is_armature(ob)]
        
        if not armatures_to_merge:
            self.report({'WARNING'}, "No other armatures selected to merge.")
            return {'CANCELLED'}
        
        success_count = 0
        
        with preserve_context_mode(original_active, 'OBJECT'):
            try:
                for arm in armatures_to_merge:
                    
                    if self.clean_bones:
                        unselect_all()
                        context.view_layer.objects.active = arm
                        arm.select_set(True)
                        
                        bpy.ops.kitsunetools.clean_unweighted_bones('EXEC_DEFAULT', cleaning_mode='FULL_CLEAN', remove_empty_vertex_groups=True)
                    
                    success = merge_armatures(active_object, arm, match_posture=self.match_posture)
                    if success:
                        success_count += 1
                
            finally:
                self.report({'INFO'}, f'Merged {success_count} armatures to active armature')
                
        return {'FINISHED'}

class TOOLS_OT_CopyVisPosture(Operator):
    bl_idname : str = "kitsunetools.copy_vis_armature_posutre"
    bl_label : str = "Copy Visual Pose"
    bl_options : Set = {'REGISTER', 'UNDO'}

    copy_type: EnumProperty(items=[('ORIGIN', 'Location', ''), ('ANGLES', 'Rotation', '')])
        
    @classmethod
    def poll(cls,context : Context) -> bool:
        if context.mode != 'OBJECT': return False
        currob : Object | None = context.object
        if not is_armature(currob): return False
        
        obs = {ob for ob in context.selected_objects  if not ob.hide_get() and ob != currob}
        return bool(obs)
    
    def draw(self, context : Context) -> None:
        layout = self.layout
    
    def execute(self, context : Context) -> Set:
        currArm : Object | None = context.object
        if currArm is None: return {'CANCELLED'}
        
        obs = {ob for ob in context.selected_objects if not ob.hide_get() and ob != currArm}

        copiedcount = 0
        for otherArm in obs:
            
            if not all([currArm.data.bones, otherArm.data.bones]):
                continue
            
            success = copy_target_armature_visualpose(
                base_armature=currArm,
                target_armature=otherArm,
                copy_type=self.copy_type,
            )
            
            if success: copiedcount += 1
        
        return {'FINISHED'} if copiedcount > 0 else {'CANCELLED'}