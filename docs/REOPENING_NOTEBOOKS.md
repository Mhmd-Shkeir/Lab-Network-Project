# Reopening the ML notebooks without retraining

Applies to active notebooks 05–09. Keep using the same Python environment.

1. After this code update, restart the notebook kernel once so it imports the updated helpers.
2. Leave `RETRAIN = False` (the default). Run the demo **Setup / Load** cell near the end of the notebook, then run a BOOK/example cell.
3. The first use fits any missing selected models and saves them. Wait for the **Saved** message before closing VS Code.
4. Tomorrow, repeat step 2. A **Loaded … from disk (no training)** message confirms that prediction is using the saved fitted models.

| Notebook | Section to run for predictions |
| --- | --- |
| 05 — popularity | Section 9 Setup, then BOOK/Predict or the section 10 examples |
| 06 — classical genre/juvenile marker | Section 9 Setup, then an example |
| 07 — neural genre/juvenile marker | Section 9 Setup, then an example |
| 08 — children-only audience | Section 9 Load, then BOOK |
| 09 — genre only | Demo Setup, then an example; it shares the genre checkpoints with 06/07 |

The files in `report/ml/models/` contain fitted estimators, neural architectures/weights where applicable, preprocessing, defaults and class/threshold information needed by the demos. The helpers check their data, split, selected configuration, code and package-version signatures before reuse. Changed inputs/settings may require rebuilding a model rather than using an incompatible checkpoint.

**Run All** reuses completed CV/test/learning-curve caches by default. Missing experiment caches are computed; they are distinct from fitted prediction models. Set `RETRAIN = True` only for a deliberate new training run. The standalone demo cells also default to loading when the top settings cell has not been run.

Saved outputs in an `.ipynb` are tables/graphs, not fitted models. An interrupted fit is not resumed from its last epoch. Checkpoints are written atomically after the relevant fit completes; an incomplete write preserves the previous complete checkpoint.

The model folder is local and excluded from Git because it is rebuildable. Keep it on this computer; another computer must either receive these trusted local files with a compatible environment or prepare its own checkpoints once. Only load model files created by this project or another trusted source.

The selected demo models are persisted, not every candidate from the CV parameter search. The notebooks retain the full recorded comparison tables. Notebook 08 predicts intended children's audience using provisional labels; it does not certify age suitability.
