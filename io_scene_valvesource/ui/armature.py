import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty
from bpy.types import UILayout, Context, Operator, Object
from typing import Set

from ..core.commonutils import (
    is_armature, is_mesh, draw_title_box_layout, draw_wrapped_texts,
    get_armature, get_armature_meshes, preserve_context_mode, draw_listing_layout,
    get_selected_bones
)

from ..core.meshutils import (
    remove_unused_vertexgroups
)

from ..core.armatureutils import (
    apply_current_pose_as_restpose, remove_bone, filter_exclude_vertexgroup_names,
    merge_armatures, copy_target_armature_visualpose
)

from ..utils import get_id
from .common import Tools_SubCategoryPanel

class TOOLS_PT_Armature(Tools_SubCategoryPanel):
    bl_label : str = "Armature"
    
    def draw(self, context : Context) -> None:
        l : UILayout = self.layout
        bx : UILayout = draw_title_box_layout(l, TOOLS_PT_Armature.bl_label, icon='ARMATURE_DATA')
        
        if is_armature(context.object) or is_mesh(context.object): pass
        else:
            draw_wrapped_texts(bx,get_id("panel_select_armature"),max_chars=40 , icon='HELP')
            return
        
        col = bx.column(align=True)
        col.label(text='Apply Pose As Rest Pose')
        
        col.scale_y = 1.3
        row = col.row(align=True)
        row.operator(TOOLS_OT_ApplyCurrentPoseAsRestPose.bl_idname,icon='POSE_HLT',text='Entire Armature').selected_only = False
        row.operator(TOOLS_OT_ApplyCurrentPoseAsRestPose.bl_idname,icon='POSE_HLT', text='Selected Bones').selected_only = True
        
        col = bx.column()
        col.operator(TOOLS_OT_MergeArmatures.bl_idname,icon='AUTOMERGE_ON')
        col.operator(TOOLS_OT_CleanUnWeightedBones.bl_idname,icon='GROUP_BONE')
        
        col = bx.column(align=True)
        col.operator(TOOLS_OT_CopyVisPosture.bl_idname,icon='POSE_HLT',text=f'{TOOLS_OT_CopyVisPosture.bl_label} (LOCATION)').copy_type = 'ORIGIN'
        col.operator(TOOLS_OT_CopyVisPosture.bl_idname,icon='POSE_HLT',text=f'{TOOLS_OT_CopyVisPosture.bl_label} (ROTATION)').copy_type = 'ANGLES'
           
class TOOLS_OT_ApplyCurrentPoseAsRestPose(Operator):
    bl_idname : str = "kitsunetools.apply_pose_as_restpose"
    bl_label : str = "Apply Pose As Restpose"
    bl_options : Set = {'REGISTER', 'UNDO'}
    
    selected_only : BoolProperty(name='Selected Only', default=False)
    
    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool(is_armature(context.object) and context.mode in {'POSE', 'OBJECT'})
    
    def execute(self, context : Context) -> Set:
        with preserve_context_mode(None, 'OBJECT'):
            armatures : Set[Object | None] = {get_armature(o) for o in context.selected_objects}
            
            success_count = 0
            for armature in armatures:
                
                if self.selected_only:
                    selected_bones = get_selected_bones(armature=armature, bone_type='POSEBONE')
                    for posebone in armature.pose.bones:
                        if posebone.name in {pb.name for pb in selected_bones}: continue
                        posebone.matrix_basis.identity()
                
                success = apply_current_pose_as_restpose(armature=armature)
                if success: success_count += 1
                
        if success_count > 0:
            if len(armatures) == 1:
                self.report({'INFO'}, 'Applied as Rest Pose')
            else:
                self.report({'INFO'}, f'Applied {len(armatures)} Armatures as Rest Pose')
            
            bpy.ops.object.mode_set(mode='OBJECT')
                    
        return {'FINISHED'} if success else {'CANCELLED'}
    
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

    @classmethod
    def poll(cls, context: Context) -> bool:
        return bool(is_armature(context.object) and context.mode in {'POSE', 'OBJECT'})
        
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400)
    
    def draw(self, context: Context) -> None:
        l: UILayout = self.layout
        col = l.column(align=True)
        col.prop(self, 'cleaning_mode', expand=False)
        
        col.separator()
        col.prop(self, 'preserve_deform_bones')
        rootcol, itemcol = draw_listing_layout(col,indent_factor=0.05)
        rootcol.prop(self, 'remove_empty_vertex_groups')
        itemcol.prop(self, 'weight_threshold', slider=True)
        
        if self.cleaning_mode == 'FULL_CLEAN':
            bx = l.box()
            bx.label(text='WARNING: May break rigs with IK/constraints!', icon='ERROR')

    def execute(self, context: Context) -> Set:
        armatures: Set[Object | None] = {get_armature(ob) for ob in context.selected_objects}
        
        total_vgroups_removed = 0
        total_bones_removed = 0
        
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
                    weight_limit=self.weight_threshold
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
                    
                    if b.name not in filter_exclude_vertexgroup_names:
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
                    break

        if total_bones_removed == 0 and total_vgroups_removed == 0:
            self.report({'INFO'}, 'No bones or vertex groups to remove.')
        else:
            self.report({'INFO'}, f'{total_bones_removed} bones removed, {total_vgroups_removed} empty vertex groups cleaned.')
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
    
class TOOLS_OT_MergeArmatures(Operator):
    bl_idname : str = "kitsunetools.merge_armatures"
    bl_label : str = "Merge Armatures"
    bl_options : Set = {'REGISTER', 'UNDO'}
    
    match_posture : BoolProperty(name='Match Visual Pose', default=True)
    
    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool(is_armature(context.object) and {ob for ob in context.selected_objects if is_armature(ob) and ob != context.object})
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def execute(self, context : Context) -> Set:
        currOb : Object | None = context.object
        
        if currOb is None: return {'CANCELLED'}
        
        armatures = [ob for ob in context.selected_objects if ob != currOb]
        
        if not armatures: return {'CANCELLED'}
        
        success_count = 0
        for arm in armatures:
            success = merge_armatures(currOb, arm, match_posture=self.match_posture)
            if success: success_count += 1
            
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