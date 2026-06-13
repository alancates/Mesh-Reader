"""
apply_weights_legacy.py  (Blender internal script)

Imports Legacy body parts extracted from Firestorm cache,
applies bind_shape_matrix + vertex weights, saves legacy_body.blend.
"""

import bpy
import json
import os
from mathutils import Matrix

OUT_FILE = r"J:\Claude Data\Mesh-Reader\exports\legacy\legacy_body.blend"

CACHE = r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache"

PARTS = [
    # (display_name, asset_uuid_prefix, subdir)
    ("Body Base A",    "9dbb65e1-5451-c975-7930-b6383ca15e1c", "9"),
    ("Body Base B",    "0d2d4a1b-7801-5bc4-37d4-4487d49eefbb", "0"),
    ("Body Upper",     "a2a889c4-0d5a-be3f-61c4-d1def17aafc0", "a"),
    ("Body Lower",     "5c47e563-2274-9875-b550-2e5e6bff68ab", "5"),
    ("Torso A",        "f500900f-2cba-ac66-0d2b-6f2989477128", "f"),
    ("Torso B",        "3fa38e76-53d8-1d13-4efc-741b4104f3fc", "3"),
    ("Legs",           "16f1226d-3300-17ac-b26d-faaca1953e23", "1"),
    ("Mid Body",       "94c0195a-4c38-1033-99c4-da2149d788a8", "9"),
    ("Body C",         "bc14f1b3-24d8-c0ff-76df-2b8c21f310b5", "b"),
    ("Extremities",    "72236dc8-8a73-b277-8794-e77b9205c433", "7"),
    ("Arms",           "328d3cc3-274b-b6a6-4532-9ad113228b83", "3"),
    ("Body D",         "e79eba2a-911b-46e8-54c3-d89c5947b9bc", "e"),
]

def make_paths(uuid, subdir):
    stem = f"sl_cache_{uuid}_0"
    base = os.path.join(CACHE, subdir, stem)
    return base + "_high_lod.obj", base + "_skin.json"

def load_skin(skin_path):
    with open(skin_path) as f:
        return json.load(f)

def bind_matrix(skin):
    m = skin.get("bind_shape_matrix")
    if not m or len(m) != 16:
        return None
    M = Matrix([
        [m[0],  m[4],  m[8],  m[12]],
        [m[1],  m[5],  m[9],  m[13]],
        [m[2],  m[6],  m[10], m[14]],
        [m[3],  m[7],  m[11], m[15]],
    ])
    # SL avatar-local: X=forward, Y=right, Z=up.
    # Rotate -90° around Z: avatar faces Blender -Y (toward viewer in front view).
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
        return
    vertex_weights = [v for face in raw for v in face]
    mesh = obj.data
    used = set()
    for influences in vertex_weights:
        for ji, _ in influences:
            used.add(ji)
    groups = {}
    for ji in used:
        if ji < len(joint_names):
            name = joint_names[ji]
            vg = obj.vertex_groups.get(name) or obj.vertex_groups.new(name=name)
            groups[ji] = vg
    if len(vertex_weights) != len(mesh.vertices):
        print(f"  WARNING: vert count mismatch {len(vertex_weights)} vs {len(mesh.vertices)}")
        return
    for vi, influences in enumerate(vertex_weights):
        for ji, weight in influences:
            if ji in groups:
                groups[ji].add([vi], weight, 'REPLACE')
    print(f"  Weights: {len(mesh.vertices)} verts, {len(groups)} groups")

# ── Main ──────────────────────────────────────────────────────────────────────

os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)

for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
for mesh in list(bpy.data.meshes):
    bpy.data.meshes.remove(mesh)

for display_name, uuid, subdir in PARTS:
    obj_path, skin_path = make_paths(uuid, subdir)
    print(f"\n=== {display_name} ({uuid[:8]}) ===")

    if not os.path.exists(obj_path):
        print(f"  SKIP: OBJ not found: {obj_path}")
        continue
    if not os.path.exists(skin_path):
        print(f"  SKIP: skin not found: {skin_path}")
        continue

    skin = load_skin(skin_path)
    mat = bind_matrix(skin)

    before = set(bpy.data.objects.keys())
    bpy.ops.wm.obj_import(filepath=obj_path, forward_axis='Y', up_axis='Z')
    new_objs = [bpy.data.objects[n] for n in bpy.data.objects.keys() if n not in before]

    if not new_objs:
        print(f"  ERROR: no objects imported")
        continue

    new_objs.sort(key=lambda o: o.name)
    bpy.ops.object.select_all(action='DESELECT')
    for o in new_objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = new_objs[0]
    if len(new_objs) > 1:
        print(f"  Joining {len(new_objs)} sub-objects")
        bpy.ops.object.join()

    obj = bpy.context.active_object
    obj.name = display_name

    if mat:
        obj.matrix_world = mat

    apply_weights(obj, skin)

print(f"\nSaving to: {OUT_FILE}")
bpy.ops.wm.save_as_mainfile(filepath=OUT_FILE)
print("Done.")
