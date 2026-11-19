# Popularity prediction clarification and single-source check

Updated 19 November 2026, following the user's clarification. The user wants one library for all three collection methods, network benchmarking, and a model that predicts low/medium/high popularity and approximate view counts for already-published books whose popularity is hidden during prediction. This is more specific than the earlier year/edition-count or year/page-count clustering proposal. The user also mentioned future publication, which requires a separate forecasting setup if interpreted literally.

## Answers to the immediate questions

- The final Open Library recheck was one independent Requests/BeautifulSoup call. Chrome was not launched for that final call and no verification checkbox was clicked. HTTP 200 contained the Human Verification page and no book heading. It did not display an explicit IP-block diagnosis.
- The dBooks example's 367 is the page count of that one listed book edition. Other books have their own page counts.
- The 278 dBooks IDs found across three capped searches are not its proven entire catalog size. We did not establish its total size or a scale comparable to Open Library.
- The dBooks fields tested do not include a verified popularity label such as views, downloads, or reading-log counts. The earlier dBooks recommendation demonstrated a year/page-count clustering dataset. It does not establish a suitable labeled dataset for this popularity-prediction goal.

## Better-matched candidate — Internet Archive

Internet Archive is one provider, with HTML pages at archive.org and its official Views API on be-api.us.archive.org. Those are endpoints of the same service, rather than two independent book libraries. No project dataset/config migration has yet been made.

One actual archived book item was checked:

```text
Identifier: prideprejudice00aust
Title: Pride and prejudice
HTML: https://archive.org/details/prideprejudice00aust
Metadata: https://archive.org/metadata/prideprejudice00aust
Views API: https://be-api.us.archive.org/views/v1/short/prideprejudice00aust
```

Verified popularity result:

| Method | Observed all-time views |
|---|---:|
| Independent Requests + BeautifulSoup on HTML | 313,037 |
| Visible WSL Selenium on the same page | 313,037 |
| Official Views API JSON | 313,037 |

The HTML and metadata endpoint returned HTTP 200. Selenium loaded with no navigation error or verification intervention. Its public-page headings contained the book title.

The working HTML selector for views is:

```text
section.item-stats-summary [itemprop="userInteractionCount"]
```

Parse the value as an integer after removing thousands separators. The tested HTML also displayed 699 favorites and 2 reviews. These values were not established as independent predictor inputs for a pre-publication task.

The metadata response exposed title, creators, publication date/year, subjects, language, added/public date, and `imagecount`. The example has publication year 1894, language `eng`, added date `2007-07-26 11:49:10`, and imagecount 518. Label that last field as scanned-image/page count if used, rather than assuming it equals printed pagination. The creators array includes Austen and an illustrator, so creator/author normalization needs explicit handling.

The Views API additionally returned last-30-day views 9,948, last-7-day views 2,139, and `have_data=true` for this item. Those recent counts were not verified as common static-HTML fields. Do not silently replace the all-time target with recent views in the three-method comparison.

An initial guessed endpoint at `archive.org/services/views/v1/short/...` returned 404. Use the documented be-api.us.archive.org endpoint above instead.

## Candidate pool size and filtering

The actual advanced-search query below returned **28,927 English text items** in Internet Archive's Gutenberg collection at check time:

```text
https://archive.org/advancedsearch.php
q=mediatype:texts AND collection:gutenberg AND language:eng
fl[]=identifier
fl[]=title
fl[]=downloads
fl[]=year
rows=1
output=json
```

This establishes a substantially larger candidate pool, not 28,927 cleaned, unique literary works with complete predictor fields. An example result lacked year. Filter book-oriented collections, deduplicate copies/editions as needed, and measure usable record counts before setting the final training size. A wider Americana query returned 4,152,620 text items but includes material such as newspapers; it should not be labelled a clean book count.

The sample Pride and Prejudice item is in Americana/New York Public Library collections, not necessarily the narrower Gutenberg subset. Select and test the final shared manifest from the chosen subset before claiming that all its items behave identically.

Search `downloads` values and item-page/API view counts can have different refresh schedules. Use the official Views API for labels and compare it with HTML in a tight collection window. Record timestamps and tolerate/report real counter updates rather than changing values to force equality.

## Model definition for the clarified goal

Training records need actual popularity measurements. Keep the view count as the target and exclude it from predictor columns. At prediction/evaluation time, give the model only allowed book features and compare its output against hidden known view counts.

- Classification can predict low/medium/high view groups. Define thresholds from training data or a justified fixed rule, then retain the same definition for held-out data.
- Regression can estimate numerical views, potentially fitting a log-transformed count because engagement is often skewed. Classification and regression are supervised tasks. K-Means can be retained as exploratory clustering, but does not by itself learn how metadata predicts a hidden view-count target.
- Candidate predictors include normalized title/topic features, creators, publication year, language, and scanned-page count when available. Time since the item was added is relevant to accumulated views for existing items. Avoid passing the target, target-derived class, or unavailable-at-prediction engagement features into the model.
- Split data before fitting feature transforms or label thresholds. Keep duplicate copies of the same work together across splits when evaluating generalization to unseen books. Compare numeric predictions with a simple training-set baseline and report errors honestly.
- Hiding popularity on an already-published held-out book evaluates estimation of existing popularity. Predicting future views for a genuinely new publication requires past-time predictors and a defined future target window. A single current snapshot of old books does not validate that claim.
- Internet Archive views measure engagement with a particular archived item/copy. They are not worldwide book sales or universal popularity. The website's view definition combines qualifying reads/downloads and limits repeated user activity per item per day.

For one-provider implementation, the three network methods can use the same benchmark manifest. A larger training sample can subsequently be collected through the chosen efficient method from Internet Archive itself. There is no need to introduce a second library merely to grow the training data.

## Access and next verification

Internet Archive publishes automated-access guidance. Use a descriptive tool/version User-Agent; the guide also asks AI agents to identify the model. Respect server rate limits and Retry-After, add delays, cache results, and prefer batch API calls. The checked robots file excluded `/control/` and `/report/`; no blanket exclusion of the tested public detail route appeared.

This check verified one item's view count through the three methods. A 10-item pilot should next verify all chosen predictor fields, the view target, IDs, missing-value rates, and update differences across the intended collection. No complete popularity training dataset or trained model has been produced.

Existing Open Library and dBooks evidence remains valuable and should be preserved. Source selection is still under discussion, with Internet Archive now the best-matched tested candidate for the clarified popularity target.

## Primary references

- Views API and fields: https://archive.org/developers/views_api.html
- Meaning of views: https://archivesupport.zendesk.com/hc/en-us/articles/360018536672-What-is-a-view
- Stats refresh schedules: https://archivesupport.zendesk.com/hc/en-us/articles/360004650632-Internet-Archive-Statistics
- Automated access: https://archive.org/developers/bots.html
- Metadata schema: https://archive.org/developers/metadata-schema/index.html
- dBooks documented fields: https://www.dbooks.org/api/
