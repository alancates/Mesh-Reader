"""
mesh_asset.py  --  SL/Firestorm mesh asset decoder and OBJ/JSON exporter.

Pipeline:
  1. Locate asset file:  cache/[UUID[0]]/sl_cache_[UUID]_0.asset
  2. Read 12-byte preamble  (version U32 + header_bytes U32 + flags U32)
  3. Parse LLSD binary mesh header  (not compressed)
  4. For each LOD: seek to offset, zlib-decompress, parse LLSD face array
  5. For skin block: seek to offset, zlib-decompress, parse LLSD skin info
  6. Decode binary geometry:
       Position  : N*3 U16-LE -> F32 via PositionDomain Min/Max
       Normal    : N*3 U16-LE -> F32 via (-1..1)
       TexCoord0 : N*2 U16-LE -> F32 via TexCoord0Domain Min/Max
       TriangleList: M*3 U16-LE indices
       Weights   : variable-length per-vertex (U8 bone_idx + U16 weight)*N + 0xFF terminator
  7. Export high_lod as OBJ + skin weights as JSON

Verified against:
  indra/llprimitive/llmodel.cpp   writeModel() / LLMeshSkinInfo::fromLLSD()
  indra/newview/llmeshrepository.cpp  write_preamble() / headerReceived()
  indra/llfilesystem/lldiskcache.cpp  metaDataToFilepath()
"""

from __future__ import annotations
import json, struct, zlib, sys
from pathlib import Path
from typing import Optional

# ── Constants ────────────────────────────────────────────────────────────────

CACHE_PREAMBLE_SIZE    = 12          # 3 x U32
CACHE_PREAMBLE_VERSION = 1

LOD_NAMES = ['lowest_lod', 'low_lod', 'medium_lod', 'high_lod']
LOD_HIGH  = 'high_lod'

# ── LLSD XML parser (minimal, for mesh headers) ──────────────────────────────

def _parse_llsd_xml(data: bytes):
    """Parse LLSD/XML to Python objects. Used for the mesh header block."""
    import xml.etree.ElementTree as ET

    def _parse_elem(e):
        tag = e.tag
        if tag == 'llsd':
            children = list(e)
            return _parse_elem(children[0]) if children else None
        if tag == 'map':
            result = {}
            children = list(e)
            for i in range(0, len(children) - 1, 2):
                key   = children[i].text or ''
                value = _parse_elem(children[i + 1])
                result[key] = value
            return result
        if tag == 'array':
            return [_parse_elem(c) for c in e]
        if tag == 'integer':  return int(e.text or 0)
        if tag == 'real':     return float(e.text or 0)
        if tag == 'string':   return e.text or ''
        if tag == 'boolean':  return (e.text or '').lower() in ('true', '1')
        if tag == 'uuid':     return e.text or ''
        if tag == 'binary':
            import base64
            return base64.b64decode(e.text or '')
        if tag == 'undef':    return None
        return e.text

    root = ET.fromstring(data.decode('utf-8', errors='replace'))
    return _parse_elem(root)


def _parse_llsd_binary(data: bytes, offset: int = 0):
    """Parse LLSD binary (from llsdserialize.cpp). Returns Python object."""
    import binascii

    class _P:
        __slots__ = ('d', 'p')
        def __init__(self, d, p): self.d = d; self.p = p

        def byte(self):
            b = self.d[self.p]; self.p += 1; return b

        def read(self, n):
            b = self.d[self.p:self.p+n]; self.p += n; return b

        def u32(self):
            v, = struct.unpack_from('>I', self.d, self.p); self.p += 4; return v

        def s32(self):
            v, = struct.unpack_from('>i', self.d, self.p); self.p += 4; return v

        def f64(self):
            v, = struct.unpack_from('>d', self.d, self.p); self.p += 8; return v

        def str_(self):
            n = self.u32()
            return self.read(n).decode('utf-8', errors='replace') if n else ''

        def uuid(self):
            b = self.read(16)
            h = binascii.hexlify(b).decode()
            return f'{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}'

        def value(self):
            c = chr(self.byte())
            if c == '{':
                count = self.u32()
                result = {}
                while True:
                    kc = chr(self.byte())
                    if kc == '}': break
                    if kc == 'k':   key = self.str_()
                    elif kc == 's': key = self.str_()
                    else: raise ValueError(f'Bad key type {kc!r} at {self.p-1}')
                    result[key] = self.value()
                return result
            if c == '[':
                count = self.u32()
                result = []
                while self.d[self.p:self.p+1] not in (b']', b''):
                    result.append(self.value())
                self.p += 1
                return result
            if c == '!': return None
            if c == '0': return False
            if c == '1': return True
            if c == 'i': return self.s32()
            if c == 'r': return self.f64()
            if c == 'u': return self.uuid()
            if c == 's': return self.str_()
            if c == 'b': n = self.u32(); return bytes(self.read(n))
            if c == 'd': return self.f64()
            if c == 'l': return self.str_()
            raise ValueError(f'Unknown LLSD type {c!r} at {self.p-1}')

    return _P(data, offset).value()


def _unzip_llsd(data: bytes) -> dict:
    """Decompress zlib block and parse as LLSD binary."""
    raw = zlib.decompress(data)
    return _parse_llsd_binary(raw)

# ── Preamble + header reader ─────────────────────────────────────────────────

def read_asset_file(path: Path) -> tuple[dict, bytes]:
    """
    Read a Firestorm mesh .asset file.
    Returns (mesh_header_llsd, full_file_bytes).

    File layout (llmeshrepository.cpp write_preamble + headerReceived):
      [0:4]   version     U32 LE  (= 1)
      [4:8]   header_bytes U32 LE (size of LLSD header block that follows)
      [8:12]  flags       U32 LE
      [12:12+header_bytes]  LLSD binary mesh header
      [12+header_bytes:]    LOD + skin data blocks (zlib compressed)
    """
    data = path.read_bytes()

    if len(data) < CACHE_PREAMBLE_SIZE:
        raise ValueError(f'File too small: {len(data)} bytes')

    version, header_bytes, flags = struct.unpack_from('<III', data, 0)

    if version != CACHE_PREAMBLE_VERSION:
        raise ValueError(f'Unknown preamble version {version}')

    header_start = CACHE_PREAMBLE_SIZE
    header_end   = header_start + header_bytes

    if header_end > len(data):
        raise ValueError('Header size exceeds file length')

    header_data = data[header_start:header_end]

    # The mesh header LLSD is NOT zlib-compressed; it's raw binary LLSD
    try:
        header = _parse_llsd_binary(header_data)
    except Exception:
        # Fallback: try XML (some older assets)
        try:
            header = _parse_llsd_xml(header_data)
        except Exception as e:
            raise ValueError(f'Failed to parse mesh header LLSD: {e}')

    return header, data


# ── Geometry decoder ─────────────────────────────────────────────────────────

def _u16_to_f32(val: int, lo: float, hi: float) -> float:
    """Decode a U16 normalised value to F32 within [lo, hi]."""
    return lo + (val / 65535.0) * (hi - lo)


def _decode_positions(blob: bytes, domain_min: list, domain_max: list) -> list:
    """Decode Position binary blob: N*3 U16-LE -> list of (x,y,z) F32 tuples."""
    n_verts = len(blob) // 6
    result = []
    for i in range(n_verts):
        off = i * 6
        x, y, z = struct.unpack_from('<HHH', blob, off)
        result.append((
            _u16_to_f32(x, domain_min[0], domain_max[0]),
            _u16_to_f32(y, domain_min[1], domain_max[1]),
            _u16_to_f32(z, domain_min[2], domain_max[2]),
        ))
    return result


def _decode_normals(blob: bytes) -> list:
    """Decode Normal binary blob: N*3 U16-LE -> list of (nx,ny,nz) F32 tuples.
    Encoding: val = (norm + 1) * 0.5 * 65535  =>  norm = val/65535*2 - 1
    """
    n_verts = len(blob) // 6
    result = []
    for i in range(n_verts):
        off = i * 6
        x, y, z = struct.unpack_from('<HHH', blob, off)
        result.append((
            x / 65535.0 * 2.0 - 1.0,
            y / 65535.0 * 2.0 - 1.0,
            z / 65535.0 * 2.0 - 1.0,
        ))
    return result


def _decode_texcoords(blob: bytes, tc_min: list, tc_max: list) -> list:
    """Decode TexCoord0 binary blob: N*2 U16-LE -> list of (u,v) F32 tuples."""
    n_verts = len(blob) // 4
    result = []
    for i in range(n_verts):
        off = i * 4
        u, v = struct.unpack_from('<HH', blob, off)
        result.append((
            _u16_to_f32(u, tc_min[0], tc_max[0]),
            _u16_to_f32(v, tc_min[1], tc_max[1]),
        ))
    return result


def _decode_indices(blob: bytes) -> list:
    """Decode TriangleList: M U16-LE -> list of ints. Group into triples for triangles."""
    count = len(blob) // 2
    return list(struct.unpack_from(f'<{count}H', blob))


def _decode_weights(blob: bytes, n_verts: int) -> list:
    """
    Decode Weights binary blob.
    Per vertex: repeated (U8 bone_idx, U16 weight_u16) until bone_idx == 0xFF.
    Returns list of dicts: [{bone_idx: weight_f32, ...}, ...]
    """
    result = []
    pos = 0
    for _ in range(n_verts):
        influences = {}
        while pos < len(blob):
            bone_idx = blob[pos];  pos += 1
            if bone_idx == 0xFF:
                break
            if pos + 2 > len(blob):
                break
            weight_u16, = struct.unpack_from('<H', blob, pos);  pos += 2
            influences[bone_idx] = weight_u16 / 65535.0
        result.append(influences)
    return result


def decode_face(face_llsd: dict) -> dict:
    """
    Decode one face (submesh) from LOD LLSD.
    Returns dict with keys: positions, normals, texcoords, indices, weights (optional).
    """
    if face_llsd.get('NoGeometry'):
        return None

    pos_min = face_llsd['PositionDomain']['Min']
    pos_max = face_llsd['PositionDomain']['Max']

    positions = _decode_positions(face_llsd['Position'], pos_min, pos_max)
    n_verts   = len(positions)

    normals   = _decode_normals(face_llsd['Normal'])   if 'Normal'    in face_llsd else []
    indices   = _decode_indices(face_llsd['TriangleList'])

    texcoords = []
    if 'TexCoord0' in face_llsd:
        tc_min = face_llsd['TexCoord0Domain']['Min']
        tc_max = face_llsd['TexCoord0Domain']['Max']
        texcoords = _decode_texcoords(face_llsd['TexCoord0'], tc_min, tc_max)

    weights = []
    if 'Weights' in face_llsd:
        weights = _decode_weights(face_llsd['Weights'], n_verts)

    return {
        'positions':  positions,
        'normals':    normals,
        'texcoords':  texcoords,
        'indices':    indices,
        'weights':    weights,
    }


def decode_skin(skin_llsd: dict) -> dict:
    """
    Decode skin info LLSD (from LLMeshSkinInfo::fromLLSD).
    Returns dict with joint_names, inverse_bind_matrices, bind_shape_matrix.
    """
    joint_names = [str(n) for n in skin_llsd.get('joint_names', [])]

    inv_bind = []
    for mat_flat in skin_llsd.get('inverse_bind_matrix', []):
        mat = [[float(mat_flat[r*4+c]) for c in range(4)] for r in range(4)]
        inv_bind.append(mat)

    bsm_flat = skin_llsd.get('bind_shape_matrix', [])
    bind_shape = [[float(bsm_flat[r*4+c]) for c in range(4)] for r in range(4)] \
                 if len(bsm_flat) == 16 else None

    return {
        'joint_names':            joint_names,
        'inverse_bind_matrices':  inv_bind,
        'bind_shape_matrix':      bind_shape,
    }


# ── Asset loader ─────────────────────────────────────────────────────────────

def load_mesh_asset(path: Path, lod: str = LOD_HIGH) -> dict:
    """
    Load and fully decode a mesh .asset file.
    Returns:
      {
        'faces':  [ {positions, normals, texcoords, indices, weights}, ... ],
        'skin':   {joint_names, inverse_bind_matrices, bind_shape_matrix} | None,
        'header': raw LLSD header dict,
      }
    """
    header, data = read_asset_file(path)
    base_offset  = CACHE_PREAMBLE_SIZE + struct.unpack_from('<I', data, 4)[0]

    # -- decode requested LOD --
    lod_info = header.get(lod)
    if not lod_info:
        # Fall back through LODs from high to lowest
        for name in reversed(LOD_NAMES):
            if header.get(name) and header[name].get('size', 0) > 0:
                lod_info = header[name]; lod = name; break

    if not lod_info or lod_info.get('size', 0) <= 0:
        raise ValueError(f'No usable LOD data found in asset')

    lod_offset = base_offset + lod_info['offset']
    lod_size   = lod_info['size']
    lod_raw    = data[lod_offset:lod_offset + lod_size]
    lod_llsd   = _unzip_llsd(lod_raw)

    faces = []
    if isinstance(lod_llsd, list):
        for face_data in lod_llsd:
            if isinstance(face_data, dict):
                decoded = decode_face(face_data)
                if decoded:
                    faces.append(decoded)

    # -- decode skin info --
    skin = None
    skin_info = header.get('skin')
    if skin_info and skin_info.get('size', 0) > 0:
        skin_offset = base_offset + skin_info['offset']
        skin_size   = skin_info['size']
        skin_raw    = data[skin_offset:skin_offset + skin_size]
        try:
            skin_llsd = _unzip_llsd(skin_raw)
            skin = decode_skin(skin_llsd)
        except Exception as e:
            print(f'WARNING: skin decode failed: {e}', file=sys.stderr)

    return {'faces': faces, 'skin': skin, 'header': header, 'lod': lod}


# ── OBJ exporter ─────────────────────────────────────────────────────────────

def export_obj(mesh: dict, out_path: Path, name: str = 'mesh'):
    """Export decoded mesh faces to Wavefront OBJ format."""
    faces  = mesh['faces']
    skin   = mesh['skin']

    with out_path.open('w', encoding='utf-8') as f:
        f.write(f'# SL mesh export  lod={mesh["lod"]}\n')
        f.write(f'# {len(faces)} submesh(es)\n\n')

        vert_offset = 1   # OBJ is 1-indexed

        for fi, face in enumerate(faces):
            f.write(f'g submesh_{fi}\n')

            for p in face['positions']:
                f.write(f'v {p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n')

            for tc in face['texcoords']:
                f.write(f'vt {tc[0]:.6f} {tc[1]:.6f}\n')

            for n in face['normals']:
                f.write(f'vn {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}\n')

            has_tc = bool(face['texcoords'])
            has_n  = bool(face['normals'])
            idx    = face['indices']

            for tri in range(0, len(idx), 3):
                verts = []
                for k in range(3):
                    vi = idx[tri + k] + vert_offset
                    if has_tc and has_n:
                        verts.append(f'{vi}/{vi}/{vi}')
                    elif has_tc:
                        verts.append(f'{vi}/{vi}')
                    elif has_n:
                        verts.append(f'{vi}//{vi}')
                    else:
                        verts.append(str(vi))
                f.write(f'f {" ".join(verts)}\n')

            vert_offset += len(face['positions'])

    # Export skin weights as sidecar JSON
    if skin:
        skin_path = out_path.with_suffix('.skin.json')
        with skin_path.open('w', encoding='utf-8') as f:
            json.dump(skin, f, indent=2)

        # Also export per-vertex weights
        weights_path = out_path.with_suffix('.weights.json')
        all_weights = []
        for fi, face in enumerate(faces):
            if face['weights']:
                face_w = []
                for vert_w in face['weights']:
                    entry = {skin['joint_names'][bi]: w
                             for bi, w in vert_w.items()
                             if bi < len(skin['joint_names'])}
                    face_w.append(entry)
                all_weights.append({'submesh': fi, 'vertices': face_w})
        with weights_path.open('w', encoding='utf-8') as f:
            json.dump(all_weights, f, indent=2)

    print(f'Exported {len(faces)} submesh(es) to {out_path}')
    if skin:
        print(f'  Skin: {len(skin["joint_names"])} joints -> {out_path.with_suffix(".skin.json")}')
        print(f'  Weights -> {out_path.with_suffix(".weights.json")}')


# ── Cache path helper ─────────────────────────────────────────────────────────

def find_asset(cache_dir: Path, uuid: str) -> Optional[Path]:
    """
    Locate a mesh asset file in the Firestorm disk cache.
    Path format (lldiskcache.cpp metaDataToFilepath):
      cache_dir / UUID[0] / sl_cache_UUID_0.asset
    """
    uuid = uuid.lower()
    candidate = cache_dir / uuid[0] / f'sl_cache_{uuid}_0.asset'
    if candidate.exists():
        return candidate
    # Some builds omit subdirectory
    flat = cache_dir / f'sl_cache_{uuid}_0.asset'
    if flat.exists():
        return flat
    return None


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Decode SL/Firestorm mesh asset files and export OBJ.'
    )
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('decode', help='Decode a single .asset file')
    p.add_argument('asset_file', help='Path to sl_cache_UUID_0.asset')
    p.add_argument('-o', '--output', default=None, help='Output OBJ path')
    p.add_argument('--lod', default='high_lod',
                   choices=LOD_NAMES, help='LOD to export (default: high_lod)')
    p.add_argument('--info', action='store_true',
                   help='Print header info only, no export')

    p = sub.add_parser('find', help='Find and decode a mesh by UUID from cache')
    p.add_argument('uuid', help='Mesh asset UUID')
    p.add_argument('cache_dir', help='Path to Firestorm cache directory')
    p.add_argument('-o', '--output', default=None, help='Output OBJ path')
    p.add_argument('--lod', default='high_lod', choices=LOD_NAMES)

    args = parser.parse_args()

    if args.command == 'decode':
        path = Path(args.asset_file)
        mesh = load_mesh_asset(path, lod=args.lod)
        if args.info:
            h = mesh['header']
            print(f'LOD present:')
            for name in LOD_NAMES:
                info = h.get(name, {})
                print(f'  {name:<12}  offset={info.get("offset","?")}  size={info.get("size","?")}')
            skin = h.get('skin', {})
            print(f'  skin         offset={skin.get("offset","?")}  size={skin.get("size","?")}')
            print(f'Faces in {mesh["lod"]}: {len(mesh["faces"])}')
            for i, face in enumerate(mesh['faces']):
                print(f'  face {i}: {len(face["positions"])} verts, '
                      f'{len(face["indices"])//3} tris, '
                      f'has_normals={bool(face["normals"])}, '
                      f'has_uv={bool(face["texcoords"])}, '
                      f'has_weights={bool(face["weights"])}')
            if mesh['skin']:
                print(f'Skin joints: {mesh["skin"]["joint_names"]}')
        else:
            out = Path(args.output) if args.output else path.with_suffix('.obj')
            export_obj(mesh, out)

    elif args.command == 'find':
        cache_dir = Path(args.cache_dir)
        asset_path = find_asset(cache_dir, args.uuid)
        if not asset_path:
            print(f'Asset {args.uuid} not found in cache {cache_dir}')
            sys.exit(1)
        print(f'Found: {asset_path}')
        mesh = load_mesh_asset(asset_path, lod=args.lod)
        out  = Path(args.output) if args.output else Path(f'{args.uuid}.obj')
        export_obj(mesh, out)


if __name__ == '__main__':
    main()
