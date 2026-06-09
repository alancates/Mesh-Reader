#!/usr/bin/env python3
"""
Mesh-Reader: Firestorm/Second Life object cache reader.
Reads object.cache (index) and objectsXXYY.slc (data) files.

Cache format verified against Firestorm source:
  indra/newview/llvocache.cpp       -- file format, header, entry serialisation
  indra/newview/llviewerobject.cpp  -- initObjectDataMap(), body field layout
  indra/llmessage/lldatapacker.cpp  -- LLDataPackerBinaryBuffer wire sizes

Body layout (initObjectDataMap, flat binary, little-endian):
  Offset  Size  Field
  0x00    16    ID          (LLUUID / full object UUID)
  0x10     4    LocalID     (U32)
  0x14     1    PCode       (U8 -- 9 = volume/mesh prim)
  0x15     1    State       (U8)
  0x16     4    CRC         (U32)
  0x1a     1    Material    (U8)
  0x1b     1    ClickAction (U8)
  0x1c    12    Scale       (3 x F32, x y z)
  0x28    12    Pos         (3 x F32, x y z, region-local)
  0x34    12    Rot         (3 x F32, packed quaternion -> vec3 form)
  0x40     4    SpecialCode (U32 bitmask)
  0x44    16    Owner       (LLUUID)
  -- conditional fields follow --
  if SpecialCode & 0x80:  +12 bytes Omega (3 x F32)
  if SpecialCode & 0x20:  +4  bytes ParentID (U32)
  -- then variable-length payload (text, particles, extra params, NV pairs …) --

SpecialCode bits (from llviewerobject.cpp processUpdateMessage OUT_FULL_COMPRESSED):
  0x01  ScratchPad data present
  0x02  Tree data present
  0x04  Floating text present
  0x08  Particle system present (legacy)
  0x10  Attached sound present
  0x20  ParentID present
  0x80  Omega (angular velocity) present
  0x100 Name/Value pairs present
  0x200 Media URL present
  0x400 New-style particle system present
"""

from __future__ import annotations

import argparse
import binascii
import csv
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from struct import unpack_from, calcsize

# ── Constants from llvocache.cpp ──────────────────────────────────────────────

ENTRY_HEADER_SIZE   = 6 * 4      # 6 x S32/U32 = 24 bytes  (llvocache.cpp line 47)
MAX_ENTRY_BODY_SIZE = 10_000     # llvocache.cpp line 48
UUID_BYTES          = 16

# SpecialCode bitmask flags (llviewerobject.cpp OUT_FULL_COMPRESSED)
SC_SCRATCHPAD   = 0x001
SC_TREE         = 0x002
SC_TEXT         = 0x004
SC_PARTICLES    = 0x008
SC_SOUND        = 0x010
SC_PARENT_ID    = 0x020
SC_OMEGA        = 0x080
SC_NAME_VALUE   = 0x100
SC_MEDIA_URL    = 0x200

# PCode values (llprimitive.h)
PCODE_VOLUME    = 0x09   # standard prim / mesh
PCODE_AVATAR    = 0x2F
PCODE_GRASS     = 0x51
PCODE_TREE      = 0x41
PCODE_NEW_TREE  = 0x43

PCODE_NAMES = {
    PCODE_VOLUME:  'volume',
    PCODE_AVATAR:  'avatar',
    PCODE_GRASS:   'grass',
    PCODE_TREE:    'tree',
    PCODE_NEW_TREE:'new_tree',
}

# Body field byte offsets (initObjectDataMap in llviewerobject.cpp)
OFF_ID          = 0x00   # 16 bytes LLUUID
OFF_LOCAL_ID    = 0x10   # U32
OFF_PCODE       = 0x14   # U8
OFF_STATE       = 0x15   # U8
OFF_CRC         = 0x16   # U32
OFF_MATERIAL    = 0x1a   # U8
OFF_CLICKACTION = 0x1b   # U8
OFF_SCALE       = 0x1c   # 3 x F32
OFF_POS         = 0x28   # 3 x F32
OFF_ROT         = 0x34   # 3 x F32 (packed quaternion as vec3)
OFF_SPECIAL     = 0x40   # U32
OFF_OWNER       = 0x44   # 16 bytes LLUUID
FIXED_HEADER_END = 0x54  # 84 bytes minimum fixed body

DISCOVERY_COLUMNS = [
    'source_file', 'record_index', 'local_id', 'full_id', 'parent_id',
    'pcode', 'pcode_name', 'state', 'material', 'click_action',
    'crc', 'update_flags',
    'owner_id', 'mesh_id',
    'is_root', 'is_child', 'is_mesh_candidate',
    'pos_x', 'pos_y', 'pos_z',
    'scale_x', 'scale_y', 'scale_z',
    'rot_x', 'rot_y', 'rot_z', 'rot_w',
    'omega_x', 'omega_y', 'omega_z',
    'has_text', 'has_sound', 'has_particles', 'has_name_value',
    'distance_from_reference',
    'bbox_min_x', 'bbox_min_y', 'bbox_min_z',
    'bbox_max_x', 'bbox_max_y', 'bbox_max_z',
    'notes',
]

# ── Structs ───────────────────────────────────────────────────────────────────

@dataclass
class HeaderMetaInfo:
    """First 8 bytes of object.cache  (llvocache.h HeaderMetaInfo)"""
    version: int = 0
    address_size: int = 0
    SIZE = calcsize('<II')

    @classmethod
    def read(cls, data: bytes, offset: int = 0) -> 'HeaderMetaInfo':
        version, address_size = unpack_from('<II', data, offset)
        return cls(version, address_size)

@dataclass
class HeaderEntryInfo:
    """16 bytes per region in object.cache  (llvocache.h HeaderEntryInfo)"""
    index: int = 0
    handle: int = 0
    time: int = 0
    SIZE = calcsize('<IQL')

    @classmethod
    def read(cls, data: bytes, offset: int = 0) -> 'HeaderEntryInfo':
        index, handle, time = unpack_from('<IQL', data, offset)
        return cls(index, handle, time)

@dataclass
class VOCacheEntryHeader:
    """
    24-byte on-disk entry header in objectsXXYY.slc
    (llvocache.cpp LLVOCacheEntry::writeToBuffer / readFromFile)

    Field layout (each sizeof(U32) = 4 bytes):
      [0]  mLocalID      U32
      [1]  mCRC          U32
      [2]  mHitCount     S32
      [3]  mDupeCount    S32
      [4]  mCRCChangeCount S32
      [5]  body_size     S32  (size of the DataPacker buffer that follows)
    """
    local_id: int = 0
    crc: int = 0
    hit_count: int = 0
    dupe_count: int = 0
    crc_change_count: int = 0
    body_size: int = 0
    SIZE = calcsize('<6i')   # 6 x S32 (signed matches llvocache.cpp memcpy usage)

    @classmethod
    def read(cls, data: bytes, offset: int = 0) -> 'VOCacheEntryHeader':
        local_id, crc, hit_count, dupe_count, crc_change_count, body_size = \
            unpack_from('<6i', data, offset)
        return cls(local_id, crc, hit_count, dupe_count, crc_change_count, body_size)

@dataclass
class VOCacheEntry:
    header: VOCacheEntryHeader
    body: bytes = field(repr=False)

# ── Body decoder ──────────────────────────────────────────────────────────────

def uuid_bytes_to_str(b: bytes) -> str:
    h = binascii.hexlify(b).decode()
    return f'{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}'

def packed_vec3_to_quat(v: tuple) -> tuple:
    """
    Firestorm stores rotation as a packed quaternion in vec3 form.
    The original sign of w is recovered by ensuring w >= 0 (convention).
    llquaternion.h: unpackFromVector3 -- x,y,z stored; w = sqrt(max(0,1-x^2-y^2-z^2))
    """
    x, y, z = v
    w2 = 1.0 - x*x - y*y - z*z
    w = math.sqrt(max(0.0, w2))
    return (x, y, z, w)

def decode_entry_body(body: bytes) -> dict:
    """
    Decode a .slc entry body using the verified field layout from
    initObjectDataMap() in llviewerobject.cpp.

    Returns a dict of decoded fields. The 'notes' key is a list of
    warning strings (empty means clean decode).
    """
    b = body
    notes = []

    d: dict = {
        'full_id':      '',
        'local_id':     '',
        'pcode':        '',
        'pcode_name':   '',
        'state':        '',
        'crc':          '',
        'material':     '',
        'click_action': '',
        'scale':        None,
        'pos':          None,
        'rot':          None,    # (x, y, z, w) quaternion
        'omega':        None,
        'special_code': None,
        'owner_id':     '',
        'parent_id':    0,
        'has_text':     0,
        'has_sound':    0,
        'has_particles':0,
        'has_name_value':0,
        'notes':        notes,
    }

    if len(b) < FIXED_HEADER_END:
        notes.append(f'body_too_short={len(b)}')
        return d

    try:
        d['full_id']      = uuid_bytes_to_str(b[OFF_ID:OFF_ID + 16])
        d['local_id'],    = unpack_from('<I', b, OFF_LOCAL_ID)
        d['pcode'],       = unpack_from('<B', b, OFF_PCODE)
        d['pcode_name']   = PCODE_NAMES.get(d['pcode'], f'unknown_0x{d["pcode"]:02x}')
        d['state'],       = unpack_from('<B', b, OFF_STATE)
        d['crc'],         = unpack_from('<I', b, OFF_CRC)
        d['material'],    = unpack_from('<B', b, OFF_MATERIAL)
        d['click_action'],= unpack_from('<B', b, OFF_CLICKACTION)
        d['scale']        = unpack_from('<3f', b, OFF_SCALE)
        d['pos']          = unpack_from('<3f', b, OFF_POS)
        rot_vec3          = unpack_from('<3f', b, OFF_ROT)
        d['rot']          = packed_vec3_to_quat(rot_vec3)
        sc,               = unpack_from('<I', b, OFF_SPECIAL)
        d['special_code'] = sc
        d['owner_id']     = uuid_bytes_to_str(b[OFF_OWNER:OFF_OWNER + 16])

        # -- conditional fields after fixed header --
        cursor = FIXED_HEADER_END   # 0x54 = 84

        if sc & SC_OMEGA:
            if cursor + 12 <= len(b):
                d['omega'] = unpack_from('<3f', b, cursor)
                cursor += 12
            else:
                notes.append('omega_truncated')

        if sc & SC_PARENT_ID:
            if cursor + 4 <= len(b):
                d['parent_id'], = unpack_from('<I', b, cursor)
                cursor += 4
            else:
                notes.append('parent_id_truncated')

        # Flag presence of variable-length payload fields
        d['has_text']      = 1 if (sc & SC_TEXT)      else 0
        d['has_sound']     = 1 if (sc & SC_SOUND)      else 0
        d['has_particles'] = 1 if (sc & SC_PARTICLES)  else 0
        d['has_name_value']= 1 if (sc & SC_NAME_VALUE) else 0

    except Exception as exc:
        notes.append(f'decode_error={exc}')

    return d

# ── CSV row builder ───────────────────────────────────────────────────────────

def entry_to_discovery_row(entry: VOCacheEntry, source_file: str,
                            record_index: int,
                            ref_point: tuple | None = None) -> dict:
    row = {k: '' for k in DISCOVERY_COLUMNS}
    row['source_file']   = source_file
    row['record_index']  = record_index
    row['update_flags']  = entry.header.crc   # per-entry crc from the slc header

    d = decode_entry_body(entry.body)

    row['local_id']    = d['local_id']   if d['local_id'] != '' else entry.header.local_id
    row['full_id']     = d['full_id']
    row['parent_id']   = d['parent_id']
    row['pcode']       = d['pcode']
    row['pcode_name']  = d['pcode_name']
    row['state']       = d['state']
    row['material']    = d['material']
    row['click_action']= d['click_action']
    row['crc']         = d['crc']
    row['owner_id']    = d['owner_id']
    row['update_flags']= entry.header.crc

    parent_id = d['parent_id']
    if d['pcode'] != '':
        row['is_root']           = 1 if parent_id == 0 else 0
        row['is_child']          = 1 if parent_id != 0 else 0
        row['is_mesh_candidate'] = 1 if d['pcode'] == PCODE_VOLUME else 0
        if d['pcode'] == PCODE_VOLUME:
            row['mesh_id'] = d['full_id']

    pos   = d['pos']
    scale = d['scale']
    rot   = d['rot']
    omega = d['omega']

    if pos is not None:
        row['pos_x'], row['pos_y'], row['pos_z'] = pos
    if scale is not None:
        row['scale_x'], row['scale_y'], row['scale_z'] = scale
    if rot is not None:
        row['rot_x'], row['rot_y'], row['rot_z'], row['rot_w'] = rot
    if omega is not None:
        row['omega_x'], row['omega_y'], row['omega_z'] = omega

    if pos is not None and scale is not None:
        px, py, pz = pos
        sx, sy, sz = scale
        row['bbox_min_x'] = px - sx / 2.0
        row['bbox_min_y'] = py - sy / 2.0
        row['bbox_min_z'] = pz - sz / 2.0
        row['bbox_max_x'] = px + sx / 2.0
        row['bbox_max_y'] = py + sy / 2.0
        row['bbox_max_z'] = pz + sz / 2.0

    if ref_point is not None and pos is not None:
        dx = pos[0] - ref_point[0]
        dy = pos[1] - ref_point[1]
        dz = pos[2] - ref_point[2]
        row['distance_from_reference'] = math.sqrt(dx*dx + dy*dy + dz*dz)

    row['has_text']       = d['has_text']
    row['has_sound']      = d['has_sound']
    row['has_particles']  = d['has_particles']
    row['has_name_value'] = d['has_name_value']
    row['notes']          = '; '.join(d['notes'])
    return row

# ── Helpers ───────────────────────────────────────────────────────────────────

def hexdump(data: bytes, limit: int = 256) -> str:
    chunk = data[:limit]
    lines = []
    for off in range(0, len(chunk), 16):
        row = chunk[off:off + 16]
        hex_part = ' '.join(f'{b2:02x}' for b2 in row)
        asc_part = ''.join(chr(b2) if 32 <= b2 < 127 else '.' for b2 in row)
        lines.append(f' {off:04x}  {hex_part:<47}  {asc_part}')
    return '\n'.join(lines)

def default_csv_path(input_path: str | Path) -> Path:
    return Path(input_path).with_suffix('.csv')

# ── File readers ──────────────────────────────────────────────────────────────

def read_object_cache(path: str | Path) -> tuple[HeaderMetaInfo, list[HeaderEntryInfo]]:
    """Read object.cache -- returns (meta, list of region entries)."""
    data = Path(path).read_bytes()
    meta = HeaderMetaInfo.read(data, 0)
    entries = []
    offset = HeaderMetaInfo.SIZE
    while offset + HeaderEntryInfo.SIZE <= len(data):
        entry = HeaderEntryInfo.read(data, offset)
        offset += HeaderEntryInfo.SIZE
        if entry.time == 0:
            continue
        entries.append(entry)
    return meta, entries

def read_slc(path: str | Path) -> tuple[bytes, int, list[VOCacheEntry]]:
    """
    Read objectsXXYY.slc
    On-disk format (llvocache.cpp readFromCache / writeToCache):
      [16 bytes]  region UUID
      [4  bytes]  S32 num_entries
      then num_entries times:
        [24 bytes]  VOCacheEntryHeader  (6 x S32)
        [n  bytes]  DataPacker body     (body_size bytes)
    """
    data = Path(path).read_bytes()
    offset = 0

    region_id = data[offset:offset + UUID_BYTES]
    offset += UUID_BYTES

    num_entries, = unpack_from('<i', data, offset)
    offset += 4

    entries: list[VOCacheEntry] = []
    for _ in range(num_entries):
        if offset + ENTRY_HEADER_SIZE > len(data):
            break
        hdr = VOCacheEntryHeader.read(data, offset)
        offset += ENTRY_HEADER_SIZE

        if hdr.body_size < 1 or hdr.body_size > MAX_ENTRY_BODY_SIZE:
            print(f'WARNING: bogus body_size {hdr.body_size} '
                  f'for local_id {hdr.local_id}, stopping.')
            break

        body = data[offset:offset + hdr.body_size]
        offset += hdr.body_size
        entries.append(VOCacheEntry(hdr, body))

    return region_id, num_entries, entries

# ── CLI commands ──────────────────────────────────────────────────────────────

def cmd_index(args):
    """Inspect object.cache index file."""
    meta, entries = read_object_cache(args.inputfile)
    print(f'=== object.cache: {args.inputfile} ===')
    print(f'Version      : {meta.version}')
    print(f'Address size : {meta.address_size}')
    print(f'Regions found: {len(entries)}')
    print()
    for i, e in enumerate(entries):
        rx = (e.handle >> 32) & 0xFFFFFFFF
        ry =  e.handle        & 0xFFFFFFFF
        print(f'[{i:3d}] index={e.index:4d} '
              f'region=({rx},{ry}) '
              f'handle=0x{e.handle:016x} '
              f'time={e.time}')

def cmd_inspect(args):
    """Inspect an .slc data file."""
    region_id, expected, entries = read_slc(args.inputfile)
    print(f'=== {args.inputfile} ===')
    print(f'Region UUID : {uuid_bytes_to_str(region_id)}')
    print(f'Expected    : {expected} entries')
    print(f'Read        : {len(entries)} entries')
    print()
    for i, e in enumerate(entries[:30]):
        h = e.header
        d = decode_entry_body(e.body)
        pname = d.get('pcode_name', '?')
        parent = d.get('parent_id', 0)
        print(f'[{i:4d}] local_id={h.local_id:10d}  '
              f'crc={h.crc:08x}  '
              f'body={h.body_size:5d}B  '
              f'pcode={d.get("pcode","?"):>3} ({pname:10s})  '
              f'parent={parent}')
    if len(entries) > 30:
        print(f'... {len(entries) - 30} more entries not shown ...')

def cmd_dump(args):
    """Dump one entry body by local_id with full field decoding."""
    _, _, entries = read_slc(args.inputfile)
    target = int(args.localid)
    for e in entries:
        if e.header.local_id == target:
            b = e.body
            d = decode_entry_body(b)
            print(f'local_id={target}  body={len(b)} bytes')
            print(hexdump(b, 256))
            print()
            print(f'Object UUID  : {d["full_id"]}')
            print(f'PCode        : {d["pcode"]}  ({d["pcode_name"]})')
            print(f'State        : {d["state"]}')
            print(f'CRC          : {d["crc"]:#010x}')
            print(f'Material     : {d["material"]}')
            print(f'ClickAction  : {d["click_action"]}')
            if d['scale']:
                print(f'Scale        : {d["scale"]}')
            if d['pos']:
                print(f'Position     : {d["pos"]}')
            if d['rot']:
                x, y, z, w = d['rot']
                print(f'Rotation     : ({x:.6f}, {y:.6f}, {z:.6f}, {w:.6f})  [quat xyzw]')
            print(f'SpecialCode  : {d["special_code"]:#010x}')
            print(f'Owner UUID   : {d["owner_id"]}')
            print(f'Parent ID    : {d["parent_id"]}')
            if d['omega']:
                print(f'Omega        : {d["omega"]}')
            flags = []
            if d['has_text']:      flags.append('text')
            if d['has_sound']:     flags.append('sound')
            if d['has_particles']: flags.append('particles')
            if d['has_name_value']:flags.append('name_value')
            if flags:
                print(f'Payload flags: {", ".join(flags)}')
            if d['notes']:
                print(f'Notes        : {"; ".join(d["notes"])}')
            return
    print(f'local_id {target} not found.')

def cmd_list(args):
    """Export all decoded objects from one .slc file to CSV discovery report."""
    _, _, entries = read_slc(args.inputfile)
    output_path = Path(args.output) if args.output else default_csv_path(args.inputfile)

    ref_point = None
    if args.ref_x is not None and args.ref_y is not None and args.ref_z is not None:
        ref_point = (args.ref_x, args.ref_y, args.ref_z)

    with output_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=DISCOVERY_COLUMNS)
        writer.writeheader()
        for i, e in enumerate(entries):
            writer.writerow(
                entry_to_discovery_row(e, Path(args.inputfile).name, i, ref_point)
            )
    print(f'Wrote {len(entries)} rows to {output_path}')

# ── Entry point ───────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Read Firestorm/SL object cache files.'
    )
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('index', help='Read object.cache index')
    p.add_argument('inputfile', help='Path to object.cache')

    p = sub.add_parser('inspect', help='Inspect a .slc data file')
    p.add_argument('inputfile', help='Path to .slc file')

    p = sub.add_parser('dump', help='Dump one entry body by local_id')
    p.add_argument('inputfile', help='Path to .slc file')
    p.add_argument('localid', help='Local object ID to dump')

    p = sub.add_parser('list', help='Export .slc entries to CSV discovery report')
    p.add_argument('inputfile', help='Path to .slc file')
    p.add_argument('-o', '--output', help='Path to output CSV')
    p.add_argument('--ref-x', type=float, help='Reference X for distance calculation')
    p.add_argument('--ref-y', type=float, help='Reference Y for distance calculation')
    p.add_argument('--ref-z', type=float, help='Reference Z for distance calculation')

    return parser

def main():
    args = build_parser().parse_args()
    dispatch = {
        'index':   cmd_index,
        'inspect': cmd_inspect,
        'dump':    cmd_dump,
        'list':    cmd_list,
    }
    dispatch[args.command](args)

if __name__ == '__main__':
    main()
