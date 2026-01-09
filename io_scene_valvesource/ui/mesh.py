import bpy, bmesh, mathutils
from bpy.types import UILayout, Context, Object, Operator, Mesh
from typing import Set

from bpy.props import BoolProperty, EnumProperty, FloatProperty

from .common import ToolsCategoryPanel
from ..core.commonutils import (
    draw_title_box_layout, draw_wrapped_texts,
    is_armature, is_mesh,
)
from ..core.meshutils import (
    get_unused_shapekeys, remove_unused_vertexgroups
)
from ..utils import hasShapes
from ..utils import get_id

class TOOLS_PT_Mesh(ToolsCategoryPanel):
    bl_label : str = "Mesh Tools"
    
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
    bl_idname : str = 'kitsunetools.clean_shape_keys'
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
    bl_idname : str = 'kitsunetools.select_shapekey_vertices'
    bl_label : str = 'Select Shapekey Vertices'
    bl_options : Set = {'REGISTER', 'UNDO'}

    select_type: EnumProperty(
        name="Selection Type",
        items=[
            ('ACTIVE', "Active Shapekey", "Use only the active shapekey"),
            ('ALL', "All Shapekeys", "Use all shapekeys except the first (basis)"),
        ],
        default='ALL'
    )

    select_inverse: BoolProperty(
        name="Select Inverse",
        default=False,
        description="Select vertices *not* affected by the shapekey(s)"
    )

    threshold: FloatProperty(
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
    bl_idname : str = "kitsunetools.remove_unused_vertexgroups"
    bl_label : str = "Clean Unused Vertex Groups"
    bl_options : Set = {'REGISTER', 'UNDO'}
    
    respect_mirror : BoolProperty(name='Respect Mirror', default=True)
    weight_threshold : FloatProperty(name='Weight Threshold', default=0.001,min=0.0001,max=0.1,precision=4)
    
    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool(context.selected_objects)
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=300)
    
    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        
        col.prop(self, 'respect_mirror')
        col.prop(self, 'weight_threshold', slider=True)
    
    def execute(self, context : Context) -> Set:
        obs = context.selected_objects
        total_removed = 0

        for ob in obs:
            removed_vgroups = remove_unused_vertexgroups(ob, weight_limit=self.weight_threshold, respect_mirror=self.respect_mirror)
            total_removed += sum(len(vgs) for vgs in removed_vgroups.values())

        self.report({'INFO'}, f"Removed {total_removed} unused vertex groups.")
        return {'FINISHED'}

class TOOLS_OT_AddToonEdgeLine(Operator):
    bl_idname: str = "kitsunetools.add_toon_edgeline"
    bl_label: str = "Add Black Toon Edgeline"
    bl_options: Set = {"REGISTER", "UNDO"}

    per_material_edgeline: BoolProperty(
        name="Per Material Edgeline",
        description="Create separate edgeline materials for each base material, or use a single unified edgeline material",
        default=False,
    )
    
    overwrite_existing_materials: BoolProperty(
        name="Overwrite Existing Materials",
        description="Replace existing edgeline material setup even if edgeline materials already exist",
        default=True,
    )

    use_component_weights: BoolProperty(
        name="Use Component Weights",
        description="Calculate vertex weights based on mesh island size",
        default=True,
    )
    
    overwrite_existing_weights: BoolProperty(
        name="Overwrite Existing Weights",
        description="Update vertex group weights even if the vertex group already exists",
        default=False
    )
    
    weight_min: FloatProperty(
        name="Min Weight",
        description="Minimum weight value",
        default=0.3,
        min=0.0,
        max=1.0,
    )
    
    weight_max: FloatProperty(
        name="Max Weight",
        description="Maximum weight value",
        default=0.8,
        min=0.0,
        max=1.0,
    )
    
    component_size_metric: EnumProperty(
        name="Size Metric",
        description="How to measure component size",
        items=[
            ('VOLUME', "Volume", "Use bounding box volume"),
            ('AREA', "Surface Area", "Use total surface area of faces"),
            ('VERTICES', "Vertex Count", "Use number of vertices"),
        ],
        default='AREA'
    )
    
    edgeline_thickness: FloatProperty(
        name="Edgeline Thickness",
        description="Thickness of the toon edgeline (in scene units)",
        default=0.15,
        min=0.0,
        precision=4,
        unit='LENGTH',
        subtype='DISTANCE'
    )

    @classmethod
    def poll(cls, context: Context) -> bool:
        return bool({ob for ob in context.selected_objects if is_mesh(ob) and not ob.hide_get()})

    def draw(self, context: Context):
        layout = self.layout
        
        layout.prop(self, "edgeline_thickness")
        layout.prop(self, "per_material_edgeline")
        layout.prop(self, "overwrite_existing_materials")
        layout.prop(self, "use_component_weights")
        
        if self.use_component_weights:
            layout.prop(self, "overwrite_existing_weights")
            
            row = layout.row(align=True)
            row.prop(self, "weight_min")
            row.prop(self, "weight_max")
            
            layout.prop(self, "component_size_metric")

    def has_existing_edgeline_setup(self, ob):
        for slot in ob.material_slots:
            if slot.material and "edgeline" in slot.material.name.lower():
                return True
        return False

    def calculate_component_weights(self, ob):
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        
        islands = []
        unvisited = set(bm.verts)
        
        while unvisited:
            island = set()
            queue = [unvisited.pop()]
            
            while queue:
                v = queue.pop(0)
                if v in island:
                    continue
                island.add(v)
                
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
                counted_faces = set()
                for v in island:
                    for face in v.link_faces:
                        if face not in counted_faces and all(fv in island for fv in face.verts):
                            area += face.calc_area()
                            counted_faces.add(face)
                size = area
            else:
                coords = [v.co for v in island]
                min_co = mathutils.Vector((min(c.x for c in coords), min(c.y for c in coords), min(c.z for c in coords)))
                max_co = mathutils.Vector((max(c.x for c in coords), max(c.y for c in coords), max(c.z for c in coords)))
                bbox_size = max_co - min_co
                size = bbox_size.x * bbox_size.y * bbox_size.z
            
            island_sizes.append(size)
        
        min_size = min(island_sizes) if island_sizes else 0
        max_size = max(island_sizes) if island_sizes else 0
        size_range = max_size - min_size
        
        vertex_weights = [0.0] * len(bm.verts)
        
        for island, size in zip(islands, island_sizes):
            if size_range > 0:
                normalized = (max_size - size) / size_range
                weight = self.weight_min + normalized * (self.weight_max - self.weight_min)
            else:
                weight = self.weight_max
            
            weight = round(weight, 2)
            
            for v in island:
                vertex_weights[v.index] = weight
        
        bm.free()
        return vertex_weights

    def create_edgeline_material(self, base_mat_name):
        edgeline_name = f"{base_mat_name}_edgeline"
        edgeline_mat = bpy.data.materials.get(edgeline_name)
        
        if edgeline_mat is None:
            edgeline_mat = bpy.data.materials.new(name=edgeline_name)
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

        edgeline_mat.vs.non_exportable_vgroup = 'Edgeline_Thickness'
        edgeline_mat.vs.do_not_export_faces_vgroup = True
        
        return edgeline_mat

    def execute(self, context: Context) -> Set:
        obs: set[Object] = {ob for ob in context.selected_objects if is_mesh(ob) and not ob.hide_get()}

        for ob in obs:
            bpy.context.view_layer.objects.active = ob

            scene = context.scene
            unit_scale = scene.unit_settings.scale_length or 1.0

            has_edgeline_setup = self.has_existing_edgeline_setup(ob)
            
            if has_edgeline_setup and not self.overwrite_existing_materials:
                pass
            else:
                if self.per_material_edgeline:
                    original_materials = []
                    old_to_new_index = {}
                    
                    for old_idx, slot in enumerate(ob.material_slots):
                        mat = slot.material
                        if mat and not mat.name.endswith("_edgeline"):
                            if mat not in original_materials:
                                original_materials.append(mat)
                            new_idx = original_materials.index(mat)
                            old_to_new_index[old_idx] = new_idx
                        else:
                            old_to_new_index[old_idx] = 0

                    mesh = ob.data
                    poly_materials = [poly.material_index for poly in mesh.polygons]

                    edgeline_materials = []
                    for mat in original_materials:
                        edgeline_mat = self.create_edgeline_material(mat.name if mat else "Material")
                        edgeline_materials.append(edgeline_mat)

                    ob.data.materials.clear()
                    for mat in original_materials:
                        ob.data.materials.append(mat)
                    for mat in edgeline_materials:
                        ob.data.materials.append(mat)

                    for poly_idx, old_mat_idx in enumerate(poly_materials):
                        if old_mat_idx in old_to_new_index:
                            mesh.polygons[poly_idx].material_index = old_to_new_index[old_mat_idx]
                    
                    material_offset = len(original_materials)
                else:
                    edgeline_mat = next((mat for mat in bpy.data.materials if mat.name == "edgeline"), None)
                    
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

                    edgeline_mat.vs.non_exportable_vgroup = 'Edgeline_Thickness'
                    edgeline_mat.vs.do_not_export_faces_vgroup = True

                    mesh = ob.data
                    poly_materials = [poly.material_index for poly in mesh.polygons]
                    
                    old_to_new_index = {}
                    non_edgeline_materials = []
                    
                    for old_idx, slot in enumerate(ob.material_slots):
                        mat = slot.material
                        if mat and "edgeline" not in mat.name.lower():
                            if mat not in non_edgeline_materials:
                                non_edgeline_materials.append(mat)
                            new_idx = non_edgeline_materials.index(mat)
                            old_to_new_index[old_idx] = new_idx
                        else:
                            old_to_new_index[old_idx] = 0
                    
                    ob.data.materials.clear()
                    
                    for mat in non_edgeline_materials:
                        ob.data.materials.append(mat)
                    
                    original_mat_count = len(non_edgeline_materials)
                    
                    for _ in range(original_mat_count):
                        ob.data.materials.append(edgeline_mat)
                    
                    for poly_idx, old_mat_idx in enumerate(poly_materials):
                        if old_mat_idx in old_to_new_index:
                            mesh.polygons[poly_idx].material_index = old_to_new_index[old_mat_idx]
                    
                    material_offset = original_mat_count

            solid = ob.modifiers.get("Toon_Edgeline") or ob.modifiers.new(name="Toon_Edgeline", type="SOLIDIFY")
            filter_vgroup = ob.vertex_groups.get('Edgeline_Thickness')
            vgroup_exists = filter_vgroup is not None
            
            if filter_vgroup is None:
                filter_vgroup = ob.vertex_groups.new(name='Edgeline_Thickness')
            
            solid.use_rim = False
            solid.thickness = -(self.edgeline_thickness / 1000.0) / unit_scale
            if not has_edgeline_setup or self.overwrite_existing_materials:
                solid.material_offset = material_offset
            solid.use_flip_normals = True
            solid.vertex_group = filter_vgroup.name
            solid.invert_vertex_group = True

            should_calculate_weights = (not vgroup_exists) or (vgroup_exists and self.overwrite_existing_weights)
            
            if self.use_component_weights and should_calculate_weights:
                vertex_weights = self.calculate_component_weights(ob)
                for i, weight in enumerate(vertex_weights):
                    if weight > 0:
                        final_weight = round(weight, 2)
                        filter_vgroup.add([i], final_weight, 'REPLACE')

        return {"FINISHED"}