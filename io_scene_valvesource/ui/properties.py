import bpy
from typing import Any

from bpy.types import (
    Panel, UIList, Operator, UILayout, Object, Context,
    VertexGroup, LoopColors, MeshLoopColorLayer
)

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
    draw_title_box_layout, draw_listing_layout, get_rotated_hitboxes, is_valid_string,
    get_valid_vertexanimation_object, is_mesh_compatible
)

from ..utils import (
    get_id, vertex_maps, vertex_float_maps, hasShapes, countShapes,
    State, ExportFormat, MakeObjectIcon, hasFlexControllerSource,
    hasCurves, getFileExt
)

from ..flex import (
    AddCorrectiveShapeDrivers, RenameShapesToMatchCorrectiveDrivers,
    DmxWriteFlexControllers
)

from .valvemodel import (
    VALVEMODEL_OT_FixAttachment, VALVEMODEL_OT_FixHitBox
)

from .bone import (
    TOOLS_OT_AssignBoneRotExportOffset
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
            SelectVertexColorMap.execute(self, context)
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

            SelectVertexFloatMap.execute(self, context)
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
    def get_invalid_names(armature_obj) -> dict:
        invalid_names = {
            'armature': [],
            'bones': [],
            'meshes': [],
            'materials': [],
        }
        
        armature = None
        if not is_armature(armature_obj):
            armature = get_armature(armature_obj)
        else:
            armature = armature_obj
            
        if armature is None: 
            return invalid_names
        
        for bone in armature.data.bones:
            if not is_valid_string(bone.name):
                invalid_names['bones'].append(bone.name)
                
        if not is_valid_string(armature.name):
            invalid_names['armature'].append(armature.name)
            
        meshes = get_armature_meshes(armature)
        for mesh in meshes:
            if mesh.vs.export is False: continue
            
            if not is_valid_string(mesh.name):
                invalid_names['meshes'].append(mesh.name)
            
            for mat in mesh.data.materials:
                if mat is None: continue
                if mat.vs.do_not_export_faces: continue
                
                if mat and not is_valid_string(mat.name):
                    if (mat.name, mesh.name) not in invalid_names['materials']:
                        invalid_names['materials'].append((mat.name, mesh.name))
        
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
            
        if get_rotated_hitboxes():
            count += 1
        
        return count

class WarningRenderer:
    INVALID_CHAR_MESSAGE = '\n\ncontain invalid characters! Only alphanumeric characters (including Unicode), spaces, underscores, and dots are allowed. Special characters will be sanitized (replaced with underscores) on export.'
    
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
    
    @staticmethod
    def draw_rotated_hitboxes(layout: UILayout) -> int:
        count = 0
        
        rotated_hitboxes = get_rotated_hitboxes()
        if rotated_hitboxes:
            draw_wrapped_texts(layout, f'Hitbox(es): {", ".join(rotated_hitboxes)} have rotation applied. This is unuseable in Source 1 Engine!', alert=True)
            count += 1
        
        return count

class SMD_PT_ContextObject(KITSUNE_PT_CustomToolPanel, Panel):
    """Displays the Main Panel for Object Properties"""
    bl_label : str = get_id("panel_context_properties")
    
    def draw(self, context : Context) -> None:
        l : UILayout = self.layout

        col = l.column(align=True)
        
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
            
            section = draw_toggleable_layout(
                col, context.scene.vs, prop, 
                show_text=label, icon=icon, 
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
        num_warnings += WarningRenderer.draw_rotated_hitboxes(layout)
                
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
        
        if is_mesh_compatible(ob): pass
        else:
            draw_wrapped_texts(l,get_id("panel_select_mesh"),max_chars=40 , icon='HELP')
            return
        
        sections = [
            ('show_flex', 'Show Shapekey Conifg', 'SHAPEKEY_DATA', self._draw_shapekey_config),
            ('show_vertexmap', 'Show VertexMap Conifg', 'GROUP_VERTEX', self._draw_vertexmap_config),
            ('show_floatmaps', 'Show FloatMaps Conifg', 'MOD_CLOTH', self._draw_floatmaps_config),
            ('show_vertexanimation', 'Show Vertex Animation', 'ANIM_DATA', self._draw_vertex_animations),
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
            draw_wrapped_texts(bx,get_id("panel_select_mesh_sk"),alert=True,icon='ERROR')
            return
        
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
        
        def insertStereoSplitUi(parent):
            col = parent.column()
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
        
        if ob.vs.flex_controller_mode == 'ADVANCED':
            controller_source = col.row()
            controller_source.alert = hasFlexControllerSource(ob.vs.flex_controller_source) == False
            controller_source.prop(ob.vs,"flex_controller_source",text=get_id("exportables_flex_src"),icon = 'TEXT' if ob.vs.flex_controller_source in bpy.data.texts else 'NONE')
            
            row = col.row(align=True)
            row.operator(DmxWriteFlexControllers.bl_idname,icon='TEXT',text=get_id("exportables_flex_generate", True))
            row.operator("wm.url_open",text=get_id("exportables_flex_help", True),icon='HELP').url = "http://developer.valvesoftware.com/wiki/Blender_SMD_Tools_Help#Flex_properties"
            
            insertCorrectiveUi(col)
            
            insertStereoSplitUi(col)
            
        elif ob.vs.flex_controller_mode == 'SPECIFIC':
            col = bx.column()
            row = col.row()
            first_col = row.column()
            first_col.template_list("DME_UL_FlexControllers","",ob.vs,"dme_flexcontrollers", ob.vs,"dme_flexcontrollers_index")
            
            if len(ob.vs.dme_flexcontrollers) > 0 and ob.vs.dme_flexcontrollers_index != -1:
                
                box = col.box()
                box_col = box.column(align=True)
                
                item = ob.vs.dme_flexcontrollers[ob.vs.dme_flexcontrollers_index]
                
                prop_col = box_col.split(factor=0.33, align=True)
                prop_col.alignment = 'RIGHT'
                prop_col.label(text='Shapekey')
                prop_col.prop_search(item,'shapekey',ob.data.shape_keys,'key_blocks',text='')
                
                prop_col = box_col.split(factor=0.33, align=True)
                prop_col.alignment = 'RIGHT'
                prop_col.label(text='Delta Name')
                prop_col.prop(item,'raw_delta_name',text='')
                
                prop_col = box_col.split(factor=0.33, align=True)
                prop_col.alignment = 'RIGHT'
                prop_col.label(text='')
                prop_col.prop(item,'eyelid',text='Is Eyelid')
                
                prop_col = box_col.split(factor=0.33, align=True)
                prop_col.alignment = 'RIGHT'
                prop_col.label(text='')
                prop_col.prop(item,'stereo',text='Is Stereo')
                
                box_row = box.row(align=True)
                
                preview_op = box_row.operator(DME_OT_PreviewFlexController.bl_idname, text="Preview (Reset)", icon='HIDE_OFF')
                preview_op.reset_others = True

                preview_op = box_row.operator(DME_OT_PreviewFlexController.bl_idname, text="Preview (Additive)", icon='ADD')
                preview_op.reset_others = False
                
                box_row.operator("object.shape_key_clear", icon='X', text="")
            
            second_col = row.column(align=True)
            second_col.operator(DME_OT_AddFlexController.bl_idname, icon='ADD',text='')
            second_col.operator(DME_OT_RemoveFlexController.bl_idname, icon='REMOVE',text='')   
            
            second_col.separator()
            
            second_col.alert = True
            second_col.operator(DME_OT_ClearFlexControllers.bl_idname, icon='TRASH',text='')   
            
            insertStereoSplitUi(col)
            
        else:
            insertCorrectiveUi(col)

        col.separator()
        row = col.row()
        row.alignment = 'CENTER'
        row.label(icon='SHAPEKEY_DATA',text = get_id("exportables_flex_count", True).format(num_shapes))
        
        if ob.vs.flex_controller_mode != 'SPECIFIC':
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
    
    def _draw_vertex_animations(self, context : Context, layout : UILayout):
        
        ob = get_valid_vertexanimation_object(context.object)
        if ob is None: return
        
        draw_wrapped_texts(layout, text="Target Object: {}".format(ob.name), icon='MESH_DATA' if is_mesh_compatible(ob) else "OUTLINER_COLLECTION")
        
        row = layout.row(align=True)
        add_op = row.operator(SMD_OT_AddVertexAnimation.bl_idname, icon="ADD", text="Add")
        
        remove_op = row.operator(SMD_OT_RemoveVertexAnimation.bl_idname, icon="REMOVE", text="Remove")
        remove_op.vertexindex = ob.vs.active_vertex_animation
        
        if ob.vs.vertex_animations:
            layout.template_list("SMD_UL_VertexAnimationItem", "", ob.vs, "vertex_animations", ob.vs, "active_vertex_animation", rows=2, maxrows=4)
            layout.operator(SMD_OT_GenerateVertexAnimationQCSnippet.bl_idname, icon='FILE_TEXT')
    
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
        
        sub = title.column(align=True)
        sub.label(text='Target Bone Forward:')
        row = sub.row(align=True)
        row.operator(TOOLS_OT_AssignBoneRotExportOffset.bl_idname,text='+X').export_rot_target = 'X'
        row.operator(TOOLS_OT_AssignBoneRotExportOffset.bl_idname,text='+Y').export_rot_target = 'Y'
        row.operator(TOOLS_OT_AssignBoneRotExportOffset.bl_idname,text='+Z').export_rot_target = 'Z'
        row.operator(TOOLS_OT_AssignBoneRotExportOffset.bl_idname,text='-X').export_rot_target = 'X_INVERT'
        row.operator(TOOLS_OT_AssignBoneRotExportOffset.bl_idname,text='-Y').export_rot_target = 'Y_INVERT'
        row.operator(TOOLS_OT_AssignBoneRotExportOffset.bl_idname,text='-Z').export_rot_target = 'Z_INVERT'
        
        message = [
            "- (Target Bone Forward) assumes you have the bone(s) in Blender's Y-forward\n",
            '- Bones rotate on export in Z→Y→X order (translation remains X→Y→Z). Use "normal" in edit mode to check. Z+90° from Y-forward → X-forward.',
        ]
        
        draw_wrapped_texts(
            title,
            message,
            max_chars=36,
            icon='INFO')
        
    def draw_materialproperties(self, context : Context, layout : UILayout) -> None:
        l : UILayout = layout
        ob : Object | None = context.object
        
        if ob is None:
            draw_wrapped_texts(l, get_id("panel_select_mesh"), max_chars=40, icon='HELP')
            return
        
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
            col.prop(currMat.vs, 'do_not_export_faces_vgroup_tolerance', slider=True)

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
        
        has_duplicate_shapekey = False
        shapekey_count = sum(1 for fc in ob.vs.dme_flexcontrollers if fc.shapekey == item.shapekey)
        has_duplicate_shapekey = shapekey_count > 1
        
        valid_keys = set(ob.data.shape_keys.key_blocks.keys()[1:]) if ob.data.shape_keys else set()
        
        used_names = {}
        has_duplicate_raw = False
        actual_export_name = None
        
        for fc in ob.vs.dme_flexcontrollers:
            if fc.shapekey not in valid_keys:
                continue
            
            raw_delta = fc.raw_delta_name.strip() if fc.raw_delta_name and fc.raw_delta_name.strip() else fc.shapekey
            
            if fc == item:
                if raw_delta in used_names:
                    has_duplicate_raw = True
                    base_name = raw_delta
                    counter = used_names[raw_delta]
                    actual_export_name = f"{base_name}.{counter:03d}"
                else:
                    actual_export_name = raw_delta
            
            if raw_delta in used_names:
                used_names[raw_delta] += 1
            else:
                used_names[raw_delta] = 1
        
        invalid_shapekey = item.shapekey is None or item.shapekey not in ob.data.shape_keys.key_blocks
        
        split = layout.split(factor=0.6, align=True)
        
        name_row = split.row(align=True)
        if has_duplicate_shapekey:
            name_row.alert = True
        name_row.label(text=item.shapekey, icon='SHAPEKEY_DATA')
        
        info_row = split.row(align=True)
        info_row.alignment = 'RIGHT'
        
        if len(item.raw_delta_name.strip()) > 0 and item.shapekey in ob.data.shape_keys.key_blocks:
            if has_duplicate_raw:
                info_row.alert = True
            info_row.label(text=actual_export_name if actual_export_name else item.raw_delta_name)
            
        if item.stereo:
                info_row.label(text="", icon='MOD_MIRROR')
                
        if item.eyelid:
                info_row.label(text="", icon='HIDE_OFF')
                
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
    
    @classmethod
    def poll(cls, context) -> bool:
        return bool(len(context.object.vs.dme_flexcontrollers) > 0)
    
    def execute(self, context) -> set:
        context.object.vs.dme_flexcontrollers.remove(context.object.vs.dme_flexcontrollers_index)
        context.object.vs.dme_flexcontrollers_index = min(max(0, context.object.vs.dme_flexcontrollers_index - 1), 
                                                 len(context.object.vs.dme_flexcontrollers) - 1)
        return {'FINISHED'}

class DME_OT_PreviewFlexController(Operator):
    bl_idname: str = "dme.preview_flexcontroller"
    bl_label: str = "Preview Flex Controller"
    bl_options: set = {'INTERNAL', 'UNDO'}
    
    reset_others: bpy.props.BoolProperty(
        name="Reset Others",
        description="Reset all other shape keys to 0",
        default=True
    )
    
    @classmethod
    def poll(cls, context) -> bool:
        ob = context.object
        return bool(ob and ob.type == 'MESH' and ob.data.shape_keys and len(ob.vs.dme_flexcontrollers) > 0)
    
    def execute(self, context: Context) -> set:
        ob: Object = context.object
        shape_keys = ob.data.shape_keys
        current_index = ob.vs.dme_flexcontrollers_index
        
        if current_index >= len(ob.vs.dme_flexcontrollers):
            return {'CANCELLED'}
        
        current_flex = ob.vs.dme_flexcontrollers[current_index]
        target_shapekey_name = current_flex.shapekey
        
        for i, key_block in enumerate(shape_keys.key_blocks):
            if i == 0:
                continue
            if key_block.name == target_shapekey_name:
                ob.active_shape_key_index = i
                key_block.value = 1.0
            elif self.reset_others:
                key_block.value = 0.0
        
        return {'FINISHED'}

class DME_OT_ClearFlexControllers(Operator):
    bl_idname: str = "dme.clear_flexcontrollers"
    bl_label: str = "Clear All Flex Controllers"
    bl_options: set = {'INTERNAL', 'UNDO'}
    
    @classmethod
    def poll(cls, context) -> bool:
        return bool(len(context.object.vs.dme_flexcontrollers) > 0)
    
    def invoke(self, context: Context, event) -> set:
        return context.window_manager.invoke_confirm(self, event)
    
    def execute(self, context: Context) -> set:
        context.object.vs.dme_flexcontrollers.clear()
        context.object.vs.dme_flexcontrollers_index = 0
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

class SMD_UL_VertexAnimationItem(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        r = layout.row()
        r.alignment='LEFT'
        r.prop(item,"name",text="",emboss=False)
        r = layout.row(align=True)
        r.alignment='RIGHT'
        r.operator(SMD_OT_PreviewVertexAnimation.bl_idname,text="",icon='PAUSE' if context.screen.is_animation_playing else 'PLAY')
        r.prop(item,"start",text="")
        r.prop(item,"end",text="")
        r.prop(item,"export_sequence",text="",icon='ACTION')

class SMD_OT_AddVertexAnimation(bpy.types.Operator):
    bl_idname = "smd.vertexanim_add"
    bl_label = get_id("vca_add")
    bl_description = get_id("vca_add_tip")
    bl_options = {'INTERNAL', 'UNDO'}
    
    index: bpy.props.IntProperty()
    
    def execute(self,context : Context) -> set:
        item = get_valid_vertexanimation_object(context.object)
        item.vs.vertex_animations.add()
        item.vs.active_vertex_animation = len(item.vs.vertex_animations) - 1
        return {'FINISHED'}

class SMD_OT_RemoveVertexAnimation(bpy.types.Operator):
    bl_idname = "smd.vertexanim_remove"
    bl_label = get_id("vca_remove")
    bl_description = get_id("vca_remove_tip")
    bl_options = {'INTERNAL', 'UNDO'}

    index : bpy.props.IntProperty(min=0)
    vertexindex : bpy.props.IntProperty(min=0)

    def execute(self, context) -> set:
        item = get_valid_vertexanimation_object(context.object)
        if len(item.vs.vertex_animations) > self.vertexindex:
            item.vs.vertex_animations.remove(self.vertexindex)
            item.vs.active_vertex_animation = max(
                0, min(self.vertexindex, len(item.vs.vertex_animations) - 1)
            )
        return {'FINISHED'}
        
class SMD_OT_PreviewVertexAnimation(bpy.types.Operator):
    bl_idname = "smd.vertexanim_preview"
    bl_label = get_id("vca_preview")
    bl_description = get_id("vca_preview_tip")
    bl_options = {'INTERNAL'}

    index: bpy.props.IntProperty(min=0)
    vertexindex: bpy.props.IntProperty(min=0)

    def execute(self, context) -> set:
        scene = context.scene

        item = get_valid_vertexanimation_object(context.object)
        if self.vertexindex >= len(item.vs.vertex_animations):
            self.report({'ERROR'}, "Invalid vertex animation index")
            return {'CANCELLED'}

        anim = item.vs.vertex_animations[self.vertexindex]

        scene.use_preview_range = True
        scene.frame_preview_start = anim.start
        scene.frame_preview_end = anim.end

        if not context.screen.is_animation_playing:
            scene.frame_set(anim.start)
        bpy.ops.screen.animation_play()

        return {'FINISHED'}

class SMD_OT_GenerateVertexAnimationQCSnippet(bpy.types.Operator):
    bl_idname = "smd.vertexanim_generate_qc"
    bl_label = get_id("vca_qcgen")
    bl_description = get_id("vca_qcgen_tip")
    bl_options = {'INTERNAL'}

    index: bpy.props.IntProperty(min=0)

    @classmethod
    def poll(cls, context) -> bool:
        return len(context.scene.vs.export_list) > 0

    def execute(self, context) -> set:
        scene = context.scene

        item = get_valid_vertexanimation_object(context.object)
        fps = scene.render.fps / scene.render.fps_base
        wm = context.window_manager

        wm.clipboard = '$model "merge_me" {0}{1}'.format(item.name, getFileExt())
        if scene.vs.export_format == 'SMD':
            wm.clipboard += ' {{\n{0}\n}}\n'.format(
                "\n".join([f"\tvcafile {vca.name}.vta" for vca in item.vs.vertex_animations])
            )
        else:
            wm.clipboard += '\n'

        wm.clipboard += "\n// vertex animation block begins\n$upaxis Y\n"
        wm.clipboard += "\n".join([
            f'''
$boneflexdriver "vcabone_{vca.name}" tx "{vca.name}" 0 1
$boneflexdriver "vcabone_{vca.name}" ty "multi_{vca.name}" 0 1
$sequence "{vca.name}" "vcaanim_{vca.name}{getFileExt()}" fps {fps}
'''.strip()
            for vca in item.vs.vertex_animations if vca.export_sequence
        ])
        wm.clipboard += "\n// vertex animation block ends\n"

        self.report({'INFO'}, "QC segment copied to clipboard.")
        return {'FINISHED'}
