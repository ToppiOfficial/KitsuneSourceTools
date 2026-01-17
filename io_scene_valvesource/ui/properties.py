import bpy
from typing import Any

from bpy.types import (
    Panel, UIList, Operator, UILayout, Object, Context,
    VertexGroup, LoopColors, MeshLoopColorLayer
)

from .common import KITSUNE_SecondaryPanel
from ..core.boneutils import get_bone_exportname
from ..core.commonutils import (
    is_armature, is_mesh, is_empty, is_curve, draw_wrapped_texts,
    draw_title_box_layout, get_valid_vertexanimation_object,
    is_mesh_compatible, get_object_path, get_collection_parent
)

from ..utils import (
    get_id, vertex_maps, vertex_float_maps, hasShapes, countShapes,
    State, ExportFormat, MakeObjectIcon, hasFlexControllerSource,
    getFileExt
)

from ..flex import AddCorrectiveShapeDrivers, RenameShapesToMatchCorrectiveDrivers,DmxWriteFlexControllers
from .bone import TOOLS_OT_AssignBoneRotExportOffset

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


class KITSUNE_PT_active_object_properties(KITSUNE_SecondaryPanel, Panel):
    bl_label = get_id("panel_context_properties")
    
    def draw(self, context) -> None:
        layout = self.layout
        active_object = context.object
        
        if active_object is None:
            draw_wrapped_texts(layout, get_id("panel_select_object"), max_chars=40, icon='HELP')
            return
        
        title = draw_title_box_layout(layout, text=f'Active Object: {active_object.name}', icon='OBJECT_DATA')
        
        path = get_object_path(active_object, context.view_layer)
        draw_wrapped_texts(title, text="Path: {}".format(path), boxed=False)
        
        box = layout.box()
        
        col = box.column(align=True)
        col.label(text=get_id("exportpanel_title"))
        col.prop(active_object.vs, 'export', text='Scene Export')
        
        parent_collection = get_collection_parent(active_object, context.scene)
        if parent_collection:
            col.prop(parent_collection.vs, 'mute', text="Supress collection '{}'".format(parent_collection.name))


class KITSUNE_PT_object_properties(KITSUNE_SecondaryPanel, Panel):
    bl_label = 'Armature Properties'
    bl_parent_id = 'KITSUNE_PT_active_object_properties'
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw_header(self, context):
        layout = self.layout
        layout.label(text='', icon='ARMATURE_DATA')
    
    def draw(self, context):
        layout = self.layout
        active_object = context.object
        
        if not is_armature(active_object):
            draw_wrapped_texts(layout, get_id("panel_select_armature"), alert=True, icon='ERROR')
            return
        
        box = layout.box()
        
        col = box.column(align=True)
        col.prop(active_object.data.vs, "ignore_bone_exportnames")
        col.label(text='Direction Naming:')
        
        row = col.row()
        row.prop(active_object.data.vs, 'bone_direction_naming_left', text='Left')
        row.prop(active_object.data.vs, 'bone_direction_naming_right', text='Right')
        
        box.prop(active_object.data.vs, 'bone_name_startcount', slider=True)

    
class KITSUNE_PT_bone_properties(KITSUNE_SecondaryPanel, Panel):
    bl_label = 'Bone Properties'
    bl_parent_id = 'KITSUNE_PT_active_object_properties'
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw_header(self, context):
        layout = self.layout
        layout.label(text='', icon='BONE_DATA')
        
    def draw(self, context):
        layout = self.layout
        active_object = context.object
        active_bone = context.active_bone
        
        if not is_armature(active_object):
            draw_wrapped_texts(layout, get_id("panel_select_armature"), alert=True, icon='ERROR')
            return
        
        if not isinstance(active_bone, (bpy.types.PoseBone, bpy.types.Bone)):
            draw_wrapped_texts(layout, get_id("panel_select_noneditbone"), alert=True, icon='ERROR')
            return
        
        title = draw_title_box_layout(layout, text=f'Active Bone: {active_bone.name}', icon='BONE_DATA')
        col = title.column(align=True)
        
        if isinstance(active_bone, bpy.types.PoseBone):
            active_bone_vs = active_bone.bone.vs
        else:
            active_bone_vs = active_bone.vs
        
        col.enabled = not active_bone_vs.bone_is_jigglebone
        
        active_bone_exportname = get_bone_exportname(active_bone)
        col.prop(active_bone.vs, 'export_name', placeholder=active_bone_exportname, text='')
        col.label(text='Export Name: {}'.format(active_bone_exportname))
        
        split = title.split(factor=0.5)
        
        col_left = split.column(align=True)
        col_left.label(text='Location Offset:', icon='ORIENTATION_LOCAL')
        col_left.prop(active_bone_vs, 'ignore_location_offset', text='Ignore', toggle=True)
        
        sub1 = col_left.column(align=True)
        sub1.active = not active_bone_vs.ignore_location_offset
        sub1.prop(active_bone_vs, 'export_location_offset_x')
        sub1.prop(active_bone_vs, 'export_location_offset_y')
        sub1.prop(active_bone_vs, 'export_location_offset_z')
        
        col_right = split.column(align=True)
        col_right.label(text='Rotation Offset:', icon='ORIENTATION_GIMBAL')
        col_right.prop(active_bone_vs, 'ignore_rotation_offset', text='Ignore', toggle=True)
        
        sub2 = col_right.column(align=True)
        sub2.active = not active_bone_vs.ignore_rotation_offset
        sub2.prop(active_bone_vs, 'export_rotation_offset_x')
        sub2.prop(active_bone_vs, 'export_rotation_offset_y')
        sub2.prop(active_bone_vs, 'export_rotation_offset_z')
        
        title.operator(TOOLS_OT_AssignBoneRotExportOffset.bl_idname)

      
class KITSUNE_PT_mesh_properties(KITSUNE_SecondaryPanel, Panel):
    bl_label = 'Mesh Properties'
    bl_parent_id = 'KITSUNE_PT_active_object_properties'
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw_header(self, context):
        layout = self.layout
        layout.label(text='', icon='MESH_DATA')
        
    def draw(self, context):
        layout = self.layout
        active_object = context.object
        
        if not is_mesh_compatible(active_object):
            draw_wrapped_texts(layout, get_id("panel_select_mesh"), alert=True, icon='ERROR')
            return

  
class KITSUNE_PT_shapekey_properties(KITSUNE_SecondaryPanel, Panel):
    bl_label = 'Shapekey'
    bl_parent_id = 'KITSUNE_PT_mesh_properties'
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        return is_mesh_compatible(context.object)
    
    def draw_header(self, context):
        layout = self.layout
        layout.label(text='', icon='SHAPEKEY_DATA')
        
    def draw(self, context):
        layout = self.layout
        active_object = context.object
        
        if not is_mesh(active_object) or not hasShapes(active_object):
            draw_wrapped_texts(layout,get_id("panel_select_mesh_sk"),alert=True,icon='ERROR')
            return
        
        num_shapes, num_correctives = countShapes(active_object)
        
        box = layout.box()
        col = box.column()
        col.prop(active_object.data.vs, "bake_shapekey_as_basis_normals")
        col.prop(active_object.data.vs, "normalize_shapekeys")
        
        col = box.column()
        col.scale_y = 1.2
        row = col.row(align=True)
        row.prop(active_object.vs,"flex_controller_mode",expand=True)
        
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
            r.label(text=active_object.data.name + ":",icon=MakeObjectIcon(active_object,suffix='_DATA'),translate=False) # type: ignore
            r2 = r.split(factor=0.7,align=True)
            
            if active_object.data.vs.flex_stereo_mode == 'VGROUP':
                r2.alert = active_object.vertex_groups.get(active_object.data.vs.flex_stereo_vg) is None
                r2.prop_search(active_object.data.vs,"flex_stereo_vg",active_object,"vertex_groups",text="")
            else:
                r2.prop(active_object.data.vs,"flex_stereo_sharpness",text="Sharpness")
                
            r2.prop(active_object.data.vs,"flex_stereo_mode",text="")
        
        if active_object.vs.flex_controller_mode == 'ADVANCED':
            controller_source = col.row()
            controller_source.alert = hasFlexControllerSource(active_object.vs.flex_controller_source) == False
            controller_source.prop(active_object.vs,"flex_controller_source",text=get_id("exportables_flex_src"),icon = 'TEXT' if active_object.vs.flex_controller_source in bpy.data.texts else 'NONE')
            
            row = col.row(align=True)
            row.operator(DmxWriteFlexControllers.bl_idname,icon='TEXT',text=get_id("exportables_flex_generate", True))
            row.operator("wm.url_open",text=get_id("exportables_flex_help", True),icon='HELP').url = "http://developer.valvesoftware.com/wiki/Blender_SMD_Tools_Help#Flex_properties"
            
            insertCorrectiveUi(col)
            
            insertStereoSplitUi(col)
            
        elif active_object.vs.flex_controller_mode == 'BUILDER':
            col = box.column()
            row = col.row()
            first_col = row.column()
            first_col.template_list("DME_UL_FlexControllers","",active_object.vs,"dme_flexcontrollers", active_object.vs,"dme_flexcontrollers_index")
            
            if len(active_object.vs.dme_flexcontrollers) > 0 and active_object.vs.dme_flexcontrollers_index != -1:
                
                box = col.box()
                box_col = box.column(align=True)
                
                item = active_object.vs.dme_flexcontrollers[active_object.vs.dme_flexcontrollers_index]
                
                prop_col = box_col.split(factor=0.33, align=True)
                prop_col.alignment = 'RIGHT'
                prop_col.label(text='Shapekey')
                prop_col.prop_search(item,'shapekey',active_object.data.shape_keys,'key_blocks',text='')
                
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
            second_col.prop(active_object.vs, 'sync_active_shapekey_to_dme', icon='UV_SYNC_SELECT',text='')   
            
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
        
        if active_object.vs.flex_controller_mode != 'BUILDER':
            row.label(icon='SHAPEKEY_DATA',text = get_id("exportables_flex_count_corrective", True).format(num_correctives))
    
        
class KITSUNE_PT_vertexmap_properties(KITSUNE_SecondaryPanel, Panel):
    bl_label = 'Vertex Maps'
    bl_parent_id = 'KITSUNE_PT_mesh_properties'
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        return is_mesh_compatible(context.object)
    
    def draw_header(self, context):
        layout = self.layout
        layout.label(text='', icon='MOD_VERTEX_WEIGHT')
        
    def draw(self, context):
        layout = self.layout
        active_object = context.object
        
        box : UILayout = layout.box()
        col = box.column(align=True)
        
        if State.exportFormat != ExportFormat.DMX:
            draw_wrapped_texts(box,'Only Applicable in DMX!',alert=True,icon='ERROR')
        
        col.label(text='Vertex Maps:')
        for map_name in vertex_maps:
            r = col.row()
            r.label(text=get_id(map_name),icon='GROUP_VCOL')
            
            add_remove = r.row(align=True)
            add_remove.operator(SMD_OT_CreateVertexMap_idname + map_name,icon='ADD',text="")
            add_remove.operator(SMD_OT_RemoveVertexMap_idname + map_name,icon='REMOVE',text="")
            add_remove.operator(SMD_OT_SelectVertexMap_idname + map_name,text="Activate")
    
      
class KITSUNE_PT_vertexfloatmap_properties(KITSUNE_SecondaryPanel, Panel):
    bl_label = 'Vertex Float Maps'
    bl_parent_id = 'KITSUNE_PT_mesh_properties'
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        return is_mesh_compatible(context.object)
    
    def draw_header(self, context):
        layout = self.layout
        layout.label(text='', icon='MOD_VERTEX_WEIGHT')
        
    def draw(self, context):
        layout = self.layout
        active_object = context.object
        
        layout.operator("wm.url_open", text=get_id("help", True), icon='INTERNET').url = "http://developer.valvesoftware.com/wiki/DMX/Source_2_Vertex_attributes"
        
        box : UILayout = layout.box()

        col = box.column()
        col.label(text='Vertex Float Maps:')
        
        col.scale_y = 1.15
        
        for map_name in vertex_float_maps:
            split1 = col.split(align=True, factor=0.55)
            r = split1.row(align=True)
            r.operator(SMD_OT_SelectVertexFloatMap_idname + map_name, text=map_name.replace("cloth_", "").replace("_", " ").title(), icon='GROUP_VERTEX')
            r.operator(SMD_OT_CreateVertexFloatMap_idname + map_name, icon='ADD', text="")
            r.operator(SMD_OT_RemoveVertexFloatMap_idname + map_name, icon='REMOVE', text="")
            
            r = split1.row(align=True)
            found = False
            for group in active_object.vs.vertex_map_remaps:
                if group.group == map_name:
                    found = True
                    r.prop(group, "min")
                    r.prop(group, "max")
                    break

            if not found:
                r.operator("smd.add_vertex_map_remap").map_name = map_name


class KITSUNE_PT_vertex_animations(KITSUNE_SecondaryPanel, Panel):
    bl_label = 'Vertex Animations'
    bl_parent_id = 'KITSUNE_PT_mesh_properties'
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        return is_mesh_compatible(context.object)
    
    def draw_header(self, context):
        layout = self.layout
        layout.label(text='', icon='ANIM_DATA')
        
    def draw(self, context):
        layout = self.layout
        active_object = get_valid_vertexanimation_object(context.object)
        
        op3 = layout.operator("wm.url_open", text='Vertex Animations Help', icon='INTERNET')
        op3.url = "http://developer.valvesoftware.com/wiki/Vertex_animation"
        
        if active_object is None:
            draw_wrapped_texts(layout, get_id("panel_select_mesh"))
            
        box = layout.box()
        
        draw_wrapped_texts(box, text="Target Object: {}".format(active_object.name), icon='MESH_DATA' if is_mesh_compatible(active_object) else "OUTLINER_COLLECTION")
        
        row = box.row(align=True)
        row.operator(SMD_OT_AddVertexAnimation.bl_idname, icon="ADD", text="Add")
        
        remove_op = row.operator(SMD_OT_RemoveVertexAnimation.bl_idname, icon="REMOVE", text="Remove")
        remove_op.vertexindex = active_object.vs.active_vertex_animation
        
        if active_object.vs.vertex_animations:
            box.template_list("SMD_UL_VertexAnimationItem", "", active_object.vs, "vertex_animations", active_object.vs, "active_vertex_animation", rows=2, maxrows=4)
            box.operator(SMD_OT_GenerateVertexAnimationQCSnippet.bl_idname, icon='FILE_TEXT')


class KITSUNE_PT_material_properties(KITSUNE_SecondaryPanel, Panel):
    bl_label = 'Material Properties'
    bl_parent_id = 'KITSUNE_PT_active_object_properties'
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw_header(self, context):
        layout = self.layout
        layout.label(text='', icon='MATERIAL_DATA')
        
    def draw(self, context):
        layout = self.layout
        active_object = context.object
        
        if not is_mesh(active_object):
            draw_wrapped_texts(layout, get_id("panel_select_mesh"), alert=True, icon='ERROR')
            return
        
        active_material = active_object.active_material
        
        if not active_material:
            draw_wrapped_texts(layout, get_id("panel_select_mesh_mat"), alert=True, icon='ERROR')
            return
        
        layout.box().label(text=f'Active Material: ({active_material.name})', icon='ERROR')
        
        box = layout.box()
        
        col = box.column(align=True)
        col.prop(active_material.vs, 'do_not_export_faces')
        col.prop(active_material.vs, 'do_not_export_faces_vgroup')
        
        if not active_material.vs.do_not_export_faces:
            col = box.column()
            
            if State.exportFormat == ExportFormat.DMX:
                col.prop(active_material.vs, 'override_dmx_export_path', placeholder=context.scene.vs.material_path)
                
            col.prop(active_material.vs, 'non_exportable_vgroup')   
            col.prop(active_material.vs, 'do_not_export_faces_vgroup_tolerance', slider=True)


class KITSUNE_PT_empty_properties(KITSUNE_SecondaryPanel, Panel):
    bl_label = 'Empty Properties'
    bl_parent_id = 'KITSUNE_PT_active_object_properties'
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw_header(self, context):
        layout = self.layout
        layout.label(text='', icon='EMPTY_DATA')
        
    def draw(self, context):
        layout = self.layout
        active_object = context.object
        
        if not is_empty(active_object):
            draw_wrapped_texts(layout, get_id("panel_select_empty"), alert=True, icon='ERROR')
            return
        
        col = layout.column()
        col.prop(active_object.vs, 'dmx_attachment', toggle=False)
        col.prop(active_object.vs, 'smd_hitbox', toggle=False)
        
        if active_object.vs.smd_hitbox:
            col.prop(active_object.vs, 'smd_hitbox_group', text='Hitbox Group')
        
        if active_object.vs.dmx_attachment and active_object.children:
            col.alert = True
            col.box().label(text="Attachment cannot be a parent",icon='WARNING_LARGE')


class KITSUNE_PT_curve_properties(KITSUNE_SecondaryPanel, Panel):
    bl_label = 'Curve Properties'
    bl_parent_id = 'KITSUNE_PT_active_object_properties'
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw_header(self, context):
        layout = self.layout
        layout.label(text='', icon='CURVE_DATA')
        
    def draw(self, context):
        layout = self.layout
        active_object = context.object
        
        if not is_curve(active_object):
            draw_wrapped_texts(layout, get_id("panel_select_curve"), alert=True, icon='ERROR')
            return
        
        done = set()
        
        row = layout.split(factor=0.33)
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
        
        is_basis = False
        if ob.data and ob.data.shape_keys and item.shapekey and len(ob.data.shape_keys.key_blocks) > 0:
            if item.shapekey == ob.data.shape_keys.key_blocks[0].name:
                is_basis = True

        split = layout.split(factor=0.6, align=True)
        
        name_row = split.row(align=True)
        if has_duplicate_shapekey or not item.shapekey or is_basis:
            name_row.alert = True
        name_row.label(text=item.shapekey if item.shapekey else "Null Flexcontroller", icon='SHAPEKEY_DATA')
        
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
        
        if hasattr(ob.data, 'shape_keys') and ob.active_shape_key_index is not None and ob.active_shape_key_index > 0:
            new_item.shapekey = ob.data.shape_keys.key_blocks[ob.active_shape_key_index].name
            new_item.raw_delta_name = new_item.shapekey.replace("_", "")
        else:
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
