import bpy
from .commonutils import getSelectedBones
from contextlib import contextmanager

_property_updating = False

@contextmanager
def ExposeAllObjects():
    """
    Temporarily unhide all objects and collections in the view layer.
    Restores original visibility afterwards.

    Notes:
        - Only restores objects/collections that were hidden before.
        - Deleted objects/collections are skipped safely.
    """
    view_layer = bpy.context.view_layer
    root_layer_coll = view_layer.layer_collection

    original_visibility = {}
    original_obj_visibility = {}

    def store_layer_collection_visibility(layer_coll, vis):
        vis[layer_coll] = {
            "exclude": layer_coll.exclude,
            "hide_viewport": layer_coll.hide_viewport,
        }
        for child in layer_coll.children:
            store_layer_collection_visibility(child, vis)

    def restore_layer_collection_visibility(vis):
        for layer_coll, state in vis.items():
            if layer_coll:
                layer_coll.exclude = state["exclude"]
                layer_coll.hide_viewport = state["hide_viewport"]

    def unhide_all_layer_collections(layer_coll):
        layer_coll.exclude = False
        layer_coll.hide_viewport = False
        for child in layer_coll.children:
            unhide_all_layer_collections(child)

    # --- Save + unhide ---
    store_layer_collection_visibility(root_layer_coll, original_visibility)

    for obj in bpy.data.objects:
        original_obj_visibility[obj.name] = {
            "hide": obj.hide_get(),
            "hide_viewport": obj.hide_viewport,
        }
        obj.hide_set(False)
        obj.hide_viewport = False

    unhide_all_layer_collections(root_layer_coll)

    try:
        yield
    finally:
        # --- Restore ---
        restore_layer_collection_visibility(original_visibility)
        for name, state in original_obj_visibility.items():
            if name not in bpy.data.objects:
                continue
            obj = bpy.data.objects[name]
            obj.hide_set(state["hide"])
            obj.hide_viewport = state["hide_viewport"]

def resolve_attr_path(obj, path: str):
    parts = path.split(".")
    for p in parts:
        obj = getattr(obj, p, None)
        if obj is None:
            return None
    return obj

def propagateProperty(self, context, prop_name: str, group_path="vs"):
    global _property_updating
    if _property_updating:
        return

    new_value = getattr(self, prop_name)

    targets = {}
    
    for obj in context.selected_objects:
        if obj.type == 'ARMATURE':
            selectedBones = getSelectedBones(obj, 'BONE', exclude_active=True)
            for b in selectedBones:
                targets[b] = obj
        else:
            if obj != context.active_object:
                targets[obj] = None

    _property_updating = True
    try:
        for target_obj, arm in targets.items():
            target = resolve_attr_path(target_obj, group_path)
            if target and hasattr(target, prop_name):
                setattr(target, prop_name, new_value)
    finally:
        _property_updating = False


def make_update(prop_name, group_path="vs"):
    return lambda self, context: propagateProperty(self, context, prop_name, group_path)