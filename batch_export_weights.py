"""
Re-export OBJ + skin.json (with vertex_weights) for all assembled_basic body parts.
Run from J:\Claude Data\Mesh-Reader:
  python batch_export_weights.py
"""

import subprocess
import sys

ASSETS = {
    "d61974b2": r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\d\sl_cache_d61974b2-5932-18ae-3185-fa301f5ff9c6_0.asset",
    "2fbb9764": r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\2\sl_cache_2fbb9764-369f-dd20-3f25-bf949cb2073f_0.asset",
    "38875df5": r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\3\sl_cache_38875df5-2ec6-3fc9-ca90-2b6015310ce9_0.asset",
    "a867fbf4": r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\a\sl_cache_a867fbf4-b463-3df8-fd26-9547150eb780_0.asset",
    "7f453051": r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\7\sl_cache_7f453051-f698-e170-8df5-cfa8be02a451_0.asset",
    "3aac1021": r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\3\sl_cache_3aac1021-aec5-5fc8-319b-f12aa30829f5_0.asset",
    "3d02e3b7": r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\3\sl_cache_3d02e3b7-d67d-a831-c970-ffd9ba3d24c2_0.asset",
    "7c618493": r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\7\sl_cache_7c618493-016f-934e-876e-8371e1dff9a4_0.asset",
    "e623b5ff": r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\e\sl_cache_e623b5ff-0ee6-ac4f-2a19-3e158dba52c9_0.asset",
    "dd2d450c": r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\d\sl_cache_dd2d450c-65fd-b5e4-1176-084db67556a4_0.asset",
    "b365df00": r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\b\sl_cache_b365df00-3ee1-b87d-5f5f-eadb1c292b7f_0.asset",
    "8f0fb98e": r"C:\Users\alanc\AppData\Local\Firestorm_x64\cache\8\sl_cache_8f0fb98e-2644-6d66-0ac5-e8339739fb7c_0.asset",
}

ok = 0
failed = []

for uuid, path in ASSETS.items():
    print(f"\n--- {uuid} ---")
    result = subprocess.run(
        [sys.executable, "mesh_asset.py", "decode", path, "--lod", "high"],
        capture_output=False
    )
    if result.returncode == 0:
        ok += 1
    else:
        failed.append(uuid)

print(f"\n{'='*50}")
print(f"Done: {ok}/{len(ASSETS)} succeeded")
if failed:
    print(f"Failed: {failed}")
