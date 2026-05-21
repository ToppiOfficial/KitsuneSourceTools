# KitsuneSourceTool [Blender 4.5+]

A character-modding-centric fork of [BlenderSourceTools](https://github.com/Artfunkel/BlenderSourceTools) by Artfunkel. This tool is designed to modernize and streamline workflows for Source Engine modding, with a heavy emphasis on DMX-based pipelines and automated post-processing.

## Important Notice
⚠️ **Project Status:** Development is focused on a new project built from scratch with the same goals, rather than extending this fork further. **No new features will be added**, but the project will continue to receive bug fixes and stability patches.

## Core Philosophy
- **DMX First:** SMD and VTA formats are legacy and maintained only for compatibility. DMX is the recommended format for all new projects.
- **Automation over Manual QC:** KitsuneSourceTool replaces manual QC compilation with integration into [KitsuneResource](https://github.com/ToppiOfficial/KitsuneResource).
- **Post-Processing on Export:** Perform complex mesh cleanup, toon-outline, and vertex group normalization automatically during the export process.

## Key Features

### Advanced Bone Controls
- **Flexible Offsets:** Custom export name, rotation, and position overrides per bone.
- **Axis Remapping:** Swap bone axes during export to match target engine requirements.

### DMX / QC Export
- Export Jigglebones, Hitboxes, and Attachments directly to QC or VMDL formats.
- Native support for KeyValues3 structures.

### Source 2 Cloth Support
- Export cloth proxy meshes leveraging `VertexFloatMap` attributes.

### Powerful Post-Processing
- **Toon Outline:** Automated Solidify-based outline generation for stylized character models.
- **Mesh Cleanup:** Contextual removal of faces/vertices via vertex groups or materials.
- **Vertex Animation:** Dedicated toolset for baking and exporting vertex animations.
- **Weight Normalization:** Limit and normalize vertex group influences per-vertex with per-bone priority via `Bone Sort Order`.
- **DMX Attachments:** Direct DMX-native attachment export.
- **Transform Overrides:** Set specific export-time height, scale, and forward axis configurations.

## Getting Started

1. **Installation:** Install as a standard Blender Add-on.
2. **Setup:** Configure your `Export Path` and `Engine Path` in the 3D View Sidebar under the `KitsuneSrcTool` tab.
3. **Workflow:** 
    - Use the **Kitsune Resource Compile** panel to set up your project path and config file.
    - Export your meshes using the standard Export operator.
    - Leverage Vertex Maps (found under Mesh Properties) for Source 2 attributes like cloth physics.

## Documentation & Links
- [KitsuneResource Compiler](https://github.com/ToppiOfficial/KitsuneResource)
- [Valve Developer Wiki: DMX/Source 2 Vertex Attributes](http://developer.valvesoftware.com/wiki/DMX/Source_2_Vertex_attributes)

## Acknowledgements
KitsuneSourceTool incorporates code from the following forks of BlenderSourceTools:
- [compucolor/BlenderSourceTools](https://github.com/compucolor/BlenderSourceTools)
- [Rectus/BlenderSourceTools](https://github.com/Rectus/BlenderSourceTools)

Additionally, `io_scene_valvesource/datamodel.py` has been modified; the base was an older version, which has been integrated with the latest version and custom patches to support newer functionality.

## Note
- Vertex Animation features are experimental and primarily for DMX-based pipelines.
- Legacy formats (SMD/VTA) are supported but receive minimal updates.
