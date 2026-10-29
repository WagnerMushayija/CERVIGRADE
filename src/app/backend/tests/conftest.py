"""
Shared test setup. The tests must run in seconds without model weights, so before anything is imported we point the
model and detector paths at files that do not exist (the app then uses the placeholder classifier and no detector)
and give the database a throwaway folder.
"""

import os
import sys
import tempfile

os.environ["CERVIGRADE_MODEL"] = os.path.join(tempfile.gettempdir(), "no-such-model.keras")
os.environ["CERVIGRADE_DETECTOR"] = os.path.join(tempfile.gettempdir(), "no-such-detector.pt")
os.environ.setdefault("CERVIGRADE_DATA", tempfile.mkdtemp(prefix="cervigrade-tests-"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
