import bpy
from bpy.types import Operator, Context, Event, UILayout
from bpy.props import BoolProperty
from mathutils import Vector, Matrix, bvhtree

from ..kitsunetools.commonutils import draw_wrapped_texts, draw_title_box_layout
from ..kitsunetools.objectutils import apply_object_transforms
from .common import KITSUNE_PT_ToolSubPanel

class OBJECT_PT_ObjectData_Panel(KITSUNE_PT_ToolSubPanel):
    bl_label = "Object Tools"
    
    def draw(self, context : Context) -> None:
        layout : UILayout = self.layout
        
        bx = layout.box()
        
        if context.active_object: pass
        else:
            draw_wrapped_texts(bx, text="Select an Object",max_chars=40 , icon='HELP')
            return
        
        transformbox = draw_title_box_layout(bx,text=f'Transform (Active: {context.active_object.name})',icon='TRANSFORM_ORIGINS',align=True)
        transformbox.operator(OBJECT_OT_Apply_Transform.bl_idname)
        transformbox.operator(SMD_OT_SurfaceSnap.bl_idname)
        
class OBJECT_OT_Apply_Transform(Operator):
    bl_idname = "objectdata.apply_transform"
    bl_label = "Apply Transform"
    bl_description = "Apply transforms to object and optionally its children"
    bl_options = {'REGISTER', 'UNDO'}
    
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


class SMD_OT_SurfaceSnap(Operator):
    bl_idname = "objectdata.surface_snap"
    bl_label = "Surface Snap"
    bl_description = "Snap selected objects to the surface under the mouse cursor"
    bl_options = {'REGISTER', 'UNDO'}
 
    mouse_x: bpy.props.IntProperty()
    mouse_y: bpy.props.IntProperty()
 
    @classmethod
    def poll(cls, context):
        return (
            context.mode == 'OBJECT'
            and context.region is not None
            and context.region.type == 'WINDOW'
            and context.region_data is not None
            and len(context.selected_objects) > 0
        )
 
    def invoke(self, context, event) -> set:
        self.mouse_x = event.mouse_x
        self.mouse_y = event.mouse_y
        return self.execute(context)
 
    def execute(self, context) -> set:
        def is_point_object(obj):
            return obj.type in {'LIGHT', 'CAMERA', 'SPEAKER', 'LIGHT_PROBE'} or (
                obj.type == 'EMPTY' and obj.empty_display_type not in {'CUBE', 'SPHERE', 'CONE', 'ARROWS'}
            )
 
        def is_surface_object(obj):
            return obj.type in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT'} and obj.visible_get()
 
        def get_view_ray():
            from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
            region = context.region
            rv3d = context.region_data
            coord = (self.mouse_x - region.x, self.mouse_y - region.y)
            origin = region_2d_to_origin_3d(region, rv3d, coord)
            direction = region_2d_to_vector_3d(region, rv3d, coord)
            return origin, direction
 
        def raycast_scene(origin, direction, exclude_objects):
            depsgraph = context.evaluated_depsgraph_get()
            best_hit = None
            best_dist = float('inf')
 
            for obj in context.visible_objects:
                if obj in exclude_objects or not is_surface_object(obj):
                    continue
 
                obj_eval = obj.evaluated_get(depsgraph)
                try:
                    mesh = obj_eval.to_mesh()
                except Exception:
                    continue
 
                if not mesh or not mesh.polygons:
                    obj_eval.to_mesh_clear()
                    continue
 
                mat_inv = obj.matrix_world.inverted()
                local_origin = mat_inv @ origin
                local_dir = (mat_inv.to_3x3() @ direction).normalized()
 
                bvh = bvhtree.BVHTree.FromObject(obj_eval, depsgraph)
                hit, normal, _, _ = bvh.ray_cast(local_origin, local_dir)
 
                obj_eval.to_mesh_clear()
 
                if hit is None:
                    continue
 
                world_hit = obj.matrix_world @ hit
                dist = (world_hit - origin).length
 
                if dist < best_dist:
                    world_normal = (obj.matrix_world.to_3x3() @ normal).normalized()
                    best_dist = dist
                    best_hit = (world_hit, world_normal, obj)
 
            return best_hit
 
        def align_object_to_surface(obj, hit_point, surface_normal, point):
            if point:
                obj.location = hit_point
            else:
                up = Vector((0, 0, 1))
                normal = surface_normal.normalized()
 
                if abs(normal.dot(up)) > 0.9999:
                    tangent = Vector((1, 0, 0))
                else:
                    tangent = up.cross(normal).normalized()
 
                bitangent = normal.cross(tangent).normalized()
 
                rot_matrix = Matrix((
                    tangent,
                    bitangent,
                    normal,
                )).transposed()
 
                obj.matrix_world = Matrix.Translation(hit_point) @ rot_matrix.to_4x4()
 
        selected = context.selected_objects
        origin, direction = get_view_ray()
        hit_result = raycast_scene(origin, direction, set(selected))
 
        if not hit_result:
            self.report({'WARNING'}, "No surface found under mouse cursor")
            return {'CANCELLED'}
 
        hit_point, surface_normal, hit_obj = hit_result
 
        snapped = 0
        for obj in selected:
            if is_point_object(obj) and is_point_object(hit_obj):
                self.report({'WARNING'}, f"'{obj.name}' skipped: point objects cannot snap to other point objects")
                continue
 
            align_object_to_surface(obj, hit_point, surface_normal, is_point_object(obj))
            snapped += 1
 
        if snapped:
            self.report({'INFO'}, f"Snapped {snapped} object(s) to surface '{hit_obj.name}'")
 
        return {'FINISHED'}