# Data dictionary

Source: Internet Archive (archive.org), Americana collection, English fiction texts (query in `data/manifest/manifest_meta.json`).
CSV files are UTF-8 **with BOM** so Excel shows accents correctly. Lists (creators, subjects) are joined with ` | `.
Tip for Excel: open via *Data → From Text/CSV* and keep `identifier` as **Text** (some identifiers are all digits or start with 0).

## Files

| File | Rows | What it is |
|---|---:|---|
| `data/benchmark_200_api.csv` | 200 | Same 200 manifest books collected with the API method (search metadata + Views API) |
| `data/benchmark_200_bs4.csv` | 200 | Same 200 books, independent Requests + BeautifulSoup on `archive.org/details/<id>` |
| `data/benchmark_200_selenium.csv` | 200 | Same 200 books, Selenium/Chrome on the same pages (fields read with WebDriver locators) |
| `data/training_api.csv` | 5,600 | Training records collected through the API only; usable rows (`status = ok`): the 200 benchmark books + 1,800 science fiction + 1,800 fantasy + 1,800 mystery/thriller (each genre: 600 Americana + 1,200 from other English texts) |
| `data/training_with_descriptions.csv` | 3,152 | The training books that have a **usable description** (25+ words after removing catalogue text such as "244 p. ; 22 cm", not boilerplate, not shared with another work): same columns as `training_api.csv` plus `description` (cleaned text) and `description_words`. Built by `scrapers/build_description_dataset.py` from `data/descriptions_raw_5600.jsonl` (raw descriptions of all 5,600 books). 941 science fiction, 1,124 fantasy, 1,020 mystery/thriller, 67 benchmark. Descriptions are catalogue/publisher summaries; their author is not known |
| `data/training_api_not_usable.csv` | few | Training ids whose row was partial/failed, with the reason |
| `data/benchmark_200_comparison/` | – | Field-by-field and view-count differences between the three methods |
| `data/manifest/` | – | Pool snapshot, `benchmark_200_ids.json`, `training_ids.json`, genre pool snapshot, `genre_availability.json`, `genre_preview.csv`, exclusions (`exclusions.csv`, `genre_exclusions.csv`), views eligibility checks, sampling metadata |
| `data/completeness_report.md/.json` | – | Counts, completeness per field, ranges, consistency checks |
| `data/runs/<run_id>/` | – | Raw run folders: checkpoint, per-attempt logs, run summary (see below) |

Rows are never filled from another method. An empty cell means that method did not obtain the value; the `status` and
`error` columns say why.

## Data columns (benchmark and training CSVs)

| Column | Type | Meaning | Notes |
|---|---|---|---|
| `identifier` | text | Internet Archive item identifier (the join key between methods) | unique per row |
| `title` | text | Item title (whitespace collapsed) | |
| `creators` | text list | All creators listed for the item, ` | `-separated | may include illustrators, editors, printers |
| `first_creator` | text | First creator in `creators` | derived |
| `publication_year` | integer | Year of this archived item's edition | not necessarily the work's first publication |
| `subjects` | text list | Subject tags, duplicates removed | order as given by the source |
| `language` | text | Language code(s) such as `eng` | HTML pages show names (English) that are mapped to codes |
| `addeddate` | text (UTC) | When the item was added to the archive, `YYYY-MM-DDThh:mm:ssZ` | |
| `scanned_page_count` | integer | Number of scanned images/pages (`imagecount`) | not the printed page count |
| `views_all_time` | integer | All-time views of this archived item | API: official Views API; BS4/Selenium: counter shown on the page. **0 is a genuine zero** when the source returned data; blank = not obtained |

## Provenance columns

| Column | Meaning |
|---|---|
| `item_url` | Canonical item page `https://archive.org/details/<identifier>` |
| `method` | `api`, `bs4` or `selenium` |
| `status` | `ok` (all required fields present), `partial` (page/API answered but some fields missing), `failed` (nothing usable) |
| `error` | Missing fields (`missing: ...`), HTTP/connection errors after retries, timeout notes |
| `http_status` | HTML methods: status of the page; API: `search/views` statuses, e.g. `200/200` |
| `attempts` | HTML methods: attempts used for this page (1 = no retry). API: attempts of the whole batch, search call + views call, shared by all ids of that batch (2 = one call each, no retry) |
| `retrieved_from` | HTML methods: final URL; API: the two endpoints and batch number |
| `retrieved_at_utc` | When the response was received (API: when the batch's views call returned) |
| `run_id` | Run folder name in `data/runs/` |
| `manifest_position` | Position in the manifest list |

## Training-only columns

| Column | Meaning |
|---|---|
| `sampling_stratum` | How the book was sampled: `benchmark_random_fiction` (the 200 benchmark books, random Americana fiction), or `science_fiction` / `fantasy` / `mystery_thriller` (1,800 each, drawn in sha256 order, **not** ordered by views or downloads) |
| `in_americana` | `True` for the 200 benchmark books and the first 600 books per genre (Americana collection); `False` for the 1,200 per genre added later from the wider English-text pool. Views are much lower for `False` (median 97 vs 285) |
| `genre_primary` | One genre per book by the rules in `scrapers/genres.py`, precedence science_fiction > fantasy > mystery_thriller; `none` if no rule matched (possible for benchmark books) |
| `genre_science_fiction`, `genre_fantasy`, `genre_mystery_thriller` | `True`/`False`: every genre rule the subject tags match. Books matching several genres have several `True` and one `genre_primary` |
| `juvenile` | `1` if any subject tag contains "juvenile" (library marker for books written for children or young readers, e.g. "Magic -- Juvenile fiction"), else `0`. 975 of the 5,600 books (17.4%). Derived from `subjects` by `genres.is_juvenile`; a catalogue label, so `0` does not prove the book is for adults |
| `work_group` | Normalised main title + first creator's surname. Copies, volumes and editions of one work share a group (at most 3 items per group). **Split train/test by this column** to avoid leakage |
| `in_benchmark` | `True` if the id is also one of the 200 benchmark books (their API record is re-collected here, separately from `benchmark_200_api.csv`) |

Genre and exclusion rules (subject-tag phrases; criticism, teaching guides, bibliographies, reference works and magazine issues are
excluded where identifiable) are in `scrapers/genres.py`; every excluded book and the reason is in `data/manifest/genre_exclusions.csv`.
The rules are heuristics on free-text tags, so a few misclassified books are possible.

## Per-run files (`data/runs/<run_id>/`)

| File | Content |
|---|---|
| `<method>.csv` | Generated by new runs; identical copies in the saved benchmark runs were removed in favor of `data/benchmark_200_<method>.csv`. Raw checkpoints remain. |
| `records.jsonl` | Checkpoint, one JSON line per finished record, incl. raw API view windows (`raw_views_api`: last 30/7 days, **not** CSV columns because they would leak the target) and, for Selenium, the `browser` block |
| `attempts.jsonl` / `attempts.csv` | One line per HTTP/navigation **attempt**: start time, `t_start_s` / `t_end_s` (seconds since the run began, from runs made after the threading update), `worker`, elapsed seconds, status, decoded body bytes, redirects, error, retry/backoff wait, outcome |
| `run.json` | Summary: totals, status counts, retries, timing split (`total_s`, `pacing_sleep_s`, `backoff_sleep_s`, `active_s_estimate`, `browser_startup_s`), `rate_limit` (mode, workers, interval, observed `min_start_gap_s`, `max_requests_in_flight`, `attempts_per_second_overall`; runs made before the threading update lack the observed fields), user agent, versions, settings. With `--workers` > 1 the sleep totals are summed over threads and `active_s_estimate` is `null` |
| `page_metrics.csv` | Selenium only: per page browser sub-requests, encoded bytes, hosts, navigation seconds |

`decoded_bytes` is the decoded HTTP body size seen by Python, **not** wire bandwidth. Selenium's browser numbers come from
Chrome's own performance log (encoded bytes, browser-reported). Wire bandwidth, packets and TCP latency must come from
`tcpdump`/Wireshark. Timings in the committed runs are collection timings that include deliberate waits (default 3 s between
requests); they are **not** the final network comparison.

## Known properties of the data

- `views_all_time` from the Views API is slightly **higher** than the counter printed on the HTML page: 195 of the 200 benchmark books differ
  (API − page: min 1, median 2, max 82; never negative); BS4 and Selenium agree on all 200. The difference is preserved, not corrected. A cause (page
  counter caching or lag) has not been verified.
- One benchmark book (`searchforform0000unse`) has a differing subject tag on the page (`James, Henry <1843-1916>`) versus the API list; all other fields
  are identical across the three methods.
- HTML pages show `addeddate` with microseconds for some items and language as a name; the scrapers truncate to seconds and map names to codes (documented normalisation).
- No genuine zero-view book appears in the data (the minimum is 7 views); if one existed with API data it would be kept.
- Views measure engagement with one archived copy, not worldwide popularity or sales.
- `subject:fiction` also matches some non-fiction books about fiction.
- Training ids were chosen so that the Views API had data for them at manifest-build time (it had data for all examined genre books).
- Genre labels are heuristics on free-text subject tags; some mislabelled or non-fiction books may remain.
