"""Scoped recovery from the original ArchiveTeam JGram WARC backup.

Only indexed entry members are decompressed. Nearby members are coalesced into
bounded ranges, reducing request load; unrelated bytes in those ranges are not
interpreted or retained. This snapshot is distinct from latest Wayback selection.
"""

import base64
import gzip
import hashlib
import io
import json
import re
import time
import tempfile
from collections import defaultdict
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit, quote
from urllib.request import Request
from urllib.robotparser import RobotFileParser

from .archive import ArchiveAccessError, ArchiveFetcher, original_label
from .archive_parser import parse_archive, NotGrammar, LicenseReviewRequired
from .crawl import now
from .http import HttpxOpener, RequestPacer
from .storage import output_root, safe_target, write_json, cache_response, record_digest, read_archive_state

ITEM = 'archiveteam_archivebot_go_20150302130001'
WARC = 'jgram.org-inf-20150224-175105-5bi1u-00000.warc.gz'
INDEX = WARC.replace('.warc.gz', '.warc.os.cdx.gz')
SNAPSHOT = 'archivebot-2015-02'
MAX_MEMBER = 2 * 1024 * 1024


def allowed_dump_url(url):
    p = urlsplit(url)
    if (p.scheme != 'https' or p.username or p.password or p.port not in {None, 443} or
        not p.hostname or not (p.hostname == 'archive.org' or p.hostname.endswith('.archive.org')) or
        p.query or p.fragment):
        return False
    if p.path == '/robots.txt':
        return True
    match = re.fullmatch(r'/(?:download|\d+/items)/' + ITEM + r'/([^/]+)', p.path)
    return bool(match and match[1] in {WARC, INDEX})


class DumpFetcher:
    def __init__(self, directory, contact=None, offline=False):
        self.root = output_root(directory)
        self.offline = offline
        self.ua = 'takoboto-grammar-db/0.3 (JGram grammar backup recovery' + (f'; {contact}' if contact else '') + ')'
        self.pacer = RequestPacer(5, 3, 30)
        self.robots = {}
        self.download_urls = {}
        self.opener = HttpxOpener(allowed_dump_url, self.before_request, self.pacer.completed, 80 * 1024 * 1024)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        try:
            write_json(self.root, 'dump-request-report.json', {'finished_at': now(),
                       **self.pacer.settings(), 'attempts': self.opener.attempts})
        finally:
            self.opener.close()

    def before_request(self, url):
        if self.offline:
            raise ArchiveAccessError('Offline dump mode cannot make requests')
        cooldown = safe_target(self.root, 'access-cooldown.json')
        if cooldown.exists() and json.loads(cooldown.read_text())['until_epoch'] > time.time():
            raise ArchiveAccessError('Archive backup backoff is still active')
        p = urlsplit(url)
        origin = f'https://{p.netloc}'
        if p.path != '/robots.txt' and origin not in self.robots:
            body, meta = self.network(origin + '/robots.txt', policy=True)
            robots = RobotFileParser()
            robots.parse(body.decode('utf-8').splitlines())
            self.robots[origin] = robots
            self.pacer.delay = max(self.pacer.delay, robots.crawl_delay(self.ua) or 0)
            rate = robots.request_rate(self.ua)
            if rate:
                self.pacer.delay = max(self.pacer.delay, rate.seconds / rate.requests)
            write_json(self.root, f'dump-policies/{hashlib.sha256(origin.encode()).hexdigest()}.json',
                       {'origin': origin, 'robots': meta, 'checked_at': now(), **self.pacer.settings()})
        if origin in self.robots and not self.robots[origin].can_fetch(self.ua, url):
            raise ArchiveAccessError(f'Archive robots.txt disallows backup retrieval: {url}')
        self.pacer.wait()

    def network(self, url, start=None, length=None, policy=False):
        headers = {'User-Agent': self.ua, 'Accept-Encoding': 'identity'}
        if start is not None:
            headers['Range'] = f'bytes={start}-{start + length - 1}'
        try:
            with self.opener.open(Request(url, headers=headers), timeout=90) as r:
                if r.headers.get('Retry-After'):
                    ArchiveFetcher.stop_with_backoff(self, url, r.status, r.headers['Retry-After'])
                body = r.read()
                meta = {'url': url, 'final_url': r.url, 'status': r.status, 'retrieved_at': now(),
                        'sha256': hashlib.sha256(body).hexdigest(),
                        'content_range': r.headers.get('Content-Range')}
                return body, meta
        except HTTPError as exc:
            exc.close()
            if policy and exc.code in {404, 410}:
                return b'', {'url': url, 'status': exc.code, 'retrieved_at': now()}
            if exc.code in {401, 403, 429} or exc.code >= 500 or exc.headers.get('Retry-After'):
                ArchiveFetcher.stop_with_backoff(self, url, exc.code, exc.headers.get('Retry-After'))
            raise

    def get(self, filename, start=None, length=None):
        if filename not in {INDEX, WARC} or (filename == WARC and
            (type(start) is not int or start < 0 or type(length) is not int or not 0 < length <= 20 * 1024 * 1024)):
            raise ValueError('Backup retrieval requires a bounded indexed range')
        identity = f'{filename}:{start}:{length}'
        key = hashlib.sha256(identity.encode()).hexdigest()
        path = safe_target(self.root, f'cache/dump-requests/{key}.json')
        if path.exists():
            meta = json.loads(path.read_text())
            body = safe_target(self.root, f'cache/dump-responses/{meta["sha256"]}.bin').read_bytes()
            if meta.get('identity') != identity or hashlib.sha256(body).hexdigest() != meta['sha256']:
                raise ValueError('Corrupt backup range cache')
            return body, meta
        if self.offline:
            # Imported indices have the same independently checked evidence
            # cache as downloaded ones, even without transport cache metadata.
            if filename == INDEX:
                inventory = json.loads(safe_target(self.root, 'inventory.json').read_text())
                verify_dump_inventory(self.root, inventory)
                body = safe_target(self.root, f'cache/dump-index/{inventory["index_sha256"]}.gz').read_bytes()
                return body, inventory['pages'][0]
            raise ArchiveAccessError(f'Offline backup range is not cached: {identity}')
        url = self.download_urls.get(filename, f'https://archive.org/download/{ITEM}/{filename}')
        body, meta = self.network(url, start, length)
        if not allowed_dump_url(meta['final_url']) or not meta['final_url'].endswith('/' + filename):
            raise ValueError('Archive download redirected to a different backup file')
        self.download_urls[filename] = meta['final_url']
        meta.update(identity=identity, offset=start, length=length)
        if filename == INDEX:
            cache_response(self.root, f'cache/dump-responses/{meta["sha256"]}.bin', body)
            write_json(self.root, f'cache/dump-requests/{key}.json', meta)
        return body, meta


def parse_dump_index(compressed):
    captures, seen, rows, expanded = [], set(), 0, 0
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as file:
        header = file.readline(4096).split()
        if header != b'CDX N b a m s k r M S V g'.split():
            raise ValueError('Unexpected ArchiveTeam CDX header')
        while True:
            line = file.readline(65537)
            if not line:
                break
            rows += 1
            expanded += len(line)
            if len(line) > 65536 or rows > 2_000_000 or expanded > 2 * 1024 ** 3:
                raise ValueError('Backup index exceeds bounds')
            fields = line.decode('utf-8').split()
            if len(fields) != 11:
                raise ValueError('Malformed backup CDX row')
            _, timestamp, original, mimetype, status, digest, _, _, length, offset, filename = fields
            label = original_label(original)
            if label is None or status != '200' or mimetype != 'text/html':
                continue
            if (not re.fullmatch(r'\d{14}', timestamp) or not '20150224000000' <= timestamp <= '20150302235959' or
                not re.fullmatch(r'[A-Z2-7]{32}', digest) or filename != ITEM + '/' + WARC or
                not length.isdigit() or not offset.isdigit() or not 0 < int(length) <= MAX_MEMBER):
                raise ValueError('Invalid scoped backup member')
            archive_url = quote(f'https://web.archive.org/web/{timestamp}id_/{original}', safe="/:?=&;%+@!()*,-._~'")
            if archive_url in seen:
                continue
            seen.add(archive_url)
            captures.append({'label': label, 'timestamp': timestamp, 'original': original,
                'mimetype': mimetype, 'digest': digest, 'archive_url': archive_url,
                'warc_offset': int(offset), 'warc_length': int(length)})
    return captures, rows


def dump_inventory(compressed, metadata):
    captures, rows = parse_dump_index(compressed)
    grouped = defaultdict(list)
    for capture in captures:
        grouped[capture['label']].append(capture)
    return {'source': 'jgram-archivebot-snapshot', 'snapshot': SNAPSHOT, 'cdx_complete': True,
        'selection': 'Latest indexed observation within the February 24–March 2, 2015 ArchiveTeam backup; not the final live database',
        'discovered_at': now(), 'index_sha256': hashlib.sha256(compressed).hexdigest(),
        'pages': [metadata], 'index_rows': rows, 'capture_count': len(captures), 'label_count': len(grouped),
        'entries': [{'label': label, 'captures': sorted(found, key=lambda c: (c['timestamp'], c['original']), reverse=True)}
                    for label, found in sorted(grouped.items())]}


def range_groups(captures):
    groups = []
    for capture in sorted(captures, key=lambda c: c['warc_offset']):
        start = capture['warc_offset']
        end = start + capture['warc_length']
        if groups and start - groups[-1]['end'] <= 512 * 1024 and end - groups[-1]['start'] <= 20 * 1024 * 1024:
            groups[-1]['end'] = max(groups[-1]['end'], end)
            groups[-1]['captures'].append(capture)
        else:
            groups.append({'start': start, 'end': end, 'captures': [capture]})
    return groups


def member_body(compressed, capture):
    if len(compressed) != capture['warc_length']:
        raise ValueError('WARC compressed length differs from index')
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as file:
        raw = file.read(MAX_MEMBER + 1)
    if len(raw) > MAX_MEMBER:
        raise ValueError('WARC member exceeds decompression bound')
    header, block = raw.split(b'\r\n\r\n', 1)
    lines = header.decode('utf-8').split('\r\n')
    if lines[0] not in {'WARC/1.0', 'WARC/1.1'}:
        raise ValueError('Invalid WARC version')
    fields = dict(line.split(': ', 1) for line in lines[1:])
    if (fields['WARC-Type'] != 'response' or fields['WARC-Target-URI'] != capture['original'] or
        fields['WARC-Date'].replace('-', '').replace(':', '').replace('T', '').rstrip('Z') != capture['timestamp']):
        raise ValueError('WARC identity differs from index')
    size = int(fields['Content-Length'])
    if size < 0 or len(block) < size or block[size:].strip():
        raise ValueError('Invalid WARC block length')
    block = block[:size]
    if fields.get('WARC-Block-Digest') != 'sha1:' + base64.b32encode(hashlib.sha1(block).digest()).decode():
        raise ValueError('WARC block digest mismatch')
    headers, body = block.split(b'\r\n\r\n', 1)
    http_lines = headers.decode('latin-1').split('\r\n')
    if not re.fullmatch(r'HTTP/1\.[01] 200(?: .*)?', http_lines[0]):
        raise ValueError('WARC response is not successful HTML')
    http_fields = {k.lower(): v for k, v in (line.split(': ', 1) for line in http_lines[1:])}
    if 'transfer-encoding' in http_fields or 'content-encoding' in http_fields:
        raise ValueError('Encoded WARC entity requires review')
    if 'content-length' in http_fields and int(http_fields['content-length']) != len(body):
        raise ValueError('HTTP payload length mismatch')
    digest = base64.b32encode(hashlib.sha1(body).digest()).decode()
    if digest != capture['digest'] or fields.get('WARC-Payload-Digest') != 'sha1:' + digest:
        raise ValueError('WARC payload digest differs from index')
    return body


def verify_dump_record(root, record, inventory):
    if record.get('snapshot') != inventory.get('snapshot') or record['snapshot'] != SNAPSHOT:
        raise ValueError('Snapshot identity mismatch')
    item = next(i for i in inventory['entries'] if i['label'] == record['label'])
    capture = item['captures'][0]
    proof = record['retrieval']
    if (proof['method'] != 'archive-item-warc-range' or proof['index_sha256'] != inventory['index_sha256'] or
        proof['offset'] != capture['warc_offset'] or proof['length'] != capture['warc_length'] or
        not allowed_dump_url(proof['url']) or not proof['url'].endswith('/' + WARC)):
        raise ValueError('WARC retrieval provenance differs from indexed member')
    digest = proof['member_sha256']
    if not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('Invalid WARC member hash')
    path = root / 'cache/warc-members' / (digest + '.gz')
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('WARC evidence escapes snapshot directory')
    compressed = path.read_bytes()
    body = member_body(compressed, capture)
    if hashlib.sha256(compressed).hexdigest() != digest or hashlib.sha256(body).hexdigest() != record['response_sha256']:
        raise ValueError('WARC evidence hash mismatch')


def verify_dump_inventory(root, inventory):
    digest = inventory['index_sha256']
    if not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('Invalid backup index hash')
    path = root / 'cache/dump-index' / (digest + '.gz')
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('Backup index evidence escapes snapshot directory')
    compressed = path.read_bytes()
    if hashlib.sha256(compressed).hexdigest() != digest:
        raise ValueError('Backup index evidence hash mismatch')
    expected = dump_inventory(compressed, inventory['pages'][0])
    if any(inventory.get(key) != expected[key] for key in
           ('snapshot', 'source', 'cdx_complete', 'index_rows', 'capture_count', 'label_count', 'entries')):
        raise ValueError('Snapshot inventory differs from original backup index')


def crawl_dump(fetcher, inventory, eligible_ids=(), labels=None, limit=None):
    entries = [i for i in inventory['entries'] if labels is None or i['label'] in labels]
    if labels and set(labels) - {i['label'] for i in entries}:
        raise ValueError('Requested label absent from backup index')
    if limit:
        entries = entries[:limit]
    groups = range_groups([i['captures'][0] for i in entries])
    report = {'snapshot': SNAPSHOT, 'selected_labels': len(entries), 'indexed_labels': inventory['label_count'],
        'range_count': len(groups), 'range_bytes': sum(g['end'] - g['start'] for g in groups),
        'parsed': [], 'excluded': [], 'review_required': [], 'failed': [], 'complete': False}
    try:
        for index, group in enumerate(groups, 1):
            cached = {}
            for capture in group['captures']:
                state = read_archive_state(fetcher.root, capture['label'])
                if state and state.get('capture') == capture and state.get('member_sha256'):
                    member_hash = state['member_sha256']
                    if not re.fullmatch(r'[0-9a-f]{64}', member_hash):
                        raise ValueError('Invalid cached WARC member hash')
                    member = safe_target(fetcher.root, f'cache/warc-members/{member_hash}.gz').read_bytes()
                    if hashlib.sha256(member).hexdigest() != member_hash:
                        raise ValueError('Corrupt cached WARC member')
                    cached[capture['label']] = (member, {'final_url': state['retrieval_url'],
                                                        'retrieved_at': state['retrieved_at']})
            chunk = None
            if len(cached) != len(group['captures']):
                chunk, range_meta = fetcher.get(WARC, group['start'], group['end'] - group['start'])
            for capture in group['captures']:
                label = capture['label']
                key = hashlib.sha256(label.encode()).hexdigest()
                state = {'label': label, 'status': 'pending', 'checked_at': now(),
                    'latest_indexed_timestamp': capture['timestamp'], 'capture': capture, 'eligible_ids': list(eligible_ids)}
                write_json(fetcher.root, f'states/{key}.json', state)
                try:
                    if label in cached:
                        compressed, meta = cached[label]
                    else:
                        offset = capture['warc_offset'] - group['start']
                        compressed = chunk[offset:offset + capture['warc_length']]
                        meta = range_meta
                    body = member_body(compressed, capture)
                    digest = hashlib.sha256(body).hexdigest()
                    member_hash = hashlib.sha256(compressed).hexdigest()
                    cache_response(fetcher.root, f'cache/warc-members/{member_hash}.gz', compressed)
                    cache_response(fetcher.root, f'cache/responses/{digest}.bin', body)
                    state.update(response_sha256=digest, retrieved_at=meta['retrieved_at'],
                                 member_sha256=member_hash, retrieval_url=meta['final_url'])
                    record = parse_archive(body, capture, meta['retrieved_at'], eligible_ids)
                    record.update(snapshot=SNAPSHOT, latest_indexed_timestamp=capture['timestamp'], selection_attempts=[],
                        retrieval={'method': 'archive-item-warc-range', 'url': meta['final_url'],
                            'offset': capture['warc_offset'], 'length': capture['warc_length'],
                            'index_sha256': inventory['index_sha256'], 'member_sha256': member_hash})
                    state.update(status='review_required' if record['warnings'] else 'parsed', record_sha256=record_digest(record))
                    folder = 'review-records' if record['warnings'] else 'records'
                    write_json(fetcher.root, f'{folder}/{key}.json', record)
                    if record['warnings']:
                        old = safe_target(fetcher.root, f'records/{key}.json')
                        if old.exists():
                            trash = output_root(Path.home() / '.Trash')
                            destination = Path(tempfile.mkdtemp(prefix='jgram-held-record-', dir=trash))
                            old.replace(safe_target(destination, old.name))
                    report['review_required' if record['warnings'] else 'parsed'].append({'label': label, 'id': record['id']})
                except NotGrammar as exc:
                    state.update(status='excluded', reason=str(exc))
                    report['excluded'].append({'label': label, 'reason': str(exc)})
                except (ValueError, KeyError) as exc:
                    state.update(status='review_required', reason=str(exc))
                    report['review_required'].append({'label': label, 'reason': str(exc)})
                finally:
                    state['checked_at'] = now()
                    write_json(fetcher.root, f'states/{key}.json', state)
            print(f"Backup range {index}/{len(groups)}: {len(group['captures'])} indexed labels; {len(report['parsed'])} grammar observations", flush=True)
            write_json(fetcher.root, 'dump-crawl-report.json', report)
    except (ArchiveAccessError, HTTPError, OSError, ValueError) as exc:
        report['failed'].append({'error': str(exc)})
        report['stopped_reason'] = str(exc)
    report['finished_at'] = now()
    report['complete'] = (len(entries) == inventory['label_count'] and not report['review_required'] and not report['failed'] and
                          len(report['parsed']) + len(report['excluded']) == len(entries))
    write_json(fetcher.root, 'dump-crawl-report.json', report)
    return report
