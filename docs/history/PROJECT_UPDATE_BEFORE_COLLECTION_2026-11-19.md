# Project update before further collection — 19 November 2026

This update follows the user's request to document the work before starting a larger collection. It also records the distinction between Internet Archive and Open Library. Read it after the earlier handoff and source-check notes.

## Website identity and book-only scope

The original selected source was Open Library at `openlibrary.org`. The newly verified source for the popularity target is Internet Archive at `archive.org`.

Open Library is a book catalog run by Internet Archive. Its records can link to digitized books hosted on archive.org. Internet Archive hosts books alongside other media, but book data can be selected through book-oriented collections and metadata filters. This relationship does not require using Open Library's website/API as an additional source.

Proposed scope is one provider, Internet Archive, with a book-only dataset. Archive.org detail pages, its metadata API, and its official Views API are parts of that same provider. Filtering should exclude audio, video, software, and other non-book material. `mediatype:texts` alone is too broad because it can also include newspapers and other documents.

The final book collection and filters are not yet locked. The tested Pride and Prejudice item is associated with Americana/New York Public Library collections. A separate size check of the English Gutenberg text collection returned 28,927 candidate items. That is not a count of cleaned unique books with complete features. We have not established which library is globally largest.

Official relationship reference: https://openlibrary.org/help/faq/about

## Exact completed work

1. Open Library originally yielded 10 matching API and Selenium records, but independent Requests/BeautifulSoup requests repeatedly received verification. Its last independent test returned a verification page, not a book. These tests did not establish an IP ban.
2. Alternatives were researched and small checks were performed. dBooks had one matching record through all three methods and 278 distinct catalog IDs discovered across three searches. Its verified fields supported year/page-count clustering, but did not provide a measured popularity target.
3. The user clarified the intended ML goal as low/medium/high popularity and approximate view-count prediction for published books with hidden popularity at evaluation time. This requires supervised prediction with an actual popularity target.
4. One Internet Archive book item was checked through all three methods. `prideprejudice00aust` returned 313,037 all-time views in independent BeautifulSoup extraction, visible Selenium, and the official Views API.
5. That item's metadata endpoint returned title, creators, year, language, subjects, added/public date, and imagecount. A creator can be an illustrator as well as an author; imagecount describes scanned images/pages rather than guaranteed printed pagination.
6. The metadata/API checks, browser result, source comparison, and popularity-goal explanation were saved in this project. There has been no complete Internet Archive 10-book pilot, large training collection, network benchmark, or trained model.

Exact working sample endpoints:

```text
https://archive.org/details/prideprejudice00aust
https://archive.org/metadata/prideprejudice00aust
https://be-api.us.archive.org/views/v1/short/prideprejudice00aust
```

Views selector:

```text
section.item-stats-summary [itemprop="userInteractionCount"]
```

The official Views API hostname is an Internet Archive endpoint, not a second library. The initially guessed archive.org/services/views/... route returned 404 and should not be reused.

## Proposed collection sequence

These are proposed implementation targets, not additional assignment requirements. Larger collection has not started.

1. Select a book-oriented collection and use 10 shared item IDs to verify every chosen field through API, independent BS4, and Selenium. Check missing fields, counter freshness, and whether the candidate pool actually contains books.
2. Retain the proposed 200-record common sample for the three-method network comparison. Keep the same IDs and retrieval-window information for all methods.
3. Build a larger labeled training sample from the same Internet Archive provider using efficient, delayed, batch-supported collection. A reasonable initial working target is 2,000 usable book records, to be adjusted after observing coverage and collection cost. This is not a claim that 2,000 clean rows already exist or that all archive content should be harvested.
4. Preserve raw source values and record missing/skipped cases, timestamps, errors, and exact extraction provenance. Do not substitute API results into a method's failed HTML extraction.
5. Hand the collected data and documentation to Claude for the next analysis/model stage. Preserve all earlier evidence rather than overwriting it.

Proposed predictor fields are item ID, title, normalized creators, publication year, subjects, language, date added, and scanned-page count where available. All-time views are the target and remain separate from predictor columns. The data also needs source URL, retrieval timestamp, and collection-method provenance. Recent-view fields are optional API-only enrichment unless independently verified as common HTML fields.

The user wants one library for scraping, network work, and training. No second library is needed for this plan. Open Library and dBooks can remain documented prior experiments rather than being combined into the training data.

## Limits that must stay explicit

- Current successful Internet Archive evidence covers one sample item's view count, not a complete multi-book predictor dataset.
- Views describe engagement with a particular archived item/copy. They do not measure worldwide book sales.
- Duplicate copies/editions need explicit handling and grouping across train/test splits.
- Training requires measured popularity labels. Hide labels at prediction/evaluation time, not throughout data collection.
- Classification/regression serve the stated prediction goal. K-Means can provide additional exploratory grouping.
- Estimating hidden views of existing books is different from forecasting future views before publication. Future forecasting needs appropriate historical-time features and a defined future target window.
- Project source selection/config still reflects Open Library. A full migration to Internet Archive has not been performed while the provider identity and collection plan are being clarified.

## Files Claude should read

- `POPULARITY_GOAL_SOURCE_CHECK_2026-11-19.md`
- `data/popularity_source_check_2026-11-19/confirmation.json`
- `data/popularity_source_check_2026-11-19/selenium_check.json`
- `SOURCE_OPTIONS_CHECK_2026-11-19.md`
- `CLAUDE_HANDOFF_2026-11-19.md` for previous code, environment, requirements, and Open Library history.

No larger book collection or model training was started while preparing this update.
