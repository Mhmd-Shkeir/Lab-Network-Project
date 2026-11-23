# notebooks/ - which notebook uses which files

**The notebooks we use in the final report: 08, 09 and 10** (plus 05 as the baseline popularity model that 10 improves on). Notebooks 06 and 07 (genre and juvenile marker) were removed from the repository (Git history); 08 and 09 still read the results they saved in `report/ml/phase2/`. Each notebook finds its helper `.py` files in this same folder, so keep them together.

| Notebook | What it does | Its helper files (in this folder) | Its saved results |
|---|---|---|---|
| `network_analysis.ipynb` | Network comparison of the three scrapers (Issa) | - | `report/network_*.csv`, `screenshots/` |
| `05_popularity_description_comparison.ipynb` | **Baseline** popularity model, without vs with description, classical and neural | `popularity_experiment.py` (+ `manual_book_prediction.py` for the try-it part) | `report/ml/` |
| **`08_children_only_audience.ipynb`** | Is a book intended for children? (provisional labels) | `children_audience.py`, `children_prediction.py` (+ `phase2_experiment.py`) | `report/ml/children/`, `data/labels/` |
| **`09_genre_only.ipynb`** | Genre only: summary of the saved 06/07 results, plus try-it examples | `phase2_experiment.py`, `phase2_demo.py` | reads `report/ml/phase2/` |
| **`10_popularity_improvements.ipynb`** | Can we improve popularity prediction? (author history, CatBoost, ordered classes) | `popularity_improvements.py`, `popularity_checkpoint.py` (+ `popularity_experiment.py`) | `report/ml/popularity_improvements/` |

Extra comparison scripts (not notebooks): `children_neural_check.py` (small neural network on the children labels) and `popularity_neural_check.py` (small neural network on the improved popularity features); results in `report/ml/children/neural/` and `report/ml/popularity_improvements/neural/`.

Shared by several notebooks: `model_store.py` (saves/loads the fitted models in `report/ml/models/`, so a model is not trained again every time).

## Running them
- Run them in this folder (`notebooks/`). The data comes from `data/popularity_training_clean.csv`; no scraping is needed.
- Leave `RETRAIN = False` (top of 08, 09, 10): saved results and saved models are reused, so a full run takes seconds. See `docs/REOPENING_NOTEBOOKS.md`.
- `tests/` holds the tests of the saving/loading code: `cd notebooks && python -m unittest discover -s tests`.
- Earlier notebooks (02, 03, 04, 06, 07, `ml_analysis1`) were removed from the repository; they remain in the Git history. 08 and 09 read the results that 06 and 07 saved in `report/ml/phase2/`.

Notebook 05 reads `data/openlibrary_ids_5600.csv`, which was removed from `data/` (restore it from Git history, see `data/README.md`, if you want to rerun 05).
