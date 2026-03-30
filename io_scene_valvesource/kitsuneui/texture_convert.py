import bpy
from bpy.types import UIList, Operator, Context, UILayout
from bpy.props import IntProperty

from .common import KITSUNE_PT_ToolSubPanel, ShowConsole
from ..kitsunetools.commonutils import draw_title_box_layout
from ..kitsunetools.shader_maps_conversion.conversion_strategies import Texture_Convert

class TEXTURECONVERSION_UL_ItemList(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname) -> None: 
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row : UILayout = layout.row(align=True)
            row.prop(item, "name", text="", emboss=False, icon='MATERIAL')
            
            has_diffuse = item.diffuse_map != ""

            row.prop(item, 'texture_conversion_mode', emboss=False, text='')
            
            if has_diffuse:
                row.label(text="", icon='CHECKMARK')
            else:
                row.label(text="", icon='ERROR')
                
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon='MATERIAL')
         
            
class TEXTURECONVERSION_OT_AddItem(Operator):
    bl_idname = "textureconvert.add_pbr_item"
    bl_label = "Add PBR Item"
    bl_options = {'INTERNAL', 'UNDO'}

    def execute(self, context: Context) -> set:
        items = context.scene.vs.texture_conversion_items
        item = items.add()

        mat = getattr(getattr(context.active_object, 'active_material', None), 'name', None)
        item.name = mat if mat else f"PBR Item {len(items)}"

        context.scene.vs.texture_conversion_active_index = len(items) - 1
        self._try_assign_from_material(context, item)
        return {'FINISHED'}

    def _walk_to_image_with_channel(self, node, from_socket, depth=0, outer_group=None) -> tuple:
        if node is None:
            return None, None, None

        if node.type == 'TEX_IMAGE':
            if from_socket.name == 'Alpha':
                return node.image, 'A', None
            return node.image, None, None

        if node.type in {'SEPARATE_COLOR', 'SEPRGB'}:
            channel_map = {'Red': 'R', 'Green': 'G', 'Blue': 'B', 'Alpha': 'A'}
            channel = channel_map.get(from_socket.name)
            color_socket = node.inputs.get('Color') or node.inputs.get('Image')
            if color_socket and color_socket.is_linked:
                image, _, _ = self._walk_to_image_with_channel(
                    color_socket.links[0].from_node,
                    color_socket.links[0].from_socket,
                    depth + 1,
                    outer_group
                )
                return image, channel, node
            return None, channel, node

        if node.type == 'GROUP' and node.node_tree:
            group_output = next(
                (n for n in node.node_tree.nodes if n.type == 'GROUP_OUTPUT'), None
            )
            if group_output:
                socket_index = from_socket.index if hasattr(from_socket, 'index') else None
                inner_socket = None
                if socket_index is not None and socket_index < len(group_output.inputs):
                    inner_socket = group_output.inputs[socket_index]
                else:
                    inner_socket = group_output.inputs.get(from_socket.name)

                if inner_socket and inner_socket.is_linked:
                    return self._walk_to_image_with_channel(
                        inner_socket.links[0].from_node,
                        inner_socket.links[0].from_socket,
                        depth + 1,
                        node
                    )

        if node.type == 'GROUP_INPUT' and outer_group is not None:
            socket_index = from_socket.index if hasattr(from_socket, 'index') else None
            outer_socket = None
            if socket_index is not None and socket_index < len(outer_group.inputs):
                outer_socket = outer_group.inputs[socket_index]
            else:
                outer_socket = outer_group.inputs.get(from_socket.name)

            if outer_socket and outer_socket.is_linked:
                return self._walk_to_image_with_channel(
                    outer_socket.links[0].from_node,
                    outer_socket.links[0].from_socket,
                    depth + 1,
                    None
                )

        best_image, best_channel, best_sep, best_depth = None, None, None, float('inf')
        for inp in node.inputs:
            if not inp.is_linked:
                continue
            image, channel, sep_node = self._walk_to_image_with_channel(
                inp.links[0].from_node,
                inp.links[0].from_socket,
                depth + 1,
                outer_group
            )
            if image and depth < best_depth:
                best_image, best_channel, best_sep, best_depth = image, channel, sep_node, depth

        return best_image, best_channel, best_sep

    def _find_image_and_channel_from_socket(self, socket) -> tuple:
        if not socket or not socket.is_linked:
            return None, None, None
        return self._walk_to_image_with_channel(
            socket.links[0].from_node,
            socket.links[0].from_socket
        )

    def _assign_from_socket(self, socket, item, img_attr: str, ch_attr: str | None = None) -> tuple:
        image, channel, sep_node = self._find_image_and_channel_from_socket(socket)
        if image:
            setattr(item, img_attr, image.name)
            if ch_attr and channel:
                setattr(item, ch_attr, channel)
        return image, channel, sep_node

    def _assign_from_node_input(self, node, input_name: str, item, img_attr: str, ch_attr: str | None = None) -> tuple:
        return self._assign_from_socket(node.inputs.get(input_name), item, img_attr, ch_attr)

    def _try_assign_from_material(self, context: Context, item) -> None:
        ob = context.active_object
        if not ob or ob.type != 'MESH':
            return

        mat = ob.active_material
        if not mat or not mat.use_nodes:
            return

        principled = next(
            (n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None
        )
        if not principled:
            return

        self._assign_base_color(principled, item)
        self._assign_normal(principled, item)
        self._assign_rmo(principled, item)
        self._assign_alpha(principled, item)

    def _assign_base_color(self, principled, item) -> None:
        socket = principled.inputs.get('Base Color')
        if not socket or not socket.is_linked:
            return

        from_node = socket.links[0].from_node

        if getattr(from_node, 'blend_type', None) == 'MULTIPLY':
            self._assign_from_node_input(from_node, 'A', item, 'diffuse_map')
            self._assign_from_node_input(from_node, 'B', item, 'ambientocclu_map', 'ambientocclu_map_ch')
        else:
            self._assign_from_socket(socket, item, 'diffuse_map')

    def _assign_normal(self, principled, item) -> None:
        socket = principled.inputs.get('Normal')
        if not socket or not socket.is_linked:
            return

        from_node = socket.links[0].from_node
        if from_node.type == 'NORMAL_MAP':
            socket = from_node.inputs.get('Color')

        self._assign_from_socket(socket, item, 'normal_map')

    def _assign_rmo(self, principled, item) -> None:
        rmo_images = {}
        
        for socket_name, img_attr, ch_attr in (
            ('Roughness', 'roughness_map', 'roughness_map_ch'),
            ('Metallic',  'metal_map',     'metal_map_ch'),
        ):
            socket = principled.inputs.get(socket_name)
            image, channel, sep_node = self._assign_from_socket(socket, item, img_attr, ch_attr)
            if image:
                rmo_images[socket_name] = (image, channel, sep_node)

        if not item.ambientocclu_map:
            for socket_name, (image, channel, sep_node) in rmo_images.items():
                if sep_node:
                    color_socket = sep_node.inputs.get('Color') or sep_node.inputs.get('Image')
                    ao_image, _, _ = self._find_image_and_channel_from_socket(color_socket)
                    if ao_image:
                        item.ambientocclu_map = ao_image.name
                        item.ambientocclu_map_ch = 'B'
                        break

    def _assign_alpha(self, principled, item) -> None:
        socket = principled.inputs.get('Alpha')
        self._assign_from_socket(socket, item, 'alpha_map', 'alpha_map_ch')


class TEXTURECONVERSION_OT_RemoveItem(Operator):
    bl_idname = "textureconvert.remove_pbr_item"
    bl_label = "Remove PBR Item"
    bl_options = {'INTERNAL', 'UNDO'}
    
    @classmethod
    def poll(cls, context : Context):
        return len(context.scene.vs.texture_conversion_items) > 0
    
    def execute(self, context) -> set:
        context.scene.vs.texture_conversion_items.remove(context.scene.vs.texture_conversion_active_index)
        context.scene.vs.texture_conversion_active_index = min(max(0, context.scene.vs.texture_conversion_active_index - 1), 
                                                 len(context.scene.vs.texture_conversion_items) - 1)
        return {'FINISHED'}


class TEXTURECONVERSION_OT_ProcessItem(Operator, Texture_Convert):
    bl_idname = 'textureconvert.process_item'
    bl_label = 'Processing'
    bl_options = {'INTERNAL'}
    
    item_index: bpy.props.IntProperty(default=-1)
    process_all: bpy.props.BoolProperty(default=False)
    
    def execute(self, context):
        vs = context.scene.vs
        
        try:
            if self.process_all:
                total_items = len(vs.texture_conversion_items)
                if total_items == 0:
                    self.report({'ERROR'}, "No items to convert")
                    return {'CANCELLED'}
                
                success_count = 0
                failed_items = []
                
                for i, item in enumerate(vs.texture_conversion_items):
                    if not item.diffuse_map:
                        failed_items.append(f"{item.name} (missing diffuse map)")
                    else:
                        success, error_msg = self.process_item_conversion(item, self.report)
                        
                        if success:
                            success_count += 1
                        else:
                            fail_reason = error_msg if error_msg else "unknown error"
                            failed_items.append(f"{item.name} ({fail_reason})")
                
                if success_count > 0:
                    self.report({'INFO'}, f"Converted {success_count}/{total_items} items")
                
                if failed_items:
                    self.report({'WARNING'}, f"Failed: {', '.join(failed_items)}")
                
            else:
                if self.item_index >= 0 and self.item_index < len(vs.texture_conversion_items):
                    item = vs.texture_conversion_items[self.item_index]
                else:
                    if vs.texture_conversion_active_index < len(vs.texture_conversion_items):
                        item = vs.texture_conversion_items[vs.texture_conversion_active_index]
                    else:
                        self.report({'ERROR'}, "No valid item selected")
                        return {'CANCELLED'}
                
                if not item.diffuse_map:
                    self.report({'ERROR'}, f"Item '{item.name}' missing diffuse map")
                    return {'CANCELLED'}
                
                success, error_msg = self.process_item_conversion(item, self.report)
                
                if success:
                    self.report({'INFO'}, f"Converted '{item.name}' successfully")
                else:
                    fail_reason = error_msg if error_msg else "unknown error"
                    self.report({'ERROR'}, f"Conversion failed for '{item.name}': {fail_reason}")
                    return {'CANCELLED'}
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error during processing: {str(e)}")
            return {'CANCELLED'}


class TEXTURECONVERSION_OT_ConvertItem(Operator, ShowConsole):
    bl_idname = 'textureconvert.convert_pbr_item'
    bl_label = 'Convert Selected Item'
    bl_options = {'INTERNAL'}
    
    item_index: IntProperty(default=-1)
    
    @classmethod
    def poll(cls, context):
        return len(context.scene.vs.texture_conversion_items) > 0
    
    def execute(self, context) -> set:
        bpy.ops.textureconvert.process_item('EXEC_DEFAULT', item_index=self.item_index, process_all=False)
        return {'FINISHED'}


class TEXTURECONVERSION_OT_ConvertAllItems(Operator, ShowConsole):
    bl_idname = 'textureconvert.convert_all_pbr_items'
    bl_label = 'Convert All Items'
    bl_options = {'INTERNAL'}
    
    @classmethod
    def poll(cls, context):
        return len(context.scene.vs.texture_conversion_items) > 0
    
    def execute(self, context) -> set:
        bpy.ops.textureconvert.process_item('EXEC_DEFAULT', process_all=True)
        return {'FINISHED'}


class TEXTURECONVERSION_PT_Panel(KITSUNE_PT_ToolSubPanel):
    bl_label = 'Texture Conversion'
    
    def draw(self, context : Context) -> None:
        layout = self.layout
        vs = context.scene.vs
        
        box = draw_title_box_layout(layout, text="Texture Conversion",icon='TEXTURE')
        
        box.prop(vs, "texture_conversion_export_path")
        
        row = box.row()
        row.template_list("TEXTURECONVERSION_UL_ItemList", "", vs, "texture_conversion_items", 
                         vs, "texture_conversion_active_index", rows=3)
        
        col = row.column(align=True)
        col.operator(TEXTURECONVERSION_OT_AddItem.bl_idname, icon='ADD', text="")
        col.operator(TEXTURECONVERSION_OT_RemoveItem.bl_idname, icon='REMOVE', text="")
        
        if len(vs.texture_conversion_items) > 0 and vs.texture_conversion_active_index < len(vs.texture_conversion_items):
            item = vs.texture_conversion_items[vs.texture_conversion_active_index]
            
            col = box.column(align=True)
            if not item.name.strip(): col.alert = True
            col.prop(item, "name")
            col.alert = False
            
            self.draw_material_maps(context, box, item)
            
            row = box.row(align=True)
            op = row.operator(TEXTURECONVERSION_OT_ConvertItem.bl_idname, text="Convert This Item")
            op.item_index = vs.texture_conversion_active_index
            row.operator(TEXTURECONVERSION_OT_ConvertAllItems.bl_idname, text="Convert All")
            
        self.draw_help_section(context, box)
    
    def draw_material_maps(self, context: Context, layout: UILayout, item):
        layout.prop(item, 'texture_conversion_mode')

        box = layout.box()
        col = box.column(align=True)
        col.label(text="Diffuse/Color Map")
        col.prop_search(item, 'diffuse_map', bpy.data, 'images', text='')
        
        box = layout.box()
        col = box.column(align=True)
        col.label(text="Alpha Map")
        row = col.split(align=True, factor=0.8)
        row.prop_search(item, 'alpha_map', bpy.data, 'images', text='')
        row.prop(item, 'alpha_map_ch', text='')
        col.prop(item, 'invert_alpha_map')
        
        if item.texture_conversion_mode in {'PSEUDOPBR', 'NPR'}:
            box = layout.box()
            col = box.column(align=True)
            col.label(text="Skin Map")
            row = col.split(align=True, factor=0.8)
            row.prop_search(item, 'skin_map', bpy.data, 'images', text='')
            row.prop(item, 'skin_map_ch', text='')
            
            row = col.row(align=True)
            row.prop(item, 'skin_map_gamma', slider=True)
            row.prop(item, 'skin_map_contrast', slider=True)
            col.prop(item, 'invert_skin_map')
        
        box = layout.box()
        col = box.column(align=True)
        col.label(text="Normal Map")
        col.prop_search(item, 'normal_map', bpy.data, 'images', text='')
        
        col.label(text="Preprocessing Options")
        col.prop(item, 'normal_map_preprocess', expand=True)
        
        if item.texture_conversion_mode != 'NPR':
            box = layout.box()
            col = box.column(align=True)
            col.label(text="Roughness Map")
            row = col.split(align=True, factor=0.8)
            row.prop_search(item, 'roughness_map', bpy.data, 'images', text='')
            row.prop(item, 'roughness_map_ch', text='')
            col.prop(item, 'invert_roughness_map')
            
            box = layout.box()
            col = box.column(align=True)
            col.label(text="Metal Map")
            row = col.split(align=True, factor=0.8)
            row.prop_search(item, 'metal_map', bpy.data, 'images', text='')
            row.prop(item, 'metal_map_ch', text='')
            col.prop(item, 'invert_metal_map')

            if item.texture_conversion_mode == 'PSEUDOPBR':
                col.prop(item, 'phong_boost_influence', slider=True)
                col.prop(item, 'phong_exponent_influence', slider=True)
            
            if item.color_alpha_mode == 'RGB_ALPHA':
                col.prop(item, 'metal_diffuse_mix', slider=True)

        if item.texture_conversion_mode == 'PSEUDOPBR':
            box = layout.box()
            col = box.column(align=True)
            col.label(text="Albedo Boost Settings")
            col.prop(item, 'adjust_for_albedoboost')
            col.prop(item, 'albedoboost_factor', slider=True)
        
        box = layout.box()
        col = box.column(align=True)
        col.label(text="Specular Map")
        row = col.split(align=True, factor=0.8)
        row.prop_search(item, 'specular_map', bpy.data, 'images', text='')
        row.prop(item, 'specular_map_ch', text='')
        col.prop(item, 'invert_specular_map')
        col.prop(item, 'specular_blend')
        col.prop(item, 'specular_map_diffuse_baked', slider=True)
        
        box = layout.box()
        col = box.column(align=True)
        col.label(text="AO Map (Optional)")
        row = col.split(align=True, factor=0.8)
        row.prop_search(item, 'ambientocclu_map', bpy.data, 'images', text='')
        row.prop(item, 'ambientocclu_map_ch', text='')
        if not item.texture_conversion_mode == 'PBR': col.prop(item, 'ambientocclu_strength', slider=True)
        col.prop(item, 'invert_ambientocclu_map')
        
        if item.texture_conversion_mode in {'PSEUDOPBR', 'NPR'}:
            box = layout.box()
            col = box.column(align=True)
            col.label(text="Emissive Map (Optional)")
            row = col.split(align=True, factor=0.8)
            row.prop_search(item, 'emissive_map', bpy.data, 'images', text='')
            row.prop(item, 'emissive_map_ch', text='')
        
        if item.texture_conversion_mode == 'PSEUDOPBR':
            box = layout.box()
            box.prop(item, 'color_alpha_mode')
    
    def draw_help_section(self, context, layout):
        op2 = layout.operator("wm.url_open", text='Sample VMT', icon='INTERNET')
        op2.url = "https://github.com/ToppiOfficial/Source-Engine-Model-Prefabs/blob/main/l4d2_pseudopbr_patch/patch_pseudopbr_new.vmt"