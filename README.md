# KitsuneSourceTool

> **ALPHA RELEASE – PARTIALLY FINISHED & EXPERIMENTAL**  

KitsuneSourceTool is a forked and modified of BlenderSourceTool that adds toolsets from my old unreleased extensions in Blender.  The tool is specifically tailored for my workflow but I decided to release publicly nonetheless.  Originally this project is under the name "Fubukitek" but was renamed to Kitsune.  Not all tools are added currently as I am slowly adding the features that originated from older extensions that I made but are on older version of Blender such as 3.8 to 4.2

> [!WARNING]
> Some panels and tools lack translation support, and most labels are in English.  
> Additionally, many tools do not have tooltips.

## Versions

Blender 4.5+

## Features

### KeyValue3
- Python implementation for encoding Source 2's KeyValue3 format.

### Vertex Float Maps (Source 2 Cloth)
- _(Forked and adapted from [BlenderSourceTools](https://github.com/Rectus/BlenderSourceTools))_  
- Export Source 2 cloth proxy meshes based on vertex groups.

### Bone Rotation & Location Offset
- Apply custom rotation or location offsets to bones.  
- Example: a 90° X rotation offset adjusts the bone during export.  
- Useful for converting Blender's Y-forward orientation to X-forward or Z-forward for Source.

### DMX Attachments
- Export DMX model attachments using an Empty object with the `DMX Attachment` property enabled.

### Additional Blender Toolkit
- **Bone Merging** – merge multiple bones into one.
- **Armature Merging** – combine multiple armatures into one.
- **Vertex Group Math** – perform basic arithmetic operations (`+`, `-`, `*`, `/`) between vertex groups.
- **Vertex Group Curve Conversion** – convert vertex group weights using curves.
- **Clean Unweighted Bones** – remove bones with no vertex weights.
- **Clean Unused Vertex Groups** – remove vertex groups not assigned to any vertices.
- **Armature Copy Visual Pose** – copy the current pose (location or rotation) from one armature to another.
