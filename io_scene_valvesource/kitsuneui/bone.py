import bpy, math
from bpy.props import FloatProperty, BoolProperty, IntProperty, EnumProperty
from bpy.types import Context, Operator, Event
from mathutils import Vector

from ..kitsunetools.commonutils import(
    is_armature, is_mesh, draw_title_box_layout, draw_wrapped_texts,
    get_armature, get_selected_bones, preserve_context_mode, get_armature_meshes
)

from ..kitsunetools.armatureutils import(
    subdivide_bone, remove_bone, merge_bones, centralize_bone_pairs
)

from ..utils import get_id
from .common import KITSUNE_PT_ToolSubPanel

class TOOLS_PT_Bone(KITSUNE_PT_ToolSubPanel):
    bl_label= "Bone"

    def draw(self, context: Context) -> None:
        layout = self.layout
        bx = layout.box()
        
        armature = get_armature(context.active_object)
        
        if not (is_armature(armature) or is_mesh(armature)):
            draw_wrapped_texts(bx, get_id("panel_select_armature"), max_chars=40, icon='HELP')
            return
        
        scene_vs = context.scene.vs
        
        main_col = bx.column(align=False)
        
        # Bone Merging Section
        merge_box = draw_title_box_layout(main_col, text='Bone Merging', icon='AUTOMERGE_ON', align=True)
        
        merge_row = merge_box.row(align=True)
        merge_row.scale_y = 1.3
        merge_row.operator(TOOLS_OT_MergeBones.bl_idname, text='To Active').mode = 'TO_ACTIVE'
        merge_row.operator(TOOLS_OT_MergeBones.bl_idname, text='To Parent').mode = 'TO_PARENT'
        
        merge_box.separator(factor=0.5)
        
        options_col = merge_box.column(align=True)
        options_col.scale_y = 0.9
        options_col.label(text='Merge Mode')
        splitoption = options_col.split(align=True)
        splitoption.prop(scene_vs, 'merge_bone_options_active', expand=True)
        splitoption.prop(scene_vs, 'merge_bone_options_parent', expand=True)
        options_col.prop(scene_vs, 'visible_mesh_only')
        
        main_col.separator()
        
        # Bone Alignment Section
        align_box = draw_title_box_layout(main_col, text='Bone Alignment', icon='ORIENTATION_VIEW', align=True)
        
        align_box.operator(TOOLS_OT_ReAlignBones.bl_idname, icon='ALIGN_JUSTIFY', text='Re-Align Bones')
        
        align_box.separator(factor=0.5)
        
        copy_row = align_box.row(align=True)
        copy_row.scale_y = 1.3
        copy_row.operator(TOOLS_OT_CopyTargetRotation.bl_idname, text='Copy Active').copy_source = 'ACTIVE'
        copy_row.operator(TOOLS_OT_CopyTargetRotation.bl_idname, text='Copy Parent').copy_source = 'PARENT'
        
        align_box.separator(factor=0.5)
        
        align_box.label(text='Point to Axis:')
        copy_row = align_box.row(align=True)
        copy_row.scale_y = 1.3
        copy_row.operator(TOOLS_OT_align_bone_to_axis.bl_idname, text='X').axis = 'X'
        copy_row.operator(TOOLS_OT_align_bone_to_axis.bl_idname, text='Y').axis = 'Y'
        copy_row.operator(TOOLS_OT_align_bone_to_axis.bl_idname, text='Z').axis = 'Z'
        copy_row.operator(TOOLS_OT_align_bone_to_axis.bl_idname, text='-X').axis = '-X'
        copy_row.operator(TOOLS_OT_align_bone_to_axis.bl_idname, text='-Y').axis = '-Y'
        copy_row.operator(TOOLS_OT_align_bone_to_axis.bl_idname, text='-Z').axis = '-Z'
        
        main_col.separator()
        
        # Bone Modifiers Section
        mod_box = draw_title_box_layout(main_col, text='Bone Modifiers', icon='MODIFIER', align=True)
        mod_box.operator(TOOLS_OT_SubdivideBone.bl_idname, icon='MOD_SUBSURF', text=TOOLS_OT_SubdivideBone.bl_label).weights_only = False
        mod_box.operator(TOOLS_OT_FlipBone.bl_idname, icon='ARROW_LEFTRIGHT')
        mod_box.operator(TOOLS_OT_CreateCenterBone.bl_idname, icon='BONE_DATA')
        mod_box.operator(TOOLS_OT_SplitActiveWeightLinear.bl_idname, icon='SPLIT_VERTICAL')
       
        
class TOOLS_OT_CopyTargetRotation(Operator):
    bl_idname = "kitsunetools.copy_target_bone_rotation"
    bl_label = "Copy Parent/Active Rotation"
    bl_options = {'REGISTER', 'UNDO'}

    copy_source: EnumProperty(
        name="Copy From",
        description="Choose which bone to copy orientation from",
        items=[
            ('PARENT', "Parent", "Copy rotation from parent bone"),
            ('ACTIVE', "Active", "Copy rotation from active bone"),
        ],
        default='PARENT'
    )

    include_axes: EnumProperty(
        name="Include Axes",
        description="Which axes to include when copying rotation",
        items=[
            ('X', "X", "Include X axis"),
            ('Y', "Y", "Include Y axis"),
            ('Z', "Z", "Include Z axis"),
        ],
        options={'ENUM_FLAG'},
        default={'X', 'Y', 'Z'}
    )

    include_roll: BoolProperty(
        name="Include Roll",
        description="Copy the bone roll",
        default=True
    )

    include_scale: BoolProperty(
        name="Include Scale",
        description="Copy the bone length/scale",
        default=False
    )

    def draw(self, context):
        layout = self.layout
        
        layout.prop(self, "copy_source", emboss=False)
        
        row = layout.row(align=True)
        row.prop_enum(self, "include_axes", 'X')
        row.prop_enum(self, "include_axes", 'Y')
        row.prop_enum(self, "include_axes", 'Z')
        row.prop(self, "include_roll", text="Roll", toggle=True)
        row.prop(self, "include_scale", text="Scale", toggle=True)

    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool((is_armature(context.active_object) or is_mesh(context.active_object)) and context.active_object.mode in ['WEIGHT_PAINT', 'EDIT', 'POSE'])

    def execute(self, context: Context) -> set:
        error_count = 0
        ref_data = None
        armature_map = {}
        
        for ob in context.selected_objects:
            if ob.type == 'ARMATURE':
                bone_names = [b.name for b in ob.data.bones if b.select]
                if bone_names:
                    armature_map[ob] = {
                        'bones': bone_names,
                        'mw': ob.matrix_world.copy(),
                        'inv_mw': ob.matrix_world.inverted()
                    }

        active_obj = context.active_object
        if not armature_map and active_obj and active_obj.type == 'ARMATURE':
            if active_obj.mode == 'EDIT':
                bone_names = [b.name for b in active_obj.data.edit_bones if b.select]
            else:
                bone_names = [b.name for b in active_obj.data.bones if b.select]
            
            if bone_names:
                armature_map[active_obj] = {
                    'bones': bone_names,
                    'mw': active_obj.matrix_world.copy(),
                    'inv_mw': active_obj.matrix_world.inverted()
                }

        if not armature_map:
            self.report({'ERROR'}, "No armatures selected")
            return {'CANCELLED'}

        if self.copy_source == 'ACTIVE' and context.active_bone:
            active_obj = context.active_object
            active_bone_name = context.active_bone.name
            
            with preserve_context_mode(active_obj, 'EDIT'):
                eb = active_obj.data.edit_bones.get(active_bone_name)
                if eb:
                    mw = active_obj.matrix_world
                    ref_data = {
                        'world_dir': (mw @ eb.tail - mw @ eb.head).normalized(),
                        'roll': eb.roll,
                        'length': eb.length
                    }
        main_armature = list(armature_map.keys())[0]
        
        with preserve_context_mode(main_armature, 'EDIT'):
            for armature, data in armature_map.items():
                try:
                    # Only switch active if the armature is different
                    if context.active_object != armature:
                        bpy.ops.object.mode_set(mode='OBJECT')
                        context.view_layer.objects.active = armature
                        bpy.ops.object.mode_set(mode='EDIT')

                    edit_bones = armature.data.edit_bones
                    mw = data['mw']
                    inv_mw = data['inv_mw']
                    
                    for b_name in data['bones']:
                        editbone = edit_bones.get(b_name)
                        if not editbone: continue

                        current_ref = ref_data
                        if self.copy_source == 'PARENT' and editbone.parent:
                            p = editbone.parent
                            current_ref = {
                                'world_dir': (mw @ p.tail - mw @ p.head).normalized(),
                                'roll': p.roll,
                                'length': p.length
                            }

                        if not current_ref: continue

                        editbone.use_connect = False
                        target_world_dir = current_ref['world_dir'].copy()
                        
                        if len(self.include_axes) < 3:
                            curr_w_dir = (mw @ editbone.tail - mw @ editbone.head).normalized()
                            if 'X' not in self.include_axes: target_world_dir.x = curr_w_dir.x
                            if 'Y' not in self.include_axes: target_world_dir.y = curr_w_dir.y
                            if 'Z' not in self.include_axes: target_world_dir.z = curr_w_dir.z
                        
                        local_dir = (inv_mw.to_3x3() @ target_world_dir).normalized()
                        editbone.tail = editbone.head + (local_dir * editbone.length)

                        if self.include_roll:
                            editbone.roll = current_ref['roll']
                        if self.include_scale:
                            editbone.length = current_ref['length']

                except Exception as e:
                    self.report({'ERROR'}, f"Error on {armature.name}: {e}")
                    error_count += 1

        if error_count == 0:
            self.report({'INFO'}, "Orientation copied successfully")
        
        return {'FINISHED'}
    

class TOOLS_OT_ReAlignBones(Operator):
    bl_idname = 'kitsunetools.realign_bone'
    bl_label = 'ReAlign Bones'
    bl_options = {'REGISTER', 'UNDO'}
    
    alignment_mode: EnumProperty(
        name="Alignment Mode",
        description="Choose how to align the bone tail",
        items=[
            ('AVERAGE_ALL', "Average All", "Align to average position of all children"),
            ('ONLY_SINGLE_CHILD', "Only Single Child", "Align only if there is a single child bone")
        ],
        default='ONLY_SINGLE_CHILD'
    )

    include_axes: EnumProperty(
        name="Include Axes",
        description="Which axes to include when aligning",
        items=[
            ('X', "X", "Include X axis"),
            ('Y', "Y", "Include Y axis"),
            ('Z', "Z", "Include Z axis"),
        ],
        options={'ENUM_FLAG'},
        default={'X', 'Y', 'Z'}
    )

    include_roll: BoolProperty(
        name="Include Roll",
        description="Align the bone roll",
        default=True
    )

    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool((is_armature(context.active_object) or is_mesh(context.active_object)) and context.active_object.mode in ['WEIGHT_PAINT', 'EDIT', 'POSE'])
        
    def draw(self, context : Context) -> None:
        layout = self.layout
        layout.prop(self, "alignment_mode")
        row = layout.row(align=True)
        row.prop_enum(self, "include_axes", 'X')
        row.prop_enum(self, "include_axes", 'Y')
        row.prop_enum(self, "include_axes", 'Z')
        row.prop(self, "include_roll", text="Roll", toggle=True)

    def realign_bone_tail(self, bone):
        child_positions = [child.head for child in bone.children]
        original_bone_roll = bone.roll

        new_tail = None

        if child_positions:
            if self.alignment_mode == 'AVERAGE_ALL':
                avg_position = sum(child_positions, Vector((0, 0, 0))) / len(child_positions)
                new_tail = Vector((
                    bone.tail.x if 'X' not in self.include_axes else avg_position.x,
                    bone.tail.y if 'Y' not in self.include_axes else avg_position.y,
                    bone.tail.z if 'Z' not in self.include_axes else avg_position.z
                ))

            elif self.alignment_mode == 'ONLY_SINGLE_CHILD' and len(child_positions) == 1:
                child_position = child_positions[0]
                new_tail = Vector((
                    bone.tail.x if 'X' not in self.include_axes else child_position.x,
                    bone.tail.y if 'Y' not in self.include_axes else child_position.y,
                    bone.tail.z if 'Z' not in self.include_axes else child_position.z
                ))
                
            if new_tail:
                if not self.include_axes:
                    if self.alignment_mode == 'AVERAGE_ALL':
                        avg_vec = sum((pos - bone.head for pos in child_positions), Vector((0,0,0))) / len(child_positions)
                        bone.length = avg_vec.length
                    elif self.alignment_mode == 'ONLY_SINGLE_CHILD' and len(child_positions) == 1:
                        vec_to_child = child_positions[0] - bone.head
                        bone.length = vec_to_child.length
                else:
                    bone.tail = new_tail

                if self.include_roll:
                    bone.align_roll(bone.tail - bone.head)
                else:
                    bone.roll = original_bone_roll

    def execute(self, context : Context) -> set:
        armature = get_armature(context.active_object)

        if not armature:
            self.report({'WARNING'}, "No armature selected")
            return {'CANCELLED'}
        
        with preserve_context_mode(armature, 'EDIT'):
            selectedbones = get_selected_bones(armature,'BONE','TO_FIRST')
            
            editbones = []
            for bone in selectedbones:
                armatureid = bone.id_data
                editbones.append(armatureid.edit_bones.get(bone.name))
            
            if editbones is None: 
                self.report({'WARNING'}, "No Bones Selected")
                return {'CANCELLED'}
                
            for bone in editbones:
                self.realign_bone_tail(bone)
                
        self.report({'INFO'}, "Bones realigned successfully")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    

class TOOLS_OT_SubdivideBone(Operator):
    bl_idname = 'kitsunetools.subdivide_bone'
    bl_label = 'Subdivide Bone'
    bl_options = {'REGISTER', 'UNDO'}
    
    subdivisions: IntProperty(
        name='Subdivisions', 
        min=2, 
        max=20, 
        default=2,
        description='Number of segments to split the bone into'
    )

    falloff : IntProperty(
        name='Falloff', 
        min=5, 
        max=20, 
        default=8,
        description='Weight falloff curve sharpness (higher = sharper transitions)'
    )
    
    smoothness : FloatProperty(
        name='Smoothness', 
        min=0, 
        soft_max=1.0, 
        default=0.0, 
        precision=3,
        description='Weight smoothing amount (0 = no smoothing, higher = smoother blending)'
    )

    weights_only: BoolProperty(
        name='Weights Only',
        default=False,
        description='Only redistribute weights without creating new bones'
    )

    skip_original_bone : BoolProperty(
        name='Skip Original Bone',
        default=True,
    )
    
    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool((is_armature(context.active_object) or is_mesh(context.active_object)) and context.active_object.mode in ["EDIT", "POSE", "WEIGHT_PAINT"])
    
    def invoke(self, context: Context, event: Event) -> set:
        any_selected = False
        for ob in context.selected_objects:
            if ob.type == 'ARMATURE':
                if any(b.select for b in ob.data.bones):
                    any_selected = True
                    break
        
        if any_selected:
            return context.window_manager.invoke_props_dialog(self)
        
        return {'CANCELLED'}

    def draw(self, context : Context) -> None:
        layout = self.layout
        
        col = layout.column(align=True)
        col.prop(self, 'subdivisions')
        
        layout.separator()
        
        col = layout.column(align=True)
        col.label(text="Weight Distribution:")
        col.prop(self, 'falloff')
        col.prop(self, 'smoothness')

        layout.separator()
        if self.weights_only:
            col = layout.column(align=True)
            col.prop(self, 'skip_original_bone')

    def execute(self, context: Context) -> set:
        armature_map = {ob: [b.name for b in ob.data.bones if b.select] 
                        for ob in context.selected_objects if ob.type == 'ARMATURE'}

        with preserve_context_mode(context.active_object, 'EDIT'):
            for arm, bone_names in armature_map.items():
                if not bone_names: continue
                
                context.view_layer.objects.active = arm
                subdivide_bone(bone_names, arm, self.subdivisions, weights_only=self.weights_only)
        
        return {'FINISHED'}


class TOOLS_OT_MergeBones(Operator):
    bl_idname= 'kitsunetools.merge_bones'
    bl_label= 'Merge Bones'
    bl_options = {'REGISTER', 'UNDO'}
    
    mode: EnumProperty(items=[
        ('TO_PARENT', 'To Parent', ''),
        ('TO_ACTIVE', 'To Active', '')
    ])
    
    @classmethod
    def poll(cls, context: Context) -> bool:
        ob = context.active_object
        arm = ob if is_armature(ob) else get_armature(ob) if is_mesh(ob) else None
        
        if arm is None or arm.mode not in ['WEIGHT_PAINT', 'POSE', 'EDIT']:
            return False

        bones = (arm.data.edit_bones if arm.mode == 'EDIT' else arm.data.bones)
        return any(b.select and not b.hide for b in bones)
    
    def execute(self, context: Context) -> set:
        if context.mode == 'PAINT_WEIGHT':
            armatures = {get_armature(context.active_object)}
        else:
            armatures = {get_armature(ob) for ob in context.selected_objects if get_armature(ob)}
            
        vs_sce = context.scene.vs
        bones_to_remove_map = {}
        vgroups_processed_map = {}

        with preserve_context_mode(mode='OBJECT'):
            for arm in armatures:
                bpy.context.view_layer.objects.active = arm
                
                if self.mode == 'TO_ACTIVE':
                    result = self._merge_to_active(arm, context, vs_sce)
                else:
                    result = self._merge_to_parent(arm, vs_sce)
                
                if result:
                    bones_to_remove_map[arm] = result[0]
                    vgroups_processed_map[arm] = result[1]

            bpy.ops.object.mode_set(mode='EDIT')
            
            for arm, bones_to_remove in bones_to_remove_map.items():
                snap_parent = (self.mode == 'TO_PARENT' and 
                             vs_sce.merge_bone_options_parent == 'SNAP_PARENT')
                source = context.active_bone.name if self.mode == 'TO_ACTIVE' else None
                
                remove_bone(arm, bones_to_remove, 
                          match_parent_to_head=snap_parent,
                          source=source)

        total_merged = sum(len(vg) for vg in vgroups_processed_map.values())
        self.report({'INFO'}, f'{total_merged} Weights merged')
        return {'FINISHED'}
    
    def _merge_to_active(self, arm, context, vs_sce):
        sel_bones = get_selected_bones(arm, 'BONE', sort_type='TO_FIRST', exclude_active=True)
        if not sel_bones:
            return None

        if not context.active_bone:
            self.report({'WARNING'}, 'No active selected bone')
            return None

        keep_bone = vs_sce.merge_bone_options_active in ['KEEP_BONE', 'KEEP_BOTH']
        keep_weight = vs_sce.merge_bone_options_active == 'KEEP_BOTH'
        centralize = vs_sce.merge_bone_options_active == 'CENTRALIZE'

        if centralize:
            bones_to_remove, merged_pairs, vgroups_processed = merge_bones(
                arm, context.active_bone, sel_bones,
                keep_bone=False,
                visible_mesh_only=vs_sce.visible_mesh_only,
                keep_original_weight=False,
                centralize_bone=True
            )
            centralize_bone_pairs(arm, merged_pairs)
        else:
            bones_to_remove, _, vgroups_processed = merge_bones(
                arm, context.active_bone, sel_bones,
                keep_bone=keep_bone,
                visible_mesh_only=vs_sce.visible_mesh_only,
                keep_original_weight=keep_weight,
                centralize_bone=False
            )

        return bones_to_remove, vgroups_processed
    
    def _merge_to_parent(self, arm, vs_sce):
        sel_bones = get_selected_bones(arm, sort_type='TO_FIRST', 
                                     bone_type='BONE', exclude_active=False)
        if not sel_bones:
            return None
        
        keep_bone = vs_sce.merge_bone_options_parent in ['KEEP_BONE', 'KEEP_BOTH']
        keep_weight = vs_sce.merge_bone_options_parent == 'KEEP_BOTH'
        
        bones_to_remove, _, vgroups_processed = merge_bones(
            arm, None, sel_bones,
            keep_bone=keep_bone,
            visible_mesh_only=vs_sce.visible_mesh_only,
            keep_original_weight=keep_weight,
            centralize_bone=False
        )
        
        return bones_to_remove, vgroups_processed
  

class TOOLS_OT_FlipBone(Operator):
    bl_idname= 'kitsunetools.flip_bone'
    bl_label= 'Flip Bone'
    bl_options: set = {'REGISTER', 'UNDO'}
    bl_description= 'Flip the selected bone(s) by swapping their head and tail positions'
    
    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool(context.mode in {'POSE', 'EDIT_ARMATURE'})
    
    def execute(self, context: Context) -> set:
        flipped_count = 0
        
        armatures = [ob for ob in context.selected_objects if ob.type == 'ARMATURE']
        
        if not armatures:
            self.report({'ERROR'}, 'No armatures selected')
            return {'CANCELLED'}

        with preserve_context_mode(armatures[0], 'EDIT'):
            for armature in armatures:
                if armature != context.active_object:
                    bpy.ops.object.mode_set(mode='OBJECT')
                    context.view_layer.objects.active = armature
                    bpy.ops.object.mode_set(mode='EDIT')
                
                edit_bones = armature.data.edit_bones
                for bone in edit_bones:
                    if bone.select:
                        old_head = bone.head.copy()
                        bone.head = bone.tail.copy()
                        bone.tail = old_head
                        flipped_count += 1

        self.report({'INFO'}, f'Flipped {flipped_count} bones')
        return {'FINISHED'}
    

class TOOLS_OT_CreateCenterBone(Operator):
    bl_idname= 'kitsunetools.create_centerbone'
    bl_label= 'Create Center Bone'
    bl_options: set = {'REGISTER', 'UNDO'}
    
    parent_choice: EnumProperty(
        name="Parent Bone",
        description="Choose which bone to use as parent",
        items=[
            ('BONE1', "First Bone's Parent", "Use the parent of the first selected bone"),
            ('BONE2', "Second Bone's Parent", "Use the parent of the second selected bone"),
            ('NONE', "No Parent", "Don't set a parent"),
        ],
        default='BONE1'
    )
    
    collection_choice: EnumProperty(
        name="Bone Collection",
        description="Choose which bone's collection to use",
        items=[
            ('BONE1', "First Bone's Collections", "Use collections from the first selected bone"),
            ('BONE2', "Second Bone's Collections", "Use collections from the second selected bone"),
            ('COMMON', "Common Collections", "Use only collections both bones share"),
        ],
        default='COMMON'
    )
    
    distance_threshold: FloatProperty(
        name="Distance Threshold",
        description="Maximum distance to consider bones connected",
        default=0.001,
        min=0.0001,
        max=0.1
    )
    
    _needs_parent_choice: bool = False
    _needs_collection_choice: bool = False
    _bone1_name: str = ""
    _bone2_name: str = ""
    _parent1_name: str = ""
    _parent2_name: str = ""
    _common_collections_count: int = 0
    
    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool(context.mode in {'POSE', 'EDIT_ARMATURE'})
    
    def invoke(self, context: Context, event : Event) -> set:
        armature = get_armature(context.active_object)
        
        if context.mode == 'EDIT_ARMATURE':
            selected_bones = [b for b in armature.data.edit_bones if b.select]
            all_bones = armature.data.edit_bones
        else:
            selected_bones = [armature.data.bones[pb.name] for pb in armature.pose.bones if pb.bone.select]
            all_bones = armature.data.bones
        
        if len(selected_bones) != 2:
            self.report({'ERROR'}, 'Only select 2 bones')
            return {'CANCELLED'}
        
        bone1, bone2 = selected_bones[0], selected_bones[1]
        self._bone1_name = bone1.name
        self._bone2_name = bone2.name
        
        center_head = None
        if context.mode == 'EDIT_ARMATURE':
            center_head = (bone1.head + bone2.head) / 2
        else:
            center_head = (bone1.head_local + bone2.head_local) / 2
        
        has_matching_tail = False
        
        if center_head is not None:
            for bone in all_bones:
                if bone not in selected_bones:
                    if context.mode == 'EDIT_ARMATURE':
                        distance = (bone.tail - center_head).length
                    else:
                        distance = (bone.tail_local - center_head).length
                        
                    if distance < self.distance_threshold:
                        has_matching_tail = True
                        break
        
        parent1 = bone1.parent
        parent2 = bone2.parent
        
        self._parent1_name = parent1.name if parent1 else "None"
        self._parent2_name = parent2.name if parent2 else "None"
        
        bone1_collections = set(bone1.collections)
        bone2_collections = set(bone2.collections)
        common_collections = bone1_collections & bone2_collections
        self._common_collections_count = len(common_collections)
        
        self._needs_parent_choice = (parent1 != parent2) and not has_matching_tail
        self._needs_collection_choice = (self._common_collections_count == 0 and len(bone1_collections) > 0 and len(bone2_collections) > 0)
        
        if self._needs_parent_choice or self._needs_collection_choice:
            self.parent_choice = 'BONE1'
            self.collection_choice = 'COMMON' if self._common_collections_count > 0 else 'BONE1'
            return context.window_manager.invoke_props_dialog(self)
        else:
            return self.execute(context)
    
    def draw(self, context : Context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        if self._needs_parent_choice:
            box = layout.box()
            col = box.column(align=True)
            col.label(text="Different Parents Detected", icon='INFO')
            col.separator(factor=0.5)
            
            row = col.row(align=True)
            row.label(text=self._bone1_name, icon='BONE_DATA')
            row.label(text=f"→ {self._parent1_name}")
            
            row = col.row(align=True)
            row.label(text=self._bone2_name, icon='BONE_DATA')
            row.label(text=f"→ {self._parent2_name}")
            
            box.separator(factor=0.5)
            box.prop(self, "parent_choice", text="Parent")
        
        if self._needs_collection_choice:
            if self._needs_parent_choice:
                layout.separator()
            
            box = layout.box()
            col = box.column(align=True)
            col.label(text="No Common Collections", icon='INFO')
            box.separator(factor=0.5)
            box.prop(self, "collection_choice", text="Collections")
    
    def find_bone_with_tail_at(self, edit_bones, position, exclude_bones, threshold):
        for bone in edit_bones:
            if bone not in exclude_bones:
                distance = (bone.tail - position).length
                if distance < threshold:
                    return bone
        return None
    
    def execute(self, context : Context) -> set:
        armature = get_armature(context.active_object)
        
        with preserve_context_mode(armature, 'EDIT') as edit_bones:
            selected_bones = get_selected_bones(armature, bone_type='EDITBONE')
            
            if len(selected_bones) != 2:
                self.report({'ERROR'}, 'Only select 2 bones')
                return {'CANCELLED'}
            
            bone1, bone2 = selected_bones[0], selected_bones[1]
            
            center_head = (bone1.head + bone2.head) / 2
            center_tail = (bone1.tail + bone2.tail) / 2
            
            new_bone = edit_bones.new(bone1.name + "_" + bone2.name)
            new_bone.head = center_head
            new_bone.tail = center_tail
            
            matching_bone = self.find_bone_with_tail_at(
                edit_bones, 
                center_head, 
                {bone1, bone2}, 
                self.distance_threshold
            )
            
            if matching_bone:
                new_bone.parent = matching_bone
                self.report({'INFO'}, f'Auto-parented to {matching_bone.name} (tail matches head)')
            elif bone1.parent == bone2.parent:
                new_bone.parent = bone1.parent
            else:
                if self.parent_choice == 'BONE1':
                    new_bone.parent = bone1.parent
                elif self.parent_choice == 'BONE2':
                    new_bone.parent = bone2.parent
            
            bone1_collections = set(bone1.collections)
            bone2_collections = set(bone2.collections)
            common_collections = bone1_collections & bone2_collections
            
            if common_collections:
                for collection in common_collections:
                    collection.assign(new_bone)
            else:
                if self.collection_choice == 'BONE1':
                    for collection in bone1.collections:
                        collection.assign(new_bone)
                elif self.collection_choice == 'BONE2':
                    for collection in bone2.collections:
                        collection.assign(new_bone)
                else:
                    if bone1.collections:
                        bone1.collections[0].assign(new_bone)
                    elif bone2.collections:
                        bone2.collections[0].assign(new_bone)
            
            self.report({'INFO'}, f'Created center bone: {new_bone.name}')
        
        return {'FINISHED'}
    

class TOOLS_OT_SplitActiveWeightLinear(Operator):
    bl_idname = 'kitsunetools.split_active_weights_linear'
    bl_label = 'Split Active Weights Linearly'
    bl_options = {'REGISTER', 'UNDO'}

    smoothness: FloatProperty(
        name="Smoothness",
        description="Smoothness of the weight split (0 = hard cut, 1 = full smooth blend)",
        min=0.0, max=1.0,
        default=0.6
    )

    @classmethod
    def poll(cls, context : Context) -> bool:
        ob  = context.active_object
        if ob is None: return False
        if ob.mode not in ['WEIGHT_PAINT', 'POSE']: return False
        
        return bool(get_armature(ob))
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def get_vgroup_index(self, mesh, name):
        for i, vg in enumerate(mesh.vertex_groups):
            if vg.name == name:
                return i
        return None

    def clamp(self, x, a, b):
        return max(a, min(x, b))

    def remap(self, value, minval, maxval):
        if maxval - minval == 0:
            return 0.5
        return (value - minval) / (maxval - minval)

    def project_point_onto_line(self, p, a, b):
        ap = p - a
        ab = b - a
        ab_len_sq = ab.length_squared
        if ab_len_sq == 0.0:
            return 0.0
        return self.clamp(ap.dot(ab) / ab_len_sq, 0.0, 1.0)

    def execute(self, context : Context) -> set:
        arm = get_armature(context.active_object)
        
        bones = get_selected_bones(arm,sort_type=None,bone_type='BONE',exclude_active=True)
        active_bone = arm.data.bones.active
        
        if not bones or len(bones) != 2 or not active_bone:
            self.report({'WARNING'}, "Select 3 bones: 2 others and 1 active (middle split point).")
            return {'CANCELLED'}
        
        og_arm_pose_mode = arm.data.pose_position
        arm.data.pose_position = 'REST'
        bpy.context.view_layer.update()

        bone1 = arm.pose.bones.get(bones[0].name)
        bone2 = arm.pose.bones.get(bones[1].name)
        active = active_bone

        bone1_name = bone1.name
        bone2_name = bone2.name
        active_name = active.name

        arm_matrix = arm.matrix_world
        p1 = arm_matrix @ ((bone1.head + bone1.tail) * 0.5)
        p2 = arm_matrix @ ((bone2.head + bone2.tail) * 0.5)

        meshes = get_armature_meshes(arm, visible_only=context.scene.vs.visible_mesh_only)

        for mesh in meshes:
            vg_active = self.get_vgroup_index(mesh, active_name)
            vg1 = mesh.vertex_groups.get(bone1_name)
            if vg1 is None:
                vg1 = mesh.vertex_groups.new(name=bone1_name)

            vg2 = mesh.vertex_groups.get(bone2_name)
            if vg2 is None:
                vg2 = mesh.vertex_groups.new(name=bone2_name)

            if vg_active is None or vg1 is None or vg2 is None:
                continue

            vtx_weights = {}
            for v in mesh.data.vertices:
                for g in v.groups:
                    if g.group == vg_active:
                        vtx_weights[v.index] = g.weight
                        break

            for vidx, weight in vtx_weights.items():
                vertex = mesh.data.vertices[vidx]
                world_pos = mesh.matrix_world @ vertex.co

                t = self.project_point_onto_line(world_pos, p1, p2)

                # THIS WAS BACKWARDS BEFORE
                if self.smoothness == 0.0:
                    w1 = weight if t < 0.5 else 0.0
                    w2 = weight if t >= 0.5 else 0.0
                else:
                    s = self.smoothness
                    edge0 = 0.5 - s * 0.5
                    edge1 = 0.5 + s * 0.5
                    smooth_t = self.remap(t, edge0, edge1)
                    smooth_t = self.clamp(smooth_t, 0.0, 1.0)
                    w1 = weight * (1.0 - smooth_t)
                    w2 = weight * smooth_t

                vg1.add([vidx], w1, 'ADD')
                vg2.add([vidx], w2, 'ADD')

            mesh.vertex_groups.remove(mesh.vertex_groups[vg_active])
            mesh.vertex_groups.active = vg1
        
        with preserve_context_mode(arm, 'EDIT'):
            remove_bone(arm,active_bone.name)
            arm.data.edit_bones.active = arm.data.edit_bones.get(bones[0].name)
        
        arm.data.pose_position = og_arm_pose_mode

        self.report({'INFO'}, f"Split {active_name} between {bone1_name} and {bone2_name}")
        return {'FINISHED'} 


class TOOLS_OT_align_bone_to_axis(Operator):
    bl_idname= 'kitsunetools.align_bone_to_axis'
    bl_label= 'Align Bone to Axis'
    bl_options: set = {'REGISTER', 'UNDO'}
    
    axis: EnumProperty(name='Axis',
                        items=[
                            ('X', 'X', ''),
                            ('Y', 'Y', ''),
                            ('Z', 'Z', ''),
                            ('-X', '-X', ''),
                            ('-Y', '-Y', ''),
                            ('-Z', '-Z', '')],
                        default='X')
    
    @classmethod
    def poll(cls, context: Context) -> bool:
        return bool(is_armature(context.active_object) and context.active_object.mode in ['EDIT', 'POSE', 'WEIGHT_PAINT'])
    
    def execute(self, context: Context) -> set:
        processed_bone = 0
        
        axis_map = {
            'X':  Vector((1, 0, 0)),
            'Y':  Vector((0, 1, 0)),
            'Z':  Vector((0, 0, 1)),
            '-X': Vector((-1, 0, 0)),
            '-Y': Vector((0, -1, 0)),
            '-Z': Vector((0, 0, -1))
        }
        axis_vector = axis_map.get(self.axis)

        armature_map = {}
        for ob in context.selected_objects:
            if ob.type == 'ARMATURE':
                bone_names = [b.name for b in ob.data.bones if b.select]
                if bone_names:
                    armature_map[ob] = bone_names

        if not armature_map:
            self.report({'ERROR'}, 'No bones selected')
            return {'CANCELLED'}

        first_armature = list(armature_map.keys())[0]

        with preserve_context_mode(first_armature, 'EDIT'):
            for armature, bone_names in armature_map.items():
                try:
                    if context.active_object != armature:
                        bpy.ops.object.mode_set(mode='OBJECT')
                        context.view_layer.objects.active = armature
                        bpy.ops.object.mode_set(mode='EDIT')

                    edit_bones = armature.data.edit_bones
                    
                    for b_name in bone_names:
                        bone = edit_bones.get(b_name)
                        if not bone: 
                            continue
                        
                        bone_length = bone.length
                        bone.tail = bone.head + (axis_vector * bone_length)
                        processed_bone += 1
                        
                except Exception as e:
                    self.report({'ERROR'}, f"Error in {armature.name}: {e}")

        self.report({'INFO'}, f'Aligned {processed_bone} bones to {self.axis} axis')
        return {'FINISHED'}
    

class TOOLS_OT_CopySourceBoneProps(Operator):
    bl_idname = "valvesource.copy_bone_props"
    bl_label = "Copy Source Bone Properties"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return (
            context.mode == 'POSE'
            and context.active_pose_bone is not None
            and len(context.selected_pose_bones) > 1
        )

    def execute(self, context) -> set:
        src = context.active_pose_bone.bone.vs
        props = [
            'export_name',
            'ignore_rotation_offset',
            'export_rotation_offset_x',
            'export_rotation_offset_y',
            'export_rotation_offset_z',
            'ignore_location_offset',
            'export_location_offset_x',
            'export_location_offset_y',
            'export_location_offset_z',
        ]

        targets = [pb for pb in context.selected_pose_bones if pb != context.active_pose_bone]
        for pb in targets:
            for prop in props:
                setattr(pb.bone.vs, prop, getattr(src, prop))

        self.report({'INFO'}, f"Copied bone properties to {len(targets)} bone(s)")
        return {'FINISHED'}