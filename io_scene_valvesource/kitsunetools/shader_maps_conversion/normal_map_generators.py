import numpy as np

class BaseMapGenerator:
    """Base class for map generators"""
    
    def __init__(self, img_proc):
        self.img_proc = img_proc 
    
    def generate(self, maps, item) -> np.ndarray:
        """Generate the map - to be implemented by subclasses"""
        raise NotImplementedError


class NormalMapGenerator(BaseMapGenerator):
    """Generates normal maps with preprocessing"""
    
    def preprocess_normal(self, normal: np.ndarray, preprocess_flags: set) -> np.ndarray:
        """Apply preprocessing to normal map"""
        processed = normal[:, :, :3].copy()
        
        if 'RED' in preprocess_flags:
            processed[:, :, 2] = normal[:, :, 0]
            processed[:, :, 0] = normal[:, :, 3] if normal.shape[2] > 3 else 0.5
            processed[:, :, 1] = normal[:, :, 1]
        
        if 'INVERT_G' in preprocess_flags:
            processed[:, :, 1] = 1.0 - processed[:, :, 1]
        
        if 'FORCE_WHITE_B' in preprocess_flags:
            processed[:, :, 2] = 1.0
        
        return processed


class PBRNormalMapGenerator(NormalMapGenerator):
    """Generates PBR-style normal maps"""
    
    def generate(self, maps, item) -> np.ndarray:
        normal = maps.get('normal')
        height, width = normal.shape[:2]
        result = np.ones((height, width, 4), dtype=np.float32)
        
        processed_rgb = self.preprocess_normal(normal, item.normal_map_preprocess)
        result[:, :, :3] = processed_rgb
        result[:, :, 3] = 1.0
        
        return result


class PhongNormalMapGenerator(NormalMapGenerator):
    """Generates Phong-style normal maps with exponent in alpha"""
    
    def generate(self, maps, item) -> np.ndarray:
        normal = maps.get('normal_sized')
        metal = maps.get('metal_normal')
        roughness = maps.get('roughness_normal')
        
        height, width = normal.shape[:2]
        result = np.ones((height, width, 4), dtype=np.float32)
        
        processed_rgb = self.preprocess_normal(normal, item.normal_map_preprocess)
        result[:, :, :3] = processed_rgb
        
        metal_uninverted = 1.0 - metal if item.invert_metal_map else metal
        alpha_channel = self._create_exponent_alpha(
            roughness, metal, metal_uninverted,
            maps.get('diffuse'), item
        )
        result[:, :, 3] = alpha_channel
        
        return result
    
    def _create_exponent_alpha(self, roughness, metal, metal_uninverted, diffuse, item):
        """Create the exponent value for normal alpha channel"""
        rough_inverted = 1.0 - roughness
        rough_rgba = np.stack([rough_inverted]*3 + [np.ones_like(rough_inverted)], axis=2)
        
        exp_red_img = self.img_proc.brightness_contrast(rough_rgba, brightness=-100, contrast=0, legacy=True)
        metal_blend = np.stack([metal]*3 + [np.ones_like(metal)], axis=2)
        exp_red_img = self.img_proc.brightness_contrast(exp_red_img, brightness=1.5, legacy=True)
        exp_red_img = self.img_proc.multiply(exp_red_img, metal_blend, opacity=0.8)
        exp_red_img = self.img_proc.brightness_contrast(exp_red_img, brightness=150, legacy=False)
        
        alpha_channel = exp_red_img[:, :, 0]
        
        if item.adjust_for_albedoboost and item.albedoboost_factor > 0 and diffuse is not None:
            alpha_channel = self._apply_albedo_adjustment(
                alpha_channel, diffuse, metal_uninverted, item.albedoboost_factor
            )
        
        if item.phong_boost_influence > 0:
            alpha_channel = self._apply_phong_boost(alpha_channel, metal, item.phong_boost_influence)
        
        return alpha_channel
    
    def _apply_albedo_adjustment(self, alpha_channel, diffuse, metal_uninverted, albedo_factor):
        """Apply albedo-based adjustment to alpha channel"""
        from .texture_map_loader import TextureMapLoader
        
        height, width = alpha_channel.shape
        grayscale = np.mean(diffuse[:, :, :3], axis=2)
        
        if grayscale.shape != (height, width):
            loader = TextureMapLoader()
            grayscale = loader.resize_channel(grayscale, height, width)
        
        masked_grayscale = grayscale * metal_uninverted
        luminance_reducer = 1.0 - (masked_grayscale * albedo_factor)
        luminance_reducer = np.clip(luminance_reducer, 0.0, 1.0)
        
        return alpha_channel * luminance_reducer
    
    def _apply_phong_boost(self, alpha_channel, metal, boost_influence):
        """Apply phong boost using screen blend"""
        base_img = np.stack([alpha_channel, alpha_channel, alpha_channel], axis=-1)
        blend_img = np.stack([metal, metal, metal], axis=-1)
        screen_result = self.img_proc.screen(base_img, blend_img, opacity=boost_influence)
        return screen_result[:, :, 0]


class NPRNormalMapGenerator(NormalMapGenerator):
    """Generates NPR-style normal maps"""
    
    def generate(self, maps, item) -> np.ndarray:
        normal = maps.get('normal')
        height, width = normal.shape[:2]
        result = np.ones((height, width, 4), dtype=np.float32)
        
        processed_rgb = self.preprocess_normal(normal, item.normal_map_preprocess)
        result[:, :, :3] = processed_rgb
        
        if 'specular' in maps and maps.get('specular') is not None:
            result[:, :, 3] = maps.get('specular')
        elif 'alpha' in maps and maps.get('alpha') is not None:
            alpha_data = maps.get('alpha')
            if alpha_data.shape != (height, width):
                from .texture_map_loader import TextureMapLoader
                loader = TextureMapLoader()
                alpha_data = loader.resize_channel(alpha_data, height, width)
            result[:, :, 3] = alpha_data
        
        return result
