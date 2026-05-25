#   MIT License
#   
#   Copyright (c) 2024 Jakob
#   
#   Permission is hereby granted, free of charge, to any person obtaining a copy
#   of this software and associated documentation files (the "Software"), to deal
#   in the Software without restriction, including without limitation the rights
#   to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#   copies of the Software, and to permit persons to whom the Software is
#   furnished to do so, subject to the following conditions:
#   
#   The above copyright notice and this permission notice shall be included in all
#   copies or substantial portions of the Software.
#   
#   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#   IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#   FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#   AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#   LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#   OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#   SOFTWARE.

import time
import math
import bpy
from mathutils import Vector, Matrix, Quaternion


# -- Per-bone simulation state -------------------------------------------------

class BoneSimState:
    __slots__ = (
        'tip_position', 'tip_velocity',
        'base_offset', 'base_velocity',
        'boing_time', 'boing_direction', 'boing_active', 'prev_speed',
        'last_sim_time',
        'base_abs_pos',
    )

    def __init__(self):
        self.tip_position: Vector | None = None
        self.tip_velocity: Vector = Vector()
        self.base_offset:  Vector = Vector()
        self.base_velocity: Vector = Vector()
        self.boing_time: float = 0.0
        self.boing_direction: Vector | None = None
        self.boing_active: bool = False
        self.prev_speed: float = 0.0
        self.last_sim_time: float | None = None
        self.base_abs_pos: Vector | None = None


_states: dict[tuple[str, str], BoneSimState] = {}
_tick_sim_world: dict[tuple[str, str], Matrix] = {}
_timer_handle = None
_last_real_time: float = 0.0


# -- Helpers -------------------------------------------------------------------

def _is_source2(scene) -> bool:
    try:
        vs = scene.vs
        return vs.export_format == 'DMX' and vs.dmx_format in ('22', '22_modeldoc')
    except Exception:
        return False


def _get_state(arm_ob, pb) -> BoneSimState:
    key = (arm_ob.name, pb.name)
    if key not in _states:
        _states[key] = BoneSimState()
    return _states[key]


def _bone_depth(pb) -> int:
    d, p = 0, pb.parent
    while p:
        d += 1
        p = p.parent
    return d


def _get_length(pb, jvs) -> float:
    if jvs.use_bone_length_for_jigglebone_length:
        return pb.bone.length
    return jvs.jiggle_length if jvs.jiggle_length > 0.0 else pb.bone.length


def _get_cols(is_s2: bool) -> tuple[int, int, int]:
    # (fwd_col, yaw_perp_col, pitch_perp_col)
    # Source 2: X-forward (col 0); Source 1: Z-forward (col 2)
    return (0, 1, 2) if is_s2 else (2, 0, 1)


def _col(mat, c: int) -> Vector:
    return Vector([mat[r][c] for r in range(3)]).normalized()


def _get_export_offset_mat(pb) -> Matrix:
    bvs = pb.bone.vs
    if bvs.ignore_rotation_offset:
        return Matrix.Identity(4)
    return (Matrix.Rotation(bvs.export_rotation_offset_z, 4, 'Z') @
            Matrix.Rotation(bvs.export_rotation_offset_y, 4, 'Y') @
            Matrix.Rotation(bvs.export_rotation_offset_x, 4, 'X'))


def _get_animated_goal(arm_ob, pb) -> tuple:
    """Compute goal matrices from the parent chain, bypassing this bone's matrix_basis.

    pb.matrix is contaminated by our own simulation writes on non-keyframed bones.
    For jiggle parents already processed this tick, _tick_sim_world holds the fresh
    simulation result - using it gives zero lag so child goals track the parent's
    current simulated rotation instantly, eliminating the per-level cascade jitter.
    For non-jiggle parents, pb.parent.matrix is the clean animated pose.
    """
    if pb.parent:
        parent_key = (arm_ob.name, pb.parent.name)
        if pb.parent.bone.vs.bone_is_jigglebone and parent_key in _tick_sim_world:
            parent_arm = arm_ob.matrix_world.inverted_safe() @ _tick_sim_world[parent_key]
        else:
            parent_arm = pb.parent.matrix
        bone_in_parent = pb.parent.bone.matrix_local.inverted_safe() @ pb.bone.matrix_local
        arm_mat = parent_arm @ bone_in_parent
    else:
        arm_mat = pb.bone.matrix_local.copy()
    anim_world = arm_ob.matrix_world @ arm_mat
    goal_world  = anim_world @ _get_export_offset_mat(pb)
    return anim_world, goal_world


def _constrain_axis(state: BoneSimState, axis: Vector,
                    enabled: bool, lo: float, hi: float,
                    friction: float, dt: float) -> None:
    if not enabled:
        return
    proj = state.base_offset.dot(axis)
    if proj < lo:
        state.base_offset += axis * (lo - proj)
        comp = state.base_velocity.dot(axis)
        if comp < 0.0 and friction > 0.0:
            state.base_velocity -= axis * comp * min(1.0, friction * dt)
    elif proj > hi:
        state.base_offset += axis * (hi - proj)
        comp = state.base_velocity.dot(axis)
        if comp > 0.0 and friction > 0.0:
            state.base_velocity -= axis * comp * min(1.0, friction * dt)


# -- Per-bone simulation step --------------------------------------------------

def _sim_bone(arm_ob, pb, dt: float, is_s2: bool) -> None:
    jvs  = pb.bone.vs
    state = _get_state(arm_ob, pb)

    now   = time.perf_counter()
    stale = state.last_sim_time is None or (now - state.last_sim_time) > 0.5
    state.last_sim_time = now

    fwd_col, yp_col, pp_col = _get_cols(is_s2)

    # Compute goal from parent chain - NOT from pb.matrix, which retains our own
    # simulation writes on non-keyframed bones and would make the goal chase the sim.
    anim_world, goal_world = _get_animated_goal(arm_ob, pb)

    export_fwd   = _col(goal_world, fwd_col)
    export_perp1 = _col(goal_world, yp_col)   # yaw perp
    export_perp2 = _col(goal_world, pp_col)   # pitch perp
    goal_base    = goal_world.to_translation()
    length       = _get_length(pb, jvs)
    goal_tip     = goal_base + export_fwd * length

    # Start from animated matrix; may be overwritten below
    new_world = anim_world.copy()

    # -- Boing replaces tip flex entirely --------------------------------------
    if jvs.jiggle_base_type == 'BOING':
        current_speed = state.tip_velocity.length if state.tip_position is not None else 0.0
        speed_delta   = abs(current_speed - state.prev_speed)
        impact_thresh = float(jvs.jiggle_impact_speed)

        if speed_delta > impact_thresh and not state.boing_active:
            state.boing_active    = True
            state.boing_time      = 0.0
            state.boing_direction = (state.tip_velocity.normalized()
                                     if current_speed > 1e-6 else export_fwd.copy())
        state.prev_speed = current_speed

        if state.boing_active:
            state.boing_time += dt
            damping = max(0.0, 1.0 - jvs.jiggle_damping_rate * state.boing_time)
            if damping <= 0.0:
                state.boing_active = False
            else:
                flex = (jvs.jiggle_amplitude
                        * math.cos(jvs.jiggle_frequency * state.boing_time)
                        * (damping ** 4))
                boing_dir = state.boing_direction or export_fwd
                sim_tip   = goal_tip + boing_dir * flex
                to_tip    = sim_tip - goal_base
                sim_fwd   = to_tip.normalized() if to_tip.length > 1e-6 else export_fwd
                delta_q   = export_fwd.rotation_difference(sim_fwd)
                new_rot   = (delta_q.to_matrix() @ anim_world.to_3x3()).normalized()
                new_world = new_rot.to_4x4()
                new_world.translation = anim_world.to_translation()

    # -- Tip flex: FLEXIBLE or RIGID -------------------------------------------
    elif jvs.jiggle_flex_type in ('FLEXIBLE', 'RIGID'):
        # RIGID always locks length regardless of allow_length_flex
        allow_length_flex = (jvs.jiggle_allow_length_flex
                             and jvs.jiggle_flex_type == 'FLEXIBLE')

        if stale or state.tip_position is None:
            state.tip_position = goal_tip.copy()
            state.tip_velocity = Vector()

        vel = state.tip_velocity
        error = goal_tip - state.tip_position

        yaw_acc   = (jvs.jiggle_yaw_stiffness  * error.dot(export_perp1)
                     - jvs.jiggle_yaw_damping   * vel.dot(export_perp1))
        pitch_acc = (jvs.jiggle_pitch_stiffness * error.dot(export_perp2)
                     - jvs.jiggle_pitch_damping  * vel.dot(export_perp2))
        if allow_length_flex:
            along_acc = (jvs.jiggle_along_stiffness * error.dot(export_fwd)
                         - jvs.jiggle_along_damping  * vel.dot(export_fwd))
        else:
            along_acc = 0.0

        gravity   = Vector((0.0, 0.0, -jvs.jiggle_tip_mass))
        total_acc = (export_perp1 * yaw_acc
                     + export_perp2 * pitch_acc
                     + export_fwd * along_acc
                     + gravity)

        state.tip_velocity += total_acc * dt
        state.tip_position += state.tip_velocity * dt

        # Angle constraint (global cone)
        if jvs.jiggle_has_angle_constraint and jvs.jiggle_angle_constraint > 0.0:
            to_tip = state.tip_position - goal_base
            if to_tip.length > 1e-6:
                sim_dir = to_tip.normalized()
                cos_a   = max(-1.0, min(1.0, sim_dir.dot(export_fwd)))
                angle   = math.acos(cos_a)
                if angle > jvs.jiggle_angle_constraint:
                    axis = export_fwd.cross(sim_dir)
                    if axis.length > 1e-6:
                        axis.normalize()
                        clamped_fwd = (
                            Quaternion(axis, jvs.jiggle_angle_constraint).to_matrix()
                            @ export_fwd
                        ).normalized()
                        rad = to_tip.length if allow_length_flex else length
                        state.tip_position = goal_base + clamped_fwd * rad
                        # Damp velocity component pointing outside cone
                        excess = sim_dir - clamped_fwd
                        out_v  = state.tip_velocity.dot(excess)
                        if out_v > 0.0:
                            state.tip_velocity -= excess.normalized() * out_v

        # Yaw constraint - min stored positive, represents negative limit (user spec)
        if jvs.jiggle_has_yaw_constraint:
            yaw_min = -jvs.jiggle_yaw_constraint_min
            yaw_max =  jvs.jiggle_yaw_constraint_max
            to_tip  = state.tip_position - goal_base
            pf = to_tip.dot(export_fwd)
            py = to_tip.dot(export_perp1)
            yaw_angle = math.atan2(py, max(pf, 1e-8))
            clamped   = max(yaw_min, min(yaw_max, yaw_angle))
            if abs(clamped - yaw_angle) > 1e-6:
                dist  = math.hypot(pf, py)
                pp_c  = to_tip.dot(export_perp2)
                state.tip_position = (goal_base
                    + export_fwd   * (dist * math.cos(clamped))
                    + export_perp1 * (dist * math.sin(clamped))
                    + export_perp2 * pp_c)
                if jvs.jiggle_yaw_friction > 0.0:
                    yv = state.tip_velocity.dot(export_perp1)
                    state.tip_velocity -= export_perp1 * yv * min(1.0, jvs.jiggle_yaw_friction * dt)

        # Pitch constraint
        if jvs.jiggle_has_pitch_constraint:
            pitch_min = -jvs.jiggle_pitch_constraint_min
            pitch_max =  jvs.jiggle_pitch_constraint_max
            to_tip    = state.tip_position - goal_base
            pf  = to_tip.dot(export_fwd)
            pp  = to_tip.dot(export_perp2)
            pitch_angle = math.atan2(pp, max(pf, 1e-8))
            clamped     = max(pitch_min, min(pitch_max, pitch_angle))
            if abs(clamped - pitch_angle) > 1e-6:
                dist = math.hypot(pf, pp)
                py_c = to_tip.dot(export_perp1)
                state.tip_position = (goal_base
                    + export_fwd   * (dist * math.cos(clamped))
                    + export_perp2 * (dist * math.sin(clamped))
                    + export_perp1 * py_c)
                if jvs.jiggle_pitch_friction > 0.0:
                    pv = state.tip_velocity.dot(export_perp2)
                    state.tip_velocity -= export_perp2 * pv * min(1.0, jvs.jiggle_pitch_friction * dt)

        # Along constraint: lock length for RIGID and when allow_length_flex is False
        if not allow_length_flex:
            to_tip = state.tip_position - goal_base
            if to_tip.length > 1e-6:
                state.tip_position = goal_base + to_tip.normalized() * length
            # Use the post-clamp direction so radial velocity is removed correctly
            sim_dir = to_tip.normalized() if to_tip.length > 1e-6 else export_fwd
            along_v = state.tip_velocity.dot(sim_dir)
            state.tip_velocity -= sim_dir * along_v

        # Reconstruct rotation from simulated tip direction
        to_tip  = state.tip_position - goal_base
        sim_fwd = to_tip.normalized() if to_tip.length > 1e-6 else export_fwd

        # delta_q is a world-space rotation: export_fwd -> sim_fwd.
        # Composing it with the animated rotation correctly carries the export
        # offset along (see plan - at rest delta_q = identity, no visual jump).
        delta_q  = export_fwd.rotation_difference(sim_fwd)
        new_rot  = (delta_q.to_matrix() @ anim_world.to_3x3()).normalized()
        new_world = new_rot.to_4x4()
        new_world.translation = anim_world.to_translation()

        # -- Base spring (may layer on top of tip flex rotation) ---------------
        if jvs.jiggle_base_type == 'BASESPRING':
            anim_base = anim_world.to_translation()
            if stale or state.base_abs_pos is None:
                state.base_abs_pos  = anim_base.copy()
                state.base_velocity = Vector()

            error = anim_base - state.base_abs_pos
            grav  = Vector((0.0, 0.0, -float(jvs.jiggle_base_mass)))
            acc   = (jvs.jiggle_base_stiffness * error
                     - jvs.jiggle_base_damping  * state.base_velocity
                     + grav)
            state.base_velocity += acc * dt
            state.base_abs_pos  += state.base_velocity * dt
            state.base_offset    = state.base_abs_pos - anim_base

            # Axis constraints (lo = stored positive -> treated as negative)
            _constrain_axis(state, export_perp1,
                            jvs.jiggle_has_left_constraint,
                            -jvs.jiggle_left_constraint_min,
                             jvs.jiggle_left_constraint_max,
                            jvs.jiggle_left_friction, dt)
            _constrain_axis(state, export_perp2,
                            jvs.jiggle_has_up_constraint,
                            -jvs.jiggle_up_constraint_min,
                             jvs.jiggle_up_constraint_max,
                            jvs.jiggle_up_friction, dt)
            _constrain_axis(state, export_fwd,
                            jvs.jiggle_has_forward_constraint,
                            -jvs.jiggle_forward_constraint_min,
                             jvs.jiggle_forward_constraint_max,
                            jvs.jiggle_forward_friction, dt)
            state.base_abs_pos = anim_base + state.base_offset

            new_world = new_world.copy()
            new_world.translation = anim_world.to_translation() + state.base_offset

    # -- Standalone base spring (flex_type NONE + base BASESPRING) -------------
    elif jvs.jiggle_base_type == 'BASESPRING':
        anim_base = anim_world.to_translation()
        if stale or state.base_abs_pos is None:
            state.base_abs_pos  = anim_base.copy()
            state.base_velocity = Vector()

        error = anim_base - state.base_abs_pos
        grav  = Vector((0.0, 0.0, -float(jvs.jiggle_base_mass)))
        acc   = (jvs.jiggle_base_stiffness * error
                 - jvs.jiggle_base_damping  * state.base_velocity
                 + grav)
        state.base_velocity += acc * dt
        state.base_abs_pos  += state.base_velocity * dt
        state.base_offset    = state.base_abs_pos - anim_base

        _constrain_axis(state, export_perp1,
                        jvs.jiggle_has_left_constraint,
                        -jvs.jiggle_left_constraint_min,
                         jvs.jiggle_left_constraint_max,
                        jvs.jiggle_left_friction, dt)
        _constrain_axis(state, export_perp2,
                        jvs.jiggle_has_up_constraint,
                        -jvs.jiggle_up_constraint_min,
                         jvs.jiggle_up_constraint_max,
                        jvs.jiggle_up_friction, dt)
        _constrain_axis(state, export_fwd,
                        jvs.jiggle_has_forward_constraint,
                        -jvs.jiggle_forward_constraint_min,
                         jvs.jiggle_forward_constraint_max,
                        jvs.jiggle_forward_friction, dt)
        state.base_abs_pos = anim_base + state.base_offset

        new_world = anim_world.copy()
        new_world.translation = anim_world.to_translation() + state.base_offset

    # Cache this tick's result so child jiggle bones can use it
    _tick_sim_world[(arm_ob.name, pb.name)] = new_world

    # -- Write simulated matrix back to the bone -------------------------------
    local_mat = arm_ob.convert_space(
        pose_bone=pb,
        matrix=new_world,
        from_space='WORLD',
        to_space='LOCAL',
    )
    if jvs.jiggle_base_type == 'BASESPRING':
        pb.matrix_basis = local_mat
    else:
        pb.matrix_basis = local_mat.to_3x3().to_4x4()


# -- Armature-level simulation -------------------------------------------------

def simulate_armature(arm_ob, scene, dt: float) -> None:
    if not arm_ob.pose:
        return
    _tick_sim_world.clear()
    is_s2     = _is_source2(scene)
    jiggle_pbs = [pb for pb in arm_ob.pose.bones
                  if pb.bone.vs.bone_is_jigglebone]
    jiggle_pbs.sort(key=_bone_depth)
    for pb in jiggle_pbs:
        try:
            _sim_bone(arm_ob, pb, dt, is_s2)
        except Exception:
            import traceback
            traceback.print_exc()


def reset_state(arm_ob=None) -> None:
    if arm_ob is None:
        _states.clear()
    else:
        for k in [k for k in _states if k[0] == arm_ob.name]:
            del _states[k]


# -- Timer (real-time viewport simulation) -------------------------------------

def _get_rate() -> float:
    try:
        return 1.0 / bpy.data.scenes[0].vs.jiggle_sim_rate
    except Exception:
        return 1.0 / 60.0


def _timer_callback():
    global _last_real_time
    try:
        ctx = bpy.context
        if ctx is None:
            return _get_rate()

        if ctx.mode not in ('OBJECT', 'POSE'):
            return _get_rate()

        # Frame-change handler drives simulation during timeline playback
        if ctx.screen and ctx.screen.is_animation_playing:
            return _get_rate()

        now = time.perf_counter()
        dt  = min(now - _last_real_time, 0.1)
        _last_real_time = now

        for scene in bpy.data.scenes:
            if not getattr(scene.vs, 'jiggle_sim_enabled', False):
                continue
            for ob in scene.objects:
                if ob.type == 'ARMATURE' and ob.pose:
                    simulate_armature(ob, scene, dt)

        for window in ctx.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()

    except Exception:
        import traceback
        traceback.print_exc()

    return _get_rate()


def _start_timer() -> None:
    global _last_real_time
    if not bpy.app.timers.is_registered(_timer_callback):
        _last_real_time = time.perf_counter()
        bpy.app.timers.register(_timer_callback, first_interval=_get_rate())


def _stop_timer() -> None:
    if bpy.app.timers.is_registered(_timer_callback):
        try:
            bpy.app.timers.unregister(_timer_callback)
        except Exception:
            pass


# -- Frame-change handler (timeline playback) ----------------------------------

@bpy.app.handlers.persistent
def _frame_change_post(scene, depsgraph):
    if not getattr(scene.vs, 'jiggle_sim_enabled', False):
        return
    fps = scene.render.fps / scene.render.fps_base
    dt  = 1.0 / fps
    for ob in scene.objects:
        if ob.type == 'ARMATURE' and ob.pose:
            simulate_armature(ob, scene, dt)


# -- Bone restore helper -------------------------------------------------------

def _restore_jiggle_bones() -> None:
    """Reset matrix_basis to identity on all jiggle bones across all scenes.

    Setting matrix_basis = identity returns each bone to its animated rest pose.
    Blender will overwrite it on the next depsgraph evaluation for keyframed bones;
    for non-keyframed jiggle bones identity IS the animated pose.
    """
    for scene in bpy.data.scenes:
        for ob in scene.objects:
            if ob.type != 'ARMATURE' or not ob.pose:
                continue
            for pb in ob.pose.bones:
                if pb.bone.vs.bone_is_jigglebone:
                    pb.matrix_basis = Matrix.Identity(4)
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except Exception:
        pass


# -- Property update callback --------------------------------------------------

def on_sim_enabled_changed(props, context):
    if props.jiggle_sim_enabled:
        _start_timer()
    else:
        _stop_timer()
        _states.clear()
        _restore_jiggle_bones()


# -- Save handlers -------------------------------------------------------------

_pre_save_jiggle_states: dict[str, bool] = {}


@bpy.app.handlers.persistent
def _save_pre(scene):
    _pre_save_jiggle_states.clear()
    for sc in bpy.data.scenes:
        was = getattr(sc.vs, 'jiggle_sim_enabled', False)
        _pre_save_jiggle_states[sc.name] = was
        if was:
            sc.vs.jiggle_sim_enabled = False


@bpy.app.handlers.persistent
def _save_post(scene):
    for sc in bpy.data.scenes:
        if _pre_save_jiggle_states.get(sc.name, False):
            sc.vs.jiggle_sim_enabled = True
    _pre_save_jiggle_states.clear()


# -- Registration --------------------------------------------------------------


def register() -> None:
    for fn in bpy.app.handlers.frame_change_post[:]:
        if getattr(fn, '__module__', '').endswith('procbones_sim'):
            bpy.app.handlers.frame_change_post.remove(fn)
    bpy.app.handlers.frame_change_post.append(_frame_change_post)
    for fn in bpy.app.handlers.save_pre[:]:
        if getattr(fn, '__module__', '').endswith('procbones_sim'):
            bpy.app.handlers.save_pre.remove(fn)
    bpy.app.handlers.save_pre.append(_save_pre)
    for fn in bpy.app.handlers.save_post[:]:
        if getattr(fn, '__module__', '').endswith('procbones_sim'):
            bpy.app.handlers.save_post.remove(fn)
    bpy.app.handlers.save_post.append(_save_post)


def unregister() -> None:
    _stop_timer()
    _states.clear()
    if _frame_change_post in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(_frame_change_post)
    if _save_pre in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(_save_pre)
    if _save_post in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(_save_post)
