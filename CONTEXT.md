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

## Avatar Attachment Mesh UUIDs

### How the cache works
- Avatar attachments are NOT stored in `.slc` region object cache files. They arrive via
  `ObjectUpdate` messages but are excluded from the region cache.
- The `.slc` extra params block (param type `0x30`, sculpt_type=5) stores mesh UUIDs for
  world-rezzed mesh objects. `mesh_reader.py` now parses these correctly.
- Avatar attachment mesh UUIDs must be found another way.

### Finding attachments via session timestamps
The only practical approach with local data only: narrow mesh asset cache files to those
downloaded during the specific Firestorm login session.

- Firestorm.log records session start/end in UTC. Cross-reference with file modification
  times (Windows stores in local time) to get the session window.
- Only **36 assets** were downloaded during the June 6 2026 session.
- The first 16 (modified at session start, 17:59–18:00 local) are the avatar's own
  attachments. They match well-known Maitreya LaraX body rigging (87 joints) and
  other known avatar components.
- Later assets (18:02–18:03) are likely from other avatars entering the region.

### Avatar attachment UUIDs (June 6 2026 session)
First 16 = avatar's own attachments (login batch):
```
e5987904-e617-4f65-0110-33f334979d97  (1042 KB)
f3c83dd0-3e42-fae3-be22-1ed5b4e7c55a  ( 156 KB)
65c3e279-5efb-23bf-1328-d45461d308fd  ( 703 KB)
ac69cdfe-d575-561f-450b-921cce7e9dac  (  23 KB)
1f8b745b-d058-6b72-8257-3c6237e21249  ( 878 KB)
522236f6-3162-3a69-ee42-3923a4713270  (  91 KB)
96e11c60-38a5-bf63-aeed-240738a11c18  ( 491 KB)
d2316aa1-e864-a909-8ce6-55aac0cc7652  ( 127 KB)
317463b6-f891-680a-3425-a479826cf1ca  ( 123 KB)
8e8e7001-be24-01c9-a19a-fb6d08a219b1  ( 393 KB)
f9075e26-a5d6-b42b-f23d-c9696a6a641b  (1499 KB)
d54d0124-a271-26b1-1be5-26060f4b0ab5  ( 286 KB)
6bbbe968-752d-706e-dd02-8fe446626712  ( 285 KB)
889b7d58-e780-b008-1c73-4ca4f3b76c83  (1506 KB)
06329385-fc76-0095-0edc-a3efd972c460  ( 209 KB)
db1391ac-3f8a-d5bf-0d57-51ec14b50bbf  ( 119 KB)
```

### LOD cache completeness issue
Firestorm pre-allocates space for all LOD sections (high/medium/low/lowest) with zeros,
then fills them in as data arrives from the CDN. For this session (brief, ~4 min) only:
- `lowest_lod` and `low_lod` were fully downloaded for most assets
- `medium_lod` for some assets has only the `Normal` blob (incomplete — no position/UVs/triangles)
- `high_lod` is all-zeros for all session assets (never downloaded)

The `get_section_data()` function in `mesh_asset.py` now detects zero-filled sections
(first byte == 0) and returns None, so the exporter silently falls back to a lower LOD.

**To get high-quality mesh geometry**: In Firestorm, set LOD to maximum, zoom the camera
to within 1–2m of the avatar, and wait several minutes for the viewer to cache all LODs.
The mesh files will then have complete high_lod sections.

### Exports
31 of 36 session assets exported to `exports/` directory:
- OBJ files at the best available LOD (mostly `low_lod` or `lowest_lod`)
- `_skin.json` with joint names, bind shape matrix, and inverse bind matrices
- Most OBJ files have very low vertex counts (< 50 verts) due to LOD limitation
- 5 assets have meaningful geometry: f5d27c34 (798v), 426dc98f (580v), 567058e8 (272v),
  ec3584ee (68v), 0e5df72b (106v)

## Possible next steps
- Get high-quality geometry: run Firestorm session with max LOD settings and camera
  zoomed to avatar — wait for cache to fill high_lod sections, then re-export
- Batch export script: `exports/` directory already has session assets; can re-run any time
- Parse skin.json inverse bind matrices and joint hierarchy for Blender rigging import

## Firestorm Source Files Used
- `indra/newview/llvocache.cpp` / `.h`
- `indra/newview/llviewerobject.cpp`
- `indra/newview/llmeshrepository.cpp`
- `indra/llprimitive/llmodel.cpp`
- `indra/llmessage/lldatapacker.cpp`
- `indra/llmessage/llsdserialize.cpp`
- `indra/llfilesystem/lldiskcache.cpp`
