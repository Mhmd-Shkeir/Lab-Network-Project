"""Offline checks for median calculation and browser recovery after a temporary HTTP error."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scrapers"))
import config
import ia_common
import ia_selenium_scraper


class MeasurementTests(unittest.TestCase):
    def test_even_number_of_request_times_uses_conventional_median(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = ia_common.Run("test", run_dir=Path(tmp) / "run")
            for value in (1.0, 2.0, 8.0, 20.0):
                run.log_attempt({"attempt": 1, "elapsed_s": value})
            result = run.finish([])
            self.assertEqual(result["attempt_seconds"]["median"], 5.0)

    def test_browser_recovers_from_503_then_200(self):
        class FakeDriver:
            title = "A book"
            current_url = ""

            def __init__(self):
                self.calls = 0
                self.events = []

            def get(self, url):
                self.calls += 1
                self.current_url = url
                status = 503 if self.calls == 1 else 200
                messages = [
                    {"method": "Network.requestWillBeSent", "params": {"request": {"url": url}}},
                    {"method": "Network.responseReceived", "params": {
                        "type": "Document", "response": {"status": status, "headers": {"Retry-After": "0"}}}},
                    {"method": "Network.loadingFinished", "params": {"encodedDataLength": 100}},
                ]
                self.events = [{"message": json.dumps({"message": m})} for m in messages]

            def get_log(self, name):
                result, self.events = self.events, []
                return result

            def find_elements(self, *args):
                return [object()]

            def quit(self):
                pass

        parsed = dict(title="A book", creators=["Writer"], publication_year=1900,
                      subjects=["Fantasy"], language="eng", addeddate="2020-01-01T00:00:00Z",
                      scanned_page_count=100, views_all_time=12)
        driver = FakeDriver()
        info = dict(browser_version="fake", driver_version="fake", chrome_binary="fake", chromedriver="fake")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            manifest = base / "ids.json"
            manifest.write_text(json.dumps({"ids": ["fixture-book"]}), encoding="utf-8")
            with mock.patch.object(config, "MAX_RETRIES", 1), \
                    mock.patch.object(config, "DELAY_SECONDS", 0), \
                    mock.patch.object(ia_selenium_scraper, "build_driver", return_value=(driver, info)), \
                    mock.patch.object(ia_selenium_scraper, "extract", return_value=parsed):
                code = ia_selenium_scraper.main([
                    "--ids", str(manifest), "--out-root", str(base / "runs"), "--label", "offline_retry"])
            run_dir = next((base / "runs").iterdir())
            record = json.loads((run_dir / "records.jsonl").read_text(encoding="utf-8"))
            attempts = [json.loads(x) for x in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(code, 0)
            self.assertEqual(driver.calls, 2)
            self.assertEqual(record["status"], "ok")
            self.assertEqual(record["http_status"], 200)
            self.assertEqual(record["browser"]["document_status"], 200)
            self.assertEqual(record["browser"]["browser_requests"], 2)
            self.assertEqual([a["status"] for a in attempts], [503, 200])
            self.assertEqual([a["outcome"] for a in attempts], ["retry", "ok"])


if __name__ == "__main__":
    unittest.main()
