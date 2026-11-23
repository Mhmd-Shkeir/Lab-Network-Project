"""Reloadable prediction for notebook 08's intended-children-audience models."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from threadpoolctl import threadpool_limits

import children_audience as ca
import model_store
import phase2_demo
import phase2_experiment as p2


class ChildrenPredictor:
    @classmethod
    def from_project(cls, retrain=False, verbose=True):
        self = cls()
        self.stages = ca.saved_children_models(retrain=retrain, verbose=verbose)
        paths = [p2.DATA_FILE, p2.OUT / "split_juvenile.csv", Path(__file__),
                 Path(ca.__file__), Path(p2.__file__), Path(phase2_demo.__file__), Path(model_store.__file__)]
        sig = model_store.signature(paths)
        tagger = None if retrain else model_store.load("08_children_tag_models", sig, verbose=verbose)
        if tagger is None:
            dj = p2.task_frame(p2.load_cohort(), "juvenile")
            m = pd.read_csv(p2.OUT / "split_juvenile.csv", keep_default_na=False).set_index("identifier").loc[dj.identifier]
            pool = dj[(m["split"] == "pool").to_numpy()].reset_index(drop=True)
            y = pool.y.to_numpy(); w = p2.class_weights("juvenile", y)
            cw = {i: float(x) for i, x in enumerate(w)}
            with threadpool_limits(4):
                tfm = phase2_demo._Transformers(p2.allowed(pool), need_svd=False)
                models = {}
                for v in p2.VARIANTS:
                    X = tfm.matrix(tfm.train_blocks, v, "sparse")
                    models[v] = LogisticRegression(C=1.0, max_iter=500, class_weight=cw).fit(X, y)
            del tfm.train_blocks
            defaults = {"publication_year": pool.publication_year.median(), "pages": np.expm1(pool.log_pages.median()),
                        "archive_years": pool.age_years.median(), "n_creators": pool.n_creators.median()}
            tagger = {"transformers": tfm, "models": models, "defaults": defaults}
            model_store.save("08_children_tag_models", tagger, sig, verbose=verbose)
        self.tagger = tagger
        # Reuse the validated title/year/pages/age input preparation, without subject-derived inputs.
        self.defaults = {"genre": tagger["defaults"]}
        return self

    def predict_book(self, **book):
        frame, notes = phase2_demo.Phase2Predictor.prepare(self, **book)
        tfm = self.tagger["transformers"]; blocks = tfm.blocks(frame)
        variants = ["A"] + (["B"] if frame.description.iloc[0] else [])
        for v in variants:
            X = tfm.matrix(blocks, v, "sparse")
            frame["tag" + v] = self.tagger["models"][v].decision_function(X)
        rows = []
        for v in variants:
            prob = float(ca.predict_fitted(self.stages[v], frame)[0])
            rows.append({"Inputs": "Without description" if v == "A" else "With description",
                         "Prediction": "children" if prob > .5 else "not children",
                         "Children model score (%)": round(100 * prob, 1)})
        if len(variants) == 1:
            notes.loc[len(notes)] = ["description", "not supplied", "only the without-description model is shown"]
        return {"predictions": pd.DataFrame(rows), "assumptions": notes}
