"""
Settings that more than one part of the backend needs, in one place. Everything can be changed with an environment
variable, so the same code runs on a laptop and on a server.

  CERVIGRADE_DATA      folder for the database, uploaded images and the signing key (default: app_data/ in the repo root)
  CERVIGRADE_MODEL     the trained classifier file (default: models/efficientnetb0_cric_retrained.keras)
  CERVIGRADE_DETECTOR  the trained cell detector (default: models/stage2_severity_oversampled_best.pt)
  CERVIGRADE_ORIGINS   other websites allowed to call the API, comma separated (default: none)
  CERVIGRADE_FRONTEND  the web page file (default: src/app/frontend/index.html)
"""

import os
import re

# This file is <repo>/src/app/backend/core/config.py, so the repo root is four folders up.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

# Other websites that may call the API from a browser. The page is served by this same server, so the default is none.
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("CERVIGRADE_ORIGINS", "").split(",") if o.strip()]

FRONTEND_FILE = os.environ.get("CERVIGRADE_FRONTEND", os.path.join(REPO_ROOT, "src", "app", "frontend", "index.html"))

# Upload rules.
MAX_IMAGES = 40
MAX_BYTES = 15 * 1024 * 1024     # per image
CODE_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")           # a patient code, so no spaces and no room for a name
EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/bmp": ".bmp", "image/tiff": ".tif", "image/webp": ".webp"}
