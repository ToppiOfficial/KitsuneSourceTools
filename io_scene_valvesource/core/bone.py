import bpy, re, math, typing, math, collections, mathutils
from .common import sanitizeString, getArmature, sortBonesByHierachy

_shortcut_pattern = re.compile(r"!(\w+)")

shortcut_keywords = {
    "vbip": "ValveBiped.Bip01",
}

direction_map = {
            '.L': '.R', '_L': '_R', 'Left': 'Right', '_Left': '_Right', '.Left': '.Right', 'L_': 'R_', 'L.': 'R.', 'L ': 'R ',
            '.R': '.L', '_R': '_L', 'Right': 'Left', '_Right': '_Left', '.Right': '.Left', 'R_': 'L_', 'R.': 'L.', 'R ': 'L '
        }

def getBoneExportName(bone: typing.Union[bpy.types.Bone, bpy.types.PoseBone], for_write = False) -> str:
    """Generate the export name for a bone or posebone, respecting custom naming rules."""
    
    if not isinstance(bone, (bpy.types.Bone, bpy.types.PoseBone)):
        return bone.name if hasattr(bone, "name") else str(bone)

    if isinstance(bone, bpy.types.PoseBone):
        data_bone = bone.bone
    else:
        data_bone = bone

    bone_prop = data_bone.vs
    armature = getArmature(data_bone)
    arm_prop = armature.data.vs
    
    if arm_prop.ignore_bone_exportnames and not for_write:
        return bone.name

    bone_head_local = data_bone.matrix_local.to_translation()
    side = (
        arm_prop.bone_direction_naming_right
        if bone_head_local.x < 0
        else arm_prop.bone_direction_naming_left
    )

    if getattr(bone_prop, "bone_is_jigglebone", False):
        name = data_bone.name
    else:
        name = bone_prop.export_name.strip() or data_bone.name
    name = name.replace("*", side)

    ordered_bones = sortBonesByHierachy(armature.data.bones)
    name_count = collections.defaultdict(lambda: arm_prop.bone_name_startcount)
    export_names = {}

    for b in ordered_bones:
        b_side = (
            arm_prop.bone_direction_naming_right
            if b.matrix_local.to_translation().x < 0
            else arm_prop.bone_direction_naming_left
        )

        # Resolve base raw name
        raw_name = (
            b.name if getattr(b.vs, "bone_is_jigglebone", False)
            else (b.vs.export_name.strip() or b.name)
        )
        raw_name = raw_name.replace("*", b_side)

        # Replace shortcuts like !vbip
        def replace_shortcut(match):
            return shortcut_keywords.get(match.group(1), match.group(0))

        raw_name = _shortcut_pattern.sub(replace_shortcut, raw_name) # type: ignore

        # Handle counters for '$'
        key = (raw_name, b_side)
        if "$" in raw_name:
            base_name = raw_name.replace("$", str(name_count[key])).strip()
            name_count[key] += 1
            export_names[b.name] = base_name
        else:
            export_names[b.name] = raw_name

    return sanitizeString(export_names[bone.name])

def getCanonicalBoneName(export_name: str) -> str:
    """Convert an exported bone name back to its canonical form:
       - Replaces directional markers with ' * '
       - Converts expanded shortcut names back to '!shortcut!' form
       - Converts underscores to spaces
       - Collapses multiple spaces into a single space
    """
    # Reverse shortcut expansion
    reversed_shortcuts = {v: k for k, v in shortcut_keywords.items()}
    for full, shortcut in reversed_shortcuts.items():
        export_name = export_name.replace(full, f"!{shortcut}!")

    for k, v in direction_map.items():
        export_name = export_name.replace(k, " * ")


    export_name = export_name.replace("_", " ")
    export_name = re.sub(r'\s+', ' ', export_name).strip()

    return export_name

import bpy
import mathutils
from mathutils import Matrix

def getBoneMatrix(
    data: bpy.types.PoseBone | Matrix,
    bone: bpy.types.PoseBone | None = None,
    rest_space : bool = False
) -> Matrix:
    """
    Returns the effective matrix of a PoseBone or matrix with applied export offsets.

    Args:
        data: PoseBone or a 4x4 Matrix.
        bone: Optional PoseBone reference (required for offset properties).
              If not provided and `data` is a PoseBone, it's automatically used.

    Returns:
        Matrix: The final transform matrix with translation and rotation offsets applied.
    """
    # Resolve matrix and bone
    if isinstance(data, bpy.types.PoseBone):
        matrix = data.matrix if not rest_space else data.bone.matrix_local
        bone = data
    elif isinstance(data, Matrix):
        matrix = data

    if bone is None:
        return matrix

    b_props = bone.bone.vs

    # Rotation offsets
    rot_x = 0.0 if b_props.ignore_rotation_offset else b_props.export_rotation_offset_x
    rot_y = 0.0 if b_props.ignore_rotation_offset else b_props.export_rotation_offset_y
    rot_z = 0.0 if b_props.ignore_rotation_offset else b_props.export_rotation_offset_z

    rot_offset_matrix = (
        Matrix.Rotation(rot_z, 4, 'Z') @ # type: ignore
        Matrix.Rotation(rot_y, 4, 'Y') @ # type: ignore
        Matrix.Rotation(rot_x, 4, 'X')  # type: ignore
    )

    # Location offsets
    loc_x = 0.0 if b_props.ignore_location_offset else b_props.export_location_offset_x
    loc_y = 0.0 if b_props.ignore_location_offset else b_props.export_location_offset_y
    loc_z = 0.0 if b_props.ignore_location_offset else b_props.export_location_offset_z

    loc_offset_matrix = Matrix.Translation((loc_x, loc_y, loc_z))

    # Translation after rotation
    offset_matrix = loc_offset_matrix @ rot_offset_matrix

    # Apply offsets in bone space
    return matrix @ offset_matrix


def getRelativeTargetMatrix(
    slave: bpy.types.PoseBone,
    master: bpy.types.PoseBone | None = None,
    axis: str = 'XYZ',
    mode: str = 'ROTATION',
    is_string: bool = False,
    rest_space : bool = True
) -> typing.Union[list[float], str]:
    """
    Returns relative translation or rotation of `slave` to `master`.

    Args:
        slave: PoseBone - the bone to measure.
        master: PoseBone - optional reference bone. If None, uses armature space.
        axis: str - which axes to include (default: 'XYZ').
        mode: str - 'LOCATION' or 'ROTATION'.
        is_string: bool - if True, returns space-separated string.

    Returns:
        list[float] or str: relative location or rotation
    """
    try:
        # Get the matrices (pose space)
        slave_matrix = getBoneMatrix(slave, rest_space=rest_space)
        master_matrix = getBoneMatrix(master, rest_space=rest_space) if master else Matrix.Identity(4)

        # Compute relative matrix: master → slave
        local_offset = master_matrix.inverted_safe() @ slave_matrix

        # Convert to rotation or location
        if mode.upper() == 'ROTATION':
            euler = local_offset.to_euler()
            values = [
                math.degrees(euler.x),
                math.degrees(euler.y),
                math.degrees(euler.z)
            ]
        elif mode.upper() == 'LOCATION':
            translation = local_offset.to_translation()
            values = [translation.x, translation.y, translation.z]
        else:
            raise ValueError("mode must be 'LOCATION' or 'ROTATION'")

        # Filter only selected axes
        axis_map = {'X': values[0], 'Y': values[1], 'Z': values[2]}
        result = [axis_map[a] for a in axis if a in axis_map]

        return " ".join(f"{v:.6f}" for v in result) if is_string else result

    except Exception:
        return "0.0 0.0 0.0" if is_string else [0.0, 0.0, 0.0]
