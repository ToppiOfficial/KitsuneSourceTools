# KitsuneSourceTool [Blender 4.5+]

KitsuneSourceTool is a personal Blender addon built for my own Source engine workflow. It's a fork of BlenderSourceTool with extensions from my older unreleased projects.

I'm releasing this publicly in case anyone finds it useful, but be aware: **this is built for my specific needs and workflow**. Don't expect comprehensive documentation or support.

> [!WARNING]
> - Work in progress
> - Original export code has been modified
> - Incomplete translations and tooltips
> - Features are being ported gradually from older versions

Originally developed as "Fubukitek", later renamed to Kitsune.

## What's Included

**Export:**
- KeyValue3 (`.vmdl`, `.vmdl_prefab`)
- Vertex Float Maps (cloth proxy mesh)
- DMX Attachments
- Offset rotation/location
- Custom bone export names

**Armature & Bone Tools:**
- Armature merging, bone cleanup, pose tools
- Bone merging, realignment, subdivision
- Jigglebones and hitboxes

**Mesh & Animation Tools:**
- Shapekey and vertex group cleanup
- Animation merging and conversion
- Custom proportion constraints
- Toon edge lines

**Material Tools:**
- PBR to Phong conversion

## Dependencies

Includes [Pillow](https://python-pillow.org/) (MIT-CMU License). See `wheels/pillow-license` for details.

---

Again: this is a personal tool. If it works for you, great. If not, you'll need to figure it out yourself or modify it.