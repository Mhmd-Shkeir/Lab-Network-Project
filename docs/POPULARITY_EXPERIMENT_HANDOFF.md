# Popularity experiment: with descriptions versus without

Use the latest main. Collection is complete: no new scraping is needed. Keep the raw exports, the 200-book networking benchmark and earlier notebooks unchanged.

## Fixed comparison dataset

Use **`data/popularity_training_clean.csv`** for BOTH variants: 17,727 archived items, 16,666 Open Library works, 37 preserved columns. The offline builder is `python scrapers/prepare_popularity_dataset.py`. Its source is `training_ol_books.csv`; `popularity_training_exclusions.csv` records all 2,544 rejected IDs/reasons and `popularity_training_quality.json` records the checks and hashes.

Required model inputs are complete and valid: identity, title, creators, year, subjects, English language, archive/retrieval dates, page count, all-time views, Open Library work/group and usable description. Missing creators are excluded. Empty optional edition IDs and the blank `error` field of successful rows are allowed. Zero views is valid. The automated description rule is not manual verification of every blurb.

## Questions and feature variants

Estimate **existing archived-item engagement**, not sales or success of an unpublished book.

1. Classify low / medium / high all-time views. Fit the tercile cut-offs on training data only, including separately inside each validation fold.
2. Regress the number of all-time views, training on `log1p(views_all_time)` and converting predictions back to non-negative view estimates.

**A: no description.** Book metadata such as title, creators, publication year, scanned pages, subjects and genre; archive age can be calculated from the two timestamps because this is an existing-item engagement task.

**B: with description.** Exactly the same available metadata and cohort as A, adding only description text. Do not use `description_words` only in B as an extra uncontrolled metadata difference. Fit text vectorisers and any scaling, imputation or dimensionality reduction within training folds.

Never put views, recent-view counts, a view-derived feature or precomputed popularity class into X. IDs, `source_batch`, `sampling_stratum`, `in_benchmark`, run/method/status fields and raw retrieval timestamps are provenance, not predictive inputs. Use timestamps only to calculate the documented archive-age feature. Collection flags should be inspected in EDA, not silently used as shortcuts.

## Split and selection

- Save one fixed split manifest with seed 2026 **before fitting models**, and reuse it for A and B and every algorithm. Group by **`ol_group`**, not the older heuristic `work_group`.
- Older test results have already been inspected. For a fresh final holdout, select approximately 15–20% of the cohort from newly collected work groups whose Open Library IDs are absent from **all** `data/openlibrary_ids_5600.csv` work IDs. Stratify by genre where practical. All copies of a work stay on one side. Keep every holdout target out of fitting, threshold selection and model choices.
- Use grouped cross-validation on the remaining training pool. Use the same folds, algorithms and tuning budget for both feature variants.
- Include dummy classifiers/regressors, linear models (LogisticRegression / Ridge) and a suitable nonlinear alternative. If using dense tree methods on text, fit any text reduction within the fold. Keep the search bounded and reproducible.
- Choose each final model from CV metrics before inspecting final holdout results. Report paired comparisons for the same algorithm and the CV-selected winner for each variant. Do not sort test scores to choose the winner.

## Evaluation and outputs

- Classification: accuracy, macro-F1, class counts, confusion matrix and train-fitted baseline. Show results by genre.
- Regression: R² on log views, MAE/median absolute error in original views, and a clearly defined within-2x rate; compare with train-fitted mean/median baselines.
- Compare the description effect on the **same held-out items**, with CV variability or group-level bootstrap uncertainty where practical. A small difference is not proof that one variant is reliably better.
- Add grouped learning curves using training data only. Do not repeatedly score the holdout while deciding how much data or which model to use.
- Write `notebooks/05_popularity_description_comparison.ipynb` with executed outputs, plus comparison tables, split manifest, actual package versions, seeds and reproduction commands. Store result tables under `report/ml/`.
- Finish with an honest answer: which variant works better for which metric, how it compares with the baseline, and its limits. Genre accuracy from earlier experiments is not popularity accuracy. Do not promise 85% or claim that more data guarantees improvement.

The existing raw exports remain the audit trail. Do not re-scrape successful records or rewrite old results to match new ones.
