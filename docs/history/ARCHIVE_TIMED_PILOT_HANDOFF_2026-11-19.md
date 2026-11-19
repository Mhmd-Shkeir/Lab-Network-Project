# Internet Archive book pilot and timing — 19 November 2026

## Current decision

The user accepted Internet Archive's book collections as the single provider for scraping, the network comparison, and popularity modelling. Use archive.org detail pages and Internet Archive APIs. Open Library is related, but openlibrary.org is not the actual collection target for this plan. Name Internet Archive in the spreadsheet/report. Do not send further Open Library test requests.

Only a ten-record feasibility/timing pilot was performed in this step. No 200-record benchmark or 2,000-record training collection has started. The existing Open Library README/config/scripts describe earlier work and still need a deliberate migration; do not treat their old field definitions as the new specification.

## Actual results

| Method | Records | Measured elapsed time | Observed acquisition |
|---|---:|---:|---|
| API | 10 | 5.50 seconds | 2 HTTP requests: batched search metadata and batched official view counts |
| Independent Requests + BeautifulSoup | 10 | 75.40 seconds | 10 detail-page requests, no redirects |
| Visible Chrome through Selenium | 10 | 67.91 seconds | 10 detail-page navigations, browser subresources not counted |

All methods collected the same ten identifiers. No human-verification page, manual intervention, or collection error occurred. All three runs were in WSL. API and BS4 identify the educational client; the visible Selenium browser uses the same identifying User-Agent. No browser identity spoofing, cookie transfer, IP changes, or verification clicking was used.

Elapsed time includes parsing, writing raw HTML, and three-second pauses between requests/pages. The API has one three-second pause between its two requests. Selenium includes 1.80 seconds of browser startup and browser shutdown. The discovery request that selected the shared identifiers is outside these method timings.

This is one run, not the final repeated network benchmark. Browser bytes/subrequests, wire bandwidth, TCP latency, firewall behaviour, multithreading, and screenshots have not been measured here. Requests' decoded response-body sizes are not wire bandwidth. Do not claim that Selenium is generally faster than BS4 from this pilot.

## Data quality and exact differences

Common fields: identifier, title, creators, publication_year, subjects, language, addeddate, scanned_page_count, views_all_time.

The initial HTML extractor missed creators on seven pages because the markup alternates between author and creator attributes. The corrected extractor reads the creator metadata block. Duplicate HTML subject tags were removed consistently. All saved HTML was reparsed locally, without more website requests. Initial extraction files are preserved separately; measured acquisition timings were not rerun after this parser correction.

After correction, all eight metadata columns match across all three methods, with no blank cells. BS4 and Selenium also match each other's view counts on all ten records. The official Views API differs from the page count on all ten records, by 1–48 views. Example: 02713411.5992.emory.edu is 865 via API and 854 on both HTML/browser pages. Preserve this discrepancy in the data-quality analysis. Different refresh/cache timing is a possibility, not a verified explanation. Use one clearly identified official Views API snapshot for training labels; do not replace the HTML methods' observed values to manufacture agreement.

The count is engagement with one archived item/copy, not worldwide book popularity or sales. Publication year is this catalog item's edition date, not necessarily first publication. The page-count field is a count of scanned images/pages, not guaranteed printed pagination. Creators can include illustrators, editors, and printers.

## Size and timing estimates

The pilot search returned 25,772 candidate records, using:

```text
collection:americana AND mediatype:texts AND language:eng AND subject:fiction
AND creator:* AND year:[1500 TO 2026] AND imagecount:[50 TO *]
```

This is a candidate count, not a count of clean, distinct fictional works. The pilot includes repeated titles/volumes and books about fiction. Sorting identifiers alphabetically was only a reproducible pilot choice; it is not a representative training sample. Final collection filters and sampling still need to be specified. No full ebook/PDF files were downloaded.

Suggested working scope: 200 common records for all three methods, followed by approximately 2,000 usable labelled records from the same provider via the efficient API. These are project choices, not PDF requirements. A larger sample does not itself guarantee a useful model.

Approximate collection times, extrapolated from this pilot with the same pauses:

| Method | 200 records, one run | 2,000 records, one run |
|---|---:|---:|
| API using the tested 10-record batches | about 3 minutes | about 28–30 minutes |
| BS4 | about 25 minutes | about 4 hours 10 minutes |
| Selenium | about 23 minutes | about 3 hours 45 minutes |

API estimates allow three seconds between successive batches as well as between metadata/views calls. Larger API batches may be faster but have not been timed. The estimates exclude sample discovery, cleaning, retries and network-analysis setup, and are not guarantees. Stop/back off on failures or rate limits. Repeated benchmark runs multiply collection time. There is no need to scrape the complete catalog or repeat 2,000 pages through both HTML methods simply to obtain training data.

## Files and continuation

Saved pilot folder: data/archive_timed_pilot_2026-11-19/. It contains the manifest, three CSVs, parsed JSONs, per-method metrics, comparison.json, and cached page HTML. The initial extraction files preserve the parser issue. The runner and seed are alongside the data; its default output uses a fresh timestamp and refuses an existing output directory.

Next: migrate project configuration/README and create the final three scraper entry points; select a common 200-item manifest; instrument repeated runs with the required Linux network tools; then collect/clean the larger training sample and hand over to Claude. Keep duplicate titles/editions grouped across training and evaluation to avoid leakage. Collect view labels for training, hide them from prediction inputs, and compare classification/regression to baselines. K-Means is exploratory clustering, not the supervised popularity predictor. A snapshot supports estimating held-out existing-item engagement; forecasting future pre-publication success requires a different temporal design.

References:
- https://archive.org/developers/views_api.html
- https://archive.org/developers/bots.html
- https://openlibrary.org/help/faq/about

No Notion content was created or changed.
