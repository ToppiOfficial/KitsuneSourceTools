#  Copyright (c) 2014 Tom Edwards contact@steamreview.org
#
# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

import bpy, bmesh, collections, re, typing, os
from bpy import ops
from bpy.app.translations import pgettext
from mathutils import Vector, Matrix
from math import *
from bpy.types import Collection

from .utils import *
from .keyvalues3 import *
from . import datamodel, ordered_set, flex


# -----------------------------------------------------------------------------
# Data types
# -----------------------------------------------------------------------------

class BakedVertexAnimation(list):
    def __init__(self):
        super().__init__()
        self.export_sequence = False
        self.bone_id = -1
        self.num_frames = 0


class BakeResult:
    def __init__(self, name: str):
        self.name = name
        self.object: bpy.types.Object = None
        self.matrix = Matrix()
        self.envelope = None
        self.bone_parent_matrix = None
        self.src: bpy.types.Object = None
        self.armature: "BakeResult" = None
        self.balance_vg = None
        self.shapes = collections.OrderedDict()
        self.vertex_animations = collections.defaultdict(BakedVertexAnimation)


# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------

class ExportCheck:
    def check_duplicate_bone_names(self, bone_names_dict: dict) -> bool:
        seen = {}
        duplicates = []
        for bone, name in bone_names_dict.items():
            if name in seen:
                duplicates.append(name)
            else:
                seen[name] = bone

        if not duplicates:
            return True

        dupe_report = {
            name: [b for b, n in bone_names_dict.items() if n == name]
            for name in set(duplicates)
        }
        msg = "Found duplicate bone export names:\n"
        for name, bones in dupe_report.items():
            msg += f"- '{name}' used by: {', '.join(bones)}\n"
        self.report({"ERROR"}, msg)
        return False


# -----------------------------------------------------------------------------
# LOD builder
# Produces decimated copies of a source object for each LOD level.
# -----------------------------------------------------------------------------

class LODBuilder:
    def __init__(self, reporter):
        self._reporter = reporter

    def build_all(self, ob: bpy.types.Object, export_name: str) -> list[tuple[int, bpy.types.Object]]:
        """
        Returns [(lod_index, lod_ob), ...] for each LOD level.
        Caller owns the returned objects and must remove them when done.
        """
        results = []
        for idx in range(1, ob.vs.lod_count + 1):
            ratio = max(0.0, 1.0 - (ob.vs.decimate_factor / 100.0) * idx)
            if ratio <= 0.0:
                self._reporter.warning(
                    f"LOD{idx} for '{export_name}' skipped: decimate ratio reached 0."
                )
                break

            lod = ob.copy()
            lod.data = ob.data.copy()
            lod.name = f"{export_name}_lod{idx}"
            bpy.context.scene.collection.objects.link(lod)

            mod = lod.modifiers.new(name="Decimate_LOD", type="DECIMATE")
            mod.ratio = ratio
            lod.vs.generate_lods = False
            lod.vs.use_toon_edgeline = False
            lod.vs.export_edgeline_separately = False

            results.append((idx, lod))
        return results


# -----------------------------------------------------------------------------
# Edgeline builder
# Produces a solidified, normal-flipped copy of a mesh for toon edgeline use.
# -----------------------------------------------------------------------------

class EdgelineBuilder:
    EDGELINE_MAT = "edgeline"
    TEMP_MAT = "temp_material"
    THICKNESS_VG = "Edgeline_Thickness"
    SOLIDIFY_MOD = "Toon_Edgeline"

    def __init__(self, reporter):
        self._reporter = reporter

    def build(self, ob: bpy.types.Object, export_name: str) -> typing.Optional[bpy.types.Object]:
        """
        Builds the edgeline mesh.
        - If ob.vs.export_edgeline_separately: returns a new separate object.
        - Otherwise: modifies ob in-place and returns ob.
        Returns None if nothing should be done.
        """
        if not ob.vs.use_toon_edgeline or bpy.context.scene.vs.do_not_export_edgeline:
            return None

        base_name = re.sub(r"_lod[1-9]\d*$", "", export_name)
        temp = self._make_temp_copy(ob)
        try:
            material_count = self._ensure_material(temp)
            thickness_vg = self._build_thickness_vg(ob, temp)
            self._apply_material_overrides(ob, temp, thickness_vg)
            self._apply_edgeline_materials(temp, material_count, ob.vs.edgeline_per_material)
            self._apply_solidify(temp, ob, thickness_vg, material_count)

            if not ob.vs.export_edgeline_separately:
                self._merge_into_source(ob, temp)
                return ob

            return self._make_separate_object(temp, ob, base_name)
        finally:
            self._cleanup_temp(temp)

    # ── private helpers ──────────────────────────────────────────────────────

    def _make_temp_copy(self, ob: bpy.types.Object) -> bpy.types.Object:
        temp = ob.copy()
        temp.data = ob.data.copy()
        temp.name = ob.name + "_edgeline_temp"
        bpy.context.scene.collection.objects.link(temp)

        if temp.type != "MESH":
            bpy.context.view_layer.objects.active = temp
            bpy.ops.object.convert(target="MESH")
            bpy.context.view_layer.objects.active = ob
        return temp

    def _ensure_material(self, temp: bpy.types.Object) -> int:
        if not temp.data.materials:
            mat = bpy.data.materials.get(self.TEMP_MAT) or bpy.data.materials.new(name=self.TEMP_MAT)
            temp.data.materials.append(mat)
            temp.vs.edgeline_per_material = False
        return len(temp.data.materials)

    def _build_thickness_vg(self, ob: bpy.types.Object, temp: bpy.types.Object) -> typing.Optional[bpy.types.VertexGroup]:
        if not getattr(temp, "vertex_groups", None):
            return None

        vg = None
        if temp.vs.apply_edgeline_thickness_by_weights:
            vg = temp.vertex_groups.get(self.THICKNESS_VG)
            if vg is None:
                vg = temp.vertex_groups.new(name=self.THICKNESS_VG)
                compute_edgeline_island_weights(temp, vg, 0.3, 0.8)

        needs_filter_override = any(
            slot.material and slot.material.vs.face_export_filter in ("BY_MATERIAL", "BY_VGROUP")
            for slot in temp.material_slots
        )
        if not needs_filter_override:
            return vg

        if vg is None:
            vg = temp.vertex_groups.get(self.THICKNESS_VG) or temp.vertex_groups.new(name=self.THICKNESS_VG)

        depsgraph = bpy.context.evaluated_depsgraph_get()
        temp_mesh = temp.evaluated_get(depsgraph).to_mesh()
        bm = bmesh.new()
        bm.from_mesh(temp_mesh)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        for slot_idx, slot in enumerate(temp.material_slots):
            if not slot.material:
                continue
            mode = slot.material.vs.face_export_filter
            if mode == "BY_MATERIAL":
                affected = {v.index for f in bm.faces if f.material_index == slot_idx for v in f.verts}
                for vi in affected:
                    vg.add([vi], 1.0, "REPLACE")
            elif mode == "BY_VGROUP":
                src = temp.vertex_groups.get(slot.material.vs.non_exportable_vgroup)
                if src:
                    tol = slot.material.vs.non_exportable_vgroup_tolerance
                    for v in temp_mesh.vertices:
                        for g in v.groups:
                            if g.group == src.index and g.weight >= tol:
                                vg.add([v.index], 1.0, "REPLACE")
                                break

        bm.free()
        temp.evaluated_get(depsgraph).to_mesh_clear()
        return vg

    def _apply_material_overrides(self, ob: bpy.types.Object, temp: bpy.types.Object, vg) -> None:
        pass  # handled inside _build_thickness_vg

    def _apply_edgeline_materials(self, temp: bpy.types.Object, material_count: int, per_material: bool) -> None:
        if per_material:
            for slot in list(temp.material_slots):
                name = f"{slot.material.name}_edgeline" if slot.material else self.EDGELINE_MAT
                mat = bpy.data.materials.get(name) or bpy.data.materials.new(name=name)
                mat.vs.face_export_filter = "BY_VGROUP"
                mat.vs.non_exportable_vgroup = self.THICKNESS_VG
                mat.vs.non_exportable_vgroup_tolerance = 0.95
                temp.data.materials.append(mat)
        else:
            mat = bpy.data.materials.get(self.EDGELINE_MAT) or bpy.data.materials.new(name=self.EDGELINE_MAT)
            mat.vs.face_export_filter = "BY_VGROUP"
            mat.vs.non_exportable_vgroup = self.THICKNESS_VG
            mat.vs.non_exportable_vgroup_tolerance = 0.95
            for _ in range(material_count):
                temp.data.materials.append(mat)

    def _apply_solidify(self, temp: bpy.types.Object, ob: bpy.types.Object, vg, material_count: int) -> None:
        solid = temp.modifiers.get(self.SOLIDIFY_MOD) or temp.modifiers.new(name=self.SOLIDIFY_MOD, type="SOLIDIFY")
        solid.use_rim = False
        solid.use_flip_normals = True
        solid.material_offset = material_count
        solid.offset = -1.0
        solid.thickness = -1 * round(ob.vs.base_toon_edgeline_thickness, 3)
        if vg and ob.vs.apply_edgeline_thickness_by_weights:
            solid.vertex_group = vg.name
            solid.invert_vertex_group = True

    def _merge_into_source(self, ob: bpy.types.Object, temp: bpy.types.Object) -> None:
        ob.data = temp.data
        for vg in temp.vertex_groups:
            if ob.vertex_groups.get(vg.name) is None:
                ob.vertex_groups.new(name=vg.name)
        for mod in temp.modifiers:
            if ob.modifiers.get(mod.name) is None:
                new_mod = ob.modifiers.new(name=mod.name, type=mod.type)
                for attr in [a for a in dir(mod) if not a.startswith("_") and a not in ("bl_rna", "rna_type", "type", "name")]:
                    try:
                        setattr(new_mod, attr, getattr(mod, attr))
                    except (AttributeError, TypeError):
                        pass

    def _make_separate_object(self, temp: bpy.types.Object, ob: bpy.types.Object, base_name: str) -> bpy.types.Object:
        edgeline = temp.copy()
        edgeline.data = temp.data.copy()
        edgeline.name = base_name + "_edgeline"
        bpy.context.scene.collection.objects.link(edgeline)

        for slot in edgeline.material_slots:
            if not slot.material:
                continue
            if not (slot.material.name == self.EDGELINE_MAT or slot.material.name.endswith("_edgeline")):
                local_mat = slot.material.copy()
                local_mat.vs.face_export_filter = "BY_MATERIAL"
                slot.material = local_mat

        edgeline.vs.use_toon_edgeline = False
        edgeline.vs.export_edgeline_separately = False
        edgeline.vs.generate_lods = False

        no_mat = edgeline.data.materials.find(self.TEMP_MAT)
        if no_mat != -1:
            edgeline.data.materials.pop(index=no_mat)

        return edgeline

    def _cleanup_temp(self, temp: bpy.types.Object) -> None:
        no_mat = bpy.data.materials.get(self.TEMP_MAT)
        if no_mat and no_mat.users == 0:
            bpy.data.materials.remove(no_mat)
        if temp.name in bpy.data.objects:
            bpy.context.scene.collection.objects.unlink(temp)
            bpy.data.objects.remove(temp, do_unlink=True)


# -----------------------------------------------------------------------------
# Export planning
#
# ExportPlanner takes a single export target (Collection or Object) and returns
# a flat, ordered list of ExportTask objects covering:
#   - the base export
#   - any LOD variants (one task per LOD level)
#   - any edgeline variants
#
# All temporary Blender objects are tracked and cleaned up via cleanup().
# This replaces the pending_decimation_exports / pending_edgeline_exports pattern.
# -----------------------------------------------------------------------------

class ExportTask:
    def __init__(self, source_id, export_name: str):
        self.source_id = source_id
        self.export_name = export_name

    def __repr__(self):
        return f"<ExportTask {self.export_name!r}>"


class ExportPlanner:
    def __init__(self, reporter):
        self._reporter = reporter
        self._lod_builder = LODBuilder(reporter)
        self._edgeline_builder = EdgelineBuilder(reporter)
        self._owned_objects: list[bpy.types.Object] = []
        self._owned_collections: list[bpy.types.Collection] = []

    def build_queue(self, id) -> list[ExportTask]:
        if isinstance(id, Collection):
            return self._plan_collection(id)
        elif isinstance(id, bpy.types.Object) and id.type == "ARMATURE":
            return [ExportTask(id, self._armature_export_name(id))]
        else:
            return self._plan_object(id, id.name)

    def cleanup(self) -> None:
        for col in self._owned_collections:
            if col.name in bpy.data.collections:
                bpy.data.collections.remove(col)
        for ob in self._owned_objects:
            if ob.name in bpy.data.objects:
                bpy.data.objects.remove(ob, do_unlink=True)
        self._owned_collections.clear()
        self._owned_objects.clear()

    def _is_existing_lod(self, name: str) -> bool:
        """Helper to check if a name represents a non-base LOD (1+)."""
        if "_lod" not in name:
            return False
        suffix = name.rsplit("_lod", 1)[-1]
        return suffix.isdigit() and int(suffix) > 0

    # ── collection planning ──────────────────────────────────────────────────

    def _plan_collection(self, col: Collection) -> list[ExportTask]:
        # Check if we need to merge edgelines into the base collection export
        needs_merged_edgeline = any(
            ob.vs.export and ob.vs.use_toon_edgeline and not ob.vs.export_edgeline_separately
            for ob in col.objects
        )

        target_col = col
        if needs_temp_base := needs_merged_edgeline:
            base_obs = []
            for ob in col.objects:
                if not ob.vs.export: continue
                # We must copy to avoid modifying the user's collection mesh
                copy = ob.copy()
                copy.data = ob.data.copy()
                bpy.context.scene.collection.objects.link(copy)
                self._owned_objects.append(copy)
                if copy.vs.use_toon_edgeline and not copy.vs.export_edgeline_separately:
                    self._edgeline_builder.build(copy, ob.name)
                base_obs.append(copy)
            target_col = self._make_collection(col.name + "_temp_base", base_obs)

        tasks = [ExportTask(target_col, col.name)]

        lod_buckets: dict[int, list[bpy.types.Object]] = collections.defaultdict(list)
        edgeline_obs: list[bpy.types.Object] = []

        for ob in col.objects:
            if not ob.vs.export or ob.session_uid not in State.exportableObjects:
                continue
            if not is_mesh_compatible(ob) or ob.type not in modifier_compatible:
                continue

            is_lod_member = self._is_existing_lod(ob.name)

            if not is_lod_member and ob.vs.generate_lods and ob.vs.lod_count > 0:
                for lod_idx, lod_ob in self._lod_builder.build_all(ob, ob.name):
                    self._owned_objects.append(lod_ob)
                    lod_buckets[lod_idx].append(lod_ob)

            # Separate edgeline export
            if not ob.name.endswith("_edgeline") and ob.vs.use_toon_edgeline:
                if not bpy.context.scene.vs.do_not_export_edgeline and ob.vs.export_edgeline_separately:
                    edgeline_ob = self._edgeline_builder.build(ob, ob.name)
                    if edgeline_ob and edgeline_ob is not ob:
                        self._owned_objects.append(edgeline_ob)
                        edgeline_obs.append(edgeline_ob)

        for lod_idx, lod_obs in lod_buckets.items():
            lod_col = self._make_lod_collection(col, lod_idx, lod_obs)
            tasks.append(ExportTask(lod_col, lod_col.name))

        if edgeline_obs:
            base_name = re.sub(r"_lod\d+$", "", col.name)
            edgeline_col = self._make_collection(base_name + "_edgeline", edgeline_obs)
            tasks.append(ExportTask(edgeline_col, edgeline_col.name))

        return tasks

    def _make_lod_collection(self, source_col: Collection, lod_idx: int, lod_obs: list) -> Collection:
        col_name = f"{source_col.name}_lod{lod_idx}"
        lod_col = bpy.data.collections.new(col_name)
        bpy.context.scene.collection.children.link(lod_col)
        self._owned_collections.append(lod_col)

        for lod_ob in lod_obs:
            lod_ob.vs.export = True
            lod_col.objects.link(lod_ob)
            State.exportableObjects.add(lod_ob.session_uid)

        for ob in source_col.objects:
            if ob.vs.export and not ob.vs.generate_lods:
                copy = ob.copy()
                copy.data = ob.data.copy()
                copy.vs.export = True
                copy.vs.generate_lods = False
                bpy.context.scene.collection.objects.link(copy)
                lod_col.objects.link(copy)
                State.exportableObjects.add(copy.session_uid)
                self._owned_objects.append(copy)

        return lod_col

    def _make_collection(self, name: str, obs: list[bpy.types.Object]) -> Collection:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
        self._owned_collections.append(col)
        for ob in obs:
            ob.vs.export = True
            col.objects.link(ob)
            State.exportableObjects.add(ob.session_uid)
        return col

    # ── object planning ──────────────────────────────────────────────────────

    def _plan_object(self, ob: bpy.types.Object, export_name: str) -> list[ExportTask]:
        target_ob = ob
        
        # Integrated Edgeline Logic
        if ob.vs.use_toon_edgeline and not ob.vs.export_edgeline_separately:
            if not bpy.context.scene.vs.do_not_export_edgeline and not export_name.endswith("_edgeline"):
                target_ob = ob.copy()
                target_ob.data = ob.data.copy()
                bpy.context.scene.collection.objects.link(target_ob)
                self._owned_objects.append(target_ob)
                # Build merges the hull into target_ob
                self._edgeline_builder.build(target_ob, export_name)
                State.exportableObjects.add(target_ob.session_uid)

        tasks = [ExportTask(target_ob, export_name)]

        if not is_mesh_compatible(ob) or ob.type not in modifier_compatible:
            return tasks

        is_lod = self._is_existing_lod(export_name)

        # LOD Generation (Now allows _lod0 as base)
        if not is_lod and ob.vs.generate_lods and ob.vs.lod_count > 0:
            for lod_idx, lod_ob in self._lod_builder.build_all(ob, export_name):
                self._owned_objects.append(lod_ob)
                State.exportableObjects.add(lod_ob.session_uid)
                tasks.append(ExportTask(lod_ob, lod_ob.name))

        # Separate Edgeline logic
        if not export_name.endswith("_edgeline") and ob.vs.use_toon_edgeline:
            if not bpy.context.scene.vs.do_not_export_edgeline and ob.vs.export_edgeline_separately:
                edgeline_ob = self._edgeline_builder.build(ob, export_name)
                if edgeline_ob and edgeline_ob is not ob:
                    self._owned_objects.append(edgeline_ob)
                    State.exportableObjects.add(edgeline_ob.session_uid)
                    base = re.sub(r"_lod[1-9]\d*$", "", export_name)
                    tasks.append(ExportTask(edgeline_ob, base + "_edgeline"))

        return tasks

    def _armature_export_name(self, id: bpy.types.Object) -> str:
        ad = id.animation_data
        if not ad:
            return id.name
        if id.data.vs.action_selection in ("FILTERED", "FILTERED_ACTIONS"):
            return id.name
        if ad.action and not State.useActionSlots:
            return ad.action.name
        if ad.action_slot and State.useActionSlots:
            return actionSlotExportName(ad)
        if ad.nla_tracks and not State.useActionSlots:
            return id.name
        return id.name


# -----------------------------------------------------------------------------
# Baker
#
# Bakes an Object or Collection into BakeResult(s).
# Maintains a cache so the same source is never baked twice per export.
# -----------------------------------------------------------------------------

class Baker:
    def __init__(self, exporter: "SmdExporter"):
        self._exporter = exporter
        self._cache: dict[int, BakeResult] = {}  # session_uid -> BakeResult

    def bake(self, ob: bpy.types.Object) -> typing.Optional[BakeResult]:
        uid = ob.session_uid
        if uid in self._cache:
            return self._cache[uid]

        result = BakeResult(ob.name)
        result.src = ob
        self._cache[uid] = result

        try:
            select_only(ob)
        except RuntimeError:
            self._exporter.warning(get_id("exporter_err_hidden", True).format(ob.name))
            return None

        should_tri = State.exportFormat == ExportFormat.SMD or ob.vs.triangulate

        # ── realize instances ────────────────────────────────────────────────
        duplis = None
        if ob.instance_type != "NONE":
            bpy.ops.object.duplicates_make_real()
            ob.select_set(False)
            if bpy.context.selected_objects:
                bpy.context.view_layer.objects.active = bpy.context.selected_objects[0]
                bpy.ops.object.join()
                dup_ob = bpy.context.active_object
                dup_ob.parent = ob
                dup_bake = self.bake(dup_ob)
                if dup_bake:
                    duplis = dup_bake.object
                    if should_tri:
                        self._triangulate()
            elif ob.type not in exportable_types:
                return None

        # ── copy for non-destructive baking ─────────────────────────────────
        top_parent = self._exporter.getTopParent(ob)

        if ob.type != "META":
            ob = ob.copy()
            bpy.context.scene.collection.objects.link(ob)
        if ob.data:
            ob.data = ob.data.copy()

        if bpy.context.active_object:
            ops.object.mode_set(mode="OBJECT")
        select_only(ob)

        if hasShapes(ob):
            ob.active_shape_key_index = 0

        # ── envelope / armature detection ────────────────────────────────────
        self._setup_envelope(ob, result, top_parent)

        # ── per-type pre-bake mesh ops ───────────────────────────────────────
        if ob.type == "MESH":
            self._pre_bake_mesh_ops(ob)

        # ── coordinate transform ─────────────────────────────────────────────
        ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
        ob.matrix_world = (
            Matrix.Translation(top_parent.location).inverted()
            @ getUpAxisMat(bpy.context.scene.vs.up_axis).inverted()
            @ getForwardAxisMat(bpy.context.scene.vs.forward_axis).inverted()
            @ getUpAxisOffsetMat(bpy.context.scene.vs.up_axis, bpy.context.scene.vs.up_axis_offset)
            @ Matrix.Scale(bpy.context.scene.vs.world_scale, 4)
            @ ob.matrix_world
        )

        if ob.type == "ARMATURE":
            for pb in ob.pose.bones:
                pb.matrix_basis.identity()
            result.armature = result
            result.object = ob
            return result

        if ob.type == "CURVE":
            ob.data.dimensions = "3D"

        for con in [c for c in ob.constraints if not c.mute]:
            con.mute = True

        # ── modifier scan ────────────────────────────────────────────────────
        solidify_fill_rim = None
        shapes_invalid = False
        for mod in ob.modifiers:
            if mod.type == "ARMATURE" and mod.object:
                if result.envelope and any(br for br in self._cache.values() if br.envelope != mod.object):
                    self._exporter.warning(get_id("exporter_err_dupeenv_arm", True).format(mod.name, ob.name))
                else:
                    result.armature = self.bake(mod.object)
                    result.envelope = mod
                    select_only(ob)
                mod.show_viewport = False
            elif mod.type == "SOLIDIFY" and solidify_fill_rim is None:
                solidify_fill_rim = mod.use_rim
            elif hasShapes(ob) and mod.type == "DECIMATE" and mod.decimate_type != "UNSUBDIV":
                self._exporter.error(get_id("exporter_err_shapes_decimate", True).format(ob.name, mod.decimate_type))
                shapes_invalid = True

        ops.object.mode_set(mode="OBJECT")

        # ── bake mesh ────────────────────────────────────────────────────────
        if ob.type in exportable_types:
            depsgraph = bpy.context.evaluated_depsgraph_get()
            data = bpy.data.meshes.new_from_object(
                ob.evaluated_get(depsgraph), preserve_all_data_layers=True, depsgraph=depsgraph
            )
            data.name = ob.name + "_baked"
            baked = self._put_in_object(ob, data, solidify_fill_rim)
            if should_tri:
                bpy.context.view_layer.objects.active = baked
                select_only(baked)
                self._triangulate()
        else:
            baked = None

        if duplis:
            if not ob.type in exportable_types:
                ob.select_set(False)
                bpy.context.view_layer.objects.active = duplis
            duplis.select_set(True)
            bpy.ops.object.join()
            baked = bpy.context.active_object

        if baked is None:
            return None

        result.object = baked

        if not baked.data.polygons:
            self._exporter.error(get_id("exporter_err_nopolys", True).format(result.name))
            return None

        if ob.type == "MESH":
            for remap in ob.vs.vertex_map_remaps:
                copy = baked.vs.vertex_map_remaps.add()
                copy.group = remap.group
                copy.min = remap.min
                copy.max = remap.max

        result.matrix = baked.matrix_world

        # ── shape key baking ─────────────────────────────────────────────────
        if not shapes_invalid and hasShapes(ob):
            self._bake_shapes(ob, baked, result, solidify_fill_rim)

        for mod in ob.modifiers:
            mod.show_viewport = False

        bpy.context.view_layer.objects.active = baked
        baked.select_set(True)

        self._generate_uvs_if_needed(baked, result)
        self._check_vertex_limit(baked, result)

        return result

    # ── private helpers ──────────────────────────────────────────────────────

    def _triangulate(self) -> None:
        ops.object.mode_set(mode="EDIT")
        ops.mesh.select_all(action="SELECT")
        ops.mesh.quads_convert_to_tris(quad_method="FIXED")
        ops.object.mode_set(mode="OBJECT")

    def _setup_envelope(self, ob: bpy.types.Object, result: BakeResult, top_parent) -> None:
        def capture_bone_parent(armature, bone_name):
            result.envelope = bone_name
            result.armature = self.bake(armature)
            select_only(ob)
            result.bone_parent_matrix = (
                armature.pose.bones[bone_name].matrix.inverted()
                @ armature.matrix_world.inverted()
                @ ob.matrix_world
            )

        cur = ob
        while cur:
            if cur.parent_bone and cur.parent_type == "BONE" and not result.envelope:
                capture_bone_parent(cur.parent, cur.parent_bone)
            for con in [c for c in cur.constraints if not c.mute]:
                if con.type in ("CHILD_OF", "COPY_TRANSFORMS") and con.target and con.target.type == "ARMATURE" and con.subtarget:
                    if not result.envelope:
                        capture_bone_parent(con.target, con.subtarget)
                    else:
                        self._exporter.warning(get_id("exporter_err_dupeenv_con", True).format(con.name, cur.name))
            if result.envelope:
                break
            cur = cur.parent

    def _pre_bake_mesh_ops(self, ob: bpy.types.Object) -> None:
        if not hasShapes(ob):
            normalize_object_vertexgroups(
                ob=ob,
                vgroup_limit=bpy.context.scene.vs.vertex_influence_limit,
                clean_tolerance=bpy.context.scene.vs.weightlink_threshold,
            )
            ops.object.mode_set(mode="EDIT")
            ops.mesh.reveal()
            if ob.matrix_world.is_negative:
                ops.mesh.select_all(action="SELECT")
                ops.mesh.flip_normals()
            ops.mesh.select_all(action="DESELECT")
            ops.object.mode_set(mode="OBJECT")
            return

        # Shape key normalization
        if not ob.data.vs.normalize_shapekeys:
            print("- Normalizing shape keys disabled, resetting all shapekey values to 0")
            for sk in ob.data.shape_keys.key_blocks:
                sk.value = 0
        else:
            self._normalize_shapekeys(ob)

        normalize_object_vertexgroups(
            ob=ob,
            vgroup_limit=bpy.context.scene.vs.vertex_influence_limit,
            clean_tolerance=bpy.context.scene.vs.weightlink_threshold,
        )

        ops.object.mode_set(mode="EDIT")
        ops.mesh.reveal()
        if ob.matrix_world.is_negative:
            ops.mesh.select_all(action="SELECT")
            ops.mesh.flip_normals()
        ops.mesh.select_all(action="DESELECT")
        ops.object.mode_set(mode="OBJECT")

    def _normalize_shapekeys(self, ob: bpy.types.Object) -> None:
        print("- Normalizing Basis and Keys (Reference-Based)")
        blocks = ob.data.shape_keys.key_blocks
        base_key = blocks[0]
        orig_coords = [v.co.copy() for v in base_key.data]

        for key in blocks[1:]:
            if key.slider_min == 0.0:
                continue
            for i, b_v in enumerate(base_key.data):
                b_v.co += (key.data[i].co - orig_coords[i]) * key.slider_min

        new_basis = [v.co.copy() for v in base_key.data]

        for key in blocks[1:]:
            s_min, s_max = key.slider_min, key.slider_max
            old_val = key.value
            rng = s_max - s_min
            for i, k_v in enumerate(key.data):
                delta = k_v.co - orig_coords[i]
                k_v.co = new_basis[i] + (delta * s_max - delta * s_min)
            key.slider_min = 0.0
            key.slider_max = 1.0
            key.value = (old_val - s_min) / rng if rng != 0 else 0.0

    def _put_in_object(self, source_ob: bpy.types.Object, data, solidify_fill_rim, quiet=False) -> bpy.types.Object:
        if bpy.context.view_layer.objects.active:
            ops.object.mode_set(mode="OBJECT")

        ob = bpy.data.objects.new(name=source_ob.name, object_data=data)
        ob.matrix_world = source_ob.matrix_world
        bpy.context.scene.collection.objects.link(ob)
        select_only(ob)

        exporting_smd = State.exportFormat == ExportFormat.SMD
        ops.object.transform_apply(scale=True, location=exporting_smd, rotation=exporting_smd)

        if hasCurves(source_ob):
            ops.object.mode_set(mode="EDIT")
            ops.mesh.select_all(action="SELECT")
            if source_ob.data.vs.faces == "BOTH":
                ops.mesh.duplicate()
                if solidify_fill_rim:
                    self._exporter.warning(get_id("exporter_err_solidifyinside", True).format(source_ob.name))
            if source_ob.data.vs.faces != "FORWARD":
                ops.mesh.flip_normals()
            ops.object.mode_set(mode="OBJECT")

        self._delete_faces_by_material(ob, quiet=quiet)
        return ob

    def _delete_faces_by_material(self, ob: bpy.types.Object, quiet: bool = False) -> None:
        me = ob.data
        if not me.materials:
            return

        faces_to_delete = set()
        for slot_index, mat in enumerate(me.materials):
            if not mat:
                continue
            mode = getattr(mat.vs, "face_export_filter", "NONE")
            if mode == "BY_MATERIAL":
                for poly in me.polygons:
                    if poly.material_index == slot_index:
                        faces_to_delete.add(poly.index)
            elif mode == "BY_VGROUP":
                vg_name = getattr(mat.vs, "non_exportable_vgroup", "")
                vg = ob.vertex_groups.get(vg_name) if vg_name else None
                if vg:
                    tol = mat.vs.non_exportable_vgroup_tolerance
                    for poly in me.polygons:
                        if poly.material_index != slot_index:
                            continue
                        if all(
                            any(g.group == vg.index and g.weight >= tol for g in me.vertices[v].groups)
                            for v in poly.vertices
                        ):
                            faces_to_delete.add(poly.index)

        if not faces_to_delete:
            return

        bm = bmesh.new()
        bm.from_mesh(me)
        bm.faces.ensure_lookup_table()
        geom = [f for f in bm.faces if f.index in faces_to_delete]
        if geom:
            if not quiet:
                print(f"- Deleting {len(geom)} faces")
            bmesh.ops.delete(bm, geom=geom, context="FACES")
        bm.to_mesh(me)
        bm.free()
        me.update()

    def _bake_shapes(self, source_ob: bpy.types.Object, baked: bpy.types.Object, result: BakeResult, solidify_fill_rim) -> None:
        should_tri = State.exportFormat == ExportFormat.SMD or source_ob.vs.triangulate
        normalize = source_ob.data.vs.normalize_shapekeys
        source_ob.show_only_shape_key = not normalize
        preserve_basis_normals = source_ob.data.vs.bake_shapekey_as_basis_normals

        if source_ob.vs.flex_controller_mode == "BUILDER":
            shapes_to_process = []
            for delta_name, shape_name in self._exporter.get_delta_shapekeys(source_ob):
                idx = source_ob.data.shape_keys.key_blocks.find(shape_name)
                if idx != -1:
                    shape = source_ob.data.shape_keys.key_blocks[idx]
                    if delta_name != shape.name:
                        shape.name = delta_name
                    shapes_to_process.append((idx, shape))
        else:
            shapes_to_process = list(enumerate(source_ob.data.shape_keys.key_blocks))[1:]

        if preserve_basis_normals:
            print(f"- Ignoring changed normals for shapekeys in {result.name}")

        for i, shape in shapes_to_process:
            source_ob.active_shape_key_index = i
            if normalize:
                original_value = shape.value
                shape.value = 1.0

            depsgraph = bpy.context.evaluated_depsgraph_get()
            baked_shape_data = bpy.data.meshes.new_from_object(source_ob.evaluated_get(depsgraph))
            baked_shape_data.name = f"{source_ob.name} -> {shape.name}"

            shape_ob = self._put_in_object(source_ob, baked_shape_data, solidify_fill_rim, quiet=True)

            if preserve_basis_normals:
                prev_idx = source_ob.active_shape_key_index
                source_ob.active_shape_key_index = 0
                mod = shape_ob.modifiers.new(name="PreserveBasisNormals", type="DATA_TRANSFER")
                mod.object = baked
                mod.use_loop_data = True
                mod.data_types_loops = {"CUSTOM_NORMAL"}
                mod.loop_mapping = "TOPOLOGY"
                apply_modifier(mod=mod, silent=True)
                source_ob.active_shape_key_index = prev_idx

            result.shapes[shape.name] = shape_ob.data

            if normalize:
                shape.value = original_value

            if should_tri:
                bpy.context.view_layer.objects.active = shape_ob
                self._triangulate()

            bpy.context.scene.collection.objects.unlink(shape_ob)
            bpy.data.objects.remove(shape_ob)

    def _generate_uvs_if_needed(self, ob: bpy.types.Object, result: BakeResult) -> None:
        if ob.data.uv_layers:
            return
        ops.object.mode_set(mode="EDIT")
        ops.mesh.select_all(action="SELECT")
        if len(result.object.data.vertices) < 2000:
            result.object.data.uv_layers.new()
            ops.uv.smart_project()
        else:
            ops.uv.unwrap()
        ops.object.mode_set(mode="OBJECT")

    def _check_vertex_limit(self, ob: bpy.types.Object, result: BakeResult) -> None:
        if State.compiler > Compiler.STUDIOMDL or State.datamodelFormat >= 22:
            return
        depsgraph = bpy.context.evaluated_depsgraph_get()
        eval_ob = ob.evaluated_get(depsgraph)
        try:
            mesh = eval_ob.to_mesh()
            count = len(mesh.vertices)
            print(f"- Vertices count for {result.name}: {count}")
            if count > 16384:
                self._exporter.warning(f"Vertices count for {result.name} is over 16384!")
        finally:
            eval_ob.to_mesh_clear()


# -----------------------------------------------------------------------------
# Main exporter operator
# -----------------------------------------------------------------------------

class SmdExporter(bpy.types.Operator, Logger, ExportCheck):
    bl_idname = "export_scene.smd"
    bl_label = get_id("exporter_title")
    bl_description = get_id("exporter_tip")

    collection: bpy.props.StringProperty(name=get_id("exporter_prop_group"), description=get_id("exporter_prop_group_tip"))
    export_scene: bpy.props.BoolProperty(name=get_id("scene_export"), description=get_id("exporter_prop_scene_tip"), default=False)

    def __init__(self, *args, **kwargs):
        bpy.types.Operator.__init__(self, *args, **kwargs)
        Logger.__init__(self)
        
    @classmethod
    def poll(cls, context):
        return len(context.scene.vs.export_list) != 0

    def invoke(self, context, event) -> set:
        State.update_scene()
        ops.wm.call_menu(name="SMD_MT_ExportChoice")
        return {"PASS_THROUGH"}

    def execute(self, context) -> set:
        if State.datamodelEncoding != 0 and context.scene.vs.export_format == "DMX":
            datamodel.check_support("binary", State.datamodelEncoding)
            if State.datamodelEncoding < 3 and State.datamodelFormat > 11 and not context.scene.vs.use_kv2:
                self.report({"ERROR"}, "DMX format \"Model {}\" requires DMX encoding \"Binary 3\" or later".format(State.datamodelFormat))
                return {"CANCELLED"}
        if not context.scene.vs.export_path:
            bpy.ops.wm.call_menu(name="SMD_MT_ConfigureScene")
            return {"CANCELLED"}
        if context.scene.vs.export_path.startswith("//") and not context.blend_data.filepath:
            self.report({"ERROR"}, get_id("exporter_err_relativeunsaved"))
            return {"CANCELLED"}
        if State.datamodelEncoding == 0 and context.scene.vs.export_format == "DMX":
            self.report({"ERROR"}, get_id("exporter_err_dmxother"))
            return {"CANCELLED"}

        prev_mode = prev_hidden = None
        if context.active_object:
            if context.active_object.hide_viewport:
                prev_hidden = context.active_object.name
                context.active_object.hide_viewport = False
            prev_mode = context.mode
            if prev_mode.find("EDIT") != -1:
                prev_mode = "EDIT"
            elif prev_mode.find("PAINT") != -1:
                prev_mode = "_".join(reversed(prev_mode.split("_")))
            ops.object.mode_set(mode="OBJECT")

        State.update_scene()
        self.materials_used = set()

        for ob in [ob for ob in bpy.context.scene.objects if ob.type == "ARMATURE" and len(ob.vs.subdir) == 0]:
            ob.vs.subdir = "anims"

        ops.ed.undo_push(message=self.bl_label)

        try:
            context.tool_settings.use_keyframe_insert_auto = False
            context.tool_settings.use_keyframe_insert_keyingset = False
            context.preferences.edit.use_enter_edit_mode = False
            State.unhook_events()
            if context.scene.rigidbody_world:
                context.scene.frame_set(context.scene.rigidbody_world.point_cache.frame_start)

            for view_layer in bpy.context.scene.view_layers:
                unhide_all(view_layer.layer_collection)

            self.files_exported = self.attemptedExports = 0

            export_ids = self._collect_export_ids(context)
            for id in export_ids:
                self._export_one(context, id)

            self.errorReport(
                get_id("exporter_report", True).format(self.files_exported, self.elapsed_time())
            )
        finally:
            ops.ed.undo_push(message=self.bl_label)
            if bpy.app.debug_value <= 1:
                ops.ed.undo()
            if prev_mode:
                ops.object.mode_set(mode=prev_mode)
            if prev_hidden:
                context.scene.objects[prev_hidden].hide_viewport = True
            context.scene.update_tag()
            context.window_manager.progress_end()
            State.hook_events()

        self.collection = ""
        self.export_scene = False
        return {"FINISHED"}

    def _collect_export_ids(self, context) -> list:
        ids = []
        if self.export_scene:
            for exportable in context.scene.vs.export_list:
                id = exportable.item
                if isinstance(id, Collection):
                    if shouldExportGroup(id):
                        ids.append(id)
                elif id.vs.export:
                    ids.append(id)
        elif self.collection:
            col = bpy.data.collections[self.collection]
            if col.vs.mute:
                self.error(get_id("exporter_err_groupmuted", True).format(col.name))
            elif not col.objects:
                self.error(get_id("exporter_err_groupempty", True).format(col.name))
            else:
                ids.append(col)
        else:
            for exportable in getSelectedExportables():
                if not isinstance(exportable.item, Collection):
                    ids.append(exportable.item)
        return ids

    def _export_one(self, context, id) -> None:
        self.attemptedExports += 1
        self._last_bake_results = []
        bench = BenchMarker()
        subdir = id.vs.subdir.lstrip("/")
        print(f"\nBlender Source Tools: exporting {id.name}")

        path = os.path.join(bpy.path.abspath(context.scene.vs.export_path), subdir)
        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except Exception as err:
                self.error(get_id("exporter_err_makedirs", True).format(err))
                return

        if isinstance(id, Collection) and not any(ob.vs.export for ob in id.objects):
            self.error(get_id("exporter_err_nogroupitems", True).format(id.name))
            return

        if isinstance(id, bpy.types.Object) and id.type == "ARMATURE":
            ad = id.animation_data
            if not ad:
                return

        planner = ExportPlanner(self)
        try:
            tasks = planner.build_queue(id)
            bench.report("planning")

            for task in tasks:
                self._execute_task(context, id, task, path, bench)
        finally:
            planner.cleanup()

        self._warn_unicode(id)

    def _execute_task(self, context, original_id, task: ExportTask, path: str, bench: BenchMarker) -> None:
        source = task.source_id

        if isinstance(source, Collection) and not any(ob.vs.export for ob in source.objects):
            return

        # ── hide unwanted metaballs ──────────────────────────────────────────
        for meta in [ob for ob in context.scene.objects if ob.type == "META" and (
            not ob.vs.export or (isinstance(source, Collection) and ob.name not in source.objects)
        )]:
            for element in meta.data.elements:
                element.hide = True

        # ── bake ─────────────────────────────────────────────────────────────
        baker = Baker(self)
        bake_results = []

        if isinstance(source, Collection):
            group_vmaps = valvesource_vertex_maps(source)
            baked_metaballs = []

            for ob in [ob for ob in source.objects if ob.vs.export and ob.session_uid in State.exportableObjects]:
                if ob.type == "META":
                    ob = self._find_basis_metaball(ob)
                    if ob in baked_metaballs:
                        continue
                    baked_metaballs.append(ob)

                bake = baker.bake(ob)
                if bake:
                    for vmap_name in group_vmaps:
                        if vmap_name not in bake.object.data.vertex_colors:
                            vc = bake.object.data.vertex_colors.new(name=vmap_name)
                            vc.data.foreach_set("color", [1.0] * 4)
                    bake_results.append(bake)
        else:
            if source.type == "META":
                bake = baker.bake(self._find_basis_metaball(source))
            else:
                bake = baker.bake(source)
            if bake:
                bake_results.append(bake)

        bench.report("bake", len(bake_results))

        if not any(bake_results):
            return

        # ── vertex animations ────────────────────────────────────────────────
        self._process_vertex_animations(source, bake_results, bench)

        # ── DMX automerge ────────────────────────────────────────────────────
        if isinstance(source, Collection) and State.exportFormat == ExportFormat.DMX and source.vs.automerge:
            bake_results = self._dmx_automerge(source, bake_results, bench)

        # ── skeleton setup ───────────────────────────────────────────────────
        self.armature = self.armature_src = None
        self.bone_ids = {}
        self.exportable_bones = []
        self.exportable_boneNames = {}
        self.exportable_empties = None

        for result in bake_results:
            if result.armature:
                if not self.armature:
                    self.armature = result.armature.object
                    self.armature_src = result.armature.src
                elif self.armature != result.armature.object:
                    self.warning(get_id("exporter_warn_multiarmature"))

        if self.armature_src:
            self._setup_skeleton(source, bake_results, baker)

        self.bake_results = list(baker._cache.values())
        self._last_bake_results.extend(bake_results)

        # ── flex controller setup ─────────────────────────────────────────────
        if State.exportFormat == ExportFormat.DMX and hasShapes(source):
            self.flex_controller_mode = source.vs.flex_controller_mode
            self.flex_controller_source = source.vs.flex_controller_source

        bpy.context.view_layer.objects.active = bake_results[0].object
        bpy.ops.object.mode_set(mode="OBJECT")

        # ── VCA automerge check ───────────────────────────────────────────────
        skip_vca = False
        if isinstance(source, Collection) and len(source.vs.vertex_animations) and len(source.objects) > 1:
            mesh_bakes = [b for b in bake_results if b.object.type == "MESH"]
            if len(mesh_bakes) > len([b for b in bake_results if (type(b.envelope) is str and b.envelope == bake_results[0].envelope) or b.envelope is None]):
                self.error(get_id("exporter_err_unmergable", True).format(source.name))
                skip_vca = True
            elif not source.vs.automerge:
                source.vs.automerge = True

        # ── write ─────────────────────────────────────────────────────────────
        write_func = self.writeDMX if State.exportFormat == ExportFormat.DMX else self.writeSMD
        bench.report("Post Bake")

        if isinstance(source, bpy.types.Object) and source.type == "ARMATURE" and source.data.vs.action_selection != "CURRENT":
            baked_armature = bake_results[0].object
            if State.useActionSlots and source.data.vs.action_selection == "FILTERED":
                for slot in actionSlotsForFilter(baked_armature):
                    baked_armature.animation_data.action_slot = slot
                    self.files_exported += write_func(source, bake_results, self.sanitiseFilename(slot.name_display), path)
            else:
                for action in actionsForFilter(baked_armature.vs.action_filter):
                    baked_armature.animation_data.action = action
                    self.files_exported += write_func(source, bake_results, self.sanitiseFilename(action.name), path)
        else:
            self.files_exported += write_func(source, bake_results, self.sanitiseFilename(task.export_name), path)

        bench.report(write_func.__name__)

        if State.compiler > Compiler.STUDIOMDL or State.datamodelFormat >= 22:
            if re.match(r"[^a-z0-9_]", source.name):
                self.warning(get_id("exporter_warn_source2names", format_string=True).format(source.name))

    def _setup_skeleton(self, source, bake_results: list[BakeResult], baker: Baker) -> None:
        if list(self.armature_src.scale).count(self.armature_src.scale[0]) != 3:
            self.warning(get_id("exporter_err_arm_nonuniform", True).format(self.armature_src.name))

        if not self.armature:
            self.armature = baker.bake(self.armature_src).object

        exporting_armature = isinstance(source, bpy.types.Object) and source.type == "ARMATURE"
        self.exportable_bones = [
            self.armature.pose.bones[b.name]
            for b in self.armature.data.bones
            if exporting_armature or b.use_deform
        ]
        self.exportable_boneNames = {
            b.name: get_bone_exportname(b)
            for b in self.armature.data.bones
            if exporting_armature or b.use_deform
        }

        if not self.check_duplicate_bone_names(self.exportable_boneNames):
            return

        skipped = len(self.armature.pose.bones) - len(self.exportable_bones)
        if skipped:
            print(f"- Skipping {skipped} non-deforming bones")

        original_pose = self.armature_src.data.pose_position
        self.armature_src.data.pose_position = "REST"
        bpy.context.view_layer.update()

        self.exportable_empties = [
            (e, e.matrix_world.copy())
            for e in bpy.data.objects
            if e.type == "EMPTY"
            and e.parent == self.armature_src
            and e.parent_type == "BONE"
            and e.parent_bone in [pb.name for pb in self.armature.pose.bones]
            and isinstance(getattr(e.vs, "dmx_attachment", None), bool)
            and e.vs.dmx_attachment
        ]

        self.armature_src.data.pose_position = original_pose
        bpy.context.view_layer.update()

    def _process_vertex_animations(self, source, bake_results: list[BakeResult], bench: BenchMarker) -> None:
        if not (isinstance(source, Collection) and len(getattr(source.vs, "vertex_animations", []))):
            return

        mesh_bakes = [b for b in bake_results if b.object.type == "MESH"]

        for va in source.vs.vertex_animations:
            if State.exportFormat == ExportFormat.DMX:
                va.name = va.name.replace("_", "-")

            vca = bake_results[0].vertex_animations[va.name]
            vca.export_sequence = va.export_sequence
            vca.num_frames = va.end - va.start
            two_percent = vca.num_frames * len(bake_results) / 50
            print(f"- Generating vertex animation \"{va.name}\"")
            anim_bench = BenchMarker(1, va.name)

            for f in range(va.start, va.end):
                bpy.context.scene.frame_set(f)
                bpy.ops.object.select_all(action="DESELECT")
                depsgraph = bpy.context.evaluated_depsgraph_get()

                for bake in mesh_bakes:
                    bake.fob = bpy.data.objects.new(
                        f"{va.name}-{f}",
                        bpy.data.meshes.new_from_object(bake.src.evaluated_get(depsgraph))
                    )
                    bake.fob.matrix_world = bake.src.matrix_world
                    bpy.context.scene.collection.objects.link(bake.fob)
                    bpy.context.view_layer.objects.active = bake.fob
                    bake.fob.select_set(True)

                    tp = self.getTopParent(bake.src)
                    if tp:
                        bake.fob.location -= tp.location

                    if bpy.context.scene.rigidbody_world:
                        prev_rbw = bpy.context.scene.rigidbody_world.enabled
                        bpy.context.scene.rigidbody_world.enabled = False

                    bpy.ops.object.transform_apply(location=True, scale=True, rotation=True)

                    if bpy.context.scene.rigidbody_world:
                        bpy.context.scene.rigidbody_world.enabled = prev_rbw

                if bpy.context.selected_objects and State.exportFormat == ExportFormat.SMD:
                    bpy.context.view_layer.objects.active = bpy.context.selected_objects[0]
                    ops.object.join()

                vca.append(
                    bpy.context.active_object
                    if len(bpy.context.selected_objects) == 1
                    else bpy.context.selected_objects
                )
                anim_bench.report("bake")

                if len(bpy.context.selected_objects) != 1:
                    for bake in mesh_bakes:
                        bpy.context.scene.collection.objects.unlink(bake.fob)
                        del bake.fob

                anim_bench.report("record")

                if two_percent and len(vca) / len(bake_results) % two_percent == 0:
                    print(".", debug_only=True, newline=False)
                    bpy.context.window_manager.progress_update(len(vca) / vca.num_frames)

            bench.report("\n" + va.name)
            bpy.context.view_layer.objects.active = bake_results[0].src

    def _dmx_automerge(self, source: Collection, bake_results: list[BakeResult], bench: BenchMarker) -> list[BakeResult]:
        bone_parents = collections.defaultdict(list)
        scene_obs = bpy.context.scene.collection.objects
        view_obs = bpy.context.view_layer.objects

        for bake in [b for b in bake_results if type(b.envelope) is str or b.envelope is None]:
            bone_parents[bake.envelope].append(bake)

        for bp, parts in bone_parents.items():
            if len(parts) <= 1:
                continue

            shape_names = {key for part in parts for key in part.shapes.keys()}

            ops.object.select_all(action="DESELECT")
            for part in parts:
                ob = part.object.copy()
                ob.data = ob.data.copy()
                ob.data.uv_layers.active.name = "__dmx_uv__"
                scene_obs.link(ob)
                ob.select_set(True)
                view_obs.active = ob
                bake_results.remove(part)

            bpy.ops.object.join()
            joined = BakeResult(bp + "_meshes" if bp else "loose_meshes")
            joined.object = bpy.context.active_object
            joined.object.name = joined.object.data.name = joined.name
            joined.envelope = bp

            if parts[0].vertex_animations:
                for src_name, src_vca in parts[0].vertex_animations.items():
                    vca = joined.vertex_animations[src_name] = BakedVertexAnimation()
                    vca.bone_id = src_vca.bone_id
                    vca.export_sequence = src_vca.export_sequence
                    vca.num_frames = src_vca.num_frames

                    for i, frame in enumerate(src_vca):
                        ops.object.select_all(action="DESELECT")
                        frame.reverse()
                        for ob in frame:
                            scene_obs.link(ob)
                            ob.select_set(True)
                        bpy.context.view_layer.objects.active = frame[0]
                        bpy.ops.object.join()
                        bpy.context.active_object.name = f"{src_name}-{i}"
                        bpy.ops.object.transform_apply(location=True, scale=True, rotation=True)
                        vca.append(bpy.context.active_object)
                        scene_obs.unlink(bpy.context.active_object)

            bake_results.append(joined)

            for shape_name in shape_names:
                ops.object.select_all(action="DESELECT")
                for part in parts:
                    mesh = part.shapes.get(shape_name, part.object.data)
                    ob = bpy.data.objects.new(name=f"{part.name} -> {shape_name}", object_data=mesh.copy())
                    scene_obs.link(ob)
                    ob.matrix_local = part.matrix
                    ob.select_set(True)
                    view_obs.active = ob

                bpy.ops.object.join()
                joined.shapes[shape_name] = bpy.context.active_object.data
                joined.shapes[shape_name].name = f"{joined.object.name} -> {shape_name}"
                scene_obs.unlink(bpy.context.active_object)
                bpy.data.objects.remove(bpy.context.active_object)

            view_obs.active = joined.object

        bench.report("Mesh merge")
        return bake_results

    # ── utilities ────────────────────────────────────────────────────────────

    def _find_basis_metaball(self, id: bpy.types.Object) -> bpy.types.Object:
        basis_ns = id.name.rsplit(".")
        if len(basis_ns) == 1:
            return id
        basis = id
        for meta in [ob for ob in bpy.data.objects if ob.type == "META"]:
            ns = meta.name.rsplit(".")
            if ns[0] != basis_ns[0]:
                continue
            if len(ns) == 1:
                return meta
            try:
                if int(ns[1]) < int(basis_ns[1]):
                    basis = meta
                    basis_ns = ns
            except ValueError:
                pass
        return basis

    def _warn_unicode(self, id) -> None:
        unicode_tested = set()

        def check(name, obj, display_type):
            if obj in unicode_tested:
                return
            unicode_tested.add(obj)
            try:
                name.encode("ascii")
            except UnicodeEncodeError:
                self.warning(get_id("exporter_warn_unicode", format_string=True).format(pgettext(display_type), name))

        for bake in getattr(self, "_last_bake_results", []):
            check(bake.name, bake, type(bake.src).__name__)
            for shape_name, shape_id in bake.shapes.items():
                check(shape_name, shape_id, "Shape Key")
        for mat in self.materials_used:
            check(mat[0], mat[1], type(mat[1]).__name__)

    def sanitiseFilename(self, name: str) -> str:
        new_name = name
        for ch in r'/?<>\:*|"':
            new_name = new_name.replace(ch, "_")
        if new_name != name:
            self.warning(get_id("exporter_warn_sanitised_filename", True).format(name, new_name))
        return new_name

    def getWeightmap(self, bake_result: BakeResult) -> list:
        out = []
        amod = bake_result.envelope
        ob = bake_result.object
        if not amod or not isinstance(amod, bpy.types.ArmatureModifier):
            return out

        amod_vg = ob.vertex_groups.get(amod.vertex_group)

        try:
            amod_ob = next(bake.object for bake in self.bake_results if bake.src == amod.object)
        except StopIteration as e:
            raise ValueError(f"Armature for exportable \"{bake_result.name}\" was not baked") from e

        model_mat = amod_ob.matrix_world.inverted() @ ob.matrix_world
        num_verts = len(ob.data.vertices)

        for v in ob.data.vertices:
            weights = []
            total_weight = 0
            if len(out) % 50 == 0:
                bpy.context.window_manager.progress_update(len(out) / num_verts)

            if amod.use_vertex_groups:
                for v_group in v.groups:
                    if v_group.group >= len(ob.vertex_groups):
                        continue
                    ob_group = ob.vertex_groups[v_group.group]
                    bone = amod_ob.pose.bones.get(ob_group.name)
                    if bone and bone in self.exportable_bones:
                        weights.append([self.bone_ids[bone.name], v_group.weight])
                        total_weight += v_group.weight

            if amod.use_bone_envelopes and total_weight == 0:
                for pb in [pb for pb in amod_ob.pose.bones if pb in self.exportable_bones]:
                    weight = pb.bone.envelope_weight * pb.evaluate_envelope(model_mat @ v.co)
                    if weight:
                        weights.append([self.bone_ids[pb.name], weight])
                        total_weight += weight

            if total_weight not in (0, 1):
                for link in weights:
                    link[1] *= 1 / total_weight

            if amod_vg and total_weight > 0:
                amod_vg_weight = 0
                for v_group in v.groups:
                    if v_group.group == amod_vg.index:
                        amod_vg_weight = v_group.weight
                        break
                if amod.invert_vertex_group:
                    amod_vg_weight = 1 - amod_vg_weight
                for link in weights:
                    link[1] *= amod_vg_weight

            out.append(weights)
        return out

    def GetMaterialName(self, ob: bpy.types.Object, material_index: int) -> tuple[str, bool]:
        mat_name = mat_id = None
        if len(ob.material_slots) > material_index:
            mat_id = ob.material_slots[material_index].material
            if mat_id:
                mat_name = sanitize_string(mat_id.name, allow_unicode=True)
        if mat_name:
            self.materials_used.add((mat_name, mat_id))
            return mat_name, True
        return "no_material", ob.display_type != "TEXTURED"

    def getTopParent(self, id: bpy.types.Object) -> bpy.types.Object:
        top = id
        while top.parent:
            top = top.parent
        return top

    def getEvaluatedPoseBones(self) -> list:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated = self.armature.evaluated_get(depsgraph)
        assert isinstance(evaluated, bpy.types.Object) and evaluated.pose
        return [evaluated.pose.bones[b.name] for b in self.exportable_bones]

    def get_delta_shapekeys(self, ob: bpy.types.Object) -> list[tuple[str, str]]:
        if not hasattr(ob, "vs") or not hasattr(ob.vs, "dme_flexcontrollers"):
            return []
        valid_keys = set(ob.data.shape_keys.key_blocks.keys()[1:]) if ob.data.shape_keys else set()
        seen = set()
        result = []
        for fc in ob.vs.dme_flexcontrollers:
            if fc.shapekey not in valid_keys:
                continue
            raw = fc.raw_delta_name.strip() if fc.raw_delta_name and fc.raw_delta_name.strip() else fc.shapekey
            delta = sanitize_string_for_delta(raw)
            if delta not in seen:
                seen.add(delta)
                result.append((delta, fc.shapekey))
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # SMD writing — logic unchanged from original
    # ─────────────────────────────────────────────────────────────────────────

    def openSMD(self, path, name, description):
        full_path = os.path.realpath(os.path.join(path, name))
        try:
            f = open(full_path, "w", encoding="utf-8")
        except Exception as err:
            self.error(get_id("exporter_err_open", True).format(description, err))
            return None
        f.write("version 1\n")
        print("-", full_path)
        return f

    def writeSMD(self, id, bake_results, name, filepath, filetype="smd"):
        bench = BenchMarker(1, "SMD")
        goldsrc = bpy.context.scene.vs.smd_format == "GOLDSOURCE"

        self.smd_file = self.openSMD(filepath, sanitize_string(name, allow_unicode=True) + "." + filetype, filetype.upper())
        if self.smd_file is None:
            return 0

        if State.compiler > Compiler.STUDIOMDL:
            self.warning(get_id("exporter_warn_source2smdsupport"))

        self.smd_file.write("nodes\n")
        curID = 0
        if not self.armature:
            self.smd_file.write("0 \"root\" -1\n")
            if filetype == "smd":
                print("- No skeleton to export")
        else:
            if self.armature.data.vs.implicit_zero_bone:
                self.smd_file.write(f"0 \"{implicit_bone_name}\" -1\n")
                curID += 1

            for bone in self.exportable_bones:
                parent = bone.parent
                while parent and parent not in self.exportable_bones:
                    parent = parent.parent

                self.bone_ids[bone.name] = curID
                bone_name = self.exportable_boneNames[bone.name]
                parent_id = str(self.bone_ids[parent.name]) if parent else "-1"
                self.smd_file.write(f"{curID} \"{bone_name}\" {parent_id}\n")
                curID += 1

            num_bones = len(self.armature.data.bones)
            if filetype == "smd":
                print(f"- Exported {num_bones} bones")
            if num_bones > 128:
                self.warning(get_id("exporter_err_bonelimit", True).format(num_bones, 128))

        for vca in [v for v in bake_results[0].vertex_animations.items() if v[1].export_sequence]:
            curID += 1
            vca[1].bone_id = curID
            self.smd_file.write(f"{curID} \"vcabone_{vca[0]}\" -1\n")

        self.smd_file.write("end\n")

        if filetype == "smd":
            self.smd_file.write("skeleton\n")
            if not self.armature:
                self.smd_file.write("time 0\n0 0 0 0 0 0 0\nend\n")
            else:
                is_anim = len(bake_results) == 1 and bake_results[0].object.type == "ARMATURE"
                anim_len = animationLength(self.armature.animation_data) + 1 if is_anim else 1

                if not is_anim:
                    for pb in self.armature.pose.bones:
                        pb.matrix_basis.identity()
                elif self.armature.data.vs.reset_pose_per_anim:
                    for pb in self.armature.pose.bones:
                        pb.matrix_basis.identity()

                for i in range(anim_len):
                    bpy.context.window_manager.progress_update(i / anim_len)
                    self.smd_file.write(f"time {i}\n")
                    if self.armature.data.vs.implicit_zero_bone:
                        self.smd_file.write("0  0 0 0  0 0 0\n")
                    if is_anim:
                        bpy.context.scene.frame_set(i)

                    evaluated = self.getEvaluatedPoseBones()
                    for pb in evaluated:
                        parent = pb.parent
                        while parent and parent not in evaluated:
                            parent = parent.parent

                        mat = get_bone_matrix(pb, rest_space=not is_anim)
                        if self.armature.data.vs.legacy_rotation:
                            mat @= mat_BlenderToSMD
                        if parent:
                            pmat = get_bone_matrix(parent, rest_space=not is_anim)
                            if self.armature.data.vs.legacy_rotation:
                                pmat @= mat_BlenderToSMD
                            mat = pmat.inverted() @ mat
                        else:
                            mat = self.armature.matrix_world @ mat

                        self.smd_file.write(f"{self.bone_ids[pb.name]}  {getSmdVec(mat.to_translation())}  {getSmdVec(mat.to_euler())}\n")

                self.smd_file.write("end\n")
                ops.object.mode_set(mode="OBJECT")
                print(f"- Exported {anim_len} frames{' (legacy rotation)' if self.armature.data.vs.legacy_rotation else ''}")

            done_header = False
            for bake in [b for b in bake_results if b.object.type != "ARMATURE"]:
                if not done_header:
                    self.smd_file.write("triangles\n")
                    done_header = True

                ob = bake.object
                uv_loop = ob.data.uv_layers.active.data
                weights = self.getWeightmap(bake)

                ob_weight_str = None
                if type(bake.envelope) == str and bake.envelope in self.bone_ids:
                    ob_weight_str = (" 1 {} 1" if not goldsrc else "{}").format(self.bone_ids[bake.envelope])
                elif not weights:
                    ob_weight_str = " 0" if not goldsrc else "0"

                bad_face_mats = 0
                multi_weight_verts = set()

                for p, poly in enumerate(ob.data.polygons):
                    if p % 10 == 0:
                        bpy.context.window_manager.progress_update(p / len(ob.data.polygons))
                    mat_name, mat_ok = self.GetMaterialName(ob, poly.material_index)
                    if not mat_ok:
                        bad_face_mats += 1
                    self.smd_file.write(mat_name + "\n")

                    for loop in [ob.data.loops[l] for l in poly.loop_indices]:
                        v = ob.data.vertices[loop.vertex_index]
                        pos_norm = f"  {getSmdVec(v.co)}  {getSmdVec(loop.normal)}  "
                        uv = " ".join(getSmdFloat(j) for j in uv_loop[loop.index].uv)

                        if not goldsrc:
                            if ob_weight_str:
                                ws = ob_weight_str
                            else:
                                valid = [(link[0], link[1]) for link in weights[v.index] if link[1] > 0]
                                ws = " {}{}".format(len(valid), "".join(f" {bi} {getSmdFloat(bw)}" for bi, bw in valid))
                            self.smd_file.write("0" + pos_norm + uv + ws + "\n")
                        else:
                            if ob_weight_str:
                                ws = ob_weight_str
                            else:
                                gw = [link for link in weights[v.index] if link[1] > 0]
                                if not gw:
                                    ws = "0"
                                else:
                                    if len(gw) > 1:
                                        multi_weight_verts.add(v)
                                    ws = str(gw[0][0])
                            self.smd_file.write(ws + pos_norm + uv + "\n")

                if goldsrc and multi_weight_verts:
                    self.warning(get_id("exporterr_goldsrc_multiweights", format_string=True).format(len(multi_weight_verts), bake.src.data.name))
                if bad_face_mats:
                    self.warning(get_id("exporter_err_facesnotex_ormat").format(bad_face_mats, bake.src.data.name))
                print(f"- Exported {len(ob.data.polygons)} polys")
                print(f"- Exported {len(self.materials_used)} materials")
                for mat in self.materials_used:
                    print("   " + mat[0])

            if done_header:
                self.smd_file.write("end\n")

        elif filetype == "vta":
            self.smd_file.write("skeleton\n")

            def write_time(time, shape_name=None):
                self.smd_file.write("time {}{}\n".format(time, f" # {shape_name}" if shape_name else ""))

            shape_names = ordered_set.OrderedSet()
            for bake in [b for b in bake_results if b.object.type != "ARMATURE"]:
                for sn in bake.shapes.keys():
                    shape_names.add(sn)

            write_time(0)
            for i, sn in enumerate(shape_names):
                write_time(i + 1, sn)
            self.smd_file.write("end\n\nvertexanimation\n")

            vert_id = 0
            write_time(0)
            for bake in [b for b in bake_results if b.object.type != "ARMATURE"]:
                bake.offset = vert_id
                verts = bake.object.data.vertices
                for loop in [bake.object.data.loops[l] for poly in bake.object.data.polygons for l in poly.loop_indices]:
                    self.smd_file.write(f"{vert_id} {getSmdVec(verts[loop.vertex_index].co)} {getSmdVec(loop.normal)}\n")
                    vert_id += 1

            total_verts = 0
            for i, shape_name in enumerate(shape_names):
                i += 1
                bpy.context.window_manager.progress_update(i / len(shape_names))
                write_time(i, shape_name)
                for bake in [b for b in bake_results if b.object.type != "ARMATURE"]:
                    shape = bake.shapes.get(shape_name)
                    if not shape:
                        continue
                    vi = bake.offset
                    for ml in [bake.object.data.loops[l] for poly in bake.object.data.polygons for l in poly.loop_indices]:
                        sv = shape.vertices[ml.vertex_index]
                        sl = shape.loops[ml.index]
                        mv = bake.object.data.vertices[ml.vertex_index]
                        if sv.co - mv.co > epsilon or sl.normal - ml.normal > epsilon:
                            self.smd_file.write(f"{vi} {getSmdVec(sv.co)} {getSmdVec(sl.normal)}\n")
                            total_verts += 1
                        vi += 1

            self.smd_file.write("end\n")
            print(f"- Exported {i} flex shapes ({total_verts} verts)")

        self.smd_file.close()
        if bench.quiet:
            print(f"- {filetype.upper()} export took", bench.total(), "\n")

        written = 1
        if filetype == "smd":
            for bake in [b for b in bake_results if b.shapes]:
                written += self.writeSMD(id, bake_results, name, filepath, filetype="vta")
            for vca_name, vca in bake_results[0].vertex_animations.items():
                written += self.writeVCA(vca_name, vca, filepath)
                if vca.export_sequence:
                    written += self.writeVCASequence(vca_name, vca, filepath)
        return written

    def writeVCA(self, name, vca, filepath):
        bench = BenchMarker()
        self.smd_file = self.openSMD(filepath, name + ".vta", "vertex animation")
        if self.smd_file is None:
            return 0

        self.smd_file.write("nodes\n0 \"root\" -1\nend\nskeleton\n")
        for i in range(len(vca)):
            self.smd_file.write(f"time {i}\n0 0 0 0 0 0 0\n")
        self.smd_file.write("end\nvertexanimation\n")

        num_frames = len(vca)
        two_percent = num_frames / 50

        for frame, vca_ob in enumerate(vca):
            self.smd_file.write(f"time {frame}\n")
            self.smd_file.writelines(
                f"{loop.index} {getSmdVec(vca_ob.data.vertices[loop.vertex_index].co)} {getSmdVec(loop.normal)}\n"
                for loop in vca_ob.data.loops
            )
            if two_percent and frame % two_percent == 0:
                print(".", debug_only=True, newline=False)
                bpy.context.window_manager.progress_update(frame / num_frames)
            removeObject(vca_ob)
            vca[frame] = None

        self.smd_file.write("end\n")
        print(debug_only=True)
        print(f"Exported {num_frames} frames ({self.smd_file.tell() / 1024 / 1024:.1f}MB)")
        self.smd_file.close()
        bench.report("Vertex animation")
        return 1

    def writeVCASequence(self, name, vca, dir_path):
        self.smd_file = self.openSMD(dir_path, f"vcaanim_{name}.smd", "SMD")
        if self.smd_file is None:
            return 0

        root_bones = (
            "\n".join(f'{self.bone_ids[b.name]} "{b.name}" -1' for b in self.exportable_bones if b.parent is None)
            if self.armature_src else '0 "root" -1'
        )
        self.smd_file.write(f"nodes\n{root_bones}\n{vca.bone_id} \"vcabone_{name}\" -1\nend\nskeleton\n")

        max_frame = float(len(vca) - 1)
        for i in range(len(vca)):
            self.smd_file.write(f"time {i}\n")
            if self.armature_src:
                for rb in [b for b in self.exportable_bones if b.parent is None]:
                    mat = getUpAxisMat("Y").inverted() @ self.armature.matrix_world @ rb.matrix
                    self.smd_file.write(f"{self.bone_ids[rb.name]} {getSmdVec(mat.to_translation())} {getSmdVec(mat.to_euler())}\n")
            else:
                self.smd_file.write("0 0 0 0 {} 0 0\n".format("-1.570797" if bpy.context.scene.vs.up_axis == "Z" else "0"))
            self.smd_file.write(f"{vca.bone_id} 1.0 {getSmdFloat(i / max_frame)} 0 0 0 0\n")

        self.smd_file.write("end\n")
        self.smd_file.close()
        return 1

    # ─────────────────────────────────────────────────────────────────────────
    # DMX writing — logic unchanged from original
    # ─────────────────────────────────────────────────────────────────────────

    def writeDMX(self, datablock: bpy.types.ID, bake_results: list[BakeResult], name: str, dir_path: str):
        bench = BenchMarker(1, "DMX")
        filepath = os.path.realpath(os.path.join(dir_path, sanitize_string(name, allow_unicode=True) + ".dmx"))
        print("-", filepath)
        armature_name = self.armature_src.name if self.armature_src else name
        materials = {}
        written = 0

        def makeTransform(name, matrix, object_name):
            trfm = dm.add_element(name, "DmeTransform", id=object_name + "transform")
            trfm["position"] = datamodel.Vector3(matrix.to_translation())
            trfm["orientation"] = getDatamodelQuat(matrix.to_quaternion())
            return trfm

        dm = datamodel.DataModel("model", State.datamodelFormat)
        dm.allow_random_ids = False
        source2 = dm.format_ver >= 22

        root = dm.add_element(bpy.context.scene.name, id="Scene" + bpy.context.scene.name)
        DmeModel = dm.add_element(armature_name, "DmeModel", id="Object" + armature_name)
        DmeModel_children = DmeModel["children"] = datamodel.make_array([], datamodel.Element)

        DmeModel_transforms = dm.add_element("base", "DmeTransformList", id="transforms" + bpy.context.scene.name)
        DmeModel["baseStates"] = datamodel.make_array([DmeModel_transforms], datamodel.Element)
        DmeModel_transforms["transforms"] = datamodel.make_array([], datamodel.Element)
        DmeModel_transforms = DmeModel_transforms["transforms"]

        if source2:
            DmeAxisSystem = DmeModel["axisSystem"] = dm.add_element("axisSystem", "DmeAxisSystem", "AxisSys" + armature_name)
            DmeAxisSystem["upAxis"] = axes_lookup_source2[bpy.context.scene.vs.up_axis]
            DmeAxisSystem["forwardParity"] = 1
            DmeAxisSystem["coordSys"] = 0

        DmeModel["transform"] = makeTransform("", Matrix(), (DmeModel.name or "") + "transform")
        keywords = getDmxKeywords(dm.format_ver)

        is_anim = bool(len(bake_results) == 1 and bake_results[0].object.type == "ARMATURE")

        if not is_anim and self.armature:
            self.armature.data.pose_position = "REST"
        elif is_anim:
            self.armature.data.pose_position = "POSE"

        if self.armature:
            if self.armature.data.vs.reset_pose_per_anim:
                for pb in self.armature.pose.bones:
                    pb.matrix_basis.identity()
            bpy.context.view_layer.update()

        root["skeleton"] = DmeModel
        want_jointlist = dm.format_ver >= 11
        want_jointtransforms = dm.format_ver in range(0, 21)

        if want_jointlist:
            jointList = DmeModel["jointList"] = datamodel.make_array([], datamodel.Element)
            if source2:
                jointList.append(DmeModel)
        if want_jointtransforms:
            jointTransforms = DmeModel["jointTransforms"] = datamodel.make_array([], datamodel.Element)
            if source2:
                jointTransforms.append(DmeModel["transform"])

        bone_elements = {}
        if self.armature:
            armature_scale = self.armature.matrix_world.to_scale()

        def writeBone(bone):
            if isinstance(bone, str):
                bone_name, bone = bone, None
            else:
                if bone and bone not in self.exportable_bones:
                    children = []
                    for child_elems in [writeBone(c) for c in bone.children]:
                        if child_elems:
                            children.extend(child_elems)
                    return children
                bone_name = bone.name

            bone_exportname = self.exportable_boneNames[bone.name] if bone else bone_name
            bone_elements[bone_name] = bone_elem = dm.add_element(bone_exportname, "DmeJoint", id=bone_name)
            if want_jointlist:
                jointList.append(bone_elem)
            self.bone_ids[bone_name] = len(bone_elements) - (0 if source2 else 1)

            if not bone:
                relMat = Matrix()
            else:
                cur_p = bone.parent
                while cur_p and cur_p not in self.exportable_bones:
                    cur_p = cur_p.parent
                if cur_p:
                    relMat = get_bone_matrix(cur_p, rest_space=True).inverted() @ bone.matrix
                else:
                    relMat = self.armature.matrix_world @ bone.matrix

            relMat = get_bone_matrix(relMat, bone, rest_space=True)
            trfm = makeTransform(bone_exportname, relMat, "bone" + bone_name)
            trfm_base = makeTransform(bone_exportname, relMat, "bone_base" + bone_name)

            if bone and bone.parent:
                for j in range(3):
                    trfm["position"][j] *= armature_scale[j]
            trfm_base["position"] = trfm["position"]

            if want_jointtransforms:
                jointTransforms.append(trfm)
            bone_elem["transform"] = trfm
            DmeModel_transforms.append(trfm_base)

            if bone:
                children = bone_elem["children"] = datamodel.make_array([], datamodel.Element)
                for child_elems in [writeBone(c) for c in bone.children]:
                    if child_elems:
                        children.extend(child_elems)
                bpy.context.window_manager.progress_update(len(bone_elements) / num_bones)
            return [bone_elem]

        if self.armature:
            num_bones = len(self.exportable_bones)
            add_implicit = not source2
            if add_implicit:
                DmeModel_children.extend(writeBone(implicit_bone_name))
            for root_elems in [writeBone(b) for b in self.armature.pose.bones if not b.parent and not (add_implicit and b.name == implicit_bone_name)]:
                if root_elems:
                    DmeModel_children.extend(root_elems)
            bench.report("Bones")

        def writeattachment(empty: bpy.types.Object, empty_matrix: Matrix):
            current_bone = self.armature.data.bones.get(empty.parent_bone)
            exportable_parent = None
            while current_bone:
                if current_bone.name in self.exportable_boneNames:
                    exportable_parent = self.armature.pose.bones.get(current_bone.name)
                    break
                current_bone = current_bone.parent

            if not exportable_parent:
                self.warning(f"Attachment '{empty.name}' has no exportable parent bone. Skipping.")
                return None

            empty_elem = dm.add_element(empty.name, "DmeDag", id=empty.name)
            attach_elem = dm.add_element(empty.name, "DmeAttachment", id="attachment" + empty.name)
            attach_elem["visible"] = True
            attach_elem["isRigid"] = True
            attach_elem["isWorldAligned"] = False
            empty_elem["shape"] = attach_elem
            empty_elem["visible"] = True
            empty_elem["children"] = datamodel.make_array([], datamodel.Element)

            if want_jointlist:
                jointList.append(empty_elem)

            boneelem = bone_elements[exportable_parent.name]
            if "children" not in boneelem:
                boneelem["children"] = datamodel.make_array([], datamodel.Element)

            pmat = get_bone_matrix(exportable_parent, rest_space=True)
            relMat = pmat.inverted() @ empty_matrix

            trfm = makeTransform(empty.name, relMat, empty.name)
            trfm_base = makeTransform(empty.name, relMat, "empty_base" + empty.name)

            if empty.parent:
                for j in range(3):
                    trfm["position"][j] *= armature_scale[j]
            trfm_base["position"] = trfm["position"]

            empty_elem["transform"] = trfm
            DmeModel_transforms.append(trfm_base)
            if want_jointtransforms:
                jointTransforms.append(trfm)

            boneelem["children"].append(empty_elem)
            return empty_elem

        if not is_anim and self.exportable_empties and self.armature:
            for empty, world_matrix in self.exportable_empties:
                writeattachment(empty, world_matrix)
            bench.report("Empties")

        for vca in bake_results[0].vertex_animations:
            DmeModel_children.extend(writeBone(f"vcabone_{vca}"))

        DmeCombinationOperator = None
        for _ in [b for b in bake_results if b.shapes]:
            if self.flex_controller_mode == "ADVANCED":
                if not hasFlexControllerSource(self.flex_controller_source):
                    self.error(get_id("exporter_err_flexctrl_undefined", True).format(name))
                    return written
                text = bpy.data.texts.get(self.flex_controller_source)
                msg = "- Loading flex controllers from "
                element_path = ["combinationOperator"]
                try:
                    if text:
                        print(msg + f"text block \"{text.name}\"")
                        controller_dm = datamodel.parse(text.as_string(), element_path=element_path)
                    else:
                        path_fc = os.path.realpath(bpy.path.abspath(self.flex_controller_source))
                        print(msg + path_fc)
                        controller_dm = datamodel.load(path=path_fc, element_path=element_path)
                    DmeCombinationOperator = controller_dm.root["combinationOperator"]
                    for elem in [e for e in DmeCombinationOperator["targets"] if e.type != "DmeFlexRules"]:
                        DmeCombinationOperator["targets"].remove(elem)
                except Exception as err:
                    self.error(get_id("exporter_err_flexctrl_loadfail", True).format(err))
                    return written
            else:
                DmeCombinationOperator = flex.DmxWriteFlexControllers.make_controllers(datablock, export=True).root["combinationOperator"]
            break

        if not DmeCombinationOperator and bake_results[0].vertex_animations:
            DmeCombinationOperator = flex.DmxWriteFlexControllers.make_controllers(datablock, export=True).root["combinationOperator"]

        if DmeCombinationOperator:
            root["combinationOperator"] = DmeCombinationOperator
            bench.report("Flex setup")

        for bake in [b for b in bake_results if b.object.type != "ARMATURE"]:
            root["model"] = DmeModel
            ob = bake.object
            assert isinstance(ob.data, bpy.types.Mesh)

            vertex_data = dm.add_element("bind", "DmeVertexData", id=bake.name + "verts")
            DmeMesh = dm.add_element(bake.name, "DmeMesh", id=bake.name + "mesh")
            DmeMesh["visible"] = True
            DmeMesh["bindState"] = vertex_data
            DmeMesh["currentState"] = vertex_data
            DmeMesh["baseStates"] = datamodel.make_array([vertex_data], datamodel.Element)

            DmeDag = dm.add_element(bake.name, "DmeDag", id="ob" + bake.name + "dag")
            if want_jointlist:
                jointList.append(DmeDag)
            DmeDag["shape"] = DmeMesh

            bone_child = isinstance(bake.envelope, str)
            if bone_child and bake.envelope in bone_elements:
                bone_elements[bake.envelope]["children"].append(DmeDag)
                trfm_mat = bake.bone_parent_matrix
            else:
                DmeModel_children.append(DmeDag)
                trfm_mat = ob.matrix_world

            trfm = makeTransform(bake.name, trfm_mat, "ob" + bake.name)
            if want_jointtransforms:
                jointTransforms.append(trfm)
            DmeDag["transform"] = trfm
            DmeModel_transforms.append(makeTransform(bake.name, trfm_mat, "ob_base" + bake.name))

            weight_link_limit = 4 if source2 else 3
            jointCount = badJointCounts = 0
            have_weightmap = False
            cloth_groups = findDmxClothVertexGroups(ob) if source2 else None

            if type(bake.envelope) is bpy.types.ArmatureModifier:
                ob_weights = self.getWeightmap(bake)
                for vw in ob_weights:
                    count = len(vw)
                    if weight_link_limit and count > weight_link_limit:
                        badJointCounts += 1
                    jointCount = max(jointCount, count)
                if jointCount:
                    have_weightmap = True
            elif bake.envelope:
                jointCount = 1

            if badJointCounts:
                self.warning(get_id("exporter_warn_weightlinks_excess", True).format(badJointCounts, bake.src.name, weight_link_limit))

            fmt = vertex_data["vertexFormat"] = datamodel.make_array([keywords["pos"], keywords["norm"]], str)
            vertex_data["flipVCoordinates"] = True
            vertex_data["jointCount"] = jointCount

            num_verts = len(ob.data.vertices)
            num_loops = len(ob.data.loops)
            norms = [None] * num_loops
            texco = ordered_set.OrderedSet()
            face_sets = collections.OrderedDict()
            texcoIndices = [None] * num_loops
            jointWeights = []
            jointIndices = []
            balance = [0.0] * num_verts
            cloth_weights = {}
            Indices = [-1] * num_loops

            if cloth_groups:
                for vgroup in cloth_groups:
                    cloth_weights[vgroup.name] = [0.0] * num_verts

            uv_layer = ob.data.uv_layers.active.data

            def remap(val, a, b, c, d):
                return (((val - a) * (d - c)) / (b - a)) + c

            bench.report("object setup")

            for v in ob.data.vertices:
                v.select = False
                if bake.shapes and bake.balance_vg:
                    try:
                        balance[v.index] = bake.balance_vg.weight(v.index)
                    except Exception:
                        pass

                if cloth_groups:
                    for vgroup in cloth_groups:
                        try:
                            w = vgroup.weight(v.index)
                            for r in ob.vs.vertex_map_remaps:
                                if r.group == vgroup.name:
                                    w = remap(w, 0.0, 1.0, r.min, r.max)
                                    break
                            cloth_weights[vgroup.name][v.index] = w
                        except Exception:
                            for r in ob.vs.vertex_map_remaps:
                                if r.group == vgroup.name:
                                    cloth_weights[vgroup.name][v.index] = r.min
                                    break

                if have_weightmap:
                    weights_row = [0.0] * jointCount
                    indices_row = [0] * jointCount
                    total = 0
                    for i, link in enumerate(ob_weights[v.index]):
                        indices_row[i] = link[0]
                        weights_row[i] = link[1]
                        total += link[1]
                    if source2 and total == 0:
                        weights_row[0] = 1.0
                    jointWeights.extend(weights_row)
                    jointIndices.extend(indices_row)

                if v.index % 50 == 0:
                    bpy.context.window_manager.progress_update(v.index / num_verts)

            bench.report("verts")

            for loop in [ob.data.loops[i] for poly in ob.data.polygons for i in poly.loop_indices]:
                texcoIndices[loop.index] = texco.add(datamodel.Vector2(uv_layer[loop.index].uv))
                norms[loop.index] = datamodel.Vector3(loop.normal)
                Indices[loop.index] = loop.vertex_index

            bench.report("loops")

            bpy.context.view_layer.objects.active = ob
            bpy.ops.object.mode_set(mode="EDIT")
            bm = bmesh.from_edit_mesh(ob.data)
            bm.verts.ensure_lookup_table()
            bm.faces.ensure_lookup_table()

            vertex_data[keywords["pos"]] = datamodel.make_array((v.co for v in bm.verts), datamodel.Vector3)
            vertex_data[keywords["pos"] + "Indices"] = datamodel.make_array((l.vert.index for f in bm.faces for l in f.loops), int)

            if source2:
                loops = [loop for face in bm.faces for loop in face.loops]
                loop_indices = datamodel.make_array([loop.index for loop in loops], int)
                layerGroups = bm.loops.layers

                class exportLayer:
                    def __init__(self, layer, exportName=None):
                        self._layer = layer
                        self.name = exportName or layer.name
                    def data_for(self, loop):
                        return loop[self._layer]

                def get_bmesh_layers(group):
                    return [exportLayer(l) for l in group if re.match(r".*\$[0-9]+", l.name)]

                defaultUvLayer = "texcoord$0"
                uv_layers_to_export = list(get_bmesh_layers(layerGroups.uv))
                if defaultUvLayer not in [l.name for l in uv_layers_to_export]:
                    uv_render = next((l.name for l in ob.data.uv_layers if l.active_render and l not in uv_layers_to_export), None)
                    if uv_render:
                        uv_layers_to_export.append(exportLayer(layerGroups.uv[uv_render], defaultUvLayer))
                        print(f"- Exporting '{uv_render}' as {defaultUvLayer}")
                    else:
                        self.warning(f"'{bake.name}' has no UV map named {defaultUvLayer} and no fallback was found.")

                for layer in uv_layers_to_export:
                    uv_set = ordered_set.OrderedSet()
                    uv_indices = []
                    for uv in (layer.data_for(loop).uv for loop in loops):
                        uv_indices.append(uv_set.add(datamodel.Vector2(uv)))
                    vertex_data[layer.name] = datamodel.make_array(uv_set, datamodel.Vector2)
                    vertex_data[layer.name + "Indices"] = datamodel.make_array(uv_indices, int)
                    fmt.append(layer.name)

                def make_vertex_layer(layer, array_type):
                    vertex_data[layer.name] = datamodel.make_array([layer.data_for(l) for l in loops], array_type)
                    vertex_data[layer.name + "Indices"] = loop_indices
                    fmt.append(layer.name)

                for layer in get_bmesh_layers(layerGroups.color):
                    make_vertex_layer(layer, datamodel.Vector4)
                for layer in get_bmesh_layers(layerGroups.float):
                    make_vertex_layer(layer, float)
                for layer in get_bmesh_layers(layerGroups.int):
                    make_vertex_layer(layer, int)
                for layer in get_bmesh_layers(layerGroups.string):
                    make_vertex_layer(layer, str)

                bench.report("Source 2 vertex data")
            else:
                fmt.append("textureCoordinates")
                vertex_data["textureCoordinates"] = datamodel.make_array(texco, datamodel.Vector2)
                vertex_data["textureCoordinatesIndices"] = datamodel.make_array(texcoIndices, int)

            if have_weightmap:
                vertex_data[keywords["weight"]] = datamodel.make_array(jointWeights, float)
                vertex_data[keywords["weight_indices"]] = datamodel.make_array(jointIndices, int)
                fmt.extend([keywords["weight"], keywords["weight_indices"]])

            deform_layer = bm.verts.layers.deform.active
            if deform_layer:
                for cloth_enable in (g for g in ob.vertex_groups if re.match(r"cloth_enable\$[0-9]+", g.name)):
                    fmt.append(cloth_enable.name)
                    values = [v[deform_layer].get(cloth_enable.index, 0) for v in bm.verts]
                    value_set = ordered_set.OrderedSet(values)
                    vertex_data[cloth_enable.name] = datamodel.make_array(value_set, float)
                    vertex_data[cloth_enable.name + "Indices"] = datamodel.make_array(
                        (value_set.index(values[i]) for i in Indices), int
                    )

            if bake.shapes and bake.balance_vg:
                vertex_data[keywords["balance"]] = datamodel.make_array(balance, float)
                vertex_data[keywords["balance"] + "Indices"] = datamodel.make_array(Indices, int)
                fmt.append(keywords["balance"])

            if cloth_groups:
                for vgroup in cloth_groups:
                    fmt.append(vgroup.name + "$0")

            vertex_data[keywords["norm"]] = datamodel.make_array(norms, datamodel.Vector3)
            vertex_data[keywords["norm"] + "Indices"] = datamodel.make_array(range(len(norms)), int)

            if cloth_groups:
                for kw in cloth_weights:
                    vertex_data[kw + "$0"] = datamodel.make_array(cloth_weights[kw], float)
                    vertex_data[kw + "$0Indices"] = datamodel.make_array(Indices, int)

            bench.report("insert")

            bad_face_mats = 0
            num_polys = len(bm.faces)
            two_percent = int(num_polys / 50)
            print("Polygons: ", debug_only=True, newline=False)

            bm_face_sets = collections.defaultdict(list)
            for p, face in enumerate(bm.faces):
                mat_name, mat_ok = self.GetMaterialName(ob, face.material_index)
                if not mat_ok:
                    bad_face_mats += 1
                bm_face_sets[mat_name].extend((*(l.index for l in face.loops), -1))
                if two_percent and p % two_percent == 0:
                    print(".", debug_only=True, newline=False)
                    bpy.context.window_manager.progress_update(p / num_polys)

            for mat_name, indices in bm_face_sets.items():
                material_elem = materials.get(mat_name)
                if not material_elem:
                    materials[mat_name] = material_elem = dm.add_element(mat_name, "DmeMaterial", id=mat_name + "mat")
                    matdata = ob.data.materials.get(mat_name)
                    if matdata and matdata.vs.override_dmx_export_path.strip():
                        mat_path = matdata.vs.override_dmx_export_path
                    else:
                        mat_path = bpy.context.scene.vs.material_path
                    material_elem["mtlName"] = os.path.join(mat_path, mat_name).replace("\\", "/")

                face_set = dm.add_element(mat_name, "DmeFaceSet", id=bake.name + mat_name + "faces")
                face_sets[mat_name] = face_set
                face_set["material"] = material_elem
                face_set["faces"] = datamodel.make_array(indices, int)

            print(debug_only=True)
            DmeMesh["faceSets"] = datamodel.make_array(list(face_sets.values()), datamodel.Element)

            if bad_face_mats:
                self.warning(get_id("exporter_err_facesnotex_ormat").format(bad_face_mats, bake.name))
            bench.report("polys")

            bpy.ops.object.mode_set(mode="OBJECT")
            del bm

            two_percent = int(len(bake.shapes) / 50)
            print("Shapes: ", debug_only=True, newline=False)
            delta_states = []
            corrective_shapes_seen = []

            if bake.shapes:
                shape_names = []
                num_shapes = len(bake.shapes)
                num_correctives = num_wrinkles = 0

                for shape_name, shape in bake.shapes.items():
                    wrinkle_scale = 0
                    corrective = getCorrectiveShapeSeparator() in shape_name

                    if corrective:
                        driver_targets = ordered_set.OrderedSet(flex.getCorrectiveShapeKeyDrivers(bake.src.data.shape_keys.key_blocks[shape_name]) or [])
                        name_targets = ordered_set.OrderedSet(shape_name.split(getCorrectiveShapeSeparator()))
                        corrective_targets = driver_targets or name_targets
                        corrective_targets.source = shape_name

                        if corrective_targets in corrective_shapes_seen:
                            prev = next(x for x in corrective_shapes_seen if x == corrective_targets)
                            self.warning(get_id("exporter_warn_correctiveshape_duplicate", True).format(shape_name, "+".join(corrective_targets), prev.source))
                            continue
                        corrective_shapes_seen.append(corrective_targets)

                        if driver_targets and driver_targets != name_targets:
                            generated = getCorrectiveShapeSeparator().join(driver_targets)
                            print(f"- Renamed shape key '{shape_name}' to '{generated}' to match corrective drivers.")
                            shape_name = generated
                        num_correctives += 1
                    else:
                        if self.flex_controller_mode == "ADVANCED":
                            def _find_scale():
                                for ctrl in controller_dm.root["combinationOperator"]["controls"]:
                                    for i in range(len(ctrl["rawControlNames"])):
                                        if ctrl["rawControlNames"][i] == shape_name:
                                            scales = ctrl.get("wrinkleScales")
                                            return scales[i] if scales else 0
                                raise ValueError()
                            try:
                                wrinkle_scale = _find_scale()
                            except ValueError:
                                self.warning(get_id("exporter_err_flexctrl_missing", True).format(shape_name))

                    shape_names.append(shape_name)
                    DmeVertexDeltaData = dm.add_element(shape_name, "DmeVertexDeltaData", id=ob.name + shape_name)
                    delta_states.append(DmeVertexDeltaData)
                    vtxFmt = DmeVertexDeltaData["vertexFormat"] = datamodel.make_array([keywords["pos"], keywords["norm"]], str)

                    shape_pos, shape_posIdx = [], []
                    shape_norms, shape_normIdx = [], []
                    wrinkle, wrinkleIdx = [], []
                    cache_deltas = wrinkle_scale
                    delta_lengths = [None] * num_verts if cache_deltas else None
                    max_delta = 0

                    for ob_vert in ob.data.vertices:
                        sv = shape.vertices[ob_vert.index]
                        if ob_vert.co != sv.co:
                            delta = sv.co - ob_vert.co
                            dl = delta.length
                            if abs(dl) > 1e-5:
                                if cache_deltas:
                                    delta_lengths[ob_vert.index] = dl
                                shape_pos.append(datamodel.Vector3(delta))
                                shape_posIdx.append(ob_vert.index)

                    if corrective:
                        corrective_target_shapes = []
                        for ct_name in corrective_targets:
                            ct = bake.shapes.get(ct_name)
                            if ct:
                                corrective_target_shapes.append(ct)
                                for sv in shape.vertices:
                                    sv.co -= ob.data.vertices[sv.index].co - ct.vertices[sv.index].co
                            else:
                                self.warning(get_id("exporter_err_missing_corrective_target", format_string=True).format(shape_name, ct_name))

                    for ob_loop in ob.data.loops:
                        sl = shape.loops[ob_loop.index]
                        norm = sl.normal
                        if corrective:
                            base = ob_loop.normal.copy()
                            for ct in corrective_target_shapes:
                                base += ct.loops[sl.index].normal - ob_loop.normal
                        else:
                            base = ob_loop.normal
                        if norm.dot(base.normalized()) < 1 - 1e-3:
                            shape_norms.append(datamodel.Vector3(norm - base))
                            shape_normIdx.append(sl.index)
                        if wrinkle_scale and delta_lengths and delta_lengths[ob_loop.vertex_index]:
                            dl = delta_lengths[ob_loop.vertex_index]
                            max_delta = max(max_delta, dl)
                            wrinkle.append(dl)
                            wrinkleIdx.append(texcoIndices[ob_loop.index])

                    if wrinkle_scale and max_delta:
                        mod = wrinkle_scale / max_delta
                        if mod != 1:
                            wrinkle = [w * mod for w in wrinkle]

                    DmeVertexDeltaData[keywords["pos"]] = datamodel.make_array(shape_pos, datamodel.Vector3)
                    DmeVertexDeltaData[keywords["pos"] + "Indices"] = datamodel.make_array(shape_posIdx, int)
                    DmeVertexDeltaData[keywords["norm"]] = datamodel.make_array(shape_norms, datamodel.Vector3)
                    DmeVertexDeltaData[keywords["norm"] + "Indices"] = datamodel.make_array(shape_normIdx, int)

                    if wrinkle_scale:
                        vtxFmt.append(keywords["wrinkle"])
                        num_wrinkles += 1
                        DmeVertexDeltaData[keywords["wrinkle"]] = datamodel.make_array(wrinkle, float)
                        DmeVertexDeltaData[keywords["wrinkle"] + "Indices"] = datamodel.make_array(wrinkleIdx, int)

                    bpy.context.window_manager.progress_update(len(shape_names) / num_shapes)
                    if two_percent and len(shape_names) % two_percent == 0:
                        print(".", debug_only=True, newline=False)

                if bpy.app.debug_value <= 1:
                    for shape in bake.shapes.values():
                        bpy.data.meshes.remove(shape)
                    bake.shapes.clear()

                print(debug_only=True)
                bench.report("shapes")
                print(f"- {num_shapes - num_correctives} flexes ({num_wrinkles} with wrinklemaps) + {num_correctives} correctives")

            vca_matrix = ob.matrix_world.inverted()
            for vca_name, vca in bake_results[0].vertex_animations.items():
                frame_shapes = []
                for i, vca_ob in enumerate(vca):
                    VDD = dm.add_element(f"{vca_name}-{i}", "DmeVertexDeltaData", id=ob.name + vca_name + str(i))
                    delta_states.append(VDD)
                    frame_shapes.append(VDD)
                    VDD["vertexFormat"] = datamodel.make_array(["positions", "normals"], str)

                    sp, spi, sn, sni = [], [], [], []
                    for sl in vca_ob.data.loops:
                        sv = vca_ob.data.vertices[sl.vertex_index]
                        ol = ob.data.loops[sl.index]
                        ov = ob.data.vertices[ol.vertex_index]
                        if ov.co != sv.co:
                            delta = vca_matrix @ sv.co - ov.co
                            if abs(delta.length) > 1e-5:
                                sp.append(datamodel.Vector3(delta))
                                spi.append(ov.index)
                        norm = Vector(sl.normal)
                        norm.rotate(vca_matrix)
                        if abs(1.0 - norm.dot(ol.normal)) > epsilon[0]:
                            sn.append(datamodel.Vector3(norm - ol.normal))
                            sni.append(sl.index)

                    VDD["positions"] = datamodel.make_array(sp, datamodel.Vector3)
                    VDD["positionsIndices"] = datamodel.make_array(spi, int)
                    VDD["normals"] = datamodel.make_array(sn, datamodel.Vector3)
                    VDD["normalsIndices"] = datamodel.make_array(sni, int)

                    removeObject(vca_ob)
                    vca[i] = None

                if vca.export_sequence:
                    vca_arm = bpy.data.objects.new("vca_arm", bpy.data.armatures.new("vca_arm"))
                    bpy.context.scene.collection.objects.link(vca_arm)
                    bpy.context.view_layer.objects.active = vca_arm
                    bpy.ops.object.mode_set(mode="EDIT")
                    vca_bone = vca_arm.data.edit_bones.new("vcabone_" + vca_name)
                    vca_bone.tail.y = 1
                    bpy.context.scene.frame_set(0)
                    mat = getUpAxisMat("y").inverted()
                    if self.armature_src:
                        for bone in [b for b in self.armature_src.data.bones if b.parent is None]:
                            b = vca_arm.data.edit_bones.new(bone.name)
                            b.head = mat @ bone.head
                            b.tail = mat @ bone.tail
                    else:
                        for bk in bake_results:
                            bm_mat = mat @ bk.object.matrix_world
                            b = vca_arm.data.edit_bones.new(bk.name)
                            b.head = bm_mat @ b.head
                            b.tail = bm_mat @ Vector([0, 1, 0])

                    bpy.ops.object.mode_set(mode="POSE")
                    ops.pose.armature_apply()

                    if State.useActionSlots:
                        fcurves = channelBagForNewActionSlot(vca_arm, vca_name).fcurves
                    else:
                        action = vca_arm.animation_data_create().action = bpy.data.actions.new("vcaanim_" + vca_name)
                        fcurves = action.fcurves

                    for ax in range(2):
                        fc = fcurves.new(f'pose.bones["vcabone_{vca_name}"].location', index=ax)
                        fc.keyframe_points.add(count=2)
                        for kp in fc.keyframe_points:
                            kp.interpolation = "LINEAR"
                        if ax == 0:
                            fc.keyframe_points[0].co = (0, 1.0)
                        fc.keyframe_points[1].co = (vca.num_frames, 1.0)
                        fc.update()

                    self._execute_task(bpy.context, vca_arm, ExportTask(vca_arm, vca_arm.name), os.path.dirname(filepath), bench)
                    written += 1

            if delta_states:
                DmeMesh["deltaStates"] = datamodel.make_array(delta_states, datamodel.Element)
                DmeMesh["deltaStateWeights"] = DmeMesh["deltaStateWeightsLagged"] = datamodel.make_array(
                    [datamodel.Vector2([0.0, 0.0])] * len(delta_states), datamodel.Vector2
                )
                if not DmeCombinationOperator:
                    raise RuntimeError("Internal error: shapes exist but no DmeCombinationOperator was created.")
                targets = DmeCombinationOperator["targets"]
                added = False
                for elem in targets:
                    if elem.type == "DmeFlexRules":
                        if elem["deltaStates"][0].name in shape_names:
                            elem["target"] = DmeMesh
                            added = True
                if not added:
                    targets.append(DmeMesh)

        if is_anim:
            ad = self.armature.animation_data
            anim_len = animationLength(ad) if ad else 0
            fps = bpy.context.scene.render.fps * bpy.context.scene.render.fps_base

            DmeChannelsClip = dm.add_element(name, "DmeChannelsClip", id=name + "clip")
            DmeAnimationList = dm.add_element(armature_name, "DmeAnimationList", id=armature_name + "list")
            DmeAnimationList["animations"] = datamodel.make_array([DmeChannelsClip], datamodel.Element)
            root["animationList"] = DmeAnimationList

            DmeTimeFrame = dm.add_element("timeframe", "DmeTimeFrame", id=name + "time")
            duration = anim_len / fps
            if dm.format_ver >= 11:
                DmeTimeFrame["duration"] = datamodel.Time(duration)
            else:
                DmeTimeFrame["durationTime"] = int(duration * 10000)
            DmeTimeFrame["scale"] = 1.0
            DmeChannelsClip["timeFrame"] = DmeTimeFrame
            DmeChannelsClip["frameRate"] = fps if source2 else int(fps)

            channels = DmeChannelsClip["channels"] = datamodel.make_array([], datamodel.Element)
            bone_channels = {}

            def makeChannel(bone):
                export_name = self.exportable_boneNames[bone.name]
                bone_channels[bone.name] = []
                for suffix, attr, type_name, dm_type in [
                    ("_p", "position", "Vector3", datamodel.Vector3),
                    ("_o", "orientation", "Quaternion", datamodel.Quaternion),
                ]:
                    ch_name = export_name + suffix
                    cur = dm.add_element(ch_name, "DmeChannel", id=bone.name + suffix)
                    cur["toAttribute"] = attr
                    cur["toElement"] = (bone_elements[bone.name] if bone else DmeModel)["transform"]
                    cur["mode"] = 1
                    layer = dm.add_element(type_name + " log", f"Dme{type_name}LogLayer", ch_name + "loglayer")
                    cur["log"] = dm.add_element(type_name + " log", f"Dme{type_name}Log", ch_name + "log")
                    cur["log"]["layers"] = datamodel.make_array([layer], datamodel.Element)
                    layer["times"] = datamodel.make_array([], datamodel.Time if dm.format_ver > 11 else int)
                    layer["values"] = datamodel.make_array([], dm_type)
                    if bone:
                        bone_channels[bone.name].append(layer)
                    channels.append(cur)

            for bone in self.exportable_bones:
                makeChannel(bone)

            num_frames = int(anim_len + 1)
            bench.report("Animation setup")
            two_percent = num_frames / 50
            print("Frames: ", debug_only=True, newline=False)

            for frame in range(num_frames):
                bpy.context.window_manager.progress_update(frame / num_frames)
                bpy.context.scene.frame_set(frame)
                keyframe_time = datamodel.Time(frame / fps) if dm.format_ver > 11 else int(frame / fps * 10000)
                evaluated = self.getEvaluatedPoseBones()

                for bone in evaluated:
                    channel = bone_channels[bone.name]
                    cur_p = bone.parent
                    while cur_p and cur_p not in evaluated:
                        cur_p = cur_p.parent
                    if cur_p:
                        relMat = get_bone_matrix(cur_p).inverted() @ bone.matrix
                    else:
                        relMat = self.armature.matrix_world @ bone.matrix
                    relMat = get_bone_matrix(relMat, bone)

                    pos = relMat.to_translation()
                    if bone.parent:
                        for j in range(3):
                            pos[j] *= armature_scale[j]

                    channel[0]["times"].append(keyframe_time)
                    channel[0]["values"].append(datamodel.Vector3(pos))
                    channel[1]["times"].append(keyframe_time)
                    channel[1]["values"].append(getDatamodelQuat(relMat.to_quaternion()))

                if two_percent and frame % two_percent:
                    print(".", debug_only=True, newline=False)

            print(debug_only=True)

        bpy.context.window_manager.progress_update(0.99)
        print("- Writing DMX...")
        try:
            if bpy.context.scene.vs.use_kv2:
                dm.write(filepath, "keyvalues2", 1)
            else:
                dm.write(filepath, "binary", State.datamodelEncoding)
            written += 1
        except (PermissionError, FileNotFoundError) as err:
            self.error(get_id("exporter_err_open", True).format("DMX", err))

        bench.report("write")
        if bench.quiet:
            print("- DMX export took", bench.total(), "\n")

        return written


class PrefabExporter(bpy.types.Operator, ExportCheck):
    bl_idname = "smd.export_prefab"
    bl_label = "Export Prefab"

    export_type: bpy.props.EnumProperty(
        items=[
            ('JIGGLEBONES', "Jigglebones", ""),
            ('ATTACHMENTS', "Attachments", ""),
            ('HITBOXES',    "Hitboxes",    ""),
        ]
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and get_armature(context.active_object) is not None
    
    def get_filepath(self, path: str | None):
        if not path or not isinstance(path, str):
            raise ValueError(f"Invalid path: {path!r}")

        path = path.replace("\\", "/")
        path = path.replace("//..", "//../")

        export_path = bpy.path.abspath(path)
        if not export_path:
            raise ValueError(f"bpy.path.abspath() failed to resolve: {path!r}")

        filename = os.path.basename(export_path)
        root, ext = os.path.splitext(filename)
        return export_path, filename, ext


    def _get_export_path(self, context):
        arm = get_armature(context.active_object)
        vs = arm.vs
        return {
            'JIGGLEBONES': vs.jigglebone_prefabfile,
            'ATTACHMENTS': vs.attachment_prefabfile,
            'HITBOXES':    vs.hitbox_prefabfile,
        }.get(self.export_type, "")

    def _write_output(self, compiled, export_path=None, warnings=None):
        if not compiled:
            return False

        if self.to_clipboard:
            bpy.context.window_manager.clipboard = compiled
            self.report({'INFO'}, "Data copied to clipboard")
            return True

        if not export_path:
            self.report({'ERROR'}, "No export path provided")
            return False

        os.makedirs(os.path.dirname(export_path), exist_ok=True)
        with open(export_path, "w", encoding="utf-8") as f:
            f.write(compiled)

        if warnings:
            self.report({'WARNING'}, f"Exported with {len(warnings)} warning(s) (see console)")
            for w in warnings:
                print(w)
        else:
            self.report({'INFO'}, f"Data exported to {export_path}")
        return True

    def execute(self, context) -> set:

        ops.ed.undo_push(message=self.bl_label)
        try:
            for view_layer in bpy.context.scene.view_layers:
                    unhide_all(view_layer.layer_collection)

            bpy.context.view_layer.update()

            arm = get_armature(context.active_object)
            self.to_clipboard = context.scene.vs.prefab_to_clipboard

            bone_names = {bone.name: get_bone_exportname(bone) for bone in arm.data.bones}
            if not self.check_duplicate_bone_names(bone_names):
                return {'CANCELLED'}

            export_path = None
            fmt = None

            if not self.to_clipboard:
                raw_path = self._get_export_path(context)
                if not raw_path:
                    self.report({'ERROR'}, "No export path set on object")
                    return {'CANCELLED'}

                export_path, filename, ext = self.get_filepath(raw_path)
                if not filename or not ext:
                    self.report({'ERROR'}, "Invalid export path: must include filename and extension")
                    return {'CANCELLED'}

                ext_lower = ext.lower()
                if ext_lower in {'.qc', '.qci'}:
                    fmt = 'QC'
                elif ext_lower in {'.vmdl', '.vmdl_prefab'}:
                    fmt = 'VMDL'
                else:
                    self.report({'ERROR'}, f"Unsupported file extension '{ext_lower}'")
                    return {'CANCELLED'}

            warnings = None
            if self.export_type == 'JIGGLEBONES':
                compiled = self._run_jigglebones(arm, fmt, export_path)
            elif self.export_type == 'ATTACHMENTS':
                compiled = self._run_attachments(arm, fmt, export_path, context)
            elif self.export_type == 'HITBOXES':
                compiled, warnings = self._run_hitboxes(arm)
            else:
                return {'CANCELLED'}

            if compiled is None:
                return {'CANCELLED'}

            if not self._write_output(compiled, export_path, warnings):
                return {'CANCELLED'}
        finally:
            ops.ed.undo_push(message=self.bl_label)
            if bpy.app.debug_value <= 1: ops.ed.undo()

        return {'FINISHED'}

    # Jigglebones

    def _run_jigglebones(self, arm, fmt, export_path):
        jigglebones = [b for b in arm.data.bones if b.vs.bone_is_jigglebone]
        if not jigglebones:
            self.report({'WARNING'}, "No jigglebones found")
            return None

        collection_groups = {}
        for bone in jigglebones:
            group_name = bone.collections[0].name if bone.collections else "Others"
            collection_groups.setdefault(group_name, []).append(bone)

        if self.to_clipboard:
            return self._jigglebones_vmdl(collection_groups, None) if State.compiler == Compiler.MODELDOC else self._jigglebones_qc(collection_groups)
        if fmt == 'QC':
            return self._jigglebones_qc(collection_groups)
        if fmt == 'VMDL':
            return self._jigglebones_vmdl(collection_groups, export_path)
        return None

    def _jigglebones_qc(self, collection_groups):
        entries = []
        for group_name, group_bones in collection_groups.items():
            entries.append(f"// Jigglebones: {group_name}")
            entries.append("")
            for bone in group_bones:
                d = []
                d.append(f'$jigglebone "{get_bone_exportname(bone)}"')
                d.append('{')
                jiggle_length = bone.length if bone.vs.use_bone_length_for_jigglebone_length else bone.vs.jiggle_length

                if bone.vs.jiggle_flex_type in ['FLEXIBLE', 'RIGID']:
                    d.append('\tis_flexible' if bone.vs.jiggle_flex_type == 'FLEXIBLE' else '\tis_rigid')
                    d.append('\t{')
                    d.append(f'\t\tlength {jiggle_length:.4f}')
                    d.append(f'\t\ttip_mass {bone.vs.jiggle_tip_mass:.2f}')
                    if bone.vs.jiggle_flex_type == 'FLEXIBLE':
                        d.append(f'\t\tyaw_stiffness {bone.vs.jiggle_yaw_stiffness:.4f}')
                        d.append(f'\t\tyaw_damping {bone.vs.jiggle_yaw_damping:.4f}')
                        if bone.vs.jiggle_has_yaw_constraint:
                            d.append(f'\t\tyaw_constraint {-abs(math.degrees(bone.vs.jiggle_yaw_constraint_min)):.4f} {abs(math.degrees(bone.vs.jiggle_yaw_constraint_max)):.4f}')
                            d.append(f'\t\tyaw_friction {bone.vs.jiggle_yaw_friction:.3f}')
                        d.append(f'\t\tpitch_stiffness {bone.vs.jiggle_pitch_stiffness:.4f}')
                        d.append(f'\t\tpitch_damping {bone.vs.jiggle_pitch_damping:.4f}')
                        if bone.vs.jiggle_has_pitch_constraint:
                            d.append(f'\t\tpitch_constraint {-abs(math.degrees(bone.vs.jiggle_pitch_constraint_min)):.4f} {abs(math.degrees(bone.vs.jiggle_pitch_constraint_max)):.4f}')
                            d.append(f'\t\tpitch_friction {bone.vs.jiggle_pitch_friction:.3f}')
                        if bone.vs.jiggle_allow_length_flex:
                            d.append('\t\tallow_length_flex')
                            d.append(f'\t\talong_stiffness {bone.vs.jiggle_along_stiffness:.4f}')
                        if bone.vs.jiggle_has_angle_constraint:
                            d.append(f'\t\tangle_constraint {math.degrees(bone.vs.jiggle_angle_constraint):.4f}')
                    d.append('\t}')

                if bone.vs.jiggle_base_type == 'BASESPRING':
                    d.append('\thas_base_spring')
                    d.append('\t{')
                    d.append(f'\t\tstiffness {bone.vs.jiggle_base_stiffness:.4f}')
                    d.append(f'\t\tdamping {bone.vs.jiggle_base_damping:.4f}')
                    d.append(f'\t\tbase_mass {bone.vs.jiggle_base_mass}')
                    if bone.vs.jiggle_has_left_constraint:
                        d.append(f'\t\tleft_constraint {-abs(bone.vs.jiggle_left_constraint_min):.2f} {abs(bone.vs.jiggle_left_constraint_max):.2f}')
                        d.append(f'\t\tleft_friction {bone.vs.jiggle_left_friction:.3f}')
                    if bone.vs.jiggle_has_up_constraint:
                        d.append(f'\t\tup_constraint {-abs(bone.vs.jiggle_up_constraint_min):.2f} {abs(bone.vs.jiggle_up_constraint_max):.2f}')
                        d.append(f'\t\tup_friction {bone.vs.jiggle_up_friction:.3f}')
                    if bone.vs.jiggle_has_forward_constraint:
                        d.append(f'\t\tforward_constraint {-abs(bone.vs.jiggle_forward_constraint_min):.2f} {abs(bone.vs.jiggle_forward_constraint_max):.2f}')
                        d.append(f'\t\tforward_friction {bone.vs.jiggle_forward_friction:.3f}')
                    d.append('\t}')
                elif bone.vs.jiggle_base_type == 'BOING':
                    d.append('\tis_boing')
                    d.append('\t{')
                    d.append(f'\t\timpact_speed {bone.vs.jiggle_impact_speed}')
                    d.append(f'\t\timpact_angle {math.degrees(bone.vs.jiggle_impact_angle):.4f}')
                    d.append(f'\t\tdamping_rate {bone.vs.jiggle_damping_rate:.3f}')
                    d.append(f'\t\tfrequency {bone.vs.jiggle_frequency:.3f}')
                    d.append(f'\t\tamplitude {bone.vs.jiggle_amplitude:.3f}')
                    d.append('\t}')
                d.append('}')
                d.append('\n')
                entries.append("\n".join(d))
        return "\n".join(entries)

    def _jigglebones_vmdl(self, collection_groups, export_path):
        folder_nodes = []
        for group_name, group_bones in collection_groups.items():
            folder = KVNode(_class="Folder", name=sanitize_string(group_name))
            for bone in group_bones:
                flex_type = 2 if bone.vs.jiggle_flex_type not in ['FLEXIBLE', 'RIGID'] else (1 if bone.vs.jiggle_flex_type == 'FLEXIBLE' else 0)
                jiggle_length = bone.length if bone.vs.use_bone_length_for_jigglebone_length else bone.vs.jiggle_length
                folder.add_child(KVNode(
                    _class="JiggleBone",
                    name=f"JiggleBone_{get_bone_exportname(bone)}",
                    jiggle_root_bone=get_bone_exportname(bone),
                    jiggle_type=flex_type,
                    has_yaw_constraint=KVBool(bone.vs.jiggle_has_yaw_constraint),
                    has_pitch_constraint=KVBool(bone.vs.jiggle_has_pitch_constraint),
                    has_angle_constraint=KVBool(bone.vs.jiggle_has_angle_constraint),
                    has_base_spring=KVBool(bone.vs.jiggle_base_type == 'BASESPRING'),
                    allow_flex_length=KVBool(bone.vs.jiggle_allow_length_flex),
                    length=jiggle_length,
                    tip_mass=bone.vs.jiggle_tip_mass,
                    angle_limit=math.degrees(bone.vs.jiggle_angle_constraint),
                    min_yaw=math.degrees(bone.vs.jiggle_yaw_constraint_min),
                    max_yaw=math.degrees(bone.vs.jiggle_yaw_constraint_max),
                    yaw_friction=bone.vs.jiggle_yaw_friction,
                    min_pitch=math.degrees(bone.vs.jiggle_pitch_constraint_min),
                    max_pitch=math.degrees(bone.vs.jiggle_pitch_constraint_max),
                    pitch_friction=bone.vs.jiggle_pitch_friction,
                    base_mass=bone.vs.jiggle_base_mass,
                    base_stiffness=bone.vs.jiggle_base_stiffness,
                    base_damping=bone.vs.jiggle_base_damping,
                    base_left_min=bone.vs.jiggle_left_constraint_min,
                    base_left_max=bone.vs.jiggle_left_constraint_max,
                    base_left_friction=bone.vs.jiggle_left_friction,
                    base_up_min=bone.vs.jiggle_up_constraint_min,
                    base_up_max=bone.vs.jiggle_up_constraint_max,
                    base_up_friction=bone.vs.jiggle_up_friction,
                    base_forward_min=bone.vs.jiggle_forward_constraint_min,
                    base_forward_max=bone.vs.jiggle_forward_constraint_max,
                    base_forward_friction=bone.vs.jiggle_forward_friction,
                    yaw_stiffness=bone.vs.jiggle_yaw_stiffness,
                    yaw_damping=bone.vs.jiggle_yaw_damping,
                    pitch_stiffness=bone.vs.jiggle_pitch_stiffness,
                    pitch_damping=bone.vs.jiggle_pitch_damping,
                    along_stiffness=bone.vs.jiggle_along_stiffness,
                    along_damping=bone.vs.jiggle_along_damping,
                ))
            folder_nodes.append(folder)

        kv_doc = update_vmdl_container(
            container_class="JiggleBoneList" if not self.to_clipboard else "ScratchArea",
            nodes=folder_nodes,
            export_path=export_path,
            to_clipboard=self.to_clipboard
        )
        if kv_doc is False:
            self.report({"WARNING"}, 'Existing file may not be a valid KeyValues3')
            return None
        return kv_doc.to_text()

    # Attachments

    def _run_attachments(self, arm, fmt, export_path, context):
        attachments = get_attachments(arm)
        if not attachments:
            self.report({'WARNING'}, "No attachments found")
            return None

        if self.to_clipboard:
            return self._attachments_vmdl(arm, attachments, None) if State.compiler == Compiler.MODELDOC else self._attachments_qc(arm, attachments)
        if fmt == 'QC':
            return self._attachments_qc(arm, attachments)
        if fmt == 'VMDL':
            return self._attachments_vmdl(arm, attachments, export_path)
        return None

    def _attachments_qc(self, arm, attachments):
        lines = []
        for empty in attachments:
            if not empty.parent_bone:
                continue
            bone = arm.data.bones.get(empty.parent_bone)
            if not bone:
                continue
            pose_bone = arm.pose.bones.get(empty.parent_bone)
            if not pose_bone:
                continue
            pmat = get_bone_matrix(pose_bone, rest_space=True)
            relMat = pmat.inverted() @ empty.matrix_world
            position = relMat.to_translation()
            rotation = relMat.to_quaternion().to_euler('XYZ')
            lines.append(f'$attachment "{empty.name}" "{get_bone_exportname(bone)}" {position.x:.2f} {position.y:.2f} {position.z:.2f} rotate {math.degrees(rotation.y):.0f} {math.degrees(rotation.z):.0f} {math.degrees(rotation.x):.0f}')
        return '\n'.join(lines)

    def _attachments_vmdl(self, arm, attachments, export_path):
        nodes = []
        for empty in attachments:
            if not empty.parent_bone:
                continue
            bone = arm.data.bones.get(empty.parent_bone)
            if not bone:
                continue
            pose_bone = arm.pose.bones.get(empty.parent_bone)
            if not pose_bone:
                continue
            pmat = get_bone_matrix(pose_bone, rest_space=True)
            relMat = pmat.inverted() @ empty.matrix_world
            position = relMat.translation
            rotation = relMat.to_euler('YZX')
            nodes.append(KVNode(
                _class="Attachment",
                name=empty.name,
                parent_bone=get_bone_exportname(bone),
                relative_origin=KVVector3(position.x, position.y, position.z),
                relative_angles=KVVector3(math.degrees(rotation.y), math.degrees(rotation.z), math.degrees(rotation.x)),
                weight=1.0,
                ignore_rotation=KVBool(False)
            ))

        kv_doc = update_vmdl_container(
            container_class="ScratchArea" if self.to_clipboard else "AttachmentList",
            nodes=nodes,
            export_path=export_path,
            to_clipboard=self.to_clipboard
        )
        if kv_doc is False:
            self.report({"WARNING"}, 'Existing file may not be a valid KeyValues3')
            return None
        return kv_doc.to_text()

    # Hitboxes

    def _run_hitboxes(self, arm):
        hitbox_data = []
        rotated = []

        for obj in bpy.data.objects:
            if obj.type != 'EMPTY' or obj.empty_display_type != 'CUBE':
                continue
            if not hasattr(obj, 'vs') or not obj.vs.smd_hitbox:
                continue
            if not (obj.parent and obj.parent == arm and obj.parent_type == 'BONE' and obj.parent_bone):
                continue

            rot = obj.rotation_euler
            if abs(rot.x) > 0.0001 or abs(rot.y) > 0.0001 or abs(rot.z) > 0.0001:
                rotated.append(obj.name)

            bounds = self._hitbox_bounds(obj, arm)
            if not bounds:
                continue

            bone = arm.data.bones.get(obj.parent_bone)
            if not bone:
                continue

            hitbox_data.append({
                'bone':      bone,
                'bone_name': get_bone_exportname(bone),
                'group':     getattr(obj.vs, 'smd_hitbox_group', 0),
                'min':       bounds[0],
                'max':       bounds[1],
            })

        if not hitbox_data:
            self.report({'WARNING'}, "No hitboxes found")
            return None, None

        sorted_bones = sort_bone_by_hierarchy([hb['bone'] for hb in hitbox_data])
        bone_to_hb = {hb['bone']: hb for hb in hitbox_data}

        lines = []
        for bone in sorted_bones:
            hb = bone_to_hb[bone]
            lines.append(f'$hbox\t{hb["group"]}\t"{hb["bone_name"]}"\t\t{hb["min"].x:.2f}\t{hb["min"].y:.2f}\t{hb["min"].z:.2f}\t{hb["max"].x:.2f}\t{hb["max"].y:.2f}\t{hb["max"].z:.2f}')

        warnings = [f"{n} has rotation (ignored in Source 1 hitboxes)" for n in rotated] if rotated else None
        return '\n'.join(lines), warnings

    def _hitbox_bounds(self, obj, arm):
        half = mathutils.Vector((obj.empty_display_size * obj.scale.x, obj.empty_display_size * obj.scale.y, obj.empty_display_size * obj.scale.z))
        world_loc = obj.matrix_world.translation

        if obj.parent and obj.parent.type == 'ARMATURE' and obj.parent_bone:
            pose_bone = arm.pose.bones[obj.parent_bone]
            base_mat = arm.matrix_world @ pose_bone.bone.matrix_local
            local_loc = base_mat.inverted() @ world_loc
            offset = pose_bone.bone.matrix_local.inverted() @ get_bone_matrix(pose_bone, rest_space=True)
            local_loc = offset.inverted() @ local_loc
            half = offset.inverted().to_3x3() @ half
        else:
            local_loc = obj.location

        c1, c2 = local_loc - half, local_loc + half
        return (
            mathutils.Vector((min(c1.x, c2.x), min(c1.y, c2.y), min(c1.z, c2.z))),
            mathutils.Vector((max(c1.x, c2.x), max(c1.y, c2.y), max(c1.z, c2.z))),
        )