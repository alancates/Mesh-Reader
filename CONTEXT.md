# Mesh-Reader Project Context

## Goal
Extract geometry (vertices, UVs, skin weights) from Second Life / Firestorm 
mesh assets for attached objects owned by the user.

## Files
- `mesh_reader.py` -- object cache reader (.slc files), commands: index, inspect, dump, list, search
- `mesh_asset.py`  -- mesh asset decoder, exports OBJ + skin.json
- `llsd_binary.py` -- standalone LLSD binary parser

## Key Facts
- Avatar UUID: `1fce2750-76a7-464c-a349-195e4f92c666`
- Cache root:  `C:\Users\alanc\AppData\Local\Firestorm_x64\`
- Object cache: `...\objectcache\objects_XXXX_YYYY.slc`
- Mesh assets:  `...\cache\[UUID[0]]\sl_cache_[UUID]_0.asset`
- Firestorm source: `https://raw.githubusercontent.com/FirestormViewer/phoenix-firestorm/master/indra/`

## Asset File Format (verified by binary analysis)

### File header (12 bytes, little-endian)
```
[0:4]  version       LE uint32 = 1
[4:8]  header_size   LE uint32 = byte length of LLSD header section
[8:12] section_count LE uint32 (number of data sections declared)
[12:]  LLSD binary data, length = header_size
[12+header_size:]  zlib-compressed mesh data sections
```

### LLSD header
A binary-encoded LLSD map. Keys include: `creator`, `date`, `version`,
`high_lod`, `medium_lod`, `low_lod`, `lowest_lod`, `physics_convex`,
`physics_cost_data`, and optionally `skin`.

Each LOD key maps to `{"offset": int, "size": int}` (offsets relative to
`12 + header_size`, i.e. the start of the compressed data block).

`lowest_lod` may also have a `mesh_triangles` key (triangle count).

### Compressed sections
Each section is zlib-compressed. **Important:** Firestorm omits the zlib
adler32 footer, so `zlib.decompress()` fails with error -5. Use
`zlib.decompressobj().decompress(chunk)` instead.

### Decompressed LOD format
LLSD binary: an array of face maps. Each face map has up to 6 keys:

| Key              | Type   | Content |
|------------------|--------|---------|
| Normal           | binary | uint16 LE × 3 × N verts; range [0,65535] maps to [-1,1] |
| Position         | binary | uint16 LE × 3 × N verts; dequantised via PositionDomain |
| PositionDomain   | map    | `{Min: [x,y,z], Max: [x,y,z]}` as LLSD real arrays |
| TexCoord0        | binary | uint16 LE × 2 × N verts; dequantised via TexCoord0Domain |
| TexCoord0Domain  | map    | `{Min: [u,v], Max: [u,v]}` |
| TriangleList     | binary | uint16 LE × (3 × num_tris) — vertex indices |

Dequantisation: `value = min + (uint16 / 65535.0) * (max - min)`

### Incomplete / partially-cached LODs
Some high_lod sections in the cache contain only Normal + Position blobs
filled with `0x7F33` placeholder bytes, with no PositionDomain or
TriangleList. This happens when the asset was not fully downloaded before
being cached. The decoder detects these (missing PositionDomain/TriangleList)
and skips those faces, reporting 0 decodable faces.

### Skin section
Decompresses to an LLSD map with joint names, bind shape matrix, inverse
bind matrices, and per-vertex weight data.

## Usage
```powershell
python mesh_asset.py info <asset_file>
python mesh_asset.py decode <asset_file> --lod [high|medium|low|lowest]
# Outputs: <stem>_<lod>.obj  and  <stem>_skin.json (if skin present)
```

## Where We Stopped
`mesh_asset.py` and `llsd_binary.py` are written and tested. Both committed
to repo. Verified against multiple real cache files:
- `info` command works on all assets
- `decode` works for complete LODs (lowest/low/medium and full high_lod)
- Incomplete high_lod sections handled gracefully (0 faces, helpful message)

### Tested assets
- `sl_cache_0001ecdb-...` — complete lowest/low/medium; incomplete high_lod
- `sl_cache_0002e8f4-...` — complete all LODs including high (2694 verts, 5152 tris, skin)
- `sl_cache_000188e7-...` — small mesh, all LODs complete

## Possible next steps
- Find mesh UUIDs referenced by avatar's attached objects (via object cache / .slc files)
- Batch decode all mesh assets for attached objects into OBJ files
- Parse skin.json to reconstruct rigging / joint weights for Blender import

## Firestorm Source Files Used
- `indra/newview/llvocache.cpp` / `.h`
- `indra/newview/llviewerobject.cpp`
- `indra/newview/llmeshrepository.cpp`
- `indra/llprimitive/llmodel.cpp`
- `indra/llmessage/lldatapacker.cpp`
- `indra/llmessage/llsdserialize.cpp`
- `indra/llfilesystem/lldiskcache.cpp`
