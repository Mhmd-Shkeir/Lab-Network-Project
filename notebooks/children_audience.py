"""Children-only audience classifier (notebook 08).

Target: INTENDED CHILDREN'S AUDIENCE (label C = children up to about 12; teens and adults are negatives), not a guarantee of age
suitability and not the catalogue's juvenile subject marker. Labels: data/labels/children_audience_labels.csv (provisional, assigned by an
AI labeller under docs/CHILDREN_LABEL_RULES.md; a manual review sample is in report/ml/children/review/).

Design (fixed before any fresh-test evaluation):
* training labels  = pilot 400 + exploratory 158 + 250 new random pool books (all grouped by ol_group, 5 grouped CV folds);
* FRESH test       = 300 separate random books of the phase-2 juvenile test side (disjoint work groups), evaluated once;
* variant A (metadata only) never receives anything computed from descriptions; variant B adds the real description text and a
  description-based juvenile score. Juvenile scores used as features are OUT OF FOLD for pool books (the saved grouped phase-2 folds) and
  come from the full-pool model only for books of the phase-2 test side (which that model never trained on).
No web access: reads files only.
"""
import hashlib
import json
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler

import phase2_experiment as p2

warnings.filterwarnings("ignore")
ROOT = p2.ROOT
LABELS_FILE = ROOT / "data" / "labels" / "children_audience_labels.csv"
OUT = ROOT / "report" / "ml" / "children"
SEED = 2026
N_FOLDS = 5
TRAIN_ROLES = ("train_pilot400", "train_new", "exploratory158")
TEST_ROLE = "fresh_test"
NUM2 = ["log_pages", "publication_year", "title_words"]
LC_FRACTIONS = (0.25, 0.5, 0.75, 1.0)
HGB2 = [{"max_iter": 100, "learning_rate": 0.05, "max_depth": 2, "min_samples_leaf": 20, "l2_regularization": 1.0},
        {"max_iter": 150, "learning_rate": 0.05, "max_depth": 3, "min_samples_leaf": 20, "l2_regularization": 2.0}]
FAMILIES = {"dummy": [{}],
            "stack_lr": [{"C": c} for c in (0.1, 0.3, 1.0)],
            "stack_hgb": HGB2,
            "direct_lr": [{"C": c} for c in (0.3, 1.0, 3.0)],
            "stack_direct_lr": [{"C": c} for c in (0.1, 0.3, 1.0)]}
FAMILY_TEXT = {"dummy": "always 'not children'", "stack_lr": "logistic regression on [juvenile-tag score(s), pages, year, title length]",
               "stack_hgb": "small gradient-boosted trees on the same inputs", "direct_lr": "logistic regression on pages/year/title length + title words + creators (+ description words in B)",
               "stack_direct_lr": "both of the above in one logistic regression"}
CRITERION = "f1"


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ---------------------------------------------------------------- labels and splits
def load_labels():
    L = pd.read_csv(LABELS_FILE, keep_default_na=False)
    L["usable"] = L.label.isin(["C", "Y", "A"]); L["child"] = (L.label == "C").astype(int)
    return L


def inventory(L):
    t = L.groupby(["role", "label"]).size().unstack(fill_value=0).reindex(columns=["C", "Y", "A", "?"], fill_value=0)
    t["total"] = t.sum(1); t["usable (C+Y+A)"] = t[["C", "Y", "A"]].sum(1)
    return t.loc[[r for r in (*TRAIN_ROLES, TEST_ROLE) if r in t.index]]


def labelled_frame(L, dj):
    """Usable labelled books joined with the cohort columns (only the allowed model inputs + identifiers/groups are used downstream)."""
    U = L[L.usable][["identifier", "role", "label", "child"]]
    d = dj.drop(columns=["y"]).merge(U, on="identifier", how="inner")
    return d.reset_index(drop=True)


def build_splits(L, dj, force=False):
    OUT.mkdir(parents=True, exist_ok=True)
    f_tr, f_te, f_meta = OUT / "children_training_folds.csv", OUT / "children_fresh_test_ids.csv", OUT / "children_split_meta.json"
    if f_tr.exists() and f_te.exists() and not force:
        return pd.read_csv(f_tr, keep_default_na=False), pd.read_csv(f_te, keep_default_na=False)
    d = labelled_frame(L, dj)
    tr = d[d.role.isin(TRAIN_ROLES)][["identifier", "ol_group", "role", "label", "child"]].reset_index(drop=True)
    te = d[d.role == TEST_ROLE][["identifier", "ol_group", "role", "label", "child"]].reset_index(drop=True)
    assert not (set(tr.ol_group) & set(te.ol_group)), "a work group is in both training labels and the fresh test"
    assert not (set(tr.identifier) & set(te.identifier))
    tr["cv_fold"] = -1
    for k, (_, va) in enumerate(StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED).split(tr, tr.child, tr.ol_group)):
        tr.loc[va, "cv_fold"] = k
    assert tr.groupby("ol_group").cv_fold.nunique().max() == 1
    tr.to_csv(f_tr, index=False); te.to_csv(f_te, index=False)
    meta = {"seed": SEED, "cv_folds": N_FOLDS, "group_column": "ol_group", "training_rows": len(tr), "training_groups": int(tr.ol_group.nunique()),
            "training_children": int(tr.child.sum()), "fresh_test_rows": len(te), "fresh_test_groups": int(te.ol_group.nunique()), "fresh_test_children": int(te.child.sum()),
            "sha256_labels": sha256_file(LABELS_FILE), "sha256_training_folds": sha256_file(f_tr), "sha256_fresh_test_ids": sha256_file(f_te),
            "created_utc": pd.Timestamp.utcnow().isoformat(), "rules": "docs/CHILDREN_LABEL_RULES.md"}
    f_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return tr, te


# ---------------------------------------------------------------- juvenile-tag scores used as features (out of fold, work groups kept together)
def tag_scores(dj, force=False):
    """Decision scores of the phase-2 juvenile-tag logistic regression: variant A (metadata only, no description) and B (with description).
    Pool books: out-of-fold with the saved grouped phase-2 folds. Books of the phase-2 test side: full-pool model (never trained on them)."""
    import pickle
    p2.CACHE.mkdir(parents=True, exist_ok=True)
    cf = p2.CACHE / "children_tag_scores.pkl"
    if cf.exists() and not force:
        return pickle.loads(cf.read_bytes())
    man = pd.read_csv(p2.OUT / "split_juvenile.csv", keep_default_na=False).set_index("identifier").loc[dj.identifier]
    is_pool = (man.split == "pool").to_numpy(); fold = man.cv_fold.to_numpy().astype(int)
    pool, other = dj[is_pool].reset_index(drop=True), dj[~is_pool].reset_index(drop=True)
    pf = fold[is_pool]
    w = p2.class_weights("juvenile", pool.y.to_numpy()); cw = {0: w[0], 1: w[1]}
    out = {}
    for variant in ("A", "B"):
        s = pd.Series(0.0, index=dj.identifier)
        for k in range(p2.N_FOLDS):
            tr, va = pool[pf != k].reset_index(drop=True), pool[pf == k].reset_index(drop=True)
            F = p2.Features(p2.allowed(tr), p2.allowed(va), need_svd=False); Xtr, Xva = F.get(variant, "sparse")
            s[va.identifier.values] = LogisticRegression(C=1.0, max_iter=500, class_weight=cw).fit(Xtr, tr.y.to_numpy()).decision_function(Xva)
        F = p2.Features(p2.allowed(pool), p2.allowed(other), need_svd=False); Xtr, Xo = F.get(variant, "sparse")
        s[other.identifier.values] = LogisticRegression(C=1.0, max_iter=500, class_weight=cw).fit(Xtr, pool.y.to_numpy()).decision_function(Xo)
        out[variant] = s
    cf.write_bytes(pickle.dumps(out))
    return out


# ---------------------------------------------------------------- second-stage models
def _tagcols(variant):
    return ["tagA"] if variant == "A" else ["tagA", "tagB"]


def fit_predict(tr, te, variant, family, cfg):
    """Probability of 'children' for the rows of `te`. Everything is fitted on `tr` only (scalers, TF-IDF, models)."""
    t0 = time.time()
    if family == "dummy":
        return np.zeros(len(te)), 0.0
    ytr = tr.child.to_numpy()
    cols = _tagcols(variant) + NUM2
    sc = StandardScaler().fit(tr[cols]); Dtr, Dte = sc.transform(tr[cols]), sc.transform(te[cols])
    if family in ("stack_lr", "stack_hgb"):
        if family == "stack_lr":
            m = LogisticRegression(C=cfg["C"], class_weight="balanced", max_iter=500).fit(Dtr, ytr)
        else:
            m = HistGradientBoostingClassifier(early_stopping=False, class_weight="balanced", random_state=SEED, **cfg).fit(Dtr, ytr)
        return m.predict_proba(Dte)[:, 1], time.time() - t0
    F = p2.Features(tr[p2.ALLOWED_COLS].reset_index(drop=True), te[p2.ALLOWED_COLS].reset_index(drop=True), need_svd=False)
    Mtr, Mte = F.blocks["tr"]["M"], F.blocks["te"]["M"]; Wtr, Wte = F.blocks["tr"]["D"], F.blocks["te"]["D"]
    if family == "direct_lr":
        dtr, dte = sc.transform(tr[cols])[:, -len(NUM2):], sc.transform(te[cols])[:, -len(NUM2):]
    else:
        dtr, dte = Dtr, Dte
    Xtr = sp.hstack([sp.csr_matrix(dtr), Mtr] + ([Wtr] if variant == "B" else [])).tocsr()
    Xte = sp.hstack([sp.csr_matrix(dte), Mte] + ([Wte] if variant == "B" else [])).tocsr()
    m = LogisticRegression(C=cfg["C"], class_weight="balanced", max_iter=500).fit(Xtr, ytr)
    return m.predict_proba(Xte)[:, 1], time.time() - t0


def prf(y, p):
    tp, fp, fn, tn = int(((p == 1) & (y == 1)).sum()), int(((p == 1) & (y == 0)).sum()), int(((p == 0) & (y == 1)).sum()), int(((p == 0) & (y == 0)).sum())
    pr, rc = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    return {"precision": pr, "recall": rc, "f1": 2 * pr * rc / max(pr + rc, 1e-12), "accuracy": (tp + tn) / max(len(y), 1), "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def with_tags(d, tags):
    d = d.copy(); d["tagA"] = d.identifier.map(tags["A"]).to_numpy(); d["tagB"] = d.identifier.map(tags["B"]).to_numpy()
    return d


def cross_validate(train, force=False):
    """Grouped CV on the training labels (saved folds). Returns per-fold rows and out-of-fold probabilities."""
    import pickle
    cf = p2.CACHE / "children_cv.pkl"
    if cf.exists() and not force:
        return pickle.loads(cf.read_bytes())
    rows, oof = [], {}
    for variant in p2.VARIANTS:
        for family, cfgs in FAMILIES.items():
            if family == "dummy" and variant == "B":
                continue
            for ci, cfg in enumerate(cfgs):
                prob = np.zeros(len(train)); fits = []
                for k in range(N_FOLDS):
                    tr, va = train[train.cv_fold != k], train[train.cv_fold == k]
                    pr, sec = fit_predict(tr, va, variant, family, cfg); prob[(train.cv_fold == k).to_numpy()] = pr; fits.append(sec)
                    rows.append({"variant": variant, "family": family, "cfg_id": ci, "cfg": json.dumps(cfg), "fold": k, "fit_seconds": sec,
                                 **prf(va.child.to_numpy(), (pr > 0.5).astype(int))})
                oof[(variant, family, ci)] = prob
    out = {"rows": pd.DataFrame(rows), "oof": oof}
    cf.write_bytes(pickle.dumps(out))
    return out


def summarise(rows):
    s = rows.groupby(["variant", "family", "cfg_id", "cfg"])[["precision", "recall", "f1", "accuracy", "fit_seconds"]].mean().reset_index()
    sd = rows.groupby(["variant", "family", "cfg_id", "cfg"])["f1"].std().reset_index().rename(columns={"f1": "f1_sd"})
    return s.merge(sd, on=["variant", "family", "cfg_id", "cfg"])


def select(summary):
    """Best configuration per family and variant by CV F1 (children class); the winner is the best non-dummy family per variant."""
    rows = []
    for (v, f), g in summary.groupby(["variant", "family"]):
        b = g.sort_values(CRITERION, ascending=False).iloc[0]
        rows.append({"variant": v, "family": f, "cfg_id": int(b.cfg_id), "cfg": b.cfg, "cv_f1": float(b.f1), "cv_precision": float(b.precision), "cv_recall": float(b.recall), "cv_accuracy": float(b.accuracy)})
    sel = pd.DataFrame(rows); sel["is_winner"] = False
    for v, g in sel.groupby("variant"):
        sel.loc[g[g.family != "dummy"].cv_f1.idxmax(), "is_winner"] = True
    return sel


def learning_curve(train, sel):
    """CV F1 of the chosen A and B models against the share of the training labels used (nested group subsets inside each training fold)."""
    rows = []
    rng0 = np.random.default_rng(SEED)
    for variant in p2.VARIANTS:
        r = sel[(sel.variant == variant) & sel.is_winner].iloc[0]; cfg = json.loads(r.cfg)
        for frac in LC_FRACTIONS:
            f1s = []
            for k in range(N_FOLDS):
                trf, va = train[train.cv_fold != k], train[train.cv_fold == k]
                order = np.random.default_rng(SEED + k).permutation(trf.ol_group.unique()); keep = set(order[: max(2, int(round(len(order) * frac)))])
                tr = trf[trf.ol_group.isin(keep)]
                pr, _ = fit_predict(tr, va, variant, r.family, cfg); f1s.append(prf(va.child.to_numpy(), (pr > 0.5).astype(int))["f1"])
                n_rows = len(tr)
            rows.append({"variant": variant, "family": r.family, "fraction": frac, "training_labels": int(round(len(train) * (N_FOLDS - 1) / N_FOLDS * frac)), "cv_f1_mean": float(np.mean(f1s)), "cv_f1_sd": float(np.std(f1s, ddof=1))})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- fresh test (evaluated once, after the selection is on disk)
def old_juvenile_predictions(test):
    """Existing phase-2 juvenile-tag models used directly as a 'children' prediction (the marker also covers teens)."""
    out = {}
    for fam, cols in (("classical", {"A": "A_hgb", "B": "B_hgb"}), ("neural", {"A": "A_mlp", "B": "B_mlp"})):
        p = pd.read_csv(p2.OUT / f"juvenile_{fam}_test_predictions.csv", keep_default_na=False).set_index("identifier")
        for v, c in cols.items():
            out[f"old juvenile-tag model, {fam} {v}"] = (p.loc[test.identifier, c] == "juvenile_marker").astype(int).to_numpy()
    return out


def evaluate_test(train, test, sel):
    res, probs = {}, {}
    for variant in p2.VARIANTS:
        r = sel[(sel.variant == variant) & sel.is_winner].iloc[0]
        pr, sec = fit_predict(train, test, variant, r.family, json.loads(r.cfg)); probs[variant] = pr
        res[variant] = {"family": r.family, "cfg": r.cfg, "fit_seconds": sec}
    return res, probs


def confusion(y, p):
    cm = np.zeros((2, 2), int); np.add.at(cm, (y, p), 1)
    return pd.DataFrame(cm, index=["true: not children", "true: children"], columns=["pred: not children", "pred: children"])


def boot_compare(y, groups, preds, pairs, n=p2.N_BOOT):
    idxs = p2.boot_indices(groups, n)
    return pd.DataFrame([{"comparison": nm, **p2.delta_ci("juvenile", y, preds[a], preds[b], idxs, 2)} for nm, a, b in pairs])


def review_agreement(filled_csv, key_csv):
    """Agreement between a reviewer's labels (sheet with reviewer_label filled in) and the provisional labels."""
    r = pd.read_csv(filled_csv, keep_default_na=False, encoding="utf-8-sig"); k = pd.read_csv(key_csv, keep_default_na=False)
    col = [c for c in r.columns if c.startswith("reviewer_label")][0]
    m = r.merge(k, on="review_id"); m = m[m[col].isin(["C", "Y", "A"]) & m.provisional_label.isin(["C", "Y", "A"])]
    bin_ = lambda s: (s == "C").astype(int)
    return {"reviewed_with_both_labels": len(m), "agreement_3_class": float((m[col] == m.provisional_label).mean()),
            "agreement_children_vs_rest": float((bin_(m[col]) == bin_(m.provisional_label)).mean()),
            "children_precision_of_provisional_vs_reviewer": float(((bin_(m.provisional_label) == 1) & (bin_(m[col]) == 1)).sum() / max((bin_(m.provisional_label) == 1).sum(), 1))}
