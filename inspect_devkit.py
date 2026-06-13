import bpy, mathutils

print("\n=== DEV KIT OBJECTS ===")
for obj in bpy.data.objects:
    if obj.type != 'MESH': continue
    me = obj.data
    if len(me.vertices) < 100: continue
    # World bounding box
    bb = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
    min_x = min(v.x for v in bb); max_x = max(v.x for v in bb)
    min_y = min(v.y for v in bb); max_y = max(v.y for v in bb)
    min_z = min(v.z for v in bb); max_z = max(v.z for v in bb)
    vg_names = [vg.name for vg in obj.vertex_groups][:6]
    print(f"{obj.name:40s}  v={len(me.vertices):7,}  Z={min_z:.3f}..{max_z:.3f}  X={min_x:.3f}..{max_x:.3f}  Y={min_y:.3f}..{max_y:.3f}  groups={len(obj.vertex_groups)}  [{','.join(vg_names)}...]")
