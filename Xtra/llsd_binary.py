"""
llsd_binary.py  --  Fast LLSD binary parser and inventory UUID->name lookup.

Format (from llsdserialize.cpp LLSDBinaryParser::doParse):
  '!'        undef
  '0'/'1'    bool
  'i' +4B    S32 big-endian
  'r' +8B    F64 big-endian
  'u' +16B   UUID bytes
  's' +4B +N string (4-byte BE length + UTF-8)
  'k' +4B +N key   (same encoding as string, used inside maps)
  'b' +4B +N binary blob
  'd' +8B    date (F64 seconds since epoch)
  'l' +4B +N URI string
  '[' +4B  items ']'   array  (4-byte BE count, then items, then ']')
  '{' +4B  pairs '}'   map    (4-byte BE count, then key+value pairs, then '}')
"""

from __future__ import annotations
import struct, binascii, gzip
from pathlib import Path


def _uuid(b: bytes) -> str:
    h = binascii.hexlify(b).decode()
    return f'{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}'


class _Parser:
    __slots__ = ('data', 'pos')

    def __init__(self, data: bytes, start: int = 0):
        self.data = data
        self.pos  = start

    # ── primitives ──────────────────────────────────────────────────────────

    def _byte(self) -> int:
        b = self.data[self.pos]
        self.pos += 1
        return b

    def _read(self, n: int) -> bytes:
        b = self.data[self.pos:self.pos + n]
        self.pos += n
        return b

    def _u32(self) -> int:
        v, = struct.unpack_from('>I', self.data, self.pos)
        self.pos += 4
        return v

    def _s32(self) -> int:
        v, = struct.unpack_from('>i', self.data, self.pos)
        self.pos += 4
        return v

    def _f64(self) -> float:
        v, = struct.unpack_from('>d', self.data, self.pos)
        self.pos += 8
        return v

    def _str(self) -> str:
        n = self._u32()
        return self._read(n).decode('utf-8', errors='replace') if n else ''

    # ── value dispatch ───────────────────────────────────────────────────────

    def value(self):
        c = chr(self._byte())

        if c == '{':                          # map
            count = self._u32()
            result = {}
            while True:
                kc = chr(self._byte())
                if kc == '}':
                    break
                if kc == 'k':
                    key = self._str()
                elif kc in ('"', "'"):
                    # notation-style quoted key (rare but handled)
                    key = self._quoted_str(kc)
                else:
                    raise ValueError(f'Bad key type {kc!r} at {self.pos-1}')
                result[key] = self.value()
            return result

        if c == '[':                          # array
            count = self._u32()
            result = []
            while self.data[self.pos:self.pos+1] != b']':
                result.append(self.value())
            self.pos += 1                     # consume ']'
            return result

        if c == '!':   return None
        if c == '0':   return False
        if c == '1':   return True
        if c == 'i':   return self._s32()
        if c == 'r':   return self._f64()
        if c == 'u':   return _uuid(self._read(16))
        if c == 's':   return self._str()
        if c == 'b':   n = self._u32(); return self._read(n)   # binary blob
        if c == 'd':   return self._f64()                      # date as epoch float
        if c == 'l':   return self._str()                      # URI
        if c in ('"', "'"): return self._quoted_str(c)

        raise ValueError(f'Unknown LLSD type {c!r} (0x{ord(c):02x}) at pos {self.pos-1}')

    def _quoted_str(self, delim: str) -> str:
        """Notation-style quoted string -- scan to closing delimiter."""
        start = self.pos
        d = ord(delim)
        while self.pos < len(self.data) and self.data[self.pos] != d:
            if self.data[self.pos] == ord('\\'):
                self.pos += 1
            self.pos += 1
        s = self.data[start:self.pos].decode('utf-8', errors='replace')
        self.pos += 1   # closing delimiter
        return s


def parse(data: bytes, offset: int = 0):
    """Parse LLSD binary from *data* starting at *offset*. Returns Python object."""
    return _Parser(data, offset).value()


# ── Inventory loader ─────────────────────────────────────────────────────────

def load_inventory(path: str | Path) -> dict[str, dict]:
    """
    Load a Firestorm *.inv.llsd.gz file and return a dict:
        { asset_id: {'name': str, 'desc': str, 'inv_type': str,
                     'type': str, 'item_id': str} }

    The file format is: 4-byte S32 version + LLSD binary blob.
    Only 'object' inv_type items are included (inv_type == 'object').
    """
    raw = Path(path).read_bytes()
    if path.endswith('.gz') or str(path).endswith('.gz'):
        import io
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as f:
            raw = f.read()

    # skip 4-byte version prefix
    inv = parse(raw, offset=4)

    items = inv.get('items', [])
    lookup: dict[str, dict] = {}

    for item in items:
        if not isinstance(item, dict):
            continue
        asset_id  = item.get('asset_id',  '')
        item_id   = item.get('item_id',   '')
        name      = item.get('name',      '')
        desc      = item.get('desc',      '')
        inv_type  = item.get('inv_type',  '')
        itype     = item.get('type',      '')

        if asset_id:
            lookup[asset_id] = {
                'name':     name,
                'desc':     desc,
                'inv_type': inv_type,
                'type':     itype,
                'item_id':  item_id,
            }
        # also index by item_id for cross-referencing
        if item_id and item_id != asset_id:
            lookup[item_id] = lookup.get(asset_id) or {
                'name':     name,
                'desc':     desc,
                'inv_type': inv_type,
                'type':     itype,
                'item_id':  item_id,
            }

    return lookup
