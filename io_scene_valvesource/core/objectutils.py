import bpy
import numpy as np
from typing import Optional, Any, cast, Any

def op_override(operator, context_override: dict[str, Any], context: Optional[bpy.types.Context] = None,
                execution_context: Optional[str] = None, undo: Optional[bool] = None, **operator_args) -> set[str]:
    """Call a Blender operator with a context override."""
    args = []
    if execution_context is not None:
        args.append(execution_context)
    if undo is not None:
        args.append(undo)

    if context is None:
        context = bpy.context
    with cast(Any, context.temp_override(**context_override)):
        return operator(*args, **operator_args)

def applyModifier(mod: bpy.types.Modifier, strict: bool = False, silent=False):
    """
    Apply a modifier safely.
    
    Args:
        mod: The Blender modifier to apply.
        strict: 
            - If True -> deny applying if the object has shapekeys.
            - If False -> advanced Cats-style handling (bake + restore).
    """
    ob: bpy.types.Object | None = cast(bpy.types.Object, mod.id_data)
    if ob is None or ob.type != 'MESH':
        return False
    
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)

    name = mod.name
    m_type = mod.type

    # Strict mode: deny applying if shapekeys exist
    if strict and ob.data.shape_keys:
        if not silent: 
            print(f"- Skipping {name} ({m_type}) on {ob.name}: object has shapekeys (strict mode).")
        return False

    if not strict and ob.data.shape_keys:
        if not silent: 
            print(f"- Applying modifier {name} ({m_type}) with shapekeys on {ob.name}")

        # Backup shapekeys
        shape_keys = {sk.name: [v.co.copy() for v in sk.data] 
                      for sk in ob.data.shape_keys.key_blocks}

        # Remove all shapekeys but preserve final shape
        context_override = {'object': ob, 'active_object': ob}
        op_override(bpy.ops.object.shape_key_remove, context_override, all=True, apply_mix=True)

        while ob.modifiers[0] != mod:
            bpy.ops.object.modifier_move_up(modifier=mod.name)
        bpy.ops.object.modifier_apply(modifier=mod.name)

        # Restore shapekeys only if vertex count unchanged
        if all(len(coords) == len(ob.data.vertices) for coords in shape_keys.values()):
            for sk_name, coords in shape_keys.items():
                new_sk = ob.shape_key_add(name=sk_name, from_mix=False)
                for i, coord in enumerate(coords):
                    new_sk.data[i].co = coord
            if not silent: 
                print(f"- Successfully applied {name} ({m_type}) with shapekeys preserved.")
        else:
            if not silent: 
                print(f"- Modifier {name} changed topology, shapekeys could not be restored.")

        return True

    # No shapekeys — apply normally
    while ob.modifiers[0] != mod:
        bpy.ops.object.modifier_move_up(modifier=mod.name)
    bpy.ops.object.modifier_apply(modifier=mod.name)

    if name not in ob.modifiers:
        if not silent: 
            print(f"- Pre-Applied Modifier {name} ({m_type}) for Object '{ob.name}'")
        return True
    else:
        if not silent: 
            print(f"- Failed to apply {name} ({m_type}) for Object '{ob.name}'")
        return False

#  Original source: https://github.com/teamneoneko/Avatar-Toolkit
def apply_armature_to_mesh_without_shape_keys(armature_obj: bpy.types.Object, mesh_obj: bpy.types.Object) -> None:
    """Apply armature deformation to a mesh that has no shape keys."""
    armature_mod: bpy.types.Modifier = mesh_obj.modifiers.new('PoseToRest', 'ARMATURE')
    armature_mod.object = armature_obj

    # Move modifier to the top before applying
    if bpy.app.version >= (3, 5):
        mesh_obj.modifiers.move(mesh_obj.modifiers.find(armature_mod.name), 0)
    else:
        for _ in range(len(mesh_obj.modifiers) - 1):
            bpy.ops.object.modifier_move_up(modifier=armature_mod.name)

    # Apply with context override
    with cast(Any, bpy.context.temp_override(object=mesh_obj)):
        bpy.ops.object.modifier_apply(modifier=armature_mod.name)

#  Original source: https://github.com/teamneoneko/Avatar-Toolkit
def apply_armature_to_mesh_with_shapekeys(armature_obj: bpy.types.Object, mesh_obj: bpy.types.Object, context: bpy.types.Context) -> None:
    """Apply armature deformation to mesh with shape keys (optimized depsgraph reuse)."""
    old_active_index = mesh_obj.active_shape_key_index
    old_show_only = mesh_obj.show_only_shape_key
    mesh_obj.show_only_shape_key = True

    me = mesh_obj.data
    key_blocks = me.shape_keys.key_blocks

    # Backup vertex groups + mute flags
    shape_key_vertex_groups = [sk.vertex_group for sk in key_blocks]
    shape_key_mutes = [sk.mute for sk in key_blocks]
    for sk in key_blocks:
        sk.vertex_group = ''
        sk.mute = False

    # Temporarily disable all visible modifiers
    mods_to_restore = []
    for mod in mesh_obj.modifiers:
        if mod.show_viewport:
            mod.show_viewport = False
            mods_to_restore.append(mod)

    # Add temporary armature modifier
    armature_mod = mesh_obj.modifiers.new('PoseToRest', 'ARMATURE')
    armature_mod.object = armature_obj

    # Pre-allocate coordinate array
    co_length = len(me.vertices) * 3
    eval_cos_array = np.empty(co_length, dtype=np.single)

    depsgraph = None
    evaluated_mesh_obj = None

    def get_eval_cos_array():
        nonlocal depsgraph, evaluated_mesh_obj
        if depsgraph is None or evaluated_mesh_obj is None:
            depsgraph = bpy.context.evaluated_depsgraph_get()
            evaluated_mesh_obj = mesh_obj.evaluated_get(depsgraph)
        else:
            depsgraph.update()
        evaluated_mesh_obj.data.vertices.foreach_get('co', eval_cos_array)
        return eval_cos_array

    # Bake each shapekey
    for i, sk in enumerate(key_blocks):
        mesh_obj.active_shape_key_index = i
        evaluated_cos = get_eval_cos_array()
        sk.data.foreach_set('co', evaluated_cos)
        if i == 0:  # Also update basis mesh
            mesh_obj.data.vertices.foreach_set('co', evaluated_cos)

    # Restore modifiers and cleanup
    for mod in mods_to_restore:
        mod.show_viewport = True
    mesh_obj.modifiers.remove(armature_mod)

    # Restore shapekey settings
    for sk, vg, mute in zip(me.shape_keys.key_blocks, shape_key_vertex_groups, shape_key_mutes):
        sk.vertex_group = vg
        sk.mute = mute

    mesh_obj.active_shape_key_index = old_active_index
    mesh_obj.show_only_shape_key = old_show_only