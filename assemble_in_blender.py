"""
assemble_in_blender.py  (Blender internal script)

Run via:
  blender-launcher.exe --background --python assemble_in_blender.py

Imports all OBJ files from OBJ_DIR, applies each mesh's bind_shape_matrix
from its _skin.json to fix scale and world position, then saves assembled.blend.
"""

import bpy
import os
import glob
import json
import math
from mathutils import Matrix

OBJ_DIR  = r"J:\Claude Data\Mesh-Reader\exports\naked_body"
OUT_FILE = os.path.join(OBJ_DIR, "assembled.blend")

# Known part labels (UUID prefix -> description).
# Uncertain IDs marked with '?' are left as-is for now.
LABELS = {
    "2fbb9764": "Body lower",
    "38875df5": "Breast L?",
    "3aac1021": "Feet flat",
    "3d02e3b7": "Feet",
    "15f2e8a3": "Feet / Hand?",
    "70a508dc": "Body Upper",
    "6b1f80c4": "Nipple",
    "83bf5228": "Body Upper",
    "7f453051": "Body lower",
    "7c618493": "Hand?",
    "a867fbf4": "Breast L?",
    "ab859d96": "Nails",
    "d61974b2": "Body Upper",
    "e623b5ff": "Feet",
    "dd2d450c": "Foot left",
    "b365df00": "Feet flat+1",
    "ee61bfb4": "Nipple",
    "a00efe25": "Nails",
    "a2ff160c": "Body Upper",
    "77d4551a": "Breast L?",
    "0d9cb017": "Maitreya LaraX main body",
}


def bind_matrix_from_skin(skin_path):
    """Read bind_shape_matrix (column-major 16 floats) and return a Blender Matrix."""
    with open(skin_path) as f:
        data = json.load(f)
    m = data.get("bind_shape_matrix")
    if not m or len(m) != 16:
        return None
    # Column-major -> row-major for Blender
    return Matrix([
        [m[0],  m[4],  m[8],  m[12]],
        [m[1],  m[5],  m[9],  m[13]],
        [m[2],  m[6],  m[10], m[14]],
        [m[3],  m[7],  m[11], m[15]],
    ])


# ── Main ──────────────────────────────────────────────────────────────────────

bpy.ops.wm.read_factory_settings(use_empty=True)

obj_files = sorted(glob.glob(os.path.join(OBJ_DIR, "*.obj")))
print(f"\nFound {len(obj_files)} OBJ files\n")

for path in obj_files:
    stem = os.path.splitext(os.path.basename(path))[0]   # e.g. 2fbb9764_high_lod
    uuid = stem.split("_")[0]                              # e.g. 2fbb9764
    skin_path = os.path.join(OBJ_DIR, f"{uuid}_skin.json")
    label = LABELS.get(uuid, "")
    display_name = f"{uuid} {label}".strip() if label else uuid

    print(f"  Importing: {display_name}")
    bpy.ops.wm.obj_import(
        filepath=path,
        forward_axis='NEGATIVE_Z',
        up_axis='Y',
    )

    mat = bind_matrix_from_skin(skin_path) if os.path.exists(skin_path) else None

    for obj in bpy.context.selected_objects:
        obj.name = display_name
        if mat:
            # Apply bind_shape_matrix as the object's world transform.
            # This corrects both scale and position in one step.
            obj.matrix_world = mat

print(f"\nSaving to: {OUT_FILE}")
bpy.ops.wm.save_as_mainfile(filepath=OUT_FILE)
print("Done.")
