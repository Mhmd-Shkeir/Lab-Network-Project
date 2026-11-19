# Book-source checks — 19 November 2026

The user requested one final independent BeautifulSoup attempt on Open Library and an actual check of alternative book sources with HTML, Selenium, JSON API, and enough metadata for the project's K-Means work. These are small source-feasibility checks. The project's existing selected dataset, README, config, and previous results were not changed by this research.

## Final Open Library attempt

Made one independent Python Requests call, then parsed the response with BeautifulSoup. No browser cookies, verification automation, identity changes, or request retries were used.

```text
Requested: https://openlibrary.org/works/OL5960415W
Returned:  https://openlibrary.org/verify_human?next=/works/OL5960415W
HTTP:      200
Title:     Human Verification | Open Library
Book h1:   absent
Elapsed:   5.091 seconds
```

Result: no live book data could be extracted by this independent method. BeautifulSoup parses the HTML it receives; it cannot extract a book from a response that contains only verification. The earlier successful Selenium and API results remain valid. This final test does not establish an IP ban or prove all possible Open Library HTML routes fail.

## Recommended next candidate — dBooks / IT eBooks

Verified one actual book independently through all three methods. API and HTML both returned HTTP 200, and Selenium opened and extracted the corresponding public page without a verification prompt.

| Field | Matched value |
|---|---|
| book_id / ISBN-10 | 1503212300 |
| title after documented normalization | Invent Your Own Computer Games with Python |
| author | Al Sweigart |
| publication_year | 2015 |
| page_count | 367 |

API endpoint

`https://www.dbooks.org/api/book/1503212300`

Requested HTML URL

`https://www.dbooks.org/invent-your-own-computer-games-with-python-1503212300/`

Actual HTML destination, reached by both Requests and Selenium

`https://it-ebooks.dev/books/game-development/invent-your-own-computer-games-with-python-3rd-edition`

The HTML h1 adds `, 3rd Edition` to the API title. The successful comparison removed a trailing ordinal edition suffix and matched rows by ISBN-10. Both raw titles are recorded in the evidence. The API publisher was `CreateSpace`, while the HTML publisher was `Amazon Digital Services`; publisher is therefore excluded from the proposed five-field schema. No conclusion about which publisher is correct was made.

Catalog-size check made three spaced API queries:

- `/api/search/data` returned 100 records.
- `/api/search/java` returned 100 records, giving 194 distinct IDs with the first query.
- `/api/search/python` returned 100 records, giving **278 distinct IDs** across the three queries.

The full ID list from those exploratory searches was not persisted. These counts prove enough discoverable candidates for a 200-book target, but do not prove that 200 complete, matching detail records have already been collected. The API documentation limits each search response to 100 books.

The checked dBooks robots file excludes download/redirect/report paths such as `/d/`, `/g/`, and `/r/`, rather than the public catalog/API paths tested here. IT eBooks' checked robots file excludes `/go`, `/share`, and `/ajax`. No `ai-train=no` content signal was present in either checked file. The dBooks API is publicly documented, and its API documentation links to IT eBooks. These observations are not a blanket assurance about every resource or book license.

Proposed ML work would cluster book editions by publication year and page count, with cleaning and feature scaling. Inspect page-count skew before choosing a log transform. This keeps a book-related topic with numeric features. It changes the original edition-count field to page count; publication year here describes the listed edition rather than the original work's first publication year.

Before switching the full project, run a 10-book pilot to check title normalization, ISBN matching, redirect behavior, missing fields, and source discrepancies across a broader sample. The redirect to a second hostname should be documented in the network report because server and network differences also influence timings.

## LibriVox — technically workable, with an unresolved training-use signal

All three methods could read the tested Count of Monte Cristo recording project:

- Documented API: `https://librivox.org/api/feed/audiobooks/?id=47&format=json`
- Static HTML and Selenium: `https://librivox.org/the-count-of-monte-cristo-by-alexandre-dumas/`
- Recording project ID 47, author Alexandre Dumas, **128 sections**, **178,995 seconds** (`49:43:15`).
- BeautifulSoup counted `table.chapter-download tbody tr` rows. Selenium independently counted the same 128 rows and read the same running time.
- API title omits the leading `The` present in the HTML title. Author display also includes life dates in HTML. Normalize those differences explicitly if this source is used.
- The section count is the number of recorded audio files, including alternate versions. It is not necessarily the count of unique literary chapters. A LibriVox ID identifies a recording project, so multiple recordings of one literary work can be separate records.
- A light API request with `limit=1&offset=200` returned another recording, demonstrating at least 201 catalog records. The API documents pagination and a maximum batch limit of 500.

Important correction to Claude's earlier statement: fitting K-Means is machine learning. It should not be dismissed as outside AI training merely because it is not a language model. LibriVox's checked robots file includes `ai-train=no`, with training/fine-tuning language. The applicability to numeric metadata clustering was not resolved by this technical check. Do not describe the proposed use as automatically exempt.

Running time and section count are sensible exploratory features, but likely correlated. Inspect their relationship and cluster quality instead of assuming two independent dimensions.

## Open Textbook Library — matching fields and clear metadata license, but slow crawl interval

Official site at `https://open.umn.edu/opentextbooks/` listed 1,915 open textbooks in the page checked through web research. The discovery page explicitly states that catalog records are CC0, and the official API supports public read access.

Verified textbook ID 4 through JSON, static HTML/BeautifulSoup, and Selenium:

- API: `https://open.umn.edu/opentextbooks/textbooks/4.json`
- Canonical HTML: `https://open.umn.edu/opentextbooks/textbooks/financial-accounting`
- Title `Accounting in the Finance World`, copyright year **2016**, average rating **4**, review count **7**, publisher `University of Minnesota Libraries Publishing`.
- Authors/contributors are empty for this example, so do not promise a complete author field for every catalog record.
- Selenium read the visible h1, the year `<time>` element, the review-count link, and the book's JSON-LD metadata. BeautifulSoup independently found the same title, year, and review count in static HTML; API and browser aggregate values match.
- The numeric `/textbooks/4` route returned an Atom revision feed to the tested Requests client, not the desired HTML book page. Use the canonical slug URL from the API. ID 1 was not a current record and returned 404.

The checked robots file asks for **Crawl-delay: 120** seconds. At one detail page per book, 200 HTML pages would require roughly 6 hours 40 minutes per method/run just in spacing. A catalog-listing approach might reduce the page count if it exposes all required fields, but that optimization has not been verified. The Selenium check waited before revisiting this host. Do not recommend this as a fast 1-2 second-per-page source.

The records' CC0 statement applies to catalog metadata; individual textbooks carry their own licenses. Potential K-Means features include copyright year, rating, and review count, after checking missing values and reviewer-coverage bias.

## Other suggestions and interpretation

- Hacker News is not a book source. A past-day front-page listing is not proof that live scores/comments returned later by the API are frozen. Do not assume perfect time-invariance for those features.
- Quotes to Scrape is technically suitable for the three methods but only has about 100 quotes in the explored catalog. The 200 target is a team choice, not a PDF minimum, but the user prefers a larger book dataset.
- Books to Scrape has HTML suitable for scraping practice, but no official matching JSON API was verified here.
- Gutenberg/Gutendex were not retested in this final check. Do not present Claude's earlier claims as newly verified results.
- Wikidata's metadata license is CC0 and one book entity/API was accessible, but The Hobbit work entity lacked a page-count statement. No complete three-method numeric book dataset was verified there in this research.

## What this establishes for ML

A few hundred clean metadata rows are a reasonable target for a small two-feature educational K-Means exercise. A large catalog alone does not establish useful clusters, a predictive model, or strong generalization. Fit K-Means to the collected numeric rows, inspect distributions, scale appropriately, compare k values, and explain the observed groups. No model was trained during these source checks.

The most practical next step is a 10-book **dBooks** pilot using the five matched fields above. Preserve the Open Library work as prior evidence. No full dataset migration or 200-book collection has been performed by this research.

## Evidence and primary sources

Saved sample CSVs and JSON observations are in `data/source_checks_2026-11-19/`. The three dBooks sample CSVs contain one matching row each. The browser-check JSON includes results for all three alternative sites. The final independent Open Library attempt is recorded in the source-check observations.

- dBooks API documentation: https://www.dbooks.org/api/
- dBooks robots: https://www.dbooks.org/robots.txt
- IT eBooks robots: https://it-ebooks.dev/robots.txt
- IT eBooks description: https://it-ebooks.dev/about
- LibriVox API documentation: https://librivox.org/api/info
- LibriVox robots and content signals: https://librivox.org/robots.txt
- Open Textbook Library API: https://open.umn.edu/opentextbooks/api-docs/index.html
- Open Textbook Library catalog-record license: https://open.umn.edu/opentextbooks/discovery
- Open Textbook Library crawl rules: https://open.umn.edu/robots.txt
- scikit-learn K-Means documentation: https://scikit-learn.org/stable/modules/clustering.html#k-means
