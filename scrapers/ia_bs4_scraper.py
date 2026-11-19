#!/usr/bin/env python3
"""Independent Requests + BeautifulSoup scraper for archive.org /details/<identifier> pages.

One HTTP GET per book (no browser, no cookies from a browser, no API data). A verification page or
HTTP 403 stops the run; nothing is bypassed. Missing fields stay blank and are listed in the
`error` column; they are never filled from the API or Selenium results.

Example:
    python scrapers/ia_bs4_scraper.py --limit 10 --label validation
    python scrapers/ia_bs4_scraper.py
"""
import argparse
import sys
from pathlib import Path

import config
from ia_common import (Abort, Client, RequestFailed, add_common_args, execute, failed_row, finalize_row,
                       iso, looks_like_gate, new_row, parse_detail_html, start_run)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(parser)
    parser.add_argument("--save-html", help="optional folder for raw pages (bulky; not committed)")
    args = parser.parse_args(argv)
    run, id_rows, todo = start_run("bs4", args)
    client = Client(run)
    html_dir = Path(args.save_html) if args.save_html else None
    if html_dir:
        html_dir.mkdir(parents=True, exist_ok=True)

    def work():
        for n, (position, identifier, _) in enumerate(todo, 1):
            row = new_row(identifier, "bs4", run, position)
            try:
                resp = client.get(config.DETAIL_URL + identifier, context={"id": identifier})
            except RequestFailed as exc:
                row["attempts"] = exc.attempts
                run.save_record(failed_row(row, str(exc), exc.status or ""))
                print(f"  {n}/{len(todo)} {identifier}: FAILED {exc}", flush=True)
                continue
            row["attempts"], row["http_status"] = resp.ia_attempts, resp.status_code
            row["retrieved_from"], row["retrieved_at_utc"] = resp.url, iso()
            if html_dir:
                (html_dir / f"{identifier}.html").write_text(resp.text, encoding="utf-8")
            parsed = parse_detail_html(resp.text)
            if looks_like_gate(resp.url, parsed["page_title"]):
                raise Abort(f"verification page returned for {identifier}; stopping (nothing bypassed)")
            if not parsed["has_h1"]:
                run.save_record(failed_row(row, f"no item title on page (title: {parsed['page_title'][:80]})",
                                           resp.status_code))
                print(f"  {n}/{len(todo)} {identifier}: unexpected page", flush=True)
                continue
            for key in ("title", "creators", "publication_year", "subjects", "language", "addeddate",
                        "scanned_page_count", "views_all_time"):
                row[key] = parsed[key]
            finalize_row(row)
            run.save_record(row)
            print(f"  {n}/{len(todo)} {identifier}: {row['status']} views={row['views_all_time']}", flush=True)

    return execute(run, id_rows, args, work)


if __name__ == "__main__":
    sys.exit(main())
