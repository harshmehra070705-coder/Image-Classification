# config.py
import os

# Base directory of the project
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Upload folder jahan photos save hongi
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')

# Database path
DATABASE_PATH = os.path.join(BASE_DIR, 'data', 'faces.db')

# Allowed file extensions
ALLOWED_EXTENSIONS = { 'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp',
    'avif', 'heic', 'heif', 'jfif'}

# Maximum file size (None)
MAX_CONTENT_LENGTH = None

# Face matching tolerance (lower = strict, higher = lenient)
# 0.4 = bahut strict (exact match)
# 0.6 = normal (recommended)
# 0.8 = lenient (similar faces bhi aa jayengi)
FACE_MATCH_TOLERANCE = 0.5

# Flask secret key
SECRET_KEY = 'mera-secret-key-change-karo-isko'

# Number of times to re-sample face (higher = more accurate but slower)
NUM_JITTERS = 1

# Face detection model
# 'hog' = fast but less accurate (CPU)
# 'cnn' = slow but more accurate (GPU recommended)
DETECTION_MODEL = 'hog'

# config.py (end me add kar do)

# InsightFace settings
INSIGHTFACE_MODEL = "buffalo_l"   # best general model pack
INSIGHTFACE_CTX_ID = -1           # -1 CPU, 0 GPU
INSIGHTFACE_DET_SIZE = 640    # 640/960/1280 (bada => small face better, slow)
INSIGHTFACE_DET_THRESH = 0.45
FACE_SIMILARITY_THRESHOLD = 0.35  # 0.30-0.45 typical
SEARCH_TOP_K = None                # top results candidatespython reset_faces.py