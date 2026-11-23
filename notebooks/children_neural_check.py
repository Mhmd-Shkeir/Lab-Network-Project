"""Children-only audience: one extra comparison with a small neural network (MLP).

Notebook 08 compared classical models only. This script adds an MLP on the SAME labels, the SAME saved folds and the
SAME inputs (juvenile-tag scores + pages/year/title length + metadata text SVD, plus description SVD in variant B).
It does not change notebook 08 or its saved models.

Rules kept: the MLP setting is chosen by 5-fold grouped CV on the training labels only. The fresh test set was already
scored once for the notebook 08 winners, so the MLP test number is a COMPARISON, never used for selection.
Run:  python notebooks/children_neural_check.py   (CPU, a few minutes)
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
import children_audience as ca
import phase2_experiment as p2

OUT = ca.OUT / "neural"
CFGS = p2.MLP_CFGS[:2]          # the same two small settings used in notebooks 07 and 09 (hidden [64])


def dense_inputs(tr, te, variant):
    F = p2.Features(tr[p2.ALLOWED_COLS].reset_index(drop=True), te[p2.ALLOWED_COLS].reset_index(drop=True), need_svd=True)
    cols = ca._tagcols(variant) + ca.NUM2
    sc = StandardScaler().fit(tr[cols])
    parts = lambda part, d: [sc.transform(d[cols]), F.blocks[part]["svdM"]] + ([F.blocks[part]["svdD"]] if variant == "B" else [])
    return np.hstack(parts("tr", tr)), np.hstack(parts("te", te))


def mlp_proba(tr, te, variant, cfg):
    Xtr, Xte = dense_inputs(tr, te, variant)
    y = tr.child.to_numpy().astype(int)
    w = p2.class_weights("juvenile", y)
    ps = [p2.train_mlp(Xtr, y, tr.ol_group.to_numpy(), 2, w, cfg, s, Xte)[0][:, 1] for s in p2.MLP_SEEDS]
    return np.mean(ps, axis=0)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    L = ca.load_labels()
    dj = p2.task_frame(p2.load_cohort(), "juvenile")
    train_ids, test_ids = ca.build_splits(L, dj, force=False)
    d = ca.with_tags(ca.labelled_frame(L, dj), ca.tag_scores(dj))
    train = d.merge(train_ids[["identifier", "cv_fold"]], on="identifier")
    test = d[d.identifier.isin(test_ids.identifier)].reset_index(drop=True)
    rows, t0 = [], time.time()
    for v in p2.VARIANTS:
        for ci, cfg in enumerate(CFGS):
            for k in range(ca.N_FOLDS):
                tr, va = train[train.cv_fold != k], train[train.cv_fold == k]
                pr = mlp_proba(tr, va, v, cfg)
                rows.append({"variant": v, "cfg_id": ci, "cfg": json.dumps(cfg), "fold": k, **ca.prf(va.child.to_numpy(), (pr > 0.5).astype(int))})
            print(v, ci, "done", round(time.time() - t0), "s", flush=True)
    cv = pd.DataFrame(rows)
    cv.round(5).to_csv(OUT / "mlp_cv_all_folds.csv", index=False)
    summ = cv.groupby(["variant", "cfg_id", "cfg"])[["precision", "recall", "f1", "accuracy"]].mean().reset_index()
    best = summ.sort_values("f1", ascending=False).groupby("variant").head(1)
    classical = pd.read_csv(ca.OUT / "cv_selection.csv")
    classical = classical[classical.is_winner][["variant", "family", "cv_f1", "cv_precision", "cv_recall", "cv_accuracy"]]
    cmp_cv = best.merge(classical, on="variant", suffixes=("_mlp", "_classical_winner"))
    cmp_cv.round(4).to_csv(OUT / "mlp_vs_classical_cv.csv", index=False)
    # one comparison score on the fresh test (not used for selection)
    out = []
    for _, r in best.iterrows():
        pr = mlp_proba(train, test, r.variant, json.loads(r.cfg))
        out.append({"variant": r.variant, "model": "MLP (CV-chosen setting)", **ca.prf(test.child.to_numpy(), (pr > 0.5).astype(int))})
    pd.DataFrame(out).round(4).to_csv(OUT / "mlp_fresh_test_comparison.csv", index=False)
    print(cmp_cv.round(3).to_string()); print(pd.DataFrame(out).round(3).to_string()); print("total", round(time.time() - t0), "s")


if __name__ == "__main__":
    main()
