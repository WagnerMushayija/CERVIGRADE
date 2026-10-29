"""
The grading vocabulary shared by the whole backend: the six grades, how serious each is, the three groups
they fall into, and how to turn six probabilities into the result the API returns.

The classes that actually run a model are in classifiers.py. They load the trained EfficientNetB0-on-CRIC
checkpoint from the repo's models/ folder (set CERVIGRADE_MODEL to point at a different file).

CRIC's six Bethesda classes, in the alphabetical order used in the training notebooks
(matches sorted(os.listdir(CRIC_CROPPED_DIR))):
"""

import os

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

def tier_of_class(class_name):
    return _CLASS_TO_TIER[class_name]


def tier_probabilities(probs):
    """Sum the six grade probabilities into the three group probabilities."""
    return {t: float(sum(probs[c] for c in members)) for t, members in TIER_MEMBERS.items()}


def describe(probs, mock):
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


_describe = describe    # the old name, kept so nothing else breaks
