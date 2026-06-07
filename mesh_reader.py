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

# ── Constants from llvocache.cpp ──────────────────────────────────────────────
ENTRY_HEADER_SIZE   = 6 * 4      # 6 x S32/U32 = 24 bytes
MAX_ENTRY_BODY_SIZE = 10_000
MAX_NUM_ENTRIES     = 128
UUID_BYTES          = 16

# ── Structs ───────────────────────────────────────────────────────────────────

@dataclass
class HeaderMetaInfo:
    """First 8 bytes of object.cache"""
    version:      int = 0
    address_size: int = 0

    SIZE = calcsize('<II')  # 8 bytes

    @classmethod
    def read(cls, data: bytes, offset: int = 0) -> 'HeaderMetaInfo':
        version, address_size = unpack_from('<II', data, offset)
        return cls(version, address_size)


@dataclass
class HeaderEntryInfo:
    """16 bytes per region entry in object.cache"""
    index:  int = 0
    handle: int = 0
    time:   int = 0

    SIZE = calcsize('<iQI')  # 16 bytes

    @classmethod
    def read(cls, data: bytes, offset: int = 0) -> 'HeaderEntryInfo':
        index, handle, time = unpack_from('<iQI', data, offset)
        return cls(index, handle, time)


@dataclass
class VOCacheEntryHeader:
    """24-byte header preceding each object body in the .slc file"""
    local_id:         int = 0
    crc:              int = 0
    hit_count:        int = 0
    dupe_count:       int = 0
    crc_change_count: int = 0
    body_size:        int = 0

    @classmethod
    def read(cls, data: bytes, offset: int = 0) -> 'VOCacheEntryHeader':
        local_id, crc, hit_count, dupe_count, crc_change_count, body_size = \
            unpack_from('<IIiiiI', data, offset)
        return cls(local_id, crc, hit_count, dupe_count,
                   crc_change_count, body_size)


@dataclass
class VOCacheEntry:
    header: VOCacheEntryHeader
    body:   bytes


# ── Helpers ───────────────────────────────────────────────────────────────────

def hexdump(data: bytes, limit: int = 256) -> str:
    chunk = data[:limit]
    lines = []
    for off in range(0, len(chunk), 16):
        row = chunk[off:off+16]
        hex_part = ' '.join(f'{b:02x}' for b in row)
        asc_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in row)
        lines.append(f'  {off:04x}  {hex_part:<47}  {asc_part}')
    return '\n'.join(lines)


def uuid_bytes_to_str(b: bytes) -> str:
    h = binascii.hexlify(b).decode()
    return f'{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}'


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
        if entry.time == 0:       # INVALID_TIME — empty slot
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
        ry =  e.handle        & 0xFFFFFFFF
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
        print(f'  ... {len(entries)-30} more entries not shown ...')


def cmd_dump(args):
    """Dump one entry body by local_id."""
    _, _, entries = read_slc(args.inputfile)
    target = int(args.localid)
    for e in entries:
        if e.header.local_id == target:
            print(f'local_id={target}  body={len(e.body)} bytes')
            print(hexdump(e.body, 256))
            return
    print(f'local_id {target} not found.')


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
    p.add_argument('localid',   help='Local object ID to dump')

    return parser


def main():
    args = build_parser().parse_args()
    if   args.command == 'index':   cmd_index(args)
    elif args.command == 'inspect': cmd_inspect(args)
    elif args.command == 'dump':    cmd_dump(args)


if __name__ == '__main__':
    main()