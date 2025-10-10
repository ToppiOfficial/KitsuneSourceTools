import os, math, bpy, mathutils
import numpy as np
from bpy.props import StringProperty
from typing import Set, Any
from bpy import props
from bpy.types import Context, Object, Operator, Panel, UILayout, Event, Bone, Scene
from ..keyvalue3 import KVBool, KVNode, KVVector3
from ..ui.common import KITSUNE_PT_CustomToolPanel

from ..core.commonutils import (
    draw_title_box, draw_wrapped_text_col, is_armature, sanitizeString,
    update_vmdl_container, is_empty, getSelectedBones, PreserveContextMode,
    getArmature, getHitboxes, create_toggle_section, getJiggleBones, getDMXAttachments
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
        self.layout.label(icon='TOOL_SETTINGS')

    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout

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
        ob : Object | None = context.object
        
        if is_armature(ob): pass
        else:
            draw_wrapped_text_col(l,get_id("panel_select_armature"),max_chars=40 , icon='HELP')
            return
        
        bx : UILayout = draw_title_box(l, 'Attachment')
        
        attachments = getDMXAttachments(ob)
        attachmentsection = create_toggle_section(bx, context.scene.vs, 'show_attachments', f'Show Attachments: {len(attachments)}', '', use_alert=not bool(attachments))
        if context.scene.vs.show_attachments:
            for attachment in attachments:
                row = attachmentsection.row(align=True)
                row.label(text=attachment.name,icon='EMPTY_DATA')
                row.label(text=attachment.parent_bone,icon='BONE_DATA')

class VALVEMODEL_PT_Jigglebone(VALVEMODEL_ModelConfig):
    bl_label : str = 'JiggleBone'

    def draw_header(self, context : Context) -> None:
        self.layout.label(icon='CONSTRAINT_BONE')

    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        ob : Object | None = context.object

        if is_armature(ob): pass
        else:
            draw_wrapped_text_col(l,get_id("panel_select_armature"),max_chars=40 , icon='HELP')
            return

        bone : bpy.types.Bone | None = ob.data.bones.active

        if bone:
            titlemessage : str = f'({bone.name})'
        else:
            titlemessage : str = 'JiggleBones'

        bx : UILayout = draw_title_box(l, titlemessage)

        jigglebones = getJiggleBones(ob)
        jigglebonesection = create_toggle_section(bx, context.scene.vs, 'show_jigglebones', f'Show Jigglebones: {len(jigglebones)}', '', use_alert=not bool(jigglebones))
        if context.scene.vs.show_jigglebones:
            for jigglebone in jigglebones:
                row = jigglebonesection.row(align=True)
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
        ob : Object | None = context.object
        return ob and is_armature(ob) and any(b.vs.bone_is_jigglebone for b in ob.data.bones)

    def execute(self, context : Context) -> Set:
        arm = context.object
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
        bx : UILayout = draw_title_box(l, VALVEMODEL_PT_Animation.bl_label)

        ob : Object | None = context.object
        if is_armature(ob): pass
        else:
            draw_wrapped_text_col(bx,get_id("panel_select_armature"),max_chars=40 , icon='HELP')
            return

        col = bx.column()

        col.operator(VALVEMODEL_OT_CreateProportionActions.bl_idname,icon='ACTION_TWEAK')

        bx : UILayout = draw_title_box(bx, VALVEMODEL_OT_ExportConstraintProportion.bl_label)
        draw_wrapped_text_col(bx, 'Constraint Proportion exports Orient and Point constraints of bones with a valid export name',max_chars=40)
        row = bx.row(align=True)
        row.scale_y = 1.25
        row.operator(VALVEMODEL_OT_ExportConstraintProportion.bl_idname,text='Write to Clipboard', icon='CONSTRAINT_BONE').to_clipboard = True
        row.operator(VALVEMODEL_OT_ExportConstraintProportion.bl_idname,text='Write to File', icon='CONSTRAINT_BONE').to_clipboard = False

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
        active_armature = context.object

        if not is_armature(active_armature):
            active_armature = getArmature(context.object)

            if active_armature is None or not is_armature(active_armature):
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

class VALVEMODEL_PT_HitBox(VALVEMODEL_ModelConfig):
    bl_label : str = 'Hitbox'

    def draw_header(self, context : Context) -> None:
        self.layout.label(icon='CUBE')

    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        ob : Object | None = context.object

        if is_empty(ob) or is_armature(ob): pass
        else:
            draw_wrapped_text_col(l,get_id("panel_select_empty"),max_chars=40 , icon='HELP')
            return

        bx : UILayout = draw_title_box(l, VALVEMODEL_PT_HitBox.bl_label)
        
        hitboxes = getHitboxes(ob)
        hitboxsection = create_toggle_section(bx, context.scene.vs, 'show_hitboxes', f'Show Hitboxes: {len(hitboxes)}', '', use_alert=not bool(hitboxes))
        if context.scene.vs.show_hitboxes:
            for hbox in hitboxes:
                row = hitboxsection.row(align=True)
                row.label(text=hbox.name, icon='CUBE')
                row.label(text=hbox.parent_bone, icon='BONE_DATA')
                row.prop(hbox.vs,'smd_hitbox_group',text='')
        
        draw_wrapped_text_col(bx,f'To setup a hitbox, add an "Empty" cube shape and parent it to a bone of the target armature with "SMD Hitbox" property checked.',max_chars=40 , icon='HELP')
        row : UILayout = bx.row(align=True)
        row.scale_y = 1.25
        row.operator(VALVEMODEL_OT_ExportHitBox.bl_idname,text='Write to Clipboard', icon='FILE_TEXT').to_clipboard = True
        row.operator(VALVEMODEL_OT_ExportHitBox.bl_idname,text='Write to File', icon='TEXT').to_clipboard = False
        
class VALVEMODEL_PT_PBRtoPhong(VALVEMODEL_ModelConfig):
    bl_label : str = 'PBR To Phong'
    
    def draw_header(self, context : Context) -> None:
        self.layout.label(icon='MATERIAL')
        
    def draw_material_selection(self, context : Context, layout : UILayout, matmap : str) -> None:
        split = layout.split(factor=0.8, align=True)
        split.prop_search(context.scene.vs, matmap, bpy.data, 'images')
        split.prop(context.scene.vs, matmap + '_ch',text='')
        
    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        
        bx : UILayout = draw_title_box(l, VALVEMODEL_PT_PBRtoPhong.bl_label)
        
        col = bx.column(align=True)
        col.prop_search(context.scene.vs, 'diffuse_map', bpy.data, 'images')
        self.draw_material_selection(context, col, 'roughness_map')
        self.draw_material_selection(context, col, 'metal_map')
        self.draw_material_selection(context, col, 'ambientocclu_map')
        col.prop(context.scene.vs, 'ambientocclu_strength', slider=True)
        col.prop_search(context.scene.vs, 'normal_map', bpy.data, 'images')
        col.prop(context.scene.vs, 'normal_map_type')
        
        col = bx.column(align=True)
        col.prop(context.scene.vs, 'use_envmap')
        col.prop(context.scene.vs, 'darken_diffuse_metal')
        col.prop(context.scene.vs, 'use_color_darken')
        
        bx.operator(VALVEMODEL_OT_ConvertPBRmapsToPhong.bl_idname)
        
        messages = [
            'Use the following Phong settings for a balanced starting point:',
            '   - $phongboost 2.5',
            '   - $phongalbedotint 1',
            '   - $phongfresnelranges "[1 2 3]"',
            '   - $phongalbedoboost 12 (if applicable)\n',
            'When applying a metal map to the color alpha channel, include:',
            '   - $color2 "[.2 .2 .2]"',
            '   - $blendtintbybasealpha 1\n',
            'However, avoid using $color2 or $blendtintbybasealpha together with $phongalbedoboost, as they can visually conflict.'
        ]
        
        helpsection = create_toggle_section(bx,context.scene.vs,'show_pbrphong_help','Show Help','')
        if context.scene.vs.show_pbrphong_help:
            draw_wrapped_text_col(helpsection,title='A good initial VMT phong setting', text=messages,max_chars=40)

class VALVEMODEL_OT_ConvertPBRmapsToPhong(Operator):
    bl_idname = 'valvemodel.convert_pbrmaps_to_phong'
    bl_label = 'Convert PBR to Phong'
    bl_options = {'INTERNAL'}
    
    filepath: StringProperty(subtype='FILE_PATH')
    
    @classmethod
    def poll(cls, context: Context) -> bool:
        valvesourceprop = context.scene.vs
        return bool(valvesourceprop.diffuse_map and valvesourceprop.roughness_map and valvesourceprop.metal_map and valvesourceprop.normal_map)
    
    def invoke(self, context: Context, event : Event) -> Set:
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context: Context) -> Set:
        vs = context.scene.vs

        if not self.filepath:
            self.report({'ERROR'}, "No export path selected")
            return {'CANCELLED'}
        
        # Normalize and extract directory + base name from filepath
        filepath = bpy.path.abspath(self.filepath)
        export_dir = os.path.dirname(filepath)
        base_name = os.path.splitext(os.path.basename(filepath))[0]  # remove extension if present
        
        if not export_dir or not base_name:
            self.report({'ERROR'}, "Invalid export path or filename")
            return {'CANCELLED'}
        
        # read images with explicit colorspace choices
        diffuse_img = self.get_image_data(vs.diffuse_map, 'RGB')
        roughness_img = self.get_image_data(vs.roughness_map, vs.roughness_map_ch)
        metal_img = self.get_image_data(vs.metal_map, vs.metal_map_ch)
        normal_img = self.get_image_data(vs.normal_map, 'RGB')
        ao_img = self.get_image_data(vs.ambientocclu_map, vs.ambientocclu_map_ch) if vs.ambientocclu_map else None
        
        if diffuse_img is None or roughness_img is None or metal_img is None or normal_img is None:
            self.report({'ERROR'}, "Failed to load one or more textures")
            return {'CANCELLED'}
        
        exponent_map = self.create_exponent_map(roughness_img, metal_img)
        self.save_tga(exponent_map, os.path.join(export_dir, f"{base_name}_e.tga"))
        
        diffuse_map = self.create_diffuse_map(diffuse_img, metal_img, exponent_map, ao_img, vs.ambientocclu_strength, vs.use_envmap, vs.darken_diffuse_metal, vs.use_color_darken)
        self.save_tga(diffuse_map, os.path.join(export_dir, f"{base_name}_d.tga"))
        
        normal_map = self.create_normal_map(normal_img, metal=metal_img, roughness=roughness_img, normal_type=vs.normal_map_type)
        self.save_tga(normal_map, os.path.join(export_dir, f"{base_name}_n.tga"))
        
        self.report({'INFO'}, f"Exported PBR to Phong maps to {export_dir}")
        return {'FINISHED'}
    
    def get_image_data(self, img_name: str, channel: str):
        if not img_name or img_name not in bpy.data.images:
            return None
        
        img = bpy.data.images[img_name]
        
        original_colorspace = img.colorspace_settings.name
        img.colorspace_settings.name = 'Non-Color'
        
        width, height = img.size
        pixels = np.array(img.pixels[:]).reshape((height, width, img.channels)) #type:ignore
        
        img.colorspace_settings.name = original_colorspace
        
        if channel == 'RGB':
            if img.channels >= 3:
                return pixels[:, :, :4] if img.channels == 4 else np.dstack([pixels[:, :, :3], np.ones((height, width))])
            return np.dstack([pixels[:, :, 0]] * 3 + [np.ones((height, width))])
        elif channel == 'R':
            return pixels[:, :, 0]
        elif channel == 'G':
            return pixels[:, :, 1] if img.channels > 1 else pixels[:, :, 0]
        elif channel == 'B':
            return pixels[:, :, 2] if img.channels > 2 else pixels[:, :, 0]
        elif channel == 'A':
            return pixels[:, :, 3] if img.channels > 3 else np.ones((height, width))
        
        return pixels
    
    def apply_curve(self, data, points):
        points_array = np.array(points)
        input_vals = points_array[:, 0] / 255.0
        output_vals = points_array[:, 1] / 255.0
        result = np.interp(data, input_vals, output_vals)
        return result
    
    def create_exponent_map(self, roughness, metal):
        height, width = roughness.shape if len(roughness.shape) == 2 else roughness.shape[:2]
        exponent = np.ones((height, width, 4))
        
        rough_inverted = 1.0 - roughness
        exponent[:, :, 0] = self.apply_curve(rough_inverted, [[90, 0], [201, 50], [255, 255]])
        exponent[:, :, 1] = metal if len(metal.shape) == 2 else metal[:, :, 0]
        exponent[:, :, 2] = 1.0
        exponent[:, :, 3] = 1.0
        
        return exponent
    
    def create_diffuse_map(self, diffuse, metal, exponent, ao, ao_strength, use_envmap, darken_diffuse_metal, use_color_darken):
        height, width = diffuse.shape[:2]
        result = np.ones((height, width, 4), dtype=np.float32)

        result[:, :, :3] = diffuse[:, :, :3]
        base_alpha = diffuse[:, :, 3] if diffuse.shape[2] >= 4 else np.ones((height, width))

        if ao is not None:
            ao_channel = ao if len(ao.shape) == 2 else ao[:, :, 0]
            strength = ao_strength / 100.0
            ao_effect = 1.0 - (1.0 - ao_channel) * strength
            result[:, :, :3] *= ao_effect[:, :, np.newaxis]

        metal_channel = metal if len(metal.shape) == 2 else metal[:, :, 0]

        if darken_diffuse_metal:
            # Apply diffuse darkening based on metal
            darkened = self.apply_curve(result[:, :, :3], [[0, 0], [255, 100]])
            result[:, :, :3] = (
                result[:, :, :3] * (1.0 - metal_channel[:, :, np.newaxis])
                + darkened * metal_channel[:, :, np.newaxis]
            )

        elif use_color_darken:
            metal_channel = metal if len(metal.shape) == 2 else metal[:, :, 0]
            result[:, :, 3] = metal_channel

            rgb = result[:, :, :3]

            # Photoshop-style contrast factor (contrast = 60%)
            contrast = 10
            f = (259 * (contrast + 255)) / (255 * (259 - contrast))  # Photoshop formula

            # Apply per-pixel contrast, masked by metal
            contrasted = np.clip(f * (rgb - 0.5) + 0.5, 0.0, 1.0)

            metal_mask = metal_channel[:, :, np.newaxis]
            result[:, :, :3] = rgb * (1.0 - metal_mask) + contrasted * metal_mask

        elif use_envmap:
            # Use exponent red channel for alpha
            result[:, :, 3] = exponent[:, :, 0]

        else:
            # Fallback: diffuse alpha or 1.0
            result[:, :, 3] = base_alpha

        return result
    
    def create_normal_map(self, normal, roughness, metal, normal_type):
        height, width = normal.shape[:2]
        result = np.ones((height, width, 4), dtype=np.float32)

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
        exp_red = self.apply_curve(rough_inverted, [[78, 0], [201, 20], [255, 255]])
        exp_green = metal if len(metal.shape) == 2 else metal[:, :, 0]
        
        exp_green = np.clip(exp_green + 0.15, 0.0, 1.0)

        # Color dodge
        alpha = exp_red / (1.0 - exp_green + 1e-6)
        alpha = np.clip(alpha, 0.0, 1.0)

        result[:, :, 3] = alpha
        return result
        
    def save_tga(self, data, filepath):
        """Save NumPy image array as TGA.
        Automatically drops alpha channel if it's fully opaque (all 1.0)."""
        height, width = data.shape[:2]

        # Check for alpha presence
        has_alpha = data.shape[2] >= 4

        if has_alpha:
            alpha = data[:, :, 3]
            # Detect if alpha is fully opaque (within tiny float tolerance)
            if np.allclose(alpha, 1.0, atol=1e-5):
                # Strip alpha entirely
                data = data[:, :, :3]
                has_alpha = False

        img = bpy.data.images.new(
            name="temp_export",
            width=width,
            height=height,
            alpha=has_alpha
        )

        # Flatten pixels correctly
        if has_alpha:
            pixels = data.astype(np.float32).flatten()
        else:
            # Expand to RGBA because Blender expects 4 channels
            alpha_filled = np.ones((height, width, 1), dtype=np.float32)
            pixels = np.concatenate([data, alpha_filled], axis=2).flatten()

        img.pixels = pixels.tolist()
        img.filepath_raw = filepath
        img.file_format = 'TARGA'
        img.save()

        bpy.data.images.remove(img)