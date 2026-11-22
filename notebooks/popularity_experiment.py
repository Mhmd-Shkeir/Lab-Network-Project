"""Helpers for notebooks/05_popularity_description_comparison.ipynb.

Existing archived-item engagement on archive.org, NOT sales or the success of a new book.
Two feature variants on exactly the same books, folds and holdout:
    A = book metadata only      B = the same metadata + description text.
Everything fitted from data (tercile cut-offs, scalers, TF-IDF, SVD, early stopping) uses TRAINING rows only.
Reads data/popularity_training_clean.csv; makes no web requests.
"""
import hashlib
import json
import os
import re
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from joblib import Parallel, delayed
from sklearn.decomposition import TruncatedSVD
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

HERE = Path(__file__).resolve().parent
# joblib worker processes must be able to import this file
os.environ["PYTHONPATH"] = str(HERE) + os.pathsep + os.environ.get("PYTHONPATH", "")
os.environ.setdefault("PYTHONWARNINGS", "ignore")
os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 4))
warnings.filterwarnings("ignore")

ROOT = HERE.parent
DATA_FILE = ROOT / "data" / "popularity_training_clean.csv"
OL_IDS_FILE = ROOT / "data" / "openlibrary_ids_5600.csv"
OUT = ROOT / "report" / "ml"
CACHE = OUT / "cache"

SEED = 2026
MLP_SEEDS = (2026, 2027, 2028)          # predeclared; the MLP result is the average of these three, never the best one
N_FOLDS = 5
HOLDOUT_FRACTION = 0.17                 # of the whole cohort, drawn from new work groups
N_BOOT = 1000
LC_FRACTIONS = (0.1, 0.2, 0.4, 0.6, 0.8, 1.0)
CLASSES = ["low", "medium", "high"]
VARIANTS = ("A", "B")                   # A: metadata only, B: metadata + description text
NUM_COLS = ["publication_year", "log_pages", "age_years", "n_creators", "n_subjects", "title_words",
            "genre_science_fiction", "genre_fantasy", "genre_mystery_thriller", "juvenile"]
DESC_MAX_FEATURES = 20000
META_MAX_FEATURES = 8000
SVD_DIM = 100

# ---------------------------------------------------------------- bounded, identical search budget for A and B
MLP_CFGS = [{"weight_decay": 1e-3, "dropout": 0.1}, {"weight_decay": 1e-2, "dropout": 0.3}, {"weight_decay": 1e-1, "dropout": 0.5}]
HGB_CFGS = [{"max_iter": 150, "learning_rate": 0.05, "max_depth": 3, "min_samples_leaf": 40, "l2_regularization": 1.0},
            {"max_iter": 300, "learning_rate": 0.03, "max_depth": 4, "min_samples_leaf": 40, "l2_regularization": 2.0},
            {"max_iter": 200, "learning_rate": 0.05, "max_depth": 6, "min_samples_leaf": 60, "l2_regularization": 5.0}]
ALGOS = {
    "classification": {"dummy": [{}], "logreg": [{"C": c} for c in (0.1, 0.3, 1.0, 3.0)], "hgb": HGB_CFGS, "mlp": MLP_CFGS},
    "regression": {"dummy_mean": [{}], "dummy_median": [{}], "ridge": [{"alpha": a} for a in (0.3, 1.0, 3.0, 10.0)],
                   "hgb": HGB_CFGS, "mlp": MLP_CFGS},
}
FAMILY = {"dummy": "baseline", "dummy_mean": "baseline", "dummy_median": "baseline", "logreg": "linear", "ridge": "linear",
          "hgb": "tree", "mlp": "neural"}
MLP_MAX_EPOCHS, MLP_PATIENCE, MLP_BATCH, MLP_LR, MLP_VAL_GROUP_FRACTION = 100, 10, 256, 1e-3, 0.15


# ================================================================= data
def load_cohort():
    df = pd.read_csv(DATA_FILE, encoding="utf-8-sig", keep_default_na=False, na_values=[""])
    for c in ("title", "creators", "first_creator", "subjects", "description", "ol_group", "sampling_stratum", "source_batch"):
        df[c] = df[c].fillna("").astype(str)
    retrieved, added = pd.to_datetime(df["retrieved_at_utc"], utc=True), pd.to_datetime(df["addeddate"], utc=True)
    df["age_years"] = ((retrieved - added).dt.days / 365.25).clip(lower=0)      # archive age: the only use of the timestamps
    df["log_pages"] = np.log1p(df["scanned_page_count"])
    df["n_creators"] = df["creators"].str.count(r" \| ") + 1
    df["n_subjects"] = df["subjects"].str.count(r" \| ") + 1
    df["title_words"] = df["title"].str.split().str.len()
    for c in ("genre_science_fiction", "genre_fantasy", "genre_mystery_thriller", "juvenile", "in_americana"):
        df[c] = df[c].astype(str).str.lower().isin(["true", "1"]).astype(int)
    df["meta_text"] = (df["title"] + " " + df["subjects"]).str.replace(r"[|\-]+", " ", regex=True).str.lower()
    df["creator_tokens"] = df["creators"].str.lower().str.split(r" \| ")
    df["views"] = df["views_all_time"].astype(int)
    df["log_views"] = np.log1p(df["views"])
    return df.reset_index(drop=True)


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ================================================================= split (written BEFORE any model is fitted)
def build_split(df, force=False):
    """Fresh holdout from new work groups + grouped stratified CV folds on the rest. Saved to report/ml/split_manifest.csv."""
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / "split_manifest.csv"
    if f.exists() and not force:
        return pd.read_csv(f, keep_default_na=False)
    old_works = set(pd.read_csv(OL_IDS_FILE, encoding="utf-8-sig")["openlibrary_work"].dropna().astype(str))
    grp = df.groupby("ol_group").agg(n=("identifier", "size"), genre=("sampling_stratum", lambda s: s.mode().iloc[0]))
    grp["eligible"] = ~grp.index.isin(old_works)
    grp = grp[grp.eligible & grp.genre.isin(["science_fiction", "fantasy", "mystery_thriller"])]
    rng = np.random.default_rng(SEED)
    hold = set()
    for g in ["science_fiction", "fantasy", "mystery_thriller"]:       # same share of each genre
        target = HOLDOUT_FRACTION * (df.sampling_stratum == g).sum()
        order = grp[grp.genre == g].index.to_numpy()
        order = order[rng.permutation(len(order))]
        got = 0
        for w in order:
            if got >= target:
                break
            hold.add(w); got += grp.loc[w, "n"]
    m = df[["identifier", "ol_group", "sampling_stratum", "source_batch"]].copy()
    m["split"] = np.where(m.ol_group.isin(hold), "holdout", "pool")
    m["cv_fold"] = -1
    pool = m[m.split == "pool"]
    strat = pool.sampling_stratum + "|" + pool.source_batch
    skf = StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
    for k, (_, va) in enumerate(skf.split(pool, strat, pool.ol_group)):
        m.loc[pool.index[va], "cv_fold"] = k
    # integrity checks
    assert not (set(m[m.split == "holdout"].ol_group) & set(m[m.split == "pool"].ol_group)), "group on both sides"
    assert not (set(m[m.split == "holdout"].ol_group) & old_works), "holdout group is an older work"
    assert m[m.split == "pool"].groupby("ol_group").cv_fold.nunique().max() == 1, "group split over folds"
    m.to_csv(f, index=False)
    return m


# ================================================================= features (fitted on training rows only)
def _creators(tokens):
    return tokens


class Features:
    """All feature blocks for a training frame and the frame(s) to predict. TF-IDF/SVD/scaling are fitted on `tr` only."""

    def __init__(self, tr, te, seed=SEED):
        t0 = time.time()
        sc = StandardScaler().fit(tr[NUM_COLS].astype(float))
        num = lambda d: sc.transform(d[NUM_COLS].astype(float))
        tf_m = TfidfVectorizer(max_features=META_MAX_FEATURES, min_df=3, sublinear_tf=True, stop_words="english", token_pattern=r"[a-z]{2,}")
        cv_c = CountVectorizer(analyzer=_creators, binary=True, min_df=2)
        tf_d = TfidfVectorizer(max_features=DESC_MAX_FEATURES, min_df=5, ngram_range=(1, 2), sublinear_tf=True, stop_words="english",
                               token_pattern=r"[a-z]{2,}", lowercase=True)
        M = lambda d, fit=False: sp.hstack([(tf_m.fit_transform if fit else tf_m.transform)(d["meta_text"]),
                                            (cv_c.fit_transform if fit else cv_c.transform)(d["creator_tokens"])]).tocsr()
        Mtr = M(tr, True); Mte = M(te)
        Dtr = tf_d.fit_transform(tr["description"]); Dte = tf_d.transform(te["description"])
        svd_m = TruncatedSVD(SVD_DIM, random_state=seed).fit(Mtr)
        svd_d = TruncatedSVD(SVD_DIM, random_state=seed).fit(Dtr)
        sm = StandardScaler().fit(svd_m.transform(Mtr)); sd = StandardScaler().fit(svd_d.transform(Dtr))
        self.blocks = {
            "tr": {"num": num(tr), "M": Mtr, "D": Dtr, "svdM": sm.transform(svd_m.transform(Mtr)), "svdD": sd.transform(svd_d.transform(Dtr))},
            "te": {"num": num(te), "M": Mte, "D": Dte, "svdM": sm.transform(svd_m.transform(Mte)), "svdD": sd.transform(svd_d.transform(Dte))},
        }
        self.n_meta_features, self.n_desc_features = Mtr.shape[1], Dtr.shape[1]
        self.seconds = time.time() - t0
        self._cache = {}

    def get(self, variant, kind):
        """kind 'sparse' (linear models), 'dense' (trees, MLP) or 'none' (dummy). Variant B only ADDS the description block."""
        key = (variant, kind)
        if key not in self._cache:
            out = []
            for part in ("tr", "te"):
                b = self.blocks[part]
                if kind == "none":
                    out.append(np.zeros((b["num"].shape[0], 1)))
                elif kind == "sparse":
                    parts = [sp.csr_matrix(b["num"]), b["M"]] + ([b["D"]] if variant == "B" else [])
                    out.append(sp.hstack(parts).tocsr())
                else:
                    parts = [b["num"], b["svdM"]] + ([b["svdD"]] if variant == "B" else [])
                    out.append(np.hstack(parts))
            self._cache[key] = tuple(out)
        return self._cache[key]


KIND = {"dummy": "none", "dummy_mean": "none", "dummy_median": "none", "logreg": "sparse", "ridge": "sparse", "hgb": "dense", "mlp": "dense"}


# ================================================================= targets
def tercile_cuts(views):
    return np.quantile(views, [1 / 3, 2 / 3])


def to_class(views, cuts):
    return np.where(views <= cuts[0], 0, np.where(views > cuts[1], 2, 1))


# ================================================================= models
def _train_mlp(Xtr, ytr, groups, task, cfg, seed, Xte):
    """Small MLP (128, 64), ReLU, AdamW. Early stopping on a validation subset made of WHOLE work groups taken from the training rows."""
    import torch
    from torch import nn
    torch.set_num_threads(2)
    rng = np.random.default_rng(seed); torch.manual_seed(seed)
    ug = np.unique(groups)
    val_g = set(rng.permutation(ug)[: max(1, int(len(ug) * MLP_VAL_GROUP_FRACTION))])
    vm = np.array([g in val_g for g in groups]); tm = ~vm
    Xt, Xv = torch.tensor(Xtr[tm], dtype=torch.float32), torch.tensor(Xtr[vm], dtype=torch.float32)
    if task == "classification":
        yt, yv = torch.tensor(ytr[tm], dtype=torch.long), torch.tensor(ytr[vm], dtype=torch.long)
        out_dim, loss_fn = 3, nn.CrossEntropyLoss()
    else:
        mu, sd = ytr[tm].mean(), ytr[tm].std()
        yt, yv = torch.tensor((ytr[tm] - mu) / sd, dtype=torch.float32), torch.tensor((ytr[vm] - mu) / sd, dtype=torch.float32)
        out_dim, loss_fn = 1, nn.MSELoss()
    net = nn.Sequential(nn.Linear(Xtr.shape[1], 128), nn.ReLU(), nn.Dropout(cfg["dropout"]), nn.Linear(128, 64), nn.ReLU(),
                        nn.Dropout(cfg["dropout"]), nn.Linear(64, out_dim))
    opt = torch.optim.AdamW(net.parameters(), lr=MLP_LR, weight_decay=cfg["weight_decay"])
    gen = torch.Generator().manual_seed(seed)

    def fwd(X):
        o = net(X)
        return o if task == "classification" else o.squeeze(1)

    hist = {"train_loss": [], "val_loss": []}
    best, best_state, bad = np.inf, None, 0
    for epoch in range(MLP_MAX_EPOCHS):
        net.train()
        perm = torch.randperm(len(Xt), generator=gen)
        for i in range(0, len(Xt), MLP_BATCH):
            b = perm[i:i + MLP_BATCH]
            opt.zero_grad(); loss_fn(fwd(Xt[b]), yt[b]).backward(); opt.step()
        net.eval()
        with torch.no_grad():
            hist["train_loss"].append(float(loss_fn(fwd(Xt), yt))); v = float(loss_fn(fwd(Xv), yv)); hist["val_loss"].append(v)
        if v < best - 1e-4:
            best, bad = v, 0; best_state = {k: t.clone() for k, t in net.state_dict().items()}
        else:
            bad += 1
            if bad >= MLP_PATIENCE:
                break
    net.load_state_dict(best_state); net.eval()
    hist["best_epoch"] = int(np.argmin(hist["val_loss"])) + 1
    hist["epochs_run"] = len(hist["val_loss"])
    with torch.no_grad():
        o = fwd(torch.tensor(Xte, dtype=torch.float32))
        pred = torch.softmax(o, 1).numpy() if task == "classification" else o.numpy() * sd + mu
    return pred, hist


def fit_predict(tr, te, feats, plan, cuts, mlp_seeds=MLP_SEEDS):
    """plan: dicts(variant, task, algo, cfg_id, cfg). Returns one record per fit, with test predictions and fit time."""
    yv = tr["views"].values
    y = {"classification": to_class(yv, cuts), "regression": np.log1p(yv)}
    groups = tr["ol_group"].values
    recs = []
    for p in plan:
        Xtr, Xte = feats.get(p["variant"], KIND[p["algo"]])
        task, algo, cfg = p["task"], p["algo"], p["cfg"]
        base = dict(variant=p["variant"], task=task, algo=algo, cfg_id=p["cfg_id"], cfg=json.dumps(cfg))
        if algo == "mlp":
            preds, secs = [], 0.0
            for s in mlp_seeds:
                t0 = time.time(); pr, h = _train_mlp(Xtr, y[task], groups, task, cfg, s, Xte); dt = time.time() - t0
                preds.append(pr); secs += dt
                recs.append({**base, "seed": s, "pred": pr, "fit_seconds": dt, "history": h})
            recs.append({**base, "seed": "avg", "pred": np.mean(preds, axis=0), "fit_seconds": secs, "history": None})
            continue
        t0 = time.time()
        if task == "classification":
            m = {"dummy": lambda: DummyClassifier(strategy="prior"),
                 "logreg": lambda: LogisticRegression(C=cfg["C"], max_iter=300),
                 "hgb": lambda: HistGradientBoostingClassifier(early_stopping=False, random_state=SEED, **cfg)}[algo]()
            m.fit(Xtr, y[task]); pr = m.predict_proba(Xte)
            if pr.shape[1] != 3:                                 # a class missing from training (cannot happen with terciles; safe)
                full = np.zeros((len(Xte), 3)); full[:, m.classes_] = pr; pr = full
        else:
            m = {"dummy_mean": lambda: DummyRegressor(strategy="mean"), "dummy_median": lambda: DummyRegressor(strategy="median"),
                 "ridge": lambda: Ridge(alpha=cfg["alpha"]),
                 "hgb": lambda: HistGradientBoostingRegressor(early_stopping=False, random_state=SEED, **cfg)}[algo]()
            m.fit(Xtr, y[task]); pr = m.predict(Xte)
        recs.append({**base, "seed": "single", "pred": pr, "fit_seconds": time.time() - t0, "history": None})
    return recs


def full_plan(only=None):
    plan = []
    for v in VARIANTS:
        for task, algos in ALGOS.items():
            for algo, cfgs in algos.items():
                for i, c in enumerate(cfgs):
                    plan.append(dict(variant=v, task=task, algo=algo, cfg_id=i, cfg=c))
    return plan


# ================================================================= metrics
def cls_metrics(ytrue, proba):
    pred = proba.argmax(1)
    return {"accuracy": float((pred == ytrue).mean()), "macro_f1": float(f1_score(ytrue, pred, average="macro", labels=[0, 1, 2], zero_division=0))}


def reg_metrics(views, logpred):
    """R2 on log1p(views) and errors in original views (prediction = expm1(max(logpred, 0)))."""
    ylog = np.log1p(views)
    pv = np.expm1(np.clip(logpred, 0, None))
    ss = ((ylog - logpred) ** 2).sum(); st = ((ylog - ylog.mean()) ** 2).sum()
    err = np.abs(pv - views)
    return {"r2_log": float(1 - ss / st), "mae_log": float(np.abs(ylog - logpred).mean()), "mae_views": float(err.mean()),
            "median_ae_views": float(np.median(err)),
            "within_2x": float((np.abs(np.log1p(pv) - ylog) <= np.log(2)).mean())}       # (pred+1)/(views+1) between 0.5 and 2


def metrics(task, df_te, cuts, pred):
    return cls_metrics(to_class(df_te["views"].values, cuts), pred) if task == "classification" else reg_metrics(df_te["views"].values, pred)


def confusion(ytrue, proba):
    cm = np.zeros((3, 3), int)
    np.add.at(cm, (ytrue, proba.argmax(1)), 1)
    return cm


# ================================================================= cross-validation on the training pool
def _cv_fold(k, pool, folds, limit=3):
    with threadpool_limits(limit):
        tr_i, va_i = np.where(folds != k)[0], np.where(folds == k)[0]
        tr, va = pool.iloc[tr_i].reset_index(drop=True), pool.iloc[va_i].reset_index(drop=True)
        cuts = tercile_cuts(tr["views"].values)            # thresholds from this fold's training rows only
        feats = Features(tr, va)
        recs = fit_predict(tr, va, feats, full_plan(), cuts)
    rows, oof, hist = [], {}, {}
    for r in recs:
        m = metrics(r["task"], va, cuts, r["pred"])
        rows.append({"fold": k, "variant": r["variant"], "task": r["task"], "algo": r["algo"], "cfg_id": r["cfg_id"], "cfg": r["cfg"], "seed": r["seed"],
                     "fit_seconds": r["fit_seconds"], "feature_seconds": feats.seconds, **m})
        key = (r["variant"], r["task"], r["algo"], r["cfg_id"], str(r["seed"]))
        oof[key] = (va_i, r["pred"])
        if r["history"]:
            hist[key + (k,)] = r["history"]
    info = {"fold": k, "cuts": cuts.tolist(), "train_rows": len(tr), "val_rows": len(va), "n_meta_features": feats.n_meta_features,
            "n_desc_features": feats.n_desc_features, "train_class_counts": np.bincount(to_class(tr["views"].values, cuts), minlength=3).tolist()}
    return rows, oof, hist, info


def run_cv(df, manifest, n_jobs=5, force=False):
    import pickle
    CACHE.mkdir(parents=True, exist_ok=True)
    cf = CACHE / "cv.pkl"
    if cf.exists() and not force:
        return pickle.loads(cf.read_bytes())
    m = manifest.set_index("identifier").loc[df.identifier]
    pool_mask = (m["split"] == "pool").to_numpy()
    pool = df[pool_mask].reset_index(drop=True)
    folds = m["cv_fold"].to_numpy()[pool_mask].astype(int)
    res = Parallel(n_jobs=n_jobs)(delayed(_cv_fold)(k, pool, folds) for k in range(N_FOLDS))
    rows = [r for x in res for r in x[0]]
    oof = {}
    for _, o, _, _ in res:
        for key, (idx, pr) in o.items():
            arr = oof.setdefault(key, np.full((len(pool),) + pr.shape[1:], np.nan))
            arr[idx] = pr
    hist = {k: v for x in res for k, v in x[2].items()}
    out = {"results": pd.DataFrame(rows), "oof": oof, "hist": hist, "fold_info": [x[3] for x in res], "pool_identifiers": pool.identifier.tolist()}
    cf.write_bytes(pickle.dumps(out))
    return out


def summarise_cv(results):
    """Mean/SD over folds per (variant, task, algo, cfg). MLP rows use the seed-average prediction (seed == 'avg')."""
    r = results[results.seed.astype(str).isin(["single", "avg"])]
    keys = ["variant", "task", "algo", "cfg_id", "cfg"]
    g = r.groupby(keys)
    s = g.agg(accuracy=("accuracy", "mean"), accuracy_sd=("accuracy", "std"), macro_f1=("macro_f1", "mean"), macro_f1_sd=("macro_f1", "std"),
              r2_log=("r2_log", "mean"), r2_log_sd=("r2_log", "std"), mae_log=("mae_log", "mean"), mae_views=("mae_views", "mean"),
              median_ae_views=("median_ae_views", "mean"), within_2x=("within_2x", "mean"), fit_seconds=("fit_seconds", "mean"),
              feature_seconds=("feature_seconds", "mean")).reset_index()
    s["family"] = s.algo.map(FAMILY)
    return s


def select_models(cv_summary):
    """Per variant and task: best config of every algorithm, then the winners. Criterion (declared before the holdout is scored):
    cross-validated macro-F1 (classification) / cross-validated R2 on log views (regression). Holdout scores are never consulted."""
    crit = {"classification": "macro_f1", "regression": "r2_log"}
    rows = []
    for (v, t, a), g in cv_summary.groupby(["variant", "task", "algo"]):
        b = g.sort_values(crit[t], ascending=False).iloc[0]
        rows.append({"variant": v, "task": t, "algo": a, "cfg_id": int(b.cfg_id), "cfg": b.cfg, "family": FAMILY[a], "cv_criterion": crit[t],
                     "cv_value": float(b[crit[t]])})
    sel = pd.DataFrame(rows)
    sel["is_variant_winner"] = False
    sel["is_best_non_neural"] = False
    for (v, t), g in sel.groupby(["variant", "task"]):
        real = g[g.family != "baseline"]
        sel.loc[real.cv_value.idxmax(), "is_variant_winner"] = True
        sel.loc[real[real.family != "neural"].cv_value.idxmax(), "is_best_non_neural"] = True
    return sel


# ================================================================= fresh holdout (selected configs only, after selection is saved)
def run_holdout(df, manifest, selection, force=False):
    import pickle
    cf = CACHE / "holdout.pkl"
    if cf.exists() and not force:
        return pickle.loads(cf.read_bytes())
    m = manifest.set_index("identifier").loc[df.identifier]
    pool = df[(m["split"] == "pool").to_numpy()].reset_index(drop=True)
    hold = df[(m["split"] == "holdout").to_numpy()].reset_index(drop=True)
    cuts = tercile_cuts(pool["views"].values)
    plan = [dict(variant=r.variant, task=r.task, algo=r.algo, cfg_id=r.cfg_id, cfg=json.loads(r.cfg)) for r in selection.itertuples()]
    with threadpool_limits(8):
        feats = Features(pool, hold)
        recs = fit_predict(pool, hold, feats, plan, cuts)
    out = {"records": recs, "cuts": cuts.tolist(), "feature_seconds": feats.seconds, "pool_rows": len(pool), "holdout_rows": len(hold),
           "holdout_identifiers": hold.identifier.tolist(), "n_meta_features": feats.n_meta_features, "n_desc_features": feats.n_desc_features}
    cf.write_bytes(pickle.dumps(out))
    return out


# ================================================================= holdout tables and grouped bootstrap
def _fast_cls(ytrue, pred, idx):
    yt, p = ytrue[idx], pred[idx]
    cm = np.bincount(yt * 3 + p, minlength=9).reshape(3, 3)
    tp = np.diag(cm).astype(float)
    prec, rec = tp / np.maximum(cm.sum(0), 1), tp / np.maximum(cm.sum(1), 1)
    f1 = 2 * prec * rec / np.maximum(prec + rec, 1e-12)
    return {"accuracy": float(tp.sum() / len(idx)), "macro_f1": float(f1.mean())}


def boot_indices(groups, n=N_BOOT, seed=SEED):
    """n resamples of ROW indices, resampling whole work groups with replacement (copies of a work stay together)."""
    ug, inv = np.unique(groups, return_inverse=True)
    rows_of = [np.where(inv == i)[0] for i in range(len(ug))]
    rng = np.random.default_rng(seed)
    return [np.concatenate([rows_of[i] for i in rng.integers(0, len(ug), len(ug))]) for _ in range(n)]


def ci_row(deltas):
    d = pd.DataFrame(deltas)
    return {f"{c}_{k}": v for c in d.columns for k, v in zip(("mean", "lo95", "hi95"), (d[c].mean(), d[c].quantile(.025), d[c].quantile(.975)))}


def holdout_tables(hold_res, df, selection):
    """Everything reported on the fresh holdout. Called only after cv_selection.csv has been written."""
    hold = df.set_index("identifier").loc[hold_res["holdout_identifiers"]].reset_index()
    cuts = np.array(hold_res["cuts"])
    ytrue_c, views = to_class(hold["views"].values, cuts), hold["views"].values
    sel = selection.set_index(["variant", "task", "algo"])
    rows, seed_rows, cms, genre_rows, preds = [], [], [], [], {}
    for r in hold_res["records"]:
        key = (r["variant"], r["task"], r["algo"])
        s = sel.loc[key]
        m = cls_metrics(ytrue_c, r["pred"]) if r["task"] == "classification" else reg_metrics(views, r["pred"])
        base = {"variant": r["variant"], "task": r["task"], "algo": r["algo"], "family": FAMILY[r["algo"]], "cfg_id": r["cfg_id"], "cfg": r["cfg"],
                "is_cv_variant_winner": bool(s.is_variant_winner), "is_cv_best_non_neural": bool(s.is_best_non_neural)}
        if str(r["seed"]) in ("single", "avg"):
            rows.append({**base, **m, "fit_seconds": r["fit_seconds"]}); preds[key] = r["pred"]
            if r["task"] == "classification":
                cm = confusion(ytrue_c, r["pred"])
                for i in range(3):
                    cms.append({"variant": r["variant"], "algo": r["algo"], "true_class": CLASSES[i], **{f"pred_{CLASSES[j]}": int(cm[i, j]) for j in range(3)}})
            for g in sorted(hold.sampling_stratum.unique()):
                mk = (hold.sampling_stratum == g).to_numpy()
                gm = cls_metrics(ytrue_c[mk], r["pred"][mk]) if r["task"] == "classification" else reg_metrics(views[mk], r["pred"][mk])
                genre_rows.append({**{k: base[k] for k in ("variant", "task", "algo", "family")}, "genre": g, "rows": int(mk.sum()), **gm})
        else:
            seed_rows.append({**base, "seed": r["seed"], **m, "fit_seconds": r["fit_seconds"], "best_epoch": r["history"]["best_epoch"]})
    res = pd.DataFrame(rows)
    # ---- grouped bootstrap (the same resampled work groups for every comparison)
    idxs = boot_indices(hold["ol_group"].values)
    ycls = {k: v.argmax(1) for k, v in preds.items() if k[1] == "classification"}

    def pred_of(v, t, a):
        return ycls[(v, t, a)] if t == "classification" else preds[(v, t, a)]

    def mfn(task, pred):
        if task == "classification":
            return lambda idx: _fast_cls(ytrue_c, pred, idx)
        return lambda idx: reg_metrics(views[idx], pred[idx])

    def delta(task, pa, pb):                                    # second minus first
        fa, fb = mfn(task, pa), mfn(task, pb)
        out = []
        for idx in idxs:
            a, b = fa(idx), fb(idx)
            out.append({k: b[k] - a[k] for k in a})
        return out

    comps = []
    for t in ("classification", "regression"):
        base_algo = "dummy" if t == "classification" else "dummy_mean"
        for a in ALGOS[t]:                                       # description effect, same algorithm
            comps.append(("description effect (B - A), same algorithm", t, a, pred_of("A", t, a), pred_of("B", t, a)))
        wa = selection[(selection.variant == "A") & (selection.task == t) & selection.is_variant_winner].iloc[0].algo
        wb = selection[(selection.variant == "B") & (selection.task == t) & selection.is_variant_winner].iloc[0].algo
        comps.append(("CV-selected winners (B winner - A winner)", t, f"{wb} (B) vs {wa} (A)", pred_of("A", t, wa), pred_of("B", t, wb)))
        for v in VARIANTS:
            other = selection[(selection.variant == v) & (selection.task == t) & selection.is_best_non_neural].iloc[0].algo
            comps.append((f"neural network minus best non-neural model by CV, variant {v}", t, f"mlp - {other}", pred_of(v, t, other), pred_of(v, t, "mlp")))
            for a in ALGOS[t]:
                if FAMILY[a] != "baseline":
                    comps.append((f"model minus train-fitted baseline ({base_algo}), variant {v}", t, a, pred_of(v, t, base_algo), pred_of(v, t, a)))
    boot = pd.DataFrame([{"comparison": n, "task": t, "detail": d, **ci_row(delta(t, pa, pb))} for n, t, d, pa, pb in comps])
    pred_df = hold[["identifier", "ol_group", "sampling_stratum", "views"]].copy()
    pred_df["true_class"] = [CLASSES[i] for i in ytrue_c]
    for (v, t, a), p in preds.items():
        pred_df[f"{v}_{t[:3]}_{a}"] = [CLASSES[i] for i in p.argmax(1)] if t == "classification" else np.round(np.expm1(np.clip(p, 0, None)), 1)
    return {"table": res, "seed_variability": pd.DataFrame(seed_rows), "confusion": pd.DataFrame(cms), "by_genre": pd.DataFrame(genre_rows),
            "bootstrap": boot, "predictions": pred_df, "holdout_class_counts": np.bincount(ytrue_c, minlength=3).tolist(), "cuts": cuts.tolist()}


def paired_cv(results, selection):
    """Per-fold B - A for the same algorithm (each variant uses the config CV chose for it). Training-pool CV only."""
    r = results[results.seed.astype(str).isin(["single", "avg"])]
    rows = []
    for t, cols in (("classification", ["accuracy", "macro_f1"]), ("regression", ["r2_log", "median_ae_views", "within_2x"])):
        for a in ALGOS[t]:
            ca = int(selection[(selection.variant == "A") & (selection.task == t) & (selection.algo == a)].cfg_id.iloc[0])
            cb = int(selection[(selection.variant == "B") & (selection.task == t) & (selection.algo == a)].cfg_id.iloc[0])
            ra = r[(r.variant == "A") & (r.task == t) & (r.algo == a) & (r.cfg_id == ca)].sort_values("fold")
            rb = r[(r.variant == "B") & (r.task == t) & (r.algo == a) & (r.cfg_id == cb)].sort_values("fold")
            for c in cols:
                d = rb[c].to_numpy() - ra[c].to_numpy()
                better = (d < 0) if c == "median_ae_views" else (d > 0)
                rows.append({"task": t, "algo": a, "metric": c, "A_mean": ra[c].mean(), "B_mean": rb[c].mean(), "mean_B_minus_A": d.mean(),
                             "sd_of_fold_differences": d.std(ddof=1), "folds_where_B_better": int(better.sum()), "folds": len(d)})
    return pd.DataFrame(rows)


# ================================================================= learning curves (training pool only)
def _lc_fold(k, pool, folds, sel, limit=3):
    with threadpool_limits(limit):
        tr_i, va_i = np.where(folds != k)[0], np.where(folds == k)[0]
        trf, va = pool.iloc[tr_i].reset_index(drop=True), pool.iloc[va_i].reset_index(drop=True)
        cuts = tercile_cuts(trf["views"].values)            # fixed from the full training fold so validation labels do not change
        rng = np.random.default_rng(SEED + k)
        gorder = rng.permutation(trf.ol_group.unique())      # nested group subsets
        rows = []
        for frac in LC_FRACTIONS:
            keep = set(gorder[: max(2, int(round(len(gorder) * frac)))])
            tr = trf[trf.ol_group.isin(keep)].reset_index(drop=True)
            feats = Features(tr, va)
            plan = [dict(variant=r.variant, task=r.task, algo=r.algo, cfg_id=r.cfg_id, cfg=json.loads(r.cfg)) for r in sel.itertuples()]
            recs = fit_predict(tr, va, feats, plan, cuts, mlp_seeds=(MLP_SEEDS[0],))
            for r in recs:
                rows.append({"fold": k, "fraction": frac, "train_rows": len(tr), "variant": r["variant"], "task": r["task"], "algo": r["algo"],
                             "fit_seconds": r["fit_seconds"], **metrics(r["task"], va, cuts, r["pred"])})
    return rows


def run_learning_curves(df, manifest, selection, n_jobs=5, force=False):
    cf = CACHE / "learning_curves.csv"
    if cf.exists() and not force:
        return pd.read_csv(cf)
    m = manifest.set_index("identifier").loc[df.identifier]
    pool_mask = (m["split"] == "pool").to_numpy()
    pool = df[pool_mask].reset_index(drop=True)
    folds = m["cv_fold"].to_numpy()[pool_mask].astype(int)
    sel = selection[selection.family.isin(["linear", "tree", "neural"])]
    res = Parallel(n_jobs=n_jobs)(delayed(_lc_fold)(k, pool, folds, sel) for k in range(N_FOLDS))
    out = pd.DataFrame([r for x in res for r in x])
    out.to_csv(cf, index=False)
    return out


def environment():
    import platform
    import sklearn, scipy, torch, joblib
    return {"python": platform.python_version(), "platform": platform.platform(), "numpy": np.__version__, "pandas": pd.__version__,
            "scipy": scipy.__version__, "scikit-learn": sklearn.__version__, "torch": torch.__version__, "joblib": joblib.__version__,
            "torch_cuda_available": bool(torch.cuda.is_available()), "device_used": "cpu", "cpu_count": os.cpu_count(), "seed": SEED,
            "mlp_seeds": list(MLP_SEEDS), "n_folds": N_FOLDS, "holdout_fraction": HOLDOUT_FRACTION, "bootstrap_resamples": N_BOOT,
            "mlp": {"hidden_layers": [128, 64], "activation": "ReLU", "optimizer": "AdamW", "lr": MLP_LR, "batch_size": MLP_BATCH,
                    "max_epochs": MLP_MAX_EPOCHS, "patience": MLP_PATIENCE, "validation": f"{MLP_VAL_GROUP_FRACTION:.0%} of training work groups"},
            "data_file": str(DATA_FILE.relative_to(ROOT)), "data_sha256": sha256_file(DATA_FILE)}
