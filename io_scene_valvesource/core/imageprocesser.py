import numpy as np
from typing import Tuple, List
from PIL import Image, ImageOps, ImageChops, ImageEnhance

class ImageProcessor:
    _LUMA_COEFFS = np.array([0.299, 0.587, 0.114], dtype=np.float32)

    @staticmethod
    def _to_pil(img: np.ndarray) -> Image.Image:
        """Convert numpy array to PIL Image"""
        img_uint8 = (np.clip(img, 0, 1) * 255).astype(np.uint8)
        img_uint8 = np.flipud(img_uint8)
        if img.shape[2] == 4:
            return Image.fromarray(img_uint8, 'RGBA')
        else:
            return Image.fromarray(img_uint8[:, :, :3], 'RGB')
    
    @staticmethod
    def _from_pil(pil_img: Image.Image, original_shape: tuple) -> np.ndarray:
        """Convert PIL Image back to numpy array"""
        arr = np.array(pil_img).astype(np.float32) / 255.0
        arr = np.flipud(arr)
        if len(original_shape) == 3 and original_shape[2] == 4 and arr.ndim == 3 and arr.shape[2] == 3:
            alpha = np.ones((arr.shape[0], arr.shape[1], 1), dtype=np.float32)
            arr = np.concatenate([arr, alpha], axis=2)
        elif arr.ndim == 2:
            arr = np.stack([arr, arr, arr, np.ones_like(arr)], axis=2)
        return arr

    @staticmethod
    def ensure_rgba(img: np.ndarray) -> np.ndarray:
        """Ensure image has 4 channels (RGBA)"""
        if img.shape[2] == 3:
            alpha = np.ones(img.shape[:2] + (1,), dtype=img.dtype)
            return np.concatenate([img, alpha], axis=2)
        return img
    
    @staticmethod
    def brightness_contrast(img: np.ndarray, brightness: float = 0.0, contrast: float = 0.0, 
                            legacy: bool = True) -> np.ndarray:
        """Adjust brightness and contrast"""
        if not legacy and brightness == 0 and contrast != 0:
            original_shape = img.shape
            pil_img = ImageProcessor._to_pil(img)
            factor = 1.0 + contrast / 100.0
            enhanced = ImageEnhance.Contrast(pil_img).enhance(max(0, factor))
            result = ImageProcessor._from_pil(enhanced, original_shape)
            result[:, :, 3] = img[:, :, 3]
            return result
        
        result = img.copy()
        rgb = result[:, :, :3]
        
        if legacy:
            if brightness != 0:
                rgb += (brightness / 255.0)
                np.clip(rgb, 0.0, 1.0, out=rgb)
            
            if contrast != 0:
                c_val = contrast * 2.55
                factor = (259 * (c_val + 255)) / (255 * (259 - c_val))
                rgb -= 0.5
                rgb *= factor
                rgb += 0.5
                np.clip(rgb, 0.0, 1.0, out=rgb)
        else:
            if brightness != 0:
                rgb *= (1.0 + brightness / 100.0)
                np.clip(rgb, 0.0, 1.0, out=rgb)
            
            if contrast != 0:
                if contrast > 0:
                    factor = np.tan((contrast / 100.0) * np.pi / 4.0) + 1.0
                    rgb -= 0.5
                    rgb *= factor
                    rgb += 0.5
                else:
                    factor = 1.0 + contrast / 100.0
                    rgb -= 0.5
                    rgb *= factor
                    rgb += 0.5
                np.clip(rgb, 0.0, 1.0, out=rgb)
        
        result[:, :, :3] = rgb
        return result
    
    @staticmethod
    def levels(img: np.ndarray, input_black: float = 0.0, input_white: float = 255.0,
               gamma: float = 1.0, output_black: float = 0.0, output_white: float = 255.0) -> np.ndarray:
        """Apply levels adjustment"""
        result = img.copy()
        rgb = result[:, :, :3]
        
        in_black_n = input_black / 255.0
        in_diff = (input_white / 255.0) - in_black_n
        out_black_n = output_black / 255.0
        out_diff = (output_white / 255.0) - out_black_n
        
        if in_diff == 0: in_diff = 1e-6
        
        rgb -= in_black_n
        rgb /= in_diff
        np.clip(rgb, 0.0, 1.0, out=rgb)
        
        if gamma != 1.0:
            np.power(rgb, 1.0 / gamma, out=rgb)
        
        rgb *= out_diff
        rgb += out_black_n
        np.clip(rgb, 0.0, 1.0, out=rgb)
        
        result[:, :, :3] = rgb
        return result
    
    @staticmethod
    def curves(img: np.ndarray, points: List[Tuple[float, float]]) -> np.ndarray:
        """Apply curve adjustment"""
        result = img.copy()
        rgb = result[:, :, :3]
        
        pts = np.array(points)
        xp = pts[:, 0] / 255.0
        fp = pts[:, 1] / 255.0
        
        for i in range(3):
            rgb[:, :, i] = np.interp(rgb[:, :, i], xp, fp)
        
        np.clip(rgb, 0.0, 1.0, out=rgb)
        result[:, :, :3] = rgb
        return result
    
    @staticmethod
    def exposure(img: np.ndarray, exposure: float = 0.0, offset: float = 0.0, 
                 gamma_correction: float = 1.0) -> np.ndarray:
        """Apply exposure adjustment"""
        result = img.copy()
        rgb = result[:, :, :3]
        
        if exposure != 0:
            rgb *= (2.0 ** exposure)
        
        if offset != 0:
            rgb += offset
        
        if gamma_correction != 1.0:
            np.clip(rgb, 0.0, 1.0, out=rgb)
            np.power(rgb, 1.0 / gamma_correction, out=rgb)
        
        np.clip(rgb, 0.0, 1.0, out=rgb)
        result[:, :, :3] = rgb
        return result
        
    @staticmethod
    def vibrance(img: np.ndarray, vibrance: float = 0.0, saturation: float = 0.0) -> np.ndarray:
        """Adjust vibrance and saturation"""
        if vibrance == 0 and saturation != 0:
            original_shape = img.shape
            pil_img = ImageProcessor._to_pil(img)
            factor = 1.0 + saturation / 100.0
            enhanced = ImageEnhance.Color(pil_img).enhance(max(0, factor))
            result = ImageProcessor._from_pil(enhanced, original_shape)
            result[:, :, 3] = img[:, :, 3]
            return result
        
        result = img.copy()
        rgb = result[:, :, :3]
        
        gray = rgb.dot(ImageProcessor._LUMA_COEFFS)[..., np.newaxis]
        
        if saturation != 0:
            factor = (saturation + 100) / 100.0
            rgb = gray + (rgb - gray) * factor
        
        if vibrance != 0:
            vib_factor = vibrance / 100.0 * 2.0
            max_rgb = np.max(rgb, axis=2, keepdims=True)
            amt = (max_rgb - np.mean(rgb, axis=2, keepdims=True)) * vib_factor
            rgb += (rgb - gray) * amt
        
        np.clip(rgb, 0.0, 1.0, out=rgb)
        result[:, :, :3] = rgb
        return result
    
    @staticmethod
    def hue_saturation(img: np.ndarray, hue: float = 0.0, saturation: float = 0.0, 
                       lightness: float = 0.0) -> np.ndarray:
        """Adjust hue, saturation, and lightness"""
        if hue == 0 and lightness == 0 and saturation != 0:
            original_shape = img.shape
            pil_img = ImageProcessor._to_pil(img)
            factor = 1.0 + saturation / 100.0
            enhanced = ImageEnhance.Color(pil_img).enhance(max(0, factor))
            result = ImageProcessor._from_pil(enhanced, original_shape)
            result[:, :, 3] = img[:, :, 3]
            return result
        
        result = img.copy()
        rgb = result[:, :, :3]
        
        hsv = ImageProcessor._rgb_to_hsv(rgb)
        
        if hue != 0:
            hsv[:, :, 0] = (hsv[:, :, 0] + hue / 360.0) % 1.0
        
        if saturation != 0:
            hsv[:, :, 1] *= ((saturation + 100) / 100.0)
            np.clip(hsv[:, :, 1], 0.0, 1.0, out=hsv[:, :, 1])
        
        if lightness != 0:
            hsv[:, :, 2] += (lightness / 100.0)
            np.clip(hsv[:, :, 2], 0.0, 1.0, out=hsv[:, :, 2])
        
        rgb = ImageProcessor._hsv_to_rgb(hsv)
        result[:, :, :3] = rgb
        return result
    
    @staticmethod
    def color_balance(img: np.ndarray, 
                      shadows: Tuple[float, float, float] = (0, 0, 0),
                      midtones: Tuple[float, float, float] = (0, 0, 0),
                      highlights: Tuple[float, float, float] = (0, 0, 0),
                      preserve_luminosity: bool = True) -> np.ndarray:
        """Adjust color balance"""
        result = img.copy()
        rgb = result[:, :, :3]
        
        luma = rgb.dot(ImageProcessor._LUMA_COEFFS)[..., np.newaxis]
        
        s_mask = 1.0 - np.clip(luma * 2.0, 0.0, 1.0)
        h_mask = np.clip((luma - 0.5) * 2.0, 0.0, 1.0)
        m_mask = 1.0 - s_mask - h_mask
        
        adjust = (s_mask * np.array(shadows) + 
                  m_mask * np.array(midtones) + 
                  h_mask * np.array(highlights)) / 100.0
        
        rgb += adjust
        
        if preserve_luminosity:
            new_luma = rgb.dot(ImageProcessor._LUMA_COEFFS)[..., np.newaxis]
            rgb *= (luma / (new_luma + 1e-7))
        
        np.clip(rgb, 0.0, 1.0, out=rgb)
        result[:, :, :3] = rgb
        return result
    
    @staticmethod
    def invert(img: np.ndarray) -> np.ndarray:
        """Invert colors"""
        original_shape = img.shape
        pil_img = ImageProcessor._to_pil(img)
        if pil_img.mode == 'RGBA':
            r, g, b, a = pil_img.split()
            r = ImageOps.invert(r)
            g = ImageOps.invert(g)
            b = ImageOps.invert(b)
            inverted = Image.merge('RGBA', (r, g, b, a))
        else:
            inverted = ImageOps.invert(pil_img)
        return ImageProcessor._from_pil(inverted, original_shape)
    
    @staticmethod
    def posterize(img: np.ndarray, levels: int = 4) -> np.ndarray:
        """Posterize image"""
        original_shape = img.shape
        pil_img = ImageProcessor._to_pil(img)
        bits = max(1, int(np.log2(levels)))
        if pil_img.mode == 'RGBA':
            r, g, b, a = pil_img.split()
            r = ImageOps.posterize(r, bits)
            g = ImageOps.posterize(g, bits)
            b = ImageOps.posterize(b, bits)
            posterized = Image.merge('RGBA', (r, g, b, a))
        else:
            posterized = ImageOps.posterize(pil_img, bits)
        return ImageProcessor._from_pil(posterized, original_shape)
    
    @staticmethod
    def threshold(img: np.ndarray, threshold: float = 128.0) -> np.ndarray:
        """Apply threshold"""
        result = img.copy()
        rgb = result[:, :, :3]
        
        mask = rgb > (threshold / 255.0)
        result[:, :, :3] = mask.astype(np.float32)
        return result
    
    @staticmethod
    def desaturate(img: np.ndarray) -> np.ndarray:
        """Convert to grayscale"""
        original_shape = img.shape
        pil_img = ImageProcessor._to_pil(img)
        gray = pil_img.convert('L')
        gray_rgb = gray.convert('RGB' if original_shape[2] == 3 else 'RGBA')
        result = ImageProcessor._from_pil(gray_rgb, original_shape)
        if original_shape[2] == 4:
            result[:, :, 3] = img[:, :, 3]
        return result
    
    @staticmethod
    def add(src: np.ndarray, blend: np.ndarray, opacity: float = 1.0) -> np.ndarray:
        """Add blend mode"""
        if opacity == 1.0:
            original_shape = src.shape
            src_pil = ImageProcessor._to_pil(src)
            blend_pil = ImageProcessor._to_pil(blend)
            added = ImageChops.add(src_pil, blend_pil)
            return ImageProcessor._from_pil(added, original_shape)
        
        result = src.copy()
        rgb_s = result[:, :, :3]
        rgb_b = blend[:, :, :3]
        
        blended = np.add(rgb_s, rgb_b)
        np.clip(blended, 0.0, 1.0, out=blended)
        
        result[:, :, :3] = rgb_s * (1.0 - opacity) + blended * opacity
        return result
    
    @staticmethod
    def subtract(src: np.ndarray, blend: np.ndarray, opacity: float = 1.0) -> np.ndarray:
        """Subtract blend mode"""
        if opacity == 1.0:
            original_shape = src.shape
            src_pil = ImageProcessor._to_pil(src)
            blend_pil = ImageProcessor._to_pil(blend)
            subtracted = ImageChops.subtract(src_pil, blend_pil)
            return ImageProcessor._from_pil(subtracted, original_shape)
        
        result = src.copy()
        rgb_s = result[:, :, :3]
        rgb_b = blend[:, :, :3]
        
        blended = np.subtract(rgb_s, rgb_b)
        np.clip(blended, 0.0, 1.0, out=blended)
        
        result[:, :, :3] = rgb_s * (1.0 - opacity) + blended * opacity
        return result
    
    @staticmethod
    def multiply(src: np.ndarray, blend: np.ndarray, opacity: float = 1.0) -> np.ndarray:
        """Multiply blend mode"""
        if opacity == 1.0:
            original_shape = src.shape
            src_pil = ImageProcessor._to_pil(src)
            blend_pil = ImageProcessor._to_pil(blend)
            multiplied = ImageChops.multiply(src_pil, blend_pil)
            return ImageProcessor._from_pil(multiplied, original_shape)
        
        result = src.copy()
        rgb_s = result[:, :, :3]
        
        blended = np.multiply(rgb_s, blend[:, :, :3])
        
        result[:, :, :3] = rgb_s * (1.0 - opacity) + blended * opacity
        return result
    
    @staticmethod
    def divide(src: np.ndarray, blend: np.ndarray, opacity: float = 1.0) -> np.ndarray:
        """Divide blend mode"""
        result = src.copy()
        rgb_s = result[:, :, :3]
        
        blended = np.divide(rgb_s, blend[:, :, :3] + 1e-7)
        np.clip(blended, 0.0, 1.0, out=blended)
        
        if opacity != 1.0:
            result[:, :, :3] = rgb_s * (1.0 - opacity) + blended * opacity
        else:
            result[:, :, :3] = blended
        return result
    
    @staticmethod
    def screen(src: np.ndarray, blend: np.ndarray, opacity: float = 1.0) -> np.ndarray:
        """Screen blend mode"""
        if opacity == 1.0:
            original_shape = src.shape
            src_pil = ImageProcessor._to_pil(src)
            blend_pil = ImageProcessor._to_pil(blend)
            screened = ImageChops.screen(src_pil, blend_pil)
            return ImageProcessor._from_pil(screened, original_shape)
        
        result = src.copy()
        rgb_s = result[:, :, :3]
        rgb_b = blend[:, :, :3]
        
        blended = 1.0 - (1.0 - rgb_s) * (1.0 - rgb_b)
        
        result[:, :, :3] = rgb_s * (1.0 - opacity) + blended * opacity
        return result
    
    @staticmethod
    def overlay(src: np.ndarray, blend: np.ndarray, opacity: float = 1.0) -> np.ndarray:
        """Overlay blend mode"""
        result = src.copy()
        rgb_s = result[:, :, :3]
        rgb_b = blend[:, :, :3]
        
        mask = rgb_s < 0.5
        blended = np.empty_like(rgb_s)
        
        blended[mask] = 2.0 * rgb_s[mask] * rgb_b[mask]
        blended[~mask] = 1.0 - 2.0 * (1.0 - rgb_s[~mask]) * (1.0 - rgb_b[~mask])
        
        if opacity != 1.0:
            result[:, :, :3] = rgb_s * (1.0 - opacity) + blended * opacity
        else:
            result[:, :, :3] = blended
        return result
    
    @staticmethod
    def _rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:
        """Convert RGB to HSV"""
        r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
        
        maxc = np.maximum(np.maximum(r, g), b)
        minc = np.minimum(np.minimum(r, g), b)
        v = maxc
        
        delta = maxc - minc
        
        s = np.zeros_like(maxc)
        non_zero = maxc != 0
        s[non_zero] = delta[non_zero] / maxc[non_zero]
        
        h = np.zeros_like(maxc)
        delta_nz = delta != 0
        
        mask = (maxc == r) & delta_nz
        h[mask] = (g[mask] - b[mask]) / delta[mask]
        
        mask = (maxc == g) & delta_nz
        h[mask] = 2.0 + (b[mask] - r[mask]) / delta[mask]
        
        mask = (maxc == b) & delta_nz
        h[mask] = 4.0 + (r[mask] - g[mask]) / delta[mask]
        
        h = (h / 6.0) % 1.0
        return np.stack([h, s, v], axis=2)
    
    @staticmethod
    def _hsv_to_rgb(hsv: np.ndarray) -> np.ndarray:
        """Convert HSV to RGB"""
        h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        
        i = (h * 6.0).astype(int)
        f = (h * 6.0) - i
        p = v * (1.0 - s)
        q = v * (1.0 - s * f)
        t = v * (1.0 - s * (1.0 - f))
        
        i = i % 6
        
        rgb = np.zeros_like(hsv)
        
        conditions = [i == 0, i == 1, i == 2, i == 3, i == 4, i == 5]
        rgb[:, :, 0] = np.select(conditions, [v, q, p, p, t, v])
        rgb[:, :, 1] = np.select(conditions, [t, v, v, q, p, p])
        rgb[:, :, 2] = np.select(conditions, [p, p, t, v, v, q])
        
        return rgb
    
    @staticmethod
    def apply_with_mask(original: np.ndarray, adjusted: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Apply adjustment using mask"""
        result = original.copy()
        
        if mask.ndim == 2:
            m = mask[:, :, np.newaxis]
        elif mask.shape[2] == 1:
            m = mask
        else:
            m = mask.dot(ImageProcessor._LUMA_COEFFS)[..., np.newaxis]
            
        result[:, :, :3] = original[:, :, :3] * (1.0 - m) + adjusted[:, :, :3] * m
        return result

    @staticmethod
    def create_mask_from_luminosity(img: np.ndarray, invert: bool = False) -> np.ndarray:
        """Create mask from image luminosity"""
        lum = img[:, :, :3].dot(ImageProcessor._LUMA_COEFFS)
        if invert:
            lum = 1.0 - lum
        return lum[:, :, np.newaxis]

    @staticmethod
    def create_mask_from_channel(img: np.ndarray, channel: int = 0) -> np.ndarray:
        """Create mask from specific channel"""
        if channel < img.shape[2]:
            return img[:, :, channel:channel+1].copy()
        return np.ones(img.shape[:2] + (1,), dtype=np.float32)

    @staticmethod
    def create_mask_from_range(img: np.ndarray, min_val: float = 0.0, max_val: float = 1.0, 
                               feather: float = 0.0) -> np.ndarray:
        """Create mask based on luminosity range"""
        lum = img[:, :, :3].dot(ImageProcessor._LUMA_COEFFS)
        
        if feather > 0:
            low = min_val + feather
            high = max_val - feather
            
            mask = np.zeros_like(lum)
            
            mask[(lum >= low) & (lum <= high)] = 1.0
            
            l_feather = (lum >= min_val) & (lum < low)
            u_feather = (lum > high) & (lum <= max_val)
            
            if np.any(l_feather):
                mask[l_feather] = (lum[l_feather] - min_val) / feather
            if np.any(u_feather):
                mask[u_feather] = (max_val - lum[u_feather]) / feather
                
        else:
            mask = ((lum >= min_val) & (lum <= max_val)).astype(np.float32)
        
        return mask[:, :, np.newaxis]