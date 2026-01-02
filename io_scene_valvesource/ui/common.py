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
        return

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