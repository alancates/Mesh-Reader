# Project plan

## Goal: 

Read and export Second Life mesh cached files into a Blender-importable format that preserves geometry, UVs, and vertex weights.

## MVP

- [ ] Identify the mesh cache file format used by Second Life / Firestorm
- [ ] Parse and decode the mesh data from cache files
- [ ] Export geometry, UVs, and vertex weights into a Blender-importable format
- [ ] Provide a way to browse/search cache contents and select the correct object by name, local ID, UUID, or other metadata before export
- [ ] Confirm imported mesh in Blender preserves geometry, UVs, and weights

## Later ideas

- [ ] Support additional export formats (FBX, GLTF)
- [ ] Batch processing of multiple cache files
- [ ] Simple GUI interface
- [ ] Preserve material/texture data where possible

## Status log

- 2026-06-06: Repository created. README and PROJECT.md added.

- 2026-06-06: Binary format fully decoded. Position/Scale/Rotation extracting correctly from .slc files. Next: add `list` command to export all objects to CSV.
