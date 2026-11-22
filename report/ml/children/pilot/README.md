# Children-only pilot (exploratory, preserved unchanged)

What happened, in order:
1. After notebooks 06/07, 160 random books of the juvenile **test side** were read blind (title, author, year, pages, blurb) and labelled children / teen / adult by Claude (2 unsure, 158 usable). Result: the catalogue-marker models matched "children's audience" poorly (see `exploratory158_sample_and_predictions.csv`).
2. A pilot children-only model was built after looking at that result: 400 random **pool** books were labelled the same way (`pilot400_sample.csv`, `pilot400_labels_part*.txt`; 123 children + 78 teen + 191 adult = **392 usable**, 8 unsure). The 392 vs "394" difference reported in an earlier message was an arithmetic slip; the code used 392 rows.
3. The pilot model (`pilot_children_model.py`, scratch paths inside are historical) stacked the existing juvenile-tag score with pages, year and title length; results are in `children_only_pilot_scores.csv`.

**Status: exploratory.** The 158-book results were already examined while the pilot was designed, so they are not a fair test. The proper experiment is `notebooks/08_children_only_audience.ipynb`, which uses these labels only as training data, expands the labels, and evaluates once on a fresh test set. All labels are provisional (AI-assigned; rules in `docs/CHILDREN_LABEL_RULES.md`). The merged label table is `data/labels/children_audience_labels.csv`.
