"""Small, paced Internet Archive feasibility/timing pilot; no challenge automation."""
import argparse
import csv
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
UA = 'LabNetUniversityPilot/1.0 (Codex; GPT-6; educational metadata study)'
DELAY = 3.0
FIELDS = ['identifier', 'title', 'creators', 'publication_year', 'subjects',
          'language', 'addeddate', 'scanned_page_count', 'views_all_time']


def clean(value):
    return re.sub(r'\s+', ' ', str(value)).strip()


def values(value):
    return list(dict.fromkeys(clean(x) for x in (value if isinstance(value, list) else [value]) if x is not None))


def parse_html(html, identifier):
    soup = BeautifulSoup(html, 'html.parser')
    if 'verify_human' in html[:3000].lower() or 'human verification' in soup.title.get_text(' ', strip=True).lower():
        raise RuntimeError('Human verification encountered; stopped without interaction')
    metadata = {}
    for dl in soup.select('dl.metadata-definition'):
        for dt in dl.find_all('dt', recursive=False):
            dd = dt.find_next_sibling('dd')
            if dd:
                metadata[clean(dt.get_text(' ', strip=True)).lower()] = dd
    title = soup.select_one('h1.item-title')
    creator = soup.select_one('dl[aria-label="Item creator metadata"]')
    views = soup.select_one('section.item-stats-summary [itemprop="userInteractionCount"]')
    def text(key):
        return clean(metadata[key].get_text(' ', strip=True)) if key in metadata else ''
    year_match = re.search(r'\b\d{4}\b', text('publication date'))
    page_text = text('pages').replace(',', '')
    return {
        'identifier': identifier,
        'title': clean(title.get_text(' ', strip=True)) if title else '',
        'creators': values([x.get_text(' ', strip=True) for x in creator.select('a')]) if creator else [],
        'publication_year': int(year_match.group()) if year_match else None,
        'subjects': values([x.get_text(' ', strip=True) for x in metadata['topics'].select('a')]) if 'topics' in metadata else [],
        'language': {'English': 'eng'}.get(text('language'), text('language')),
        'addeddate': text('addeddate').replace(' ', 'T') + 'Z' if text('addeddate') else '',
        'scanned_page_count': int(page_text) if page_text.isdigit() else None,
        'views_all_time': int(views.get_text(strip=True).replace(',', '')) if views else None,
    }


def save_rows(path, rows):
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({k: json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v for k, v in row.items()} for row in rows)


def run(mode, out, seed):
    ids = [x['identifier'] for x in seed['response']['response']['docs']]
    rows, requests_log, errors = [], [], []
    session = requests.Session()
    session.headers['User-Agent'] = UA
    start = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    def get(url, **kwargs):
        before = time.perf_counter()
        r = session.get(url, timeout=(15, 45), **kwargs)
        requests_log.append({'url': r.url, 'status': r.status_code,
                             'seconds': time.perf_counter()-before,
                             'decoded_body_bytes': len(r.content),
                             'redirects': len(r.history)})
        r.raise_for_status()
        return r
    driver = None
    startup_seconds = None
    try:
        if mode == 'api':
            query = 'identifier:(' + ' OR '.join('"' + x + '"' for x in ids) + ')'
            params = [('q', query), ('rows', len(ids)), ('output', 'json')]
            params += [('fl[]', x) for x in ['identifier','title','creator','year','subject','language','addeddate','imagecount']]
            docs = get('https://archive.org/advancedsearch.php', params=params).json()['response']['docs']
            time.sleep(DELAY)
            views = get('https://be-api.us.archive.org/views/v1/short/' + ','.join(ids)).json()
            by_id = {x['identifier']: x for x in docs}
            for identifier in ids:
                x = by_id[identifier]
                count = views[identifier]
                if not count.get('have_data'):
                    raise RuntimeError('Views unavailable for ' + identifier)
                rows.append(dict(identifier=identifier, title=clean(x.get('title','')),
                                 creators=values(x.get('creator',[])), publication_year=x.get('year'),
                                 subjects=values(x.get('subject',[])), language=','.join(values(x.get('language',[]))),
                                 addeddate=x.get('addeddate',''), scanned_page_count=x.get('imagecount'),
                                 views_all_time=count['all_time']))
        else:
            if mode == 'selenium':
                from selenium import webdriver
                from selenium.webdriver.chrome.service import Service
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.common.exceptions import TimeoutException
                options = webdriver.ChromeOptions()
                options.binary_location = '/home/mhmd2/chrome_for_testing/chrome-linux64/chrome'
                options.page_load_strategy = 'eager'
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--window-size=1150,850')
                options.add_argument('--user-agent=' + UA)
                driver = webdriver.Chrome(service=Service('/home/mhmd2/chrome_for_testing/chromedriver-linux64/chromedriver'), options=options)
                driver.set_page_load_timeout(40)
                startup_seconds = time.perf_counter()-start
            for i, identifier in enumerate(ids):
                url = 'https://archive.org/details/' + identifier
                if mode == 'bs4':
                    response = get(url)
                    html = response.text
                else:
                    before = time.perf_counter()
                    driver.get(url)
                    WebDriverWait(driver, 20).until(lambda d: d.find_elements('css selector', 'h1.item-title'))
                    html = driver.page_source
                    requests_log.append({'url': driver.current_url, 'seconds': time.perf_counter()-before,
                                         'kind': 'browser_navigation', 'note': 'Subresource requests/bytes not counted here'})
                (out / (mode + '_' + identifier + '.html')).write_text(html, encoding='utf-8')
                row = parse_html(html, identifier)
                if not row['title'] or row['views_all_time'] is None:
                    raise RuntimeError('Required title/views missing: ' + identifier)
                rows.append(row)
                print(mode, i+1, identifier, 'views', row['views_all_time'], flush=True)
                if i < len(ids)-1:
                    time.sleep(DELAY)
    except Exception as exc:
        errors.append({'type': type(exc).__name__, 'message': str(exc)})
    finally:
        if driver:
            driver.quit()
        seconds = time.perf_counter()-start
        save_rows(out / (mode + '.csv'), rows)
        (out / (mode + '.json')).write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')
        metrics = dict(method=mode, started_at=started_at, seconds=seconds,
                       records=len(rows), deliberate_delay_seconds=DELAY,
                       startup_seconds=startup_seconds, requests=requests_log, errors=errors)
        (out / (mode + '_metrics.json')).write_text(json.dumps(metrics, indent=2), encoding='utf-8')
        print(json.dumps({k:v for k,v in metrics.items() if k != 'requests'}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['api','bs4','selenium','all'], default='all')
    parser.add_argument('--seed', type=Path, default=ROOT/'archive_pilot_seed.json')
    parser.add_argument('--out', type=Path, default=ROOT/('archive_timed_pilot_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')))
    args = parser.parse_args()
    seed = json.loads(args.seed.read_text(encoding='utf-8'))
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(seed, indent=2), encoding='utf-8')
    for mode in (['api','bs4','selenium'] if args.mode == 'all' else [args.mode]):
        run(mode, out, seed)
        if args.mode == 'all' and mode != 'selenium':
            time.sleep(DELAY)
