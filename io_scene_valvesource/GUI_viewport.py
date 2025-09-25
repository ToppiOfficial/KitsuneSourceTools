import bpy, bmesh, json, os
from bpy.props import StringProperty, BoolProperty, EnumProperty, IntProperty, CollectionProperty, FloatProperty, PointerProperty
from .utils import *
from .flex import *
from .core.common import *
from .core.bone import *
from .core.armature import *
from .core.mesh import *
from bpy.types import Panel, UIList, Operator
from math import degrees, radians
from mathutils import Vector
from .keyvalue3 import *
from . import iconloader

class SMD_PT_toolpanel(object):
    bl_label = 'sample_toolpanel'
    bl_category = 'KitsuneSourceTool'
    bl_region_type = 'UI'
    bl_space_type = 'VIEW_3D'
    bl_order = 1
    
class SMD_PT_ContextObject(SMD_PT_toolpanel, Panel):
    bl_label = get_id("panel_context_object")
    
    def draw_header(self, context):
        self.layout.label(icon='OBJECT_DATA')
    
    def draw(self, context):
        l = self.layout
        bx = l.box()
        
        ob = context.object
        
        if ob:
            
            bx.box().label(text=f'Active Object: ({ob.name})')
            
            if not ob.parent:
                row = bx.row(align=True)
                col = row.column()
                col.prop(ob.vs, 'ignore_location_offset', toggle=True)
                col = col.column(align=True)
                if ob.vs.ignore_location_offset: col.active = False
                col.prop(ob.vs, 'export_location_offset_x')
                col.prop(ob.vs, 'export_location_offset_y')
                col.prop(ob.vs, 'export_location_offset_z')

                col = row.column()
                col.prop(ob.vs, 'ignore_rotation_offset', toggle=True)
                col = col.column(align=True)
                if ob.vs.ignore_rotation_offset: col.active = False
                col.prop(ob.vs, 'export_rotation_offset_x')
                col.prop(ob.vs, 'export_rotation_offset_y')
                col.prop(ob.vs, 'export_rotation_offset_z')
            else:
                messages = 'Transform Offset not available for Parented Objects'
                col = bx.column(align=True)
                draw_wrapped_text_col(col, messages, 32, icon='ERROR')
            
        else:
            bx.box().label(text='Select an Object', icon='HELP')
        
class ExportableConfigurationPanel(SMD_PT_toolpanel, Panel):
    bl_label = get_id("panel_context_exportable")
    bl_parent_id = "SMD_PT_ContextObject"
    bl_options = {'DEFAULT_CLOSED'}

class SMD_PT_Armature(ExportableConfigurationPanel):
    bl_label = get_id("panel_context_armature")
    bl_options = set()
    
    def draw_header(self, context):
        title = "Armature"
        self.bl_label = title
        self.layout.label(icon='ARMATURE_DATA')

    @classmethod
    def poll(cls, context):
        return is_armature(context.object)

    def draw(self, context):
        armature = context.object
        
        l = self.layout
        bx = l.box()
        col = bx.column()
        
        col.prop(armature.data.vs, "ignore_bone_exportnames", toggle=True)
        col.row().prop(armature.data.vs,"action_selection",expand=True)
        if armature.data.vs.action_selection != 'CURRENT':
            is_slot_filter = armature.data.vs.action_selection == 'FILTERED' and State.useActionSlots
            col.prop(armature.vs,"action_filter", text = get_id("slot_filter") if is_slot_filter else get_id("action_filter"))
            
        if State.exportFormat == ExportFormat.SMD:
            col.prop(armature.data.vs,"implicit_zero_bone")
            col.prop(armature.data.vs,"legacy_rotation")

        if armature.animation_data and not State.useActionSlots:
            col.template_ID(armature.animation_data, "action", new="action.new")

class DME_UL_FlexControllers(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        ob = context.object
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            
            split1 = row.split(factor=0.4, align=True)
            split1.prop_search(item, "shapekey", ob.data.shape_keys, "key_blocks", text="")

            split2 = split1.split(align=True)
            split2.prop(item, "eyelid", toggle=True)
            split2.prop(item, "stereo", toggle=True)

            split3 = split1.split(align=True)
            split3.prop(item, "dme_min", text="Min")
            split3.prop(item, "dme_max", text="Max")

        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=item.shapekey)
            
class DME_OT_AddFlexController(Operator):
    bl_idname = "dme.add_flexcontroller"
    bl_label = "Add Flex Controller"
    bl_options = {'INTERNAL', 'UNDO'}  

    def execute(self, context):
        ob = context.object

        new_item = ob.vs.dme_flexcontrollers.add()
        ob.vs.dme_flexcontrollers_index = len(ob.vs.dme_flexcontrollers) - 1
        new_item.shapekey = ""
        return {'FINISHED'}

class DME_OT_RemoveFlexController(Operator):
    bl_idname = "dme.remove_flexcontroller"
    bl_label = "Remove Flex Controller"
    bl_options = {'INTERNAL', 'UNDO'}  

    @classmethod
    def poll(cls, context):
        ob = context.object
        return ob and hasattr(ob, "vs") and len(ob.vs.dme_flexcontrollers) > 0

    def execute(self, context):
        ob = context.object

        idx = ob.vs.dme_flexcontrollers_index
        ob.vs.dme_flexcontrollers.remove(idx)
        ob.vs.dme_flexcontrollers_index = max(0, idx - 1)
        return {'FINISHED'}

class SMD_PT_ShapeKeys(ExportableConfigurationPanel):
    bl_label = get_id("exportables_flex_props")
    bl_options = set()

    @classmethod
    def poll(cls, context):
        return is_mesh(context.object) and hasShapes(context.object,valid_only=False)
    
    def draw_header(self, context):
        self.layout.label(icon='SHAPEKEY_DATA')
    
    def draw(self, context):
        l = self.layout
        bx = l.box()
        col = bx.column()
        item = context.object
        col.prop(item.data.vs, "bake_shapekey_as_basis_normals", toggle=True, icon='NORMALS_FACE')
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
            r.label(text=item.data.name + ":",icon=MakeObjectIcon(item,suffix='_DATA'),translate=False)
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

SMD_OT_CreateVertexMap_idname = "smd.vertex_map_create_"
SMD_OT_SelectVertexMap_idname = "smd.vertex_map_select_"
SMD_OT_RemoveVertexMap_idname = "smd.vertex_map_remove_"

for map_name in vertex_maps:

    class SelectVertexColorMap(bpy.types.Operator):
        bl_idname = SMD_OT_SelectVertexMap_idname + map_name
        bl_label = bl_description = get_id("vertmap_select")
        bl_options = {'INTERNAL'}
        vertex_map = map_name
    
        @classmethod
        def poll(cls, c):
            if not is_mesh(c.active_object):
                return False
            vc_loop = c.active_object.data.vertex_colors.get(cls.vertex_map)
            return vc_loop and not vc_loop.active

        def execute(self, c):
            c.active_object.data.vertex_colors[self.vertex_map].active = True
            return {'FINISHED'}

    class CreateVertexColorMap(bpy.types.Operator):
        bl_idname = SMD_OT_CreateVertexMap_idname + map_name
        bl_label = bl_description = get_id("vertmap_create")
        bl_options = {'INTERNAL'}
        vertex_map = map_name
    
        @classmethod
        def poll(cls, c):
            return is_mesh(c.active_object) and cls.vertex_map not in c.active_object.data.vertex_colors

        def execute(self, c):
            vc = c.active_object.data.vertex_colors.new(name=self.vertex_map)
            vc.data.foreach_set("color", [1.0] * len(vc.data) * 4)
            bpy.context.view_layer.update()
            SelectVertexColorMap.execute(self, c)
            return {'FINISHED'}

    class RemoveVertexColorMap(bpy.types.Operator):
        bl_idname = SMD_OT_RemoveVertexMap_idname + map_name
        bl_label = bl_description = get_id("vertmap_remove")
        bl_options = {'INTERNAL'}
        vertex_map = map_name
    
        @classmethod
        def poll(cls, c):
            return is_mesh(c.active_object) and cls.vertex_map in c.active_object.data.vertex_colors

        def execute(self, c):
            vcs = c.active_object.data.vertex_colors
            vcs.remove(vcs[self.vertex_map])
            return {'FINISHED'}

    bpy.utils.register_class(SelectVertexColorMap)
    bpy.utils.register_class(CreateVertexColorMap)
    bpy.utils.register_class(RemoveVertexColorMap)

class SMD_PT_VertexMaps(ExportableConfigurationPanel):
    bl_label = get_id("vertmap_group_props")

    @classmethod
    def poll(cls, context):
        return is_mesh(context.object)
    
    def draw_header(self, context):
        self.layout.label(icon='VPAINT_HLT')

    def draw(self, context):
        l = self.layout
        bx = l.box()
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

SMD_OT_CreateVertexFloatMap_idname = "smd.vertex_float_map_create_"
SMD_OT_SelectVertexFloatMap_idname = "smd.vertex_float_map_select_"
SMD_OT_RemoveVertexFloatMap_idname = "smd.vertex_float_map_remove_"

for map_name in vertex_float_maps:

    class SelectVertexFloatMap(bpy.types.Operator):
        bl_idname = SMD_OT_SelectVertexFloatMap_idname + map_name
        bl_label = bl_description = get_id("vertmap_select")
        bl_options = {'INTERNAL'}
        vertex_map = map_name

        @classmethod
        def poll(cls, context):
            vg_loop = context.object.vertex_groups.get(cls.vertex_map)
            return vg_loop and not context.active_object.vertex_groups.active == vg_loop

        def execute(self, context):
            context.active_object.vertex_groups.active_index = context.active_object.vertex_groups[self.vertex_map].index
            return {'FINISHED'}

    class CreateVertexFloatMap(bpy.types.Operator):
        bl_idname = SMD_OT_CreateVertexFloatMap_idname + map_name
        bl_label = bl_description = get_id("vertmap_create")
        bl_options = {'INTERNAL'}
        vertex_map = map_name

        @classmethod
        def poll(cls, context):
            return context.object and context.object.type == 'MESH' and cls.vertex_map not in context.object.vertex_groups

        def execute(self, context):
            vc = context.active_object.vertex_groups.new(name=self.vertex_map)

            found = False
            for remap in context.object.vs.vertex_map_remaps:
                if remap.group == map_name:
                    found = True
                    break

            if not found:
                remap = context.object.vs.vertex_map_remaps.add()
                remap.group = map_name
                remap.min = 0.0
                remap.max = 1.0

            SelectVertexFloatMap.execute(self, context)
            return {'FINISHED'}

    class RemoveVertexFloatMap(bpy.types.Operator):
        bl_idname = SMD_OT_RemoveVertexFloatMap_idname + map_name
        bl_label = bl_description = get_id("vertmap_remove")
        bl_options = {'INTERNAL'}
        vertex_map = map_name

        @classmethod
        def poll(cls, context):
            return context.object and context.object.type == 'MESH' and cls.vertex_map in context.active_object.vertex_groups

        def execute(self, context):
            vgs = context.active_object.vertex_groups
            vgs.remove(vgs[self.vertex_map])
            return {'FINISHED'}

    bpy.utils.register_class(SelectVertexFloatMap)
    bpy.utils.register_class(CreateVertexFloatMap)
    bpy.utils.register_class(RemoveVertexFloatMap)

class SMD_OT_AddVertexMapRemap(Operator):
    bl_idname = "smd.add_vertex_map_remap"
    bl_label = "Add Remap Range"

    map_name: bpy.props.StringProperty()

    def execute(self, context):
        active_object = context.object
        if active_object and active_object.type == 'MESH':
            group = active_object.vs.vertex_map_remaps.add()
            group.group = self.map_name
            group.min = 0.0
            group.max = 1.0
        return {'FINISHED'}

class SMD_PT_FloatMaps(ExportableConfigurationPanel):
    bl_label = get_id("vertmap_group_props_float")

    @classmethod
    def poll(cls, context):
        return is_mesh(context.object)
    
    def draw_header(self, context):
        self.layout.label(icon='MOD_CLOTH')

    def draw(self, context):
        l = self.layout
        bx = l.box()
        col = bx.column()
        
        ob = context.active_object
        
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
    bl_label = get_id("exportables_curve_props")
    
    @classmethod
    def poll(cls, context):
        return context.object and hasCurves(context.object)		
    
    def draw_header(self, context):
        self.layout.label(icon='CURVE_DATA')
    
    def draw(self, context):
        l = self.layout
        bx = l.box()
        done = set()
        if hasCurves(context.object):
            row = bx.split(factor=0.33)
            row.label(text=context.object.data.name + ":",icon=MakeObjectIcon(context.object,suffix='_DATA'),translate=False)
            row.prop(context.object.data.vs,"faces",text="")
            done.add(context.object.data)

class SMD_PT_Materials(ExportableConfigurationPanel):
    bl_label = get_id("materials_prop")
    bl_options = set()
    
    @classmethod
    def poll(cls, context):
        return is_mesh(context.object) and has_materials(context.object)
    
    def draw_header(self, context):
        self.layout.label(icon='MATERIAL_DATA')
    
    def draw(self, context):
        l = self.layout
        bx = l.box()
        
        ob = context.object
        currMat = ob.active_material
        bx.box().label(text=f'Active Material: ({currMat.name})')
        
        col = bx.column(align=True)
        col.prop(currMat.vs, 'do_not_export_faces', toggle=True)
        col.prop(currMat.vs, 'do_not_export_faces_vgroup', toggle=True)
        
        if not currMat.vs.do_not_export_faces:
            col = bx.column()
            col.prop(currMat.vs, 'override_dmx_export_path')
            col.prop(currMat.vs, 'non_exportable_vgroup')     
            
class SMD_PT_Bones(ExportableConfigurationPanel):
    bl_label = get_id("bone_prop")
    bl_options = set()
        
    @classmethod
    def poll(cls, context):
        ob = context.object
        return is_armature(ob)
    
    def draw_header(self, context):
        self.layout.label(icon='BONE_DATA')
    
    def draw(self, context):
        ob = context.object
        try:
            bone = ob.data.bones.active if context.mode != 'EDIT_ARMATURE' else ob.data.bones.get(ob.data.edit_bones.active.name)
        except:
            bone = None
        
        l = self.layout
        bx = l.box()
        
        if bone:
            subbx = bx.box()
            subbx.label(text=f'Active Bone: {bone.name}')
            if bone.vs.export_name:
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
    bl_label = 'Empty'

    @classmethod
    def poll(cls, context):
        return is_empty(context.object)
    
    def draw_header(self, context):
        self.layout.label(icon='EMPTY_DATA')

    def draw(self, context):
        l = self.layout
        bx = l.box()
        col = bx.column()
        
        col.prop(context.object.vs, 'dmx_attachment', toggle=True)
        
        if context.object.vs.dmx_attachment and context.object.children:
            col.alert = True
            col.box().label(text="Attachment cannot be a parent",icon='WARNING_LARGE')
         
class SMD_PT_Tools(SMD_PT_toolpanel, Panel):
    bl_label = 'Tools'
    
    def draw_header(self, context):
        self.layout.label(icon='TOOL_SETTINGS')
        
    @classmethod
    def poll(cls, context):
        return context.object
    
    def draw(self, context):
        l = self.layout
        
class ToolsSubPanel(SMD_PT_toolpanel, Panel):
    bl_label = "SubTools"
    bl_parent_id = "SMD_PT_Tools"
    bl_options = {'DEFAULT_CLOSED'}
    
class SMD_PT_Tools_Armature(ToolsSubPanel):
    bl_label = "Armature Tools"
    
    def draw_header(self, context):
        self.layout.label(icon='ARMATURE_DATA')
    
    @classmethod
    def poll(cls, context):
        return is_armature(context.object)
    
    def draw(self, context):
        l = self.layout
        bx = l.box()
        
        col = bx.column()
        col.scale_y = 1.3
        row = col.row(align=True)
        row.operator(TOOLS_OT_ApplyCurrentPoseAsRestPose.bl_idname,icon='POSE_HLT')
        row.operator(TOOLS_OT_MergeArmatures.bl_idname,icon='AUTOMERGE_ON')
        
        col = bx.column()
        col.operator(TOOLS_OT_CleanUnWeightedBones.bl_idname,icon='GROUP_BONE')
        col.operator(TOOLS_OT_RemoveUnusedVertexGroups.bl_idname, icon='GROUP_VERTEX')
        col.operator(TOOLS_OT_CreateProportionActions.bl_idname,icon='ACTION_TWEAK')
        
        col = bx.column(align=True)
        row = col.row(align=True)
        row.scale_y = 1.3
        row.operator(TOOLS_OT_CopyVisPosture.bl_idname,icon='POSE_HLT',text=f'{TOOLS_OT_CopyVisPosture.bl_label} (LOCATION)').copy_type = 'ORIGIN'
        row.operator(TOOLS_OT_CopyVisPosture.bl_idname,icon='POSE_HLT',text=f'{TOOLS_OT_CopyVisPosture.bl_label} (ROTATION)').copy_type = 'ANGLES'

class JSONBONE_UL_BoneList(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if item:
            row = layout.row()
            split = row.split(factor=0.9)
            split.prop(item, 'boneExportName', text="")
            split.label(text="", )
            row.operator(JSONBONE_OT_RemoveItem.bl_idname, text="", icon="X").index = index

class JSONBONE_OT_AddItem(bpy.types.Operator):
    bl_idname = "jsonbone.add_item"
    bl_label = "Add Bone"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}
    
    add_type: bpy.props.EnumProperty(items=[
        ('SELECTED', 'Selected', 'Add all selected bones'),
        ('SINGLE', 'Single', 'Add an empty item')
    ])
    
    def execute(self, context):
        ob = context.object
        if not ob or ob.type != 'ARMATURE':
            self.report({'ERROR'}, "Active object must be an armature")
            return {'CANCELLED'}
        
        collection = ob.vs.json_bonecollections

        if self.add_type == 'SINGLE':
            collection.add()
            return {'FINISHED'}
        
        if context.mode != 'POSE':
            self.report({'ERROR'}, "Must be in Pose mode to add selected bones")
            return {'CANCELLED'}
        
        existing_names = {item.boneExportName for item in collection if hasattr(item, "boneExportName")}
        skipped = 0
        
        for pb in context.selected_pose_bones:
            if pb.name in existing_names:
                skipped += 1
                continue
            item = collection.add()
            if 'boneExportName' in item.bl_rna.properties:
                item.boneExportName = pb.name
        
        if skipped > 0:
            self.report({'INFO'}, f"Skipped {skipped} already existing bone(s)")
        
        return {'FINISHED'}

class JSONBONE_OT_RemoveItem(bpy.types.Operator):
    bl_idname = "jsonbone.remove_item"
    bl_label = "Remove Bone"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}
    
    index: IntProperty()
    
    def execute(self, context):
        coll = context.object.vs.json_bonecollections
        if 0 <= self.index < len(coll):
            coll.remove(self.index)
        return {'FINISHED'}

class JSONBONE_PT_RetargetArmature(ToolsSubPanel):
    bl_label = 'Retarget Armature'
    
    @classmethod
    def poll(cls, context):
        return is_armature(context.object)
    
    def draw_header(self, context):
        self.layout.label(icon='OUTLINER_OB_ARMATURE')
    
    def draw(self, context):
        l = self.layout
        bx = l.box()
        
        col = bx.column()
        
        draw_wrapped_text_col(
            col,
            "Deprecated: This tool is no longer recommended for use",
            max_chars=32,
            icon='WARNING_LARGE',
            alert=True
        )
        
        row = bx.row(align=True)
        row.prop(context.scene.vs, 'defineArmatureCategory', expand=True)
        
        if context.scene.vs.defineArmatureCategory == 'WRITE':
            row = bx.row()
            row.template_list(
                "JSONBONE_UL_BoneList",
                "",
                context.object.vs,
                "json_bonecollections",
                context.object.vs,
                "json_bonecollections_index",
                rows=3
            )
            row = bx.row()
            row.scale_y = 1.25
            split = row.split(factor=0.4,align=True)
            split.operator(JSONBONE_OT_AddItem.bl_idname, icon="ADD", text=JSONBONE_OT_AddItem.bl_label).add_type = 'SINGLE'
            split.operator(JSONBONE_OT_AddItem.bl_idname, icon="ADD", text=JSONBONE_OT_AddItem.bl_label + " (Selected Bones)").add_type = 'SELECTED'
            
            if 0 <= context.object.vs.json_bonecollections_index < len(context.object.vs.json_bonecollections):
                item = context.object.vs.json_bonecollections[context.object.vs.json_bonecollections_index]
                
                col = bx.column(align=True)
                col.prop(item, "boneExportName")
                col.alert = not bool(item.boneName.strip())
                col.prop(item, "boneName")
                col.alert = False
                col.prop(item, "parentBone")
                col.row().prop(item, "writeRotation", expand=True)
                col.prop(item, "writeExportRotationOffset")
                col.prop(item, "writeTwistBone")
                if item.writeTwistBone:
                    col.prop(item, "twistBoneTarget")
                bx.operator(JSONBONE_OT_WriteJson.bl_idname, icon='FILE')
                
        else:
            col = bx.column(align=True)
            col.prop(context.object.vs, 'retarget_armature_ishumanoid', toggle=True)
            
            if context.object.vs.retarget_armature_ishumanoid:
                col = bx.column(align=True)
                col = col.box()
                col = col.column(align=True)
                
                draw_wrapped_text_col(col,text='Head, Chest and Pelvis are required to have inputs', icon='HELP')
                col.prop_search(context.object.vs, 'retarget_armature_head',   context.object.data, "bones", text="Head")
                col.prop_search(context.object.vs, 'retarget_armature_chest',  context.object.data, "bones", text="Chest")
                col.prop_search(context.object.vs, 'retarget_armature_pelvis', context.object.data, "bones", text="Pelvis")

                col.separator()
                col.separator(type='LINE')
                col.separator()

                row = col.row(align=True)
                row.scale_x = 0.2
                row.label(text='Thigh L & R')
                row.prop_search(context.object.vs, 'retarget_armature_thigh_l', context.object.data, "bones", text="")
                row.prop_search(context.object.vs, 'retarget_armature_thigh_r', context.object.data, "bones", text="")

                row = col.row(align=True)
                row.scale_x = 0.2
                row.label(text='Ankle L & R')
                row.prop_search(context.object.vs, 'retarget_armature_ankle_l', context.object.data, "bones", text="")
                row.prop_search(context.object.vs, 'retarget_armature_ankle_r', context.object.data, "bones", text="")

                row = col.row(align=True)
                row.scale_x = 0.2
                row.label(text='Toe L & R')
                row.prop_search(context.object.vs, 'retarget_armature_toe_l', context.object.data, "bones", text="")
                row.prop_search(context.object.vs, 'retarget_armature_toe_r', context.object.data, "bones", text="")

                col.separator()
                col.separator(type='LINE')
                col.separator()

                row = col.row(align=True)
                row.scale_x = 0.2
                row.label(text='Shoulder L & R')
                row.prop_search(context.object.vs, 'retarget_armature_shoulder_l', context.object.data, "bones", text="")
                row.prop_search(context.object.vs, 'retarget_armature_shoulder_r', context.object.data, "bones", text="")

                row = col.row(align=True)
                row.scale_x = 0.2
                row.label(text='Wrist L & R')
                row.prop_search(context.object.vs, 'retarget_armature_wrist_l', context.object.data, "bones", text="")
                row.prop_search(context.object.vs, 'retarget_armature_wrist_r', context.object.data, "bones", text="")

                col.separator()
                col.separator(type='LINE')
                col.separator()

                row = col.row(align=True)
                row.scale_x = 0.2
                row.label(text='Thumb L & R')
                row.prop_search(context.object.vs, 'retarget_armature_thumb_f_l', context.object.data, "bones", text="")
                row.prop_search(context.object.vs, 'retarget_armature_thumb_f_r', context.object.data, "bones", text="")

                row = col.row(align=True)
                row.scale_x = 0.2
                row.label(text='Index L & R')
                row.prop_search(context.object.vs, 'retarget_armature_index_f_l', context.object.data, "bones", text="")
                row.prop_search(context.object.vs, 'retarget_armature_index_f_r', context.object.data, "bones", text="")

                row = col.row(align=True)
                row.scale_x = 0.2
                row.label(text='Middle L & R')
                row.prop_search(context.object.vs, 'retarget_armature_middle_f_l', context.object.data, "bones", text="")
                row.prop_search(context.object.vs, 'retarget_armature_middle_f_r', context.object.data, "bones", text="")

                row = col.row(align=True)
                row.scale_x = 0.2
                row.label(text='Ring L & R')
                row.prop_search(context.object.vs, 'retarget_armature_ring_f_l', context.object.data, "bones", text="")
                row.prop_search(context.object.vs, 'retarget_armature_ring_f_r', context.object.data, "bones", text="")

                row = col.row(align=True)
                row.scale_x = 0.2
                row.label(text='Pinky L & R')
                row.prop_search(context.object.vs, 'retarget_armature_pinky_f_l', context.object.data, "bones", text="")
                row.prop_search(context.object.vs, 'retarget_armature_pinky_f_r', context.object.data, "bones", text="")
                
            col.operator(JSONBONE_OT_LoadJson.bl_idname)
                
class JSONBONE_OT_WriteJson(bpy.types.Operator):
    bl_idname = "jsonbone.write_json"
    bl_label = "Write Json"
    bl_options = {"INTERNAL", "REGISTER"}
    
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    
    syntax_replacement = {
        r"(?<=\b)R(?=[_\. ]|\b)": "*",
        r"(?<=\b)L(?=[_\. ]|\b)": "*",
        r"(?<=\b)Right(?=[_\. ]|\b)": "*",
        r"(?<=\b)Left(?=[_\. ]|\b)": "*",
    }
    
    @classmethod
    def poll(cls, context):
        return is_armature(context.object) and len(context.object.vs.json_bonecollections) > 0
    
    def sortItemsByBoneHierarchy(self, ob, items):
        """Return a list of items sorted by bone parent hierarchy."""
        # Map item -> bone
        item_bone_map = {}
        for item in items:
            bone = ob.data.bones.get(item.boneExportName)
            if bone:
                item_bone_map[item] = bone

        sorted_items = []
        visited = set()

        def dfs(bone):
            if bone in visited:
                return
            visited.add(bone)
            # Add corresponding item first
            for itm, b in item_bone_map.items():
                if b == bone:
                    sorted_items.append(itm)
                    break
            # Then visit children
            for child in bone.children:
                dfs(child)

        # Start from root bones
        for bone in ob.data.bones:
            if bone.parent is None:
                dfs(bone)

        return sorted_items


    def execute(self, context):
        if not self.filepath:
            self.report({'ERROR'}, "No file path set")
            return {'CANCELLED'}

        if not self.filepath.lower().endswith(".json"):
            self.report({'ERROR'}, "File must have a .json extension")
            return {'CANCELLED'}
        
        ob = context.object
        items = ob.vs.json_bonecollections
        bones = []
        skipped_count = 0
        
        sorted_items = self.sortItemsByBoneHierarchy(ob, items)
        with PreserveContextMode(ob, 'EDIT'):
            for item in reversed(sorted_items):
                if not item.boneName.strip():
                    skipped_count += 1
                    continue

                if item.boneExportName not in ob.data.bones:
                    skipped_count += 1
                    continue

                bone = ob.data.bones.get(item.boneExportName)
                
                ParsedboneName = next((item.boneExportName.replace(v, f"!{k}", 1) for k, v in shortcut_keywords.items() if v in item.boneExportName), item.boneExportName)
                ParsedboneName = ParsedboneName.replace("_", " ")
                for pattern, replacement in self.syntax_replacement.items():
                    ParsedboneName = re.sub(pattern, replacement, ParsedboneName, flags=re.IGNORECASE)
                
                editbone = ob.data.edit_bones.get(item.boneExportName)
                ebone_roll = editbone.roll
                
                boneDict = {
                    "BoneName" : item.boneName,
                    "ExportName" : ParsedboneName
                }
                
                if not item.parentBone.strip():
                    parent_bone = bone.parent
                    if parent_bone:
                        parent_item = next((i for i in items if i.boneExportName == parent_bone.name), None)
                        if parent_item and parent_item.boneName.strip():
                            boneDict["ParentBone"] = parent_item.boneName
                        else:
                            boneDict["ParentBone"] = parent_bone.name
                else:
                    boneDict["ParentBone"] = item.parentBone
                
                if item.writeRotation == 'ROTATION':
                    head = bone.head_local
                    tail = bone.tail_local
                    tail_offset = tail - head
                    boneDict['Rotation'] = [tail_offset.x, tail_offset.y, tail_offset.z]
                    boneDict['Roll'] = ebone_roll
                elif item.writeRotation == 'ROLL':
                    boneDict['Roll'] = ebone_roll
                    
                if item.writeExportRotationOffset and not bone.vs.ignore_rotation_offset:
                    boneDict['ExportRotationOffset'] = [
                        bone.vs.export_rotation_offset_x,
                        bone.vs.export_rotation_offset_y,
                        bone.vs.export_rotation_offset_z
                    ]
                    
                if item.writeTwistBone:
                    if item.twistBoneTarget.strip(): 
                        twist_name = item.twistBoneTarget.strip()
                    else:
                        parent_bone = bone.parent
                        if parent_bone:
                            parent_item = next((i for i in items if i.boneExportName == parent_bone.name), None)
                            twist_name = parent_item.boneName if parent_item else parent_bone.name
                        else:
                            twist_name = None
                            print(f'{item.boneExportName} cannot have twist due to not having a proper target bone')
                        
                    if twist_name:
                        boneDict['TwistBones'] = twist_name
                    
                bones.append(boneDict)
        
        if bones:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(bones, f, indent=4)

            self.report({'INFO'}, f"Exported JSON to: {self.filepath} | Skipped {skipped_count} bone(s)")
        else:
            self.report({'WARNING'}, f"No bones exported. Skipped {skipped_count} bone(s)")
        
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
class JSONBONE_OT_LoadJson(Operator):
    bl_idname = "jsonbone.load_json"
    bl_label = "Load JSON"
    bl_options = {"REGISTER", "UNDO"}

    filepath: StringProperty(subtype="FILE_PATH")

    ignore_export_name: BoolProperty(
        name="Ignore Export Name",
        description="Ignore the export name field in the JSON",
        default=False
    )

    def invoke(self, context, event):
        # Opens the file browser
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):

        json_path = self.filepath

        if not json_path.lower().endswith(".json"):
            self.report({"ERROR"}, "Please select a JSON file")
            return {"CANCELLED"}

        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        boneElems = {entry["BoneName"]: entry for entry in data}

        arm = getArmature(context.object)
        if arm is None:
            self.report({"ERROR"}, "No valid armature selected")
            return {"CANCELLED"}
        
        def remapped_humanoid_armature_bones(arm: bpy.types.Object):
            vs_arm = getattr(arm, "vs", None)
            if not vs_arm:
                return False

            bones = arm.data.bones
            rename_map = {}

            def is_valid_bone(name: str) -> bool:
                return bool(name) and isinstance(name, str) and name in arm.data.bones.keys()

            # --- Conflict check ---
            bone_props = [attr for attr in dir(vs_arm) if attr.startswith("retarget_armature_")]
            bone_values = [getattr(vs_arm, prop) for prop in bone_props]
            if all(not v for v in bone_values):
                return True
            selected_bones = [v for v in bone_values if is_valid_bone(v)]
            seen, duplicates = set(), set()
            for b in selected_bones:
                if b in seen:
                    duplicates.add(b)
                else:
                    seen.add(b)
            if duplicates:
                print(f"[Humanoid Rename] Conflicting assignments: {duplicates}")
                return False

            # --- Helpers ---
            def collect_chain(start_name, end_name):
                if not (is_valid_bone(start_name) and is_valid_bone(end_name)):
                    return []

                start_bone = bones[start_name]
                end_bone = bones[end_name]

                def dfs(bone, target, path):
                    path.append(bone)
                    if bone == target:
                        return True
                    for child in bone.children:
                        if dfs(child, target, path):
                            return True
                    path.pop()
                    return False

                chain = []
                if dfs(start_bone, end_bone, chain):
                    return chain
                return []

            def realign_chain_tails(chain):
                if len(chain) < 2:
                    return
                # Must be in EDIT mode
                prev_mode = arm.mode
                if bpy.context.object != arm:
                    bpy.context.view_layer.objects.active = arm
                bpy.ops.object.mode_set(mode='EDIT')

                edit_bones = arm.data.edit_bones
                for i in range(len(chain) - 1):
                    a = edit_bones.get(chain[i].name)
                    b = edit_bones.get(chain[i + 1].name)
                    if a and b:
                        a.tail = b.head

                bpy.ops.object.mode_set(mode=prev_mode)

            def build_torso_chain(pelvis_name, chest_name):
                chain = collect_chain(pelvis_name, chest_name)
                if len(chain) < 2:
                    return
                names = ["Hips"]
                middle_count = len(chain) - 2
                if middle_count == 1:
                    names.append("Spine")
                elif middle_count == 2:
                    names.extend(["Waist", "Spine"])
                elif middle_count == 3:
                    names.extend(["Waist", "Spine", "Stomach"])
                elif middle_count > 3:
                    names.extend(["Waist", "Spine", "Stomach"])
                    names.extend([f"Spine_{i+1}" for i in range(middle_count - 3)])
                names.append("Chest")

                for bone, new_name in zip(chain, names):
                    rename_map[bone.name] = new_name

                realign_chain_tails(chain)

            def build_neck_chain(chest_name, head_name):
                chain = collect_chain(chest_name, head_name)
                if len(chain) < 2:
                    return
                for i, bone in enumerate(chain[1:-1], 1):
                    rename_map[bone.name] = "Neck" if i == 1 else f"Neck_{i-1}"
                rename_map[head_name] = "Head"

                realign_chain_tails(chain)

            def build_chain_mapping(start_name, end_name, base_names, side=None):
                chain = collect_chain(start_name, end_name)
                if not chain:
                    return
                target_count = len(base_names)
                for i, bone in enumerate(chain):
                    idx = min(i, target_count - 1)
                    name = base_names[idx]
                    if side == "L":
                        new_name = f"Left {name}"
                    elif side == "R":
                        new_name = f"Right {name}"
                    else:
                        new_name = name
                    if len(chain) > target_count and i >= target_count:
                        new_name += f"_{i - target_count + 1}"
                    rename_map[bone.name] = new_name

                realign_chain_tails(chain)

            def build_finger_mapping(start_name, base, side, start_index=1):
                if not is_valid_bone(start_name):
                    return
                bone = bones[start_name]
                chain = []
                while bone:
                    chain.append(bone)
                    bone = bone.children[0] if bone.children else None
                for i, bone in enumerate(chain):
                    rename_map[bone.name] = f"{base}{i+start_index}_{side}"

                realign_chain_tails(chain)


            # ===== Spine (Pelvis → Chest) =====
            build_torso_chain(vs_arm.retarget_armature_pelvis, vs_arm.retarget_armature_chest)

            # ===== Neck (Chest → Head) =====
            if is_valid_bone(vs_arm.retarget_armature_chest) and is_valid_bone(vs_arm.retarget_armature_head):
                build_neck_chain(vs_arm.retarget_armature_chest, vs_arm.retarget_armature_head)

            # ===== Legs =====
            build_chain_mapping(vs_arm.retarget_armature_thigh_l, vs_arm.retarget_armature_ankle_l,
                                ["leg", "knee", "ankle"], side="L")
            if is_valid_bone(vs_arm.retarget_armature_toe_l):
                rename_map[vs_arm.retarget_armature_toe_l] = "Left toe"

            build_chain_mapping(vs_arm.retarget_armature_thigh_r, vs_arm.retarget_armature_ankle_r,
                                ["leg", "knee", "ankle"], side="R")
            if is_valid_bone(vs_arm.retarget_armature_toe_r):
                rename_map[vs_arm.retarget_armature_toe_r] = "Right toe"

            # ===== Arms =====
            build_chain_mapping(vs_arm.retarget_armature_shoulder_l, vs_arm.retarget_armature_wrist_l,
                                ["shoulder", "arm", "elbow", "wrist"], side="L")
            build_chain_mapping(vs_arm.retarget_armature_shoulder_r, vs_arm.retarget_armature_wrist_r,
                                ["shoulder", "arm", "elbow", "wrist"], side="R")

            # ===== Fingers =====
            build_finger_mapping(vs_arm.retarget_armature_index_f_l, "IndexFinger", "L", start_index=1)
            build_finger_mapping(vs_arm.retarget_armature_middle_f_l, "MiddleFinger", "L", start_index=1)
            build_finger_mapping(vs_arm.retarget_armature_ring_f_l, "RingFinger", "L", start_index=1)
            build_finger_mapping(vs_arm.retarget_armature_pinky_f_l, "LittleFinger", "L", start_index=1)
            build_finger_mapping(vs_arm.retarget_armature_thumb_f_l, "Thumb", "L", start_index=0)

            build_finger_mapping(vs_arm.retarget_armature_index_f_r, "IndexFinger", "R", start_index=1)
            build_finger_mapping(vs_arm.retarget_armature_middle_f_r, "MiddleFinger", "R", start_index=1)
            build_finger_mapping(vs_arm.retarget_armature_ring_f_r, "RingFinger", "R", start_index=1)
            build_finger_mapping(vs_arm.retarget_armature_pinky_f_r, "LittleFinger", "R", start_index=1)
            build_finger_mapping(vs_arm.retarget_armature_thumb_f_r, "Thumb", "R", start_index=0)

            # ===== Apply renames =====
            old_to_new = {}
            for old_name, new_name in rename_map.items():
                if old_name in bones:
                    bones[old_name].name = new_name
                    old_to_new[old_name] = new_name

            # Update properties with new names
            for attr in dir(vs_arm):
                if not attr.startswith("retarget_armature_"):
                    continue
                old_val = getattr(vs_arm, attr)
                if old_val in old_to_new:
                    setattr(vs_arm, attr, old_to_new[old_val])

            return old_to_new
        
        def writeMissingBone(bone_name: str, child_hint: str | None = None):
            """Create a missing bone and its parent if needed.
            child_hint = existing child bone name (used to position the new bone)."""

            # If already exists, return it
            existing = arm.data.edit_bones.get(bone_name)
            if existing:
                return existing

            bone_data = boneElems.get(bone_name)
            if not bone_data:
                print(f"[WARN] No JSON entry for '{bone_name}', skipping.")
                return None

            # Create the new bone
            new_bone = arm.data.edit_bones.new(bone_name)

            # Position based on the child if available
            if child_hint:
                child_bone = arm.data.edit_bones.get(child_hint)
                if child_bone:
                    new_bone.head = child_bone.head.copy()
                    new_bone.tail = child_bone.tail.copy()
                    new_bone.length = child_bone.length * 0.5
                else: 
                    new_bone.head = Vector((0, 0, 0))  # what is all of these?
                    new_bone.tail = Vector((0, 0.1, 0))
            else:
                new_bone.head = Vector((0, 0, 0))
                new_bone.tail = Vector((0, 0.1, 0))

            parent_name = bone_data.get("ParentBone")
            if parent_name and parent_name != bone_name:
                parent_bone = arm.data.edit_bones.get(parent_name)
                if not parent_bone:
                    parent_bone = writeMissingBone(parent_name, child_hint=bone_name)

                if parent_bone:
                    new_bone.parent = parent_bone

            if child_hint:
                child_bone = arm.data.edit_bones.get(child_hint)
                if child_bone and child_bone.parent != new_bone:
                    child_bone.parent = new_bone
                    
                for col in child_bone.collections:
                    col.assign(new_bone)

            print(f"[CREATE] {bone_name} (Parent: {parent_name})")
            return new_bone

        if arm.vs.retarget_armature_ishumanoid:
            bone_remapped = remapped_humanoid_armature_bones(arm)
            if not bone_remapped:
                self.report({'WARNING'}, 'Misconfiguration of Bone Remaps!')
                return {'CANCELLED'}
        
        with PreserveContextMode(arm, 'EDIT'):
            arm.show_in_front = True
            arm.data.display_type == 'WIRE'
            
            for bone_name, bone_data in boneElems.items():
                bone = arm.data.edit_bones.get(bone_name)

                if bone is None:
                    print(f"[SKIP] {bone_name} not found in armature, skipping creation.")
                    continue

                parent_name = bone_data.get("ParentBone")
                if parent_name and arm.data.edit_bones.get(parent_name) is None:
                    writeMissingBone(parent_name, child_hint=bone_name)
                
                rot = bone_data.get("Rotation")
                roll = bone_data.get("Roll")
                if rot and roll:
                    rotatedbones = assignBoneAngles(arm, [(bone_name, rot[0], rot[1], rot[2], roll)])
                elif not rot and roll:
                    rotatedbones = assignBoneAngles(arm, [(bone_name, None, None, None, roll)])
                else:
                    pass
                
                bone = arm.data.edit_bones.get(bone_name)
                twisttarget = bone_data.get("TwistBones")
                if twisttarget:
                    twistbone = arm.data.edit_bones.get(bone_name + " twist")
                    
                    if not twistbone:
                        twistbone = arm.data.edit_bones.new(bone_name + " twist")
                        twistbone.head = bone.head
                        twistbone.tail = bone.tail
                        twistbone.roll = bone.roll
                        twistbone.length = bone.length * 0.5
                        twistbone.parent = bone
                    else:
                        twistbone.head = bone.head
                        twistbone.tail = bone.tail
                        twistbone.length = bone.length * 0.5
                        twistbone.roll = bone.roll
                        twistbone.parent = bone
                
            bpy.ops.object.mode_set(mode='OBJECT')
            
            for bone_name, bone_data in boneElems.items():
                pb = arm.pose.bones.get(bone_name)
                if pb:
                    if bone_data.get("ExportRotationOffset"):
                        pb.bone.vs.export_rotation_offset_x = bone_data.get("ExportRotationOffset")[0]
                        pb.bone.vs.export_rotation_offset_y = bone_data.get("ExportRotationOffset")[1]
                        pb.bone.vs.export_rotation_offset_z = bone_data.get("ExportRotationOffset")[2]
                    else:
                        pb.bone.vs.ignore_rotation_offset = True
                    
                pbtwist = arm.pose.bones.get(bone_name + " twist")
                if pbtwist:
                    twisttarget = bone_data.get("TwistBones")
                    
                    if bone_data.get("ExportRotationOffset"):
                        pbtwist.bone.vs.export_rotation_offset_x = bone_data.get("ExportRotationOffset")[0]
                        pbtwist.bone.vs.export_rotation_offset_y = bone_data.get("ExportRotationOffset")[1]
                        pbtwist.bone.vs.export_rotation_offset_z = bone_data.get("ExportRotationOffset")[2]
                    else:
                        pb.bone.vs.ignore_rotation_offset = True
                    
                    twistconstraint : bpy.types.CopyRotationConstraint = pbtwist.constraints.new('COPY_ROTATION')
                    twistconstraint.target = arm
                    twistconstraint.subtarget = twisttarget
                    twistconstraint.use_x = False
                    twistconstraint.use_y = True
                    twistconstraint.use_z = False
                    twistconstraint.owner_space = 'LOCAL'
                    twistconstraint.target_space = 'LOCAL'
                    
                    if twisttarget == pbtwist.parent.name:
                        twistconstraint.invert_y = True
                        twistconstraint.influence = 0.8
                    else:
                        twistconstraint.influence = 0.65
                        
                    for col in pb.bone.collections:
                        col.assign(pbtwist.bone)
                     
        self.report({"INFO"}, "Armature Converted successfully.")
        return {"FINISHED"}

class SMD_PT_Tools_Bone(ToolsSubPanel):
    bl_label = "Bone Tools"
    
    def draw_header(self, context):
        self.layout.label(icon='BONE_DATA')
    
    @classmethod
    def poll(cls, context):
        return (is_armature(context.object) and context.object.mode in ['EDIT', 'POSE']) or (is_mesh(context.object) and context.object.mode == 'WEIGHT_PAINT')
    
    def draw(self, context):
        l = self.layout
        bx = l.box()
        
        armature = getArmature(context.object)
        
        col = bx.column(align=True)
        if context.object.mode == 'EDIT':
            col.prop(armature.data, 'use_mirror_x', toggle=True, text='X-Axis Mirror')
        else:
            col.prop(armature.pose, 'use_mirror_x', toggle=True, text='X-Axis Mirror')
        
        col.label(text='Bone Merging')
        split = col.split(align=True)
        split.scale_y = 1.3
        split.operator(TOOLS_OT_MergeBones.bl_idname,icon='AUTOMERGE_ON',text='TO ACTIVE').mode = 'TO_ACTIVE'
        split.operator(TOOLS_OT_MergeBones.bl_idname,icon='AUTOMERGE_ON',text='TO PARENT').mode = 'TO_PARENT'
        
        subbx = col.box()
        subbx.label(text='Options',icon='OPTIONS')
        col = subbx.column(align=True)
        col.prop(context.scene.vs, 'merge_keep_bone')
        col.prop(context.scene.vs, 'visible_mesh_only')
        col.prop(context.scene.vs, 'snap_parent_tip')
        col.prop(context.scene.vs, 'recenter_bone')
        col.prop(context.scene.vs, 'keep_original_weight')
        
        col = bx.column(align=True)
        col.label(text='Bone Alignment')
        col.operator(TOOLS_OT_ReAlignBones.bl_idname)
        row = col.row(align=True)
        row.scale_y = 1.3
        row.operator(TOOLS_OT_CopyTargetRotation.bl_idname, text='Copy Rotation (ACTIVE)').copy_source = 'ACTIVE'
        row.operator(TOOLS_OT_CopyTargetRotation.bl_idname, text='Copy Rotation (PARENT)').copy_source = 'PARENT'
        subbx = col.box()
        subbx.label(text='Options (Exlude Copy)',icon='OPTIONS')
        row = subbx.row(align=True)
        row.prop(context.scene.vs, 'alignment_exclude_axes', expand=True)
           
class TOOLS_OT_ApplyCurrentPoseAsRestPose(bpy.types.Operator):
    bl_idname = "tools._apply_pose_as_restpose"
    bl_label = "Apply Pose As Restpose"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return is_armature(context.object) and context.mode in {'POSE', 'OBJECT'}
    
    def execute(self, context):
        armature = context.object
        bpy.ops.object.mode_set(mode='OBJECT')
        success = applyCurrPoseAsRest(armature)
        if success:
            self.report({'INFO'}, 'Applied as Rest Pose')
        return {'FINISHED'} if success else {'CANCELLED'}
    
class TOOLS_OT_CleanUnWeightedBones(bpy.types.Operator):
    bl_idname = 'tools.clean_unweighted_bones'
    bl_label = 'Clean Unweighted Bones'
    bl_options = {'REGISTER', 'UNDO'}
    
    respect_animation : BoolProperty(
    name='Respect Animation Bones',
    description='Preserve bones that have animation keyframes or are part of a hierarchy that does',
    default=True
)

    aggressive_cleaning : BoolProperty(
    name='Aggressive Removal',
    description='Remove all bones without weight painting, even if they have animated or weighted child bones. '
                'WARNING: This will not respect hierarchy-dependent armature structures and may break rig constraints.',
    default=False
    )

    @classmethod
    def poll(cls, context):
        return is_armature(context.object) and context.mode in {'POSE', 'OBJECT'}
        
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        l = self.layout
        l.prop(self, 'aggressive_cleaning')
        
        if not self.aggressive_cleaning:
            l.prop(self, 'respect_animation')
        else:
            bx = l.box()
            bx.label(text='Cleaning will break constraints and IK!', icon='ERROR')

    def execute(self, context):
        armature = getArmature(context.object)
        bones = armature.pose.bones
        meshes = getArmatureMeshes(armature)
        
        if self.aggressive_cleaning:
            self.respect_animation = False

        if not meshes or not bones:
            self.report({'WARNING'}, "No meshes or bones associated with the armature.")
            return {'CANCELLED'}

        removed_vgroups = clean_vertex_groups(armature, armature.data.bones)

        remaining_vgroups = {
            mesh: set(vg.name for vg in mesh.vertex_groups)
            for mesh in meshes
        }

        total_bones_removed = 0

        while True:
            bones_to_remove = set()
            for b in bones:
                if b.children and not self.aggressive_cleaning:
                    continue

                has_weight = any(b.name in remaining_vgroups[mesh] for mesh in meshes)
                if has_weight:
                    continue

                if self.respect_animation and not self.aggressive_cleaning:
                    if self.hierarchy_has_animation(armature, b):
                        continue

                bones_to_remove.add(b.name)

            if bones_to_remove:
                with PreserveContextMode(armature, 'EDIT'):
                    removeBone(armature, bones_to_remove)
                    
                    total_bones_removed += len(bones_to_remove)
                    bones = armature.pose.bones
                    
                    remaining_vgroups = {
                        mesh: set(vg.name for vg in mesh.vertex_groups)
                        for mesh in meshes
                    }
            else:
                break

        total_vgroups_removed = sum(len(vgs) for vgs in removed_vgroups.values())

        self.report({'INFO'}, f'{total_bones_removed} bones removed with {total_vgroups_removed} empty vertex groups removed.')
        return {'FINISHED'}

    def bone_has_animation(self, armature, bone_name):
        bone = armature.pose.bones.get(bone_name)
        if not bone:
            return False

        # Check keyframes
        for action in bpy.data.actions:
            for fcurve in action.fcurves:
                if fcurve.data_path.startswith(f'pose.bones["{bone_name}"]'):
                    if any(kw in fcurve.data_path for kw in ('location', 'rotation', 'scale')):
                        keyframes = set(kf.co[1] for kf in fcurve.keyframe_points)
                        if len(keyframes) > 1:
                            return True

        # Check constraints
        for constr in bone.constraints:
            if getattr(constr, "target", None) or getattr(constr, "driver_add", None):
                return True

        return False

    def hierarchy_has_animation(self, armature, bone):
        if self.bone_has_animation(armature, bone.name):
            return True
        for child in bone.children:
            if self.hierarchy_has_animation(armature, child):
                return True
        return False
    
class TOOLS_OT_MergeBones(bpy.types.Operator):
    bl_idname = 'tools.merge_bones'
    bl_label = 'Merge Bones'
    bl_options = {'REGISTER', 'UNDO'}
    
    mode: bpy.props.EnumProperty(items=[('TO_PARENT', 'To Parent', ''), ('TO_ACTIVE', 'To Active', '')])
    
    @classmethod
    def poll(cls, context):
        ob = context.object
        arm = None
        if not is_armature(ob):
            if is_mesh(ob): arm = getArmature(ob)
        else:
            arm = ob
        
        if arm is None: return False

        if arm.mode == 'EDIT':
            bones = {b for b in arm.data.edit_bones if b.select and not b.hide}
        else:
            bones = {b for b in arm.data.bones if b.select and not b.hide}

        return bool(bones)
    
    def execute(self,context):
        arm = context.object
        
        if not is_armature(arm):
            arm = getArmature(arm)
            
        if arm is None: return {'CANCELLED'}
        
        vs_sce = context.scene.vs

        if self.mode == 'TO_PARENT':
            sel_bones = getBones(arm, sorted=True,reverse_sort=True, bonetype='BONE' if arm.mode != 'EDIT' else 'EDITBONE' ,exclude_active=False)
            with PreserveContextMode(arm, 'EDIT'):
                removeBone(arm, mergeBones(arm, None, sel_bones, vs_sce.merge_keep_bone, vs_sce.visible_mesh_only, vs_sce.keep_original_weight), match_parent_to_head=vs_sce.snap_parent_tip)
        
        elif self.mode == 'TO_ACTIVE':
            sel_bones = getBones(arm, sorted=True,reverse_sort=True, bonetype='BONE' if arm.mode != 'EDIT' else 'EDITBONE' , exclude_active=True)
            if not arm.data.bones.active.select:
                self.report({'WARNING'}, 'No active selected bone')
                return {'CANCELLED'}
            
            with PreserveContextMode(arm, 'EDIT'):
                centralize_b = vs_sce.recenter_bone

                # run merge with centralize option if needed
                if centralize_b:
                    bones_to_remove, merged_pairs = mergeBones(
                        arm,
                        arm.data.bones.active,
                        sel_bones,
                        vs_sce.merge_keep_bone,
                        vs_sce.visible_mesh_only,
                        vs_sce.keep_original_weight,
                        centralize_bone=True
                    )

                    # centralize before removing
                    CentralizeBonePairs(arm, merged_pairs)

                    removeBone(arm, bones_to_remove, arm.data.bones.active.name)

                else:
                    bones_to_remove = mergeBones(
                        arm,
                        arm.data.bones.active,
                        sel_bones,
                        vs_sce.merge_keep_bone,
                        vs_sce.visible_mesh_only,
                        vs_sce.keep_original_weight,
                        centralize_bone=False
                    )

                    removeBone(arm, bones_to_remove, arm.data.bones.active.name)
        
        self.report({'INFO'}, f'{len(sel_bones)} Weights merged')
        return {'FINISHED'}

class TOOLS_OT_MergeArmatures(bpy.types.Operator):
    bl_idname = "tools.merge_armatures"
    bl_label = "Merge Armatures"
    bl_options = {'REGISTER', 'UNDO'}
    
    match_posture : BoolProperty(name='Match Visual Pose', default=True)
    
    @classmethod
    def poll(cls, context):
        return is_armature(context.object) and {ob for ob in context.view_layer.objects if is_armature(ob) and ob != context.object and ob.select_get()}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def execute(self, context):
        armatures = [ob for ob in bpy.data.objects if ob.select_get() and ob != context.object]
        
        if not armatures: return {'CANCELLED'}
        
        for arm in armatures:
            success = mergeArmatures(context.object, arm, match_posture=self.match_posture)
            
        return {'FINISHED'}

class TOOLS_OT_CreateProportionActions(bpy.types.Operator):
    bl_idname = 'tools.create_proportion_actions'
    bl_label = 'Create Delta Proportion Pose'
    bl_options = {'REGISTER', 'UNDO'}
    
    ProportionName : StringProperty(name='Action Proportion Name', default='proportion')
    ReferenceName : StringProperty(name='Action Reference Name', default='reference')
    
    @classmethod
    def poll(cls, context):
        ob = context.object
        return context.mode == 'OBJECT' and is_armature(ob) and {ob for ob in context.view_layer.objects if ob != context.object and ob.select_get()}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def execute(self, context):
        currArm = context.object
        otherArms = {ob for ob in context.view_layer.objects if ob.select_get() and ob.type == 'ARMATURE'}
        
        otherArms.discard(currArm)
        
        if not self.ReferenceName.strip() or not self.ProportionName.strip() : return {'CANCELLED'}
        
        last_pose_state = currArm.data.pose_position
        currArm.data.pose_position = 'REST' # reset to rest pose for first
        
        context.scene.frame_set(0)
        context.view_layer.update()
        
        for arm in otherArms:  
            if arm.animation_data is None:
                arm.animation_data_create()
                
            arm.animation_data.action = None

            for bone in arm.pose.bones:
                bone.matrix_basis.identity()
            
            ActionReference = None
            ActionProportion = None
            
            if len(otherArms) > 1:
                ActionReferenceName = f"{self.ReferenceName}_{arm.name}"
                ActionProportionName = f"{self.ProportionName}_{arm.name}"
            else:
                ActionReferenceName = self.ReferenceName
                ActionProportionName = self.ProportionName
            
            ActionReference = bpy.data.actions.get(ActionReferenceName)
            ActionProportion = bpy.data.actions.get(ActionProportionName)
            
            if ActionReference is None:
                ActionReference = bpy.data.actions.new(ActionReferenceName)
            else:
                ActionReference.fcurves.clear()
            
            # do the reference pose that has rotation match only
            arm.animation_data.action = ActionReference
            ActionReference.use_fake_user = True
                
            success = copyArmatureVisualPose(currArm,arm,copy_type='ANGLES')
            
            if success:
                for pbone in arm.pose.bones:
                    pbone.keyframe_insert(data_path="location", group=pbone.name)
                    pbone.keyframe_insert(data_path="rotation_quaternion", group=pbone.name)
                    pbone.keyframe_insert(data_path="rotation_euler", group=pbone.name)
                
            arm.animation_data.action = None
            context.view_layer.update()
                
            # now do the proportion that has the exact match of location and rotation
            if ActionProportion is None:
                ActionProportion = bpy.data.actions.new(ActionProportionName)
            else:
                ActionProportion.fcurves.clear()
            
            arm.animation_data.action = ActionProportion
            ActionProportion.use_fake_user = True
            success1 = copyArmatureVisualPose(currArm,arm,copy_type='ANGLES')
            success2 = copyArmatureVisualPose(currArm,arm,copy_type='ORIGIN')
            
            if success1 and success2:
                for pbone in arm.pose.bones:
                    pbone.keyframe_insert(data_path="location", group=pbone.name)
                    pbone.keyframe_insert(data_path="rotation_quaternion", group=pbone.name)
                    pbone.keyframe_insert(data_path="rotation_euler", group=pbone.name)
            
            # set back to reference as that is the cleaner pose
            arm.animation_data.action = ActionReference
            context.view_layer.update()
        
        currArm.data.pose_position = last_pose_state
        return {'FINISHED'}

class TOOLS_OT_ReAlignBones(bpy.types.Operator):
    bl_idname = 'tools.realign_bone'
    bl_label = 'ReAlign Bones'
    bl_options = {'REGISTER', 'UNDO'}
    
    alignment_mode: bpy.props.EnumProperty(
        name="Alignment Mode",
        description="Choose how to align the bone tail",
        items=[
            ('AVERAGE_ALL', "Average All", "Align to average position of all children"),
            ('ONLY_SINGLE_CHILD', "Only Single Child", "Align only if there is a single child bone")
        ],
        default='ONLY_SINGLE_CHILD'
    )

    @classmethod
    def poll(cls, context):
        return is_armature(context.object)
        
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "alignment_mode")

    def realign_bone_tail(self, bone, exclude_x=False, exclude_y=False, exclude_z=False, exclude_roll=False):
        child_positions = [child.head for child in bone.children]
        original_bone_roll = bone.roll

        new_tail = None

        if child_positions:
            if self.alignment_mode == 'AVERAGE_ALL':
                avg_position = sum(child_positions, Vector((0, 0, 0))) / len(child_positions)
                new_tail = Vector((
                    bone.tail.x if exclude_x else avg_position.x,
                    bone.tail.y if exclude_y else avg_position.y,
                    bone.tail.z if exclude_z else avg_position.z
                ))

            elif self.alignment_mode == 'ONLY_SINGLE_CHILD' and len(child_positions) == 1:
                child_position = child_positions[0]
                new_tail = Vector((
                    bone.tail.x if exclude_x else child_position.x,
                    bone.tail.y if exclude_y else child_position.y,
                    bone.tail.z if exclude_z else child_position.z
                ))

            if all([exclude_x, exclude_y, exclude_z]):
                if self.alignment_mode == 'AVERAGE_ALL':
                    avg_vec = sum((pos - bone.head for pos in child_positions), Vector((0,0,0))) / len(child_positions)
                    bone.length = avg_vec.length
                elif self.alignment_mode == 'ONLY_SINGLE_CHILD' and len(child_positions) == 1:
                    vec_to_child = child_positions[0] - bone.head
                    bone.length = vec_to_child.length
            else:
                bone.tail = new_tail

        if not exclude_roll:
            bone.align_roll(bone.tail - bone.head)
        else:
            bone.roll = original_bone_roll

    def execute(self, context):
        armature = getArmature()

        if not armature:
            self.report({'WARNING'}, "No armature selected")
            return {'CANCELLED'}

        mode = context.mode
        vs_sce = context.scene.vs
        original_mode = "EDIT" if mode == "EDIT_ARMATURE" else mode
        bpy.ops.object.mode_set(mode='EDIT')

        bones = getBones(arm=armature,sorted=True,reverse_sort=True,bonetype='EDITBONE')
        for bone in bones:
            self.realign_bone_tail(bone,
                                   exclude_x= ('EXCLUDE_X' in vs_sce.alignment_exclude_axes),
                                   exclude_y= ('EXCLUDE_Y' in vs_sce.alignment_exclude_axes),
                                   exclude_z= ('EXCLUDE_Z' in vs_sce.alignment_exclude_axes),
                                   exclude_roll= ('EXCLUDE_ROLL' in vs_sce.alignment_exclude_axes)
                                   )

        bpy.ops.object.mode_set(mode=original_mode)
        self.report({'INFO'}, "Bones realigned successfully")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
class TOOLS_OT_CopyTargetRotation(bpy.types.Operator):
    bl_idname = "tools.copy_target_bone_rotation"
    bl_label = "Copy Parent/Active Rotation"
    bl_options = {'REGISTER', 'UNDO'}

    copy_source: bpy.props.EnumProperty(
        name="Copy From",
        description="Choose which bone to copy orientation from",
        items=[
            ('PARENT', "Parent", "Copy rotation from parent bone"),
            ('ACTIVE', "Active", "Copy rotation from active bone"),
        ],
        default='PARENT'
    )

    @classmethod
    def poll(cls, context):
        return is_armature(context.object)

    def execute(self, context):
        og_mode = context.object.mode
        armature = context.object
        vs_sce = context.scene.vs
        
        bpy.ops.object.mode_set(mode='EDIT')

        error = 0
        bones: list[bpy.types.Bone] = getBones(
            arm=armature, 
            sorted=True, 
            reverse_sort=True, 
            bonetype='EDITBONE'
        )

        if not bones:
            bpy.ops.object.mode_set(mode=og_mode)
            self.report({'WARNING'}, 'No selected bone to process')
            return {'CANCELLED'}

        active_bone = armature.data.edit_bones.active

        for bone in bones:
            edit_bone = armature.data.edit_bones.get(bone.name)
            try:
                if not edit_bone:
                    continue

                # Determine reference bone
                if self.copy_source == 'PARENT':
                    reference_bone = edit_bone.parent
                else:  # ACTIVE
                    reference_bone = active_bone if active_bone else None

                if not reference_bone:
                    continue

                edit_bone.use_connect = False

                ref_head_world = armature.matrix_world @ reference_bone.head
                ref_tail_world = armature.matrix_world @ reference_bone.tail

                ref_direction = (ref_tail_world - ref_head_world).normalized()

                original_head_world = armature.matrix_world @ edit_bone.head
                new_head_local = armature.matrix_world.inverted() @ original_head_world
                edit_bone.head = new_head_local

                original_length = (edit_bone.tail - edit_bone.head).length

                if 'EXCLUDE_X' in vs_sce.alignment_exclude_axes: ref_direction.x = ref_direction.x
                if 'EXCLUDE_Y' in vs_sce.alignment_exclude_axes: ref_direction.y = ref_direction.y
                if 'EXCLUDE_Z' in vs_sce.alignment_exclude_axes: ref_direction.z = ref_direction.z

                ref_direction.normalize()
                edit_bone.tail = edit_bone.head + (ref_direction * original_length)

                if 'EXCLUDE_ROLL' not in vs_sce.alignment_exclude_axes:
                    edit_bone.roll = reference_bone.roll
                if 'EXCLUDE_SCALE' not in vs_sce.alignment_exclude_axes:
                    edit_bone.length = reference_bone.length

            except Exception as e:
                print(f'Failed to re-orient bone: {e}')
                error += 1
                continue

        bpy.ops.object.mode_set(mode=og_mode)

        if error == 0:
            self.report({'INFO'}, "Orientation copied successfully")
        else:
            self.report({'WARNING'}, f"Copied with {error} errors")

        return {"FINISHED"}
    
class SMD_PT_Tools_Mesh(ToolsSubPanel):
    bl_label = "Mesh Tools"
    
    def draw_header(self, context):
        self.layout.label(icon='MESH_DATA')
    
    @classmethod
    def poll(cls, context):
        return is_mesh(context.object)
    
    def draw(self, context):
        l = self.layout
        bx = l.box()
        
        col = bx.column()
        row = col.row(align=True)
        row.scale_y = 1.3
        row.operator(TOOLS_OT_CleanShapeKeys.bl_idname, icon='SHAPEKEY_DATA')
        row.operator(TOOLS_OT_RemoveUnusedVertexGroups.bl_idname, icon='GROUP_VERTEX')
        
        col.operator(TOOLS_OT_SelectShapekeyVets.bl_idname, icon='VERTEXSEL')
        col.operator(TOOLS_OT_AddToonEdgeLine.bl_idname, icon='MOD_SOLIDIFY')
        
class TOOLS_OT_CleanShapeKeys(bpy.types.Operator):
    bl_idname = 'tools.clean_shape_keys'
    bl_label = 'Clean Shape Keys'
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        objects = [o for o in context.view_layer.objects if o.select_get()]
        
        if not objects:
            self.report({'WARNING'}, 'No objects are selected')
            return {'CANCELLED'}
        
        cleaned_objects = 0
        removed_shapekeys = 0
        
        for ob in objects:
            if ob.type != 'MESH': continue
            
            deleted_sk = get_unused_shape_keys(ob)
            
            if deleted_sk:
                cleaned_objects += 1
                removed_shapekeys += len(deleted_sk)
                
        if cleaned_objects and removed_shapekeys:
            self.report({'INFO'}, f'{cleaned_objects} objects processed with {removed_shapekeys} shapekeys removed')
        else:
            self.report({'INFO'}, f'No shapekeys were removed')
            
        return {'FINISHED'}
    
class TOOLS_OT_SelectShapekeyVets(bpy.types.Operator):
    bl_idname = 'tools.select_shapekey_vertices'
    bl_label = 'Select Shapekey Vertices'
    bl_options = {'REGISTER', 'UNDO'}

    select_type: bpy.props.EnumProperty(
        name="Selection Type",
        items=[
            ('ACTIVE', "Active Shapekey", "Use only the active shapekey"),
            ('ALL', "All Shapekeys", "Use all shapekeys except the first (basis)"),
        ],
        default='ALL'
    )

    select_inverse: bpy.props.BoolProperty(
        name="Select Inverse",
        default=False,
        description="Select vertices *not* affected by the shapekey(s)"
    )

    threshold: bpy.props.FloatProperty(
        name="Threshold",
        description="Minimum vertex delta to consider as affected by shapekey",
        default=0.01,
        min=0.001,
        max=1.0,
        precision=4
    )

    @classmethod
    def poll(cls, context):
        ob = context.object
        return is_mesh(ob) and ob.data.shape_keys and ob.mode == 'EDIT'

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()

        shapekeys = mesh.shape_keys.key_blocks
        basis = shapekeys[0]

        if self.select_type == 'ACTIVE':
            keyblocks = [obj.active_shape_key] if obj.active_shape_key != basis else []
        else:  # ALL
            keyblocks = [kb for kb in shapekeys[1:]]

        basis_coords = basis.data

        # Collect affected vertices (shapekey deltas)
        affected_indices = {
            i for kb in keyblocks
            for i, (v_basis, v_shape) in enumerate(zip(basis_coords, kb.data))
            if (v_basis.co - v_shape.co).length > self.threshold
        }

        # Apply selection
        inv = self.select_inverse
        for i, v in enumerate(bm.verts):
            v.select_set((i in affected_indices) != inv)  # XOR

        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
        bpy.ops.mesh.select_mode(type='VERT')
        return {'FINISHED'}

class TOOLS_OT_RemoveUnusedVertexGroups(bpy.types.Operator):
    bl_idname = "tools.remove_unused_vertexgroups"
    bl_label = "Clean Unused Vertex Groups"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return any(ob.select_get() for ob in context.view_layer.objects)
    
    def execute(self, context):
        obs = [ob for ob in context.view_layer.objects if ob.select_get()]
        total_removed = 0

        for ob in obs:
            removed_vgroups = clean_vertex_groups(ob)
            total_removed += sum(len(vgs) for vgs in removed_vgroups.values())

        self.report({'INFO'}, f"Removed {total_removed} unused vertex groups.")
        return {'FINISHED'}

class SMD_PT_Tools_VertexGroup(ToolsSubPanel):
    bl_label = "VertexGroup Tools"
    
    def draw_header(self, context):
        self.layout.label(icon='GROUP_VERTEX')
    
    @classmethod
    def poll(cls, context):
        ob = context.object
        return (is_mesh(ob) and ob.mode == 'WEIGHT_PAINT') or (is_armature(ob) and ob.mode == 'POSE')
    
    def draw(self, context):
        l = self.layout
        bx = l.box()
        
        col = bx.column()
        col.operator(TOOLS_OT_WeightMath.bl_idname, icon='LINENUMBERS_ON')
        col.operator(TOOLS_OT_SwapVertexGroups.bl_idname,icon='AREA_SWAP')
        col.operator(TOOLS_OT_SplitActiveWeightLinear.bl_idname,icon='SPLIT_VERTICAL')
        
        if context.object.mode == 'WEIGHT_PAINT':
            col = bx.column(align=True)
            tool_settings = context.tool_settings
            brush = tool_settings.weight_paint.brush
            
            col.operator(TOOLS_OT_curve_ramp_weights.bl_idname)
            row = col.row(align=True)
                
            col.template_curve_mapping(brush, "curve", brush=False)
            row = col.row(align=True)
            row.operator("brush.curve_preset", icon='SMOOTHCURVE', text="").shape = 'SMOOTH'
            row.operator("brush.curve_preset", icon='SPHERECURVE', text="").shape = 'ROUND'
            row.operator("brush.curve_preset", icon='ROOTCURVE', text="").shape = 'ROOT'
            row.operator("brush.curve_preset", icon='SHARPCURVE', text="").shape = 'SHARP'
            row.operator("brush.curve_preset", icon='LINCURVE', text="").shape = 'LINE'
            row.operator("brush.curve_preset", icon='NOCURVE', text="").shape = 'MAX'
            
class TOOLS_OT_init_weight_brush(bpy.types.Operator):
    bl_idname = "tools.init_weight_brush"
    bl_label = "Initialize Weight Brush"

    def execute(self, context):
        tool_settings = context.tool_settings
        prev_obj = context.object
        prev_mode = prev_obj.mode if prev_obj else 'OBJECT'
        temp_obj = None

        # This is the best way I can initialize the brush curve as it is not initialize on blender startup.
        # this is very stupid but too bad.
        if not prev_obj or prev_obj.type != 'MESH':
            mesh = bpy.data.meshes.new("TempMesh")
            temp_obj = bpy.data.objects.new("TempObj", mesh)
            context.collection.objects.link(temp_obj)
            bpy.context.view_layer.objects.active = temp_obj
            bpy.ops.object.mode_set(mode='OBJECT')  # ensure safe switch

        bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
        brush = tool_settings.weight_paint.brush

        if brush is None:
            brush = bpy.data.brushes.new(name="WeightBrush", mode='WEIGHT_PAINT')

        if brush.curve is None:
            brush.curve = bpy.types.CurveMapping()
            brush.curve.initialize()

        if prev_obj and prev_obj != temp_obj:
            bpy.context.view_layer.objects.active = prev_obj
            try:
                bpy.ops.object.mode_set(mode=prev_mode)
            except RuntimeError:
                bpy.ops.object.mode_set(mode='OBJECT')

        if temp_obj:
            temp_data = temp_obj.data
            bpy.data.objects.remove(temp_obj, do_unlink=True)
            if temp_data and temp_data.users == 0:
                bpy.data.meshes.remove(temp_data, do_unlink=True)
            temp_obj = None

        self.report({'INFO'}, "Weight brush ready (curve initialized)")
        return {'FINISHED'}

class TOOLS_OT_WeightMath(bpy.types.Operator):
    bl_idname = "tools.weight_math"
    bl_label = "Weight Math"
    bl_options = {'REGISTER', 'UNDO'}

    operation: bpy.props.EnumProperty(
        name="Operation",
        description="Math operation to apply",
        items=[
            ('ADD', "Add", "Add other bones to active"),
            ('SUBTRACT', "Subtract", "Subtract sum of others from active"),
            ('MULTIPLY', "Multiply", "Multiply active by sum of others"),
            ('DIVIDE', "Divide", "Divide active by sum of others"),
        ],
        default='SUBTRACT'
    )

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return (is_mesh(ob) or is_armature(ob)) and ob.mode in {'POSE', 'WEIGHT_PAINT'} and getArmature(ob).select_get()
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        
        arm = getArmature(context.object)
        meshes = getArmatureMeshes(arm, visible_only=getattr(context.scene.vs, 'visible_mesh_only', False))
        
        if not meshes:
            self.report({'WARNING'}, "No meshes bound to armature")
            return {'CANCELLED'}

        curr_bone = arm.data.bones.active
        if not curr_bone:
            self.report({'WARNING'}, "No active bone")
            return {'CANCELLED'}
        selected_bones = [b for b in arm.data.bones if b.select]
        if len(selected_bones) < 2:
            self.report({'WARNING'}, "Select at least 2 bones")
            return {'CANCELLED'}

        active_name = curr_bone.name
        other_names = [b.name for b in selected_bones if b != curr_bone]
        
        prev_mode = arm.mode
        
        for mesh in meshes:

            vg_active = mesh.vertex_groups.get(active_name)
            if not vg_active:
                continue

            vg_others = [mesh.vertex_groups.get(n) for n in other_names if mesh.vertex_groups.get(n)]
            if not vg_others:
                continue

            for v in mesh.data.vertices:
                try:
                    w_active = vg_active.weight(v.index)
                except RuntimeError:
                    w_active = 0.0

                w_sum = 0.0
                for vg in vg_others:
                    try:
                        w_sum += vg.weight(v.index)
                    except RuntimeError:
                        pass

                if self.operation == 'ADD':
                    new_w = w_active + w_sum
                elif self.operation == 'SUBTRACT':
                    new_w = w_active - w_sum
                elif self.operation == 'MULTIPLY':
                    new_w = w_active * w_sum
                elif self.operation == 'DIVIDE':
                    new_w = w_active / w_sum if w_sum != 0 else w_active
                else:
                    new_w = w_active

                new_w = max(0.0, min(1.0, new_w))
                vg_active.add([v.index], new_w, 'REPLACE')

        return {'FINISHED'}
    
class TOOLS_OT_SwapVertexGroups(bpy.types.Operator):
    bl_idname = 'tools.swap_vertex_group'
    bl_label = 'Swap Vertex Group'
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ob = context.object
        if not ob: return False
        if ob.mode not in {'POSE', 'WEIGHT_PAINT'}: return False
        
        arm = None
        if is_armature(ob):
            arm = ob
        elif is_mesh(ob):
            arm = getArmature(ob)
            
        if arm:
            if arm.data.bones.active and arm.data.bones.active.select and len(getBones(arm,False,'BONE')) == 2:
                return True
        else:
            return False
    
    def execute(self,context):
        arm = getArmature(context.object)
        currBone = arm.data.bones.active
        otherBone = getBones(arm, False, exclude_active= True)[0]
        
        if currBone.id_data != otherBone.id_data:
            self.report({'WARNING'}, "Bones selected are not in the same armature")
            return {'CANCELLED'}
        
        meshes = getArmatureMeshes(arm, visible_only=getattr(context.scene.vs, 'visible_mesh_only', False))
        
        if not meshes:
            self.report({'WARNING'}, "Armature doesn't have any Meshes")
            return {'CANCELLED'}
        
        for mesh in meshes:        
            group1 = mesh.vertex_groups.get(currBone.name)
            group2 = mesh.vertex_groups.get(otherBone.name)
            
            if group1 is None:
                group1 = mesh.vertex_groups.new(name=currBone.name)
            if group2 is None:
                group2 = mesh.vertex_groups.new(name=otherBone.name)
            
            weights1 = {v.index: group1.weight(v.index) for v in mesh.data.vertices if group1.index in [g.group for g in v.groups]}
            weights2 = {v.index: group2.weight(v.index) for v in mesh.data.vertices if group2.index in [g.group for g in v.groups]}

            for vertex_index in weights1.keys():
                group2.add([vertex_index], weights1[vertex_index], 'REPLACE')
            
            for vertex_index in weights2.keys():
                group1.add([vertex_index], weights2[vertex_index], 'REPLACE')

            for vertex_index in weights1.keys():
                group1.remove([vertex_index])
            for vertex_index in weights2.keys():
                group2.remove([vertex_index])

            for vertex_index, weight in weights2.items():
                group1.add([vertex_index], weight, 'REPLACE')
            for vertex_index, weight in weights1.items():
                group2.add([vertex_index], weight, 'REPLACE')
        
        self.report({'INFO'}, f"{currBone.name} and {otherBone.name} vertex froup swapped")
        return {'FINISHED'}
    
class TOOLS_OT_CopyVisPosture(bpy.types.Operator):
    bl_idname = "tools.copy_vis_armature_posutre"
    bl_label = "Copy Visual Pose"
    bl_options = {'REGISTER', 'UNDO'}

    copy_type: bpy.props.EnumProperty(items=[('ORIGIN', 'Location', ''), ('ANGLES', 'Rotation', '')])
        
    @classmethod
    def poll(cls,context):
        currob = context.object
        if not is_armature(currob): return False
        
        obs = {ob for ob in context.view_layer.objects if ob.select_get() and not ob.hide_get() and ob != currob}
        return obs
    
    def execute(self, context):
        currArm = context.object
        obs = {ob for ob in context.view_layer.objects if ob.select_get() and not ob.hide_get() and ob != currArm}

        copiedcount = 0
        for otherArm in obs:
            
            if not all([currArm.data.bones, otherArm.data.bones]):
                continue
            
            success = copyArmatureVisualPose(
                base_armature=currArm,
                target_armature=otherArm,
                copy_type=self.copy_type,
            )
            
            if success: copiedcount += 1
        
        return {'FINISHED'} if copiedcount > 0 else {'CANCELLED'}
    
class TOOLS_OT_AddToonEdgeLine(bpy.types.Operator):
    bl_idname = "tools.add_toon_edgeline"
    bl_label = "Add Black Toon Edgeline"
    bl_options = {"REGISTER", "UNDO"}

    has_sharp_edgesplit: bpy.props.BoolProperty(
        name="Has Sharp EdgeSplit",
        description="Add or ensure a sharp-only EdgeSplit modifier before the Solidify modifier",
        default=False,
    )

    edgeline_thickness: bpy.props.FloatProperty(
        name="Edgeline Thickness",
        description="Thickness of the toon edgeline (in scene units)",
        default=0.05,
        min=0.0,
        precision=4,unit='LENGTH',subtype='DISTANCE'
    )
    
    @classmethod
    def poll(cls, context):
        return {ob for ob in context.view_layer.objects if is_mesh(ob) and ob.select_get() and not ob.hide_get()}

    def execute(self, context):
        obs = {ob for ob in context.view_layer.objects if is_mesh(ob) and ob.select_get() and not ob.hide_get()}

        for ob in obs:
            bpy.context.view_layer.objects.active = ob

            scene = context.scene
            unit_scale = scene.unit_settings.scale_length or 1.0  # meters

            # --- Find or create edgeline material ---
            edgeline_mat = None
            for mat in bpy.data.materials:
                if "edgeline" in mat.name.lower():
                    edgeline_mat = mat
                    break

            if edgeline_mat is None:
                edgeline_mat = bpy.data.materials.new(name="edgeline")
                edgeline_mat.use_nodes = True

                nodes = edgeline_mat.node_tree.nodes
                nodes.clear()

                emission_node = nodes.new(type="ShaderNodeEmission")
                emission_node.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
                emission_node.inputs["Strength"].default_value = 1.0

                output_node = nodes.new(type="ShaderNodeOutputMaterial")
                links = edgeline_mat.node_tree.links
                links.new(emission_node.outputs["Emission"], output_node.inputs["Surface"])

            edgeline_mat.use_backface_culling = True
            if hasattr(edgeline_mat, "use_backface_culling_shadow"):
                edgeline_mat.use_backface_culling_shadow = True

            edgeline_mat.vs.non_exportable_vgroup = 'non_exportable_face'
            edgeline_mat.vs.do_not_export_faces_vgroup = True

            # --- Sync edgeline materials with original slots ---
            original_mat_count = 0
            for slot in ob.material_slots:
                if slot.material and "edgeline" in slot.material.name.lower():
                    continue
                original_mat_count += 1

            expected_mat_count = original_mat_count * 2
            while len(ob.data.materials) < expected_mat_count:
                ob.data.materials.append(edgeline_mat)

            # --- Solidify modifier (always exists) ---
            if "Toon_Edgeline" not in ob.modifiers:
                solid = ob.modifiers.new(name="Toon_Edgeline", type="SOLIDIFY")
            else:
                solid = ob.modifiers["Toon_Edgeline"]

            filter_vgroup = ob.vertex_groups.get('non_exportable_face')
            if filter_vgroup is None:
                filter_vgroup = ob.vertex_groups.new(name='non_exportable_face')

            solid.use_rim = False
            # Negative thickness = inverted normals
            solid.thickness = -(self.edgeline_thickness / 1000.0) / unit_scale
            solid.material_offset = original_mat_count
            solid.use_flip_normals = True
            solid.vertex_group = filter_vgroup.name
            solid.invert_vertex_group = True

            # --- Sharp EdgeSplit modifier ---
            if self.has_sharp_edgesplit:
                if "Toon_EdgeSplit" not in ob.modifiers:
                    edgesplit = ob.modifiers.new(name="Toon_EdgeSplit", type="EDGE_SPLIT")
                else:
                    edgesplit = ob.modifiers["Toon_EdgeSplit"]

                edgesplit.use_edge_angle = False
                edgesplit.use_edge_sharp = True

                # Ensure EdgeSplit comes right before Solidify
                while ob.modifiers[0] != edgesplit:
                    bpy.ops.object.modifier_move_up(modifier=edgesplit.name)

            solid_index_target = 1 if self.has_sharp_edgesplit else 0
            while ob.modifiers[solid_index_target] != solid:
                bpy.ops.object.modifier_move_up(modifier=solid.name)

        return {"FINISHED"}

class SMD_PT_ValveModel(SMD_PT_toolpanel, Panel):
    bl_label = 'Valve Models'
    
    def draw_header(self, context):
        self.layout.label(icon='TOOL_SETTINGS')
        
    @classmethod
    def poll(cls, context):
        return context.object
    
    def draw(self, context):
        l = self.layout
        
class ValveModelConfig(SMD_PT_toolpanel, Panel):
    bl_label = "ValveModel Config"
    bl_parent_id = "SMD_PT_ValveModel"
    bl_options = {'DEFAULT_CLOSED'}

class SMD_PT_Jigglebones(ValveModelConfig):
    bl_label = 'JiggleBones'
    
    @classmethod
    def poll(cls, context):
        return is_armature(context.object)
    
    def draw_header(self, context):
        self.layout.label(icon='CONSTRAINT_BONE')
    
    def draw(self, context):
        l = self.layout
        bx = l.box()
        
        ob = context.object
        
        vs_sce = context.scene.vs
        vs_ob = ob.vs
        
        bones = getBones(ob, select_all=True,bonetype='BONE', visible_only=False)
        bone = ob.data.bones.active
        
        if bone:
            bx.label(text=f'JiggleBones ({bone.name})', icon='BONE_DATA')
        else:
            bx.label(text='JiggleBones', icon='BONE_DATA')
        
        if bones:
            jigglebones = [b for b in bones if b.vs.bone_is_jigglebone]
            
            if len(jigglebones) > 0:
                bx.prop(vs_sce, 'jigglebone_export_path')
                bx.label(text=f'Write Jigglebones : {len(jigglebones)} Jigglebones',icon='FILE')
                row = bx.row(align=True)
                row.scale_y = 1.2
                row.operator(TOOLS_OT_WriteJiggleBone.bl_idname,text='Studiomdl').export_type = 'QC'
                row.operator(TOOLS_OT_WriteJiggleBone.bl_idname,text='Modeldoc').export_type = 'VMDL'
                #row.operator(TOOLS_OT_ImportJiggleBone.bl_idname, icon='IMPORT')
        
        if bone and bone.select:
            
            vs_bone = bone.vs
            
            col = bx.column()
            sub_box = col.box()  
                    
            sub_box.prop(vs_bone, 'bone_is_jigglebone', toggle=True)
            
            if vs_bone.bone_is_jigglebone:
                row = sub_box.row(align=True)
                row.prop(vs_bone, 'jiggle_flex_type')
                
                col = sub_box.column(align=True)
                    
                if vs_bone.jiggle_flex_type in ['FLEXIBLE', 'RIGID']:
                    col.prop(vs_bone, 'use_bone_length_for_jigglebone_length', toggle=True)
                    if not vs_bone.use_bone_length_for_jigglebone_length: col.prop(vs_bone, 'jiggle_length')
                    col.prop(vs_bone, 'jiggle_tip_mass')
                    
                if vs_bone.jiggle_flex_type == 'FLEXIBLE':
                    col.prop(vs_bone, 'jiggle_yaw_stiffness', slider=True)
                    col.prop(vs_bone, 'jiggle_yaw_damping', slider=True)
                    col.prop(vs_bone, 'jiggle_pitch_stiffness', slider=True)
                    col.prop(vs_bone, 'jiggle_pitch_damping', slider=True)
                    col.prop(vs_bone, 'jiggle_allow_length_flex', toggle=True)
                    if vs_bone.jiggle_allow_length_flex:
                        col.prop(vs_bone, 'jiggle_along_stiffness', slider=True)
                        col.prop(vs_bone, 'jiggle_along_damping', slider=True)
                
                if vs_bone.jiggle_flex_type in ['FLEXIBLE', 'RIGID']:
                    col = sub_box.column(align=True)
                    row = col.row(align=True)
                    row.prop(vs_bone, 'jiggle_has_angle_constraint',toggle=True)  
                    row.prop(vs_bone, 'jiggle_has_yaw_constraint',toggle=True)  
                    row.prop(vs_bone, 'jiggle_has_pitch_constraint',toggle=True)  
                    
                    if any([vs_bone.jiggle_has_angle_constraint, vs_bone.jiggle_has_yaw_constraint, vs_bone.jiggle_has_pitch_constraint]):
                        col = sub_box.column(align=True)
                        
                    if vs_bone.jiggle_has_angle_constraint:
                        col.prop(vs_bone, 'jiggle_angle_constraint')
                    
                    if vs_bone.jiggle_has_yaw_constraint:
                        row = col.row(align=True)
                        row.prop(vs_bone, 'jiggle_yaw_constraint_min', slider=True)
                        row.prop(vs_bone, 'jiggle_yaw_constraint_max', slider=True)
                        
                        col.prop(vs_bone, 'jiggle_yaw_friction', slider=True)
                        
                    if vs_bone.jiggle_has_pitch_constraint:
                        row = col.row(align=True)
                        row.prop(vs_bone, 'jiggle_pitch_constraint_min', slider=True)
                        row.prop(vs_bone, 'jiggle_pitch_constraint_max', slider=True)
                        
                        col.prop(vs_bone, 'jiggle_pitch_friction', slider=True)
                
                row = sub_box.row(align=True)
                row.prop(vs_bone, "jiggle_base_type")
                if vs_bone.jiggle_base_type == 'BASESPRING':
                    col = sub_box.column(align=True)
                    col.prop(vs_bone, "jiggle_base_stiffness", slider=True)
                    col.prop(vs_bone, "jiggle_base_damping", slider=True)
                    col.prop(vs_bone, "jiggle_base_mass", slider=True)
                    
                    col = sub_box.column(align=True)
                    
                    row = col.row(align=True)
                    row.prop(vs_bone, 'jiggle_has_left_constraint',toggle=True)  
                    row.prop(vs_bone, 'jiggle_has_up_constraint',toggle=True)  
                    row.prop(vs_bone, 'jiggle_has_forward_constraint',toggle=True) 
                    
                    if any([vs_bone.jiggle_has_left_constraint, vs_bone.jiggle_has_up_constraint, vs_bone.jiggle_has_forward_constraint]):
                        col = sub_box.column(align=True) 
                    
                    if vs_bone.jiggle_has_left_constraint:
                        row = col.row(align=True)
                        row.prop(vs_bone, 'jiggle_left_constraint_min', slider=True)
                        row.prop(vs_bone, 'jiggle_left_constraint_max', slider=True)
                        
                        col.prop(vs_bone, 'jiggle_left_friction', slider=True)
                        
                    if vs_bone.jiggle_has_up_constraint:
                        row = col.row(align=True)
                        row.prop(vs_bone, 'jiggle_up_constraint_min', slider=True)
                        row.prop(vs_bone, 'jiggle_up_constraint_max', slider=True)
                        
                        col.prop(vs_bone, 'jiggle_up_friction', slider=True)    
                        
                    if vs_bone.jiggle_has_forward_constraint:
                        row = col.row(align=True)
                        row.prop(vs_bone, 'jiggle_forward_constraint_min', slider=True)
                        row.prop(vs_bone, 'jiggle_forward_constraint_max', slider=True)
                        
                        col.prop(vs_bone, 'jiggle_forward_friction', slider=True)
                elif vs_bone.jiggle_base_type == 'BOING':
                    col = sub_box.column(align=True)
                    col.prop(vs_bone, "jiggle_impact_speed", slider=True)
                    col.prop(vs_bone, "jiggle_impact_angle", slider=True)
                    col.prop(vs_bone, "jiggle_damping_rate", slider=True)
                    col.prop(vs_bone, "jiggle_frequency", slider=True)
                    col.prop(vs_bone, "jiggle_amplitude", slider=True)
                else:
                    pass
                
        else:
            bx.box().label(text='Select a Valid Bone', icon='ERROR')
          
class TOOLS_OT_WriteJiggleBone(bpy.types.Operator):
    bl_idname = "smd.write_jigglebone"
    bl_label = "Write Jigglebones"
    
    get_all : BoolProperty(name='Export All Bones', default=True)
    clipboard : BoolProperty(name='Copy To Clipboard', default=False)
    
    export_type : EnumProperty(name='',items=[
        ('QC', 'Studiomdl', ''),
        ('VMDL', 'Modeldoc', ''),
        ])
    
    def draw(self, context):
        l = self.layout
        # Draw scaled icon
        if not self.clipboard: l.box().label(text='It will overwrite existing file', icon='WARNING_LARGE')

        l.prop(self, 'clipboard')
        l.prop(self, 'get_all')
    
    @classmethod
    def poll(cls, context):
        export_path = context.scene.vs.jigglebone_export_path.strip()
        if not export_path: return False
        
        ob = context.object
        if not is_armature(ob): return False
        return any([b for b in ob.data.bones if b.vs.bone_is_jigglebone])
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def execute(self, context):
        arm = context.object
        jigglebones = []
        
        if not self.clipboard:
            export_path, filename, ext = getFilePath(context.scene.vs.jigglebone_export_path)
            
            if not filename or not ext:
                self.report({'ERROR'}, "Invalid export path: must include filename and extension (e.g. jigglebones.qci)")
                return {'CANCELLED'}
            
            if self.export_type == 'QC' and ext in {'.qc', '.qci'}:
                os.makedirs(os.path.dirname(export_path), exist_ok=True)
                if not os.path.exists(export_path):
                    open(export_path, "w", encoding="utf8").close()
        
            elif self.export_type == 'VMDL' and ext in {'.vmdl', '.vmdl_prefab'}:
                os.makedirs(os.path.dirname(export_path), exist_ok=True)
                if not os.path.exists(export_path):
                    open(export_path, "w", encoding="utf8").close()
                    
            else:
                self.report({'ERROR'}, "Invalid file format QC format for Modeldoc or vice versa?")
                return {'CANCELLED'}
        
        if self.get_all:
            bones = arm.data.bones
        else:
            bones = getBones(arm, False, 'BONE')
            if not bones:
                self.report({'WARNING'}, 'No bones selected')
                return {'CANCELLED'}
        
        for bone in bones:
            if bone.vs.bone_is_jigglebone:
                jigglebones.append(bone)
        
        if not jigglebones:
            return {'CANCELLED'}
        
        compiled = None
        
        collection_groups = {}
        for bone in jigglebones:
            group_name = bone.collections[0].name if bone.collections else "Others"
            if group_name not in collection_groups:
                collection_groups[group_name] = []
            collection_groups[group_name].append(bone)
        
        if self.export_type == 'QC':
            entries = []
            for group_name, group_bones in collection_groups.items():
                entries.append("//=====================================================")
                entries.append(f"// Jigglebones - Collection: {group_name}")
                entries.append("//=====================================================")
                entries.append("")

                for bone in group_bones:
                    _datas = []
                    _datas.append(f'$jigglebone "{getBoneExportName(bone)}"')
                    _datas.append('{')
                    
                    jiggle_length = bone.length if bone.vs.use_bone_length_for_jigglebone_length else bone.vs.jiggle_length

                    if bone.vs.jiggle_flex_type in ['FLEXIBLE', 'RIGID']:
                        if bone.vs.jiggle_flex_type == 'FLEXIBLE':
                            _datas.append('\tis_flexible')
                        elif bone.vs.jiggle_flex_type == 'RIGID':
                            _datas.append('\tis_rigid')

                        _datas.append('\t{')
                        _datas.append(f'\t\tlength {jiggle_length}')
                        _datas.append(f'\t\ttip_mass {bone.vs.jiggle_tip_mass}')
                        
                        if bone.vs.jiggle_flex_type == 'FLEXIBLE':
                            _datas.append(f'\t\tyaw_stiffness {bone.vs.jiggle_yaw_stiffness}')
                            _datas.append(f'\t\tyaw_damping {bone.vs.jiggle_yaw_damping}')
                            
                            if bone.vs.jiggle_has_yaw_constraint:
                                _datas.append(f'\t\tyaw_constraint {-abs(degrees(bone.vs.jiggle_yaw_constraint_min))} {abs(degrees(bone.vs.jiggle_yaw_constraint_max))}')
                                _datas.append(f'\t\tyaw_friction {bone.vs.jiggle_yaw_friction}')
                            
                            _datas.append(f'\t\tpitch_stiffness {bone.vs.jiggle_pitch_stiffness}')
                            _datas.append(f'\t\tpitch_damping {bone.vs.jiggle_pitch_damping}')
                            
                            if bone.vs.jiggle_has_pitch_constraint:
                                _datas.append(f'\t\tpitch_constraint {-abs(degrees(bone.vs.jiggle_pitch_constraint_min))} {abs(degrees(bone.vs.jiggle_pitch_constraint_max))}')
                                _datas.append(f'\t\tpitch_friction {bone.vs.jiggle_pitch_friction}')
                            
                            if bone.vs.jiggle_allow_length_flex:
                                _datas.append(f'\t\tallow_length_flex')
                                _datas.append(f'\t\talong_stiffness {bone.vs.jiggle_along_stiffness}')
                            
                            if bone.vs.jiggle_has_angle_constraint:
                                _datas.append(f'\t\tangle_constraint {degrees(bone.vs.jiggle_angle_constraint)}')
                        
                        _datas.append('\t}')
                    
                    if bone.vs.jiggle_base_type == 'BASESPRING':
                        _datas.append('\thas_base_spring')
                        _datas.append('\t{')
                        _datas.append(f'\t\tstiffness {bone.vs.jiggle_base_stiffness}')
                        _datas.append(f'\t\tdamping {bone.vs.jiggle_base_damping}')
                        _datas.append(f'\t\tbase_mass {bone.vs.jiggle_base_mass}')
                        
                        if bone.vs.jiggle_has_left_constraint:
                            _datas.append(f'\t\tleft_constraint {-abs(bone.vs.jiggle_left_constraint_min)} {abs(bone.vs.jiggle_left_constraint_max)}')
                            _datas.append(f'\t\tleft_friction {bone.vs.jiggle_left_friction}')
                        
                        if bone.vs.jiggle_has_up_constraint:
                            _datas.append(f'\t\tup_constraint {-abs(bone.vs.jiggle_up_constraint_min)} {abs(bone.vs.jiggle_up_constraint_max)}')
                            _datas.append(f'\t\tup_friction {bone.vs.jiggle_up_friction}')
                        
                        if bone.vs.jiggle_has_forward_constraint:
                            _datas.append(f'\t\tforward_constraint {-abs(bone.vs.jiggle_forward_constraint_min)} {abs(bone.vs.jiggle_forward_constraint_max)}')
                            _datas.append(f'\t\tforward_friction {bone.vs.jiggle_forward_friction}')
                        
                        _datas.append('\t}')
                        
                    elif bone.vs.jiggle_base_type == 'BOING':
                        _datas.append('\tis_boing')
                        _datas.append('\t{')
                        _datas.append(f'\t\timpact_speed {bone.vs.jiggle_impact_speed}')
                        _datas.append(f'\t\timpact_angle {bone.vs.jiggle_impact_angle}')
                        _datas.append(f'\t\tdamping_rate {bone.vs.jiggle_damping_rate}')
                        _datas.append(f'\t\tfrequency {bone.vs.jiggle_frequency}')
                        _datas.append(f'\t\tamplitude {bone.vs.jiggle_amplitude}')
                        _datas.append('\t}')
                    
                    _datas.append('}')
                    _datas.append('\n')

                    entries.append("\n".join(_datas))
                        
            compiled = "\n".join(entries)
            
        elif self.export_type == 'VMDL':
            
            root = KVNode(_class="RootNode")
            datalist = None
            
            if self.clipboard: datalist = KVNode(_class="ScratchArea")
            else: datalist = KVNode(_class="JiggleBoneList")
            
            for group_name, group_bones in collection_groups.items():
                folder = KVNode(_class = "Folder", name = f"{sanitizeString(group_name)}")
                for bone in group_bones:
                
                    flex_type = 2
                    if bone.vs.jiggle_flex_type == 'FLEXIBLE': flex_type = 1
                    elif bone.vs.jiggle_flex_type == 'RIGID': flex_type = 0
                    
                    jiggle_length = bone.length if bone.vs.use_bone_length_for_jigglebone_length else bone.vs.jiggle_length
                
                    jigglebone = KVNode(
                        _class = "JiggleBone",
                        name = f"JiggleBone_{getBoneExportName(bone)}",
                        jiggle_root_bone = f"{getBoneExportName(bone)}",
                        jiggle_type = flex_type,
                        has_yaw_constraint = KVBool(bone.vs.jiggle_has_yaw_constraint),
                        has_pitch_constraint = KVBool(bone.vs.jiggle_has_pitch_constraint),
                        has_angle_constraint = KVBool(bone.vs.jiggle_has_angle_constraint),
                        has_base_spring = KVBool(True if bone.vs.jiggle_base_type == 'BASESPRING' else False),
                        allow_flex_length = KVBool(bone.vs.jiggle_allow_length_flex),
                        length = jiggle_length,
                        tip_mass = bone.vs.jiggle_tip_mass,
                        angle_limit = degrees(bone.vs.jiggle_angle_constraint),
                        min_yaw = degrees(bone.vs.jiggle_yaw_constraint_min),
                        max_yaw = degrees(bone.vs.jiggle_yaw_constraint_max),
                        yaw_friction = bone.vs.jiggle_yaw_friction,
                        min_pitch = degrees(bone.vs.jiggle_pitch_constraint_min),
                        max_pitch = degrees(bone.vs.jiggle_pitch_constraint_max),
                        pitch_friction = bone.vs.jiggle_pitch_friction,
                        base_mass = bone.vs.jiggle_base_mass,
                        base_stiffness = bone.vs.jiggle_base_stiffness,
                        base_damping = bone.vs.jiggle_base_damping,
                        base_left_min = bone.vs.jiggle_left_constraint_min,
                        base_left_max = bone.vs.jiggle_left_constraint_max,
                        base_left_friction = bone.vs.jiggle_left_friction,
                        base_up_min = bone.vs.jiggle_up_constraint_min,
                        base_up_max = bone.vs.jiggle_up_constraint_max,
                        base_up_friction = bone.vs.jiggle_up_friction,
                        base_forward_min = bone.vs.jiggle_forward_constraint_min,
                        base_forward_max = bone.vs.jiggle_forward_constraint_max,
                        base_forward_friction = bone.vs.jiggle_forward_friction,
                        yaw_stiffness = bone.vs.jiggle_yaw_stiffness,
                        yaw_damping = bone.vs.jiggle_yaw_damping,
                        pitch_stiffness = bone.vs.jiggle_pitch_stiffness,
                        pitch_damping = bone.vs.jiggle_pitch_damping,
                        along_stiffness = bone.vs.jiggle_along_stiffness,
                        along_damping = bone.vs.jiggle_along_damping,
                    )
                    
                    folder.add_child(jigglebone)
                datalist.add_child(folder)
            root.add_child(datalist)
            
            kv_doc = KVDocument()
            kv_doc.add_root("rootNode", root)
            compiled = kv_doc.to_text()
        else:
            pass
        
        if compiled:
            
            if not self.clipboard:
                with open(export_path, "w", encoding="utf-8") as f:
                    f.write(compiled)
                self.report({'INFO'}, f"Jigglebone data exported to {export_path}")
            else:
                bpy.context.window_manager.clipboard = compiled
                self.report({'INFO'}, f"Jigglebone data exported to Clipboard")
            
        else:
            self.report({'INFO'}, f"No Jigglesbones exported")
            return {'CANCELLED'}
        
        return {'FINISHED'}
    
class TOOLS_OT_curve_ramp_weights(bpy.types.Operator):
    bl_idname = 'tools.curve_ramp_weights'
    bl_label = 'Curve Ramp Bone Weights'
    bl_options = {'REGISTER', 'UNDO'}
    
    min_weight_mask: FloatProperty(name="Min Weight Mask", default=0.001, min=0.001, max=0.9, precision=4)
    max_weight_mask: FloatProperty(name="Max Weight Mask", default=1.0, min=0.01, max=1.0, precision=4)
    invert_ramp: BoolProperty(name="Invert Ramp Direction", default=False)
    normalize_to_parent: BoolProperty(name="Normalize Weight", default=True)
    constant_mask: BoolProperty(name="Ignore Vertex Value Mask", default=False)
    
    vertex_group_target: StringProperty(
        name="Target Vertex Group",
        description="Vertex group to receive residuals",
        default=""
    )
    
    is_humanoid_limb_twist: BoolProperty(name="Handle Limb Twist Bones", default=False)
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout

        col = layout.column(align=True)
        col.label(text="Weight Mask:")
        col.prop(self, "min_weight_mask", slider=True)
        col.prop(self, "max_weight_mask", slider=True)

        col.separator()
        col.label(text="Options:")
        row = col.row(align=True)
        col.prop(self, "invert_ramp", toggle=True)
        row.prop(self, "constant_mask", toggle=True)
        row.prop(self, "normalize_to_parent", toggle=True)
        col.prop(self, "is_humanoid_limb_twist", toggle=True)

        if not self.is_humanoid_limb_twist:
            col.separator()
            col.label(text="Target Vertex Group:")
            col.prop_search(
                self,
                "vertex_group_target",
                context.object,
                "vertex_groups",
                text=""
            )
    
    def execute(self, context):
        arm_obj = getArmature(context.object)
            
        if arm_obj is None:
            return {'CANCELLED'}
        
        if arm_obj.select_get():
            selected_bones = getBones(arm_obj, sorted=True, bonetype='POSEBONE', reverse_sort=True)
        else:
            selected_bones = [arm_obj.pose.bones.get(context.object.vertex_groups.active.name)]
            
        if not selected_bones:
            self.report({'ERROR'}, "No bones selected.")
            return {'CANCELLED'}
        
        # Save and switch to rest pose
        og_arm_pose_mode = arm_obj.data.pose_position
        arm_obj.data.pose_position = 'REST'
        bpy.context.view_layer.update()
        
        with PreserveContextMode(context.object,'WEIGHT_PAINT'), PreserveArmatureState(arm_obj):
            try:
                for bone in selected_bones:
                    target_vg = None
                    if self.is_humanoid_limb_twist:
                        twist_name = f"{bone.name} twist"
                        target_vg = twist_name
                    else:
                        target_vg = self.vertex_group_target if self.vertex_group_target else None

                    # Use the global brush curve for example
                    curve = context.tool_settings.weight_paint.brush.curve

                    convert_weight_to_curve_ramp(
                        arm=arm_obj,
                        bones=[bone],
                        curve=curve,
                        invert=self.invert_ramp,
                        vertex_group_target=target_vg,
                        min_weight_mask=self.min_weight_mask,
                        max_weight_mask=self.max_weight_mask,
                        normalize_to_parent=self.normalize_to_parent,
                        constant_mask=self.constant_mask,
                    )
            except:
                pass
        
        arm_obj.data.pose_position = og_arm_pose_mode
        bpy.context.view_layer.update()
        
        self.report({'INFO'}, f'Processed {len(selected_bones)} Bones')
        return {'FINISHED'}

class TOOLS_OT_SplitActiveWeightLinear(bpy.types.Operator):
    bl_idname = 'tools.split_active_weights_linear'
    bl_label = 'Split Active Weights Linearly'
    bl_options = {'REGISTER', 'UNDO'}

    smoothness: FloatProperty(
        name="Smoothness",
        description="Smoothness of the weight split (0 = hard cut, 1 = full smooth blend)",
        min=0.0, max=1.0,
        default=0.6
    )

    @classmethod
    def poll(cls, context):
        ob = context.object
        if ob.mode not in ['WEIGHT_PAINT', 'POSE']: return False
        
        arm = getArmature(ob)
        if arm is None: return False
        
        return arm.data.bones.active 
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def get_vgroup_index(self, mesh, name):
        for i, vg in enumerate(mesh.vertex_groups):
            if vg.name == name:
                return i
        return None

    def clamp(self, x, a, b):
        return max(a, min(x, b))

    def remap(self, value, minval, maxval):
        if maxval - minval == 0:
            return 0.5
        return (value - minval) / (maxval - minval)

    def project_point_onto_line(self, p, a, b):
        ap = p - a
        ab = b - a
        ab_len_sq = ab.length_squared
        if ab_len_sq == 0.0:
            return 0.0
        return self.clamp(ap.dot(ab) / ab_len_sq, 0.0, 1.0)

    def execute(self, context):
        arm = getArmature(context.object)
        bones = [b for b in context.selected_pose_bones if b != context.active_pose_bone]
        active_bone = arm.data.bones.active

        if not bones or len(bones) != 2 or not active_bone:
            self.report({'WARNING'}, "Select 3 bones: 2 others and 1 active (middle split point).")
            return {'CANCELLED'}
        
        og_arm_pose_mode = arm.data.pose_position
        arm.data.pose_position = 'REST'
        bpy.context.view_layer.update()

        bone1 = bones[0]
        bone2 = bones[1]
        active = active_bone

        bone1_name = bone1.name
        bone2_name = bone2.name
        active_name = active.name

        arm_matrix = arm.matrix_world
        p1 = arm_matrix @ ((bone1.head + bone1.tail) * 0.5)
        p2 = arm_matrix @ ((bone2.head + bone2.tail) * 0.5)

        meshes = getArmatureMeshes(arm, visible_only=context.scene.vs.visible_mesh_only)

        for mesh in meshes:
            vg_active = self.get_vgroup_index(mesh, active_name)
            vg1 = mesh.vertex_groups.get(bone1_name)
            if vg1 is None:
                vg1 = mesh.vertex_groups.new(name=bone1_name)

            # Ensure vg2 exists
            vg2 = mesh.vertex_groups.get(bone2_name)
            if vg2 is None:
                vg2 = mesh.vertex_groups.new(name=bone2_name)

            if vg_active is None or vg1 is None or vg2 is None:
                continue

            vtx_weights = {}
            for v in mesh.data.vertices:
                for g in v.groups:
                    if g.group == vg_active:
                        vtx_weights[v.index] = g.weight
                        break

            for vidx, weight in vtx_weights.items():
                vertex = mesh.data.vertices[vidx]
                world_pos = mesh.matrix_world @ vertex.co

                t = self.project_point_onto_line(world_pos, p1, p2)

                if self.smoothness == 0.0:
                    w1 = weight if t < 0.5 else 0.0
                    w2 = weight if t >= 0.5 else 0.0
                else:
                    s = self.smoothness
                    edge0 = 0.0 + s * 0.5
                    edge1 = 1.0 - s * 0.5
                    smooth_t = self.remap(t, edge0, edge1)
                    smooth_t = self.clamp(smooth_t, 0.0, 1.0)
                    w1 = weight * (1.0 - smooth_t)
                    w2 = weight * smooth_t

                vg1.add([vidx], w1, 'ADD')
                vg2.add([vidx], w2, 'ADD')

            mesh.vertex_groups.remove(mesh.vertex_groups[vg_active])
        
        with PreserveContextMode(arm, 'EDIT'):
            removeBone(arm,active_bone.name)
        
        arm.data.pose_position = og_arm_pose_mode

        self.report({'INFO'}, f"Split {active_name} between {bone1_name} and {bone2_name}")
        return {'FINISHED'} 

class SMD_PT_Developer(SMD_PT_toolpanel, bpy.types.Panel):
    bl_label = 'Developer Tools'
    bl_order = 1000 
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        return context.mode in ['OBJECT', 'POSE']
    
    def draw(self, context):
        l = self.layout
        bx = l.box()   
        
        ob = context.object
        
        bx.template_icon(icon_value=iconloader.preview_collections["custom_icons"]["LENNABEG"].icon_id, scale=5)
        draw_wrapped_text_col(bx, text='This no use to you so ignore this as to import you need my old add-on that I never released')
        
        col = bx.column()
        col.scale_y = 1.3
        col.operator(SMD_OT_ImportLegacyDatas.bl_idname, icon='MOD_DATA_TRANSFER')
        
class SMD_OT_ImportLegacyDatas(bpy.types.Operator):
    bl_idname = "smd.importlegacydata"
    bl_label = "Import Legacy Data"
    bl_options = {'REGISTER','UNDO'}
    
    @classmethod
    def poll(cls, context):
        return hasattr(context.scene, 'fubukitek')
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        l = self.layout
        bx = l.box()
        
        bx.label(text='This will overwrite every Object!', icon='ERROR')
    
    def execute(self, context):
        switch('OBJECT')
        bpy.context.view_layer.update()
        bpy.context.view_layer.depsgraph.update()

        obs = bpy.data.objects

        for ob in obs:
            if hasattr(ob, "vs"): _ = ob.vs
            if hasattr(ob, "fubukitek"): _ = ob.fubukitek

            if ob.type == 'MESH':
                if hasattr(ob.data, "vs"): _ = ob.data.vs
                if hasattr(ob.data, "fubukitek"): _ = ob.data.fubukitek
                for mat in ob.data.materials:
                    if mat:
                        if hasattr(mat, "vs"): _ = mat.vs
                        if hasattr(mat, "fubukitek"): _ = mat.fubukitek

            elif ob.type == 'ARMATURE':
                if hasattr(ob.data, "vs"): _ = ob.data.vs
                if hasattr(ob.data, "fubukitek"): _ = ob.data.fubukitek
                for col in getattr(ob.data, "collections", []):
                    if hasattr(col, "vs"): _ = col.vs
                    if hasattr(col, "fubukitek"): _ = col.fubukitek
                for bone in ob.data.bones:
                    if hasattr(bone, "vs"): _ = bone.vs
                    if hasattr(bone, "fubukitek"): _ = bone.fubukitek

        for ob in obs:
            fb_ob = ob.fubukitek
            vs_ob = ob.vs
            if not (fb_ob and vs_ob):
                self.report({'WARNING'}, f"Skipped object {ob.name} (missing vs/fubukitek)")
                continue

            setattr(vs_ob, "export_rotation_offset_x", radians(fb_ob.rotation_offset_x))
            setattr(vs_ob, "export_rotation_offset_y", radians(fb_ob.rotation_offset_y))
            setattr(vs_ob, "export_rotation_offset_z", radians(fb_ob.rotation_offset_z))

            setattr(vs_ob, "export_location_offset_x", fb_ob.translation_offset_x)
            setattr(vs_ob, "export_location_offset_y", fb_ob.translation_offset_y)
            setattr(vs_ob, "export_location_offset_z", fb_ob.translation_offset_z)

            if ob.type == 'MESH':
                fb_mesh = ob.data.fubukitek
                vs_mesh = ob.data.vs
                if not (fb_mesh and vs_mesh):
                    pass

                #setattr(vs_mesh, "export_filtered_shapekeys", fb_mesh.disable_shapekeys)
                #setattr(vs_mesh, "ignore_shapekey_vertex_output", fb_mesh.preserve_shapekey_normals)
                #setattr(vs_mesh, "is_cloth_proxy_mesh", fb_mesh.is_cloth)
                #vs_mesh.exportable_shapekeys.clear()
                #for old_item in getattr(fb_mesh, "exportable_shapekeys_new", []):
                #    new_item = vs_mesh.exportable_shapekeys.add()
                #    for attr in dir(old_item):
                #        if not attr.startswith("_") and hasattr(new_item, attr):
                #            try:
                #                setattr(new_item, attr, getattr(old_item, attr))
                #            except Exception:
                #                pass
                for mat in ob.data.materials:
                    if not mat:
                        continue
                    vs_mat = mat.vs
                    fb_mat = mat.fubukitek
                    if vs_mat and fb_mat:
                        #setattr(vs_mat, "do_not_export_faces", fb_mat.remove_faces_export)
                        #setattr(vs_mat, "bake_backface", fb_mat.prebake_backface)
                        setattr(vs_mat, "override_dmx_export_path", fb_mat.material_path)

            elif ob.type == 'ARMATURE':
                bpy.ops.object.mode_set(mode='POSE')
                bpy.ops.pose.select_all(action='DESELECT')
                bpy.ops.object.mode_set(mode='OBJECT')
                
                ob.data.use_mirror_x = False
                
                fb_arm = ob.data.fubukitek
                vs_arm = ob.data.vs
                if fb_arm and vs_arm:
                    #for col in ob.data.collections:
                    #    fb_col = col.fubukitek
                    #    vs_col = col.vs
                    #    if fb_col and vs_col:
                    #        setattr(vs_col, "export_bones_with_tipbones", fb_col.generate_tipbones)
                    #        setattr(vs_col, "merge_collection", fb_col.merge_to_parent)

                    setattr(vs_arm, "bone_direction_naming_left", fb_arm.export_name_left)
                    setattr(vs_arm, "bone_direction_naming_right", fb_arm.export_name_right)
                    setattr(vs_arm, "bone_name_startcount", fb_arm.export_name_startcount)
                    setattr(vs_arm, "ignore_bone_exportnames", fb_arm.export_ignoreExportName)
                    #setattr(vs_arm, "armature_json_header", fb_arm.jsonExportName)

                for bone in ob.data.bones:
                    fb_bone = bone.fubukitek
                    vs_bone = bone.vs
                    if not (fb_bone and vs_bone):
                        pass

                    setattr(vs_bone, "export_name", fb_bone.export_name)
                    setattr(vs_bone, "merge_to_parent", fb_bone.merge_to_parent)
                    setattr(vs_bone, "ignore_rotation_offset", fb_bone.ignore_export_offset)
                    
                    rot_x_val = fb_bone.rotation_offset_x if fb_bone.rotation_offset_x != 0 else fb_bone.rotation_offset_y
                    setattr(vs_bone, "export_rotation_offset_x", radians(rot_x_val))
                    
                    #setattr(vs_bone, "export_rotation_offset_y", radians(fb_bone.rotation_offset_x))
                    setattr(vs_bone, "export_rotation_offset_y", 0)
                    setattr(vs_bone, "export_rotation_offset_z", radians(fb_bone.rotation_offset_z))
                    setattr(vs_bone, "export_location_offset_x", fb_bone.translation_offset_x)
                    setattr(vs_bone, "export_location_offset_y", fb_bone.translation_offset_y)
                    setattr(vs_bone, "export_location_offset_z", fb_bone.translation_offset_z)
                    #setattr(vs_bone, "json_reference_bone", fb_bone.referenceBoneName)
                    #setattr(vs_bone, "json_do_not_parse_euler_rotation", fb_bone.ignoreAnglesSerialize)
                    #setattr(vs_bone, "json_add_twistbone", fb_bone.json_addtwistbone)
                    #setattr(vs_bone, "json_twist_bone_target", fb_bone.json_twisttype)
                    setattr(vs_bone, "bone_is_jigglebone", bool(fb_bone.jigglebone.types))
                    setattr(vs_bone, "jiggle_flex_type", 'RIGID' if 'is_rigid' in fb_bone.jigglebone.types else 'FLEXIBLE')
                    setattr(vs_bone, "use_bone_length_for_jigglebone_length", fb_bone.jigglebone.use_blend_bonelength)
                    setattr(vs_bone, "jiggle_length", fb_bone.jigglebone.length.val)
                    setattr(vs_bone, "jiggle_tip_mass", int(fb_bone.jigglebone.tip_mass.val))
                    setattr(vs_bone, "jiggle_has_angle_constraint", fb_bone.jigglebone.angle_constraint.enabled)
                    setattr(vs_bone, "jiggle_angle_constraint", radians(fb_bone.jigglebone.angle_constraint.val))
                    setattr(vs_bone, "jiggle_yaw_stiffness", fb_bone.jigglebone.yaw_stiffness.val)
                    setattr(vs_bone, "jiggle_yaw_damping", fb_bone.jigglebone.yaw_damping.val)
                    setattr(vs_bone, "jiggle_has_yaw_constraint", fb_bone.jigglebone.yaw_constraint.enabled)
                    setattr(vs_bone, "jiggle_yaw_constraint_min", radians(abs(fb_bone.jigglebone.yaw_constraint.min)))
                    setattr(vs_bone, "jiggle_yaw_constraint_max", radians(abs(fb_bone.jigglebone.yaw_constraint.max)))
                    setattr(vs_bone, "jiggle_yaw_friction", fb_bone.jigglebone.yaw_friction.val)
                    setattr(vs_bone, "jiggle_pitch_stiffness", fb_bone.jigglebone.pitch_stiffness.val)
                    setattr(vs_bone, "jiggle_pitch_damping", fb_bone.jigglebone.pitch_damping.val)
                    setattr(vs_bone, "jiggle_has_pitch_constraint", fb_bone.jigglebone.pitch_constraint.enabled)
                    setattr(vs_bone, "jiggle_pitch_constraint_min", radians(abs(fb_bone.jigglebone.pitch_constraint.min)))
                    setattr(vs_bone, "jiggle_pitch_constraint_max", radians(abs(fb_bone.jigglebone.pitch_constraint.max)))
                    setattr(vs_bone, "jiggle_pitch_friction", fb_bone.jigglebone.pitch_friction.val)
                    setattr(vs_bone, "jiggle_allow_length_flex", fb_bone.jigglebone.allow_length_flex)
                    setattr(vs_bone, "jiggle_along_stiffness", fb_bone.jigglebone.along_stiffness.val)
                    setattr(vs_bone, "jiggle_along_damping", fb_bone.jigglebone.along_damping.val)
                    
                    if 'has_base_spring' in fb_bone.jigglebone.types:
                        vs_bone.jiggle_base_type = 'BASESPRING'

                    setattr(vs_bone, "jiggle_base_stiffness", fb_bone.jigglebone.stiffness.val)
                    setattr(vs_bone, "jiggle_base_damping", fb_bone.jigglebone.damping.val)
                    setattr(vs_bone, "jiggle_base_mass", int(fb_bone.jigglebone.base_mass.val))
                    setattr(vs_bone, "jiggle_has_left_constraint", fb_bone.jigglebone.left_constraint.enabled)
                    setattr(vs_bone, "jiggle_left_constraint_min", abs(fb_bone.jigglebone.left_constraint.min))
                    setattr(vs_bone, "jiggle_left_constraint_max", abs(fb_bone.jigglebone.left_constraint.max))
                    setattr(vs_bone, "jiggle_left_friction", fb_bone.jigglebone.left_friction.val)
                    setattr(vs_bone, "jiggle_has_up_constraint", fb_bone.jigglebone.up_constraint.enabled)
                    setattr(vs_bone, "jiggle_up_constraint_min", abs(fb_bone.jigglebone.up_constraint.min))
                    setattr(vs_bone, "jiggle_up_constraint_max", abs(fb_bone.jigglebone.up_constraint.max))
                    setattr(vs_bone, "jiggle_up_friction", fb_bone.jigglebone.up_friction.val)
                    setattr(vs_bone, "jiggle_has_forward_constraint", fb_bone.jigglebone.forward_constraint.enabled)
                    setattr(vs_bone, "jiggle_forward_constraint_min", abs(fb_bone.jigglebone.forward_constraint.min))
                    setattr(vs_bone, "jiggle_forward_constraint_max", abs(fb_bone.jigglebone.forward_constraint.max))
                    setattr(vs_bone, "jiggle_forward_friction", fb_bone.jigglebone.forward_friction.val)

        return {'FINISHED'}
