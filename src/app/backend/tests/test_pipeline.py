"""
The photo-level rules of the pipeline, tested with a fake detector and a fake classifier so no model weights are needed.
(The real models are checked end to end by running the app; here the point is the logic around them.)
"""

import cv2
import numpy as np
import pytest

from classifiers import Classifier
from model import CLASS_NAMES
from pipeline import CellDetector, FieldPipeline, crop_at


def png(width, height):
    ok, data = cv2.imencode(".png", np.full((height, width, 3), 128, dtype="uint8"))
    return data.tobytes()


class FakeDetector:
    ready = True
    conf = 0.25
    identity = "fake.pt"

    def __init__(self, boxes):
        self._boxes = np.array(boxes, dtype="float32").reshape(-1, 4)

    def find_cells(self, img):
        return self._boxes, np.full(len(self._boxes), 0.9, dtype="float32")


class FakeClassifier(Classifier):
    """Returns a fixed (grade, confidence) for each crop, in order."""
    is_real = True
    name, version = "fake", "1"

    def __init__(self, answers):
        self._answers = answers

    def predict(self, crops):
        rows = []
        for grade, conf in self._answers[:len(crops)]:
            row = np.full(6, (1 - conf) / 5)
            row[CLASS_NAMES.index(grade)] = conf
            rows.append(row)
        return np.array(rows)

    def explain(self, crop, class_index):
        return None


BOXES = [[100, 100, 150, 150], [300, 300, 350, 350], [500, 500, 550, 550]]


def run(answers, boxes=BOXES, size=(1000, 1000), detector=None):
    pipe = FieldPipeline(detector or FakeDetector(boxes), FakeClassifier(answers))
    return pipe.analyze(png(*size))


def test_a_sure_abnormal_cell_sets_the_photo_result():
    r = run([("Negative", 0.99), ("HSIL", 0.95), ("Negative", 0.9)])
    assert r["mode"] == "field" and r["predicted_class"] == "HSIL" and r["tier"] == "high"
    assert r["detections"]["counted"] == 3 and r["detections"]["set_aside"] == 0
    assert set(r["detections"]["timings"]) == {"detect_s", "classify_s"}      # how long each stage took, for performance testing


def test_an_unsure_abnormal_cell_is_set_aside_and_flags_the_photo():
    r = run([("Negative", 0.99), ("HSIL", 0.95), ("SCC", 0.6)])
    assert r["predicted_class"] == "HSIL"                     # the unsure SCC does not decide the result
    assert r["detections"]["set_aside"] == 1
    assert r["low_confidence"] is True                        # but a worse unsure cell means "look closer"


def test_when_nothing_abnormal_counts_the_photo_is_negative():
    r = run([("Negative", 0.99), ("LSIL", 0.5), ("HSIL", 0.4)])
    assert r["predicted_class"] == "Negative" and r["detections"]["decisive"] is None


def test_the_worst_counted_grade_wins():
    r = run([("LSIL", 0.95), ("SCC", 0.92), ("HSIL", 0.99)])
    assert r["predicted_class"] == "SCC"


def test_no_cells_found_gives_a_readable_error():
    r = run([], boxes=[])
    assert "no cells" in r["error"].lower()


def test_a_small_photo_is_graded_as_one_cell_without_the_detector():
    r = run([("LSIL", 0.8)], size=(200, 200))
    assert r["mode"] == "cell" and r["detections"] is None and r["predicted_class"] == "LSIL"


def test_a_big_photo_without_a_detector_is_graded_whole_and_flagged():
    pipe = FieldPipeline(CellDetector(path="/no/such/detector.pt"), FakeClassifier([("Negative", 0.99)]))
    r = pipe.analyze(png(1000, 1000))
    assert r["mode"] == "whole" and r["low_confidence"] is True


def test_the_placeholder_classifier_marks_results_as_mock():
    from classifiers import StubClassifier
    r = FieldPipeline(FakeDetector(BOXES), StubClassifier()).analyze(png(1000, 1000))
    assert r["mock"] is True and r["mode"] == "cell"


def test_a_file_that_is_not_an_image_is_an_error_not_a_crash():
    out = FieldPipeline(FakeDetector(BOXES), FakeClassifier([])).analyze_many([b"not an image"])
    assert out[0]["error"]


def test_one_bad_photo_does_not_stop_the_others():
    pipe = FieldPipeline(FakeDetector(BOXES), FakeClassifier([("Negative", 0.99)] * 3))
    out = pipe.analyze_many([b"junk", png(1000, 1000)])
    assert "error" in out[0] and out[1]["mode"] == "field"


def test_crops_stay_inside_the_photo_at_the_edges():
    img = np.zeros((300, 400, 3), dtype="uint8")
    for cx, cy in [(0, 0), (399, 299), (200, 150)]:
        assert crop_at(img, cx, cy).shape[:2] == (200, 200)
