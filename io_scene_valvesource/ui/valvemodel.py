import os, math, bpy, mathutils, re
from bpy.props import StringProperty, EnumProperty
from typing import Set, Any
from bpy import props
from bpy.types import Context, Object, Operator, Panel, UILayout, Event
from ..keyvalue3 import KVBool, KVNode, KVVector3, KVParser
from ..ui.common import KITSUNE_PT_CustomToolPanel

from ..utils import hitbox_group, import_hitboxes_from_content

from ..core.commonutils import (
    draw_title_box_layout, draw_wrapped_texts, is_armature, sanitize_string,
    update_vmdl_container, is_empty, get_selected_bones, preserve_context_mode,
    get_armature, get_hitboxes, draw_toggleable_layout, get_jigglebones, get_dmxattachments,
    get_object_path
)

from ..utils import (
    get_filepath, get_smd_prefab_enum, get_id, State, Compiler, import_jigglebones_from_content
)

from ..core.boneutils import(
    get_bone_exportname,
)

from ..core.armatureutils import(
    copy_target_armature_visualpose, sort_bone_by_hierachy, get_bone_matrix, get_relative_target_matrix
)

from ..core.objectutils import(
    reevaluate_bone_parented_empty_matrix
)

class PrefabExport():
    
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

        export_path, filename, ext = get_filepath(prefabs[idx].filepath)
        if not filename or not ext:
            self.report({'ERROR'}, "Invalid export path: must include filename and extension (e.g. constraints.vmdl)")
            return None

        if ext.lower() not in {'.vmdl', '.vmdl_prefab', '.qci', '.qc'}:
            self.report({'ERROR'}, f"Unsupported file extension '{ext.lower()}'")
            return None

        return export_path

    def write_output(self, compiled: str | None, export_path: str | None = None, warnings : list[str] = []):
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
            
        if len(warnings) > 0:
            self.report({'WARNING'}, f"Data exported with {len(warnings)} warnings (see console) to {export_path}")
            
            for warning in warnings:
                print(warning)
            
        else:
            self.report({'INFO'}, f"Data exported to {export_path}")
        return True

class PrefabImport():
    
    def simple_read_file(self, filepath: str):
        content = None
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        
        except Exception as e:
            print(f"- Failed to read file '{filepath}': {e}")
            
        finally:
            return content if content else None

class VALVEMODEL_PT_PANEL(KITSUNE_PT_CustomToolPanel, Panel):
    bl_label: str = 'ValveModel'
    
    write_load_button_scale = 1.25

    def draw(self, context: Context) -> None:
        l = self.layout 
        col = l.column(align=True)  
        self._draw_active_armature_info(context, col)
        
        col.separator()
        
        sections = [
            ('show_smdjigglebone', 'JiggleBone', 'BONE_DATA', self.draw_jigglebone),
            ('show_smdhitbox', 'Hitbox', 'CUBE', self.draw_hitbox),
            ('show_smdattachments', 'Attachment', 'EMPTY_DATA', self.draw_attachment),
            ('show_smdanimation', 'Animation', 'ANIM_DATA', self.draw_animation)
        ]
        
        for prop, label, icon, draw_func in sections:
            section = draw_toggleable_layout(
                col, context.scene.vs, prop, 
                show_text=label, icon=icon, 
                toggle_scale_y=1.0,
                icon_outside=True
            )
            if section:
                draw_func(context, section)
    
    def _draw_active_armature_info(self, context: Context, layout: UILayout) -> None:
        armature = get_armature(context.object)
        if armature:
            path = get_object_path(armature, context.view_layer)
            text = f'Target Armature: {path}\n'
        else:
            text = 'Target Armature: None\n'
        draw_wrapped_texts(layout, text=text, icon='ARMATURE_DATA')
        
        ob = armature if armature else context.object
        if not ob:
            return
        
        info_section = draw_toggleable_layout(
            layout, context.scene.vs, 'show_smdarmature',
            show_text='Show All Lists',
            icon='PRESET',
            toggle_scale_y=0.8
        )
        
        if not info_section:
            return
        
        attachments = get_dmxattachments(ob)
        att_section = draw_toggleable_layout(
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
                row.prop_search(attachment, 'parent_bone', search_data=ob.data, search_property='bones', text='')
        
        if is_armature(ob):
            jigglebones = get_jigglebones(ob)
            jb_section = draw_toggleable_layout(
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
        
        hitboxes = get_hitboxes(ob)
        hb_section = draw_toggleable_layout(
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
                    row.prop_search(hbox, 'parent_bone', search_data=ob.data, search_property='bones', text='')
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
        
        draw_wrapped_texts(layout, get_id(message_map[required_type]), max_chars=40, icon='HELP')
        return False
       
    def draw_jigglebone(self, context: Context, layout: UILayout) -> None:
        ob = get_armature(context.object)
        
        if not self._validate_object_type(layout, ob, 'armature'):
            return
        
        bone = ob.data.bones.active
        
        layout.label(text='Write & Load')
        
        self._draw_export_buttons(layout, VALVEMODEL_OT_ExportJiggleBone.bl_idname,scale_y=self.write_load_button_scale)
        
        col = layout.column()
        col.scale_y = self.write_load_button_scale
        col.operator(VALVEMODEL_OT_ImportJigglebones.bl_idname, icon='IMPORT')
        
        layout.label(text='Jigglebone Tools')
        if bone and bone.select:
            layout.operator(VALVEMODEL_OT_CopyJiggleBoneProperties.bl_idname, icon='COPYDOWN')
            self.draw_jigglebone_properties(layout, bone)
        else:
            box = layout.box()
            box.label(text='Select a Valid Bone', icon='ERROR')

    def _draw_export_buttons(self, layout: UILayout, operator: str, scale_y: float = 1.2, 
                            clipboard_text: str = 'Write to Clipboard',
                            file_text: str = 'Write to File',
                            clipboard_icon: str = 'FILE_TEXT',
                            file_icon: str = 'EXPORT') -> None:
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
        ob = get_armature(context.object)
        
        if not self._validate_object_type(layout, ob, 'armature_or_empty'):
            return
        
        layout.label(text='Write & Load')
        
        self._draw_export_buttons(layout,VALVEMODEL_OT_ExportHitBox.bl_idname,scale_y=self.write_load_button_scale)
        
        col = layout.column()
        col.scale_y = self.write_load_button_scale
        col.operator(VALVEMODEL_OT_ImportHitBox.bl_idname, icon='IMPORT')
        
        layout.label(text='Hitbox Tools')
        layout.operator(VALVEMODEL_OT_AddHitbox.bl_idname, icon='CUBE')
        layout.operator(VALVEMODEL_OT_FixHitBox.bl_idname, icon='OPTIONS')
    
    def draw_attachment(self,context: Context, layout: UILayout) -> None:
        ob = get_armature(context.object)
        
        layout.label(text='Attachment Tools')
        layout.operator(VALVEMODEL_OT_FixAttachment.bl_idname, icon='OPTIONS')
    
    def draw_animation(self, context: Context, layout: UILayout) -> None:
        ob = get_armature(context.object)
        
        if not self._validate_object_type(layout, ob, 'armature'):
            return
        
        layout.operator(VALVEMODEL_OT_CreateProportionActions.bl_idname, icon='ACTION_TWEAK')
        
        bx = draw_title_box_layout(layout, VALVEMODEL_OT_ExportConstraintProportion.bl_label)
        draw_wrapped_texts(
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
    bl_label: str = "Fix Attachment Matrix"
    bl_description = "Fixes the Location and Rotation offset due to Blender's weird occurence that the empty is still relative to the world rather than the bone's tip."
    bl_options: Set = {'INTERNAL', 'UNDO'}
    
    def execute(self, context: Context) -> set:
        def is_attachment(obj):
            return obj.vs.dmx_attachment
        
        fixed_count = reevaluate_bone_parented_empty_matrix(
            filter_func=is_attachment,
            preserve_rotation=True
        )
        
        if fixed_count > 0:
            self.report({'INFO'}, f'Fixed {fixed_count} attachment(s)')
        else:
            self.report({'INFO'}, 'No attachments needed fixing')
        
        return {'FINISHED'}

class VALVEMODEL_OT_ImportJigglebones(Operator, PrefabImport):
    bl_idname : str = "smd.import_jigglebones"
    bl_label : str = "Import Jigglebones"
    bl_options: Set = {'REGISTER', 'UNDO'}
    
    filepath: StringProperty(
        subtype='FILE_PATH',
        name="File Path",
        description="Path to the VMDL or QC file containing jigglebone data"
    )
    
    @classmethod
    def poll(cls, context) -> bool:
        return bool(context.mode in {'OBJECT', 'POSE'} and is_armature(context.object) and len(context.object.data.bones) > 0)
    
    def invoke(self, context, event) -> set:
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context) -> set:
        armature = context.object
        
        if not self.filepath:
            self.report({'ERROR'}, "No file selected.")
            return {'CANCELLED'}
        
        filepath : str = self.filepath
        
        # Determine file type
        file_extension = filepath.lower().split('.')[-1]
        
        if file_extension in ['vmdl', 'vmdl_prefab']:
            imported_count = self._import_vmdl(context, armature, filepath)
            
        elif file_extension in ['qc', 'qci']:
            content = self.simple_read_file(filepath)
            
            if not content:
                self.report({'ERROR'}, f"Failed to read file '{filepath}'.")
                return {'CANCELLED'}
            
            imported_count, missing_bones = import_jigglebones_from_content(content, armature)
            if missing_bones:
                self.report({'WARNING'}, f"Could not find bones for {len(missing_bones)} jigglebone(s): {', '.join(missing_bones)}")
        
        else:
            self.report({'ERROR'}, f"Unsupported file type: .{file_extension}. Please select a .vmdl, .vmdl_prefab, .qc, or .qci file.")
            return {'CANCELLED'}
            
        if imported_count > 0:
            self.report({'INFO'}, f"Successfully imported jigglebone data for {imported_count} bone(s).")
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "No jigglebone data imported.")
            return {'CANCELLED'}

    def _import_vmdl(self, context, armature, filepath) -> int:
        imported_count = 0
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                file_content = f.read()
        except Exception as e:
            self.report({'ERROR'}, f"Failed to read VMDL file '{filepath}': {e}")
            return 0
            
        try:
            parser = KVParser(file_content)
            kv_doc = parser.parse()
        except Exception as e:
            self.report({'ERROR'}, f"Failed to parse VMDL file '{filepath}': {e}")
            return 0
            
        bone_map = {}
        for b in armature.data.bones:
            bone_map[get_bone_exportname(b)] = b
        
        def find_jigglebone_nodes(node):
            """Recursively find all JiggleBone nodes in the structure."""
            found = []
            
            if isinstance(node, KVNode):
                if node.properties.get('_class') == "JiggleBone":
                    found.append(node)
                
                for child in node.children:
                    found.extend(find_jigglebone_nodes(child))
            
            elif isinstance(node, dict):
                for value in node.values():
                    found.extend(find_jigglebone_nodes(value))
            
            elif isinstance(node, (list, tuple)):
                for item in node:
                    found.extend(find_jigglebone_nodes(item))
            
            return found
        
        jigglebone_nodes = []
        for root_key, root_node in kv_doc.roots.items():
            jigglebone_nodes.extend(find_jigglebone_nodes(root_node))
        
        if not jigglebone_nodes:
            self.report({'WARNING'}, f"No JiggleBone nodes found in VMDL file. Searched {len(kv_doc.roots)} root(s).")
            return 0

        for jb_node in jigglebone_nodes:
            props = jb_node.properties
            root_bone_name = props.get('jiggle_root_bone')
            
            if not root_bone_name:
                self.report({'WARNING'}, f"JiggleBone node without 'jiggle_root_bone' property found. Skipping.")
                continue
                
            blender_bone = bone_map.get(root_bone_name)
            if not blender_bone:
                self.report({'WARNING'}, f"No matching Blender bone found for '{root_bone_name}'. Skipping.")
                continue
                
            vs_bone = blender_bone.vs
            vs_bone.bone_is_jigglebone = True
            imported_count += 1
            
            jiggle_type_int = props.get('jiggle_type')
            if jiggle_type_int == 0:
                vs_bone.jiggle_flex_type = 'RIGID'
            elif jiggle_type_int == 1:
                vs_bone.jiggle_flex_type = 'FLEXIBLE'
            elif jiggle_type_int == 2:
                vs_bone.jiggle_flex_type = 'NONE'
                
            vs_bone.jiggle_has_yaw_constraint = props.get('has_yaw_constraint', False)
            vs_bone.jiggle_has_pitch_constraint = props.get('has_pitch_constraint', False)
            vs_bone.jiggle_has_angle_constraint = props.get('has_angle_constraint', False)
            vs_bone.jiggle_has_base_spring = props.get('has_base_spring', False)
            vs_bone.jiggle_allow_length_flex = props.get('allow_flex_length', False)
            
            if vs_bone.jiggle_has_base_spring:
                vs_bone.jiggle_base_type = 'BASESPRING'
            else:
                vs_bone.jiggle_base_type = 'NONE'

            if 'length' in props:
                vs_bone.use_bone_length_for_jigglebone_length = False
                vs_bone.jiggle_length = float(props['length'])
            if 'tip_mass' in props:
                vs_bone.jiggle_tip_mass = float(props['tip_mass'])

            if 'angle_limit' in props:
                vs_bone.jiggle_angle_constraint = math.radians(float(props['angle_limit']))
            if 'min_yaw' in props:
                vs_bone.jiggle_yaw_constraint_min = math.radians(float(props['min_yaw']))
            if 'max_yaw' in props:
                vs_bone.jiggle_yaw_constraint_max = math.radians(float(props['max_yaw']))
            if 'min_pitch' in props:
                vs_bone.jiggle_pitch_constraint_min = math.radians(float(props['min_pitch']))
            if 'max_pitch' in props:
                vs_bone.jiggle_pitch_constraint_max = math.radians(float(props['max_pitch']))
            
            if 'yaw_friction' in props:
                vs_bone.jiggle_yaw_friction = float(props['yaw_friction'])
            if 'pitch_friction' in props:
                vs_bone.jiggle_pitch_friction = float(props['pitch_friction'])

            if 'base_mass' in props:
                vs_bone.jiggle_base_mass = int(float(props['base_mass']))
            if 'base_stiffness' in props:
                vs_bone.jiggle_base_stiffness = float(props['base_stiffness'])
            if 'base_damping' in props:
                vs_bone.jiggle_base_damping = float(props['base_damping'])

            if 'base_left_min' in props:
                vs_bone.jiggle_left_constraint_min = float(props['base_left_min'])
            if 'base_left_max' in props:
                vs_bone.jiggle_left_constraint_max = float(props['base_left_max'])
            if 'base_left_friction' in props:
                vs_bone.jiggle_left_friction = float(props['base_left_friction'])
            if 'base_up_min' in props:
                vs_bone.jiggle_up_constraint_min = float(props['base_up_min'])
            if 'base_up_max' in props:
                vs_bone.jiggle_up_constraint_max = float(props['base_up_max'])
            if 'base_up_friction' in props:
                vs_bone.jiggle_up_friction = float(props['base_up_friction'])
            if 'base_forward_min' in props:
                vs_bone.jiggle_forward_constraint_min = float(props['base_forward_min'])
            if 'base_forward_max' in props:
                vs_bone.jiggle_forward_constraint_max = float(props['base_forward_max'])
            if 'base_forward_friction' in props:
                vs_bone.jiggle_forward_friction = float(props['base_forward_friction'])
            
            if 'yaw_stiffness' in props:
                vs_bone.jiggle_yaw_stiffness = float(props['yaw_stiffness'])
            if 'yaw_damping' in props:
                vs_bone.jiggle_yaw_damping = float(props['yaw_damping'])
            if 'pitch_stiffness' in props:
                vs_bone.jiggle_pitch_stiffness = float(props['pitch_stiffness'])
            if 'pitch_damping' in props:
                vs_bone.jiggle_pitch_damping = float(props['pitch_damping'])
            if 'along_stiffness' in props:
                vs_bone.jiggle_along_stiffness = float(props['along_stiffness'])
            if 'along_damping' in props:
                vs_bone.jiggle_along_damping = float(props['along_damping'])

        return imported_count

class VALVEMODEL_OT_ExportJiggleBone(Operator, PrefabExport):
    bl_idname : str = "smd.write_jigglebone"
    bl_label : str = "Write Jigglebones"

    def draw(self, context : Context) -> None:
        if not self.to_clipboard:
            l : UILayout = self.layout
            l.prop(self, "prefab_index")

    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool(cls._has_jigglebones(context))

    @staticmethod
    def _has_jigglebones(context):
        ob : Object | None = get_armature(context.object)
        return ob and is_armature(ob) and any(b.vs.bone_is_jigglebone for b in ob.data.bones)

    def execute(self, context : Context) -> Set:
        arm = get_armature(context.object)
        jigglebones = [b for b in arm.data.bones if b.vs.bone_is_jigglebone]

        if not jigglebones:
            self.report({'WARNING'}, "No jigglebones found")
            return {'CANCELLED'}

        export_path = self.get_export_path(context)

        if export_path is None and not self.to_clipboard:
            return {'CANCELLED'}
        fmt = None

        if not self.to_clipboard:
            export_path, filename, ext = get_filepath(export_path)
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
            entries.append(f"// Jigglebones: {group_name}")
            entries.append("")
            for bone in group_bones:
                _datas = []
                _datas.append(f'$jigglebone "{get_bone_exportname(bone)}"')
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
            folder = KVNode(_class="Folder", name=sanitize_string(group_name))
            for bone in group_bones:
                flex_type = 2 if bone.vs.jiggle_flex_type not in ['FLEXIBLE', 'RIGID'] else (1 if bone.vs.jiggle_flex_type == 'FLEXIBLE' else 0)
                jiggle_length = bone.length if bone.vs.use_bone_length_for_jigglebone_length else bone.vs.jiggle_length
                jigglebone = KVNode(
                    _class="JiggleBone",
                    name=f"JiggleBone_{get_bone_exportname(bone)}",
                    jiggle_root_bone=get_bone_exportname(bone),
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
    KeepNonCopiedKeyframes: props.BoolProperty(
        name='Keep Non-Copied Keyframes',
        description='Preserve existing keyframes for bones that do not match between armatures',
        default=True
    )

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

            if not self.KeepNonCopiedKeyframes:
                actionslots = list(action.slots)
                for slot in actionslots:
                    action.slots.remove(slot)

            for pb in arm.pose.bones:
                pb.matrix_basis.identity()

            slot_ref = self._get_or_create_slot(action, self.ReferenceName)
            slot_prop = self._get_or_create_slot(action, self.ProportionName)

            if len(action.layers) == 0:
                layer = action.layers.new("BaseLayer")
            else:
                layer = action.layers[0]

            if len(layer.strips) == 0:
                strip = layer.strips.new(type='KEYFRAME')
            else:
                strip = layer.strips[0]

            matched_bones = self._get_matching_bones(currArm, arm)

            if self.KeepNonCopiedKeyframes:
                self._clear_keyframes_for_bones(action, layer, strip, slot_ref, matched_bones)

            arm.animation_data.action = action
            arm.animation_data.action_slot = slot_ref

            success = copy_target_armature_visualpose(currArm, arm, copy_type='ANGLES')
            if success:
                for pbone in arm.pose.bones:
                    if not self.KeepNonCopiedKeyframes or pbone.name in matched_bones:
                        pbone.keyframe_insert(data_path="location", group=pbone.name) # type: ignore
                        pbone.keyframe_insert(data_path="rotation_quaternion", group=pbone.name) # type: ignore
                        pbone.keyframe_insert(data_path="rotation_euler", group=pbone.name) # type: ignore

            context.view_layer.update()

            if self.KeepNonCopiedKeyframes:
                self._clear_keyframes_for_bones(action, layer, strip, slot_prop, matched_bones)

            arm.animation_data.action_slot = slot_prop
            success1 = copy_target_armature_visualpose(currArm, arm, copy_type='ANGLES')
            success2 = copy_target_armature_visualpose(currArm, arm, copy_type='ORIGIN')

            if success1 and success2:
                for pbone in arm.pose.bones:
                    if not self.KeepNonCopiedKeyframes or pbone.name in matched_bones:
                        pbone.keyframe_insert(data_path="location", group=pbone.name) # type: ignore
                        pbone.keyframe_insert(data_path="rotation_quaternion", group=pbone.name) # type: ignore
                        pbone.keyframe_insert(data_path="rotation_euler", group=pbone.name) # type: ignore

            arm.animation_data.action_slot = slot_ref
            context.view_layer.update()
                
        currArm.data.pose_position = last_pose_state
        return {'FINISHED'}

    def _get_or_create_slot(self, action: bpy.types.Action, slot_name: str) -> bpy.types.ActionSlot:
        """Gets existing slot or creates new one with given name"""
        for slot in action.slots:
            if slot.name_display == slot_name:
                return slot
        return action.slots.new(id_type='OBJECT', name=slot_name)

    def _clear_keyframes_for_bones(self, action: bpy.types.Action, layer: bpy.types.ActionLayer, 
                                   strip: bpy.types.ActionStrip, slot: bpy.types.ActionSlot, 
                                   bone_names: set[str]) -> None:
        """Removes keyframes only for specified bones in the given slot"""
        channelbag = strip.channelbag(slot)
        if not channelbag:
            return
        
        fcurves_to_remove = []
        for fcurve in channelbag.fcurves:
            for bone_name in bone_names:
                if f'pose.bones["{bone_name}"]' in fcurve.data_path:
                    fcurves_to_remove.append(fcurve)
                    break
        
        for fcurve in fcurves_to_remove:
            channelbag.fcurves.remove(fcurve)

    def _get_matching_bones(self, source_arm: bpy.types.Object, target_arm: bpy.types.Object) -> set[str]:
        """Returns set of bone names that exist in both armatures or match via export names"""
        matched_bones = set()
        source_bones = {get_bone_exportname(b, for_write=True): b.name for b in source_arm.data.bones}
        source_bones.update({b.name: b.name for b in source_arm.data.bones})
        
        for target_bone in target_arm.data.bones:
            target_export = get_bone_exportname(target_bone, for_write=True)
            if target_bone.name in source_bones or target_export in source_bones:
                matched_bones.add(target_bone.name)
        
        return matched_bones

class VALVEMODEL_OT_ExportConstraintProportion(Operator, PrefabExport):
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
        bones = get_selected_bones(armature, 'BONE', select_all=True, sort_type='TO_LAST')
        if not bones:
            self.report({'WARNING'}, "No bones found in armature")
            return {'CANCELLED'}

        filepath = self.get_export_path(context)

        with preserve_context_mode(armature, 'OBJECT'):
            compiled = self._export_constraints(armature, bones, filepath)

        export_path, filename, ext = get_filepath(filepath)

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
            bone_name = get_bone_exportname(bone, for_write=True)
            posebone = armature.pose.bones.get(bone.name)
            original_bone_name = sanitize_string(bone.name)
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
                parent_name = get_bone_exportname(bone.parent, for_write=True) if has_parent else None

                con_point = KVNode(
                    _class="AnimConstraintPoint",
                    name=f'Point_{bone_name}'
                )

                relativepos = get_relative_target_matrix(posebone, posebone.parent, mode='LOCATION') if has_parent else [0,0,0]
                relativeangle = get_relative_target_matrix(posebone, posebone.parent, mode='ROTATION', axis='YZX') if has_parent else [0,0,0]

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

class VALVEMODEL_OT_ExportHitBox(Operator, PrefabExport):
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

            bone_matrix_with_offset = get_bone_matrix(pose_bone, rest_space=True)
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
        active_armature = get_armature(context.object)

        if active_armature is None:
            self.report({'WARNING'}, "Active object is not an armature")
            return {'CANCELLED'}

        hitbox_data = []
        skipped_count = 0
        rotated_hitboxes = []

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
            has_rotation = (abs(obj.rotation_euler.x) > rotation_threshold or
                           abs(obj.rotation_euler.y) > rotation_threshold or
                           abs(obj.rotation_euler.z) > rotation_threshold)

            bounds = self.get_hitbox_bounds(obj)

            if bounds:
                currP = active_armature.data.bones.get(obj.parent_bone)

                if currP:
                    bone_name = get_bone_exportname(currP)
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

                    if has_rotation:
                        rotated_hitboxes.append(f"{obj.name} ({bone_name})")

        if len(hitbox_data) == 0:
            if skipped_count > 0:
                self.report({'WARNING'}, f"No valid hitboxes found. {skipped_count} hitbox(es) skipped (missing parent bone)")
            else:
                self.report({'WARNING'}, "No hitboxes found with vs.smd_hitbox = True")
            return {'CANCELLED'}

        bones_list = [hb['bone'] for hb in hitbox_data]
        sorted_bones = sort_bone_by_hierachy(bones_list)

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
            if rotated_hitboxes:
                print(f"WARNING: {len(rotated_hitboxes)} hitbox(es) have rotation (This is not used in Source 1 cube hitboxes):")
                for name in rotated_hitboxes:
                    print(f"  - {name}")
            print()

            if rotated_hitboxes:
                self.report({'WARNING'}, f"Exported {hitbox_count} hitbox(es) to clipboard ({len(rotated_hitboxes)} with rotation)")
            else:
                self.report({'INFO'}, f"Exported {hitbox_count} hitbox(es) to clipboard")
        else:
            filepath = self.get_export_path(context)
            if not filepath:
                self.report({'ERROR'}, "No file path specified")
                return {'CANCELLED'}

            export_path, filename, ext = get_filepath(filepath)

            if not filename or not ext:
                self.report({'ERROR'}, "Invalid export path: must include filename and extension")
                return {'CANCELLED'}

            ext_lower = ext.lower()
            if ext_lower not in {'.qc', '.qci'}:
                self.report({'ERROR'}, f"Unsupported file extension '{ext_lower}'. Use .qc or .qci")
                return {'CANCELLED'}

            warnings = []
            if rotated_hitboxes:
                for name in rotated_hitboxes:
                    warnings.append(f"  - {name} have rotation (This is not used in Source 1 cube hitboxes)")

            if not self.write_output(compiled, export_path, warnings=warnings):
                return {'CANCELLED'}

        return {'FINISHED'}

class VALVEMODEL_OT_ImportHitBox(Operator, PrefabImport):
    bl_idname: str = "smd.import_hitboxes"
    bl_label: str = "Import Source Hitboxes"
    bl_description: str = "Import Source Engine hitbox format from QC/QCI file"
    bl_options: Set = {'REGISTER', 'UNDO'}
    
    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default='*.qc;*.qci', options={'HIDDEN'})
    
    @classmethod
    def poll(cls, context: Context) -> bool:
        return is_armature(context.object)
    
    def invoke(self, context: Context, event: Event) -> set:
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context: Context) -> set:
        armature = get_armature(context.object)
        
        if not armature:
            self.report({'WARNING'}, "Active object is not an armature")
            return {'CANCELLED'}
        
        
        content = self.simple_read_file(filepath=self.filepath)
        
        if not content:
            self.report({'ERROR'}, "Failed to read file")
            return {'CANCELLED'}

        created_count, skipped_count, skipped_bones = import_hitboxes_from_content(content, armature, context)
        
        if created_count > 0:
            if skipped_count > 0:
                self.report({'WARNING'}, f"Imported {created_count} hitbox(es), skipped {skipped_count}")
            else:
                self.report({'INFO'}, f"Imported {created_count} hitbox(es)")
        else:
            self.report({'WARNING'}, "No hitboxes were imported")
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
        
        fixed_count = reevaluate_bone_parented_empty_matrix(
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
        armature = get_armature()
        
        if not armature or len(armature.data.bones) == 0:
            self.report({'WARNING'}, 'Armature has no bones')
            return {'CANCELLED'}
        
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context : Context):
        layout = self.layout
        armature = get_armature()
        
        if armature.mode == 'POSE' and context.selected_pose_bones:
            layout.label(text=f"{len(context.selected_pose_bones)} bone(s) selected")
        else:
            layout.prop_search(self, "parent_bone", armature.data, "bones", text="Parent Bone")
        
        layout.prop(self, "hitbox_group")
    
    def execute(self, context : Context) -> set:
        armature = get_armature()
        
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

class VALVEMODEL_OT_CopyJiggleBoneProperties(Operator):
    bl_idname: str = "smd.copy_jiggleboneproperties"
    bl_label: str = "Copy Jigglebone Properties"
    bl_options: Set = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context : Context) -> bool:
        if not is_armature(context.object) or context.mode != 'POSE':
            return False
        if context.object.data.bones.active is None:
            return False
        return True
    
    def execute(self, context : Context) -> set:
        armature = get_armature(context.object)
        active_bone = armature.data.bones.active
        selected_bones = get_selected_bones(armature, bone_type='BONE', exclude_active=True)
        
        if not selected_bones:
            self.report({'WARNING'}, "No other bones selected")
            return {'CANCELLED'}
        
        source_vs = active_bone.vs
        
        if not source_vs.bone_is_jigglebone:
            self.report({'WARNING'}, "Active bone is not a jigglebone")
            return {'CANCELLED'}
        
        jigglebone_props = [
            'bone_is_jigglebone',
            'jiggle_flex_type',
            'jiggle_base_type',
            'use_bone_length_for_jigglebone_length',
            'jiggle_length',
            'jiggle_tip_mass',
            'jiggle_yaw_stiffness',
            'jiggle_yaw_damping',
            'jiggle_pitch_stiffness',
            'jiggle_pitch_damping',
            'jiggle_allow_length_flex',
            'jiggle_along_stiffness',
            'jiggle_along_damping',
            'jiggle_has_angle_constraint',
            'jiggle_has_yaw_constraint',
            'jiggle_has_pitch_constraint',
            'jiggle_angle_constraint',
            'jiggle_yaw_constraint_min',
            'jiggle_yaw_constraint_max',
            'jiggle_yaw_friction',
            'jiggle_pitch_constraint_min',
            'jiggle_pitch_constraint_max',
            'jiggle_pitch_friction',
            'jiggle_base_stiffness',
            'jiggle_base_damping',
            'jiggle_base_mass',
            'jiggle_has_left_constraint',
            'jiggle_has_up_constraint',
            'jiggle_has_forward_constraint',
            'jiggle_left_constraint_min',
            'jiggle_left_constraint_max',
            'jiggle_left_friction',
            'jiggle_up_constraint_min',
            'jiggle_up_constraint_max',
            'jiggle_up_friction',
            'jiggle_forward_constraint_min',
            'jiggle_forward_constraint_max',
            'jiggle_forward_friction',
            'jiggle_impact_speed',
            'jiggle_impact_angle',
            'jiggle_damping_rate',
            'jiggle_frequency',
            'jiggle_amplitude'
        ]
        
        for bone in selected_bones:
            target_vs = bone.vs
            for prop in jigglebone_props:
                try:
                    setattr(target_vs, prop, getattr(source_vs, prop))
                except AttributeError:
                    continue
        
        self.report({'INFO'}, f"Copied jigglebone properties to {len(selected_bones)} bone(s)")
        return {'FINISHED'}