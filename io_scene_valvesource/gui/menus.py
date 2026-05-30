import bpy
from bpy.types import Menu
from ..utils import (get_id, getSelectedExportables, count_exports, is_armature,
                     get_attachments, get_hitboxes, get_jigglebones)
from ..export_smd import SmdExporter, PrefabExporter, KitsuneResourceCompile
from .operators import (
    SMD_OT_AddAllFlexControllers,
    SMD_OT_SortFlexControllers,
    SMD_OT_AutoAssignFlexGroups,
    SMD_OT_CopyFlexControllers,
    SMD_OT_ClearFlexControllers,
    SMD_OT_ProcBoneDuplicate,
    SMD_OT_ProcBoneCopyActive,
    SMD_OT_ProcBoneCopyByDriverBone,
    SMD_OT_ProcBoneCopyAll,
    SMD_OT_ProcBoneCopyTolerance,
    SMD_OT_ProcBonePasteEntries,
    SMD_OT_ProcBonePasteTolerance,
)


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
                if type(self).__name__ == 'SMD_PT_Scene':
                    if i == 0: group_col = l.column(align=True)
                    if i % 2 == 0: group_layout = group_col.row(align=True)
                group_layout.operator(SmdExporter.bl_idname, text=group.name, icon='GROUP').collection = group.item.name

            if len(exportables) - len(groups) > 1:
                l.operator(SmdExporter.bl_idname, text=get_id("exportmenu_selected", True).format(len(exportables)), icon='OBJECT_DATA')
            elif len(single_obs):
                op = l.operator(SmdExporter.bl_idname, text=single_obs[0].name, icon=single_obs[0].icon)
                op.object_name = single_obs[0].item.name

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
                _emp_att = get_attachments(arm)
                _avs_pb  = getattr(getattr(arm.data, 'vs', None), 'proc_bones', [])
                _lookat_count = len({e.driver_bone for e in _avs_pb
                                     if getattr(e, 'proc_type', 'TRIGGER') == 'LOOKAT'
                                     and e.driver_bone and arm.data.bones.get(e.driver_bone)})
                if (_emp_att or _lookat_count) and arm.vs.attachment_prefabfile:
                    l.operator(PrefabExporter.bl_idname, text=f"Attachments ({len(_emp_att) + _lookat_count}) \"{arm.name}\"", icon='EMPTY_ARROWS').export_type = 'ATTACHMENTS'
                if get_hitboxes(arm) and arm.vs.hitbox_prefabfile:
                    l.operator(PrefabExporter.bl_idname, text=f"Hitboxes ({len(get_hitboxes(arm))}) \"{arm.name}\"", icon='MESH_CUBE').export_type = 'HITBOXES'
                _proc_entries = [e for e in getattr(getattr(arm.data, 'vs', None), 'proc_bones', [])
                                 if e.helper_bone and arm.data.bones.get(e.helper_bone)]
                if _proc_entries and arm.vs.procedural_prefabfile:
                    l.operator(PrefabExporter.bl_idname, text=f"Procedural ({len(_proc_entries)}) \"{arm.name}\"", icon='CON_TRACKTO').export_type = 'PROCEDURAL'
            else:
                is_hitbox = active.type == 'EMPTY' and active.empty_display_type == 'CUBE' and getattr(active.vs, 'smd_hitbox', False)
                is_attachment = active.type == 'EMPTY' and getattr(active.vs, 'dmx_attachment', False)

                if is_hitbox and get_hitboxes(arm) and arm.vs.hitbox_prefabfile:
                    l.operator(PrefabExporter.bl_idname, text=f"Hitboxes ({len(get_hitboxes(arm))}) \"{arm.name}\"", icon='MESH_CUBE').export_type = 'HITBOXES'
                if is_attachment and get_attachments(arm) and arm.vs.attachment_prefabfile:
                    l.operator(PrefabExporter.bl_idname, text=f"Attachments ({len(get_attachments(arm))}) \"{arm.name}\"", icon='EMPTY_ARROWS').export_type = 'ATTACHMENTS'


class SMD_MT_KitsuneCompileChoice(Menu):
    bl_label  = "KitsuneResource"

    def draw(self, context):
        layout = self.layout
        vs     = context.scene.vs
        checked_model_count = sum(1 for e in vs.kitsuneresource_model_entries if e.export)
        checked_data_count  = sum(1 for e in vs.kitsuneresource_data_entries if e.export)
        checked_count = checked_model_count + checked_data_count

        op = layout.operator(KitsuneResourceCompile.bl_idname, text="Compile All", icon='WORLD')
        op.export_choice = 'ALL'
        op.entry_index   = -1

        op = layout.operator(KitsuneResourceCompile.bl_idname, text=f"Compile ({checked_count})", icon='CHECKBOX_HLT')
        op.export_choice = 'CHECKED'
        op.entry_index   = -1

        if vs.kitsuneresource_model_entries or vs.kitsuneresource_data_entries:
            layout.separator()
            for i, entry in enumerate(vs.kitsuneresource_model_entries):
                op = layout.operator(KitsuneResourceCompile.bl_idname, text=entry.name, icon='MESH_DATA')
                op.export_choice = 'ENTRY'
                op.entry_index   = i
                op.entry_type    = 'MODEL'

            layout.separator()

            for i, entry in enumerate(vs.kitsuneresource_data_entries):
                op = layout.operator(KitsuneResourceCompile.bl_idname, text=entry.name, icon='FILE_CACHE')
                op.export_choice = 'ENTRY'
                op.entry_index   = i
                op.entry_type    = 'DATA'


class SMD_MT_ConfigureScene(Menu):
    bl_label = get_id("exporter_report_menu")
    def draw(self, context ) -> None:
        self.layout.label(text=get_id("exporter_err_unconfigured"))


class SMD_MT_FlexControllerSpecials(Menu):
    bl_label = "Flex Controller Specials"

    def draw(self, context):
        layout = self.layout
        layout.operator(SMD_OT_AddAllFlexControllers.bl_idname, icon='IMPORT',      text=get_id('label_add_all', True))
        layout.operator(SMD_OT_SortFlexControllers.bl_idname,   icon='SORTALPHA',   text=get_id('label_sort_by_name', True))
        layout.operator(SMD_OT_AutoAssignFlexGroups.bl_idname,  icon='GROUP')
        layout.operator(SMD_OT_CopyFlexControllers.bl_idname,   icon='PASTEDOWN')
        layout.separator()
        layout.operator(SMD_OT_ClearFlexControllers.bl_idname,  icon='TRASH',       text="Delete All")


class SMD_MT_ProcBoneSpecials(Menu):
    bl_label = "Proc Bone Specials"

    def draw(self, context):
        layout = self.layout
        layout.operator(SMD_OT_ProcBoneDuplicate.bl_idname,         icon='DUPLICATE')
        layout.separator()
        layout.operator(SMD_OT_ProcBoneCopyActive.bl_idname,        icon='COPYDOWN')
        layout.operator(SMD_OT_ProcBoneCopyAll.bl_idname,           icon='COPYDOWN')
        layout.operator(SMD_OT_ProcBoneCopyByDriverBone.bl_idname,  icon='COPYDOWN')
        layout.operator(SMD_OT_ProcBonePasteEntries.bl_idname,      icon='PASTEDOWN')
        layout.separator()
        layout.operator(SMD_OT_ProcBoneCopyTolerance.bl_idname,     icon='COPYDOWN')
        layout.operator(SMD_OT_ProcBonePasteTolerance.bl_idname,    icon='PASTEDOWN')
