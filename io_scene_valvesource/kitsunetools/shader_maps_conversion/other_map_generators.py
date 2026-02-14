import numpy as np
from .normal_map_generators import BaseMapGenerator

class MRAOMapGenerator(BaseMapGenerator):
    """Generates Metal-Roughness-AO maps for PBR"""
    
    def generate(self, maps, item) -> np.ndarray:
        metal = maps.get('metal_sized')
        roughness = maps.get('roughness_sized')
        ao = maps.get('ao_sized')
        
        height, width = metal.shape
        mrao = np.ones((height, width, 4), dtype=np.float32)
        mrao[:, :, 0] = metal
        mrao[:, :, 1] = roughness
        mrao[:, :, 2] = ao
        return mrao


class ExponentMapGenerator(BaseMapGenerator):
    """Generates exponent maps for Phong shading"""
    
    def generate(self, maps, item) -> np.ndarray:
        roughness = maps.get('roughness')
        metal = maps.get('metal')
        
        height, width = roughness.shape
        exponent = np.ones((height, width, 4))
        
        rough_inverted = 1.0 - roughness
        
        exponent_red = self.img_proc.brightness_contrast(
            np.stack([rough_inverted]*3 + [np.ones_like(rough_inverted)], axis=2),
            brightness=-100
        )[:, :, 0]
        
        if item.phong_exponent_influence > 0:
            base_img = np.stack([exponent_red, exponent_red, exponent_red], axis=-1)
            blend_img = np.stack([metal, metal, metal], axis=-1)
            screen_result = self.img_proc.screen(base_img, blend_img, opacity=item.phong_exponent_influence)
            exponent_red = screen_result[:, :, 0]
        
        exponent[:, :, 0] = exponent_red
        exponent[:, :, 1] = metal * 0.5
        exponent[:, :, 2] = 0.0
        exponent[:, :, 3] = 1.0
        
        return exponent


class EmissiveMapGenerator(BaseMapGenerator):
    """Generates emissive maps"""
    
    def generate(self, maps, item) -> np.ndarray:
        if 'emissive' not in maps:
            return None
        
        emissive = maps.get('emissive')
        
        if item.emissive_map_ch == "COLOR":
            return emissive
        
        if len(emissive.shape) == 2:
            height, width = emissive.shape
            emissive_map = np.ones((height, width, 4), dtype=np.float32)
            emissive_map[:, :, 0] = emissive
            emissive_map[:, :, 1] = emissive
            emissive_map[:, :, 2] = emissive
            return emissive_map
        
        return emissive


class PhongEmissiveMapGenerator(BaseMapGenerator):
    """Generates Phong-style emissive maps (multiplied with diffuse)"""
    
    def generate(self, maps, item) -> np.ndarray:
        if 'emissive' not in maps:
            return None
        
        emissive = maps.get('emissive')
        diffuse = maps.get('diffuse')
        
        if item.emissive_map_ch == "COLOR":
            return emissive
        
        emissive_4ch = np.stack([emissive]*3 + [np.ones_like(emissive)], axis=2)
        result = self.img_proc.multiply(diffuse, emissive_4ch, opacity=1.0)
        result[:, :, 3] = 1.0
        return result
