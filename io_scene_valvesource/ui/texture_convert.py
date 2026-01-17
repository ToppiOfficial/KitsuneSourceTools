import bpy, os
import numpy as np
from PIL import Image
from ..core.imageprocesser import ImageProcessor

from bpy.types import (
    UIList, Operator, Context, UILayout
)

from bpy.props import (
    IntProperty
)

from .common import KITSUNE_PT_ToolsPanel, ShowConsole
from ..core.commonutils import draw_title_box_layout, draw_wrapped_texts

class TEXTURECONVERSION_UL_ItemList(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname) -> None: 
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(item, "name", text="", emboss=False, icon='MATERIAL')
            
            has_diffuse = item.diffuse_map != ""
            
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
    
    def execute(self, context : Context) -> set:
        item = context.scene.vs.texture_conversion_items.add()
        item.name = f"PBR Item {len(context.scene.vs.texture_conversion_items)}"
        context.scene.vs.texture_conversion_active_index = len(context.scene.vs.texture_conversion_items) - 1
        return {'FINISHED'}

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

class From_PBR_Conversion:
    @property
    def img_proc(self):
        if not hasattr(self, '_img_proc'):
            self._img_proc = ImageProcessor()
        return self._img_proc
    
    def _ensure_default_images(self):
        if "flat_normal" not in bpy.data.images:
            img = bpy.data.images.new("flat_normal", width=32, height=32, alpha=False)
            pixels = []
            for _ in range(32 * 32):
                pixels.extend([0.5, 0.5, 1.0, 1.0])
            img.pixels = pixels
            img.use_fake_user = True
            img.pack()
        
        if "flat_rmao" not in bpy.data.images:
            img = bpy.data.images.new("flat_rmao", width=32, height=32, alpha=False)
            pixels = []
            for _ in range(32 * 32):
                pixels.extend([1.0, 0.0, 1.0, 1.0])
            img.pixels = pixels
            img.use_fake_user = True
            img.pack()
        
        if "flat_alpha" not in bpy.data.images:
            img = bpy.data.images.new("flat_alpha", width=32, height=32, alpha=False)
            pixels = []
            for _ in range(32 * 32):
                pixels.extend([1.0, 1.0, 1.0, 1.0])
            img.pixels = pixels
            img.use_fake_user = True
            img.pack()
            
        bpy.context.view_layer.update()
    
    def _ensure_item_maps(self, item):
        self._ensure_default_images()
        
        if not item.normal_map or item.normal_map == "":
            item.normal_map = "flat_normal"
        
        if not item.roughness_map or item.roughness_map == "":
            item.roughness_map = "flat_rmao"
            item.roughness_map_ch = 'R'
            item.invert_roughness_map = False
        
        if not item.metal_map or item.metal_map == "":
            item.metal_map = "flat_rmao"
            item.metal_map_ch = 'G'
            item.invert_metal_map = False
        
        if not item.ambientocclu_map or item.ambientocclu_map == "":
            item.ambientocclu_map = "flat_rmao"
            item.ambientocclu_map_ch = 'B'
            item.invert_minvert_ambientocclu_mapetal_map = False
        
        if not item.alpha_map or item.alpha_map == "":
            item.alpha_map = "flat_alpha"
            item.alpha_map_ch = 'R'
            item.invert_alpha_map = False
    
    def _load_image_data(self, img_name: str):
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
    
    def _load_channel(self, img_name: str, channel: str):
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
        
        return result
    
    def _resize_channel(self, data, new_height, new_width):
        data_uint8 = (np.clip(data, 0, 1) * 255).astype(np.uint8)
        pil_img = Image.fromarray(data_uint8, mode='L')
        resized = pil_img.resize((new_width, new_height), Image.BILINEAR)
        return np.array(resized).astype(np.float32) / 255.0
    
    def _resize_image(self, data, target_height, target_width):
        if data is None:
            return None
        
        current_h, current_w = data.shape[:2]
        
        if (current_h, current_w) == (target_height, target_width):
            return data
        
        if len(data.shape) == 3:
            resized_channels = []
            for ch in range(data.shape[2]):
                resized_channels.append(self._resize_channel(data[:, :, ch], target_height, target_width))
            return np.stack(resized_channels, axis=2)
        else:
            return self._resize_channel(data, target_height, target_width)
    
    def _load_and_prep_channel(self, img_name: str, channel: str, target_h: int, target_w: int, invert: bool):
        data = self._load_channel(img_name, channel)
        if data is None:
            return None
        
        if target_h > 0 and target_w > 0:
            data = self._resize_image(data, target_h, target_w)
        
        if invert:
            data = 1.0 - data
        
        return data
    
    def _load_all_maps(self, item, diffuse_height, diffuse_width):
        print(f"\nLoading maps for '{item.name}'")
        maps = {}
        
        print(f"  Loading diffuse: {item.diffuse_map}")
        maps['diffuse'] = self._load_image_data(item.diffuse_map)
        print(f"  Loading normal: {item.normal_map}")
        maps['normal'] = self._load_image_data(item.normal_map)
        
        if maps['diffuse'] is None or maps['normal'] is None:
            print("  ERROR: Failed to load diffuse or normal map")
            return None
        
        print(f"  Loading roughness: {item.roughness_map} (channel: {item.roughness_map_ch})")
        rough_raw = self._load_channel(item.roughness_map, item.roughness_map_ch)
        print(f"  Loading metal: {item.metal_map} (channel: {item.metal_map_ch})")
        metal_raw = self._load_channel(item.metal_map, item.metal_map_ch)
        print(f"  Loading AO: {item.ambientocclu_map} (channel: {item.ambientocclu_map_ch})")
        ao_raw = self._load_channel(item.ambientocclu_map, item.ambientocclu_map_ch)
        
        if rough_raw is None or metal_raw is None or ao_raw is None:
            print("  ERROR: Failed to load roughness, metal, or AO map")
            return None
        
        max_h = max(rough_raw.shape[0], metal_raw.shape[0], ao_raw.shape[0], maps['normal'].shape[0])
        max_w = max(rough_raw.shape[1], metal_raw.shape[1], ao_raw.shape[1], maps['normal'].shape[1])
        print(f"  Target size for RMA maps: {max_h}x{max_w}")
        
        print("  Resizing roughness, metal, AO to target size...")
        maps['roughness'] = self._resize_image(rough_raw, max_h, max_w)
        maps['metal'] = self._resize_image(metal_raw, max_h, max_w)
        maps['ao'] = self._resize_image(ao_raw, max_h, max_w)
        
        print("  Applying inversions...")
        if item.invert_roughness_map:
            print("    Inverting roughness")
            maps['roughness'] = 1.0 - maps['roughness']
        if item.invert_metal_map:
            print("    Inverting metal")
            maps['metal'] = 1.0 - maps['metal']
        if item.invert_ambientocclu_map:
            print("    Inverting AO")
            maps['ao'] = 1.0 - maps['ao']
        
        print("  Creating sized variants...")
        maps['roughness_sized'] = self._resize_image(maps['roughness'], max_h, max_w)
        maps['metal_sized'] = self._resize_image(maps['metal'], max_h, max_w)
        maps['ao_sized'] = self._resize_image(maps['ao'], max_h, max_w)
        
        print(f"  Creating diffuse-sized variants ({diffuse_height}x{diffuse_width})...")
        maps['metal_diffuse'] = self._resize_image(maps['metal'], diffuse_height, diffuse_width)
        maps['ao_diffuse'] = self._resize_image(maps['ao'], diffuse_height, diffuse_width)
        
        print(f"  Creating normal-sized variants ({max_h}x{max_w})...")
        maps['metal_normal'] = self._resize_image(maps['metal'], max_h, max_w)
        maps['roughness_normal'] = self._resize_image(maps['roughness'], max_h, max_w)
        maps['normal_sized'] = self._resize_image(maps['normal'], max_h, max_w)
        
        print(f"  Loading alpha: {item.alpha_map} (channel: {item.alpha_map_ch})")
        maps['alpha'] = self._load_and_prep_channel(
            item.alpha_map, item.alpha_map_ch, 
            diffuse_height, diffuse_width, item.invert_alpha_map
        )
        if item.invert_alpha_map:
            print("    Inverting alpha")
        
        if item.skin_map and item.skin_map != "":
            print(f"  Loading skin: {item.skin_map} (channel: {item.skin_map_ch})")
            maps['skin'] = self._load_and_prep_channel(
                item.skin_map, item.skin_map_ch, 
                diffuse_height, diffuse_width, item.invert_skin_map
            )
            if item.invert_skin_map:
                print("    Inverting skin")
        
        if item.emissive_map and item.emissive_map != "":
            print(f"  Loading emissive: {item.emissive_map} (channel: {item.emissive_map_ch})")
            if item.emissive_map_ch == 'COLOR':
                emissive_data = self._load_image_data(item.emissive_map)
                if emissive_data is not None:
                    maps['emissive'] = self._resize_image(emissive_data, diffuse_height, diffuse_width)
            else:
                maps['emissive'] = self._load_and_prep_channel(
                    item.emissive_map, item.emissive_map_ch, 
                    diffuse_height, diffuse_width, False
                )
        
        print("  All maps loaded successfully")
        return maps
    
    def create_pbr_color_map(self, diffuse, alpha):
        result = diffuse.copy()
        result[:, :, 3] = alpha
        return result
    
    def create_pbr_emissive_map(self, emissive):
        height, width = emissive.shape
        emissive_map = np.ones((height, width, 4), dtype=np.float32)
        emissive_map[:, :, 0] = emissive
        emissive_map[:, :, 1] = emissive
        emissive_map[:, :, 2] = emissive
        return emissive_map
    
    def create_pbr_mrao_map(self, metal, roughness, ao):
        height, width = metal.shape
        mrao = np.ones((height, width, 4), dtype=np.float32)
        mrao[:, :, 0] = metal
        mrao[:, :, 1] = roughness
        mrao[:, :, 2] = ao
        return mrao
    
    def create_pbr_normal_map(self, normal, normal_map_preprocess):
        print(f"  Normal preprocess flags: {normal_map_preprocess}")
        print(f"  Type of normal_map_preprocess: {type(normal_map_preprocess)}")
        height, width = normal.shape[:2]
        result = np.ones((height, width, 4), dtype=np.float32)

        processed_normal_rgb = normal[:, :, :3].copy()

        if 'RED' in normal_map_preprocess:
            processed_normal_rgb[:, :, 2] = normal[:, :, 0]
            processed_normal_rgb[:, :, 0] = normal[:, :, 3] if normal.shape[2] > 3 else 0.5
            processed_normal_rgb[:, :, 1] = normal[:, :, 1]

        if 'INVERT_G' in normal_map_preprocess:
            processed_normal_rgb[:, :, 1] = 1.0 - processed_normal_rgb[:, :, 1]

        if 'FORCE_WHITE_B' in normal_map_preprocess:
            processed_normal_rgb[:, :, 2] = 1.0
        
        result[:, :, :3] = processed_normal_rgb
        result[:, :, 3] = 1.0
        return result
    
    def create_exponent_map(self, roughness, metal, color_alpha_mode):
        height, width = roughness.shape
        exponent = np.ones((height, width, 4))
        
        rough_inverted = 1.0 - roughness
        
        exponent_red = self.img_proc.brightness_contrast(
            np.stack([rough_inverted]*3 + [np.ones_like(rough_inverted)], axis=2),
            brightness=-100
        )[:, :, 0]
        
        exponent[:, :, 0] = exponent_red
        exponent[:, :, 1] = metal * 0.5
        exponent[:, :, 2] = 0.0
        exponent[:, :, 3] = 1.0
        
        return exponent
    
    def create_diffuse_map(self, diffuse, metal, ao, alpha, skin, ao_strength, 
                          skin_gamma, skin_contrast, color_alpha_mode, metal_mix_strength):
        result = diffuse.copy()
        
        ao_blend = np.stack([ao]*3 + [np.ones_like(ao)], axis=2)
        result = self.img_proc.multiply(result, ao_blend, opacity=ao_strength / 100.0)
        
        if color_alpha_mode == 'RGB_ALPHA':
            darkened = self.img_proc.brightness_contrast(result, brightness=-55 * metal_mix_strength, contrast=6, legacy=False)
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
            skin_mask = skin[:, :, np.newaxis]
            result[:, :, :3] = result[:, :, :3] * (1.0 - skin_mask) + diffuse[:, :, :3] * skin_mask
            
            if skin_gamma != 0:
                gamma_corrected = self.img_proc.exposure(result, exposure=0.0, gamma_correction=skin_gamma)
                result = self.img_proc.apply_with_mask(result, gamma_corrected, skin_mask)
            
            if skin_contrast != 0:
                contrasted = self.img_proc.brightness_contrast(result, brightness=0.0, contrast=skin_contrast, legacy=False)
                result = self.img_proc.apply_with_mask(result, contrasted, skin_mask)

        if color_alpha_mode != 'ALPHA':
            result[:, :, 3] = alpha

        return result
    
    def create_normal_map(self, normal, metal_uninverted, metal, roughness, 
                         normal_map_preprocess, is_npr, adjust_albedo, albedo_factor, diffuse_orig):
        print(f"  Normal preprocess flags: {normal_map_preprocess}")
        
        height, width = normal.shape[:2]
        result = np.ones((height, width, 4), dtype=np.float32)

        processed_normal_rgb = normal[:, :, :3].copy()

        if 'RED' in normal_map_preprocess:
            processed_normal_rgb[:, :, 2] = normal[:, :, 0]
            processed_normal_rgb[:, :, 0] = normal[:, :, 3] if normal.shape[2] > 3 else 0.5
            processed_normal_rgb[:, :, 1] = normal[:, :, 1]

        if 'INVERT_G' in normal_map_preprocess:
            processed_normal_rgb[:, :, 1] = 1.0 - processed_normal_rgb[:, :, 1]

        if 'FORCE_WHITE_B' in normal_map_preprocess:
            processed_normal_rgb[:, :, 2] = 1.0
        
        result[:, :, :3] = processed_normal_rgb

        rough_inverted = 1.0 - roughness
        rough_rgba = np.stack([rough_inverted]*3 + [np.ones_like(rough_inverted)], axis=2)
        
        exp_red_img = self.img_proc.brightness_contrast(rough_rgba, brightness=-100, contrast=0, legacy=True)
        metal_blend = np.stack([metal]*3 + [np.ones_like(metal)], axis=2)
        exp_red_img = self.img_proc.brightness_contrast(exp_red_img, brightness=1.5, legacy=True)
        exp_red_img = self.img_proc.multiply(exp_red_img, metal_blend, opacity=0.8)
        
        if not is_npr:
            exp_red_img = self.img_proc.brightness_contrast(exp_red_img, brightness=150, legacy=False)
        
        alpha_channel = exp_red_img[:, :, 0]
        
        if adjust_albedo and albedo_factor > 0 and diffuse_orig is not None:
            grayscale = np.mean(diffuse_orig[:, :, :3], axis=2)
            if grayscale.shape != (height, width):
                grayscale = self._resize_channel(grayscale, height, width)
            
            masked_grayscale = grayscale * metal_uninverted
            luminance_reducer = 1.0 - (masked_grayscale * albedo_factor)
            luminance_reducer = np.clip(luminance_reducer, 0.0, 1.0)
            alpha_channel = alpha_channel * luminance_reducer

        result[:, :, 3] = alpha_channel
        return result
    
    def create_emissive_map(self, diffuse, emissive):
        emissive_4ch = np.stack([emissive]*3 + [np.ones_like(emissive)], axis=2)
        result = self.img_proc.multiply(diffuse, emissive_4ch, opacity=1.0)
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
    
    def _process_pbr_conversion(self, item, maps, export_dir, base_name):
        print(f"\nProcessing PBR conversion for '{item.name}'")
        
        print("  Creating color map...")
        color_map = self.create_pbr_color_map(maps['diffuse'], maps['alpha'])
        color_path = os.path.join(export_dir, f"{base_name}_color.tga")
        print(f"  Saving: {color_path}")
        self.save_tga(color_map, color_path)
        
        print("  Creating MRAO map...")
        mrao_map = self.create_pbr_mrao_map(maps['metal_sized'], maps['roughness_sized'], maps['ao_sized'])
        mrao_path = os.path.join(export_dir, f"{base_name}_mrao.tga")
        print(f"  Saving: {mrao_path}")
        self.save_tga(mrao_map, mrao_path)
        
        print("  Creating normal map...")
        normal_map = self.create_pbr_normal_map(maps['normal'], item.normal_map_preprocess)
        normal_path = os.path.join(export_dir, f"{base_name}_normal.tga")
        print(f"  Saving: {normal_path}")
        self.save_tga(normal_map, normal_path)
        
        if 'emissive' in maps:
            print("  Creating emissive map...")
            if item.emissive_map_ch == "COLOR":
                emissive_map = maps['emissive']
            else:
                emissive_map = self.create_pbr_emissive_map(maps['emissive'])
            emissive_path = os.path.join(export_dir, f"{base_name}_emissive.tga")
            print(f"  Saving: {emissive_path}")
            self.save_tga(emissive_map, emissive_path)
        
        print("  PBR conversion complete!")
    
    def _process_phong_conversion(self, item, maps, export_dir, base_name):
        print(f"\nProcessing Phong conversion for '{item.name}'")
        
        print("  Creating exponent map...")
        exponent_map = self.create_exponent_map(maps['roughness'], maps['metal'], item.color_alpha_mode)
        exp_path = os.path.join(export_dir, f"{base_name}_e.tga")
        print(f"  Saving: {exp_path}")
        self.save_tga(exponent_map, exp_path)
        
        print("  Creating diffuse map...")
        diffuse_map = self.create_diffuse_map(
            maps['diffuse'], maps['metal_diffuse'], maps['ao_diffuse'], maps['alpha'],
            maps.get('skin'), item.ambientocclu_strength, 
            item.skin_map_gamma, item.skin_map_contrast, 
            item.color_alpha_mode, item.metal_diffuse_mix
        )
        diffuse_path = os.path.join(export_dir, f"{base_name}_d.tga")
        print(f"  Saving: {diffuse_path}")
        self.save_tga(diffuse_map, diffuse_path)
        
        print("  Creating normal map...")
        metal_uninverted = 1.0 - maps['metal_normal'] if item.invert_metal_map else maps['metal_normal']
        
        normal_map = self.create_normal_map(
            maps['normal_sized'], metal_uninverted, maps['metal_normal'], maps['roughness_normal'], item.normal_map_preprocess, item.is_npr,
            item.adjust_for_albedoboost, item.albedoboost_factor, maps['diffuse']
        )
        normal_path = os.path.join(export_dir, f"{base_name}_n.tga")
        print(f"  Saving: {normal_path}")
        self.save_tga(normal_map, normal_path)
        
        if 'emissive' in maps:
            print("  Creating emissive map...")
            if item.emissive_map_ch == "COLOR":
                emissive_map = maps['emissive']
            else:
                emissive_map = self.create_emissive_map(maps['diffuse'], maps['emissive'])
            emissive_path = os.path.join(export_dir, f"{base_name}_em.tga")
            print(f"  Saving: {emissive_path}")
            self.save_tga(emissive_map, emissive_path)
        
        print("  Phong conversion complete!")
    
    def process_item_conversion(self, item, report_func):
        print(f"Starting conversion for item: {item.name}")
        
        self._ensure_item_maps(item)
        
        export_path = bpy.context.scene.vs.texture_conversion_export_path
        
        export_dir = os.path.dirname(export_path)
        base_name = item.name
        
        print(f"Export directory: {export_dir}")
        print(f"Base name: {base_name}")
        
        if not export_dir or not base_name:
            error_msg = f"Invalid export path or name for '{item.name}'"
            print(f"ERROR: {error_msg}")
            report_func({'ERROR'}, error_msg)
            return False, error_msg
        
        print(f"\nLoading diffuse texture: {item.diffuse_map}")
        diffuse_img = self._load_image_data(item.diffuse_map)
        if diffuse_img is None:
            error_msg = f"Failed to load diffuse texture for '{item.name}'"
            print(f"ERROR: {error_msg}")
            report_func({'ERROR'}, error_msg)
            return False, error_msg
        
        diffuse_height, diffuse_width = diffuse_img.shape[:2]
        print(f"Diffuse size: {diffuse_height}x{diffuse_width}")
        
        print("\nLoading all texture maps...")
        maps = self._load_all_maps(item, diffuse_height, diffuse_width)
        if maps is None:
            error_msg = f"Failed to load required textures for '{item.name}'"
            print(f"ERROR: {error_msg}")
            report_func({'ERROR'}, error_msg)
            return False, error_msg
        
        conversion_mode = bpy.context.scene.vs.texture_conversion_mode
        print(f"\nConversion mode: {conversion_mode}")
        
        try:
            if conversion_mode == 'PBR':
                self._process_pbr_conversion(item, maps, export_dir, base_name)
            else:
                self._process_phong_conversion(item, maps, export_dir, base_name)
            
            print(f"Successfully converted: {item.name}")
            return True, None
        except Exception as e:
            error_msg = str(e)
            print(f"\nERROR during conversion: {error_msg}")
            print(f"{'='*60}\n")
            report_func({'ERROR'}, f"Conversion error for '{item.name}': {error_msg}")
            return False, error_msg

class TEXTURECONVERSION_OT_ProcessItem(Operator, From_PBR_Conversion):
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

class TEXTURECONVERSION_OT_Convert_Legacy_PBR_Items(Operator):
    bl_idname = "textureconvert.convert_legacy_pbr_items"
    bl_label = "Convert Legacy PBR Items"
    bl_description = "Convert legacy pbr_items to texture_conversion_items"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context) -> bool:
        sce = context.scene
        return bool(sce and hasattr(sce.vs, 'pbr_items'))
    
    def execute(self, context) -> set:
        sce = context.scene
        converted_count = 0
        
        if not hasattr(sce.vs, 'pbr_items'):
            self.report({'WARNING'}, "No legacy texture_conversion_items found")
            return {'CANCELLED'}
        
        if not hasattr(sce.vs, 'texture_conversion_items'):
            self.report({'ERROR'}, "texture_conversion_items property not found")
            return {'CANCELLED'}
        
        sce.vs.texture_conversion_items.clear()
        
        for old_item in sce.vs.pbr_items:
            new_item = sce.vs.texture_conversion_items.add()
            
            setattr(new_item, 'name', old_item.name)
            
            for prop in old_item.bl_rna.properties:
                if prop.identifier not in {'rna_type', 'name'}:
                    try:
                        setattr(new_item, prop.identifier, getattr(old_item, prop.identifier))
                    except:
                        pass
            
            converted_count += 1
        
        sce.vs.pbr_items.clear()
        
        self.report({'INFO'}, f"Converted {converted_count} items")
        return {'FINISHED'}

class TEXTURECONVERSION_PT_Panel(KITSUNE_PT_ToolsPanel):
    bl_label = 'Texture Conversion'
    
    def draw(self, context : Context) -> None:
        layout = self.layout
        vs = context.scene.vs
        
        box = draw_title_box_layout(layout, text="Texture Conversion",icon='TEXTURE')
        
        box.prop(vs, "texture_conversion_mode", text="Mode")
        box.prop(vs, "texture_conversion_export_path")
        
        if len(vs.pbr_items) > 0:
            op = box.operator(TEXTURECONVERSION_OT_Convert_Legacy_PBR_Items.bl_idname)
        
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
        vs = context.scene.vs
        
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
        
        if vs.texture_conversion_mode == 'PHONG':
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
        
        if item.color_alpha_mode == 'RGB_ALPHA':
            col.prop(item, 'metal_diffuse_mix', slider=True)
        
        box = layout.box()
        col = box.column(align=True)
        col.label(text="AO Map (Optional)")
        row = col.split(align=True, factor=0.8)
        row.prop_search(item, 'ambientocclu_map', bpy.data, 'images', text='')
        row.prop(item, 'ambientocclu_map_ch', text='')
        col.prop(item, 'ambientocclu_strength', slider=True)
        col.prop(item, 'invert_ambientocclu_map')
        
        box = layout.box()
        col = box.column(align=True)
        col.label(text="Emissive Map (Optional)")
        row = col.split(align=True, factor=0.8)
        row.prop_search(item, 'emissive_map', bpy.data, 'images', text='')
        row.prop(item, 'emissive_map_ch', text='')
            
        if vs.texture_conversion_mode == 'PHONG':
            box = layout.box()
            col = box.column(align=True)
            col.label(text="Albedo Boost Settings")
            col.prop(item, 'adjust_for_albedoboost')
            col.prop(item, 'albedoboost_factor', slider=True)
        
        box = layout.box()
        
        if vs.texture_conversion_mode == 'PHONG':
            box.prop(item, 'is_npr')
            
        box.prop(item, 'color_alpha_mode')
    
    def draw_help_section(self, context, layout):
        vs = context.scene.vs
        
        if vs.texture_conversion_mode == 'PHONG':
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
        
        if vs.texture_conversion_mode == 'PHONG':
            draw_wrapped_texts(layout,title='A good initial VMT phong setting', text=messages, boxed=False)
            draw_wrapped_texts(layout,text="The conversion may or may not be accurate!", alert=True, boxed=False)
        else:
            draw_wrapped_texts(layout,title='PBR Format', text=messages, boxed=False)