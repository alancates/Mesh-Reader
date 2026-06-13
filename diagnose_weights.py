"""
Inspect the raw Weights blob from a mesh asset face to determine the encoding.
"""
import struct
import zlib
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
import llsd_binary

path = r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\d\sl_cache_d61974b2-5932-18ae-3185-fa301f5ff9c6_0.asset"

with open(path, 'rb') as f:
    data = f.read()

version, header_size, section_count = struct.unpack_from('<III', data, 0)
header = llsd_binary.parse(data[12:12 + header_size])
data_start = 12 + header_size

info = header["high_lod"]
compressed = data[data_start + info["offset"]: data_start + info["offset"] + info["size"]]
raw = zlib.decompressobj().decompress(compressed)
faces = llsd_binary.parse(raw)

face = faces[0]
w = face["Weights"]
num_verts = len(face["Position"]) // 6  # 3 components * 2 bytes each

print(f"Num verts (face 0): {num_verts}")
print(f"Weights blob size:  {len(w)} bytes")
print(f"Ratio bytes/vert:   {len(w)/num_verts:.3f}")
print()

# Show first 80 bytes as hex and as float32
print("First 80 bytes (hex):")
print(" ".join(f"{b:02x}" for b in w[:80]))
print()
print("First 20 float32 values:")
for i in range(20):
    val = struct.unpack_from('<f', w, i*4)[0]
    joint = int(val)
    frac = val - joint
    print(f"  [{i:2d}]  raw={val:.6f}  joint={joint}  frac={frac:.6f}  weight~={frac*255:.1f}/255")
print()

# Check if it could be U8 per influence with a different packing
print("First 80 bytes as uint8:")
print([b for b in w[:80]])
