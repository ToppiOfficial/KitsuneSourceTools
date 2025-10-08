import bpy, bmesh
from bpy.types import UILayout, Context, Object, Operator, Mesh
from typing import Set

from .common import Tools_SubCategoryPanel
from ..core.commonutils import (
    draw_title_box, draw_wrapped_text_col,
    is_armature, is_mesh,
)
from ..core.meshutils import (
    get_unused_shape_keys, clean_vertex_groups
)
from ..utils import hasShapes
from ..utils import get_id

class TOOLS_PT_Mesh(Tools_SubCategoryPanel):
    bl_label : str = "Mesh Tools"
    
    def draw(self, context : Context) -> None:
        l : UILayout | None = self.layout
        bx : UILayout = draw_title_box(l, TOOLS_PT_Mesh.bl_label, icon='MESH_DATA')
        
        if is_mesh(context.object) or is_armature(context.object): pass
        else:
            draw_wrapped_text_col(bx,get_id("panel_select_mesh"),max_chars=40 , icon='HELP')
            return
        
        col = bx.column()
        row = col.row(align=True)
        row.scale_y = 1.3
        row.operator(TOOLS_OT_CleanShapeKeys.bl_idname, icon='SHAPEKEY_DATA')
        row.operator(TOOLS_OT_RemoveUnusedVertexGroups.bl_idname, icon='GROUP_VERTEX')
        
        col.operator(TOOLS_OT_SelectShapekeyVets.bl_idname, icon='VERTEXSEL')
        col.operator(TOOLS_OT_AddToonEdgeLine.bl_idname, icon='MOD_SOLIDIFY')
        
class TOOLS_OT_CleanShapeKeys(Operator):
    bl_idname : str = 'tools.clean_shape_keys'
    bl_label : str = 'Clean Shape Keys'
    bl_options : Set = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool(is_mesh(context.object) and hasShapes(context.object, valid_only=True))
    
    def execute(self, context : Context) -> Set:
        objects = context.selected_objects
        
        if not objects:
            self.report({'WARNING'}, 'No objects are selected')
            return {'CANCELLED'}
        
        cleaned_objects = 0
        removed_shapekeys = 0
        
        for ob in objects:
            if ob.type != 'MESH': continue
            
            deleted_sk = get_unused_shape_keys(ob)
            
            if deleted_sk:
                cleaned_objects += 1
                removed_shapekeys += len(deleted_sk)
                
        if cleaned_objects and removed_shapekeys:
            self.report({'INFO'}, f'{cleaned_objects} objects processed with {removed_shapekeys} shapekeys removed')
        else:
            self.report({'INFO'}, f'No shapekeys were removed')
            
        return {'FINISHED'}
    
class TOOLS_OT_SelectShapekeyVets(Operator):
    bl_idname : str = 'tools.select_shapekey_vertices'
    bl_label : str = 'Select Shapekey Vertices'
    bl_options : Set = {'REGISTER', 'UNDO'}

    select_type: bpy.props.EnumProperty(
        name="Selection Type",
        items=[
            ('ACTIVE', "Active Shapekey", "Use only the active shapekey"),
            ('ALL', "All Shapekeys", "Use all shapekeys except the first (basis)"),
        ],
        default='ALL'
    )

    select_inverse: bpy.props.BoolProperty(
        name="Select Inverse",
        default=False,
        description="Select vertices *not* affected by the shapekey(s)"
    )

    threshold: bpy.props.FloatProperty(
        name="Threshold",
        description="Minimum vertex delta to consider as affected by shapekey",
        default=0.01,
        min=0.001,
        max=1.0,
        precision=4
    )

    @classmethod
    def poll(cls, context : Context) -> bool:
        ob : Object | None = context.object
        return bool(is_mesh(ob) and ob.data.shape_keys and ob.mode == 'EDIT')

    def execute(self, context : Context) -> Set:
        obj = context.active_object
        mesh : Mesh = obj.data # type: ignore
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()

        shapekeys = mesh.shape_keys.key_blocks
        basis = shapekeys[0]

        if self.select_type == 'ACTIVE':
            keyblocks = [obj.active_shape_key] if obj.active_shape_key != basis else []
        else:  # ALL
            keyblocks = [kb for kb in shapekeys[1:]]

        basis_coords = basis.data

        affected_indices = {
            i for kb in keyblocks
            for i, (v_basis, v_shape) in enumerate(zip(basis_coords, kb.data))
            if (v_basis.co - v_shape.co).length > self.threshold
        }

        inv = self.select_inverse
        for i, v in enumerate(bm.verts):
            v.select_set((i in affected_indices) != inv)  # XOR

        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
        bpy.ops.mesh.select_mode(type='VERT')
        return {'FINISHED'}

class TOOLS_OT_RemoveUnusedVertexGroups(Operator):
    bl_idname : str = "tools.remove_unused_vertexgroups"
    bl_label : str = "Clean Unused Vertex Groups"
    bl_options : Set = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool(context.selected_objects)
    
    def execute(self, context : Context) -> Set:
        obs = context.selected_objects
        total_removed = 0

        for ob in obs:
            removed_vgroups = clean_vertex_groups(ob)
            total_removed += sum(len(vgs) for vgs in removed_vgroups.values())

        self.report({'INFO'}, f"Removed {total_removed} unused vertex groups.")
        return {'FINISHED'}

class TOOLS_OT_AddToonEdgeLine(Operator):
    bl_idname : str = "tools.add_toon_edgeline"
    bl_label : str = "Add Black Toon Edgeline"
    bl_options : Set = {"REGISTER", "UNDO"}

    has_sharp_edgesplit: bpy.props.BoolProperty(
        name="Has Sharp EdgeSplit",
        description="Add or ensure a sharp-only EdgeSplit modifier before the Solidify modifier",
        default=False,
    )

    use_shape_key_weights: bpy.props.BoolProperty(
        name="Use Shape Key Weights",
        description="Assign vertex weights based on total movement from all shape keys",
        default=False
    )
    
    edgeline_thickness: bpy.props.FloatProperty(
        name="Edgeline Thickness",
        description="Thickness of the toon edgeline (in scene units)",
        default=0.05,
        min=0.0,
        precision=4,
        unit='LENGTH',
        subtype='DISTANCE'
    )

    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool({ob for ob in context.selected_objects if is_mesh(ob) and not ob.hide_get()})

    def execute(self, context : Context) -> Set:
        obs = {ob for ob in context.selected_objects if is_mesh(ob) and not ob.hide_get()}

        for ob in obs:
            bpy.context.view_layer.objects.active = ob

            scene = context.scene
            unit_scale = scene.unit_settings.scale_length or 1.0

            edgeline_mat = None
            for mat in bpy.data.materials:
                if "edgeline" in mat.name.lower():
                    edgeline_mat = mat
                    break

            if edgeline_mat is None:
                edgeline_mat = bpy.data.materials.new(name="edgeline")
                edgeline_mat.use_nodes = True
                nodes = edgeline_mat.node_tree.nodes
                nodes.clear()
                emission_node = nodes.new(type="ShaderNodeEmission")
                emission_node.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
                emission_node.inputs["Strength"].default_value = 1.0
                output_node = nodes.new(type="ShaderNodeOutputMaterial")
                edgeline_mat.node_tree.links.new(emission_node.outputs["Emission"], output_node.inputs["Surface"])

            edgeline_mat.use_backface_culling = True
            if hasattr(edgeline_mat, "use_backface_culling_shadow"):
                edgeline_mat.use_backface_culling_shadow = True

            edgeline_mat.vs.non_exportable_vgroup = 'non_exportable_face'
            edgeline_mat.vs.do_not_export_faces_vgroup = True

            original_mat_count = sum(1 for slot in ob.material_slots if slot.material and "edgeline" not in slot.material.name.lower())
            expected_mat_count = original_mat_count * 2
            while len(ob.data.materials) < expected_mat_count:
                ob.data.materials.append(edgeline_mat)

            solid = ob.modifiers.get("Toon_Edgeline") or ob.modifiers.new(name="Toon_Edgeline", type="SOLIDIFY")
            filter_vgroup = ob.vertex_groups.get('non_exportable_face') or ob.vertex_groups.new(name='non_exportable_face')
            solid.use_rim = False
            solid.thickness = -(self.edgeline_thickness / 1000.0) / unit_scale
            solid.material_offset = original_mat_count
            solid.use_flip_normals = True
            solid.vertex_group = filter_vgroup.name
            solid.invert_vertex_group = True

            if self.use_shape_key_weights and ob.data.shape_keys and len(ob.data.shape_keys.key_blocks) > 1:
                base = ob.data.shape_keys.key_blocks[0].data
                vertex_weights = [0.0] * len(ob.data.vertices)

                for sk in ob.data.shape_keys.key_blocks[1:]:
                    for i, vert in enumerate(sk.data):
                        delta = (vert.co - base[i].co).length
                        if delta > 0:
                            vertex_weights[i] += delta

                for i, weight in enumerate(vertex_weights):
                    if weight > 0:
                        filter_vgroup.add([i], weight, 'REPLACE')
                        
            if self.has_sharp_edgesplit:
                edgesplit = ob.modifiers.get("Toon_EdgeSplit") or ob.modifiers.new(name="Toon_EdgeSplit", type="EDGE_SPLIT")
                edgesplit.use_edge_angle = False
                edgesplit.use_edge_sharp = True
                while ob.modifiers[0] != edgesplit:
                    bpy.ops.object.modifier_move_up(modifier=edgesplit.name)
                solid_index_target = 1
            else:
                edgesplit = ob.modifiers.get("Toon_EdgeSplit")
                if edgesplit:
                    ob.modifiers.remove(edgesplit)
                solid_index_target = 0

            while ob.modifiers[solid_index_target] != solid:
                bpy.ops.object.modifier_move_up(modifier=solid.name)

        return {"FINISHED"}
