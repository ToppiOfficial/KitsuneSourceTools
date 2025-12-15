import bpy, bmesh, mathutils
from bpy.types import UILayout, Context, Object, Operator, Mesh
from typing import Set

from .common import Tools_SubCategoryPanel
from ..core.commonutils import (
    draw_title_box_layout, draw_wrapped_texts,
    is_armature, is_mesh,
)
from ..core.meshutils import (
    get_unused_shapekeys, remove_unused_vertexgroups
)
from ..utils import hasShapes
from ..utils import get_id

class TOOLS_PT_Mesh(Tools_SubCategoryPanel):
    bl_label : str = "Mesh"
    
    def draw(self, context : Context) -> None:
        l : UILayout = self.layout
        bx : UILayout = draw_title_box_layout(l, TOOLS_PT_Mesh.bl_label, icon='MESH_DATA')
        
        if is_mesh(context.object) or is_armature(context.object): pass
        else:
            draw_wrapped_texts(bx,get_id("panel_select_mesh"),max_chars=40 , icon='HELP')
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
    bl_options : set = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool(is_mesh(context.object) and hasShapes(context.object, valid_only=True))
    
    def execute(self, context : Context) -> set:
        objects = context.selected_objects
        
        if not objects:
            self.report({'WARNING'}, 'No objects are selected')
            return {'CANCELLED'}
        
        cleaned_objects = 0
        removed_shapekeys = 0
        
        for ob in objects:
            if ob.type != 'MESH': continue
            
            deleted_sk = get_unused_shapekeys(ob)
            
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
            removed_vgroups = remove_unused_vertexgroups(ob)
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
    
    overwrite_existing_weights: bpy.props.BoolProperty(
        name="Overwrite Existing Weights",
        description="Update vertex group weights even if the vertex group already exists",
        default=True
    )
    
    shape_key_weight_mode: bpy.props.EnumProperty(
        name="Weight Mode",
        description="How to apply shape key deformation as vertex weights",
        items=[
            ('ABSOLUTE', "Absolute", "Set all deformed vertices to weight 1.0"),
            ('LINEAR', "Linear", "Map deformation linearly between min and max weights"),
            ('SQUARED', "Squared", "Apply squared falloff for smoother transitions"),
            ('SQRT', "Square Root", "Apply square root for sharper transitions"),
        ],
        default='LINEAR'
    )
    
    weight_min: bpy.props.FloatProperty(
        name="Min Weight",
        description="Minimum weight value for shape key deformation",
        default=0.0,
        min=0.0,
        max=1.0,
    )
    
    weight_max: bpy.props.FloatProperty(
        name="Max Weight",
        description="Maximum weight value for shape key deformation",
        default=1.0,
        min=0.0,
        max=1.0,
    )
    
    weight_threshold: bpy.props.FloatProperty(
        name="Threshold",
        description="Minimum deformation distance to consider (in scene units)",
        default=0.0001,
        min=0.0,
        precision=5,
        unit='LENGTH',
        subtype='DISTANCE'
    )
    
    weight_expansion: bpy.props.FloatProperty(
        name="Weight Expansion",
        description="Expand weights to neighboring vertices (0 = no expansion)",
        default=0.0,
        min=0.0,
        max=10.0,
    )
    
    normalize_per_shapekey: bpy.props.BoolProperty(
        name="Normalize Per Shape Key",
        description="Normalize weights for each shape key individually before combining",
        default=False
    )
    
    use_component_size_weights: bpy.props.BoolProperty(
        name="Use Component Size Weights",
        description="Assign vertex weights based on relative size of mesh components (islands)",
        default=False
    )
    
    component_weight_min: bpy.props.FloatProperty(
        name="Min Component Weight",
        description="Minimum weight for smallest mesh component",
        default=0.0,
        min=0.0,
        max=1.0,
    )
    
    component_weight_max: bpy.props.FloatProperty(
        name="Max Component Weight",
        description="Maximum weight for largest mesh component",
        default=0.8,
        min=0.0,
        max=1.0,
    )
    
    component_size_metric: bpy.props.EnumProperty(
        name="Size Metric",
        description="How to measure component size",
        items=[
            ('VOLUME', "Volume", "Use bounding box volume"),
            ('AREA', "Surface Area", "Use total surface area of faces"),
            ('VERTICES', "Vertex Count", "Use number of vertices"),
        ],
        default='VOLUME'
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

    def draw(self, context : Context):
        layout = self.layout
        
        layout.prop(self, "edgeline_thickness")
        layout.prop(self, "has_sharp_edgesplit") 
        layout.prop(self, "use_shape_key_weights")
        
        if self.use_shape_key_weights:
            box = layout.box()
            box.prop(self, "overwrite_existing_weights")
            box.prop(self, "shape_key_weight_mode")
            
            row = box.row(align=True)
            row.prop(self, "weight_min")
            row.prop(self, "weight_max")
            
            box.prop(self, "weight_threshold")
            box.prop(self, "weight_expansion")
            box.prop(self, "normalize_per_shapekey")
        
        layout.prop(self, "use_component_size_weights")
        
        if self.use_component_size_weights:
            box = layout.box()
            box.prop(self, "component_size_metric")
            row = box.row(align=True)
            row.prop(self, "component_weight_min")
            row.prop(self, "component_weight_max")

    def calculate_component_weights(self, ob):
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        
        islands = []
        unvisited = set(bm.verts)
        
        while unvisited:
            island = []
            queue = [unvisited.pop()]
            
            while queue:
                v = queue.pop(0)
                if v in island:
                    continue
                island.append(v)
                
                for edge in v.link_edges:
                    other = edge.other_vert(v)
                    if other in unvisited:
                        unvisited.discard(other)
                        queue.append(other)
            
            islands.append(island)
        
        island_sizes = []
        for island in islands:
            if self.component_size_metric == 'VERTICES':
                size = len(island)
            elif self.component_size_metric == 'AREA':
                area = 0.0
                for v in island:
                    for face in v.link_faces:
                        if all(fv in island for fv in face.verts):
                            area += face.calc_area()
                size = area / len(island)
            else:
                coords = [v.co for v in island]
                min_co = mathutils.Vector((min(c.x for c in coords), min(c.y for c in coords), min(c.z for c in coords)))
                max_co = mathutils.Vector((max(c.x for c in coords), max(c.y for c in coords), max(c.z for c in coords)))
                bbox_size = max_co - min_co
                size = bbox_size.x * bbox_size.y * bbox_size.z
            
            island_sizes.append(size)
        
        min_size = min(island_sizes)
        max_size = max(island_sizes)
        size_range = max_size - min_size
        
        vertex_weights = [0.0] * len(bm.verts)
        
        for island, size in zip(islands, island_sizes):
            if size_range > 0:
                normalized = (max_size - size) / size_range
                weight = self.component_weight_min + normalized * (self.component_weight_max - self.component_weight_min)
            else:
                weight = self.component_weight_max
            
            weight = round(weight, 2)
            
            for v in island:
                vertex_weights[v.index] = weight
        
        bm.free()
        return vertex_weights

    def execute(self, context : Context) -> Set:
        obs : set[Object]  = {ob for ob in context.selected_objects if is_mesh(ob) and not ob.hide_get()}

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

            old_to_new_index = {}
            non_edgeline_indices = []
            edgeline_indices = []
            
            for old_idx, slot in enumerate(ob.material_slots):
                if slot.material and "edgeline" in slot.material.name.lower():
                    edgeline_indices.append(old_idx)
                else:
                    non_edgeline_indices.append(old_idx)

            original_mat_count = len(non_edgeline_indices)
            
            for new_idx, old_idx in enumerate(non_edgeline_indices):
                old_to_new_index[old_idx] = new_idx
            
            for new_idx, old_idx in enumerate(edgeline_indices):
                old_to_new_index[old_idx] = original_mat_count + new_idx
            
            for poly in ob.data.polygons:
                if poly.material_index in old_to_new_index:
                    poly.material_index = old_to_new_index[poly.material_index]
            
            new_order = non_edgeline_indices + edgeline_indices
            temp_materials = [ob.material_slots[i].material for i in new_order]
            
            expected_edgeline_count = original_mat_count
            while len(temp_materials) < original_mat_count + expected_edgeline_count:
                temp_materials.append(edgeline_mat)
            
            for i, mat in enumerate(temp_materials):
                if i < len(ob.material_slots):
                    ob.material_slots[i].material = mat
                else:
                    ob.data.materials.append(mat)

            solid = ob.modifiers.get("Toon_Edgeline") or ob.modifiers.new(name="Toon_Edgeline", type="SOLIDIFY")
            filter_vgroup = ob.vertex_groups.get('non_exportable_face')
            vgroup_exists = filter_vgroup is not None
            
            if filter_vgroup is None:
                filter_vgroup = ob.vertex_groups.new(name='non_exportable_face')
            
            solid.use_rim = False
            solid.thickness = -(self.edgeline_thickness / 1000.0) / unit_scale
            solid.material_offset = original_mat_count
            solid.use_flip_normals = True
            solid.vertex_group = filter_vgroup.name
            solid.invert_vertex_group = True

            vertex_weights = [0.0] * len(ob.data.vertices)
            
            if self.use_component_size_weights:
                component_weights = self.calculate_component_weights(ob)
                for i in range(len(vertex_weights)):
                    vertex_weights[i] = max(vertex_weights[i], component_weights[i])

            should_update_weights = self.use_shape_key_weights and (self.overwrite_existing_weights or not vgroup_exists)
            
            if should_update_weights and ob.data.shape_keys and len(ob.data.shape_keys.key_blocks) > 1:
                base = ob.data.shape_keys.key_blocks[0].data
                shape_weights = [0.0] * len(ob.data.vertices)

                for sk in ob.data.shape_keys.key_blocks[1:]:
                    sk_weights = [0.0] * len(ob.data.vertices)
                    
                    for i, vert in enumerate(sk.data):
                        delta = (vert.co - base[i].co).length
                        if delta > self.weight_threshold:
                            sk_weights[i] = delta
                    
                    if self.normalize_per_shapekey and max(sk_weights) > 0:
                        max_delta = max(sk_weights)
                        sk_weights = [w / max_delta for w in sk_weights]
                    
                    for i, weight in enumerate(sk_weights):
                        shape_weights[i] += weight

                if max(shape_weights) > 0:
                    max_weight = max(shape_weights)
                    
                    for i, weight in enumerate(shape_weights):
                        if weight > 0:
                            normalized = weight / max_weight
                            
                            if self.shape_key_weight_mode == 'ABSOLUTE':
                                final_weight = self.weight_max
                            elif self.shape_key_weight_mode == 'LINEAR':
                                final_weight = self.weight_min + normalized * (self.weight_max - self.weight_min)
                            elif self.shape_key_weight_mode == 'SQUARED':
                                final_weight = self.weight_min + (normalized ** 2) * (self.weight_max - self.weight_min)
                            elif self.shape_key_weight_mode == 'SQRT':
                                final_weight = self.weight_min + (normalized ** 0.5) * (self.weight_max - self.weight_min)
                            
                            shape_weights[i] = final_weight

                if self.weight_expansion > 0:
                    bm = bmesh.new()
                    bm.from_mesh(ob.data)
                    bm.verts.ensure_lookup_table()
                    
                    expanded_weights = shape_weights.copy()
                    iterations = int(self.weight_expansion)
                    
                    for _ in range(iterations):
                        new_weights = expanded_weights.copy()
                        for v in bm.verts:
                            if expanded_weights[v.index] > 0:
                                for edge in v.link_edges:
                                    other = edge.other_vert(v)
                                    new_weights[other.index] = max(new_weights[other.index], expanded_weights[v.index])
                        expanded_weights = new_weights
                    
                    bm.free()
                    shape_weights = expanded_weights

                for i, weight in enumerate(shape_weights):
                    vertex_weights[i] = max(vertex_weights[i], weight)

            for i, weight in enumerate(vertex_weights):
                if weight > 0:
                    final_weight = round(weight, 2)
                    filter_vgroup.add([i], final_weight, 'REPLACE')
                        
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