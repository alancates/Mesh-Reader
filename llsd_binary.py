"""
Standalone LLSD binary format parser.

Implements the Linden Lab Structured Data binary encoding used in Second Life
mesh assets and other SL/Firestorm file formats.

Type bytes:
  { } = map start/end    [ ] = array start/end
  k   = key (4-byte BE len + UTF-8)
  i   = int32 (4-byte BE)
  r   = real64 (8-byte BE)
  u   = UUID (16 bytes)
  s   = string (4-byte BE len + UTF-8)
  b   = binary (4-byte BE len + raw bytes)
  d   = date (8-byte BE double, seconds since epoch)
  l   = URI (4-byte BE len + UTF-8)
  1   = true
  0   = false
  !   = undef
"""

import struct
import uuid as _uuid
from datetime import datetime, timezone


class ParseError(Exception):
    pass


class IncompleteData(Exception):
    """Raised when the data stream ends or has unexpected bytes mid-structure."""
    pass


def _read_key(data, pos):
    if pos >= len(data):
        raise IncompleteData(f"unexpected end at {pos:#x}")
    if data[pos:pos+1] != b'k':
        raise IncompleteData(f"expected key 'k' at {pos:#x}, got {data[pos]:#x}")
    pos += 1
    length = struct.unpack_from('>I', data, pos)[0]
    pos += 4
    key = data[pos:pos+length].decode('utf-8')
    return key, pos + length


def _parse(data, pos):
    if pos >= len(data):
        raise ParseError(f"unexpected end of data at pos {pos}")
    t = data[pos:pos+1]
    pos += 1

    if t == b'{':
        count = struct.unpack_from('>I', data, pos)[0]
        pos += 4
        result = {}
        for _ in range(count):
            try:
                key, pos = _read_key(data, pos)
                value, pos = _parse(data, pos)
                result[key] = value
            except IncompleteData:
                # Partial map (e.g. incompletely cached mesh LOD) — return what we have
                result['__incomplete__'] = True
                return result, pos
        if data[pos:pos+1] != b'}':
            raise ParseError(f"expected '}}' at {pos:#x}, got {data[pos]:#x}")
        pos += 1
        return result, pos

    if t == b'[':
        count = struct.unpack_from('>I', data, pos)[0]
        pos += 4
        result = []
        for _ in range(count):
            try:
                value, pos = _parse(data, pos)
                result.append(value)
            except (IncompleteData, ParseError):
                break
        if data[pos:pos+1] == b']':
            pos += 1
        return result, pos

    if t == b'i':
        value = struct.unpack_from('>i', data, pos)[0]
        return value, pos + 4

    if t == b'r':
        value = struct.unpack_from('>d', data, pos)[0]
        return value, pos + 8

    if t == b'u':
        raw = data[pos:pos+16]
        value = str(_uuid.UUID(bytes=raw))
        return value, pos + 16

    if t == b's' or t == b'l':
        length = struct.unpack_from('>I', data, pos)[0]
        pos += 4
        value = data[pos:pos+length].decode('utf-8')
        return value, pos + length

    if t == b'b':
        length = struct.unpack_from('>I', data, pos)[0]
        pos += 4
        return bytes(data[pos:pos+length]), pos + length

    if t == b'd':
        ts = struct.unpack_from('>d', data, pos)[0]
        try:
            value = datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            value = ts
        return value, pos + 8

    if t == b'1':
        return True, pos

    if t == b'0':
        return False, pos

    if t == b'!':
        return None, pos

    raise ParseError(f"unknown type byte {t!r} at {pos-1:#x}")


def parse(data, offset=0):
    """Parse LLSD binary data starting at offset. Returns the parsed value."""
    value, _ = _parse(data, offset)
    return value


def parse_with_end(data, offset=0):
    """Parse LLSD binary data. Returns (value, bytes_consumed)."""
    value, end = _parse(data, offset)
    return value, end - offset
