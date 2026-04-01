import bpy, bmesh, mathutils
from bpy.types import UILayout, Context, Object, Operator, Mesh
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty, IntProperty

from .common import KITSUNE_PT_ToolSubPanel
from ..kitsunetools.commonutils import draw_wrapped_texts, is_armature, is_mesh, preserve_context_mode
from ..kitsunetools.meshutils import clean_unused_shapekeys, remove_unused_vertexgroups
from ..utils import hasShapes, get_id, image_channels

class TOOLS_PT_Mesh(KITSUNE_PT_ToolSubPanel):
    bl_label = "Mesh"
    
    def draw(self, context : Context) -> None:
        layout = self.layout
        box = layout.box()
        
        if is_mesh(context.active_object) or is_armature(context.active_object): pass
        else:
            draw_wrapped_texts(box,get_id("panel_select_mesh"),max_chars=40 , icon='HELP')
            return
        
        box1 = box.box()
        col = box1.column(align=True)
        col.label(text='Optimization')
        col.operator(TOOLS_OT_CleanShapeKeys.bl_idname, icon='SHAPEKEY_DATA')
        col.operator(TOOLS_OT_RemoveUnusedVertexGroups.bl_idname, icon='GROUP_VERTEX')
        col.operator(TOOLS_OT_Delete_Faces_by_ImageMask.bl_idname, icon='UV_FACESEL')
        col.operator(TOOLS_OT_CleanDuplicateMaterials.bl_idname, icon='UV_FACESEL')
        
        box1 = box.box()
        col = box1.column(align=True)
        col.label(text='Selection')
        col.operator(TOOLS_OT_SelectShapekeyVets.bl_idname, icon='VERTEXSEL')
        col.operator(TOOLS_OT_Select_Faces_by_ImageMask.bl_idname, icon='RESTRICT_SELECT_OFF')
        
        box1 = box.box()
        col = box1.column(align=True)
        col.label(text='Modifiers')
        col.operator(TOOLS_OT_AddToonEdgeLine.bl_idname, icon='MOD_SOLIDIFY', text=TOOLS_OT_AddToonEdgeLine.bl_label + ' (DEPRECATED)')
        col.operator(TOOLS_OT_transfer_topology_shapekeys.bl_idname, icon='MOD_DATA_TRANSFER')
        col.operator(TOOLS_OT_unlock_all_vertexgroups.bl_idname, icon='UNLOCKED')


class TOOLS_OT_CleanShapeKeys(Operator):
    bl_idname = 'kitsunetools.clean_shape_keys'
    bl_label = 'Clean Shape Keys'
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool(is_mesh(context.active_object) and hasShapes(context.active_object, valid_only=True))
    
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
    bl_idname = 'kitsunetools.select_shapekey_vertices'
    bl_label = 'Select Shapekey Vertices'
    bl_options = {'REGISTER', 'UNDO'}

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
        ob  = context.active_object
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
    bl_idname = "kitsunetools.remove_unused_vertexgroups"
    bl_label = "Clean Unused Vertex Groups"
    bl_options = {'REGISTER', 'UNDO'}
    
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


# This is now replaced with an 'Export' version
# NOTE: Do note use this in conjunction with the new version!!
EDGELINE_PROP = "toon_edgeline_thickness"

class TOOLS_OT_AddToonEdgeLine(Operator):
    bl_idname = "kitsunetools.add_toon_edgeline"
    bl_label = "Add Black Toon Edgeline"
    bl_options = {"REGISTER", "UNDO"}

    per_material_edgeline: BoolProperty(name="Per Material Edgeline", default=False)
    overwrite_existing_materials: BoolProperty(name="Overwrite Existing Materials", default=True)
    use_component_weights: BoolProperty(name="Use Component Weights", default=True)
    overwrite_existing_weights: BoolProperty(name="Overwrite Existing Weights", default=False)
    weight_min: FloatProperty(name="Min Weight", default=0.3, min=0.0, max=1.0)
    weight_max: FloatProperty(name="Max Weight", default=0.8, min=0.0, max=1.0)
    
    component_size_metric: EnumProperty(
        name="Size Metric",
        items=[
            ('VOLUME', "Volume", "Bounding box volume"),
            ('AREA', "Surface Area", "Total face area"),
            ('VERTICES', "Vertex Count", "Number of vertices"),
        ],
        default='AREA',
    )

    edgeline_thickness: FloatProperty(
        name="Edgeline Thickness",
        default=0.15,
        min=0.0,
        unit='LENGTH',
        subtype='DISTANCE',
    )

    @classmethod
    def poll(cls, context: Context):
        return context.mode == 'OBJECT' and any(obj.type == 'MESH' for obj in context.selected_objects)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "edgeline_thickness")
        layout.prop(self, "per_material_edgeline")
        layout.prop(self, "overwrite_existing_materials")
        layout.prop(self, "use_component_weights")
        if self.use_component_weights:
            box = layout.box()
            box.prop(self, "overwrite_existing_weights")
            box.prop(self, "weight_min")
            box.prop(self, "weight_max")
            box.prop(self, "component_size_metric")

    def _get_edgeline_mat(self, name: str):
        mat = bpy.data.materials.get(name)
        if not mat:
            mat = bpy.data.materials.new(name=name)
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            nodes.clear()
            node_em = nodes.new('ShaderNodeEmission')
            node_em.inputs[0].default_value = (0, 0, 0, 1)
            node_out = nodes.new('ShaderNodeOutputMaterial')
            mat.node_tree.links.new(node_em.outputs[0], node_out.inputs[0])
            mat.vs.face_export_filter = 'BY_VGROUP'
            mat.vs.non_exportable_vgroup = "Edgeline_Thickness"
        
        mat.use_backface_culling = True
        mat.use_backface_culling_shadow = True
        return mat

    def _apply_island_weights(self, ob, vg):
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        
        islands = []
        verts_to_visit = set(bm.verts)
        
        while verts_to_visit:
            start_v = next(iter(verts_to_visit))
            island = [start_v]
            verts_to_visit.remove(start_v)
            
            # Simple BFS/DFS to find all connected verts
            stack = [start_v]
            while stack:
                v = stack.pop()
                for edge in v.link_edges:
                    other_v = edge.other_vert(v)
                    if other_v in verts_to_visit:
                        verts_to_visit.remove(other_v)
                        island.append(other_v)
                        stack.append(other_v)
            islands.append(island)

        if not islands:
            bm.free()
            return

        island_data = []
        for island_verts in islands:
            if self.component_size_metric == 'VERTICES':
                size = len(island_verts)
            elif self.component_size_metric == 'AREA':
                # Calculate area of faces where all verts belong to this island
                island_set = set(island_verts)
                size = sum(f.calc_area() for v in island_verts for f in v.link_faces 
                           if all(fv in island_set for fv in f.verts))
            else: # VOLUME
                coords = [v.co for v in island_verts]
                hi = mathutils.Vector((max(c.x for c in coords), max(c.y for c in coords), max(c.z for c in coords)))
                lo = mathutils.Vector((min(c.x for c in coords), min(c.y for c in coords), min(c.z for c in coords)))
                size = (hi.x - lo.x) * (hi.y - lo.y) * (hi.z - lo.z)
            island_data.append((island_verts, size))

        sizes = [d[1] for d in island_data]
        min_s, max_s = min(sizes), max(sizes)
        s_range = max_s - min_s

        for verts, size in island_data:
            weight = self.weight_max
            if s_range > 0:
                # Normalizing: Smaller = Higher Weight (Thicker)
                factor = (max_s - size) / s_range
                weight = self.weight_min + (factor * (self.weight_max - self.weight_min))
            
            for v in verts:
                vg.add([v.index], weight, 'REPLACE')
        
        bm.free()

    def _process_object(self, context, ob: Object, unit_scale: float):
        if self.overwrite_existing_materials:
            # Using low-level data access is safer for multiple objects
            for i in reversed(range(len(ob.material_slots))):
                slot = ob.material_slots[i]
                if slot.material and "edgeline" in slot.material.name.lower():
                    ob.active_material_index = i
                    bpy.ops.object.material_slot_remove()

        original_slot_count = len(ob.material_slots)
        if original_slot_count == 0: return

        if self.per_material_edgeline:
            for i in range(original_slot_count):
                base_mat = ob.material_slots[i].material
                name = f"{base_mat.name}_edgeline" if base_mat else "edgeline"
                ob.data.materials.append(self._get_edgeline_mat(name))
        else:
            main_edge = self._get_edgeline_mat("edgeline")
            for _ in range(original_slot_count):
                ob.data.materials.append(main_edge)

        vg_name = 'Edgeline_Thickness'
        vg = ob.vertex_groups.get(vg_name)
        vg_existed = vg is not None
        if not vg:
            vg = ob.vertex_groups.new(name=vg_name)

        if self.use_component_weights and (not vg_existed or self.overwrite_existing_weights):
            self._apply_island_weights(ob, vg)

        mod_name = "Toon_Edgeline"
        solid = ob.modifiers.get(mod_name) or ob.modifiers.new(name=mod_name, type='SOLIDIFY')
        solid.use_rim = False
        solid.use_flip_normals = True
        solid.material_offset = original_slot_count
        solid.vertex_group = vg.name
        solid.invert_vertex_group = True
        
        ob[EDGELINE_PROP] = self.edgeline_thickness
        self._setup_driver(ob, solid, unit_scale)

    def _setup_driver(self, ob, modifier, unit_scale):
        modifier.driver_remove("thickness")
        fcurve = modifier.driver_add("thickness")
        drv = fcurve.driver
        drv.type = 'SCRIPTED'
        var = drv.variables.new()
        var.name = "t"
        var.type = 'SINGLE_PROP'
        var.targets[0].id = ob
        var.targets[0].data_path = f'["{EDGELINE_PROP}"]'
        drv.expression = f"-(t / 1000.0) / {unit_scale}"

    def execute(self, context) -> set:
        unit_scale = context.scene.unit_settings.scale_length
        selected_meshes = [o for o in context.selected_objects if o.type == 'MESH']
        
        with preserve_context_mode(context.view_layer.objects.active, 'OBJECT'):
            for ob in selected_meshes:
                context.view_layer.objects.active = ob
                self._process_object(context, ob, unit_scale)
            
        return {'FINISHED'}


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
    bl_idname= "kitsunetools.delete_face_by_image_mask"
    bl_label= "Delete Face by Image Mask"
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
        return context.mode in ['OBJECT', 'EDIT_MESH'] and is_mesh(context.active_object) and hasattr(context.active_object.data, 'uv_layers')
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400)
    
    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.use_property_split = True
        col.use_property_decorate = False
        
        col.prop_search(self, "image_mask", bpy.data, "images")

        if context.active_object and context.active_object.data and hasattr(context.active_object.data, 'materials'):
             col.prop_search(self, "material_name", context.active_object.data, "materials")
        
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
    bl_idname= "kitsunetools.select_faces_by_image_mask"
    bl_label= "Select Faces by Image Mask"
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
        return context.mode == 'EDIT_MESH' and is_mesh(context.active_object) and hasattr(context.active_object.data, 'uv_layers')

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
    

class TOOLS_OT_transfer_topology_shapekeys(bpy.types.Operator):
    bl_idname = "kitsunetools.transfer_topology_shapekeys"
    bl_label = "Transfer Topology Shape Keys"
    bl_description = "Transfer vertex positions from selected objects to active object as shape keys"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and 
                context.active_object.type == 'MESH' and
                len(context.selected_objects) > 1)
    
    def check_topology_match(self, mesh1, mesh2):
        if len(mesh1.vertices) != len(mesh2.vertices):
            return False
        if len(mesh1.edges) != len(mesh2.edges):
            return False
        if len(mesh1.polygons) != len(mesh2.polygons):
            return False
        return True
    
    def extract_shape_name(self, source_name, active_name):
        min_len = min(len(source_name), len(active_name))
        
        for i in range(min_len):
            if source_name[i] != active_name[i]:
                suffix = source_name[i:]
                return suffix if suffix else source_name
        
        if len(source_name) > len(active_name):
            return source_name[min_len:]
        
        return source_name
    
    def execute(self, context):
        active_obj = context.active_object
        selected_objects = [obj for obj in context.selected_objects if obj != active_obj and obj.type == 'MESH']
        
        if not selected_objects:
            self.report({'WARNING'}, "No other mesh objects selected")
            return {'CANCELLED'}
        
        active_mesh = active_obj.data
        
        if not active_mesh.shape_keys:
            basis = active_obj.shape_key_add(name="Basis", from_mix=False)
            basis.interpolation = 'KEY_LINEAR'
        
        transferred_count = 0
        skipped_count = 0
        skipped_names = []
        
        for source_obj in selected_objects:
            source_mesh = source_obj.data
            
            if not self.check_topology_match(active_mesh, source_mesh):
                skipped_names.append(source_obj.name)
                skipped_count += 1
                continue
            
            shape_key_name = self.extract_shape_name(source_obj.name, active_obj.name)
            counter = 1
            original_name = shape_key_name
            while shape_key_name in active_mesh.shape_keys.key_blocks:
                shape_key_name = f"{original_name}.{counter:03d}"
                counter += 1
            
            new_shape_key = active_obj.shape_key_add(name=shape_key_name, from_mix=False)
            new_shape_key.interpolation = 'KEY_LINEAR'
            new_shape_key.value = 0.0
            
            for i, vert in enumerate(source_mesh.vertices):
                new_shape_key.data[i].co = vert.co
            
            transferred_count += 1
        
        if skipped_count > 0:
            skipped_list = ", ".join(skipped_names)
            self.report({'WARNING'}, f"Topology mismatch - skipped: {skipped_list}")
        
        if transferred_count > 0:
            self.report({'INFO'}, f"Transferred {transferred_count} shape key(s)")
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "No shape keys transferred")
            return {'CANCELLED'}
    
        
class TOOLS_OT_unlock_all_vertexgroups(bpy.types.Operator):
    bl_idname = "kitsunetools.unlock_all_vertexgroups"
    bl_label = "Unlock All Vertex Groups"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and 
                context.active_object.type == 'MESH')
    
    def execute(self, context):
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']

        unlocked_count = 0

        for mesh in selected_objects:
            vgroups = mesh.vertex_groups
            for vgroup in vgroups:

                if vgroup.lock_weight:
                    vgroup.lock_weight = False
                    unlocked_count += 1
                
        self.report({'INFO'}, f"Unlocked {unlocked_count} vertex group(s)")
        return {'FINISHED'}


class TOOLS_OT_CleanDuplicateMaterials(Operator):
    bl_idname = "kitsunetools.clean_duplicate_materials"
    bl_label = "Clean Duplicate Materials"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        selected_meshes = [o for o in context.selected_objects if o.type == 'MESH']
        materials_remapped = 0

        for obj in selected_meshes:
            if not obj.data.materials:
                continue

            for slot in obj.material_slots:
                if not slot.material:
                    continue

                mat_name = slot.material.name
                parts = mat_name.rsplit('.', 1)
                if len(parts) == 2 and parts[1].isdigit():
                    base_name = parts[0]
                    if base_name in bpy.data.materials:
                        slot.material = bpy.data.materials[base_name]
                        materials_remapped += 1

        self.report({'INFO'}, f"Remapped {materials_remapped} duplicate material(s)")
        return {'FINISHED'}