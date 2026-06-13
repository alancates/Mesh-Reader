import bpy

KEEP = lambda name: (
    name.lower() == "body" or
    "feet" in name.lower() or
    "foot" in name.lower()
)

to_delete = [o for o in bpy.data.objects if not KEEP(o.name)]
print(f"Deleting {len(to_delete)} objects:")
for o in to_delete:
    print(f"  {o.name}")
    bpy.data.objects.remove(o, do_unlink=True)

bpy.ops.outliner.orphans_purge(do_recursive=True)
bpy.ops.wm.save_mainfile()
print("Done. Remaining objects:")
for o in bpy.data.objects:
    print(f"  {o.name}")
