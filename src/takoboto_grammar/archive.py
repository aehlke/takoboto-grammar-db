"""Polite, cached Wayback CDX discovery and JGram replay retrieval.

One request at a time; five seconds between request starts by default. No Save
Page Now calls, proxy rotation, authentication, or live-origin fallbacks.
"""

import hashlib
import base64
import json
import re
import time
from uuid import uuid4
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from urllib.request import Request
from urllib.robotparser import RobotFileParser

from .archive_parser import NotGrammar, LicenseReviewRequired, parse_archive
from .crawl import now
from .parser import ParseError
from .storage import output_root, safe_target, write_json, write_record, cache_response, record_digest, annotate_archive_record
from .http import HttpxOpener, RequestPacer

CDX = 'https://web.archive.org/cdx/search/cdx'
GRAMMAR_FEEDS = tuple('/rss/' + name + '.xml' for name in ('updates', 'jlpt1', 'jlpt2', 'jlpt3', 'jlpt4'))


class ArchiveAccessError(RuntimeError):
    pass


def original_label(url):
    p = urlsplit(url)
    if p.scheme not in {'http', 'https'} or p.hostname not in {'jgram.org', 'www.jgram.org'}:
        return None
    if p.port not in {None, 80, 443} or p.path.lower() != '/pages/viewone.php' or p.fragment:
        return None
    q = parse_qs(p.query, keep_blank_values=True)
    if 'tagE' not in q or set(q) - {'tagE', 'date'} or len(q['tagE']) != 1 or not q['tagE'][0]:
        return None
    if 'date' in q and (len(q['date']) != 1 or not re.fullmatch(r'\d{4}-\d{1,2}-\d{1,2}', q['date'][0])):
        return None
    return q['tagE'][0]


def allowed_archive_url(url):
    p = urlsplit(url)
    if p.scheme != 'https' or p.netloc != 'web.archive.org' or p.fragment:
        return False
    if p.path == '/robots.txt':
        return not p.query
    if p.path == '/cdx/search/cdx':
        q = parse_qs(p.query)
        return (q.get('url') in [['jgram.org/pages/viewOne.php']] + [['jgram.org' + path] for path in GRAMMAR_FEEDS]
                and not set(q) - {'url', 'matchType', 'output', 'filter', 'fl', 'showResumeKey', 'limit', 'resumeKey', 'resolveRevisits'})
    match = re.fullmatch(r'/web/(\d{14})(?:id_)?/(https?://.*)', p.path + ('?' + p.query if p.query else ''))
    if not match:
        return False
    original = urlsplit(match[2])
    feed = (original.scheme in {'http', 'https'} and original.hostname in {'jgram.org', 'www.jgram.org'}
        and original.port in {None, 80, 443} and original.path in GRAMMAR_FEEDS and not original.query and not original.fragment)
    return original_label(match[2]) is not None or feed


class ArchiveFetcher:
    def __init__(self, directory, delay=5, contact=None, refresh=False, offline=False, burst_size=3, burst_pause=30):
        if delay < 3:
            raise ValueError('Archive delay must be at least three seconds; default is five')
        self.pacer = RequestPacer(delay, burst_size, burst_pause)
        self.root = output_root(directory)
        self.delay, self.refresh = delay, refresh
        self.offline = offline
        if offline and refresh:
            raise ValueError('Offline mode cannot refresh responses')
        self.ua = 'takoboto-grammar-db/0.2 (JGram public grammar preservation' + (f'; {contact}' if contact else '') + ')'
        self.opener = HttpxOpener(allowed_archive_url, self.before_request, self.pacer.completed, 20 * 1024 * 1024,
                                 on_retry_after=self.stop_with_backoff)
        self.run_id = uuid4().hex
        self.robots = None
        self.policy_checked = False
    def __enter__(self):
        return self

    def __exit__(self, *args):
        try:
            report = {'run_id': self.run_id, 'finished_at': now(), **self.pacer.settings(),
                      'attempt_count': len(self.opener.attempts), 'attempts': self.opener.attempts}
            write_json(self.root, f'request-reports/{self.run_id}.json', report)
            write_json(self.root, 'request-report.json', report)
        finally:
            self.opener.close()

    def before_request(self, url):
        if url != 'https://web.archive.org/robots.txt' and not self.policy_checked:
            raise ArchiveAccessError('Call check_access() before online archive retrieval')
        if self.robots and not self.robots.can_fetch(self.ua, url):
            raise ArchiveAccessError(f'Archive robots.txt disallows: {url}')
        self.pacer.delay = self.delay
        self.pacer.wait()

    def stop_with_backoff(self, url, status, retry_after=None, minimum=300):
        wait = minimum
        if retry_after:
            try:
                wait = max(wait, int(retry_after) if retry_after.isdigit() else
                    (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError, OverflowError):
                pass
        write_json(self.root, 'access-cooldown.json', {'until_epoch': time.time() + wait,
            'reason': f'HTTP {status}', 'url': url, 'recorded_at': now()})
        raise ArchiveAccessError(f'Archive returned HTTP {status}; stopped with persisted backoff')

    def get(self, url, policy=False):
        if policy and url != 'https://web.archive.org/robots.txt':
            raise ArchiveAccessError('Policy retrieval is restricted to robots.txt')
        if not allowed_archive_url(url):
            raise ArchiveAccessError(f'Out-of-scope archive URL: {url}')
        key = hashlib.sha256(url.encode()).hexdigest()
        path = safe_target(self.root, f'cache/urls/{key}.json')
        if path.exists() and not self.refresh and not policy:
            meta = json.loads(path.read_text(encoding='utf-8'))
            body = safe_target(self.root, f'cache/responses/{meta["sha256"]}.bin').read_bytes()
            if meta['url'] != url or hashlib.sha256(body).hexdigest() != meta['sha256']:
                raise ArchiveAccessError(f'Corrupt archive cache: {url}')
            return body, meta
        if self.offline:
            raise ArchiveAccessError(f'Offline mode: response not cached: {url}')
        if not policy and not self.policy_checked:
            raise ArchiveAccessError('Call check_access() before online archive retrieval')
        if self.robots and not self.robots.can_fetch(self.ua, url):
            raise ArchiveAccessError(f'Archive robots.txt disallows: {url}')
        cooldown = safe_target(self.root, 'access-cooldown.json')
        if cooldown.exists():
            until = json.loads(cooldown.read_text())['until_epoch']
            if until > time.time():
                raise ArchiveAccessError('Archive backoff is still active; resume after access-cooldown.json time')
        for attempt in range(3):
            try:
                with self.opener.open(Request(url, headers={'User-Agent': self.ua}), timeout=45) as response:
                    body = response.read(20 * 1024 * 1024 + 1)
                    if len(body) > 20 * 1024 * 1024:
                        raise ArchiveAccessError('Response exceeds 20 MiB; stop rather than truncate')
                    meta = {'url': url, 'final_url': response.url, 'status': response.status,
                        'retrieved_at': now(), 'sha256': hashlib.sha256(body).hexdigest(),
                        'headers': {k: v for k, v in response.headers.items() if k.lower() in
                            {'date', 'content-type', 'memento-datetime', 'x-archive-src', 'x-archive-orig-date', 'x-archive-orig-content-type'}}}
                break
            except HTTPError as exc:
                exc.close()
                if policy and exc.code in {404, 410}:
                    # Missing robots.txt imposes no rules; server errors never imply permission.
                    body = b''
                    meta = {'url': url, 'status': exc.code, 'retrieved_at': now(), 'sha256': hashlib.sha256(body).hexdigest(),
                            'policy': 'robots.txt unavailable with 404/410; no advertised restrictions'}
                    break
                if exc.code in {401, 403, 429}:
                    self.stop_with_backoff(url, exc.code, exc.headers.get('Retry-After'))
                if 500 <= exc.code <= 599 and exc.headers.get('Retry-After'):
                    self.stop_with_backoff(url, exc.code, exc.headers['Retry-After'])
                if 500 <= exc.code <= 599 and attempt == 2:
                    self.stop_with_backoff(url, exc.code)
                if exc.code not in {500, 502, 503, 504} or attempt == 2:
                    raise
                time.sleep(10 * (attempt + 1))
            except (URLError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(10 * (attempt + 1))
        cache_response(self.root, f'cache/responses/{meta["sha256"]}.bin', body)
        write_json(self.root, f'cache/urls/{key}.json', meta)
        stamp = meta['retrieved_at'].replace(':', '-')
        write_json(self.root, f'cache/snapshots/{key}/{stamp}-{meta["sha256"]}.json', meta)
        return body, meta

    def check_access(self):
        if self.offline:
            return
        body, meta = self.get('https://web.archive.org/robots.txt', policy=True)
        self.robots = RobotFileParser()
        self.robots.parse(body.decode('utf-8').splitlines())
        self.policy_checked = True
        delay = self.robots.crawl_delay(self.ua)
        if delay:
            self.delay = max(self.delay, delay)
        rate = self.robots.request_rate(self.ua)
        if rate:
            self.delay = max(self.delay, rate.seconds / rate.requests)
        self.pacer.delay = self.delay
        write_json(self.root, 'access-policy.json', {'checked_at': now(), 'robots': meta,
            **self.pacer.settings(),
            'cdx_documentation': 'https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server',
            'requests': 'GET only; no Save Page Now; no origin fallback; stop on 401/403/429, server Retry-After, exhausted server retries'})


def parse_cdx(body):
    rows = json.loads(body.decode('utf-8'))
    if not rows:
        return [], None
    header = rows[0]
    if not isinstance(header, list) or not {'timestamp', 'original', 'mimetype', 'digest'}.issubset(header):
        raise ParseError('Unexpected CDX fields')
    captures, resume = [], None
    for row in rows[1:]:
        if not row:
            continue
        if len(row) == 1:
            if resume is not None:
                raise ParseError('Multiple CDX resume keys')
            resume = row[0]
            continue
        if len(row) != len(header):
            raise ParseError('Malformed CDX row')
        item = dict(zip(header, row))
        if not re.fullmatch(r'\d{14}', item['timestamp']):
            raise ParseError('Malformed CDX timestamp')
        label = original_label(item['original'])
        if label is not None and item['mimetype'] in {'text/html', 'warc/revisit'}:
            item['label'] = label
            item['archive_url'] = quote(f"https://web.archive.org/web/{item['timestamp']}id_/{item['original']}", safe="/:?=&;%+@!()*,-._~'")
            captures.append(item)
    return captures, resume


def discover_archive(fetcher):
    base = [('url', 'jgram.org/pages/viewOne.php'), ('matchType', 'prefix'), ('output', 'json'),
            ('filter', 'statuscode:200'), ('fl', 'timestamp,original,mimetype,digest'),
            ('showResumeKey', 'true'), ('limit', '10000')]
    captures, pages, resume, visited = [], [], None, set()
    while True:
        url = CDX + '?' + urlencode(base + ([('resumeKey', resume)] if resume else []))
        body, meta = fetcher.get(url)
        found, next_resume = parse_cdx(body)
        captures.extend(found)
        pages.append({'url': url, 'sha256': meta['sha256'], 'retrieved_at': meta['retrieved_at'], 'accepted_captures': len(found)})
        print(f'CDX page {len(pages)}: {len(found)} usable captures', flush=True)
        if next_resume is None:
            break
        if next_resume in visited:
            raise ParseError('CDX resumption loop')
        visited.add(next_resume)
        resume = next_resume
    labels = {}
    for capture in captures:
        labels.setdefault(capture['label'], []).append(capture)
    entries = []
    for label, rows in sorted(labels.items()):
        # Keep the latest timestamp of each body digest for fallback; unlike CDX
        # collapse=urlkey/digest this does not accidentally select an earliest capture.
        unique, alternates = {}, []
        for row in sorted(rows, key=lambda r: (r['timestamp'], r['original']), reverse=True):
            key = row['digest'] if row['digest'] != '-' else row['archive_url']
            if key in unique:
                alternates.append(row)
            else:
                unique[key] = row
        entries.append({'label': label, 'captures': list(unique.values()), 'alternate_captures': alternates})
    inventory = {'source': 'jgram-wayback', 'discovered_at': now(), 'cdx_complete': True,
                 'selection': 'latest available successful JGram grammar page per canonical tagE label',
                 'pages': pages, 'capture_count': len(captures), 'label_count': len(entries), 'entries': entries}
    write_json(fetcher.root, 'inventory.json', inventory)
    return inventory


def replay_candidates(item):
    """Try up to three observations of each of three distinct revisions."""
    for primary in item['captures'][:3]:
        yield primary
        if re.fullmatch(r'[A-Z2-7]{32}', primary.get('digest') or ''):
            matching = [row for row in item.get('alternate_captures', [])
                        if row['digest'] == primary['digest']]
            yield from sorted(matching, key=lambda r: (r['timestamp'], r['original']), reverse=True)[:2]


def latest_body_equivalent(body, capture, item):
    """Prove payload identity using both indexed membership and raw SHA-1.

    CDX timestamps alone do not establish equivalence. Unknown digests and
    unindexed redirect destinations cannot satisfy this check.
    """
    latest = item['captures'][0]
    digest = latest.get('digest') or ''
    if not re.fullmatch(r'[A-Z2-7]{32}', digest):
        return False
    indexed = item['captures'] + item.get('alternate_captures', [])
    return (base64.b32encode(hashlib.sha1(body).digest()).decode() == digest and
            any(row.get('digest') == digest and all(row.get(key) == capture.get(key)
                for key in ('label', 'timestamp', 'original', 'archive_url')) for row in indexed))


def crawl_archive(fetcher, inventory, eligible_ids=(), limit=None):
    eligible_ids = tuple(eligible_ids)
    entries = inventory['entries'][:limit] if limit else inventory['entries']
    report = {'started_at': now(), 'selected_labels': len(entries), 'indexed_labels': inventory['label_count'],
              'parsed': [], 'excluded': [], 'review_required': [], 'failed': [], 'warnings': [], 'complete': False}
    consecutive_failures = 0
    for index, item in enumerate(entries, 1):
        label, attempts = item['label'], []
        key = hashlib.sha256(label.encode()).hexdigest()
        state = {'label': label, 'status': 'pending', 'checked_at': now(),
                 'latest_indexed_timestamp': item['captures'][0]['timestamp'],
                 'eligible_ids': list(eligible_ids)}
        # A pending hold prevents an interrupted refresh from exporting an older record.
        write_json(fetcher.root, f'states/{key}.json', state)
        try:
            for candidate in replay_candidates(item):
                try:
                    body, meta = fetcher.get(candidate['archive_url'])
                    # Wayback can redirect to a different capture. Preserve actual time.
                    actual = dict(candidate)
                    replay = re.search(r'/web/(\d{14})', meta.get('final_url', candidate['archive_url']))
                    if replay:
                        actual['timestamp'] = replay[1]
                        actual['archive_url'] = meta.get('final_url', candidate['archive_url'])
                    final_original = re.sub(r'^https://web\.archive\.org/web/\d{14}(?:id_)?/', '', actual['archive_url'])
                    if original_label(final_original) != label:
                        raise ParseError('Replay redirected to a different JGram label')
                    actual['original'] = final_original
                    indexed = item['captures'] + item.get('alternate_captures', [])
                    actual['digest'] = next((row.get('digest') for row in indexed
                        if row['archive_url'] == actual['archive_url']), None)
                    digest = hashlib.sha256(body).hexdigest()
                    cache_response(fetcher.root, f'cache/responses/{digest}.bin', body)
                    state.update(capture=actual, requested_timestamp=candidate['timestamp'],
                                 response_sha256=digest, retrieved_at=meta['retrieved_at'])
                    equivalent = latest_body_equivalent(body, actual, item)
                    record = parse_archive(body, actual, meta['retrieved_at'], eligible_ids)
                    if attempts and not equivalent:
                        record['warnings'].append('Used older capture after latest replay failed; inspect selection_attempts')
                    if actual['timestamp'] != candidate['timestamp'] and not equivalent:
                        record['warnings'].append('Replay redirected to a different capture timestamp')
                    annotate_archive_record(record, selection_attempts=attempts,
                                            latest_indexed_timestamp=item['captures'][0]['timestamp'])
                    folder = 'review-records' if record['warnings'] else 'records'
                    write_record(fetcher.root, f'{folder}/{key}.yaml', record)
                    state.update(status='review_required' if record['warnings'] else 'parsed',
                                 record_sha256=record_digest(record))
                    if record['warnings']:
                        state['reason'] = 'Historical extraction has warnings; inspect retained record'
                        report['review_required'].append({'label': label, 'reason': state['reason'],
                                                          'archive_url': record['archive_url']})
                    report['parsed'].append({'label': label, 'id': record['id'], 'archive_timestamp': record['archive_timestamp'], 'key': key})
                    report['warnings'].extend({'label': label, 'warning': w} for w in record['warnings'])
                    print(f"[{index}/{len(entries)}] {label}: {len(record['notes'])} notes, {len(record['examples'])} examples, {len(record['comments'])} comments ({record['archive_timestamp']})", flush=True)
                    consecutive_failures = 0
                    break
                except LicenseReviewRequired as exc:
                    state.update(status='review_required', reason=str(exc))
                    report['review_required'].append({'label': label, 'reason': str(exc), 'archive_url': candidate['archive_url']})
                    consecutive_failures = 0
                    break
                except NotGrammar as exc:
                    held = ((attempts or actual['timestamp'] != item['captures'][0]['timestamp']) and not equivalent)
                    status = 'review_required' if held else 'excluded'
                    reason = 'Older non-grammar observation does not establish latest scope' if held else str(exc)
                    state.update(status=status, reason=reason)
                    report[status].append({'label': label, 'reason': reason, 'archive_url': actual['archive_url']})
                    consecutive_failures = 0
                    break
                except (ParseError, HTTPError) as exc:
                    attempts.append({'archive_url': candidate['archive_url'], 'error': str(exc)})
                    if isinstance(exc, HTTPError):
                        exc.close()
            else:
                report['failed'].append({'label': label, 'attempts': attempts})
                consecutive_failures += 1
            if consecutive_failures >= 3:
                report['stopped_reason'] = 'Three consecutive replay failures; inspect before resuming'
                break
        except (ArchiveAccessError, URLError, TimeoutError) as exc:
            report['failed'].append({'label': label, 'error': str(exc)})
            report['stopped_reason'] = str(exc)
            break
        except Exception as exc:
            report['failed'].append({'label': label, 'error': f'{type(exc).__name__}: {exc}'})
            report['stopped_reason'] = 'Unexpected error; inspect before resuming'
            raise
        finally:
            if state['status'] == 'pending':
                state['status'] = 'failed'
            state['selection_attempts'] = attempts
            state['checked_at'] = now()
            write_json(fetcher.root, f'states/{key}.json', state)
            write_json(fetcher.root, 'crawl-report.json', report)
    report['finished_at'] = now()
    report['complete'] = (inventory.get('cdx_complete') is True and limit is None and len(entries) == inventory['label_count'] and not report['failed'] and not report['warnings'] and not report['review_required']
        and len(report['parsed']) + len(report['excluded']) == len(entries))
    write_json(fetcher.root, 'crawl-report.json', report)
    return report
