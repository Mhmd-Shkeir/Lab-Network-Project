# Networks Lab: PDF requirements audit — 19 November 2026

Source: D:/Downloads/proj-labnet1 (1).pdf, both pages reread and visually inspected. The original proj-labnet1.pdf is byte-identical. The PDF is the assignment specification; the earlier milestone checklist contains additional team choices and now has obsolete Open Library fields.

## Does the collection plan fit?

Yes, the written PDF permits this structure: the same 200 book items and fields collected independently with Selenium, BeautifulSoup, and API, followed by additional API-collected items from the same Internet Archive provider for an approximately 2,000-item training dataset. The 200 benchmark items can be included in that larger dataset. This means three methods visiting the same 200 items, not 600 different books.

The PDF specifies neither 200 nor 2,000 records, a minimum dataset size, nor that the entire ML dataset must be collected by every method. These are implementation choices. The larger API collection must be described separately from the common-sample comparison; do not compare the runtime of 200 HTML items against 2,000 API items. Popularity prediction is explicitly listed as a regression example. A 2,000-item sample is a starting target, not a guarantee of prediction quality.

This structure addresses the data-collection part of the assignment. It does not replace any networking, security, analysis, or presentation work below. It is a reading of the supplied PDF, not evidence of separate instructor approval or any additional verbal course requirements.

## Complete requirement checklist

### 1. Criteria and target definition — PDF page 1
- [x] Read the assignment deadline: Wednesday, 25 November 2026.
- [x] Team of two: Mohammad Ali Shkeir and Issa Tawil, as supplied in the project context.
- [x] Select a source: current decision is Internet Archive book collections, archive.org.
- [ ] Finalize/document the book filters, sampling, common fields, item identifiers and collection scope in the current configuration and README. The existing files still describe Open Library.

### 2. Three scraping implementations — PDF page 1
- [x] Demonstrate acquisition through all three methods on ten common Internet Archive records.
- [x] Save separate CSVs from the ten-record API, independent Requests/BS4, and Selenium acquisitions.
- [x] Check matching identifiers, completeness and field differences. After offline parser correction, metadata matches; view-count differences remain documented.
- [ ] Deliver the three final scraper scripts/modules required by the PDF. The current Internet Archive pilot is one runner with three modes, not the final three-script deliverable.
- [ ] Run all three methods on the same final benchmark sample with the same fields, saving the outputs independently.

### 3. Performance comparison — PDF pages 1–2
- [ ] Record method, bandwidth in KB, elapsed time in seconds, number of requests, and average latency in milliseconds.
- [ ] Measure all three methods on the same workload under documented conditions.
- [ ] Keep successful/failed records, missing values, and errors as additional stability evidence.

Only single-pilot elapsed times are currently measured. They do not constitute the complete comparison. Three repetitions and reporting median runtime are useful team choices from the earlier checklist; they are not an explicit PDF requirement.

### 4. Linux network observation — PDF pages 1–2
- [ ] Use ss to observe scraper/browser connections.
- [ ] Use iftop and nload to observe bandwidth.
- [ ] Capture traffic with tcpdump and retain the packet-capture files.
- [ ] Inspect/visualize traces in Wireshark and save screenshots.
- [ ] Explain the observed network differences in a networking notebook.

The checked project capture and screenshot folders contain only placeholders. Installed tools are not evidence that these exercises have been completed. Browser navigations are not the total HTTP request count: scripts, images and other resources must also be considered. Decoded HTML/JSON size is not wire bandwidth. Define what the reported latency measures and use suitable client/browser logs; encrypted packet traces alone do not expose all HTTP requests.

### 5. Firewall, rate limiting and multithreading — PDF pages 1–2
- [x] Add pacing in the pilot: three-second gaps between requests/pages.
- [ ] Complete documented error handling/backoff for timeouts, rate limits and other failures in the final scrapers.
- [ ] Use ufw to demonstrate blocked HTTPS, observe failure, restore the temporary rule and demonstrate recovery. Verify the rule was active; do not count an issued command alone as a successful experiment.
- [ ] Implement/use multithreading and document its effect, while retaining responsible request pacing. A sequential-versus-threaded comparison is the team's proposed way to demonstrate this.
- [ ] Record stability observations for the optimization report.

Proxy configuration (Squid/Tor) is explicitly optional in the detailed instructions, despite appearing in the broad goals. No proxy is needed to complete the mandatory list. This audit performs no firewall changes and sends no website requests.

### 6. Cleaning, EDA and machine learning — PDF pages 1–2
- [ ] Collect the larger labelled dataset if using the proposed 2,000-item target.
- [ ] Clean duplicates, missing values, types and implausible values; describe exclusions and source differences.
- [ ] Perform exploratory data analysis with pandas, matplotlib and seaborn.
- [ ] Apply dataset-appropriate ML and present the results in a Jupyter or Colab notebook.

The PDF lists regression, classification and clustering as dataset-dependent examples; it does not explicitly demand all three, or K-Means specifically. For the user's goal, regression estimates archived-item engagement and classification can predict low/medium/high engagement. K-Means may add exploratory groups. Evaluation, held-out labels, simple baselines and suitable metrics are our implementation plan for credible model results, rather than extra verbatim PDF requirements.

Training needs measured view labels; labels must not be prediction inputs. Use one identified official Views API snapshot for labels, retaining the HTML/API discrepancies in the scraping comparison. Related copies/editions need grouped evaluation to reduce leakage. A current snapshot does not establish ability to forecast success before a new book is published.

### 7. Optimization report — PDF page 1 goals and sections
- [ ] Recommend the best strategy for efficiency and stability using the measurements.
- [ ] Include comparative charts, request/bandwidth/time/latency evidence, failures and limitations.
- [ ] Explain which settings helped and when API, BS4 or Selenium is appropriate.

The API was quickest in the pilot. The final recommendation must follow the full measurements and stability observations; a winner is not a preassigned assignment requirement.

### 8. Repository and presentation deliverables — PDF page 2
- [ ] Three scraper scripts.
- [ ] Networking analysis notebook with screenshots.
- [ ] ML notebook, Jupyter or Colab.
- [ ] Final PDF report.
- [ ] Ten-minute presentation showing comparative performance charts, visualized network traces and ML results.

At audit time, notebooks/, report/, captures/ and screenshots/ in the project contain only .gitkeep placeholders. There is no completed networking notebook, ML notebook, final report or packet capture in those destinations. Earlier Open Library scripts and Internet Archive pilot evidence exist, but the full submission is not complete.

## Work order from the present state

1. Migrate the source/field configuration and produce the final scraper entry points.
2. Instrument and collect the common 200-item sample, recording all requested metrics and network evidence during each run.
3. Perform the firewall and multithreading experiments separately from baseline runs; retain pacing and error evidence.
4. Collect the larger API training sample from the same provider, clean it, perform EDA and evaluate the chosen ML task(s).
5. Complete the notebooks, optimization PDF and ten-minute presentation.

The full course/lab syllabus has not been supplied in this audit, so compliance with every topic taught outside the PDF cannot be confirmed. The checklist above covers every explicit item in the supplied two-page assignment. No Notion content was changed.
