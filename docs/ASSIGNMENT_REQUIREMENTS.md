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

Internet Archive, the 200-item comparison, 2,000-row training dataset, three genre allocations and three repetitions per method are our project choices. The PDF does not prescribe those values or mandate Open Library or K-Means. Compare all methods on the same benchmark workload; collect the larger training dataset separately through the API.

Current status and owners are maintained only in [the checklist](../LABNET_PROJECT_CHECKLIST.md).
