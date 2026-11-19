#!/usr/bin/env python3
"""Selenium scraper: opens each archive.org /details/<identifier> page in Chrome/Chromium.

Fields are read with Selenium's own element locators (not BeautifulSoup, not the API).
Browser and driver are found without hard-coded paths, in this order:
  1. --chrome-binary / --chromedriver arguments
  2. CHROME_BINARY / CHROMEDRIVER environment variables
  3. google-chrome, google-chrome-stable, chromium, chromium-browser / chromedriver on PATH
  4. Selenium Manager (downloads a matching Chrome for Testing + driver; x86-64 Linux/Windows/macOS only)
See docs/SETUP_UBUNTU_VM.md. A fresh temporary browser profile is created for every run (cold cache).

The Chrome performance log is used to count the browser's own sub-requests and encoded bytes per page
(browser-reported numbers, NOT wire bytes: use tcpdump/Wireshark for those).

Example:
    python scrapers/ia_selenium_scraper.py --limit 10 --label validation
    python scrapers/ia_selenium_scraper.py                # visible browser (needs a desktop session)
    python scrapers/ia_selenium_scraper.py --headless     # no window
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from collections import Counter
from urllib.parse import urlparse

import config
from ia_common import (Abort, add_common_args, clean, execute, failed_row, finalize_row, iso, language_codes,
                       added_to_iso, looks_like_gate, new_row, start_run, to_int, unique, write_flat_csv,
                       year_from, _retry_after_seconds)

CHROME_NAMES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]
VIEWS_SELECTOR = 'section.item-stats-summary [itemprop="userInteractionCount"]'


# ----------------------------------------------------------------------------- browser setup
def find_executable(explicit, env_name, names):
    if explicit:
        return explicit
    if os.environ.get(env_name):
        return os.environ[env_name]
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def build_driver(args, profile_dir):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    options = webdriver.ChromeOptions()
    binary = find_executable(args.chrome_binary, "CHROME_BINARY", CHROME_NAMES)
    if binary:
        options.binary_location = binary
    options.page_load_strategy = args.page_load_strategy
    options.add_argument(f"--user-agent={config.USER_AGENT}")
    options.add_argument(f"--user-data-dir={profile_dir}")
    for flag in ("--window-size=1150,850", "--disable-dev-shm-usage", "--no-first-run",
                 "--no-default-browser-check"):
        options.add_argument(flag)
    if args.headless:
        options.add_argument("--headless=new")
    if os.environ.get("CHROME_NO_SANDBOX") == "1":      # needed when running as root / in some VMs
        options.add_argument("--no-sandbox")
    for flag in args.chrome_arg or []:
        options.add_argument(flag)
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    options.add_experimental_option("perfLoggingPrefs", {"enableNetwork": True, "enablePage": False})
    driver_path = find_executable(args.chromedriver, "CHROMEDRIVER", ["chromedriver"])
    service = Service(driver_path) if driver_path else Service()   # empty -> Selenium Manager
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(args.page_timeout)
    return driver, {"chrome_binary": binary, "chromedriver": driver_path,
                    "browser_version": driver.capabilities.get("browserVersion"),
                    "driver_version": (driver.capabilities.get("chrome") or {}).get("chromedriverVersion", "")[:40]}


# ----------------------------------------------------------------------------- performance log
def drain(driver):
    try:
        return driver.get_log("performance")
    except Exception:
        return []


def summarize_perf(entries):
    requests, encoded, failed, hosts = 0, 0, 0, Counter()
    doc_status, doc_headers = None, {}
    for entry in entries:
        try:
            msg = json.loads(entry["message"])["message"]
        except (KeyError, ValueError):
            continue
        method, params = msg.get("method"), msg.get("params", {})
        if method == "Network.requestWillBeSent":
            url = params.get("request", {}).get("url", "")
            if url.startswith(("http://", "https://")):
                requests += 1
                hosts[urlparse(url).netloc] += 1
        elif method == "Network.responseReceived" and params.get("type") == "Document" and doc_status is None:
            doc_status = params.get("response", {}).get("status")
            doc_headers = {k.lower(): v for k, v in (params.get("response", {}).get("headers") or {}).items()}
        elif method == "Network.loadingFinished":
            encoded += int(params.get("encodedDataLength") or 0)
        elif method == "Network.loadingFailed":
            failed += 1
    return {"browser_requests": requests, "browser_encoded_bytes": encoded, "browser_failed_requests": failed,
            "browser_hosts": dict(hosts), "document_status": doc_status, "document_headers": doc_headers}


# ----------------------------------------------------------------------------- extraction
def extract(driver):
    """Read the fields with WebDriver locators. Same selectors as the BS4 scraper, different tool."""
    from selenium.common.exceptions import StaleElementReferenceException
    from selenium.webdriver.common.by import By

    def text(el):
        return clean(el.get_attribute("textContent") or "")

    for _ in range(3):
        try:
            h1 = driver.find_elements(By.CSS_SELECTOR, "h1.item-title")
            meta = {}
            for dl in driver.find_elements(By.CSS_SELECTOR, "dl.metadata-definition"):
                for dt in dl.find_elements(By.XPATH, "./dt"):
                    dds = dt.find_elements(By.XPATH, "following-sibling::dd[1]")
                    if dds:
                        meta[text(dt).lower()] = dds[0]
            creators = driver.find_elements(By.CSS_SELECTOR, 'dl[aria-label="Item creator metadata"] a')
            views = driver.find_elements(By.CSS_SELECTOR, VIEWS_SELECTOR)

            def value(key):
                return text(meta[key]) if key in meta else ""

            return {
                "has_h1": bool(h1),
                "title": text(h1[0]) if h1 else "",
                "creators": unique([text(a) for a in creators]),
                "publication_year": year_from(value("publication date")),
                "subjects": unique([text(a) for a in meta["topics"].find_elements(By.CSS_SELECTOR, "a")])
                if "topics" in meta else [],
                "language": language_codes(value("language")),
                "addeddate": added_to_iso(value("addeddate")),
                "scanned_page_count": to_int(value("pages")),
                "views_all_time": to_int(text(views[0])) if views else None,
            }
        except StaleElementReferenceException:
            time.sleep(0.5)
    raise RuntimeError("page kept changing while reading it (stale elements)")


# ----------------------------------------------------------------------------- main
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(parser)
    parser.add_argument("--chrome-binary", help="path to Chrome/Chromium (else CHROME_BINARY or PATH)")
    parser.add_argument("--chromedriver", help="path to chromedriver (else CHROMEDRIVER or PATH)")
    parser.add_argument("--headless", action="store_true", help="run without a window (default: visible)")
    parser.add_argument("--page-load-strategy", choices=["normal", "eager", "none"], default="normal",
                        help="normal waits for the load event (default); eager stops at DOMContentLoaded")
    parser.add_argument("--page-timeout", type=int, default=60, help="page load timeout, seconds")
    parser.add_argument("--element-timeout", type=int, default=20, help="seconds to wait for the item title")
    parser.add_argument("--chrome-arg", action="append", help="extra Chrome flag, repeatable")
    args = parser.parse_args(argv)

    from selenium.common.exceptions import TimeoutException, WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    run, id_rows, todo = start_run("selenium", args, extra={
        "page_load_strategy": args.page_load_strategy, "headless": args.headless})
    profile_dir = tempfile.mkdtemp(prefix="labnet_chrome_")
    state = {"driver": None, "pending": None, "restarts": 0}
    page_metrics = []

    def start_browser():
        t = time.perf_counter()
        state["driver"], info = build_driver(args, profile_dir)
        run.browser_startup_s = (run.browser_startup_s or 0) + (time.perf_counter() - t)
        run.extra.update(info)
        print(f"  browser {info['browser_version']} ready in {time.perf_counter() - t:.1f}s", flush=True)

    def commit(extra_events):
        """Attach late sub-requests to the previous page's record, then checkpoint it."""
        pending = state["pending"]
        if pending is None:
            return
        row, events, nav_seconds = pending
        events = events + extra_events
        perf = summarize_perf(events)
        row["browser"] = {k: v for k, v in perf.items() if k != "document_headers"}
        row["browser"]["navigation_seconds"] = nav_seconds
        page_metrics.append({"identifier": row["identifier"], "navigation_seconds": nav_seconds,
                             "requests": perf["browser_requests"], "encoded_bytes": perf["browser_encoded_bytes"],
                             "failed_requests": perf["browser_failed_requests"],
                             "document_status": perf["document_status"],
                             "hosts": json.dumps(perf["browser_hosts"])})
        state["pending"] = None
        run.save_record(row)
        print(f"  {row['identifier']}: {row['status']} views={row['views_all_time']} "
              f"browser_requests={perf['browser_requests']} encoded_bytes={perf['browser_encoded_bytes']}",
              flush=True)

    def collect(position, identifier):
        row = new_row(identifier, "selenium", run, position)
        url = config.DETAIL_URL + identifier
        events, error = [], ""
        for attempt in range(1, config.MAX_RETRIES + 2):
            run.pacer.wait()
            if attempt == 1:                      # sub-requests of the previous page finished during the gap
                commit(drain(state["driver"]))
            else:
                events += drain(state["driver"])
            started, t0 = iso(), time.perf_counter()
            error, timed_out, usable = "", False, False
            try:
                state["driver"].get(url)
            except TimeoutException:
                timed_out = True
            except WebDriverException as exc:
                error = f"{type(exc).__name__}: {str(exc).splitlines()[0][:200]}"
            driver = state["driver"]
            if not error:
                try:
                    WebDriverWait(driver, args.element_timeout).until(
                        lambda d: d.find_elements(By.CSS_SELECTOR, "h1.item-title"))
                    usable = True
                    try:    # views counter is rendered with the page; give it a short extra moment
                        WebDriverWait(driver, 5).until(lambda d: d.find_elements(By.CSS_SELECTOR, VIEWS_SELECTOR))
                    except TimeoutException:
                        pass
                except TimeoutException:
                    usable = False
            elapsed = time.perf_counter() - t0
            run.pacer.done()
            events += drain(driver)
            perf = summarize_perf(events)
            status = perf["document_status"]
            entry = {"context": identifier, "attempt": attempt, "started_at_utc": started,
                     "elapsed_s": round(elapsed, 4), "url": url, "status": status, "decoded_bytes": None,
                     "final_url": driver.current_url if not error else None, "error": error or None,
                     "navigation_timeout": timed_out,
                     "browser_requests_so_far": perf["browser_requests"]}
            if status == 403:
                entry["outcome"] = "abort_403"
                run.log_attempt(entry)
                raise Abort(f"HTTP 403 for {identifier}; stopping, no workaround attempted")
            title = driver.title if not error else ""
            if not error and looks_like_gate(driver.current_url, title):
                entry["outcome"] = "abort_verification"
                run.log_attempt(entry)
                raise Abort(f"verification page for {identifier}; stopping (nothing bypassed or clicked)")
            retryable = bool(error) or status in config.RETRY_STATUSES or (
                not usable and status in (None, 200))      # other 4xx (e.g. 404) are final, not retried
            if usable and (status is None or status == 200):
                entry["outcome"] = "ok_timeout_dom_usable" if timed_out else "ok"
                run.log_attempt(entry)
                parsed = extract(driver)
                row["attempts"], row["http_status"] = attempt, status or ""
                row["retrieved_from"], row["retrieved_at_utc"] = driver.current_url, iso()
                for key in ("title", "creators", "publication_year", "subjects", "language", "addeddate",
                            "scanned_page_count", "views_all_time"):
                    row[key] = parsed[key]
                notes = ["page load timeout; DOM was usable"] if timed_out else []
                finalize_row(row, notes)
                state["pending"] = (row, events, round(elapsed, 3))
                return
            wait = None
            if retryable and attempt <= config.MAX_RETRIES:
                ra = _retry_after_seconds(perf["document_headers"].get("retry-after"))
                if status in (429, 503):
                    run.pacer.slow_down()
                if ra is not None and ra > config.MAX_RETRY_AFTER:
                    entry["outcome"] = "abort_retry_after_too_long"
                    run.log_attempt(entry)
                    raise Abort(f"Retry-After {ra:.0f}s exceeds the {config.MAX_RETRY_AFTER:.0f}s cap")
                wait = ra if ra is not None else min(config.BACKOFF_CAP, config.BACKOFF_BASE * 2 ** (attempt - 1)) + 0.5
                entry["outcome"], entry["backoff_wait_s"] = "retry", round(wait, 3)
                if error and ("invalid session" in error.lower() or "not reachable" in error.lower()
                              or "disconnected" in error.lower()):
                    entry["note"] = "browser session lost; restarting browser"
                    run.log_attempt(entry)
                    state["restarts"] += 1
                    if state["restarts"] > 3:
                        raise Abort("browser kept crashing (4 restarts)")
                    try:
                        state["driver"].quit()
                    except Exception:
                        pass
                    start_browser()
                    continue
                run.log_attempt(entry)
                run.pacer.backoff(wait)
                continue
            entry["outcome"] = "failed"
            run.log_attempt(entry)
            row["attempts"], row["http_status"] = attempt, status or ""
            message = error or f"HTTP {status}" if (error or status) else "item page did not load (no item title)"
            state["pending"] = (failed_row(row, message, status or ""), events, round(elapsed, 3))
            return
        # loop ends only through return/raise above

    def work():
        start_browser()
        try:
            for n, (position, identifier, _) in enumerate(todo, 1):
                collect(position, identifier)
                print(f"  {n}/{len(todo)} navigated {identifier}", flush=True)
            run.pacer.wait()                       # let the last page's sub-requests settle
            commit(drain(state["driver"]))
        finally:
            try:
                commit([])                         # checkpoint a pending record after an abort/interrupt
            except Abort:
                pass

    code = 1
    try:
        code = execute(run, id_rows, args, work)
    finally:
        if state["driver"] is not None:
            try:
                state["driver"].quit()
            except Exception:
                pass
        shutil.rmtree(profile_dir, ignore_errors=True)
        if page_metrics:
            write_flat_csv(run.dir / "page_metrics.csv", page_metrics)
    return code


if __name__ == "__main__":
    sys.exit(main())
