#!/usr/bin/env python3
"""
Mesh-Reader: Firestorm/Second Life object cache reader.
Reads object.cache (index) and objectsXXYY.slc (data) files.
Based on llvocache.h / llvocache.cpp from the Firestorm source.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from struct import unpack_from, calcsize
import argparse
import binascii
import csv
import math
import uuid

# ── Constants from llvocache.cpp ──────────────────────────────────────────────
ENTRY_HEADER_SIZE = 6 * 4  # 6 x S32/U32 = 24 bytes
MAX_ENTRY_BODY_SIZE = 10_000
MAX_NUM_ENTRIES = 128
UUID_BYTES = 16

DISCOVERY_COLUMNS = [
    'source_file', 'record_index', 'local_id', 'full_id', 'parent_id',
    'root_id', 'pcode', 'state', 'update_flags', 'crc', 'name',
    'description', 'owner_id', 'creator_id', 'group_id', 'asset_id',
    'mesh_id', 'is_root', 'is_child', 'is_mesh_candidate', 'pos_x',
    'pos_y', 'pos_z', 'scale_x', 'scale_y', 'scale_z', 'rot_x', 'rot_y',
    'rot_z', 'rot_w', 'distance_from_reference', 'bbox_min_x',
    'bbox_min_y', 'bbox_min_z', 'bbox_max_x', 'bbox_max_y', 'bbox_max_z',
    'notes'
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

    SIZE = calcsize('<IQL')

    @classmethod
    def read(cls, data: bytes, offset: int = 0) -> 'HeaderEntryInfo':
        index, handle, time = unpack_from('<IQL', data, offset)
        return cls(index, handle, time)


@dataclass
class VOCacheEntryHeader:
    """
    24-byte entry header in objectsXXYY.slc

    S32     mLocalID;          //  0
    U32     mCRC;              //  4
    U32     mHitCount;         //  8
    U32     mDupeCount;        // 12
    U32     mCRCChangeCount;   // 16
    S32     mBodySize;         // 20
    """
    local_id: int = 0
    crc: int = 0
    hit_count: int = 0
    dupe_count: int = 0
    crc_change_count: int = 0
    body_size: int = 0

    SIZE = calcsize('<6I')

    @classmethod
    def read(cls, data: bytes, offset: int = 0) -> 'VOCacheEntryHeader':
        local_id, crc, hit_count, dupe_count, crc_change_count, body_size = \
            unpack_from('<6I', data, offset)
        return cls(local_id, crc, hit_count, dupe_count, crc_change_count, body_size)


@dataclass
class VOCacheEntry:
    header: VOCacheEntryHeader
    body: bytes = field(repr=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def hexdump(data: bytes, limit: int = 256) -> str:
    chunk = data[:limit]
    lines = []
    for off in range(0, len(chunk), 16):
        row = chunk[off:off + 16]
        hex_part = ' '.join(f'{b:02x}' for b in row)
        asc_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in row)
        lines.append(f' {off:04x}  {hex_part:<47}  {asc_part}')
    return '\n'.join(lines)


def uuid_bytes_to_str(b: bytes) -> str:
    h = binascii.hexlify(b).decode()
    return f'{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}'


def default_csv_path(input_path: str | Path) -> Path:
    p = Path(input_path)
    return p.with_suffix('.csv')


def decode_entry_fields(entry: VOCacheEntry) -> dict:
    """
    Minimal shared decode path for .slc object bodies.
    Reused by dump/list so field extraction stays in one place.
    """
    h = entry.header
    b = entry.body

    decoded = {
        'local_id': h.local_id,
        'crc': h.crc,
        'full_id': '',
        'parent_id': '',
        'root_id': '',
        'pcode': '',
        'state': '',
        'update_flags': '',
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
        'notes': [],
    }

    if len(b) < 0x44:
        decoded['notes'].append('body_too_short')
        return decoded

    try:
        decoded['full_id'] = uuid_bytes_to_str(b[0:16])

        local_id, = unpack_from('<I', b, 0x10)
        decoded['local_id'] = local_id
        decoded['pcode'] = b[0x14]
        decoded['state'] = b[0x15]

        crc, = unpack_from('<I', b, 0x16)
        decoded['crc'] = crc

        decoded['scale'] = unpack_from('<fff', b, 0x1C)
        decoded['pos'] = unpack_from('<fff', b, 0x28)
        rot_xyz = unpack_from('<fff', b, 0x34)
        decoded['rot'] = (rot_xyz[0], rot_xyz[1], rot_xyz[2], '')

        update_flags, = unpack_from('<I', b, 0x40)
        decoded['update_flags'] = update_flags

        if len(b) >= 0x48:
            parent_id, = unpack_from('<I', b, 0x44)
            decoded['parent_id'] = parent_id
            decoded['root_id'] = local_id if parent_id == 0 else ''

        if decoded['pcode'] == 9:
            decoded['mesh_id'] = decoded['full_id']

    except Exception as exc:
        decoded['notes'].append(f'decode_error={exc}')

    return decoded


def object_to_discovery_row(obj, source_file, record_index, ref_point=None):
    row = {k: '' for k in DISCOVERY_COLUMNS}
    row['source_file'] = source_file
    row['record_index'] = record_index

    decoded = decode_entry_fields(obj)

    row['local_id'] = decoded['local_id']
    row['full_id'] = decoded['full_id']
    row['parent_id'] = decoded['parent_id']
    row['root_id'] = decoded['root_id']
    row['pcode'] = decoded['pcode']
    row['state'] = decoded['state']
    row['update_flags'] = decoded['update_flags']
    row['crc'] = decoded['crc']
    row['name'] = decoded['name']
    row['description'] = decoded['description']
    row['owner_id'] = decoded['owner_id']
    row['creator_id'] = decoded['creator_id']
    row['group_id'] = decoded['group_id']
    row['asset_id'] = decoded['asset_id']
    row['mesh_id'] = decoded['mesh_id']

    parent_id = decoded['parent_id']
    if parent_id != '':
        row['is_root'] = 1 if parent_id == 0 else 0
        row['is_child'] = 1 if parent_id != 0 else 0

    pcode = decoded['pcode']
    if pcode != '':
        row['is_mesh_candidate'] = 1 if pcode == 9 else 0

    pos = decoded['pos']
    scale = decoded['scale']
    rot = decoded['rot']

    if pos is not None:
        row['pos_x'], row['pos_y'], row['pos_z'] = pos

    if scale is not None:
        row['scale_x'], row['scale_y'], row['scale_z'] = scale

    if rot is not None:
        row['rot_x'], row['rot_y'], row['rot_z'], row['rot_w'] = rot

    if pos is not None and scale is not None:
        px, py, pz = pos
        sx, sy, sz = scale
        row['bbox_min_x'] = px - (sx / 2.0)
        row['bbox_min_y'] = py - (sy / 2.0)
        row['bbox_min_z'] = pz - (sz / 2.0)
        row['bbox_max_x'] = px + (sx / 2.0)
        row['bbox_max_y'] = py + (sy / 2.0)
        row['bbox_max_z'] = pz + (sz / 2.0)

    if ref_point is not None and pos is not None:
        dx = pos[0] - ref_point[0]
        dy = pos[1] - ref_point[1]
        dz = pos[2] - ref_point[2]
        row['distance_from_reference'] = math.sqrt(dx * dx + dy * dy + dz * dz)

    row['notes'] = '; '.join(decoded['notes'])
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

    num_entries, = unpack_from('<I', data, offset)
    offset += 4

    entries = []
    for _ in range(num_entries):
        if offset + ENTRY_HEADER_SIZE > len(data):
            break

        hdr = VOCacheEntryHeader.read(data, offset)
        offset += ENTRY_HEADER_SIZE

        if hdr.body_size <= 0 or hdr.body_size > MAX_ENTRY_BODY_SIZE:
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
        ry = e.handle & 0xFFFFFFFF
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
        print(f'[{i:4d}] local_id={h.local_id:10d} '
              f'crc={h.crc:08x} '
              f'body={h.body_size:5d}B '
              f'hits={h.hit_count} '
              f'dupes={h.dupe_count}')
    if len(entries) > 30:
        print(f'... {len(entries) - 30} more entries not shown ...')


def cmd_dump(args):
    """Dump one entry body by local_id with field decoding."""
    _, _, entries = read_slc(args.inputfile)
    target = int(args.localid)

    for e in entries:
        if e.header.local_id == target:
            b = e.body
            decoded = decode_entry_fields(e)

            print(f'local_id={target} body={len(b)} bytes')
            print(hexdump(b, 256))
            print()

            if decoded['full_id']:
                print(f'Object UUID: {decoded["full_id"]}')
            if decoded['parent_id'] != '':
                print(f'Parent ID : {decoded["parent_id"]}')
            if decoded['pcode'] != '':
                print(f'PCode     : {decoded["pcode"]}')
            if decoded['state'] != '':
                print(f'State     : {decoded["state"]}')
            if decoded['update_flags'] != '':
                print(f'Flags     : {decoded["update_flags"]}')
            if decoded['scale'] is not None:
                sx, sy, sz = decoded['scale']
                print(f'Scale     : ({sx}, {sy}, {sz})')
            if decoded['pos'] is not None:
                px, py, pz = decoded['pos']
                print(f'Position  : ({px}, {py}, {pz})')
            if decoded['rot'] is not None:
                rx, ry, rz, rw = decoded['rot']
                print(f'Rotation  : ({rx}, {ry}, {rz}, {rw})')
            if decoded['notes']:
                print(f'Notes     : {"; ".join(decoded["notes"])}')
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
                object_to_discovery_row(e, Path(args.inputfile).name, i, ref_point)
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