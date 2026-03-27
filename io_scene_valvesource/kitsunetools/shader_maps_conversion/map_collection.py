import numpy as np

class MapCollection:
    """Collects and manages all texture maps for conversion"""
    
    def __init__(self, loader):
        self.loader = loader
        self.maps = {}
    
    def load_all(self, item, diffuse_height: int, diffuse_width: int) -> bool:
        """Load all required maps for an item"""
        print(f"\nLoading maps for '{item.name}'")
        
        print(f"  Loading diffuse: {item.diffuse_map}")
        self.maps['diffuse'] = self.loader.load_image_data(item.diffuse_map)
        
        print(f"  Loading normal: {item.normal_map}")
        self.maps['normal'] = self.loader.load_image_data(item.normal_map)
        
        if self.maps['diffuse'] is None or self.maps['normal'] is None:
            print("  ERROR: Failed to load diffuse or normal map")
            return False
        
        self._load_rma_maps(item)
        
        rma_height, rma_width = self._determine_rma_size()
        print(f"  Target size for RMA maps: {rma_height}x{rma_width}")
        
        self._resize_and_invert_rma(item, rma_height, rma_width)
        self._create_sized_variants(diffuse_height, diffuse_width, rma_height, rma_width)
        self._load_optional_maps(item, diffuse_height, diffuse_width)
        
        print("  All maps loaded successfully")
        return True
    
    def _load_rma_maps(self, item):
        """Load roughness, metal, and AO maps"""
        print(f"  Loading roughness: {item.roughness_map} (channel: {item.roughness_map_ch})")
        rough_raw = self.loader.load_channel(item.roughness_map, item.roughness_map_ch)
        
        print(f"  Loading metal: {item.metal_map} (channel: {item.metal_map_ch})")
        metal_raw = self.loader.load_channel(item.metal_map, item.metal_map_ch)
        
        print(f"  Loading AO: {item.ambientocclu_map} (channel: {item.ambientocclu_map_ch})")
        ao_raw = self.loader.load_channel(item.ambientocclu_map, item.ambientocclu_map_ch)
        
        if rough_raw is None or metal_raw is None or ao_raw is None:
            raise ValueError("Failed to load roughness, metal, or AO map")
        
        self.maps['roughness_raw'] = rough_raw
        self.maps['metal_raw'] = metal_raw
        self.maps['ao_raw'] = ao_raw
    
    def _determine_rma_size(self) -> tuple:
        """Determine the maximum size for RMA maps"""
        max_h = max(
            self.maps['roughness_raw'].shape[0],
            self.maps['metal_raw'].shape[0],
            self.maps['ao_raw'].shape[0],
            self.maps['normal'].shape[0]
        )
        max_w = max(
            self.maps['roughness_raw'].shape[1],
            self.maps['metal_raw'].shape[1],
            self.maps['ao_raw'].shape[1],
            self.maps['normal'].shape[1]
        )
        return max_h, max_w
    
    def _resize_and_invert_rma(self, item, target_h: int, target_w: int):
        """Resize RMA maps to target size and apply inversions"""
        print("  Resizing roughness, metal, AO to target size...")
        self.maps['roughness'] = self.loader.resize_image(self.maps['roughness_raw'], target_h, target_w)
        self.maps['metal'] = self.loader.resize_image(self.maps['metal_raw'], target_h, target_w)
        self.maps['ao'] = self.loader.resize_image(self.maps['ao_raw'], target_h, target_w)
        
        print("  Applying inversions...")
        if item.invert_roughness_map:
            print("    Inverting roughness")
            self.maps['roughness'] = 1.0 - self.maps['roughness']
        if item.invert_metal_map:
            print("    Inverting metal")
            self.maps['metal'] = 1.0 - self.maps['metal']
        if item.invert_ambientocclu_map:
            print("    Inverting AO")
            self.maps['ao'] = 1.0 - self.maps['ao']
    
    def _create_sized_variants(self, diffuse_h: int, diffuse_w: int, rma_h: int, rma_w: int):
        """Create different sized variants for different uses"""
        print("  Creating sized variants...")
        
        self.maps['roughness_sized'] = self.loader.resize_image(self.maps['roughness'], rma_h, rma_w)
        self.maps['metal_sized'] = self.loader.resize_image(self.maps['metal'], rma_h, rma_w)
        self.maps['ao_sized'] = self.loader.resize_image(self.maps['ao'], rma_h, rma_w)
        
        print(f"  Creating diffuse-sized variants ({diffuse_h}x{diffuse_w})...")
        self.maps['metal_diffuse'] = self.loader.resize_image(self.maps['metal'], diffuse_h, diffuse_w)
        self.maps['ao_diffuse'] = self.loader.resize_image(self.maps['ao'], diffuse_h, diffuse_w)
        
        print(f"  Creating normal-sized variants ({rma_h}x{rma_w})...")
        self.maps['metal_normal'] = self.loader.resize_image(self.maps['metal'], rma_h, rma_w)
        self.maps['roughness_normal'] = self.loader.resize_image(self.maps['roughness'], rma_h, rma_w)
        self.maps['normal_sized'] = self.loader.resize_image(self.maps['normal'], rma_h, rma_w)
    
    def _load_optional_maps(self, item, diffuse_h: int, diffuse_w: int):
        """Load optional maps like alpha, skin, specular, and emissive"""
        print(f"  Loading alpha: {item.alpha_map} (channel: {item.alpha_map_ch})")
        self.maps['alpha'] = self.loader.load_and_prep_channel(
            item.alpha_map, item.alpha_map_ch,
            diffuse_h, diffuse_w, item.invert_alpha_map
        )
        if item.invert_alpha_map:
            print("    Inverting alpha")
        
        if item.skin_map and item.skin_map != "":
            print(f"  Loading skin: {item.skin_map} (channel: {item.skin_map_ch})")
            self.maps['skin'] = self.loader.load_and_prep_channel(
                item.skin_map, item.skin_map_ch,
                diffuse_h, diffuse_w, item.invert_skin_map
            )
            if item.invert_skin_map:
                print("    Inverting skin")
        
        if item.specular_map and item.specular_map != "":
            print(f"  Loading specular: {item.specular_map} (channel: {item.specular_map_ch})")
            self.maps['specular'] = self.loader.load_and_prep_channel(
                item.specular_map, item.specular_map_ch,
                0, 0, item.invert_specular_map
            )
            if item.invert_specular_map:
                print("    Inverting specular")
        
        if item.emissive_map and item.emissive_map != "":
            print(f"  Loading emissive: {item.emissive_map} (channel: {item.emissive_map_ch})")
            if item.emissive_map_ch == 'COLOR':
                emissive_data = self.loader.load_image_data(item.emissive_map)
                if emissive_data is not None:
                    self.maps['emissive'] = self.loader.resize_image(emissive_data, diffuse_h, diffuse_w)
            else:
                self.maps['emissive'] = self.loader.load_and_prep_channel(
                    item.emissive_map, item.emissive_map_ch,
                    diffuse_h, diffuse_w, False
                )
    
    def get(self, key: str) -> np.ndarray:
        """Get a map from the collection"""
        return self.maps.get(key)
    
    def __contains__(self, key: str) -> bool:
        """Check if a map exists in the collection"""
        return key in self.maps