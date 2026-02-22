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
from .utils import getSelectedExportables, count_exports, get_id, State, Compiler, ExportFormat
from .export_smd import SmdExporter, PrefabExporter
from .kitsunetools.commonutils import is_armature, get_attachments, get_hitboxes, get_jigglebones


class SMD_MT_ExportChoice(bpy.types.Menu):
    bl_label = get_id("exportmenu_title")

    def draw(self, context : bpy.types.Context) -> None:
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

        active = context.active_object

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
                    l.operator(PrefabExporter.bl_idname, text=f"Export Jigglebones ({len(get_jigglebones(arm))})", icon='BONE_DATA').export_type = 'JIGGLEBONES'
                if get_attachments(arm) and arm.vs.attachment_prefabfile:
                    l.operator(PrefabExporter.bl_idname, text=f"Export Attachments ({len(get_attachments(arm))})", icon='EMPTY_ARROWS').export_type = 'ATTACHMENTS'
                if get_hitboxes(arm) and arm.vs.hitbox_prefabfile:
                    l.operator(PrefabExporter.bl_idname, text=f"Export Hitboxes ({len(get_hitboxes(arm))})", icon='MESH_CUBE').export_type = 'HITBOXES'
            else:
                is_hitbox = active.type == 'EMPTY' and active.empty_display_type == 'CUBE' and getattr(active.vs, 'smd_hitbox', False)
                is_attachment = active.type == 'EMPTY' and getattr(active.vs, 'dmx_attachment', False)

                if is_hitbox and get_hitboxes(arm) and arm.vs.hitbox_prefabfile:
                    l.operator(PrefabExporter.bl_idname, text=f"Export Hitboxes ({len(get_hitboxes(arm))})", icon='MESH_CUBE').export_type = 'HITBOXES'
                if is_attachment and get_attachments(arm) and arm.vs.attachment_prefabfile:
                    l.operator(PrefabExporter.bl_idname, text=f"Export Attachments ({len(get_attachments(arm))})", icon='EMPTY_ARROWS').export_type = 'ATTACHMENTS'


class SMD_PT_Scene(bpy.types.Panel):
    bl_label = get_id("exportpanel_title")
    bl_category = 'KitsuneSrcTool'
    bl_region_type = 'UI'
    bl_space_type = 'VIEW_3D'

    def draw(self, context: bpy.types.Context) -> None:
        l = self.layout
        scene = context.scene

        # Export
        l.operator(SmdExporter.bl_idname, text="Export", icon='EXPORT')

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

        # Axes
        row = box.row().split(factor=0.33)
        row.label(text=get_id("up_axis") + ":")
        row.row().prop(scene.vs, "up_axis", expand=True)

        row = box.row().split(factor=0.33)
        row.label(text=get_id("up_axis_offset") + ":")
        row.row().prop(scene.vs, "up_axis_offset", expand=True)

        row = box.row().split(factor=0.33)
        row.label(text=get_id("forward_axis") + ":")
        row.row().prop(scene.vs, "forward_axis", expand=True)

        # Mesh
        box.prop(scene.vs, "weightlink_threshold", slider=True)
        box.prop(scene.vs, "vertex_influence_limit", slider=True)


class SMD_MT_ConfigureScene(bpy.types.Menu):
    bl_label = get_id("exporter_report_menu")
    def draw(self, context : bpy.types.Context) -> None:
        self.layout.label(text=get_id("exporter_err_unconfigured"))
