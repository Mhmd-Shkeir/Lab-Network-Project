# Completeness report

Pool query: `collection:americana AND mediatype:texts AND language:eng AND subject:fiction AND creator:* AND year:[1800 TO 2020] AND imagecount:[50 TO 1500]`  
Snapshot: `pool_snapshot_20261119.csv.gz` (25722 rows, sha256 `95c397b5b71c851e…`), seed 2026.

## Benchmark (200 manifest ids)

| Method | rows | ok | partial | failed | zero-view rows | retries |
|---|---:|---:|---:|---:|---:|---:|
| api | 200 | 200 | 0 | 0 | 0 | 0 |
| bs4 | 200 | 200 | 0 | 0 | 0 | 0 |
| selenium | 200 | 200 | 0 | 0 | 0 | 0 |

Per-field filled cells (of 200):

| Field | api | bs4 | selenium |
|---|---:|---:|---:|
| identifier | 200 | 200 | 200 |
| title | 200 | 200 | 200 |
| creators | 200 | 200 | 200 |
| first_creator | 200 | 200 | 200 |
| publication_year | 200 | 200 | 200 |
| subjects | 200 | 200 | 200 |
| language | 200 | 200 | 200 |
| addeddate | 200 | 200 | 200 |
| scanned_page_count | 200 | 200 | 200 |
| views_all_time | 200 | 200 | 200 |

Field agreement between the three methods (rows complete in all three):

| Field | compared | equal | differ | missing in a method |
|---|---:|---:|---:|---:|
| title | 200 | 200 | 0 | 0 |
| creators | 200 | 200 | 0 | 0 |
| first_creator | 200 | 200 | 0 | 0 |
| publication_year | 200 | 200 | 0 | 0 |
| subjects | 200 | 199 | 1 | 0 |
| language | 200 | 200 | 0 | 0 |
| addeddate | 200 | 200 | 0 | 0 |
| scanned_page_count | 200 | 200 | 0 | 0 |
| views_all_time | 200 | 5 | 195 | 0 |

## Training set (API)

- usable rows (status ok): **5600** of 5600 manifest ids; not usable: 0
- distinct work groups: 5391 (max 3 items per group)
- benchmark ids inside the training CSV: 200
- genuine zero-view rows kept: 0
- views_all_time: {'min': 4, 'median': 147.0, 'max': 184689, 'mean': 479.46}
- publication_year: {'min': 1800, 'median': 2002.0, 'max': 2020, 'mean': 1996.22}
- scanned_page_count: {'min': 50, 'median': 294.0, 'max': 1434, 'mean': 310.11}
- views snapshot window (UTC): ['2026-11-19T21:33:22Z', '2026-11-21T17:32:23Z']
- benchmark ids whose API views changed between the benchmark run and the training run: 0
- usable rows per sampling stratum: {'benchmark_random_fiction': 200, 'science_fiction': 1800, 'fantasy': 1800, 'mystery_thriller': 1800} (manifest: {'benchmark_random_fiction': 200, 'science_fiction': 1800, 'fantasy': 1800, 'mystery_thriller': 1800})
- of which in the Americana collection: {'benchmark_random_fiction': 200, 'science_fiction': 600, 'fantasy': 600, 'mystery_thriller': 600}
- rows of the previous training_api.csv (2000): changed 0, missing now 0
- rows matching more than one genre rule: 359; genre flags differing from the manifest: 0
- views percentiles (all usable rows): {'p10': 38, 'p25': 66, 'p33': 87, 'p50': 147, 'p66': 259, 'p75': 370, 'p90': 923, 'p99': 4897}
- tercile cut-offs of all rows: low <= 87, high >= 259 (illustration only; thresholds must be fitted on the training split)

Rows per views range and stratum:

| Stratum | 0 | 1-9 | 10-99 | 100-999 | 1000-9999 | 10000+ |
|---|---:|---:|---:|---:|---:|---:|
| benchmark_random_fiction | 0 | 1 | 49 | 119 | 30 | 1 |
| science_fiction | 0 | 4 | 572 | 1060 | 156 | 8 |
| fantasy | 0 | 1 | 654 | 914 | 224 | 7 |
| mystery_thriller | 0 | 1 | 839 | 881 | 78 | 1 |

Share of each stratum in the low / medium / high terciles of all rows:

| Stratum | low | medium | high |
|---|---:|---:|---:|
| benchmark_random_fiction | 44 | 56 | 100 |
| science_fiction | 503 | 648 | 649 |
| fantasy | 581 | 556 | 663 |
| mystery_thriller | 755 | 582 | 463 |

Timings in the run folders are pilot/collection timings (including deliberate waits); the final network comparison is produced separately by re-running the scrapers under packet capture.
