"""
Run the finished CerviGrade pipeline (detector, then EfficientNetB0 at 90%) on a sample of Mendeley LBC photos
and compare each photo's verdict with its folder label.

Usage, from src/app/backend (so the models load the way the app loads them):
    python ../../evaluation/mendeley_pipeline_check.py "<path to the 'mendley dataset' folder>" [photos per class] [output csv]

The folder must hold the four class folders (High/Low squamous intra-epithelial lesion, Negative..., Squamous cell carcinoma).
Photos are picked at random with seed 42. One photo takes roughly 45 s to 3 min on a CPU.
"""
import csv, glob, os, random, sys, time

sys.path.insert(0, os.getcwd())
import pipeline  # noqa: E402  (src/app/backend)

TIER = {"Negative": "negative", "ASC-US": "low", "LSIL": "low", "ASC-H": "high", "HSIL": "high", "SCC": "high"}
FOLDER_LABEL = {"High squamous intra-epithelial lesion": "HSIL", "Low squamous intra-epithelial lesion": "LSIL",
                "Negative for Intraepithelial malignancy": "Negative", "Squamous cell carcinoma": "SCC"}


def main():
    root = sys.argv[1]
    per_class = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    out_csv = sys.argv[3] if len(sys.argv) > 3 else "mendeley_full_pipeline_results.csv"
    rows, t0 = [], time.time()
    for folder, true in FOLDER_LABEL.items():
        files = sorted(glob.glob(os.path.join(root, folder, "*.jp*g")) + glob.glob(os.path.join(root, folder, "*.png")))
        random.Random(42).shuffle(files)
        for f in files[:per_class]:
            r = pipeline.PIPELINE.analyze(open(f, "rb").read())
            d = r.get("detections") or {}
            rows.append({"file": os.path.basename(f), "true": true, "predicted": r.get("predicted_class"), "confidence": round(r.get("confidence") or 0, 3),
                         "cells_found": d.get("found"), "cells_counted": d.get("counted"), "needs_closer_look": r.get("low_confidence"), "error": r.get("error")})
            print(len(rows), true, "->", rows[-1]["predicted"], f"{time.time() - t0:.0f}s", flush=True)
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    ok = [r for r in rows if r["predicted"]]
    exact = sum(r["predicted"] == r["true"] for r in ok)
    tier = sum(TIER[r["predicted"]] == TIER[r["true"]] for r in ok)
    abn = [r for r in ok if r["true"] != "Negative"]
    neg = [r for r in ok if r["true"] == "Negative"]
    print(f"\nexact grade right: {exact}/{len(ok)}   right tier: {tier}/{len(ok)}")
    print(f"abnormal photos flagged: {sum(r['predicted'] != 'Negative' for r in abn)}/{len(abn)}   healthy kept healthy: {sum(r['predicted'] == 'Negative' for r in neg)}/{len(neg)}")


if __name__ == "__main__":
    main()
