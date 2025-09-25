# KitsuneSourceTool

> **ALPHA RELEASE – PARTIALLY FINISHED & EXPERIMENTAL**  
> This is in early development and partially tested. Some features may be incomplete or broken, and more features will be added. Use at your own risk.

**Version Alpha** – A fork of BlenderSourceTool that adds small features for DMX models and incorporates utilities adapted from **AvatarToolkit** and **CATS**.

> [!WARNING]
> Some panels and tools lack translation support, and most labels are in English.  
> Additionally, many tools do not have tooltips.

## Versions

Blender 4.5+ (4.3 or 4.2 Untested)

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
- ⚠️ StudioMDL requires attachments to be parented to a bone. Unparented empties will not be exported.

### Export Bones Under a Different Name
- Allows exporting armature bones with a custom name via the `Export Name` property.

### Vertex Bone Influence Count
- Specify how many bones can influence a vertex (default is 4 for Source 2).

### Simple JiggleBone Setup
- Set up jigglebones on the armature and export values to QCI or VMDL.  
- Note: Jigglebones are not simulated in Blender.

### Additional Blender Toolkit
Utilities to streamline rigging, weight painting, and mesh preparation:

- **Bone Merging** – merge multiple bones into one.
- **Armature Merging** – combine multiple armatures into one.
- **Vertex Group Math** – perform basic arithmetic operations (`+`, `-`, `*`, `/`) between vertex groups.
- **Vertex Group Curve Conversion** – convert vertex group weights using curves.
- **Clean Unweighted Bones** – remove bones with no vertex weights.
- **Clean Unused Vertex Groups** – remove vertex groups not assigned to any vertices.
- **Armature Copy Visual Pose** – copy the current pose (location or rotation) from one armature to another.
