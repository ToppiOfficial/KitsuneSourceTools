import bpy, re, math, typing, math, collections, mathutils
from .common import sanitizeString, getArmature, sortBonesByHierachy, PreserveContextMode

_shortcut_pattern = re.compile(r"!(\w+)")

shortcut_keywords = {
    "vbip": "ValveBiped.Bip01",
}

def getBoneExportName(bone: typing.Union[bpy.types.Bone, bpy.types.PoseBone]) -> str:
    """Generate the export name for a bone or posebone, respecting custom naming rules."""
    
    if not isinstance(bone, (bpy.types.Bone, bpy.types.PoseBone)):
        return bone.name if hasattr(bone, "name") else str(bone)

    # Resolve to data bone if PoseBone is given
    if isinstance(bone, bpy.types.PoseBone):
        data_bone = bone.bone
    else:
        data_bone = bone

    bone_prop = data_bone.vs
    armature = getArmature(data_bone)
    arm_prop = armature.data.vs

    # Safer future-proof: use matrix_local translation
    bone_head_local = data_bone.matrix_local.to_translation()
    side = (
        arm_prop.bone_direction_naming_right
        if bone_head_local.x < 0
        else arm_prop.bone_direction_naming_left
    )

    # Base name (skip custom export name for jiggle bones)
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

        raw_name = _shortcut_pattern.sub(replace_shortcut, raw_name)

        # Handle counters for '$'
        key = (raw_name, b_side)
        if "$" in raw_name:
            base_name = raw_name.replace("$", str(name_count[key])).strip()
            name_count[key] += 1
            export_names[b.name] = base_name
        else:
            export_names[b.name] = raw_name

    return sanitizeString(export_names[bone.name])

def getBoneMatrix(data, bone : bpy.types.PoseBone = None):
    if isinstance(data, bpy.types.PoseBone):
        matrix = data.matrix
        bone = data
    else:
        matrix = data

    if bone is None:
        return matrix
    
    b_Prop = bone.bone.vs
    
    if b_Prop.ignore_rotation_offset:
        rot_offset_x, rot_offset_y, rot_offset_z = 0, 0, 0
    else:
        rot_offset_x = b_Prop.export_rotation_offset_x
        rot_offset_y = b_Prop.export_rotation_offset_y
        rot_offset_z = b_Prop.export_rotation_offset_z
    
    if b_Prop.ignore_location_offset:
        loc_offset_x, loc_offset_y, loc_offset_z = 0, 0, 0
    else:
        loc_offset_x = b_Prop.export_location_offset_x
        loc_offset_y = b_Prop.export_location_offset_y
        loc_offset_z = b_Prop.export_location_offset_z
    
    loc_offset_matrix = mathutils.Matrix.Translation((loc_offset_x, loc_offset_y, loc_offset_z))
    rot_offset_matrix = (
        mathutils.Matrix.Rotation(rot_offset_z, 4, 'Z') @
        mathutils.Matrix.Rotation(rot_offset_y, 4, 'Y') @
        mathutils.Matrix.Rotation(rot_offset_x, 4, 'X')
    )
    
    # Combine translation and rotation: translation happens AFTER rotation
    combined_matrix = loc_offset_matrix @ rot_offset_matrix
    final_matrix = matrix @ combined_matrix
    
    return final_matrix
    
def getRelativeTargetMatrix(slave : bpy.types.PoseBone, master : bpy.types.PoseBone = None, axis : str = 'XYZ', is_string = False) -> mathutils.Vector:
    
    if slave is None: return None
    
    slave_matrix = getBoneMatrix(slave)
    master_matrix = getBoneMatrix(master) if master is not None else None
    
    local_matrix = slave_matrix
    if master_matrix is not None:
        local_matrix = master_matrix.inverted_safe() @ slave_matrix
    
    euler_conversion = local_matrix.to_euler()
    angles = [math.degrees(euler_conversion.x), math.degrees(euler_conversion.y), math.degrees(euler_conversion.z)]
    
    axis_map = {'X': angles[0], 'Y': angles[1], 'Z': angles[2]}
    rotation = list(axis_map[axis_char] for axis_char in axis)
   
    return " ".join(f"{v}" for v in rotation) if is_string else rotation