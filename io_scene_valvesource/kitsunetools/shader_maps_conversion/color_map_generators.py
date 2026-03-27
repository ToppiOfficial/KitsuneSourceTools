import numpy as np
from .normal_map_generators import BaseMapGenerator

class ColorMapGenerator(BaseMapGenerator):
    """Base class for color/diffuse map generators"""
    pass

class SpecularBaking():
    def _apply_specular_baking(self, result, maps, item):
        """Apply specular map baking"""
        specular = maps.get('specular')
        print(specular)
        if specular is None:
            return result
        
        blend_strength = item.specular_map_diffuse_baked / 100.0
        if blend_strength <= 0:
            return result
        
        diffuse_h, diffuse_w = result.shape[:2]
        spec_h, spec_w = specular.shape[:2]
        
        if (spec_h, spec_w) != (diffuse_h, diffuse_w):
            from .texture_map_loader import TextureMapLoader
            loader = TextureMapLoader()
            specular = loader.resize_channel(specular, diffuse_h, diffuse_w)
        
        specular_rgb = np.stack([specular]*3, axis=2)
        specular_rgba = np.dstack([specular_rgb, np.ones((diffuse_h, diffuse_w))])
        
        if item.specular_blend == 'COLOR_BURN':
            result = self.img_proc.color_burn(result, specular_rgba, opacity=blend_strength)
        else:
            result = self.img_proc.add(result, specular_rgba, opacity=blend_strength)
        
        return result


class PBRColorMapGenerator(ColorMapGenerator, SpecularBaking):
    """Generates PBR color maps"""
    
    def generate(self, maps, item) -> np.ndarray:
        diffuse = maps.get('diffuse')
        alpha = maps.get('alpha')
        
        result = diffuse.copy()
        result[:, :, 3] = alpha
        
        result = self._apply_specular_baking(result, maps, item)
        
        return result
    

class PhongDiffuseMapGenerator(ColorMapGenerator, SpecularBaking):
    """Generates Phong diffuse maps with AO and metal adjustments"""
    
    def generate(self, maps, item) -> np.ndarray:
        diffuse = maps.get('diffuse')
        metal = maps.get('metal_diffuse')
        ao = maps.get('ao_diffuse')
        alpha = maps.get('alpha')
        skin = maps.get('skin')
        
        result = diffuse.copy()
        
        result = self._apply_ao(result, ao, item.ambientocclu_strength)
        result = self._apply_metal_adjustments(result, metal, item)
        
        if skin is not None:
            result = self._apply_skin_adjustments(result, diffuse, skin, item)
        
        result = self._apply_specular_baking(result, maps, item)
        
        if item.color_alpha_mode != 'ALPHA':
            result[:, :, 3] = alpha
        
        return result
    
    def _apply_ao(self, result, ao, ao_strength):
        """Apply ambient occlusion"""
        ao_blend = np.stack([ao]*3 + [np.ones_like(ao)], axis=2)
        return self.img_proc.multiply(result, ao_blend, opacity=ao_strength / 100.0)
    
    def _apply_metal_adjustments(self, result, metal, item):
        """Apply metal-specific adjustments based on color_alpha_mode"""
        metal_mask = metal[:, :, np.newaxis]
        
        if item.color_alpha_mode == 'RGB_ALPHA':
            darkened = self.img_proc.brightness_contrast(
                result, brightness=-55 * item.metal_diffuse_mix, contrast=6, legacy=False
            )
            result = self.img_proc.apply_with_mask(result, darkened, metal_mask)
            saturated = self.img_proc.hue_saturation(result, saturation=20)
            result = self.img_proc.apply_with_mask(result, saturated, metal_mask)
        
        elif item.color_alpha_mode == 'ALPHA':
            result[:, :, 3] = metal
            contrasted = self.img_proc.brightness_contrast(result, brightness=0.0, contrast=10.0, legacy=True)
            result = self.img_proc.apply_with_mask(result, contrasted, metal_mask)
            saturated = self.img_proc.hue_saturation(result, saturation=25)
            result = self.img_proc.apply_with_mask(result, saturated, metal_mask)
        
        return result
    
    def _apply_skin_adjustments(self, result, diffuse, skin, item):
        """Apply skin map adjustments"""
        skin_mask = skin[:, :, np.newaxis]
        result[:, :, :3] = result[:, :, :3] * (1.0 - skin_mask) + diffuse[:, :, :3] * skin_mask
        
        if item.skin_map_gamma != 0:
            gamma_corrected = self.img_proc.exposure(result, exposure=0.0, gamma_correction=item.skin_map_gamma)
            result = self.img_proc.apply_with_mask(result, gamma_corrected, skin_mask)
        
        if item.skin_map_contrast != 0:
            contrasted = self.img_proc.brightness_contrast(result, brightness=0.0, contrast=item.skin_map_contrast, legacy=False)
            result = self.img_proc.apply_with_mask(result, contrasted, skin_mask)
        
        return result


class NPRColorMapGenerator(ColorMapGenerator, SpecularBaking):
    """Generates NPR color/diffuse maps"""
    
    def generate(self, maps, item) -> np.ndarray:
        diffuse = maps.get('diffuse')
        alpha = maps.get('alpha')
        ao = maps.get('ao')
        skin = maps.get('skin')
        
        result = diffuse.copy()
        diffuse_h, diffuse_w = diffuse.shape[:2]
        
        if ao is not None:
            ao_h, ao_w = ao.shape[:2]
            if (ao_h, ao_w) != (diffuse_h, diffuse_w):
                from .texture_map_loader import TextureMapLoader
                loader = TextureMapLoader()
                ao = loader.resize_channel(ao, diffuse_h, diffuse_w)
            
            ao_strength = getattr(item, 'ambientocclu_strength', 100.0)
            ao_blend = np.stack([ao]*3 + [np.ones_like(ao)], axis=2)
            result = self.img_proc.multiply(result, ao_blend, opacity=ao_strength / 100.0)

        if skin is not None:
            result = self._apply_skin_adjustments(result, diffuse, skin, item)

        result = self._apply_specular_baking(result, maps, item)

        if alpha is not None:
            result[:, :, 3] = alpha
        
        return result

    def _apply_skin_adjustments(self, result, diffuse, skin, item):
        """Apply skin map adjustments"""
        skin_mask = skin[:, :, np.newaxis]
        result[:, :, :3] = result[:, :, :3] * (1.0 - skin_mask) + diffuse[:, :, :3] * skin_mask
        
        if item.skin_map_gamma != 0:
            gamma_corrected = self.img_proc.exposure(result, exposure=0.0, gamma_correction=item.skin_map_gamma)
            result = self.img_proc.apply_with_mask(result, gamma_corrected, skin_mask)
        
        if item.skin_map_contrast != 0:
            contrasted = self.img_proc.brightness_contrast(result, brightness=0.0, contrast=item.skin_map_contrast, legacy=False)
            result = self.img_proc.apply_with_mask(result, contrasted, skin_mask)
        
        return result