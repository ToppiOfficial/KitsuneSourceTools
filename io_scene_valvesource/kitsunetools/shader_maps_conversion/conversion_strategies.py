import os
import numpy as np
import bpy

from .image_processor import ImageProcessor
from .texture_map_loader import TextureMapLoader
from .texture_map_defaults import TextureMapDefaults
from .normal_map_generators import PBRNormalMapGenerator, PhongNormalMapGenerator, NPRNormalMapGenerator
from .color_map_generators import PBRColorMapGenerator, PhongDiffuseMapGenerator, NPRColorMapGenerator
from .map_collection import MapCollection
from .other_map_generators import MRAOMapGenerator, ExponentMapGenerator, EmissiveMapGenerator, PhongEmissiveMapGenerator, SeparateMapGenerator

class ConversionStrategy:
    """Base class for conversion strategies"""
    
    def __init__(self, img_proc):
        self.img_proc = img_proc
    
    def convert(self, item, maps, export_dir: str, base_name: str):
        """Execute the conversion - to be implemented by subclasses"""
        raise NotImplementedError
    
    def _save_tga(self, data: np.ndarray, filepath: str, item=None):
        """Save texture as TGA file"""
        height, width = data.shape[:2]
        has_alpha = data.shape[2] >= 4
        
        if has_alpha and not (item is not None and item.texture_conversion_mode == 'NPR'):
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


class PBRConversionStrategy(ConversionStrategy):
    """Handles PBR texture conversion"""
    
    def convert(self, item, maps, export_dir: str, base_name: str):
        print(f"\nProcessing PBR conversion for '{item.name}'")
        
        print("  Creating color map...")
        color_gen = PBRColorMapGenerator(self.img_proc)
        color_map = color_gen.generate(maps, item)
        color_path = os.path.join(export_dir, f"{base_name}_color.tga")
        print(f"  Saving: {color_path}")
        self._save_tga(color_map, color_path)
        
        print("  Creating MRAO map...")
        mrao_gen = MRAOMapGenerator(self.img_proc)
        mrao_map = mrao_gen.generate(maps, item)
        mrao_path = os.path.join(export_dir, f"{base_name}_mrao.tga")
        print(f"  Saving: {mrao_path}")
        self._save_tga(mrao_map, mrao_path)
        
        print("  Creating normal map...")
        normal_gen = PBRNormalMapGenerator(self.img_proc)
        normal_map = normal_gen.generate(maps, item)
        normal_path = os.path.join(export_dir, f"{base_name}_normal.tga")
        print(f"  Saving: {normal_path}")
        self._save_tga(normal_map, normal_path)
        
        if 'emissive' in maps:
            print("  Creating emissive map...")
            emissive_gen = EmissiveMapGenerator(self.img_proc)
            emissive_map = emissive_gen.generate(maps, item)
            if emissive_map is not None:
                emissive_path = os.path.join(export_dir, f"{base_name}_emissive.tga")
                print(f"  Saving: {emissive_path}")
                self._save_tga(emissive_map, emissive_path)
        
        print("  PBR conversion complete!")


class SeparatePBRConversionStrategy(ConversionStrategy):
    """Handles PBR conversion with separate grayscale files instead of packed MRAO"""
    
    def convert(self, item, maps, export_dir: str, base_name: str):
        print(f"\nProcessing Separate PBR conversion for '{item.name}'")
        
        print("  Creating color map...")
        color_gen = PBRColorMapGenerator(self.img_proc)
        color_map = color_gen.generate(maps, item)
        color_path = os.path.join(export_dir, f"{base_name}_color.tga")
        self._save_tga(color_map, color_path)
        
        print("  Creating separate Metal, Roughness, and AO maps...")
        sep_gen = SeparateMapGenerator(self.img_proc)
        # Result is a stacked array [3, H, W]
        stacked_maps = sep_gen.generate(maps, item)
        
        # Define the suffixes and their corresponding indices in the stack
        suffixes = ['metal', 'roughness', 'ao']
        for i, suffix in enumerate(suffixes):
            map_data = stacked_maps[i]
            path = os.path.join(export_dir, f"{base_name}_{suffix}.tga")
            print(f"  Saving: {path}")
            self._save_tga(map_data, path)
        
        print("  Creating normal map...")
        normal_gen = PBRNormalMapGenerator(self.img_proc)
        normal_map = normal_gen.generate(maps, item)
        normal_path = os.path.join(export_dir, f"{base_name}_normal.tga")
        self._save_tga(normal_map, normal_path)
        
        if 'emissive' in maps:
            print("  Creating emissive map...")
            emissive_gen = EmissiveMapGenerator(self.img_proc)
            emissive_map = emissive_gen.generate(maps, item)
            if emissive_map is not None:
                emissive_path = os.path.join(export_dir, f"{base_name}_emissive.tga")
                self._save_tga(emissive_map, emissive_path)
        
        print("  Separate PBR conversion complete!")


class PhongConversionStrategy(ConversionStrategy):
    """Handles Phong (PSEUDOPBR) texture conversion"""
    
    def convert(self, item, maps, export_dir: str, base_name: str):
        print(f"\nProcessing Phong conversion for '{item.name}'")
        
        print("  Creating exponent map...")
        exp_gen = ExponentMapGenerator(self.img_proc)
        exponent_map = exp_gen.generate(maps, item)
        exp_path = os.path.join(export_dir, f"{base_name}_e.tga")
        print(f"  Saving: {exp_path}")
        self._save_tga(exponent_map, exp_path)
        
        print("  Creating diffuse map...")
        diffuse_gen = PhongDiffuseMapGenerator(self.img_proc)
        diffuse_map = diffuse_gen.generate(maps, item)
        diffuse_path = os.path.join(export_dir, f"{base_name}_d.tga")
        print(f"  Saving: {diffuse_path}")
        self._save_tga(diffuse_map, diffuse_path)
        
        print("  Creating normal map...")
        normal_gen = PhongNormalMapGenerator(self.img_proc)
        normal_map = normal_gen.generate(maps, item)
        normal_path = os.path.join(export_dir, f"{base_name}_n.tga")
        print(f"  Saving: {normal_path}")
        self._save_tga(normal_map, normal_path)
        
        if 'emissive' in maps:
            print("  Creating emissive map...")
            emissive_gen = PhongEmissiveMapGenerator(self.img_proc)
            emissive_map = emissive_gen.generate(maps, item)
            if emissive_map is not None:
                emissive_path = os.path.join(export_dir, f"{base_name}_em.tga")
                print(f"  Saving: {emissive_path}")
                self._save_tga(emissive_map, emissive_path)
        
        print("  Phong conversion complete!")


class NPRConversionStrategy(ConversionStrategy):
    """Handles NPR texture conversion"""
    
    def convert(self, item, maps, export_dir: str, base_name: str):
        print(f"\nProcessing NPR conversion for '{item.name}'")
        
        print("  Creating color map...")
        color_gen = NPRColorMapGenerator(self.img_proc)
        color_map = color_gen.generate(maps, item)
        color_path = os.path.join(export_dir, f"{base_name}_d.tga")
        print(f"  Saving: {color_path}")
        self._save_tga(color_map, color_path, item=item)
        
        print("  Creating normal map...")
        normal_gen = NPRNormalMapGenerator(self.img_proc)
        normal_map = normal_gen.generate(maps, item)
        normal_path = os.path.join(export_dir, f"{base_name}_n.tga")
        print(f"  Saving: {normal_path}")
        self._save_tga(normal_map, normal_path)
        
        if 'emissive' in maps:
            print("  Creating emissive map...")
            emissive_gen = PhongEmissiveMapGenerator(self.img_proc)
            emissive_map = emissive_gen.generate(maps, item)
            if emissive_map is not None:
                emissive_path = os.path.join(export_dir, f"{base_name}_em.tga")
                print(f"  Saving: {emissive_path}")
                self._save_tga(emissive_map, emissive_path)
        
        print("  NPR conversion complete!")


class Texture_Convert:
    @property
    def img_proc(self):
        if not hasattr(self, '_img_proc'):
            self._img_proc = ImageProcessor()
        return self._img_proc
    
    @property
    def loader(self):
        if not hasattr(self, '_loader'):
            self._loader = TextureMapLoader()
        return self._loader
    
    @property
    def strategies(self):
        if not hasattr(self, '_strategies'):
            self._strategies = {
                'PBR': PBRConversionStrategy(self.img_proc),
                'SOURCE2PBR': SeparatePBRConversionStrategy(self.img_proc),
                'PSEUDOPBR': PhongConversionStrategy(self.img_proc),
                'NPR': NPRConversionStrategy(self.img_proc),
            }
        return self._strategies
    
    def process_item_conversion(self, item, report_func):
        """Main entry point for converting a texture item"""
        print(f"Starting conversion for item: {item.name}")
        
        try:
            self._prepare_item(item)
            
            export_dir, base_name = self._get_export_info(item, report_func)
            if not export_dir or not base_name:
                return False, "Invalid export path or name"
            
            maps = self._load_all_maps(item, report_func)
            if maps is None:
                return False, "Failed to load required maps"
            
            self._execute_conversion(item, maps, export_dir, base_name)
            
            return True, None
            
        except Exception as e:
            error_msg = str(e)
            print(f"\nERROR during conversion: {error_msg}")
            report_func({'ERROR'}, f"Conversion error for '{item.name}': {error_msg}")
            return False, error_msg
    
    def _prepare_item(self, item):
        """Prepare the item by ensuring defaults and creating fallback images"""
        self.loader.ensure_default_images()
        TextureMapDefaults.ensure_item_maps(item)
    
    def _get_export_info(self, item, report_func) -> tuple:
        """Get export directory and base name"""
        export_path = bpy.context.scene.vs.texture_conversion_export_path
        export_dir = os.path.dirname(export_path)
        base_name = item.name
        
        print(f"Export directory: {export_dir}")
        print(f"Base name: {base_name}")
        
        if not export_dir or not base_name:
            error_msg = f"Invalid export path or name for '{item.name}'"
            print(f"ERROR: {error_msg}")
            report_func({'ERROR'}, error_msg)
            return None, None
        
        return export_dir, base_name
    
    def _load_all_maps(self, item, report_func):
        """Load all texture maps for the item"""
        print(f"\nLoading diffuse texture: {item.diffuse_map}")
        diffuse_img = self.loader.load_image_data(item.diffuse_map)
        
        if diffuse_img is None:
            error_msg = f"Failed to load diffuse texture for '{item.name}'"
            print(f"ERROR: {error_msg}")
            report_func({'ERROR'}, error_msg)
            return None
        
        diffuse_height, diffuse_width = diffuse_img.shape[:2]
        print(f"Diffuse size: {diffuse_height}x{diffuse_width}")
        
        map_collection = MapCollection(self.loader)
        success = map_collection.load_all(item, diffuse_height, diffuse_width)
        
        if not success:
            error_msg = f"Failed to load required textures for '{item.name}'"
            print(f"ERROR: {error_msg}")
            report_func({'ERROR'}, error_msg)
            return None
        
        return map_collection
    
    def _execute_conversion(self, item, maps, export_dir, base_name):
        """Execute the appropriate conversion strategy"""
        conversion_mode = item.texture_conversion_mode
        print(f"\nConversion mode: {conversion_mode}")
        
        strategy = self.strategies.get(conversion_mode)
        if strategy is None:
            raise ValueError(f"Unknown conversion mode: {conversion_mode}")
        
        strategy.convert(item, maps, export_dir, base_name)