import bpy, os
from PIL import Image

from ..kitsunetools.commonutils import is_mesh


class KITSUNETOOLS_UL_nodes_to_bake(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)

        node = None
        for mat in bpy.data.materials:
            if mat.node_tree and item.node_name in mat.node_tree.nodes:
                node = mat.node_tree.nodes[item.node_name]
                break

        if node:
            if hasattr(node, 'node_tree') and node.node_tree:
                display_name = node.node_tree.name
            else:
                display_name = node.name
        else:
            display_name = item.node_name if item.node_name else "Select Node..."

        row.label(text=display_name, icon='NODE')
        if item.name:
            row.label(text=f"({item.name})")


class KITSUNETOOLS_UL_material_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if context.scene.vs.node_baker_material_listmode == 'ALL':
            mat = item
        else:
            mat = item.material

        if mat:
            layout.label(text=mat.name, icon_value=layout.icon(mat))
        else:
            layout.label(text="(empty slot)", icon='BLANK1')

    def filter_items(self, context, data, propname):
        if context.scene.vs.node_baker_material_listmode == 'ALL':
            items = list(bpy.data.materials)
            flt_flags = [self.bitflag_filter_item] * len(items)
            flt_neworder = list(range(len(items)))
        else:
            items = list(getattr(data, propname))
            flt_flags = [self.bitflag_filter_item if slot.material else 0 for slot in items]
            flt_neworder = list(range(len(items)))
        return flt_flags, flt_neworder


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

        scene_vs = context.scene.vs
        listmode = scene_vs.node_baker_material_listmode

        layout.row(align=True).prop(scene_vs, 'node_baker_material_listmode', expand=True)
        layout.label(text="Object Materials:")
        if listmode == 'ALL':
            layout.template_list(
                "KITSUNETOOLS_UL_material_list", "all_mats",
                bpy.data, "materials",
                scene_vs, "node_baker_material_list_index"
            )
            idx = scene_vs.node_baker_material_list_index
            mat = bpy.data.materials[idx] if 0 <= idx < len(bpy.data.materials) else None
        else:
            layout.template_list(
                "KITSUNETOOLS_UL_material_list", "active_slots",
                obj, "material_slots",
                obj, "active_material_index"
            )
            mat = obj.active_material

        if not mat or not mat.use_nodes:
            layout.label(text="Active material has no nodes", icon='INFO')
            return

        layout.separator()
        layout.label(text=f"Nodes: {mat.name}")
        row = layout.row()
        row.template_list("KITSUNETOOLS_UL_nodes_to_bake", "", mat.vs, "node_baker_list", mat.vs, "node_baker_list_index")
        
        col = row.column(align=True)
        col.operator(KITSUNETOOLS_OT_node_bake_add.bl_idname, icon='ADD', text="")
        col.operator(KITSUNETOOLS_OT_node_bake_remove.bl_idname, icon='REMOVE', text="")

        def _draw_split(box, label, prop_owner, prop_name, **kwargs):
            split = box.split(factor=0.4)
            split.alignment = 'RIGHT'
            split.label(text=label)
            split.prop(prop_owner, prop_name, text="", **kwargs)

        if len(mat.vs.node_baker_list) > 0 and mat.vs.node_baker_list_index < len(mat.vs.node_baker_list):
            item = mat.vs.node_baker_list[mat.vs.node_baker_list_index]
            box = layout.box()

            row = box.row(align=True)
            row.prop_search(item, "node_name", mat.node_tree, "nodes", text="", icon='NODE_SEL')

            _draw_split(box, "Suffix", item, "name")
            _draw_split(box, "Output", item, "socket_index")

            split = box.split(factor=0.4)
            split.alignment = 'RIGHT'
            split.label(text="")
            split.prop(item, "has_alpha_channel", text="Alpha Channel")

            if item.has_alpha_channel:
                _draw_split(box, "Alpha Out", item, "alpha_socket_index")

            col = box.column(align=True)
            row = col.row(align=True)
            split = row.split(factor=0.4)
            split.alignment = 'RIGHT'
            split.label(text="X Resolution" if not item.sync_y_with_x else "Resolution")
            sub = split.row(align=True)
            sub.prop(item, "resolution_x", text="")
            sub.prop(item, "sync_y_with_x", text="", icon='LOCKED' if item.sync_y_with_x else 'UNLOCKED', toggle=True, emboss=False)

            if not item.sync_y_with_x:
                row = col.row(align=True)
                split = row.split(factor=0.4)
                split.alignment = 'RIGHT'
                split.label(text="Y Resolution")
                sub = split.row(align=True)
                sub.prop(item, "resolution_y", text="")
                sub.label(icon='BLANK1')

            split = box.split(factor=0.4)
            split.alignment = 'RIGHT'
            split.label(text="")
            split.prop(item, "use_full_frame", text="Full Frame (No UV)")

        layout.separator()
        layout.prop(context.scene.vs, "node_baker_export_dir")
        layout.prop(context.scene.vs, "node_baker_file_format")

        row = layout.row(align=True)
        row.operator(KITSUNETOOLS_OT_node_bake_run.bl_idname, text="Bake Selected").all_items = False
        row.operator(KITSUNETOOLS_OT_node_bake_run.bl_idname, text="Bake All").all_items = True

        layout.operator(KITSUNETOOLS_OT_node_bake_all_materials.bl_idname, text="Bake All Materials", icon='MATERIAL')


class KITSUNETOOLS_OT_node_bake_add(bpy.types.Operator):
    bl_idname = "kitsunetools.node_bake_node_add"
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
    bl_idname = "kitsunetools.node_bake_node_remove"
    bl_label = "Remove Bake Item"
    bl_options = {'UNDO'}
    
    def execute(self, context) -> set:
        mat = context.active_object.active_material
        mat.vs.node_baker_list.remove(mat.vs.node_baker_list_index)
        mat.vs.node_baker_list_index = max(0, mat.vs.node_baker_list_index - 1)
        return {'FINISHED'}


def _run_bake_for_material(operator, context, obj, mat, export_path):
    items = list(mat.vs.node_baker_list)
    total = len(items)

    if total == 0:
        print(f"  [skip] '{mat.name}' has no items.")
        return

    for item_idx, item in enumerate(items):
        node = mat.node_tree.nodes.get(item.node_name)
        if not node:
            print(f"  [{item_idx + 1}/{total}] WARNING: Node '{item.node_name}' not found in '{mat.name}', skipping.")
            continue

        socket = node.outputs[int(item.socket_index)]
        suffix = item.name if item.name else socket.name
        filename = f"{mat.name}_{suffix}"

        print(f"  [{item_idx + 1}/{total}] Baking '{filename}' | node: '{node.name}' | socket: '{socket.name}'")

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
            print(f"    Baking color channel...")
            operator._process_bake(context, bake_obj, mat, node, int(item.socket_index), item, temp_col, save_alpha=item.has_alpha_channel)

            if item.has_alpha_channel:
                print(f"    Baking alpha channel (socket index: {item.alpha_socket_index})...")
                operator._process_bake(context, bake_obj, mat, node, int(item.alpha_socket_index), item, temp_alpha, force_colorspace='Non-Color')
                print(f"    Merging color + alpha...")
                operator._merge_with_pil(temp_col, temp_alpha, export_path, filename, context.scene.vs.node_baker_file_format)
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

        print(f"    Done -> {os.path.join(export_path, filename)}")
        operator.report({'INFO'}, f"Baked '{filename}' -> {os.path.join(export_path, filename)}")


class KITSUNETOOLS_OT_node_bake_run(bpy.types.Operator):
    bl_idname = "kitsunetools.node_bake_run"
    bl_label = "Run Node Bake"
    all_items: bpy.props.BoolProperty(default=False)

    def execute(self, context) -> set:
        obj = context.active_object
        mat = obj.active_material
        if not mat or not mat.node_tree: return {'CANCELLED'}

        vs = mat.vs
        items = list(vs.node_baker_list) if self.all_items else [vs.node_baker_list[vs.node_baker_list_index]]
        total = len(items)

        raw_path = bpy.path.abspath(context.scene.vs.node_baker_export_dir)
        export_path = os.path.normpath(raw_path)
        os.makedirs(export_path, exist_ok=True)

        print(f"\n[Node Baker] Starting bake: {total} item(s) from material '{mat.name}'")

        for item_idx, item in enumerate(items):
            node = mat.node_tree.nodes.get(item.node_name)
            if not node:
                print(f"  [{item_idx + 1}/{total}] WARNING: Node '{item.node_name}' not found, skipping.")
                continue

            socket = node.outputs[int(item.socket_index)]
            suffix = item.name if item.name else socket.name
            filename = f"{mat.name}_{suffix}"

            print(f"  [{item_idx + 1}/{total}] Baking '{filename}' | node: '{node.name}' | socket: '{socket.name}'")

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
                print(f"    Baking color channel...")
                self._process_bake(context, bake_obj, mat, node, int(item.socket_index), item, temp_col, save_alpha=item.has_alpha_channel)

                if item.has_alpha_channel:
                    print(f"    Baking alpha channel (socket index: {item.alpha_socket_index})...")
                    self._process_bake(context, bake_obj, mat, node, int(item.alpha_socket_index), item, temp_alpha, force_colorspace='Non-Color')
                    print(f"    Merging color + alpha...")
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

            print(f"    Done -> {os.path.join(export_path, filename)}")
            self.report({'INFO'}, f"Baked '{filename}' -> {os.path.join(export_path, filename)}")

        print(f"[Node Baker] Finished. {total} item(s) baked from '{mat.name}'.\n")
        return {'FINISHED'}

    def _process_bake(self, context, obj, mat, node, socket_idx, item, filepath, force_colorspace=None, save_alpha=False):
        ntree = mat.node_tree
        res_x = int(item.resolution_x)
        res_y = int(item.resolution_y) if not item.sync_y_with_x else res_x
        colorspace = force_colorspace if force_colorspace else item.color_space

        print(f"      _process_bake | res_x={res_x} | res_y={res_y} | colorspace='{colorspace}' | save_alpha={save_alpha}")

        bake_img = bpy.data.images.new("_temp_bake", width=res_x, height=res_y, alpha=save_alpha)
        bake_img.colorspace_settings.name = colorspace

        mat_out = next((n for n in ntree.nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output), None)
        if not mat_out:
            print(f"      ERROR: No active Material Output node in '{mat.name}'.")
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
            print(f"      Socket type VECTOR — inserting SeparateXYZ + CombineRGB.")
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

        print(f"      Running bpy.ops.object.bake...")
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj
        bpy.ops.object.bake(type='EMIT')

        if not save_alpha:
            pixels = list(bake_img.pixels)
            for i in range(3, len(pixels), 4):
                pixels[i] = 1.0
            bake_img.pixels = pixels

        bake_img.filepath_raw = os.path.normpath(filepath)
        bake_img.file_format = 'TARGA'
        bake_img.save()
        print(f"      Saved temp image -> '{filepath}'")

        for n in temp_nodes: ntree.nodes.remove(n)
        for f, t in old_links: ntree.links.new(f, t)
        bpy.data.images.remove(bake_img)

        scene.render.engine = old_engine
        scene.view_settings.view_transform = old_transform
        scene.render.image_settings.file_format = old_format

    def _merge_with_pil(self, col_path, alpha_path, export_dir, filename, fmt):
        print(f"      PIL merge: '{col_path}' + '{alpha_path}'")
        with Image.open(col_path).convert("RGBA") as base_img:
            with Image.open(alpha_path).convert("L") as alpha_mask:
                r, g, b, _ = base_img.split()
                final_rgba = Image.merge("RGBA", (r, g, b, alpha_mask))
                ext = ".png" if fmt == 'PNG' else ".tga"
                save_path = os.path.normpath(os.path.join(export_dir, filename + ext))
                final_rgba.save(save_path)
                print(f"      Merged image saved -> '{save_path}'")


class KITSUNETOOLS_OT_node_bake_all_materials(bpy.types.Operator):
    bl_idname = "kitsunetools.node_bake_all_materials"
    bl_label = "Bake All Materials"

    def invoke(self, context, event):
        if context.scene.vs.node_baker_material_listmode == 'ALL':
            return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

    def execute(self, context) -> set:
        obj = context.active_object
        if not obj or not is_mesh(obj):
            self.report({'ERROR'}, "No active mesh object.")
            return {'CANCELLED'}

        listmode = context.scene.vs.node_baker_material_listmode

        if listmode == 'ALL':
            material_slots = [
                type('S', (), {'material': m})()
                for m in bpy.data.materials
                if m.use_nodes and len(m.vs.node_baker_list) > 0
            ]
        else:
            material_slots = [slot for slot in obj.material_slots if slot.material and slot.material.use_nodes]
            
        total_mats = len(material_slots)

        if total_mats == 0:
            self.report({'WARNING'}, "No materials with node trees found on this object.")
            return {'CANCELLED'}

        raw_path = bpy.path.abspath(context.scene.vs.node_baker_export_dir)
        export_path = os.path.normpath(raw_path)
        os.makedirs(export_path, exist_ok=True)

        print(f"\n[Node Baker] Bake All Materials — '{obj.name}' | {total_mats} material(s)")
        print(f"[Node Baker] Export path: {export_path}")

        for mat_idx, slot in enumerate(material_slots):
            mat = slot.material
            total_items = len(mat.vs.node_baker_list)
            print(f"\n[Node Baker] Material [{mat_idx + 1}/{total_mats}]: '{mat.name}' | {total_items} item(s)")
            obj.active_material_index = mat_idx
            _run_bake_for_material(self, context, obj, mat, export_path)

        print(f"\n[Node Baker] All done. {total_mats} material(s) processed on '{obj.name}'.\n")
        self.report({'INFO'}, f"Baked all materials on '{obj.name}'.")
        return {'FINISHED'}

    def _process_bake(self, context, obj, mat, node, socket_idx, item, filepath, force_colorspace=None, save_alpha=False):
        return KITSUNETOOLS_OT_node_bake_run._process_bake(self, context, obj, mat, node, socket_idx, item, filepath, force_colorspace, save_alpha)

    def _merge_with_pil(self, col_path, alpha_path, export_dir, filename, fmt):
        return KITSUNETOOLS_OT_node_bake_run._merge_with_pil(self, col_path, alpha_path, export_dir, filename, fmt)