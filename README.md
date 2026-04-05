# KitsuneSourceTool [Blender 4.5+]

A fork of [BlenderSourceTools by Artfunkel](https://github.com/Artfunkel/BlenderSourceTools)

## Features

### Bone Controls
- Custom export name, rotation, and position per bone
- Swap bone axes and assign different names on export

### QC / VMDL Export
- Export Jigglebones, Hitboxes, and Attachments to QC or VMDL
- KeyValues3.py

### Source 2 Cloth *(ported from [Rectus](https://github.com/Rectus/BlenderSourceTools))*
- Export cloth proxy meshes using `VertexFloatMap`

### Post-Processing on Export
- **Toon Outline** — Solidify modifier export that mimics edgeline/outline effects
- **Mesh Cleanup** — Remove faces/vertices via vertex groups or materials before export
- **Flexcontrollers** — Export specific shapekeys and DMX config using `Build` mode
- **DMX Attachments** — Export attachments directly in DMX format
- **Transform Override** — Export at a specific height, scale, and forward axis
