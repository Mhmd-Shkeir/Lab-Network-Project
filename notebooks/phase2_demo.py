"""Try-a-book helper for notebook 09 (and for the earlier notebooks 06 classical / 07 neural, now only in Git history).

Refits, once and without any web access, the CV-selected genre and juvenile-marker models of the chosen family on the saved
training pool of each task (the same books, features and settings as in the notebook), then predicts one book typed by hand.
The models see ONLY the allowed inputs (title, creators, year, pages, archive age, number of creators/title words and, in the
'with description' model, the description). Subjects, genre flags and the juvenile marker are never inputs.
"""
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC
from threadpoolctl import threadpool_limits

import phase2_experiment as p2
import model_store

GENRE_LABELS = {"science_fiction": "science fiction", "fantasy": "fantasy", "mystery_thriller": "mystery / thriller"}


class _Transformers:
    """Same transformers and settings as phase2_experiment.Features, kept so that new books can be transformed."""

    def __init__(self, tr, need_svd):
        self.sc = StandardScaler().fit(tr[p2.NUM_COLS].astype(float))
        self.tf_t = TfidfVectorizer(max_features=5000, min_df=2, ngram_range=(1, 2), sublinear_tf=True, token_pattern=r"[a-z]{2,}")
        self.cv_c = CountVectorizer(analyzer=p2._creators, binary=True, min_df=2)
        self.tf_d = TfidfVectorizer(max_features=20000, min_df=5, ngram_range=(1, 2), sublinear_tf=True, stop_words="english", token_pattern=r"[a-z]{2,}")
        Mtr = sp.hstack([self.tf_t.fit_transform(tr["title_text"]), self.cv_c.fit_transform(tr["creator_tokens"])]).tocsr()
        Dtr = self.tf_d.fit_transform(tr["description"])
        self.need_svd = need_svd
        if need_svd:
            self.sm = TruncatedSVD(p2.SVD_META, random_state=p2.SEED).fit(Mtr); self.sd = TruncatedSVD(p2.SVD_DESC, random_state=p2.SEED).fit(Dtr)
            self.zm = StandardScaler().fit(self.sm.transform(Mtr)); self.zd = StandardScaler().fit(self.sd.transform(Dtr))
        self.train_blocks = self.blocks(tr)

    def blocks(self, d):
        M = sp.hstack([self.tf_t.transform(d["title_text"]), self.cv_c.transform(d["creator_tokens"])]).tocsr()
        D = self.tf_d.transform(d["description"])
        b = {"num": self.sc.transform(d[p2.NUM_COLS].astype(float)), "M": M, "D": D}
        if self.need_svd:
            b["svdM"] = self.zm.transform(self.sm.transform(M)); b["svdD"] = self.zd.transform(self.sd.transform(D))
        return b

    @staticmethod
    def matrix(b, variant, kind):
        if kind == "sparse":
            return sp.hstack([sp.csr_matrix(b["num"]), b["M"]] + ([b["D"]] if variant == "B" else [])).tocsr()
        return np.hstack([b["num"], b["svdM"]] + ([b["svdD"]] if variant == "B" else []))


def _train_mlp_net(Xtr, ytr, groups, K, weights, cfg, seed):
    """Identical recipe to phase2_experiment.train_mlp, but returns the trained network."""
    import torch
    from torch import nn
    torch.set_num_threads(2)
    rng = np.random.default_rng(seed); torch.manual_seed(seed)
    ug = np.unique(groups)
    val_g = set(rng.permutation(ug)[: max(1, int(len(ug) * p2.MLP_VAL_GROUP_FRACTION))])
    vm = np.array([g in val_g for g in groups]); tm = ~vm
    Xt, Xv = torch.tensor(Xtr[tm], dtype=torch.float32), torch.tensor(Xtr[vm], dtype=torch.float32)
    yt, yv = torch.tensor(ytr[tm], dtype=torch.long), torch.tensor(ytr[vm], dtype=torch.long)
    loss_fn = nn.CrossEntropyLoss(weight=None if weights is None else torch.tensor(weights, dtype=torch.float32))
    layers, d_in = [], Xtr.shape[1]
    for h in cfg["hidden"]:
        layers += [nn.Linear(d_in, h), nn.ReLU(), nn.Dropout(cfg["dropout"])]; d_in = h
    net = nn.Sequential(*layers, nn.Linear(d_in, K))
    opt = torch.optim.AdamW(net.parameters(), lr=p2.MLP_LR, weight_decay=cfg["weight_decay"])
    gen = torch.Generator().manual_seed(seed)
    best, best_state, bad = np.inf, None, 0
    for _ in range(p2.MLP_MAX_EPOCHS):
        net.train()
        perm = torch.randperm(len(Xt), generator=gen)
        for i in range(0, len(Xt), p2.MLP_BATCH):
            b = perm[i:i + p2.MLP_BATCH]
            opt.zero_grad(); loss_fn(net(Xt[b]), yt[b]).backward(); opt.step()
        net.eval()
        with torch.no_grad():
            v = float(loss_fn(net(Xv), yv))
        if v < best - 1e-4:
            best, bad = v, 0; best_state = {k: t.clone() for k, t in net.state_dict().items()}
        else:
            bad += 1
            if bad >= p2.MLP_PATIENCE:
                break
    net.load_state_dict(best_state); net.eval()
    return net


def _softmax(z):
    z = z - z.max(1, keepdims=True); e = np.exp(z)
    return e / e.sum(1, keepdims=True)


class Phase2Predictor:
    """family = 'classical' (notebook 06: CV-selected LogReg / LinearSVC / HistGradientBoosting) or 'neural' (notebook 07: small MLP)."""

    @classmethod
    def from_project(cls, family="classical", verbose=True, tasks=None, retrain=False):
        requested = tuple(tasks or p2.TASKS)
        if family not in ("classical", "neural") or not requested or any(t not in p2.TASKS for t in requested):
            raise ValueError("Use classical/neural and genre/juvenile tasks.")
        self = cls(); self.family = family
        env = json.loads((p2.OUT / "environment_phase2.json").read_text(encoding="utf-8"))
        if p2.sha256_file(p2.DATA_FILE) != env["data_sha256"]:
            raise ValueError("The dataset changed after the experiment; rerun notebook 06 before using this demo.")
        df = None  # load training rows only when a fitted task checkpoint is missing
        self.models, self.defaults, self.sizes = {}, {}, {}
        t0 = time.time()
        if verbose:
            print(f"Loading saved {family} models; only missing or changed checkpoints require training ...")
        for task in requested:
            paths = [p2.DATA_FILE, p2.OUT / f"split_{task}.csv", p2.OUT / f"{task}_{family}_cv_selection.csv",
                     Path(__file__), Path(p2.__file__), Path(model_store.__file__)]
            sig = model_store.signature(paths, {"family": family, "task": task})
            name = f"phase2_{family}_{task}"
            saved = None if retrain else model_store.load(name, sig, verbose=verbose)
            if saved is not None:
                self.defaults[task], self.sizes[task] = saved["defaults"], saved["rows"]
                for v, model in saved["models"].items():
                    self.models[(task, v)] = model
                continue
            if df is None:
                df = p2.load_cohort()
            d = p2.task_frame(df, task)
            meta = json.loads((p2.OUT / f"split_{task}_meta.json").read_text(encoding="utf-8"))
            if meta["sha256"] != p2.sha256_file(p2.OUT / f"split_{task}.csv"):
                raise ValueError("A saved split file changed after notebook 06.")
            man = pd.read_csv(p2.OUT / f"split_{task}.csv", keep_default_na=False).set_index("identifier").loc[d.identifier]
            pool = d[(man["split"] == "pool").to_numpy()].reset_index(drop=True)
            self.sizes[task] = len(pool)
            sel = pd.read_csv(p2.OUT / f"{task}_{family}_cv_selection.csv")
            sel = sel[sel.is_best_in_family]
            tr = p2.allowed(pool)
            self.defaults[task] = {"publication_year": pool.publication_year.median(), "pages": np.expm1(pool.log_pages.median()), "archive_years": pool.age_years.median(),
                                   "n_creators": pool.n_creators.median(), "title_words": pool.title_words.median()}
            tfm = _Transformers(tr, need_svd=any(p2.KIND[a] == "dense" for a in sel.algo))
            y, groups = pool["y"].to_numpy(), pool["ol_group"].to_numpy()
            w = p2.class_weights(task, y); cw = None if w is None else {i: float(x) for i, x in enumerate(w)}
            K = len(p2.TASKS[task]["classes"])
            for r in sel.itertuples():
                cfg = json.loads(r.cfg); X = tfm.matrix(tfm.train_blocks, r.variant, p2.KIND[r.algo])
                with threadpool_limits(4):
                    if r.algo == "logreg":
                        m = LogisticRegression(C=cfg["C"], max_iter=500, class_weight=cw).fit(X, y)
                    elif r.algo == "linsvc":
                        m = LinearSVC(C=cfg["C"], class_weight=cw, max_iter=3000).fit(X, y)
                    elif r.algo == "hgb":
                        sw = None if cw is None else np.array([cw[int(c)] for c in y])
                        m = HistGradientBoostingClassifier(early_stopping=False, random_state=p2.SEED, **cfg).fit(X, y, sample_weight=sw)
                    else:
                        m = [_train_mlp_net(X, y, groups, K, w, cfg, s) for s in p2.MLP_SEEDS]
                self.models[(task, r.variant)] = (r.algo, m, tfm)
            del tfm.train_blocks  # prediction needs the fitted transformers, not the training matrices
            saved = {"defaults": self.defaults[task], "rows": self.sizes[task],
                     "models": {v: self.models[(task, v)] for v in p2.VARIANTS}}
            model_store.save(name, saved, sig, verbose=verbose)
        self.n_train = self.sizes
        if verbose:
            print(f"Ready in {time.time() - t0:.0f} s. Edit BOOK and rerun only the Predict cell for each book.")
        return self

    # -------------------------------------------------------------- scores for a frame of allowed columns
    def _scores(self, task, variant, frame):
        algo, m, tfm = self.models[(task, variant)]
        b = tfm.blocks(frame); X = tfm.matrix(b, variant, p2.KIND[algo])
        if algo == "mlp":
            import torch
            with torch.no_grad():
                Xt = torch.tensor(X, dtype=torch.float32)
                return np.mean([torch.softmax(net(Xt), 1).numpy() for net in m], axis=0), "probability"
        if algo == "linsvc":
            s = m.decision_function(X)
            if s.ndim == 1:
                s = np.column_stack([-s, s])
            return _softmax(s), "relative score"
        return m.predict_proba(X), "probability"

    def predict_frame(self, task, variant, frame):
        return self._scores(task, variant, frame)[0]

    # -------------------------------------------------------------- one typed book
    def prepare(self, *, title, description="", author="", publication_year=None, pages=None, archive_years=None):
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Enter a non-empty book title.")
        description = (description or "").strip(); title = title.strip()
        dfl = self.defaults["genre"]
        notes = []

        def num(v, key, name, integer=False):
            if v is None or v == "":
                val = float(dfl[key]); notes.append({"input": name, "value_used": round(val, 2), "reason": "training-pool median (not entered)"}); return val
            try:
                val = float(v)
            except (TypeError, ValueError):
                raise ValueError(f"{name} must be a number, or None to use the training median.") from None
            if not math.isfinite(val) or val < (1 if name != "archive_years" else 0):
                raise ValueError(f"{name} is outside the usable range.")
            return int(round(val)) if integer else val

        year = num(publication_year, "publication_year", "publication_year", True)
        if year > 9999:
            raise ValueError("publication_year must have at most four digits.")
        page_count = num(pages, "pages", "pages", True)
        age = num(archive_years, "archive_years", "archive_years")
        creators = [c.strip() for c in str(author or "").split("|") if c.strip()]
        if not creators:
            notes.append({"input": "author", "value_used": "not supplied", "reason": "creator count uses the training-pool median"})
        if description and len(description.split()) < 25:
            notes.append({"input": "description", "value_used": f"{len(description.split())} words", "reason": "shorter than the 25-word minimum of the training cohort"})
        frame = pd.DataFrame([{"publication_year": year, "log_pages": np.log1p(page_count), "age_years": age,
                               "n_creators": len(creators) if creators else dfl["n_creators"], "title_words": len(title.split()),
                               "title_text": title.lower(), "creator_tokens": [c.lower() for c in creators], "description": description}])[p2.ALLOWED_COLS]
        return frame, pd.DataFrame(notes, columns=["input", "value_used", "reason"])

    def predict_book(self, **book):
        frame, notes = self.prepare(**book)
        variants = ["A"] + (["B"] if frame.description.iloc[0] else [])
        if len(variants) == 1:
            notes.loc[len(notes)] = ["description", "not supplied", "only the without-description models are shown"]
        names = {"A": "Without description", "B": "With description"}
        g_rows, j_rows = [], []
        for v in variants:
            pg, kind = self._scores("genre", v, frame); pj, _ = self._scores("juvenile", v, frame)
            pg, pj = pg[0], pj[0]
            kj = self._scores("juvenile", v, frame)[1]
            g_rows.append({"Inputs": names[v], "Predicted genre": GENRE_LABELS[p2.GENRES[int(pg.argmax())]], **{f"{GENRE_LABELS[g]} (%)": round(float(pg[i]) * 100, 1) for i, g in enumerate(p2.GENRES)},
                           "Score type": kind})
            j_rows.append({"Inputs": names[v], "Predicted": "juvenile marker" if pj[1] > 0.5 else "no marker", "Juvenile-marker score (%)": round(float(pj[1]) * 100, 1), "Score type": kj})
        return {"genre": pd.DataFrame(g_rows), "juvenile": pd.DataFrame(j_rows), "assumptions": notes}

    def show(self, BOOK, CATALOGUE=None, note=None):
        """Predict, display, and (for the real examples) compare with the catalogue labels, which are never model inputs."""
        from IPython.display import display
        ans = self.predict_book(**BOOK)
        print("Book:", BOOK["title"], "|", BOOK.get("author", ""))
        if note:
            print(note)
        g, j = ans["genre"].copy(), ans["juvenile"].copy()
        if CATALOGUE:
            g["Catalogue genre"] = GENRE_LABELS[CATALOGUE["genre"]]; g["Genre matches?"] = g["Predicted genre"] == GENRE_LABELS[CATALOGUE["genre"]]
            truth = "juvenile marker" if CATALOGUE["juvenile"] else "no marker"
            j["Catalogue juvenile marker"] = truth; j["Marker matches?"] = j["Predicted"] == truth
        print("\nGENRE (science fiction / fantasy / mystery-thriller)"); display(g)
        print("JUVENILE MARKER (\"no marker\" does not mean the book is for adults; scores come from a class-balanced model, so they overstate how common the marker is)"); display(j)
        if len(ans["assumptions"]):
            print("Missing details / assumptions used:"); display(ans["assumptions"])
        return ans
