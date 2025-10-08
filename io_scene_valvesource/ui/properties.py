import bpy
from .common import KITSUNE_PT_CustomToolPanel
from ..utils import *
from ..flex import *
from ..core.commonutils import *
from ..core.boneutils import *
from ..core.armatureutils import *
from ..core.meshutils import *
from bpy.types import Panel, UIList, Operator, UILayout, Object, Context, VertexGroup, LoopColors, MeshLoopColorLayer
from typing import Set, Any
from ..keyvalue3 import *

SMD_OT_CreateVertexMap_idname : str = "smd.vertex_map_create_"
SMD_OT_SelectVertexMap_idname : str = "smd.vertex_map_select_"
SMD_OT_RemoveVertexMap_idname : str = "smd.vertex_map_remove_"

for map_name in vertex_maps:

    class SelectVertexColorMap(Operator):
        bl_idname : str = SMD_OT_SelectVertexMap_idname + map_name
        bl_label : str = get_id("vertmap_select")
        bl_description : str = get_id("vertmap_select")
        bl_options : Set = {'INTERNAL'}
        vertex_map : str = map_name
    
        @classmethod
        def poll(cls, context : Context) -> bool:
            if not is_mesh(context.active_object):
                return False
            vc_loop : MeshLoopColorLayer | None = context.active_object.data.vertex_colors.get(cls.vertex_map)
            return bool(vc_loop and not vc_loop.active)

        def execute(self, context : Context) -> Set:
            context.active_object.data.vertex_colors[self.vertex_map].active = True
            return {'FINISHED'}

    class CreateVertexColorMap(Operator):
        bl_idname : str = SMD_OT_CreateVertexMap_idname + map_name
        bl_label : str = get_id("vertmap_create")
        bl_description : str = get_id("vertmap_create")
        bl_options : Set = {'INTERNAL'}
        vertex_map : str = map_name
    
        @classmethod
        def poll(cls, context : Context) -> bool:
            return bool(is_mesh(context.active_object) and cls.vertex_map not in context.active_object.data.vertex_colors)

        def execute(self, context : Context) -> Set:
            vc : MeshLoopColorLayer = context.active_object.data.vertex_colors.new(name=self.vertex_map)
            vc.data.foreach_set("color", [1.0] * len(vc.data) * 4)
            bpy.context.view_layer.update()
            SelectVertexColorMap().execute(context)
            return {'FINISHED'}

    class RemoveVertexColorMap(Operator):
        bl_idname : str = SMD_OT_RemoveVertexMap_idname + map_name
        bl_label : str = get_id("vertmap_remove")
        bl_description : str = get_id("vertmap_remove")
        bl_options : Set = {'INTERNAL'}
        vertex_map : str = map_name
    
        @classmethod
        def poll(cls, context : Context) -> bool:
            return bool(is_mesh(context.active_object) and cls.vertex_map in context.active_object.data.vertex_colors)

        def execute(self, context : Context) -> Set:
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
        bl_options : Set = {'INTERNAL'}
        vertex_map : str = map_name

        @classmethod
        def poll(cls, context : Context) -> bool:
            vg_loop = context.object.vertex_groups.get(cls.vertex_map)
            return bool(vg_loop and not context.active_object.vertex_groups.active == vg_loop)

        def execute(self, context : Context) -> Set:
            context.active_object.vertex_groups.active_index = context.active_object.vertex_groups[self.vertex_map].index
            return {'FINISHED'}

    class CreateVertexFloatMap(Operator):
        bl_idname : str = SMD_OT_CreateVertexFloatMap_idname + map_name
        bl_label : str = get_id("vertmap_create")
        bl_description : str = get_id("vertmap_create")
        bl_options : Set = {'INTERNAL'}
        vertex_map : str = map_name

        @classmethod
        def poll(cls, context : Context) -> bool:
            return bool(context.object and context.object.type == 'MESH' and cls.vertex_map not in context.object.vertex_groups)

        def execute(self, context : Context) -> Set:
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
        bl_options : Set = {'INTERNAL'}
        vertex_map : str = map_name

        @classmethod
        def poll(cls, context) -> bool:
            return bool(context.object and context.object.type == 'MESH' and cls.vertex_map in context.active_object.vertex_groups)

        def execute(self, context : Context) -> Set:
            vgs = context.active_object.vertex_groups
            vgs.remove(vgs[self.vertex_map])
            return {'FINISHED'}

    bpy.utils.register_class(SelectVertexFloatMap)
    bpy.utils.register_class(CreateVertexFloatMap)
    bpy.utils.register_class(RemoveVertexFloatMap)

class SMD_PT_ContextObject(KITSUNE_PT_CustomToolPanel, Panel):
    """Displays the Main Panel for Object Properties"""
    bl_label : str = get_id("panel_context_properties")
    
    def draw_header(self, context : Context) -> None :
        self.layout.label(icon='PROPERTIES')
    
    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        draw_wrapped_text_col(l,get_id('introduction_message'),max_chars=40, icon='WARNING_LARGE', title='KitsuneSourceTool (Alpha 2.0)')

class ExportableConfigurationPanel(KITSUNE_PT_CustomToolPanel, Panel):
    bl_label : str = ''
    bl_parent_id : str = "SMD_PT_ContextObject"
    bl_options : Any = {'DEFAULT_CLOSED'}

class SMD_PT_Object(ExportableConfigurationPanel):
    bl_label : str = get_id("panel_context_object")
    
    def draw_header(self, context : Context) -> None:
        self.layout.label(icon='OBJECT_DATA')
        
    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        bx : UILayout = draw_title_box(l, SMD_PT_Object.bl_label)
        ob : Object | None = context.object
        
        if not ob:
            draw_wrapped_text_col(bx,get_id("panel_select_object"),max_chars=40 , icon='HELP')
            return
        
        bx.box().label(text=f'Active Object: ({ob.name})')

class SMD_PT_Mesh(ExportableConfigurationPanel):
    bl_label : str = get_id("panel_context_mesh")
    
    def draw_header(self, context : Context) -> None:
        self.layout.label(icon='MESH_DATA')
        
    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        ob : Object | None = context.object
        bx : UILayout = draw_title_box(l, SMD_PT_Mesh.bl_label)
        
        if is_mesh(ob): pass
        else:
            draw_wrapped_text_col(bx,get_id("panel_select_mesh"),max_chars=40 , icon='HELP')
            return
        
class DME_UL_FlexControllers(UIList):
    def draw_item(self, context: Context, layout: UILayout, data: Any | None, item: Any | None, icon: int | None, active_data: Any, active_property: str | None, index: int | None, flt_flag: int | None) -> None:
        ob : Object | None = context.object
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row : UILayout = layout.row(align=True)
            
            split1 : UILayout = row.split(factor=0.4, align=True)
            split1.prop_search(item, "shapekey", ob.data.shape_keys, "key_blocks", text="")

            split2 : UILayout = split1.split(align=True)
            split2.prop(item, "eyelid", toggle=True)
            split2.prop(item, "stereo", toggle=True)

        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=item.shapekey)
            
class DME_OT_AddFlexController(Operator):
    bl_idname : str = "dme.add_flexcontroller"
    bl_label : str = "Add Flex Controller"
    bl_options : Set = {'INTERNAL', 'UNDO'}  

    def execute(self, context : Context) -> Set:
        ob : Object | None = context.object

        new_item = ob.vs.dme_flexcontrollers.add()
        ob.vs.dme_flexcontrollers_index = len(ob.vs.dme_flexcontrollers) - 1
        new_item.shapekey = ""
        return {'FINISHED'}

class DME_OT_RemoveFlexController(Operator):
    bl_idname : str = "dme.remove_flexcontroller"
    bl_label : str = "Remove Flex Controller"
    bl_options : Set = {'INTERNAL', 'UNDO'}  

    @classmethod
    def poll(cls, context : Context) -> bool:
        ob : Object | None = context.object
        return bool(ob and hasattr(ob, "vs") and len(ob.vs.dme_flexcontrollers) > 0)

    def execute(self, context : Context) -> Set:
        ob : Object | None = context.object

        idx : int = ob.vs.dme_flexcontrollers_index
        ob.vs.dme_flexcontrollers.remove(idx)
        ob.vs.dme_flexcontrollers_index = max(0, idx - 1)
        return {'FINISHED'}

class SMD_PT_ShapeKeys(ExportableConfigurationPanel):
    bl_label : str = get_id("exportables_flex_props")
    bl_parent_id : str = "SMD_PT_Mesh"
    
    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        bx : UILayout = draw_title_box(l, SMD_PT_ShapeKeys.bl_label)
        item = context.object
        
        if is_mesh(item) and hasShapes(item): pass
        else:
            draw_wrapped_text_col(bx,get_id("panel_select_mesh_sk"),max_chars=40 , icon='HELP')
            return
        
        col = bx.column()
        col.prop(item.data.vs, "bake_shapekey_as_basis_normals", toggle=True, icon='NORMALS_FACE')
        col.prop(item.data.vs, "normalize_shapekeys", toggle=True, icon='NORMALS_VERTEX')
        col.row().prop(item.vs,"flex_controller_mode",expand=True)

        def insertCorrectiveUi(parent):
            col = parent.column(align=True)
            col.operator(AddCorrectiveShapeDrivers.bl_idname, icon='DRIVER',text=get_id("gen_drivers",True))
            col.operator(RenameShapesToMatchCorrectiveDrivers.bl_idname, icon='SYNTAX_OFF',text=get_id("apply_drivers",True))
            
        if item.vs.flex_controller_mode == 'ADVANCED':
            controller_source = col.row()
            controller_source.alert = hasFlexControllerSource(item.vs.flex_controller_source) == False
            controller_source.prop(item.vs,"flex_controller_source",text=get_id("exportables_flex_src"),icon = 'TEXT' if item.vs.flex_controller_source in bpy.data.texts else 'NONE')
            
            row = col.row(align=True)
            row.operator(DmxWriteFlexControllers.bl_idname,icon='TEXT',text=get_id("exportables_flex_generate", True))
            row.operator("wm.url_open",text=get_id("exportables_flex_help", True),icon='HELP').url = "http://developer.valvesoftware.com/wiki/Blender_SMD_Tools_Help#Flex_properties"
            
            insertCorrectiveUi(col)
            
            col = bx.column()
            subbx = col.box()
            
            subbx.label(text=get_id("exportables_flex_split"))
            sharpness_col = subbx.column(align=True)
            
            r = sharpness_col.split(factor=0.33,align=True)
            r.label(text=item.data.name + ":",icon=MakeObjectIcon(item,suffix='_DATA'),translate=False) # type: ignore
            r2 = r.split(factor=0.7,align=True)
            
            if item.data.vs.flex_stereo_mode == 'VGROUP':
                r2.alert = item.vertex_groups.get(item.data.vs.flex_stereo_vg) is None
                r2.prop_search(item.data.vs,"flex_stereo_vg",item,"vertex_groups",text="")
            else:
                r2.prop(item.data.vs,"flex_stereo_sharpness",text="Sharpness")
                
            r2.prop(item.data.vs,"flex_stereo_mode",text="")
            
        elif item.vs.flex_controller_mode == 'STRICT':
            col = bx.column()
            col.label(text='Flex Controllers')
            draw_wrapped_text_col(col,'Empty List will export the object without shapekeys',32,icon='HELP')
            
            col.template_list("DME_UL_FlexControllers","",item.vs,"dme_flexcontrollers", item.vs,"dme_flexcontrollers_index",rows=3,)

            row = col.row(align=True)
            row.operator("dme.add_flexcontroller", icon='ADD')
            row.operator("dme.remove_flexcontroller", icon='REMOVE')
            
        else:
            insertCorrectiveUi(col)
        
        num_shapes, num_correctives = countShapes(item)
        
        col.separator()
        row = col.row()
        row.alignment = 'CENTER'
        row.label(icon='SHAPEKEY_DATA',text = get_id("exportables_flex_count", True).format(num_shapes))
        
        if item.vs.flex_controller_mode != 'STRICT':
            row.label(icon='SHAPEKEY_DATA',text = get_id("exportables_flex_count_corrective", True).format(num_correctives))

class SMD_PT_VertexMaps(ExportableConfigurationPanel):
    bl_label : str = get_id("vertmap_group_props")
    bl_parent_id : str = "SMD_PT_Mesh"

    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        bx : UILayout = draw_title_box(l, SMD_PT_VertexMaps.bl_label)
        ob : Object | None = context.object
        if is_mesh(ob): pass
        else:
            draw_wrapped_text_col(bx,get_id("panel_select_mesh"),max_chars=40 , icon='HELP')
            return
        
        col = bx.column(align=True)
        
        if State.exportFormat != ExportFormat.DMX:
            col.box().label(text='Only Applicable in DMX', icon='ERROR')
            col.alert = True
        
        for map_name in vertex_maps:
            r = col.row()
            r.label(text=get_id(map_name),icon='GROUP_VCOL')
            
            add_remove = r.row(align=True)
            add_remove.operator(SMD_OT_CreateVertexMap_idname + map_name,icon='ADD',text="")
            add_remove.operator(SMD_OT_RemoveVertexMap_idname + map_name,icon='REMOVE',text="")
            add_remove.operator(SMD_OT_SelectVertexMap_idname + map_name,text="Activate")

class SMD_OT_AddVertexMapRemap(Operator):
    bl_idname : str = "smd.add_vertex_map_remap"
    bl_label : str = "Add Remap Range"

    map_name: bpy.props.StringProperty()

    def execute(self, context : Context) -> Set:
        active_object = context.object
        if active_object and active_object.type == 'MESH':
            group = active_object.vs.vertex_map_remaps.add()
            group.group = self.map_name
            group.min = 0.0
            group.max = 1.0
        return {'FINISHED'}

class SMD_PT_FloatMaps(ExportableConfigurationPanel):
    bl_label : str = get_id("vertmap_group_props_float")
    bl_parent_id : str = "SMD_PT_Mesh"
    
    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        bx : UILayout = draw_title_box(l, SMD_PT_FloatMaps.bl_label)
        
        ob = context.active_object
        if ob: pass
        else:
            draw_wrapped_text_col(bx,"No Mesh Selected",max_chars=40 , icon='HELP')
            return
        
        col = bx.column()
        
        col.operator("wm.url_open", text=get_id("help", True), icon='HELP').url = "http://developer.valvesoftware.com/wiki/DMX/Source_2_Vertex_attributes"
    
        col = bx.column(align=False)
        if State.compiler != Compiler.MODELDOC or State.exportFormat != ExportFormat.DMX:
            messages = 'Only Applicable in Source 2 and DMX'
            draw_wrapped_text_col(col, messages, 32, alert=True, icon='ERROR')
            col.active = False

        col = col.column(align=True)
        for map_name in vertex_float_maps:
            r = col.row(align=True)
            r.operator(SMD_OT_SelectVertexFloatMap_idname + map_name, text=map_name.replace("cloth_", "").replace("_", " ").title(), icon='GROUP_VERTEX')
            add_remove = r.row(align=True)
            add_remove.operator(SMD_OT_CreateVertexFloatMap_idname + map_name, icon='ADD', text="")
            add_remove.operator(SMD_OT_RemoveVertexFloatMap_idname + map_name, icon='REMOVE', text="")
            
            found = False
            for group in ob.vs.vertex_map_remaps:
                if group.group == map_name:
                    found = True
                    r.prop(group, "min")
                    r.prop(group, "max")
                    break

            if not found:
                r.operator("smd.add_vertex_map_remap").map_name = map_name
            
class SMD_PT_Curves(ExportableConfigurationPanel):
    bl_label : str = get_id("exportables_curve_props")
    
    def draw_header(self, context : Context) -> None:
        self.layout.label(icon='CURVE_DATA')
    
    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        bx : UILayout = draw_title_box(l, SMD_PT_Curves.bl_label)
        
        if is_curve(context.object) and hasCurves(context.object): pass
        else:
            draw_wrapped_text_col(bx,get_id("panel_select_curve"),max_chars=40 , icon='HELP')
            return
        
        done = set()
        
        row = bx.split(factor=0.33)
        row.label(text=context.object.data.name + ":",icon=MakeObjectIcon(context.object,suffix='_DATA'),translate=False) # type: ignore
        row.prop(context.object.data.vs,"faces",text="")
        done.add(context.object.data)

class SMD_PT_Materials(ExportableConfigurationPanel):
    bl_label : str = get_id("panel_context_material")

    def draw_header(self, context : Context) -> None:
        self.layout.label(icon='MATERIAL_DATA')
    
    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        bx : UILayout = draw_title_box(l, SMD_PT_Materials.bl_label)
        ob : Object | None = context.object
        if ob is None: return
        if is_mesh(ob) and has_materials(ob): pass
        else:
            draw_wrapped_text_col(bx,get_id("panel_select_mesh_mat"),max_chars=40 , icon='HELP')
            return
        
        currMat = ob.active_material
        bx.box().label(text=f'Active Material: ({currMat.name})')
        
        col = bx.column(align=True)
        col.prop(currMat.vs, 'do_not_export_faces')
        col.prop(currMat.vs, 'do_not_export_faces_vgroup')
        
        if not currMat.vs.do_not_export_faces:
            col = bx.column()
            col.prop(currMat.vs, 'override_dmx_export_path')
            col.prop(currMat.vs, 'non_exportable_vgroup')     
            
class SMD_PT_Bones(ExportableConfigurationPanel):
    bl_label : str = get_id("panel_context_bone")
    
    def draw_header(self, context : Context) -> None:
        self.layout.label(icon='BONE_DATA')
    
    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        bx : UILayout = draw_title_box(l, SMD_PT_Bones.bl_label)
        ob : Object | None = context.object
        
        if is_armature(ob): pass
        else:
            draw_wrapped_text_col(bx,get_id("panel_select_armature"),max_chars=40 , icon='HELP')
            return
            
        try:
            bone : bpy.types.Bone | None = ob.data.bones.active if context.mode != 'EDIT_ARMATURE' else ob.data.bones.get(ob.data.edit_bones.active.name)
        except:
            bone = None
        
        if bone is not None:
            bx.prop(ob.data.vs, "ignore_bone_exportnames", toggle=True)
            draw_wrapped_text_col(bx,'Ignore bone export name affects all bones',max_chars=40 , icon='ERROR')
            subbx = bx.box()  
            subbx.label(text=f'Active Bone: {bone.name}')
            subbx.separator(type='LINE')
            subbx.label(text=f'Export Name : {getBoneExportName(bone)}')

            if context.mode != 'EDIT_ARMATURE':
                col = bx.column(align=False)
                col.prop(bone.vs, 'export_name')
                row = col.split(align=True, factor=0.4)
                row.label(text='Direction Naming:')
                row.prop(ob.data.vs, 'bone_direction_naming_left',text='')
                row.prop(ob.data.vs, 'bone_direction_naming_right',text='')
                col.prop(ob.data.vs, 'bone_name_startcount', slider=True)
                
                row = bx.row(align=True)
                col = row.column(align=True)
                col.prop(bone.vs, 'ignore_location_offset', toggle=True)
                
                col = col.column(align=True)
                if bone.vs.ignore_location_offset: col.active = False
                col.prop(bone.vs, 'export_location_offset_x')
                col.prop(bone.vs, 'export_location_offset_y')
                col.prop(bone.vs, 'export_location_offset_z')
                
                col = row.column(align=True)
                col.prop(bone.vs, 'ignore_rotation_offset', toggle=True)
                
                col = col.column(align=True)
                if bone.vs.ignore_rotation_offset: col.active = False
                col.prop(bone.vs, 'export_rotation_offset_x')
                col.prop(bone.vs, 'export_rotation_offset_y')
                col.prop(bone.vs, 'export_rotation_offset_z')
                
                col = bx.column()
                draw_wrapped_text_col(
                    col,
                    'Bones rotate on export in Z→Y→X order (translation remains X→Y→Z). Use "normal" in edit mode to check. Z+90° from Y-forward → X-forward.',
                    max_chars=36)
                
                col = bx.column()
                col.prop(bone, 'use_deform', toggle=True)

            else:
                col = bx.column(align=True)
                messages = 'Bone Properties is not editable in Edit Mode'
                draw_wrapped_text_col(col, messages, max_chars=32, alert=True,icon='ERROR')
        else:
            bx.label(text='Select a Valid Bone')
 
class SMD_PT_Empty(ExportableConfigurationPanel):
    bl_label : str = get_id('panel_context_empty')

    def draw_header(self, context : Context) -> None:
        self.layout.label(icon='EMPTY_DATA')

    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        bx : UILayout = draw_title_box(l, SMD_PT_Empty.bl_label)
        ob : Object | None = context.object
        
        if is_empty(ob): pass
        else:
            draw_wrapped_text_col(bx,get_id("panel_select_empty"),max_chars=40 , icon='HELP')
            return
        
        col : UILayout = bx.column()
        
        col.prop(ob.vs, 'dmx_attachment', toggle=False)
        col.prop(ob.vs, 'smd_hitbox', toggle=False)
        
        if ob.vs.smd_hitbox:
            col.prop(ob.vs, 'smd_hitbox_group', text='Hitbox Group')
        
        if ob.vs.dmx_attachment and ob.children:
            col.alert = True
            col.box().label(text="Attachment cannot be a parent",icon='WARNING_LARGE')
