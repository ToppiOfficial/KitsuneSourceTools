import bpy
from bpy.types import Operator, Context, Event, UILayout
from bpy.props import BoolProperty

from ..kitsunetools.commonutils import draw_wrapped_texts, draw_title_box_layout
from ..kitsunetools.objectutils import apply_object_transforms
from .common import KITSUNE_PT_ToolsPanel

class OBJECT_PT_ObjectData_Panel(KITSUNE_PT_ToolsPanel):
    bl_label : str = "Object Tools"
    
    def draw(self, context : Context) -> None:
        layout : UILayout = self.layout
        
        bx = layout.box()
        
        if context.active_object: pass
        else:
            draw_wrapped_texts(bx, text="Select an Object",max_chars=40 , icon='HELP')
            return
        
        transformbox = draw_title_box_layout(bx,text=f'Transform (Active: {context.active_object.name})',icon='TRANSFORM_ORIGINS',align=True)
        transformbox.operator(OBJECT_OT_Apply_Transform.bl_idname)
        
class OBJECT_OT_Apply_Transform(Operator):
    bl_idname : str = "objectdata.apply_transform"
    bl_label : str = "Apply Transform"
    bl_description : str = "Apply transforms to object and optionally its children"
    bl_options : set = {'REGISTER', 'UNDO'}
    
    location: BoolProperty(
        name="Location",
        description="Apply location transform",
        default=True
    )
    
    rotation: BoolProperty(
        name="Rotation",
        description="Apply rotation transform",
        default=True
    )
    
    scale: BoolProperty(
        name="Scale",
        description="Apply scale transform",
        default=True
    )
    
    include_children: BoolProperty(
        name="Include Children",
        description="Apply transforms to children as well",
        default=True
    )
    
    fix_bone_empties: BoolProperty(
        name="Fix Bone-Parented Empties",
        description="Automatically fix bone-parented empties after applying transforms to armatures",
        default=True
    )
    
    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool(context.active_object)
    
    def invoke(self, context : Context, event : Event) -> set:
        return context.window_manager.invoke_props_dialog(self, width=300)
    
    def draw(self, context : Context) -> None:
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        col = layout.column(align=True)
        col.label(text="Transform Components:")
        col.prop(self, "location")
        col.prop(self, "rotation")
        col.prop(self, "scale")
        
        col = layout.column(align=True)
        col.label(text="Options:")
        col.prop(self, "include_children")
        
        if context.active_object and context.active_object.type == 'ARMATURE':
            col.label(text="Armature Options:")
            col.prop(self, "fix_bone_empties")
    
    def execute(self, context : Context) -> set:
        obj = context.active_object
        
        if obj is None:
            self.report({'ERROR'}, "No active object")
            return {'CANCELLED'}
        
        try:
            count, fixed_count = apply_object_transforms(
                obj=obj,
                location=self.location,
                rotation=self.rotation,
                scale=self.scale,
                include_children=self.include_children,
                fix_bone_parented=self.fix_bone_empties
            )
            
            if fixed_count > 0:
                self.report({'INFO'}, f"Applied transforms to {count} object(s), fixed {fixed_count} empty(s)")
            else:
                self.report({'INFO'}, f"Applied transforms to {count} object(s)")
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to apply transforms: {str(e)}")
            return {'CANCELLED'}