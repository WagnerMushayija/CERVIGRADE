"""The Classifier rulebook, its placeholder version, and swapping one classifier for another."""

import numpy as np
import pytest

from services.classifiers import Classifier, ModelLoadError, StubClassifier, load_classifier
from services.grading import CLASS_NAMES


def test_the_rulebook_cannot_be_used_directly():
    with pytest.raises(TypeError):
        Classifier()


def test_placeholder_gives_six_probabilities_per_crop_that_add_up_to_one():
    crops = [np.zeros((200, 200, 3), dtype="uint8")] * 5
    probs = StubClassifier().predict(crops)
    assert probs.shape == (5, len(CLASS_NAMES))
    assert np.allclose(probs.sum(axis=1), 1.0, atol=1e-5)


def test_placeholder_says_it_is_not_real_and_cannot_explain():
    stub = StubClassifier()
    assert stub.is_real is False
    assert stub.identity() == ("stub (placeholder)", "none")
    with pytest.raises(NotImplementedError):
        stub.explain(np.zeros((10, 10, 3), dtype="uint8"), 0)


def test_a_missing_weights_file_is_an_error_by_default(tmp_path):
    with pytest.raises(ModelLoadError, match="no classifier file"):
        load_classifier(str(tmp_path / "missing.keras"))


def test_a_file_that_is_not_a_model_is_an_error_by_default(tmp_path):
    bad = tmp_path / "broken.keras"
    bad.write_bytes(b"not a model")
    with pytest.raises(ModelLoadError, match="failed to load"):
        load_classifier(str(bad))


def test_the_placeholder_is_only_returned_when_asked_for_on_purpose(tmp_path):
    assert isinstance(load_classifier(str(tmp_path / "missing.keras"), allow_placeholder=True), StubClassifier)
    bad = tmp_path / "broken.keras"
    bad.write_bytes(b"not a model")
    assert isinstance(load_classifier(str(bad), allow_placeholder=True), StubClassifier)
