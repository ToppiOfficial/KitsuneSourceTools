from typing import Literal, Set
from bpy.types import Context, Panel, UILayout, UILayout

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

    def draw_header(self, context : Context) -> None:
        self.layout.label(icon='TOOL_SETTINGS')

    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout

class Tools_SubCategoryPanel(KITSUNE_PT_CustomToolPanel, Panel):
    "Sub panel for the sub panel 'TOOLS_PT_PANEL'"
    bl_label : str = "SubTools"
    bl_parent_id : str = "TOOLS_PT_PANEL"
    bl_options : Set = {'DEFAULT_CLOSED'}
  