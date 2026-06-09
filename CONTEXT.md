# Mesh-Reader Project Context

## Goal
Extract geometry (vertices, UVs, skin weights) from Second Life / Firestorm 
mesh assets for attached objects owned by the user.

## Files
- `mesh_reader.py` -- object cache reader (.slc files), commands: index, inspect, dump, list, search
- `mesh_asset.py`  -- mesh asset decoder, exports OBJ + skin.json + weights.json
- `llsd_binary.py` -- standalone LLSD binary parser

## Key Facts
- Avatar UUID: `1fce2750-76a7-464c-a349-195e4f92c666`
- Cache root:  `C:\Users\alanc\AppData\Local\Firestorm_x64\`
- Object cache: `...\objectcache\objects_XXXX_YYYY.slc`
- Mesh assets:  `...\cache\[UUID[0]]\sl_cache_[UUID]_0.asset`
- Firestorm source: `https://raw.githubusercontent.com/FirestormViewer/phoenix-firestorm/master/indra/`

## Where We Stopped
`mesh_asset.py` is written but untested. Next step:
1. Run in PowerShell to find sample asset files:
   `Get-ChildItem "C:\Users\alanc\AppData\Local\Firestorm_x64\cache" -Recurse -Filter "sl_cache_*_0.asset" | Select-Object -First 5 | Format-Table FullName, Length`
2. Upload one to Claude and test the decoder with:
   `python mesh_asset.py decode sl_cache_UUID_0.asset --info`

## Firestorm Source Files Used
- `indra/newview/llvocache.cpp` / `.h`
- `indra/newview/llviewerobject.cpp`
- `indra/newview/llmeshrepository.cpp`
- `indra/llprimitive/llmodel.cpp`
- `indra/llmessage/lldatapacker.cpp`
- `indra/llmessage/llsdserialize.cpp`
- `indra/llfilesystem/lldiskcache.cpp`
