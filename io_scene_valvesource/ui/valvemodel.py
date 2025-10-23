import os, math, bpy, mathutils
import numpy as np
from bpy.props import StringProperty, BoolProperty
from typing import Set, Any
from bpy import props
from bpy.types import Context, Object, Operator, Panel, UILayout, Event, Bone, Scene
from ..keyvalue3 import KVBool, KVNode, KVVector3
from ..ui.common import KITSUNE_PT_CustomToolPanel

from .. import iconloader

from ..core.commonutils import (
    draw_title_box, draw_wrapped_text_col, is_armature, sanitizeString,
    update_vmdl_container, is_empty, getSelectedBones, PreserveContextMode,
    getArmature, getHitboxes, create_toggle_section, getJiggleBones, getDMXAttachments, getBoneClothNodes,
    get_object_path
)

from ..utils import (
    getFilePath, get_smd_prefab_enum, get_id, State, Compiler
)

from ..core.boneutils import(
    getBoneExportName,
)

from ..core.armatureutils import(
    copyArmatureVisualPose, sortBonesByHierachy, getBoneMatrix, getArmatureMeshes
)

class VALVEMODEL_PrefabExportOperator():
    
    to_clipboard: props.BoolProperty(
        name='Copy To Clipboard',
        default=False
    )

    prefab_index: props.EnumProperty(
        name="Prefab File",
        items=get_smd_prefab_enum
    )

    def draw(self, context : Context) -> None:
        if not self.to_clipboard:
            self.layout.prop(self, "prefab_index")

    def invoke(self, context, event):
        if self.to_clipboard:
            return self.execute(context)

        prefabs = context.scene.vs.smd_prefabs
        if not prefabs or len(prefabs) == 0:
            self.report({'WARNING'}, "No prefabs available. Please add one before exporting.")
            return {'CANCELLED'}

        return context.window_manager.invoke_props_dialog(self)

    def get_export_path(self, context : Context) -> str | None:
        if self.to_clipboard:
            return None

        prefabs = context.scene.vs.smd_prefabs
        if not prefabs:
            self.report({'ERROR'}, "No prefabs defined")
            return None

        try:
            idx = int(self.prefab_index)
        except ValueError:
            idx = next((i for i, p in enumerate(prefabs) if p.name == self.prefab_index), -1)

        if idx < 0 or idx >= len(prefabs):
            self.report({'ERROR'}, "Invalid prefab selection")
            return None

        export_path, filename, ext = getFilePath(prefabs[idx].filepath)
        if not filename or not ext:
            self.report({'ERROR'}, "Invalid export path: must include filename and extension (e.g. constraints.vmdl)")
            return None

        if ext.lower() not in {'.vmdl', '.vmdl_prefab', '.qci', '.qc'}:
            self.report({'ERROR'}, f"Unsupported file extension '{ext.lower()}'")
            return None

        return export_path

    def write_output(self, compiled: str | None, export_path: str | None = None):
        """
        Handles writing the compiled content to a file or clipboard.
        Returns True if successful, False otherwise.
        """
        if not compiled:
            return False

        if self.to_clipboard:
            bpy.context.window_manager.clipboard = compiled
            self.report({'INFO'}, "Data copied to clipboard")
            return True

        if not export_path:
            self.report({'ERROR'}, "No export path provided")
            return False

        os.makedirs(os.path.dirname(export_path), exist_ok=True)
        with open(export_path, "w", encoding="utf-8") as f:
            f.write(compiled)

        self.report({'INFO'}, f"Data exported to {export_path}")
        return True

class VALVEMODEL_PT_PANEL(KITSUNE_PT_CustomToolPanel, Panel):
    bl_label : str = 'Valve Models'
    bl_options : Set = {'DEFAULT_CLOSED'}

    def draw_header(self, context : Context) -> None:
        self.layout.label(icon='OBJECT_DATA')

    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        armature = getArmature(context.object)
        if armature is not None:
            path = get_object_path(armature, context.view_layer)
            draw_wrapped_text_col(l, text=f'Active Armature: {armature.name}\n\n{path}', icon='ARMATURE_DATA')
        else:
            draw_wrapped_text_col(l, text='Active Armature: None', icon='ARMATURE_DATA')

class VALVEMODEL_ModelConfig(KITSUNE_PT_CustomToolPanel, Panel):
    bl_label : str = "ValveModel Config"
    bl_parent_id : str = "VALVEMODEL_PT_PANEL"
    bl_options : Set = {'DEFAULT_CLOSED'}

class VALVEMODEL_PT_Attachments(VALVEMODEL_ModelConfig):
    bl_label : str = 'Attachment'

    def draw_header(self, context : Context) -> None:
        self.layout.label(icon='EMPTY_AXIS')

    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        ob : bpy.types.Object | None = getArmature(context.object)
        
        if is_armature(ob) or is_empty(ob): pass
        else:
            draw_wrapped_text_col(l,get_id("panel_select_armature"),max_chars=40 , icon='HELP')
            return
        
        bx : UILayout = draw_title_box(l, 'Attachment')
        
        attachments = getDMXAttachments(ob)
        attachmentsection = create_toggle_section(bx, context.scene.vs, 'show_attachments', f'Show Attachments: {len(attachments)}', '', alert=not bool(attachments), align=True)
        if context.scene.vs.show_attachments:
            for attachment in attachments:
                row = attachmentsection.row(align=True)
                row.label(text=attachment.name,icon='EMPTY_DATA')
                row.label(text=attachment.parent_bone,icon='BONE_DATA')
                
        bx.operator(VALVEMODEL_OT_FixAttachment.bl_idname,icon='OPTIONS')

class VALVEMODEL_OT_FixAttachment(Operator):
    bl_idname : str = "smd.fix_attachments"
    bl_label : str = "Fix Source Attachment Empties Matrix"
    bl_description = "Fixes the Location and Rotation offset due to Blender's weird occurence that the empty is still relative to the world rather than the bone's tip."
    bl_options : Set = {'INTERNAL', 'UNDO'}
    
    def execute(self, context : Context) -> set:
        fixed_count = 0
        
        for obj in bpy.data.objects:
            if obj.type != 'EMPTY':
                continue
            
            if not obj.vs.dmx_attachment:
                continue
            
            if not obj.parent or obj.parent.type != 'ARMATURE' or obj.parent_type != 'BONE':
                continue
            
            armature = obj.parent
            bone_name = obj.parent_bone
            
            if bone_name not in armature.data.bones:
                continue
            
            world_matrix = obj.matrix_world.copy()
            world_location = obj.matrix_world.to_translation()
            world_rotation = obj.matrix_world.to_euler()
            world_scale = obj.matrix_world.to_scale()
            
            pose_bone = armature.pose.bones[bone_name]
            bone_tip_matrix = armature.matrix_world @ pose_bone.matrix @ mathutils.Matrix.Translation((0, pose_bone.length, 0))
            
            obj.parent = None
            
            obj.parent = armature
            obj.parent_type = 'BONE'
            obj.parent_bone = bone_name
            
            local_location = bone_tip_matrix.inverted() @ world_location
            local_rotation = (bone_tip_matrix.inverted() @ world_matrix).to_euler()
            
            obj.location = local_location
            obj.rotation_euler = local_rotation
            obj.scale = world_scale
            
            fixed_count += 1
        
        if fixed_count > 0:
            self.report({'INFO'}, f'Fixed {fixed_count} attachment(s)')
        else:
            self.report({'INFO'}, 'No attachments needed fixing')
        
        return {'FINISHED'}

class VALVEMODEL_PT_Jigglebone(VALVEMODEL_ModelConfig):
    bl_label : str = 'JiggleBone'

    def draw_header(self, context : Context) -> None:
        self.layout.label(icon='CONSTRAINT_BONE')

    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        ob : bpy.types.Object | None = getArmature(context.object)

        if is_armature(ob): pass
        else:
            draw_wrapped_text_col(l,get_id("panel_select_armature"),max_chars=40 , icon='HELP')
            return

        bone : bpy.types.Bone | None = ob.data.bones.active

        if bone:
            titlemessage : str = f'JiggleBone ({bone.name})'
        else:
            titlemessage : str = 'JiggleBones'

        bx : UILayout = draw_title_box(l, titlemessage)

        jigglebones = getJiggleBones(ob)
        jigglebonesection = create_toggle_section(bx, context.scene.vs, 'show_jigglebones', f'Show Jigglebones: {len(jigglebones)}', '', alert=not bool(jigglebones), align=True)
        if context.scene.vs.show_jigglebones:
            col = jigglebonesection.column()
            for jigglebone in jigglebones:
                row = col.row(align=True)
                row.label(text=jigglebone.name,icon='BONE_DATA')
                
                if len(jigglebone.collections) == 1:
                    row.label(text=jigglebone.collections[0].name,icon='GROUP_BONE')
                elif len(jigglebone.collections) > 1:
                    row.label(text="In Multiple Collection",icon='GROUP_BONE')
                else:
                    row.label(text="Not in Collection",icon='GROUP_BONE')

        row = bx.row(align=True)
        row.scale_y = 1.2
        row.operator(VALVEMODEL_OT_ExportJiggleBone.bl_idname,text='Write to Clipboard').to_clipboard = True
        row.operator(VALVEMODEL_OT_ExportJiggleBone.bl_idname,text='Write to File').to_clipboard = False
                
        if bone and bone.select:
            self.draw_jigglebone_properties(bx, bone)
        else:
            bx.box().label(text='Select a Valid Bone', icon='ERROR')

    def draw_jigglebone_properties(self, layout : UILayout, bone : bpy.types.Bone) -> None:
        vs_bone = bone.vs
        col : UILayout = layout.column()
        maincol : UILayout = col.column()
        maincol.prop(vs_bone, 'bone_is_jigglebone', toggle=True, icon='DOWNARROW_HLT' if vs_bone.bone_is_jigglebone else 'RIGHTARROW_THIN')

        if vs_bone.bone_is_jigglebone:
            col = maincol.column(align=True)
            col.prop(vs_bone, 'jiggle_flex_type')
            col.prop(vs_bone, "jiggle_base_type")

            col = maincol.column(align=True)

            if vs_bone.jiggle_flex_type in ['FLEXIBLE', 'RIGID']:
                col.prop(vs_bone, 'use_bone_length_for_jigglebone_length', toggle=True)
                if not vs_bone.use_bone_length_for_jigglebone_length: col.prop(vs_bone, 'jiggle_length')
                col.prop(vs_bone, 'jiggle_tip_mass')

            if vs_bone.jiggle_flex_type == 'FLEXIBLE':
                col.prop(vs_bone, 'jiggle_yaw_stiffness', slider=True)
                col.prop(vs_bone, 'jiggle_yaw_damping', slider=True)
                col.prop(vs_bone, 'jiggle_pitch_stiffness', slider=True)
                col.prop(vs_bone, 'jiggle_pitch_damping', slider=True)
                col.prop(vs_bone, 'jiggle_allow_length_flex', toggle=True)
                if vs_bone.jiggle_allow_length_flex:
                    col.prop(vs_bone, 'jiggle_along_stiffness', slider=True)
                    col.prop(vs_bone, 'jiggle_along_damping', slider=True)

            if vs_bone.jiggle_flex_type in ['FLEXIBLE', 'RIGID']:
                col = maincol.column(align=True)
                row = col.row(align=True)
                row.prop(vs_bone, 'jiggle_has_angle_constraint',toggle=True)
                row.prop(vs_bone, 'jiggle_has_yaw_constraint',toggle=True)
                row.prop(vs_bone, 'jiggle_has_pitch_constraint',toggle=True)

                if any([vs_bone.jiggle_has_angle_constraint, vs_bone.jiggle_has_yaw_constraint, vs_bone.jiggle_has_pitch_constraint]):
                    col = maincol.column(align=True)

                if vs_bone.jiggle_has_angle_constraint:
                    col.prop(vs_bone, 'jiggle_angle_constraint')

                if vs_bone.jiggle_has_yaw_constraint:
                    row = col.row(align=True)
                    row.prop(vs_bone, 'jiggle_yaw_constraint_min', slider=True)
                    row.prop(vs_bone, 'jiggle_yaw_constraint_max', slider=True)

                    col.prop(vs_bone, 'jiggle_yaw_friction', slider=True)

                if vs_bone.jiggle_has_pitch_constraint:
                    row = col.row(align=True)
                    row.prop(vs_bone, 'jiggle_pitch_constraint_min', slider=True)
                    row.prop(vs_bone, 'jiggle_pitch_constraint_max', slider=True)

                    col.prop(vs_bone, 'jiggle_pitch_friction', slider=True)

            if vs_bone.jiggle_base_type == 'BASESPRING':
                col = maincol.column(align=True)
                col.prop(vs_bone, "jiggle_base_stiffness", slider=True)
                col.prop(vs_bone, "jiggle_base_damping", slider=True)
                col.prop(vs_bone, "jiggle_base_mass", slider=True)

                col = maincol.column(align=True)

                row = col.row(align=True)
                row.prop(vs_bone, 'jiggle_has_left_constraint',toggle=True)
                row.prop(vs_bone, 'jiggle_has_up_constraint',toggle=True)
                row.prop(vs_bone, 'jiggle_has_forward_constraint',toggle=True)

                if any([vs_bone.jiggle_has_left_constraint, vs_bone.jiggle_has_up_constraint, vs_bone.jiggle_has_forward_constraint]):
                    col = maincol.column(align=True)

                if vs_bone.jiggle_has_left_constraint:
                    row = col.row(align=True)
                    row.prop(vs_bone, 'jiggle_left_constraint_min', slider=True)
                    row.prop(vs_bone, 'jiggle_left_constraint_max', slider=True)

                    col.prop(vs_bone, 'jiggle_left_friction', slider=True)

                if vs_bone.jiggle_has_up_constraint:
                    row = col.row(align=True)
                    row.prop(vs_bone, 'jiggle_up_constraint_min', slider=True)
                    row.prop(vs_bone, 'jiggle_up_constraint_max', slider=True)

                    col.prop(vs_bone, 'jiggle_up_friction', slider=True)

                if vs_bone.jiggle_has_forward_constraint:
                    row = col.row(align=True)
                    row.prop(vs_bone, 'jiggle_forward_constraint_min', slider=True)
                    row.prop(vs_bone, 'jiggle_forward_constraint_max', slider=True)

                    col.prop(vs_bone, 'jiggle_forward_friction', slider=True)
            elif vs_bone.jiggle_base_type == 'BOING':
                col = maincol.column(align=True)
                col.prop(vs_bone, "jiggle_impact_speed", slider=True)
                col.prop(vs_bone, "jiggle_impact_angle", slider=True)
                col.prop(vs_bone, "jiggle_damping_rate", slider=True)
                col.prop(vs_bone, "jiggle_frequency", slider=True)
                col.prop(vs_bone, "jiggle_amplitude", slider=True)
            else:
                pass

class VALVEMODEL_OT_ExportJiggleBone(Operator, VALVEMODEL_PrefabExportOperator):
    bl_idname : str = "smd.write_jigglebone"
    bl_label : str = "Write Jigglebones"

    def draw(self, context : Context) -> None:
        if not self.to_clipboard:
            l : UILayout | None = self.layout
            l.prop(self, "prefab_index")

    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool(cls._has_jigglebones(context))

    @staticmethod
    def _has_jigglebones(context):
        ob : Object | None = getArmature(context.object)
        return ob and is_armature(ob) and any(b.vs.bone_is_jigglebone for b in ob.data.bones)

    def execute(self, context : Context) -> Set:
        arm = getArmature(context.object)
        jigglebones = [b for b in arm.data.bones if b.vs.bone_is_jigglebone]

        if not jigglebones:
            self.report({'WARNING'}, "No jigglebones found")
            return {'CANCELLED'}

        export_path = self.get_export_path(context)

        if export_path is None and not self.to_clipboard:
            return {'CANCELLED'}
        fmt = None

        if not self.to_clipboard:
            export_path, filename, ext = getFilePath(export_path)
            if not filename or not ext:
                self.report({'ERROR'}, "Invalid export path: must include filename and extension")
                return {'CANCELLED'}

            ext_lower = ext.lower()
            if ext_lower in {'.qc', '.qci'}:
                fmt = 'QC'
            elif ext_lower in {'.vmdl', '.vmdl_prefab'}:
                fmt = 'VMDL'
            else:
                self.report({'ERROR'}, f"Unsupported file extension '{ext_lower}'")
                return {'CANCELLED'}

        compiled = self._export_jigglebones(fmt, jigglebones, export_path)

        if not self.write_output(compiled, export_path):
            return {'CANCELLED'}

        return {'FINISHED'}

    def _export_jigglebones(self, fmt, jigglebones, export_path):
        arm = bpy.context.object
        collection_groups = {}
        for bone in jigglebones:
            group_name = bone.collections[0].name if bone.collections else "Others"
            collection_groups.setdefault(group_name, []).append(bone)

        if self.to_clipboard:
            if State.compiler == Compiler.MODELDOC:
                return self._export_vmdl(collection_groups, export_path)
            else:
                return self._export_qc(collection_groups)
        else:
            if fmt == 'QC' or (not fmt):
                return self._export_qc(collection_groups)
            elif fmt == 'VMDL':
                return self._export_vmdl(collection_groups, export_path)
            else:
                return None

    def _export_qc(self, collection_groups):
        entries = []
        for group_name, group_bones in collection_groups.items():
            entries.append("//=====================================================")
            entries.append(f"// Jigglebones - Collection: {group_name}")
            entries.append("//=====================================================")
            entries.append("")
            for bone in group_bones:
                _datas = []
                _datas.append(f'$jigglebone "{getBoneExportName(bone)}"')
                _datas.append('{')
                jiggle_length = bone.length if bone.vs.use_bone_length_for_jigglebone_length else bone.vs.jiggle_length

                if bone.vs.jiggle_flex_type in ['FLEXIBLE', 'RIGID']:
                    _datas.append('\tis_flexible' if bone.vs.jiggle_flex_type == 'FLEXIBLE' else '\tis_rigid')
                    _datas.append('\t{')
                    _datas.append(f'\t\tlength {jiggle_length}')
                    _datas.append(f'\t\ttip_mass {bone.vs.jiggle_tip_mass}')
                    if bone.vs.jiggle_flex_type == 'FLEXIBLE':
                        _datas.append(f'\t\tyaw_stiffness {bone.vs.jiggle_yaw_stiffness}')
                        _datas.append(f'\t\tyaw_damping {bone.vs.jiggle_yaw_damping}')
                        if bone.vs.jiggle_has_yaw_constraint:
                            _datas.append(f'\t\tyaw_constraint {-abs(math.degrees(bone.vs.jiggle_yaw_constraint_min))} {abs(math.degrees(bone.vs.jiggle_yaw_constraint_max))}')
                            _datas.append(f'\t\tyaw_friction {bone.vs.jiggle_yaw_friction}')
                        _datas.append(f'\t\tpitch_stiffness {bone.vs.jiggle_pitch_stiffness}')
                        _datas.append(f'\t\tpitch_damping {bone.vs.jiggle_pitch_damping}')
                        if bone.vs.jiggle_has_pitch_constraint:
                            _datas.append(f'\t\tpitch_constraint {-abs(math.degrees(bone.vs.jiggle_pitch_constraint_min))} {abs(math.degrees(bone.vs.jiggle_pitch_constraint_max))}')
                            _datas.append(f'\t\tpitch_friction {bone.vs.jiggle_pitch_friction}')
                        if bone.vs.jiggle_allow_length_flex:
                            _datas.append(f'\t\tallow_length_flex')
                            _datas.append(f'\t\talong_stiffness {bone.vs.jiggle_along_stiffness}')
                        if bone.vs.jiggle_has_angle_constraint:
                            _datas.append(f'\t\tangle_constraint {math.degrees(bone.vs.jiggle_angle_constraint)}')
                    _datas.append('\t}')

                if bone.vs.jiggle_base_type == 'BASESPRING':
                    _datas.append('\thas_base_spring')
                    _datas.append('\t{')
                    _datas.append(f'\t\tstiffness {bone.vs.jiggle_base_stiffness}')
                    _datas.append(f'\t\tdamping {bone.vs.jiggle_base_damping}')
                    _datas.append(f'\t\tbase_mass {bone.vs.jiggle_base_mass}')
                    if bone.vs.jiggle_has_left_constraint:
                        _datas.append(f'\t\tleft_constraint {-abs(bone.vs.jiggle_left_constraint_min)} {abs(bone.vs.jiggle_left_constraint_max)}')
                        _datas.append(f'\t\tleft_friction {bone.vs.jiggle_left_friction}')
                    if bone.vs.jiggle_has_up_constraint:
                        _datas.append(f'\t\tup_constraint {-abs(bone.vs.jiggle_up_constraint_min)} {abs(bone.vs.jiggle_up_constraint_max)}')
                        _datas.append(f'\t\tup_friction {bone.vs.jiggle_up_friction}')
                    if bone.vs.jiggle_has_forward_constraint:
                        _datas.append(f'\t\tforward_constraint {-abs(bone.vs.jiggle_forward_constraint_min)} {abs(bone.vs.jiggle_forward_constraint_max)}')
                        _datas.append(f'\t\tforward_friction {bone.vs.jiggle_forward_friction}')
                    _datas.append('\t}')
                elif bone.vs.jiggle_base_type == 'BOING':
                    _datas.append('\tis_boing')
                    _datas.append('\t{')
                    _datas.append(f'\t\timpact_speed {bone.vs.jiggle_impact_speed}')
                    _datas.append(f'\t\timpact_angle {bone.vs.jiggle_impact_angle}')
                    _datas.append(f'\t\tdamping_rate {bone.vs.jiggle_damping_rate}')
                    _datas.append(f'\t\tfrequency {bone.vs.jiggle_frequency}')
                    _datas.append(f'\t\tamplitude {bone.vs.jiggle_amplitude}')
                    _datas.append('\t}')
                _datas.append('}')
                _datas.append('\n')
                entries.append("\n".join(_datas))
        return "\n".join(entries)

    def _export_vmdl(self, collection_groups, export_path):
        folder_nodes = []

        # Create a folder per collection
        for group_name, group_bones in collection_groups.items():
            folder = KVNode(_class="Folder", name=sanitizeString(group_name))
            for bone in group_bones:
                flex_type = 2 if bone.vs.jiggle_flex_type not in ['FLEXIBLE', 'RIGID'] else (1 if bone.vs.jiggle_flex_type == 'FLEXIBLE' else 0)
                jiggle_length = bone.length if bone.vs.use_bone_length_for_jigglebone_length else bone.vs.jiggle_length
                jigglebone = KVNode(
                    _class="JiggleBone",
                    name=f"JiggleBone_{getBoneExportName(bone)}",
                    jiggle_root_bone=getBoneExportName(bone),
                    jiggle_type=flex_type,
                    has_yaw_constraint=KVBool(bone.vs.jiggle_has_yaw_constraint),
                    has_pitch_constraint=KVBool(bone.vs.jiggle_has_pitch_constraint),
                    has_angle_constraint=KVBool(bone.vs.jiggle_has_angle_constraint),
                    has_base_spring=KVBool(bone.vs.jiggle_base_type == 'BASESPRING'),
                    allow_flex_length=KVBool(bone.vs.jiggle_allow_length_flex),
                    length=jiggle_length,
                    tip_mass=bone.vs.jiggle_tip_mass,
                    angle_limit=math.degrees(bone.vs.jiggle_angle_constraint),
                    min_yaw=math.degrees(bone.vs.jiggle_yaw_constraint_min),
                    max_yaw=math.degrees(bone.vs.jiggle_yaw_constraint_max),
                    yaw_friction=bone.vs.jiggle_yaw_friction,
                    min_pitch=math.degrees(bone.vs.jiggle_pitch_constraint_min),
                    max_pitch=math.degrees(bone.vs.jiggle_pitch_constraint_max),
                    pitch_friction=bone.vs.jiggle_pitch_friction,
                    base_mass=bone.vs.jiggle_base_mass,
                    base_stiffness=bone.vs.jiggle_base_stiffness,
                    base_damping=bone.vs.jiggle_base_damping,
                    base_left_min=bone.vs.jiggle_left_constraint_min,
                    base_left_max=bone.vs.jiggle_left_constraint_max,
                    base_left_friction=bone.vs.jiggle_left_friction,
                    base_up_min=bone.vs.jiggle_up_constraint_min,
                    base_up_max=bone.vs.jiggle_up_constraint_max,
                    base_up_friction=bone.vs.jiggle_up_friction,
                    base_forward_min=bone.vs.jiggle_forward_constraint_min,
                    base_forward_max=bone.vs.jiggle_forward_constraint_max,
                    base_forward_friction=bone.vs.jiggle_forward_friction,
                    yaw_stiffness=bone.vs.jiggle_yaw_stiffness,
                    yaw_damping=bone.vs.jiggle_yaw_damping,
                    pitch_stiffness=bone.vs.jiggle_pitch_stiffness,
                    pitch_damping=bone.vs.jiggle_pitch_damping,
                    along_stiffness=bone.vs.jiggle_along_stiffness,
                    along_damping=bone.vs.jiggle_along_damping,
                )
                folder.add_child(jigglebone)
            folder_nodes.append(folder)

        # Use helper to append/overwrite JiggleBoneList container
        kv_doc = update_vmdl_container(
            container_class="JiggleBoneList" if not self.to_clipboard else "ScratchArea",
            nodes=folder_nodes,
            export_path=export_path,
            to_clipboard=self.to_clipboard
        )

        if kv_doc is False:
            self.report({"WARNING"}, 'Existing file may not be a valid KeyValue3')
            return None

        return kv_doc.to_text()

class VALVEMODEL_PT_ClothNode(VALVEMODEL_ModelConfig):
    bl_label : str = 'ClothNode (Source 2)'

    def draw_header(self, context : Context) -> None:
        self.layout.label(icon='CONSTRAINT_BONE')
        
    def draw(self, context):
        l : UILayout | None = self.layout
        ob : bpy.types.Object | None = getArmature(context.object)
        
        if is_armature(ob): pass
        else:
            draw_wrapped_text_col(l,get_id("panel_select_armature"),max_chars=40 , icon='HELP')
            return
        
        bone = context.object.data.bones.active
        
        if bone:
            titlemessage : str = f'ClothNode ({bone.name})'
        else:
            titlemessage : str = 'ClothNode'
        
        titlebox = draw_title_box(l,titlemessage)
        
        clothnodebones = getBoneClothNodes(ob)
        clothnodesection = create_toggle_section(titlebox, context.scene.vs, 'show_clothnodes', f'Show ClothNodes: {len(clothnodebones)}', '', alert=not bool(clothnodebones), align=True)
        if context.scene.vs.show_clothnodes:
            for clothnode in clothnodebones:
                row = clothnodesection.row(align=True)
                row.label(text=clothnode.name,icon='BONE_DATA')
                if len(clothnode.collections) == 1:
                    row.label(text=clothnode.collections[0].name,icon='GROUP_BONE')
                elif len(clothnode.collections) > 1:
                    row.label(text="In Multiple Collection",icon='GROUP_BONE')
                else:
                    row.label(text="Not in Collection",icon='GROUP_BONE')
        
        if bone and bone.select:
            self.draw_clothnode_params(context, titlebox, bone)
        else:
            titlebox.box().label(text='Select a Valid Bone', icon='ERROR')
            return
        
    def draw_clothnode_params(self, context : Context, layout : UILayout, bone : bpy.types.Bone): 
        layout.prop(bone.vs, 'bone_is_clothnode', toggle=True, icon='DOWNARROW_HLT' if bone.vs.bone_is_clothnode else 'RIGHTARROW_THIN')
        
        if bone.vs.bone_is_clothnode:
            col = layout.column(align=False)
            
            row = col.row(align=True)
            row.prop(bone.vs, 'cloth_static', toggle=True)
            if bone.vs.cloth_static: row.prop(bone.vs, 'cloth_allow_rotation', toggle=True) 
            col.prop(bone.vs, 'cloth_transform_alignment')
            col.prop(bone.vs, 'cloth_make_spring')
            col.prop(bone.vs, 'cloth_lock_translation')
            
            paramcol = col.column()
            paramcol.enabled = not bone.vs.cloth_static
            col = paramcol.column(align=True)
            col.prop(bone.vs, 'cloth_goal_strength', slider=True)
            col.prop(bone.vs, 'cloth_goal_damping', slider=True)
            col.prop(bone.vs, 'cloth_mass', slider=True)
            col.prop(bone.vs, 'cloth_gravity', slider=True)
            
            col = paramcol.column(align=True)
            col.prop(bone.vs,'cloth_collision_radius', slider=True)
            col.prop(bone.vs,'cloth_friction', slider=True)
            col.prop(bone.vs,'cloth_collision_layer', expand=True)
            col.prop(bone.vs,'cloth_has_world_collision')
            
            col = paramcol.column(align=True)
            col.prop(bone.vs,'cloth_stray_radius', slider=True)
            
            col = paramcol.column(align=True)
            col.prop(bone.vs,'cloth_generate_tip', toggle=True)
            
            if bone.vs.cloth_generate_tip:
                col.prop(bone.vs,'cloth_tip_goal_strength', slider=True)
                col.prop(bone.vs,'cloth_tip_mass', slider=True)
                col.prop(bone.vs,'cloth_tip_gravity', slider=True)

class VALVEMODEL_OT_CreateProportionActions(Operator):
    bl_idname : str = 'smd.create_proportion_actions'
    bl_label : str = 'Create Delta Proportion Pose'
    bl_options : Set = {'REGISTER', 'UNDO'}

    ProportionName: props.StringProperty(name='Proportion Slot Name', default='proportion')
    ReferenceName: props.StringProperty(name='Reference Slot Name', default='reference')

    @classmethod
    def poll(cls, context : Context) -> bool:
        ob : Object | None = context.object
        return bool(
            context.mode == 'OBJECT'
            and is_armature(ob)
            and {o for o in context.selected_objects if o != context.object}
        )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context : Context) -> Set:
        currArm : bpy.types.Object | None = context.object
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

            actionslots = {s for s in action.slots}
            for slot in actionslots:
                action.slots.remove(slot)

            for pb in arm.pose.bones:
                pb.matrix_basis.identity()

            slot_ref = action.slots.get(self.ReferenceName)
            if slot_ref is None:
                slot_ref = action.slots.new(id_type='OBJECT', name=self.ReferenceName)

            slot_prop = action.slots.get(self.ProportionName)
            if slot_prop is None:
                slot_prop = action.slots.new(id_type='OBJECT', name=self.ProportionName)

            if len(action.layers) == 0:
                layer = action.layers.new("BaseLayer")
            else:
                layer = action.layers[0]

            if len(layer.strips) == 0:
                strip = layer.strips.new(type='KEYFRAME')
            else:
                strip = layer.strips[0]

            arm.animation_data.action = action
            arm.animation_data.action_slot = slot_ref

            success = copyArmatureVisualPose(currArm, arm, copy_type='ANGLES')
            if success:
                for pbone in arm.pose.bones:
                    pbone.keyframe_insert(data_path="location", group=pbone.name) # type: ignore
                    pbone.keyframe_insert(data_path="rotation_quaternion", group=pbone.name) # type: ignore
                    pbone.keyframe_insert(data_path="rotation_euler", group=pbone.name) # type: ignore

            context.view_layer.update()

            arm.animation_data.action_slot = slot_prop
            success1 = copyArmatureVisualPose(currArm, arm, copy_type='ANGLES')
            success2 = copyArmatureVisualPose(currArm, arm, copy_type='ORIGIN')

            if success1 and success2:
                for pbone in arm.pose.bones:
                    pbone.keyframe_insert(data_path="location", group=pbone.name) # type: ignore
                    pbone.keyframe_insert(data_path="rotation_quaternion", group=pbone.name) # type: ignore
                    pbone.keyframe_insert(data_path="rotation_euler", group=pbone.name) # type: ignore

            arm.animation_data.action_slot = slot_ref
            context.view_layer.update()
                
        currArm.data.pose_position = last_pose_state
        return {'FINISHED'}

class VALVEMODEL_OT_ExportConstraintProportion(Operator, VALVEMODEL_PrefabExportOperator):
    bl_idname : str = "smd.encode_exportname_as_constraint_proportion"
    bl_label : str = "Write Constraint Proportions (Source 2)"

    proportion_type : bpy.props.EnumProperty(name="Proportion Type", items=[
            ('ANGLESLOC', "Point and Angles Proportions", "Creates Rotation and Location constraints for bones with a custom export"),
            ('POINT', "Point Proportions", "Creates point constraints for bones with a custom export"),])

    def draw(self, context : Context) -> None:
        self.layout.prop(self, "proportion_type")
        if not self.to_clipboard:
            self.layout.prop(self, "prefab_index")

    def invoke(self, context : Context, event : Event) -> Any:
        if self.to_clipboard:
            return context.window_manager.invoke_props_dialog(self)

        prefabs = context.scene.vs.smd_prefabs
        if not prefabs or len(prefabs) == 0:
            self.report({'WARNING'}, "No prefabs available. Please add one before exporting.")
            return {'CANCELLED'}

        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context : Context) -> Set:
        armature = context.object
        bones = getSelectedBones(armature, 'BONE', select_all=True, sort_type='TO_LAST')
        if not bones:
            self.report({'WARNING'}, "No bones found in armature")
            return {'CANCELLED'}

        filepath = self.get_export_path(context)

        with PreserveContextMode(armature, 'OBJECT'):
            compiled = self._export_constraints(armature, bones, filepath)

        export_path, filename, ext = getFilePath(filepath)

        if not filename or not ext:
            self.report({'ERROR'}, "Invalid export path: must include filename and extension")
            return {'CANCELLED'}

        ext_lower = ext.lower()
        if ext_lower not in {'.vmdl', '.vmdl_prefab'}:
            self.report({'ERROR'}, f"Unsupported file extension '{ext_lower}'")
            return {'CANCELLED'}

        if not self.write_output(compiled, filepath):
            return {'CANCELLED'}

        return {'FINISHED'}

    def _export_constraints(self, armature, bones, export_path):
        folder_node = KVNode(_class='Folder', name="constraints_CustomProportions")

        for bone in bones:
            bone_name = bone.getBoneExportName(bone, for_write=True)
            posebone = armature.pose.bones.get(bone.name)
            original_bone_name = sanitizeString(bone.name)
            has_parent = bool(bone.parent)

            if bone_name == original_bone_name:
                continue

            if self.proportion_type == 'ANGLESLOC':

                con_orient = KVNode(
                    _class="AnimConstraintOrient",
                    name=f'Angles_{original_bone_name}_{bone_name}'
                )
                con_orient.add_child(KVNode(_class="AnimConstraintBoneInput", parent_bone=bone_name, weight=1.0))
                con_orient.add_child(KVNode(_class="AnimConstraintSlave", parent_bone=original_bone_name, weight=1.0))

                con_point = KVNode(
                    _class="AnimConstraintPoint",
                    name=f'Point_{original_bone_name}_{bone_name}'
                )
                con_point.add_child(KVNode(_class="AnimConstraintBoneInput",
                                        parent_bone=original_bone_name if has_parent else bone_name,
                                        weight=1.0))
                con_point.add_child(KVNode(_class="AnimConstraintSlave",
                                        parent_bone=bone_name if has_parent else original_bone_name,
                                        weight=1.0))

                folder_node.add_child(con_orient)

            else:
                parent_name = bone.getBoneExportName(bone.parent, for_write=True) if has_parent else None

                con_point = KVNode(
                    _class="AnimConstraintPoint",
                    name=f'Point_{bone_name}'
                )

                relativepos = bone.getRelativeTargetMatrix(posebone, posebone.parent, mode='LOCATION') if has_parent else [0,0,0]
                relativeangle = bone.getRelativeTargetMatrix(posebone, posebone.parent, mode='ROTATION', axis='YZX') if has_parent else [0,0,0]

                con_point.add_child(KVNode(_class="AnimConstraintBoneInput",
                                        parent_bone=parent_name if has_parent else bone_name,
                                        relative_origin=KVVector3(relativepos[0], relativepos[1], relativepos[2]),
                                        relative_angles=KVVector3(relativeangle[0], relativeangle[1], relativeangle[2]),
                                        weight=1.0))
                con_point.add_child(KVNode(_class="AnimConstraintSlave",
                                        parent_bone=bone_name,
                                        weight=1.0))

            folder_node.add_child(con_point)

        kv_doc = update_vmdl_container(
            container_class="ScratchArea" if self.to_clipboard else "AnimConstraintList",
            nodes=[folder_node],  # single folder node
            export_path=export_path,
            to_clipboard=self.to_clipboard
        )

        if kv_doc == False:
            return None

        return kv_doc.to_text()

class VALVEMODEL_PT_Animation(VALVEMODEL_ModelConfig):
    bl_label : str = 'Animation'

    def draw_header(self, context : Context) -> None:
        self.layout.label(icon='ANIM_DATA')

    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout

        ob : Object | None = getArmature(context.object)
        if is_armature(ob): pass
        else:
            draw_wrapped_text_col(l,get_id("panel_select_armature"),max_chars=40 , icon='HELP')
            return

        bx : UILayout = draw_title_box(l, VALVEMODEL_PT_Animation.bl_label)
        col = bx.column()

        col.operator(VALVEMODEL_OT_CreateProportionActions.bl_idname,icon='ACTION_TWEAK')

        bx : UILayout = draw_title_box(bx, VALVEMODEL_OT_ExportConstraintProportion.bl_label)
        draw_wrapped_text_col(bx, 'Constraint Proportion exports Orient and Point constraints of bones with a valid export name',max_chars=40)
        row = bx.row(align=True)
        row.scale_y = 1.25
        row.operator(VALVEMODEL_OT_ExportConstraintProportion.bl_idname,text='Write to Clipboard', icon='CONSTRAINT_BONE').to_clipboard = True
        row.operator(VALVEMODEL_OT_ExportConstraintProportion.bl_idname,text='Write to File', icon='CONSTRAINT_BONE').to_clipboard = False

class VALVEMODEL_PT_HitBox(VALVEMODEL_ModelConfig):
    bl_label : str = 'Hitbox'

    def draw_header(self, context : Context) -> None:
        self.layout.label(icon='CUBE')

    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        ob : bpy.types.Object | None = getArmature(context.object)

        if is_empty(ob) or is_armature(ob): pass
        else:
            draw_wrapped_text_col(l,get_id("panel_select_empty"),max_chars=40 , icon='HELP')
            return

        bx : UILayout = draw_title_box(l, VALVEMODEL_PT_HitBox.bl_label)
        
        hitboxes = getHitboxes(ob)
        hitboxsection = create_toggle_section(bx, context.scene.vs, 'show_hitboxes', f'Show Hitboxes: {len(hitboxes)}', '', alert=not bool(hitboxes), align=True)
        if context.scene.vs.show_hitboxes:
            for hbox in hitboxes:
                try:
                    row = hitboxsection.row()
                    row.label(text=hbox.name, icon='CUBE')
                    row.label(text=hbox.parent_bone,icon='BONE_DATA')
                    row.prop(hbox.vs,'smd_hitbox_group',text='')
                except:
                    continue
        
        bx.operator(VALVEMODEL_OT_AddHitbox.bl_idname, icon='CUBE')
        bx.operator(VALVEMODEL_OT_FixHitBox.bl_idname, icon='OPTIONS')
        row : UILayout = bx.row(align=True)
        row.scale_y = 1.25
        row.operator(VALVEMODEL_OT_ExportHitBox.bl_idname,text='Write to Clipboard', icon='FILE_TEXT').to_clipboard = True
        row.operator(VALVEMODEL_OT_ExportHitBox.bl_idname,text='Write to File', icon='TEXT').to_clipboard = False

class VALVEMODEL_OT_ExportHitBox(Operator, VALVEMODEL_PrefabExportOperator):
    bl_idname : str = "smd.export_hitboxes"
    bl_label : str = "Export Source Hitboxes"
    bl_description = "Export empty cubes as Source Engine hitbox format"
    bl_options : Set = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context : Context) -> bool:
        return is_armature(context.object) or is_empty(context.object)

    def get_hitbox_bounds(self, empty_obj):
        if empty_obj.type != 'EMPTY' or empty_obj.empty_display_type != 'CUBE':
            return None

        radius = empty_obj.empty_display_size
        scale = empty_obj.scale

        half_extents = mathutils.Vector((
            radius * scale.x,
            radius * scale.y,
            radius * scale.z
        ))

        world_location = empty_obj.matrix_world.translation

        if empty_obj.parent and empty_obj.parent.type == 'ARMATURE' and empty_obj.parent_bone:
            armature = empty_obj.parent
            pose_bone = armature.pose.bones[empty_obj.parent_bone]

            bone_matrix_no_offset = pose_bone.bone.matrix_local
            bone_matrix_world_no_offset = armature.matrix_world @ bone_matrix_no_offset

            bone_matrix_inv_no_offset = bone_matrix_world_no_offset.inverted()
            local_location = bone_matrix_inv_no_offset @ world_location

            bone_matrix_with_offset = getBoneMatrix(pose_bone, rest_space=True)
            offset_only = bone_matrix_no_offset.inverted() @ bone_matrix_with_offset

            local_location = offset_only.inverted() @ local_location
            half_extents = offset_only.inverted().to_3x3() @ half_extents
        else:
            local_location = empty_obj.location

        corner1 = local_location - half_extents
        corner2 = local_location + half_extents

        min_point = mathutils.Vector((
            min(corner1.x, corner2.x),
            min(corner1.y, corner2.y),
            min(corner1.z, corner2.z)
        ))

        max_point = mathutils.Vector((
            max(corner1.x, corner2.x),
            max(corner1.y, corner2.y),
            max(corner1.z, corner2.z)
        ))

        return min_point, max_point

    def execute(self, context : Context) -> Set:
        active_armature = getArmature(context.object)

        if active_armature is None:
            self.report({'WARNING'}, "Active object is not an armature")
            return {'CANCELLED'}

        hitbox_data = []
        skipped_count = 0

        for obj in bpy.data.objects:
            if obj.type != 'EMPTY' or obj.empty_display_type != 'CUBE':
                continue

            if not hasattr(obj, 'vs') or not hasattr(obj.vs, 'smd_hitbox'):
                continue

            if not obj.vs.smd_hitbox:
                continue

            if not (obj.parent and obj.parent == active_armature and obj.parent_type == 'BONE' and obj.parent_bone):
                continue

            rotation_threshold = 0.0001
            if (abs(obj.rotation_euler.x) > rotation_threshold or
                abs(obj.rotation_euler.y) > rotation_threshold or
                abs(obj.rotation_euler.z) > rotation_threshold):
                skipped_count += 1
                continue

            bounds = self.get_hitbox_bounds(obj)

            if bounds:
                currP = active_armature.data.bones.get(obj.parent_bone)

                if currP:
                    bone_name = getBoneExportName(currP)
                    min_point, max_point = bounds

                    group_number = 0
                    if hasattr(obj.vs, 'smd_hitbox_group'):
                        group_number = obj.vs.smd_hitbox_group

                    hitbox_data.append({
                        'bone': currP,
                        'bone_name': bone_name,
                        'group': group_number,
                        'min': min_point,
                        'max': max_point
                    })

        if len(hitbox_data) == 0:
            if skipped_count > 0:
                self.report({'WARNING'}, f"No valid hitboxes found. {skipped_count} hitbox(es) skipped (missing parent bone or has rotation)")
            else:
                self.report({'WARNING'}, "No hitboxes found with vs.smd_hitbox = True")
            return {'CANCELLED'}

        bones_list = [hb['bone'] for hb in hitbox_data]
        sorted_bones = sortBonesByHierachy(bones_list)

        bone_to_hitbox = {hb['bone']: hb for hb in hitbox_data}

        hitbox_lines = []
        for bone in sorted_bones:
            hb = bone_to_hitbox[bone]
            hitbox_line = f'$hbox\t{hb["group"]}\t"{hb["bone_name"]}"\t\t{hb["min"].x:.2f}\t{hb["min"].y:.2f}\t{hb["min"].z:.2f}\t{hb["max"].x:.2f}\t{hb["max"].y:.2f}\t{hb["max"].z:.2f}'
            hitbox_lines.append(hitbox_line)

        compiled = '\n'.join(hitbox_lines)
        hitbox_count = len(hitbox_lines)

        if self.to_clipboard:
            context.window_manager.clipboard = compiled
            print("\n=== Source Engine Hitboxes ===")
            print(compiled)
            print(f"=============================="
                  f"\nExported {hitbox_count} hitbox(es)")
            if skipped_count > 0:
                print(f"Skipped {skipped_count} hitbox(es) (missing parent bone or has rotation)\n")
            else:
                print()

            if skipped_count > 0:
                self.report({'INFO'}, f"Exported {hitbox_count} hitbox(es) to clipboard ({skipped_count} skipped)")
            else:
                self.report({'INFO'}, f"Exported {hitbox_count} hitbox(es) to clipboard")
        else:
            filepath = self.get_export_path(context)
            if not filepath:
                self.report({'ERROR'}, "No file path specified")
                return {'CANCELLED'}

            export_path, filename, ext = getFilePath(filepath)

            if not filename or not ext:
                self.report({'ERROR'}, "Invalid export path: must include filename and extension")
                return {'CANCELLED'}

            ext_lower = ext.lower()
            if ext_lower not in {'.qc', '.qci'}:
                self.report({'ERROR'}, f"Unsupported file extension '{ext_lower}'. Use .qc or .qci")
                return {'CANCELLED'}

            if not self.write_output(compiled, export_path):
                return {'CANCELLED'}

        return {'FINISHED'}
    
class VALVEMODEL_OT_FixHitBox(Operator):
    bl_idname : str = "smd.fix_hitboxes"
    bl_label : str = "Fix Source Hitboxes Empties Matrix"
    bl_description = "Fixes the Location and Rotation offset due to Blender's weird occurence that the empty is still relative to the world rather than the bone's tip."
    bl_options : Set = {'INTERNAL', 'UNDO'}
    
    def execute(self, context : Context) -> set:
        fixed_count = 0
        
        for obj in bpy.data.objects:
            if obj.type != 'EMPTY' or obj.empty_display_type != 'CUBE':
                continue
            
            if not obj.vs.smd_hitbox_group:
                continue
            
            if not obj.parent or obj.parent.type != 'ARMATURE' or obj.parent_type != 'BONE':
                continue
            
            armature = obj.parent
            bone_name = obj.parent_bone
            
            if bone_name not in armature.data.bones:
                continue
            
            world_matrix = obj.matrix_world.copy()
            world_location = obj.matrix_world.to_translation()
            world_scale = obj.matrix_world.to_scale()
            
            pose_bone = armature.pose.bones[bone_name]
            bone_tip_matrix = armature.matrix_world @ pose_bone.matrix @ mathutils.Matrix.Translation((0, pose_bone.length, 0))
            
            obj.parent = None
            
            obj.parent = armature
            obj.parent_type = 'BONE'
            obj.parent_bone = bone_name
            
            local_location = bone_tip_matrix.inverted() @ world_location
            
            obj.location = local_location
            obj.rotation_euler = (0, 0, 0)
            obj.scale = world_scale
            
            fixed_count += 1
        
        if fixed_count > 0:
            self.report({'INFO'}, f'Fixed {fixed_count} hitbox(es)')
        else:
            self.report({'INFO'}, 'No hitboxes needed fixing')
        
        return {'FINISHED'}
    
class VALVEMODEL_OT_AddHitbox(Operator, VALVEMODEL_ModelConfig):
    bl_idname : str = "smd.add_hitboxes"
    bl_label : str = "Add Source Hitboxes"
    bl_description = "Add empty cubes as Source Engine hitbox format"
    bl_options : Set = {'REGISTER', 'UNDO'}
    
    parent_bone: StringProperty(
        name="Parent Bone",
        description="Bone to parent the hitbox to"
    )
    
    def invoke(self, context : Context, event : Event) -> set:
        armature = getArmature()
        
        if not armature or len(armature.data.bones) == 0:
            self.report({'WARNING'}, 'Armature has no bones')
            return {'CANCELLED'}
        
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context : Context):
        layout = self.layout
        armature = getArmature()
        
        layout.prop_search(self, "parent_bone", armature.data, "bones", text="Parent Bone")
    
    def execute(self, context : Context) -> set:
        armature = getArmature()
        
        if not self.parent_bone:
            self.report({'WARNING'}, 'No parent bone selected')
            return {'CANCELLED'}
        
        if self.parent_bone not in armature.data.bones:
            self.report({'WARNING'}, f'Bone "{self.parent_bone}" not found')
            return {'CANCELLED'}
        
        bpy.ops.object.empty_add(type='CUBE')
        empty = context.active_object
        empty.name = f"hbox_{self.parent_bone}"
        
        empty.parent = armature
        empty.parent_type = 'BONE'
        empty.parent_bone = self.parent_bone
        empty.location = [0,0,0]
        empty.vs.smd_hitbox = True
        
        self.report({'INFO'}, f'Created hitbox parented to {self.parent_bone}')
        
        bpy.ops.object.mode_set(mode='OBJECT')
        return {'FINISHED'}
               
class VALVEMODEL_PT_PBRtoPhong(VALVEMODEL_ModelConfig):
    bl_label : str = 'PBR To Phong'
    
    def draw_header(self, context : Context) -> None:
        self.layout.label(icon='MATERIAL')
        
    def draw_material_selection(self, context : Context, layout : UILayout, matmap : str) -> None:
        split = layout.split(factor=0.8, align=True)
        split.prop_search(context.scene.vs, matmap, bpy.data, 'images',text='')
        split.prop(context.scene.vs, matmap + '_ch',text='')
        
    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        
        bx : UILayout = draw_title_box(l, VALVEMODEL_PT_PBRtoPhong.bl_label)
        
        noticebox = draw_wrapped_text_col(bx,text='The conversion may or may not be accurate!',icon='WARNING_LARGE')
        
        col = bx.column(align=True)
        
        subbox = draw_title_box(col,text='Diffuse/Color Map',icon='MATERIAL_DATA')
        subbox.prop_search(context.scene.vs, 'diffuse_map', bpy.data, 'images',text='')
        
        subbox = draw_title_box(col,text='Skin Map',icon='MATERIAL_DATA')
        self.draw_material_selection(context, subbox, 'skin_map')
        subcol = subbox.column(align=True)
        subcol.prop(context.scene.vs, 'skin_map_gamma', slider=True)
        subcol.prop(context.scene.vs, 'skin_map_contrast', slider=True)
        
        subbox = draw_title_box(col,text='Normal Map',icon='MATERIAL_DATA')
        split = subbox.split(align=True, factor=0.7)
        split.prop_search(context.scene.vs, 'normal_map', bpy.data, 'images',text='')
        split.prop(context.scene.vs, 'normal_map_type',text='')
        subbox.prop(context.scene.vs, 'normal_metal_strength', slider=True)
        
        subbox = draw_title_box(col,text='Roughness Map',icon='MATERIAL_DATA')
        self.draw_material_selection(context, subbox, 'roughness_map')
        
        subbox = draw_title_box(col,text='Metal Map',icon='MATERIAL_DATA')
        self.draw_material_selection(context, subbox, 'metal_map')
        
        subbox = draw_title_box(col,text='AO Map (Optional)',icon='MATERIAL_DATA')
        self.draw_material_selection(context, subbox, 'ambientocclu_map')
        subbox.prop(context.scene.vs, 'ambientocclu_strength', slider=True)
        
        subbox = draw_title_box(col,text='Emissive Map (Optional)',icon='MATERIAL_DATA')
        self.draw_material_selection(context, subbox, 'emissive_map')
        
        col = bx.column(align=True)
        col.prop(context.scene.vs, 'use_envmap')
        col.prop(context.scene.vs, 'darken_diffuse_metal')
        col.prop(context.scene.vs, 'use_color_darken')
        
        bx.operator(VALVEMODEL_OT_ConvertPBRmapsToPhong.bl_idname)
        
        messages = [
            'Use the following Phong settings for a balanced starting point:',
            '   - $phongboost 5',
            '   - $phongalbedotint 1',
            '   - $phongfresnelranges "[0.5 1 2]"',
            '   - $phongalbedoboost 12 (if applicable)\n',
            'When applying a metal map to the color alpha channel, include:',
            '   - $color2 "[.18 .18 .18]"',
            '   - $blendtintbybasealpha 1\n',
            'However, avoid using $color2 or $blendtintbybasealpha together with $phongalbedoboost, as they can visually conflict.\n',
            'If using envmap:',
            '$envmaptint "[.3 .3 .3]"'
        ]
        
        helpsection = create_toggle_section(bx,context.scene.vs,'show_pbrphong_help','Show Help','')
        if context.scene.vs.show_pbrphong_help:
            draw_wrapped_text_col(helpsection,title='A good initial VMT phong setting', text=messages,max_chars=40)

# exponent[:, :, 0] = self.apply_curve(rough_inverted, [[90, 0], [221, 32], [255, 255]]) old curve code for exponent
class VALVEMODEL_OT_ConvertPBRmapsToPhong(Operator):
    bl_idname = 'valvemodel.convert_pbrmaps_to_phong'
    bl_label = 'Convert PBR to Phong'
    bl_options = {'INTERNAL'}
    
    filepath: StringProperty(subtype='FILE_PATH')
    debug_mode: BoolProperty(name="Debug Mode", default=False, description="Export intermediate processing steps")
    
    @classmethod
    def poll(cls, context: Context) -> bool:
        valvesourceprop = context.scene.vs
        return bool(valvesourceprop.diffuse_map and valvesourceprop.normal_map)
    
    def invoke(self, context: Context, event: Event) -> Set:
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context: Context) -> Set:
        vs = context.scene.vs

        if not self.filepath:
            self.report({'ERROR'}, "No export path selected")
            return {'CANCELLED'}
        
        filepath = bpy.path.abspath(self.filepath)
        export_dir = os.path.dirname(filepath)
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        
        if not export_dir or not base_name:
            self.report({'ERROR'}, "Invalid export path or filename")
            return {'CANCELLED'}
        
        diffuse_img = self.get_image_data(vs.diffuse_map)
        normal_img = self.get_image_data(vs.normal_map)
        
        if diffuse_img is None or normal_img is None:
            self.report({'ERROR'}, "Failed to load diffuse or normal texture")
            return {'CANCELLED'}
        
        height, width = diffuse_img.shape[:2]
        
        roughness_img = self.get_channel_data(vs.roughness_map, vs.roughness_map_ch, height, width) if vs.roughness_map else np.ones((height, width))
        metal_img = self.get_channel_data(vs.metal_map, vs.metal_map_ch, height, width) if vs.metal_map else np.zeros((height, width))
        ao_img = self.get_channel_data(vs.ambientocclu_map, vs.ambientocclu_map_ch, height, width) if vs.ambientocclu_map else np.ones((height, width))
        emissive_img = self.get_channel_data(vs.emissive_map, vs.emissive_map_ch, height, width) if vs.emissive_map else None
        skin_img = self.get_channel_data(vs.skin_map, vs.skin_map_ch, height, width) if vs.skin_map else None
        
        if self.debug_mode:
            self.export_debug_grayscale(roughness_img, export_dir, f"{base_name}_debug_roughness_raw.tga")
            self.export_debug_grayscale(metal_img, export_dir, f"{base_name}_debug_metal_raw.tga")
            self.export_debug_grayscale(ao_img, export_dir, f"{base_name}_debug_ao_raw.tga")
            if skin_img is not None:
                self.export_debug_grayscale(skin_img, export_dir, f"{base_name}_debug_skin_raw.tga")
        
        rough_inverted = 1.0 - roughness_img # type:ignore
        if self.debug_mode:
            self.export_debug_grayscale(rough_inverted, export_dir, f"{base_name}_debug_roughness_inverted.tga")
        
        exponent_map = self.create_exponent_map(roughness_img, metal_img, export_dir, base_name if self.debug_mode else None)
        self.save_tga(exponent_map, os.path.join(export_dir, f"{base_name}_e.tga"))
        
        diffuse_map = self.create_diffuse_map(diffuse_img, metal_img, exponent_map, ao_img, skin_img,
                                              vs.ambientocclu_strength, vs.skin_map_gamma, vs.skin_map_contrast,
                                              vs.use_envmap, vs.darken_diffuse_metal, vs.use_color_darken,
                                              export_dir, base_name if self.debug_mode else None)
        self.save_tga(diffuse_map, os.path.join(export_dir, f"{base_name}_d.tga"))
        
        normal_map = self.create_normal_map(normal_img, metal_img, roughness_img, 
                                            vs.normal_map_type, vs.normal_metal_strength,
                                            export_dir, base_name if self.debug_mode else None)
        self.save_tga(normal_map, os.path.join(export_dir, f"{base_name}_n.tga"))
        
        if emissive_img is not None:
            if self.debug_mode:
                self.export_debug_grayscale(emissive_img, export_dir, f"{base_name}_debug_emissive_raw.tga")
            emissive_map = self.create_emissive_map(diffuse_img, emissive_img)
            self.save_tga(emissive_map, os.path.join(export_dir, f"{base_name}_em.tga"))
        
        status = "with debug outputs" if self.debug_mode else ""
        self.report({'INFO'}, f"Exported PBR to Phong maps {status} to {export_dir}")
        return {'FINISHED'}
    
    def export_debug_grayscale(self, data, export_dir, filename):
        height, width = data.shape
        debug_img = np.zeros((height, width, 4), dtype=np.float32)
        debug_img[:, :, 0] = data
        debug_img[:, :, 1] = data
        debug_img[:, :, 2] = data
        debug_img[:, :, 3] = 1.0
        self.save_tga(debug_img, os.path.join(export_dir, filename))
    
    def get_image_data(self, img_name: str):
        if not img_name or img_name not in bpy.data.images:
            return None
        
        img = bpy.data.images[img_name]
        original_colorspace = img.colorspace_settings.name
        img.colorspace_settings.name = 'Non-Color'
        
        width, height = img.size
        pixels = np.array(img.pixels[:]).reshape((height, width, img.channels)) # type:ignore
        
        img.colorspace_settings.name = original_colorspace
        
        if img.channels == 3:
            return np.dstack([pixels, np.ones((height, width))])
        return pixels
    
    def get_channel_data(self, img_name: str, channel: str, height: int, width: int):
        if not img_name or img_name not in bpy.data.images:
            return None
        
        img = bpy.data.images[img_name]
        original_colorspace = img.colorspace_settings.name
        img.colorspace_settings.name = 'Non-Color'
        
        w, h = img.size
        pixels = np.array(img.pixels[:]).reshape((h, w, img.channels)) # type:ignore
        
        img.colorspace_settings.name = original_colorspace
        
        channel_map = {'R': 0, 'G': 1, 'B': 2, 'A': 3}
        ch_idx = channel_map.get(channel)
        
        if ch_idx is not None:
            if ch_idx < img.channels:
                result = pixels[:, :, ch_idx]
            elif ch_idx == 3:
                result = np.ones((h, w))
            else:
                result = pixels[:, :, 0]
        else:
            result = np.mean(pixels[:, :, :3], axis=2)
        
        if (h, w) != (height, width):
            result = self.resize_array(result, height, width)
        
        return result
    
    def resize_array(self, data, new_height, new_width):
        old_height, old_width = data.shape
        
        y_ratio = old_height / new_height
        x_ratio = old_width / new_width
        
        y_coords = np.arange(new_height) * y_ratio
        x_coords = np.arange(new_width) * x_ratio
        
        y0 = np.floor(y_coords).astype(int)
        x0 = np.floor(x_coords).astype(int)
        y1 = np.minimum(y0 + 1, old_height - 1)
        x1 = np.minimum(x0 + 1, old_width - 1)
        
        y_weight = y_coords - y0
        x_weight = x_coords - x0
        
        result = np.zeros((new_height, new_width), dtype=np.float32)
        
        for i in range(new_height):
            for j in range(new_width):
                tl = data[y0[i], x0[j]]
                tr = data[y0[i], x1[j]]
                bl = data[y1[i], x0[j]]
                br = data[y1[i], x1[j]]
                
                top = tl * (1 - x_weight[j]) + tr * x_weight[j]
                bottom = bl * (1 - x_weight[j]) + br * x_weight[j]
                result[i, j] = top * (1 - y_weight[i]) + bottom * y_weight[i]
        
        return result
    
    def apply_curve(self, data, points):
        points_array = np.array(points)
        input_vals = points_array[:, 0] / 255.0
        output_vals = points_array[:, 1] / 255.0
        return np.interp(data, input_vals, output_vals)
    
    def create_exponent_map(self, roughness, metal, export_dir=None, base_name=None):
        height, width = roughness.shape
        exponent = np.ones((height, width, 4))
        
        rough_inverted = 1.0 - roughness
        
        exponent_red = self.apply_curve(rough_inverted, [[90, 0], [221, 60], [255, 255]])
        exponent[:, :, 0] = exponent_red
        exponent[:, :, 1] = metal
        exponent[:, :, 2] = 0.0
        exponent[:, :, 3] = 1.0
        
        if export_dir and base_name:
            self.export_debug_grayscale(exponent_red, export_dir, f"{base_name}_debug_exponent_red_curved.tga")
        
        return exponent
    
    def create_diffuse_map(self, diffuse, metal, exponent, ao, skin, ao_strength, skin_gamma, skin_contrast,
                          use_envmap, darken_diffuse_metal, use_color_darken, export_dir=None, base_name=None):
        height, width = diffuse.shape[:2]
        result = diffuse.copy()
        
        if skin is not None:
            if skin_gamma != 0 or skin_contrast != 0:
                rgb = result[:, :, :3]
                
                if skin_gamma != 0:
                    gamma_val = 1.0 / (1.0 + skin_gamma / 10.0) if skin_gamma > 0 else 1.0 - skin_gamma / 10.0
                    gamma_corrected = np.power(rgb, gamma_val)
                    rgb = rgb * (1.0 - skin[:, :, np.newaxis]) + gamma_corrected * skin[:, :, np.newaxis]
                
                if skin_contrast != 0:
                    contrast_val = skin_contrast * 25.5
                    f = (259 * (contrast_val + 255)) / (255 * (259 - contrast_val))
                    contrasted = np.clip(f * (rgb - 0.5) + 0.5, 0.0, 1.0)
                    rgb = rgb * (1.0 - skin[:, :, np.newaxis]) + contrasted * skin[:, :, np.newaxis]
                
                result[:, :, :3] = rgb
        
        strength = ao_strength / 100.0
        ao_effect = 1.0 - (1.0 - ao) * strength
        
        if skin is not None:
            ao_effect = ao_effect * (1.0 - skin) + skin
        
        if export_dir and base_name:
            self.export_debug_grayscale(ao_effect, export_dir, f"{base_name}_debug_ao_effect.tga")
        
        result[:, :, :3] *= ao_effect[:, :, np.newaxis]

        if darken_diffuse_metal:
            darkened = self.apply_curve(result[:, :, :3], [[0, 0], [255, 100]])
            if export_dir and base_name:
                debug_darkened = np.zeros((height, width, 4), dtype=np.float32)
                debug_darkened[:, :, :3] = darkened
                debug_darkened[:, :, 3] = 1.0
                self.save_tga(debug_darkened, os.path.join(export_dir, f"{base_name}_debug_diffuse_darkened.tga"))
            result[:, :, :3] = (result[:, :, :3] * (1.0 - metal[:, :, np.newaxis]) + 
                               darkened * metal[:, :, np.newaxis])
        elif use_color_darken:
            result[:, :, 3] = metal
            rgb = result[:, :, :3]
            contrast = 10
            f = (259 * (contrast + 255)) / (255 * (259 - contrast))
            contrasted = np.clip(f * (rgb - 0.5) + 0.5, 0.0, 1.0)
            result[:, :, :3] = rgb * (1.0 - metal[:, :, np.newaxis]) + contrasted * metal[:, :, np.newaxis]
        elif use_envmap:
            result[:, :, 3] = exponent[:, :, 0]

        return result
    
    def create_normal_map(self, normal, metal, roughness, normal_type, metal_strength=100.0, export_dir=None, base_name=None):
        height, width = normal.shape[:2]
        result = np.ones((height, width, 4), dtype=np.float32)

        if metal.shape != (height, width):
            metal = self.resize_array(metal, height, width)
        
        if roughness.shape != (height, width):
            roughness = self.resize_array(roughness, height, width)

        if normal_type == 'DEF':
            result[:, :, :3] = normal[:, :, :3]
        elif normal_type == 'RED':
            result[:, :, 2] = normal[:, :, 0]
            result[:, :, 0] = normal[:, :, 3] if normal.shape[2] > 3 else 0.5
            result[:, :, 1] = normal[:, :, 1]
        elif normal_type == 'YELLOW':
            result[:, :, :3] = 1.0 - normal[:, :, :3]
        elif normal_type == 'OPENGL':
            result[:, :, 0] = normal[:, :, 0]
            result[:, :, 1] = 1.0 - normal[:, :, 1]
            result[:, :, 2] = normal[:, :, 2]

        rough_inverted = 1.0 - roughness
        
        exp_red = self.apply_curve(rough_inverted, [[57, 0], [201, 20], [255, 255]])
        exp_green_adjusted = metal * (metal_strength / 100.0)
        
        if export_dir and base_name:
            self.export_debug_grayscale(exp_red, export_dir, f"{base_name}_debug_normal_alpha_exp_red.tga")
            self.export_debug_grayscale(exp_green_adjusted, export_dir, f"{base_name}_debug_normal_alpha_metal_adj.tga")
        
        alpha = np.clip(exp_red / (1.0 - exp_green_adjusted + 1e-7), 0.0, 1.0)
        result[:, :, 3] = alpha
        
        if export_dir and base_name:
            self.export_debug_grayscale(alpha, export_dir, f"{base_name}_debug_normal_alpha_final.tga")
        
        return result
    
    def create_emissive_map(self, diffuse, emissive):
        height, width = diffuse.shape[:2]
        result = np.zeros((height, width, 4), dtype=np.float32)
        
        result[:, :, :3] = diffuse[:, :, :3] * emissive[:, :, np.newaxis]
        result[:, :, 3] = 1.0
        
        return result
        
    def save_tga(self, data, filepath):
        height, width = data.shape[:2]
        has_alpha = data.shape[2] >= 4

        if has_alpha:
            alpha = data[:, :, 3]
            if np.allclose(alpha, 1.0, atol=1e-5):
                data = data[:, :, :3]
                has_alpha = False

        img = bpy.data.images.new(name="temp_export", width=width, height=height, alpha=has_alpha)

        if has_alpha:
            pixels = data.astype(np.float32).flatten()
        else:
            alpha_filled = np.ones((height, width, 1), dtype=np.float32)
            pixels = np.concatenate([data, alpha_filled], axis=2).flatten()

        img.pixels = pixels.tolist()
        img.filepath_raw = filepath
        img.file_format = 'TARGA'
        img.save()
        bpy.data.images.remove(img)