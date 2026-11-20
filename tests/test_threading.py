"""Offline tests of the bounded multithreading option and its GLOBAL request limit (local fake servers, no internet).

Run:  python -m unittest discover -s tests -v      (from the project root)
"""
import json
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scrapers"))
import config  # noqa: E402
import ia_api_scraper  # noqa: E402
import ia_bs4_scraper  # noqa: E402
import ia_common as c  # noqa: E402
import ia_selenium_scraper  # noqa: E402

LOCK, STATE = threading.Lock(), {"hits": 0, "latency": 0.0, "first_429": False}

PAGE = """<html><head><title>{i} : Internet Archive</title></head><body>
<h1 class="item-title">Book {i}</h1>
<dl aria-label="Item creator metadata"><dd><a>Writer, A</a></dd></dl>
<dl class="metadata-definition"><dt>Publication date</dt><dd>c1900</dd><dt>Topics</dt><dd><a>Fantasy</a></dd>
<dt>Language</dt><dd>English</dd><dt>Addeddate</dt><dd>2020-01-01 10:00:00.123</dd><dt>Pages</dt><dd>100</dd></dl>
<section class="item-stats-summary"><span itemprop="userInteractionCount">12</span></section></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        with LOCK:
            STATE["hits"] += 1
            first = STATE["hits"] == 1 and STATE["first_429"]
        time.sleep(STATE["latency"])
        if "ratelimited" in self.path and first:
            return self._send(429, b"slow down", "text/plain", {"Retry-After": "1"})
        if self.path.startswith("/details/"):
            return self._send(200, PAGE.format(i=self.path.rsplit("/", 1)[1]).encode(), "text/html")
        if self.path.startswith("/search"):
            return self._send(200, json.dumps({"response": {"docs": [
                {"identifier": i, "title": f"Book {i}", "creator": "Writer, A", "year": 1900, "subject": ["Fantasy"],
                 "language": ["eng"], "addeddate": "2020-01-01T10:00:00Z", "imagecount": 100}
                for i in self._ids("q")]}}).encode(), "application/json")
        if self.path.startswith("/views/"):
            ids = self.path.split("/views/", 1)[1].split(",")
            return self._send(200, json.dumps({i: {"have_data": True, "all_time": 5, "last_30day": 1, "last_7day": 0}
                                               for i in ids}).encode(), "application/json")
        self._send(200, b"{}", "application/json")

    def _ids(self, key):
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(self.path).query)[key][0]
        return [x.strip('" ') for x in q.replace("identifier:(", "").rstrip(")").split(" OR ")]

    def _send(self, status, body, ctype, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def write_manifest(folder, n):
    path = Path(folder) / "ids.json"
    path.write_text(json.dumps({"ids": [{"identifier": f"book{i:02d}", "position": i} for i in range(1, n + 1)]}))
    return path


class ThreadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        STATE.update(hits=0, latency=0.0, first_429=False)
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [mock.patch.object(config, "MIN_ALLOWED_INTERVAL", 0.01),
                        mock.patch.object(config, "DETAIL_URL", self.base + "/details/"),
                        mock.patch.object(config, "SEARCH_URL", self.base + "/search"),
                        mock.patch.object(config, "VIEWS_URL", self.base + "/views/")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def run_json(self):
        folder = next((Path(self.tmp.name) / "runs").iterdir())
        return folder, json.loads((folder / "run.json").read_text())

    # -- the limiter itself
    def test_sequential_pacer_does_not_give_a_global_limit_across_threads(self):
        """Documents why a new limiter was needed: the end-to-start gap lets all threads start together."""
        pacer, starts = c.Pacer(0.2), []

        def worker():
            pacer.wait()
            starts.append(time.monotonic())
            time.sleep(0.3)                       # the "request"
            pacer.done()
        threads = [threading.Thread(target=worker) for _ in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        starts.sort()
        self.assertLess(min(b - a for a, b in zip(starts, starts[1:])), 0.1)

    def test_shared_limiter_spaces_request_starts_across_all_threads(self):
        limiter, starts, lock = c.SharedRateLimiter(0.1), [], threading.Lock()

        def worker():
            for _ in range(5):
                limiter.wait()
                with lock:
                    starts.append(time.monotonic())
                time.sleep(0.25)                  # slow "request": threads overlap, starts still spaced
        threads = [threading.Thread(target=worker) for _ in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        starts.sort()
        self.assertEqual(len(starts), 20)
        self.assertGreaterEqual(min(b - a for a, b in zip(starts, starts[1:])), 0.1 - 0.04)

    def test_hold_pauses_workers_that_already_reserved_a_slot(self):
        limiter, times, lock = c.SharedRateLimiter(0.05), [], threading.Lock()
        limiter.wait()                            # first start at ~0
        threads = []

        def worker():
            limiter.wait()
            with lock:
                times.append(time.monotonic())
        t0 = time.monotonic()
        for _ in range(3):
            threads.append(threading.Thread(target=worker))
            threads[-1].start()
        time.sleep(0.02)                          # they are sleeping on their slots now
        limiter.hold(0.6)
        [t.join() for t in threads]
        self.assertGreaterEqual(min(times) - t0, 0.55)

    # -- bounds
    def test_bounds_are_enforced(self):
        manifest = write_manifest(self.tmp.name, 2)
        base = ["--ids", str(manifest), "--out-root", str(Path(self.tmp.name) / "runs")]
        with mock.patch.object(config, "MIN_ALLOWED_INTERVAL", 0.5):
            for bad in (["--workers", "0"], ["--workers", "9"], ["--workers", "2", "--min-interval", "0.1"],
                        ["--min-interval", "3"], ["--workers", "2", "--delay", "1"]):
                with self.assertRaises(SystemExit, msg=str(bad)):
                    ia_bs4_scraper.main(base + bad)
            with self.assertRaises(SystemExit):               # Selenium cap is lower (one Chrome per worker)
                ia_selenium_scraper.main(base + ["--workers", "5"])

    # -- whole scrapers against local servers
    def test_bs4_threads_share_one_global_limit_and_keep_all_records(self):
        STATE["latency"] = 0.35                     # slower than the interval, so the workers really overlap
        manifest = write_manifest(self.tmp.name, 12)
        code = ia_bs4_scraper.main(["--ids", str(manifest), "--out-root", str(Path(self.tmp.name) / "runs"),
                                    "--workers", "4", "--min-interval", "0.1", "--label", "t4"])
        folder, meta = self.run_json()
        rate = meta["rate_limit"]
        self.assertEqual(code, 0)
        self.assertEqual(meta["status_counts"], {"ok": 12})
        self.assertEqual((rate["mode"], rate["workers"]), ("shared_start_interval", 4))
        self.assertGreaterEqual(rate["min_start_gap_s"], 0.1 - 0.04)        # the global limit held
        self.assertGreaterEqual(rate["max_requests_in_flight"], 2)          # and the threads did overlap
        self.assertLessEqual(rate["max_requests_in_flight"], 4)             # bounded by the worker count
        self.assertIsNone(meta["segments"][-1]["active_s_estimate"])        # not derivable with several workers
        rows = (folder / "bs4.csv").read_text(encoding="utf-8-sig").splitlines()[1:]
        self.assertEqual([r.split(",")[0] for r in rows], [f"book{i:02d}" for i in range(1, 13)])   # manifest order
        workers = {json.loads(x)["worker"] for x in (folder / "attempts.jsonl").read_text().splitlines()}
        self.assertTrue(workers <= {f"worker-{n}" for n in range(1, 5)} and len(workers) >= 2)

    def test_threads_are_faster_than_sequential_only_because_latency_overlaps(self):
        STATE["latency"] = 0.3
        manifest = write_manifest(self.tmp.name, 8)
        out = str(Path(self.tmp.name) / "runs")
        t = time.perf_counter()
        ia_bs4_scraper.main(["--ids", str(manifest), "--out-root", out, "--workers", "1", "--min-interval", "0.1",
                             "--label", "w1"])
        one = time.perf_counter() - t
        t = time.perf_counter()
        ia_bs4_scraper.main(["--ids", str(manifest), "--out-root", out, "--workers", "4", "--min-interval", "0.1",
                             "--label", "w4"])
        four = time.perf_counter() - t
        self.assertLess(four, one)                  # 8 x 0.3 s sequential vs overlapping with a 0.1 s start cap
        self.assertGreaterEqual(four, 7 * 0.1)      # but never faster than the global cap allows

    def test_429_with_retry_after_pauses_all_workers(self):
        STATE["first_429"] = True
        STATE["latency"] = 0.05
        manifest = Path(self.tmp.name) / "ids.json"
        manifest.write_text(json.dumps({"ids": [f"ratelimited{i}" for i in range(6)]}))
        ia_bs4_scraper.main(["--ids", str(manifest), "--out-root", str(Path(self.tmp.name) / "runs"),
                             "--workers", "3", "--min-interval", "0.1"])
        folder, meta = self.run_json()
        attempts = [json.loads(x) for x in (folder / "attempts.jsonl").read_text().splitlines()]
        first = next(a for a in attempts if a["status"] == 429)
        # requests already in flight when the 429 arrived may finish; nothing may START after it for ~Retry-After
        later = [a["t_start_s"] for a in attempts if a is not first and a["t_start_s"] >= first["t_end_s"]]
        self.assertEqual(meta["status_counts"], {"ok": 6})
        self.assertTrue(later)
        self.assertGreaterEqual(min(later), first["t_end_s"] + 0.9)         # nobody started during Retry-After: 1
        self.assertGreater(meta["rate_limit"]["interval_s_at_end"], 0.1 - 1e-9)   # shared interval slowed down

    def test_abort_in_one_worker_stops_the_others(self):
        done, lock = [], threading.Lock()

        def handler(item):
            if item == 3:
                raise c.Abort("simulated 403")
            time.sleep(0.05)
            with lock:
                done.append(item)
        with self.assertRaises(c.Abort):
            c.run_parallel(list(range(1, 101)), handler, 4)
        self.assertLess(len(done), 100)

    def test_api_threads_collect_batches_in_parallel(self):
        STATE["latency"] = 0.25
        manifest = write_manifest(self.tmp.name, 10)
        code = ia_api_scraper.main(["--ids", str(manifest), "--out-root", str(Path(self.tmp.name) / "runs"),
                                    "--batch-size", "2", "--workers", "3", "--min-interval", "0.1"])
        folder, meta = self.run_json()
        self.assertEqual(code, 0)
        self.assertEqual(meta["status_counts"], {"ok": 10})
        self.assertEqual(meta["attempts_logged_total"], 10)                 # 5 batches x (search + views)
        self.assertGreaterEqual(meta["rate_limit"]["min_start_gap_s"], 0.1 - 0.04)

    def test_selenium_workers_each_own_a_browser_and_share_the_limit(self):
        drivers, lock = [], threading.Lock()

        class FakeDriver:
            title, current_url = "A book", ""

            def __init__(self):
                self.events, self.quit_called = [], False

            def get(self, url):
                self.current_url = url
                msgs = [{"method": "Network.requestWillBeSent", "params": {"request": {"url": url}}},
                        {"method": "Network.responseReceived", "params": {
                            "type": "Document", "response": {"status": 200, "headers": {}}}},
                        {"method": "Network.loadingFinished", "params": {"encodedDataLength": 100}}]
                self.events = [{"message": json.dumps({"message": m})} for m in msgs]
                time.sleep(0.2)

            def get_log(self, name):
                out, self.events = self.events, []
                return out

            def find_elements(self, *a):
                return [object()]

            def quit(self):
                self.quit_called = True

        def fake_build(args, profile):
            d = FakeDriver()
            with lock:
                drivers.append(d)
            return d, dict(browser_version="fake", driver_version="fake", chrome_binary="fake", chromedriver="fake")
        parsed = dict(title="A book", creators=["W"], publication_year=1900, subjects=["Fantasy"], language="eng",
                      addeddate="2020-01-01T00:00:00Z", scanned_page_count=100, views_all_time=12)
        manifest = write_manifest(self.tmp.name, 6)
        with mock.patch.object(ia_selenium_scraper, "build_driver", side_effect=fake_build), \
                mock.patch.object(ia_selenium_scraper, "extract", return_value=parsed):
            code = ia_selenium_scraper.main(["--ids", str(manifest), "--out-root", str(Path(self.tmp.name) / "runs"),
                                             "--workers", "2", "--min-interval", "0.1"])
        folder, meta = self.run_json()
        self.assertEqual(code, 0)
        self.assertEqual(meta["status_counts"], {"ok": 6})
        self.assertEqual(len(drivers), 2)                                   # one browser per worker
        self.assertTrue(all(d.quit_called for d in drivers))
        self.assertGreaterEqual(meta["rate_limit"]["min_start_gap_s"], 0.1 - 0.04)
        self.assertEqual(len((folder / "page_metrics.csv").read_text(encoding="utf-8-sig").splitlines()), 7)


if __name__ == "__main__":
    unittest.main()
