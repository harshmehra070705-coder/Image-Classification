import os
from database import get_all_photos
from face_utils import detect_and_encode_faces

photos = get_all_photos()
print("Total photos:", len(photos))

for p in photos:
    path = p["filepath"]
    if os.path.exists(path):
        r = detect_and_encode_faces(path, p["id"])
        print(p["id"], p["filename"], r["faces_found"], r["message"])
    else:
        print("Missing file:", path)

print("Done.")