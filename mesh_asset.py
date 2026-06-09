"""
Mesh asset decoder for Second Life / Firestorm mesh cache files.

File format (sl_cache_<UUID>_0.asset):
  [0:4]   version      LE uint32, always 1
  [4:8]   header_size  LE uint32, byte length of the LLSD header section
  [8:12]  section_count LE uint32 (number of data sections)
  [12:]   LLSD binary header — map of LOD names to {offset, size}
  [12+header_size:]  zlib-compressed mesh data sections

Each decompressed section is LLSD binary — an array of face maps:
  PositionDomain: {Min:[x,y,z], Max:[x,y,z]}
  Position:       binary, uint16 LE * 3 * num_verts (quantised)
  Normal:         binary, uint16 LE * 3 * num_verts (optional)
  TexCoord0Domain:{Min:[u,v], Max:[u,v]}  (optional)
  TexCoord0:      binary, uint16 LE * 2 * num_verts (optional)
  TriangleList:   binary, uint16 LE * num_indices

Skin section (key "skin") contains an LLSD map with joint names, bind shape,
inverse bind matrices, and per-vertex weights.

Usage:
  python mesh_asset.py decode <asset_file> [--lod high|medium|low|lowest]
  python mesh_asset.py info   <asset_file>
"""

import argparse
import json
import os
import struct
import zlib

import llsd_binary


LOD_NAMES = ["high_lod", "medium_lod", "low_lod", "lowest_lod"]


# ---------------------------------------------------------------------------
# File-level parsing
# ---------------------------------------------------------------------------

def read_file_header(data):
    if len(data) < 12:
        raise ValueError("file too short to contain mesh asset header")
    version, header_size, section_count = struct.unpack_from('<III', data, 0)
    if version != 1:
        raise ValueError(f"unsupported mesh asset version {version}")
    return version, header_size, section_count


def load_asset(path):
    with open(path, 'rb') as f:
        data = f.read()
    version, header_size, section_count = read_file_header(data)
    header_bytes = data[12:12 + header_size]
    header = llsd_binary.parse(header_bytes)
    data_start = 12 + header_size
    return data, header, data_start


def get_section_data(data, header, data_start, section_name):
    if section_name not in header:
        return None
    info = header[section_name]
    offset = info["offset"]
    size = info["size"]
    if size == 0:
        return None
    compressed = data[data_start + offset: data_start + offset + size]
    # Newer Firestorm versions pre-allocate section space filled with zeros for
    # sections not yet downloaded from the CDN.  Detect and skip them.
    if not compressed or compressed[0] == 0:
        return None
    # Use decompressobj — Firestorm omits the zlib adler32 footer so zlib.decompress() rejects it
    return zlib.decompressobj().decompress(compressed)


# ---------------------------------------------------------------------------
# Geometry decoding
# ---------------------------------------------------------------------------

def _dequant16(raw_bytes, domain_min, domain_range, components):
    """Dequantise a block of uint16 LE values into floats using the given domain."""
    count = len(raw_bytes) // (2 * components)
    result = []
    pos = 0
    for _ in range(count):
        vertex = []
        for c in range(components):
            u = struct.unpack_from('<H', raw_bytes, pos)[0]
            pos += 2
            vertex.append(domain_min[c] + (u / 65535.0) * domain_range[c])
        result.append(vertex)
    return result


def decode_face(face):
    """Decode one face map from the decompressed LOD LLSD.
    Returns None if the face is incomplete (e.g. not fully cached)."""
    if face.get('__incomplete__') or 'PositionDomain' not in face or 'TriangleList' not in face:
        return None

    result = {}

    # Positions (required)
    pd = face["PositionDomain"]
    mn = pd["Min"]
    mx = pd["Max"]
    rng = [mx[i] - mn[i] for i in range(3)]
    result["positions"] = _dequant16(face["Position"], mn, rng, 3)

    # Normals (optional)
    if "Normal" in face:
        nm_min = [-1.0, -1.0, -1.0]
        nm_rng = [2.0, 2.0, 2.0]
        result["normals"] = _dequant16(face["Normal"], nm_min, nm_rng, 3)

    # UVs (optional)
    if "TexCoord0" in face and "TexCoord0Domain" in face:
        td = face["TexCoord0Domain"]
        tc_min = td["Min"]
        tc_max = td["Max"]
        tc_rng = [tc_max[i] - tc_min[i] for i in range(2)]
        result["uvs"] = _dequant16(face["TexCoord0"], tc_min, tc_rng, 2)

    # Triangle indices
    idx_raw = face["TriangleList"]
    count = len(idx_raw) // 2
    result["indices"] = [struct.unpack_from('<H', idx_raw, i*2)[0] for i in range(count)]

    return result


def decode_lod(decompressed):
    """Decode a decompressed LOD section into a list of face geometry dicts."""
    faces_llsd = llsd_binary.parse(decompressed)
    if not isinstance(faces_llsd, list):
        raise ValueError("expected LLSD array at top level of decompressed LOD section")
    decoded = [decode_face(f) for f in faces_llsd]
    return [f for f in decoded if f is not None]


# ---------------------------------------------------------------------------
# Skin / weights decoding
# ---------------------------------------------------------------------------

def decode_skin(decompressed):
    """Return the raw skin LLSD dict (joint names, bind shape, weights)."""
    return llsd_binary.parse(decompressed)


# ---------------------------------------------------------------------------
# OBJ export
# ---------------------------------------------------------------------------

def export_obj(faces, out_path, name="mesh"):
    vert_offset = 1
    uv_offset = 1
    norm_offset = 1

    with open(out_path, 'w') as f:
        f.write(f"# Exported by mesh_asset.py\n")
        f.write(f"o {name}\n\n")

        for face_idx, face in enumerate(faces):
            positions = face["positions"]
            normals = face.get("normals", [])
            uvs = face.get("uvs", [])
            indices = face["indices"]

            f.write(f"# face {face_idx}  verts={len(positions)}\n")

            for v in positions:
                f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
            for vn in normals:
                f.write(f"vn {vn[0]:.6f} {vn[1]:.6f} {vn[2]:.6f}\n")
            for vt in uvs:
                f.write(f"vt {vt[0]:.6f} {vt[1]:.6f}\n")

            f.write(f"g face_{face_idx}\n")

            has_uv = len(uvs) > 0
            has_norm = len(normals) > 0

            for tri in range(0, len(indices), 3):
                a, b, c = [indices[tri+k] for k in range(3)]
                def fmt(i):
                    vi = i + vert_offset
                    if has_uv and has_norm:
                        return f"{vi}/{i + uv_offset}/{i + norm_offset}"
                    elif has_uv:
                        return f"{vi}/{i + uv_offset}"
                    elif has_norm:
                        return f"{vi}//{i + norm_offset}"
                    return str(vi)
                f.write(f"f {fmt(a)} {fmt(b)} {fmt(c)}\n")

            vert_offset += len(positions)
            uv_offset += len(uvs)
            norm_offset += len(normals)


# ---------------------------------------------------------------------------
# Weights JSON export
# ---------------------------------------------------------------------------

def export_weights(skin, out_path):
    """Write skin data as JSON. Converts any bytes values to base64 for JSON compat."""
    import base64

    def prep(obj):
        if isinstance(obj, bytes):
            return {"__bytes__": base64.b64encode(obj).decode()}
        if isinstance(obj, dict):
            return {k: prep(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [prep(v) for v in obj]
        return obj

    with open(out_path, 'w') as f:
        json.dump(prep(skin), f, indent=2, default=str)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_info(args):
    data, header, data_start = load_asset(args.file)
    version, header_size, section_count = read_file_header(data)
    print(f"File:          {args.file}")
    print(f"File size:     {len(data)} bytes")
    print(f"Version:       {version}")
    print(f"Header size:   {header_size} bytes")
    print(f"Data offset:   {data_start}")
    print()
    for key, val in sorted(header.items()):
        if isinstance(val, dict) and "offset" in val:
            print(f"  {key:<25}  offset={val['offset']:#8x}  size={val['size']:#8x} ({val['size']} bytes)")
        else:
            print(f"  {key:<25}  {val}")


def cmd_decode(args):
    data, header, data_start = load_asset(args.file)
    lod = args.lod + "_lod" if not args.lod.endswith("_lod") else args.lod

    raw = get_section_data(data, header, data_start, lod)
    if raw is None:
        print(f"LOD section '{lod}' not found in asset.")
        return

    faces = decode_lod(raw)
    total_verts = sum(len(f["positions"]) for f in faces)
    total_tris = sum(len(f["indices"]) // 3 for f in faces)
    if len(faces) == 0:
        print(f"LOD: {lod}  — no complete faces found (LOD may be incomplete in cache)")
        print("Tip: try a lower LOD with --lod medium / --lod low / --lod lowest")
        return
    print(f"LOD: {lod}  faces={len(faces)}  verts={total_verts}  tris={total_tris}")

    stem = os.path.splitext(args.file)[0]
    obj_path = f"{stem}_{lod}.obj"
    export_obj(faces, obj_path, name=os.path.basename(stem))
    print(f"OBJ written: {obj_path}")

    # Skin/weights
    if "skin" in header:
        skin_raw = get_section_data(data, header, data_start, "skin")
        if skin_raw:
            skin = decode_skin(skin_raw)
            weights_path = f"{stem}_skin.json"
            export_weights(skin, weights_path)
            print(f"Skin written: {weights_path}")


def main():
    parser = argparse.ArgumentParser(description="Decode SL/Firestorm mesh asset files")
    sub = parser.add_subparsers(dest="command", required=True)

    p_info = sub.add_parser("info", help="Show asset header and section list")
    p_info.add_argument("file")

    p_dec = sub.add_parser("decode", help="Decode a LOD and export OBJ + skin.json")
    p_dec.add_argument("file")
    p_dec.add_argument("--lod", default="high", choices=["high", "medium", "low", "lowest"],
                       help="Which LOD to export (default: high)")

    args = parser.parse_args()

    if args.command == "info":
        cmd_info(args)
    elif args.command == "decode":
        cmd_decode(args)


if __name__ == "__main__":
    main()
