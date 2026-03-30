import bpy, os
from PIL import Image

from ..kitsunetools.commonutils import is_mesh


class KITSUNETOOLS_UL_node_queue(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.label(text=item.node_name if item.node_name else "Select Node...", icon='NODE')
        if item.name:
            row.label(text=f"({item.name})", icon='EDITMODE_HLT')


class KITSUNETOOLS_PT_node_baker(bpy.types.Panel):
    bl_label = "Node Baker"
    bl_idname = "KITSUNETOOLS_PT_node_baker"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "KitsuneSrcTool"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        
        if not is_mesh(obj):
            layout.label(text="Select a Mesh Object", icon='ERROR')
            return

        layout.label(text="Object Materials:")
        layout.template_list("UI_UL_list", "material_slots", obj, "material_slots", obj, "active_material_index")

        mat = obj.active_material
        if not mat or not mat.use_nodes:
            layout.label(text="Active material has no nodes", icon='INFO')
            return

        layout.separator()
        layout.label(text=f"Bake Queue: {mat.name}")
        row = layout.row()
        row.template_list("KITSUNETOOLS_UL_node_queue", "", mat.vs, "node_baker_list", mat.vs, "node_baker_list_index")
        
        col = row.column(align=True)
        col.operator(KITSUNETOOLS_OT_node_bake_add.bl_idname, icon='ADD', text="")
        col.operator(KITSUNETOOLS_OT_node_bake_remove.bl_idname, icon='REMOVE', text="")

        if len(mat.vs.node_baker_list) > 0 and mat.vs.node_baker_list_index < len(mat.vs.node_baker_list):
            item = mat.vs.node_baker_list[mat.vs.node_baker_list_index]
            box = layout.box()
            box.prop_search(item, "node_name", mat.node_tree, "nodes", text="Target Node", icon='NODE_SEL')

            box.prop(item, "name", text="Filename Suffix")
            box.prop(item, "socket_index", text="Output")

            box.prop(item, "has_alpha_channel")
            if item.has_alpha_channel:
                box.prop(item,'alpha_socket_index')
            
            col = box.column(align=True)
            col.prop(item, "resolution")
            col.prop(item, "color_space")
            box.prop(item, "use_full_frame")

        layout.separator()
        layout.prop(context.scene.vs, "node_baker_export_dir")
        layout.prop(context.scene.vs, "node_baker_file_format")

        row = layout.row(align=True)
        row.operator(KITSUNETOOLS_OT_node_bake_run.bl_idname, text="Bake Selected").all_items = False
        row.operator(KITSUNETOOLS_OT_node_bake_run.bl_idname, text="Bake All").all_items = True


class KITSUNETOOLS_OT_node_bake_add(bpy.types.Operator):
    bl_idname = "kitsunetools.node_bake_queue_add"
    bl_label = "Add Bake Item"
    bl_options = {'UNDO'}
    
    def execute(self, context) -> set:
        mat = context.active_object.active_material
        node = context.space_data.node_tree.nodes.active
        item = mat.vs.node_baker_list.add()
        if node: item.node_name = node.name
        mat.vs.node_baker_list_index = len(mat.vs.node_baker_list) - 1
        return {'FINISHED'}


class KITSUNETOOLS_OT_node_bake_remove(bpy.types.Operator):
    bl_idname = "kitsunetools.node_bake_queue_remove"
    bl_label = "Remove Bake Item"
    bl_options = {'UNDO'}
    
    def execute(self, context) -> set:
        mat = context.active_object.active_material
        mat.vs.node_baker_list.remove(mat.vs.node_baker_list_index)
        mat.vs.node_baker_list_index = max(0, mat.vs.node_baker_list_index - 1)
        return {'FINISHED'}


class KITSUNETOOLS_OT_node_bake_run(bpy.types.Operator):
    bl_idname = "kitsunetools.node_bake_run"
    bl_label = "Run Node Bake"
    all_items: bpy.props.BoolProperty(default=False)

    def execute(self, context) -> set:
        obj = context.active_object
        mat = obj.active_material
        if not mat or not mat.node_tree: return {'CANCELLED'}

        vs = mat.vs
        items = vs.node_baker_list if self.all_items else [vs.node_baker_list[vs.node_baker_list_index]]

        raw_path = bpy.path.abspath(context.scene.vs.node_baker_export_dir)
        export_path = os.path.normpath(raw_path)
        os.makedirs(export_path, exist_ok=True)

        for item in items:
            node = mat.node_tree.nodes.get(item.node_name)
            if not node: continue

            socket = node.outputs[int(item.socket_index)]
            suffix = item.name if item.name else socket.name
            filename = f"{mat.name}_{suffix}"

            temp_col = os.path.join(export_path, f"_temp_col_{mat.name}.tga")
            temp_alpha = os.path.join(export_path, f"_temp_alpha_{mat.name}.tga")

            if item.use_full_frame:
                prev_active = context.view_layer.objects.active
                prev_selected = list(context.selected_objects)
                bpy.ops.object.select_all(action='DESELECT')
                bpy.ops.mesh.primitive_plane_add(size=2)
                temp_plane = context.active_object
                temp_plane.data.materials.append(mat)
                bake_obj = temp_plane
            else:
                temp_plane = None
                bake_obj = obj

            try:
                self._process_bake(context, bake_obj, mat, node, int(item.socket_index), item, temp_col)

                if item.has_alpha_channel:
                    self._process_bake(context, bake_obj, mat, node, int(item.alpha_socket_index), item, temp_alpha, force_colorspace='Non-Color')
                    self._merge_with_pil(temp_col, temp_alpha, export_path, filename, context.scene.vs.node_baker_file_format)
                else:
                    ext = ".png" if context.scene.vs.node_baker_file_format == 'PNG' else ".tga"
                    final_path = os.path.normpath(os.path.join(export_path, filename + ext))
                    if os.path.exists(final_path): os.remove(final_path)
                    os.rename(temp_col, final_path)

            finally:
                for p in [temp_col, temp_alpha]:
                    if os.path.exists(p):
                        try: os.remove(p)
                        except: pass
                if temp_plane:
                    bpy.data.objects.remove(temp_plane, do_unlink=True)
                    for o in prev_selected: o.select_set(True)
                    context.view_layer.objects.active = prev_active

            self.report({'INFO'}, f"Baked '{filename}' → {os.path.join(export_path, filename)}")

        return {'FINISHED'}

    def _process_bake(self, context, obj, mat, node, socket_idx, item, filepath, force_colorspace=None):
        ntree = mat.node_tree
        res = int(item.resolution)
        colorspace = force_colorspace if force_colorspace else item.color_space

        bake_img = bpy.data.images.new("_temp_bake", width=res, height=res, alpha=True)
        bake_img.colorspace_settings.name = colorspace

        mat_out = next((n for n in ntree.nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output), None)
        if not mat_out:
            bpy.data.images.remove(bake_img)
            return

        temp_nodes = []
        img_node = ntree.nodes.new('ShaderNodeTexImage')
        img_node.image = bake_img
        temp_nodes.append(img_node)
        ntree.nodes.active = img_node

        emit = ntree.nodes.new('ShaderNodeEmission')
        temp_nodes.append(emit)

        old_links = []
        surf_in = mat_out.inputs['Surface']
        for link in surf_in.links:
            old_links.append((link.from_socket, link.to_socket))
            ntree.links.remove(link)

        ntree.links.new(emit.outputs[0], surf_in)

        socket = node.outputs[socket_idx]
        if socket.type == 'VECTOR':
            sep = ntree.nodes.new('ShaderNodeSeparateXYZ')
            comb = ntree.nodes.new('ShaderNodeCombineRGB')
            temp_nodes.extend([sep, comb])
            ntree.links.new(socket, sep.inputs[0])
            ntree.links.new(sep.outputs[0], comb.inputs[0])
            ntree.links.new(sep.outputs[1], comb.inputs[1])
            ntree.links.new(sep.outputs[2], comb.inputs[2])
            ntree.links.new(comb.outputs[0], emit.inputs['Color'])
        else:
            ntree.links.new(socket, emit.inputs['Color'])

        scene = context.scene
        old_engine = scene.render.engine
        old_transform = scene.view_settings.view_transform
        old_format = scene.render.image_settings.file_format

        scene.render.engine = 'CYCLES'
        scene.cycles.bake_type = 'EMIT'
        scene.view_settings.view_transform = 'Standard'

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj
        bpy.ops.object.bake(type='EMIT')

        bake_img.filepath_raw = os.path.normpath(filepath)
        bake_img.file_format = 'TARGA'
        bake_img.save()

        for n in temp_nodes: ntree.nodes.remove(n)
        for f, t in old_links: ntree.links.new(f, t)
        bpy.data.images.remove(bake_img)

        scene.render.engine = old_engine
        scene.view_settings.view_transform = old_transform
        scene.render.image_settings.file_format = old_format

    def _merge_with_pil(self, col_path, alpha_path, export_dir, filename, fmt):
        from PIL import Image
        with Image.open(col_path).convert("RGBA") as base_img:
            with Image.open(alpha_path).convert("L") as alpha_mask:
                r, g, b, _ = base_img.split()
                final_rgba = Image.merge("RGBA", (r, g, b, alpha_mask))
                ext = ".png" if fmt == 'PNG' else ".tga"
                save_path = os.path.normpath(os.path.join(export_dir, filename + ext))
                final_rgba.save(save_path)