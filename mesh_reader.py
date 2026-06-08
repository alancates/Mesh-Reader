#!/usr/bin/env python3
"""
Mesh-Reader: Firestorm/Second Life object cache reader.
Reads object.cache (index) and objectsXXYY.slc (data) files.
Based on llvocache.h / llvocache.cpp and Firestorm llviewerobject.cpp.
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from struct import unpack_from, calcsize
import argparse
import binascii
import csv
import math

# ── Constants from llvocache.cpp ──────────────────────────────────────────────
ENTRY_HEADER_SIZE   = 6 * 4      # 6 x S32/U32 = 24 bytes
MAX_ENTRY_BODY_SIZE = 10_000
MAX_NUM_ENTRIES     = 128
UUID_BYTES          = 16

DISCOVERY_COLUMNS = [
    'source_file', 'record_index', 'local_id', 'full_id', 'parent_id', 'root_id',
    'pcode', 'state', 'update_flags', 'crc', 'name', 'description', 'owner_id',
    'creator_id', 'group_id', 'asset_id', 'mesh_id', 'is_root', 'is_child',
    'is_mesh_candidate', 'pos_x', 'pos_y', 'pos_z', 'scale_x', 'scale_y',
    'scale_z', 'rot_x', 'rot_y', 'rot_z', 'rot_w', 'distance_from_reference',
    'bbox_min_x', 'bbox_min_y', 'bbox_min_z', 'bbox_max_x', 'bbox_max_y',
    'bbox_max_z', 'notes'
]

# ── Structs ───────────────────────────────────────────────────────────────────

@dataclass
class HeaderMetaInfo:
    """First 8 bytes of object.cache"""
    version: int = 0
    address_size: int = 0

    SIZE = calcsize('<II')

    @classmethod
    def read(cls, data: bytes, offset: int = 0) -> 'HeaderMetaInfo':
        version, address_size = unpack_from('<II', data, offset)
        return cls(version, address_size)


@dataclass
class HeaderEntryInfo:
    """16 bytes per region entry in object.cache"""
    index: int = 0
    handle: int = 0
    time: int = 0

    SIZE = calcsize('<iQI')

    @classmethod
    def read(cls, data: bytes, offset: int = 0) -> 'HeaderEntryInfo':
        index, handle, time = unpack_from('<iQI', data, offset)
        return cls(index, handle, time)


@dataclass
class VOCacheEntryHeader:
    """24-byte header preceding each object body in the .slc file"""
    local_id: int = 0
    crc: int = 0
    hit_count: int = 0
    dupe_count: int = 0
    crc_change_count: int = 0
    body_size: int = 0

    @classmethod
    def read(cls, data: bytes, offset: int = 0) -> 'VOCacheEntryHeader':
        local_id, crc, hit_count, dupe_count, crc_change_count, body_size = \
            unpack_from('<IIiiiI', data, offset)
        return cls(local_id, crc, hit_count, dupe_count,
                   crc_change_count, body_size)


@dataclass
class VOCacheEntry:
    header: VOCacheEntryHeader
    body: bytes


# ── Helpers ───────────────────────────────────────────────────────────────────

def hexdump(data: bytes, limit: int = 256) -> str:
    chunk = data[:limit]
    lines = []
    for off in range(0, len(chunk), 16):
        row = chunk[off:off + 16]
        hex_part = ' '.join(f'{b:02x}' for b in row)
        asc_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in row)
        lines.append(f'  {off:04x}  {hex_part:<47}  {asc_part}')
    return '\n'.join(lines)


def uuid_bytes_to_str(b: bytes) -> str:
    h = binascii.hexlify(b).decode()
    return f'{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}'


def maybe_uuid(body: bytes, offset: int) -> str:
    if offset + UUID_BYTES > len(body):
        return ''
    raw = body[offset:offset + UUID_BYTES]
    if not any(raw):
        return ''
    return uuid_bytes_to_str(raw)


def default_csv_path(input_path):
    input_path = Path(input_path)
    return input_path.with_suffix('.csv')


def unpack_vec3(body: bytes, offset: int):
    if offset + 12 > len(body):
        return None
    return unpack_from('<fff', body, offset)


def decode_object_body(body: bytes) -> dict:
    obj = {
        'full_id': '',
        'local_id': '',
        'parent_id': '',
        'root_id': '',
        'pcode': '',
        'state': '',
        'update_flags': '',
        'crc': '',
        'name': '',
        'description': '',
        'owner_id': '',
        'creator_id': '',
        'group_id': '',
        'asset_id': '',
        'mesh_id': '',
        'pos': None,
        'scale': None,
        'rot': None,
        'special_code': None,
        'notes': ''
    }

    if len(body) < 0x44:
        obj['notes'] = 'body_too_small'
        return obj

    obj['full_id'] = maybe_uuid(body, 0x00)
    obj['local_id'] = unpack_from('<I', body, 0x10)[0]
    obj['pcode'] = body[0x14]
    obj['state'] = body[0x15]
    obj['crc'] = unpack_from('<I', body, 0x16)[0]
    obj['scale'] = unpack_vec3(body, 0x1C)
    obj['pos'] = unpack_vec3(body, 0x28)

    rot_xyz = unpack_vec3(body, 0x34)
    if rot_xyz is not None:
        rx, ry, rz = rot_xyz
        rw_sq = max(0.0, 1.0 - (rx * rx + ry * ry + rz * rz))
        obj['rot'] = (rx, ry, rz, math.sqrt(rw_sq))

    obj['special_code'] = unpack_from('<I', body, 0x40)[0]
    obj['owner_id'] = maybe_uuid(body, 0x44)

    offset = 0x54
    if obj['special_code'] & 0x80:
        if offset + 12 > len(body):
            obj['notes'] = 'truncated_omega'
            return obj
        offset += 12

    if obj['special_code'] & 0x20:
        if offset + 4 > len(body):
            obj['notes'] = 'truncated_parent_id'
            return obj
        obj['parent_id'] = unpack_from('<I', body, offset)[0]

    notes = []
    if obj['special_code'] & 0x20:
        notes.append('has_parent')
    if obj['pcode'] == 9:
        notes.append('mesh_pcode')
    obj['notes'] = ','.join(notes)
    return obj


def object_to_discovery_row(obj, source_file, record_index, ref_point=None):
    row = {col: '' for col in DISCOVERY_COLUMNS}
    row['source_file'] = source_file
    row['record_index'] = record_index
    row['local_id'] = obj.get('local_id', '')
    row['full_id'] = obj.get('full_id', '')
    row['parent_id'] = obj.get('parent_id', '')
    row['root_id'] = obj.get('root_id', '')
    row['pcode'] = obj.get('pcode', '')
    row['state'] = obj.get('state', '')
    row['update_flags'] = obj.get('update_flags', '')
    row['crc'] = obj.get('crc', '')
    row['name'] = obj.get('name', '')
    row['description'] = obj.get('description', '')
    row['owner_id'] = obj.get('owner_id', '')
    row['creator_id'] = obj.get('creator_id', '')
    row['group_id'] = obj.get('group_id', '')
    row['asset_id'] = obj.get('asset_id', '')
    row['mesh_id'] = obj.get('mesh_id', '')

    parent_id = obj.get('parent_id', '')
    row['is_root'] = parent_id in ('', None, 0)
    row['is_child'] = not row['is_root']
    row['is_mesh_candidate'] = bool(obj.get('pcode') == 9 or obj.get('mesh_id'))

    pos = obj.get('pos')
    scale = obj.get('scale')
    rot = obj.get('rot')

    if pos is not None:
        row['pos_x'], row['pos_y'], row['pos_z'] = pos
    if scale is not None:
        row['scale_x'], row['scale_y'], row['scale_z'] = scale
    if rot is not None:
        row['rot_x'], row['rot_y'], row['rot_z'], row['rot_w'] = rot

    if ref_point is not None and pos is not None:
        dx = pos[0] - ref_point[0]
        dy = pos[1] - ref_point[1]
        dz = pos[2] - ref_point[2]
        row['distance_from_reference'] = math.sqrt(dx * dx + dy * dy + dz * dz)

    if pos is not None and scale is not None:
        hx = scale[0] / 2.0
        hy = scale[1] / 2.0
        hz = scale[2] / 2.0
        row['bbox_min_x'] = pos[0] - hx
        row['bbox_min_y'] = pos[1] - hy
        row['bbox_min_z'] = pos[2] - hz
        row['bbox_max_x'] = pos[0] + hx
        row['bbox_max_y'] = pos[1] + hy
        row['bbox_max_z'] = pos[2] + hz

    row['notes'] = obj.get('notes', '')
    return row


# ── Readers ───────────────────────────────────────────────────────────────────

def read_object_cache(path: str | Path) -> tuple[HeaderMetaInfo, list[HeaderEntryInfo]]:
    """Read object.cache — returns (meta, list of region entries)."""
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
    Format: [16 UUID][4 S32 count][entries...]
    Each entry: [24-byte header][body_size bytes]
    """
    data = Path(path).read_bytes()
    offset = 0

    region_id = data[offset:offset + UUID_BYTES]
    offset += UUID_BYTES

    num_entries, = unpack_from('<i', data, offset)
    offset += 4

    entries = []
    for _ in range(num_entries):
        if offset + ENTRY_HEADER_SIZE > len(data):
            break
        hdr = VOCacheEntryHeader.read(data, offset)
        offset += ENTRY_HEADER_SIZE

        if hdr.body_size <= 0 or hdr.body_size > MAX_ENTRY_BODY_SIZE:
            print(f'  WARNING: bogus body_size {hdr.body_size} '
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
        ry = e.handle & 0xFFFFFFFF
        print(f'  [{i:3d}] index={e.index:4d}  '
              f'region=({rx},{ry})  '
              f'handle=0x{e.handle:016x}  '
              f'time={e.time}')


def cmd_inspect(args):
    """Inspect an .slc data file."""
    region_id, expected, entries = read_slc(args.inputfile)
    print(f'=== {args.inputfile} ===')
    print(f'Region UUID  : {uuid_bytes_to_str(region_id)}')
    print(f'Expected     : {expected} entries')
    print(f'Read         : {len(entries)} entries')
    print()
    for i, e in enumerate(entries[:30]):
        h = e.header
        print(f'  [{i:4d}] local_id={h.local_id:10d}  '
              f'crc={h.crc:08x}  '
              f'body={h.body_size:5d}B  '
              f'hits={h.hit_count}  '
              f'dupes={h.dupe_count}')
    if len(entries) > 30:
        print(f'  ... {len(entries) - 30} more entries not shown ...')


def cmd_dump(args):
    """Dump one entry body by local_id with field decoding."""
    _, _, entries = read_slc(args.inputfile)
    target = int(args.localid)
    for e in entries:
        if e.header.local_id == target:
            b = e.body
            obj = decode_object_body(b)
            print(f'local_id={target}  body={len(b)} bytes')
            print(hexdump(b, 256))
            print()
            print(f"  UUID       : {obj.get('full_id', '')}")
            print(f"  LocalID    : {obj.get('local_id', '')}")
            print(f"  PCode      : {obj.get('pcode', '')}")
            print(f"  State      : {obj.get('state', '')}")
            print(f"  CRC        : 0x{obj.get('crc', 0):08x}" if obj.get('crc', '') != '' else '  CRC        : ')
            if obj.get('scale') is not None:
                sx, sy, sz = obj['scale']
                print(f'  Scale      : ({sx:.4f}, {sy:.4f}, {sz:.4f})')
            if obj.get('pos') is not None:
                px, py, pz = obj['pos']
                print(f'  Position   : ({px:.4f}, {py:.4f}, {pz:.4f})')
            if obj.get('rot') is not None:
                rx, ry, rz, rw = obj['rot']
                print(f'  Rotation   : ({rx:.4f}, {ry:.4f}, {rz:.4f}, {rw:.4f})')
            print(f"  Owner      : {obj.get('owner_id', '')}")
            print(f"  ParentID   : {obj.get('parent_id', '')}")
            print(f"  SpecialCode: 0x{obj.get('special_code', 0):08x}" if obj.get('special_code') is not None else '  SpecialCode: ')
            return
    print(f'local_id {target} not found.')


def cmd_list(args):
    _, _, entries = read_slc(args.inputfile)
    input_path = Path(args.inputfile)
    output_path = Path(args.output) if args.output else default_csv_path(input_path)

    ref_point = None
    if args.ref_x is not None and args.ref_y is not None and args.ref_z is not None:
        ref_point = (args.ref_x, args.ref_y, args.ref_z)

    rows = []
    for i, entry in enumerate(entries):
        obj = decode_object_body(entry.body)
        if not obj.get('local_id'):
            obj['local_id'] = entry.header.local_id
        if obj.get('crc', '') == '':
            obj['crc'] = entry.header.crc
        rows.append(object_to_discovery_row(
            obj,
            source_file=input_path.name,
            record_index=i,
            ref_point=ref_point,
        ))

    with output_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=DISCOVERY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f'Wrote {len(rows)} rows to {output_path}')


# ── Entry point ───────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Read Firestorm/SL object cache files.')
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('index', help='Read object.cache index')
    p.add_argument('inputfile', help='Path to object.cache')

    p = sub.add_parser('inspect', help='Inspect a .slc data file')
    p.add_argument('inputfile', help='Path to .slc file')

    p = sub.add_parser('dump', help='Dump one entry body by local_id')
    p.add_argument('inputfile', help='Path to .slc file')
    p.add_argument('localid', help='Local object ID to dump')

    p = sub.add_parser('list', help='Export a CSV discovery report from a .slc file')
    p.add_argument('inputfile', help='Path to .slc file')
    p.add_argument('-o', '--output', help='Path to output CSV')
    p.add_argument('--ref-x', type=float, default=None, help='Reference X for distance')
    p.add_argument('--ref-y', type=float, default=None, help='Reference Y for distance')
    p.add_argument('--ref-z', type=float, default=None, help='Reference Z for distance')

    return parser


def main():
    args = build_parser().parse_args()
    if args.command == 'index':
        cmd_index(args)
    elif args.command == 'inspect':
        cmd_inspect(args)
    elif args.command == 'dump':
        cmd_dump(args)
    elif args.command == 'list':
        cmd_list(args)


if __name__ == '__main__':
    main()
