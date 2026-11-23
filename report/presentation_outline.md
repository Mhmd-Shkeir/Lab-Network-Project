# Ten-minute presentation outline

The finished deck is `report/Lab_Network_Presentation.pptx` (10 slides, speaker notes in each slide). Suggested division: Issa presents networking and security (slides 4 to 6); Mohammad presents collection, the dataset and the machine learning (slides 3, 7 to 9); both give the opening and the recommendation. Total about 9 minutes 20 seconds, which leaves time for questions.

| Slide | Time | Speaker | Content |
|---|---:|---|---|
| 1. Title | 0:30 | Both | Three ways to collect the same 200 Internet Archive books: API, BeautifulSoup and Selenium; what each costs on the network and what the data can predict. |
| 2. One question, four steps | 0:40 | Both | Collect, measure, analyse, predict. Same 200 books, same 3-second pacing, one captured run per method on one Mac. |
| 3. Three scrapers, one polite pace | 0:50 | Mohammad | API (8 requests), BS4 (200 page requests), Selenium (200 pages, 8,933 browser requests). Shared rate limit, identifying User-Agent, retries, stop on 403. |
| 4. The API is about 54x faster | 1:30 | Issa | One run per method: API 31.0 s and 163.2 KB; BS4 1,664.1 s (27.7 min) and 11.37 MB; Selenium 1,712.8 s (28.5 min) and 18.63 MB. All 200 of 200 records. Packet bytes are counted for the archive.org endpoint only; there are no repeated-run medians. |
| 5. What the traffic looks like | 1:00 | Issa | Wireshark I/O graph of the Selenium run (a burst per page); 8,933 browser requests against 8 for the API; round trips of a few milliseconds. |
| 6. Threads and the firewall | 1:00 | Issa | Shared limiter: API 20 books 21.9 s with 1 or 2 threads; BS4 6 slow pages 27.1 s against 17.8 s, with the gap between starts staying at 3.000 s. macOS pf block timed out after 5.1 s and recovered; state clearly that pf is a platform substitute for ufw. |
| 7. From 200 books to 17,727 | 0:50 | Mohammad | 200 benchmark books; 5,600 training books; 15,000 more with the API in 47 minutes; 17,727 clean books after the quality checks. Views measure engagement with an archived copy, not sales. |
| 8. Popularity: better than guessing, not 80% | 1:20 | Mohammad | Three classes (low, medium, high). Majority baseline 35.2%; simple models 57.35% without and 59.35% with description; neural network 56.4% / 56.5%; improved model (consistent author names, author and subject history) 61.5% / 62.8%. The 80% target was not reached. The improved result is a comparison on a holdout that was already examined once. |
| 9. Easier questions reach higher accuracy | 0:40 | Mohammad | Genre 70.8% / 86.3%, archive juvenile marker 71.9% / 82.5%, intended for children 75.3% / 85.6% (without / with description). These are different, easier tasks and not popularity accuracy; the children labels are provisional (AI-made, human check pending). |
| 10. What we recommend | 1:00 | Both | Use the API when it has the fields; BS4 when the data is only in the HTML; Selenium only when a browser is needed; threads never beat the rate limit. ML: popularity about 62%, authors help most, descriptions help genre, a neural network never beat the simple models. Limits: one run per method on one Mac, macOS pf instead of ufw, archived-copy views, provisional children labels. |

## Where the evidence comes from

- Slide 4: `report/network_measurements.csv`, `report/network_summary.csv` and `notebooks/network_analysis.ipynb`.
- Slide 5: `screenshots/selenium_io_graph.png` (more in `screenshots/`).
- Slide 6: `report/rate_limit_experiment.csv` and `screenshots/mac_pf_firewall_demo.png`.
- Slides 7 to 9: `report/ml/` (notebooks 05, 08, 09 and 10; see `notebooks/README.md`) and the final report, sections 6 and 7.
