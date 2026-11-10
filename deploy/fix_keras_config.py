"""
Makes the classifier file loadable on Keras 3.12 (the newest Keras that Python 3.10 can install).

The file was saved with Keras 3.13, which writes one extra setting (quantization_config, always empty) that Keras 3.12
does not recognise. This removes that setting from the file's config. The weights are not touched, and a backup is kept.
Safe to run more than once, and does nothing when the file is already fine.

    python deploy/fix_keras_config.py models/efficientnetb0_cric_retrained.keras
"""

import json
import os
import shutil
import sys
import zipfile


def strip(node):
    """Remove every quantization_config key. Returns how many were removed."""
    removed = 0
    if isinstance(node, dict):
        if "quantization_config" in node:
            del node["quantization_config"]
            removed += 1
        for value in node.values():
            removed += strip(value)
    elif isinstance(node, list):
        for value in node:
            removed += strip(value)
    return removed


def main(path):
    with zipfile.ZipFile(path) as z:
        config = json.loads(z.read("config.json"))
    if strip(config) == 0:
        print("Nothing to fix in", path)
        return
    backup = path + ".bak"
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
    with zipfile.ZipFile(backup) as src, zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as out:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "config.json":
                data = json.dumps(config).encode()
            out.writestr(item, data)
    print("Fixed", path, "(backup:", backup + ")")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "models/efficientnetb0_cric_retrained.keras")
