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

import bpy, sys, os, subprocess, json
from bpy.types import Menu, Panel, Operator, MeshLoopColorLayer, UILayout, UIList, LoopColors, Collection, Object, UI_UL_list, PoseBone, Bone, EditBone
from bpy.props import FloatProperty, BoolProperty, IntProperty, EnumProperty, StringProperty
from bpy.app.translations import pgettext
from .utils import getSelectedExportables, count_exports, get_id, State, Compiler, ExportFormat, is_armature, get_attachments, get_hitboxes, get_jigglebones
from .export_smd import SmdExporter, PrefabExporter
from .import_smd import SmdImporter
from .flex import AddCorrectiveShapeDrivers, RenameShapesToMatchCorrectiveDrivers,DmxWriteFlexControllers
from .utils import *


class SMD_MT_ExportChoice(Menu):
    bl_label = get_id("exportmenu_title")

    def draw(self, context ) -> None:
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

        active = context.object

        arm = None
        if active:
            if is_armature(active):
                arm = active
            elif active.parent and is_armature(active.parent):
                arm = active.parent

        if arm:
            l.separator()
            if is_armature(active):
                if get_jigglebones(arm) and arm.vs.jigglebone_prefabfile:
                    l.operator(PrefabExporter.bl_idname, text=f"Jigglebones ({len(get_jigglebones(arm))}) \"{arm.name}\"", icon='BONE_DATA').export_type = 'JIGGLEBONES'
                if get_attachments(arm) and arm.vs.attachment_prefabfile:
                    l.operator(PrefabExporter.bl_idname, text=f"Attachments ({len(get_attachments(arm))}) \"{arm.name}\"", icon='EMPTY_ARROWS').export_type = 'ATTACHMENTS'
                if get_hitboxes(arm) and arm.vs.hitbox_prefabfile:
                    l.operator(PrefabExporter.bl_idname, text=f"Hitboxes ({len(get_hitboxes(arm))}) \"{arm.name}\"", icon='MESH_CUBE').export_type = 'HITBOXES'
            else:
                is_hitbox = active.type == 'EMPTY' and active.empty_display_type == 'CUBE' and getattr(active.vs, 'smd_hitbox', False)
                is_attachment = active.type == 'EMPTY' and getattr(active.vs, 'dmx_attachment', False)

                if is_hitbox and get_hitboxes(arm) and arm.vs.hitbox_prefabfile:
                    l.operator(PrefabExporter.bl_idname, text=f"Hitboxes ({len(get_hitboxes(arm))}) \"{arm.name}\"", icon='MESH_CUBE').export_type = 'HITBOXES'
                if is_attachment and get_attachments(arm) and arm.vs.attachment_prefabfile:
                    l.operator(PrefabExporter.bl_idname, text=f"Attachments ({len(get_attachments(arm))}) \"{arm.name}\"", icon='EMPTY_ARROWS').export_type = 'ATTACHMENTS'


class SMD_PT_Scene(Panel):
    bl_label = get_id("exportpanel_title")
    bl_category = 'KitsuneSrcTool'
    bl_region_type = 'UI'
    bl_space_type = 'VIEW_3D'

    def draw(self, context) -> None:
        l = self.layout
        scene = context.scene

        # Export
        row = l.row(align=True)
        row.scale_y = 1.5
        row.operator(SmdImporter.bl_idname, text="Import", icon='IMPORT')
        row.operator(SmdExporter.bl_idname, text="Export", icon='EXPORT')

        box = l.box()
        row = box.row()
        row.alert = len(scene.vs.export_path) == 0
        row.prop(scene.vs, "export_path")

        row = box.row()
        row.alert = len(scene.vs.engine_path) > 0 and State.compiler == Compiler.UNKNOWN
        row.prop(scene.vs, "engine_path")

        # Format

        if State.datamodelEncoding != 0:
            row = box.row().split(factor=0.33)
            row.label(text=get_id("export_format") + ":")
            row.row().prop(scene.vs, "export_format", expand=True)

        if scene.vs.export_format == 'DMX':
            if State.engineBranch is None:
                row = box.split(factor=0.33)
                row.label(text=get_id("exportpanel_dmxver"))
                sub = row.row(align=True)
                sub.prop(scene.vs, "dmx_encoding", text="")
                sub.prop(scene.vs, "dmx_format", text="")
                sub.enabled = not sub.alert
            if State.exportFormat == ExportFormat.DMX:
                box.prop(scene.vs, "material_path")
        else:
            row = box.split(factor=0.33)
            row.label(text=get_id("smd_format") + ":")
            row.row().prop(scene.vs, "smd_format", expand=True)

        #Scene
        
        row = box.row().split(factor=0.33)
        row.label(text=get_id("up_axis") + ":")
        row.row().prop(scene.vs, "up_axis", expand=True)

        row = box.row().split(factor=0.33)
        row.label(text=get_id("up_axis_offset") + ":")
        row.row().prop(scene.vs, "up_axis_offset", expand=True)

        row = box.row().split(factor=0.33)
        row.label(text=get_id("forward_axis") + ":")
        row.row().prop(scene.vs, "forward_axis", expand=True)

        row = box.row().split(factor=0.33)
        row.label(text=get_id("world_scale") + ":")
        row.row().prop(scene.vs, "world_scale")

        # Mesh
        box.prop(scene.vs, "weightlink_threshold", slider=True)
        box.prop(scene.vs, "vertex_influence_limit", slider=True)

        # OTHERS
        box1 = box.box().column(align=True)
        box1.label(text='Options', icon='OPTIONS')
        box1.prop(context.scene.vs,"use_kv2", text='Write ASCII DMX File')
        box1.prop(scene.vs, "prefab_to_clipboard")


class SMD_MT_ConfigureScene(Menu):
    bl_label = get_id("exporter_report_menu")
    def draw(self, context ) -> None:
        self.layout.label(text=get_id("exporter_err_unconfigured"))


class SMD_UL_KitsuneResourceEntries(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname): # pyright: ignore
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.label(text=item.name, icon='MESH_DATA')
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text='', icon='MESH_DATA')


class SMD_PT_KitsuneResourceCompile(Panel):
    bl_label = 'Kitsune Resource Compile'
    bl_category = 'KitsuneSrcTool'
    bl_region_type = 'UI'
    bl_space_type = 'VIEW_3D'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return sys.platform == 'win32'

    def draw(self, context) -> None:
        l = self.layout
        l.use_property_split = True
        l.use_property_decorate = False
        scene = context.scene
        vs = scene.vs

        box = l.box()

        col = box.column()
        col.alert = len(vs.kitsuneresource_app_path) == 0
        col.prop(vs, 'kitsuneresource_app_path')

        col = box.column()
        col.enabled = len(vs.kitsuneresource_app_path) > 0
        col.prop(vs, 'kitsuneresource_config')

        col = box.column()
        col.enabled = len(vs.kitsuneresource_config) > 0
        col.prop(vs, 'kitsuneresource_project_path')

        col = box.column()
        col.enabled = len(vs.kitsuneresource_app_path) > 0
        col.row(align=True).prop(vs, 'kitsuneresource_flag_game_or_package', expand=True)

        if vs.kitsuneresource_flag_game_or_package == 'PACKAGE':
            col.prop(vs, 'kitsuneresource_flag_single_addon')
            col.prop(vs, 'kitsuneresource_flag_no_mat_local')
            col.prop(vs, 'kitsuneresource_flag_archive_old')

        col.prop(vs, 'kitsuneresource_args', text="Extra Args")

        col = box.column()
        col.enabled = len(vs.kitsuneresource_config) > 0
        row = col.row()
        row.template_list("SMD_UL_KitsuneResourceEntries", "",vs, "kitsuneresource_model_entries",vs, "kitsuneresource_model_entry_index",rows=4)
        row.operator(SMD_OT_KitsuneResourceLoadEntries.bl_idname, text="", icon='FILE_REFRESH')

        col = box.column(align=True).row(align=True)
        col.scale_y = 1.2
        op = col.operator(SMD_OT_KitsuneResourceCompile.bl_idname, text="Compile All")
        op.compile_all = True
        op = col.operator(SMD_OT_KitsuneResourceCompile.bl_idname, text="Compile Selected")
        op.compile_all = False

        data_row = box.column()
        data_row.operator(SMD_OT_KitsuneResourceCompileData.bl_idname)


class SMD_OT_KitsuneResourceLoadEntries(Operator):
    bl_idname = "smd.kitsuneresource_load_entries"
    bl_label = "Reload Model Entries"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return len(context.scene.vs.kitsuneresource_config) > 0

    def execute(self, context) -> set:
        vs = context.scene.vs

        raw_app  = vs.kitsuneresource_app_path.strip()
        resolved = bpy.path.abspath(raw_app)
        app_path = resolved if os.path.isfile(resolved) else raw_app

        config_path = bpy.path.abspath(vs.kitsuneresource_config.strip())

        try:
            result = subprocess.run(
                [app_path, "--fetch", config_path],
                capture_output=True, text=True, timeout=15,
            )
            print(result.stdout)  # <-- add this temporarily
            data = json.loads(result.stdout)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to fetch entries: {e}")
            return {'CANCELLED'}

        if "error" in data:
            self.report({'ERROR'}, data["error"])
            return {'CANCELLED'}

        models = data.get("model", [])

        vs.kitsuneresource_model_entries.clear()
        for k in data.get("model", []):
            vs.kitsuneresource_model_entries.add().name = k
        vs.kitsuneresource_model_entry_index = 0

        vs.kitsuneresource_data_entries.clear()
        for k in data.get("data", []):
            vs.kitsuneresource_data_entries.add().name = k

        self.report({'INFO'}, f"Loaded {len(vs.kitsuneresource_model_entries)} model / {len(vs.kitsuneresource_data_entries)} data entries.")
        return {'FINISHED'}

 
class SMD_OT_KitsuneResourceCompile(Operator):
    bl_idname = "smd.kitsuneresource_compile"
    bl_label  = "Compile"
    bl_options = {'REGISTER'}

    compile_all: BoolProperty(name="Compile All", default=True)

    @classmethod
    def poll(cls, context):
        vs = context.scene.vs
        return (
            len(vs.kitsuneresource_project_path) > 0
            and len(vs.kitsuneresource_app_path) > 0
            and len(vs.kitsuneresource_config) > 0
        )

    def execute(self, context) -> set:
        vs          = context.scene.vs
        app_path    = resolve_kitsuneresource_app(vs)
        basedir     = resolve_kitsuneresource_project_basedir(vs)
        config_path = bpy.path.abspath(vs.kitsuneresource_config.strip())
        cmd         = build_base_cmd(vs, app_path, config_path)

        if not self.compile_all:
            idx     = vs.kitsuneresource_model_entry_index
            entries = vs.kitsuneresource_model_entries
            if 0 <= idx < len(entries):
                cmd += ["--only", entries[idx].name]
            else:
                self.report({'WARNING'}, "No entry selected; compiling all.")

        return run_and_report(self, cmd, basedir)
    

class SMD_OT_KitsuneResourceCompileData(Operator):
    bl_idname = "smd.kitsuneresource_compile_data"
    bl_label  = "Compile All Data"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        vs = context.scene.vs
        return (
            len(vs.kitsuneresource_project_path) > 0
            and len(vs.kitsuneresource_app_path) > 0
            and len(vs.kitsuneresource_config) > 0
            and len(vs.kitsuneresource_data_entries) > 0
            and not vs.kitsuneresource_flag_game_or_package == 'GAME'
        )

    def execute(self, context) -> set:
        vs          = context.scene.vs
        app_path    = resolve_kitsuneresource_app(vs)
        basedir     = resolve_kitsuneresource_project_basedir(vs)
        config_path = bpy.path.abspath(vs.kitsuneresource_config.strip())
        cmd         = build_base_cmd(vs, app_path, config_path)

        for entry in vs.kitsuneresource_data_entries:
            cmd += ["--only", entry.name]

        return run_and_report(self, cmd, basedir)
    

class TOOLS_OT_CopySourceBoneProps(Operator):
    bl_idname = "smd.copy_bone_props"
    bl_label = "Copy Source Bone Properties"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return (
            context.mode == 'POSE'
            and context.active_pose_bone is not None
            and len(context.selected_pose_bones) > 1
        )

    def execute(self, context) -> set:
        src = context.active_pose_bone.bone.vs
        props = [
            'export_name',
            'ignore_rotation_offset',
            'export_rotation_offset_x',
            'export_rotation_offset_y',
            'export_rotation_offset_z',
            'ignore_location_offset',
            'export_location_offset_x',
            'export_location_offset_y',
            'export_location_offset_z',
        ]

        targets = [pb for pb in context.selected_pose_bones if pb != context.active_pose_bone]
        for pb in targets:
            for prop in props:
                setattr(pb.bone.vs, prop, getattr(src, prop))

        self.report({'INFO'}, f"Copied bone properties to {len(targets)} bone(s)")
        return {'FINISHED'}
   

SMD_OT_CreateVertexMap_idname : str = "smd.vertex_map_create_"
SMD_OT_SelectVertexMap_idname : str = "smd.vertex_map_select_"
SMD_OT_RemoveVertexMap_idname : str = "smd.vertex_map_remove_"

for map_name in vertex_maps:

    class SelectVertexColorMap(Operator):
        bl_idname = SMD_OT_SelectVertexMap_idname + map_name
        bl_label = get_id("vertmap_select")
        bl_description = get_id("vertmap_select")
        bl_options = {'INTERNAL'}
        vertex_map = map_name
    
        @classmethod
        def poll(cls, context) -> bool:
            if not is_mesh(context.object):
                return False
            vc_loop : MeshLoopColorLayer | None = context.object.data.vertex_colors.get(cls.vertex_map)
            return bool(vc_loop and not vc_loop.active)

        def execute(self, context) -> set:
            context.object.data.vertex_colors[self.vertex_map].active = True
            return {'FINISHED'}

    class CreateVertexColorMap(Operator):
        bl_idname = SMD_OT_CreateVertexMap_idname + map_name
        bl_label = get_id("vertmap_create")
        bl_description = get_id("vertmap_create")
        bl_options = {'INTERNAL'}
        vertex_map = map_name
    
        @classmethod
        def poll(cls, context) -> bool:
            return bool(is_mesh(context.object) and cls.vertex_map not in context.object.data.vertex_colors)

        def execute(self, context) -> set:
            vc : MeshLoopColorLayer = context.object.data.vertex_colors.new(name=self.vertex_map)
            vc.data.foreach_set("color", [1.0] * len(vc.data) * 4)
            SelectVertexColorMap.execute(self, context)
            return {'FINISHED'}

    class RemoveVertexColorMap(Operator):
        bl_idname = SMD_OT_RemoveVertexMap_idname + map_name
        bl_label = get_id("vertmap_remove")
        bl_description = get_id("vertmap_remove")
        bl_options = {'INTERNAL'}
        vertex_map = map_name
    
        @classmethod
        def poll(cls, context) -> bool:
            return bool(is_mesh(context.object) and cls.vertex_map in context.object.data.vertex_colors)

        def execute(self, context) -> set:
            vcs : LoopColors  = context.object.data.vertex_colors
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
        bl_idname = SMD_OT_SelectVertexFloatMap_idname + map_name
        bl_label = get_id("vertmap_select")
        bl_description = get_id("vertmap_select")
        bl_options = {'INTERNAL'}
        vertex_map = map_name

        @classmethod
        def poll(cls, context) -> bool:
            vg_loop = context.object.vertex_groups.get(cls.vertex_map)
            return bool(vg_loop and not context.object.vertex_groups.active == vg_loop)

        def execute(self, context) -> set:
            context.object.vertex_groups.active_index = context.object.vertex_groups[self.vertex_map].index
            return {'FINISHED'}

    class CreateVertexFloatMap(Operator):
        bl_idname = SMD_OT_CreateVertexFloatMap_idname + map_name
        bl_label = get_id("vertmap_create")
        bl_description = get_id("vertmap_create")
        bl_options = {'INTERNAL'}
        vertex_map = map_name

        @classmethod
        def poll(cls, context) -> bool:
            return bool(context.object and context.object.type == 'MESH' and cls.vertex_map not in context.object.vertex_groups)

        def execute(self, context) -> set:
            vc = context.object.vertex_groups.new(name=self.vertex_map)

            found : bool = False
            for remap in context.object.vs.vertex_map_remaps:
                if remap.group == map_name:
                    found = True
                    break

            if not found:
                remap = context.object.vs.vertex_map_remaps.add()
                remap.group = map_name
                remap.min : float = 0.0
                remap.max : float = 1.0

            SelectVertexFloatMap.execute(self, context)
            return {'FINISHED'}

    class RemoveVertexFloatMap(Operator):
        bl_idname = SMD_OT_RemoveVertexFloatMap_idname + map_name
        bl_label = get_id("vertmap_remove")
        bl_description = get_id("vertmap_remove")
        bl_options = {'INTERNAL'}
        vertex_map = map_name

        @classmethod
        def poll(cls, context) -> bool:
            return bool(context.object and context.object.type == 'MESH' and cls.vertex_map in context.object.vertex_groups)

        def execute(self, context) -> set:
            vgs = context.object.vertex_groups
            vgs.remove(vgs[self.vertex_map])
            return {'FINISHED'}

    bpy.utils.register_class(SelectVertexFloatMap)
    bpy.utils.register_class(CreateVertexFloatMap)
    bpy.utils.register_class(RemoveVertexFloatMap)


vca_icon = 'EDITMODE_HLT'


class SMD_UL_ExportItems(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index, flt_flag):
        obj = item.item
        is_collection = isinstance(obj, Collection)
        enabled = not (is_collection and obj.vs.mute)
        
        col = layout.column()
        split1 = self._draw_header_row(col, obj, item, enabled, index, is_collection = is_collection)
        
        if enabled:
            self._draw_stats_row(split1, obj)
    
    def _draw_header_row(self, col : UILayout, obj : Object, item, enabled, index, is_collection : bool):
        row = col.row(align=True)
        
        export_icon = 'CHECKBOX_HLT' if obj.vs.export and enabled else 'CHECKBOX_DEHLT'
        row.prop(obj.vs, "export", icon=export_icon, text="", emboss=False)
        row.label(text='', icon=item.icon)
        
        split1 = row.split(factor=0.8)
        split1.alert = not enabled
        split1.label(text=item.name)
        
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


class FilterCache:
    def __init__(self):
        self.state_objects = State.exportableObjects

    fname = None
    filter = None
    order = None


gui_cache = {}
class SMD_UL_GroupItems(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index, flt_flag):
        r = layout.row(align=True)
        r.prop(item.vs,"export",text="",icon='CHECKBOX_HLT' if item.vs.export else 'CHECKBOX_DEHLT',emboss=False)
        r.label(text=item.name,translate=False,icon=MakeObjectIcon(item,suffix="_DATA"))
    
    def filter_items(self, context, data, propname): # pyright: ignore
        fname = self.filter_name.lower()
        cache = gui_cache.get(data)

        if not (cache and cache.fname == fname and cache.state_objects is State.exportableObjects):
            cache = FilterCache()
            cache.filter = [self.bitflag_filter_item if ob.session_uid in State.exportableObjects and (not fname or fname in ob.name.lower()) else 0 for ob in data.objects]
            cache.order = UI_UL_list.sort_items_by_name(data.objects)
            cache.fname = fname
            gui_cache[data] = cache
            
        return cache.filter, cache.order if self.use_filter_sort_alpha else []


class SMD_PT_Properties(Panel):
    bl_label = get_id('exportables_title')
    bl_category = 'KitsuneSrcTool'
    bl_region_type = 'UI'
    bl_space_type = 'VIEW_3D'
    
    def draw(self, context) -> None:
        layout = self.layout
        active_object = context.object

        if active_object is None: return

        box = layout.box().column(align=True)
        box.label(text='Export Options', icon='SETTINGS')
        box.prop(active_object.vs, 'export')


class Properties_SubPanel(Panel):
    bl_label = 'sample_propertiessub'
    bl_category = 'KitsuneSrcTool'
    bl_region_type = 'UI'
    bl_space_type = 'VIEW_3D'
    bl_parent_id = 'SMD_PT_Properties'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def get_item(cls, context):
        active_exportable = get_active_exportable(context)
        if not active_exportable:
            return None
        return active_exportable.item

    @classmethod
    def is_collection(cls, item):
        return isinstance(item, Collection)

    def draw(self, context):
        layout = self.layout


class SMD_PT_Group(Properties_SubPanel):
    bl_label = ''
    bl_options = set()

    def draw_header(self, context):
        item = self.get_item(context)
        label = '{} ({})'.format(pgettext("Group"), item.name) if item else pgettext("Group")
        self.layout.label(text=label, icon='GROUP')

    def draw(self, context):
        layout = self.layout
        item = self.get_item(context)
        scene = context.scene

        if item is not None:vs = item.vs
        else: vs = None
        if vs is not None: layout.column().prop(vs,"subdir",icon='FILE_FOLDER')

        layout.template_list("SMD_UL_ExportItems","",scene.vs,"export_list",scene.vs,"export_list_active",rows=3,maxrows=8)

        if not item or not self.is_collection(item):
            layout.label(text=get_id("panel_select_group"), icon='ERROR')
            return
        
        if vs:
            r = layout.row()
            r.alignment = 'CENTER'
            r.prop(vs, "mute")
            if vs.mute:
                return
            elif State.exportFormat == ExportFormat.DMX:
                r.prop(vs, "automerge")

            if not vs.mute:
                layout.template_list("SMD_UL_GroupItems", item.name, item, "objects", vs, "selected_item", columns=2, rows=2, maxrows=10)


class SMD_PT_Armature(Properties_SubPanel):
    bl_label = ''

    def draw_header(self, context):
        active_object = get_armature(context.object)
        label = '{} ({})'.format(pgettext("Armature"), active_object.name) if active_object else pgettext("Armature")
        self.layout.label(text=label, icon='ARMATURE_DATA')
    
    def draw(self, context):
        layout = self.layout
        active_object = get_armature(context.object)
        
        if not is_armature(active_object):
            layout.label(text=get_id("panel_select_armature"), icon='ERROR')
            return
        
        box = layout.box()
        col = box.column()
        col.prop(active_object.vs,"jigglebone_prefabfile")
        col.prop(active_object.vs,"attachment_prefabfile")
        col.prop(active_object.vs,"hitbox_prefabfile")

        box = layout.box()
        col = box.column()
        col.row().prop(active_object.data.vs, "action_selection", expand=True)
        if active_object.data.vs.action_selection != 'CURRENT':
            is_slot_filter = active_object.data.vs.action_selection == 'FILTERED' and State.useActionSlots
            col.prop(active_object.vs, "action_filter", text=get_id("slot_filter") if is_slot_filter else get_id("action_filter"))
            col.prop(active_object.data.vs, "reset_pose_per_anim")

        if active_object.animation_data and not State.useActionSlots:
            col.template_ID(active_object.animation_data, "action", new="action.new")

        box = layout.box()
        col = box.column()
        col.enabled = bool(State.exportFormat == ExportFormat.SMD)
        col.prop(active_object.data.vs,"implicit_zero_bone")
        col.prop(active_object.data.vs,"legacy_rotation")

        box = layout.box()
        col = box.column(align=True)
        col.prop(active_object.data.vs, "ignore_bone_exportnames")
        col.label(text='Direction Naming:')
        
        row = col.row()
        row.prop(active_object.data.vs, 'bone_direction_naming_left', text='Left')
        row.prop(active_object.data.vs, 'bone_direction_naming_right', text='Right')
        
        box.prop(active_object.data.vs, 'bone_name_startcount', slider=True)

    
class SMD_PT_Bone(Properties_SubPanel):
    bl_label = ''

    def draw_header(self, context):
        active_bone = context.active_bone
        label = '{} ({})'.format(pgettext("Bone"), active_bone.name) if active_bone else pgettext("Bone")
        self.layout.label(text=label, icon='BONE_DATA')
        
    def draw(self, context):
        layout = self.layout
        active_object = context.object
        active_bone = context.active_bone
        
        if not is_armature(active_object):
            layout.label(text=get_id("panel_select_armature"), icon='ERROR')
            return
        
        if not isinstance(active_bone, (PoseBone, Bone)):
            layout.label(text=get_id("panel_select_noneditbone"), icon='ERROR')
            return


class SMD_PT_BoneData(Properties_SubPanel):
    bl_label = 'Bone Data'
    bl_parent_id = 'SMD_PT_Bone'

    @classmethod
    def poll(cls, context):
        return is_armature(context.object) and context.active_bone is not None and not isinstance(context.active_bone, EditBone)

    def draw(self, context):
        layout = self.layout
        active_object = context.object
        active_bone = context.active_bone
        
        box = layout.box()
        col = box.column(align=True)
        
        if isinstance(active_bone, PoseBone):
            active_bone_vs = active_bone.bone.vs
        else:
            active_bone_vs = active_bone.vs
        
        active_bone_exportname = get_bone_exportname(active_bone)
        col.prop(active_bone.vs, 'export_name', placeholder=active_bone_exportname, text='')
        col.separator()
        col.prop(active_bone.vs, 'bone_sort_order', slider=True)
        col.label(text='Export Name: {}'.format(active_bone_exportname))

        col.operator(SMD_OT_CopyBoneExportName.bl_idname, icon='COPY_ID')
        
        split = box.split(factor=0.5)
        
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
        
        box.operator(SMD_OT_AssignBoneRotExportOffset.bl_idname)


class SMD_PT_Jigglebones(Properties_SubPanel):
    bl_label = 'Jigglebones'
    bl_parent_id = 'SMD_PT_Bone'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return is_armature(context.object) and context.active_bone is not None and not isinstance(context.active_bone, EditBone)
        
    def draw(self, context):
        layout = self.layout
        active_object = context.object
        active_armature = get_armature(active_object)
        active_bone = context.active_bone
        
        box = layout.box()
        box.label(text='Jigglebone Properties')
        if active_bone and active_bone.select:
            copyop = box.operator(SMD_OT_CopySourceBoneProps.bl_idname, text='Copy Jigglebone Properties')
            copyop.to_invoke = False
            copyop.copy_name = False
            copyop.copy_rotation = False
            copyop.copy_location = False
            copyop.copy_jigglebone = True
            self.draw_jigglebone_properties(box, active_bone)
        else:
            box = box.box()
            box.label(text='Select a Valid Bone', icon='ERROR')
        
    def _draw_export_buttons(self, layout: UILayout, operator: str, scale_y: float = 1.25, 
                            clipboard_text= 'Write to Clipboard',
                            file_text= 'Write to File',
                            clipboard_icon= 'FILE_TEXT',
                            file_icon= 'EXPORT') -> None:
        """Draw standard export button pair (clipboard/file)."""
        row = layout.row(align=True)
        row.scale_y = scale_y
        row.operator(operator, text=clipboard_text, icon=clipboard_icon).to_clipboard = True
        row.operator(operator, text=file_text, icon=file_icon).to_clipboard = False
        
    def draw_jigglebone_properties(self, layout: UILayout, bone: Bone) -> None:
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
            vs_bone.jiggle_has_pitch_constraint])
        
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

    
class SMD_PT_Mesh(Properties_SubPanel):
    bl_label = ''

    def draw_header(self, context):
        active_object = context.object
        label = '{} ({})'.format(pgettext("Mesh"), active_object.name) if is_mesh_compatible(active_object) else pgettext("Mesh")
        self.layout.label(text=label, icon='MESH_DATA')
        
    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        active_object = context.object
        
        if not is_mesh_compatible(active_object):
            layout.label(text=get_id("panel_select_mesh"), icon='ERROR')
            return
        
        vs = active_object.vs

        box = layout.box().column(align=True)
        box.prop_search(vs, 'non_exportable_vgroup', active_object, 'vertex_groups')
        box.separator(factor=0.5)
        box.prop(vs, 'non_exportable_vgroup_tolerance')
        
        box.prop(vs, 'merge_vertices')

  
class SMD_PT_Shapekey(Properties_SubPanel):
    bl_label = ''
    bl_parent_id = 'SMD_PT_Mesh'
    
    @classmethod
    def poll(cls, context):
        return is_mesh_compatible(context.object)
    
    def draw_header(self, context):
        active_object = context.object
        val1, val2 = countShapes(active_object)
        label = '{} ({} Shapes, {} Correctives)'.format(pgettext("Shape keys"), val1, val2) if is_mesh_compatible(active_object) else pgettext("Shape Keys")
        self.layout.label(text=label, icon='SHAPEKEY_DATA')
        
    def draw(self, context):
        layout = self.layout
        active_object = context.object
        
        if not is_mesh_compatible(active_object):
            layout.label(text=get_id("panel_select_mesh"), icon='ERROR')
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
            first_col.template_list("SMD_UL_FlexControllers","",active_object.vs,"dme_flexcontrollers", active_object.vs,"dme_flexcontrollers_index")
            
            second_col = row.column(align=True)
            second_col.operator(SMD_OT_AddFlexController.bl_idname, icon='ADD', text='')
            second_col.operator(SMD_OT_RemoveFlexController.bl_idname, icon='REMOVE', text='')

            second_col.separator()

            second_col.menu('SMD_MT_FlexControllerSpecials', icon='DOWNARROW_HLT', text='')

            second_col.separator()

            move_up = second_col.operator(SMD_OT_MoveFlexController.bl_idname, icon='TRIA_UP', text='')
            move_up.direction = 'UP'
            move_down = second_col.operator(SMD_OT_MoveFlexController.bl_idname, icon='TRIA_DOWN', text='')
            move_down.direction = 'DOWN'

            if len(active_object.vs.dme_flexcontrollers) > 0 and active_object.vs.dme_flexcontrollers_index != -1:
                
                box = col.box()
                box_col = box.column(align=True)
                
                item = active_object.vs.dme_flexcontrollers[active_object.vs.dme_flexcontrollers_index]

                prop_col = box_col.split(factor=0.33, align=True)
                prop_col.alignment = 'RIGHT'
                prop_col.label(text='Controller Name')
                prop_col.prop(item,'controller_name',text='')

                prop_col = box_col.split(factor=0.33, align=True)
                prop_col.alignment = 'RIGHT'
                prop_col.label(text='Delta Name')
                prop_col.prop(item,'raw_delta_name',text='')

                prop_col = box_col.split(factor=0.33, align=True)
                prop_col.alignment = 'RIGHT'
                prop_col.label(text='Shapekey')
                prop_col.prop_search(item,'shapekey',active_object.data.shape_keys,'key_blocks',text='')
                
                prop_col = box_col.split(factor=0.33, align=True)
                prop_col.alignment = 'RIGHT'
                prop_col.label(text='')
                prop_col.prop(item,'eyelid',text='Is Eyelid')
                
                prop_col = box_col.split(factor=0.33, align=True)
                prop_col.alignment = 'RIGHT'
                prop_col.label(text='')
                prop_col.prop(item,'stereo',text='Is Stereo')
                
                prop_col = box_col.split(factor=0.33, align=True)
                prop_col.alignment = 'RIGHT'
                prop_col.label(text='Flex Type')
                prop_col.prop(item,'flexgroup',text='')
                
                box_row = box.row(align=True)
                
                preview_op = box_row.operator(SMD_OT_PreviewFlexController.bl_idname, text="Preview (Reset)", icon='HIDE_OFF')
                preview_op.reset_others = True

                preview_op = box_row.operator(SMD_OT_PreviewFlexController.bl_idname, text="Preview (Additive)", icon='ADD')
                preview_op.reset_others = False
                
                box_row.operator("object.shape_key_clear", icon='X', text="")
            
            insertStereoSplitUi(col)
            
        else:
            insertCorrectiveUi(col)
            
        col.separator()
        row = col.row()
        row.alignment = 'CENTER'
        row.label(icon='SHAPEKEY_DATA',text = get_id("exportables_flex_count", True).format(num_shapes))
        
        if active_object.vs.flex_controller_mode != 'BUILDER':
            row.label(icon='SHAPEKEY_DATA',text = get_id("exportables_flex_count_corrective", True).format(num_correctives))
    
        
class SMD_PT_Vertexmap(Properties_SubPanel):
    bl_label = 'Vertex Maps'
    bl_parent_id = 'SMD_PT_Mesh'
    
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
            box.label(text='Only Applicable in DMX!', icon='ERROR')
        
        col.label(text='Vertex Maps:')
        for map_name in vertex_maps:
            r = col.row()
            r.label(text=get_id(map_name),icon='GROUP_VCOL')
            
            add_remove = r.row(align=True)
            add_remove.operator(SMD_OT_CreateVertexMap_idname + map_name,icon='ADD',text="")
            add_remove.operator(SMD_OT_RemoveVertexMap_idname + map_name,icon='REMOVE',text="")
            add_remove.operator(SMD_OT_SelectVertexMap_idname + map_name,text="Activate")
    
      
class SMD_PT_Vertexfloatmap(Properties_SubPanel):
    bl_label = 'Vertex Float Maps'
    bl_parent_id = 'SMD_PT_Mesh'
    
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


class SMD_PT_Vertexanimations(Properties_SubPanel):
    bl_label = 'Vertex Animations'
    bl_parent_id = 'SMD_PT_Mesh'
    
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
            layout.label(text=get_id("panel_select_mesh"))
            return
            
        box = layout.box()
        
        box.label(text="Target Object: {}".format(active_object.name), icon='MESH_DATA' if is_mesh_compatible(active_object) else "OUTLINER_COLLECTION")
        row = box.row(align=True)
        row.operator(SMD_OT_AddVertexAnimation.bl_idname, icon="ADD", text="Add")
        
        remove_op = row.operator(SMD_OT_RemoveVertexAnimation.bl_idname, icon="REMOVE", text="Remove")
        remove_op.vertexindex = active_object.vs.active_vertex_animation
        
        if active_object.vs.vertex_animations:
            box.template_list("SMD_UL_VertexAnimationItem", "", active_object.vs, "vertex_animations", active_object.vs, "active_vertex_animation", rows=2, maxrows=4)
            box.operator(SMD_OT_GenerateVertexAnimationQCSnippet.bl_idname, icon='FILE_TEXT')


class SMD_PT_ToonEdgeline(Properties_SubPanel):
    bl_label = ''
    bl_parent_id = 'SMD_PT_Mesh'
    
    @classmethod
    def poll(cls, context):
        return is_mesh_compatible(context.object)
    
    def draw_header(self, context):
        active_object = context.object
        is_outline = active_object.vs.use_toon_edgeline
        label = '{} ({})'.format(pgettext("Toon Outline/Edgeline"), str(is_outline)) if is_mesh_compatible(active_object) else pgettext("Toon Outline/Edgeline")
        self.layout.label(text=label, icon='MOD_SOLIDIFY')
        
    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        active_object = context.object

        if not is_mesh_compatible(active_object) or active_object.type not in modifier_compatible:
            layout.label(text=get_id("panel_select_mesh"), icon='ERROR')
            return

        vs = active_object.vs

        box = layout.box().column(align=True)
        box.prop(vs, 'use_toon_edgeline')
        
        col = box.column(align=True)     
        col.enabled = vs.use_toon_edgeline
        col.prop(vs, 'edgeline_per_material')
        col.prop(vs, 'export_edgeline_separately', text="Export Edgeline Separately")
        col.prop(vs, 'base_toon_edgeline_thickness', text='Thickness')   
        col.prop_search(vs, 'toon_edgeline_vertexgroup', active_object, 'vertex_groups', text="Outline Width VertexGroup", icon='GROUP_VERTEX')


class SMD_PT_LOD(Properties_SubPanel):
    bl_label = ''
    bl_parent_id = 'SMD_PT_Mesh'
    
    @classmethod
    def poll(cls, context):
        return is_mesh_compatible(context.object)
    
    def draw_header(self, context):
        active_object = context.object
        is_outline = active_object.vs.use_toon_edgeline
        label = '{} ({})'.format(pgettext("Level Of Detail"), str(is_outline)) if is_mesh_compatible(active_object) else pgettext("Level Of Detail")
        self.layout.label(text=label, icon='MOD_DECIM')
        
    def draw(self, context):
        layout = self.layout
        active_object = context.object

        if not is_mesh_compatible(active_object) or active_object.type not in modifier_compatible:
            layout.label(text=get_id("panel_select_mesh"), icon='ERROR')
            return

        vs = active_object.vs

        box = layout.box()
        box.prop(vs, 'generate_lods', text="Generate LODs on export", toggle=True)

        col = box.column(align=True)
        col.enabled = vs.generate_lods

        col.prop(vs, 'lod_count', slider=True)
        col.prop(vs, 'decimate_factor', slider=True)


class SMD_PT_Material(Properties_SubPanel):
    bl_label = ''

    def draw_header(self, context):
        active_object = context.object
        active_material = active_object.active_material if is_mesh(active_object) else None
        label = '{} ({})'.format(pgettext("Material"), active_material.name) if active_material else pgettext("Material")
        self.layout.label(text=label, icon='MATERIAL_DATA')
        
    def draw(self, context):
        layout = self.layout
        active_object = context.object
        
        if not is_mesh_compatible(active_object):
            layout.label(text=get_id("panel_select_mesh"), icon='ERROR')
            return
        
        active_material = active_object.active_material
        
        if not active_material:
            layout.label(text=get_id("panel_select_mesh_mat"), icon='ERROR')
            return
        
        box = layout.box()

        if State.exportFormat == ExportFormat.DMX:
            box.prop(active_material.vs, 'override_dmx_export_path', placeholder=context.scene.vs.material_path)


class SMD_PT_Empty(Properties_SubPanel):
    bl_label = ''

    def draw_header(self, context):
        active_object = context.object
        label = '{} ({})'.format(pgettext("Empty"), active_object.name) if is_empty(active_object) else pgettext("Empty")
        self.layout.label(text=label, icon='EMPTY_DATA')
        
    def draw(self, context):
        layout = self.layout
        active_object = context.object
        
        if not is_empty(active_object):
            layout.label(text=get_id("panel_select_empty"), icon='ERROR')
            return

        box = layout.box()
        
        col = box.column()
        col.prop(active_object.vs, 'dmx_attachment', toggle=False)
        col.prop(active_object.vs, 'smd_hitbox', toggle=False)
        
        if active_object.vs.smd_hitbox:
            col.prop(active_object.vs, 'smd_hitbox_group', text='Hitbox Group')
        
        if active_object.vs.dmx_attachment and active_object.children:
            col.alert = True
            col.box().label(text="Attachment cannot be a parent",icon='WARNING_LARGE')


class SMD_PT_Curve(Properties_SubPanel):
    bl_label = ''

    def draw_header(self, context):
        active_object = context.object
        label = '{} ({})'.format(pgettext("Curve"), active_object.name) if is_curve(active_object) else pgettext("Curve")
        self.layout.label(text=label, icon='CURVE_DATA')
        
    def draw(self, context):
        layout = self.layout
        active_object = context.object
        
        if not is_curve(active_object):
            layout.label(text=get_id("panel_select_curve"), icon='ERROR')
            return
        
        box = layout.box()
        
        done = set()
        
        row = box.split(factor=0.33)
        row.label(text=context.object.data.name + ":",icon=MakeObjectIcon(context.object,suffix='_DATA'),translate=False) # type: ignore
        row.prop(context.object.data.vs,"faces",text="")
        done.add(context.object.data)

   
class SMD_UL_FlexControllers(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index, flt_flag):
        ob = context.object
        
        is_basis = False
        if ob.data and ob.data.shape_keys and item.shapekey and len(ob.data.shape_keys.key_blocks) > 0:
            if item.shapekey == ob.data.shape_keys.key_blocks[0].name:
                is_basis = True

        controller_name = item.controller_name.strip() if item.controller_name and item.controller_name.strip() else item.shapekey if item.shapekey else "Null Flexcontroller"
        
        has_duplicate_controller = sum(1 for fc in ob.vs.dme_flexcontrollers 
                                       if (fc.controller_name.strip() if fc.controller_name and fc.controller_name.strip() else fc.shapekey) == controller_name) > 1

        main_split = layout.split(factor=0.15, align=True)
        
        group_text = item.flexgroup.title() if item.flexgroup != 'NONE' else "-"
        main_split.label(text=group_text)
        
        name_split = main_split.split(factor=0.55, align=True)
        name_row = name_split.row(align=True)
        
        if has_duplicate_controller or not item.shapekey or is_basis:
            name_row.alert = True
        
        name_row.label(text=controller_name, icon='SHAPEKEY_DATA')
        
        info_row = name_split.row(align=True)
        info_row.alignment = 'RIGHT'
        
        if len(item.raw_delta_name.strip()) > 0 and item.shapekey in ob.data.shape_keys.key_blocks:
            info_row.label(text=sanitize_string_for_delta(item.raw_delta_name))
        elif item.shapekey in ob.data.shape_keys.key_blocks:
            info_row.label(text=sanitize_string_for_delta(item.shapekey))
            
        if item.stereo:
            info_row.label(text="", icon='MOD_MIRROR')
                
        if item.eyelid:
            info_row.label(text="", icon='HIDE_OFF')


class SMD_MT_FlexControllerSpecials(Menu):
    bl_label = "Flex Controller Specials"

    def draw(self, context):
        layout = self.layout
        layout.operator(SMD_OT_AddAllFlexControllers.bl_idname, icon='IMPORT', text="Add All")
        layout.operator(SMD_OT_SortFlexControllers.bl_idname, icon='SORTALPHA', text="Sort by Name")
        layout.operator(SMD_OT_AutoAssignFlexGroups.bl_idname, icon='GROUP')
        layout.separator()
        layout.operator(SMD_OT_ClearFlexControllers.bl_idname, icon='TRASH', text="Delete All")


class SMD_OT_AddFlexController(Operator):
    bl_idname = "smd.add_flexcontroller"
    bl_label = "Add Flex Controller"
    bl_options = {'INTERNAL', 'UNDO'}  

    def execute(self, context) -> set:
        ob  = context.object

        new_item = ob.vs.dme_flexcontrollers.add()
        ob.vs.dme_flexcontrollers_index = len(ob.vs.dme_flexcontrollers) - 1
        
        if hasattr(ob.data, 'shape_keys') and ob.active_shape_key_index is not None and ob.active_shape_key_index > 0:
            new_item.shapekey = ob.data.shape_keys.key_blocks[ob.active_shape_key_index].name
            new_item.raw_delta_name = new_item.shapekey
        else:
            new_item.shapekey = ""
        
        return {'FINISHED'}


class SMD_OT_AddAllFlexControllers(Operator):
    bl_idname = "smd.add_all_flexcontrollers"
    bl_label = "Add All Flex Controllers"
    bl_options = {'INTERNAL', 'UNDO'}

    mode: EnumProperty(
        name="Add Mode",
        items=[
            ('ALL', "Add All", "Add all shape keys, replacing existing entries"),
            ('MISSING', "Add Missing", "Only add shape keys not already in the list"),
        ],
        default='MISSING',
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context) -> set:
        ob = context.object

        if not hasattr(ob.data, 'shape_keys') or ob.data.shape_keys is None:
            self.report({'WARNING'}, "No shape keys found on active object")
            return {'CANCELLED'}

        key_blocks = ob.data.shape_keys.key_blocks
        existing = {item.shapekey for item in ob.vs.dme_flexcontrollers}

        added = 0
        for key in key_blocks[1:]:  # skip Basis
            if self.mode == 'MISSING' and key.name in existing:
                continue
            new_item = ob.vs.dme_flexcontrollers.add()
            new_item.shapekey = key.name
            new_item.raw_delta_name = key.name
            added += 1

        if added:
            ob.vs.dme_flexcontrollers_index = len(ob.vs.dme_flexcontrollers) - 1

        self.report({'INFO'}, f"Added {added} flex controller(s)")
        return {'FINISHED'}


class SMD_OT_RemoveFlexController(Operator):
    bl_idname = "smd.remove_flexcontroller"
    bl_label = "Remove Flex Controller"
    bl_options = {'INTERNAL', 'UNDO'}
    
    @classmethod
    def poll(cls, context) -> bool:
        return bool(len(context.object.vs.dme_flexcontrollers) > 0)
    
    def execute(self, context) -> set:
        context.object.vs.dme_flexcontrollers.remove(context.object.vs.dme_flexcontrollers_index)
        context.object.vs.dme_flexcontrollers_index = min(max(0, context.object.vs.dme_flexcontrollers_index - 1), 
                                                 len(context.object.vs.dme_flexcontrollers) - 1)
        return {'FINISHED'}


class SMD_OT_MoveFlexController(Operator):
    bl_idname = "smd.move_flexcontroller"
    bl_label = "Move Flex Controller"
    bl_options = {'INTERNAL', 'UNDO'}

    direction: EnumProperty(items=[('UP', "Up", ""), ('DOWN', "Down", "")])

    def execute(self, context) -> set:
        ob = context.object
        controllers = ob.vs.dme_flexcontrollers
        index = ob.vs.dme_flexcontrollers_index

        if self.direction == 'UP' and index > 0:
            controllers.move(index, index - 1)
            ob.vs.dme_flexcontrollers_index -= 1
        elif self.direction == 'DOWN' and index < len(controllers) - 1:
            controllers.move(index, index + 1)
            ob.vs.dme_flexcontrollers_index += 1

        return {'FINISHED'}


class SMD_OT_AutoAssignFlexGroups(Operator):
    bl_idname = "smd.auto_assign_flexgroups"
    bl_label = "Auto Assign Flex Groups"
    bl_description = "Automatically categorize flex controllers based on keywords"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context) -> bool:
        return bool(context.object and 
                hasattr(context.object, "vs") and 
                len(context.object.vs.dme_flexcontrollers) > 0)

    def execute(self, context) -> set:
        ob = context.object
        controllers = ob.vs.dme_flexcontrollers
        
        mapping = [
            ('EYELID', ['lid', 'blink', 'wink']),
            ('EYES', ['eye']),
            ('BROW', ['brow']),
            ('MOUTH', ['mouth', 'phoneme', 'smile', 'frown', 'jaw', 'lip', 'tongue']),
            ('CHEEK', ['cheek', 'puff']),
        ]

        assigned_count = 0

        for item in controllers:
            search_name = ""
            if item.controller_name:
                search_name = item.controller_name.lower()
            elif hasattr(item, 'raw_delta_name') and item.raw_delta_name:
                search_name = item.raw_delta_name.lower()
            elif hasattr(item, 'shapekey') and item.shapekey:
                search_name = item.shapekey.lower()

            if not search_name:
                continue

            for group_id, keywords in mapping:
                if any(kw in search_name for kw in keywords):
                    item.flexgroup = group_id
                    assigned_count += 1
                    break
            
        self.report({'INFO'}, f"Categorized {assigned_count} controllers")
        return {'FINISHED'}


class SMD_OT_SortFlexControllers(Operator):
    bl_idname = "smd.sort_flexcontrollers"
    bl_label = "Sort Flex Controllers"
    bl_options = {'INTERNAL', 'UNDO'}

    def execute(self, context) -> set:
        ob = context.object
        controllers = ob.vs.dme_flexcontrollers

        def sort_key(fc):
            name = fc.controller_name.strip() if fc.controller_name and fc.controller_name.strip() else None
            delta = fc.raw_delta_name.strip() if fc.raw_delta_name and fc.raw_delta_name.strip() else None
            return (name or delta or fc.shapekey or "").lower()

        sorted_controllers = sorted(controllers, key=sort_key)

        temp = [(fc.controller_name, fc.shapekey, fc.raw_delta_name, fc.stereo, fc.eyelid) for fc in sorted_controllers]

        controllers.clear()
        for controller_name, shapekey, raw_delta_name, stereo, eyelid in temp:
            item = controllers.add()
            item.controller_name = controller_name
            item.shapekey = shapekey
            item.raw_delta_name = raw_delta_name
            item.stereo = stereo
            item.eyelid = eyelid

        ob.vs.dme_flexcontrollers_index = 0
        return {'FINISHED'}


class SMD_OT_PreviewFlexController(Operator):
    bl_idname= "dme.preview_flexcontroller"
    bl_label= "Preview Flex Controller"
    bl_options: set = {'INTERNAL', 'UNDO'}
    
    reset_others: BoolProperty(
        name="Reset Others",
        description="Reset all other shape keys to 0",
        default=True
    )
    
    @classmethod
    def poll(cls, context) -> bool:
        ob = context.object
        return bool(ob and ob.type == 'MESH' and ob.data.shape_keys and len(ob.vs.dme_flexcontrollers) > 0)
    
    def execute(self, context) -> set:
        ob = context.object
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


class SMD_OT_ClearFlexControllers(Operator):
    bl_idname= "dme.clear_flexcontrollers"
    bl_label= "Clear All Flex Controllers"
    bl_options: set = {'INTERNAL', 'UNDO'}
    
    @classmethod
    def poll(cls, context) -> bool:
        return bool(len(context.object.vs.dme_flexcontrollers) > 0)
    
    def invoke(self, context, event) -> set:
        return context.window_manager.invoke_confirm(self, event)
    
    def execute(self, context) -> set:
        context.object.vs.dme_flexcontrollers.clear()
        context.object.vs.dme_flexcontrollers_index = 0
        return {'FINISHED'}


class SMD_OT_AddVertexMapRemap(Operator):
    bl_idname = "smd.add_vertex_map_remap"
    bl_label = "Apply Remap Range"

    map_name: StringProperty()

    def execute(self, context) -> set:
        active_object = context.object
        if active_object and active_object.type == 'MESH':
            group = active_object.vs.vertex_map_remaps.add()
            group.group = self.map_name
            group.min = 0.0
            group.max = 1.0
        return {'FINISHED'}


class SMD_UL_VertexAnimationItem(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index): # pyright: ignore
        r = layout.row()
        r.alignment='LEFT'
        r.prop(item,"name",text="",emboss=False)
        r = layout.row(align=True)
        r.alignment='RIGHT'
        r.operator(SMD_OT_PreviewVertexAnimation.bl_idname,text="",icon='PAUSE' if context.screen.is_animation_playing else 'PLAY')
        r.prop(item,"start",text="")
        r.prop(item,"end",text="")
        r.prop(item,"export_sequence",text="",icon='ACTION')


class SMD_OT_AddVertexAnimation(Operator):
    bl_idname = "smd.vertexanim_add"
    bl_label = get_id("vca_add")
    bl_description = get_id("vca_add_tip")
    bl_options = {'INTERNAL', 'UNDO'}
    
    index: IntProperty()
    
    def execute(self,context) -> set:
        item = get_valid_vertexanimation_object(context.object)
        item.vs.vertex_animations.add()
        item.vs.active_vertex_animation = len(item.vs.vertex_animations) - 1
        return {'FINISHED'}


class SMD_OT_RemoveVertexAnimation(Operator):
    bl_idname = "smd.vertexanim_remove"
    bl_label = get_id("vca_remove")
    bl_description = get_id("vca_remove_tip")
    bl_options = {'INTERNAL', 'UNDO'}

    index : IntProperty(min=0)
    vertexindex : IntProperty(min=0)

    def execute(self, context) -> set:
        item = get_valid_vertexanimation_object(context.object)
        if len(item.vs.vertex_animations) > self.vertexindex:
            item.vs.vertex_animations.remove(self.vertexindex)
            item.vs.active_vertex_animation = max(
                0, min(self.vertexindex, len(item.vs.vertex_animations) - 1)
            )
        return {'FINISHED'}


class SMD_OT_PreviewVertexAnimation(Operator):
    bl_idname = "smd.vertexanim_preview"
    bl_label = get_id("vca_preview")
    bl_description = get_id("vca_preview_tip")
    bl_options = {'INTERNAL'}

    index: IntProperty(min=0)
    vertexindex: IntProperty(min=0)

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


class SMD_OT_GenerateVertexAnimationQCSnippet(Operator):
    bl_idname = "smd.vertexanim_generate_qc"
    bl_label = get_id("vca_qcgen")
    bl_description = get_id("vca_qcgen_tip")
    bl_options = {'INTERNAL'}

    index: IntProperty(min=0)

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


class SMD_OT_CopyBoneExportName(Operator):
    bl_idname = "smd.copy_bone_export_name"
    bl_label = 'Copy Name to Clipboard'
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return bool(context.object and context.object.type == 'ARMATURE' and context.active_bone)
    
    def execute(self, context) -> set:
        active_object = context.object
        active_bone = active_object.data.bones.get(context.active_bone.name)
        
        bpy.context.window_manager.clipboard = get_bone_exportname(active_bone, for_write=True)
        self.report({'INFO'}, "Name copied to clipboard.")
        return {'FINISHED'}
    

class SMD_OT_AssignBoneRotExportOffset(Operator):
    bl_idname = 'smd.assign_bone_rot_export_offset'
    bl_label = 'Assign Bone Target Forward'
    bl_options: set = {'REGISTER', 'UNDO'}
    bl_description = "Target Bone Forward: Sets the bone's forward direction for export. Blender bones use Y-forward by default in edit mode (check with 'normal' gizmo). This property specifies which axis will be forward in the target engine/application. Example: Setting 'X-forward' rotates the bone +90° around Z on export, converting Y-forward → X-forward. Rotation order on export: Z→Y→X (translation: X→Y→Z)"
    
    export_rot_target : EnumProperty(
        name='Rotation Target',
        description="Target Bone Forward (Assuming the bone is currently on Blender's Y-forward format)",
        items=[
            ('X', '+X', ''),
            ('Y', '+Y', ''),
            ('Z', '+Z', ''),
            ('X_INVERT', '-X', ''),
            ('Y_INVERT', '-Y', ''),
            ('Z_INVERT', '-Z', ''),
        ], default='X'
    )
    
    only_active_bone : BoolProperty(
        name='Only Active Bone',
        default=False
    )
    
    @classmethod
    def poll(cls, context) -> bool:
        selected_arms = [ob for ob in context.selected_objects if is_armature(ob)]
        return bool(selected_arms) and context.mode not in {'EDIT', 'EDIT_ARMATURE'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


    def draw(self, context):
        layout = self.layout
        layout.label(text='Y to...')
        row = layout.row(align=True)
        row.prop(self,'export_rot_target',expand=True)


    def execute(self, context) -> set:
        selected_arms = [ob for ob in context.selected_objects if is_armature(ob)]

        if not selected_arms:
            return {'CANCELLED'}

        any_bones_found = False

        for arm in selected_arms:
            if self.only_active_bone:
                selected_bones = [arm.data.bones.active] if arm.data.bones.active else []
            else:
                selected_bones = [b for b in arm.data.bones if not b.hide_select and b.select]

            if not selected_bones:
                continue

            any_bones_found = True

            for bone in selected_bones:
                if not bone.vs:
                    continue

                bone.vs.export_rotation_offset_x = 0
                bone.vs.export_rotation_offset_y = 0
                bone.vs.export_rotation_offset_z = 0

                match self.export_rot_target:
                    case 'X':
                        bone.vs.export_rotation_offset_z = math.radians(90)
                    case 'Z':
                        bone.vs.export_rotation_offset_x = math.radians(-90)
                    case 'X_INVERT':
                        bone.vs.export_rotation_offset_z = math.radians(-90)
                    case 'Y_INVERT':
                        bone.vs.export_rotation_offset_y = math.radians(180)
                    case 'Z_INVERT':
                        bone.vs.export_rotation_offset_x = math.radians(-90)

        if not any_bones_found:
            self.report({'ERROR'}, 'No active or selected bones')
            return {'CANCELLED'}

        return {'FINISHED'}


class SMD_PT_All_Jigglebones(Properties_SubPanel):
    bl_label = ''
    bl_parent_id = 'SMD_PT_Armature'
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        active_armature = get_armature(context.object)
        return bool(active_armature)
    
    def draw_header(self, context):
        layout = self.layout
        
        active_armature = get_armature(context.object)
        jigglebones = get_jigglebones(active_armature)

        self.bl_label = 'All Jigglebones' + ' (' + str(len(jigglebones)) + ')'
    
    def draw(self, context):
        layout = self.layout
        active_armature = get_armature(context.object)
        
        box = layout.box()
        col = box.column(align=True)
        
        jigglebones = get_jigglebones(active_armature)
        
        if jigglebones:
            for jigglebone in jigglebones:
                row = col.row(align=True)
                row.label(text=jigglebone.name, icon='BONE_DATA')
                
                collection_count = len(jigglebone.collections)
                if collection_count == 1:
                    row.label(text=jigglebone.collections[0].name, icon='GROUP_BONE')
                elif collection_count > 1:
                    row.label(text="In Multiple Collection", icon='GROUP_BONE')
                else:
                    row.label(text="Not in Collection", icon='GROUP_BONE')
        else:
            col.label(text='No Jigglebones', icon='INFO')
    

class SMD_PT_All_Hitboxes(Properties_SubPanel):
    bl_label = ''
    bl_parent_id = 'SMD_PT_Armature'
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        active_armature = get_armature(context.object)
        return bool(active_armature)
    
    def draw_header(self, context):
        layout = self.layout
        
        active_armature = get_armature(context.object)
        hitboxes = get_hitboxes(active_armature)
        
        self.bl_label = 'All Hitboxes' + ' (' + str(len(hitboxes)) + ')'
        
    def draw(self, context):
        layout = self.layout
        active_armature = get_armature(context.object)
        
        box = layout.box()
        col = box.column(align=True)

        hitboxes = get_hitboxes(active_armature)
        if hitboxes:
            for hbox in hitboxes:
                try:
                    row = col.row()
                    row.label(text=hbox.name, icon='CUBE')
                    row.prop_search(hbox, 'parent_bone', search_data=active_armature.data, search_property='bones', text='')
                    row.prop(hbox.vs, 'smd_hitbox_group', text='')
                except:
                    continue
        else:
            col.label(text='No Hitboxes', icon='INFO')


class SMD_PT_All_Attachments(Properties_SubPanel):
    bl_label = ''
    bl_parent_id = 'SMD_PT_Armature'
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        active_armature = get_armature(context.object)
        return bool(active_armature)
    
    def draw_header(self, context):
        layout = self.layout
        
        active_armature = get_armature(context.object)
        attachments = get_attachments(active_armature)
        
        self.bl_label = 'All Attachments' + ' (' + str(len(attachments)) + ')'
        
    def draw(self, context):
        layout = self.layout
        active_armature = get_armature(context.object)
        
        box = layout.box()
        col = box.column(align=True)

        attachments = get_attachments(active_armature)
        
        if attachments:
            for attachment in attachments:
                row = col.row(align=True)
                row.label(text=attachment.name, icon='EMPTY_DATA')
                row.prop_search(attachment, 'parent_bone', search_data=active_armature.data, search_property='bones', text='')
        else:
            col.label(text='No Attachments', icon='INFO')


class SMD_OT_CopySourceBoneProps(Operator):
    bl_idname = "smd.copy_bone_props"
    bl_label = "Copy Source Bone Properties"
    bl_options = {"REGISTER", "UNDO"}

    copy_name: BoolProperty(name="Export Name", default=False)
    copy_rotation: BoolProperty(name="Export Rotation Offset", default=True)
    copy_location: BoolProperty(name="Export Location Offset", default=True)
    copy_jigglebone: BoolProperty(name="Jigglebone", default=False)
    to_invoke : BoolProperty(default=True)

    @classmethod
    def poll(cls, context):
        return (
            context.mode == 'POSE'
            and context.active_pose_bone is not None
            and len(context.selected_pose_bones) > 1
        )

    def invoke(self, context, event):
        if self.to_invoke:
            self.copy_jigglebone = context.active_pose_bone.bone.vs.bone_is_jigglebone
            return context.window_manager.invoke_props_dialog(self)
        else:
            return self.execute(context)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Properties to copy:")
        layout.prop(self, "copy_name")
        layout.prop(self, "copy_rotation")
        layout.prop(self, "copy_location")
        row = layout.row()
        row.prop(self, "copy_jigglebone")
        row.enabled = context.active_pose_bone.bone.vs.bone_is_jigglebone

    def execute(self, context) -> set:
        src = context.active_pose_bone.bone.vs

        props = []
        if self.copy_name:
            props.append('export_name')
        if self.copy_rotation:
            props += [
                'ignore_rotation_offset',
                'export_rotation_offset_x',
                'export_rotation_offset_y',
                'export_rotation_offset_z',
            ]
        if self.copy_location:
            props += [
                'ignore_location_offset',
                'export_location_offset_x',
                'export_location_offset_y',
                'export_location_offset_z',
            ]
        if self.copy_jigglebone:
            if not src.bone_is_jigglebone:
                self.report({'WARNING'}, "Active bone is not a jigglebone")
                return {'CANCELLED'}
            props += [
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
                'jiggle_amplitude',
            ]

        if not props:
            self.report({'WARNING'}, "Nothing selected to copy")
            return {'CANCELLED'}

        targets = [pb for pb in context.selected_pose_bones if pb != context.active_pose_bone]
        for pb in targets:
            for prop in props:
                try:
                    setattr(pb.bone.vs, prop, getattr(src, prop))
                except AttributeError:
                    continue

        self.report({'INFO'}, f"Copied bone properties to {len(targets)} bone(s)")
        return {'FINISHED'}