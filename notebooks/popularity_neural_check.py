"""Popularity (low / medium / high): one extra comparison with a small neural network (MLP) on the IMPROVED features of notebook 10.

Same pool, same saved grouped folds, same fold-wise features (author names + author/subject history of OTHER works, step 5),
same two small MLP settings as notebooks 07 and 09, three predeclared seeds averaged. Notebook 10 itself is not changed.
The setting is chosen by 5-fold grouped CV on the training pool only. The historical holdout was already examined in
notebooks 05 and 10, so its number here is a COMPARISON, never used for selection.
Run:  python notebooks/popularity_neural_check.py   (CPU)
"""
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase2_experiment as p2
import popularity_experiment as pe
import popularity_improvements as pi

OUT = pi.OUT / "neural"
STEP = 5
CFGS = p2.MLP_CFGS[:2]


def mlp_cls(fd, variant, cfg, ytr, groups):
    Xtr, Xte = fd.dense(STEP, variant)
    sc = StandardScaler().fit(Xtr)
    Xtr, Xte = sc.transform(Xtr), sc.transform(Xte)
    ps = [p2.train_mlp(Xtr, ytr, groups, 3, None, cfg, s, Xte)[0] for s in p2.MLP_SEEDS]
    return np.mean(ps, axis=0).argmax(1)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df = pi.prepare(pe.load_cohort())
    manifest = pe.build_split(df, force=False)
    m = manifest.set_index("identifier").loc[df.identifier]
    pm = (m.split == "pool").to_numpy()
    pool, hold = df[pm].reset_index(drop=True), df[~pm].reset_index(drop=True)
    folds = m.cv_fold.to_numpy()[pm].astype(int)
    rows, t0 = [], time.time()
    for k in range(pi.N_FOLDS):
        tr, va = pool[folds != k].reset_index(drop=True), pool[folds == k].reset_index(drop=True)
        _, ytr, yva = pi.class_labels(tr["views"].to_numpy(), va["views"].to_numpy())
        fd = pi.FoldData(tr, va)
        for v in p2.VARIANTS:
            for ci, cfg in enumerate(CFGS):
                pred = mlp_cls(fd, v, cfg, ytr, tr.ol_group.to_numpy())
                rows.append({"variant": v, "cfg_id": ci, "cfg": json.dumps(cfg), "fold": k, **pi.cls_row(yva, pred)})
        print("fold", k, "done", round(time.time() - t0), "s", flush=True)
    cv = pd.DataFrame(rows)
    cv.round(5).to_csv(OUT / "mlp_cv_all_folds.csv", index=False)
    summ = cv.groupby(["variant", "cfg_id", "cfg"])[["accuracy", "macro_f1", "recall_medium"]].mean().reset_index()
    best = summ.sort_values("macro_f1", ascending=False).groupby("variant").head(1).sort_values("variant")
    sel = pd.read_csv(pi.OUT / "cv_selection.csv")
    win = sel[(sel.task == "classification") & (sel.role == "overall CV winner")][["variant", "family", "accuracy", "macro_f1", "recall_medium"]]
    base = sel[(sel.task == "classification") & (sel.role == "best logreg")][["variant", "accuracy", "macro_f1", "recall_medium"]]
    cmp_cv = best.merge(win, on="variant", suffixes=("_mlp", "_cv_winner")).merge(base.rename(columns={c: c + "_logreg" for c in base.columns if c != "variant"}), on="variant")
    cmp_cv.round(4).to_csv(OUT / "mlp_vs_improved_classical_cv.csv", index=False)
    # one comparison score on the already-examined historical holdout (not used for selection)
    _, ytr, yho = pi.class_labels(pool["views"].to_numpy(), hold["views"].to_numpy())
    fd = pi.FoldData(pool, hold)
    out = []
    for _, r in best.iterrows():
        pred = mlp_cls(fd, r.variant, json.loads(r.cfg), ytr, pool.ol_group.to_numpy())
        out.append({"variant": r.variant, "model": "MLP (CV-chosen setting)", **pi.cls_row(yho, pred)})
    pd.DataFrame(out).round(4).to_csv(OUT / "mlp_historical_holdout_comparison.csv", index=False)
    print(cmp_cv.round(3).to_string()); print(pd.DataFrame(out).round(3).to_string()); print("total", round(time.time() - t0), "s")


if __name__ == "__main__":
    main()
