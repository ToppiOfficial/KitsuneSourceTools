import bpy
from bpy.props import BoolProperty, EnumProperty
from bpy.types import UILayout, Context, Operator, Object
from typing import Set

from ..core.commonutils import (
    is_armature, is_mesh, draw_title_box, draw_wrapped_text_col,
    getArmature, getArmatureMeshes, PreserveContextMode
)

from ..core.meshutils import (
    clean_vertex_groups
)

from ..core.armatureutils import (
    applyCurrPoseAsRest, removeBone, unweightedBoneFilters,
    mergeArmatures, copyArmatureVisualPose
)

from ..utils import get_id
from .common import Tools_SubCategoryPanel

class TOOLS_PT_Armature(Tools_SubCategoryPanel):
    bl_label : str = "Armature Tools"
    
    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        bx : UILayout = draw_title_box(l, TOOLS_PT_Armature.bl_label, icon='ARMATURE_DATA')
        
        if is_armature(context.object) or is_mesh(context.object): pass
        else:
            draw_wrapped_text_col(bx,get_id("panel_select_armature"),max_chars=40 , icon='HELP')
            return
        
        col = bx.column()
        col.scale_y = 1.3
        row = col.row(align=True)
        row.operator(TOOLS_OT_ApplyCurrentPoseAsRestPose.bl_idname,icon='POSE_HLT')
        row.operator(TOOLS_OT_MergeArmatures.bl_idname,icon='AUTOMERGE_ON')
        
        col = bx.column()
        col.operator(TOOLS_OT_CleanUnWeightedBones.bl_idname,icon='GROUP_BONE')
        
        col = bx.column(align=True)
        col.operator(TOOLS_OT_CopyVisPosture.bl_idname,icon='POSE_HLT',text=f'{TOOLS_OT_CopyVisPosture.bl_label} (LOCATION)').copy_type = 'ORIGIN'
        col.operator(TOOLS_OT_CopyVisPosture.bl_idname,icon='POSE_HLT',text=f'{TOOLS_OT_CopyVisPosture.bl_label} (ROTATION)').copy_type = 'ANGLES'
           
class TOOLS_OT_ApplyCurrentPoseAsRestPose(Operator):
    bl_idname : str = "tools._apply_pose_as_restpose"
    bl_label : str = "Apply Pose As Restpose"
    bl_options : Set = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool(is_armature(context.object) and context.mode in {'POSE', 'OBJECT'})
    
    def execute(self, context : Context) -> Set:
        with PreserveContextMode(None, 'OBJECT'):
            armatures : Set[Object | None] = {getArmature(o) for o in context.selected_objects}
            
            success_count = 0
            for armature in armatures:
                success = applyCurrPoseAsRest(armature)
                if success: success_count += 1
                
        if success_count > 0:
            if len(armatures) == 1:
                self.report({'INFO'}, 'Applied as Rest Pose')
            else:
                self.report({'INFO'}, f'Applied {len(armatures)} Armatures as Rest Pose')
            
            bpy.ops.object.mode_set(mode='OBJECT')
                    
        return {'FINISHED'} if success else {'CANCELLED'}
    
class TOOLS_OT_CleanUnWeightedBones(Operator):
    bl_idname : str = 'tools.clean_unweighted_bones'
    bl_label : str = 'Clean Unweighted Bones'
    bl_options : Set = {'REGISTER', 'UNDO'}
    
    respect_animation : BoolProperty(
    name='Respect Animation Bones',
    description='Preserve bones that have animation keyframes or are part of a hierarchy that does',
    default=True
)

    aggressive_cleaning : BoolProperty(
    name='Aggressive Removal',
    description='Remove all bones without weight painting, even if they have animated or weighted child bones. '
                'WARNING: This will not respect hierarchy-dependent armature structures and may break rig constraints.',
    default=False
    )

    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool(is_armature(context.object) and context.mode in {'POSE', 'OBJECT'})
        
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        l.prop(self, 'aggressive_cleaning')
        
        if not self.aggressive_cleaning:
            l.prop(self, 'respect_animation')
        else:
            bx = l.box()
            bx.label(text='Cleaning will break constraints and IK!', icon='ERROR')

    def execute(self, context : Context) -> Set:
        
        armatures : Set[Object | None] = {getArmature(ob) for ob in context.selected_objects}
        
        total_vgroups_removed = 0
        total_bones_removed = 0
        
        for armature in armatures:
            bones = armature.pose.bones
            meshes = getArmatureMeshes(armature)
            
            if self.aggressive_cleaning:
                self.respect_animation = False

            if not meshes or not bones:
                self.report({'WARNING'}, "No meshes or bones associated with the armature.")
                return {'CANCELLED'}

            removed_vgroups = clean_vertex_groups(armature, armature.data.bones)

            remaining_vgroups = {
                mesh: set(vg.name for vg in mesh.vertex_groups)
                for mesh in meshes
            }

            while True:
                bones_to_remove = set()
                for b in bones:
                    if b.children and not self.aggressive_cleaning:
                        continue

                    has_weight = any(b.name in remaining_vgroups[mesh] for mesh in meshes)
                    if has_weight:
                        continue

                    if self.respect_animation and not self.aggressive_cleaning:
                        if self.hierarchy_has_animation(armature, b):
                            continue
                    
                    if b.name not in unweightedBoneFilters:
                        bones_to_remove.add(b.name)

                if bones_to_remove:
                    with PreserveContextMode(armature, 'EDIT'):
                        removeBone(armature, bones_to_remove)
                        
                        total_bones_removed += len(bones_to_remove)
                        bones = armature.pose.bones
                        
                        remaining_vgroups = {
                            mesh: set(vg.name for vg in mesh.vertex_groups)
                            for mesh in meshes
                        }
                else:
                    break

            total_vgroups_removed += sum(len(vgs) for vgs in removed_vgroups.values())

        self.report({'INFO'}, f'{total_bones_removed} bones removed with {total_vgroups_removed} empty vertex groups removed.')
        return {'FINISHED'}

    def bone_has_animation(self, armature, bone_name):
        bone = armature.pose.bones.get(bone_name)
        if not bone:
            return False

        # Check keyframes
        for action in bpy.data.actions:
            for fcurve in action.fcurves:
                if fcurve.data_path.startswith(f'pose.bones["{bone_name}"]'):
                    if any(kw in fcurve.data_path for kw in ('location', 'rotation', 'scale')):
                        keyframes = set(kf.co[1] for kf in fcurve.keyframe_points)
                        if len(keyframes) > 1:
                            return True

        # Check constraints
        for constr in bone.constraints:
            if getattr(constr, "target", None) or getattr(constr, "driver_add", None):
                return True

        return False

    def hierarchy_has_animation(self, armature, bone):
        if self.bone_has_animation(armature, bone.name):
            return True
        for child in bone.children:
            if self.hierarchy_has_animation(armature, child):
                return True
        return False
    
class TOOLS_OT_MergeArmatures(Operator):
    bl_idname : str = "tools.merge_armatures"
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
            success = mergeArmatures(currOb, arm, match_posture=self.match_posture)
            if success: success_count += 1
            
        self.report({'INFO'}, f'Merged {success} armatures to active armature')
            
        return {'FINISHED'}

class TOOLS_OT_CopyVisPosture(Operator):
    bl_idname : str = "tools.copy_vis_armature_posutre"
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
            
            success = copyArmatureVisualPose(
                base_armature=currArm,
                target_armature=otherArm,
                copy_type=self.copy_type,
            )
            
            if success: copiedcount += 1
        
        return {'FINISHED'} if copiedcount > 0 else {'CANCELLED'}