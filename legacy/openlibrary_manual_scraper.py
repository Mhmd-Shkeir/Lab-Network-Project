"""Open one book in visible WSL Chrome and wait for manual verification.

Run with the existing WSL labnet_venv Python. This script monitors the
browser locally while waiting. It never clicks a verification button or
repeatedly requests the website. Close the browser to cancel.
"""

import csv
import json
import re
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.service import Service


TARGET_URL = "https://openlibrary.org/works/OL52267W"
BROWSER_DIRECTORY = Path.home() / "chrome_for_testing"
OUTPUT_DIRECTORY = Path(__file__).resolve().parent


def extract_visible_record(driver):
    """Read fields actually displayed on the loaded book page."""
    headings = driver.find_elements("css selector", '.work-line a[href*="/works/"]')
    if not headings:
        headings = driver.find_elements("css selector", "h1.work-title, h1")
    title = next((item.text.strip() for item in headings if item.text.strip()), "")
    authors = driver.find_elements(
        "css selector",
        '.work-by a[href*="/authors/"], '
        '.edition-byline a[href*="/authors/"], '
        '[itemprop="author"] a[href*="/authors/"], '
        'a[itemprop="author"]',
    )
    author_names = list(dict.fromkeys(item.text.strip() for item in authors if item.text.strip()))
    body = driver.find_element("tag name", "body").text
    year_elements = driver.find_elements("css selector", ".first-published-date")
    year_text = " ".join(
        (element.get_attribute("title") or "") + " " + element.text
        for element in year_elements
    )
    year_match = re.search(r"\b(\d{4})\b", year_text)
    if not year_match:
        year_match = re.search(r"first published(?:\s+in)?\s+(\d{4})", body, re.IGNORECASE)
    editions_match = re.search(r"\b([\d,]+)\s+editions\b", body, re.IGNORECASE)
    work_match = re.search(r"/works/(OL\d+W)", driver.current_url)
    return {
        "work_id": work_match.group(1) if work_match else "",
        "title": title,
        "author": "; ".join(author_names),
        "first_publish_year": int(year_match.group(1)) if year_match else None,
        "edition_count": int(editions_match.group(1).replace(",", "")) if editions_match else None,
    }


def main():
    options = webdriver.ChromeOptions()
    options.binary_location = str(BROWSER_DIRECTORY / "chrome-linux64" / "chrome")
    options.page_load_strategy = "eager"
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1150,850")
    service = Service(str(BROWSER_DIRECTORY / "chromedriver-linux64" / "chromedriver"))
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(30)
    started = time.monotonic()
    verification_seen = False
    last_state = None
    print("Opening the exact book URL in visible Chrome.", flush=True)
    try:
        try:
            driver.get(TARGET_URL)
        except WebDriverException as error:
            print("Initial navigation:", str(error).splitlines()[0], flush=True)

        while driver.window_handles:
            url = driver.current_url
            title = driver.title
            body = driver.find_element("tag name", "body").text
            gated = "verify_human" in url or "Human Verification" in title
            verification_seen = verification_seen or gated
            network_error = any(
                marker in body
                for marker in ("ERR_CONNECTION_", "ERR_NAME_NOT_RESOLVED", "ERR_TIMED_OUT")
            )
            state = "loading"
            if network_error:
                state = "connection_error"
            elif gated:
                state = "waiting_for_manual_verification"
            elif "/works/OL52267W" in url and driver.find_elements("css selector", "h1.work-title"):
                state = "book_loaded"

            if state != last_state:
                print(json.dumps({"state": state, "url": url, "title": title}), flush=True)
                if state == "waiting_for_manual_verification":
                    print("Complete the verification yourself in Chrome. The script will keep waiting.", flush=True)
                if state == "connection_error":
                    print("After your connection is ready, press Reload in this Chrome window. The script is monitoring locally.", flush=True)
                last_state = state

            if state == "book_loaded":
                record = extract_visible_record(driver)
                missing = [key for key, value in record.items() if value is None or value == ""]
                result = {
                    "record": record,
                    "missing_fields": missing,
                    "verification_page_seen": verification_seen,
                    "elapsed_seconds_including_manual_wait": round(time.monotonic() - started, 2),
                    "note": "Single-page feasibility test. This is not a benchmark run.",
                }
                (OUTPUT_DIRECTORY / "openlibrary_manual_result.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                with (OUTPUT_DIRECTORY / "openlibrary_manual_record.csv").open(
                    "w", newline="", encoding="utf-8-sig"
                ) as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(record))
                    writer.writeheader()
                    writer.writerow(record)
                (OUTPUT_DIRECTORY / "openlibrary_manual_page.html").write_text(
                    driver.page_source, encoding="utf-8"
                )
                driver.save_screenshot(str(OUTPUT_DIRECTORY / "openlibrary_manual_page.png"))
                print(json.dumps(result, ensure_ascii=False), flush=True)
                print("Saved the record and page evidence beside this script.", flush=True)
                return
            time.sleep(2)
    except WebDriverException as error:
        print("Browser session ended:", str(error).splitlines()[0], flush=True)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
