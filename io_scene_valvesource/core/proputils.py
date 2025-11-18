from .commonutils import get_selected_bones

_property_updating = False

def resolve_attr_path(obj, path: str):
    parts = path.split(".")
    for p in parts:
        obj = getattr(obj, p, None)
        if obj is None:
            return None
    return obj

def propagate_property(self, context, prop_name: str, group_path="vs", propagate_enabled=True, include_active=False):
    global _property_updating
    if _property_updating or not propagate_enabled:
        return

    new_value = getattr(self, prop_name)

    targets = {}
    
    for obj in context.selected_objects:
        if obj.type == 'ARMATURE':
            selectedBones = get_selected_bones(obj, 'BONE', exclude_active=not include_active)
            for b in selectedBones:
                targets[b] = obj
        else:
            if include_active or obj != context.active_object:
                targets[obj] = None

    _property_updating = True
    try:
        for target_obj, arm in targets.items():
            target = resolve_attr_path(target_obj, group_path)
            if target and hasattr(target, prop_name):
                setattr(target, prop_name, new_value)
    finally:
        _property_updating = False

def make_update(prop_name, group_path="vs", propagate_enabled_attr="propagate_enabled", include_active_attr="propagate_include_active"):
    def update_func(self, context):
        propagate_enabled = getattr(context.scene.vs, propagate_enabled_attr, True)
        include_active = getattr(context.scene.vs, include_active_attr, False)
        propagate_property(self, context, prop_name, group_path, propagate_enabled, include_active)
    return update_func
