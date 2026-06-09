"""
clear_attachment_cache.py

Deletes the 16 known avatar attachment mesh cache files so that
Firestorm will re-download them fresh on next login.

After running this script:
1. Open Firestorm and log in as Nalates Urriah
2. Set Graphics > Mesh Detail to MAXIMUM
3. Zoom the camera to within 1-2 metres of your avatar
4. Wait 3-5 minutes for all LODs to download
5. Log out cleanly (File > Quit, not force-close)
6. Run:  python batch_export.py --uuids june6  --lod high

The viewer will re-create fresh .asset files with complete
high_lod sections once it actually renders the avatar at close range.
"""

import os
import shutil
import sys

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


def find_path(uid):
    subdir = uid[0].lower()
    return os.path.join(CACHE_ROOT, subdir, f"sl_cache_{uid}_0.asset")


def main():
    backup = "--backup" in sys.argv
    dry_run = "--dry-run" in sys.argv or (len(sys.argv) == 1)

    if dry_run and "--dry-run" not in sys.argv:
        print("DRY RUN (pass --delete to actually delete, --backup to backup first)\n")

    backup_dir = os.path.join(os.path.dirname(__file__), "cache_backup_june6")
    if backup:
        os.makedirs(backup_dir, exist_ok=True)
        print(f"Backup dir: {backup_dir}\n")

    found = 0
    for uid in ATTACHMENT_UUIDS:
        path = find_path(uid)
        size = os.path.getsize(path) if os.path.exists(path) else None
        if size is None:
            print(f"  NOT FOUND  {uid}")
            continue
        found += 1
        action = ""
        if "--delete" in sys.argv or backup:
            if backup:
                dst = os.path.join(backup_dir, os.path.basename(path))
                shutil.copy2(path, dst)
                action = " [backed up]"
            if "--delete" in sys.argv:
                os.remove(path)
                action += " [DELETED]"
        print(f"  {uid[:8]}  {size//1024:>6} KB{action}")

    print(f"\n{found}/{len(ATTACHMENT_UUIDS)} files found.")
    if dry_run:
        print("\nTo delete:  python clear_attachment_cache.py --delete")
        print("To backup first:  python clear_attachment_cache.py --backup --delete")


if __name__ == "__main__":
    main()
