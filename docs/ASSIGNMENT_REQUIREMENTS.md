# Assignment requirements

Source: the supplied two-page assignment, *Analyzing Website Data Collection Efficiency and Network Behavior Using Multiple Web Scraping Techniques*. Deadline: **Wednesday 25 November 2026**. Team size: **two**.

## Required work

1. Choose a website and define the fields to collect.
2. Implement Selenium, BeautifulSoup and API scraping, collecting the same data fields and saving CSV files.
3. Compare speed, bandwidth, number of requests and latency. The requested table contains method, bandwidth in KB, time in seconds, request count and average latency in milliseconds.
4. Observe networking with ss, iftop, nload, tcpdump and Wireshark.
5. Demonstrate ufw port blocking/allowing, responsible rate limiting and multithreading. Proxy configuration is explicitly optional in the technical instructions.
6. Clean the data, perform EDA using pandas/matplotlib/seaborn and apply dataset-appropriate ML. Regression, classification and clustering are examples; popularity is explicitly a regression example.
7. Recommend an efficient and stable scraping strategy using the evidence.

## Submission

- Repository containing three scraper scripts.
- Networking analysis notebook with screenshots.
- ML notebook in Jupyter or Colab.
- Final PDF report.
- Ten-minute presentation showing performance comparisons, visualized network traces and ML results.

## Team implementation choices

Internet Archive, the 200-item comparison, the larger training dataset (5,600 books, then 15,000 more; 17,727 after cleaning) and the three genres are our project choices; we captured one run per method (three repeats were planned but not done). The PDF does not prescribe those values or mandate Open Library or K-Means. Compare all methods on the same benchmark workload; collect the larger training dataset separately through the API.

## Where each requirement is in the repository

| Requirement | Where |
|---|---|
| Three scrapers and CSV files | `scrapers/ia_api_scraper.py`, `ia_bs4_scraper.py`, `ia_selenium_scraper.py`; `data/benchmark_200_*.csv` |
| Speed, bandwidth, requests, latency table | `report/network_measurements.csv`, `report/network_summary.csv`, `notebooks/network_analysis.ipynb` |
| ss / iftop / nload / tcpdump / Wireshark | `screenshots/` (macOS `lsof` stands in for `ss`), `run_mac_*.sh`, `docs/MAC_NETWORK_CAPTURE.md` |
| Firewall, rate limiting, multithreading | `run_mac_pf_demo.sh` (macOS `pf` stands in for `ufw`), `report/rate_limit_experiment.csv`, `--workers` option of the scrapers |
| Cleaning, EDA, ML | `data/popularity_training_clean.csv`; notebooks 05, 08, 09, 10 (see `notebooks/README.md`) |
| Recommendation | Section 8 of the final report |
| Final report | `report/Lab_Network_Final_Report.pdf` (Word version: `Lab_Network_Final_Report.docx`) |
| Presentation (10 min) | `report/Lab_Network_Presentation.pptx` |

