"""Shared settings for all scrapers (Internet Archive book project).

Source: Internet Archive (https://archive.org), Americana collection, English fiction texts.
Open Library / dBooks / LibriVox experiments are kept as history (see HISTORY.md) and are NOT used here.

Everything that can differ between machines is read from environment variables
(see docs/SETUP_UBUNTU_VM.md); nothing in this file is tied to Windows, WSL or one browser path.
"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MANIFEST_DIR = DATA_DIR / "manifest"
RUNS_DIR = DATA_DIR / "runs"

# ---- Candidate pool (frozen in data/manifest/manifest_meta.json) -------------------------
POOL_COLLECTION = "americana"
YEAR_MIN, YEAR_MAX = 1800, 2020
IMAGECOUNT_MIN, IMAGECOUNT_MAX = 50, 1500
POOL_QUERY = (
    f"collection:{POOL_COLLECTION} AND mediatype:texts AND language:eng AND subject:fiction "
    f"AND creator:* AND year:[{YEAR_MIN} TO {YEAR_MAX}] "
    f"AND imagecount:[{IMAGECOUNT_MIN} TO {IMAGECOUNT_MAX}]"
)
SNAPSHOT_FIELDS = ["identifier", "title", "creator", "year", "imagecount", "addeddate", "language"]

# ---- Sampling -----------------------------------------------------------------------------
SEED = 2026                  # items are ordered by sha256(f"{SEED}:{identifier}")
BENCHMARK_SIZE = 200
TRAINING_TARGET = 2000
BENCHMARK_GROUP_CAP = 1      # at most 1 item per work_group in the 200 benchmark books
TRAINING_GROUP_CAP = 3       # at most 3 items per work_group in the training set
VIEWS_CHECK_BATCH = 50       # ids per Views API call (100 ids returned HTTP 502 for one tested set; 50 works)

# ---- Endpoints -----------------------------------------------------------------------------
SEARCH_URL = "https://archive.org/advancedsearch.php"
SCRAPE_URL = "https://archive.org/services/search/v1/scrape"
VIEWS_URL = "https://be-api.us.archive.org/views/v1/short/"
DETAIL_URL = "https://archive.org/details/"

# ---- Responsible access (see https://archive.org/developers/bots.html) ---------------------
# The guide asks for tool name + version and, for AI agents, the model used. Add your own
# contact text with LABNET_CONTACT (optional, never committed).
_base_ua = "LabNetProject/1.0 (university networking lab project; code written with claude-sonnet-5-5)"
USER_AGENT = os.environ.get("LABNET_USER_AGENT") or (
    _base_ua + (f" contact:{os.environ['LABNET_CONTACT']}" if os.environ.get("LABNET_CONTACT") else "")
)
DELAY_SECONDS = float(os.environ.get("LABNET_DELAY", "3.0"))  # gap between end of one request and start of next
CONNECT_TIMEOUT = float(os.environ.get("LABNET_CONNECT_TIMEOUT", "15"))
READ_TIMEOUT = float(os.environ.get("LABNET_READ_TIMEOUT", "45"))
MAX_RETRIES = int(os.environ.get("LABNET_MAX_RETRIES", "4"))   # retries after the first attempt (5 attempts total)
BACKOFF_BASE = 2.0               # waits 2, 4, 8, 16 s (+ jitter), capped
BACKOFF_CAP = 60.0
MAX_RETRY_AFTER = 120.0          # longer Retry-After than this stops the run instead of waiting
RETRY_STATUSES = {408, 429, 500, 502, 503, 504}
BREAKER_CONSECUTIVE_FAILURES = 5  # stop the run after this many failed records in a row
MAX_WORKERS = 8                  # hard cap for --workers (API / BS4)
MAX_WORKERS_SELENIUM = 4         # one Chrome per worker, so a lower cap
MIN_ALLOWED_INTERVAL = 0.5       # --min-interval below this is refused (no unthrottled runs); total cap = 1 / interval
SLOWDOWN_MAX_INTERVAL = 30.0     # delay doubles on 429/503 up to this value
SLOWDOWN_RECOVER_AFTER = 50      # clean requests before the delay halves again

# ---- Scraper defaults ----------------------------------------------------------------------
API_BATCH_SIZE = int(os.environ.get("LABNET_API_BATCH", "50"))

# ---- CSV schema (same data fields for all three methods) -----------------------------------
DATA_FIELDS = [
    "identifier", "title", "creators", "first_creator", "publication_year", "subjects",
    "language", "addeddate", "scanned_page_count", "views_all_time",
]
PROVENANCE_FIELDS = [
    "item_url", "method", "status", "error", "http_status", "attempts",
    "retrieved_from", "retrieved_at_utc", "run_id", "manifest_position",
]
CSV_FIELDS = DATA_FIELDS + PROVENANCE_FIELDS
REQUIRED_FIELDS = [
    "title", "creators", "publication_year", "subjects", "language",
    "addeddate", "scanned_page_count", "views_all_time",
]
LIST_SEPARATOR = " | "           # lists (creators, subjects) are joined with this in the CSVs
