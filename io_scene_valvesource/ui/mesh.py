import bpy, bmesh, mathutils
from bpy.types import UILayout, Context, Object, Operator, Mesh
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty, IntProperty

from .common import KITSUNE_PT_ToolsPanel
from ..core.commonutils import draw_title_box_layout, draw_wrapped_texts, is_armature, is_mesh
from ..core.meshutils import clean_unused_shapekeys, remove_unused_vertexgroups
from ..utils import hasShapes, get_id, image_channels

class TOOLS_PT_Mesh(KITSUNE_PT_ToolsPanel):
    bl_label : str = "Mesh Tools"
    
    def draw(self, context : Context) -> None:
        layout = self.layout
        box = layout.box()
        
        if is_mesh(context.object) or is_armature(context.object): pass
        else:
            draw_wrapped_texts(box,get_id("panel_select_mesh"),max_chars=40 , icon='HELP')
            return
        
        box1 = box.box()
        col = box1.column(align=True)
        col.label(text='Optimization')
        col.operator(TOOLS_OT_CleanShapeKeys.bl_idname, icon='SHAPEKEY_DATA')
        col.operator(TOOLS_OT_RemoveUnusedVertexGroups.bl_idname, icon='GROUP_VERTEX')
        col.operator(TOOLS_OT_Delete_Faces_by_ImageMask.bl_idname, icon='UV_FACESEL')
        
        box1 = box.box()
        col = box1.column(align=True)
        col.label(text='Selection')
        col.operator(TOOLS_OT_SelectShapekeyVets.bl_idname, icon='VERTEXSEL')
        col.operator(TOOLS_OT_Select_Faces_by_ImageMask.bl_idname, icon='RESTRICT_SELECT_OFF')
        
        box1 = box.box()
        col = box1.column(align=True)
        col.label(text='Modifiers')
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
            
            deleted_sk = clean_unused_shapekeys(ob)
            
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
    bl_options : set = {'REGISTER', 'UNDO'}

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

    def execute(self, context : Context) -> set:
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
    bl_options : set = {'REGISTER', 'UNDO'}
    
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
    
    def execute(self, context : Context) -> set:
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
    bl_options: set = {"REGISTER", "UNDO"}

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
        return bool(context.mode == 'OBJECT' and {ob for ob in context.selected_objects if is_mesh(ob) and not ob.hide_get()})

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

    def execute(self, context: Context) -> set:
        obs: set[Object] = {ob for ob in context.selected_objects if is_mesh(ob) and not ob.hide_get()}

        for ob in obs:
            bpy.context.view_layer.objects.active = ob

            scene = context.scene
            unit_scale = scene.unit_settings.scale_length or 1.0

            has_edgeline_setup = self.has_existing_edgeline_setup(ob)
            
            if has_edgeline_setup and not self.overwrite_existing_materials:
                pass
            else:
                for i in range(len(ob.material_slots) - 1, -1, -1):
                    slot = ob.material_slots[i]
                    if slot.material and "edgeline" in slot.material.name.lower():
                        ob.active_material_index = i
                        bpy.ops.object.material_slot_remove()
                
                bpy.ops.object.material_slot_remove_unused()
                
                if self.per_material_edgeline:
                    original_slot_count = len(ob.material_slots)
                    edgeline_materials = []
                    
                    for slot in ob.material_slots:
                        mat = slot.material
                        if mat and not mat.name.endswith("_edgeline"):
                            edgeline_mat = self.create_edgeline_material(mat.name)
                        else:
                            edgeline_mat = self.create_edgeline_material("Material")
                        edgeline_materials.append(edgeline_mat)
                    
                    for edgeline_mat in edgeline_materials:
                        ob.data.materials.append(edgeline_mat)
                    
                    material_offset = original_slot_count
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

                    original_slot_count = len(ob.material_slots)
                    
                    for _ in range(original_slot_count):
                        ob.data.materials.append(edgeline_mat)
                    
                    material_offset = original_slot_count

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
    
class faces_by_imagemask():
    image_mask : StringProperty(name="Image Mask", default="")
    
    image_channel : EnumProperty(name='Channel', items=image_channels)
    
    invert_image_mask : BoolProperty(
        name="Invert Image Mask",
        default=False)

    exclude_selected_faces: BoolProperty(
        name="Exclude Selected Faces",
        description="Don't delete faces that are currently selected in Edit Mode",
        default=True
    )
    
    
class TOOLS_OT_Delete_Faces_by_ImageMask(Operator, faces_by_imagemask):
    bl_idname: str = "kitsunetools.delete_face_by_image_mask"
    bl_label: str = "Delete Face by Image Mask"
    bl_options: set = {"REGISTER", "UNDO"}
    
    material_name : StringProperty(
        name="Material",
        description="Only process faces assigned to this material. If empty, process all.",
        default="",
    )
    
    tolerance : FloatProperty(name='Tolerance', default=0.01, soft_min=0.00001,soft_max=0.03, precision=5)

    @classmethod
    def poll(cls, context):
        if bpy.data.images is None: return False
        return context.mode in ['OBJECT', 'EDIT_MESH'] and is_mesh(context.object) and hasattr(context.object.data, 'uv_layers')
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400)
    
    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.use_property_split = True
        col.use_property_decorate = False
        
        col.prop_search(self, "image_mask", bpy.data, "images")

        if context.object and context.object.data and hasattr(context.object.data, 'materials'):
             col.prop_search(self, "material_name", context.object.data, "materials")
        
        col.prop(self, "image_channel")
        col.prop(self, "invert_image_mask")

        if context.mode == 'EDIT_MESH':
            col.prop(self, "exclude_selected_faces")

        col.prop(self, "tolerance", slider=True)
    
    def execute(self, context) -> set:
        image = bpy.data.images.get(self.image_mask)
        if image is None:
            self.report({'WARNING'}, "Image not found")
            return {'CANCELLED'}

        is_editmode = (context.mode == 'EDIT_MESH')
        
        if is_editmode:
            objects_to_process = {context.edit_object}
        else:
            objects_to_process = {obj for obj in context.selected_objects if is_mesh(obj)}

        if not objects_to_process:
            self.report({'WARNING'}, "No suitable mesh selected")
            return {'CANCELLED'}

        pixels = list(image.pixels)
        img_width = image.size[0]
        img_height = image.size[1]
        channels = image.channels

        faces_deleted_total = 0

        for obj in objects_to_process:
            target_mat_index = -1
            if self.material_name:
                target_mat_index = obj.data.materials.find(self.material_name)
                if target_mat_index == -1:
                    self.report({'INFO'}, f"Material '{self.material_name}' not on '{obj.name}', skipping.")
                    continue
            
            if is_editmode:
                bm = bmesh.from_edit_mesh(obj.data)
            else:
                bm = bmesh.new()
                bm.from_mesh(obj.data)
            
            uv_layer = bm.loops.layers.uv.active
            if not uv_layer:
                self.report({'INFO'}, f"Object '{obj.name}' has no active UV layer, skipping.")
                if not is_editmode:
                    bm.free()
                continue
            
            bm.faces.ensure_lookup_table()

            faces_to_delete = []
            for face in bm.faces:
                if is_editmode and self.exclude_selected_faces and face.select:
                    continue

                if target_mat_index != -1 and face.material_index != target_mat_index:
                    continue
                
                avg_brightness = 0.0
                
                if not face.loops:
                    continue
                
                for loop in face.loops:
                    uv = loop[uv_layer].uv
                    
                    u = uv.x % 1.0
                    v = uv.y % 1.0
                    
                    px = int(u * (img_width - 1))
                    py = int(v * (img_height - 1))

                    px = max(0, min(img_width - 1, px))
                    py = max(0, min(img_height - 1, py))
                    
                    pix_index = (py * img_width + px) * channels
                    
                    brightness = 0.0
                    if pix_index + (channels - 1) < len(pixels):
                        if self.image_channel == 'GREY':
                            if channels >= 1:
                                brightness = pixels[pix_index] # Red channel is used for greyscale
                        else:
                            channel_map = {'R': 0, 'G': 1, 'B': 2, 'A': 3}
                            channel_index = channel_map.get(self.image_channel)
                            if channel_index is not None and channel_index < channels:
                                brightness = pixels[pix_index + channel_index]
                    
                    avg_brightness += brightness
                
                avg_brightness /= len(face.loops)
                
                should_delete = avg_brightness < self.tolerance
                if self.invert_image_mask:
                    should_delete = not should_delete

                if should_delete:
                    faces_to_delete.append(face)

            if faces_to_delete:
                faces_deleted_total += len(faces_to_delete)
                bmesh.ops.delete(bm, geom=faces_to_delete, context='FACES')

                if is_editmode:
                    bmesh.update_edit_mesh(obj.data)
                else:
                    bm.to_mesh(obj.data)
                    obj.data.update()
            
            if not is_editmode:
                bm.free()

        self.report({'INFO'}, f"Deleted {faces_deleted_total} faces.")
        return {'FINISHED'}


class TOOLS_OT_Select_Faces_by_ImageMask(Operator, faces_by_imagemask):
    bl_idname: str = "kitsunetools.select_faces_by_image_mask"
    bl_label: str = "Select Faces by Image Mask"
    bl_options: set = {"REGISTER", "UNDO"}

    min_white_threshold: IntProperty(
        name="Min White Threshold",
        description="Select faces where the average brightness is above this value (0-255)",
        default=175,
        min=0,
        max=255
    )
    
    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and is_mesh(context.object) and hasattr(context.object.data, 'uv_layers')

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.use_property_split = True
        col.use_property_decorate = False
        
        col.prop_search(self, "image_mask", bpy.data, "images")
        
        col.prop(self, "image_channel")
        col.prop(self, "invert_image_mask")
        col.prop(self, "exclude_selected_faces")
        col.prop(self, "min_white_threshold", slider=True)

    def execute(self, context) -> set:
        image = bpy.data.images.get(self.image_mask)
        if image is None:
            self.report({'WARNING'}, "Image not found")
            return {'CANCELLED'}

        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        
        uv_layer = bm.loops.layers.uv.active
        if not uv_layer:
            self.report({'INFO'}, f"Object '{obj.name}' has no active UV layer, skipping.")
            return {'CANCELLED'}
        
        pixels = list(image.pixels)
        img_width = image.size[0]
        img_height = image.size[1]
        channels = image.channels
        
        bm.faces.ensure_lookup_table()
        
        faces_selected_total = 0
        
        for face in bm.faces:
            if self.exclude_selected_faces and face.select:
                continue
            
            avg_brightness = 0.0
            
            if not face.loops:
                continue
            
            for loop in face.loops:
                uv = loop[uv_layer].uv
                
                u = uv.x % 1.0
                v = uv.y % 1.0
                
                px = int(u * (img_width - 1))
                py = int(v * (img_height - 1))
                
                px = max(0, min(img_width - 1, px))
                py = max(0, min(img_height - 1, py))
                
                pix_index = (py * img_width + px) * channels
                
                brightness = 0.0
                if pix_index + (channels - 1) < len(pixels):
                    if self.image_channel == 'GREY':
                        if channels >= 1:
                            brightness = pixels[pix_index] # Red channel is used for greyscale
                    else:
                        channel_map = {'R': 0, 'G': 1, 'B': 2, 'A': 3}
                        channel_index = channel_map.get(self.image_channel)
                        if channel_index is not None and channel_index < channels:
                            brightness = pixels[pix_index + channel_index]
                
                avg_brightness += brightness
            
            avg_brightness /= len(face.loops)
            
            avg_brightness_int = int(avg_brightness * 255)
            
            should_select = avg_brightness_int > self.min_white_threshold
            if self.invert_image_mask:
                should_select = not should_select
                
            if should_select:
                face.select = True
                faces_selected_total += 1

        bmesh.update_edit_mesh(obj.data)
        
        self.report({'INFO'}, f"Selected {faces_selected_total} faces.")
        return {'FINISHED'}