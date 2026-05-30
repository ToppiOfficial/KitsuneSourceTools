import bpy, math
from ..utils import get_armature, vertex_float_maps, validate_corrective_components, validate_flex_expression
from .. import procbones_sim as _procbones_sim


def _mesh_type_allows(ob, feature: str) -> bool:
    mt = getattr(ob.vs, 'mesh_type', 'DEFAULT') if ob and hasattr(ob, 'vs') else 'DEFAULT'
    if mt == 'DEFAULT':
        return True
    if mt == 'CLOTHPROXY':
        return feature in ('vertexmap', 'vertexfloatmap')
    return False  # COLLISION blocks everything


def _draw_proc_bone_context_menu(self, context):
    if context.mode == 'POSE' and context.selected_pose_bones:
        arm_ob = get_armature(context.object)
        if arm_ob:
            self.layout.operator_context = 'INVOKE_DEFAULT'
            self.layout.operator("smd.proc_bone_add_from_selected", icon='DRIVER')


def _ensure_cloth_remaps():
    context = bpy.context
    if context.object and context.object.type == 'MESH':
        existing = {r.group for r in context.object.vs.vertex_map_remaps}
        for map_name in vertex_float_maps:
            if map_name not in existing:
                remap = context.object.vs.vertex_map_remaps.add()
                remap.group = map_name
                remap.min = 0.0
                remap.max = 1.0
    return None


def _get_or_create_proc_tol_fcurve(entry, dp: str):
    """Find or create the proc_tolerance fcurve in entry.action. Returns None on failure."""
    action = entry.action
    if getattr(action, 'is_action_legacy', True):
        fc = action.fcurves.find(dp, index=0)
        return fc if fc is not None else action.fcurves.new(dp, index=0)
    target_slot = _procbones_sim._find_action_slot(action, entry.action_slot_name)
    if target_slot is None:
        return None
    for layer in action.layers:
        for strip in layer.strips:
            cb_fn = getattr(strip, 'channelbag', None)
            if cb_fn and callable(cb_fn):
                try:
                    bag = cb_fn(target_slot)
                    if bag is not None:
                        fc = bag.fcurves.find(dp, index=0)
                        return fc if fc is not None else bag.fcurves.new(dp, index=0)
                except Exception:
                    pass
            for bag in getattr(strip, 'channelbags', ()):
                if getattr(bag, 'slot_handle', None) == target_slot.handle:
                    fc = bag.fcurves.find(dp, index=0)
                    return fc if fc is not None else bag.fcurves.new(dp, index=0)
    return None


def _get_entry_proc_tol(entry, frame: float, arm_ob=None) -> float:
    """Return proc_tolerance from entry.action's fcurves at frame.
    Falls back to the bone's static value, then to the 90° default."""
    if not entry.action or not entry.driver_bone:
        if arm_ob:
            eb = arm_ob.data.bones.get(entry.driver_bone)
            if eb:
                return eb.vs.proc_tolerance
        return math.pi / 2
    fcurves = _procbones_sim._get_action_fcurves(entry.action, entry.action_slot_name)
    dp = f'bones["{entry.driver_bone}"].vs.proc_tolerance'
    for fc in fcurves:
        if fc.data_path == dp and fc.array_index == 0:
            return fc.evaluate(frame)
    if arm_ob:
        eb = arm_ob.data.bones.get(entry.driver_bone)
        if eb:
            return eb.vs.proc_tolerance
    return math.pi / 2
