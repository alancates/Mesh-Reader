"""
import_to_blender.py  (Blender internal script)

Run via:
  blender-launcher.exe --background --python import_to_blender.py

Imports all OBJ files from OBJ_DIR into a single .blend file, laying each
mesh out in a grid across the X-Y plane so nothing overlaps.
"""

import bpy
import os
import glob
import math

OBJ_DIR   = r"J:\Claude Data\Mesh-Reader\exports\naked_body"
OUT_FILE  = os.path.join(OBJ_DIR, "naked_body.blend")
SPACING   = 3.0   # metres between grid cells (increase if meshes still overlap)

# Clear the default scene
bpy.ops.wm.read_factory_settings(use_empty=True)

obj_files = sorted(glob.glob(os.path.join(OBJ_DIR, "*.obj")))
print(f"\nFound {len(obj_files)} OBJ files to import\n")

cols = max(1, math.ceil(math.sqrt(len(obj_files))))

for idx, path in enumerate(obj_files):
    name = os.path.splitext(os.path.basename(path))[0]
    print(f"  Importing: {name}")
    bpy.ops.wm.obj_import(
        filepath=path,
        forward_axis='NEGATIVE_Z',
        up_axis='Y',
    )

    col = idx % cols
    row = idx // cols
    x_offset = col * SPACING
    y_offset = row * SPACING

    for obj in bpy.context.selected_objects:
        obj.name = name
        obj.location.x += x_offset
        obj.location.y += y_offset

print(f"\nSaving to: {OUT_FILE}")
bpy.ops.wm.save_as_mainfile(filepath=OUT_FILE)
print("Done.")
