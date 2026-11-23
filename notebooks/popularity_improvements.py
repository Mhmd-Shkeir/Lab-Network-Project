"""Notebook 10: can existing scraped data support better popularity prediction? (archived-item engagement, not sales)

Same cohort, same saved grouped folds and the same targets as notebook 05 (helpers imported from popularity_experiment.py, which is unchanged).
Features are added step by step (STEPS). Nothing derived from the predicted book's own views is ever an input: history features (author / subject
engagement of OTHER books) are computed from inner grouped out-of-fold statistics that exclude the book's entire work group, with every average and
fallback computed from training rows only. No web access.
"""
import json
import re
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from joblib import Parallel, delayed
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.preprocessing import SplineTransformer, StandardScaler
from threadpoolctl import threadpool_limits

import popularity_experiment as pe

warnings.filterwarnings("ignore")
ROOT = pe.ROOT
OUT = ROOT / "report" / "ml" / "popularity_improvements"
CACHE = OUT / "cache"
SEED = pe.SEED
N_FOLDS = pe.N_FOLDS
STEPS = {0: "05 baseline features", 1: "+ nonlinear archive age", 2: "+ age x genre", 3: "+ collection flag", 4: "+ consistent author names", 5: "+ author & subject history"}
GENRE_ID = {"science_fiction": 1, "fantasy": 2, "mystery_thriller": 3}
SVD_DIM = 100
HIST_M = 5.0
CB_CFGS = [{"depth": 4, "iterations": 500, "learning_rate": 0.06, "l2_leaf_reg": 5.0}, {"depth": 6, "iterations": 500, "learning_rate": 0.05, "l2_leaf_reg": 10.0}]
LOGREG_C = [0.3, 1.0, 3.0]
RIDGE_A = [1.0, 3.0, 10.0]
CLASS_NAMES = ["low", "medium", "high"]

# ---------------------------------------------------------------- consistent author names
_ROLE = re.compile(r"\b(?:author|authors|illustrator|illustrators|editor|editors|ed|eds|comp|compiler|translator|trans|narrator|photographer|joint author|ill|writer|artist|designer|"
                   r"book designer|reader|creator|adapter|adaptor|foreword|introduction|mangaka group|comic book)\b\.?", re.I)


def norm_name(s):
    """'Rowling, J. K., author' / 'Rowling, J. K' / 'Rowling, J. K. (Joanne), 1965-' -> 'rowling j'  (surname + first initial); names without a comma stay as words."""
    s = str(s).lower()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"\b\d{3,4}\??\s*-\s*(?:\d{3,4})?\??", " ", s)
    s = re.sub(r"\b(?:b|d|ca)\.?\s*\d{4}\b", " ", s)
    s = _ROLE.sub(" ", s)
    s = re.sub(r"[^a-z, ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" ,")
    if "," in s:
        sur, _, given = s.partition(",")
        given = [g for g in re.split(r"[ ,]+", given.strip()) if g]
        return (sur.strip() + (" " + given[0][0] if given else "")).strip()
    return s


def prepare(df):
    """Adds the derived columns used here to a cohort frame (pure functions of the input columns; no views involved)."""
    df = df.copy()
    df["author_keys"] = df["creators"].map(lambda c: sorted({k for k in (norm_name(x) for x in str(c).split(" | ")) if k}))
    df["author_first"] = df["author_keys"].map(lambda k: k[0] if k else "")
    df["subject_tags"] = df["subjects"].map(lambda s: sorted({t.strip().lower() for t in str(s).split(" | ") if t.strip()}))
    df["genre_id"] = df["genre_primary"].map(lambda g: GENRE_ID.get(g, 0))
    return df


# ---------------------------------------------------------------- history features (grouped, out of fold)
def _incidence(lists, vocab):
    rows, cols = [], []
    for i, ks in enumerate(lists):
        for k in ks:
            j = vocab.get(k)
            if j is not None:
                rows.append(i); cols.append(j)
    return sp.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(lists), len(vocab)))


def _stats(X, y, mask):
    Xm = X[mask]
    return np.asarray(Xm.T @ y[mask]).ravel(), np.asarray(Xm.sum(0)).ravel()


def _encode(X, s, c, g_row, m=HIST_M):
    """Mean over the book's keys of the smoothed mean (prior = genre mean) and log mean-count of the OTHER books with that key."""
    u, v = s / (c + m), 1.0 / (c + m)
    U, V = np.asarray(X @ u).ravel(), np.asarray(X @ v).ravel()
    na = np.asarray(X.sum(1)).ravel(); nn = np.asarray(X @ c).ravel()
    mean = np.where(na > 0, (U + m * g_row * V) / np.maximum(na, 1), g_row)
    return mean, np.log1p(np.where(na > 0, nn / np.maximum(na, 1), 0.0))


def history_features(tr, te, n_inner=5, seed=SEED):
    """Training rows: inner grouped out-of-fold (whole work group excluded). Other rows: statistics of all training rows. Returns (H_tr, H_te) with 4 columns:
    author mean, author log-count, subject mean, subject log-count. Genre means / global fallback come from the rows used for the statistics only."""
    y = tr["log_views"].to_numpy()
    av = {k: i for i, k in enumerate(sorted({k for ks in tr.author_keys for k in ks}))}; sv = {k: i for i, k in enumerate(sorted({k for ks in tr.subject_tags for k in ks}))}
    Atr, Str = _incidence(tr.author_keys, av), _incidence(tr.subject_tags, sv)
    Ate, Ste = _incidence(te.author_keys, av), _incidence(te.subject_tags, sv)
    gtr, gte = tr.genre_id.to_numpy(), te.genre_id.to_numpy()

    def genre_means(mask):
        gm = np.full(4, y[mask].mean())
        for g in range(4):
            sel = mask & (gtr == g)
            if sel.sum() > 0:
                gm[g] = y[sel].mean()
        return gm

    Htr = np.zeros((len(tr), 4))
    groups = tr.ol_group.to_numpy(); ug = np.unique(groups); rng = np.random.default_rng(seed)
    fold_of = dict(zip(rng.permutation(ug), np.arange(len(ug)) % n_inner)); fr = np.array([fold_of[g] for g in groups])
    for k in range(n_inner):
        mask = fr != k; sel = fr == k; gm = genre_means(mask)
        sa, ca = _stats(Atr, y, mask); ss, cs = _stats(Str, y, mask)
        Htr[sel, 0], Htr[sel, 1] = _encode(Atr[sel], sa, ca, gm[gtr[sel]])
        Htr[sel, 2], Htr[sel, 3] = _encode(Str[sel], ss, cs, gm[gtr[sel]])
    allm = np.ones(len(tr), bool); gm = genre_means(allm); sa, ca = _stats(Atr, y, allm); ss, cs = _stats(Str, y, allm)
    Hte = np.zeros((len(te), 4))
    Hte[:, 0], Hte[:, 1] = _encode(Ate, sa, ca, gm[gte]); Hte[:, 2], Hte[:, 3] = _encode(Ste, ss, cs, gm[gte])
    return Htr, Hte


# ---------------------------------------------------------------- feature blocks for one training / prediction pair
class FoldData:
    def __init__(self, tr, te, seed=SEED):
        t0 = time.time()
        self.tr, self.te = tr.reset_index(drop=True), te.reset_index(drop=True)
        tr, te = self.tr, self.te
        sc = StandardScaler().fit(tr[pe.NUM_COLS].astype(float)); self.num = (sc.transform(tr[pe.NUM_COLS].astype(float)), sc.transform(te[pe.NUM_COLS].astype(float)))
        tf_m = TfidfVectorizer(max_features=pe.META_MAX_FEATURES, min_df=3, sublinear_tf=True, stop_words="english", token_pattern=r"[a-z]{2,}")
        Ttr, Tte = tf_m.fit_transform(tr["meta_text"]), tf_m.transform(te["meta_text"])
        cv_raw = CountVectorizer(analyzer=pe._creators, binary=True, min_df=2); Rtr, Rte = cv_raw.fit_transform(tr["creator_tokens"]), cv_raw.transform(te["creator_tokens"])
        cv_norm = CountVectorizer(analyzer=pe._creators, binary=True, min_df=2); Ntr, Nte = cv_norm.fit_transform(tr["author_keys"]), cv_norm.transform(te["author_keys"])
        tf_d = TfidfVectorizer(max_features=pe.DESC_MAX_FEATURES, min_df=5, ngram_range=(1, 2), sublinear_tf=True, stop_words="english", token_pattern=r"[a-z]{2,}", lowercase=True)
        self.T, self.R, self.N = (Ttr, Tte), (Rtr, Rte), (Ntr, Nte)
        self.D = (tf_d.fit_transform(tr["description"]), tf_d.transform(te["description"]))
        # nonlinear archive age
        spl = SplineTransformer(n_knots=6, degree=3, knots="quantile", extrapolation="constant", include_bias=False).fit(tr[["age_years"]])
        Str_, Ste_ = spl.transform(tr[["age_years"]]), spl.transform(te[["age_years"]])
        poly = lambda d: np.column_stack([d.age_years ** 2, np.log1p(d.age_years)])
        age_tr, age_te = np.hstack([Str_, poly(tr)]), np.hstack([Ste_, poly(te)])
        sa = StandardScaler().fit(age_tr); self.age = (sa.transform(age_tr), sa.transform(age_te))
        flags = ["genre_science_fiction", "genre_fantasy", "genre_mystery_thriller"]
        inter = lambda S, d: np.hstack([S * d[f].to_numpy()[:, None] for f in flags])
        it_tr, it_te = inter(Str_, tr), inter(Ste_, te); si = StandardScaler().fit(it_tr); self.inter = (si.transform(it_tr), si.transform(it_te))
        self.coll = (tr[["in_americana"]].to_numpy(float), te[["in_americana"]].to_numpy(float))
        H_tr, H_te = history_features(tr, te, seed=seed); sh = StandardScaler().fit(H_tr); self.hist = (sh.transform(H_tr), sh.transform(H_te))
        self.hist_raw = (H_tr, H_te)
        self.transformers = {"numeric": sc, "text": tf_m, "raw_authors": cv_raw, "normal_authors": cv_norm,
                             "description": tf_d, "spline": spl, "age": sa, "interaction": si, "history": sh}
        from popularity_checkpoint import HistoryLookup
        self.history_lookup = HistoryLookup(tr)
        self.svd_transformers = {}
        self._svd = {}
        self.seconds = time.time() - t0

    # ----- sparse design for the linear models
    def sparse(self, step, variant):
        out = []
        for i in (0, 1):
            dense = [self.num[i]]
            if step >= 1: dense.append(self.age[i])
            if step >= 2: dense.append(self.inter[i])
            if step >= 3: dense.append(self.coll[i])
            if step >= 5: dense.append(self.hist[i])
            parts = [sp.csr_matrix(np.hstack(dense)), self.T[i], (self.N if step >= 4 else self.R)[i]] + ([self.D[i]] if variant == "B" else [])
            out.append(sp.hstack(parts).tocsr())
        return tuple(out)

    def _svd_block(self, key, mats, seed=SEED):
        if key not in self._svd:
            Mtr = mats[0]; svd = TruncatedSVD(SVD_DIM, random_state=seed).fit(Mtr); z = StandardScaler().fit(svd.transform(Mtr))
            self.svd_transformers[key] = (svd, z)
            self._svd[key] = tuple(z.transform(svd.transform(m)) for m in mats)
        return self._svd[key]

    # ----- dense design for the tree models (raw numeric columns, SVD text blocks)
    def dense(self, step, variant):
        out = []
        raw = lambda d: np.column_stack([d[pe.NUM_COLS].astype(float).to_numpy()] + ([d[["in_americana"]].to_numpy(float)] if step >= 3 else []))
        base = [raw(self.tr), raw(self.te)]
        if step >= 5: base = [np.hstack([base[0], self.hist_raw[0]]), np.hstack([base[1], self.hist_raw[1]])]
        cre = self.N if step >= 4 else self.R
        svdM = self._svd_block(("M", step >= 4), [sp.hstack([self.T[0], cre[0]]).tocsr(), sp.hstack([self.T[1], cre[1]]).tocsr()])
        svdD = self._svd_block(("D",), [self.D[0], self.D[1]]) if variant == "B" else None
        for i in (0, 1):
            out.append(np.hstack([base[i], svdM[i]] + ([svdD[i]] if variant == "B" else [])))
        return tuple(out)

    def author_cat(self):
        return self.tr["author_first"].astype(str).to_numpy(), self.te["author_first"].astype(str).to_numpy()


# ---------------------------------------------------------------- targets, metrics
def class_labels(views_tr, views_te):
    cuts = pe.tercile_cuts(views_tr)
    return cuts, pe.to_class(views_tr, cuts), pe.to_class(views_te, cuts)


def cls_row(y, pred):
    cm = np.zeros((3, 3), int); np.add.at(cm, (y, pred), 1)
    rec = cm.diagonal() / np.maximum(cm.sum(1), 1)
    m = pe.cls_metrics(y, np.eye(3)[pred])
    return {**m, "recall_low": rec[0], "recall_medium": rec[1], "recall_high": rec[2]}


def reg_row(views, pred_log):
    return pe.reg_metrics(views, pred_log)


# ---------------------------------------------------------------- models
def _cum_probs(p1, p2_):
    p2_ = np.minimum(p2_, p1)
    return np.column_stack([1 - p1, p1 - p2_, p2_])


def tune_thresholds(pred, y):
    """Two cut-offs on a continuous prediction that maximise macro-F1 on the given (training, out-of-fold) predictions."""
    from sklearn.metrics import f1_score
    qs = np.quantile(pred, np.linspace(0.05, 0.95, 91)); best, arg = -1, (qs[30], qs[60])
    for i in range(0, 60, 2):
        for j in range(i + 4, 91, 2):
            lab = np.where(pred <= qs[i], 0, np.where(pred > qs[j], 2, 1)); f = f1_score(y, lab, average="macro", labels=[0, 1, 2], zero_division=0)
            if f > best:
                best, arg = f, (qs[i], qs[j])
    return arg


def inner_oof_ridge(Xtr, ytr_log, groups, alpha, n_inner=4, seed=SEED):
    ug = np.unique(groups); rng = np.random.default_rng(seed); fold_of = dict(zip(rng.permutation(ug), np.arange(len(ug)) % n_inner)); fr = np.array([fold_of[g] for g in groups])
    oof = np.zeros(len(ytr_log))
    for k in range(n_inner):
        oof[fr == k] = Ridge(alpha=alpha).fit(Xtr[fr != k], ytr_log[fr != k]).predict(Xtr[fr == k])
    return oof


def predict(fd, family, cfg, step, variant, ycls_tr, ylog_tr, seed=SEED):
    """Original fit/predict recipe; final evaluation and demos retain these fitted pipelines."""
    from popularity_checkpoint import fit_spec, predict_arrays
    fitted, Xte = fit_spec(fd, family, cfg, step, variant, ycls_tr, ylog_tr, seed)
    return predict_arrays(fitted, Xte)
def fold_job(k, pool, folds, specs, limit=3):
    with threadpool_limits(limit):
        tr_i, va_i = np.where(folds != k)[0], np.where(folds == k)[0]
        tr, va = pool.iloc[tr_i].reset_index(drop=True), pool.iloc[va_i].reset_index(drop=True)
        cuts, ytr_c, yva_c = class_labels(tr["views"].to_numpy(), va["views"].to_numpy()); ytr_l = tr["log_views"].to_numpy()
        fd = FoldData(tr, va)
        rows, oof = [], {}
        for sp_ in specs:
            t0 = time.time(); pr = predict(fd, sp_["family"], sp_["cfg"], sp_["step"], sp_["variant"], ytr_c, ytr_l); sec = time.time() - t0
            base = {"stage": sp_["stage"], "variant": sp_["variant"], "step": sp_["step"], "family": sp_["family"], "cfg_id": sp_["cfg_id"], "cfg": json.dumps(sp_["cfg"]), "fold": k, "fit_seconds": sec}
            key = (sp_["stage"], sp_["variant"], sp_["step"], sp_["family"], sp_["cfg_id"])
            if pr["cls"] is not None:
                rows.append({**base, "task": "classification", **cls_row(yva_c, pr["cls"])}); oof[key + ("cls",)] = (va_i, pr["cls"])
            if pr["reg"] is not None:
                rows.append({**base, "task": "regression", **reg_row(va["views"].to_numpy(), pr["reg"])}); oof[key + ("reg",)] = (va_i, pr["reg"])
    return rows, oof, {"fold": k, "cuts": cuts.tolist(), "yva_c": (va_i, yva_c), "feature_seconds": fd.seconds}


def run_cv(name, pool, folds, specs, n_jobs=5, force=False):
    import pickle
    CACHE.mkdir(parents=True, exist_ok=True)
    cf = CACHE / f"cv_{name}.pkl"
    if cf.exists() and not force:
        return pickle.loads(cf.read_bytes())
    res = Parallel(n_jobs=n_jobs)(delayed(fold_job)(k, pool, folds, specs) for k in range(N_FOLDS))
    rows = [r for x in res for r in x[0]]
    oof = {}
    for _, o, _ in res:
        for key, (idx, pr) in o.items():
            arr = oof.setdefault(key, np.zeros(len(pool), float if key[-1] == "reg" else int)); arr[idx] = pr
    true_c = np.zeros(len(pool), int)
    for _, _, meta in res:
        idx, y = meta["yva_c"]; true_c[idx] = y
    out = {"rows": pd.DataFrame(rows), "oof": oof, "true_class": true_c, "folds_meta": [x[2] for x in res]}
    cf.write_bytes(pickle.dumps(out))
    return out


def make_specs(stage, steps, variants=("A", "B"), families=None):
    specs = []
    for step in steps:
        for v in variants:
            for fam, cfgs in families.items():
                for i, c in enumerate(cfgs):
                    specs.append(dict(stage=stage, step=step, variant=v, family=fam, cfg_id=i, cfg=c))
    return specs


def summarise(rows):
    g = rows.groupby(["stage", "task", "variant", "step", "family", "cfg_id", "cfg"])
    metrics = [c for c in rows.columns if c not in ("stage", "task", "variant", "step", "family", "cfg_id", "cfg", "fold", "fit_seconds")]
    s = g[metrics + ["fit_seconds"]].mean().reset_index()
    sd = g[["macro_f1", "r2_log"]].std().reset_index().rename(columns={"macro_f1": "macro_f1_sd", "r2_log": "r2_log_sd"})
    return s.merge(sd, on=["stage", "task", "variant", "step", "family", "cfg_id", "cfg"])


def best_per(summary, keys, task):
    crit = "macro_f1" if task == "classification" else "r2_log"
    s = summary[summary.task == task].dropna(subset=[crit]); idx = s.groupby(keys)[crit].idxmax()
    return s.loc[idx].reset_index(drop=True)


# ---------------------------------------------------------------- pooled out-of-fold analysis
def pooled_cls(true_c, pred):
    cm = np.zeros((3, 3), int); np.add.at(cm, (true_c, pred), 1)
    return cm


def medium_errors(cm):
    """Where the medium class goes wrong: share of true-medium predicted low / high, and severe (low<->high) errors across all books."""
    med = cm[1] / max(cm[1].sum(), 1)
    return {"medium_recall": med[1], "medium_to_low": med[0], "medium_to_high": med[2], "severe_errors_low_high": (cm[0, 2] + cm[2, 0]) / cm.sum()}


def boot_diff(groups, true_c, views, a, b, kind, n=pe.N_BOOT, seed=SEED):
    """Group-bootstrap CI for (b - a) on the pooled out-of-fold predictions of the SAME books. kind 'cls' (a, b are class vectors) or 'reg' (log predictions)."""
    idxs = pe.boot_indices(groups, n, seed)
    out = []
    for idx in idxs:
        if kind == "cls":
            ma, mb = pe._fast_cls(true_c, a, idx), pe._fast_cls(true_c, b, idx)
        else:
            ma, mb = pe.reg_metrics(views[idx], a[idx]), pe.reg_metrics(views[idx], b[idx])
        out.append({k: mb[k] - ma[k] for k in ma})
    d = pd.DataFrame(out)
    return {f"{c}_{s}": v for c in d.columns for s, v in zip(("mean", "lo95", "hi95"), (d[c].mean(), d[c].quantile(.025), d[c].quantile(.975)))}


# ---------------------------------------------------------------- fit on the whole pool, score other books (historical holdout / external check)
def fit_score(pool, other, specs, limit=8, retrain=False):
    """Reuse saved fitted final models/results; fit and checkpoint missing evaluations once."""
    from popularity_checkpoint import fit_score_saved
    return fit_score_saved(pool, other, specs, limit=limit, retrain=retrain)
def load_unused_books():
    """Books of the full linked export that are NOT in the clean cohort and whose work group is absent from it (no new scraping).
    The 2,374 rows are saved next to the notebook-10 results (unused_books_input.csv), so the check still works after the big
    20,271-row export has been removed from data/."""
    saved, meta = OUT / "unused_books_input.csv", OUT / "unused_books_input.meta.json"
    big = ROOT / "data" / "training_ol_books.csv"
    if big.exists():
        full = pd.read_csv(big, encoding="utf-8-sig", keep_default_na=False)
        clean = pd.read_csv(pe.DATA_FILE, encoding="utf-8-sig", keep_default_na=False)
        ex = full[~full.identifier.isin(clean.identifier) & ~full.ol_group.isin(clean.ol_group)]
        n_excl = len(full) - len(clean)
        OUT.mkdir(parents=True, exist_ok=True)
        ex.to_csv(saved, index=False, encoding="utf-8-sig"); meta.write_text(json.dumps({"n_excluded_from_cohort": n_excl, "rows_work_disjoint": len(ex)}), encoding="utf-8")
    else:
        n_excl = json.loads(meta.read_text(encoding="utf-8"))["n_excluded_from_cohort"]
    CACHE.mkdir(parents=True, exist_ok=True)
    old = pe.DATA_FILE; pe.DATA_FILE = saved
    try:
        df = pe.load_cohort()
    finally:
        pe.DATA_FILE = old
    return prepare(df), n_excl


def environment():
    import catboost, sklearn
    return {**pe.environment(), "catboost": catboost.__version__, "scikit-learn": sklearn.__version__, "steps": STEPS, "history_smoothing_m": HIST_M, "catboost_configs": CB_CFGS,
            "inner_history_folds": 5, "outputs": str(OUT.relative_to(ROOT))}


# ---------------------------------------------------------------- try-a-book demo (notebook 10, section 11)
def book_frame(books):
    """One typed book (dict) or a list of them -> rows with exactly the columns the features need. Views are NOT needed and never used for these rows."""
    books = [books] if isinstance(books, dict) else list(books)
    rows = []
    for i, b in enumerate(books):
        title = str(b["title"]).strip()
        creators = [c.strip() for c in str(b.get("author") or "").split("|") if c.strip()]
        subj = [t.strip() for t in str(b.get("subjects") or "").split("|") if t.strip()]
        g = b.get("genre"); flags = {"science_fiction": 0, "fantasy": 0, "mystery_thriller": 0}
        if g in flags: flags[g] = 1
        subjects = " | ".join(subj)
        meta = re.sub(r"[|\-]+", " ", (title + " " + subjects)).lower()
        rows.append({"publication_year": int(b["publication_year"]), "log_pages": float(np.log1p(float(b["pages"]))), "age_years": float(b["archive_years"]),
                     "n_creators": max(1, len(creators)), "n_subjects": max(1, len(subj)), "title_words": len(title.split()),
                     "genre_science_fiction": flags["science_fiction"], "genre_fantasy": flags["fantasy"], "genre_mystery_thriller": flags["mystery_thriller"],
                     "juvenile": int(bool(b.get("juvenile", False))), "in_americana": int(bool(b.get("collection_flag", 0))), "meta_text": meta,
                     "creator_tokens": [c.lower() for c in creators] or [""], "author_keys": sorted({k for k in (norm_name(c) for c in creators) if k}),
                     "subject_tags": sorted({t.lower() for t in subj}), "genre_id": GENRE_ID.get(g, 0), "description": (b.get("description") or "").strip(),
                     "ol_group": f"demo_{i}", "views": 0, "log_views": 0.0})
    return pd.DataFrame(rows)


def demo_predict(pool, books, selection, retrain=False):
    """Backward-compatible demo: load saved selected models instead of fitting for every book."""
    from popularity_checkpoint import ImprovedPopularityPredictor
    return ImprovedPopularityPredictor.from_project(pool=pool, selection=selection, retrain=retrain).predict(books)
