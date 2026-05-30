import bpy
from bpy.types import UIList, UILayout, Collection, Object, UI_UL_list
from ..utils import State, get_armature, countShapes, MakeObjectIcon, sanitize_string_for_delta, get_id, get_jigglebones, get_hitboxes, get_attachments


class SMD_UL_KitsuneResourceEntries(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname): # pyright: ignore
        if self.layout_type == 'GRID':
            layout.alignment = 'CENTER'

        vs = data
        if item.entry_type == 'MODEL':
            source = next((e for e in vs.kitsuneresource_model_entries if e.name == item.name), None)
            entry_icon = 'MESH_DATA'
        else:
            source = next((e for e in vs.kitsuneresource_data_entries if e.name == item.name), None)
            entry_icon = 'FILE_CACHE'

        target = source if source is not None else item
        layout.prop(target, "export", text="",
                    icon='CHECKBOX_HLT' if target.export else 'CHECKBOX_DEHLT', emboss=False)
        layout.label(text=item.name, icon=entry_icon)


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

        split1 = row.split(factor=0.7)
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
            row.label(text=str(num_vca), icon='EDITMODE_HLT')

        subdir = obj.vs.subdir
        if subdir and subdir != ".":
            row.label(text=f"{subdir}/")


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


class SMD_UL_DmeFlexControllers(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index, flt_flag):
        row = layout.row(align=True)

        has_name = bool(item.controller_name and item.controller_name.strip())
        name_row = row.row(align=True)
        name_row.alert = not has_name
        name_row.label(
            text=item.controller_name if has_name else "(unnamed)",
            icon='SHAPEKEY_DATA' if has_name else 'ERROR',
        )

        info_row = row.row(align=True)
        info_row.alignment = 'RIGHT'
        if item.shapekey:
            info_row.label(text=item.shapekey)
        if item.stereo:
            info_row.label(text="", icon='MOD_MIRROR')
        if item.eyelid:
            info_row.label(text="", icon='HIDE_OFF')


class SMD_UL_DmeFlexRules(UIList):
    _ICONS = {
        'EXPRESSION':  'DRIVER',
        'PASSTHROUGH': 'SHAPEKEY_DATA',
        'LOCALVAR':    'NODE',
        'DOMINATION':  'RESTRICT_SELECT_ON',
        'CORRECTIVE':  'SCULPTMODE_HLT',
    }

    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index, flt_flag):
        ob = context.object
        row = layout.row(align=True)

        type_icon = self._ICONS.get(item.rule_type, 'QUESTION')
        row.label(text="", icon=type_icon)

        if item.rule_type == 'CORRECTIVE':
            name_row = row.row(align=True)
            name_row.alert = not item.components
            name_row.label(text=item.components if item.components else "(no components)")

        elif item.rule_type == 'DOMINATION':
            dom_label = item.dominator_names[:24] + ("…" if len(item.dominator_names) > 24 else "") if item.dominator_names else "(no dominators)"
            sup_label = item.suppressed_names[:20] + ("…" if len(item.suppressed_names) > 20 else "") if item.suppressed_names else ""
            name_col = row.row(align=True)
            name_col.alert = not item.dominator_names or not item.suppressed_names
            name_col.label(text=dom_label)
            if sup_label:
                right = row.row(align=True)
                right.alignment = 'RIGHT'
                right.label(text="→ " + sup_label)
        else:
            # PASSTHROUGH names must be a controller; EXPRESSION names must be a delta or local var
            name_alert = False
            if item.name:
                if item.rule_type == 'PASSTHROUGH':
                    ctrl_names = {fc.controller_name for fc in ob.vs.dme_flexcontrollers if fc.controller_name and fc.controller_name.strip()}
                    name_alert = item.name not in ctrl_names
                elif item.rule_type == 'EXPRESSION':
                    sk = ob.data.shape_keys if ob.data and hasattr(ob.data, 'shape_keys') else None
                    in_shapekeys = sk is not None and item.name in sk.key_blocks
                    in_localvars = any(r.rule_type == 'LOCALVAR' and r.name == item.name for r in ob.vs.dme_flex_rules)
                    name_alert = not in_shapekeys and not in_localvars
            name_row = row.row(align=True)
            name_row.alert = name_alert
            display_name = item.name if item.name else ("(unnamed)" if item.rule_type != 'LOCALVAR' else "(local var)")
            name_row.label(text=display_name)

            if item.rule_type == 'EXPRESSION' and item.expression:
                expr_row = row.row(align=True)
                expr_row.alignment = 'RIGHT'
                truncated = item.expression[:28] + ("…" if len(item.expression) > 28 else "")
                expr_row.label(text=truncated)
            elif item.rule_type == 'PASSTHROUGH':
                pass_row = row.row(align=True)
                pass_row.alignment = 'RIGHT'
                pass_row.enabled = False
                pass_row.label(text="pass-through")


class SMD_UL_VertexAnimationItem(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index): # pyright: ignore
        r = layout.row()
        r.alignment='LEFT'
        r.prop(item,"name",text="",emboss=False)
        r = layout.row(align=True)
        r.alignment='RIGHT'
        r.operator("smd.vertexanim_preview",text="",icon='PAUSE' if context.screen.is_animation_playing else 'PLAY')
        r.prop(item,"start",text="")
        r.prop(item,"end",text="")
        r.prop(item,"export_sequence",text="",icon='ACTION')


class SMD_UL_ArmatureItems(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        arm = get_armature(context.object)
        if active_propname == 'arm_hitbox_index':
            obj = item.obj
            if obj:
                row = layout.row()
                row.label(text=obj.name, icon='CUBE')
                if arm:
                    row.prop_search(obj, 'parent_bone', arm.data, 'bones', text='')
                row.prop(obj.vs, 'smd_hitbox_group', text='')
        elif active_propname == 'arm_attachment_index':
            obj = item.obj
            if obj:
                row = layout.row(align=True)
                row.label(text=obj.name, icon='EMPTY_DATA')
                if arm:
                    row.prop_search(obj, 'parent_bone', arm.data, 'bones', text='')
        else:  # arm_jigglebone_index
            bone = arm.data.bones.get(item.bone_name) if arm else None
            row = layout.row(align=True)
            row.label(text=item.bone_name or '?', icon='BONE_DATA')
            if bone:
                count = len(bone.collections)
                if count == 1:
                    row.label(text=bone.collections[0].name, icon='GROUP_BONE')
                elif count > 1:
                    row.label(text=get_id('label_in_multiple_collection', format_string=True), icon='GROUP_BONE')
                else:
                    row.label(text=get_id('label_not_in_collection', format_string=True), icon='GROUP_BONE')


class SMD_UL_ProcBones(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        proc_type = getattr(item, 'proc_type', 'TRIGGER')
        row.label(text='', icon='ACTION' if proc_type == 'TRIGGER' else 'CON_TRACKTO')
        row.label(text=item.helper_bone if item.helper_bone else "", icon='BONE_DATA')
        row.label(text=item.driver_bone if item.driver_bone else "", icon='DRIVER')
        if proc_type == 'TRIGGER':
            row.label(text=item.action.name if item.action else "", icon='ACTION')
