"""Fitted checkpoints for notebook 10; training and transform-only prediction are separate."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.linear_model import LogisticRegression, Ridge
from threadpoolctl import threadpool_limits

import model_store
import popularity_experiment as pe
import popularity_improvements as pi


def frame_hash(frame):
    return hashlib.sha256(pd.util.hash_pandas_object(frame.astype(str), index=True).values.tobytes()).hexdigest()


def signature(options):
    try:
        cb = importlib.metadata.version("catboost")
    except importlib.metadata.PackageNotFoundError:
        cb = None
    paths = [pe.DATA_FILE, pe.OUT / "split_manifest.csv", pi.OUT / "cv_selection.csv",
             Path(__file__), Path(pi.__file__), Path(pe.__file__), Path(model_store.__file__)]
    return model_store.signature(paths, {**options, "catboost_version": cb})


class HistoryLookup:
    """Full-training author/subject statistics for predicting other works (never fits on new rows)."""
    def __init__(self, tr):
        y = tr.log_views.to_numpy(); groups = tr.genre_id.to_numpy()
        self.genre_means = np.full(4, y.mean())
        for g in range(4):
            if (groups == g).any():
                self.genre_means[g] = y[groups == g].mean()
        self.stats = {}
        for col in ("author_keys", "subject_tags"):
            vocab = {k:i for i,k in enumerate(sorted({k for keys in tr[col] for k in keys}))}
            X = pi._incidence(tr[col], vocab)
            sums, counts = pi._stats(X, y, np.ones(len(tr), bool))
            self.stats[col] = (vocab, sums, counts)

    def transform(self, other):
        H = np.zeros((len(other), 4)); prior = self.genre_means[other.genre_id.to_numpy()]
        for offset, col in ((0, "author_keys"), (2, "subject_tags")):
            vocab, sums, counts = self.stats[col]
            X = pi._incidence(other[col], vocab)
            H[:, offset], H[:, offset+1] = pi._encode(X, sums, counts, prior)
        return H


def new_matrix(fd, frame, step, variant, dense=False, categorical=False):
    """Apply the stored training transformers, SVD and history statistics. No fitting."""
    t = fd.transformers
    T = t["text"].transform(frame.meta_text)
    C = t["normal_authors" if step >= 4 else "raw_authors"].transform(frame.author_keys if step >= 4 else frame.creator_tokens)
    if dense:
        raw = [frame[pe.NUM_COLS].astype(float).to_numpy()]
        if step >= 3:
            raw.append(frame[["in_americana"]].to_numpy(float))
        if step >= 5:
            raw.append(fd.history_lookup.transform(frame))
        svd, scale = fd.svd_transformers[("M", step >= 4)]
        parts = raw + [scale.transform(svd.transform(sp.hstack([T,C]).tocsr()))]
        if variant == "B":
            svd, scale = fd.svd_transformers[("D",)]
            parts.append(scale.transform(svd.transform(t["description"].transform(frame.description))))
        X = np.hstack(parts)
        if categorical:
            authors = frame.author_first if "author_first" in frame else frame.author_keys.map(lambda keys: keys[0] if keys else "")
            X = pd.DataFrame(X).assign(author=authors.astype(str).to_numpy())
            X.columns = [str(c) for c in X.columns]
        return X
    parts = [t["numeric"].transform(frame[pe.NUM_COLS].astype(float))]
    splines = t["spline"].transform(frame[["age_years"]])
    if step >= 1:
        age = np.hstack([splines, np.column_stack([frame.age_years**2, np.log1p(frame.age_years)])])
        parts.append(t["age"].transform(age))
    if step >= 2:
        interaction = np.hstack([splines * frame[f].to_numpy()[:,None] for f in
                                ("genre_science_fiction", "genre_fantasy", "genre_mystery_thriller")])
        parts.append(t["interaction"].transform(interaction))
    if step >= 3:
        parts.append(frame[["in_americana"]].to_numpy(float))
    if step >= 5:
        parts.append(t["history"].transform(fd.history_lookup.transform(frame)))
    blocks = [sp.csr_matrix(np.hstack(parts)), T, C]
    if variant == "B":
        blocks.append(t["description"].transform(frame.description))
    return sp.hstack(blocks).tocsr()


def fit_spec(fd, family, cfg, step, variant, ycls, ylog, seed=pi.SEED):
    bundle = {"family": family, "cfg": cfg, "step": step, "variant": variant, "models": {}}
    models = bundle["models"]
    if family in ("logreg", "ridge", "cum_lr", "ridge_thr"):
        Xtr, Xte = fd.sparse(step, variant)
        if family == "logreg":
            models["classifier"] = LogisticRegression(C=cfg["C"], max_iter=300).fit(Xtr, ycls)
        elif family == "ridge":
            models["regressor"] = Ridge(alpha=cfg["alpha"]).fit(Xtr, ylog)
        elif family == "cum_lr":
            models["above_low"] = LogisticRegression(C=cfg["C"], max_iter=300).fit(Xtr, (ycls>=1).astype(int))
            models["above_medium"] = LogisticRegression(C=cfg["C"], max_iter=300).fit(Xtr, (ycls>=2).astype(int))
        else:
            oof = pi.inner_oof_ridge(Xtr, ylog, fd.tr.ol_group.to_numpy(), cfg["alpha"])
            bundle["thresholds"] = pi.tune_thresholds(oof, ycls)
            models["regressor"] = Ridge(alpha=cfg["alpha"]).fit(Xtr, ylog)
    elif family in ("cb", "cb_cat", "cb_cum"):
        from catboost import CatBoostClassifier, CatBoostRegressor
        Xtr, Xte = fd.dense(step, variant)
        kw = dict(depth=cfg["depth"], iterations=cfg["iterations"], learning_rate=cfg["learning_rate"],
                  l2_leaf_reg=cfg["l2_leaf_reg"], random_seed=seed, verbose=0, thread_count=3, allow_writing_files=False)
        if family == "cb_cat":
            ctr, cte = fd.author_cat()
            Xtr = pd.DataFrame(Xtr).assign(author=ctr); Xte = pd.DataFrame(Xte).assign(author=cte)
            Xtr.columns = Xte.columns = [str(c) for c in Xtr.columns]; kw["cat_features"] = ["author"]
        if family == "cb_cum":
            models["above_low"] = CatBoostClassifier(loss_function="Logloss", **kw).fit(Xtr, (ycls>=1).astype(int))
            models["above_medium"] = CatBoostClassifier(loss_function="Logloss", **kw).fit(Xtr, (ycls>=2).astype(int))
        else:
            models["classifier"] = CatBoostClassifier(loss_function="MultiClass", **kw).fit(Xtr, ycls)
            models["regressor"] = CatBoostRegressor(loss_function="RMSE", **kw).fit(Xtr, ylog)
    else:
        raise ValueError(family)
    return bundle, Xte


def predict_arrays(bundle, X):
    models = bundle["models"]; out = {"cls": None, "reg": None}
    if "classifier" in models:
        out["cls"] = np.asarray(models["classifier"].predict(X)).ravel().astype(int)
    if "above_low" in models:
        p1 = models["above_low"].predict_proba(X)[:,1]
        p2 = models["above_medium"].predict_proba(X)[:,1]
        out["cls"] = pi._cum_probs(p1,p2).argmax(1)
    if "regressor" in models:
        out["reg"] = models["regressor"].predict(X)
    if "thresholds" in bundle:
        a,b = bundle["thresholds"]
        out["cls"] = np.where(out["reg"]<=a, 0, np.where(out["reg"]>b, 2, 1))
    return out


def freeze(fd):
    # Keep only the fitted transforms/statistics, never the full training/prediction tables or matrices.
    for key in ("tr","te","num","T","R","N","D","age","inter","coll","hist","hist_raw","_svd"):
        if hasattr(fd,key):
            delattr(fd,key)
    return fd


def fit_score_saved(pool, other, specs, limit=8, retrain=False):
    options = {"pool": frame_hash(pool), "other": frame_hash(other), "specs": specs}
    key = hashlib.sha256(json.dumps(options, sort_keys=True).encode()).hexdigest()[:16]
    name = "10_evaluation_" + key; sig = signature(options)
    saved = None if retrain else model_store.load(name,sig)
    if saved is not None:
        return saved["result"]
    with threadpool_limits(limit):
        cuts, ytr_c, yo_c = pi.class_labels(pool.views.to_numpy(),other.views.to_numpy())
        ytr_l = pool.log_views.to_numpy(); fd = pi.FoldData(pool,other)
        rows,preds,fitted = [],{},[]
        for spec in specs:
            t0=time.time()
            bundle,X = fit_spec(fd,spec["family"],spec["cfg"],spec["step"],spec["variant"],ytr_c,ytr_l)
            pred=predict_arrays(bundle,X);seconds=time.time()-t0
            fitted.append({"spec":spec,"bundle":bundle})
            base={"variant":spec["variant"],"step":spec["step"],"family":spec["family"],"cfg":json.dumps(spec["cfg"]),
                  "label":spec.get("label",""),"fit_seconds":seconds}
            k=(spec.get("label",""),spec["variant"])
            if pred["cls"] is not None:
                rows.append({**base,"task":"classification",**pi.cls_row(yo_c,pred["cls"])});preds[k+("cls",)]=pred["cls"]
            if pred["reg"] is not None:
                rows.append({**base,"task":"regression",**pi.reg_row(other.views.to_numpy(),pred["reg"])});preds[k+("reg",)]=pred["reg"]
    result=(pd.DataFrame(rows),preds,yo_c,cuts)
    model_store.save(name,{"result":result,"features":freeze(fd),"fitted":fitted},sig)
    return result


class ImprovedPopularityPredictor:
    """Preserves section 11's selected cumulative LogReg / Ridge demonstration."""
    @classmethod
    def from_project(cls,retrain=False,verbose=True,pool=None,selection=None):
        if pool is None:
            df=pi.prepare(pe.load_cohort())
            manifest=pd.read_csv(pe.OUT/"split_manifest.csv",keep_default_na=False).set_index("identifier").loc[df.identifier]
            pool=df[(manifest["split"]=="pool").to_numpy()].reset_index(drop=True)
        if selection is None:
            selection=pd.read_csv(pi.OUT/"cv_selection.csv")
        sig=signature({"pool":frame_hash(pool),"selection":frame_hash(selection),"demo":"section11_cumulative_ridge"})
        saved=None if retrain else model_store.load("10_popularity_demo",sig,verbose=verbose)
        if saved is not None:
            return saved
        self=cls();self.cuts=pe.tercile_cuts(pool.views.to_numpy());self.models={}
        ycls=pe.to_class(pool.views.to_numpy(),self.cuts);ylog=pool.log_views.to_numpy()
        # An actual pool row is used only to construct compatible prediction matrices.
        with threadpool_limits(4):
            fd=pi.FoldData(pool,pool.iloc[:1])
            for v in ("A","B"):
                c=selection[(selection.task=="classification")&(selection.variant==v)&(selection.role=="best cum_lr")].iloc[0]
                r=selection[(selection.task=="regression")&(selection.variant==v)&(selection.role=="best ridge")].iloc[0]
                classifier,_=fit_spec(fd,"cum_lr",json.loads(c.cfg),5,v,ycls,ylog)
                regressor,_=fit_spec(fd,"ridge",json.loads(r.cfg),5,v,ycls,ylog)
                self.models[v]=(classifier,regressor)
        self.features=freeze(fd)
        model_store.save("10_popularity_demo",self,sig,verbose=verbose)
        return self

    def predict(self,books):
        new=pi.book_frame(books);rows=[]
        for v in ("A","B"):
            classifier,regressor=self.models[v]
            X=new_matrix(self.features,new,5,v)
            m=classifier["models"]
            probs=pi._cum_probs(m["above_low"].predict_proba(X)[:,1],m["above_medium"].predict_proba(X)[:,1])
            est=np.expm1(np.clip(regressor["models"]["regressor"].predict(X),0,None))
            for i in range(len(new)):
                rows.append({"book":i,"Inputs":"Without description" if v=="A" else "With description",
                             "Predicted popularity":pi.CLASS_NAMES[int(probs[i].argmax())],
                             "Low (%)":round(float(probs[i,0])*100,1),"Medium (%)":round(float(probs[i,1])*100,1),
                             "High (%)":round(float(probs[i,2])*100,1),"Estimated views":int(round(float(est[i])))})
        return pd.DataFrame(rows),self.cuts
