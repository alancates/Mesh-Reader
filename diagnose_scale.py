"""
Print PositionDomain, NormalizedScale, and bind_shape_matrix for each face
of the main body mesh to understand the full transform chain.
"""
import struct, zlib, sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
import llsd_binary

ASSETS = {
    "d61974b2 (Body Upper Base)": r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\d\sl_cache_d61974b2-5932-18ae-3185-fa301f5ff9c6_0.asset",
    "2fbb9764 (Body Lower)":      r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\2\sl_cache_2fbb9764-369f-dd20-3f25-bf949cb2073f_0.asset",
    "0d9cb017 (LaraX main body)": r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\0\sl_cache_0d9cb017-XXXX_0.asset",  # placeholder
}

def load(path):
    with open(path, 'rb') as f: data = f.read()
    v, hs, sc = struct.unpack_from('<III', data, 0)
    header = llsd_binary.parse(data[12:12+hs])
    ds = 12 + hs
    info = header["high_lod"]
    comp = data[ds+info["offset"]:ds+info["offset"]+info["size"]]
    return llsd_binary.parse(zlib.decompressobj().decompress(comp)), header

def show_matrix(label, m):
    if not m or len(m) != 16: print(f"  {label}: missing"); return
    print(f"  {label}:")
    print(f"    Scale  X={m[0]:.6f}  Y={m[5]:.6f}  Z={m[10]:.6f}")
    print(f"    Trans  X={m[12]:.6f}  Y={m[13]:.6f}  Z={m[14]:.6f}")

for label, path in ASSETS.items():
    if "XXXX" in path:
        continue
    print(f"\n{'='*60}")
    print(f"{label}")
    try:
        faces, header = load(path)
    except Exception as e:
        print(f"  ERROR: {e}"); continue

    # Skin section bind_shape_matrix
    with open(path, 'rb') as f: data = f.read()
    v, hs, sc = struct.unpack_from('<III', data, 0)
    hdr = llsd_binary.parse(data[12:12+hs])
    ds = 12 + hs
    if "skin" in hdr:
        si = hdr["skin"]
        sc2 = data[ds+si["offset"]:ds+si["offset"]+si["size"]]
        if sc2 and sc2[0] != 0:
            skin = llsd_binary.parse(zlib.decompressobj().decompress(sc2))
            bsm = skin.get("bind_shape_matrix")
            show_matrix("bind_shape_matrix", bsm)

    for i, face in enumerate(faces):
        pd = face.get("PositionDomain", {})
        mn = pd.get("Min", [])
        mx = pd.get("Max", [])
        ns = face.get("NormalizedScale")
        nverts = len(face.get("Position", b"")) // 6
        print(f"\n  Face {i}  ({nverts} verts)")
        if mn and mx:
            print(f"    PositionDomain Min: {[round(v,4) for v in mn]}")
            print(f"    PositionDomain Max: {[round(v,4) for v in mx]}")
            size = [mx[j]-mn[j] for j in range(3)]
            print(f"    Domain size (extent): {[round(s,4) for s in size]}")
        if ns is not None:
            print(f"    NormalizedScale: {ns}")
        else:
            print(f"    NormalizedScale: (not present)")
