import bpy, sys, blf, gpu, traceback, time, io
from typing import Literal, Set
from bpy.types import Panel
from gpu_extras.batch import batch_for_shader
    
class KITSUNE_SecondaryPanel():
    bl_label : str = 'sample_toolpanel'
    bl_category : str = 'KitsuneSrcTool'
    bl_region_type : Literal[str] = 'UI'
    bl_space_type : Literal[str] = 'VIEW_3D'

class KITSUNE_PT_ToolsPanel(Panel):
    "Sub panel for the sub panel 'TOOLS_PT_PANEL'"
    bl_label : str = "Tools"
    bl_category : str = 'KitsuneSrcTool'
    bl_region_type : Literal[str] = 'UI'
    bl_space_type : Literal[str] = 'VIEW_3D'
    bl_options : Set = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
    
console_output = []
max_lines = 50

class ConsoleCapture(io.StringIO):
    def __init__(self, original_stream, update_callback=None):
        super().__init__()
        self.original_stream = original_stream
        self.update_callback = update_callback
    
    def write(self, text):
        global console_output
        
        if "Draw window and swap" in text:
            return len(text)
        
        if text.strip():
            console_output.append(text.rstrip())
            if len(console_output) > max_lines:
                console_output.pop(0)
            
            if self.update_callback:
                self.update_callback()
        
        if self.original_stream:
            self.original_stream.write(text)
        
        return len(text)
    
    def flush(self):
        if self.original_stream:
            self.original_stream.flush()

class ShowConsole:
    _draw_handler = None
    _original_stdout = None
    _original_stderr = None
    _is_drawing = False
    _last_update = 0
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        
        if hasattr(cls, 'execute'):
            original_execute = cls.execute
            
            def wrapped_execute(self, context):
                self._start_console_capture(context)
                try:
                    result = original_execute(self, context)
                    return result
                except Exception as e:
                    print(f"ERROR: {str(e)}")
                    traceback.print_exc()
                    return {'CANCELLED'}
                finally:
                    self._stop_console_capture(context)
            
            cls.execute = wrapped_execute
        
        # Only auto-create invoke if the class doesn't define its own
        if 'invoke' not in cls.__dict__:
            def auto_invoke(self, context, event):
                return self.execute(context)
            
            cls.invoke = auto_invoke
    
    def _force_redraw(self):
        current_time = time.time()
        if current_time - self._last_update > 0.05:
            self._last_update = current_time
            
            try:
                if bpy.context.scene.vs.enable_gui_console:
                    for window in bpy.context.window_manager.windows:
                        for area in window.screen.areas:
                            if area.type == 'VIEW_3D':
                                area.tag_redraw()
                    
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
            except:
                pass
    
    def _start_console_capture(self, context):
        global console_output
        console_output.clear()
        
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        self._last_update = time.time()
        
        capture_stdout = ConsoleCapture(self._original_stdout, update_callback=self._force_redraw)
        capture_stderr = ConsoleCapture(self._original_stderr, update_callback=self._force_redraw)
        sys.stdout = capture_stdout
        sys.stderr = capture_stderr
        
        if context.scene.vs.enable_gui_console:
            self._is_drawing = True
            args = (self,)
            self._draw_handler = bpy.types.SpaceView3D.draw_handler_add(
                self._draw_console_overlay, args, 'WINDOW', 'POST_PIXEL')
            
            self._force_redraw()
        else:
            self._is_drawing = False
    
    def _stop_console_capture(self, context):
        self._is_drawing = False
        
        if self._draw_handler:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(self._draw_handler, 'WINDOW')
            except:
                pass
            self._draw_handler = None
        
        if self._original_stdout:
            sys.stdout = self._original_stdout
        if self._original_stderr:
            sys.stderr = self._original_stderr
        
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    
    def _draw_console_overlay(self, dummy):
        if not self._is_drawing:
            return
            
        try:
            context = bpy.context
            if not context or not context.area:
                return
                
            font_id = 0
            line_height = 20
            margin = 15
            
            panel_width = context.area.width * 0.9
            panel_height = context.area.height * 0.7
            
            x_offset = (context.area.width - panel_width) / 2
            y_offset = (context.area.height - panel_height) / 2
            
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            vertices = (
                (x_offset, y_offset), 
                (x_offset, y_offset + panel_height),
                (x_offset + panel_width, y_offset + panel_height),
                (x_offset + panel_width, y_offset))
            indices = ((0, 1, 2), (0, 2, 3))
            
            gpu.state.blend_set('ALPHA')
            batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
            shader.bind()
            shader.uniform_float("color", (0.05, 0.05, 0.05, 0.98))
            batch.draw(shader)
            gpu.state.blend_set('NONE')
            
            blf.color(font_id, 0.2, 1.0, 0.3, 1.0)
            blf.size(font_id, 15)
            
            y_pos = y_offset + panel_height - margin
            blf.position(font_id, x_offset + margin, y_pos, 0)
            blf.draw(font_id, "Console Output")
            
            y_pos -= line_height * 2
            blf.color(font_id, 0.85, 0.85, 0.85, 1.0)
            blf.size(font_id, 13)
            
            visible_lines = min(len(console_output), 
                              int((panel_height - 80) // line_height))
            start_idx = max(0, len(console_output) - visible_lines)
            
            for line in console_output[start_idx:]:
                blf.position(font_id, x_offset + margin, y_pos, 0)
                display_line = line[:int(panel_width / 8)] + "..." if len(line) > int(panel_width / 8) else line
                blf.draw(font_id, display_line)
                y_pos -= line_height
                
        except Exception as e:
            pass
        