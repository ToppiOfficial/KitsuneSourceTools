
<p align="center">
  <img width="256" height="256" alt="kitsunelogo"
       src="https://raw.githubusercontent.com/ToppiOfficial/KitsuneSourceTools/refs/heads/master/io_scene_valvesource/icons/kitsunelogo.png" />
</p>

# KitsuneSourceTool [Blender 4.5] [Alpha Release]

KitsuneSourceTool is a fork and extended version of BlenderSourceTool, integrating toolsets from my older, previously unreleased Blender extensions.
It’s primarily tailored to my personal workflow, but I’ve decided to release it publicly for others who may find it useful.

Originally developed under the project name “Fubukitek”, the project was later renamed to Kitsune.
Not all tools have been ported yet — I’m gradually reintroducing features from my older extensions that were built for Blender versions 3.8 through 4.2.

> [!WARNING]
> - The original code for export and others are being modified as well, use at your own risk for your project at this current version
> - Some panels and tools lack translation support, and most labels are in English.  
> - Additionally, many tools do not have tooltips.

## TODO

- [ ] **Source 2 Cloth Node for Bone Config** — Implement a dedicated setup for configuring bone that will be driven by cloth.
- [ ] **Bake Combined Animation** — Allow baking the current animation from multiple selected armatures into a single unified action.
- [ ] **Convert Attachment Empties to Bones** — Add support for converting attachment empties into bones for QC rigid setups.
- [ ] **Procudral Bone/ Rbf Constraints** - Add a dedicated setup for procedural bones for source 1 or Rbf constraints for Source 2

## Export Features

| Export Feature | Description | Notes |
|----------------|--------------|-------|
| **KeyValue3** | Exports Source 2 KeyValue3 files such as `.vmdl` and `.vmdl_prefab`. | This feature is a work in progress. |
| **Vertex Float Maps (Cloth Proxy Mesh)** | Exports Source 2 cloth proxy mesh data, allowing for more advanced cloth setups. | Forked and adapted from [BlenderSourceTools (Rectus)](https://github.com/Rectus/BlenderSourceTools). |
| **DMX Attachments** | Embeds attachments (similar to QC attachments) into DMX data using empties. | Embedded DMX attachments currently work only for Source 1 models, as this feature may have been deprecated in Source 2. |
| **Offset Rotation and Location** | Allows exporting bones with different rotation and location matrices — useful when converting Blender’s Y-forward orientation to X-forward for Source character models. |  |
| **Bone Export Name** | Exports bones under a custom name instead of the Blender bone name. | Useful for remapping bone names without renaming them in the armature. |

## ToolKit Features

### Armature Tools
| Tool | Description | Notes |
|------|--------------|-------|
| **Armature Merging** | Merge two or more armatures into a single armature. | Includes an option to match the visual posture before merging. |
| **Clean Unweighted Bones** | Removes bones from the armature that have no vertex weights. |  |
| **Apply Pose as Rest Pose** | Applies the current pose as the new rest/default pose for the armature. |  |
| **Copy Visual Posture** | Copies the visual bone posture between armatures that share the same bone names. | Similar to Blender’s *Copy Visual Pose* (per bone). |

### Bone Tools
| Tool | Description | Notes |
|------|--------------|-------|
| **Bone Merging** | Merge two or more bones into one. |  |
| **ReAlign Bone** | Realigns a bone’s tip to face its child bone’s head. | Works only if the bone has a single child. |
| **Split Bone** | Splits a bone, similar to Blender’s *Subdivide*, and also splits the corresponding vertex groups. |  |
| **Copy Location or Rotation** | Copies the head and tail positions of a target bone in Edit Mode. | Can exclude specific axes, scale, or roll. |
| **Jigglebones** | Configures and exports jigglebone data for Source 1 or 2 models. | Does not simulate physics in Blender. |
| **Hitbox** | Configures and exports hitboxes for Source 1 models using cube-shaped empties parented to bones. | Must be marked as a hitbox before export. |

### Mesh Tools
| Tool | Description | Notes |
|------|--------------|-------|
| **Clean Shapekeys** | Removes shapekeys that do not move any vertices. | Currently also deletes driver-only shapekeys. |
| **Clean Unused Vertex Groups** | Removes vertex groups without any weight influence. |  |
| **Select Shapekey Vertices** | Selects vertices influenced by a specific shapekey. |  |
| **Add Black Toon Edgeline** | Adds an inverted-hull toon outline with a black material to the selected mesh. | Useful for anime/toon-style shading. |

### Animation Tools
| Tool | Description | Notes |
|------|--------------|-------|
| **Merge Animations** | Merges multiple Action slots into one. |  |
| **Convert Rotation Keyframes** | Converts keyframe rotation modes (e.g., Quaternion ↔ XYZ Euler). |  |
| **Create Proportion Posture Delta** | Generates a proportional and reference animation used for custom-proportion character rigs. | Commonly used in Source character models. |
| **Export Custom Proportion Constraint** | Exports custom proportions via Source 2 Point and Orient constraints. | Uses export names and the actual bone names. |

### Material Tools
| Tool | Description | Notes |
|------|--------------|-------|
| **PBR to Phong** | Converts PBR material maps into Phong-style shading maps. | Uses a custom method tailored for Source materials. |
