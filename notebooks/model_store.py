"""Local fitted-model checkpoints, including preprocessing and input/version checks."""
import hashlib
import importlib.metadata
import os
import platform
import tempfile
from pathlib import Path

import joblib

ROOT = Path(__file__).resolve().parent.parent


def signature(paths, options=None):
    versions = {"python": platform.python_version()}
    for name in ("numpy", "scipy", "scikit-learn", "joblib", "torch"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return {"format": 1, "files": {str(Path(p).resolve()): hashlib.sha256(Path(p).read_bytes()).hexdigest()
                                    for p in paths}, "versions": versions, "options": options}


def path_for(name, root=ROOT):
    return Path(root) / "report" / "ml" / "models" / (name + ".joblib")


def load(name, expected, root=ROOT, verbose=True):
    path = path_for(name, root)
    if not path.exists():
        return None
    try:
        saved = joblib.load(path)
    except Exception as exc:
        raise RuntimeError(f"Cannot read saved model {path}. Use retrain=True to rebuild it.") from exc
    if saved.get("signature") != expected:
        if verbose:
            print(f"Saved {name} no longer matches the data, settings, code or package versions; rebuilding it.")
        return None
    if verbose:
        print(f"Loaded {name} from disk (no training).")
    return saved["model"]


def save(name, model, expected, root=ROOT, verbose=True):
    path = path_for(name, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=path.parent)
    os.close(fd)
    try:
        joblib.dump({"signature": expected, "model": model}, tmp, compress=3)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    if verbose:
        print(f"Saved {name}; future sessions can load it without training.")
    return path
