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

from .. import iconloader

from .. import format_version

from bpy.props import IntProperty

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

class ValidationChecker:
    @staticmethod
    def is_valid_name(name: str) -> bool:
        for char in name:
            if not (char.isascii() and (char.isalnum() or char in (' ', '_'))):
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
            armature = getArmature(armature_obj)
        else:
            armature = armature_obj
            
        if armature is None: 
            return invalid_names
        
        for bone in armature.data.bones:
            if not ValidationChecker.is_valid_name(bone.name):
                invalid_names['bones'].append(bone.name)
                
        if not ValidationChecker.is_valid_name(armature.name):
            invalid_names['armature'].append(armature.name)
            
        meshes = getArmatureMeshes(armature)
        for mesh in meshes:
            if not ValidationChecker.is_valid_name(mesh.name):
                invalid_names['meshes'].append(mesh.name)
            
            for mat in mesh.data.materials:
                if mat and not ValidationChecker.is_valid_name(mat.name):
                    invalid_names['materials'].append(mat.name)
            
            if mesh.data.shape_keys:
                for key in mesh.data.shape_keys.key_blocks:
                    if not ValidationChecker.is_valid_name(key.name):
                        invalid_names['shapekeys'].append(key.name)
        
        return invalid_names

    @staticmethod
    def count_warnings(context: Context) -> int:
        count = 0
        
        if is_armature(context.object):
            conflictProceduralBones = get_conflicting_clothjiggle(context.object)
            if conflictProceduralBones and len(conflictProceduralBones) > 0:
                count += 1
        
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
    def draw_conflicting_procedural_bones(layout: UILayout, armature_obj) -> int:
        if not is_armature(armature_obj):
            return 0
            
        conflictProceduralBones = get_conflicting_clothjiggle(armature_obj)
        if conflictProceduralBones:
            draw_wrapped_text_col(layout, f'Bone(s): {", ".join(conflictProceduralBones)} is/are marked as Jigglebone and Cloth!', alert=True)
            return 1
        return 0
    
    @staticmethod
    def draw_invalid_names(layout: UILayout, invalid_names: dict) -> int:
        count = 0
        
        if invalid_names['armature']:
            draw_wrapped_text_col(layout, f'Armature Name: {", ".join(invalid_names["armature"])}{WarningRenderer.INVALID_CHAR_MESSAGE}', alert=True)
            count += 1
        
        if invalid_names['bones']:
            draw_wrapped_text_col(layout, f'Bone(s): {", ".join(invalid_names["bones"])}{WarningRenderer.INVALID_CHAR_MESSAGE}', alert=True)
            count += 1
        
        if invalid_names['meshes']:
            draw_wrapped_text_col(layout, f'Mesh Object(s): {", ".join(invalid_names["meshes"])}{WarningRenderer.INVALID_CHAR_MESSAGE}', alert=True)
            count += 1
        
        if invalid_names['materials']:
            draw_wrapped_text_col(layout, f'Material(s): {", ".join(invalid_names["materials"])}{WarningRenderer.INVALID_CHAR_MESSAGE}', alert=True)
            count += 1
        
        if invalid_names['shapekeys']:
            draw_wrapped_text_col(layout, f'Shapekey(s): {", ".join(invalid_names["shapekeys"])}{WarningRenderer.INVALID_CHAR_MESSAGE}', alert=True)
            count += 1
        
        return count
    
    @staticmethod
    def draw_unparented_items(layout: UILayout) -> int:
        count = 0
        
        unparented_hitboxes = get_unparented_hitboxes()
        if unparented_hitboxes:
            draw_wrapped_text_col(layout, f'Hitbox(es): {", ".join(unparented_hitboxes)} must be parented to a bone!', alert=True)
            count += 1
        
        unparented_attachments = get_unparented_attachments()
        if unparented_attachments:
            draw_wrapped_text_col(layout, f'Attachment(s): {", ".join(unparented_attachments)} must be parented to a bone!', alert=True)
            count += 1
        
        return count
    
    @staticmethod
    def draw_bugged_items(layout: UILayout) -> int:
        count = 0
        
        bugged_hitboxes = get_bugged_hitboxes()
        if bugged_hitboxes:
            draw_wrapped_text_col(layout, f'Hitbox(es): {", ".join(bugged_hitboxes)} have incorrect matrix (world-space instead of bone-relative). Use Fix Hitboxes operator!', alert=True)
            count += 1
        
        bugged_attachments = get_bugged_attachments()
        if bugged_attachments:
            draw_wrapped_text_col(layout, f'Attachment(s): {", ".join(bugged_attachments)} have incorrect matrix (world-space instead of bone-relative). Use Fix Attachments operator!', alert=True)
            count += 1
        
        return count

class SMD_PT_ContextObject(KITSUNE_PT_CustomToolPanel, Panel):
    """Displays the Main Panel for Object Properties"""
    bl_label : str = get_id("panel_context_properties")
    
    def draw_header(self, context : Context) -> None :
        self.layout.label(icon='PROPERTIES')
    
    def draw(self, context : Context) -> None:
        l : UILayout = self.layout
        
        addonver, addondevstate = format_version()
        draw_wrapped_text_col(l, get_id('introduction_message'), max_chars=38, title=f'KitsuneSourceTool {addonver}_{addondevstate}')
        
        prophelpsection : UILayout = create_toggle_section(l, context.scene.vs, 'show_properties_help', f'Show Tips', '', icon='HELP')
        if context.scene.vs.show_properties_help:
            help_text = [
                '- Selecting multiple objects or bones and changing a property of either will be copied over to other selected of the same type.\n\n',
                '- Exporting bones with non alphanumeric character will be sanitize and can lead to issues with bone mixup.',
            ]
            draw_wrapped_text_col(prophelpsection, text="".join(help_text), max_chars=40)

        warning_count = ValidationChecker.count_warnings(context)
        has_warnings = warning_count > 0
        
        section_title = 'Show Validation Check' if warning_count == 0 else f'Show Validation Check ({warning_count})'
        warningsection : UILayout = create_toggle_section(l, context.scene.vs, 'show_objectwarnings', section_title, '', alert=has_warnings, icon='SCENE_DATA')
        
        if context.scene.vs.show_objectwarnings:
            self.draw_warning_checks(context, warningsection)

    def draw_warning_checks(self, context: Context, layout: UILayout) -> int:
        num_warnings = 0
        
        num_warnings += WarningRenderer.draw_conflicting_procedural_bones(layout, context.object)
        
        invalid_names = ValidationChecker.get_invalid_names(context.object)
        num_warnings += WarningRenderer.draw_invalid_names(layout, invalid_names)
        
        num_warnings += WarningRenderer.draw_unparented_items(layout)
        num_warnings += WarningRenderer.draw_bugged_items(layout)
                
        if num_warnings == 0:
            draw_wrapped_text_col(layout, f'No Errors found on selected object')
            
        return num_warnings
        
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
        bx.prop(ob.vs, 'export')

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
        
        col = bx.column()
        shapekeysection = create_toggle_section(col, context.scene.vs, 'show_flex', 'Show Shapekey Conifg', icon='SHAPEKEY_DATA')
        vertexmapsection = create_toggle_section(col, context.scene.vs, 'show_vertexmap', 'Show VertexMap Conifg', icon='GROUP_VERTEX')
        floatmapssection = create_toggle_section(col, context.scene.vs, 'show_floatmaps', 'Show FloatMaps Conifg', icon='MOD_CLOTH')
        
        if context.scene.vs.show_flex:
            self.draw_shapekey_config(context,shapekeysection)
            
        if context.scene.vs.show_vertexmap:
            self.draw_vertexmap_config(context,vertexmapsection)
            
        if context.scene.vs.show_floatmaps:
            self.draw_floatmaps_config(context, floatmapssection)
            
    def draw_shapekey_config(self,context : Context, layout : UILayout):
        bx : UILayout = layout
        ob = context.object
        
        if not hasShapes(ob):
            draw_wrapped_text_col(bx,'Mesh has no Shapekeys!',alert=True,icon='ERROR')
        
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
                draw_wrapped_text_col(col,'Empty List will export the object without shapekeys',icon='HELP', boxed=False)
            
        else:
            insertCorrectiveUi(col)

        
        col.separator()
        row = col.row()
        row.alignment = 'CENTER'
        row.label(icon='SHAPEKEY_DATA',text = get_id("exportables_flex_count", True).format(num_shapes))
        
        if ob.vs.flex_controller_mode != 'STRICT':
            row.label(icon='SHAPEKEY_DATA',text = get_id("exportables_flex_count_corrective", True).format(num_correctives))
        
    def draw_vertexmap_config(self, context : Context, layout : UILayout):
        bx : UILayout = layout
        col = bx.column(align=True)
        
        if State.exportFormat != ExportFormat.DMX:
            draw_wrapped_text_col(bx,'Only Applicable in DMX!',alert=True,icon='ERROR')
        
        for map_name in vertex_maps:
            r = col.row()
            r.label(text=get_id(map_name),icon='GROUP_VCOL')
            
            add_remove = r.row(align=True)
            add_remove.operator(SMD_OT_CreateVertexMap_idname + map_name,icon='ADD',text="")
            add_remove.operator(SMD_OT_RemoveVertexMap_idname + map_name,icon='REMOVE',text="")
            add_remove.operator(SMD_OT_SelectVertexMap_idname + map_name,text="Activate")
     
    def draw_floatmaps_config(self, context : Context, layout :UILayout):
        ob = context.active_object
        col = layout.column()
        
        col.operator("wm.url_open", text=get_id("help", True), icon_value=iconloader.preview_collections["custom_icons"]["SOURCESDK"].icon_id).url = "http://developer.valvesoftware.com/wiki/DMX/Source_2_Vertex_attributes"
    
        col = layout.column(align=False)
        col.scale_y = 1.1
        if State.compiler != Compiler.MODELDOC or State.exportFormat != ExportFormat.DMX:
            messages = 'Only Applicable in Source 2 and DMX'
            draw_wrapped_text_col(col, messages, 32, alert=True, icon='ERROR')
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
    
    index : IntProperty()

    def execute(self, context : Context) -> Set:
        ob : Object | None = context.object

        ob.vs.dme_flexcontrollers.remove(self.index)
        ob.vs.dme_flexcontrollers_index = max(0, min(self.index, len(ob.vs.dme_flexcontrollers) - 1))
        return {'FINISHED'}

class SMD_OT_AddVertexMapRemap(Operator):
    bl_idname : str = "smd.add_vertex_map_remap"
    bl_label : str = "Apply Remap Range"

    map_name: bpy.props.StringProperty()

    def execute(self, context : Context) -> Set:
        active_object = context.object
        if active_object and active_object.type == 'MESH':
            group = active_object.vs.vertex_map_remaps.add()
            group.group = self.map_name
            group.min = 0.0
            group.max = 1.0
        return {'FINISHED'}

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
        
        allmats = getAllMats(ob)
        allmaterials_section = create_toggle_section(bx,context.scene.vs,'show_materials',f'Show All Materials: {len(allmats)}','',alert=not bool(allmats))
        if context.scene.vs.show_materials:
            
            if context.scene.vs.material_path.strip():
                titlebox = draw_title_box(allmaterials_section,'Default Material Path')
                titlebox.prop(context.scene.vs, 'material_path',text='', emboss=False)
            
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
                    col.prop(mat.vs,'override_dmx_export_path',icon='FOLDER_REDIRECT', placeholder=context.scene.vs.material_path)
                    if mat.vs.do_not_export_faces_vgroup:
                        col.prop(mat.vs,'non_exportable_vgroup',icon='GROUP_VERTEX')
        
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
            col.prop(currMat.vs, 'override_dmx_export_path', placeholder=context.scene.vs.material_path)
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
