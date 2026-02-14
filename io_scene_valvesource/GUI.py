#  Copyright (c) 2014 Tom Edwards contact@steamreview.org
#
# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

import bpy
from .utils import *
from .export_smd import SmdExporter, SMD_OT_Compile
from .flex import *
from bpy.props import StringProperty, BoolProperty, EnumProperty, IntProperty, CollectionProperty, FloatProperty, PointerProperty

from bpy.types import UILayout, Context

from .kitsunetools.commonutils import sanitize_string

vca_icon = 'EDITMODE_HLT'

class SMD_MT_ExportChoice(bpy.types.Menu):
    bl_label = get_id("exportmenu_title")

    def draw(self, context : Context) -> None:
        l = self.layout
        l.operator_context = 'EXEC_DEFAULT'
        
        exportables = list(getSelectedExportables())
        if len(exportables):
            single_obs = list([ex for ex in exportables if ex.ob_type != 'COLLECTION'])
            groups = list([ex for ex in exportables if ex.ob_type == 'COLLECTION'])
            groups.sort(key=lambda g: g.name.lower())
                
            group_layout = l
            for i,group in enumerate(groups): # always display all possible groups, as an object could be part of several
                if type(self) == SMD_PT_Scene:
                    if i == 0: group_col = l.column(align=True)
                    if i % 2 == 0: group_layout = group_col.row(align=True)
                group_layout.operator(SmdExporter.bl_idname, text=group.name, icon='GROUP').collection = group.item.name
                
            if len(exportables) - len(groups) > 1:
                l.operator(SmdExporter.bl_idname, text=get_id("exportmenu_selected", True).format(len(exportables)), icon='OBJECT_DATA')
            elif len(single_obs):
                l.operator(SmdExporter.bl_idname, text=single_obs[0].name, icon=single_obs[0].icon)
        elif len(bpy.context.selected_objects):
            row = l.row()
            row.operator(SmdExporter.bl_idname, text=get_id("exportmenu_invalid"),icon='BLANK1')
            row.enabled = False

        row = l.row()
        num_scene_exports = count_exports(context)
        row.operator(SmdExporter.bl_idname, text=get_id("exportmenu_scene", True).format(num_scene_exports), icon='SCENE_DATA').export_scene = True
        row.enabled = num_scene_exports > 0

class SMD_PT_Scene(bpy.types.Panel):
    bl_label = get_id("exportpanel_title")
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context : Context) -> None:
        l = self.layout
        scene = context.scene

        col = l.column()
        col.operator(SmdExporter.bl_idname,text="Export")
        
        row = l.row()
        row.alert = len(scene.vs.export_path) == 0
        row.prop(scene.vs,"export_path")
        
        if State.datamodelEncoding != 0:
            row = l.row().split(factor=0.33)
            row.label(text=get_id("export_format") + ":")
            row.row().prop(scene.vs,"export_format",expand=True)
        row = l.row().split(factor=0.33)
        row.label(text=get_id("up_axis") + ":")
        row.row().prop(scene.vs,"up_axis", expand=True)
        
        row = l.row().split(factor=0.33)
        row.label(text=get_id("up_axis_offset") + ":")
        row.row().prop(scene.vs,"up_axis_offset", expand=True)
        
        row = l.row().split(factor=0.33)
        row.label(text=get_id("forward_axis") + ":")
        row.row().prop(scene.vs,"forward_axis", expand=True)
        
        row = l.row()
        row.alert = len(scene.vs.engine_path) > 0 and State.compiler == Compiler.UNKNOWN
        row.prop(scene.vs,"engine_path")
        
        if scene.vs.export_format == 'DMX':
            if State.engineBranch is None:
                row = l.split(factor=0.33)
                row.label(text=get_id("exportpanel_dmxver"))
                row = row.row(align=True)
                row.prop(scene.vs,"dmx_encoding",text="")
                row.prop(scene.vs,"dmx_format",text="")
                row.enabled = not row.alert
            if State.exportFormat == ExportFormat.DMX:
                col = l.column()
                col.prop(scene.vs,"material_path")
        else:
            row = l.split(factor=0.33)
            row.label(text=get_id("smd_format") + ":")
            row.row().prop(scene.vs,"smd_format", expand=True)
        
        col = l.column()
        col.prop(scene.vs,"weightlink_threshold",slider=True)
        col.prop(scene.vs,"vertex_influence_limit",slider=True)
        
        col = l.column(align=True)
        row = col.row(align=True)
        self.draw_urls(layout=l)
        
    @staticmethod
    def draw_urls(layout : UILayout):
        row = layout.row()
        
        op1 = row.operator("wm.url_open", text=get_id("help",True), icon='INTERNET')
        op1.url = "http://developer.valvesoftware.com/wiki/Blender_Source_Tools_Help#Exporting"
        
        op2 = row.operator("wm.url_open", text=get_id("exportpanel_steam",True), icon='INTERNET')
        op2.url = "http://steamcommunity.com/groups/BlenderSourceTools"
        
class SMD_MT_ConfigureScene(bpy.types.Menu):
    bl_label = get_id("exporter_report_menu")
    def draw(self, context : Context) -> None:
        self.layout.label(text=get_id("exporter_err_unconfigured"))
        SMD_PT_Scene.HelpButton(self.layout)

class SMD_UL_ExportItems(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index, flt_flag):
        obj = item.item
        is_collection = isinstance(obj, bpy.types.Collection)
        enabled = not (is_collection and obj.vs.mute)
        
        col = layout.column()
        split1 = self._draw_header_row(col, obj, item, enabled, index)
        
        if enabled:
            self._draw_stats_row(split1, obj)
    
    def _draw_header_row(self, col : UILayout, obj : bpy.types.Object, item, enabled, index):
        row = col.row(align=True)
        
        export_icon = 'CHECKBOX_HLT' if obj.vs.export and enabled else 'CHECKBOX_DEHLT'
        row.prop(obj.vs, "export", icon=export_icon, text="", emboss=False)
        row.label(text='', icon=item.icon)
        
        split1 = row.split(factor=0.8)
        split1.alert = not enabled
        split1.label(text=sanitize_string(item.name))
        
        return split1
    
    def _draw_stats_row(self, split1 : UILayout, obj):
        row = split1.row(align=True)
        row.alignment = 'RIGHT'
        
        num_shapes, num_correctives = countShapes(obj)
        total_shapes = num_shapes + num_correctives
        if total_shapes > 0:
            row.label(text=str(total_shapes), icon='SHAPEKEY_DATA')
        
        num_vca = len(obj.vs.vertex_animations)
        if num_vca > 0:
            row.label(text=str(num_vca), icon=vca_icon)
            
class SMD_OT_ShowExportCollection(bpy.types.Operator):
    """Toggle visibility of expanded UIList items (no undo)"""
    bl_idname = "smd.show_exportableitems"
    bl_label = 'Show Options'
    bl_options = {'INTERNAL'}

    index: bpy.props.IntProperty()

    def execute(self, context) -> set:
        export_list = context.scene.vs.export_list
        current_obj = export_list[self.index].item
        current_state = current_obj.vs.show_items
        
        for item in export_list:
            item.item.vs.show_items = False
        
        current_obj.vs.show_items = not current_state
        return {'FINISHED'}
    
class SMD_OT_ShowVertexAnimation(bpy.types.Operator):
    """Toggle visibility of expanded UIList items (no undo)"""
    bl_idname = "smd.show_vertexanims"
    bl_label = 'Show Options'
    bl_options = {'INTERNAL'}

    index: bpy.props.IntProperty()

    def execute(self, context) -> set:
        obj = context.scene.vs.export_list[self.index].item
        obj.vs.show_vertexanim_items = not obj.vs.show_vertexanim_items
        return {'FINISHED'}

class FilterCache:
    def __init__(self):
        self.state_objects = State.exportableObjects

    fname = None
    filter = None
    order = None

gui_cache = {}
class SMD_UL_GroupItems(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index, flt_flag):
        r = layout.row(align=True)
        r.prop(item.vs,"export",text="",icon='CHECKBOX_HLT' if item.vs.export else 'CHECKBOX_DEHLT',emboss=False)
        r.label(text=item.name,translate=False,icon=MakeObjectIcon(item,suffix="_DATA"))
    
    def filter_items(self, context, data, propname):
        fname = self.filter_name.lower()
        cache = gui_cache.get(data)

        if not (cache and cache.fname == fname and cache.state_objects is State.exportableObjects):
            cache = FilterCache()
            cache.filter = [self.bitflag_filter_item if ob.session_uid in State.exportableObjects and (not fname or fname in ob.name.lower()) else 0 for ob in data.objects]
            cache.order = bpy.types.UI_UL_list.sort_items_by_name(data.objects)
            cache.fname = fname
            gui_cache[data] = cache
            
        return cache.filter, cache.order if self.use_filter_sort_alpha else []

class SMD_PT_Object_Config(bpy.types.Panel):
	bl_label = get_id('exportables_title')
	bl_space_type = "PROPERTIES"
	bl_region_type = "WINDOW"
	bl_context = "scene"
	bl_options = {'DEFAULT_CLOSED'}
	
	def draw(self,context):
		l = self.layout
		scene = context.scene
		
		l.template_list("SMD_UL_ExportItems","",scene.vs,"export_list",scene.vs,"export_list_active",rows=3,maxrows=8)
				
		active_exportable = get_active_exportable(context)
		if not active_exportable:
			return

		item = active_exportable.item

class ExportableConfigurationPanel(bpy.types.Panel):
	bl_space_type = "PROPERTIES"
	bl_region_type = "WINDOW"
	bl_context = "scene"
	bl_parent_id = "SMD_PT_Object_Config"
	bl_options = {'DEFAULT_CLOSED'}
	vs_icon = ""

	@classmethod
	def get_item(cls, context):
		active_exportable = get_active_exportable(context)
		if not active_exportable:
			return

		return active_exportable.item

	@classmethod
	def poll(cls, context):
		return (cls.get_item(context) is not None)

	@classmethod
	def is_collection(cls, item):
		return isinstance(item, bpy.types.Collection)

	@classmethod
	def get_active_object(cls, context):
		item = cls.get_item(context)
		
		if not cls.is_collection(item):
			return item
		
		ob = context.active_object
		if ob and ob.name in item.objects:
			return ob

	@classmethod
	def unpack_collection(cls, context):
		item = cls.get_item(context)
		return [ob for ob in item.objects if ob.session_uid in State.exportableObjects] if cls.is_collection(item) else [item]

	def draw_header(self, context):
		if self.vs_icon:
			self.layout.label(icon=self.vs_icon)	


class SMD_PT_Group(ExportableConfigurationPanel):
	bl_label = get_id("exportables_group_props")
	bl_options = set() # override
	vs_icon = 'GROUP'

	@classmethod
	def poll(cls, context):
		item = cls.get_item(context)
		return item and cls.is_collection(item)

	def draw(self, context):
		item = self.get_item(context)
		if not item.vs.mute:				
			self.layout.template_list("SMD_UL_GroupItems",item.name,item,"objects",item.vs,"selected_item",columns=2,rows=2,maxrows=10)
		
		r = self.layout.row()
		r.alignment = 'CENTER'
		r.prop(item.vs,"mute")
		if item.vs.mute:
			return
		elif State.exportFormat == ExportFormat.DMX:
			r.prop(item.vs,"automerge")


class SMD_PT_Prefabs(bpy.types.Panel):
    bl_label = "Source Engine Prefabs"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        l = self.layout
        scene = context.scene

        row = l.row()
        col = row.column(align=True)
        col.template_list("SMD_UL_Prefabs", "", scene.vs, "smd_prefabs", scene.vs, "smd_prefabs_index")
        
        col = row.column(align=True)
        col.operator(SMD_OT_AddPrefab.bl_idname, icon="ADD", text='')
        col.operator(SMD_OT_RemovePrefab.bl_idname, icon="REMOVE", text='')
        col.separator()
        col.operator(SMD_OT_MovePrefabUp.bl_idname, icon="TRIA_UP", text='')
        col.operator(SMD_OT_MovePrefabDown.bl_idname, icon="TRIA_DOWN", text='')

        if scene.vs.smd_prefabs_index >= 0 and scene.vs.smd_prefabs_index < len(scene.vs.smd_prefabs):
            active_prefab = scene.vs.smd_prefabs[scene.vs.smd_prefabs_index]
            row = l.row()
            if not active_prefab.filepath:
                row.alert = True
            row.prop(active_prefab, "filepath", text="Prefab File", icon='FILE')


class SMD_UL_Prefabs(bpy.types.UIList):
    bl_idname = "SMD_UL_Prefabs"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row : UILayout = layout.row(align=True)
        
        if item.filepath:
            import os
            display_name = os.path.basename(item.filepath)
        else:
            display_name = f"Prefab {index + 1}"
        row.label(text=display_name, icon='FILE')


class SMD_OT_AddPrefab(bpy.types.Operator):
    bl_idname = "smd.add_prefab"
    bl_label = "Add Prefab"

    def execute(self, context) -> set:
        context.scene.vs.smd_prefabs.add()
        return {'FINISHED'}


class SMD_OT_RemovePrefab(bpy.types.Operator):
    bl_idname = "smd.remove_prefab"
    bl_label = "Remove Prefab"

    @classmethod
    def poll(cls, context):
        return len(context.scene.vs.smd_prefabs) > 0 and context.scene.vs.smd_prefabs_index >= 0
    
    def execute(self, context) -> set:
        context.scene.vs.smd_prefabs.remove(context.scene.vs.smd_prefabs_index)
        context.scene.vs.smd_prefabs_index = min(max(0, context.scene.vs.smd_prefabs_index - 1), 
                                                 len(context.scene.vs.smd_prefabs) - 1)
        return {'FINISHED'}


class SMD_OT_MovePrefabUp(bpy.types.Operator):
    bl_idname = "smd.move_prefab_up"
    bl_label = "Move Prefab Up"

    @classmethod
    def poll(cls, context):
        return context.scene.vs.smd_prefabs_index > 0

    def execute(self, context) -> set:
        prefabs = context.scene.vs.smd_prefabs
        index = context.scene.vs.smd_prefabs_index
        prefabs.move(index, index - 1)
        context.scene.vs.smd_prefabs_index = index - 1
        return {'FINISHED'}


class SMD_OT_MovePrefabDown(bpy.types.Operator):
    bl_idname = "smd.move_prefab_down"
    bl_label = "Move Prefab Down"

    @classmethod
    def poll(cls, context):
        prefabs = context.scene.vs.smd_prefabs
        return context.scene.vs.smd_prefabs_index < len(prefabs) - 1

    def execute(self, context) -> set:
        prefabs = context.scene.vs.smd_prefabs
        index = context.scene.vs.smd_prefabs_index
        prefabs.move(index, index + 1)
        context.scene.vs.smd_prefabs_index = index + 1
        return {'FINISHED'}


class SMD_PT_Scene_QC_Complie(bpy.types.Panel):
    bl_label = get_id("qc_title")
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_options = {'DEFAULT_CLOSED'}

    searchPath = None
    lastPathRow = None
    qcFiles = None
    lastUpdate = 0.0
        
    def draw(self,context):
        l = self.layout
        scene = context.scene
        
        if State.compiler == Compiler.UNKNOWN:
            if len(scene.vs.engine_path):
                l.label(icon='ERROR',text=get_id("qc_bad_enginepath"))
            else:
                l.label(icon='INFO',text=get_id("qc_no_enginepath"))
            return

        if State.compiler > Compiler.STUDIOMDL:
            l.enabled = False
            l.label(icon='INFO',text=get_id("qc_invalid_source2"))
            return
            
        row = l.row()
        row.alert = len(scene.vs.game_path) and State.gamePath is None
        row.prop(scene.vs,"game_path")
        
        if not len(scene.vs.game_path) and State.gamePath is None:
            row = l.row()
            row.label(icon='ERROR',text=get_id("qc_nogamepath"))
            row.enabled = False
            return
        
        # QCs
        filesRow = l.row()
        if scene.vs.qc_path != self.searchPath or self.qcFiles is None or time.time() > self.lastUpdate + 2:
            self.qcFiles = SMD_OT_Compile.getQCs()
            self.searchPath = scene.vs.qc_path
        self.lastUpdate = time.time()
    
        if self.qcFiles:
            c = l.column_flow(columns=2)
            c.operator_context = 'EXEC_DEFAULT'
            for path in self.qcFiles:
                c.operator(SMD_OT_Compile.bl_idname,text=os.path.basename(path),translate=False).filepath = path
        
        compile_row = l.row()
        compile_row.prop(scene.vs,"qc_compile")
        compile_row.operator_context = 'EXEC_DEFAULT'
        compile_row.operator(SMD_OT_Compile.bl_idname,text=get_id("qc_compilenow", True),icon='FILE_TEXT').filepath="*"
        
        if not self.qcFiles:
            if scene.vs.qc_path:
                filesRow.alert = True
            compile_row.enabled = False
        filesRow.prop(scene.vs,"qc_path") # can't add this until the above test completes!
        
        l.operator(SMD_OT_LaunchHLMV.bl_idname,icon='PREFERENCES',text=get_id("launch_hlmv",True))
