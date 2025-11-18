import bpy
from bpy.props import IntProperty
from typing import Any

from bpy.types import (
    Panel, UIList, Operator, UILayout, Object, Context,
    VertexGroup, LoopColors, MeshLoopColorLayer
)

from .. import format_version
from .common import KITSUNE_PT_CustomToolPanel

from ..core.boneutils import (
    get_bone_exportname
)

from ..core.armatureutils import (
    get_armature, get_armature_meshes
)

from ..core.commonutils import (
    is_armature, is_mesh, is_empty, is_curve, get_unparented_attachments,
    get_unparented_hitboxes, get_bugged_hitboxes, get_bugged_attachments,
    get_all_materials, has_materials, draw_wrapped_texts, draw_toggleable_layout,
    draw_title_box_layout, draw_listing_layout
)

from ..core.meshutils import (
    get_flexcontrollers
)

from ..utils import (
    get_id, vertex_maps, vertex_float_maps, hasShapes, countShapes,
    State, ExportFormat, Compiler, MakeObjectIcon, hasFlexControllerSource,
    hasCurves
)

from ..flex import (
    AddCorrectiveShapeDrivers, RenameShapesToMatchCorrectiveDrivers,
    DmxWriteFlexControllers
)

from .valvemodel import (
    VALVEMODEL_OT_FixAttachment, VALVEMODEL_OT_FixHitBox
)

SMD_OT_CreateVertexMap_idname : str = "smd.vertex_map_create_"
SMD_OT_SelectVertexMap_idname : str = "smd.vertex_map_select_"
SMD_OT_RemoveVertexMap_idname : str = "smd.vertex_map_remove_"

for map_name in vertex_maps:

    class SelectVertexColorMap(Operator):
        bl_idname : str = SMD_OT_SelectVertexMap_idname + map_name
        bl_label : str = get_id("vertmap_select")
        bl_description : str = get_id("vertmap_select")
        bl_options : set = {'INTERNAL'}
        vertex_map : str = map_name
    
        @classmethod
        def poll(cls, context : Context) -> bool:
            if not is_mesh(context.active_object):
                return False
            vc_loop : MeshLoopColorLayer | None = context.active_object.data.vertex_colors.get(cls.vertex_map)
            return bool(vc_loop and not vc_loop.active)

        def execute(self, context : Context) -> set:
            context.active_object.data.vertex_colors[self.vertex_map].active = True
            return {'FINISHED'}

    class CreateVertexColorMap(Operator):
        bl_idname : str = SMD_OT_CreateVertexMap_idname + map_name
        bl_label : str = get_id("vertmap_create")
        bl_description : str = get_id("vertmap_create")
        bl_options : set = {'INTERNAL'}
        vertex_map : str = map_name
    
        @classmethod
        def poll(cls, context : Context) -> bool:
            return bool(is_mesh(context.active_object) and cls.vertex_map not in context.active_object.data.vertex_colors)

        def execute(self, context : Context) -> set:
            vc : MeshLoopColorLayer = context.active_object.data.vertex_colors.new(name=self.vertex_map)
            vc.data.foreach_set("color", [1.0] * len(vc.data) * 4)
            bpy.context.view_layer.update()
            SelectVertexColorMap().execute(context)
            return {'FINISHED'}

    class RemoveVertexColorMap(Operator):
        bl_idname : str = SMD_OT_RemoveVertexMap_idname + map_name
        bl_label : str = get_id("vertmap_remove")
        bl_description : str = get_id("vertmap_remove")
        bl_options : set = {'INTERNAL'}
        vertex_map : str = map_name
    
        @classmethod
        def poll(cls, context : Context) -> bool:
            return bool(is_mesh(context.active_object) and cls.vertex_map in context.active_object.data.vertex_colors)

        def execute(self, context : Context) -> set:
            vcs : LoopColors  = context.active_object.data.vertex_colors
            vcs.remove(vcs[self.vertex_map])
            return {'FINISHED'}

    bpy.utils.register_class(SelectVertexColorMap)
    bpy.utils.register_class(CreateVertexColorMap)
    bpy.utils.register_class(RemoveVertexColorMap)

SMD_OT_CreateVertexFloatMap_idname : str = "smd.vertex_float_map_create_"
SMD_OT_SelectVertexFloatMap_idname : str = "smd.vertex_float_map_select_"
SMD_OT_RemoveVertexFloatMap_idname : str = "smd.vertex_float_map_remove_"

for map_name in vertex_float_maps:

    class SelectVertexFloatMap(Operator):
        bl_idname : str = SMD_OT_SelectVertexFloatMap_idname + map_name
        bl_label : str = get_id("vertmap_select")
        bl_description : str = get_id("vertmap_select")
        bl_options : set = {'INTERNAL'}
        vertex_map : str = map_name

        @classmethod
        def poll(cls, context : Context) -> bool:
            vg_loop = context.object.vertex_groups.get(cls.vertex_map)
            return bool(vg_loop and not context.active_object.vertex_groups.active == vg_loop)

        def execute(self, context : Context) -> set:
            context.active_object.vertex_groups.active_index = context.active_object.vertex_groups[self.vertex_map].index
            return {'FINISHED'}

    class CreateVertexFloatMap(Operator):
        bl_idname : str = SMD_OT_CreateVertexFloatMap_idname + map_name
        bl_label : str = get_id("vertmap_create")
        bl_description : str = get_id("vertmap_create")
        bl_options : set = {'INTERNAL'}
        vertex_map : str = map_name

        @classmethod
        def poll(cls, context : Context) -> bool:
            return bool(context.object and context.object.type == 'MESH' and cls.vertex_map not in context.object.vertex_groups)

        def execute(self, context : Context) -> set:
            vc : VertexGroup = context.active_object.vertex_groups.new(name=self.vertex_map)

            found : bool = False
            for remap in context.object.vs.vertex_map_remaps:
                if remap.group == map_name:
                    found = True
                    break

            if not found:
                remap = context.object.vs.vertex_map_remaps.add()
                remap.group : str = map_name
                remap.min : float = 0.0
                remap.max : float = 1.0

            SelectVertexFloatMap().execute(context)
            return {'FINISHED'}

    class RemoveVertexFloatMap(Operator):
        bl_idname : str = SMD_OT_RemoveVertexFloatMap_idname + map_name
        bl_label : str = get_id("vertmap_remove")
        bl_description : str = get_id("vertmap_remove")
        bl_options : set = {'INTERNAL'}
        vertex_map : str = map_name

        @classmethod
        def poll(cls, context) -> bool:
            return bool(context.object and context.object.type == 'MESH' and cls.vertex_map in context.active_object.vertex_groups)

        def execute(self, context : Context) -> set:
            vgs = context.active_object.vertex_groups
            vgs.remove(vgs[self.vertex_map])
            return {'FINISHED'}

    bpy.utils.register_class(SelectVertexFloatMap)
    bpy.utils.register_class(CreateVertexFloatMap)
    bpy.utils.register_class(RemoveVertexFloatMap)

class ValidationChecker:
    @staticmethod
    def is_valid_name(name: str) -> bool:
        for char in name:
            if not (char.isascii() and (char.isalnum() or char in (' ', '_', '.'))):
                return False
        return True

    @staticmethod
    def get_invalid_names(armature_obj) -> dict:
        invalid_names = {
            'armature': [],
            'bones': [],
            'meshes': [],
            'materials': [],
            'shapekeys': []
        }
        
        armature = None
        if not is_armature(armature_obj):
            armature = get_armature(armature_obj)
        else:
            armature = armature_obj
            
        if armature is None: 
            return invalid_names
        
        for bone in armature.data.bones:
            if not ValidationChecker.is_valid_name(bone.name):
                invalid_names['bones'].append(bone.name)
                
        if not ValidationChecker.is_valid_name(armature.name):
            invalid_names['armature'].append(armature.name)
            
        meshes = get_armature_meshes(armature)
        for mesh in meshes:
            if mesh.vs.export is False: continue
            
            if not ValidationChecker.is_valid_name(mesh.name):
                invalid_names['meshes'].append(mesh.name)
            
            for mat in mesh.data.materials:
                if mat.vs.do_not_export_faces: continue
                
                if mat and not ValidationChecker.is_valid_name(mat.name):
                    if (mat.name, mesh.name) not in invalid_names['materials']:
                        invalid_names['materials'].append((mat.name, mesh.name))
            
            if mesh.data.shape_keys:
                for key in mesh.data.shape_keys.key_blocks:
                    if mesh.vs.flex_controller_mode == 'STRICT':
                        if key.name not in (fc[0] for fc in get_flexcontrollers(mesh)):
                            continue
                    
                    if not ValidationChecker.is_valid_name(key.name):
                        invalid_names['shapekeys'].append((key.name, mesh.name))
        
        return invalid_names

    @staticmethod
    def count_warnings(context: Context) -> int:
        count = 0
        
        invalid_names = ValidationChecker.get_invalid_names(context.object)
        count += sum(1 for category in invalid_names.values() if category)
        
        if get_unparented_hitboxes():
            count += 1
        
        if get_unparented_attachments():
            count += 1
        
        if get_bugged_hitboxes():
            count += 1
        
        if get_bugged_attachments():
            count += 1
        
        return count

class WarningRenderer:
    INVALID_CHAR_MESSAGE = '\n\ncontain invalid characters! Only alphanumeric, spaces, and underscores are allowed for Source Engine.'
    
    @staticmethod
    def draw_invalid_names(layout: UILayout, invalid_names: dict) -> int:
        count = 0
        
        if invalid_names['armature']:
            draw_wrapped_texts(layout, f'Armature Name: {", ".join(invalid_names["armature"])}{WarningRenderer.INVALID_CHAR_MESSAGE}', alert=True)
            count += 1
        
        if invalid_names['bones']:
            bone_list = "\n".join(invalid_names["bones"])
            draw_wrapped_texts(layout, f'Bone(s):\n\n{bone_list}{WarningRenderer.INVALID_CHAR_MESSAGE}', alert=True)
            count += 1

        if invalid_names['meshes']:
            mesh_list = "\n".join(invalid_names["meshes"])
            draw_wrapped_texts(layout, f'Mesh Object(s):\n\n{mesh_list}{WarningRenderer.INVALID_CHAR_MESSAGE}', alert=True)
            count += 1

        if invalid_names['materials']:
            material_list = "\n".join(f"{mat} in '{mesh}'" for mat, mesh in invalid_names["materials"])
            draw_wrapped_texts(layout, f'Material(s):\n\n{material_list}{WarningRenderer.INVALID_CHAR_MESSAGE}', alert=True)
            count += 1

        if invalid_names['shapekeys']:
            shapekey_list = "\n".join(f"{key} in '{mesh}'" for key, mesh in invalid_names["shapekeys"])
            draw_wrapped_texts(layout, f'Shapekey(s):\n\n{shapekey_list}{WarningRenderer.INVALID_CHAR_MESSAGE}', alert=True)
            count += 1
        
        return count
    
    @staticmethod
    def draw_unparented_items(layout: UILayout) -> int:
        count = 0
        
        unparented_hitboxes = get_unparented_hitboxes()
        if unparented_hitboxes:
            draw_wrapped_texts(layout, f'Hitbox(es): {", ".join(unparented_hitboxes)} must be parented to a bone!', alert=True)
            count += 1
        
        unparented_attachments = get_unparented_attachments()
        if unparented_attachments:
            draw_wrapped_texts(layout, f'Attachment(s): {", ".join(unparented_attachments)} must be parented to a bone!', alert=True)
            count += 1
        
        return count
    
    @staticmethod
    def draw_bugged_items(layout: UILayout) -> int:
        count = 0
        
        bugged_hitboxes = get_bugged_hitboxes()
        if bugged_hitboxes:
            col = layout.column(align=True)
            col.operator(VALVEMODEL_OT_FixHitBox.bl_idname)
            draw_wrapped_texts(col, f'Hitbox(es): {", ".join(bugged_hitboxes)} have incorrect matrix (world-space instead of bone-relative). Use Fix Hitboxes operator!', alert=True)
            count += 1
        
        bugged_attachments = get_bugged_attachments()
        if bugged_attachments:
            col = layout.column(align=True)
            col.operator(VALVEMODEL_OT_FixAttachment.bl_idname)
            draw_wrapped_texts(col, f'Attachment(s): {", ".join(bugged_attachments)} have incorrect matrix (world-space instead of bone-relative). Use Fix Attachments operator!', alert=True)
            count += 1
        
        return count

class SMD_PT_ContextObject(KITSUNE_PT_CustomToolPanel, Panel):
    """Displays the Main Panel for Object Properties"""
    bl_label : str = get_id("panel_context_properties")
    
    def draw(self, context : Context) -> None:
        l : UILayout = self.layout

        col = l.column(align=True)
        
        addonver, addondevstate = format_version()
        addoninfo_section : UILayout = draw_toggleable_layout(col, context.scene.vs, 'show_addoninfo', show_text=f'KitsuneSourceTool {addonver}_{addondevstate}', hide_text='', toggle_scale_y=0.8)
        if addoninfo_section is not None:
            draw_wrapped_texts(addoninfo_section, get_id('introduction_message'), boxed=False)
        
        prophelpsection : UILayout = draw_toggleable_layout(col, context.scene.vs, 'show_properties_help', f'Show Tips', '', toggle_scale_y=0.7)
        if prophelpsection is not None:
            help_text = [
                '- Selecting multiple objects or bones and changing a property of either will be copied over to other selected of the same type.',
                '- Exporting bones with non alphanumeric character will be sanitize and can lead to issues with bone mixup.',
            ]
            draw_wrapped_texts(prophelpsection, text=help_text[0], max_chars=40, boxed=False)
            draw_wrapped_texts(prophelpsection, text=help_text[1], max_chars=40, alert=True, boxed=False)

        warning_count = ValidationChecker.count_warnings(context)
        has_warnings = warning_count > 0
        
        section_title = 'Object(s) Validation' if warning_count == 0 else f'Object(s) Validation ({warning_count})'
        warningsection : UILayout = draw_toggleable_layout(col, context.scene.vs, 'show_objectwarnings', section_title, '', alert=has_warnings)
        
        if warningsection is not None:
            self.draw_warning_checks(context, warningsection)
            
        sections = [
            ('show_smdobject', get_id("panel_context_object"), 'OBJECT_DATA', self.draw_objectproperties, None),
            ('show_smdbone', get_id("panel_context_bone"), 'BONE_DATA', self.draw_boneproperties, 'ARMATURE'),
            ('show_smdmesh', get_id("panel_context_mesh"), 'MESH_DATA', self.draw_meshproperties, 'MESH'),
            ('show_smdmaterials', get_id("panel_context_material"), 'MATERIAL_DATA', self.draw_materialproperties, ['MESH', 'ARMATURE']),
            ('show_smdempty', get_id('panel_context_empty'), 'EMPTY_DATA', self.draw_emptyproperties, 'EMPTY'),
            ('show_smdcurve', get_id("exportables_curve_props"), 'CURVE_DATA', self.draw_curveproperties, 'NONE'),
        ]
        
        col.separator()
        
        for prop, label, icon, draw_func, object_type in sections:
            
            is_sametype = False
            if object_type is None and context.object: is_sametype = True
            elif context.object and (context.object.type == object_type or context.object.type in object_type): is_sametype = True
            
            section = draw_toggleable_layout(
                col, context.scene.vs, prop, 
                show_text=label, icon=icon, 
                enabled=is_sametype,
                toggle_scale_y=0.9,
                icon_outside=True
            )
            if section:
                draw_func(context, section)
            
    def draw_warning_checks(self, context: Context, layout: UILayout) -> int:
        num_warnings = 0
        
        invalid_names = ValidationChecker.get_invalid_names(context.object)
        num_warnings += WarningRenderer.draw_invalid_names(layout, invalid_names)
        
        num_warnings += WarningRenderer.draw_unparented_items(layout)
        num_warnings += WarningRenderer.draw_bugged_items(layout)
                
        if num_warnings == 0:
            draw_wrapped_texts(layout, f'No Errors found on active object', boxed=False)
            
        return num_warnings
    
    def draw_objectproperties(self, context : Context, layout : UILayout) -> None:
        l : UILayout = layout
        ob : Object | None = context.object
        
        if not ob:
            draw_wrapped_texts(l, get_id("panel_select_object"), max_chars=40, icon='HELP')
            return
        
        object_box = draw_title_box_layout(l, text=f'Active Object: {ob.name}', icon='OBJECT_DATA')
        
        col = object_box.column(align=True)
        col.scale_y = 1.2
        col.prop(ob.vs, 'export', text='Scene Export')
        
        if is_armature(ob):   
            armaturebox = draw_title_box_layout(l, text='Armature Settings', icon='ARMATURE_DATA')
            
            col = armaturebox.column(align=True)
            col.prop(ob.data.vs, "ignore_bone_exportnames")
            
            rootitem, subitems = draw_listing_layout(col)
            rootitem.label(text='Direction Naming:')
            row = subitems.row()
            row.prop(ob.data.vs, 'bone_direction_naming_left', text='Left')
            row.prop(ob.data.vs, 'bone_direction_naming_right', text='Right')
            
            armaturebox.prop(ob.data.vs, 'bone_name_startcount', slider=True)
        
    def draw_meshproperties(self, context : Context, layout : UILayout) -> None:
        l : UILayout = layout
        ob : Object | None = context.object
        
        if is_mesh(ob): pass
        else:
            draw_wrapped_texts(l,get_id("panel_select_mesh"),max_chars=40 , icon='HELP')
            return
        
        sections = [
            ('show_flex', 'Show Shapekey Conifg', 'SHAPEKEY_DATA', self._draw_shapekey_config),
            ('show_vertexmap', 'Show VertexMap Conifg', 'GROUP_VERTEX', self._draw_vertexmap_config),
            ('show_floatmaps', 'Show FloatMaps Conifg', 'MOD_CLOTH', self._draw_floatmaps_config),
        ]
        
        col = l.column()
        
        for prop, label, icon, draw_func in sections:
            section = draw_toggleable_layout(
                col, context.scene.vs, prop, 
                show_text=label, icon=icon,
                boxed=False
            )
            if section:
                draw_func(context, section)
            
    def _draw_shapekey_config(self,context : Context, layout : UILayout):
        bx : UILayout = layout
        ob = context.object
        
        if not hasShapes(ob):
            draw_wrapped_texts(bx,'Mesh has no Shapekeys!',alert=True,icon='ERROR')
        
        num_shapes, num_correctives = countShapes(ob)
        
        col = bx.column()
        col.prop(ob.data.vs, "bake_shapekey_as_basis_normals")
        col.prop(ob.data.vs, "normalize_shapekeys")
        
        col.separator()
        col = bx.column()
        col.scale_y = 1.2
        row = col.row(align=True)
        row.prop(ob.vs,"flex_controller_mode",expand=True)

        col = bx.column()
        
        def insertCorrectiveUi(parent):
            col = parent.column(align=True)
            col.operator(AddCorrectiveShapeDrivers.bl_idname, icon='DRIVER',text=get_id("gen_drivers",True))
            col.operator(RenameShapesToMatchCorrectiveDrivers.bl_idname, icon='SYNTAX_OFF',text=get_id("apply_drivers",True))
        
        if ob.vs.flex_controller_mode == 'ADVANCED':
            controller_source = col.row()
            controller_source.alert = hasFlexControllerSource(ob.vs.flex_controller_source) == False
            controller_source.prop(ob.vs,"flex_controller_source",text=get_id("exportables_flex_src"),icon = 'TEXT' if ob.vs.flex_controller_source in bpy.data.texts else 'NONE')
            
            row = col.row(align=True)
            row.operator(DmxWriteFlexControllers.bl_idname,icon='TEXT',text=get_id("exportables_flex_generate", True))
            row.operator("wm.url_open",text=get_id("exportables_flex_help", True),icon='HELP').url = "http://developer.valvesoftware.com/wiki/Blender_SMD_Tools_Help#Flex_properties"
            
            insertCorrectiveUi(col)
            
            col = bx.column()
            subbx = col.box()
            
            subbx.label(text=get_id("exportables_flex_split"))
            sharpness_col = subbx.column(align=True)
            
            r = sharpness_col.split(factor=0.33,align=True)
            r.label(text=ob.data.name + ":",icon=MakeObjectIcon(ob,suffix='_DATA'),translate=False) # type: ignore
            r2 = r.split(factor=0.7,align=True)
            
            if ob.data.vs.flex_stereo_mode == 'VGROUP':
                r2.alert = ob.vertex_groups.get(ob.data.vs.flex_stereo_vg) is None
                r2.prop_search(ob.data.vs,"flex_stereo_vg",ob,"vertex_groups",text="")
            else:
                r2.prop(ob.data.vs,"flex_stereo_sharpness",text="Sharpness")
                
            r2.prop(ob.data.vs,"flex_stereo_mode",text="")
            
        elif ob.vs.flex_controller_mode == 'STRICT':
            col = bx.column()
            col.template_list("DME_UL_FlexControllers","",ob.vs,"dme_flexcontrollers", ob.vs,"dme_flexcontrollers_index",rows=3,)

            row = col.row(align=True)
            row.operator("dme.add_flexcontroller", icon='ADD')
            
            if num_shapes == 0:
                col.separator()
                draw_wrapped_texts(col,'Empty List will export the object without shapekeys',icon='HELP', boxed=False)
            
        else:
            insertCorrectiveUi(col)

        
        col.separator()
        row = col.row()
        row.alignment = 'CENTER'
        row.label(icon='SHAPEKEY_DATA',text = get_id("exportables_flex_count", True).format(num_shapes))
        
        if ob.vs.flex_controller_mode != 'STRICT':
            row.label(icon='SHAPEKEY_DATA',text = get_id("exportables_flex_count_corrective", True).format(num_correctives))
        
    def _draw_vertexmap_config(self, context : Context, layout : UILayout):
        bx : UILayout = layout
        col = bx.column(align=True)
        
        if State.exportFormat != ExportFormat.DMX:
            draw_wrapped_texts(bx,'Only Applicable in DMX!',alert=True,icon='ERROR')
        
        for map_name in vertex_maps:
            r = col.row()
            r.label(text=get_id(map_name),icon='GROUP_VCOL')
            
            add_remove = r.row(align=True)
            add_remove.operator(SMD_OT_CreateVertexMap_idname + map_name,icon='ADD',text="")
            add_remove.operator(SMD_OT_RemoveVertexMap_idname + map_name,icon='REMOVE',text="")
            add_remove.operator(SMD_OT_SelectVertexMap_idname + map_name,text="Activate")
     
    def _draw_floatmaps_config(self, context : Context, layout :UILayout):
        ob = context.active_object
        col = layout.column()
        
        col.operator("wm.url_open", text=get_id("help", True), icon='INTERNET').url = "http://developer.valvesoftware.com/wiki/DMX/Source_2_Vertex_attributes"
    
        col = layout.column(align=False)
        col.scale_y = 1.1
        if State.compiler != Compiler.MODELDOC or State.exportFormat != ExportFormat.DMX:
            messages = 'Only Applicable in Source 2 and DMX'
            draw_wrapped_texts(col, messages, 32, alert=True, icon='ERROR')
            col.active = False

        col = col.column(align=False)
        col.scale_y = 1.15
        for map_name in vertex_float_maps:
            split1 = col.split(align=True, factor=0.55)
            r = split1.row(align=True)
            r.operator(SMD_OT_SelectVertexFloatMap_idname + map_name, text=map_name.replace("cloth_", "").replace("_", " ").title(), icon='GROUP_VERTEX')
            r.operator(SMD_OT_CreateVertexFloatMap_idname + map_name, icon='ADD', text="")
            r.operator(SMD_OT_RemoveVertexFloatMap_idname + map_name, icon='REMOVE', text="")
            
            r = split1.row(align=True)
            found = False
            for group in ob.vs.vertex_map_remaps:
                if group.group == map_name:
                    found = True
                    r.prop(group, "min")
                    r.prop(group, "max")
                    break

            if not found:
                r.operator("smd.add_vertex_map_remap").map_name = map_name
    
    def draw_boneproperties(self, context : Context, layout : UILayout) -> None:
        l : UILayout = layout
        ob : Object | None = context.object
        
        if not is_armature(ob):
            draw_wrapped_texts(l, get_id("panel_select_armature"), max_chars=40, icon='HELP')
            return
        
        try:
            bone : bpy.types.Bone | None = ob.data.bones.active if context.mode != 'EDIT_ARMATURE' else ob.data.bones.get(ob.data.edit_bones.active.name)
        except:
            bone = None
        
        if bone is None:
            draw_wrapped_texts(l, 'Select a bone to edit properties', max_chars=40, icon='INFO')
            return
        
        if context.mode == 'EDIT_ARMATURE':
            draw_wrapped_texts(l, 'Bone properties are not editable in Edit Mode', max_chars=36, alert=True, icon='ERROR')
            return
        
        title = draw_title_box_layout(l, text=f'Active Bone: {bone.name}', icon='BONE_DATA')

        col = title.column(align=True)
        rootitem, subitems = draw_listing_layout(col)
        
        rootitem.prop(bone.vs, 'export_name', placeholder=get_bone_exportname(bone))
        subitems.label(text=f'Export Name: {get_bone_exportname(bone)}')
        
        title.separator(type='LINE')
        
        split = title.split(factor=0.5)
        
        col_left = split.column(align=True)
        col_left.label(text='Location Offset:', icon='ORIENTATION_LOCAL')
        col_left.prop(bone.vs, 'ignore_location_offset', text='Ignore', toggle=True)
        
        sub = col_left.column(align=True)
        sub.active = not bone.vs.ignore_location_offset
        sub.prop(bone.vs, 'export_location_offset_x')
        sub.prop(bone.vs, 'export_location_offset_y')
        sub.prop(bone.vs, 'export_location_offset_z')
        
        col_right = split.column(align=True)
        col_right.label(text='Rotation Offset:', icon='ORIENTATION_GIMBAL')
        col_right.prop(bone.vs, 'ignore_rotation_offset', text='Ignore', toggle=True)
        
        sub = col_right.column(align=True)
        sub.active = not bone.vs.ignore_rotation_offset
        sub.prop(bone.vs, 'export_rotation_offset_x')
        sub.prop(bone.vs, 'export_rotation_offset_y')
        sub.prop(bone.vs, 'export_rotation_offset_z')
        
        draw_wrapped_texts(
            title,
            'Bones rotate on export in Z→Y→X order (translation remains X→Y→Z). Use "normal" in edit mode to check. Z+90° from Y-forward → X-forward.',
            max_chars=36,
            icon='INFO')
    
    def draw_materialproperties(self, context : Context, layout : UILayout) -> None:
        l : UILayout = layout
        ob : Object | None = context.object
        if ob is None: return
        
        allmats = get_all_materials(ob)
        allmaterials_section = draw_toggleable_layout(l,context.scene.vs,'show_materials',f'Show All Mesh Materials: {len(allmats)}','',alert=not bool(allmats), toggle_scale_y=0.7)
        if allmaterials_section is not None:
            for mat in allmats:
                subbx = allmaterials_section.box()
                col = subbx.column(align=False)
                row = col.row(align=True)
                
                if mat.preview is not None:
                    row.label(text=mat.name, icon_value=mat.preview.icon_id)
                else:
                    row.label(text=mat.name, icon='MATERIAL')
                    
                row.prop(mat.vs, 'do_not_export_faces',text='Do Not Export',toggle=True)
                row.prop(mat.vs, 'do_not_export_faces_vgroup', text='Vertex Filtering',toggle=True)
                
                if not mat.vs.do_not_export_faces:
                    col = subbx.column(align=True)
                    col.scale_y = 1.05
                    
                    if State.exportFormat == ExportFormat.DMX:
                        col.prop(mat.vs,'override_dmx_export_path',icon='FOLDER_REDIRECT', placeholder=context.scene.vs.material_path, text='')
                        
                    if mat.vs.do_not_export_faces_vgroup:
                        col.prop(mat.vs,'non_exportable_vgroup',icon='GROUP_VERTEX')
        
        if is_mesh(ob) and has_materials(ob): pass
        else:
            draw_wrapped_texts(l,get_id("panel_select_mesh_mat"),max_chars=40 , icon='HELP')
            return
        
        currMat = ob.active_material
        l.box().label(text=f'Active Material: ({currMat.name})')
        
        col = l.column(align=True)
        col.prop(currMat.vs, 'do_not_export_faces')
        col.prop(currMat.vs, 'do_not_export_faces_vgroup')
        
        if not currMat.vs.do_not_export_faces:
            col = l.column()
            
            if State.exportFormat == ExportFormat.DMX:
                col.prop(currMat.vs, 'override_dmx_export_path', placeholder=context.scene.vs.material_path)
                
            col.prop(currMat.vs, 'non_exportable_vgroup')   

    def draw_emptyproperties(self, context : Context, layout : UILayout) -> None:
        L : UILayout = layout
        ob : Object | None = context.object
        
        if is_empty(ob): pass
        else:
            draw_wrapped_texts(L,get_id("panel_select_empty"),max_chars=40 , icon='HELP')
            return
        
        col : UILayout = L.column()
        
        col.prop(ob.vs, 'dmx_attachment', toggle=False)
        col.prop(ob.vs, 'smd_hitbox', toggle=False)
        
        if ob.vs.smd_hitbox:
            col.prop(ob.vs, 'smd_hitbox_group', text='Hitbox Group')
        
        if ob.vs.dmx_attachment and ob.children:
            col.alert = True
            col.box().label(text="Attachment cannot be a parent",icon='WARNING_LARGE')

    def draw_curveproperties(self, context : Context, layout :UILayout) -> None:
        l : UILayout = layout
        
        if is_curve(context.object) and hasCurves(context.object): pass
        else:
            draw_wrapped_texts(l,get_id("panel_select_curve"),max_chars=40 , icon='HELP')
            return
        
        done = set()
        
        row = l.split(factor=0.33)
        row.label(text=context.object.data.name + ":",icon=MakeObjectIcon(context.object,suffix='_DATA'),translate=False) # type: ignore
        row.prop(context.object.data.vs,"faces",text="")
        done.add(context.object.data)
       
class DME_UL_FlexControllers(UIList):
    def draw_item(self, context: Context, layout: UILayout, data: Any | None, item: Any | None, icon: int | None, active_data: Any, active_property: str | None, index: int | None, flt_flag: int | None) -> None:
        ob : Object | None = context.object
        
        split = layout.split(factor=0.6)
        row : UILayout = split.row(align=True)
        row.prop_search(item, "shapekey", ob.data.shape_keys, "key_blocks", text="")
        row : UILayout = split.row(align=True)
        row.prop(item, "eyelid", toggle=True)
        row.prop(item, "stereo", toggle=True)
        
        op = row.operator("dme.remove_flexcontroller", text="", icon='X')
        op.index = index
            
class DME_OT_AddFlexController(Operator):
    bl_idname : str = "dme.add_flexcontroller"
    bl_label : str = "Add Flex Controller"
    bl_options : set = {'INTERNAL', 'UNDO'}  

    def execute(self, context : Context) -> set:
        ob : Object | None = context.object

        new_item = ob.vs.dme_flexcontrollers.add()
        ob.vs.dme_flexcontrollers_index = len(ob.vs.dme_flexcontrollers) - 1
        new_item.shapekey = ""
        return {'FINISHED'}

class DME_OT_RemoveFlexController(Operator):
    bl_idname : str = "dme.remove_flexcontroller"
    bl_label : str = "Remove Flex Controller"
    bl_options : set = {'INTERNAL', 'UNDO'}
    
    index : IntProperty()

    def execute(self, context : Context) -> set:
        ob : Object | None = context.object

        ob.vs.dme_flexcontrollers.remove(self.index)
        ob.vs.dme_flexcontrollers_index = max(0, min(self.index, len(ob.vs.dme_flexcontrollers) - 1))
        return {'FINISHED'}

class SMD_OT_AddVertexMapRemap(Operator):
    bl_idname : str = "smd.add_vertex_map_remap"
    bl_label : str = "Apply Remap Range"

    map_name: bpy.props.StringProperty()

    def execute(self, context : Context) -> set:
        active_object = context.object
        if active_object and active_object.type == 'MESH':
            group = active_object.vs.vertex_map_remaps.add()
            group.group = self.map_name
            group.min = 0.0
            group.max = 1.0
        return {'FINISHED'}
