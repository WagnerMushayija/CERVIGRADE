"""
Renders Grad-CAM pictures for the page. The heat itself comes from model.gradcam; this file only draws it.
The colours are soft on purpose: nothing at all where the model paid little attention, violet to pink to amber where it paid more.
"""

import numpy as np

OUT_SIZE = 400          # the longest side of the picture sent to the page


def _palette(heat):
    """heat 0..1 -> RGB floats. Violet, then pink, then amber at the hottest."""
    stops = np.array([0.0, 0.5, 1.0])
    colours = np.array([[110, 90, 230], [232, 70, 125], [255, 196, 64]], dtype="float32")
    return np.stack([np.interp(heat, stops, colours[:, k]) for k in range(3)], axis=-1)


def render(crop_bgr, heat, overlay=True):
    """PNG bytes: the cell crop, with the heat laid over it when overlay is true."""
    import cv2
    h, w = crop_bgr.shape[:2]
    scale = OUT_SIZE / max(h, w)
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    base = cv2.resize(crop_bgr, size, interpolation=cv2.INTER_CUBIC).astype("float32")
    if overlay and heat is not None:
        grid = cv2.resize(heat, size, interpolation=cv2.INTER_CUBIC).clip(0, 1)
        rgb = _palette(grid)[..., ::-1]                               # to BGR
        alpha = (grid ** 1.1 * 0.72)[..., None]
        base = base * (1 - alpha) + rgb * alpha
    ok, buf = cv2.imencode(".png", base.clip(0, 255).astype("uint8"))
    return buf.tobytes()
