# Lab Network Project: Open Library scraping efficiency

Compare Selenium, BeautifulSoup and the Open Library Search API for collecting the same book data,
measure each method's network behavior, then cluster the books with K-Means.
Progress checklist: [LABNET_PROJECT_CHECKLIST.md](LABNET_PROJECT_CHECKLIST.md)

## Dataset (pending, not locked)
Two candidates are being compared; nothing is fixed until the team decides:
- **Open Library**: `subject:"science fiction"`, English, first publication 1950-2020. Open questions: a sort order
  supported by both the page and the API, and robots.txt disallowing `/search`.
- **Quotes to Scrape** (quotes.toscrape.com): first 10 quotes compared across Selenium, BeautifulSoup and the JSON API.

Whichever is chosen, the settings go in `scrapers/config.py` so all three scrapers share them.

## Layout
`scrapers/` scripts and config, `data/` CSVs and the saved work-ID list, `captures/` pcap files (not committed),
`screenshots/`, `notebooks/` (networking + ML), `report/` final PDF.
