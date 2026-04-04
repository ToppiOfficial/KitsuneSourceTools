from .common import KITSUNE_PT_ToolSubPanel
from bpy.types import Context, Panel

class DEVELOPER_PT_PANEL(KITSUNE_PT_ToolSubPanel, Panel):
    bl_label = 'Developer'
    bl_order = 1000
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context : Context) -> None:
        layout = self.layout
        box = layout.box()
        
        maincol = box.column()
        maincol.prop(context.scene.vs,"use_kv2", text='Write ASCII DMX File')
        maincol.prop(context.scene.vs,"enable_gui_console")