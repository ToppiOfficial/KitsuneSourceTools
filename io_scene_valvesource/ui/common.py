import bpy
from typing import Literal, Set
from bpy.types import Context, Panel, UILayout, UILayout
from ..utils import toggle_show_ops

class KITSUNE_PT_CustomToolPanel():
    "The primary panel that holds every UI"
    bl_label : str = 'sample_toolpanel'
    bl_category : str = 'KitsuneSourceTool'
    bl_region_type : Literal[str] = 'UI'
    bl_space_type : Literal[str] = 'VIEW_3D'
    bl_order : int = 1

class TOOLS_PT_PANEL(KITSUNE_PT_CustomToolPanel, Panel):
    "Sub that contains all tools"
    bl_label : str = 'Tools'
    bl_options : Set = {'DEFAULT_CLOSED'}

    def draw(self, context : Context) -> None:
        l : UILayout = self.layout

class Tools_SubCategoryPanel(KITSUNE_PT_CustomToolPanel, Panel):
    "Sub panel for the sub panel 'TOOLS_PT_PANEL'"
    bl_label : str = "SubTools"
    bl_parent_id : str = "TOOLS_PT_PANEL"
    bl_options : Set = {'DEFAULT_CLOSED'}
    
def make_toggle_operator_scene(suffix: str, mutual_exclusive_group: list[str] | None = None):
    """Create an operator that toggles a BoolProperty in context.scene.vs."""
    class_name : str = f"KITSUNE_OT_toggle_{suffix}"
    bl_idname : str = f"kitsunetoggle.{suffix}"
    bl_label : str = f"{suffix.replace('_', ' ').title()}"
    bl_options : set = {'INTERNAL'}

    def execute(self, context):
        vs = getattr(context.scene, "vs", None)
        if not vs:
            self.report({'ERROR'}, "context.scene.vs not found")
            return {'CANCELLED'}

        if not hasattr(vs, suffix):
            self.report({'ERROR'}, f"vs.{suffix} not found")
            return {'CANCELLED'}

        current = getattr(vs, suffix)
        if not isinstance(current, bool):
            self.report({'ERROR'}, f"vs.{suffix} is not a BoolProperty")
            return {'CANCELLED'}

        new_val = not current
        
        if new_val and mutual_exclusive_group:
            for prop in mutual_exclusive_group:
                if prop != suffix and hasattr(vs, prop):
                    setattr(vs, prop, False)
        
        setattr(vs, suffix, new_val)
        return {'FINISHED'}

    return type(
        class_name,
        (bpy.types.Operator,),
        {
            "bl_idname": bl_idname,
            "bl_label": bl_label,
            "execute": execute,
        }
    )

for entry in toggle_show_ops:
    if isinstance(entry, list):
        for name in entry:
            cls = make_toggle_operator_scene(name, mutual_exclusive_group=entry)
            bpy.utils.register_class(cls)
    else:
        cls = make_toggle_operator_scene(entry)
        bpy.utils.register_class(cls)
        
import blf

class ModalUIProcess:    
    @staticmethod
    def draw_modal_overlay(region, main_text: str, sub_text: str, progress: float = 0.0, show_progress: bool = False):
        """
        Draw a modern modal overlay
        
        Args:
            region: Blender region to draw on
            main_text: Main heading text
            sub_text: Subtitle/status text
            progress: Progress value 0.0 to 1.0
            show_progress: Whether to show progress bar
        """
        font_id = 1
        main_text_size = 17
        sub_text_size = 13
        padding = 20
        
        blf.size(font_id, main_text_size)
        text_width, text_height = blf.dimensions(font_id, main_text)
        
        blf.size(font_id, sub_text_size)
        sub_width, sub_height = blf.dimensions(font_id, sub_text)
        
        try:
            import gpu
            from gpu_extras.batch import batch_for_shader
            
            box_width = max(text_width, sub_width) + padding * 2
            box_height = text_height + sub_height + padding * 3
            
            box_x = (region.width - box_width) / 2
            box_y = (region.height - box_height) / 2
            
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            
            vertices = (
                (box_x, box_y),
                (box_x + box_width, box_y),
                (box_x + box_width, box_y + box_height),
                (box_x, box_y + box_height)
            )
            indices = ((0, 1, 2), (0, 2, 3))
            
            batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
            
            gpu.state.blend_set('ALPHA')
            shader.bind()
            shader.uniform_float("color", (0.12, 0.12, 0.12, 0.92))
            batch.draw(shader)
            
            border_thickness = 1
            border_color_top = (0.25, 0.25, 0.25, 0.9)
            border_color_sides = (0.25, 0.25, 0.25, 0.9)
            border_color_bottom = (0.25, 0.25, 0.25, 0.9)
            
            top_vertices = (
                (box_x, box_y + box_height - border_thickness),
                (box_x + box_width, box_y + box_height - border_thickness),
                (box_x + box_width, box_y + box_height),
                (box_x, box_y + box_height)
            )
            top_batch = batch_for_shader(shader, 'TRIS', {"pos": top_vertices}, indices=indices)
            shader.uniform_float("color", border_color_top)
            top_batch.draw(shader)
            
            right_vertices = (
                (box_x + box_width - border_thickness, box_y),
                (box_x + box_width, box_y),
                (box_x + box_width, box_y + box_height),
                (box_x + box_width - border_thickness, box_y + box_height)
            )
            right_batch = batch_for_shader(shader, 'TRIS', {"pos": right_vertices}, indices=indices)
            shader.uniform_float("color", border_color_sides)
            right_batch.draw(shader)
            
            left_vertices = (
                (box_x, box_y),
                (box_x + border_thickness, box_y),
                (box_x + border_thickness, box_y + box_height),
                (box_x, box_y + box_height)
            )
            left_batch = batch_for_shader(shader, 'TRIS', {"pos": left_vertices}, indices=indices)
            shader.uniform_float("color", border_color_sides)
            left_batch.draw(shader)
            
            bottom_vertices = (
                (box_x, box_y),
                (box_x + box_width, box_y),
                (box_x + box_width, box_y + border_thickness),
                (box_x, box_y + border_thickness)
            )
            bottom_batch = batch_for_shader(shader, 'TRIS', {"pos": bottom_vertices}, indices=indices)
            shader.uniform_float("color", border_color_bottom)
            bottom_batch.draw(shader)
            
            if show_progress:
                progress_bar_height = 20
                progress_bar_y = box_y + padding // 6
                progress_bar_x = box_x + padding
                progress_bar_width = box_width - padding * 2
                
                bg_vertices = (
                    (progress_bar_x, progress_bar_y),
                    (progress_bar_x + progress_bar_width, progress_bar_y),
                    (progress_bar_x + progress_bar_width, progress_bar_y + progress_bar_height),
                    (progress_bar_x, progress_bar_y + progress_bar_height)
                )
                bg_batch = batch_for_shader(shader, 'TRIS', {"pos": bg_vertices}, indices=indices)
                shader.uniform_float("color", (0.2, 0.2, 0.22, 0.8))
                bg_batch.draw(shader)
                
                filled_width = progress_bar_width * max(0.0, min(1.0, progress))
                
                if filled_width > 0:
                    fill_vertices = (
                        (progress_bar_x, progress_bar_y),
                        (progress_bar_x + filled_width, progress_bar_y),
                        (progress_bar_x + filled_width, progress_bar_y + progress_bar_height),
                        (progress_bar_x, progress_bar_y + progress_bar_height)
                    )
                    fill_batch = batch_for_shader(shader, 'TRIS', {"pos": fill_vertices}, indices=indices)
                    shader.uniform_float("color", (0.8, 0.8, 0.8, 1.0))
                    fill_batch.draw(shader)
            
            gpu.state.blend_set('NONE')
        except Exception:
            pass
        
        blf.size(font_id, main_text_size)
        blf.enable(font_id, blf.SHADOW)
        blf.shadow(font_id, 5, 0.0, 0.0, 0.0, 0.7)
        blf.shadow_offset(font_id, 1, -1)
        blf.color(font_id, 0.95, 0.95, 0.98, 1.0)
        text_x = (region.width - text_width) / 2
        text_y = box_y + box_height - padding - text_height + 5
        blf.position(font_id, text_x, text_y, 0)
        blf.draw(font_id, main_text)

        blf.size(font_id, sub_text_size)
        blf.shadow(font_id, 3, 0.0, 0.0, 0.0, 0.5)
        blf.color(font_id, 0.7, 0.7, 0.75, 1.0)
        sub_x = (region.width - sub_width) / 2
        sub_y = box_y + padding + (12 if show_progress else 10)
        blf.position(font_id, sub_x, sub_y, 0)
        blf.draw(font_id, sub_text)
        blf.disable(font_id, blf.SHADOW)
