"""Manual-input demo using the paired experiment's CV-selected linear models.

Fit once on the saved training pool, then predict as many manually entered books
as needed. No website requests, holdout fitting, data edits or experiment reruns.
"""
from pathlib import Path
import hashlib
import json
import math
import sys

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits
import model_store

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT/'scrapers'))
from genres import genre_flags, is_juvenile

NUM_COLS = ['publication_year', 'log_pages', 'age_years', 'n_creators', 'n_subjects', 'title_words',
            'genre_science_fiction', 'genre_fantasy', 'genre_mystery_thriller', 'juvenile']
CLASSES = ['low', 'medium', 'high']
GENRE_TAGS = {'science_fiction': 'Science fiction', 'fantasy': 'Fantasy',
              'mystery_thriller': 'Detective and mystery stories'}


def tokens(value):
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple)) else str(value).split('|')
    return [str(v).strip() for v in values if str(v).strip()]


def creator_tokens(value):
    """CountVectorizer's analyser accepts already separated creator names."""
    return value


def number(value, name, default, minimum, integer=False):
    if value is None or (isinstance(value, str) and not value.strip()):
        return default, True
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError(f'{name} must be a number, or None to use the training median.') from None
    if not math.isfinite(result) or result < minimum or (integer and not result.is_integer()):
        raise ValueError(f'{name} must be {"an integer" if integer else "a finite number"} >= {minimum}.')
    return (int(result) if integer else result), False


def prepare_book(*, title, defaults, description='', author='', publication_year=None,
                 pages=None, genre=None, subjects=None, archive_years=None, juvenile=None):
    """One human-entered book -> the same feature columns used in the experiment."""
    if not isinstance(title, str) or not title.strip():
        raise ValueError('Enter a non-empty book title.')
    if description is None:
        description = ''
    if not isinstance(description, str):
        raise ValueError('description must be text.')
    title, description = title.strip(), description.strip()
    if genre in ('', 'other'):
        genre = None
    if genre is not None and genre not in GENRE_TAGS:
        raise ValueError('genre must be science_fiction, fantasy, mystery_thriller, other or None.')
    tags = tokens(subjects)
    if genre and GENRE_TAGS[genre].lower() not in {t.lower() for t in tags}:
        tags.append(GENRE_TAGS[genre])
    creators = tokens(author)
    assumptions = []
    year, used = number(publication_year, 'publication_year', int(defaults['publication_year']), 1, True)
    if year > 9999:
        raise ValueError('publication_year must have at most four digits.')
    if used:
        assumptions.append({'input': 'publication_year', 'value_used': year, 'reason': 'training-pool median'})
    page_count, used = number(pages, 'pages', int(defaults['pages']), 1, True)
    if used:
        assumptions.append({'input': 'pages', 'value_used': page_count, 'reason': 'training-pool median'})
    age, used = number(archive_years, 'archive_years', float(defaults['archive_years']), 0)
    if used:
        assumptions.append({'input': 'archive_years', 'value_used': round(age, 2), 'reason': 'training-pool median; this is archive age, not publication age'})
    if not creators:
        assumptions.append({'input': 'author', 'value_used': 'not supplied', 'reason': 'no named-author feature; creator count uses training-pool median'})
    if not tags:
        assumptions.append({'input': 'subjects', 'value_used': 'not supplied', 'reason': 'no subject words; subject count uses training-pool median'})
    flags = genre_flags(tags)
    if juvenile is None:
        juvenile_value = is_juvenile(tags)
    elif isinstance(juvenile, (bool, np.bool_)) or (isinstance(juvenile, int) and juvenile in (0, 1)):
        juvenile_value = int(juvenile)
    else:
        raise ValueError('juvenile must be True, False or None.')
    if description and len(description.split()) < 25:
        assumptions.append({'input': 'description', 'value_used': f'{len(description.split())} words',
                            'reason': 'shorter than the 25-word minimum used in the training cohort'})
    row = {'publication_year': year, 'log_pages': np.log1p(page_count), 'age_years': age,
           'n_creators': len(creators) if creators else defaults['n_creators'],
           'n_subjects': len(tags) if tags else defaults['n_subjects'], 'title_words': len(title.split()),
           **{f'genre_{g}': int(flags[g]) for g in GENRE_TAGS}, 'juvenile': juvenile_value,
           'meta_text': (title+' '+' '.join(tags)).replace('|', ' ').replace('-', ' ').lower(),
           'creator_tokens': [c.lower() for c in creators], 'description': description}
    return pd.DataFrame([row]), pd.DataFrame(assumptions, columns=['input', 'value_used', 'reason'])


class ManualBookPredictor:
    """CV-selected LogisticRegression and Ridge, using original A/B features."""

    @classmethod
    def from_project(cls, root=ROOT, verbose=True, retrain=False):
        root = Path(root)
        data_path, report = root/'data/popularity_training_clean.csv', root/'report/ml'
        manifest_path = report/'split_manifest.csv'
        env = json.loads((report/'environment.json').read_text(encoding='utf-8'))
        meta = json.loads((report/'split_meta.json').read_text(encoding='utf-8'))
        if hashlib.sha256(data_path.read_bytes()).hexdigest() != env['data_sha256']:
            raise ValueError('The dataset changed after the experiment. Prepare a matching model/split before using this demo.')
        if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != meta['manifest_sha256']:
            raise ValueError('The experiment split manifest hash does not match.')
        sig = model_store.signature([data_path, manifest_path, report/'cv_selection.csv',
                                     Path(__file__), Path(model_store.__file__), root/'scrapers/genres.py'])
        cached = None if retrain else model_store.load('05_popularity', sig, root=root, verbose=verbose)
        if cached is not None:
            return cached
        df = pd.read_csv(data_path, encoding='utf-8-sig', keep_default_na=False)
        manifest = pd.read_csv(manifest_path, keep_default_na=False)
        if df.identifier.duplicated().any() or manifest.identifier.duplicated().any() or set(df.identifier) != set(manifest.identifier):
            raise ValueError('Dataset and split IDs must match uniquely.')
        manifest = manifest.set_index('identifier').loc[df.identifier]
        pool = df[(manifest['split'] == 'pool').to_numpy()].reset_index(drop=True)
        selection = pd.read_csv(report/'cv_selection.csv')
        model = cls().fit(pool, selection, verbose=verbose)
        model.project_root = root
        model.data_sha256 = env['data_sha256']
        model.split_sha256 = meta['manifest_sha256']
        model_store.save('05_popularity', model, sig, root=root, verbose=verbose)
        return model

    def fit(self, pool, selection, verbose=True):
        pool = pool.copy()
        self.training_identifiers = tuple(pool.identifier)
        self.training_groups = frozenset(pool.ol_group)
        if verbose:
            print(f'Preparing the selected models once from {len(pool):,} saved training items; no scraping or CV rerun.')
        pool['age_years'] = (pd.to_datetime(pool.retrieved_at_utc, utc=True)-pd.to_datetime(pool.addeddate, utc=True)).dt.days/365.25
        pool['age_years'] = pool.age_years.clip(lower=0)
        pool['log_pages'] = np.log1p(pool.scanned_page_count)
        pool['n_creators'] = pool.creators.str.count(r' \| ')+1
        pool['n_subjects'] = pool.subjects.str.count(r' \| ')+1
        pool['title_words'] = pool.title.str.split().str.len()
        for c in ['genre_science_fiction', 'genre_fantasy', 'genre_mystery_thriller', 'juvenile']:
            pool[c] = pool[c].astype(str).str.lower().isin(['true', '1']).astype(int)
        pool['meta_text'] = (pool.title+' '+pool.subjects).str.replace(r'[|\-]+', ' ', regex=True).str.lower()
        pool['creator_tokens'] = pool.creators.str.lower().str.split(r' \| ')
        self.defaults = {'publication_year': pool.publication_year.median(), 'pages': pool.scanned_page_count.median(),
                         'archive_years': pool.age_years.median(), 'n_creators': pool.n_creators.median(),
                         'n_subjects': pool.n_subjects.median()}
        self.numeric = StandardScaler().fit(pool[NUM_COLS].astype(float))
        self.meta_text = TfidfVectorizer(max_features=8000, min_df=3, sublinear_tf=True, stop_words='english', token_pattern=r'[a-z]{2,}')
        self.authors = CountVectorizer(analyzer=creator_tokens, binary=True, min_df=2)
        self.description = TfidfVectorizer(max_features=20000, min_df=5, ngram_range=(1, 2), sublinear_tf=True,
                                           stop_words='english', token_pattern=r'[a-z]{2,}', lowercase=True)
        num = sp.csr_matrix(self.numeric.transform(pool[NUM_COLS].astype(float)))
        words = self.meta_text.fit_transform(pool.meta_text)
        authors = self.authors.fit_transform(pool.creator_tokens)
        desc = self.description.fit_transform(pool.description)
        X = {'A': sp.hstack([num, words, authors]).tocsr(),
             'B': sp.hstack([num, words, authors, desc]).tocsr()}
        views = pool.views_all_time.to_numpy(dtype=int)
        self.cutoffs = np.quantile(views, [1/3, 2/3])
        classes = np.where(views <= self.cutoffs[0], 0, np.where(views > self.cutoffs[1], 2, 1))
        self.models = {}
        with threadpool_limits(2):
            for variant in ['A', 'B']:
                chosen = selection[(selection.variant == variant) & selection.is_variant_winner.astype(str).str.lower().eq('true')]
                clf_row = chosen[chosen.task == 'classification'].iloc[0]
                reg_row = chosen[chosen.task == 'regression'].iloc[0]
                if clf_row.algo != 'logreg' or reg_row.algo != 'ridge':
                    raise ValueError('This demo supports the recorded CV-selected LogisticRegression/Ridge pair; the selection has changed.')
                clf = LogisticRegression(max_iter=300, **json.loads(clf_row.cfg)).fit(X[variant], classes)
                reg = Ridge(**json.loads(reg_row.cfg)).fit(X[variant], np.log1p(views))
                self.models[variant] = (clf, reg)
        if verbose:
            print('Ready. Edit BOOK and rerun only the prediction cell for each book.')
        return self

    def predict_book(self, **book):
        frame, assumptions = prepare_book(defaults=self.defaults, **book)
        num = sp.csr_matrix(self.numeric.transform(frame[NUM_COLS].astype(float)))
        words = self.meta_text.transform(frame.meta_text)
        authors = self.authors.transform(frame.creator_tokens)
        metadata = sp.hstack([num, words, authors]).tocsr()
        X = {'A': metadata}
        if frame.description.iloc[0]:
            X['B'] = sp.hstack([metadata, self.description.transform(frame.description)]).tocsr()
        else:
            assumptions.loc[len(assumptions)] = ['description', 'not supplied', 'only the without-description model is shown']
        rows = []
        with threadpool_limits(2):
            for variant, features in X.items():
                clf, reg = self.models[variant]
                probabilities = clf.predict_proba(features)[0]
                log_views = float(reg.predict(features)[0])
                estimate = float(np.expm1(max(0.0, log_views)))
                if not math.isfinite(estimate):
                    raise ValueError('This input produces an extreme estimate outside the model\'s usable range.')
                rows.append({'Inputs': 'Without description' if variant == 'A' else 'With description',
                             'Predicted popularity': CLASSES[int(clf.classes_[probabilities.argmax()])],
                             'Estimated archive views': int(round(estimate)),
                             'Low probability (%)': round(float(probabilities[0])*100, 1),
                             'Medium probability (%)': round(float(probabilities[1])*100, 1),
                             'High probability (%)': round(float(probabilities[2])*100, 1)})
        return {'predictions': pd.DataFrame(rows), 'assumptions': assumptions, 'inputs_used': frame,
                'class_cutoffs': {'low_max': float(self.cutoffs[0]), 'medium_max': float(self.cutoffs[1])}}


    def archive_example(self, kind='holdout'):
        """Load a real saved Archive item; observed views are returned separately from model inputs."""
        examples = {'training': 'fahrenheit4510000brad',
                    'holdout': 'timemachineinvis0000well_p4k8'}
        if kind not in examples:
            raise ValueError("Choose kind='training' or kind='holdout'.")
        if not hasattr(self, 'project_root'):
            raise RuntimeError('Run the updated Setup cell first.')
        root = self.project_root
        data_file, split_file = root/'data/popularity_training_clean.csv', root/'report/ml/split_manifest.csv'
        if (hashlib.sha256(data_file.read_bytes()).hexdigest() != self.data_sha256 or
                hashlib.sha256(split_file.read_bytes()).hexdigest() != self.split_sha256):
            raise ValueError('The dataset/split changed since Setup. Reload matching models before using the examples.')
        data = pd.read_csv(data_file, encoding='utf-8-sig', keep_default_na=False).set_index('identifier')
        manifest = pd.read_csv(split_file, keep_default_na=False).set_index('identifier')
        identifier = examples[kind]
        row, split = data.loc[identifier], manifest.loc[identifier]
        seen = identifier in self.training_identifiers
        group_seen = row['ol_group'] in self.training_groups
        if kind == 'training' and (split['split'] != 'pool' or not seen or not group_seen):
            raise ValueError('The training example is not in the fitted training pool.')
        if kind == 'holdout' and (split['split'] != 'holdout' or seen or group_seen):
            raise ValueError('The held-out example must have neither its item nor its work group in training.')
        years = (pd.to_datetime(row.retrieved_at_utc, utc=True)-pd.to_datetime(row.addeddate, utc=True)).days/365.25
        book = {'title': row['title'], 'description': row['description'], 'author': row['creators'],
                'publication_year': int(row.publication_year), 'pages': int(row.scanned_page_count),
                'genre': None, 'subjects': row['subjects'], 'archive_years': float(years),
                'juvenile': str(row.juvenile).lower() in ['1', 'true']}
        observed = int(row.views_all_time)
        actual = 'low' if observed <= self.cutoffs[0] else ('high' if observed > self.cutoffs[1] else 'medium')
        reference = {'title': row['title'], 'identifier': identifier, 'item_url': row.item_url,
                     'split': 'training pool' if seen else 'held-out test set (work not trained on)',
                     'observed_archive_views': observed, 'observed_popularity': actual,
                     'observed_at_utc': row.retrieved_at_utc, 'work_group': row.ol_group}
        return {'book': book, 'reference': reference}

    def predict_archive_example(self, kind='holdout'):
        """Predict from book metadata first, then attach the separately saved observed target for comparison."""
        example = self.archive_example(kind)
        answer = self.predict_book(**example['book'])
        reference = example['reference']
        table = answer['predictions'].copy()
        table['Observed archive views'] = reference['observed_archive_views']
        table['Observed popularity'] = reference['observed_popularity']
        table['Class matches observed?'] = table['Predicted popularity'] == reference['observed_popularity']
        table['Absolute view-count error'] = (table['Estimated archive views']-reference['observed_archive_views']).abs()
        answer.update(predictions=table, reference=reference, book=example['book'])
        return answer
