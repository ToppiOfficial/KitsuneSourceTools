import bpy, os
import numpy as np

from bpy.types import (
    UIList, Operator, Context, UILayout
)

from bpy.props import (
    IntProperty
)

from .common import Tools_SubCategoryPanel

from ..core.commonutils import (
    draw_title_box, draw_wrapped_text_col, create_toggle_section
)

class PSEUDOPBR_UL_PBRToPhongList(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(item, "name", text="", emboss=False, icon='MATERIAL')
            
            has_diffuse = item.diffuse_map != ""
            has_normal = item.normal_map != ""
            
            if has_diffuse and has_normal:
                row.label(text="", icon='CHECKMARK')
            else:
                row.label(text="", icon='ERROR')
                
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon='MATERIAL')
            
class PSEUDOPBR_OT_AddPBRItem(Operator):
    bl_idname = "valvemodel.add_pbr_item"
    bl_label = "Add PBR Item"
    bl_options = {'INTERNAL', 'UNDO'}
    
    def execute(self, context : Context) -> set:
        item = context.scene.vs.pbr_items.add()
        item.name = f"PBR Item {len(context.scene.vs.pbr_items)}"
        context.scene.vs.pbr_active_index = len(context.scene.vs.pbr_items) - 1
        return {'FINISHED'}

class PSEUDOPBR_OT_RemovePBRItem(Operator):
    bl_idname = "valvemodel.remove_pbr_item"
    bl_label = "Remove PBR Item"
    bl_options = {'INTERNAL', 'UNDO'}
    
    @classmethod
    def poll(cls, context : Context):
        return len(context.scene.vs.pbr_items) > 0
    
    def execute(self, context) -> set:
        context.scene.vs.pbr_items.remove(context.scene.vs.pbr_active_index)
        context.scene.vs.pbr_active_index = min(max(0, context.scene.vs.pbr_active_index - 1), 
                                                 len(context.scene.vs.pbr_items) - 1)
        return {'FINISHED'}

# exponent[:, :, 0] = self.apply_curve(rough_inverted, [[90, 0], [221, 32], [255, 255]]) old curve code for exponent
class PBRConversionMixin:
    """Mixin class containing shared conversion logic for PBR operators"""
    
    def get_image_data(self, img_name: str):
        if not img_name or img_name not in bpy.data.images:
            return None
        
        img = bpy.data.images[img_name]
        original_colorspace = img.colorspace_settings.name
        img.colorspace_settings.name = 'Non-Color'
        
        width, height = img.size
        pixels = np.array(img.pixels[:]).reshape((height, width, img.channels))
        
        img.colorspace_settings.name = original_colorspace
        
        if img.channels == 3:
            return np.dstack([pixels, np.ones((height, width))])
        return pixels
    
    def get_channel_data(self, img_name: str, channel: str, height: int, width: int):
        if not img_name or img_name not in bpy.data.images:
            return None
        
        img = bpy.data.images[img_name]
        original_colorspace = img.colorspace_settings.name
        img.colorspace_settings.name = 'Non-Color'
        
        w, h = img.size
        pixels = np.array(img.pixels[:]).reshape((h, w, img.channels))
        
        img.colorspace_settings.name = original_colorspace
        
        channel_map = {'R': 0, 'G': 1, 'B': 2, 'A': 3}
        ch_idx = channel_map.get(channel)
        
        if ch_idx is not None:
            if ch_idx < img.channels:
                result = pixels[:, :, ch_idx]
            elif ch_idx == 3:
                result = np.ones((h, w))
            else:
                result = pixels[:, :, 0]
        else:
            result = np.mean(pixels[:, :, :3], axis=2)
        
        if (h, w) != (height, width):
            result = self.resize_array(result, height, width)
        
        return result
    
    def resize_array(self, data, new_height, new_width):
        old_height, old_width = data.shape
        
        y_ratio = old_height / new_height
        x_ratio = old_width / new_width
        
        y_coords = np.arange(new_height) * y_ratio
        x_coords = np.arange(new_width) * x_ratio
        
        y0 = np.floor(y_coords).astype(int)
        x0 = np.floor(x_coords).astype(int)
        y1 = np.minimum(y0 + 1, old_height - 1)
        x1 = np.minimum(x0 + 1, old_width - 1)
        
        y_weight = y_coords - y0
        x_weight = x_coords - x0
        
        result = np.zeros((new_height, new_width), dtype=np.float32)
        
        for i in range(new_height):
            for j in range(new_width):
                tl = data[y0[i], x0[j]]
                tr = data[y0[i], x1[j]]
                bl = data[y1[i], x0[j]]
                br = data[y1[i], x1[j]]
                
                top = tl * (1 - x_weight[j]) + tr * x_weight[j]
                bottom = bl * (1 - x_weight[j]) + br * x_weight[j]
                result[i, j] = top * (1 - y_weight[i]) + bottom * y_weight[i]
        
        return result
    
    def apply_curve(self, data, points):
        points_array = np.array(points)
        input_vals = points_array[:, 0] / 255.0
        output_vals = points_array[:, 1] / 255.0
        return np.interp(data, input_vals, output_vals)
    
    def create_exponent_map(self, roughness, metal):
        height, width = roughness.shape
        exponent = np.ones((height, width, 4))
        
        rough_inverted = 1.0 - roughness
        
        exponent_red = self.apply_curve(rough_inverted, [[90, 0], [221, 60], [255, 255]])
        exponent[:, :, 0] = exponent_red
        exponent[:, :, 1] = metal
        exponent[:, :, 2] = 0.0
        exponent[:, :, 3] = 1.0
        
        return exponent
    
    def create_diffuse_map(self, diffuse, metal, exponent, ao, skin, ao_strength, skin_gamma, skin_contrast,
                          use_envmap, darken_diffuse_metal, use_color_darken):
        height, width = diffuse.shape[:2]
        result = diffuse.copy()
        
        if skin is not None:
            if skin_gamma != 0 or skin_contrast != 0:
                rgb = result[:, :, :3]
                
                if skin_gamma != 0:
                    gamma_val = 1.0 / (1.0 + skin_gamma / 10.0) if skin_gamma > 0 else 1.0 - skin_gamma / 10.0
                    gamma_corrected = np.power(rgb, gamma_val)
                    rgb = rgb * (1.0 - skin[:, :, np.newaxis]) + gamma_corrected * skin[:, :, np.newaxis]
                
                if skin_contrast != 0:
                    contrast_val = skin_contrast * 25.5
                    f = (259 * (contrast_val + 255)) / (255 * (259 - contrast_val))
                    contrasted = np.clip(f * (rgb - 0.5) + 0.5, 0.0, 1.0)
                    rgb = rgb * (1.0 - skin[:, :, np.newaxis]) + contrasted * skin[:, :, np.newaxis]
                
                result[:, :, :3] = rgb
        
        strength = ao_strength / 100.0
        ao_effect = 1.0 - (1.0 - ao) * strength
        
        if skin is not None:
            ao_effect = ao_effect * (1.0 - skin) + skin
        
        result[:, :, :3] *= ao_effect[:, :, np.newaxis]

        if darken_diffuse_metal:
            darkened = self.apply_curve(result[:, :, :3], [[0, 0], [255, 100]])
            result[:, :, :3] = (result[:, :, :3] * (1.0 - metal[:, :, np.newaxis]) + 
                               darkened * metal[:, :, np.newaxis])
        elif use_color_darken:
            result[:, :, 3] = metal
            rgb = result[:, :, :3]
            contrast = 10
            f = (259 * (contrast + 255)) / (255 * (259 - contrast))
            contrasted = np.clip(f * (rgb - 0.5) + 0.5, 0.0, 1.0)
            result[:, :, :3] = rgb * (1.0 - metal[:, :, np.newaxis]) + contrasted * metal[:, :, np.newaxis]
        elif use_envmap:
            result[:, :, 3] = exponent[:, :, 0]

        return result
    
    def create_normal_map(self, normal, metal, roughness, normal_type, metal_strength=100.0):
        height, width = normal.shape[:2]
        result = np.ones((height, width, 4), dtype=np.float32)

        if metal.shape != (height, width):
            metal = self.resize_array(metal, height, width)
        
        if roughness.shape != (height, width):
            roughness = self.resize_array(roughness, height, width)

        if normal_type == 'DEF':
            result[:, :, :3] = normal[:, :, :3]
        elif normal_type == 'RED':
            result[:, :, 2] = normal[:, :, 0]
            result[:, :, 0] = normal[:, :, 3] if normal.shape[2] > 3 else 0.5
            result[:, :, 1] = normal[:, :, 1]
        elif normal_type == 'YELLOW':
            result[:, :, :3] = 1.0 - normal[:, :, :3]
        elif normal_type == 'OPENGL':
            result[:, :, 0] = normal[:, :, 0]
            result[:, :, 1] = 1.0 - normal[:, :, 1]
            result[:, :, 2] = normal[:, :, 2]

        rough_inverted = 1.0 - roughness
        
        exp_red = self.apply_curve(rough_inverted, [[57, 0], [201, 20], [255, 255]])
        exp_green_adjusted = metal * (metal_strength / 100.0)
        
        alpha = np.clip(exp_red / (1.0 - exp_green_adjusted + 1e-7), 0.0, 1.0)
        result[:, :, 3] = alpha
        
        return result
    
    def create_emissive_map(self, diffuse, emissive):
        height, width = diffuse.shape[:2]
        result = np.zeros((height, width, 4), dtype=np.float32)
        
        result[:, :, :3] = diffuse[:, :, :3] * emissive[:, :, np.newaxis]
        result[:, :, 3] = 1.0
        
        return result
        
    def save_tga(self, data, filepath):
        height, width = data.shape[:2]
        has_alpha = data.shape[2] >= 4

        if has_alpha:
            alpha = data[:, :, 3]
            if np.allclose(alpha, 1.0, atol=1e-5):
                data = data[:, :, :3]
                has_alpha = False

        img = bpy.data.images.new(name="temp_export", width=width, height=height, alpha=has_alpha)

        if has_alpha:
            pixels = data.astype(np.float32).flatten()
        else:
            alpha_filled = np.ones((height, width, 1), dtype=np.float32)
            pixels = np.concatenate([data, alpha_filled], axis=2).flatten()

        img.pixels = pixels.tolist()
        img.filepath_raw = filepath
        img.file_format = 'TARGA'
        img.save()
        bpy.data.images.remove(img)
    
    def process_item_conversion(self, item, report_func):
        """Core conversion logic shared by both operators"""
        
        export_path = bpy.path.abspath(item.export_path)
        
        if not export_path.strip():
            export_path = bpy.context.scene.vs.pbr_to_phong_export_path
        
        export_dir = os.path.dirname(export_path)
        base_name = item.name
        
        if not export_dir or not base_name:
            report_func({'ERROR'}, f"Invalid export path or name for '{item.name}'")
            return False
        
        # Load image data
        diffuse_img = self.get_image_data(item.diffuse_map)
        normal_img = self.get_image_data(item.normal_map)
        
        if diffuse_img is None or normal_img is None:
            report_func({'ERROR'}, f"Failed to load diffuse or normal texture for '{item.name}'")
            return False
        
        height, width = diffuse_img.shape[:2]
        
        # Load optional maps
        roughness_img = self.get_channel_data(item.roughness_map, item.roughness_map_ch, height, width) if item.roughness_map else np.ones((height, width))
        metal_img = self.get_channel_data(item.metal_map, item.metal_map_ch, height, width) if item.metal_map else np.zeros((height, width))
        ao_img = self.get_channel_data(item.ambientocclu_map, item.ambientocclu_map_ch, height, width) if item.ambientocclu_map else np.ones((height, width))
        emissive_img = self.get_channel_data(item.emissive_map, item.emissive_map_ch, height, width) if item.emissive_map else None
        skin_img = self.get_channel_data(item.skin_map, item.skin_map_ch, height, width) if item.skin_map else None
        
        # Create exponent map
        exponent_map = self.create_exponent_map(roughness_img, metal_img)
        self.save_tga(exponent_map, os.path.join(export_dir, f"{base_name}_e.tga"))
        
        # Create diffuse map
        diffuse_map = self.create_diffuse_map(diffuse_img, metal_img, exponent_map, ao_img, skin_img,
                                              item.ambientocclu_strength, item.skin_map_gamma, item.skin_map_contrast,
                                              item.use_envmap, item.darken_diffuse_metal, item.use_color_darken)
        self.save_tga(diffuse_map, os.path.join(export_dir, f"{base_name}_d.tga"))
        
        # Create normal map
        normal_map = self.create_normal_map(normal_img, metal_img, roughness_img, 
                                            item.normal_map_type, item.normal_metal_strength)
        self.save_tga(normal_map, os.path.join(export_dir, f"{base_name}_n.tga"))
        
        # Create emissive map if needed
        if emissive_img is not None:
            emissive_map = self.create_emissive_map(diffuse_img, emissive_img)
            self.save_tga(emissive_map, os.path.join(export_dir, f"{base_name}_em.tga"))
        
        return True

class PSEUDOPBR_OT_ConvertPBRItem(Operator, PBRConversionMixin):
    bl_idname = 'valvemodel.convert_pbr_item'
    bl_label = 'Convert Selected Item'
    bl_options = {'INTERNAL'}
    
    item_index: IntProperty(default=-1)
    
    @classmethod
    def poll(cls, context):
        return len(context.scene.vs.pbr_items) > 0
    
    def execute(self, context) -> set:
        vs = context.scene.vs
        
        if self.item_index >= 0 and self.item_index < len(vs.pbr_items):
            item = vs.pbr_items[self.item_index]
        else:
            if vs.pbr_active_index < len(vs.pbr_items):
                item = vs.pbr_items[vs.pbr_active_index]
            else:
                self.report({'ERROR'}, "No valid item selected")
                return {'CANCELLED'}
        
        if not item.diffuse_map or not item.normal_map:
            self.report({'ERROR'}, f"Item '{item.name}' missing required maps (diffuse and normal)")
            return {'CANCELLED'}
        
        result = self.process_item_conversion(item, self.report)
        
        if result:
            self.report({'INFO'}, f"Converted '{item.name}' successfully")
            return {'FINISHED'}
        else:
            return {'CANCELLED'}

class PSEUDOPBR_OT_ConvertAllPBRItems(Operator, PBRConversionMixin):
    bl_idname = 'valvemodel.convert_all_pbr_items'
    bl_label = 'Convert All Items'
    bl_options = {'INTERNAL'}
    
    @classmethod
    def poll(cls, context):
        return len(context.scene.vs.pbr_items) > 0
    
    def execute(self, context) -> set:
        vs = context.scene.vs
        success_count = 0
        failed_items = []
        
        for i, item in enumerate(vs.pbr_items):
            if not item.diffuse_map or not item.normal_map:
                failed_items.append(f"{item.name} (missing maps)")
                continue
            
            result = self.process_item_conversion(item, self.report)
            if result:
                success_count += 1
            else:
                failed_items.append(item.name)
        
        if success_count > 0:
            self.report({'INFO'}, f"Converted {success_count}/{len(vs.pbr_items)} items")
        
        if failed_items:
            self.report({'WARNING'}, f"Failed: {', '.join(failed_items)}")
        
        return {'FINISHED'}

class PSEUDOPBR_PT_PBRtoPhong(Tools_SubCategoryPanel):
    bl_label = 'PBR To Phong'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Valve Model'
    
    def draw(self, context):
        layout = self.layout
        vs = context.scene.vs
        
        box = draw_title_box(layout, text="PBR To Phong Conversion",icon='MATERIAL')
        
        box.prop(vs, "pbr_to_phong_export_path")
        
        row = box.row()
        row.template_list("PSEUDOPBR_UL_PBRToPhongList", "", vs, "pbr_items", 
                         vs, "pbr_active_index", rows=3)
        
        col = row.column(align=True)
        col.operator(PSEUDOPBR_OT_AddPBRItem.bl_idname, icon='ADD', text="")
        col.operator(PSEUDOPBR_OT_RemovePBRItem.bl_idname, icon='REMOVE', text="")
        
        if len(vs.pbr_items) > 0 and vs.pbr_active_index < len(vs.pbr_items):
            item = vs.pbr_items[vs.pbr_active_index]
            
            col = box.column(align=True)
            if not item.name.strip(): col.alert = True
            col.prop(item, "name")
            col.alert = False
            col.prop(item, "export_path")
            
            self.draw_material_maps(context, box, item)
            
            row = box.row(align=True)
            op = row.operator(PSEUDOPBR_OT_ConvertPBRItem.bl_idname, text="Convert This Item")
            op.item_index = vs.pbr_active_index
            row.operator(PSEUDOPBR_OT_ConvertAllPBRItems.bl_idname, text="Convert All")
            
        self.draw_help_section(context, box)
    
    def draw_material_maps(self, context : Context, layout : UILayout, item):
        col = layout.column(align=True)
        
        col.label(text="Diffuse/Color Map")
        col.prop_search(item, 'diffuse_map', bpy.data, 'images', text='')
        
        col.separator(factor=3)
        
        col.label(text="Skin Map")
        row = col.split(align=True,factor=0.8)
        row.prop_search(item, 'skin_map', bpy.data, 'images', text='')
        row.prop(item, 'skin_map_ch', text='')
        col.prop(item, 'skin_map_gamma', slider=True)
        col.prop(item, 'skin_map_contrast', slider=True)
        
        col.separator(factor=3)
        
        col.label(text="Normal Map")
        row = col.split(align=True,factor=0.8)
        row.prop_search(item, 'normal_map', bpy.data, 'images', text='')
        row.prop(item, 'normal_map_type', text='')
        col.prop(item, 'normal_metal_strength', slider=True)
        
        col.separator(factor=3)
        
        col.label(text="Roughness Map")
        row = col.split(align=True,factor=0.8)
        row.prop_search(item, 'roughness_map', bpy.data, 'images', text='')
        row.prop(item, 'roughness_map_ch', text='')
        
        col.separator(factor=3)
        
        col.label(text="Metal Map")
        row = col.split(align=True,factor=0.8)
        row.prop_search(item, 'metal_map', bpy.data, 'images', text='')
        row.prop(item, 'metal_map_ch', text='')
        
        col.separator(factor=3)
        
        col.label(text="AO Map (Optional)")
        row = col.split(align=True,factor=0.8)
        row.prop_search(item, 'ambientocclu_map', bpy.data, 'images', text='')
        row.prop(item, 'ambientocclu_map_ch', text='')
        col.prop(item, 'ambientocclu_strength', slider=True)
        
        col.separator(factor=3)
        
        col.label(text="Emissive Map (Optional)")
        row = col.split(align=True,factor=0.8)
        row.prop_search(item, 'emissive_map', bpy.data, 'images', text='')
        row.prop(item, 'emissive_map_ch', text='')
        
        col = layout.column(align=True)
        col.prop(item, 'use_envmap')
        col.prop(item, 'darken_diffuse_metal')
        col.prop(item, 'use_color_darken')
    
    def draw_help_section(self, context, layout):
        messages = [
            'Use the following Phong settings for a balanced starting point:',
            '   - $phongboost 5',
            '   - $phongalbedotint 1',
            '   - $phongfresnelranges "[0.5 1 2]"',
            '   - $phongalbedoboost 12 (if applicable)\n',
            'When applying a metal map to the color alpha channel, include:',
            '   - $color2 "[.18 .18 .18]"',
            '   - $blendtintbybasealpha 1\n',
            'However, avoid using $color2 or $blendtintbybasealpha together with $phongalbedoboost, as they can visually conflict.\n',
            'If using envmap:',
            '$envmaptint "[.3 .3 .3]"'
        ]
        
        helpsection = create_toggle_section(layout,context.scene.vs,'show_pbrphong_help','Show Help','', icon='HELP')
        if helpsection is not None:
            draw_wrapped_text_col(helpsection,title='A good initial VMT phong setting', text=messages,max_chars=40, boxed=False)
            draw_wrapped_text_col(helpsection,text="The conversion may or may not be accurate!", max_chars=40, alert=True, boxed=False)