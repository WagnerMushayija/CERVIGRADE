"""
CerviGrade prediction backend.

Loads the trained EfficientNetB0-on-CRIC checkpoint from the repo's models/ folder
(set CERVIGRADE_MODEL to point at a different file). If the file is missing, a stub
predictor takes over so the API and the page can still be tried out: every response
carries a "mock" flag, and /health reports "using_real_model".

CRIC's six Bethesda classes, in the alphabetical order used in the training notebooks
(matches sorted(os.listdir(CRIC_CROPPED_DIR))):
"""

import os
import random
from datetime import datetime, timezone

CLASS_NAMES = ["ASC-H", "ASC-US", "HSIL", "LSIL", "Negative", "SCC"]

# Most to least severe. Used to decide which finding sets the overall result.
SEVERITY_ORDER = ["SCC", "HSIL", "ASC-H", "LSIL", "ASC-US", "Negative"]
SEVERITY_RANK = {c: len(SEVERITY_ORDER) - i for i, c in enumerate(SEVERITY_ORDER)}   # SCC highest

# Three groups. ASC-US and LSIL look alike (to the model and to doctors), and so do
# ASC-H, HSIL and SCC at the coarse level, so the page leads with the group and shows
# the exact grade underneath. A group's score is the sum of its grades' probabilities.
TIER_MEMBERS = {"negative": ["Negative"], "low": ["ASC-US", "LSIL"], "high": ["ASC-H", "HSIL", "SCC"]}
TIER_LABELS = {"negative": "Negative", "low": "Low-grade", "high": "High-grade"}
TIER_RANK = {"negative": 0, "low": 1, "high": 2}
_CLASS_TO_TIER = {c: t for t, members in TIER_MEMBERS.items() for c in members}

# Below this confidence the page asks the reader to look at the image more closely.
LOW_CONFIDENCE = 0.60

# Weights live in the repo's models/ folder (src/app/backend -> three levels up).
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MODEL_PATH = os.environ.get("CERVIGRADE_MODEL", os.path.join(_REPO_ROOT, "models", "efficientnetb0_cric_retrained.keras"))

_model = None
_using_real_model = False


def _try_load_real_model():
    global _model, _using_real_model
    if not os.path.exists(MODEL_PATH):
        print(f"[model] No checkpoint at {MODEL_PATH}, using the stub predictor")
        return
    try:
        import tensorflow as tf
        _model = tf.keras.models.load_model(MODEL_PATH)
        _using_real_model = True
        print(f"[model] Loaded real checkpoint from {MODEL_PATH}")
    except Exception as e:
        print(f"[model] Found {MODEL_PATH} but failed to load it, falling back to stub: {e}")
        _model = None
        _using_real_model = False


_try_load_real_model()


def is_using_real_model():
    return _using_real_model


def model_identity():
    """(name, version) of the model that makes the predictions, stored with every prediction."""
    if _using_real_model:
        stamp = datetime.fromtimestamp(os.path.getmtime(MODEL_PATH), tz=timezone.utc).strftime("%Y-%m-%d")
        return os.path.basename(MODEL_PATH), stamp
    return "stub (placeholder)", "none"


def tier_of_class(class_name):
    return _CLASS_TO_TIER[class_name]


def tier_probabilities(probs):
    """Sum the six grade probabilities into the three group probabilities."""
    return {t: float(sum(probs[c] for c in members)) for t, members in TIER_MEMBERS.items()}


def _preprocess(image_bytes):
    """
    Mirrors the training notebooks' pipeline: tf.io.decode_image -> tf.image.resize
    (bilinear) -> EfficientNet's (pass-through) preprocess_input. Returns shape (1, 224, 224, 3).
    """
    import tensorflow as tf
    image = tf.io.decode_image(image_bytes, channels=3, expand_animations=False)
    image = tf.image.resize(image, [224, 224])
    image = tf.expand_dims(image, axis=0)
    return tf.keras.applications.efficientnet.preprocess_input(image).numpy()


def predict_crops(crops_bgr):
    """
    Grade cell crops already cut out of a photo (OpenCV BGR arrays of any size).
    Same steps as the detector-plus-CNN notebook: BGR -> RGB, resize to 224 (bilinear), EfficientNet preprocess.
    Returns an (n, 6) array of probabilities in CLASS_NAMES order. Only valid when the real model is loaded.
    """
    import cv2
    import numpy as np
    import tensorflow as tf
    batch = np.stack([cv2.resize(cv2.cvtColor(c, cv2.COLOR_BGR2RGB), (224, 224), interpolation=cv2.INTER_LINEAR)
                      for c in crops_bgr]).astype("float32")
    batch = tf.keras.applications.efficientnet.preprocess_input(batch)
    return _model.predict(batch, batch_size=32, verbose=0)



_cam_parts = None


def _cam_setup():
    """Split the loaded model into (backbone that also returns the last conv maps, dense head weights). Built once."""
    global _cam_parts
    if _cam_parts is None:
        import tensorflow as tf
        base = next(l for l in _model.layers if isinstance(l, tf.keras.Model))
        conv_layer = next(l for l in reversed(base.layers) if len(l.output.shape) == 4)       # last layer that still has a spatial grid
        feat = tf.keras.Model(base.input, [conv_layer.output, base.output])
        dense = _model.layers[-1]
        _cam_parts = (feat, dense.kernel, dense.bias)
    return _cam_parts


def gradcam(crop_bgr, class_index):
    """
    Grad-CAM for one cell crop: which parts of the crop pushed the model toward class_index.
    Weights = average gradient of that class's pre-softmax score over each last-layer feature map; heat = ReLU of the weighted sum.
    Returns a small float array (the feature grid, 7 x 7 for EfficientNetB0) scaled to 0..1, or None if nothing pushed toward the class.
    Same preprocessing as predict_crops. Only valid when the real model is loaded.
    """
    import cv2
    import numpy as np
    import tensorflow as tf
    feat, kernel, bias = _cam_setup()
    x = cv2.resize(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB), (224, 224), interpolation=cv2.INTER_LINEAR).astype("float32")[None]
    x = tf.keras.applications.efficientnet.preprocess_input(x)
    with tf.GradientTape() as tape:
        conv, pooled = feat(x, training=False)
        score = tf.matmul(pooled, kernel)[:, class_index] + bias[class_index]       # the dropout layer does nothing at inference
    grads = tape.gradient(score, conv)
    weights = tf.reduce_mean(grads, axis=(1, 2), keepdims=True)
    heat = tf.nn.relu(tf.reduce_sum(weights * conv, axis=-1))[0].numpy()
    top = float(heat.max())
    return None if top <= 0 else (heat / top).astype("float32")

def _stub_probabilities():
    """Plausible-looking but NOT real probabilities, only so the interface can be tried without the model."""
    weights = {"ASC-H": 0.08, "ASC-US": 0.05, "HSIL": 0.15, "LSIL": 0.12, "Negative": 0.55, "SCC": 0.05}
    noise = {c: max(0.01, w + random.uniform(-0.05, 0.05)) for c, w in weights.items()}
    total = sum(noise.values())
    return {c: v / total for c, v in noise.items()}


def _describe(probs, mock):
    """Turn six probabilities into the dict the API returns for one image."""
    predicted = max(probs, key=probs.get)
    tier_probs = tier_probabilities(probs)
    tier = max(tier_probs, key=tier_probs.get)
    return {
        "predicted_class": predicted,
        "confidence": probs[predicted],
        "probabilities": probs,
        "tier": tier,
        "tier_label": TIER_LABELS[tier],
        "tier_confidence": tier_probs[tier],
        "tier_probabilities": tier_probs,
        "low_confidence": probs[predicted] < LOW_CONFIDENCE,
        "mock": mock,
    }


def predict_severity(image_bytes):
    """One image in, one result out."""
    return predict_many([image_bytes])[0]


def predict_many(images):
    """
    A list of image byte strings in, a list of results out, in the same order.
    An image that cannot be read gives {"error": "..."} in its place instead of failing the whole batch.
    The real model is run once on all readable images together.
    """
    results = [None] * len(images)
    batch, positions = [], []
    for i, data in enumerate(images):
        if not _using_real_model or _model is None:
            results[i] = _describe(_stub_probabilities(), mock=True)
            continue
        try:
            batch.append(_preprocess(data)[0])
            positions.append(i)
        except Exception as e:
            results[i] = {"error": f"Could not read this image ({type(e).__name__})."}
    if batch:
        import numpy as np
        preds = _model.predict(np.stack(batch), verbose=0)
        for pos, row in zip(positions, preds):
            probs = {CLASS_NAMES[k]: float(row[k]) for k in range(len(CLASS_NAMES))}
            results[pos] = _describe(probs, mock=False)
    return results


def overall_verdict(results):
    """
    The overall result for one patient: the most serious finding among the readable images.
    Order: group first (high > low > negative), then the exact grade, then confidence.
    Returns None when no image could be read.
    """
    scored = [(i, r) for i, r in enumerate(results) if r and "error" not in r]
    if not scored:
        return None
    i, best = max(scored, key=lambda ir: (TIER_RANK[ir[1]["tier"]], SEVERITY_RANK[ir[1]["predicted_class"]], ir[1]["confidence"]))
    return {
        "tier": best["tier"],
        "tier_label": best["tier_label"],
        "predicted_class": best["predicted_class"],
        "image_index": i,
        "images_read": len(scored),
        "images_total": len(results),
        "low_confidence_images": [j for j, r in scored if r["low_confidence"]],
        "mock": any(r["mock"] for _, r in scored),
    }
