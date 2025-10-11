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
from .core.commonutils import draw_wrapped_text_col, create_toggle_section
from .export_smd import SmdExporter, SMD_OT_Compile
from .flex import *
from bpy.props import StringProperty, BoolProperty, EnumProperty, IntProperty, CollectionProperty, FloatProperty, PointerProperty

from bpy.types import UILayout, Context
from . import iconloader

vca_icon = 'EDITMODE_HLT'

class SMD_MT_ExportChoice(bpy.types.Menu):
    bl_label = get_id("exportmenu_title")

    def draw(self, context):
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

    def draw(self, context):
        l = self.layout
        scene = context.scene
        num_to_export = 0

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
        
        if State.exportFormat == ExportFormat.DMX:
            l.prop(scene.vs,"use_kv2")
        
        col = l.column(align=True)
        row = col.row(align=True)
        self.HelpButton(row)
        row.operator("wm.url_open",text=get_id("exportpanel_steam",True),icon_value=iconloader.preview_collections["custom_icons"]["BLENDSRCTOOL"].icon_id).url = "http://steamcommunity.com/groups/BlenderSourceTools"

    @staticmethod
    def HelpButton(layout):
        layout.operator("wm.url_open",text=get_id("help",True),icon_value=iconloader.preview_collections["custom_icons"]["SOURCESDK"].icon_id).url = "http://developer.valvesoftware.com/wiki/Blender_Source_Tools_Help#Exporting"

class SMD_MT_ConfigureScene(bpy.types.Menu):
    bl_label = get_id("exporter_report_menu")
    def draw(self, context):
        self.layout.label(text=get_id("exporter_err_unconfigured"))
        SMD_PT_Scene.HelpButton(self.layout)

class SMD_UL_ExportItems(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index, flt_flag):
        obj = item.item
        is_collection = isinstance(obj, bpy.types.Collection)
        enabled = not (is_collection and obj.vs.mute)
        
        col = layout.column()
        
        split1 = self._draw_header_row(col, obj, item, enabled, index)
        
        if obj.vs.show_items:
            self._draw_expanded_content(col, obj, is_collection, enabled, index, item)
        
        if enabled:
            self._draw_stats_row(split1, obj)
    
    def _draw_header_row(self, col, obj, item, enabled,index):
        row = col.row(align=True)
        
        export_icon = 'CHECKBOX_HLT' if obj.vs.export and enabled else 'CHECKBOX_DEHLT'
        row.prop(obj.vs, "export", icon=export_icon, text="", emboss=False)
        row.label(text='', icon=item.icon)
        
        split1 = row.split(factor=0.8)
        split1.alert = not enabled
        toggle_icon = 'TRIA_DOWN' if obj.vs.show_items else 'TRIA_RIGHT'
        op = split1.operator(SMD_OT_ShowExportCollection.bl_idname, icon=toggle_icon, text=item.name, emboss=False)
        op.index = index
        
        return split1
    
    def _draw_expanded_content(self, col : UILayout, obj, is_collection, enabled,index,item):
        row = col.row(align=True)
        if is_collection:
            row.prop(obj.vs, 'mute',toggle=True)
        
        if is_collection and obj.vs.mute:
            pass
        else: col.prop(obj.vs, 'subdir')
        
        if is_collection:
            if enabled:
                self._draw_collection_content(col, obj, row)
                self._draw_mesh_content(col, obj,index,item)
        elif obj.type == 'ARMATURE':
            self._draw_armature_content(col, obj,index)
        elif obj.type in mesh_compatible:
            self._draw_mesh_content(col, obj,index,item)
    
    def _draw_collection_content(self, col : UILayout, obj, row):
        row.prop(obj.vs, 'automerge',toggle=True)
        
        col.label(text='Exportable Objects')
        col.template_list("SMD_UL_GroupItems", obj.name, obj, "objects", obj.vs, "selected_item", 
                         type='GRID', columns=2, rows=2, maxrows=10)
    
    def _draw_armature_content(self, col : UILayout, obj,index):
        col.row().prop(obj.data.vs, "action_selection", expand=True)
        
        if obj.data.vs.action_selection != 'CURRENT':
            is_slot_filter = obj.data.vs.action_selection == 'FILTERED' and State.useActionSlots
            filter_label = get_id("slot_filter") if is_slot_filter else get_id("action_filter")
            col.prop(obj.vs, "action_filter", text=filter_label)
        
        if State.exportFormat == ExportFormat.SMD:
            col.prop(obj.data.vs, "implicit_zero_bone")
            col.prop(obj.data.vs, "legacy_rotation")
        
        if obj.animation_data and not State.useActionSlots:
            col.template_ID(obj.animation_data, "action", new="action.new")
    
    def _draw_mesh_content(self, col : UILayout, obj, index,item):
        col.separator(type='LINE')
        
        box = col.box()
        
        toggle_icon = 'TRIA_DOWN' if obj.vs.show_vertexanim_items else 'TRIA_RIGHT'
        op = box.operator(SMD_OT_ShowVertexAnimation.bl_idname, icon=toggle_icon, text='Vertex Animation', emboss=False)
        op.index = index
        
        if obj.vs.show_vertexanim_items:
            row = box.row(align=True)
            
            row.enabled = type(obj) in [bpy.types.Object, bpy.types.Collection]
            
            add_op = row.operator(SMD_OT_AddVertexAnimation.bl_idname, icon="ADD", text="Add")
            add_op.index = index
            
            remove_op = row.operator(SMD_OT_RemoveVertexAnimation.bl_idname, icon="REMOVE", text="Remove")
            remove_op.index = index
            remove_op.vertexindex = obj.vs.active_vertex_animation
            
            if obj.vs.vertex_animations:
                box.template_list("SMD_UL_VertexAnimationItem", "", obj.vs, "vertex_animations", 
                                obj.vs, "active_vertex_animation", rows=2, maxrows=4)
                box.operator(SMD_OT_GenerateVertexAnimationQCSnippet.bl_idname, icon='FILE_TEXT')
    
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
        obj = context.scene.vs.export_list[self.index].item
        obj.vs.show_items = not obj.vs.show_items
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
    
    def execute(self,context):
        item = context.scene.vs.export_list[self.index].item
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
        item = context.scene.vs.export_list[self.index].item
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

    def execute(self, context):
        scene = context.scene

        if self.index >= len(scene.vs.export_list):
            self.report({'ERROR'}, "Invalid export list index")
            return {'CANCELLED'}

        item = scene.vs.export_list[self.index].item
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
    def poll(cls, c):
        return hasattr(c.scene, "vs") and len(c.scene.vs.export_list) > 0

    def execute(self, c):
        scene = c.scene
        if self.index >= len(scene.vs.export_list):
            self.report({'ERROR'}, "Invalid export list index")
            return {'CANCELLED'}

        item = scene.vs.export_list[self.index].item
        fps = scene.render.fps / scene.render.fps_base
        wm = c.window_manager

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

class SMD_PT_Object_Config(bpy.types.Panel):
    bl_label = get_id('exportables_title')
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self,context):
        l = self.layout
        scene = context.scene
        
        l.label(text='Exportable Objects', icon='EXPORT')
        l.template_list("SMD_UL_ExportItems","",scene.vs,"export_list",scene.vs,"export_list_active",rows=3,maxrows=8, type='DEFAULT')
        
        exportablehelp_section = create_toggle_section(l, context.scene.vs, 'show_exportable_help', f'Show Help', '')
        if scene.vs.show_exportable_help:
            row = exportablehelp_section.row()
            row.scale_y = 1.3
            row.operator("wm.url_open", text='Vertex Animations Help', icon_value=iconloader.preview_collections["custom_icons"]["SOURCESDK"].icon_id).url = \
            "http://developer.valvesoftware.com/wiki/Vertex_animation"
            
        l.separator(type='LINE')
        
        l.label(text='Prefabs', icon='FILE_TEXT')
        prefabhelpsection = create_toggle_section(l,context.scene.vs,'show_prefab_help','Read Me','')
        if context.scene.vs.show_prefab_help:
            draw_wrapped_text_col(prefabhelpsection,'Writing to QC or QCI will always overwrite the entire file. VMDL and VMDL_Prefab support both appending and updating existing data without affecting unrelated content. However, it’s still recommended to store export data in a separate prefab file for safety', max_chars=40, icon='WARNING_LARGE',boxed=False)
        
        l.operator("smd.add_prefab", icon="ADD")
        l.template_list("SMD_UL_Prefabs", "", scene.vs, "smd_prefabs", scene.vs, "smd_prefabs_index")

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

class SMD_OT_AddPrefab(bpy.types.Operator):
    bl_idname = "smd.add_prefab"
    bl_label = "Add Prefab"

    def execute(self, context):
        context.scene.vs.smd_prefabs.add()
        return {'FINISHED'}

class SMD_OT_RemovePrefab(bpy.types.Operator):
    bl_idname = "smd.remove_prefab"
    bl_label = "Remove Prefab"

    index: IntProperty()

    def execute(self, context):
        prefabs = context.scene.vs.smd_prefabs
        if 0 <= self.index < len(prefabs):
            prefabs.remove(self.index)
        return {'FINISHED'}

class SMD_OT_BrowsePrefab(bpy.types.Operator):
    bl_idname = "smd.browse_prefab"
    bl_label = "Browse Prefab"
    bl_description = "Open file location in system file explorer"

    index: IntProperty()

    def execute(self, context):
        prefabs = context.scene.vs.smd_prefabs
        if 0 <= self.index < len(prefabs):
            path = bpy.path.abspath(prefabs[self.index].filepath)
            folder = path if os.path.isdir(path) else os.path.dirname(path)

            if os.path.exists(folder):
                if os.name == "nt":  # Windows
                    os.startfile(folder)
                elif os.name == "posix":  # macOS / Linux
                    subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", folder])
                self.report({'INFO'}, f"Opened: {folder}")
            else:
                self.report({'WARNING'}, "Folder does not exist")

        return {'FINISHED'}

class SMD_UL_Prefabs(bpy.types.UIList):
    bl_idname = "SMD_UL_Prefabs"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        split = row.split(align=True, factor=0.7)
        
        if not item.filepath:
            split.alert = True
        
        split.prop(item, "filepath", text="")
        split = split.split(align=True, factor=0.7)
        
        split.alert = False
        split.operator("smd.browse_prefab", text="Open").index = index
        split.operator("smd.remove_prefab", text="", icon='X').index = index