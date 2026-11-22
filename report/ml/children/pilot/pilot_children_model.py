import re, sys, json, numpy as np, pandas as pd, scipy.sparse as sp
sys.path.insert(0, r"D:\Downloads\semester 9\lab network\project\notebooks")
import phase2_experiment as p2
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import average_precision_score
SC = "C:/Users/mhmd2/AppData/Local/Temp/claude/93d76002291a296f/e674d208-b3e2-48cd-a5e2-982668ed71b3/scratchpad/"
ROOT = r"D:\Downloads\semester 9\lab network\project"

def parse(path):
    return {int(m.group(1)): m.group(2) for m in re.finditer(r"(\d+)([CYA?])", open(path, encoding="utf-8").read())}
lab = {**parse(SC + "kid_labels_1.txt"), **parse(SC + "kid_labels_2.txt")}
assert sorted(lab) == list(range(1, 401))
ks = pd.read_csv(SC + "kid_sample.csv"); ks["label"] = ks.n.map(lab)
print("training labels:", ks.label.value_counts().to_dict())
ks = ks[ks.label != "?"].copy(); ks["child"] = (ks.label == "C").astype(int)

df = p2.load_cohort(); dj = p2.task_frame(df, "juvenile")
man = pd.read_csv(p2.OUT / "split_juvenile.csv", keep_default_na=False).set_index("identifier").loc[dj.identifier]
pool = dj[(man.split == "pool").to_numpy()].reset_index(drop=True); pfold = man.cv_fold.to_numpy()[(man.split == "pool").to_numpy()].astype(int)
w = p2.class_weights("juvenile", pool.y.to_numpy()); cw = {0: w[0], 1: w[1]}

# evaluation set: the 158 blind-labelled test books (children only = my label C)
ev = pd.read_csv(ROOT + r"\report\ml\phase2\audience_check_sample.csv", keep_default_na=False)
ev = ev[ev.my_label != "?"].copy(); ev["child"] = (ev.my_label == "C").astype(int)
test = dj[dj.identifier.isin(ev.identifier)].set_index("identifier").loc[ev.identifier].reset_index()

def tag_logit(variant):
    """Out-of-fold decision score of the existing juvenile-tag logistic regression for pool books, and full-pool-model score for the test books."""
    oof = np.zeros(len(pool))
    for k in range(p2.N_FOLDS):
        tr, va = pool[pfold != k], pool[pfold == k]
        F = p2.Features(p2.allowed(tr.reset_index(drop=True)), p2.allowed(va.reset_index(drop=True)), need_svd=False)
        Xtr, Xva = F.get(variant, "sparse")
        oof[pfold == k] = LogisticRegression(C=1.0, max_iter=500, class_weight=cw).fit(Xtr, tr.y.to_numpy()).decision_function(Xva)
    F = p2.Features(p2.allowed(pool), p2.allowed(test), need_svd=False)
    Xtr, Xte = F.get(variant, "sparse")
    return oof, LogisticRegression(C=1.0, max_iter=500, class_weight=cw).fit(Xtr, pool.y.to_numpy()).decision_function(Xte)

oofA, teA = tag_logit("A"); oofB, teB = tag_logit("B")
idx = pool.reset_index().set_index("identifier").loc[ks.identifier, "index"].to_numpy()
ks["tagA"], ks["tagB"] = oofA[idx], oofB[idx]; ev["tagA"], ev["tagB"] = teA, teB
ks = ks.merge(pool[["identifier", "log_pages", "publication_year", "title_words", "title_text", "description", "ol_group"]], on="identifier")
ev = ev.merge(test[["identifier", "log_pages", "publication_year", "title_words", "title_text", "description"]], on="identifier")

def prf(y, p):
    tp, fp, fn = int(((p == 1) & (y == 1)).sum()), int(((p == 1) & (y == 0)).sum()), int(((p == 0) & (y == 1)).sum())
    pr, rc = tp / max(tp + fp, 1), tp / max(tp + fn, 1); return dict(precision=pr, recall=rc, f1=2 * pr * rc / max(pr + rc, 1e-9), accuracy=float((p == y).mean()), tp=tp, fp=fp, fn=fn)

def feats(kind, tr, te):
    num = ["log_pages", "publication_year", "title_words"]
    cols_tag = {"A": ["tagA"], "B": ["tagB"]}
    parts = {"stackA": cols_tag["A"] + num, "stackB": cols_tag["B"] + num}
    cols = parts[kind]
    sc = StandardScaler().fit(tr[cols]); return sc.transform(tr[cols]), sc.transform(te[cols])

y = ks.child.to_numpy()
skf = StratifiedKFold(5, shuffle=True, random_state=2026)
cands = {"existing tag-model score alone, threshold tuned (A: no description)": ("tagonlyA",), "existing tag-model score alone, threshold tuned (B: with description)": ("tagonlyB",),
         "stacked: tag score + pages + year (A)": ("stackA",), "stacked: tag score + pages + year (B)": ("stackB",)}
rows = []
res = {}
for name, (kind,) in cands.items():
    oof = np.zeros(len(ks))
    for tr_i, va_i in skf.split(ks, y):
        tr, va = ks.iloc[tr_i], ks.iloc[va_i]
        if kind.startswith("tagonly"):
            col = "tagA" if kind.endswith("A") else "tagB"
            ths = np.quantile(tr[col], np.linspace(0.3, 0.95, 66)); best = max(ths, key=lambda t: prf(tr.child.to_numpy(), (tr[col].to_numpy() > t).astype(int))["f1"])
            oof[va_i] = (va[col].to_numpy() > best).astype(int)
        else:
            Xtr, Xva = feats(kind, tr, va)
            oof[va_i] = LogisticRegression(C=0.3, class_weight="balanced", max_iter=500).fit(Xtr, tr.child.to_numpy()).predict(Xva)
    m = prf(y, oof.astype(int)); rows.append(dict(model=name, **m))
cv = pd.DataFrame(rows); pd.set_option("display.width", 250, "display.max_colwidth", 80)
print("\nCROSS-VALIDATION on the 394 training labels (children-only; positives:", int(y.sum()), ")"); print(cv.round(3).to_string(index=False))
best = cv.sort_values("f1", ascending=False).iloc[0].model; print("\nchosen by CV F1:", best)

# final fit on all 394, evaluate once on the 158 blind-labelled test books
def final(kind):
    yt = ev.child.to_numpy()
    if kind.startswith("tagonly"):
        col = "tagA" if kind.endswith("A") else "tagB"
        ths = np.quantile(ks[col], np.linspace(0.3, 0.95, 66)); t = max(ths, key=lambda t: prf(y, (ks[col].to_numpy() > t).astype(int))["f1"])
        return prf(yt, (ev[col].to_numpy() > t).astype(int))
    Xtr, Xte = feats(kind, ks, ev)
    return prf(yt, LogisticRegression(C=0.3, class_weight="balanced", max_iter=500).fit(Xtr, y).predict(Xte))
out = []
for name, (kind,) in cands.items():
    out.append(dict(model=name, **final(kind)))
base = pd.DataFrame([
    dict(model="BASELINE existing juvenile-tag model, classical A", **prf(ev.child.to_numpy(), (ev.classical_A == "juvenile_marker").astype(int).to_numpy())),
    dict(model="BASELINE existing juvenile-tag model, classical B", **prf(ev.child.to_numpy(), (ev.classical_B == "juvenile_marker").astype(int).to_numpy())),
    dict(model="BASELINE existing juvenile-tag model, neural B", **prf(ev.child.to_numpy(), (ev.neural_B == "juvenile_marker").astype(int).to_numpy()))])
R = pd.concat([base, pd.DataFrame(out)])
print("\nFINAL on the 158 blind-labelled test books (children only = label C; positives:", int(ev.child.sum()), ", n =", len(ev), ")")
print(R.round(3).to_string(index=False))
R.round(4).to_csv(ROOT + r"\report\ml\phase2\children_only_pilot_scores.csv", index=False)
ks[["n", "identifier", "label"]].assign(note="label C=children, Y=teen, A=adult; assigned by Claude from title/author/blurb; not human-verified").to_csv(ROOT + r"\report\ml\phase2\children_only_training_labels_400.csv", index=False)

# --- extra diagnostics for the chosen model
Xtr, Xte = feats("stackB", ks, ev)
m = LogisticRegression(C=0.3, class_weight="balanced", max_iter=500).fit(Xtr, y)
print("\nstandardised coefficients (tag score, log pages, year, title words):", np.round(m.coef_[0], 2))
pr = m.predict(Xte); ev["pred_child"] = pr
fp = ev[(pr == 1) & (ev.child == 0)]; fn = ev[(pr == 0) & (ev.child == 1)]
print("false positives by my label:", fp.my_label.value_counts().to_dict(), "| false negatives:", len(fn))
print("pages: children median %.0f vs teen %.0f vs adult %.0f" % tuple(np.expm1(ev.groupby("my_label").log_pages.median()[["C", "Y", "A"]])))
d_ = pd.read_csv(r"D:\Downloads\semester 9\lab network\project\data\popularity_training_clean.csv", encoding="utf-8-sig", keep_default_na=False).set_index("identifier")
print("missed children's books:", [d_.loc[i].title[:35] for i in fn.identifier][:9])
ci = []
rng = np.random.default_rng(2026)
for _ in range(2000):
    s = rng.integers(0, len(ev), len(ev)); yy, pp = ev.child.to_numpy()[s], pr[s]; ci.append(prf(yy, pp)["f1"])
print("bootstrap 95%% interval of F1 on the 158: %.2f - %.2f" % tuple(np.quantile(ci, [.025, .975])))
