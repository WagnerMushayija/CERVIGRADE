"""
Field photo in, graded cells out.

This is the pipeline tested in the detector-plus-CNN notebook:
  1. A YOLO11n detector slides a 224 px window over the photo and boxes every cell it can find.
  2. Each box is cut out as the same 200 x 200 crop the CNN was trained on, centred on the box.
  3. The CNN grades every crop.
  4. A cell counts toward the result if the CNN says Negative, or if it is at least CNN_SURE confident.
     The photo's result is the most serious grade among the cells that count.

Cells the CNN is unsure about are kept and shown, but set aside, because in the tests they were mostly
false alarms. If the weights for the detector are missing, a small photo is graded as one cell
(the old behaviour) and a big photo is graded whole, which is unreliable and is flagged.

Settings come from the notebook run: oversampled detector at 0.25, CNN cut-off 0.9.
"""

import os
import threading

import numpy as np

from model import (CLASS_NAMES, LOW_CONFIDENCE, SEVERITY_RANK, TIER_LABELS, TIER_RANK, _REPO_ROOT,
                   is_using_real_model, predict_crops, tier_of_class, tier_probabilities)

DETECTOR_PATH = os.environ.get("CERVIGRADE_DETECTOR", os.path.join(_REPO_ROOT, "models", "stage2_severity_oversampled_best.pt"))
DET_CONF = float(os.environ.get("CERVIGRADE_DET_CONF", "0.25"))     # the detector keeps every box above this
CNN_SURE = float(os.environ.get("CERVIGRADE_CNN_SURE", "0.9"))      # an abnormal cell must be this sure to count
TILE, STRIDE, CROP = 224, 112, 200                                  # detector window, its step, CNN crop size
SMALL_IMAGE = 400          # a photo no bigger than this on both sides is treated as one cropped cell
MAX_CELLS = 400            # the most boxes graded in one photo (highest detector confidence first)
MAX_PIXELS = 40_000_000    # refuse absurdly large photos

_detector = None
_lock = threading.Lock()   # the models are shared, so one photo is analysed at a time


def _load_detector():
    global _detector
    if not os.path.exists(DETECTOR_PATH):
        print(f"[pipeline] No detector at {DETECTOR_PATH}. Field photos will be graded whole (unreliable).")
        return
    try:
        from ultralytics import YOLO
        det = YOLO(DETECTOR_PATH)
        if len(det.names) != 6:
            raise ValueError(f"expected a 6-class detector, found {len(det.names)} classes")
        _detector = det
        print(f"[pipeline] Loaded detector {DETECTOR_PATH}")
    except Exception as e:
        print(f"[pipeline] Found {DETECTOR_PATH} but could not load it: {e}")


_load_detector()


def detector_ready():
    return _detector is not None


def detector_identity():
    return os.path.basename(DETECTOR_PATH) if _detector is not None else None


def _tile_starts(length, tile, stride):
    last = max(length - tile, 0)
    starts = list(range(0, last + 1, stride))
    if starts[-1] != last:
        starts.append(last)
    return starts


def detect_cells(img_bgr):
    """Boxes (x1, y1, x2, y2), detector confidences. One box per cell: overlapping boxes from neighbouring windows are merged."""
    import torch
    from torchvision.ops import nms
    H, W = img_bgr.shape[:2]
    tiles, offsets = [], []
    for y in _tile_starts(H, TILE, STRIDE):
        for x in _tile_starts(W, TILE, STRIDE):
            tiles.append(img_bgr[y:y + TILE, x:x + TILE])
            offsets.append((x, y))
    results = _detector.predict(tiles, imgsz=224, conf=DET_CONF, verbose=False, batch=64)
    boxes, scores = [], []
    for r, (ox, oy) in zip(results, offsets):
        if r.boxes is None or len(r.boxes) == 0:
            continue
        xyxy = r.boxes.xyxy.cpu().numpy().copy()
        xyxy[:, [0, 2]] += ox
        xyxy[:, [1, 3]] += oy
        boxes.append(xyxy)
        scores.append(r.boxes.conf.cpu().numpy())
    if not boxes:
        return np.zeros((0, 4), dtype=np.float32), np.zeros(0, dtype=np.float32)
    boxes, scores = np.concatenate(boxes), np.concatenate(scores)
    keep = nms(torch.tensor(boxes), torch.tensor(scores), 0.5).numpy()
    return boxes[keep], scores[keep]


def crop_at(img_bgr, cx, cy):
    """The 200 x 200 window the CNN was trained on: centred on the point, pushed back inside the photo at the edges."""
    h, w = img_bgr.shape[:2]
    size = min(CROP, h, w)
    left = max(0, min(int(cx) - size // 2, w - size))
    top = max(0, min(int(cy) - size // 2, h - size))
    return img_bgr[top:top + size, left:left + size]


def _describe_whole(probs, mock):
    """The result for an image graded as one cell (small photos, or no detector)."""
    from model import _describe
    d = _describe(probs, mock)
    d["tier"] = tier_of_class(d["predicted_class"])
    d["tier_label"] = TIER_LABELS[d["tier"]]
    return d


def analyze_one(image_bytes):
    """
    One uploaded image in, the dict stored as its prediction out (or {"error": ...}).
    Extra keys: "detections" (what the page draws) and "mode" ("field", "cell" or "whole").
    """
    import cv2
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return {"error": "Could not read this image."}
    H, W = img.shape[:2]
    if H * W > MAX_PIXELS:
        return {"error": f"This photo is too large ({W} x {H} pixels)."}

    # ---- stub model: keep the interface working without weights
    if not is_using_real_model():
        from model import _describe, _stub_probabilities
        d = _describe_whole(_stub_probabilities(), mock=True)
        d["mode"], d["detections"] = "cell", None
        return d

    small = max(H, W) <= SMALL_IMAGE
    if small or _detector is None:
        row = predict_crops([img])[0]
        d = _describe_whole({CLASS_NAMES[k]: float(row[k]) for k in range(6)}, mock=False)
        d["mode"] = "cell" if small else "whole"
        d["detections"] = None
        if not small:
            d["low_confidence"] = True      # a whole field fed to a single-cell model: always worth a second look
        return d

    with _lock:
        boxes, det_scores = detect_cells(img)
    if len(boxes) == 0:
        return {"error": "The detector found no cells in this photo. Check that it is a microscope field photo."}
    order = np.argsort(-det_scores)[:MAX_CELLS]
    boxes, det_scores = boxes[order], det_scores[order]
    crops = [crop_at(img, (b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for b in boxes]
    with _lock:
        probs = predict_crops(crops)                       # (n, 6)

    cls = probs.argmax(1)
    conf = probs.max(1)
    neg = CLASS_NAMES.index("Negative")
    counted = (cls == neg) | (conf >= CNN_SURE)
    names = [CLASS_NAMES[i] for i in cls]
    cells = []
    for i in range(len(boxes)):
        t = tier_of_class(names[i])
        cells.append({"box": [round(float(v), 1) for v in boxes[i]], "det": round(float(det_scores[i]), 3),
                      "cls": names[i], "conf": round(float(conf[i]), 3), "tier": t, "counted": bool(counted[i]),
                      "p": [round(float(v), 3) for v in probs[i]]})

    def key(i):
        return (TIER_RANK[tier_of_class(names[i])], SEVERITY_RANK[names[i]], conf[i])

    idx_counted = [i for i in range(len(boxes)) if counted[i]]
    set_aside = [i for i in range(len(boxes)) if not counted[i]]
    if idx_counted:
        best = max(idx_counted, key=key)
        verdict_class = names[best]
    else:
        best, verdict_class = None, "Negative"
    verdict_rank = (TIER_RANK[tier_of_class(verdict_class)], SEVERITY_RANK[verdict_class])
    worse_unsure = any((TIER_RANK[tier_of_class(names[i])], SEVERITY_RANK[names[i]]) > verdict_rank for i in set_aside)

    if verdict_class != "Negative":
        p = probs[best]
        confidence = float(conf[best])
        decisive = best
    else:
        p = probs.mean(axis=0)                              # nothing abnormal counted: the average cell
        confidence = float(p[neg])
        decisive = None
    prob_dict = {CLASS_NAMES[k]: float(p[k]) for k in range(6)}
    tier = tier_of_class(verdict_class)
    tp = tier_probabilities(prob_dict)
    counts_by_tier = {t: sum(1 for i in idx_counted if cells[i]["tier"] == t) for t in ("negative", "low", "high")}
    return {
        "predicted_class": verdict_class, "confidence": confidence, "probabilities": prob_dict,
        "tier": tier, "tier_label": TIER_LABELS[tier], "tier_confidence": float(tp[tier]),
        "tier_probabilities": tp,
        "low_confidence": bool(confidence < LOW_CONFIDENCE or worse_unsure),
        "mock": False, "mode": "field",
        "detections": {
            "image_size": [W, H],
            "settings": {"detector_conf": DET_CONF, "cnn_sure": CNN_SURE, "crop": CROP},
            "decisive": decisive,
            "found": len(cells), "counted": len(idx_counted), "set_aside": len(set_aside),
            "counted_by_tier": counts_by_tier,
            "cells": cells,
        },
    }


def analyze_many(images):
    """A list of image byte strings in, a list of results out, same order. Unreadable images give {"error": ...}."""
    out = []
    for data in images:
        try:
            out.append(analyze_one(data))
        except Exception as e:
            out.append({"error": f"Could not analyse this image ({type(e).__name__})."})
    return out


def cam_png(path, box, class_index, overlay=True):
    """Grad-CAM picture (PNG bytes) for the cell in `box` of the stored photo, or for the whole image when box is None."""
    import cv2
    import gradcam
    from model import gradcam as heat_for
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    crop = img if box is None else crop_at(img, (box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
    with _lock:
        heat = heat_for(crop, class_index) if overlay else None
    return gradcam.render(crop, heat, overlay)
