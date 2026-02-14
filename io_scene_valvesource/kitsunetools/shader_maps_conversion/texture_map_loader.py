import numpy as np
from PIL import Image
import bpy

class TextureMapLoader:
    """Handles loading and preprocessing of texture maps"""
    
    def __init__(self):
        self._default_images = {
            "flat_normal": ([0.5, 0.5, 1.0, 1.0], False),
            "flat_rmao": ([1.0, 0.0, 1.0, 1.0], False),
            "flat_alpha": ([1.0, 1.0, 1.0, 1.0], False),
            "flat_specular": ([0.0, 0.0, 0.0, 1.0], False),
        }
    
    def ensure_default_images(self):
        """Create default fallback images if they don't exist"""
        for name, (pixel_values, _) in self._default_images.items():
            if name not in bpy.data.images:
                img = bpy.data.images.new(name, width=32, height=32, alpha=False)
                pixels = pixel_values * (32 * 32)
                img.pixels = pixels
                img.use_fake_user = True
                img.pack()
        bpy.context.view_layer.update()
    
    def load_image_data(self, img_name: str) -> np.ndarray:
        """Load full RGBA image data from Blender image"""
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
    
    def load_channel(self, img_name: str, channel: str) -> np.ndarray:
        """Load a single channel from an image"""
        if not img_name or img_name not in bpy.data.images:
            return None
        
        img = bpy.data.images[img_name]
        original_colorspace = img.colorspace_settings.name
        img.colorspace_settings.name = 'Non-Color'
        
        w, h = img.size
        pixels = np.array(img.pixels[:]).reshape((h, w, img.channels))
        
        img.colorspace_settings.name = original_colorspace
        
        channel_map = {'R': 0, 'G': 1, 'B': 2, 'A': 3, 'GREY': None}
        ch_idx = channel_map.get(channel)
        
        if ch_idx is not None:
            if ch_idx < img.channels:
                return pixels[:, :, ch_idx]
            elif ch_idx == 3:
                return np.ones((h, w))
            else:
                return pixels[:, :, 0]
        else:
            return np.mean(pixels[:, :, :3], axis=2)
    
    def resize_channel(self, data: np.ndarray, new_height: int, new_width: int) -> np.ndarray:
        """Resize a single channel using PIL"""
        data_uint8 = (np.clip(data, 0, 1) * 255).astype(np.uint8)
        pil_img = Image.fromarray(data_uint8, mode='L')
        resized = pil_img.resize((new_width, new_height), Image.BILINEAR)
        return np.array(resized).astype(np.float32) / 255.0
    
    def resize_image(self, data: np.ndarray, target_height: int, target_width: int) -> np.ndarray:
        """Resize multi-channel image"""
        if data is None:
            return None
        
        current_h, current_w = data.shape[:2]
        if (current_h, current_w) == (target_height, target_width):
            return data
        
        if len(data.shape) == 3:
            resized_channels = []
            for ch in range(data.shape[2]):
                resized_channels.append(self.resize_channel(data[:, :, ch], target_height, target_width))
            return np.stack(resized_channels, axis=2)
        else:
            return self.resize_channel(data, target_height, target_width)
    
    def load_and_prep_channel(self, img_name: str, channel: str, target_h: int, 
                              target_w: int, invert: bool) -> np.ndarray:
        """Load, resize, and optionally invert a channel"""
        data = self.load_channel(img_name, channel)
        if data is None:
            return None
        
        if target_h > 0 and target_w > 0:
            data = self.resize_image(data, target_h, target_w)
        
        if invert:
            data = 1.0 - data
        
        return data
