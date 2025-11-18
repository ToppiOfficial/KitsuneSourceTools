import bpy, os, blf
import numpy as np
from ..core.imageprocesser import ImageProcessor
import numpy as np

from bpy.types import (
    UIList, Operator, Context, UILayout
)

from bpy.props import (
    IntProperty
)

from .common import Tools_SubCategoryPanel, ModalUIProcess

from ..core.commonutils import (
    draw_title_box_layout, draw_wrapped_texts, draw_toggleable_layout
)

class PSEUDOPBR_UL_PBRToPhongList(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname) -> None: 
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

class PBRConversionMixin:
    @property
    def img_proc(self):
        if not hasattr(self, '_img_proc'):
            self._img_proc = ImageProcessor()
        return self._img_proc
    
    # ==================== Image Loading ====================
    
    def get_image_data(self, img_name: str):
        """Load full image data with all channels"""
        if not img_name or img_name not in bpy.data.images:
            return None
        
        img = bpy.data.images[img_name]
        original_colorspace = img.colorspace_settings.name
        img.colorspace_settings.name = 'Non-Color'
        
        width, height = img.size
        pixels = np.array(img.pixels[:]).reshape((height, width, img.channels)) # type: ignore
        
        img.colorspace_settings.name = original_colorspace
        
        if img.channels == 3:
            return np.dstack([pixels, np.ones((height, width))])
        return pixels
    
    def get_channel_data(self, img_name: str, channel: str, height: int, width: int):
        """Extract specific channel from image and optionally resize"""
        if not img_name or img_name not in bpy.data.images:
            return None
        
        img = bpy.data.images[img_name]
        original_colorspace = img.colorspace_settings.name
        img.colorspace_settings.name = 'Non-Color'
        
        w, h = img.size
        pixels = np.array(img.pixels[:]).reshape((h, w, img.channels)) # type: ignore
        
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
        
        if height > 0 and width > 0 and (h, w) != (height, width):
            result = self.resize_array(result, height, width)
        
        return result
    
    # ==================== Image Processing ====================
    
    def resize_array(self, data, new_height, new_width):
        """Bilinear interpolation resize"""
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
    
    def _apply_inversion(self, data, should_invert):
        """Apply inversion if needed"""
        return 1.0 - data if should_invert else data
    
    def _ensure_size(self, data, target_height, target_width):
        """Resize data if it doesn't match target size"""
        if data.shape != (target_height, target_width):
            return self.resize_array(data, target_height, target_width)
        return data
    
    # ==================== PBR Map Creation ====================
    
    def create_pbr_color_map(self, diffuse):
        """Create PBR color map (simple copy of diffuse)"""
        return diffuse.copy()
    
    def create_pbr_mrao_map(self, metal, roughness, ao, height, width, item):
        """Create PBR MRAO (Metal/Roughness/AO) packed texture"""
        mrao = np.ones((height, width, 4), dtype=np.float32)
        
        metal = self._ensure_size(metal, height, width)
        roughness = self._ensure_size(roughness, height, width)
        ao = self._ensure_size(ao, height, width)
        
        metal = self._apply_inversion(metal, item.invert_metal_map)
        roughness = self._apply_inversion(roughness, item.invert_roughness_map)
        ao = self._apply_inversion(ao, item.invert_ambientocclu_map)
        
        mrao[:, :, 0] = metal
        mrao[:, :, 1] = roughness
        mrao[:, :, 2] = ao
        mrao[:, :, 3] = 1.0
        
        return mrao
    
    def create_pbr_normal_map(self, normal, normal_type, item):
        """Create PBR normal map with type conversion"""
        height, width = normal.shape[:2]
        result = np.ones((height, width, 4), dtype=np.float32)

        if normal_type == 'DEF':
            result[:, :, :3] = normal[:, :, :3]
        elif normal_type == 'RED':
            result[:, :, 2] = normal[:, :, 0]
            result[:, :, 0] = normal[:, :, 3] if normal.shape[2] > 3 else 0.5
            result[:, :, 1] = normal[:, :, 1]
        elif normal_type == 'YELLOW':
            result[:, :, 0] = normal[:, :, 0]
            result[:, :, 1] = 1.0 - normal[:, :, 1]
            result[:, :, 2] = normal[:, :, 2]
        elif normal_type == 'OPENGL':
            result[:, :, 0] = normal[:, :, 0]
            result[:, :, 1] = 1.0 - normal[:, :, 1]
            result[:, :, 2] = normal[:, :, 2]
        
        result[:, :, 3] = 1.0
        return result
    
    # ==================== Phong Map Creation ====================
    
    def create_exponent_map(self, roughness, metal, color_alpha_mode, item):
        """Create Phong exponent map"""
        height, width = roughness.shape
        exponent = np.ones((height, width, 4))
        
        metal = self._apply_inversion(metal, item.invert_metal_map)
        rough_inverted = self._apply_inversion(roughness, not item.invert_roughness_map)
        
        exponent_red = self.img_proc.brightness_contrast(
            np.stack([rough_inverted]*3 + [np.ones_like(rough_inverted)], axis=2),
            brightness=-100
        )[:, :, 0]
        
        exponent[:, :, 0] = exponent_red
        exponent[:, :, 1] = metal if color_alpha_mode != 'RGB_ALPHA' else metal * 0.5
        exponent[:, :, 2] = 0.0
        exponent[:, :, 3] = 1.0
        
        return exponent
    
    def create_diffuse_map(self, diffuse, metal, exponent, ao, skin, ao_strength, 
                          skin_gamma, skin_contrast, color_alpha_mode, item):
        """Create Phong diffuse map with AO, skin, and metal adjustments"""
        height, width = diffuse.shape[:2]
        result = diffuse.copy()
        
        ao_blend = np.stack([ao]*3 + [np.ones_like(ao)], axis=2)
        ao_blend = self._apply_inversion(ao_blend, item.invert_ambientocclu_map)
        result = self.img_proc.multiply(result, ao_blend, opacity=ao_strength / 100.0)
        
        if color_alpha_mode == 'RGB_ALPHA':
            darkened = self.img_proc.brightness_contrast(result, brightness=-60, contrast=8, legacy=False)
            metal_mask = metal[:, :, np.newaxis]
            result = self.img_proc.apply_with_mask(result, darkened, metal_mask)
            saturated = self.img_proc.hue_saturation(result, saturation=20)
            result = self.img_proc.apply_with_mask(result, saturated, metal_mask)
            
        elif color_alpha_mode == 'ALPHA':
            result[:, :, 3] = metal
            contrasted = self.img_proc.brightness_contrast(result, brightness=0.0, contrast=10.0, legacy=True)
            metal_mask = metal[:, :, np.newaxis]
            result = self.img_proc.apply_with_mask(result, contrasted, metal_mask)
            saturated = self.img_proc.hue_saturation(result, saturation=25)
            result = self.img_proc.apply_with_mask(result, saturated, metal_mask)

        if skin is not None:
            skin_mask = self._apply_inversion(skin, item.invert_skin_map)
            skin_mask = skin_mask[:, :, np.newaxis]
            result[:, :, :3] = result[:, :, :3] * (1.0 - skin_mask) + diffuse[:, :, :3] * skin_mask
            
            if skin_gamma != 0:
                gamma_corrected = self.img_proc.exposure(result, exposure=0.0, gamma_correction=skin_gamma)
                result = self.img_proc.apply_with_mask(result, gamma_corrected, skin_mask)
            
            if skin_contrast != 0:
                contrasted = self.img_proc.brightness_contrast(result, brightness=0.0, contrast=skin_contrast, legacy=False)
                result = self.img_proc.apply_with_mask(result, contrasted, skin_mask)

        return result
    
    def create_normal_map(self, normal, metal, roughness, normal_type, item):
        """Create Phong normal map with alpha channel for specular"""
        height, width = normal.shape[:2]
        result = np.ones((height, width, 4), dtype=np.float32)

        metal = self._ensure_size(metal, height, width)
        roughness = self._ensure_size(roughness, height, width)
        
        metal_for_masking = self._apply_inversion(metal.copy(), item.invert_metal_map)
        
        metal = self._apply_inversion(metal, item.invert_metal_map)
        roughness = self._apply_inversion(roughness, item.invert_roughness_map)

        if normal_type == 'DEF':
            result[:, :, :3] = normal[:, :, :3]
        elif normal_type == 'RED':
            result[:, :, 2] = normal[:, :, 0]
            result[:, :, 0] = normal[:, :, 3] if normal.shape[2] > 3 else 0.5
            result[:, :, 1] = normal[:, :, 1]
        elif normal_type == 'YELLOW':
            result = self.img_proc.invert(normal)
        elif normal_type == 'OPENGL':
            result[:, :, 0] = normal[:, :, 0]
            result[:, :, 1] = 1.0 - normal[:, :, 1]
            result[:, :, 2] = normal[:, :, 2]

        if item.roughness_map is None:
            result[:, :, 3] = 0.0
        else: 
            rough_inverted = 1.0 - roughness
            
            rough_rgba = np.stack([rough_inverted]*3 + [np.ones_like(rough_inverted)], axis=2)
            
            exp_red_img = self.img_proc.brightness_contrast(
                rough_rgba,
                brightness=-100, contrast=0, legacy=True
            )
            
            metal_blend = np.stack([metal]*3 + [np.ones_like(metal)], axis=2)
            
            exp_red_img = self.img_proc.brightness_contrast(
                exp_red_img, brightness=1.5, legacy=True
            )
            
            exp_red_img = self.img_proc.multiply(exp_red_img, metal_blend, opacity=0.8)
            
            exp_red_img = self.img_proc.brightness_contrast(
                exp_red_img, brightness=150, legacy=False
            )
            
            alpha_channel = exp_red_img[:, :, 0]
            
            if item.adjust_for_albedoboost and item.albedoboost_factor > 0:
                original_color = self.get_image_data(item.diffuse_map)
                if original_color is not None:
                    grayscale = np.mean(original_color[:, :, :3], axis=2)
                    
                    if grayscale.shape != (height, width):
                        grayscale = self.resize_array(grayscale, height, width)
                    
                    masked_grayscale = grayscale * metal_for_masking
                    
                    luminance_reducer = 1.0 - (masked_grayscale * item.albedoboost_factor)
                    luminance_reducer = np.clip(luminance_reducer, 0.0, 1.0)
                    
                    alpha_channel = alpha_channel * luminance_reducer

            result[:, :, 3] = alpha_channel
        
        return result
    
    def create_emissive_map(self, diffuse, emissive):
        """Create emissive map by multiplying diffuse with emissive mask"""
        height, width = diffuse.shape[:2]
        emissive_4ch = np.stack([emissive]*3 + [np.ones_like(emissive)], axis=2)
        result = self.img_proc.multiply(diffuse, emissive_4ch, opacity=1.0)
        result[:, :, 3] = 1.0
        return result
    
    # ==================== File I/O ====================
    
    def save_tga(self, data, filepath):
        """Save numpy array as TGA file"""
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
    
    # ==================== Conversion Processing ====================
    
    def _load_and_prepare_maps(self, item, target_height, target_width):
        """Load and prepare texture maps with consistent sizing"""
        maps = {}
        
        maps['roughness'] = (
            self.get_channel_data(item.roughness_map, item.roughness_map_ch, target_height, target_width)
            if item.roughness_map else np.ones((target_height, target_width))
        )
        
        maps['metal'] = (
            self.get_channel_data(item.metal_map, item.metal_map_ch, target_height, target_width)
            if item.metal_map else np.zeros((target_height, target_width))
        )
        
        maps['ao'] = (
            self.get_channel_data(item.ambientocclu_map, item.ambientocclu_map_ch, target_height, target_width)
            if item.ambientocclu_map else np.ones((target_height, target_width))
        )
        
        for key in ['roughness', 'metal', 'ao']:
            maps[key] = self._ensure_size(maps[key], target_height, target_width)
        
        return maps
    
    def _process_pbr_conversion(self, item, diffuse_img, normal_img, export_dir, base_name):
        """Process PBR to PBR conversion"""
        diffuse_height, diffuse_width = diffuse_img.shape[:2]
        maps = self._load_and_prepare_maps(item, diffuse_height, diffuse_width)
        
        color_map = self.create_pbr_color_map(diffuse_img)
        self.save_tga(color_map, os.path.join(export_dir, f"{base_name}_color.tga"))
        
        mrao_map = self.create_pbr_mrao_map(
            maps['metal'], maps['roughness'], maps['ao'], 
            diffuse_height, diffuse_width, item
        )
        self.save_tga(mrao_map, os.path.join(export_dir, f"{base_name}_mrao.tga"))
        
        normal_map = self.create_pbr_normal_map(normal_img, item.normal_map_type, item)
        self.save_tga(normal_map, os.path.join(export_dir, f"{base_name}_normal.tga"))
    
    def _load_optional_maps(self, item, diffuse_height, diffuse_width):
        """Load optional maps (skin, emissive) with proper sizing"""
        optional = {}
        
        if item.skin_map and item.skin_map != "":
            skin_raw = self.get_channel_data(item.skin_map, item.skin_map_ch, 0, 0)
            if skin_raw is not None:
                optional['skin'] = self._ensure_size(skin_raw, diffuse_height, diffuse_width)
        
        if item.emissive_map and item.emissive_map != "":
            emissive_raw = self.get_channel_data(item.emissive_map, item.emissive_map_ch, 0, 0)
            if emissive_raw is not None:
                optional['emissive'] = self._ensure_size(emissive_raw, diffuse_height, diffuse_width)
        
        return optional
    
    def _determine_exponent_size(self, item):
        """Determine size for exponent map based on available inputs"""
        has_roughness = item.roughness_map is not None and item.roughness_map != ""
        has_metal = item.metal_map is not None and item.metal_map != ""
        
        if not has_roughness and not has_metal:
            return np.ones((32, 32)), np.zeros((32, 32))
        
        roughness_raw = self.get_channel_data(item.roughness_map, item.roughness_map_ch, 0, 0) if has_roughness else None
        metal_raw = self.get_channel_data(item.metal_map, item.metal_map_ch, 0, 0) if has_metal else None
        
        if roughness_raw is not None and metal_raw is not None:
            roughness_img, metal_img = roughness_raw, metal_raw
            
            if roughness_img.shape != metal_img.shape:
                max_height = max(roughness_img.shape[0], metal_img.shape[0])
                max_width = max(roughness_img.shape[1], metal_img.shape[1])
                roughness_img = self._ensure_size(roughness_img, max_height, max_width)
                metal_img = self._ensure_size(metal_img, max_height, max_width)
                
        elif roughness_raw is None:
            metal_img = metal_raw
            roughness_img = np.ones(metal_img.shape)
        elif metal_raw is None:
            roughness_img = roughness_raw
            metal_img = np.zeros(roughness_img.shape)
        else:
            roughness_img = np.ones((32, 32))
            metal_img = np.zeros((32, 32))
        
        return roughness_img, metal_img
    
    def _process_phong_conversion(self, item, diffuse_img, normal_img, export_dir, base_name):
        """Process PBR to Phong conversion"""
        diffuse_height, diffuse_width = diffuse_img.shape[:2]
        normal_height, normal_width = normal_img.shape[:2]
        
        roughness_img, metal_img = self._determine_exponent_size(item)
        
        exponent_map = self.create_exponent_map(roughness_img, metal_img, item.color_alpha_mode, item)
        self.save_tga(exponent_map, os.path.join(export_dir, f"{base_name}_e.tga"))
        
        has_ao = item.ambientocclu_map is not None and item.ambientocclu_map != ""
        ao_raw = self.get_channel_data(item.ambientocclu_map, item.ambientocclu_map_ch, 0, 0) if has_ao else None
        ao_img = self._ensure_size(ao_raw, diffuse_height, diffuse_width) if ao_raw is not None else np.ones((diffuse_height, diffuse_width))
        
        metal_for_diffuse = self._ensure_size(metal_img.copy(), diffuse_height, diffuse_width)
        
        optional_maps = self._load_optional_maps(item, diffuse_height, diffuse_width)
        
        diffuse_map = self.create_diffuse_map(
            diffuse_img, metal_for_diffuse, exponent_map, ao_img, 
            optional_maps.get('skin'), item.ambientocclu_strength, 
            item.skin_map_gamma, item.skin_map_contrast, 
            item.color_alpha_mode, item
        )
        self.save_tga(diffuse_map, os.path.join(export_dir, f"{base_name}_d.tga"))
        
        metal_for_normal = self._ensure_size(metal_img.copy(), normal_height, normal_width)
        roughness_for_normal = self._ensure_size(roughness_img.copy(), normal_height, normal_width)
        
        normal_map = self.create_normal_map(
            normal_img, metal_for_normal, roughness_for_normal, 
            item.normal_map_type, item
        )
        self.save_tga(normal_map, os.path.join(export_dir, f"{base_name}_n.tga"))
        
        if 'emissive' in optional_maps:
            emissive_map = self.create_emissive_map(diffuse_img, optional_maps['emissive'])
            self.save_tga(emissive_map, os.path.join(export_dir, f"{base_name}_em.tga"))
    
    def process_item_conversion(self, item, report_func):
        """Core conversion logic shared by both operators"""
        export_path = bpy.path.abspath(item.export_path)
        
        if not export_path.strip():
            export_path = bpy.context.scene.vs.pbr_to_phong_export_path
        
        export_dir = os.path.dirname(export_path)
        base_name = item.name
        
        if not export_dir or not base_name:
            error_msg = f"Invalid export path or name for '{item.name}'"
            report_func({'ERROR'}, error_msg)
            return False, error_msg
        
        diffuse_img = self.get_image_data(item.diffuse_map)
        normal_img = self.get_image_data(item.normal_map)
        
        if diffuse_img is None or normal_img is None:
            error_msg = f"Failed to load diffuse or normal texture for '{item.name}'"
            report_func({'ERROR'}, error_msg)
            return False, error_msg
        
        conversion_mode = bpy.context.scene.vs.pbr_conversion_mode
        
        try:
            if conversion_mode == 'PBR':
                self._process_pbr_conversion(item, diffuse_img, normal_img, export_dir, base_name)
            else:
                self._process_phong_conversion(item, diffuse_img, normal_img, export_dir, base_name)
            
            return True, None
        except Exception as e:
            error_msg = str(e)
            report_func({'ERROR'}, f"Conversion error for '{item.name}': {error_msg}")
            return False, error_msg

class PSEUDOPBR_OT_ProcessingModal(Operator, PBRConversionMixin):
    bl_idname = 'valvemodel.processing_modal'
    bl_label = 'Processing'
    bl_options = {'INTERNAL'}
    
    item_index: bpy.props.IntProperty(default=-1)
    process_all: bpy.props.BoolProperty(default=False)
    
    _timer = None
    _handle = None
    _processing_done = False
    _current_index = 0
    _success_count = 0
    _failed_items = []
    _total_items = 0
    _result = None
    
    def draw_callback(self, context):
        region = context.region
        
        if self.process_all:
            main_text = f"Processing Textures {self._current_index}/{self._total_items}"
        else:
            main_text = "Processing Texture"
        
        sub_text = "Please wait, Blender may appear frozen"
        
        progress = 0.0
        if self.process_all and self._total_items > 0:
            progress = self._current_index / self._total_items
        
        ModalUIProcess.draw_modal_overlay(region, main_text, sub_text, progress, show_progress=self.process_all)
    
    def modal(self, context, event):
        if event.type == 'TIMER':
            if not self._processing_done:
                vs = context.scene.vs
                
                try:
                    if self.process_all:
                        if self._current_index < len(vs.pbr_items):
                            item = vs.pbr_items[self._current_index]
                            
                            if not item.diffuse_map or not item.normal_map:
                                self._failed_items.append(f"{item.name} (missing maps)")
                            else:
                                success, error_msg = self.process_item_conversion(item, self.report)
                                
                                if success:
                                    self._success_count += 1
                                else:
                                    fail_reason = error_msg if error_msg else "unknown error"
                                    self._failed_items.append(f"{item.name} ({fail_reason})")
                            
                            self._current_index += 1
                            context.area.tag_redraw()
                            return {'RUNNING_MODAL'}
                        else:
                            self._processing_done = True
                    else:
                        if self.item_index >= 0 and self.item_index < len(vs.pbr_items):
                            item = vs.pbr_items[self.item_index]
                        else:
                            if vs.pbr_active_index < len(vs.pbr_items):
                                item = vs.pbr_items[vs.pbr_active_index]
                            else:
                                self._result = ({'ERROR'}, "No valid item selected")
                                self._processing_done = True
                                return {'RUNNING_MODAL'}
                        
                        if not item.diffuse_map or not item.normal_map:
                            self._result = ({'ERROR'}, f"Item '{item.name}' missing required maps (diffuse and normal)")
                            self._processing_done = True
                            return {'RUNNING_MODAL'}
                        
                        success, error_msg = self.process_item_conversion(item, self.report)
                        
                        if success:
                            self._result = ({'INFO'}, f"Converted '{item.name}' successfully")
                        else:
                            fail_reason = error_msg if error_msg else "unknown error"
                            self._result = ({'ERROR'}, f"Conversion failed for '{item.name}': {fail_reason}")
                        
                        self._processing_done = True
                
                except Exception as e:
                    self._result = ({'ERROR'}, f"Error during processing: {str(e)}")
                    self._processing_done = True
                    
            else:
                self.cleanup(context)
                
                if self.process_all:
                    if self._success_count > 0:
                        self.report({'INFO'}, f"Converted {self._success_count}/{self._total_items} items")
                    
                    if self._failed_items:
                        self.report({'WARNING'}, f"Failed: {', '.join(self._failed_items)}")
                else:
                    if self._result:
                        self.report(self._result[0], self._result[1])
                
                return {'FINISHED'}
        
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}
    
    def execute(self, context : Context) -> set:
        vs = context.scene.vs
        
        if self.process_all:
            self._total_items = len(vs.pbr_items)
            if self._total_items == 0:
                self.report({'ERROR'}, "No items to convert")
                return {'CANCELLED'}
        
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        
        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            self.draw_callback, (context,), 'WINDOW', 'POST_PIXEL'
        )
        
        return {'RUNNING_MODAL'}
    
    def cleanup(self, context):
        if self._timer:
            wm = context.window_manager
            wm.event_timer_remove(self._timer)
            self._timer = None
        
        if self._handle:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            self._handle = None
            context.area.tag_redraw()
    
    def cancel(self, context):
        self.cleanup(context)

class PSEUDOPBR_OT_ConvertPBRItem(Operator):
    bl_idname = 'valvemodel.convert_pbr_item'
    bl_label = 'Convert Selected Item'
    bl_options = {'INTERNAL'}
    
    item_index: IntProperty(default=-1)
    
    @classmethod
    def poll(cls, context):
        return len(context.scene.vs.pbr_items) > 0
    
    def execute(self, context) -> set:
        bpy.ops.valvemodel.processing_modal('INVOKE_DEFAULT', item_index=self.item_index, process_all=False)
        return {'FINISHED'}

class PSEUDOPBR_OT_ConvertAllPBRItems(Operator):
    bl_idname = 'valvemodel.convert_all_pbr_items'
    bl_label = 'Convert All Items'
    bl_options = {'INTERNAL'}
    
    @classmethod
    def poll(cls, context):
        return len(context.scene.vs.pbr_items) > 0
    
    def execute(self, context) -> set:
        bpy.ops.valvemodel.processing_modal('INVOKE_DEFAULT', process_all=True)
        return {'FINISHED'}

class PSEUDOPBR_PT_PBRtoPhong(Tools_SubCategoryPanel):
    bl_label = 'PseudoPBR'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Valve Model'
    
    def draw(self, context : Context) -> None:
        layout = self.layout
        vs = context.scene.vs
        
        box = draw_title_box_layout(layout, text="PBR Conversion",icon='MATERIAL')
        
        box.prop(vs, "pbr_conversion_mode", text="Mode")
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
    
    def draw_material_maps(self, context: Context, layout: UILayout, item):
        vs = context.scene.vs
        
        box = layout.box()
        col = box.column(align=True)
        col.label(text="Diffuse/Color Map")
        col.prop_search(item, 'diffuse_map', bpy.data, 'images', text='')
        
        if vs.pbr_conversion_mode == 'PHONG':
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
        row = col.split(align=True, factor=0.8)
        row.prop_search(item, 'normal_map', bpy.data, 'images', text='')
        row.prop(item, 'normal_map_type', text='')
        
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
        
        box = layout.box()
        col = box.column(align=True)
        col.label(text="AO Map (Optional)")
        row = col.split(align=True, factor=0.8)
        row.prop_search(item, 'ambientocclu_map', bpy.data, 'images', text='')
        row.prop(item, 'ambientocclu_map_ch', text='')
        col.prop(item, 'invert_ambientocclu_map')
        
        if vs.pbr_conversion_mode == 'PHONG':
            col.prop(item, 'ambientocclu_strength', slider=True)
            
            box = layout.box()
            col = box.column(align=True)
            col.label(text="Emissive Map (Optional)")
            row = col.split(align=True, factor=0.8)
            row.prop_search(item, 'emissive_map', bpy.data, 'images', text='')
            row.prop(item, 'emissive_map_ch', text='')
            
        if vs.pbr_conversion_mode == 'PHONG':
            box = layout.box()
            col = box.column(align=True)
            col.label(text="Albedo Boost Settings")
            col.prop(item, 'adjust_for_albedoboost')
            col.prop(item, 'albedoboost_factor', slider=True)
        
        box = layout.box()
        box.prop(item, 'color_alpha_mode')
    
    def draw_help_section(self, context, layout):
        vs = context.scene.vs
        
        if vs.pbr_conversion_mode == 'PHONG':
            messages = [
                'Use the following Phong settings for a balanced starting point:',
                '   - $phongboost 5',
                '   - $phongalbedotint 1',
                '   - $phongfresnelranges "[0.5 1 2]"',
                '   - $phongalbedoboost 55 (if applicable and not using the $color2 method)\n',
                'When applying a metal map to the color alpha channel, include:',
                '   - $color2 "[.18 .18 .18]"',
                '   - $blendtintbybasealpha 1\n',
                'However, avoid using $color2 and $blendtintbybasealpha together with $phongalbedoboost, as they can visually conflict.\n',
                'If using envmap:',
                '$envmaptint "[.12 .12 .12]"'
            ]
        else:
            messages = [
                'PBR outputs simple texture maps:',
                '   - _color: Diffuse with alpha channel preserved',
                '   - _mrao: Metal (R), Roughness (G), AO (B)',
                '   - _normal: Normal map with format conversion\n',
                'These maps can be used with PBR shaders that expect this texture layout.'
            ]
        
        helpsection = draw_toggleable_layout(layout,context.scene.vs,'show_pbrphong_help','Show Help','', icon='HELP')
        if helpsection is not None:
            if vs.pbr_conversion_mode == 'PHONG':
                draw_wrapped_texts(helpsection,title='A good initial VMT phong setting', text=messages, boxed=False)
                draw_wrapped_texts(helpsection,text="The conversion may or may not be accurate!", alert=True, boxed=False)
            else:
                draw_wrapped_texts(helpsection,title='PBR Format', text=messages, boxed=False)