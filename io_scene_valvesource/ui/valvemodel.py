import os, math, bpy, mathutils
from bpy.props import StringProperty, EnumProperty
from typing import Set, Any
from bpy import props
from bpy.types import Context, Object, Operator, Panel, UILayout, Event
from ..keyvalue3 import KVBool, KVNode, KVVector3
from ..ui.common import KITSUNE_PT_CustomToolPanel

from ..utils import hitbox_group

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
    copyArmatureVisualPose, sortBonesByHierachy, getBoneMatrix
)

from ..core.objectutils import(
    fix_bone_parented_empties
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
    bl_label: str = 'ValveModels'
    bl_options: Set = {'DEFAULT_CLOSED'}

    def draw(self, context: Context) -> None:
        l = self.layout 
        col = l.column(align=True)  
        self._draw_active_armature_info(context, col)
        
        col.separator()
        
        sections = [
            ('show_smdattachments', 'Attachment', 'EMPTY_AXIS', self.draw_attachment),
            ('show_smdjigglebone', 'JiggleBone', 'BONE_DATA', self.draw_jigglebone),
            ('show_smdhitbox', 'Hitbox', 'CUBE', self.draw_hitbox),
            ('show_smdanimation', 'Animation', 'ANIM_DATA', self.draw_animation)
        ]
        
        for prop, label, icon, draw_func in sections:
            section = create_toggle_section(
                col, context.scene.vs, prop, 
                show_text=label, icon=icon, 
                toggle_scale_y=0.9,
                icon_outside=True
            )
            if section:
                draw_func(context, section)
    
    def _draw_active_armature_info(self, context: Context, layout: UILayout) -> None:
        armature = getArmature(context.object)
        if armature:
            path = get_object_path(armature, context.view_layer)
            text = f'Active Armature: {armature.name}\n\n{path}'
        else:
            text = 'Active Armature: None'
        draw_wrapped_text_col(layout, text=text, icon='ARMATURE_DATA')
        
        ob = armature if armature else context.object
        if not ob:
            return
        
        info_section = create_toggle_section(
            layout, context.scene.vs, 'show_smdarmature',
            show_text='Show All Lists',
            icon='PRESET',
            toggle_scale_y=0.8
        )
        
        if not info_section:
            return
        
        attachments = getDMXAttachments(ob)
        att_section = create_toggle_section(
            info_section, context.scene.vs, 'show_attachments',
            f'Attachment List ({len(attachments)})',
            alert=not bool(attachments),
            align=True,
            toggle_scale_y=0.8
        )
        if att_section:
            for attachment in attachments:
                row = att_section.row(align=True)
                row.label(text=attachment.name, icon='EMPTY_DATA')
                row.label(text=attachment.parent_bone, icon='BONE_DATA')
        
        if is_armature(ob):
            jigglebones = getJiggleBones(ob)
            jb_section = create_toggle_section(
                info_section, context.scene.vs, 'show_jigglebones',
                f'JiggleBone List ({len(jigglebones)})',
                alert=not bool(jigglebones),
                align=True,
                toggle_scale_y=0.8
            )
            if jb_section:
                for jigglebone in jigglebones:
                    row = jb_section.row(align=True)
                    row.label(text=jigglebone.name, icon='BONE_DATA')
                    
                    collection_count = len(jigglebone.collections)
                    if collection_count == 1:
                        row.label(text=jigglebone.collections[0].name, icon='GROUP_BONE')
                    elif collection_count > 1:
                        row.label(text="In Multiple Collection", icon='GROUP_BONE')
                    else:
                        row.label(text="Not in Collection", icon='GROUP_BONE')
        
        hitboxes = getHitboxes(ob)
        hb_section = create_toggle_section(
            info_section, context.scene.vs, 'show_hitboxes',
            f'Hitbox List ({len(hitboxes)})',
            alert=not bool(hitboxes),
            align=True,
            toggle_scale_y=0.8
        )
        if hb_section:
            for hbox in hitboxes:
                try:
                    row = hb_section.row()
                    row.label(text=hbox.name, icon='CUBE')
                    row.label(text=hbox.parent_bone, icon='BONE_DATA')
                    row.prop(hbox.vs, 'smd_hitbox_group', text='')
                except:
                    continue
    
    def _validate_object_type(self, layout: UILayout, obj, required_type: str) -> bool:
        """Validate object type and show error if invalid. Returns True if valid."""
        type_checks = {
            'armature': is_armature,
            'empty': is_empty,
            'armature_or_empty': lambda o: is_armature(o) or is_empty(o)
        }
        
        if obj and type_checks.get(required_type, lambda o: False)(obj):
            return True
        
        message_map = {
            'armature': 'panel_select_armature',
            'empty': 'panel_select_empty',
            'armature_or_empty': 'panel_select_armature'
        }
        
        draw_wrapped_text_col(layout, get_id(message_map[required_type]), max_chars=40, icon='HELP')
        return False
       
    def draw_attachment(self, context: Context, layout: UILayout) -> None:
        ob = getArmature(context.object)
        
        if not self._validate_object_type(layout, ob, 'armature_or_empty'):
            return
        
        layout.operator(VALVEMODEL_OT_FixAttachment.bl_idname, icon='OPTIONS')
    
    def draw_jigglebone(self, context: Context, layout: UILayout) -> None:
        ob = getArmature(context.object)
        
        if not self._validate_object_type(layout, ob, 'armature'):
            return
        
        bone = ob.data.bones.active

        self._draw_export_buttons(
            layout, 
            VALVEMODEL_OT_ExportJiggleBone.bl_idname,
            scale_y=1.2
        )
        
        if bone and bone.select:
            self.draw_jigglebone_properties(layout, bone)
        else:
            box = layout.box()
            box.label(text='Select a Valid Bone', icon='ERROR')

    def _draw_export_buttons(self, layout: UILayout, operator: str, scale_y: float = 1.2, 
                            clipboard_text: str = 'Write to Clipboard',
                            file_text: str = 'Write to File',
                            clipboard_icon: str = 'FILE_TEXT',
                            file_icon: str = 'TEXT') -> None:
        """Draw standard export button pair (clipboard/file)."""
        row = layout.row(align=True)
        row.scale_y = scale_y
        row.operator(operator, text=clipboard_text, icon=clipboard_icon).to_clipboard = True
        row.operator(operator, text=file_text, icon=file_icon).to_clipboard = False

    def draw_jigglebone_properties(self, layout: UILayout, bone: bpy.types.Bone) -> None:
        vs_bone = bone.vs
        
        box = layout
        row = box.row()
        row.prop(
            vs_bone, 'bone_is_jigglebone', 
            toggle=True, 
            icon='DOWNARROW_HLT' if vs_bone.bone_is_jigglebone else 'RIGHTARROW',
            text=f'{bone.name}',
            emboss=True
        )
        
        if not vs_bone.bone_is_jigglebone:
            return
        
        box = layout
        col = box.column(align=False)
        
        col.label(text='Jiggle Type:', icon='DRIVER')
        subcol = col.column(align=True)
        subcol.prop(vs_bone, 'jiggle_flex_type', text='Flexibility')
        subcol.prop(vs_bone, 'jiggle_base_type', text='Base Type')
        
        col.separator(factor=0.5)
        
        self._draw_flexible_rigid_props(col, vs_bone)
        
        if vs_bone.jiggle_base_type == 'BASESPRING':
            self._draw_basespring_props(col, vs_bone)
        elif vs_bone.jiggle_base_type == 'BOING':
            self._draw_boing_props(col, vs_bone)
    
    def _draw_flexible_rigid_props(self, layout: UILayout, vs_bone) -> None:
        if vs_bone.jiggle_flex_type not in ['FLEXIBLE', 'RIGID']:
            return
        
        box = layout.box()
        col = box.column(align=False)
        
        col.label(text='Physical Properties:', icon='PHYSICS')
        subcol = col.column(align=True)
        subcol.prop(vs_bone, 'use_bone_length_for_jigglebone_length', toggle=True, text='Use Bone Length')
        if not vs_bone.use_bone_length_for_jigglebone_length:
            subcol.prop(vs_bone, 'jiggle_length', text='Length')
        subcol.prop(vs_bone, 'jiggle_tip_mass', text='Tip Mass')
        
        if vs_bone.jiggle_flex_type == 'FLEXIBLE':
            col.separator(factor=0.5)
            col.label(text='Stiffness & Damping:', icon='FORCE_TURBULENCE')
            
            subcol = col.column(align=True)
            subcol.prop(vs_bone, 'jiggle_yaw_stiffness', slider=True, text='Yaw Stiffness')
            subcol.prop(vs_bone, 'jiggle_yaw_damping', slider=True, text='Yaw Damping')
            
            subcol = col.column(align=True)
            subcol.prop(vs_bone, 'jiggle_pitch_stiffness', slider=True, text='Pitch Stiffness')
            subcol.prop(vs_bone, 'jiggle_pitch_damping', slider=True, text='Pitch Damping')
            
            col.separator(factor=0.5)
            subcol = col.column(align=True)
            subcol.prop(vs_bone, 'jiggle_allow_length_flex', toggle=True, text='Allow Length Flex')
            
            if vs_bone.jiggle_allow_length_flex:
                subcol.prop(vs_bone, 'jiggle_along_stiffness', slider=True, text='Along Stiffness')
                subcol.prop(vs_bone, 'jiggle_along_damping', slider=True, text='Along Damping')
        
        layout.separator(factor=0.5)
        self._draw_angle_constraints(layout, vs_bone)
    
    def _draw_angle_constraints(self, layout: UILayout, vs_bone) -> None:
        box = layout.box()
        col = box.column(align=False)
        
        col.label(text='Angle Constraints:', icon='CON_ROTLIMIT')
        row = col.row(align=True)
        row.prop(vs_bone, 'jiggle_has_angle_constraint', toggle=True, text='Angle')
        row.prop(vs_bone, 'jiggle_has_yaw_constraint', toggle=True, text='Yaw')
        row.prop(vs_bone, 'jiggle_has_pitch_constraint', toggle=True, text='Pitch')
        
        has_any = any([
            vs_bone.jiggle_has_angle_constraint,
            vs_bone.jiggle_has_yaw_constraint,
            vs_bone.jiggle_has_pitch_constraint
        ])
        
        if not has_any:
            return
        
        col.separator(factor=0.3)
        
        if vs_bone.jiggle_has_angle_constraint:
            subcol = col.column(align=True)
            subcol.prop(vs_bone, 'jiggle_angle_constraint', text='Angular Constraint')
            col.separator(factor=0.3)
        
        if vs_bone.jiggle_has_yaw_constraint:
            subcol = col.column(align=False)
            subcol.label(text='Yaw Limits:', icon='EMPTY_SINGLE_ARROW')
            row = subcol.row(align=True)
            row.prop(vs_bone, 'jiggle_yaw_constraint_min', slider=True, text='Min')
            row.prop(vs_bone, 'jiggle_yaw_constraint_max', slider=True, text='Max')
            subcol.prop(vs_bone, 'jiggle_yaw_friction', slider=True, text='Friction')
            col.separator(factor=0.3)
        
        if vs_bone.jiggle_has_pitch_constraint:
            subcol = col.column(align=False)
            subcol.label(text='Pitch Limits:', icon='EMPTY_SINGLE_ARROW')
            row = subcol.row(align=True)
            row.prop(vs_bone, 'jiggle_pitch_constraint_min', slider=True, text='Min')
            row.prop(vs_bone, 'jiggle_pitch_constraint_max', slider=True, text='Max')
            subcol.prop(vs_bone, 'jiggle_pitch_friction', slider=True, text='Friction')
    
    def _draw_basespring_props(self, layout: UILayout, vs_bone) -> None:
        box = layout.box()
        col = box.column(align=False)
        
        col.label(text='Base Spring Properties:', icon='FORCE_HARMONIC')
        subcol = col.column(align=True)
        subcol.prop(vs_bone, 'jiggle_base_stiffness', slider=True, text='Stiffness')
        subcol.prop(vs_bone, 'jiggle_base_damping', slider=True, text='Damping')
        subcol.prop(vs_bone, 'jiggle_base_mass', slider=True, text='Mass')
        
        col.separator(factor=0.5)
        col.label(text='Side Constraints:', icon='CON_LOCLIMIT')
        row = col.row(align=True)
        row.prop(vs_bone, 'jiggle_has_left_constraint', toggle=True, text='Side')
        row.prop(vs_bone, 'jiggle_has_up_constraint', toggle=True, text='Up')
        row.prop(vs_bone, 'jiggle_has_forward_constraint', toggle=True, text='Forward')
        
        has_any = any([
            vs_bone.jiggle_has_left_constraint,
            vs_bone.jiggle_has_up_constraint,
            vs_bone.jiggle_has_forward_constraint
        ])
        
        if not has_any:
            return
        
        col.separator(factor=0.3)
        
        constraint_props = [
            (vs_bone.jiggle_has_left_constraint, 'left', 'Side'),
            (vs_bone.jiggle_has_up_constraint, 'up', 'Up'),
            (vs_bone.jiggle_has_forward_constraint, 'forward', 'Forward')
        ]
        
        for has_constraint, direction, label in constraint_props:
            if has_constraint:
                subcol = col.column(align=False)
                subcol.label(text=f'{label} Limits:', icon='EMPTY_SINGLE_ARROW')
                row = subcol.row(align=True)
                row.prop(vs_bone, f'jiggle_{direction}_constraint_min', slider=True, text='Min')
                row.prop(vs_bone, f'jiggle_{direction}_constraint_max', slider=True, text='Max')
                subcol.prop(vs_bone, f'jiggle_{direction}_friction', slider=True, text='Friction')
                col.separator(factor=0.3)
    
    def _draw_boing_props(self, layout: UILayout, vs_bone) -> None:
        box = layout.box()
        col = box.column(align=False)
        
        col.label(text='Boing Properties:', icon='FORCE_FORCE')
        subcol = col.column(align=True)
        subcol.prop(vs_bone, 'jiggle_impact_speed', slider=True, text='Impact Speed')
        subcol.prop(vs_bone, 'jiggle_impact_angle', slider=True, text='Impact Angle')
        subcol.prop(vs_bone, 'jiggle_damping_rate', slider=True, text='Damping Rate')
        subcol.prop(vs_bone, 'jiggle_frequency', slider=True, text='Frequency')
        subcol.prop(vs_bone, 'jiggle_amplitude', slider=True, text='Amplitude')
    
    def draw_hitbox(self, context: Context, layout: UILayout) -> None:
        ob = getArmature(context.object)
        
        if not self._validate_object_type(layout, ob, 'armature_or_empty'):
            return
        
        layout.operator(VALVEMODEL_OT_FixHitBox.bl_idname, icon='OPTIONS')
        layout.operator(VALVEMODEL_OT_AddHitbox.bl_idname, icon='CUBE')
        
        self._draw_export_buttons(
            layout,
            VALVEMODEL_OT_ExportHitBox.bl_idname,
            scale_y=1.25
        )
    
    def draw_animation(self, context: Context, layout: UILayout) -> None:
        ob = getArmature(context.object)
        
        if not self._validate_object_type(layout, ob, 'armature'):
            return
        
        layout.operator(VALVEMODEL_OT_CreateProportionActions.bl_idname, icon='ACTION_TWEAK')
        
        bx = draw_title_box(layout, VALVEMODEL_OT_ExportConstraintProportion.bl_label)
        draw_wrapped_text_col(
            bx,
            'Constraint Proportion exports Orient and Point constraints of bones with a valid export name',
            max_chars=40
        )
        
        self._draw_export_buttons(
            bx,
            VALVEMODEL_OT_ExportConstraintProportion.bl_idname,
            scale_y=1.25,
            clipboard_icon='CONSTRAINT_BONE',
            file_icon='CONSTRAINT_BONE'
        )
      
        
class VALVEMODEL_OT_FixAttachment(Operator):
    bl_idname: str = "smd.fix_attachments"
    bl_label: str = "Fix Source Attachment Empties Matrix"
    bl_description = "Fixes the Location and Rotation offset due to Blender's weird occurence that the empty is still relative to the world rather than the bone's tip."
    bl_options: Set = {'INTERNAL', 'UNDO'}
    
    def execute(self, context: Context) -> set:
        def is_attachment(obj):
            return obj.vs.dmx_attachment
        
        fixed_count = fix_bone_parented_empties(
            filter_func=is_attachment,
            preserve_rotation=True
        )
        
        if fixed_count > 0:
            self.report({'INFO'}, f'Fixed {fixed_count} attachment(s)')
        else:
            self.report({'INFO'}, 'No attachments needed fixing')
        
        return {'FINISHED'}

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

class VALVEMODEL_PT_ClothNode():
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
        if clothnodesection is not None:
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
    bl_idname: str = "smd.fix_hitboxes"
    bl_label: str = "Fix Source Hitboxes Empties Matrix"
    bl_description = "Fixes the Location and Rotation offset due to Blender's weird occurence that the empty is still relative to the world rather than the bone's tip."
    bl_options: Set = {'INTERNAL', 'UNDO'}
    
    def execute(self, context: Context) -> set:
        def is_hitbox(obj):
            return (obj.empty_display_type == 'CUBE' and 
                    obj.vs.smd_hitbox_group)
        
        fixed_count = fix_bone_parented_empties(
            filter_func=is_hitbox,
            preserve_rotation=False
        )
        
        if fixed_count > 0:
            self.report({'INFO'}, f'Fixed {fixed_count} hitbox(es)')
        else:
            self.report({'INFO'}, 'No hitboxes needed fixing')
        
        return {'FINISHED'}
    
class VALVEMODEL_OT_AddHitbox(Operator):
    bl_idname : str = "smd.add_hitboxes"
    bl_label : str = "Add Source Hitboxes"
    bl_description = "Add empty cubes as Source Engine hitbox format"
    bl_options : Set = {'REGISTER', 'UNDO'}
    
    parent_bone: StringProperty(
        name="Parent Bone",
        description="Bone to parent the hitbox to"
    )
    
    hitbox_group: EnumProperty(
        name="Hitbox Group",
        description="Hitbox group for collision detection",
        items=hitbox_group,
        default='0'
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
        
        if armature.mode == 'POSE' and context.selected_pose_bones:
            layout.label(text=f"{len(context.selected_pose_bones)} bone(s) selected")
        else:
            layout.prop_search(self, "parent_bone", armature.data, "bones", text="Parent Bone")
        
        layout.prop(self, "hitbox_group")
    
    def execute(self, context : Context) -> set:
        armature = getArmature()
        
        previous_mode = armature.mode if armature else 'OBJECT'
        selected_pose_bones = []
        
        if previous_mode == 'POSE' and context.selected_pose_bones:
            selected_pose_bones = [bone.name for bone in context.selected_pose_bones]
        elif self.parent_bone:
            selected_pose_bones = [self.parent_bone]
        
        if not selected_pose_bones:
            self.report({'WARNING'}, 'No parent bone selected')
            return {'CANCELLED'}
        
        if previous_mode == 'POSE':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        created_count = 0
        for bone_name in selected_pose_bones:
            if bone_name not in armature.data.bones:
                self.report({'WARNING'}, f'Bone "{bone_name}" not found')
                continue
            
            bpy.ops.object.empty_add(type='CUBE')
            empty = context.active_object
            empty.name = f"hbox_{bone_name}"
            
            empty.parent = armature
            empty.parent_type = 'BONE'
            empty.parent_bone = bone_name
            empty.location = [0,0,0]
            empty.vs.smd_hitbox = True
            empty.vs.smd_hitbox_group = self.hitbox_group
            
            created_count += 1
        
        if created_count > 0:
            self.report({'INFO'}, f'Created {created_count} hitbox(es)')
        
        if previous_mode == 'POSE':
            armature.select_set(True)
            context.view_layer.objects.active = armature
            bpy.ops.object.mode_set(mode='POSE')
        else:
            bpy.ops.object.mode_set(mode='OBJECT')
        
        return {'FINISHED'}
