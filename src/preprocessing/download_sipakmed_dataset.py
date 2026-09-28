"""
Downloads the SIPaKMeD cervical Pap smear cell dataset (Plissiti et al.,
2018) directly from its official host at the University of Ioannina.

Unlike CRIC, this dataset isn't split across hundreds of API items - it's
5 archive files (one per cell-type category: Superficial-Intermediate,
Parabasal, Koilocytotic, Metaplastic, Dyskeratotic) plus one description
PDF, all served as plain, directly-downloadable files. No API, no login.

Citation the dataset's own page asks for (keep this in your references):
  Marina E. Plissiti, Panagiotis Dimitrakopoulos, Giorgos Sfikas,
  Christophoros Nikou, Olga Krikoni, Antonia Charchanti, "SIPAKMED: A new
  dataset for feature and image based classification of normal and
  pathological cervical cells in Pap smear images", IEEE International
  Conference on Image Processing (ICIP) 2018, Athens, Greece.

What this script does NOT download, on purpose: the precomputed
handcrafted/deep feature files the site also hosts (Features_CELL.7z,
FcFeatures.rar, ConvFeatures.rar). Those are features someone else already
extracted with their own pipeline - not useful here, since CerviGrade
fine-tunes its own models directly on the raw images.

How to run it:
  1. Make sure Python 3 is installed on your computer.
  2. Install the one library this script needs, for reading .7z archives:
         pip install py7zr
  3. Open a terminal anywhere inside the project folder and run:
         python src/preprocessing/download_sipakmed_dataset.py
  4. It creates data/raw/SIPaKMeD/, with one subfolder of images per cell
     type, plus the description PDF.

Safe to stop and re-run: it skips any archive it has already downloaded
and successfully extracted, so a dropped connection just means running it
again.
"""

import os
import time
import urllib.error
import urllib.request

import py7zr

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # src/preprocessing -> src -> project root
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "SIPaKMeD")

BASE_URL = "https://www.cs.uoi.gr/~marina/SIPAKMED"

# (archive filename on the server, folder name to extract it into)
CATEGORY_ARCHIVES = [
    ("im_Superficial-Intermediate.7z", "Superficial-Intermediate"),
    ("im_Parabasal.7z", "Parabasal"),
    ("im_Koilocytotic.7z", "Koilocytotic"),
    ("im_Metaplastic.7z", "Metaplastic"),
    ("im_Dyskeratotic.7z", "Dyskeratotic"),
]
DESCRIPTION_PDF = "Description_of_Features.pdf"

# Small pause between requests - same courtesy as the CRIC script, so we
# don't hammer someone's university web server either.
REQUEST_DELAY = 1.0


def download_with_retries(url, dest_path, label, attempts=5):
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        print(f"  already have {label}, skipping download")
        return True

    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cervigrade-dataset-downloader"})
            with urllib.request.urlopen(req, timeout=120) as resp, open(dest_path, "wb") as out:
                out.write(resp.read())
            if os.path.getsize(dest_path) == 0:
                raise IOError("downloaded file is 0 bytes")
            print(f"  downloaded {label}")
            time.sleep(REQUEST_DELAY)
            return True
        except Exception as exc:
            print(f"  attempt {attempt + 1} failed for {label}: {exc}")
            if os.path.exists(dest_path):
                os.remove(dest_path)
            wait = 5 * (attempt + 1)
            time.sleep(wait)
    print(f"  GIVING UP on {label} after {attempts} attempts, re-run the script later to retry")
    return False


def extract_archive(archive_path, extract_to, label):
    marker = os.path.join(extract_to, ".extracted_ok")
    if os.path.exists(marker):
        print(f"  {label} already extracted, skipping")
        return True

    os.makedirs(extract_to, exist_ok=True)
    try:
        with py7zr.SevenZipFile(archive_path, mode="r") as archive:
            archive.extractall(path=extract_to)
        # Extraction succeeding (no exception) is itself the integrity
        # check: a corrupted/truncated .7z raises during extractall.
        with open(marker, "w") as f:
            f.write("ok\n")
        print(f"  extracted {label}")
        return True
    except Exception as exc:
        print(f"  FAILED to extract {label}: {exc}")
        print(f"  deleting the archive so a re-run downloads it fresh: {archive_path}")
        if os.path.exists(archive_path):
            os.remove(archive_path)
        return False


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Saving SIPaKMeD into: {OUTPUT_DIR}\n")

    all_ok = True
    for archive_name, folder_name in CATEGORY_ARCHIVES:
        print(f"[{folder_name}]")
        archive_path = os.path.join(OUTPUT_DIR, archive_name)
        url = f"{BASE_URL}/{archive_name}"
        ok = download_with_retries(url, archive_path, archive_name)
        if not ok:
            all_ok = False
            continue

        extract_to = os.path.join(OUTPUT_DIR, folder_name)
        ok = extract_archive(archive_path, extract_to, folder_name)
        all_ok = all_ok and ok

    # Grab the description PDF too - useful reference, tiny file.
    pdf_path = os.path.join(OUTPUT_DIR, DESCRIPTION_PDF)
    download_with_retries(f"{BASE_URL}/{DESCRIPTION_PDF}", pdf_path, DESCRIPTION_PDF)

    print()
    if all_ok:
        print("Done. All 5 categories downloaded and extracted successfully.")
    else:
        print("Finished, but at least one category failed - re-run this script to retry just that one.")


if __name__ == "__main__":
    main()
