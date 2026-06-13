# Mesh-Reader Project Context

## Goal
Extract geometry (vertices, UVs, skin weights) from Second Life / Firestorm 
mesh assets for attached objects owned by the user.

## Files
- `mesh_reader.py` -- object cache reader (.slc files), commands: index, inspect, dump, list, search
- `mesh_asset.py`  -- mesh asset decoder, exports OBJ + skin.json
- `llsd_binary.py` -- standalone LLSD binary parser
- `batch_export_june6.py` -- batch export the 16 known June 6 attachment UUIDs
- `clear_attachment_cache.py` -- delete/backup the 16 June 6 cache files to force re-download
- `import_to_blender.py` -- Blender headless script: imports all OBJ from a folder into one .blend
- `run_import_blender.bat` -- launches import_to_blender.py via blender-launcher.exe

## Key Facts
- Avatar UUID: `1fce2750-76a7-464c-a349-195e4f92c666`
- Cache root:  `C:\Users\alanc\AppData\Local\Firestorm_x64\`
- Object cache: `...\objectcache\objects_XXXX_YYYY.slc`
- Mesh assets:  `...\cache\[UUID[0]]\sl_cache_[UUID]_0.asset`
- Firestorm source: `https://raw.githubusercontent.com/FirestormViewer/phoenix-firestorm/master/indra/`
- Blender: `C:\Users\alanc\Downloads\Blender\blender-5.1.2-windows-x64\blender-5.1.2-windows-x64\blender-launcher.exe`

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

### Zero-filled sections (Firestorm 7.2.4+)
Firestorm pre-allocates space for all LOD sections with zeros when a cache
file is first created, then fills them in as data arrives from CDN.
`get_section_data()` detects `compressed[0] == 0` and returns None.

### Skin section
Decompresses to an LLSD map with joint names, bind shape matrix, inverse
bind matrices, and per-vertex weight data.

## Usage
```powershell
python mesh_asset.py info <asset_file>
python mesh_asset.py decode <asset_file> --lod [high|medium|low|lowest]
# Outputs: <stem>_<lod>.obj  and  <stem>_skin.json (if skin present)
```

## Critical Discovery: Self-Avatar vs Third-Party Caching

**The viewer uses `LLVOAvatarSelf` for your own avatar** — a separate rendering
path that downloads mesh directly from CDN into RAM, bypassing the `sl_cache_*`
disk cache entirely. This is why your own body mesh never appears in the cache
files with complete high_lod data, no matter how close the camera is.

**The fix**: log in with a second account (Naltees Brim) in the same region.
Brim's viewer sees Nalates as a third-party avatar (`LLVOAvatar`), which DOES
write full high_lod data to disk cache. All subsequent mesh extraction uses
this approach.

## Workflow for Extracting Avatar Mesh (Confirmed Working)

1. Log in as Nalates Urriah. Strip avatar to only the items you want to extract.
2. Log in as Naltees Brim (second account, same Firestorm install, same cache).
3. Stand Brim close to Nalates. Set Brim's LOD to maximum (4.0).
4. Wait ~30 seconds for Brim's viewer to cache Nalates' mesh at high_lod.
5. Run the extraction script to find new rigged HIGH OK files.
6. Export to OBJ + skin.json, import into Blender via `run_import_blender.bat`.

## Identified Mesh UUIDs (June 9 2026 session)

### Nalates naked body session (08:58 local)
Nalates wore only the Maitreya LaraX body (no head, no attachments).
Captured via Brim standing close.

| UUID | Size | Verts | Tris | Identity |
|------|------|-------|------|----------|
| `0d9cb017` | 4559KB | 212,681 | 150,765 | **Maitreya LaraX main body** |
| `f993e280` | 2106KB | 70,330 | 135,433 | body part (TBD) |
| `d61974b2` | 1874KB | 62,828 | 120,465 | body part (TBD) |
| `70a508dc` | 1873KB | 62,709 | 120,465 | body part (TBD) |
| `20b81a3f` | 1873KB | 62,691 | 120,465 | body part (TBD) |
| `83bf5228` | 1873KB | 62,682 | 120,465 | body part (TBD) |
| `8f0fb98e` | 1818KB | 62,573 | 115,381 | body part (TBD) |
| `7c618493` | 1818KB | 62,573 | 115,381 | body part (TBD) |

### Body + head session (08:13 local)
Nalates wore body + GAEG head only.

| UUID | Size | Verts | Tris | Identity |
|------|------|-------|------|----------|
| `dd90f477` | 1772KB | 23,474 | 44,152 | GAEG Head |
| `59a05245` | 617KB | 7,777 | 14,596 | Head part 2 |
| `c533a3ec` | 305KB | 4,774 | 9,216 | Ears |
| `07b4d3ab` | 272KB | 5,736 | 4,922 | Eye lashes |
| `97070041` | 114KB | 2,178 | 3,570 | Teeth |

### Body + head + hands session (08:14 local)

| UUID | Size | Verts | Tris | Identity |
|------|------|-------|------|----------|
| `49559930` | 1103KB | 41,320 | 77,218 | Left hand |
| `9586e146` | 1121KB | 41,320 | 77,218 | Right hand |

### Earlier session with full outfit (07:45 local)

| UUID | Size | Verts | Tris | Identity |
|------|------|-------|------|----------|
| `6c6e870b` | 2414KB | 64,032 | 59,206 | Jacket |
| `211ebfbb` | 909KB | 15,936 | 21,591 | Cum lower |
| `a0a71e17` | 784KB | 23,631 | 28,464 | Vagina |
| `1b10d327` | 782KB | 12,927 | 23,004 | Cum upper |
| `bbb3dc28` | 685KB | 11,225 | 18,552 | Cum more |
| `bac5b6ae` | 614KB | 15,850 | 23,735 | Inner vagina |

## Exports
All exports in `J:\Claude Data\Mesh-Reader\exports\`:

| Folder | Contents |
|--------|----------|
| `june6_best\` | June 6 session assets at best available LOD (all low/lowest, minimal geometry) |
| `brim_session\` | First Brim capture — full outfit, 121 files |
| `body_only\` | Head-only strip session (5 files: GAEG head, ears, lashes, teeth) |
| `body_only2\` | Body+head session (32K-vert body candidates + head parts) |
| `naked_body\` | **Best export** — naked body only, 91 files, main body confirmed present |

### Blender import
`run_import_blender.bat` runs `import_to_blender.py` headlessly and saves
`naked_body.blend` in `exports\naked_body\`. Currently points at `naked_body\`.
Edit `OBJ_DIR` in `import_to_blender.py` to change source folder.

## Coordinate System (Critical — do not re-derive)

**SL avatar local space**: X = forward (avatar faces +X), Y = left/right (arm span in T-pose), Z = up.

**OBJ import settings**: `forward_axis='Y', up_axis='Z'` → preserves SL local coords as-is in Blender.

**Blender/Avastar convention**: avatar faces **−Y** (toward viewer in front view).

**Fix**: apply −90° rotation around Z to the `bind_shape_matrix` before setting `obj.matrix_world`:
```python
R = Matrix([[ 0, 1, 0, 0], [-1, 0, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
return R @ M
```
This maps SL local +X (avatar forward) → Blender −Y (toward viewer). **Confirmed working.**

**Do not attempt**: applying C @ M @ C.inv or any per-part COLLADA conversion — causes severely
twisted mesh because different body parts use different local axis conventions.

## Maitreya Body — Known Limitation (do not re-derive)

The extracted Maitreya LaraX body (`weighted_parts.blend`) has **correct orientation** and
**correct geometry** but does **not** match the user's custom SL avatar shape. The shape
difference is caused by **collision volume bones** (BELLY, BUTT, CHEST, LEFT_PEC, RIGHT_PEC,
LOWER_BACK, PELVIS, leg volumes) which drive Maitreya's proprietary morphs via avatar shape
sliders. These morphs are **not in the cache** — they are in the Maitreya dev kit only.

**What does NOT work** (confirmed by user — do not suggest again):
- Repositioning skeleton bones to match the user's shape
- Importing the user's SL shape XML into Avastar to resize the mesh
- Any approach that modifies bones or the armature to correct the mesh shape

The only path to a correctly-shaped Maitreya body is the **official Maitreya dev kit**.
The user has applied for kit access via the Maitreya in-world group; no response yet (as of 2026-06-13).

**Maitreya dev kit is not included in the purchased body package.**
**The viewer cannot export Maitreya assets** (not full-perm).
**No workaround exists** without the dev kit.

## Collision Volume Bones — Technical Note

SL fitted mesh uses these collision volume bones: BELLY, BUTT, CHEST, LEFT_PEC, RIGHT_PEC,
LOWER_BACK, PELVIS, L/R_UPPER_LEG, L/R_LOWER_LEG. Their `inv_bind_matrix` values in the
skin.json are **not in world-meter space** (BELLY appears at ~7.89m, LEFT_PEC at ~28m).
They operate in a proprietary deformation coordinate system and cannot be reconstructed
from cache data alone.

## Legacy Body Extraction — Validated Pipeline

The Legacy body (worn by Nalates in-world, captured by Brim) was extracted from cache and
imported into Blender. The pipeline is validated against the official Legacy dev kit:

- **Dev kit arm span** (Y axis): ±0.621m = 1.242m total  
- **Extracted Body Upper arm span** (scY = 1.2454): 1.245m total  
- **Match**: within 3mm ✓

The Legacy dev kit is freely available (no approval required):
`J:\Second Life\Legacy\[MESHBODY] Legacy (f) All Archetypes 2.5.3 (Blender)\`

### Legacy Body Parts in Cache

| Part Name | UUID prefix | Notes |
|-----------|-------------|-------|
| Body Base A | `9dbb65e1` | BOM layer — only 2 joints (mChest, mHead) |
| Body Base B | `0d2d4a1b` | BOM layer — only 2 joints (mChest, mHead) |
| Body Upper | `a2a889c4` | Main visual body — chest/torso/arms |
| Body Lower | `5c47e563` | Main visual body — hips/thighs |
| Torso A | `f500900f` | Torso detail layer |
| Torso B | `3fa38e76` | Torso detail layer |
| Legs | `16f1226d` | Leg detail |
| Mid Body | `94c0195a` | Mid-section |
| Body C | `bc14f1b3` | Additional body layer |
| Extremities | `72236dc8` | Hands/feet/extremities |
| Arms | `328d3cc3` | Arm detail |
| Body D | `e79eba2a` | Additional body layer |

**Primary visual mesh**: Body Upper + Body Lower + Extremities  
**BOM (Bakes on Mesh) layers**: Body Base A + B — ignore for shape/clothing work

### Legacy Dev Kit Body Dimensions (Mannequin archetype, Bare Foot)
- Height Z: −0.006 to 1.869m (≈ 1.875m total, feet to top of neck)
- Arm span Y: ±0.621m (1.242m total)
- Depth X: −0.149 to 0.200m (belly protrudes more than back)
- Vertex count: 58,555 per archetype
- Joint count: 74

### Legacy Archetypes (all same bounding box, different internal shape)
- Mannequin (standard reference), Perky, Perky Petite, Perky Mannequin
- Pinup × Bombshell, Pinup × Pushup, Pregnancy
- Foot variants: Bare Foot, Low Foot, Mid Foot, High Foot, Ouch Foot, Pointe Foot

**User wears**: Special Edition (with foot variants) — visible in dev kit Scene Collection.

## Completed Milestones (June 2026)
- Scale fixed via bind_shape_matrix applied as Blender world matrix
- Body parts identified and assembled in `assembled_basic.blend`
- Vertex weight decoder implemented in `mesh_asset.py` (3-byte format:
  U8 joint index + U16LE weight, 0xFF terminator for <4 influences)
- Weights extracted for all 12 Maitreya body parts and applied as Blender vertex groups
- `weighted_parts.blend` — all parts separately imported with correct vertex groups
- **Orientation fix**: −90° Z rotation applied in bind_matrix() — avatar now faces −Y in Blender
- Legacy body extracted and validated against dev kit (arm span matches within 3mm)
- `legacy_body.blend` — all 12 Legacy parts imported with weights and correct orientation

## Blender Files
| File | Contents |
|------|----------|
| `naked_body_Parts.blend` | Original grid import with parts identified by red material |
| `assembled.blend` | All parts assembled using bind_shape_matrix, grid layout |
| `assembled_basic.blend` | Cleaned up: Body (joined upper+lower+breasts), feet variants, vagina |
| `weighted_parts.blend` | Maitreya body — 12 parts with vertex groups, bound to Avastar rig, orientation fixed |
| `exports/legacy/legacy_body.blend` | Legacy body — 12 parts with vertex groups, orientation fixed, validated |

## Scripts
| Script | Purpose |
|--------|---------|
| `run_apply_weights.bat` | Runs `apply_weights_blender.py` via blender.exe --factory-startup |
| `apply_weights_blender.py` | Maitreya: imports OBJs, applies bind_shape_matrix + −90° Z rotation + vertex weights |
| `run_legacy_blender.bat` | Runs `apply_weights_legacy.py` via blender.exe --factory-startup |
| `apply_weights_legacy.py` | Legacy: same pipeline as Maitreya script, saves legacy_body.blend |
| `batch_export_weights.py` | Re-exports all 12 body part OBJ + skin.json with vertex weights |
| `run_assemble_blender.bat` | Runs `assemble_in_blender.py` to produce assembled.blend |

## Known Issues / Next Steps
- **Maitreya shape distortion**: base mesh does not match user's custom SL avatar shape —
  requires Maitreya dev kit (user has applied, awaiting response)
- **Remaining body parts**: ~79 unidentified UUIDs from the naked body session
  (likely alpha layers, LOD variants, physics meshes)
- **Clothing workflow**: blocked on getting a correctly-shaped reference body
  (either Maitreya dev kit or accept Legacy body as alternative)

## Firestorm Source Files Used
- `indra/newview/llvocache.cpp` / `.h`
- `indra/newview/llviewerobject.cpp`
- `indra/newview/llmeshrepository.cpp`
- `indra/llprimitive/llmodel.cpp`
- `indra/llmessage/lldatapacker.cpp`
- `indra/llmessage/llsdserialize.cpp`
- `indra/llfilesystem/lldiskcache.cpp`
