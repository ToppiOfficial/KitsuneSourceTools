class TextureMapDefaults:
    """Manages default texture maps for items"""
    
    @staticmethod
    def ensure_item_maps(item):
        """Ensure all required maps have defaults"""
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
            item.invert_ambientocclu_map = False
        
        if not item.alpha_map or item.alpha_map == "":
            item.alpha_map = "flat_alpha"
            item.alpha_map_ch = 'GREY'
            item.invert_alpha_map = False

        if not item.specular_map or item.specular_map == "":
            item.specular_map = "flat_specular"
            item.specular_map_ch = 'GREY'
            item.invert_specular_map = False
