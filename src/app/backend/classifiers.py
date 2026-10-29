"""
Cell classifiers: one interface, two implementations.

A Classifier takes cell crops and returns six grade probabilities per crop. The rest of the app only talks to
this interface, so it does not care whether the real model or the placeholder is behind it:

    Classifier                  the rulebook (abstract: it cannot be used directly)
      EfficientNetClassifier    the trained EfficientNetB0, with Grad-CAM
      StubClassifier            made-up numbers, so the page can be tried when the weights file is missing

load_classifier() picks the real one when the weights load and falls back to the placeholder otherwise.
"""

import os
import random
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import numpy as np

from model import CLASS_NAMES, MODEL_PATH


class Classifier(ABC):
    """Grades cell crops. Subclasses say how, and whether the numbers are real."""

    is_real = False                 # False means "placeholder numbers, do not trust"

    @property
    @abstractmethod
    def name(self) -> str:
        """Short name stored with every prediction."""

    @property
    @abstractmethod
    def version(self) -> str:
        """A version label stored with every prediction."""

    @abstractmethod
    def predict(self, crops_bgr) -> np.ndarray:
        """Crops in (OpenCV BGR arrays of any size), an (n, 6) array of probabilities out, in CLASS_NAMES order."""

    def explain(self, crop_bgr, class_index):
        """A small heat grid (values 0..1) showing what pushed the model toward class_index, or None."""
        raise NotImplementedError(f"{type(self).__name__} cannot explain its grades.")

    def identity(self):
        return self.name, self.version


class EfficientNetClassifier(Classifier):
    """The trained EfficientNetB0 (a Keras file). Grad-CAM works on its last convolution layer."""

    is_real = True

    def __init__(self, path):
        import tensorflow as tf                     # imported here so the placeholder works without TensorFlow
        self._path = path
        self._model = tf.keras.models.load_model(path)
        self._cam_parts = None                      # built the first time an explanation is asked for

    @property
    def name(self):
        return os.path.basename(self._path)

    @property
    def version(self):
        return datetime.fromtimestamp(os.path.getmtime(self._path), tz=timezone.utc).strftime("%Y-%m-%d")

    def predict(self, crops_bgr):
        """Same steps as the training notebooks: BGR -> RGB, resize to 224 (bilinear), EfficientNet preprocess."""
        import cv2
        import tensorflow as tf
        batch = np.stack([cv2.resize(cv2.cvtColor(c, cv2.COLOR_BGR2RGB), (224, 224), interpolation=cv2.INTER_LINEAR)
                          for c in crops_bgr]).astype("float32")
        batch = tf.keras.applications.efficientnet.preprocess_input(batch)
        return self._model.predict(batch, batch_size=32, verbose=0)

    def _cam_setup(self):
        """Split the model into (backbone that also returns the last conv maps, dense head weights). Built once."""
        if self._cam_parts is None:
            import tensorflow as tf
            base = next(l for l in self._model.layers if isinstance(l, tf.keras.Model))
            conv_layer = next(l for l in reversed(base.layers) if len(l.output.shape) == 4)    # last layer that still has a spatial grid
            feat = tf.keras.Model(base.input, [conv_layer.output, base.output])
            dense = self._model.layers[-1]
            self._cam_parts = (feat, dense.kernel, dense.bias)
        return self._cam_parts

    def explain(self, crop_bgr, class_index):
        """
        Grad-CAM for one cell crop. Weights = average gradient of that class's pre-softmax score over each last-layer
        feature map; heat = ReLU of the weighted sum. Returns the feature grid (7 x 7 here) scaled to 0..1,
        or None if nothing pushed toward the class. Same preprocessing as predict().
        """
        import cv2
        import tensorflow as tf
        feat, kernel, bias = self._cam_setup()
        x = cv2.resize(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB), (224, 224), interpolation=cv2.INTER_LINEAR).astype("float32")[None]
        x = tf.keras.applications.efficientnet.preprocess_input(x)
        with tf.GradientTape() as tape:
            conv, pooled = feat(x, training=False)
            score = tf.matmul(pooled, kernel)[:, class_index] + bias[class_index]    # the dropout layer does nothing at inference
        grads = tape.gradient(score, conv)
        weights = tf.reduce_mean(grads, axis=(1, 2), keepdims=True)
        heat = tf.nn.relu(tf.reduce_sum(weights * conv, axis=-1))[0].numpy()
        top = float(heat.max())
        return None if top <= 0 else (heat / top).astype("float32")


class StubClassifier(Classifier):
    """Plausible-looking but NOT real probabilities, only so the interface can be tried without the model."""

    _WEIGHTS = {"ASC-H": 0.08, "ASC-US": 0.05, "HSIL": 0.15, "LSIL": 0.12, "Negative": 0.55, "SCC": 0.05}

    @property
    def name(self):
        return "stub (placeholder)"

    @property
    def version(self):
        return "none"

    def predict(self, crops_bgr):
        rows = []
        for _ in crops_bgr:
            noisy = [max(0.01, self._WEIGHTS[c] + random.uniform(-0.05, 0.05)) for c in CLASS_NAMES]
            total = sum(noisy)
            rows.append([v / total for v in noisy])
        return np.array(rows, dtype="float32")


def load_classifier(path=MODEL_PATH):
    """The real classifier when the weights file loads, otherwise the placeholder (and the terminal says so)."""
    if not os.path.exists(path):
        print(f"[model] No checkpoint at {path}, using the stub predictor")
        return StubClassifier()
    try:
        classifier = EfficientNetClassifier(path)
        print(f"[model] Loaded real checkpoint from {path}")
        return classifier
    except Exception as e:
        print(f"[model] Found {path} but failed to load it, falling back to stub: {e}")
        return StubClassifier()
