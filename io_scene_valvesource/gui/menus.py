import bpy
from bpy.types import Menu
from ..utils import (get_id, getSelectedExportables, count_exports, is_armature,
                     prefab_available_types, prefab_type_info)
from ..export_smd import SmdExporter, PrefabExporter, KitsuneResourceCompile
from .operators import (
    SMD_OT_AddAllFlexControllers,
    SMD_OT_ImportFlexControllersFromText,
    SMD_OT_SortFlexControllers,
    SMD_OT_AutoAssignFlexGroups,
    SMD_OT_CopyFlexControllers,
    SMD_OT_ClearFlexControllers,
    SMD_OT_MigrateQCDeltasToOverrides,
    SMD_OT_ProcBoneDuplicate,
    SMD_OT_ProcBoneCopyActive,
    SMD_OT_ProcBoneCopyByDriverBone,
    SMD_OT_ProcBoneCopyAll,
    SMD_OT_ProcBoneCopyTolerance,
    SMD_OT_ProcBonePasteEntries,
    SMD_OT_ProcBonePasteTolerance,
    SMD_OT_HitboxDuplicate,
    SMD_OT_HitboxCopyEntry,
    SMD_OT_HitboxCopyAll,
    SMD_OT_HitboxPasteEntries,
    SMD_OT_HitboxPasteValues,
    SMD_OT_HitboxCopyToArmature,
    SMD_OT_HitboxMirror,
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
            available = prefab_available_types(arm)
            if is_armature(active):
                allowed = {t for t, _ in available}
            else:
                # From a child object, only offer the prefabs relevant to it.
                is_attachment = active.type == 'EMPTY' and getattr(active.vs, 'dmx_attachment', False)
                allowed = {'HITBOXES'}
                if is_attachment:
                    allowed.add('ATTACHMENTS')

            entries = [(t, c) for t, c in available if t in allowed]
            if entries:
                l.separator()
                for ptype, count in entries:
                    icon, label = prefab_type_info[ptype]
                    l.operator(PrefabExporter.bl_idname,
                               text=f"{label} ({count}) \"{arm.name}\"",
                               icon=icon).export_type = ptype


class SMD_MT_KitsuneCompileChoice(Menu):
    bl_label = "KitsuneResource"

    def draw(self, context):
        layout = self.layout
        vs = context.scene.vs

        layout.operator("smd.kitsuneresource_configure", text="Configure...", icon='SETTINGS')

        has_valid_config = (
            len(vs.kitsuneresource_app_path) > 0
            and len(vs.kitsuneresource_config) > 0
            and len(vs.kitsuneresource_project_path) > 0
            and (len(vs.kitsuneresource_model_entries) > 0 or len(vs.kitsuneresource_data_entries) > 0)
        )

        if not has_valid_config:
            return

        layout.separator()
        layout.operator_context = 'EXEC_DEFAULT'

        checked_count = (
            sum(1 for e in vs.kitsuneresource_model_entries if e.export)
            + sum(1 for e in vs.kitsuneresource_data_entries if e.export)
        )

        op = layout.operator(KitsuneResourceCompile.bl_idname, text="Compile All", icon='WORLD')
        op.export_choice = 'ALL'
        op.entry_index   = -1

        op = layout.operator(KitsuneResourceCompile.bl_idname, text=f"Compile ({checked_count})", icon='CHECKBOX_HLT')
        op.export_choice = 'CHECKED'
        op.entry_index   = -1

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
        layout.operator(SMD_OT_ImportFlexControllersFromText.bl_idname, icon='TEXT', text=get_id('label_import_flex_text', True))
        layout.operator(SMD_OT_SortFlexControllers.bl_idname,   icon='SORTALPHA',   text=get_id('label_sort_by_name', True))
        layout.operator(SMD_OT_AutoAssignFlexGroups.bl_idname,  icon='GROUP')
        layout.operator(SMD_OT_CopyFlexControllers.bl_idname,   icon='PASTEDOWN')
        layout.separator()
        layout.operator(SMD_OT_MigrateQCDeltasToOverrides.bl_idname, icon='FORWARD', text="Migrate QC Deltas to Overrides")
        layout.separator()
        layout.operator(SMD_OT_ClearFlexControllers.bl_idname,  icon='TRASH',       text="Delete All")


class SMD_MT_HitboxSpecials(Menu):
    bl_label = "Hitbox Specials"

    def draw(self, context):
        layout = self.layout
        layout.operator(SMD_OT_HitboxDuplicate.bl_idname,      icon='DUPLICATE')
        layout.separator()
        layout.operator(SMD_OT_HitboxCopyEntry.bl_idname,      icon='COPYDOWN')
        layout.operator(SMD_OT_HitboxCopyAll.bl_idname,        icon='COPYDOWN')
        layout.operator(SMD_OT_HitboxPasteEntries.bl_idname,   icon='PASTEDOWN')
        layout.operator(SMD_OT_HitboxPasteValues.bl_idname,    icon='PASTEDOWN')
        layout.separator()
        layout.operator(SMD_OT_HitboxCopyToArmature.bl_idname, icon='ARMATURE_DATA')
        layout.separator()
        layout.operator(SMD_OT_HitboxMirror.bl_idname, text=get_id('op_hitbox_mirror_x'), icon='MOD_MIRROR').axis = 'X'
        layout.operator(SMD_OT_HitboxMirror.bl_idname, text=get_id('op_hitbox_mirror_y'), icon='MOD_MIRROR').axis = 'Y'
        layout.operator(SMD_OT_HitboxMirror.bl_idname, text=get_id('op_hitbox_mirror_z'), icon='MOD_MIRROR').axis = 'Z'


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
