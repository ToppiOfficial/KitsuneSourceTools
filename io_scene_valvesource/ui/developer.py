import bpy, math
from .. import iconloader
from .common import KITSUNE_PT_CustomToolPanel
from bpy.types import Context, Panel, UILayout, Operator
from typing import Set

from ..core.commonutils import (
    draw_title_box, draw_wrapped_text_col, create_toggle_section, create_subitem_ui
)

class DEVELOPER_PT_PANEL(KITSUNE_PT_CustomToolPanel, Panel):
    bl_label : str = 'Developer'
    bl_order = 1000
    bl_options : Set = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context : Context) -> bool:
        return context.mode in ['OBJECT', 'POSE']

    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        bx = draw_title_box(l,text='Developer Only Options', icon='OPTIONS')
        
        maincol = bx.column()
        draw_wrapped_text_col(maincol,'This is intended for me (Kitsune), Do not use any of the tools here for regular projects', alert=True)
        
        boolsection = draw_title_box(maincol,text='Bool Parameters')
        boolsection.prop(context.scene.vs,"use_kv2", text='Write ASCII DMX File')
        
        rootcol, itemcol = create_subitem_ui(boolsection)
        rootcol.prop(context.scene.vs,"propagate_enabled")
        itemcol.prop(context.scene.vs,"propagate_include_active")
        
        operatorsection = draw_title_box(maincol,text='Operators')
        operatorsection.operator(DEVELOPER_OT_ImportLegacyData.bl_idname, icon='MOD_DATA_TRANSFER')
        
        bx.template_icon(icon_value=iconloader.get_icon("KITSUNE"), scale=8) # type: ignore
 
class DEVELOPER_OT_ImportLegacyData(Operator):
    bl_idname : str = "smd.importlegacydata"
    bl_label : str = "Import FubukiTek Data"
    bl_description : str = "Import all plugin properties of the name 'FubukiTek' of the current blend file to KitsuneSourceTool properties"
    bl_options : Set = {'REGISTER','UNDO'}

    @classmethod
    def poll(cls, context : Context) -> bool:
        return hasattr(context.scene, 'fubukitek')

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        bx = l.box()

        bx.label(text='This will overwrite every Object!', icon='ERROR')

    def execute(self, context : Context) -> Set:
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.view_layer.update()
        bpy.context.view_layer.depsgraph.update()

        obs = bpy.data.objects

        for ob in obs:
            if hasattr(ob, "vs"): _ = ob.vs
            if hasattr(ob, "fubukitek"): _ = ob.fubukitek

            if ob.type == 'MESH':
                if hasattr(ob.data, "vs"): _ = ob.data.vs
                if hasattr(ob.data, "fubukitek"): _ = ob.data.fubukitek
                for mat in ob.data.materials:
                    if mat:
                        if hasattr(mat, "vs"): _ = mat.vs
                        if hasattr(mat, "fubukitek"): _ = mat.fubukitek

            elif ob.type == 'ARMATURE':
                if hasattr(ob.data, "vs"): _ = ob.data.vs
                if hasattr(ob.data, "fubukitek"): _ = ob.data.fubukitek
                for col in getattr(ob.data, "collections", []):
                    if hasattr(col, "vs"): _ = col.vs
                    if hasattr(col, "fubukitek"): _ = col.fubukitek
                for bone in ob.data.bones:
                    if hasattr(bone, "vs"): _ = bone.vs
                    if hasattr(bone, "fubukitek"): _ = bone.fubukitek

        for ob in obs:
            fb_ob = ob.fubukitek
            vs_ob = ob.vs
            if not (fb_ob and vs_ob):
                self.report({'WARNING'}, f"Skipped object {ob.name} (missing vs/fubukitek)")
                continue

            setattr(vs_ob, "export_rotation_offset_x", math.radians(fb_ob.rotation_offset_x))
            setattr(vs_ob, "export_rotation_offset_y", math.radians(fb_ob.rotation_offset_y))
            setattr(vs_ob, "export_rotation_offset_z", math.radians(fb_ob.rotation_offset_z))

            setattr(vs_ob, "export_location_offset_x", fb_ob.translation_offset_x)
            setattr(vs_ob, "export_location_offset_y", fb_ob.translation_offset_y)
            setattr(vs_ob, "export_location_offset_z", fb_ob.translation_offset_z)

            if ob.type == 'MESH':
                fb_mesh = ob.data.fubukitek
                vs_mesh = ob.data.vs
                if not (fb_mesh and vs_mesh):
                    pass

                for mat in ob.data.materials:
                    if not mat:
                        continue
                    vs_mat = mat.vs
                    fb_mat = mat.fubukitek
                    if vs_mat and fb_mat:
                        setattr(vs_mat, "override_dmx_export_path", fb_mat.material_path)

            elif ob.type == 'ARMATURE':
                bpy.ops.object.mode_set(mode='POSE')
                bpy.ops.pose.select_all(action='DESELECT')
                bpy.ops.object.mode_set(mode='OBJECT')

                ob.data.use_mirror_x = False

                fb_arm = ob.data.fubukitek
                vs_arm = ob.data.vs
                if fb_arm and vs_arm:

                    setattr(vs_arm, "bone_direction_naming_left", fb_arm.export_name_left)
                    setattr(vs_arm, "bone_direction_naming_right", fb_arm.export_name_right)
                    setattr(vs_arm, "bone_name_startcount", fb_arm.export_name_startcount)
                    setattr(vs_arm, "ignore_bone_exportnames", fb_arm.export_ignoreExportName)

                for bone in ob.data.bones:
                    fb_bone = bone.fubukitek
                    vs_bone = bone.vs
                    if not (fb_bone and vs_bone):
                        pass

                    setattr(vs_bone, "export_name", fb_bone.export_name)
                    setattr(vs_bone, "merge_to_parent", fb_bone.merge_to_parent)
                    setattr(vs_bone, "ignore_rotation_offset", fb_bone.ignore_export_offset)

                    rot_x_val = fb_bone.rotation_offset_x if fb_bone.rotation_offset_x != 0 else fb_bone.rotation_offset_y
                    setattr(vs_bone, "export_rotation_offset_x", math.radians(rot_x_val))

                    setattr(vs_bone, "export_rotation_offset_y", 0)
                    setattr(vs_bone, "export_rotation_offset_z", math.radians(fb_bone.rotation_offset_z))
                    setattr(vs_bone, "export_location_offset_x", fb_bone.translation_offset_x)
                    setattr(vs_bone, "export_location_offset_y", fb_bone.translation_offset_y)
                    setattr(vs_bone, "export_location_offset_z", fb_bone.translation_offset_z)
                    setattr(vs_bone, "bone_is_jigglebone", bool(fb_bone.jigglebone.types))
                    setattr(vs_bone, "jiggle_flex_type", 'RIGID' if 'is_rigid' in fb_bone.jigglebone.types else 'FLEXIBLE')
                    setattr(vs_bone, "use_bone_length_for_jigglebone_length", fb_bone.jigglebone.use_blend_bonelength)
                    setattr(vs_bone, "jiggle_length", fb_bone.jigglebone.length.val)
                    setattr(vs_bone, "jiggle_tip_mass", int(fb_bone.jigglebone.tip_mass.val))
                    setattr(vs_bone, "jiggle_has_angle_constraint", fb_bone.jigglebone.angle_constraint.enabled)
                    setattr(vs_bone, "jiggle_angle_constraint", math.radians(fb_bone.jigglebone.angle_constraint.val))
                    setattr(vs_bone, "jiggle_yaw_stiffness", fb_bone.jigglebone.yaw_stiffness.val)
                    setattr(vs_bone, "jiggle_yaw_damping", fb_bone.jigglebone.yaw_damping.val)
                    setattr(vs_bone, "jiggle_has_yaw_constraint", fb_bone.jigglebone.yaw_constraint.enabled)
                    setattr(vs_bone, "jiggle_yaw_constraint_min", math.radians(abs(fb_bone.jigglebone.yaw_constraint.min)))
                    setattr(vs_bone, "jiggle_yaw_constraint_max", math.radians(abs(fb_bone.jigglebone.yaw_constraint.max)))
                    setattr(vs_bone, "jiggle_yaw_friction", fb_bone.jigglebone.yaw_friction.val)
                    setattr(vs_bone, "jiggle_pitch_stiffness", fb_bone.jigglebone.pitch_stiffness.val)
                    setattr(vs_bone, "jiggle_pitch_damping", fb_bone.jigglebone.pitch_damping.val)
                    setattr(vs_bone, "jiggle_has_pitch_constraint", fb_bone.jigglebone.pitch_constraint.enabled)
                    setattr(vs_bone, "jiggle_pitch_constraint_min", math.radians(abs(fb_bone.jigglebone.pitch_constraint.min)))
                    setattr(vs_bone, "jiggle_pitch_constraint_max", math.radians(abs(fb_bone.jigglebone.pitch_constraint.max)))
                    setattr(vs_bone, "jiggle_pitch_friction", fb_bone.jigglebone.pitch_friction.val)
                    setattr(vs_bone, "jiggle_allow_length_flex", fb_bone.jigglebone.allow_length_flex)
                    setattr(vs_bone, "jiggle_along_stiffness", fb_bone.jigglebone.along_stiffness.val)
                    setattr(vs_bone, "jiggle_along_damping", fb_bone.jigglebone.along_damping.val)

                    if 'has_base_spring' in fb_bone.jigglebone.types:
                        vs_bone.jiggle_base_type = 'BASESPRING'

                    setattr(vs_bone, "jiggle_base_stiffness", fb_bone.jigglebone.stiffness.val)
                    setattr(vs_bone, "jiggle_base_damping", fb_bone.jigglebone.damping.val)
                    setattr(vs_bone, "jiggle_base_mass", int(fb_bone.jigglebone.base_mass.val))
                    setattr(vs_bone, "jiggle_has_left_constraint", fb_bone.jigglebone.left_constraint.enabled)
                    setattr(vs_bone, "jiggle_left_constraint_min", abs(fb_bone.jigglebone.left_constraint.min))
                    setattr(vs_bone, "jiggle_left_constraint_max", abs(fb_bone.jigglebone.left_constraint.max))
                    setattr(vs_bone, "jiggle_left_friction", fb_bone.jigglebone.left_friction.val)
                    setattr(vs_bone, "jiggle_has_up_constraint", fb_bone.jigglebone.up_constraint.enabled)
                    setattr(vs_bone, "jiggle_up_constraint_min", abs(fb_bone.jigglebone.up_constraint.min))
                    setattr(vs_bone, "jiggle_up_constraint_max", abs(fb_bone.jigglebone.up_constraint.max))
                    setattr(vs_bone, "jiggle_up_friction", fb_bone.jigglebone.up_friction.val)
                    setattr(vs_bone, "jiggle_has_forward_constraint", fb_bone.jigglebone.forward_constraint.enabled)
                    setattr(vs_bone, "jiggle_forward_constraint_min", abs(fb_bone.jigglebone.forward_constraint.min))
                    setattr(vs_bone, "jiggle_forward_constraint_max", abs(fb_bone.jigglebone.forward_constraint.max))
                    setattr(vs_bone, "jiggle_forward_friction", fb_bone.jigglebone.forward_friction.val)

        return {'FINISHED'}