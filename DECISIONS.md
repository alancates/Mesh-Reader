# Decisions

Each entry records one important choice: what we decided, why, and what we considered but rejected.

---

## 2026-06-06 – Project approach

- Decision: Build a standalone tool (not a plugin) to read Second Life / Firestorm mesh cache files and export them.
- Why: Easier to develop and test independently; no dependency on the viewer being open.
- Alternatives considered: Firestorm plugin/addon, Python script inside Blender.

## 2026-06-06 – Primary output format

- Decision: Target OBJ as the first export format.
- Why: OBJ is universally supported by Blender and most 3D tools; simplest to implement.
- Alternatives considered: FBX (more complex), GLTF (better for future but harder to start with).

## 2026-06-06 – Language / stack

- Decision: TBD — to be decided in first working session.
- Options: Python (easiest for file parsing and Blender compatibility), PHP (familiar but not ideal for binary parsing), C# or C++.
