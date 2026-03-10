# face_utils.py
import cv2
import numpy as np
from PIL import Image, ImageOps, ImageFile
# AVIF/HEIC open support (Pillow plugins)
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass

try:
    import pillow_avif  # noqa: F401
except Exception:
    pass

from insightface.app import FaceAnalysis

from config import (
    INSIGHTFACE_MODEL,
    INSIGHTFACE_CTX_ID,
    INSIGHTFACE_DET_SIZE,
    INSIGHTFACE_DET_THRESH,
    FACE_SIMILARITY_THRESHOLD,
    SEARCH_TOP_K
)

from database import (
    save_face_encoding,
    update_photo_face_info,
    get_all_face_encodings
)

# Pillow safety
ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None


# -------------------------------
# InsightFace init (global)
#   Two apps:
#   - base: your config
#   - hi  : bigger det_size + slightly lower thresh for Google/low-res faces
# -------------------------------
_BASE_DET = int(INSIGHTFACE_DET_SIZE)
_HI_DET = min(1280, max(1024, _BASE_DET * 2))
_FALLBACK_THRESH = max(0.30, float(INSIGHTFACE_DET_THRESH) - 0.15)

_face_app = FaceAnalysis(name=INSIGHTFACE_MODEL)
_face_app.prepare(
    ctx_id=int(INSIGHTFACE_CTX_ID),  # -1 CPU, 0 GPU
    det_size=(_BASE_DET, _BASE_DET),
    det_thresh=float(INSIGHTFACE_DET_THRESH)
)

_face_app_hi = FaceAnalysis(name=INSIGHTFACE_MODEL)
_face_app_hi.prepare(
    ctx_id=int(INSIGHTFACE_CTX_ID),
    det_size=(_HI_DET, _HI_DET),
    det_thresh=float(_FALLBACK_THRESH)
)


# -------------------------------
# Helpers
# -------------------------------
from pathlib import Path

def normalize_to_jpeg(input_path: str, output_path: str | None = None, max_size: int = 4000) -> str:
    """
    Any image -> RGB JPEG (EXIF rotation handled).
    Returns output jpg path.
    """
    if output_path is None:
        output_path = str(Path(input_path).with_suffix(".jpg"))

    with Image.open(input_path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")

        if max(im.size) > max_size:
            ratio = max_size / float(max(im.size))
            new_size = (int(im.size[0] * ratio), int(im.size[1] * ratio))
            im = im.resize(new_size, Image.LANCZOS)

        im.save(output_path, format="JPEG", quality=95, optimize=True)

    return output_path

def _read_bgr(image_path: str) -> np.ndarray | None:
    """
    Reads image using PIL (handles EXIF rotation), returns BGR uint8 contiguous np.ndarray.
    """
    try:
        with Image.open(image_path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            arr = np.array(im, dtype=np.uint8)  # RGB
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        return np.ascontiguousarray(bgr, dtype=np.uint8)
    except Exception:
        return None


def _bbox_to_location(bbox):
    """
    bbox = [x1,y1,x2,y2] -> location = [top,right,bottom,left] (face_recognition style)
    """
    x1, y1, x2, y2 = bbox
    return [int(round(y1)), int(round(x2)), int(round(y2)), int(round(x1))]


def _clip_location(loc, h: int, w: int):
    """
    loc = [top,right,bottom,left], clip inside image bounds
    """
    top, right, bottom, left = loc
    top = max(0, min(int(top), h - 1))
    bottom = max(0, min(int(bottom), h))
    left = max(0, min(int(left), w - 1))
    right = max(0, min(int(right), w))
    # ensure proper order
    if bottom <= top:
        bottom = min(h, top + 1)
    if right <= left:
        right = min(w, left + 1)
    return [top, right, bottom, left]


def _detect_faces_best(img_bgr: np.ndarray, min_side: int = 800):
    """
    Better detection for small/thumbnails:
    - If image is small, upscale so that min(h,w) >= min_side
    - Then multi-pass detect
    Returns: (faces, total_scale_used)
    """
    img_bgr = np.ascontiguousarray(img_bgr, dtype=np.uint8)
    h, w = img_bgr.shape[:2]

    # Base upscale for small images (Google thumbnails)
    base_scale = 1.0
    m = min(h, w)
    if m > 0 and m < min_side:
        base_scale = float(min_side) / float(m)

    # Try list: (extra_scale, app)
    tries = [
        (1.0, _face_app),
        (1.0, _face_app_hi),
        (1.5, _face_app_hi),
        (2.0, _face_app_hi),
        (3.0, _face_app_hi),
        (4.0, _face_app_hi),
    ]

    for extra_scale, app in tries:
        total_scale = base_scale * float(extra_scale)

        if total_scale == 1.0:
            test = img_bgr
        else:
            test = cv2.resize(
                img_bgr, None,
                fx=total_scale, fy=total_scale,
                interpolation=cv2.INTER_CUBIC
            )

        faces = app.get(test)
        if faces:
            return faces, total_scale

    return [], 1.0


# -------------------------------
# Indexing / Encoding
# -------------------------------
def detect_and_encode_faces(image_path: str, photo_id: int):
    """
    Upload/index time:
    - Detect all faces (multi-pass)
    - Store 512-d normed embeddings in DB
    """
    try:
        img = _read_bgr(image_path)
        if img is None:
            update_photo_face_info(photo_id, False, 0)
            return {'success': False, 'faces_found': 0, 'message': 'Image read nahi ho paayi'}

        h, w = img.shape[:2]
        faces, scale = _detect_faces_best(img)

        if not faces:
            update_photo_face_info(photo_id, False, 0)
            return {
                'success': True,
                'faces_found': 0,
                'message': f'Koi face detect nahi hua (image: {w}x{h}). Agar Google thumbnail hai to full-res image use karo.'
            }

        for f in faces:
            # embedding
            emb = f.normed_embedding.astype("float32")

            # bbox scale-back to original coords if upscaled was used
            bbox = (f.bbox / scale).tolist()  # [x1,y1,x2,y2] in original image coords
            loc = _bbox_to_location(bbox)
            loc = _clip_location(loc, h, w)

            save_face_encoding(photo_id, emb, loc)

        update_photo_face_info(photo_id, True, len(faces))
        return {'success': True, 'faces_found': len(faces), 'message': f'{len(faces)} face(s) detected!'}

    except Exception as e:
        update_photo_face_info(photo_id, False, 0)
        return {'success': False, 'faces_found': 0, 'message': f'Error: {str(e)}'}


# -------------------------------
# Search
# -------------------------------
def search_similar_faces(search_image_path: str):
    """
    GROUP PHOTO SUPPORT (Multi-face search)
    """
    try:
        img = _read_bgr(search_image_path)
        if img is None:
            return {'success': False, 'message': 'Search image read nahi ho paayi', 'results': []}

        q_faces, q_scale = _detect_faces_best(img)
        if not q_faces:
            return {
                'success': False,
                'message': 'Search photo me koi face nahi mila! Clear face wali photo daalo.',
                'results': []
            }

        all_faces = get_all_face_encodings()
        if not all_faces:
            return {
                'success': True,
                'message': 'Database me abhi koi photo nahi hai. Pehle photos upload karo!',
                'results': []
            }

        q_dim = int(q_faces[0].normed_embedding.shape[0])  # usually 512

        # Build aligned DB arrays (skip invalid encodings)
        valid_faces = []
        known = []
        for item in all_faces:
            enc = item["encoding"].astype("float32")
            if enc.ndim != 1 or enc.shape[0] != q_dim:
                continue
            known.append(enc)
            valid_faces.append(item)

        if not known:
            return {
                'success': False,
                'message': 'Database me invalid/old encodings hain. Reset faces + rebuild run karo.',
                'results': []
            }

        known = np.stack(known, axis=0).astype("float32")  # Nx512

        # Candidate count
        if SEARCH_TOP_K is None:
            k = known.shape[0]
        else:
            k = min(int(SEARCH_TOP_K), known.shape[0])

        global_matched = {}   # photo_id -> best payload
        per_face_results = []

        for qi, qf in enumerate(q_faces):
            q_emb = qf.normed_embedding.astype("float32")
            sims = known @ q_emb  # cosine similarity (since normed)

            top_idx = np.argsort(-sims)[:k]

            per_face_matched = {}
            for idx in top_idx:
                sim = float(sims[idx])
                if sim < float(FACE_SIMILARITY_THRESHOLD):
                    continue

                face_data = valid_faces[idx]
                photo_id = face_data["photo_id"]
                confidence = round(sim * 100, 2)

                payload = {
                    'photo_id': photo_id,
                    'filename': face_data.get('filename'),
                    'original_name': face_data.get('original_name'),
                    'confidence': confidence,
                    'distance': round(1.0 - sim, 4),
                    'similarity': round(sim, 4),
                    'face_location': face_data.get('face_location'),
                    'matched_query_face_index': qi
                }

                # Per-face best per photo
                if (photo_id not in per_face_matched) or (confidence > per_face_matched[photo_id]['confidence']):
                    per_face_matched[photo_id] = payload

                # Global best per photo
                if (photo_id not in global_matched) or (confidence > global_matched[photo_id]['confidence']):
                    global_matched[photo_id] = payload

            per_face_sorted = sorted(per_face_matched.values(), key=lambda x: x['confidence'], reverse=True)
            per_face_results.append({
                "query_face_index": qi,
                "query_face_location": _bbox_to_location((qf.bbox / q_scale).tolist()),
                "results": per_face_sorted
            })

        results = sorted(global_matched.values(), key=lambda x: x['confidence'], reverse=True)

        return {
            'success': True,
            'message': f'{len(results)} matching photo(s) mili! (query faces: {len(q_faces)})',
            'results': results,
            'per_face_results': per_face_results,
            'query_faces_found': len(q_faces),
            'total_searched': len(valid_faces)
        }

    except Exception as e:
        return {'success': False, 'message': f'Search me error aaya: {str(e)}', 'results': []}


# -------------------------------
# Utilities (thumbnail / draw / validate / resize)
# -------------------------------
def get_face_thumbnail(image_path: str, face_location, output_size=(150, 150), padding=30):
    """
    face_location: [top, right, bottom, left]
    returns: BGR thumbnail (np.ndarray) or None
    """
    try:
        img = _read_bgr(image_path)
        if img is None:
            return None

        h, w = img.shape[:2]
        top, right, bottom, left = face_location
        top, right, bottom, left = _clip_location([top, right, bottom, left], h, w)

        top = max(0, top - int(padding))
        left = max(0, left - int(padding))
        bottom = min(h, bottom + int(padding))
        right = min(w, right + int(padding))

        face_img = img[top:bottom, left:right]
        if face_img.size == 0:
            return None

        face_img = cv2.resize(face_img, output_size, interpolation=cv2.INTER_CUBIC)
        return face_img
    except Exception:
        return None


def draw_faces_on_image(image_path: str):
    """
    returns: (image_bgr_with_boxes, faces_count)
    """
    try:
        img = _read_bgr(image_path)
        if img is None:
            return None, 0

        faces, scale = _detect_faces_best(img)
        for f in faces:
            x1, y1, x2, y2 = (f.bbox / scale).astype(int)
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 3)

        return img, len(faces)
    except Exception:
        return None, 0


def validate_image(file_path: str) -> bool:
    """
    True if image decode ho jaati hai (corrupt nahi hai)
    """
    try:
        with Image.open(file_path) as img:
            img.load()
        return True
    except Exception:
        return False


def resize_image_if_needed(image_path: str, max_size=4000) -> bool:
    """
    If very large image, downscale to max_size (max(width,height)).
    """
    try:
        with Image.open(image_path) as img:
            img = ImageOps.exif_transpose(img)
            if max(img.size) <= max_size:
                return True

            ratio = max_size / float(max(img.size))
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.LANCZOS)
            img.save(image_path, quality=95)
        return True
    except Exception:
        return False