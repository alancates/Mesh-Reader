"""
batch_export_june6.py

Batch-export all 16 June 6 avatar attachment mesh cache files.
Outputs OBJ + skin.json for each asset into exports/june6_<lod>/

Usage:
  python batch_export_june6.py                  # best available LOD
  python batch_export_june6.py --lod high       # force high_lod only
  python batch_export_june6.py --lod medium
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import mesh_asset

CACHE_ROOT = r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache"

ATTACHMENT_UUIDS = [
    "e5987904-e617-4f65-0110-33f334979d97",
    "f3c83dd0-3e42-fae3-be22-1ed5b4e7c55a",
    "65c3e279-5efb-23bf-1328-d45461d308fd",
    "ac69cdfe-d575-561f-450b-921cce7e9dac",
    "1f8b745b-d058-6b72-8257-3c6237e21249",
    "522236f6-3162-3a69-ee42-3923a4713270",
    "96e11c60-38a5-bf63-aeed-240738a11c18",
    "d2316aa1-e864-a909-8ce6-55aac0cc7652",
    "317463b6-f891-680a-3425-a479826cf1ca",
    "8e8e7001-be24-01c9-a19a-fb6d08a219b1",
    "f9075e26-a5d6-b42b-f23d-c9696a6a641b",
    "d54d0124-a271-26b1-1be5-26060f4b0ab5",
    "6bbbe968-752d-706e-dd02-8fe446626712",
    "889b7d58-e780-b008-1c73-4ca4f3b76c83",
    "06329385-fc76-0095-0edc-a3efd972c460",
    "db1391ac-3f8a-d5bf-0d57-51ec14b50bbf",
]

LOD_PRIORITY = ["high_lod", "medium_lod", "low_lod", "lowest_lod"]


def export_uuid(uid, out_dir, force_lod=None):
    subdir = uid[0].lower()
    path = os.path.join(CACHE_ROOT, subdir, f"sl_cache_{uid}_0.asset")
    if not os.path.exists(path):
        print(f"  MISSING    {uid}")
        return

    try:
        data, header, data_start = mesh_asset.load_asset(path)
    except Exception as e:
        print(f"  ERROR      {uid}  load failed: {e}")
        return

    lod_order = [force_lod] if force_lod else LOD_PRIORITY

    for lod in lod_order:
        raw = mesh_asset.get_section_data(data, header, data_start, lod)
        if raw is None:
            continue
        try:
            faces = mesh_asset.decode_lod(raw)
        except Exception as e:
            print(f"  ERROR      {uid}  {lod} decode: {e}")
            continue
        if not faces:
            continue

        verts = sum(len(f["positions"]) for f in faces)
        tris  = sum(len(f["indices"]) // 3 for f in faces)

        stem = os.path.join(out_dir, uid[:8])
        obj_path = f"{stem}_{lod}.obj"
        mesh_asset.export_obj(faces, obj_path, name=uid[:8])

        if "skin" in header:
            skin_raw = mesh_asset.get_section_data(data, header, data_start, "skin")
            if skin_raw:
                skin = mesh_asset.decode_skin(skin_raw)
                mesh_asset.export_weights(skin, f"{stem}_skin.json")

        print(f"  OK         {uid[:8]}  {lod:<12}  faces={len(faces)}  verts={verts:>5}  tris={tris:>6}")
        return

    if force_lod:
        print(f"  NO DATA    {uid}  ({force_lod} not available or empty)")
    else:
        print(f"  NO GEOMETRY {uid}  (all LODs empty)")


def main():
    parser = argparse.ArgumentParser(description="Batch export June 6 avatar attachment meshes")
    parser.add_argument("--lod", choices=["high", "medium", "low", "lowest"],
                        default=None,
                        help="Force a specific LOD (default: best available)")
    args = parser.parse_args()

    force_lod = (args.lod + "_lod") if args.lod else None
    label = args.lod if args.lod else "best"
    out_dir = os.path.join(os.path.dirname(__file__), "exports", f"june6_{label}")
    os.makedirs(out_dir, exist_ok=True)

    print(f"Output dir:  {out_dir}")
    print(f"LOD:         {label}")
    print()

    ok = 0
    for uid in ATTACHMENT_UUIDS:
        before = ok
        export_uuid(uid, out_dir, force_lod)

    print(f"\nDone. OBJ files in: {out_dir}")


if __name__ == "__main__":
    main()
