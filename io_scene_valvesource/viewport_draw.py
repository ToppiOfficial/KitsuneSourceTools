import math

import blf
import bpy
import gpu
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from .utils import get_bone_matrix, is_armature, is_mesh_compatible

_handle          = None
_handle_2d       = None
_edgeline_handle = None
_edgeline_cache: dict    = {}   # ob.session_uid -> (cache_key, [(color, verts)])
_edgeline_mesh_map: dict = {}   # mesh.session_uid -> ob.session_uid (for weight-paint invalidation)
_edgeline_last_mode: str = ''   # previous context.mode, used to detect pose-mode exit
_edgeline_depsgraph_handle = None
_EDGELINE_THICK_CLAMP = 3.5   # mirrors solid.thickness_clamp in EdgelineBuilder
_label_queue: list       = []


def _is_source2(context):
    try:
        vs = context.scene.vs
        return vs.export_format == 'DMX' and vs.dmx_format in ('22', '22_modeldoc')
    except Exception:
        return False


def _get_bone_color(pb):
    try:
        bc = pb.color
        if bc.palette == 'CUSTOM':
            c = bc.custom.normal
            return (c[0], c[1], c[2])
        elif bc.palette != 'DEFAULT':
            idx = int(bc.palette[5:]) - 1  # 'THEME01'->0 … 'THEME20'->19
            c = bpy.context.preferences.themes[0].bone_color_sets[idx].normal
            return (c[0], c[1], c[2])
    except Exception:
        pass
    return (1, 1, 1)


def _bone_octahedron_verts(mat, length):
    s    = length * 0.12
    loc  = mat.to_translation()
    x_ax = Vector((mat[0][0], mat[1][0], mat[2][0])).normalized()
    y_ax = Vector((mat[0][1], mat[1][1], mat[2][1])).normalized()
    z_ax = Vector((mat[0][2], mat[1][2], mat[2][2])).normalized()
    _r   = 0.7071067811865476  # 1/sqrt(2) - rotates ring 45° around Y
    rx   = (x_ax + z_ax) * _r
    rz   = (z_ax - x_ax) * _r
    head = loc
    tail = loc + y_ax * length
    vr   = loc + rx * s + y_ax * s
    vl   = loc - rx * s + y_ax * s
    vf   = loc + rz * s + y_ax * s
    vb   = loc - rz * s + y_ax * s
    return head, tail, vr, vl, vf, vb


def _bone_octahedron_tris_split(mat, length):
    """Returns (lit_tris, shadow_tris) where the face with the most -Z normal is shadowed."""
    head, tail, vr, vl, vf, vb = _bone_octahedron_verts(mat, length)
    faces = [
        (head, vr, vf), (head, vf, vl), (head, vl, vb), (head, vb, vr),
        (tail, vf, vr), (tail, vl, vf), (tail, vb, vl), (tail, vr, vb),
    ]
    nz = [(b - a).cross(c - a).z for a, b, c in faces]
    shadow_idxs = {nz.index(min(nz)), nz.index(max(nz))}
    lit, shadow = [], []
    for i, (a, b, c) in enumerate(faces):
        (shadow if i in shadow_idxs else lit).extend([a, b, c])
    return lit, shadow


def _bone_octahedron_lines(mat, length):
    head, tail, vr, vl, vf, vb = _bone_octahedron_verts(mat, length)
    return [head, vr,  head, vl,  head, vf,  head, vb]


# -- Jiggle geometry helpers ----------------------------------------------------

def _plane_tris(tip, fwd, perp, angle, length, width_scale=0.7):
    """Flat rectangular plane at `angle` rad from fwd toward perp - one page of the book.
    Length is measured along fwd so the plane always reaches full length regardless of angle."""
    dir_vec = (fwd * math.cos(angle) + perp * math.sin(angle)).normalized()
    side    = fwd.cross(perp).normalized()
    hw      = length * width_scale
    far     = tip + dir_vec * length
    a = tip - side * hw
    b = tip + side * hw
    c = far + side * hw
    d = far - side * hw
    return [a, b, c,  a, c, d]


def _plane_lines(tip, fwd, perp, angle, length, width_scale=0.7):
    """Outline of the rectangular plane."""
    dir_vec = (fwd * math.cos(angle) + perp * math.sin(angle)).normalized()
    side    = fwd.cross(perp).normalized()
    hw      = length * width_scale
    far     = tip + dir_vec * length
    a = tip - side * hw
    b = tip + side * hw
    c = far + side * hw
    d = far - side * hw
    return [a, b,  b, c,  c, d,  d, a]


def _cone_tris(tip, fwd, p1, p2, half_angle, h, n=24):
    r      = h * math.tan(half_angle)
    base_c = tip + fwd * h
    circle = [base_c + (p1 * math.cos(2 * math.pi * i / n) +
                        p2 * math.sin(2 * math.pi * i / n)) * r
              for i in range(n)]
    verts = []
    for i in range(n):
        verts += [tip, circle[i], circle[(i + 1) % n]]
    return verts


def _cone_lines(tip, fwd, p1, p2, half_angle, h, n=24):
    r      = h * math.tan(half_angle)
    base_c = tip + fwd * h
    circle = [base_c + (p1 * math.cos(2 * math.pi * i / n) +
                        p2 * math.sin(2 * math.pi * i / n)) * r
              for i in range(n)]
    verts = []
    for s in (0, n // 4, n // 2, 3 * n // 4):
        verts += [tip, circle[s]]
    for i in range(n):
        verts += [circle[i], circle[(i + 1) % n]]
    return verts


def _stick_tris(origin, y_ax, x_ax, z_ax, length, width):
    hw = width * 0.5
    s0 = origin + (-x_ax - z_ax) * hw
    s1 = origin + ( x_ax - z_ax) * hw
    s2 = origin + ( x_ax + z_ax) * hw
    s3 = origin + (-x_ax + z_ax) * hw
    e0 = s0 + y_ax * length
    e1 = s1 + y_ax * length
    e2 = s2 + y_ax * length
    e3 = s3 + y_ax * length
    verts = []
    for a, b, c, d in [(s0, s1, e1, e0), (s1, s2, e2, e1), (s2, s3, e3, e2), (s3, s0, e0, e3)]:
        verts += [a, b, c,  a, c, d]
    verts += [e0, e1, e2,  e0, e2, e3]
    return verts


def _stick_lines(origin, y_ax, x_ax, z_ax, length, width):
    hw = width * 0.5
    s0 = origin + (-x_ax - z_ax) * hw
    s1 = origin + ( x_ax - z_ax) * hw
    s2 = origin + ( x_ax + z_ax) * hw
    s3 = origin + (-x_ax + z_ax) * hw
    e0 = s0 + y_ax * length
    e1 = s1 + y_ax * length
    e2 = s2 + y_ax * length
    e3 = s3 + y_ax * length
    return [
        s0, s1,  s1, s2,  s2, s3,  s3, s0,
        e0, e1,  e1, e2,  e2, e3,  e3, e0,
        s0, e0,  s1, e1,  s2, e2,  s3, e3,
    ]


def _capsule_lines(tip, fwd, perp1, perp2, length, radius, n=16):
    end = tip + fwd * length
    ring_s = [tip + (perp1 * math.cos(2*math.pi*i/n) + perp2 * math.sin(2*math.pi*i/n)) * radius
              for i in range(n)]
    ring_e = [end + (perp1 * math.cos(2*math.pi*i/n) + perp2 * math.sin(2*math.pi*i/n)) * radius
              for i in range(n)]
    verts = []
    for i in range(n):
        verts += [ring_s[i], ring_s[(i+1)%n]]
        verts += [ring_e[i], ring_e[(i+1)%n]]
    for perp, s in ((perp1, 1), (perp1, -1), (perp2, 1), (perp2, -1)):
        p = perp * s * radius
        verts += [tip + p, end + p]
    half = n // 2
    for perp in (perp1, perp2):
        for center, sign in ((tip, -1), (end, 1)):
            arc = [center + (perp * math.cos(math.pi * i / half) +
                             fwd * sign * math.sin(math.pi * i / half)) * radius
                   for i in range(half + 1)]
            for i in range(len(arc) - 1):
                verts += [arc[i], arc[i+1]]
    return verts


def _capsule_tris(tip, fwd, perp1, perp2, length, radius, n=16):
    end   = tip + fwd * length
    ring_s = [tip + (perp1 * math.cos(2*math.pi*i/n) + perp2 * math.sin(2*math.pi*i/n)) * radius
              for i in range(n)]
    ring_e = [end + (perp1 * math.cos(2*math.pi*i/n) + perp2 * math.sin(2*math.pi*i/n)) * radius
              for i in range(n)]
    verts = []
    for i in range(n):
        j = (i+1) % n
        verts += [ring_s[i], ring_s[j], ring_e[i], ring_s[j], ring_e[j], ring_e[i]]
    pole_s = tip - fwd * radius
    pole_e = end + fwd * radius
    for i in range(n):
        verts += [pole_s, ring_s[(i+1)%n], ring_s[i]]
        verts += [pole_e, ring_e[i], ring_e[(i+1)%n]]
    return verts


def _box_tris(center, l_ax, u_ax, f_ax, l_min, l_max, u_min, u_max, f_min, f_max):
    def c(ls, us, fs):
        return (center
                + l_ax * (l_max if ls else -l_min)
                + u_ax * (u_max if us else -u_min)
                + f_ax * (f_max if fs else -f_min))
    def quad(a, b, cc, d):
        return [a, b, cc,  a, cc, d]
    return (
        quad(c(0,0,0), c(0,0,1), c(0,1,1), c(0,1,0)) +
        quad(c(1,0,0), c(1,1,0), c(1,1,1), c(1,0,1)) +
        quad(c(0,0,0), c(1,0,0), c(1,0,1), c(0,0,1)) +
        quad(c(0,1,0), c(0,1,1), c(1,1,1), c(1,1,0)) +
        quad(c(0,0,0), c(0,1,0), c(1,1,0), c(1,0,0)) +
        quad(c(0,0,1), c(1,0,1), c(1,1,1), c(0,1,1))
    )


def _box_lines(center, l_ax, u_ax, f_ax, l_min, l_max, u_min, u_max, f_min, f_max):
    def c(ls, us, fs):
        return (center
                + l_ax * (l_max if ls else -l_min)
                + u_ax * (u_max if us else -u_min)
                + f_ax * (f_max if fs else -f_min))
    return [
        c(0,0,0), c(1,0,0),  c(0,1,0), c(1,1,0),  c(0,0,1), c(1,0,1),  c(0,1,1), c(1,1,1),
        c(0,0,0), c(0,1,0),  c(1,0,0), c(1,1,0),  c(0,0,1), c(0,1,1),  c(1,0,1), c(1,1,1),
        c(0,0,0), c(0,0,1),  c(1,0,0), c(1,0,1),  c(0,1,0), c(0,1,1),  c(1,1,0), c(1,1,1),
    ]


# Jiggle constraint colors: pitch=red, yaw=blue, angle=green, base spring=cyan
_COLOR_PITCH        = (1.0, 0.2, 0.2)
_COLOR_YAW          = (0.2, 0.4, 1.0)
_COLOR_ANGLE        = (0.2, 1.0, 0.3)
_COLOR_BASE_SPRING  = (0.2, 0.9, 0.9)


def _draw_jigglebone(shader, pb, ghost_mat, cr, cg, cb, s2, scale_fac=1.0):
    jvs  = pb.bone.vs
    x_ax = Vector((ghost_mat[0][0], ghost_mat[1][0], ghost_mat[2][0])).normalized()
    y_ax = Vector((ghost_mat[0][1], ghost_mat[1][1], ghost_mat[2][1])).normalized()
    z_ax = Vector((ghost_mat[0][2], ghost_mat[1][2], ghost_mat[2][2])).normalized()
    tip  = ghost_mat.to_translation()

    if s2:
        fwd        = x_ax
        yaw_perp   = y_ax  # yaw fan sweeps fwd->y
        pitch_perp = z_ax  # pitch fan sweeps fwd->z
        perp1      = y_ax
        perp2      = z_ax
    else:
        # Source 1: bone points along +Z
        fwd        = z_ax
        yaw_perp   = x_ax  # yaw fan sweeps fwd->x (left/right)
        pitch_perp = y_ax  # pitch fan sweeps fwd->y (up/down)
        perp1      = x_ax
        perp2      = y_ax

    has_angle       = jvs.jiggle_has_angle_constraint and jvs.jiggle_angle_constraint > 0
    has_yaw         = jvs.jiggle_has_yaw_constraint   and (jvs.jiggle_yaw_constraint_min   > 0 or jvs.jiggle_yaw_constraint_max   > 0)
    has_pitch       = jvs.jiggle_has_pitch_constraint and (jvs.jiggle_pitch_constraint_min > 0 or jvs.jiggle_pitch_constraint_max > 0)
    has_length      = not jvs.use_bone_length_for_jigglebone_length and jvs.jiggle_length > 0
    has_base_spring = jvs.jiggle_base_type == 'BASESPRING'

    if not has_angle and not has_yaw and not has_pitch and not has_length and not has_base_spring:
        return

    display_len = (pb.bone.length if jvs.use_bone_length_for_jigglebone_length else (
        jvs.jiggle_length if jvs.jiggle_length > 0 else pb.bone.length
    )) * scale_fac
    plane_len = pb.bone.length * 0.5 * scale_fac

    if has_angle:
        r, g, b = _COLOR_ANGLE
        tris  = _cone_tris(tip, fwd, perp1, perp2, jvs.jiggle_angle_constraint, display_len * 0.8)
        lines = _cone_lines(tip, fwd, perp1, perp2, jvs.jiggle_angle_constraint, display_len * 0.8)
        gpu.state.depth_mask_set(False)
        shader.uniform_float('color', (r, g, b, 0.10))
        batch_for_shader(shader, 'TRIS', {'pos': tris}).draw(shader)
        gpu.state.depth_mask_set(True)
        gpu.state.line_width_set(1.5)
        shader.uniform_float('color', (r, g, b, 0.55))
        batch_for_shader(shader, 'LINES', {'pos': lines}).draw(shader)

    if has_pitch:
        r, g, b = _COLOR_PITCH
        min_a = jvs.jiggle_pitch_constraint_min
        max_a = jvs.jiggle_pitch_constraint_max
        tris  = (_plane_tris(tip, fwd, pitch_perp, -min_a, plane_len) +
                 _plane_tris(tip, fwd, pitch_perp, +max_a, plane_len))
        lines = (_plane_lines(tip, fwd, pitch_perp, -min_a, plane_len) +
                 _plane_lines(tip, fwd, pitch_perp, +max_a, plane_len))
        gpu.state.depth_mask_set(False)
        shader.uniform_float('color', (r, g, b, 0.15))
        batch_for_shader(shader, 'TRIS', {'pos': tris}).draw(shader)
        gpu.state.depth_mask_set(True)
        gpu.state.line_width_set(1.5)
        shader.uniform_float('color', (r, g, b, 0.75))
        batch_for_shader(shader, 'LINES', {'pos': lines}).draw(shader)

    if has_yaw:
        r, g, b = _COLOR_YAW
        min_a = jvs.jiggle_yaw_constraint_min
        max_a = jvs.jiggle_yaw_constraint_max
        tris  = (_plane_tris(tip, fwd, yaw_perp, -min_a, plane_len) +
                 _plane_tris(tip, fwd, yaw_perp, +max_a, plane_len))
        lines = (_plane_lines(tip, fwd, yaw_perp, -min_a, plane_len) +
                 _plane_lines(tip, fwd, yaw_perp, +max_a, plane_len))
        gpu.state.depth_mask_set(False)
        shader.uniform_float('color', (r, g, b, 0.15))
        batch_for_shader(shader, 'TRIS', {'pos': tris}).draw(shader)
        gpu.state.depth_mask_set(True)
        gpu.state.line_width_set(1.5)
        shader.uniform_float('color', (r, g, b, 0.75))
        batch_for_shader(shader, 'LINES', {'pos': lines}).draw(shader)

    if has_base_spring:
        if s2:
            box_l, box_u, box_f = z_ax, y_ax, x_ax
        else:
            box_l, box_u, box_f = x_ax, y_ax, z_ax
        l_min = (jvs.jiggle_left_constraint_min    if jvs.jiggle_has_left_constraint    else 0) * scale_fac
        l_max = (jvs.jiggle_left_constraint_max    if jvs.jiggle_has_left_constraint    else 0) * scale_fac
        u_min = (jvs.jiggle_up_constraint_min      if jvs.jiggle_has_up_constraint      else 0) * scale_fac
        u_max = (jvs.jiggle_up_constraint_max      if jvs.jiggle_has_up_constraint      else 0) * scale_fac
        f_min = (jvs.jiggle_forward_constraint_min if jvs.jiggle_has_forward_constraint else 0) * scale_fac
        f_max = (jvs.jiggle_forward_constraint_max if jvs.jiggle_has_forward_constraint else 0) * scale_fac
        if l_min or l_max or u_min or u_max or f_min or f_max:
            r, g, b = _COLOR_BASE_SPRING
            tris  = _box_tris(tip, box_l, box_u, box_f, l_min, l_max, u_min, u_max, f_min, f_max)
            lines = _box_lines(tip, box_l, box_u, box_f, l_min, l_max, u_min, u_max, f_min, f_max)
            gpu.state.depth_mask_set(False)
            shader.uniform_float('color', (r, g, b, 0.12))
            batch_for_shader(shader, 'TRIS', {'pos': tris}).draw(shader)
            gpu.state.depth_mask_set(True)
            gpu.state.line_width_set(1.5)
            shader.uniform_float('color', (r, g, b, 0.65))
            batch_for_shader(shader, 'LINES', {'pos': lines}).draw(shader)

    if has_length:
        cap_r = pb.bone.length * scale_fac * 0.06
        tris  = _capsule_tris(tip, fwd, perp1, perp2, display_len, cap_r)
        lines = _capsule_lines(tip, fwd, perp1, perp2, display_len, cap_r)
        gpu.state.depth_mask_set(False)
        shader.uniform_float('color', (cr, cg, cb, 0.10))
        batch_for_shader(shader, 'TRIS', {'pos': tris}).draw(shader)
        gpu.state.depth_mask_set(True)
        gpu.state.line_width_set(1.5)
        shader.uniform_float('color', (cr, cg, cb, 0.70))
        batch_for_shader(shader, 'LINES', {'pos': lines}).draw(shader)


_AXIS_COLORS = (
    ((1.0,  0.4,  0.4),  'X'),
    ((0.4,  1.0,  0.4),  'Y'),
    ((0.4,  0.55, 1.0),  'Z'),
)


def _draw_ghost_axes(shader, context, ghost_mat, bone_length):
    tip    = ghost_mat.to_translation()
    axes   = [Vector((ghost_mat[r][c] for r in range(3))).normalized() for c in range(3)]
    scale  = bone_length * 0.45
    region = context.region
    rv3d   = context.region_data

    gpu.state.line_width_set(2.0)
    for ax, ((r, g, b), label) in zip(axes, _AXIS_COLORS):
        end = tip + ax * scale
        shader.uniform_float('color', (r, g, b, 1.0))
        batch_for_shader(shader, 'LINES', {'pos': [tip, end]}).draw(shader)
        pos_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, end)
        if pos_2d:
            _label_queue.append((pos_2d.x + 3, pos_2d.y + 3, r, g, b, label))


def _draw_labels_2d():
    if not _label_queue:
        return
    try:
        dm        = 8
        shader_2d = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        for x, y, r, g, b, text in _label_queue:
            # filled diamond at axis tip
            shader_2d.bind()
            shader_2d.uniform_float('color', (r, g, b, 1.0))
            batch_for_shader(shader_2d, 'TRIS', {'pos': [
                (x, y + dm), (x + dm, y), (x, y - dm),
                (x, y + dm), (x, y - dm), (x - dm, y),
            ]}).draw(shader_2d)
            # centered label just above the diamond
            blf.size(0, 14)
            blf.color(0, r, g, b, 1.0)
            w, h = blf.dimensions(0, text)
            blf.position(0, x - w * 0.5, y + dm + 4, 0)
            blf.draw(0, text)
        gpu.state.blend_set('NONE')
    except Exception:
        pass
    _label_queue.clear()


# -- Main draw callback ---------------------------------------------------------

def _draw_export_pose_preview():
    try:
        context = bpy.context

        if context.mode == 'EDIT_ARMATURE':
            ob = context.active_object
            if not ob or not is_armature(ob):
                return
            if not context.selected_bones or ob.data.show_axes:
                return
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            gpu.state.blend_set('ALPHA')
            gpu.state.depth_test_set('ALWAYS')
            shader.bind()
            for eb in context.selected_bones:
                pb = ob.pose.bones.get(eb.name)
                if pb is None:
                    continue
                ghost_mat = ob.matrix_world @ get_bone_matrix(eb.matrix, pb)
                y_col     = Vector((ghost_mat[0][1], ghost_mat[1][1], ghost_mat[2][1]))
                world_bl  = eb.length * y_col.length
                _draw_ghost_axes(shader, context, ghost_mat, world_bl)
            gpu.state.blend_set('NONE')
            gpu.state.depth_test_set('NONE')
            gpu.state.line_width_set(1.0)
            return

        if context.mode != 'POSE':
            return
        
        ob = context.active_object
        if not ob or not is_armature(ob):
            return
        preview_pose = context.scene.vs.preview_export_pose
        if not context.selected_pose_bones:
            return

        s2     = _is_source2(context)
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('ALWAYS')
        gpu.state.face_culling_set('NONE')
        shader.bind()

        for pb in context.selected_pose_bones:
            b = pb.bone.vs
            has_rot = not b.ignore_rotation_offset and any((
                b.export_rotation_offset_x, b.export_rotation_offset_y, b.export_rotation_offset_z
            ))
            has_loc = not b.ignore_location_offset and any((
                b.export_location_offset_x, b.export_location_offset_y, b.export_location_offset_z
            ))
            is_jiggle = b.bone_is_jigglebone

            if not is_jiggle and not preview_pose:
                continue
            if not has_rot and not has_loc and not is_jiggle:
                continue

            bl        = pb.bone.length
            ghost_mat = ob.matrix_world @ get_bone_matrix(pb)
            curr_mat  = ob.matrix_world @ pb.matrix
            cr, cg, cb = _get_bone_color(pb)

            # Scale factor: length of ghost_mat Y column encodes object's world scale
            y_col     = Vector((ghost_mat[0][1], ghost_mat[1][1], ghost_mat[2][1]))
            scale_fac = y_col.length
            world_bl  = bl * scale_fac

            if preview_pose and (has_rot or has_loc):
                lit_tris, shadow_tris = _bone_octahedron_tris_split(ghost_mat, world_bl)
                gpu.state.face_culling_set('BACK')
                gpu.state.depth_mask_set(False)
                if shadow_tris:
                    shader.uniform_float('color', (cr * 0.5, cg * 0.5, cb * 0.5, 0.30))
                    batch_for_shader(shader, 'TRIS', {'pos': shadow_tris}).draw(shader)
                if lit_tris:
                    shader.uniform_float('color', (cr, cg, cb, 0.25))
                    batch_for_shader(shader, 'TRIS', {'pos': lit_tris}).draw(shader)
                gpu.state.depth_mask_set(True)
                gpu.state.face_culling_set('NONE')

                gpu.state.line_width_set(2.0)
                shader.uniform_float('color', (cr, cg, cb, 0.85))
                batch_for_shader(shader, 'LINES', {'pos': _bone_octahedron_lines(ghost_mat, world_bl)}).draw(shader)

                ghost_y    = y_col.normalized()
                curr_y     = Vector((curr_mat[0][1], curr_mat[1][1], curr_mat[2][1])).normalized()
                ghost_tail = ghost_mat.to_translation() + ghost_y * world_bl
                curr_tail  = curr_mat.to_translation()  + curr_y  * world_bl
                gpu.state.line_width_set(1.5)
                shader.uniform_float('color', (0.6, 0.85, 1.0, 0.55))
                batch_for_shader(shader, 'LINES', {'pos': [curr_tail, ghost_tail]}).draw(shader)

                if not ob.data.show_axes:
                    _draw_ghost_axes(shader, context, ghost_mat, world_bl)

            if is_jiggle:
                _draw_jigglebone(shader, pb, ghost_mat, cr, cg, cb, s2, scale_fac)

        gpu.state.face_culling_set('NONE')
        gpu.state.blend_set('NONE')
        gpu.state.depth_test_set('NONE')
        gpu.state.line_width_set(1.0)
    except Exception:
        import traceback; traceback.print_exc()


# -- Edgeline preview ----------------------------------------------------------

def _mat_color(mat_name: str) -> tuple:
    """Deterministic RGB from material name - identical across calls, no external deps."""
    h = 0
    for c in mat_name.encode('utf-8'):
        h = (h * 31 + c) & 0xFFFFFFFF
    hue = (h % 1000) / 1000.0
    s, v = 0.75, 0.90
    i   = int(hue * 6)
    f   = hue * 6 - i
    p, q, t_ = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    sector = i % 6
    if sector == 0: return (v,  t_, p)
    if sector == 1: return (q,  v,  p)
    if sector == 2: return (p,  v,  t_)
    if sector == 3: return (p,  q,  v)
    if sector == 4: return (t_, p,  v)
    return (v, p, q)


def _edgeline_cache_key(ob: bpy.types.Object) -> tuple:
    vs  = ob.vs
    mat = ob.matrix_world
    return (
        id(ob.data),
        round(vs.base_toon_edgeline_thickness, 4),
        vs.edgeline_per_material,
        getattr(vs, 'toon_edgeline_vertexgroup', ''),
        getattr(vs, 'non_exportable_vgroup', ''),
        round(getattr(vs, 'non_exportable_vgroup_tolerance', 0.90), 3),
        tuple(round(mat[i][j], 4) for i in range(4) for j in range(4)),
    )


def _build_edgeline_verts(ob: bpy.types.Object, depsgraph) -> list:
    """
    Builds vertex position lists for the edgeline shell - called only on cache miss.
    Returns [(color_rgb, [world_pos, ...]), ...] - GPUBatch created inline at draw time.
    """
    vs             = ob.vs
    thickness      = vs.base_toon_edgeline_thickness
    per_mat        = vs.edgeline_per_material
    edge_vg_name   = getattr(vs, 'toon_edgeline_vertexgroup', '')
    nonexp_vg_name = getattr(vs, 'non_exportable_vgroup', '')
    nonexp_tol     = getattr(vs, 'non_exportable_vgroup_tolerance', 0.90)
    EDGE_HIDE_TOL  = 0.90

    eval_ob = ob.evaluated_get(depsgraph)
    mesh    = eval_ob.to_mesh()
    mesh.calc_loop_triangles()

    # Per-vertex minimum adjacent edge length for thickness clamping.
    # Mirrors MOD_solidify_extrude.cc: offset = abs(thickness) * offset_clamp (3.5),
    # then per-vertex: if min_edge_len < offset -> scalar = min_edge_len / offset -> t *= scalar.
    clamp_offset    = thickness * _EDGELINE_THICK_CLAMP   # reference = thickness * 3.5
    clamp_offset_sq = clamp_offset * clamp_offset
    min_edge_len_sq: dict[int, float] = {}
    verts = mesh.vertices
    for e in mesh.edges:
        i0, i1 = e.vertices
        ln_sq = (Vector(verts[i0].co) - Vector(verts[i1].co)).length_squared
        if ln_sq < min_edge_len_sq.get(i0, float('inf')):
            min_edge_len_sq[i0] = ln_sq
        if ln_sq < min_edge_len_sq.get(i1, float('inf')):
            min_edge_len_sq[i1] = ln_sq

    edge_weights:   dict[int, float] = {}
    nonexp_weights: dict[int, float] = {}

    if edge_vg_name:
        vg = ob.vertex_groups.get(edge_vg_name)
        if vg:
            vgi = vg.index
            for v in mesh.vertices:
                for g in v.groups:
                    if g.group == vgi:
                        edge_weights[v.index] = g.weight
                        break

    if nonexp_vg_name:
        vg = ob.vertex_groups.get(nonexp_vg_name)
        if vg:
            vgi = vg.index
            for v in mesh.vertices:
                for g in v.groups:
                    if g.group == vgi:
                        nonexp_weights[v.index] = g.weight
                        break

    buckets: dict[int, list] = {}
    world_mat = ob.matrix_world

    for tri in mesh.loop_triangles:
        vi = tri.vertices

        if nonexp_weights and all(nonexp_weights.get(i, 0.0) >= nonexp_tol for i in vi):
            continue
        if edge_weights and all(edge_weights.get(i, 0.0) >= EDGE_HIDE_TOL for i in vi):
            continue

        # Face normal (not vertex normal) for displacement: guarantees the direction is
        # outward for front-facing triangles, inward-facing for back faces. This means
        # back-facing shell triangles always displace away from the camera -> fail the depth
        # test -> no bleed-through. Vertex normals at concave areas can average toward the
        # camera even on back-facing triangles, causing the smudge artifact.
        face_normal = Vector(tri.normal)
        slot   = tri.material_index if per_mat else 0
        bucket = buckets.setdefault(slot, [])

        for idx in vi:
            v     = mesh.vertices[idx]
            w     = edge_weights.get(idx, 0.0)
            t     = thickness * (1.0 - w)
            ln_sq = min_edge_len_sq.get(idx, clamp_offset_sq)
            if ln_sq < clamp_offset_sq:
                t *= math.sqrt(ln_sq) / clamp_offset
            bucket.append(world_mat @ (Vector(v.co) + face_normal * t))

    src_mats = ob.data.materials
    eval_ob.to_mesh_clear()

    result = []
    for slot, verts in sorted(buckets.items()):
        if not verts:
            continue
        color = (
            _mat_color(src_mats[slot].name)
            if per_mat and slot < len(src_mats) and src_mats[slot]
            else (0.0, 0.0, 0.0)
        )
        result.append((color, verts))
    return result


def _on_edgeline_depsgraph_update(scene, depsgraph):
    """Invalidate cache entries when an Object or its Mesh data-block is updated."""
    if not _edgeline_cache:
        return
    for update in depsgraph.updates:
        uid = getattr(update.id, 'session_uid', None)
        if uid is None:
            continue
        # Object updated directly (transform, VS properties)
        if uid in _edgeline_cache:
            del _edgeline_cache[uid]
            continue
        # Mesh data-block updated (weight paint, sculpt, edit mode)
        ob_uid = _edgeline_mesh_map.get(uid)
        if ob_uid is not None:
            _edgeline_cache.pop(ob_uid, None)


def _draw_edgeline_preview():
    global _edgeline_last_mode
    try:
        context = bpy.context

        if not getattr(getattr(context.scene, 'vs', None), 'preview_edgeline', False):
            return

        cur_mode = context.mode

        # Edgeline is a static preview only - skip during animation playback.
        if context.screen.is_animation_playing:
            return

        # Edgeline is incompatible with live simulation (pose or jiggle).
        # Clear cache on exit so it rebuilds fresh from the current pose/sim state.
        live = (cur_mode == 'POSE'
                or getattr(getattr(context.scene, 'vs', None), 'jiggle_sim_enabled', False))
        if live:
            if not _edgeline_last_mode.startswith('_live'):
                _edgeline_last_mode = '_live'
            return
        if _edgeline_last_mode == '_live':
            _edgeline_cache.clear()
        _edgeline_last_mode = cur_mode

        if cur_mode.startswith('EDIT'):
            return
        try:
            if context.space_data.shading.type == 'WIREFRAME':
                return
        except Exception:
            return

        depsgraph    = context.evaluated_depsgraph_get()
        shader       = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.depth_mask_set(True)
        gpu.state.blend_set('NONE')
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.face_culling_set('FRONT')
        shader.bind()

        if context.mode == 'PAINT_WEIGHT':
            # Only draw the painted object - always fresh, no cache.
            ob = context.active_object
            if (ob and ob.visible_get()
                    and getattr(getattr(ob, 'vs', None), 'use_toon_edgeline', False)
                    and is_mesh_compatible(ob)):
                try:
                    for color, verts in _build_edgeline_verts(ob, depsgraph):
                        shader.uniform_float('color', (*color, 1.0))
                        batch_for_shader(shader, 'TRIS', {'pos': verts}).draw(shader)
                except Exception:
                    import traceback; traceback.print_exc()
        else:
            for ob in context.view_layer.objects:
                if not ob.visible_get():
                    continue
                if not getattr(getattr(ob, 'vs', None), 'use_toon_edgeline', False):
                    continue
                if not is_mesh_compatible(ob):
                    continue

                try:
                    uid = ob.session_uid
                    key = _edgeline_cache_key(ob)
                    if uid not in _edgeline_cache or _edgeline_cache[uid][0] != key:
                        _edgeline_cache[uid] = (key, _build_edgeline_verts(ob, depsgraph))
                        _edgeline_mesh_map[ob.data.session_uid] = uid
                    for color, verts in _edgeline_cache[uid][1]:
                        shader.uniform_float('color', (*color, 1.0))
                        batch_for_shader(shader, 'TRIS', {'pos': verts}).draw(shader)
                except Exception:
                    import traceback; traceback.print_exc()

        gpu.state.face_culling_set('NONE')
        gpu.state.depth_test_set('NONE')
        gpu.state.blend_set('NONE')
    except Exception:
        import traceback; traceback.print_exc()


def register_draw_handler():
    global _handle, _handle_2d, _edgeline_handle, _edgeline_depsgraph_handle
    if _handle is not None:
        try: bpy.types.SpaceView3D.draw_handler_remove(_handle, 'WINDOW')
        except Exception: pass
    if _handle_2d is not None:
        try: bpy.types.SpaceView3D.draw_handler_remove(_handle_2d, 'WINDOW')
        except Exception: pass
    if _edgeline_handle is not None:
        try: bpy.types.SpaceView3D.draw_handler_remove(_edgeline_handle, 'WINDOW')
        except Exception: pass
    if _edgeline_depsgraph_handle is not None:
        try: bpy.app.handlers.depsgraph_update_post.remove(_edgeline_depsgraph_handle)
        except Exception: pass
    _edgeline_cache.clear()
    _edgeline_mesh_map.clear()
    _handle    = bpy.types.SpaceView3D.draw_handler_add(
        _draw_export_pose_preview, (), 'WINDOW', 'POST_VIEW'
    )
    _handle_2d = bpy.types.SpaceView3D.draw_handler_add(
        _draw_labels_2d, (), 'WINDOW', 'POST_PIXEL'
    )
    _edgeline_handle = bpy.types.SpaceView3D.draw_handler_add(
        _draw_edgeline_preview, (), 'WINDOW', 'POST_VIEW'
    )
    bpy.app.handlers.depsgraph_update_post.append(_on_edgeline_depsgraph_update)
    _edgeline_depsgraph_handle = _on_edgeline_depsgraph_update


def unregister_draw_handler():
    global _handle, _handle_2d, _edgeline_handle, _edgeline_depsgraph_handle
    if _handle is not None:
        try: bpy.types.SpaceView3D.draw_handler_remove(_handle, 'WINDOW')
        except Exception: pass
        _handle = None
    if _handle_2d is not None:
        try: bpy.types.SpaceView3D.draw_handler_remove(_handle_2d, 'WINDOW')
        except Exception: pass
        _handle_2d = None
    if _edgeline_handle is not None:
        try: bpy.types.SpaceView3D.draw_handler_remove(_edgeline_handle, 'WINDOW')
        except Exception: pass
        _edgeline_handle = None
    if _edgeline_depsgraph_handle is not None:
        try: bpy.app.handlers.depsgraph_update_post.remove(_edgeline_depsgraph_handle)
        except Exception: pass
        _edgeline_depsgraph_handle = None
    _edgeline_cache.clear()
    _edgeline_mesh_map.clear()