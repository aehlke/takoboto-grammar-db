"""Offline checks of captured JGram contributions and explicit historical coverage."""

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup

from .parser import text, parse_entry
from .crawl import now
from .archive_parser import NotGrammar, parse_archive, source_soup
from .archive import original_label, allowed_archive_url, latest_body_equivalent
from .storage import read_records, read_archive_records, read_archive_feeds, read_archive_state, read_feed_state, record_digest, write_json, expand_archive_records, annotate_archive_record
from .archive_feeds import parse_feed


def cached_body(root, digest, extension='.bin'):
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('Invalid response hash')
    path = root / 'cache/responses' / (digest + extension)
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('Cached response path escapes archive directory')
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != digest:
        raise ValueError('Response hash mismatch')
    return body


def verified_current_records(directory):
    if directory is None:
        return []
    root = Path(directory).expanduser().resolve(strict=True)
    records = read_records(root, for_export=True)
    for record in records:
        body = cached_body(root, record['response_sha256'], '.html')
        expected = parse_entry(body, record['id'], record['retrieved_at'], record['response_sha256'])
        if expected != record or expected['warnings']:
            raise ValueError(f"Current membership record is not source-verified: {record['id']}")
    return records


def legacy_holds(root, filename, field):
    path = root / filename
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError(f'Unexpected legacy report path: {path}')
    if not path.exists():
        return {}
    report = json.loads(path.read_text(encoding='utf-8'))
    return {item[field]: status for status in ('review_required', 'failed', 'excluded')
            for item in report.get(status, []) if field in item}


def check_latest_cached_response(root, url, digest, final_url):
    key = hashlib.sha256(url.encode()).hexdigest()
    path = root / 'cache/urls' / f'{key}.json'
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('Unexpected cached URL metadata path')
    if not path.exists():
        raise ValueError('Latest cached URL metadata is missing; reparse the cached source with the crawler')
    metadata = json.loads(path.read_text(encoding='utf-8'))
    if (metadata['url'] != url or metadata['sha256'] != digest or
        metadata.get('final_url', url) != final_url):
        raise ValueError('Record differs from latest cached response; inspect the newer observation before migration')


def verify_entry_replay(capture, label):
    if original_label(capture['original']) != label or not allowed_archive_url(capture['archive_url']):
        raise ValueError('Historical source URL does not match label or scope')
    replay = re.fullmatch(r'https://web\.archive\.org/web/(\d{14})(?:id_)?/(.*)', capture['archive_url'])
    original = quote(capture['original'], safe="/:?=&;%+@!()*,-._~'")
    if not replay or replay[1] != capture['timestamp'] or replay[2] != original:
        raise ValueError('Historical replay URL, timestamp and original URL disagree')


def audit_entry_content(soup, record, report, counts, categories):
    label = record['label']
    headings = {text(h).strip(' \u00a0:'): h for h in soup.select('.titleSection')}
    categories[record['category'] or 'unclassified; verified current ID'] += 1
    report['warnings'].extend({'label': label, 'warning': w} for w in record['warnings'])
    for kind, heading_name, content_column in [('notes', 'Notes', 0), ('comments', 'Comments', 1)]:
        heading = headings.get(heading_name)
        rows = []
        if heading:
            for row in heading.find_parent('table').find_all('tr', recursive=False):
                cells = row.find_all('td', recursive=False)
                if len(cells) > 1 and any('bottom' in cls for cell in cells for cls in cell.get('class', [])):
                    rows.append(cells)
        if len(rows) != len(record[kind]):
            report['errors'].append({'label': label, 'error': f'{kind} count mismatch: source {len(rows)}, extracted {len(record[kind])}'})
        for cells, extracted in zip(rows, record[kind]):
            source = cells[content_column]
            author_node = (cells[1].select_one('a[href*="contributions.php"]') if kind == 'notes' else cells[0])
            if text(source) != extracted['text'] or (text(author_node) or None) != extracted['credits_raw']:
                report['errors'].append({'label': label, 'error': f'{kind} text or credit mismatch at position {extracted["position"]}'})
            for asset in source.select('img,object,iframe,audio,video'):
                report['content_assets'].append({'label': label, 'html': str(asset)})
        counts[kind] += len(record[kind])
    anchors = [a for a in soup.select('a[name]') if a['name'].isdigit() and re.search(r'ex\s*#', text(a), re.I)]
    if len(anchors) != len(record['examples']):
        report['errors'].append({'label': label, 'error': 'Example count mismatch'})
    for anchor, extracted in zip(anchors, record['examples']):
        cells = anchor.find_parent('tr').find_all('td', recursive=False)
        if (len(cells) != 3 or int(anchor['name']) != extracted['source_id'] or
            text(cells[1]) != extracted['body_text'] or
            (text(cells[2].select_one('a[href*="contributions.php"]')) or None) != extracted['credits_raw']):
            report['errors'].append({'label': label, 'error': f'Example body, ID or credits mismatch: {anchor["name"]}'})
        if len(cells) > 1:
            for asset in cells[1].select('img,object,iframe,audio,video'):
                report['content_assets'].append({'label': label, 'html': str(asset)})
    counts['examples'] += len(record['examples'])
    see = headings.get('See Also')
    links = []
    if see:
        # Each list item is one relation. Annotation prose can link the
        # same or another entry again; malformed old HTML nests <li>s.
        owners = set()
        for link in see.parent.select('li a[href]'):
            if 'viewOne.php' in link['href']:
                owner = id(link.find_parent('li'))
                if owner not in owners:
                    owners.add(owner)
                    links.append(link)
    if len(links) != len(record['related_entries']):
        report['errors'].append({'label': label, 'error': 'Annotated relationship count mismatch'})
    counts['relationships'] += len(record['related_entries'])
    for node in soup.select('time,[datetime],[data-date],[data-timestamp]'):
        report['date_metadata'].append({'label': label, 'html': str(node)})


def audit_archive(directory, takoboto=None, record_verification=False):
    original = Path(directory).expanduser()
    if record_verification and original.is_symlink():
        raise ValueError(f'Archive verification directory is a symlink: {original}')
    root = Path(directory).expanduser().resolve(strict=True)
    current = verified_current_records(takoboto)
    eligible_ids = {record['id'] for record in current}
    verified_labels = {record['romanized_label']: record['id'] for record in current}
    membership = [{'id': r['id'], 'response_sha256': r['response_sha256']} for r in current]
    membership_digest = record_digest(membership) if takoboto is not None else None
    inventory = json.loads((root / 'inventory.json').read_text(encoding='utf-8'))
    if inventory.get('snapshot'):
        from .archive_dump import verify_dump_inventory
        verify_dump_inventory(root, inventory)
    records = read_archive_records(root, for_export=False)
    indexed = {item['label'] for item in inventory['entries']}
    latest = {item['label']: item['captures'][0]['timestamp'] for item in inventory['entries'] if item.get('captures')}
    latest_urls = {item['label']: item['captures'][0]['archive_url'] for item in inventory['entries'] if item.get('captures')}
    indexed_entries = {item['label']: item for item in inventory['entries']}
    report = {'indexed_labels': len(indexed), 'captured_entries': len(records),
        'pending_labels': sorted(indexed - {r['label'] for r in records}),
        'errors': [], 'warnings': [], 'content_assets': [], 'date_metadata': [],
        'verified_exclusions': [], 'blocked_records': [],
        'unverified_records': [], 'verification_states_written': {'entries': 0, 'feeds': 0},
        'current_membership': {'verified_entries': len(current), 'evidence_sha256': membership_digest},
        'counts': {}, 'categories': {}, 'parsed_records_verified': False,
        'historical_coverage_complete': False}
    counts, categories = Counter(), Counter()
    record_holds = legacy_holds(root, 'crawl-report.json', 'label')
    feed_holds = legacy_holds(root, 'feed-crawl-report.json', 'path')
    entry_states, feed_states = [], []
    for record in records:
        label = record['label']
        state = read_archive_state(root, label)
        if state and (state['status'] != 'parsed' or state.get('response_sha256') != record['response_sha256']
                      or state.get('capture', {}).get('archive_url') != record['archive_url']):
            report['blocked_records'].append({'label': label, 'status': state['status']})
        elif not state and label in record_holds:
            report['blocked_records'].append({'label': label, 'status': record_holds[label]})
        if not state or state.get('record_sha256') != record_digest(record):
            report['unverified_records'].append(label)
        if label not in indexed:
            report['warnings'].append({'label': label, 'warning': 'Stored label absent from current inventory'})
        if label in latest and record.get('latest_indexed_timestamp') != latest[label]:
            report['warnings'].append({'label': label, 'warning': 'Stored record has not been checked against the latest indexed capture'})
        try:
            body = cached_body(root, record['response_sha256'])
            capture = {'label': label, 'original': record['source_url'], 'archive_url': record['archive_url'],
                       'timestamp': record['archive_timestamp'], 'digest': record.get('archive_digest')}
            verify_entry_replay(capture, label)
            if inventory.get('snapshot') or record.get('snapshot'):
                from .archive_dump import verify_dump_record
                verify_dump_record(root, record, inventory)
            if label in latest and record['archive_timestamp'] != latest[label]:
                if not latest_body_equivalent(body, capture, indexed_entries[label]):
                    report['warnings'].append({'label': label, 'warning': 'Stored replay is not the latest indexed content'})
            expected = parse_archive(body, capture, record['retrieved_at'], eligible_ids)
            if expected.get('additional_entries'):
                annotate_archive_record(expected, **{key: record[key] for key in
                    ('snapshot', 'retrieval', 'latest_indexed_timestamp', 'selection_attempts') if key in record})
            if any(warning not in record['warnings'] for warning in expected['warnings']):
                report['errors'].append({'label': label, 'error': 'Stored record omits source parser warnings'})
            mismatches = [key for key, value in expected.items() if key != 'warnings' and record.get(key) != value]
            if mismatches:
                report['errors'].append({'label': label, 'error': 'Stored extraction differs from source', 'fields': mismatches})
                continue
            if not any(item['label'] == label for item in report['blocked_records']) and not record['warnings']:
                verified_labels.setdefault(label, record['id'])
            if not state or state.get('record_sha256') != record_digest(record):
                if record_verification:
                    if not inventory.get('snapshot'):
                        check_latest_cached_response(root, record['archive_url'], record['response_sha256'], record['archive_url'])
                preserved_capture = capture
                if state and all(state.get('capture', {}).get(key) == capture.get(key) for key in
                                 ('label', 'original', 'archive_url', 'timestamp')):
                    preserved_capture = state['capture']
                entry_states.append((label, dict(state or {}) | {'label': label, 'status': 'parsed', 'checked_at': now(),
                    'verification': 'offline-source-audit', 'current_membership_sha256': membership_digest,
                    'latest_indexed_timestamp': latest.get(label), 'eligible_ids': sorted(eligible_ids),
                    'capture': preserved_capture, 'response_sha256': record['response_sha256'],
                    'record_sha256': record_digest(record), 'retrieved_at': record['retrieved_at']}))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            report['errors'].append({'label': label, 'error': str(exc)})
            continue
        soup, _ = source_soup(body)
        titles = soup.select('.viewOnetitle')
        scopes = [title.find_parent('table') for title in titles] if len(titles) > 1 else [soup]
        components = expand_archive_records([record])
        if len(scopes) != len(components):
            report['errors'].append({'label': label, 'error': 'Source entry header count differs from extracted entries'})
            continue
        for scope, component in zip(scopes, components):
            if scope is None or (len(titles) > 1 and len(scope.select('.viewOnetitle')) != 1):
                report['errors'].append({'label': label, 'error': 'Ambiguous source entry boundary'})
                continue
            audit_entry_content(scope, component, report, counts, categories)
    counts['entries'] = len(expand_archive_records(records))
    report['counts'], report['categories'] = dict(counts), dict(categories)
    report['parsed_records_verified'] = bool(records) and not any(report[k] for k in
        ('errors', 'warnings', 'content_assets', 'date_metadata', 'blocked_records'))
    # Unparsed labels can be aliases, non-grammar or unavailable pages. They
    # cannot be called eligible or safely excluded without observing a replay.
    # An exclusion counts only after the retained response reproduces its classification.
    for label in sorted(indexed):
        state = read_archive_state(root, label)
        if not state or state['status'] != 'excluded':
            continue
        try:
            capture = state['capture']
            verify_entry_replay(capture, label)
            body = cached_body(root, state['response_sha256'])
            if (state.get('latest_indexed_timestamp') != latest.get(label) or
                (capture['timestamp'] != latest.get(label) and not latest_body_equivalent(body, capture, indexed_entries[label])) or
                original_label(capture['original']) != label or not allowed_archive_url(capture['archive_url'])):
                raise ValueError('Exclusion is not backed by the latest indexed replay')
            try:
                parse_archive(body, capture, state['retrieved_at'], eligible_ids)
            except NotGrammar:
                report['verified_exclusions'].append({'label': label, 'archive_url': capture['archive_url']})
            else:
                raise ValueError('Retained replay does not support the exclusion')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            report['errors'].append({'label': label, 'error': f'Invalid exclusion evidence: {exc}'})
    exported_labels = {r['label'] for r in records} - {r['label'] for r in report['blocked_records']}
    excluded_labels = {r['label'] for r in report['verified_exclusions']}
    report['pending_labels'] = sorted(indexed - exported_labels - excluded_labels)
    report['historical_coverage_complete'] = (inventory.get('cdx_complete') is True and
        not report['pending_labels'] and not any(report[k] for k in
        ('errors', 'warnings', 'content_assets', 'date_metadata', 'blocked_records')) and
        (report['parsed_records_verified'] or not records))
    feed_errors, publication_events, feeds = [], [], read_archive_feeds(root, for_export=False)
    feed_reviews, feed_warnings, unverified_feeds = [], [], []
    for feed in feeds:
        state = read_feed_state(root, feed['feed_path'])
        if state and (state['status'] != 'parsed' or state.get('response_sha256') != feed['response_sha256']
                      or state.get('archive_url') != feed['archive_url']):
            feed_errors.append({'path': feed['feed_path'], 'error': f"Last feed attempt is {state['status']}"})
        elif not state and feed['feed_path'] in feed_holds:
            feed_errors.append({'path': feed['feed_path'], 'error': f"Legacy feed hold is {feed_holds[feed['feed_path']]}"})
        if not state or state.get('record_sha256') != record_digest(feed):
            unverified_feeds.append(feed['feed_path'])
        feed_reviews.extend({'path': feed['feed_path'], **item} for item in feed['review_required'])
        feed_warnings.extend({'path': feed['feed_path'], 'warning': warning} for warning in feed['warnings'])
        try:
            raw = cached_body(root, feed['response_sha256'])
            source_items = ET.fromstring(raw).findall('./channel/item')
            expected = parse_feed(raw, {'original': feed['source_url'], 'archive_url': feed['archive_url'],
                                       'timestamp': feed['archive_timestamp']},
                                  {'retrieved_at': feed['retrieved_at']},
                                  verified_labels)
            mismatches = [key for key, value in expected.items() if key != 'warnings' and feed.get(key) != value]
            if mismatches:
                feed_errors.append({'path': feed['feed_path'], 'error': 'Stored feed differs from source', 'fields': mismatches})
                continue
            if not state or state.get('record_sha256') != record_digest(feed):
                if record_verification:
                    check_latest_cached_response(root, feed['archive_url'], feed['response_sha256'], feed['archive_url'])
                feed_states.append((feed['feed_path'], {'feed_path': feed['feed_path'], 'status': 'parsed',
                    'checked_at': now(), 'verification': 'offline-source-audit',
                    'response_sha256': feed['response_sha256'], 'record_sha256': record_digest(feed),
                    'archive_url': feed['archive_url'], 'current_membership_sha256': membership_digest}))
        except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
            feed_errors.append({'path': feed['feed_path'], 'error': str(exc)})
            continue
        reviewed_positions = {item['position'] for item in feed['review_required'] if type(item.get('position')) is int}
        if len(source_items) != len(feed['items']) + len(reviewed_positions):
            feed_errors.append({'path': feed['feed_path'], 'error': 'Feed item count mismatch'})
        for item in feed['items']:
            if type(item['position']) is not int or not 0 <= item['position'] < len(source_items):
                feed_errors.append({'path': feed['feed_path'], 'error': 'Invalid feed item position'})
                continue
            source = source_items[item['position']]
            for source_key, record_key in [('pubDate', 'pub_date_raw'), ('link', 'source_url'),
                ('description', 'description_raw_html'), ('title', 'title')]:
                if source.findtext(source_key) != item[record_key]:
                    feed_errors.append({'path': feed['feed_path'], 'error': f'Feed {source_key} mismatch'})
            publication_events.append({'label': item['label'], 'pub_date_raw': item['pub_date_raw']})
    report['rss'] = {'captured_feeds': len(feeds), 'items': sum(len(f['items']) for f in feeds),
        'publication_events': publication_events, 'errors': feed_errors,
        'review_required': feed_reviews, 'warnings': feed_warnings,
        'unverified_feeds': unverified_feeds,
        'captured_records_verified': bool(feeds) and not any((feed_errors, feed_reviews, feed_warnings))}
    source_verified = ((not records or report['parsed_records_verified']) and
                       (not feeds or report['rss']['captured_records_verified']) and
                       bool(records or feeds) and not report['errors'])
    if record_verification and source_verified:
        # Validate the whole batch before writing any state; never lift existing holds.
        for label, state in entry_states:
            key = hashlib.sha256(label.encode()).hexdigest()
            write_json(root, f'states/{key}.json', state)
            report['verification_states_written']['entries'] += 1
        for path, state in feed_states:
            key = hashlib.sha256(path.encode()).hexdigest()
            write_json(root, f'feed-states/{key}.json', state)
            report['verification_states_written']['feeds'] += 1
        report['unverified_records'] = []
        report['rss']['unverified_feeds'] = []
    report['export_ready'] = source_verified and not (report['unverified_records'] or report['rss']['unverified_feeds'])
    write_json(root, 'coverage-report.json', report)
    return report
