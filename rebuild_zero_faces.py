import os
from database import get_all_photos
from face_utils import detect_and_encode_faces

photos = get_all_photos()
zero = [p for p in photos if (not p["has_faces"]) or (p["face_count"] == 0)]

print("Total photos:", len(photos))
print("Zero-face photos:", len(zero))

for p in zero:
    if os.path.exists(p["filepath"]):
        r = detect_and_encode_faces(p["filepath"], p["id"])
        print(p["id"], p["original_name"], "=>", r["faces_found"], r["message"])
    else:
        print("Missing file:", p["filepath"])