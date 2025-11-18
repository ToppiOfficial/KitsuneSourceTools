import numpy as np
from typing import Tuple, List

class ImageProcessor:
    """Image processing library with Photoshop-like adjustments"""
    
    @staticmethod
    def ensure_rgba(img: np.ndarray) -> np.ndarray:
        """Ensure image has 4 channels (RGBA)"""
        if img.shape[2] == 3:
            alpha = np.ones((img.shape[0], img.shape[1], 1), dtype=img.dtype)
            return np.concatenate([img, alpha], axis=2)
        return img
    
    @staticmethod
    def brightness_contrast(img: np.ndarray, brightness: float = 0.0, contrast: float = 0.0, 
                        legacy: bool = True) -> np.ndarray:
        """
        Adjust brightness and contrast
        Args:
            img: Input image (H, W, C)
            brightness: -100 to 100 if legacy, -150 to 150 if not
            contrast: -100 to 100 (both modes)
            legacy: Use Photoshop legacy algorithm
        """
        result = img.copy()
        rgb = result[:, :, :3]
        
        if legacy:
            if brightness != 0:
                brightness_factor = brightness / 255.0
                rgb = np.clip(rgb + brightness_factor, 0.0, 1.0)
            
            if contrast != 0:
                contrast_val = contrast * 2.55
                factor = (259 * (contrast_val + 255)) / (255 * (259 - contrast_val))
                rgb = np.clip(factor * (rgb - 0.5) + 0.5, 0.0, 1.0)
        else:  # non-legacy mode
            if brightness != 0:
                # Brightness works like gamma/midtone adjustment
                brightness_factor = 1.0 + brightness / 100.0
                rgb = np.clip(rgb * brightness_factor, 0.0, 1.0)
            
            if contrast != 0:
                # Non-legacy contrast: S-curve that preserves endpoints
                # and has a brightness-preserving property
                # Contrast range: -100 to 100
                if contrast > 0:
                    # Positive contrast: expand around midpoint with preservation
                    factor = np.tan((contrast / 100.0) * np.pi / 4.0)
                    rgb = 0.5 + (rgb - 0.5) * (1.0 + factor)
                else:
                    # Negative contrast: compress toward midpoint
                    factor = 1.0 + contrast / 100.0
                    rgb = 0.5 + (rgb - 0.5) * factor
                
                rgb = np.clip(rgb, 0.0, 1.0)
        
        result[:, :, :3] = rgb
        return result
    
    @staticmethod
    def levels(img: np.ndarray, input_black: float = 0.0, input_white: float = 255.0,
              gamma: float = 1.0, output_black: float = 0.0, output_white: float = 255.0) -> np.ndarray:
        """
        Apply levels adjustment
        Args:
            input_black, input_white: 0-255 range
            gamma: 0.1-10.0 (1.0 = no change)
            output_black, output_white: 0-255 range
        """
        result = img.copy()
        rgb = result[:, :, :3]
        
        in_black = input_black / 255.0
        in_white = input_white / 255.0
        out_black = output_black / 255.0
        out_white = output_white / 255.0
        
        rgb = np.clip((rgb - in_black) / (in_white - in_black), 0.0, 1.0)
        
        if gamma != 1.0:
            rgb = np.power(rgb, 1.0 / gamma)
        
        rgb = rgb * (out_white - out_black) + out_black
        rgb = np.clip(rgb, 0.0, 1.0)
        
        result[:, :, :3] = rgb
        return result
    
    @staticmethod
    def curves(img: np.ndarray, points: List[Tuple[float, float]]) -> np.ndarray:
        """
        Apply curve adjustment
        Args:
            img: Input image
            points: List of (input, output) points, values 0-255
        """
        result = img.copy()
        rgb = result[:, :, :3]
        
        points_array = np.array(points)
        input_vals = points_array[:, 0] / 255.0
        output_vals = points_array[:, 1] / 255.0
        
        for i in range(3):
            rgb[:, :, i] = np.interp(rgb[:, :, i], input_vals, output_vals)
        
        result[:, :, :3] = np.clip(rgb, 0.0, 1.0)
        return result
    
    @staticmethod
    def exposure(img: np.ndarray, exposure: float = 0.0, offset: float = 0.0, 
                gamma_correction: float = 1.0) -> np.ndarray:
        """
        Apply exposure adjustment
        Args:
            exposure: -20 to 20 (stops)
            offset: -0.5 to 0.5
            gamma_correction: 0.01 to 10
        """
        result = img.copy()
        rgb = result[:, :, :3]
        
        rgb = rgb * np.power(2.0, exposure)
        
        rgb = rgb + offset
        
        if gamma_correction != 1.0:
            rgb = np.power(np.clip(rgb, 0.0, 1.0), 1.0 / gamma_correction)
        
        result[:, :, :3] = np.clip(rgb, 0.0, 1.0)
        return result
        
    @staticmethod
    def vibrance(img: np.ndarray, vibrance: float = 0.0, saturation: float = 0.0) -> np.ndarray:
        """
        Adjust vibrance and saturation
        Args:
            vibrance: -100 to 100
            saturation: -100 to 100
        """
        result = img.copy()
        rgb = result[:, :, :3]
        
        gray = np.mean(rgb, axis=2, keepdims=True)
        
        if saturation != 0:
            sat_factor = (saturation + 100) / 100.0
            rgb = gray + (rgb - gray) * sat_factor
        
        if vibrance != 0:
            vib_factor = vibrance / 100.0
            avg = np.mean(rgb, axis=2, keepdims=True)
            mx = np.max(rgb, axis=2, keepdims=True)
            amt = (mx - avg) * vib_factor * 2.0
            rgb = rgb + (rgb - gray) * amt
        
        result[:, :, :3] = np.clip(rgb, 0.0, 1.0)
        return result
    
    @staticmethod
    def hue_saturation(img: np.ndarray, hue: float = 0.0, saturation: float = 0.0, 
                      lightness: float = 0.0) -> np.ndarray:
        """
        Adjust hue, saturation, and lightness
        Args:
            hue: -180 to 180 degrees
            saturation: -100 to 100
            lightness: -100 to 100
        """
        result = img.copy()
        rgb = result[:, :, :3]
        
        hsv = ImageProcessor._rgb_to_hsv(rgb)
        
        if hue != 0:
            hsv[:, :, 0] = (hsv[:, :, 0] + hue / 360.0) % 1.0
        
        if saturation != 0:
            sat_factor = (saturation + 100) / 100.0
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * sat_factor, 0.0, 1.0)
        
        if lightness != 0:
            light_factor = lightness / 100.0
            hsv[:, :, 2] = np.clip(hsv[:, :, 2] + light_factor, 0.0, 1.0)
        
        rgb = ImageProcessor._hsv_to_rgb(hsv)
        result[:, :, :3] = rgb
        return result
    
    @staticmethod
    def color_balance(img: np.ndarray, 
                     shadows: Tuple[float, float, float] = (0, 0, 0),
                     midtones: Tuple[float, float, float] = (0, 0, 0),
                     highlights: Tuple[float, float, float] = (0, 0, 0),
                     preserve_luminosity: bool = True) -> np.ndarray:
        """
        Adjust color balance
        Args:
            shadows/midtones/highlights: (cyan-red, magenta-green, yellow-blue) -100 to 100 each
            preserve_luminosity: Maintain brightness
        """
        result = img.copy()
        rgb = result[:, :, :3]
        
        luminance = np.mean(rgb, axis=2, keepdims=True) if preserve_luminosity else None
        
        shadows_mask = 1.0 - np.clip(np.mean(rgb, axis=2, keepdims=True) * 2.0, 0.0, 1.0)
        highlights_mask = np.clip((np.mean(rgb, axis=2, keepdims=True) - 0.5) * 2.0, 0.0, 1.0)
        midtones_mask = 1.0 - shadows_mask - highlights_mask
        
        adjustment = np.zeros_like(rgb)
        adjustment += shadows_mask * np.array(shadows) / 100.0
        adjustment += midtones_mask * np.array(midtones) / 100.0
        adjustment += highlights_mask * np.array(highlights) / 100.0
        
        rgb = rgb + adjustment
        
        if preserve_luminosity:
            current_lum = np.mean(rgb, axis=2, keepdims=True)
            rgb = rgb * (luminance / (current_lum + 1e-7))
        
        result[:, :, :3] = np.clip(rgb, 0.0, 1.0)
        return result
    
    @staticmethod
    def invert(img: np.ndarray) -> np.ndarray:
        """Invert colors (preserves alpha)"""
        result = img.copy()
        result[:, :, :3] = 1.0 - result[:, :, :3]
        return result
    
    @staticmethod
    def posterize(img: np.ndarray, levels: int = 4) -> np.ndarray:
        """
        Posterize image
        Args:
            levels: 2-255 (number of tonal levels per channel)
        """
        result = img.copy()
        rgb = result[:, :, :3]
        
        levels = np.clip(levels, 2, 255)
        rgb = np.floor(rgb * levels) / (levels - 1)
        
        result[:, :, :3] = np.clip(rgb, 0.0, 1.0)
        return result
    
    @staticmethod
    def threshold(img: np.ndarray, threshold: float = 128.0) -> np.ndarray:
        """
        Apply threshold (0-255)
        """
        result = img.copy()
        rgb = result[:, :, :3]
        
        threshold_norm = threshold / 255.0
        rgb = (rgb > threshold_norm).astype(np.float32)
        
        result[:, :, :3] = rgb
        return result
    
    @staticmethod
    def desaturate(img: np.ndarray) -> np.ndarray:
        """Convert to grayscale"""
        result = img.copy()
        rgb = result[:, :, :3]
        
        gray = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
        result[:, :, :3] = gray[:, :, np.newaxis]
        
        return result
    
    @staticmethod
    def add(src: np.ndarray, blend: np.ndarray, opacity: float = 1.0) -> np.ndarray:
        """
        Add blend mode
        Args:
            opacity: 0.0-1.0
        """
        result = src.copy()
        rgb_src = result[:, :, :3]
        rgb_blend = blend[:, :, :3]
        
        blended = np.clip(rgb_src + rgb_blend, 0.0, 1.0)
        result[:, :, :3] = rgb_src * (1.0 - opacity) + blended * opacity
        
        return result
    
    @staticmethod
    def subtract(src: np.ndarray, blend: np.ndarray, opacity: float = 1.0) -> np.ndarray:
        """Subtract blend mode"""
        result = src.copy()
        rgb_src = result[:, :, :3]
        rgb_blend = blend[:, :, :3]
        
        blended = np.clip(rgb_src - rgb_blend, 0.0, 1.0)
        result[:, :, :3] = rgb_src * (1.0 - opacity) + blended * opacity
        
        return result
    
    @staticmethod
    def multiply(src: np.ndarray, blend: np.ndarray, opacity: float = 1.0) -> np.ndarray:
        """Multiply blend mode"""
        result = src.copy()
        rgb_src = result[:, :, :3]
        rgb_blend = blend[:, :, :3]
        
        blended = rgb_src * rgb_blend
        result[:, :, :3] = rgb_src * (1.0 - opacity) + blended * opacity
        
        return result
    
    @staticmethod
    def divide(src: np.ndarray, blend: np.ndarray, opacity: float = 1.0) -> np.ndarray:
        """Divide blend mode"""
        result = src.copy()
        rgb_src = result[:, :, :3]
        rgb_blend = blend[:, :, :3]
        
        blended = np.clip(rgb_src / (rgb_blend + 1e-7), 0.0, 1.0)
        result[:, :, :3] = rgb_src * (1.0 - opacity) + blended * opacity
        
        return result
    
    @staticmethod
    def screen(src: np.ndarray, blend: np.ndarray, opacity: float = 1.0) -> np.ndarray:
        """Screen blend mode"""
        result = src.copy()
        rgb_src = result[:, :, :3]
        rgb_blend = blend[:, :, :3]
        
        blended = 1.0 - (1.0 - rgb_src) * (1.0 - rgb_blend)
        result[:, :, :3] = rgb_src * (1.0 - opacity) + blended * opacity
        
        return result
    
    @staticmethod
    def overlay(src: np.ndarray, blend: np.ndarray, opacity: float = 1.0) -> np.ndarray:
        """Overlay blend mode"""
        result = src.copy()
        rgb_src = result[:, :, :3]
        rgb_blend = blend[:, :, :3]
        
        blended = np.where(
            rgb_src < 0.5,
            2.0 * rgb_src * rgb_blend,
            1.0 - 2.0 * (1.0 - rgb_src) * (1.0 - rgb_blend)
        )
        
        result[:, :, :3] = rgb_src * (1.0 - opacity) + blended * opacity
        return result
    
    @staticmethod
    def _rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:
        """Convert RGB to HSV"""
        r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
        
        maxc = np.maximum(np.maximum(r, g), b)
        minc = np.minimum(np.minimum(r, g), b)
        v = maxc
        
        delta = maxc - minc
        s = np.divide(delta, maxc, out=np.zeros_like(maxc), where=maxc != 0)
        
        h = np.zeros_like(maxc)
        
        mask_r = (maxc == r) & (delta != 0)
        mask_g = (maxc == g) & (delta != 0)
        mask_b = (maxc == b) & (delta != 0)
        
        h[mask_r] = ((g[mask_r] - b[mask_r]) / delta[mask_r]) % 6
        h[mask_g] = ((b[mask_g] - r[mask_g]) / delta[mask_g]) + 2
        h[mask_b] = ((r[mask_b] - g[mask_b]) / delta[mask_b]) + 4
        
        h = h / 6.0
        
        return np.stack([h, s, v], axis=2)
    
    @staticmethod
    def _hsv_to_rgb(hsv: np.ndarray) -> np.ndarray:
        """Convert HSV to RGB"""
        h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        
        h = h * 6.0
        i = np.floor(h).astype(int)
        f = h - i
        
        p = v * (1.0 - s)
        q = v * (1.0 - s * f)
        t = v * (1.0 - s * (1.0 - f))
        
        i = i % 6
        
        rgb = np.zeros_like(hsv)
        
        mask0 = (i == 0)
        mask1 = (i == 1)
        mask2 = (i == 2)
        mask3 = (i == 3)
        mask4 = (i == 4)
        mask5 = (i == 5)
        
        rgb[mask0] = np.stack([v[mask0], t[mask0], p[mask0]], axis=1)
        rgb[mask1] = np.stack([q[mask1], v[mask1], p[mask1]], axis=1)
        rgb[mask2] = np.stack([p[mask2], v[mask2], t[mask2]], axis=1)
        rgb[mask3] = np.stack([p[mask3], q[mask3], v[mask3]], axis=1)
        rgb[mask4] = np.stack([t[mask4], p[mask4], v[mask4]], axis=1)
        rgb[mask5] = np.stack([v[mask5], p[mask5], q[mask5]], axis=1)
        
        return np.clip(rgb, 0.0, 1.0)
    
    @staticmethod
    def apply_with_mask(original: np.ndarray, adjusted: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """
        Apply an adjustment using a mask
        Args:
            original: Original image (H, W, C)
            adjusted: Adjusted image (H, W, C)
            mask: Grayscale mask (H, W) or (H, W, 1) or (H, W, C) where white = 100% effect, black = 0% effect
        Returns:
            Blended result based on mask
        """
        result = original.copy()
        
        if len(mask.shape) == 2:
            mask_normalized = mask[:, :, np.newaxis]
        elif mask.shape[2] == 1:
            mask_normalized = mask
        else:
            mask_normalized = np.mean(mask[:, :, :3], axis=2, keepdims=True)
        
        result[:, :, :3] = original[:, :, :3] * (1.0 - mask_normalized) + adjusted[:, :, :3] * mask_normalized
        
        return result

    @staticmethod
    def create_mask_from_luminosity(img: np.ndarray, invert: bool = False) -> np.ndarray:
        """
        Create a mask from image luminosity
        Args:
            img: Input image
            invert: If True, dark areas become white in mask
        Returns:
            Grayscale mask (H, W, 1)
        """
        rgb = img[:, :, :3]
        luminosity = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
        
        if invert:
            luminosity = 1.0 - luminosity
        
        return luminosity[:, :, np.newaxis]

    @staticmethod
    def create_mask_from_channel(img: np.ndarray, channel: int = 0) -> np.ndarray:
        """
        Create a mask from a specific channel
        Args:
            img: Input image
            channel: 0=Red, 1=Green, 2=Blue, 3=Alpha
        Returns:
            Grayscale mask (H, W, 1)
        """
        if channel < img.shape[2]:
            return img[:, :, channel:channel+1].copy()
        return np.ones((img.shape[0], img.shape[1], 1), dtype=np.float32)

    @staticmethod
    def create_mask_from_range(img: np.ndarray, min_val: float = 0.0, max_val: float = 1.0, 
                            feather: float = 0.0) -> np.ndarray:
        """
        Create a mask based on luminosity range
        Args:
            img: Input image
            min_val: Minimum luminosity (0-1)
            max_val: Maximum luminosity (0-1)
            feather: Softness of edges (0-0.5)
        Returns:
            Grayscale mask (H, W, 1)
        """
        rgb = img[:, :, :3]
        luminosity = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
        
        if feather > 0:
            lower_feather = min_val + feather
            upper_feather = max_val - feather
            
            mask = np.where(
                luminosity < min_val, 0.0,
                np.where(
                    luminosity < lower_feather, (luminosity - min_val) / feather,
                    np.where(
                        luminosity < upper_feather, 1.0,
                        np.where(
                            luminosity < max_val, (max_val - luminosity) / feather,
                            0.0
                        )
                    )
                )
            )
        else:
            mask = np.where((luminosity >= min_val) & (luminosity <= max_val), 1.0, 0.0)
        
        return mask[:, :, np.newaxis]