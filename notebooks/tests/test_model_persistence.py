"""Offline checks for fitted-model persistence and unchanged feature transforms."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import model_store
import phase2_experiment as p2


class ModelPersistenceTests(unittest.TestCase):
    def test_fitted_pipeline_loads_in_fresh_process_without_fit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "data.txt"; source.write_text("fixed input")
            expected = model_store.signature([source], {"task": "test"})
            X = np.array([[0., 3.], [1., 3.], [4., 7.], [5., 8.]])
            model = make_pipeline(StandardScaler(), LogisticRegression()).fit(X, [0, 0, 1, 1])
            path = model_store.save("test", model, expected, root=root, verbose=False)
            want = model.predict_proba([[2., 4.]])[0, 1]
            script = '''import joblib,sys
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
def forbidden(*a, **k): raise AssertionError("loading/prediction must never fit")
LogisticRegression.fit = forbidden
StandardScaler.fit = forbidden
model = joblib.load(sys.argv[1])["model"]
print(model.predict_proba([[2.,4.]])[0,1])
'''
            proc = subprocess.run([sys.executable, "-B", "-c", script, str(path)], capture_output=True, text=True, check=True)
            self.assertAlmostEqual(want, float(proc.stdout.strip()), places=12)
            loaded = model_store.load("test", expected, root=root, verbose=False)
            np.testing.assert_allclose(loaded.predict_proba(X), model.predict_proba(X), rtol=0, atol=1e-12)

    def test_changed_input_or_settings_rejects_stale_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / "data.txt"; source.write_text("version one")
            sig = model_store.signature([source], {"variant": "A"})
            model_store.save("test", {"fitted": True}, sig, root=root, verbose=False)
            changed = model_store.signature([source], {"variant": "B"})
            self.assertIsNone(model_store.load("test", changed, root=root, verbose=False))
            source.write_text("version two")
            self.assertIsNone(model_store.load("test", model_store.signature([source], {"variant": "A"}), root=root, verbose=False))

    def test_failed_save_preserves_last_complete_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); sig = model_store.signature([])
            path = model_store.save("test", {"generation": 1}, sig, root=root, verbose=False)
            before = path.read_bytes()
            with patch.object(model_store.joblib, "dump", side_effect=OSError("simulated interrupted write")):
                with self.assertRaises(OSError):
                    model_store.save("test", {"generation": 2}, sig, root=root, verbose=False)
            self.assertEqual(before, path.read_bytes())
            self.assertEqual([], list(path.parent.glob("*.tmp")))

    def test_transforming_new_books_matches_original_feature_blocks(self):
        def frame(n, offset=0):
            return pd.DataFrame([{
                "publication_year": 1990 + i, "log_pages": np.log1p(100 + i), "age_years": 2. + i,
                "n_creators": 1., "title_words": 4., "title_text": "mystery at the lighthouse" if i % 2 else "voyage to another planet",
                "creator_tokens": ["author one" if i % 2 else "author two"],
                "description": "children discover a mystery and explore the lighthouse together" if i % 2 else "space explorers travel to another planet in a distant galaxy",
            } for i in range(offset, offset + n)])[p2.ALLOWED_COLS]
        tr, te = frame(20), frame(3, 20)
        features = p2.Features(tr, te, need_svd=False)
        # Transform-only prediction must work even after training matrices are discarded.
        expected = features.blocks["te"]
        features.blocks = {}; features._c = {}
        with patch.object(StandardScaler, "fit", side_effect=AssertionError("unexpected refit")):
            actual = features.transform(te)
        np.testing.assert_allclose(actual["num"], expected["num"], rtol=0, atol=1e-12)
        for block in ("M", "D"):
            np.testing.assert_allclose(actual[block].toarray(), expected[block].toarray(), rtol=0, atol=1e-12)


if __name__ == "__main__":
    unittest.main()
