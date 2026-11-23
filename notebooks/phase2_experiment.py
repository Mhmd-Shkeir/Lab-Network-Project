"""Phase 2 helpers: genre classification and juvenile-marker classification, without / with description.

Used by notebooks/06_genre_juvenile_classical.ipynb and notebooks/07_genre_juvenile_neural.ipynb.
Cohort: data/popularity_training_clean.csv (no scraping). Groups: ol_group. All fitting uses training rows only.

LABEL-LEAKAGE RULE: the labels (genre flags and the juvenile marker) are derived from subject tags. Therefore NO subject-derived
column is ever given to a model: not the subject tags, their count, the genre flags, genre_primary, juvenile, sampling_stratum or the
collection flag. A model only receives `ALLOWED_COLS` (see below), enforced by `Features`.
"""
import hashlib
import json
import os
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from joblib import Parallel, delayed
from sklearn.decomposition import TruncatedSVD
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, f1_score, precision_recall_fscore_support, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC
from threadpoolctl import threadpool_limits

HERE = Path(__file__).resolve().parent
os.environ["PYTHONPATH"] = str(HERE) + os.pathsep + os.environ.get("PYTHONPATH", "")
os.environ.setdefault("PYTHONWARNINGS", "ignore")
os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 4))
warnings.filterwarnings("ignore")

ROOT = HERE.parent
DATA_FILE = ROOT / "data" / "popularity_training_clean.csv"
OUT = ROOT / "report" / "ml" / "phase2"
CACHE = OUT / "cache"

SEED = 2026
MLP_SEEDS = (2026, 2027, 2028)          # predeclared; the neural result is the average of the three, never the best one
N_FOLDS = 5
TEST_FOLDS = 5                          # one of five grouped folds (about 20 %) is the locked test set
N_BOOT = 1000
LC_FRACTIONS = (0.1, 0.2, 0.4, 0.6, 0.8, 1.0)
VARIANTS = ("A", "B")                   # A: metadata, B: the same metadata + description text
GENRES = ["science_fiction", "fantasy", "mystery_thriller"]
TASKS = {"genre": {"classes": GENRES, "positive": None},
         "juvenile": {"classes": ["no_marker", "juvenile_marker"], "positive": 1}}

NUM_COLS = ["publication_year", "log_pages", "age_years", "n_creators", "title_words"]
ALLOWED_COLS = NUM_COLS + ["title_text", "creator_tokens", "description"]        # the ONLY columns a model sees
EXCLUDED = ["subjects", "n_subjects", "juvenile", "genre_primary", "genre_science_fiction", "genre_fantasy", "genre_mystery_thriller",
            "sampling_stratum", "in_americana", "source_batch", "identifier", "ol_group", "work_group", "views_all_time", "description_words"]
SVD_META, SVD_DESC = 100, 200

HGB_CFGS = [{"max_iter": 150, "learning_rate": 0.05, "max_depth": 3, "min_samples_leaf": 40, "l2_regularization": 1.0},
            {"max_iter": 300, "learning_rate": 0.03, "max_depth": 4, "min_samples_leaf": 40, "l2_regularization": 2.0},
            {"max_iter": 200, "learning_rate": 0.05, "max_depth": 6, "min_samples_leaf": 60, "l2_regularization": 5.0}]
MLP_CFGS = [{"hidden": [64], "weight_decay": 1e-3, "dropout": 0.1}, {"hidden": [64], "weight_decay": 1e-2, "dropout": 0.3},
            {"hidden": [128, 64], "weight_decay": 1e-3, "dropout": 0.1}, {"hidden": [128, 64], "weight_decay": 1e-2, "dropout": 0.3}]
ALGOS = {"classical": {"dummy": [{}], "logreg": [{"C": c} for c in (0.3, 1.0, 3.0, 10.0)], "linsvc": [{"C": c} for c in (0.03, 0.1, 0.3, 1.0)], "hgb": HGB_CFGS},
         "neural": {"mlp": MLP_CFGS}}
FAMILY = {"dummy": "baseline", "logreg": "linear", "linsvc": "linear", "hgb": "tree", "mlp": "neural"}
KIND = {"dummy": "none", "logreg": "sparse", "linsvc": "sparse", "hgb": "dense", "mlp": "dense"}
MLP_MAX_EPOCHS, MLP_PATIENCE, MLP_BATCH, MLP_LR, MLP_VAL_GROUP_FRACTION = 100, 10, 256, 1e-3, 0.15


# ================================================================= data
def load_cohort():
    df = pd.read_csv(DATA_FILE, encoding="utf-8-sig", keep_default_na=False, na_values=[""])
    for c in ("title", "creators", "first_creator", "description", "ol_group", "subjects", "sampling_stratum"):
        df[c] = df[c].fillna("").astype(str)
    retrieved, added = pd.to_datetime(df["retrieved_at_utc"], utc=True), pd.to_datetime(df["addeddate"], utc=True)
    df["age_years"] = ((retrieved - added).dt.days / 365.25).clip(lower=0)
    df["log_pages"] = np.log1p(df["scanned_page_count"])
    df["n_creators"] = df["creators"].str.count(r" \| ") + 1
    df["title_words"] = df["title"].str.split().str.len()
    for c in ("genre_science_fiction", "genre_fantasy", "genre_mystery_thriller", "juvenile"):
        df[c] = df[c].astype(str).str.lower().isin(["true", "1"]).astype(int)
    df["title_text"] = df["title"].str.lower()
    df["creator_tokens"] = df["creators"].str.lower().str.split(r" \| ")
    return df.reset_index(drop=True)


def task_frame(df, task):
    """Eligible books and integer labels. Genre: only clearly single-genre records (exactly one genre flag)."""
    g = df[["genre_science_fiction", "genre_fantasy", "genre_mystery_thriller"]].to_numpy()
    if task == "genre":
        keep = g.sum(1) == 1
        out = df[keep].copy(); out["y"] = g[keep].argmax(1)
    else:
        out = df.copy(); out["y"] = out["juvenile"].astype(int)
    return out.reset_index(drop=True)


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build_split(task, d, force=False):
    """Saved grouped split: ~20 % of work groups locked as test; the rest 5 grouped stratified CV folds. Written before any fit."""
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"split_{task}.csv"
    if f.exists() and not force:
        return pd.read_csv(f, keep_default_na=False)
    m = d[["identifier", "ol_group", "y"]].copy(); m["split"] = "pool"; m["cv_fold"] = -1
    outer = StratifiedGroupKFold(n_splits=TEST_FOLDS, shuffle=True, random_state=SEED)
    _, te = next(outer.split(m, m.y, m.ol_group))
    m.loc[m.index[te], "split"] = "test"
    pool = m[m.split == "pool"]
    for k, (_, va) in enumerate(StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED).split(pool, pool.y, pool.ol_group)):
        m.loc[pool.index[va], "cv_fold"] = k
    assert not (set(m[m.split == "test"].ol_group) & set(m[m.split == "pool"].ol_group)), "a work group is on both sides"
    assert m[m.split == "pool"].groupby("ol_group").cv_fold.nunique().max() == 1
    m.to_csv(f, index=False)
    meta = {"task": task, "seed": SEED, "rows": len(m), "groups": int(m.ol_group.nunique()), "test_rows": int((m.split == "test").sum()),
            "pool_rows": int((m.split == "pool").sum()), "cv_folds": N_FOLDS, "group_column": "ol_group", "sha256": sha256_file(f),
            "created_utc": pd.Timestamp.utcnow().isoformat()}
    (OUT / f"split_{task}_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return m


def _creators(t):
    return t


# ================================================================= features: fitted on the training rows only
class Features:
    """Blocks: numeric (scaled), title TF-IDF + creator one-hot (the metadata text), description TF-IDF. Variant B only ADDS the description."""

    def __init__(self, tr, te, seed=SEED, need_svd=True):
        assert set(tr.columns) == set(ALLOWED_COLS), "a model may only see the allowed columns: %s" % sorted(set(tr.columns) ^ set(ALLOWED_COLS))
        t0 = time.time()
        sc = StandardScaler().fit(tr[NUM_COLS].astype(float))
        tf_t = TfidfVectorizer(max_features=5000, min_df=2, ngram_range=(1, 2), sublinear_tf=True, token_pattern=r"[a-z]{2,}")
        cv_c = CountVectorizer(analyzer=_creators, binary=True, min_df=2)
        tf_d = TfidfVectorizer(max_features=20000, min_df=5, ngram_range=(1, 2), sublinear_tf=True, stop_words="english", token_pattern=r"[a-z]{2,}")
        M = lambda d, fit=False: sp.hstack([(tf_t.fit_transform if fit else tf_t.transform)(d["title_text"]),
                                            (cv_c.fit_transform if fit else cv_c.transform)(d["creator_tokens"])]).tocsr()
        Mtr, Mte = M(tr, True), M(te)
        Dtr, Dte = tf_d.fit_transform(tr["description"]), tf_d.transform(te["description"])
        self.blocks = {"tr": {"num": sc.transform(tr[NUM_COLS].astype(float)), "M": Mtr, "D": Dtr},
                       "te": {"num": sc.transform(te[NUM_COLS].astype(float)), "M": Mte, "D": Dte}}
        if need_svd:
            sm, sd = TruncatedSVD(SVD_META, random_state=seed).fit(Mtr), TruncatedSVD(SVD_DESC, random_state=seed).fit(Dtr)
            zm, zd = StandardScaler().fit(sm.transform(Mtr)), StandardScaler().fit(sd.transform(Dtr))
            for part, (Mx, Dx) in (("tr", (Mtr, Dtr)), ("te", (Mte, Dte))):
                self.blocks[part]["svdM"] = zm.transform(sm.transform(Mx)); self.blocks[part]["svdD"] = zd.transform(sd.transform(Dx))
        self.transformers = {"numeric": sc, "title": tf_t, "creators": cv_c, "description": tf_d}
        self.n_meta, self.n_desc = Mtr.shape[1], Dtr.shape[1]
        self.seconds = time.time() - t0
        self._c = {}

    def transform(self, d):
        """Apply fitted sparse blocks to new books, without fitting anything."""
        tr = self.transformers
        return {"num": tr["numeric"].transform(d[NUM_COLS].astype(float)),
                "M": sp.hstack([tr["title"].transform(d["title_text"]),
                                tr["creators"].transform(d["creator_tokens"])]).tocsr(),
                "D": tr["description"].transform(d["description"])}

    def get(self, variant, kind):
        key = (variant, kind)
        if key not in self._c:
            out = []
            for part in ("tr", "te"):
                b = self.blocks[part]
                if kind == "none":
                    out.append(np.zeros((b["num"].shape[0], 1)))
                elif kind == "sparse":
                    out.append(sp.hstack([sp.csr_matrix(b["num"]), b["M"]] + ([b["D"]] if variant == "B" else [])).tocsr())
                else:
                    out.append(np.hstack([b["num"], b["svdM"]] + ([b["svdD"]] if variant == "B" else [])))
            self._c[key] = tuple(out)
        return self._c[key]


def allowed(d):
    return d[ALLOWED_COLS]


# ================================================================= neural network
def train_mlp(Xtr, ytr, groups, K, weights, cfg, seed, Xte):
    import torch
    from torch import nn
    torch.set_num_threads(2)
    rng = np.random.default_rng(seed); torch.manual_seed(seed)
    ug = np.unique(groups)
    val_g = set(rng.permutation(ug)[: max(1, int(len(ug) * MLP_VAL_GROUP_FRACTION))])
    vm = np.array([g in val_g for g in groups]); tm = ~vm
    Xt, Xv = torch.tensor(Xtr[tm], dtype=torch.float32), torch.tensor(Xtr[vm], dtype=torch.float32)
    yt, yv = torch.tensor(ytr[tm], dtype=torch.long), torch.tensor(ytr[vm], dtype=torch.long)
    loss_fn = nn.CrossEntropyLoss(weight=None if weights is None else torch.tensor(weights, dtype=torch.float32))
    layers, d_in = [], Xtr.shape[1]
    for h in cfg["hidden"]:
        layers += [nn.Linear(d_in, h), nn.ReLU(), nn.Dropout(cfg["dropout"])]; d_in = h
    net = nn.Sequential(*layers, nn.Linear(d_in, K))
    opt = torch.optim.AdamW(net.parameters(), lr=MLP_LR, weight_decay=cfg["weight_decay"])
    gen = torch.Generator().manual_seed(seed)
    hist = {"train_loss": [], "val_loss": []}
    best, best_state, bad = np.inf, None, 0
    for epoch in range(MLP_MAX_EPOCHS):
        net.train()
        perm = torch.randperm(len(Xt), generator=gen)
        for i in range(0, len(Xt), MLP_BATCH):
            b = perm[i:i + MLP_BATCH]
            opt.zero_grad(); loss_fn(net(Xt[b]), yt[b]).backward(); opt.step()
        net.eval()
        with torch.no_grad():
            hist["train_loss"].append(float(loss_fn(net(Xt), yt))); v = float(loss_fn(net(Xv), yv)); hist["val_loss"].append(v)
        if v < best - 1e-4:
            best, bad = v, 0; best_state = {k: t.clone() for k, t in net.state_dict().items()}
        else:
            bad += 1
            if bad >= MLP_PATIENCE:
                break
    net.load_state_dict(best_state); net.eval()
    hist["best_epoch"] = int(np.argmin(hist["val_loss"])) + 1; hist["epochs_run"] = len(hist["val_loss"])
    with torch.no_grad():
        return torch.softmax(net(torch.tensor(Xte, dtype=torch.float32)), 1).numpy(), hist


def class_weights(task, y):
    """Juvenile is uneven (about 27 % positive): balanced class weights in every model. Genre is roughly balanced: none."""
    if task != "juvenile":
        return None
    n = np.bincount(y, minlength=2)
    return len(y) / (2.0 * np.maximum(n, 1))


# ================================================================= fit / predict
def make_plan(task, family):
    return [dict(variant=v, algo=a, cfg_id=i, cfg=c) for v in VARIANTS for a, cfgs in ALGOS[family].items() for i, c in enumerate(cfgs)]


def fit_predict(task, tr_y, tr_groups, feats, plan, mlp_seeds=MLP_SEEDS):
    K = len(TASKS[task]["classes"])
    w = class_weights(task, tr_y)
    cw = None if w is None else {i: float(x) for i, x in enumerate(w)}
    recs = []
    for p in plan:
        Xtr, Xte = feats.get(p["variant"], KIND[p["algo"]])
        a, cfg = p["algo"], p["cfg"]
        base = dict(variant=p["variant"], algo=a, cfg_id=p["cfg_id"], cfg=json.dumps(cfg))
        if a == "mlp":
            preds, secs = [], 0.0
            for s in mlp_seeds:
                t0 = time.time(); pr, h = train_mlp(Xtr, tr_y, tr_groups, K, w, cfg, s, Xte); dt = time.time() - t0
                preds.append(pr); secs += dt
                recs.append({**base, "seed": s, "score": pr, "fit_seconds": dt, "history": h})
            recs.append({**base, "seed": "avg", "score": np.mean(preds, axis=0), "fit_seconds": secs, "history": None})
            continue
        t0 = time.time()
        if a == "dummy":
            m = DummyClassifier(strategy="prior").fit(Xtr, tr_y); sc = m.predict_proba(Xte)
        elif a == "logreg":
            m = LogisticRegression(C=cfg["C"], max_iter=500, class_weight=cw).fit(Xtr, tr_y); sc = m.predict_proba(Xte)
        elif a == "linsvc":
            m = LinearSVC(C=cfg["C"], class_weight=cw, max_iter=3000).fit(Xtr, tr_y); sc = m.decision_function(Xte)
            if sc.ndim == 1:
                sc = np.column_stack([-sc, sc])
        else:
            sw = None if cw is None else np.array([cw[int(c)] for c in tr_y])
            m = HistGradientBoostingClassifier(early_stopping=False, random_state=SEED, **cfg).fit(Xtr, tr_y, sample_weight=sw); sc = m.predict_proba(Xte)
        recs.append({**base, "seed": "single", "score": sc, "fit_seconds": time.time() - t0, "history": None})
    return recs


# ================================================================= metrics
def metrics(task, ytrue, score):
    pred = score.argmax(1)
    out = {"accuracy": float((pred == ytrue).mean()), "macro_f1": float(f1_score(ytrue, pred, average="macro", labels=list(range(score.shape[1])), zero_division=0)),
           "balanced_accuracy": float(balanced_accuracy_score(ytrue, pred))}
    if task == "juvenile":
        p, r, f, _ = precision_recall_fscore_support(ytrue, pred, labels=[1], zero_division=0)
        out.update(juv_precision=float(p[0]), juv_recall=float(r[0]), juv_f1=float(f[0]))
        try:
            out["roc_auc"] = float(roc_auc_score(ytrue, score[:, 1]))
        except ValueError:
            out["roc_auc"] = float("nan")
    else:
        _, _, f, _ = precision_recall_fscore_support(ytrue, pred, labels=[0, 1, 2], zero_division=0)
        for c, x in zip(GENRES, f):
            out[f"f1_{c}"] = float(x)
    return out


def confusion(ytrue, score):
    K = score.shape[1]
    cm = np.zeros((K, K), int); np.add.at(cm, (ytrue, score.argmax(1)), 1)
    return cm


def fast_metrics(task, ytrue, pred, idx, K):
    yt, p = ytrue[idx], pred[idx]
    cm = np.bincount(yt * K + p, minlength=K * K).reshape(K, K); tp = np.diag(cm).astype(float)
    prec, rec = tp / np.maximum(cm.sum(0), 1), tp / np.maximum(cm.sum(1), 1)
    f1 = 2 * prec * rec / np.maximum(prec + rec, 1e-12)
    out = {"accuracy": float(tp.sum() / len(idx)), "macro_f1": float(f1.mean()), "balanced_accuracy": float(rec.mean())}
    if task == "juvenile":
        out.update(juv_precision=float(prec[1]), juv_recall=float(rec[1]), juv_f1=float(f1[1]))
    return out


def boot_indices(groups, n=N_BOOT, seed=SEED):
    ug, inv = np.unique(groups, return_inverse=True)
    rows_of = [np.where(inv == i)[0] for i in range(len(ug))]
    rng = np.random.default_rng(seed)
    return [np.concatenate([rows_of[i] for i in rng.integers(0, len(ug), len(ug))]) for _ in range(n)]


def delta_ci(task, ytrue, pred_first, pred_second, idxs, K):
    rows = []
    for idx in idxs:
        a, b = fast_metrics(task, ytrue, pred_first, idx, K), fast_metrics(task, ytrue, pred_second, idx, K)
        rows.append({k: b[k] - a[k] for k in a})
    d = pd.DataFrame(rows)
    return {f"{c}_{k}": v for c in d.columns for k, v in zip(("mean", "lo95", "hi95"), (d[c].mean(), d[c].quantile(.025), d[c].quantile(.975)))}


# ================================================================= cross-validation on the training pool
def _prep(d, manifest):
    m = manifest.set_index("identifier").loc[d.identifier]
    return m


def _cv_fold(task, k, pool, folds, family, limit=3):
    with threadpool_limits(limit):
        tr_i, va_i = np.where(folds != k)[0], np.where(folds == k)[0]
        tr, va = pool.iloc[tr_i].reset_index(drop=True), pool.iloc[va_i].reset_index(drop=True)
        feats = Features(allowed(tr), allowed(va), need_svd=any(KIND[a] == "dense" for a in ALGOS[family]))
        recs = fit_predict(task, tr["y"].to_numpy(), tr["ol_group"].to_numpy(), feats, make_plan(task, family))
    rows, oof, hist = [], {}, {}
    for r in recs:
        m = metrics(task, va["y"].to_numpy(), r["score"])
        rows.append({"fold": k, "variant": r["variant"], "algo": r["algo"], "cfg_id": r["cfg_id"], "cfg": r["cfg"], "seed": r["seed"],
                     "fit_seconds": r["fit_seconds"], "feature_seconds": feats.seconds, **m})
        key = (r["variant"], r["algo"], r["cfg_id"], str(r["seed"]))
        oof[key] = (va_i, r["score"])
        if r["history"]:
            hist[key + (k,)] = r["history"]
    return rows, oof, hist, {"fold": k, "train_rows": len(tr), "val_rows": len(va), "train_class_counts": np.bincount(tr["y"], minlength=len(TASKS[task]["classes"])).tolist(),
                             "val_class_counts": np.bincount(va["y"], minlength=len(TASKS[task]["classes"])).tolist(), "n_meta": feats.n_meta, "n_desc": feats.n_desc}


def run_cv(task, d, manifest, family, n_jobs=5, force=False):
    import pickle
    CACHE.mkdir(parents=True, exist_ok=True)
    cf = CACHE / f"cv_{task}_{family}.pkl"
    if cf.exists() and not force:
        return pickle.loads(cf.read_bytes())
    m = _prep(d, manifest); pm = (m["split"] == "pool").to_numpy()
    pool = d[pm].reset_index(drop=True); folds = m["cv_fold"].to_numpy()[pm].astype(int)
    res = Parallel(n_jobs=n_jobs)(delayed(_cv_fold)(task, k, pool, folds, family) for k in range(N_FOLDS))
    rows = [r for x in res for r in x[0]]
    hist = {k: v for x in res for k, v in x[2].items()}
    out = {"results": pd.DataFrame(rows), "hist": hist, "fold_info": [x[3] for x in res]}
    cf.write_bytes(pickle.dumps(out))
    return out


def summarise_cv(results):
    r = results[results.seed.astype(str).isin(["single", "avg"])]
    cols = [c for c in r.columns if c not in ("fold", "variant", "algo", "cfg_id", "cfg", "seed")]
    s = r.groupby(["variant", "algo", "cfg_id", "cfg"])[cols].mean().reset_index()
    sd = r.groupby(["variant", "algo", "cfg_id", "cfg"])[["accuracy", "macro_f1"]].std().reset_index().rename(columns={"accuracy": "accuracy_sd", "macro_f1": "macro_f1_sd"})
    s = s.merge(sd, on=["variant", "algo", "cfg_id", "cfg"])
    s["family"] = s.algo.map(FAMILY)
    return s


def select_models(cv_summary, criterion="macro_f1"):
    """Best config per algorithm and variant by CV macro-F1; best non-baseline algorithm flagged. Written to disk before any test scoring."""
    rows = []
    for (v, a), g in cv_summary.groupby(["variant", "algo"]):
        b = g.sort_values(criterion, ascending=False).iloc[0]
        rows.append({"variant": v, "algo": a, "family": FAMILY[a], "cfg_id": int(b.cfg_id), "cfg": b.cfg, "cv_macro_f1": float(b.macro_f1), "cv_accuracy": float(b.accuracy)})
    sel = pd.DataFrame(rows); sel["is_best_in_family"] = False
    for v, g in sel.groupby("variant"):
        real = g[g.family != "baseline"]
        sel.loc[real.cv_macro_f1.idxmax(), "is_best_in_family"] = True
    return sel


# ================================================================= locked test set
def run_test(task, d, manifest, selection, family, force=False):
    import pickle
    cf = CACHE / f"test_{task}_{family}.pkl"
    if cf.exists() and not force:
        return pickle.loads(cf.read_bytes())
    m = _prep(d, manifest)
    pool = d[(m["split"] == "pool").to_numpy()].reset_index(drop=True); test = d[(m["split"] == "test").to_numpy()].reset_index(drop=True)
    plan = [dict(variant=r.variant, algo=r.algo, cfg_id=r.cfg_id, cfg=json.loads(r.cfg)) for r in selection.itertuples()]
    with threadpool_limits(8):
        feats = Features(allowed(pool), allowed(test), need_svd=any(KIND[p["algo"]] == "dense" for p in plan))
        recs = fit_predict(task, pool["y"].to_numpy(), pool["ol_group"].to_numpy(), feats, plan)
    seen = set(t for ts in pool.creator_tokens for t in ts)
    test_author_seen = test.creator_tokens.map(lambda ts: any(t in seen for t in ts)).to_numpy()
    out = {"records": recs, "test_identifiers": test.identifier.tolist(), "test_y": test["y"].to_numpy(), "test_groups": test["ol_group"].to_numpy(),
           "author_seen": test_author_seen, "feature_seconds": feats.seconds, "pool_rows": len(pool), "test_rows": len(test),
           "n_meta": feats.n_meta, "n_desc": feats.n_desc}
    cf.write_bytes(pickle.dumps(out))
    return out


def test_tables(task, test_res, selection):
    y, K = test_res["test_y"], len(TASKS[task]["classes"])
    cls = TASKS[task]["classes"]
    sel = selection.set_index(["variant", "algo"])
    rows, seeds, cms, scores = [], [], [], {}
    for r in test_res["records"]:
        s = sel.loc[(r["variant"], r["algo"])]
        base = {"variant": r["variant"], "algo": r["algo"], "family": FAMILY[r["algo"]], "cfg": r["cfg"], "is_best_in_family": bool(s.is_best_in_family)}
        m = metrics(task, y, r["score"])
        if str(r["seed"]) in ("single", "avg"):
            rows.append({**base, **m, "fit_seconds": r["fit_seconds"]}); scores[(r["variant"], r["algo"])] = r["score"]
            cm = confusion(y, r["score"])
            for i in range(K):
                cms.append({"variant": r["variant"], "algo": r["algo"], "true_class": cls[i], **{f"pred_{cls[j]}": int(cm[i, j]) for j in range(K)}})
            for label, mask in (("author seen in training", test_res["author_seen"]), ("author NOT seen in training", ~test_res["author_seen"])):
                if mask.sum() > 20:
                    sm = metrics(task, y[mask], r["score"][mask])
                    rows[-1][f"accuracy | {label}"] = sm["accuracy"]; rows[-1][f"macro_f1 | {label}"] = sm["macro_f1"]
        else:
            seeds.append({**base, "seed": r["seed"], **m, "best_epoch": r["history"]["best_epoch"], "fit_seconds": r["fit_seconds"]})
    return {"table": pd.DataFrame(rows), "seeds": pd.DataFrame(seeds), "confusion": pd.DataFrame(cms), "scores": scores,
            "n_author_seen": int(test_res["author_seen"].sum()), "n_author_unseen": int((~test_res["author_seen"]).sum())}


def predictions_frame(task, test_res, scores, d):
    cls = TASKS[task]["classes"]
    out = pd.DataFrame({"identifier": test_res["test_identifiers"], "ol_group": test_res["test_groups"], "true": [cls[i] for i in test_res["test_y"]],
                        "author_seen": test_res["author_seen"]})
    for (v, a), sc in scores.items():
        out[f"{v}_{a}"] = [cls[i] for i in sc.argmax(1)]
    return out


def bootstrap_comparisons(task, ytrue, groups, pred_by_key, pairs, n=N_BOOT):
    """pairs: list of (name, detail, key_first, key_second); predictions are integer arrays keyed by (variant, algo) or any label."""
    K = len(TASKS[task]["classes"]); idxs = boot_indices(groups, n)
    return pd.DataFrame([{"comparison": nm, "detail": dt, **delta_ci(task, ytrue, pred_by_key[a], pred_by_key[b], idxs, K)} for nm, dt, a, b in pairs])


# ================================================================= learning curves (training pool only)
def _lc_fold(task, k, pool, folds, sel, family, limit=3):
    with threadpool_limits(limit):
        tr_i, va_i = np.where(folds != k)[0], np.where(folds == k)[0]
        trf, va = pool.iloc[tr_i].reset_index(drop=True), pool.iloc[va_i].reset_index(drop=True)
        rng = np.random.default_rng(SEED + k)
        order = rng.permutation(trf.ol_group.unique())
        rows = []
        for frac in LC_FRACTIONS:
            keep = set(order[: max(2, int(round(len(order) * frac)))])
            tr = trf[trf.ol_group.isin(keep)].reset_index(drop=True)
            feats = Features(allowed(tr), allowed(va), need_svd=any(KIND[a] == "dense" for a in sel.algo))
            plan = [dict(variant=r.variant, algo=r.algo, cfg_id=r.cfg_id, cfg=json.loads(r.cfg)) for r in sel.itertuples()]
            for r in fit_predict(task, tr["y"].to_numpy(), tr["ol_group"].to_numpy(), feats, plan, mlp_seeds=(MLP_SEEDS[0],)):
                rows.append({"fold": k, "fraction": frac, "train_rows": len(tr), "variant": r["variant"], "algo": r["algo"], "fit_seconds": r["fit_seconds"],
                             **metrics(task, va["y"].to_numpy(), r["score"])})
    return rows


def run_learning_curves(task, d, manifest, selection, family, n_jobs=5, force=False):
    cf = CACHE / f"lc_{task}_{family}.csv"
    if cf.exists() and not force:
        return pd.read_csv(cf)
    m = _prep(d, manifest); pm = (m["split"] == "pool").to_numpy()
    pool = d[pm].reset_index(drop=True); folds = m["cv_fold"].to_numpy()[pm].astype(int)
    sel = selection[selection.family != "baseline"]
    res = Parallel(n_jobs=n_jobs)(delayed(_lc_fold)(task, k, pool, folds, sel, family) for k in range(N_FOLDS))
    out = pd.DataFrame([r for x in res for r in x]); out.to_csv(cf, index=False)
    return out


def environment():
    import platform
    import sklearn, scipy, torch, joblib
    return {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__, "scikit-learn": sklearn.__version__,
            "torch": torch.__version__, "joblib": joblib.__version__, "device": "cpu", "cpu_count": os.cpu_count(), "seed": SEED, "mlp_seeds": list(MLP_SEEDS),
            "cv_folds": N_FOLDS, "test_share": f"1/{TEST_FOLDS} of work groups", "bootstrap_resamples": N_BOOT, "svd_dims": {"metadata": SVD_META, "description": SVD_DESC},
            "mlp": {"optimizer": "AdamW", "lr": MLP_LR, "batch": MLP_BATCH, "max_epochs": MLP_MAX_EPOCHS, "patience": MLP_PATIENCE,
                    "validation": f"{MLP_VAL_GROUP_FRACTION:.0%} of training work groups"},
            "data_file": str(DATA_FILE.relative_to(ROOT)), "data_sha256": sha256_file(DATA_FILE), "model_inputs": ALLOWED_COLS, "never_inputs": EXCLUDED}
