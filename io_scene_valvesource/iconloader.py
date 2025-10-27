import os
import bpy
import pathlib
import bpy.utils.previews

preview_collections = {}

addon_dir = pathlib.Path(__file__).parent.resolve()
icons_dir = os.path.join(addon_dir, "icons")

ICON_REGISTRY = {
    'KITSUNE': 'kitsunelogo.png',
}

def load_other_icons():
    pcoll = bpy.utils.previews.new()
    
    for icon_name, filename in ICON_REGISTRY.items():
        print(f'- Loaded Icon: {icon_name} using {filename}')
        icon_path = os.path.abspath(os.path.join(icons_dir, filename))
        pcoll.load(icon_name, icon_path, 'IMAGE')
    
    preview_collections['custom_icons'] = pcoll


def get_icon(icon_name: str) -> int:
    if 'custom_icons' not in preview_collections:
        return 0
    
    pcoll = preview_collections['custom_icons']
    
    if icon_name not in pcoll:
        print(f"Warning: Icon '{icon_name}' not found")
        return 0
    
    return pcoll[icon_name].icon_id


def unload_icons():
    for pcoll in preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()