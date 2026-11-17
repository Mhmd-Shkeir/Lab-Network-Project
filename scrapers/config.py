"""Shared settings for all scrapers. The dataset choice is PENDING (nothing here is locked yet).

Candidates:
  A) Open Library: subject:"science fiction", English, first publication 1950-2020 (sort order undecided;
     note: robots.txt disallows /search for all crawlers, to be decided with the team)
  B) Quotes to Scrape (quotes.toscrape.com): first 10 quotes, compare Selenium / BS4 / JSON API output
"""

DATASET = None  # set to "openlibrary" or "quotes" once the team decides

PILOT_SIZE = 10
TARGET_SIZE = 200

# Polite client settings (identifies the project, no personal details)
USER_AGENT = "LabNetworkProject/1.0 (university networking lab)"
DELAY_SECONDS = 1.5   # pause between requests
TIMEOUT_SECONDS = 20
