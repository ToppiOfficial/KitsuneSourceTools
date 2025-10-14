import os
import bpy
import pathlib
import bpy.utils.previews
from bpy.utils.previews import ImagePreviewCollection
import typing

# global variables
preview_collections: typing.Type[ImagePreviewCollection] = {}
reloading = False

addon_dir = pathlib.Path(__file__).parent.resolve()
icons_dir = os.path.join(addon_dir, "icons")

def load_other_icons():
    pcoll: typing.Type[ImagePreviewCollection] = bpy.utils.previews.new()
    pcoll.load('BLENDSRCTOOL', os.path.join(icons_dir, 'blendsrctool.png'), 'IMAGE')
    pcoll.load('SOURCESDK', os.path.join(icons_dir, 'sourcesdk.png'), 'IMAGE')
    pcoll.load('KITSUNE', os.path.join(icons_dir, 'kitsunelogo.png'), 'IMAGE')

    preview_collections['custom_icons'] = pcoll


def unload_icons():
    print('UNLOADING ICONS!')
    for pcoll in preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()
    print('DONE!')
    