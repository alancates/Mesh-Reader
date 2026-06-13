"""
cleanup_assemble.py  (run inside Blender via Scripting workspace)

- Deletes all hidden objects
- Joins body upper, lower, and breasts into one mesh named "Body"
- Keeps feet and vagina as separate objects
- Saves as assembled_basic.blend alongside assembled.blend
"""

import bpy
import os

JOIN_NAMES = {
    "d61974b2 Body Upper Base",
    "7f453051 Body lower",
    "38875df5 Breast L",
    "a867fbf4 Breast R",
}

# ── 1. Delete hidden objects ──────────────────────────────────────────────────
hidden = [o for o in bpy.context.scene.objects if o.hide_viewport]
print(f"Deleting {len(hidden)} hidden objects...")
bpy.ops.object.select_all(action='DESELECT')
for obj in hidden:
    obj.hide_viewport = False
    obj.select_set(True)
bpy.ops.object.delete()

# ── 2. Join body parts ────────────────────────────────────────────────────────
bpy.ops.object.select_all(action='DESELECT')

join_objects = [o for o in bpy.context.scene.objects if o.name in JOIN_NAMES]
missing = JOIN_NAMES - {o.name for o in join_objects}
if missing:
    print(f"WARNING: could not find: {missing}")

print(f"Joining {len(join_objects)} objects into 'Body'...")
for obj in join_objects:
    obj.select_set(True)

if join_objects:
    bpy.context.view_layer.objects.active = join_objects[0]
    bpy.ops.object.join()
    bpy.context.active_object.name = "Body"

# ── 3. Apply transforms on all remaining objects ──────────────────────────────
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.ops.object.select_all(action='DESELECT')

# ── 4. Save as assembled_basic.blend ─────────────────────────────────────────
current = bpy.data.filepath
out_file = os.path.join(os.path.dirname(current), "assembled_basic.blend")
print(f"Saving to: {out_file}")
bpy.ops.wm.save_as_mainfile(filepath=out_file, copy=True)
print("Done.")
