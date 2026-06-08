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

# -- Constants from llvocache.cpp ---------------------------------------------
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


# -- Structs ------------------------------------------------------------------

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

    SIZE = calcsize('<6I')

    @classmethod
    def read(cls, data: bytes, offset: int = 0) -> 'VOCacheEntryHeader':
        local_id, crc, hit_count, dupe_count, crc_change_count, body_size = unpack_from('<6I', data, offset)
        return cls(local_id, crc, hit_count, dupe_count, crc_change_count, body_size)


@dataclass
class VOCacheEntry:
    header: VOCacheEntryHeader
    body: bytes


# -- Helpers ------------------------------------------------------------------

def hexdump(data: bytes, limit: int = 256) -> str:
    chunk = data[:limit]
    lines = []
    for off in range(0, len(chunk), 16):
        row = chunk[off:off + 16]
        hexpart = ' '.join(f'{b:02x}' for b in row)
        ascpart = ''.join(chr(b) if 32 <= b < 127 else '.' for b in row)
        lines.append(f'{off:04x}  {hexpart:<47}  {ascpart}')
    return '\n'.join(lines)


def uuid_bytes_to_str(b: bytes) -> str:
    h = binascii.hexlify(b).decode()
    return f'{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}'


def default_csv_path(input_path: str | Path) -> Path:
    p = Path(input_path)
    return p.with_suffix('.csv')


def decode_object_body(body: bytes) -> dict:
    obj = {
        'full_id': '',
        'local_id': None,
        'pcode': None,
        'state': None,
        'crc': None,
        'scale_x': None, 'scale_y': None, 'scale_z': None,
        'pos_x': None, 'pos_y': None, 'pos_z': None,
        'rot_x': None, 'rot_y': None, 'rot_z': None, 'rot_w': None,
        'update_flags': None,
        'parent_id': '',
        'root_id': '',
        'mesh_id': '',
        'owner_id': '',
        'creator_id': '',
        'group_id': '',
        'asset_id': '',
        'name': '',
        'description': '',
        'notes': '',
    }

    try:
        if len(body) >= 0x44:
            obj['full_id'] = uuid_bytes_to_str(body[0:16])
            obj['local_id'], = unpack_from('<I', body, 0x10)
            obj['pcode'] = body[0x14]
            obj['state'] = body[0x15]
            obj['crc'], = unpack_from('<I', body, 0x16)
            sx, sy, sz = unpack_from('<fff', body, 0x1C)
            px, py, pz = unpack_from('<fff', body, 0x28)
            rx, ry, rz = unpack_from('<fff', body, 0x34)
            obj['scale_x'], obj['scale_y'], obj['scale_z'] = sx, sy, sz
            obj['pos_x'], obj['pos_y'], obj['pos_z'] = px, py, pz
            obj['rot_x'], obj['rot_y'], obj['rot_z'] = rx, ry, rz
            obj['rot_w'] = None
            obj['update_flags'], = unpack_from('<I', body, 0x40)

            if obj['update_flags'] & 0x20 and len(body) >= 0x48:
                parent_id, = unpack_from('<I', body, 0x44)
                obj['parent_id'] = str(parent_id)
                obj['root_id'] = str(parent_id) if parent_id != 0 else ''
        else:
            obj['notes'] = 'body_too_short'
    except Exception as exc:
        obj['notes'] = f'decode_error:{exc}'

    if obj['pcode'] == 9 and obj['full_id']:
        obj['mesh_id'] = obj['full_id']

    return obj


def object_to_discovery_row(
    obj: dict,
    source_file: str,
    record_index: int,
    ref_point: tuple[float, float, float] | None = None,
) -> dict:
    row = {k: '' for k in DISCOVERY_COLUMNS}
    row['source_file'] = source_file
    row['record_index'] = record_index

    for k in row:
        if k in obj and obj[k] is not None:
            row[k] = obj[k]

    parent = row.get('parent_id', '')
    row['is_root'] = 1 if parent in ('', '0', 0) else 0
    row['is_child'] = 0 if row['is_root'] else 1
    row['is_mesh_candidate'] = 1 if row.get('pcode') == 9 else 0

    try:
        px = float(row['pos_x'])
        py = float(row['pos_y'])
        pz = float(row['pos_z'])
        sx = float(row['scale_x'])
        sy = float(row['scale_y'])
        sz = float(row['scale_z'])

        row['bbox_min_x'] = px - sx / 2.0
        row['bbox_min_y'] = py - sy / 2.0
        row['bbox_min_z'] = pz - sz / 2.0
        row['bbox_max_x'] = px + sx / 2.0
        row['bbox_max_y'] = py + sy / 2.0
        row['bbox_max_z'] = pz + sz / 2.0

        if ref_point is not None:
            dx = px - ref_point[0]
            dy = py - ref_point[1]
            dz = pz - ref_point[2]
            row['distance_from_reference'] = math.sqrt(dx * dx + dy * dy + dz * dz)
    except Exception:
        pass

    return row


# -- Readers ------------------------------------------------------------------

def read_object_cache(path: str | Path) -> tuple[HeaderMetaInfo, list[HeaderEntryInfo]]:
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
    data = Path(path).read_bytes()
    offset = 0

    region_id = data[offset:offset + UUID_BYTES]
    offset += UUID_BYTES

    num_entries, = unpack_from('<I', data, offset)
    offset += 4

    entries = []
    for _ in range(num_entries):
        if offset + ENTRY_HEADER_SIZE > len(data):
            break

        hdr = VOCacheEntryHeader.read(data, offset)
        offset += ENTRY_HEADER_SIZE

        if hdr.body_size < 0 or hdr.body_size > MAX_ENTRY_BODY_SIZE:
            print(f'WARNING: bogus body_size {hdr.body_size} for local_id {hdr.local_id}, stopping.')
            break

        body = data[offset:offset + hdr.body_size]
        offset += hdr.body_size
        entries.append(VOCacheEntry(hdr, body))

    return region_id, num_entries, entries


# -- CLI commands -------------------------------------------------------------

def cmd_index(args):
    meta, entries = read_object_cache(args.inputfile)
    print(f'object.cache: {args.inputfile}')
    print(f'Version      : {meta.version}')
    print(f'Address size : {meta.address_size}')
    print(f'Regions found: {len(entries)}')
    print()

    for i, e in enumerate(entries):
        rx = (e.handle >> 32) & 0xFFFFFFFF
        ry = e.handle & 0xFFFFFFFF
        print(f'{i:3d} index={e.index:4d} region=({rx},{ry}) handle=0x{e.handle:016x} time={e.time}')


def cmd_inspect(args):
    region_id, expected, entries = read_slc(args.inputfile)
    print(args.inputfile)
    print(f'Region UUID      : {uuid_bytes_to_str(region_id)}')
    print(f'Expected entries : {expected}')
    print(f'Read entries     : {len(entries)}')
    print()

    for i, e in enumerate(entries[:30]):
        h = e.header
        print(
            f'{i:4d} local_id={h.local_id:10d} crc=0x{h.crc:08x} '
            f'body={h.body_size:5d}B hits={h.hit_count} dupes={h.dupe_count}'
        )
    if len(entries) > 30:
        print(f'... {len(entries) - 30} more entries not shown ...')


def cmd_dump(args):
    _, _, entries = read_slc(args.inputfile)
    target = int(args.localid)

    for e in entries:
        if e.header.local_id == target:
            b = e.body
            obj = decode_object_body(b)

            print(f'local_id {target} body ({len(b)} bytes)')
            print(hexdump(b, 256))
            print()
            print(f"  FullID     : {obj.get('full_id', '')}")
            print(f"  LocalID    : {obj.get('local_id', '')}")
            print(f"  PCode      : {obj.get('pcode', '')}")
            print(f"  State      : {obj.get('state', '')}")
            print(f"  CRC        : {obj.get('crc', '')}")
            print(f"  Position   : {obj.get('pos_x', '')}, {obj.get('pos_y', '')}, {obj.get('pos_z', '')}")
            print(f"  Scale      : {obj.get('scale_x', '')}, {obj.get('scale_y', '')}, {obj.get('scale_z', '')}")
            print(f"  Rotation   : {obj.get('rot_x', '')}, {obj.get('rot_y', '')}, {obj.get('rot_z', '')}")
            print(f"  UpdateFlags: {obj.get('update_flags', '')}")
            print(f"  Owner      : {obj.get('owner_id', '')}")
            print(f"  ParentID   : {obj.get('parent_id', '')}")
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


# -- Entry point --------------------------------------------------------------

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