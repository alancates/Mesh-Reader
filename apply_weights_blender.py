"""
apply_weights_blender.py  (Blender internal script)

Run via Scripting workspace in Blender.

For each body part:
  - Imports the OBJ (may create multiple objects for multi-face meshes)
  - Joins sub-objects in face order to preserve vertex ordering
  - Applies bind_shape_matrix (scale + position)
  - Creates vertex groups from joint_names and assigns weights
  - Names the object correctly

Saves result as weighted_parts.blend — do NOT join yet,
keep parts separate so weights are clean before merging.
"""

import bpy
import json
import os
from mathutils import Matrix

OUT_FILE = r"J:\Claude Data\Mesh-Reader\exports\naked_body\weighted_parts.blend"

# Each entry: (display_name, obj_path, skin_json_path)
PARTS = [
    (
        "Body Upper Base",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\d\sl_cache_d61974b2-5932-18ae-3185-fa301f5ff9c6_0_high_lod.obj",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\d\sl_cache_d61974b2-5932-18ae-3185-fa301f5ff9c6_0_skin.json",
    ),
    (
        "Body Lower",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\2\sl_cache_2fbb9764-369f-dd20-3f25-bf949cb2073f_0_high_lod.obj",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\2\sl_cache_2fbb9764-369f-dd20-3f25-bf949cb2073f_0_skin.json",
    ),
    (
        "Body Lower 2",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\7\sl_cache_7f453051-f698-e170-8df5-cfa8be02a451_0_high_lod.obj",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\7\sl_cache_7f453051-f698-e170-8df5-cfa8be02a451_0_skin.json",
    ),
    (
        "Breast L",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\3\sl_cache_38875df5-2ec6-3fc9-ca90-2b6015310ce9_0_high_lod.obj",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\3\sl_cache_38875df5-2ec6-3fc9-ca90-2b6015310ce9_0_skin.json",
    ),
    (
        "Breast R",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\a\sl_cache_a867fbf4-b463-3df8-fd26-9547150eb780_0_high_lod.obj",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\a\sl_cache_a867fbf4-b463-3df8-fd26-9547150eb780_0_skin.json",
    ),
    (
        "Feet Flat",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\3\sl_cache_3aac1021-aec5-5fc8-319b-f12aa30829f5_0_high_lod.obj",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\3\sl_cache_3aac1021-aec5-5fc8-319b-f12aa30829f5_0_skin.json",
    ),
    (
        "Feet TipToe",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\3\sl_cache_3d02e3b7-d67d-a831-c970-ffd9ba3d24c2_0_high_lod.obj",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\3\sl_cache_3d02e3b7-d67d-a831-c970-ffd9ba3d24c2_0_skin.json",
    ),
    (
        "Foot L Curl",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\7\sl_cache_7c618493-016f-934e-876e-8371e1dff9a4_0_high_lod.obj",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\7\sl_cache_7c618493-016f-934e-876e-8371e1dff9a4_0_skin.json",
    ),
    (
        "Feet F2",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\e\sl_cache_e623b5ff-0ee6-ac4f-2a19-3e158dba52c9_0_high_lod.obj",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\e\sl_cache_e623b5ff-0ee6-ac4f-2a19-3e158dba52c9_0_skin.json",
    ),
    (
        "Foot Left TipToe",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\d\sl_cache_dd2d450c-65fd-b5e4-1176-084db67556a4_0_high_lod.obj",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\d\sl_cache_dd2d450c-65fd-b5e4-1176-084db67556a4_0_skin.json",
    ),
    (
        "Feet Flat+1",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\b\sl_cache_b365df00-3ee1-b87d-5f5f-eadb1c292b7f_0_high_lod.obj",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\b\sl_cache_b365df00-3ee1-b87d-5f5f-eadb1c292b7f_0_skin.json",
    ),
    (
        "Foot L Curved",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\8\sl_cache_8f0fb98e-2644-6d66-0ac5-e8339739fb7c_0_high_lod.obj",
        r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\8\sl_cache_8f0fb98e-2644-6d66-0ac5-e8339739fb7c_0_skin.json",
    ),
]


def load_skin(skin_path):
    with open(skin_path) as f:
        return json.load(f)


def bind_matrix(skin):
    m = skin.get("bind_shape_matrix")
    if not m or len(m) != 16:
        return None
    # Column-major stored → Blender row-major Matrix.
    M = Matrix([
        [m[0],  m[4],  m[8],  m[12]],
        [m[1],  m[5],  m[9],  m[13]],
        [m[2],  m[6],  m[10], m[14]],
        [m[3],  m[7],  m[11], m[15]],
    ])
    # SL avatar-local axes: X=forward (avatar faces +X), Y=right (arm span), Z=up.
    # OBJ imported with up_axis='Z'/forward_axis='Y' keeps these axes as-is.
    # Avastar expects the avatar facing -Y (toward viewer in Blender front view).
    # Apply -90° around Z: local +X (SL forward) → Blender -Y (toward viewer).
    R = Matrix([
        [ 0, 1, 0, 0],
        [-1, 0, 0, 0],
        [ 0, 0, 1, 0],
        [ 0, 0, 0, 1],
    ])
    return R @ M


def apply_weights(obj, skin):
    joint_names = skin.get("joint_names", [])
    raw = skin.get("vertex_weights")
    if not raw:
        print(f"  WARNING: no vertex_weights in skin for {obj.name}")
        return
    # vertex_weights is a list-of-faces; flatten to a single per-vertex list
    vertex_weights = [v for face in raw for v in face]

    mesh = obj.data

    # Create a vertex group per joint (only joints actually used)
    used_joints = set()
    for influences in vertex_weights:
        for joint_idx, _ in influences:
            used_joints.add(joint_idx)

    groups = {}
    for ji in used_joints:
        if ji < len(joint_names):
            name = joint_names[ji]
            vg = obj.vertex_groups.get(name) or obj.vertex_groups.new(name=name)
            groups[ji] = vg

    # Assign weights — vertex index in the mesh must match vertex_weights index
    if len(vertex_weights) != len(mesh.vertices):
        print(f"  WARNING: vertex count mismatch — "
              f"skin has {len(vertex_weights)}, mesh has {len(mesh.vertices)}")
        return

    for vi, influences in enumerate(vertex_weights):
        for joint_idx, weight in influences:
            if joint_idx in groups:
                groups[joint_idx].add([vi], weight, 'REPLACE')

    print(f"  Weights applied: {len(mesh.vertices)} verts, "
          f"{len(groups)} joint groups")


# ── Main ──────────────────────────────────────────────────────────────────────

# Clear scene without triggering addon load handlers
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
for mesh in list(bpy.data.meshes):
    bpy.data.meshes.remove(mesh)

for display_name, obj_path, skin_path in PARTS:
    print(f"\n=== {display_name} ===")

    skin = load_skin(skin_path)
    mat = bind_matrix(skin)

    before = set(bpy.data.objects.keys())
    bpy.ops.wm.obj_import(
        filepath=obj_path,
        forward_axis='Y',
        up_axis='Z',
    )
    new_objs = [bpy.data.objects[n] for n in bpy.data.objects.keys()
                if n not in before]

    if not new_objs:
        print(f"  ERROR: no objects imported")
        continue

    # Sort by name so face_0, face_1, face_2 are in order before joining
    new_objs.sort(key=lambda o: o.name)

    # Join multiple sub-objects into one (preserves vertex order face_0..N)
    bpy.ops.object.select_all(action='DESELECT')
    for o in new_objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = new_objs[0]
    if len(new_objs) > 1:
        print(f"  Joining {len(new_objs)} sub-objects")
        bpy.ops.object.join()

    obj = bpy.context.active_object
    obj.name = display_name

    # Apply bind_shape_matrix for correct scale and position
    if mat:
        obj.matrix_world = mat

    apply_weights(obj, skin)

print(f"\nSaving to: {OUT_FILE}")
bpy.ops.wm.save_as_mainfile(filepath=OUT_FILE)
print("Done.")
