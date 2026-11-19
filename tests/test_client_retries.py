"""Offline tests of the retry/backoff/Retry-After/abort logic using a local fake server (no internet).

Run:  python -m unittest discover -s tests -v      (from the project root)
"""
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scrapers"))
import config  # noqa: E402
import ia_common as c  # noqa: E402

HITS = {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        HITS[self.path] = HITS.get(self.path, 0) + 1
        n = HITS[self.path]
        if self.path == "/ok":
            self._send(200, {"ok": True})
        elif self.path == "/flaky503":                    # 503 + Retry-After once, then 200
            self._send(503 if n == 1 else 200, {"n": n}, {"Retry-After": "1"} if n == 1 else {})
        elif self.path == "/always502":
            self._send(502, {})
        elif self.path == "/forbidden":
            self._send(403, {})
        elif self.path == "/notfound":
            self._send(404, {})
        elif self.path == "/longretry":
            self._send(429, {}, {"Retry-After": "9999"})
        else:
            self._send(404, {})

    def _send(self, status, body, headers=None):
        data = json.dumps(body).encode()
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        config.DELAY_SECONDS, config.BACKOFF_BASE, config.BACKOFF_CAP = 0.05, 0.1, 0.5
        config.MAX_RETRIES = 4

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        HITS.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.run_ = c.Run("test", run_dir=Path(self.tmp.name) / "r")
        self.client = c.Client(self.run_)

    def tearDown(self):
        self.tmp.cleanup()

    def attempts(self):
        return [json.loads(x) for x in self.run_.attempts_path.read_text().splitlines()]

    def test_success_first_try(self):
        resp = self.client.get(self.base + "/ok")
        self.assertEqual(resp.ia_attempts, 1)
        self.assertEqual(self.attempts()[0]["outcome"], "ok")

    def test_retry_after_is_honoured(self):
        resp = self.client.get(self.base + "/flaky503")
        self.assertEqual(resp.ia_attempts, 2)
        first = self.attempts()[0]
        self.assertEqual(first["outcome"], "retry")
        self.assertEqual(first["backoff_wait_s"], 1.0)           # Retry-After: 1 used instead of the backoff
        self.assertGreaterEqual(self.run_.pacer.backoff_sleep_s, 1.0)
        self.assertGreater(self.run_.pacer.interval, self.run_.pacer.base - 1e-9)   # slowed down after 503

    def test_gives_up_after_max_retries_with_exponential_backoff(self):
        from unittest import mock
        with mock.patch.object(c.random, "uniform", return_value=0.0), self.assertRaises(c.RequestFailed) as ctx:
            self.client.get(self.base + "/always502")          # jitter removed so the growth is deterministic
        self.assertEqual(ctx.exception.attempts, config.MAX_RETRIES + 1)
        self.assertEqual(ctx.exception.status, 502)
        waits = [a.get("backoff_wait_s") for a in self.attempts() if a["outcome"] == "retry"]
        self.assertEqual(len(waits), config.MAX_RETRIES)
        self.assertLess(waits[0], waits[2])                       # grows (until the cap)
        self.assertEqual(self.attempts()[-1]["outcome"], "failed")

    def test_404_is_not_retried(self):
        with self.assertRaises(c.RequestFailed) as ctx:
            self.client.get(self.base + "/notfound")
        self.assertEqual(ctx.exception.attempts, 1)
        self.assertEqual(HITS["/notfound"], 1)

    def test_403_aborts_the_run(self):
        with self.assertRaises(c.Abort):
            self.client.get(self.base + "/forbidden")
        self.assertEqual(HITS["/forbidden"], 1)

    def test_overlong_retry_after_aborts(self):
        with self.assertRaises(c.Abort):
            self.client.get(self.base + "/longretry")
        self.assertEqual(HITS["/longretry"], 1)

    def test_connection_error_is_retried(self):
        client = c.Client(self.run_)
        with self.assertRaises(c.RequestFailed) as ctx:
            client.get("http://127.0.0.1:9/nothing-listens")       # port 9: connection refused
        self.assertEqual(ctx.exception.attempts, config.MAX_RETRIES + 1)

    def test_circuit_breaker_after_consecutive_failed_records(self):
        with self.assertRaises(c.Abort):
            for i in range(config.BREAKER_CONSECUTIVE_FAILURES):
                self.run_.save_record({"identifier": f"x{i}", "status": "failed", "error": "test"})

    def test_success_resets_breaker_and_checkpoint_resume(self):
        for i in range(config.BREAKER_CONSECUTIVE_FAILURES - 1):
            self.run_.save_record({"identifier": f"x{i}", "status": "failed", "error": "t"})
        self.run_.save_record({"identifier": "good", "status": "ok"})
        self.assertEqual(self.run_.consecutive_failed, 0)
        resumed = c.Run("test", resume=self.run_.dir)
        ids = [(1, "good", {}), (2, "x0", {}), (3, "new", {})]
        self.assertEqual([i for _, i, _ in resumed.pending(ids)], ["new"])
        self.assertEqual([i for _, i, _ in resumed.pending(ids, retry_failed=True)], ["x0", "new"])


class ParsingTests(unittest.TestCase):
    def test_work_group_merges_volumes_and_copies(self):
        a = c.work_group("The last of the Mohicans : a narrative of 1757", ["Cooper, James Fenimore, 1789-1851"])
        b = c.work_group("Last of the Mohicans v.2", ["Cooper, James Fenimore"])
        self.assertEqual(a, b)

    def test_normalisers_seen_in_the_200_book_run(self):
        self.assertEqual(c.year_from("c1920"), 1920)
        self.assertEqual(c.year_from("c1891]"), 1891)
        self.assertEqual(c.year_from("1884"), 1884)
        self.assertIsNone(c.year_from("undated"))
        self.assertEqual(c.added_to_iso("2013-12-15 04:20:50.616587"), "2013-12-15T04:20:50Z")
        self.assertEqual(c.added_to_iso("2014-10-14 11:42:42"), "2014-10-14T11:42:42Z")
        self.assertEqual(c.language_codes("English, Yiddish"), "eng,yid")

    def test_zero_views_is_kept_but_missing_is_not(self):
        row = c.new_row("x", "api", type("R", (), {"run_id": "r"})(), 1)
        row.update(title="T", creators=["A"], publication_year=1900, subjects=["s"], language="eng",
                   addeddate="2020-01-01T00:00:00Z", scanned_page_count=100, views_all_time=0)
        self.assertEqual(c.finalize_row(row)["status"], "ok")
        row["views_all_time"] = None
        self.assertEqual(c.finalize_row(row)["status"], "partial")


if __name__ == "__main__":
    unittest.main()
