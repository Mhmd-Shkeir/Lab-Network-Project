"""Small synthetic checks only: no book-data training or experiment execution."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression,Ridge
from sklearn.preprocessing import StandardScaler,SplineTransformer
from sklearn.feature_extraction.text import TfidfVectorizer,CountVectorizer
from threadpoolctl import threadpool_limits
import model_store
import popularity_experiment as pe
import popularity_improvements as pi
import popularity_checkpoint as pc


def books(n=60,offset=0):
    rows=[]
    for i in range(offset,offset+n):
        g=list(pi.GENRE_ID)[i%3]
        title=f"Voyage mystery {chr(97+i%26)}{chr(97+i//26)}"
        author=f"Writer {chr(97+i%6)}"
        words="Young explorers discover a hidden mystery on a distant planet and learn to work together while searching for their missing friends and a way home"
        words += " " + ["They explore a castle with dragons and magical spells.", "They travel in a spaceship across galaxies and planets.", "They investigate clues to solve a detective case."][i%3]
        b=dict(title=title,author=author,subjects="Stories | Adventure",genre=g,description=words,
               publication_year=1960+i,pages=100+i,archive_years=1.+i/10,juvenile=i%2,collection_flag=i%2)
        r=pi.book_frame([b]).iloc[0].to_dict()
        views=float((i%3+1)**3*40+i)
        r.update(identifier=f"synthetic_{i}",ol_group=f"work_{i//2}",views=views,log_views=np.log1p(views),
                 author_first=pi.norm_name(author))
        rows.append(r)
    return pd.DataFrame(rows)


def forbidden(*a,**k):
    raise AssertionError("Loaded prediction attempted to refit")


class PopularityCheckpointTests(unittest.TestCase):
    def test_frozen_transforms_match_original_sparse_dense_and_categorical_matrices(self):
        tr,te=books(),books(9,75)
        with threadpool_limits(2),patch.object(pi,"SVD_DIM",3):
            fd=pi.FoldData(tr,te)
            want_sparse={(s,v):fd.sparse(s,v)[1] for s in range(6) for v in "AB"}
            want_dense={(s,v):fd.dense(s,v)[1] for s in (0,4,5) for v in "AB"}
            pc.freeze(fd)
            with patch.object(StandardScaler,"fit",forbidden),patch.object(TfidfVectorizer,"fit_transform",forbidden),patch.object(SplineTransformer,"fit",forbidden):
                for key,want in want_sparse.items():
                    got=pc.new_matrix(fd,te,*key)
                    np.testing.assert_allclose(got.toarray(),want.toarray(),rtol=0,atol=1e-12)
                for key,want in want_dense.items():
                    got=pc.new_matrix(fd,te,*key,dense=True)
                    np.testing.assert_allclose(got,want,rtol=0,atol=1e-12)
                got=pc.new_matrix(fd,te,5,"B",dense=True,categorical=True)
                np.testing.assert_allclose(got.iloc[:,:-1].to_numpy(),want_dense[(5,"B")],rtol=0,atol=1e-12)
                self.assertEqual(got.author.tolist(),te.author_first.tolist())

    def test_demo_reload_in_a_fresh_process_never_fits(self):
        tr=books();other=books(4,70)
        with threadpool_limits(2):
            fd=pi.FoldData(tr,other)
            obj=pc.ImprovedPopularityPredictor();obj.cuts=pe.tercile_cuts(tr.views.to_numpy());obj.models={}
            y=pe.to_class(tr.views.to_numpy(),obj.cuts)
            for v in "AB":
                clf,_=pc.fit_spec(fd,"cum_lr",{"C":0.3},5,v,y,tr.log_views.to_numpy())
                reg,_=pc.fit_spec(fd,"ridge",{"alpha":3.0},5,v,y,tr.log_views.to_numpy())
                obj.models[v]=(clf,reg)
            obj.features=pc.freeze(fd)
        book=dict(title="A new voyage",author="Writer a",subjects="Stories | Adventure",genre="science_fiction",
                  description="Young explorers discover a hidden mystery on a distant planet and learn to work together while searching for their missing friends and a way home",
                  publication_year=2005,pages=150,archive_years=4.2,juvenile=True,collection_flag=1)
        expected=obj.predict([book])[0].to_json(orient="records")
        with tempfile.TemporaryDirectory() as tmp:
            path=model_store.save("demo",obj,model_store.signature([]),root=tmp,verbose=False)
            script='''import sys,json,joblib
sys.path.insert(0,sys.argv[1])
from sklearn.linear_model import LogisticRegression,Ridge
from sklearn.preprocessing import StandardScaler,SplineTransformer
from sklearn.feature_extraction.text import TfidfVectorizer,CountVectorizer
import popularity_improvements as pi
def no_fit(*a,**k): raise AssertionError("unexpected training")
for cls in (LogisticRegression,Ridge,StandardScaler,SplineTransformer,TfidfVectorizer,CountVectorizer):
    cls.fit=no_fit
pi.FoldData.__init__=no_fit
model=joblib.load(sys.argv[2])["model"]
print(model.predict([json.loads(sys.argv[3])])[0].to_json(orient="records"))
'''
            proc=subprocess.run([sys.executable,"-B","-c",script,str(Path(pi.__file__).parent),str(path),json.dumps(book)],capture_output=True,text=True,check=True)
            self.assertEqual(expected,proc.stdout.strip())

    def test_final_evaluation_keeps_fitted_models_and_reuses_results(self):
        tr,te=books(),books(9,75)
        specs=[dict(variant="A",step=5,family="ridge",cfg={"alpha":3.0},label="synthetic")]
        with tempfile.TemporaryDirectory() as tmp,threadpool_limits(2):
            original_save,original_load=model_store.save,model_store.load
            with patch.object(pc,"signature",lambda options:model_store.signature([],options)),\
                 patch.object(model_store,"save",lambda name,obj,sig:original_save(name,obj,sig,root=tmp,verbose=False)),\
                 patch.object(model_store,"load",lambda name,sig:original_load(name,sig,root=tmp,verbose=False)):
                first=pc.fit_score_saved(tr,te,specs)
                with patch.object(pi.FoldData,"__init__",forbidden),patch.object(Ridge,"fit",forbidden):
                    second=pc.fit_score_saved(tr,te,specs)
                pd.testing.assert_frame_equal(first[0],second[0])
                path=next((Path(tmp)/"report/ml/models").glob("*.joblib"))
                record=joblib.load(path)["model"]
                bundle=record["fitted"][0]["bundle"]
                got=pc.predict_arrays(bundle,pc.new_matrix(record["features"],te,5,"A"))
                np.testing.assert_allclose(got["reg"],first[1][("synthetic","A","reg")],rtol=0,atol=1e-12)

    def test_categorical_catboost_weights_and_transforms_roundtrip(self):
        try:
            import catboost
        except ImportError:
            self.skipTest("catboost not installed")
        tr,te=books(),books(6,75)
        with threadpool_limits(2),patch.object(pi,"SVD_DIM",3):
            fd=pi.FoldData(tr,te);cuts,y,_=pi.class_labels(tr.views.to_numpy(),te.views.to_numpy())
            bundle,X=pc.fit_spec(fd,"cb_cat",{"depth":2,"iterations":8,"learning_rate":0.1,"l2_leaf_reg":3.0},5,"B",y,tr.log_views.to_numpy())
            expected=pc.predict_arrays(bundle,X)
            with tempfile.TemporaryDirectory() as tmp:
                f=Path(tmp)/"cb.joblib";joblib.dump((pc.freeze(fd),bundle),f)
                frozen,loaded=joblib.load(f)
                with patch.object(catboost.CatBoostClassifier,"fit",forbidden),patch.object(catboost.CatBoostRegressor,"fit",forbidden):
                    got=pc.predict_arrays(loaded,pc.new_matrix(frozen,te,5,"B",dense=True,categorical=True))
                np.testing.assert_array_equal(got["cls"],expected["cls"])
                np.testing.assert_allclose(got["reg"],expected["reg"],rtol=0,atol=1e-12)


if __name__=="__main__":
    unittest.main()
