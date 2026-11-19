"""Ten-work Open Library feasibility check. Run in the existing WSL venv.

Human verification is completed by the user in visible Chrome. Requests/BS4
uses its own HTTP session. Browser cookies are never exported to that session.
These observations are not a packet-capture benchmark.
"""

import argparse
import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.service import Service


FIELDS = ["work_id", "title", "author", "first_publish_year", "edition_count"]
BASE = "https://openlibrary.org"
USER_AGENT = "LabNetUniversityFeasibilityCheck/1.0 (small educational pilot)"


def save_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def number(text):
    match = re.search(r"\d[\d,]*", text)
    return int(match.group().replace(",", "")) if match else None


def parse_html(html, work_id):
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.select_one('.work-line a[href*="/works/"]') or soup.select_one("h1.work-title")
    if heading is None:
        return None
    authors = soup.select('.work-by a[href*="/authors/"], .edition-byline a[href*="/authors/"], [itemprop="author"] a[href*="/authors/"], a[itemprop="author"]')
    names = list(dict.fromkeys(item.get_text(" ", strip=True) for item in authors if item.get_text(strip=True)))
    date = soup.select_one(".first-published-date")
    year_text = (date.get("title", "") + " " + date.get_text(" ", strip=True)) if date else ""
    year = re.search(r"\b\d{4}\b", year_text)
    editions = re.search(r"\b([\d,]+)\s+editions\b", soup.get_text(" ", strip=True), re.IGNORECASE)
    return dict(zip(FIELDS, [work_id, heading.get_text(" ", strip=True), "; ".join(names), int(year.group()) if year else None, number(editions.group(1)) if editions else None]))


def parse_browser(driver, work_id):
    headings = driver.find_elements("css selector", '.work-line a[href*="/works/"]')
    if not headings:
        headings = driver.find_elements("css selector", "h1.work-title")
    title = next((item.text.strip() for item in headings if item.text.strip()), "")
    authors = driver.find_elements("css selector", '.work-by a[href*="/authors/"], .edition-byline a[href*="/authors/"], [itemprop="author"] a[href*="/authors/"], a[itemprop="author"]')
    names = list(dict.fromkeys(item.text.strip() for item in authors if item.text.strip()))
    dates = driver.find_elements("css selector", ".first-published-date")
    date_text = " ".join((item.get_attribute("title") or "") + " " + item.text for item in dates)
    year = re.search(r"\b\d{4}\b", date_text)
    editions = re.search(r"\b([\d,]+)\s+editions\b", driver.find_element("tag name", "body").text, re.IGNORECASE)
    return dict(zip(FIELDS, [work_id, title, "; ".join(names), int(year.group()) if year else None, number(editions.group(1)) if editions else None]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--resume", type=Path, help="Retry Selenium with an existing saved sample.")
    args = parser.parse_args()
    stamp = datetime.now(ZoneInfo("Asia/Beirut")).strftime("%Y-%m-%d_%H%M%S")
    output = args.resume or (args.project / "data" / ("feasibility_" + stamp))
    output.mkdir(parents=True, exist_ok=bool(args.resume))
    print("RESULT_DIRECTORY " + str(output), flush=True)
    observations = {"date_beirut": stamp, "scope": "10-work feasibility pilot, not a formal network benchmark", "api": [], "bs4": [], "selenium": [], "notes": []}
    if args.resume:
        observations = json.loads((output / "observations.json").read_text(encoding="utf-8"))
        observations["notes"].append("Retried Selenium after fixing a transient missing-body page-loading error. Existing API and BS4 evidence retained.")
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    def checkpoint():
        (output / "observations.json").write_text(json.dumps(observations, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(url, params=None):
        started = time.monotonic()
        try:
            response = session.get(url, params=params, timeout=(10, 25))
            initial_request = response.history[0].request if response.history else response.request
            event = {"requested_url": initial_request.url, "final_url": response.url, "status": response.status_code, "elapsed_seconds": round(time.monotonic() - started, 3), "response_body_bytes": len(response.content), "http_responses_including_redirects": len(response.history) + 1}
            return response, event
        except requests.RequestException as error:
            return None, {"requested_url": url, "error": str(error), "elapsed_seconds": round(time.monotonic() - started, 3)}
        finally:
            time.sleep(2)

    # The saved ID list fixes the sample. All first-publication years must
    # satisfy the proposed range; an API publication filter alone is insufficient.
    records = []
    if args.resume:
        with (output / "api.csv").open(encoding="utf-8-sig", newline="") as stream:
            records = list(csv.DictReader(stream))
        for row in records:
            for field in ("first_publish_year", "edition_count"):
                row[field] = int(row[field]) if row[field] else None
    for offset in (() if args.resume else (0, 50, 100)):
        response, event = get(BASE + "/subjects/science_fiction.json", {"limit": 50, "offset": offset, "published_in": "1950-2020"})
        observations["api"].append(event)
        checkpoint()
        if response is None or response.status_code != 200:
            break
        try:
            works = response.json().get("works", [])
        except ValueError:
            event["error"] = "The API returned a non-JSON response."
            break
        for work in works:
            year = work.get("first_publish_year")
            work_id = work.get("key", "").split("/")[-1]
            if isinstance(year, int) and 1950 <= year <= 2020 and work_id not in {item["work_id"] for item in records}:
                records.append({"work_id": work_id, "title": work.get("title", ""), "author": "; ".join(author.get("name", "") for author in work.get("authors", [])), "first_publish_year": year, "edition_count": work.get("edition_count")})
            if len(records) == 10:
                break
        if len(records) == 10 or not works:
            break
    save_csv(output / "api.csv", records)
    (output / "work_ids.json").write_text(json.dumps([item["work_id"] for item in records], indent=2), encoding="utf-8")
    observations["notes"].append("Science-fiction subject; retained first publication years 1950-2020. English-edition filtering is not established by this Subjects API pilot. Sample uses the API default order and is not representative.")
    print("API_RECORDS " + str(len(records)), flush=True)
    checkpoint()

    direct_rows = []
    if args.resume:
        with (output / "bs4.csv").open(encoding="utf-8-sig", newline="") as stream:
            direct_rows = list(csv.DictReader(stream))
        for row in direct_rows:
            for field in ("first_publish_year", "edition_count"):
                row[field] = int(row[field]) if row[field] else None
    consecutive_gates = 0
    for item in ([] if args.resume else records):
        response, event = get(BASE + "/works/" + item["work_id"])
        event["work_id"] = item["work_id"]
        if response is not None:
            soup = BeautifulSoup(response.text, "html.parser")
            event["page_title"] = soup.title.get_text(" ", strip=True) if soup.title else ""
            event["verification_page"] = "verify_human" in response.url or "Human Verification" in event["page_title"]
            if event["verification_page"]:
                consecutive_gates += 1
            elif response.status_code == 200:
                row = parse_html(response.text, item["work_id"])
                if row:
                    direct_rows.append(row)
                consecutive_gates = 0
        observations["bs4"].append(event)
        checkpoint()
        print("BS4 " + json.dumps(event), flush=True)
        if consecutive_gates == 2 or response is None or response.status_code in (403, 429):
            observations["notes"].append("Stopped independent BS4 after two consecutive verification pages or a connection/access failure. Remaining target works were not attempted by BS4.")
            break
    save_csv(output / "bs4.csv", direct_rows)

    selenium_rows = []
    parsed_snapshot_rows = []
    if records:
        chrome = Path.home() / "chrome_for_testing"
        options = webdriver.ChromeOptions()
        options.binary_location = str(chrome / "chrome-linux64" / "chrome")
        options.page_load_strategy = "eager"
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1150,850")
        driver = None
        try:
            driver = webdriver.Chrome(service=Service(str(chrome / "chromedriver-linux64" / "chromedriver")), options=options)
            driver.set_page_load_timeout(30)
            for index, item in enumerate(records):
                started = time.monotonic()
                url = BASE + "/works/" + item["work_id"]
                event = {"work_id": item["work_id"], "requested_url": url, "verification_page_seen": False, "manual_wait_seconds": 0, "connection_error_seen": False}
                try:
                    driver.get(url)
                except WebDriverException as error:
                    event["navigation_error"] = str(error).splitlines()[0]
                last_state = None
                blocked_since = None
                connection_error_since = None
                while driver.window_handles:
                    current = driver.current_url
                    title = driver.title
                    body = driver.execute_script("return document.body ? document.body.innerText : ''")
                    gated = "verify_human" in current or "Human Verification" in title
                    connection_error = any(term in body for term in ("ERR_CONNECTION_", "ERR_NAME_NOT_RESOLVED", "ERR_TIMED_OUT"))
                    event["verification_page_seen"] = event["verification_page_seen"] or gated
                    event["connection_error_seen"] = event["connection_error_seen"] or connection_error
                    if connection_error and connection_error_since is None:
                        connection_error_since = time.monotonic()
                    if not connection_error:
                        connection_error_since = None
                    state = "loading"
                    if connection_error:
                        state = "connection_error"
                    elif gated:
                        state = "manual_verification"
                    elif "/works/" + item["work_id"] in current and driver.find_elements("css selector", "h1.work-title"):
                        state = "ready"
                    if state != last_state:
                        print("SELENIUM " + json.dumps({"book": index + 1, "total": len(records), "state": state, "url": current}), flush=True)
                        if state == "manual_verification":
                            print("Please complete human verification yourself. Waiting for the book page.", flush=True)
                        if state == "connection_error":
                            print("Connection error. You may press Reload in this Chrome window when ready.", flush=True)
                        last_state = state
                    if state in ("manual_verification", "connection_error") and blocked_since is None:
                        blocked_since = time.monotonic()
                    if connection_error_since is not None and time.monotonic() - connection_error_since >= 90:
                        event["error"] = "Connection error persisted for 90 seconds; stopped this attempt."
                        break
                    if state == "loading" and time.monotonic() - started >= 90:
                        event["error"] = "No usable page or verification screen loaded within 90 seconds."
                        break
                    if state == "ready":
                        if blocked_since is not None:
                            event["manual_wait_seconds"] = round(time.monotonic() - blocked_since, 3)
                        row = parse_browser(driver, item["work_id"])
                        selenium_rows.append(row)
                        # Supplemental parser check on the browser's captured DOM.
                        # It does not count as independent live Requests/BS4 success.
                        parsed_row = parse_html(driver.page_source, item["work_id"])
                        if parsed_row:
                            parsed_snapshot_rows.append(parsed_row)
                        event["missing_fields"] = [key for key, value in row.items() if value is None or value == ""]
                        if index == 0:
                            driver.save_screenshot(str(output / "selenium_first_book.png"))
                        break
                    time.sleep(2)
                event["elapsed_seconds_including_manual_wait"] = round(time.monotonic() - started, 3)
                event["final_url"] = driver.current_url
                event["page_title"] = driver.title
                observations["selenium"].append(event)
                save_csv(output / "selenium.csv", selenium_rows)
                save_csv(output / "bs4_browser_snapshot_supplement.csv", parsed_snapshot_rows)
                checkpoint()
                if event.get("error"):
                    break
                time.sleep(2)
        except KeyboardInterrupt:
            observations["notes"].append("The waiting Selenium test was stopped manually; partial observations retained.")
        except WebDriverException as error:
            observations["notes"].append("Selenium interrupted: " + str(error).splitlines()[0])
        finally:
            if driver:
                driver.quit()
    save_csv(output / "selenium.csv", selenium_rows)
    save_csv(output / "bs4_browser_snapshot_supplement.csv", parsed_snapshot_rows)

    def normalized(value):
        if isinstance(value, str):
            return " ".join(value.casefold().split())
        return value

    differences = []
    for method, rows in (("bs4", direct_rows), ("selenium", selenium_rows)):
        lookup = {row["work_id"]: row for row in rows}
        for expected in records:
            actual = lookup.get(expected["work_id"])
            if actual is None:
                differences.append({"method": method, "work_id": expected["work_id"], "issue": "record not collected"})
                continue
            for field in FIELDS[1:]:
                if normalized(actual[field]) != normalized(expected[field]):
                    differences.append({"method": method, "work_id": expected["work_id"], "field": field, "api": expected[field], "observed": actual[field]})
    summary = {"target_records": len(records), "api_records": len(records), "independent_bs4_records": len(direct_rows), "selenium_records": len(selenium_rows), "supplemental_bs4_browser_snapshot_records": len(parsed_snapshot_rows), "differences": differences}
    observations["summary"] = summary
    checkpoint()
    print("COMPLETE " + json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
