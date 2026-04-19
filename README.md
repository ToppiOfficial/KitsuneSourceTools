# KitsuneSourceTool [Blender 4.5+]

A fork of [BlenderSourceTools by Artfunkel](https://github.com/Artfunkel/BlenderSourceTools) specifically tailored for character modding

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
- **Vertex Group Normalization** — Limit and normalize vertex group influences per vertex on export, with per-bone priority control via `Bone Sort Order`

## Note
- SMD, VTA are hardly maintained and updated. I recommend using DMX for export.
- Vertex Animation is not considered to work with the new post-processing features and is completely untested.
- Compile QC is completely removed and KitsuneResource Compile replaced it. see: [KitsuneResource](https://github.com/ToppiOfficial/KitsuneResource)
