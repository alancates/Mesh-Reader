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

2026-06-08 – Vertex weights requirement
---------------------------------------

* Decision: Preserve and export vertex weight data when available in mesh assets.
* Why: Vertex weights are required for proper rigging / deformation and are necessary for character or weighted mesh recovery.
* Consequence: OBJ can remain an early geometry-export format, but a weight-capable format or sidecar export will be needed for full fidelity.
* Alternatives considered: Ignore weights for first version; export geometry only.

## 2026-06-11 – Viewer compilation

- Decision: Do not compile a modified Firestorm viewer.
- Why: The build is a multi-day effort (large dependency tree, Visual Studio toolchain, 1–3 hour builds), and the export restrictions we need to bypass are already circumvented by reading cache files directly. No capability gap justifies the cost.
- Alternatives considered: Building Firestorm from source with export-permission checks removed from `llfloatermodelpreview.cpp` and `llviewermenufile.cpp`.

## 2026-06-12 – Coordinate system / orientation fix

- Decision: Apply a −90° rotation matrix around Z to the bind_shape_matrix before setting obj.matrix_world in Blender.
- Why: SL avatar local space has X=forward (avatar faces +X). OBJ import with forward_axis='Y'/up_axis='Z' preserves SL local coords. Blender/Avastar expects avatar facing −Y. The R matrix (−90° Z) maps SL +X → Blender −Y. User confirmed: "Rotation is fixed."
- Alternatives rejected:
  - C @ M @ C.inv (COLLADA-style conversion): caused severely twisted mesh — different body parts use different local axis conventions, so a blanket conversion is wrong.
  - Rotating the mesh manually 90° after import: correct result but not reproducible in script.
- Code: `R = Matrix([[0,1,0,0],[-1,0,0,0],[0,0,1,0],[0,0,0,1]]); return R @ M`

## 2026-06-12 – Maitreya shape correction approaches rejected

- Decision: Do not attempt to correct Maitreya body shape via bone repositioning, Avastar shape import, or any armature-based approach.
- Why: The shape difference between the extracted Maitreya base mesh and the user's SL avatar is caused by Maitreya's proprietary collision-volume morphs. These are driven by avatar shape sliders in-world but require morph targets from the Maitreya dev kit — they are not present in the cache. Importing the user's SL shape XML into Avastar only scales skeleton bones (height, limb lengths); it does not drive Maitreya-specific morphs. User explicitly confirmed these approaches are wrong.
- Correct path: Obtain the official Maitreya dev kit (user has applied via in-world group, awaiting approval).
- Alternatives rejected: bone repositioning, Avastar shape slider import, collision volume bone manipulation.

## 2026-06-13 – Legacy body as validated alternative reference

- Decision: Use the freely available Legacy dev kit body as the validated reference while waiting for Maitreya dev kit access.
- Why: The Legacy dev kit requires no approval and is already on disk. The extracted Legacy cache body was validated against the dev kit: arm span matches within 3mm (1.245m extracted vs 1.242m dev kit). The user confirmed the extracted body "looks close to what I see in SL." The user wears the Special Edition (with foot variants).
- Note: This does not replace the need for the Maitreya body — clothing designed for Legacy will not fit Maitreya without rework. Legacy is a temporary reference only.
