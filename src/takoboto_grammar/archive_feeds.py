"""Latest original grammar RSS snapshots; publication dates remain feed events."""

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote, urlencode, urlsplit

from bs4 import BeautifulSoup

from .archive import CDX, GRAMMAR_FEEDS, ArchiveAccessError, allowed_archive_url, original_label
from .crawl import now
from .parser import LICENSE, ParseError, cc_license_links, is_data_license, fragment, text
from .storage import write_json, write_record, record_digest


def feed_replay(url):
    replay = re.fullmatch(r'https://web\.archive\.org/web/(\d{14})(?:id_)?/(.*)', url)
    if not replay or not allowed_archive_url(url) or urlsplit(replay[2]).path not in GRAMMAR_FEEDS:
        raise ParseError('RSS replay URL is outside the archived grammar feed scope')
    return replay[1], replay[2]


def parse_feed(body, capture, meta, verified_labels):
    requested_timestamp, requested_original = feed_replay(capture['archive_url'])
    if requested_timestamp != capture['timestamp'] or requested_original != capture['original']:
        raise ParseError('RSS replay URL, timestamp and original URL disagree')
    final_url = meta.get('final_url', capture['archive_url'])
    actual_timestamp, actual_original = feed_replay(final_url)
    if urlsplit(actual_original).path != urlsplit(capture['original']).path:
        raise ParseError('RSS replay redirected to a different feed')
    try:
        xml = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ParseError(f'Invalid archived RSS: {exc}') from exc
    if xml.tag != 'rss' or xml.find('channel') is None:
        raise ParseError('Replay is not an RSS grammar feed')
    channel = xml.find('channel')
    record = {'feed_schema_version': 1, 'source': 'jgram-wayback-rss',
        'feed_path': urlsplit(actual_original).path, 'source_url': actual_original,
        'archive_url': final_url, 'archive_timestamp': actual_timestamp,
        'retrieved_at': meta['retrieved_at'], 'response_sha256': hashlib.sha256(body).hexdigest(),
        'title': channel.findtext('title'), 'description': channel.findtext('description'),
        'channel_xml': ET.tostring(channel, encoding='unicode'), 'license': LICENSE,
        'license_basis': 'JGram/Takoboto grammar notice; items restricted to verified grammar labels',
        'items': [], 'warnings': [], 'review_required': []}
    # A feed-wide rights declaration applies even when individual excerpts look eligible.
    declarations = [child for child in channel if child.tag.rsplit('}', 1)[-1].lower()
                    in {'copyright', 'rights', 'license'}]
    for declaration in declarations:
        declared = ' '.join(declaration.itertext()) + ' ' + ' '.join(declaration.attrib.values())
        links = re.findall(r'https?://(?:www\.)?creativecommons\.org/licenses/[^\s<>"\']+', declared)
        shorthand = re.findall(r'\b(?:CC|Creative[-\s]+Commons)[-\s]+BY(?:[-\s]+[A-Z]+)*[-\s]+\d+(?:\.\d+)?', declared, re.I)
        restrictive = re.search(r'all\s+rights\s+reserved|non[-\s]?commercial|no\s+(?:copying|redistribution)', declared, re.I)
        unknown_license = (declaration.tag.rsplit('}', 1)[-1].lower() == 'license'
                           and declared.strip() and not links and not shorthand)
        if restrictive or unknown_license or any(not is_data_license(link) for link in links) or (
            any(re.sub(r'[-\s]+', '-', notice.upper()) not in
                {'CC-BY-SA-2.0', 'CREATIVE-COMMONS-BY-SA-2.0'} for notice in shorthand)):
            record['review_required'].append({'position': None, 'link': None,
                                             'reason': 'Conflicting feed-wide license declaration'})
    if actual_timestamp != requested_timestamp:
        record['warnings'].append('Feed replay redirected to a different capture timestamp')
    for position, item in enumerate(channel.findall('item')):
        link = item.findtext('link')
        label = original_label(link or '')
        raw_html = item.findtext('description') or ''
        soup = BeautifulSoup(raw_html, 'html.parser')
        licenses = cc_license_links(soup)
        if label not in verified_labels or any(not is_data_license(url) for url in licenses):
            record['review_required'].append({'position': position, 'link': link,
                'reason': 'Unverified grammar label or conflicting item license'})
            continue
        # RSS copies include contribution controls: retain source XML, remove
        # those controls from the reader fragment. Never follow these links.
        for anchor in list(soup.select('a[href]')):
            if re.search(r'/pages/(?:add\w*|parser|setStudy|seeAlsoForm)\.php', anchor['href'], re.I):
                anchor.decompose()
        wrapper = BeautifulSoup('<div></div>', 'html.parser').div
        for node in list(soup.contents):
            wrapper.append(node.extract())
        record['items'].append({'position': position, 'label': label,
            'entry_id': verified_labels[label], 'title': item.findtext('title'), 'source_url': link,
            'pub_date_raw': item.findtext('pubDate'), 'author_raw': item.findtext('author'),
            'creator_raw': item.findtext('{http://purl.org/dc/elements/1.1/}creator'),
            'guid': item.findtext('guid'), 'description_raw_html': raw_html,
            'body_html': fragment(wrapper, actual_original), 'body_text': text(wrapper),
            'item_xml': ET.tostring(item, encoding='unicode')})
    return record


def crawl_feeds(fetcher, verified_labels):
    report = {'started_at': now(), 'parsed': [], 'failed': [], 'review_required': [], 'warnings': [], 'complete': False}
    for path in GRAMMAR_FEEDS:
        key = hashlib.sha256(path.encode()).hexdigest()
        state = {'feed_path': path, 'status': 'pending', 'checked_at': now()}
        write_json(fetcher.root, f'feed-states/{key}.json', state)
        try:
            url = CDX + '?' + urlencode({'url': 'jgram.org' + path, 'output': 'json',
                'filter': 'statuscode:200', 'fl': 'timestamp,original,mimetype,digest', 'limit': '10000'})
            body, index_meta = fetcher.get(url)
            rows = json.loads(body)
            if not rows or len(rows) >= 10001:
                raise ParseError('Feed index absent or reaches bounded query limit; inspect before claiming latest')
            if not {'timestamp', 'original', 'mimetype', 'digest'}.issubset(rows[0]):
                raise ParseError('Unexpected feed CDX header')
            captures = []
            for row in rows[1:]:
                if len(row) != len(rows[0]):
                    raise ParseError('Malformed feed CDX row')
                cap = dict(zip(rows[0], row))
                if not re.fullmatch(r'\d{14}', cap['timestamp']):
                    raise ParseError('Malformed feed timestamp')
                cap['archive_url'] = quote(f"https://web.archive.org/web/{cap['timestamp']}id_/{cap['original']}", safe="/:?=&;%+@!()*,-._~'")
                if urlsplit(cap['original']).path != path or not allowed_archive_url(cap['archive_url']):
                    raise ParseError('Out-of-scope original in feed CDX result')
                captures.append(cap)
            if not captures:
                raise ParseError('No successful archived feed capture')
            selected = max(captures, key=lambda c: (c['timestamp'], c['original']))
            raw, meta = fetcher.get(selected['archive_url'])
            record = parse_feed(raw, selected, meta, verified_labels)
            record['indexed_capture_count'] = len(captures)
            record['index_response_sha256'] = index_meta['sha256']
            write_record(fetcher.root, f"feeds/{path.rsplit('/', 1)[-1][:-4]}.yaml", record)
            state.update(status='review_required' if record['review_required'] or record['warnings'] else 'parsed',
                         response_sha256=record['response_sha256'], archive_url=record['archive_url'],
                         record_sha256=record_digest(record))
            report['parsed'].append({'path': path, 'items': len(record['items']), 'archive_timestamp': record['archive_timestamp']})
            report['warnings'].extend({'path': path, 'warning': w} for w in record['warnings'])
            report['review_required'].extend({'path': path, **item} for item in record['review_required'])
            print(f"RSS {path}: {len(record['items'])} items ({record['archive_timestamp']})", flush=True)
        except (ArchiveAccessError, OSError, ParseError, ValueError) as exc:
            report['failed'].append({'path': path, 'error': str(exc)})
            break
        finally:
            if state['status'] == 'pending':
                state['status'] = 'failed'
            state['checked_at'] = now()
            write_json(fetcher.root, f'feed-states/{key}.json', state)
            write_json(fetcher.root, 'feed-crawl-report.json', report)
    report['finished_at'] = now()
    report['complete'] = len(report['parsed']) == len(GRAMMAR_FEEDS) and not any(report[k] for k in ('failed', 'warnings', 'review_required'))
    write_json(fetcher.root, 'feed-crawl-report.json', report)
    return report
