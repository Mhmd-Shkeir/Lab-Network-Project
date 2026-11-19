"""Shared code for the three Internet Archive scrapers and the manifest builder.

Provides: responsible pacing (Pacer), a Requests client with retries/backoff/Retry-After and
per-attempt logging (Client), run folders with checkpoints (Run), field parsing/normalisation,
work-group keys, and Excel-friendly CSV output.

Nothing here bypasses a gate: a 403 or a verification page stops the run.
"""
import csv
import email.utils
import hashlib
import json
import platform
import random
import re
import sys
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import config


# ----------------------------------------------------------------------------- small helpers
def utcnow():
    return datetime.now(timezone.utc)


def iso(dt=None):
    return (dt or utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean(value):
    return re.sub(r"\s+", " ", str(value)).strip()


def as_list(value):
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def unique(values):
    """Clean, drop empties and de-duplicate while keeping order."""
    seen, out = set(), []
    for v in as_list(values):
        v = clean(v)
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dump_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


# ----------------------------------------------------------------------------- work groups
_VOLUME = re.compile(r"\b(?:v|vol|volume|pt|part)\.?\s*(?:\d+|[ivxlc]+)\b", re.I)
_EDITION = re.compile(
    r"\b(?:\d+(?:st|nd|rd|th)|first|second|third|fourth|fifth|new|revised|enlarged)\s+(?:ed|edition)\b\.?", re.I)


def norm_text(text):
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower().replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text)).strip()


def work_group(title, creators):
    """Group copies/volumes/editions of one work: normalised main title + first creator's surname."""
    main = re.split(r"\s[:;/]\s|\s--\s", clean(title), maxsplit=1)[0]
    main = _EDITION.sub(" ", _VOLUME.sub(" ", main))
    main = re.sub(r"^(the|a|an)\s+", "", norm_text(main))
    first = unique(creators)[0] if unique(creators) else ""
    surname = norm_text(first.split(",")[0]) if first else ""
    return f"{main}|{surname}"


def order_key(identifier):
    """Reproducible pseudo-random order (independent of Python/random versions)."""
    return hashlib.sha256(f"{config.SEED}:{identifier}".encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------------- errors
class Abort(Exception):
    """Stop the whole run (gate/403, circuit breaker, over-long Retry-After)."""


class RequestFailed(Exception):
    def __init__(self, status, message, attempts):
        super().__init__(message)
        self.status, self.attempts = status, attempts


# ----------------------------------------------------------------------------- pacing
class Pacer:
    """Gap between the END of one request and the START of the next (thread-safe).

    Deliberate waiting is accounted separately: pacing_sleep_s (normal gap) and backoff_sleep_s
    (retries / Retry-After), so active time can be reported apart from sleep.
    """

    def __init__(self, delay=None):
        self.base = self.interval = float(config.DELAY_SECONDS if delay is None else delay)
        self.pacing_sleep_s = 0.0
        self.backoff_sleep_s = 0.0
        self._last_end = None
        self._clean = 0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            if self._last_end is not None:
                gap = self.interval - (time.monotonic() - self._last_end)
                if gap > 0:
                    time.sleep(gap)
                    self.pacing_sleep_s += gap

    def done(self):
        with self._lock:
            self._last_end = time.monotonic()

    def backoff(self, seconds):
        time.sleep(seconds)
        with self._lock:
            self.backoff_sleep_s += seconds

    def slow_down(self):
        with self._lock:
            self.interval = min(self.interval * 2, config.SLOWDOWN_MAX_INTERVAL)
            self._clean = 0

    def note_ok(self):
        with self._lock:
            self._clean += 1
            if self.interval > self.base and self._clean >= config.SLOWDOWN_RECOVER_AFTER:
                self.interval = max(self.base, self.interval / 2)
                self._clean = 0


# ----------------------------------------------------------------------------- run folder
def load_ids(path, limit=None):
    """Read a manifest JSON -> list of (position, identifier, extra dict)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data["ids"] if isinstance(data, dict) else data
    out = []
    for i, item in enumerate(items, 1):
        if isinstance(item, dict):
            out.append((item.get("position", i), item["identifier"], item))
        else:
            out.append((i, item, {}))
    return out[:limit] if limit else out


class Run:
    """One scraper run: its folder, checkpoint (records.jsonl), per-attempt log, run.json, CSV."""

    def __init__(self, method, out_root=None, resume=None, label=None, ids_path=None,
                 run_dir=None, extra=None):
        self.method = method
        self.t0 = time.perf_counter()
        self.started_at = iso()
        self.extra = extra or {}
        if run_dir:
            self.dir = Path(run_dir)
            self.dir.mkdir(parents=True, exist_ok=True)
            self.run_id = self.dir.name
        elif resume:
            self.dir = Path(resume)
            if not self.dir.is_dir():
                raise SystemExit(f"--resume folder not found: {self.dir}")
            self.run_id = self.dir.name
        else:
            root = Path(out_root or config.RUNS_DIR)
            stamp = utcnow().strftime("%Y%m%d_%H%M%S")
            self.run_id = f"{method}_{stamp}" + (f"_{label}" if label else "")
            self.dir = root / self.run_id
            self.dir.mkdir(parents=True, exist_ok=False)     # a fresh run never reuses a folder
        self.records_path = self.dir / "records.jsonl"
        self.attempts_path = self.dir / "attempts.jsonl"
        self.records = {}
        self.consecutive_failed = 0
        self.segments = []
        self.resumed = bool(resume)
        self._lock = threading.Lock()
        self.pacer = Pacer()
        self.browser_startup_s = None
        self.ids_path = str(ids_path) if ids_path else None
        if resume:
            if self.records_path.exists():
                for line in self.records_path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        row = json.loads(line)
                        self.records[row["identifier"]] = row
            meta = self.dir / "run.json"
            if meta.exists():
                self.segments = json.loads(meta.read_text(encoding="utf-8")).get("segments", [])

    # -- logging
    def log_attempt(self, entry):
        entry = {"run_id": self.run_id, "method": self.method, **entry}
        with self._lock, open(self.attempts_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    def save_record(self, row):
        """Checkpoint one finished record (success, partial or failed).

        Raises Abort after BREAKER_CONSECUTIVE_FAILURES failed records in a row (circuit breaker).
        """
        with self._lock:
            self.records[row["identifier"]] = row
            with open(self.records_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            self.consecutive_failed = self.consecutive_failed + 1 if row.get("status") == "failed" else 0
            if self.consecutive_failed >= config.BREAKER_CONSECUTIVE_FAILURES:
                raise Abort(f"circuit breaker: {self.consecutive_failed} failed records in a row "
                            f"(last: {row.get('error', '')[:120]})")

    def pending(self, id_rows, retry_failed=False):
        todo = []
        for position, identifier, extra in id_rows:
            prev = self.records.get(identifier)
            if prev is None or (retry_failed and prev.get("status") == "failed"):
                todo.append((position, identifier, extra))
        return todo

    # -- finishing
    def _attempt_rows(self):
        if not self.attempts_path.exists():
            return []
        return [json.loads(x) for x in self.attempts_path.read_text(encoding="utf-8").splitlines() if x.strip()]

    def finish(self, id_rows, aborted=None):
        ordered = []
        for position, identifier, _ in id_rows:
            if identifier in self.records:
                ordered.append(self.records[identifier])
        write_records_csv(self.dir / f"{self.method}.csv", ordered)
        attempts = self._attempt_rows()
        write_flat_csv(self.dir / "attempts.csv", attempts)
        total = time.perf_counter() - self.t0
        statuses = {}
        for r in ordered:
            statuses[r.get("status", "")] = statuses.get(r.get("status", ""), 0) + 1
        elapsed = [a["elapsed_s"] for a in attempts if isinstance(a.get("elapsed_s"), (int, float))]
        segment = {
            "started_at_utc": self.started_at, "ended_at_utc": iso(),
            "total_s": round(total, 3),
            "pacing_sleep_s": round(self.pacer.pacing_sleep_s, 3),
            "backoff_sleep_s": round(self.pacer.backoff_sleep_s, 3),
            "browser_startup_s": None if self.browser_startup_s is None else round(self.browser_startup_s, 3),
            "active_s_estimate": round(total - self.pacer.pacing_sleep_s - self.pacer.backoff_sleep_s, 3),
            "aborted": aborted,
        }
        self.segments.append(segment)
        summary = {
            "run_id": self.run_id, "method": self.method, "ids_file": self.ids_path,
            "ids_requested": len(id_rows), "records_saved": len(ordered), "status_counts": statuses,
            "attempts_logged_total": len(attempts),
            "retry_attempts_total": sum(1 for a in attempts if a.get("attempt", 1) > 1),
            "attempt_seconds": {
                "n": len(elapsed), "mean": round(sum(elapsed) / len(elapsed), 3) if elapsed else None,
                "median": round(sorted(elapsed)[len(elapsed) // 2], 3) if elapsed else None,
                "max": round(max(elapsed), 3) if elapsed else None,
            },
            "decoded_body_bytes_total": sum(a.get("decoded_bytes") or 0 for a in attempts),
            "delay_seconds_setting": self.pacer.base, "user_agent": config.USER_AGENT,
            "resumed": self.resumed, "segments": self.segments,
            "notes": "Timings are pilot/collection timings, not the final network comparison. "
                     "decoded_body_bytes_total is decoded response body size, not wire bandwidth.",
            "environment": environment_info(), **self.extra,
        }
        dump_json(self.dir / "run.json", summary)
        return summary


def environment_info():
    info = {"python": sys.version.split()[0], "platform": platform.platform(), "machine": platform.machine()}
    for mod in ("requests", "bs4", "selenium"):
        try:
            info[mod] = __import__(mod).__version__
        except Exception:
            info[mod] = None
    return info


# ----------------------------------------------------------------------------- HTTP client
def _retry_after_seconds(value):
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            when = email.utils.parsedate_to_datetime(value)
            return max(0.0, (when - utcnow()).total_seconds())
        except Exception:
            return None


class Client:
    """requests.Session with pacing, retries, exponential backoff, Retry-After and attempt logging."""

    def __init__(self, run):
        import requests
        self.requests = requests
        self.run = run
        self.pacer = run.pacer
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.USER_AGENT, "Accept": "*/*"})

    def get(self, url, params=None, context=None):
        """GET with retries. Returns the response (HTTP 200) or raises RequestFailed / Abort."""
        last_status, last_error = None, None
        for attempt in range(1, config.MAX_RETRIES + 2):
            self.pacer.wait()
            started, t0 = iso(), time.perf_counter()
            resp, exc = None, None
            try:
                resp = self.session.get(url, params=params, timeout=(config.CONNECT_TIMEOUT, config.READ_TIMEOUT))
            except self.requests.RequestException as e:
                exc = e
            elapsed = time.perf_counter() - t0
            self.pacer.done()
            entry = {
                "context": context, "attempt": attempt, "started_at_utc": started,
                "elapsed_s": round(elapsed, 4),
                "url": (resp.request.url if resp is not None else url)[:300],
                "status": resp.status_code if resp is not None else None,
                "decoded_bytes": len(resp.content) if resp is not None else None,
                "redirects": len(resp.history) if resp is not None else None,
                "final_url": resp.url[:300] if resp is not None else None,
                "error": f"{type(exc).__name__}: {exc}"[:300] if exc else None,
            }
            retry_wait, outcome = None, "ok"
            if exc is None and resp.status_code == 200:
                self.pacer.note_ok()
                entry["outcome"] = outcome
                self.run.log_attempt(entry)
                resp.ia_attempts = attempt
                return resp
            if exc is None:
                last_status, last_error = resp.status_code, f"HTTP {resp.status_code}"
                if resp.status_code == 403:
                    entry["outcome"] = "abort_403"
                    self.run.log_attempt(entry)
                    raise Abort(f"HTTP 403 for {url[:120]} - stopping, no workaround attempted")
                retryable = resp.status_code in config.RETRY_STATUSES
                ra = _retry_after_seconds(resp.headers.get("Retry-After"))
                entry["retry_after_s"] = ra
                if resp.status_code in (429, 503):
                    self.pacer.slow_down()
            else:
                last_status, last_error = None, entry["error"]
                retryable, ra = True, None
            if retryable and attempt <= config.MAX_RETRIES:
                if ra is not None and ra > config.MAX_RETRY_AFTER:
                    entry["outcome"] = "abort_retry_after_too_long"
                    self.run.log_attempt(entry)
                    raise Abort(f"Retry-After {ra:.0f}s exceeds the {config.MAX_RETRY_AFTER:.0f}s cap")
                retry_wait = ra if ra is not None else min(
                    config.BACKOFF_CAP, config.BACKOFF_BASE * 2 ** (attempt - 1)) + random.uniform(0, 1)
                entry["outcome"], entry["backoff_wait_s"] = "retry", round(retry_wait, 3)
                self.run.log_attempt(entry)
                self.pacer.backoff(retry_wait)
                continue
            entry["outcome"] = "failed"
            self.run.log_attempt(entry)
            break
        raise RequestFailed(last_status, last_error or "request failed", attempt)


# ----------------------------------------------------------------------------- records
LANGUAGE_CODES = {"english": "eng", "french": "fre", "german": "ger", "latin": "lat", "spanish": "spa",
                  "italian": "ita", "dutch": "dut", "welsh": "wel", "greek": "gre", "yiddish": "yid",
                  "hebrew": "heb", "russian": "rus", "portuguese": "por", "swedish": "swe", "danish": "dan",
                  "norwegian": "nor", "polish": "pol", "czech": "cze", "chinese": "chi", "japanese": "jpn",
                  "arabic": "ara", "irish": "gle", "hungarian": "hun", "finnish": "fin", "turkish": "tur",
                  "hindi": "hin", "korean": "kor", "romanian": "rum", "icelandic": "ice", "catalan": "cat",
                  "esperanto": "epo", "scottish gaelic": "gla", "afrikaans": "afr", "ukrainian": "ukr",
                  "persian": "per", "sanskrit": "san", "tagalog": "tgl", "ancient greek": "grc",
                  "middle english": "enm", "old english": "ang", "multiple languages": "mul"}


def new_row(identifier, method, run, position):
    return {
        "identifier": identifier, "title": "", "creators": [], "first_creator": "",
        "publication_year": None, "subjects": [], "language": "", "addeddate": "",
        "scanned_page_count": None, "views_all_time": None,
        "item_url": config.DETAIL_URL + identifier, "method": method, "status": "failed", "error": "",
        "http_status": "", "attempts": 0, "retrieved_from": "", "retrieved_at_utc": "",
        "run_id": run.run_id, "manifest_position": position,
    }


def finalize_row(row, extra_errors=()):
    """Set first_creator and status ('ok' / 'partial'); list every missing required field."""
    row["creators"] = unique(row["creators"])
    row["first_creator"] = row["creators"][0] if row["creators"] else ""
    missing = []
    for field in config.REQUIRED_FIELDS:
        value = row[field]
        if value is None or value == "" or value == []:
            missing.append(field)
    errors = [e for e in [row.get("error", "")] + list(extra_errors) if e]
    if missing:
        errors.append("missing: " + ",".join(missing))
    row["status"] = "partial" if missing else "ok"
    row["error"] = "; ".join(errors)
    return row


def failed_row(row, message, http_status=""):
    row["status"], row["error"], row["http_status"] = "failed", message, http_status
    return row


def to_int(text):
    text = clean(text).replace(",", "")
    return int(text) if re.fullmatch(r"\d+", text) else None


def year_from(text):
    """First 4-digit year; also reads 'c1920', '[1891]', '1884.' (no word boundary needed)."""
    m = re.search(r"(?<!\d)(\d{4})(?!\d)", str(text or ""))
    return int(m.group(1)) if m else None


def language_codes(text):
    parts = [clean(p) for p in re.split(r"[,;]", str(text or "")) if clean(p)]
    return ",".join(LANGUAGE_CODES.get(p.lower(), p) for p in parts)


def added_to_iso(text):
    """'2013-12-15 04:20:50[.616587]' -> '2013-12-15T04:20:50Z' (fraction of a second dropped, as in the API)."""
    text = clean(text)
    m = re.fullmatch(r"(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d)(?:\.\d+)?", text)
    return f"{m.group(1)}T{m.group(2)}Z" if m else text


def looks_like_gate(final_url, title):
    probe = f"{final_url} {title}".lower()
    return any(k in probe for k in ("verify_human", "human verification", "captcha", "are you a robot"))


def parse_detail_html(html):
    """BeautifulSoup extraction from an archive.org /details/<id> page. Missing values stay empty."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    page_title = clean(soup.title.get_text(" ", strip=True)) if soup.title else ""
    meta = {}
    for dl in soup.select("dl.metadata-definition"):
        for dt in dl.find_all("dt", recursive=False):
            dd = dt.find_next_sibling("dd")
            if dd is not None:
                meta[clean(dt.get_text(" ", strip=True)).lower()] = dd
    h1 = soup.select_one("h1.item-title")
    creator_block = soup.select_one('dl[aria-label="Item creator metadata"]')
    views = soup.select_one('section.item-stats-summary [itemprop="userInteractionCount"]')

    def text(key):
        return clean(meta[key].get_text(" ", strip=True)) if key in meta else ""

    return {
        "page_title": page_title, "has_h1": h1 is not None,
        "title": clean(h1.get_text(" ", strip=True)) if h1 else "",
        "creators": unique([a.get_text(" ", strip=True) for a in creator_block.select("a")]) if creator_block else [],
        "publication_year": year_from(text("publication date")),
        "subjects": unique([a.get_text(" ", strip=True) for a in meta["topics"].select("a")]) if "topics" in meta else [],
        "language": language_codes(text("language")),
        "addeddate": added_to_iso(text("addeddate")),
        "scanned_page_count": to_int(text("pages")),
        "views_all_time": to_int(views.get_text(strip=True)) if views is not None else None,
    }


# ----------------------------------------------------------------------------- CSV output
def _cell(value):
    if isinstance(value, list):
        return config.LIST_SEPARATOR.join(str(v) for v in value)
    return "" if value is None else value


def write_records_csv(path, rows, fields=None):
    """UTF-8 with BOM so Excel opens accents correctly; lists are joined with ' | '."""
    fields = fields or config.CSV_FIELDS
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _cell(row.get(k)) for k in fields})


def write_flat_csv(path, rows):
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=keys or ["empty"], extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: _cell(r.get(k)) if not isinstance(r.get(k), (dict, list)) or isinstance(r.get(k), list)
                             else json.dumps(r.get(k), ensure_ascii=False) for k in keys})


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# ----------------------------------------------------------------------------- CLI
def add_common_args(parser, default_ids="data/manifest/benchmark_200_ids.json"):
    parser.add_argument("--ids", default=str(config.PROJECT_ROOT / default_ids),
                        help="manifest JSON with the identifiers to collect")
    parser.add_argument("--limit", type=int, help="only the first N manifest ids (validation runs)")
    parser.add_argument("--out-root", default=str(config.RUNS_DIR), help="folder that gets one new run folder")
    parser.add_argument("--label", help="suffix for the new run folder name")
    parser.add_argument("--resume", help="resume an existing run folder instead of starting fresh")
    parser.add_argument("--retry-failed", action="store_true", help="with --resume: try failed ids again")
    parser.add_argument("--delay", type=float, help=f"seconds between requests (default {config.DELAY_SECONDS})")
    parser.add_argument("--final-csv", help="also write the finished CSV to this path")


def start_run(method, args, extra=None):
    """Create the run (fresh folder, or --resume) and apply --delay. Returns (run, id_rows, todo)."""
    id_rows = load_ids(args.ids, args.limit)
    run = Run(method, out_root=args.out_root, resume=args.resume, label=args.label,
              ids_path=args.ids, extra=extra)
    if args.delay is not None:
        run.pacer.base = run.pacer.interval = float(args.delay)
    todo = run.pending(id_rows, retry_failed=args.retry_failed)
    print(f"[{run.run_id}] {len(id_rows)} ids in manifest, {len(todo)} to collect -> {run.dir}", flush=True)
    return run, id_rows, todo


def execute(run, id_rows, args, work):
    """Run work(); always write CSV/run.json (also after an abort). Returns a process exit code."""
    aborted = None
    try:
        work()
    except Abort as exc:
        aborted = str(exc)
        print(f"ABORTED: {aborted}", flush=True)
    except KeyboardInterrupt:
        aborted = "interrupted by user"
        print("INTERRUPTED", flush=True)
    finally:
        summary = run.finish(id_rows, aborted)
        if args.final_csv:
            rows = [run.records[i] for _, i, _ in id_rows if i in run.records]
            write_records_csv(args.final_csv, rows)
        print(json.dumps({k: summary[k] for k in ("run_id", "status_counts", "attempts_logged_total",
                                                   "retry_attempts_total", "segments")}, indent=1), flush=True)
    return 1 if aborted else 0
