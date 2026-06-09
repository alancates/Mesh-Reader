# Firestorm source references

## Purpose

These are reference files for understanding Firestorm mesh/model and object cache structures,
and translating them into Python for use in mesh_reader.py.

---

## Core mesh/model files

Used to understand mesh face structure, UV maps, and model loading.

- [llmodel.h](https://github.com/FirestormViewer/phoenix-firestorm/blob/master/indra/llprimitive/llmodel.h)
- [llmodel.cpp](https://github.com/FirestormViewer/phoenix-firestorm/blob/master/indra/llprimitive/llmodel.cpp)
- [llmodelloader.h](https://github.com/FirestormViewer/phoenix-firestorm/blob/master/indra/llprimitive/llmodelloader.h)
- [llmodelloader.cpp](https://github.com/FirestormViewer/phoenix-firestorm/blob/master/indra/llprimitive/llmodelloader.cpp)

---

## Object cache files

Used to understand the binary .slc (object cache) format — entry layout, header fields,
and how object data is stored and retrieved by the viewer.

- [llvocache.h](https://github.com/FirestormViewer/phoenix-firestorm/blob/master/indra/newview/llvocache.h)
- [llvocache.cpp](https://github.com/FirestormViewer/phoenix-firestorm/blob/master/indra/newview/llvocache.cpp)
- [llviewerobject.h](https://github.com/FirestormViewer/phoenix-firestorm/blob/master/indra/newview/llviewerobject.h)
- [llviewerobject.cpp](https://github.com/FirestormViewer/phoenix-firestorm/blob/master/indra/newview/llviewerobject.cpp)

### Key findings from llvocache.cpp

- Each cache entry begins with a local ID (U32) and CRC (U32)
- Object position is stored as three F32 values (x, y, z) in a LLVector3
- Object scale is stored as three F32 values
- Object rotation is stored as a LLQuaternion (4x F32)
- The entry count and entry offsets are stored in the file header
- `LLVOCacheEntry::updateEntry()` shows what fields are written per object
- `LLVOCachePartition` manages spatial partitioning but is not part of the binary layout

### Key findings from llviewerobject.cpp

- `LLViewerObject::processUpdateMessage()` decodes the object update packets
- Object type/pcode is a single byte identifying the primitive type
- Position, scale, and rotation are the primary spatial fields available in cache entries
- Text fields (name, description) are not stored in the .slc binary; they come from the sim

---

## How these files informed mesh_reader.py

The `list` subcommand in mesh_reader.py exports a summary of all objects decoded from a
single .slc file to CSV. The field layout — local_id, crc, x, y, z, scale_x, scale_y,
scale_z — was derived from the binary structure described in llvocache.h and llvocache.cpp.

Fields not available in the cache binary (such as object name or description) are left
blank in the CSV output rather than filled with placeholder data.
