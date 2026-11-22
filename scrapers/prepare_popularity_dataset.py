#!/usr/bin/env python3
"""Create a complete-case cohort for a fair description/no-description experiment.

Offline only. Preserve the collected files; export rejected IDs and all reasons.
Optional edition IDs and successful rows' empty error fields are not missing inputs.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = (
    'identifier', 'title', 'creators', 'first_creator', 'publication_year',
    'subjects', 'language', 'addeddate', 'scanned_page_count', 'views_all_time',
    'retrieved_at_utc', 'openlibrary_work', 'ol_group', 'description',
)
NULLS = {'', 'none', 'null', 'nan', 'n/a'}


def missing(value):
    return value is None or str(value).strip().lower() in NULLS


def date(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def rejection_reasons(row):
    reasons = [f'missing:{field}' for field in REQUIRED if missing(row.get(field))]
    if row.get('status') != 'ok':
        reasons.append('collection_status_not_ok')
    if str(row.get('description_ready')).lower() not in {'1', 'true'}:
        reasons.append('description_not_ready')
    if len(str(row.get('description') or '').split()) < 25:
        reasons.append('description_under_25_words')
    if str(row.get('author_missing')).lower() in {'1', 'true'}:
        reasons.append('author_flagged_missing')
    if 'eng' not in str(row.get('language') or '').split(','):
        reasons.append('english_not_listed')
    for field, minimum, maximum in [('publication_year', 1, 9999),
                                     ('scanned_page_count', 1, None),
                                     ('views_all_time', 0, None)]:
        if missing(row.get(field)):
            continue
        try:
            number = float(row[field])
            if (not math.isfinite(number) or not number.is_integer() or
                    number < minimum or (maximum is not None and number > maximum)):
                raise ValueError()
        except (ValueError, TypeError):
            reasons.append(f'invalid:{field}')
    dates = {}
    for field in ['addeddate', 'retrieved_at_utc']:
        if missing(row.get(field)):
            continue
        try:
            dates[field] = date(row[field])
        except (ValueError, TypeError):
            reasons.append(f'invalid:{field}')
    if len(dates) == 2 and dates['addeddate'] > dates['retrieved_at_utc']:
        reasons.append('negative_archive_age')
    if row.get('ol_group') != row.get('openlibrary_work'):
        reasons.append('work_group_mismatch')
    return reasons


def write_csv(path, fields, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT/'data/training_ol_books.csv')
    parser.add_argument('--out-dir', type=Path, default=ROOT/'data')
    args = parser.parse_args(argv)
    with args.input.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    absent = set(REQUIRED + ('status', 'description_ready', 'author_missing')) - set(fields or [])
    if absent:
        raise ValueError(f'Missing input columns: {sorted(absent)}')
    ids = [row['identifier'] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate item IDs in source: resolve these before preparing the cohort.')
    kept, excluded, reason_counts = [], [], Counter()
    for row in rows:
        reasons = rejection_reasons(row)
        if reasons:
            excluded.append({'identifier': row['identifier'], 'source_batch': row.get('source_batch', ''),
                             'reasons': ' | '.join(reasons)})
            reason_counts.update(reasons)
        else:
            kept.append(row)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    output = args.out_dir/'popularity_training_clean.csv'
    rejected = args.out_dir/'popularity_training_exclusions.csv'
    write_csv(output, fields, kept)
    write_csv(rejected, ['identifier', 'source_batch', 'reasons'], excluded)
    report = {
        'source_file': args.input.name,
        'source_sha256': hashlib.sha256(args.input.read_bytes()).hexdigest(),
        'input_rows': len(rows), 'clean_rows': len(kept), 'excluded_rows': len(excluded),
        'columns_preserved': fields, 'required_inputs': list(REQUIRED),
        'reason_counts_overlapping': dict(reason_counts),
        'clean_per_stratum': dict(Counter(r['sampling_stratum'] for r in kept)),
        'clean_per_source': dict(Counter(r['source_batch'] for r in kept)),
        'distinct_works': len({r['ol_group'] for r in kept}),
        'output_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
        'exclusions_sha256': hashlib.sha256(rejected.read_bytes()).hexdigest(),
        'notes': [
            'Same complete-case cohort for both description/no-description experiments; use ol_group for splitting.',
            'Views of zero are valid. Empty optional edition IDs and error fields are allowed.',
            'All original source files are preserved; no imputation or target-based exclusions.',
            'Description readiness is an automated filter, not manual verification of every summary.',
        ],
    }
    (args.out_dir/'popularity_training_quality.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['input_rows', 'clean_rows', 'excluded_rows', 'distinct_works', 'clean_per_source']}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
