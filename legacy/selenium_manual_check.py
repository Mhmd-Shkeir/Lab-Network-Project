"""Visible Selenium check of Open Library's subject page and one book page.

If a human-verification page appears the script does NOT touch it: it waits while a person completes it in the
browser window, then records that manual interaction was required (matters for benchmark reproducibility).
Usage (WSLg shows the window):  python scrapers/selenium_manual_check.py [output_dir]
"""
import json
import pathlib
import re
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

URLS = {
    "subject": "https://openlibrary.org/subjects/science_fiction",
    "book": "https://openlibrary.org/works/OL52267W",   # The Time Machine
}
USER_AGENT = "LabNetworkProject/1.0 (university networking lab)"
WAIT_FOR_HUMAN_S = 300

home = pathlib.Path.home() / "chrome_for_testing"
out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
options = webdriver.ChromeOptions()
options.binary_location = str(home / "chrome-linux64" / "chrome")
for a in ("--no-sandbox", "--disable-dev-shm-usage", f"--user-agent={USER_AGENT}"):  # NOT headless
    options.add_argument(a)
driver = webdriver.Chrome(service=Service(str(home / "chromedriver-linux64" / "chromedriver")), options=options)
driver.set_page_load_timeout(90)


def gated():
    return "verify_human" in driver.current_url or "Human Verification" in driver.title


results = {}
try:
    for name, url in URLS.items():
        rec = {"requested": url}
        driver.get(url)
        time.sleep(2)
        rec["gate_shown"] = gated()
        rec["manual_interaction_required"] = False
        if rec["gate_shown"]:
            print(f"[{name}] human verification shown. Please complete it in the browser window...", flush=True)
            t0 = time.time()
            while gated() and time.time() - t0 < WAIT_FOR_HUMAN_S:
                time.sleep(2)
            rec["manual_interaction_required"] = True
            rec["seconds_waiting_for_human"] = round(time.time() - t0, 1)
            time.sleep(3)
        rec["final_url"] = driver.current_url
        rec["title"] = driver.title
        rec["still_gated"] = gated()
        (out / f"selenium_{name}.html").write_text(driver.page_source, encoding="utf-8")
        body = driver.find_element(By.TAG_NAME, "body").text
        if name == "book" and not rec["still_gated"]:
            h1 = driver.find_elements(By.TAG_NAME, "h1")
            au = driver.find_elements(By.CSS_SELECTOR, 'a[href^="/authors/"]')
            rec["fields"] = {
                "title": h1[0].text if h1 else None,
                "author": au[0].text if au else None,
                "first_publish_year": (re.search(r"First published in (\d{4})", body) or [None, None])[1],
                "edition_count": (re.search(r"([\d,]+) editions?", body) or [None, None])[1],
            }
        results[name] = rec
        print(json.dumps(rec, indent=1), flush=True)
        time.sleep(3)
    print("Leaving the window open 20 s so you can look at it...", flush=True)
    time.sleep(20)
finally:
    driver.quit()
(out / "selenium_manual_check.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
