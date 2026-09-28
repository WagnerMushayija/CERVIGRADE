"""
Downloads the full CRIC Cervix cytology dataset (400 images + labels) from
Figshare, using Figshare's public API. No login or API key needed, since
the collection is public.

Why this script exists: the CRIC dataset's 400 images are posted on
Figshare as 400 separate items (not one bundled zip), so downloading them
by hand would mean 400 individual clicks. This script does it for you.

How to run it:
  1. Make sure Python 3 is installed on your computer.
  2. Open a terminal in the folder where this file is saved.
  3. Install one small library the script needs:
         pip install requests
  4. Run the script:
         python download_cric_dataset.py
  5. It will create a folder called "CRIC_dataset" next to this script,
     with all 400 images inside an "images" subfolder and the
     classification labels (classifications.csv, classifications.json,
     README.md) alongside them.

The script is safe to stop and re-run: it skips any file it has already
downloaded, so if your connection drops partway through, just run it
again and it will pick up where it left off.

2026-09-22 fix: a version of this script had a bug where a file that
failed mid-download (connection dropped after the local file was created
but before any bytes were written) would be left as a 0-byte file, and
the "skip if it already exists" check would then treat that empty file
as done forever, silently leaving it corrupted. This version now also
checks the file's size against what Figshare reports, and re-downloads
anything that's missing, empty, or smaller than expected.

2026-09-22 second fix: the script was hammering Figshare's API with one
request per article back-to-back, no pause at all, and after a few
hundred requests in a row Figshare started returning "403 Forbidden"
(rate limiting/blocking, not a real permissions problem) - and since
api_get() had no retry logic, that crashed the whole script. It now
waits briefly between API requests, and retries a 403/429/5xx response
a few times with a growing delay before giving up on that one request.

2026-09-22 third fix: this script now lives in src/preprocessing/, but it
used to save the dataset into a "CRIC_dataset" folder right next to
itself. That meant running it from src/preprocessing/ would create a
second, separate copy of the dataset there instead of reusing the one at
data/raw/CRIC_dataset. It now always saves into data/raw/CRIC_dataset
relative to the project root, no matter where the script itself is run
from, as long as it stays two folders deep (src/preprocessing/) under the
project root.
"""

import json
import os
import time
import urllib.error
import urllib.request

COLLECTION_ID = "4960286"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # src/preprocessing -> src -> project root
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "CRIC_dataset")
IMAGES_DIR = os.path.join(OUTPUT_DIR, "images")
API_BASE = "https://api.figshare.com/v2"

# Pause between API calls (not file downloads) so we don't look like a
# bot hammering Figshare. 400+ articles at ~1 request/second is what
# triggered the 403s last time.
API_REQUEST_DELAY = 1.5


def api_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "cric-dataset-downloader"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            time.sleep(API_REQUEST_DELAY)
            return result
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429) or exc.code >= 500:
                wait = 5 * (attempt + 1)
                print(f"  got HTTP {exc.code} from Figshare, backing off {wait}s "
                      f"(attempt {attempt + 1}/5)...")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"Giving up on {url} after repeated HTTP errors from Figshare")


def download_file(url, dest_path, label, expected_size=None):
    if os.path.exists(dest_path):
        actual_size = os.path.getsize(dest_path)
        if actual_size > 0 and (expected_size is None or actual_size == expected_size):
            print(f"  already have {label}, skipping")
            return
        print(f"  {label} exists but looks incomplete/corrupted (size {actual_size}"
              f"{f', expected {expected_size}' if expected_size is not None else ''}) - re-downloading")

    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cric-dataset-downloader"})
            with urllib.request.urlopen(req, timeout=60) as resp, open(dest_path, "wb") as out:
                out.write(resp.read())
            actual_size = os.path.getsize(dest_path)
            if actual_size == 0 or (expected_size is not None and actual_size != expected_size):
                raise IOError(f"downloaded file is {actual_size} bytes, expected {expected_size}")
            print(f"  downloaded {label}")
            return
        except Exception as exc:
            print(f"  attempt {attempt + 1} failed for {label}: {exc}")
            if os.path.exists(dest_path):
                os.remove(dest_path)
            time.sleep(2)
    print(f"  GIVING UP on {label} after 3 attempts, you may want to re-run the script later")


def main():
    os.makedirs(IMAGES_DIR, exist_ok=True)

    print("Fetching the list of items in the CRIC collection...")
    all_articles = []
    page = 1
    page_size = 100
    while True:
        url = f"{API_BASE}/collections/{COLLECTION_ID}/articles?page={page}&page_size={page_size}"
        batch = api_get(url)
        if not batch:
            break
        all_articles.extend(batch)
        print(f"  fetched page {page} ({len(batch)} items, {len(all_articles)} total so far)")
        if len(batch) < page_size:
            break
        page += 1

    print(f"Found {len(all_articles)} items in the collection.\n")

    for i, article in enumerate(all_articles, start=1):
        article_id = article["id"]
        title = article.get("title", str(article_id))
        try:
            detail = api_get(f"{API_BASE}/articles/{article_id}")
        except Exception as exc:
            print(f"[{i}/{len(all_articles)}] {title}")
            print(f"  SKIPPING this article for now (repeated errors: {exc}). "
                  f"Re-run the script later to pick it up.")
            continue
        files = detail.get("files", [])

        # The one article titled "CRIC Cervix Classification" holds the
        # label files (CSV/JSON/README); everything else is one image.
        is_labels_article = "classification" in title.lower()
        target_dir = OUTPUT_DIR if is_labels_article else IMAGES_DIR

        print(f"[{i}/{len(all_articles)}] {title}")
        for f in files:
            dest_name = f["name"]
            if not is_labels_article:
                # Prefix image files with the slide number so they sort
                # sensibly and never collide across articles.
                dest_name = f"{article_id}_{dest_name}"
            dest_path = os.path.join(target_dir, dest_name)
            download_file(f["download_url"], dest_path, dest_name, expected_size=f.get("size"))

    print("\nDone. Everything is in the CRIC_dataset folder next to this script.")


if __name__ == "__main__":
    main()
