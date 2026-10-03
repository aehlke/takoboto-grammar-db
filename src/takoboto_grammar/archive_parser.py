"""JGram source observations, kept separate from current Takoboto records."""

import hashlib
import re
import copy
import base64
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit, quote_from_bytes

from bs4 import BeautifulSoup

from .parser import LICENSE, ParseError, cc_license_links, is_data_license, fragment, text
from .record_yaml import load_yaml

MEMBERSHIP_REVIEWS = load_yaml(Path(__file__).with_name('grammar-membership.yaml').read_text(encoding='utf-8'))['entries']


class NotGrammar(ParseError):
    """A valid archived page outside the requested grammar collection."""


class LicenseReviewRequired(ParseError):
    """Do not substitute an older capture to sidestep a source license notice."""


def indexed_payload_mismatch(body, capture):
    digest = capture.get('digest') or ''
    return bool(re.fullmatch(r'[A-Z2-7]{32}', digest) and
                base64.b32encode(hashlib.sha1(body).digest()).decode() != digest)


def outside_collection(body, capture, reason):
    if indexed_payload_mismatch(body, capture):
        raise LicenseReviewRequired('Exclusion payload differs from indexed digest; retain for review')
    raise NotGrammar(reason)


def source_soup(body):
    """Honor Shift-JIS, including Windows extensions and provable UTF-8 nodes.

    Some old comments were stored as UTF-8 inside a Shift-JIS page. Repair a
    text node only when strict CP932 fails and strict UTF-8 succeeds. Preserve
    byte offsets so the decoding decision is reproducible from source bytes.
    """
    repairs = []
    if re.search(rb'charset\s*=\s*["\']?(?:x-sjis|shift[_-]jis)', body[:4096], re.I):
        try:
            body.decode('shift_jis')
        except UnicodeDecodeError:
            offsets = [0] + [i + 1 for i, byte in enumerate(body) if byte == 10]
            class Nodes(HTMLParser):
                def handle_starttag(self, tag, attrs):
                    raw_tag = self.get_starttag_text().encode('latin-1')
                    line, column = self.getpos()
                    base = offsets[line - 1] + column
                    for match in re.finditer(rb'''\b(?:href|src)\s*=\s*(['"])(.*?)\1''', raw_tag, re.S | re.I):
                        raw_url = match[2]
                        try:
                            raw_url.decode('cp932')
                        except UnicodeDecodeError:
                            encoded = quote_from_bytes(raw_url, safe='/:?=&;%+@!()*,-._~').encode('ascii')
                            start = base + match.start(2)
                            if body[start:start + len(raw_url)] == raw_url:
                                repairs.append((start, len(raw_url), encoded, 'percent-encoded-original-url-bytes', raw_url.hex()))

                def handle_data(self, data):
                    raw = data.encode('latin-1')
                    try:
                        raw.decode('cp932')
                    except UnicodeDecodeError:
                        try:
                            decoded = raw.decode('utf-8')
                            encoding = 'utf-8'
                        except UnicodeDecodeError:
                            decoded = raw.decode('cp932', errors='replace')
                            encoding = 'cp932-with-undecodable-bytes'
                        line, column = self.getpos()
                        start = offsets[line - 1] + column
                        if body[start:start + len(raw)] != raw:
                            return
                        repaired = ''.join(c if ord(c) < 128 else f'&#{ord(c)};' for c in decoded).encode('ascii')
                        repairs.append((start, len(raw), repaired, encoding, raw.hex()))
            parser = Nodes(convert_charrefs=False)
            parser.feed(body.decode('latin-1'))
            parser.close()
            revised = body
            repairs.sort()
            for offset, length, replacement, encoding, original_hex in reversed(repairs):
                revised = revised[:offset] + replacement + revised[offset + length:]
            try:
                revised.decode('cp932')
                return BeautifulSoup(revised, 'html.parser', from_encoding='cp932'), [
                    {'byte_offset': offset, 'byte_length': length, 'encoding': encoding, 'original_bytes_hex': original_hex}
                    for offset, length, _, encoding, original_hex in repairs]
            except UnicodeDecodeError:
                pass
    return BeautifulSoup(body, 'html.parser'), []


def labeled_value(soup, label, italic=False):
    marker = soup.find('b', string=re.compile(r'^' + re.escape(label) + r'\s*$'))
    if not marker:
        return None
    if italic:
        node = marker.find_next('i')
        return text(node) or None
    out = []
    for node in marker.next_siblings:
        if getattr(node, 'name', None) == 'br':
            break
        out.append(node.get_text() if hasattr(node, 'get_text') else str(node))
    return ''.join(out).lstrip(': ').strip() or None


def parse_archive(body, capture, retrieved_at, eligible_ids=()):
    soup, decoding_segments = source_soup(body)
    titles = soup.select('.viewOnetitle')
    if len(titles) <= 1:
        return parse_archive_entry(body, capture, retrieved_at, eligible_ids, soup, decoding_segments)
    # JGram could return several distinct IDs for one tagE. Their contribution
    # tables repeat the same section names; a heading dictionary cannot identify
    # the entry that owns a note, comment or example.
    tables = [title.find_parent('table') for title in titles]
    if (any(table is None or len(table.select('.viewOnetitle')) != 1 for table in tables) or
        len({id(table) for table in tables}) != len(tables)):
        raise LicenseReviewRequired('Multiple entry headers lack distinct source table boundaries; retain for review')
    records = []
    for position in range(len(titles)):
        scoped = copy.copy(soup)
        scoped_titles = scoped.select('.viewOnetitle')
        for other, title in enumerate(scoped_titles):
            if other != position:
                title.find_parent('table').decompose()
        try:
            record = parse_archive_entry(body, capture, retrieved_at, eligible_ids, scoped, decoding_segments)
        except NotGrammar as exc:
            raise LicenseReviewRequired('Multi-entry response contains a component requiring separate scope review') from exc
        record['archive_schema_version'] = 2
        record['page_entry_position'] = position
        records.append(record)
    if len({record['id'] for record in records}) != len(records) or any(record['id'] is None for record in records):
        raise LicenseReviewRequired('Multiple entry headers have missing or repeated grammar IDs; retain for review')
    records[0]['additional_entries'] = records[1:]
    for additional in records[1:]:
        records[0]['warnings'].extend(f"Additional entry {additional['id']}: {warning}" for warning in additional['warnings'])
    return records[0]


def parse_archive_entry(body, capture, retrieved_at, eligible_ids, soup, decoding_segments):
    title_node = soup.select_one('.viewOnetitle')
    if title_node is None:
        missing = re.search(r'No entry exists for\s+(.*?)\s+- click here to add one', text(soup))
        raw_missing = re.search(rb'''No entry exists for\s*(.*?)\s*-\s*(?:<a\s+href=['"]addGrammar\.php['"]>click here</a>|click here)\s+to add one''', body, re.S)
        raw_labels = [capture['label'].encode('utf-8')]
        try:
            raw_labels.append(capture['label'].encode('cp932'))
        except UnicodeEncodeError:
            pass
        exact_raw = any(re.search(rb'''No entry exists for ''' + re.escape(label) +
            rb'''\s*-\s*(?:<a\s+href=['"]addGrammar\.php['"]>click here</a>|click here)\s+to add one''', body)
            for label in raw_labels)
        matches = ((missing and missing[1] == capture['label']) or exact_raw or
                   (raw_missing and raw_missing[1] in raw_labels))
        if (matches and soup.title and 'JGram' in text(soup.title) and
            any(is_data_license(href) for href in cc_license_links(soup))):
            outside_collection(body, capture, 'Archived JGram explicitly reports no entry for this label')
        raise ParseError('Replay is not a JGram entry (missing viewOnetitle)')
    identifier = None
    for link in soup.select('a[href]'):
        parts = urlsplit(link['href'])
        if parts.path.endswith('/addGrammar.php') or parts.path == 'addGrammar.php':
            value = parse_qs(parts.query).get('id', [None])[0]
            if value and value.isdigit():
                identifier = int(value)
                break
    category = labeled_value(soup, 'Category', italic=True)
    scope_review = next((r for r in MEMBERSHIP_REVIEWS if r['id'] == identifier and r['label'] == capture['label']), None)
    if scope_review and category is None and text(title_node) != scope_review['expected_title_raw']:
        raise LicenseReviewRequired('Entry title differs from historical membership review; recheck scope evidence')
    if category is None and identifier is not None and identifier not in set(eligible_ids):
        if scope_review is None:
            raise LicenseReviewRequired('Original collection membership is unclassified; retain response for scope review')
        if scope_review['decision'] == 'non-grammar':
            outside_collection(body, capture, 'Reviewed dictionary-only entry: ' + scope_review['basis'])
    reviewed_grammar = category is None and scope_review and scope_review['decision'] == 'grammar'
    if category not in {'grammar', 'lesson'} and identifier not in set(eligible_ids) and not reviewed_grammar:
        outside_collection(body, capture, f'Outside collection: category {category!r}, ID {identifier}')
    license_links = cc_license_links(soup)
    if not any(is_data_license(href) for href in license_links):
        raise LicenseReviewRequired('JGram license notice missing or changed; retain response for review')
    if any(not is_data_license(href) for href in license_links):
        raise LicenseReviewRequired('Additional or conflicting license on historical page; retain response for review')
    title_raw = text(title_node)
    match = re.fullmatch(r'(.*?)\s*\(?\[(.*?)\]\s*\)?\s*\((.*)\)', title_raw)
    record = {
        'archive_schema_version': 1, 'source': 'jgram-wayback', 'id': identifier,
        'label': capture['label'], 'title_raw': title_raw,
        'title': match[1].strip() if match else title_raw,
        'reading': match[2].strip() if match else None,
        'romanized_label': match[3].strip() if match else capture['label'],
        'category': category, 'jlpt_level_original': labeled_value(soup, 'JLPT Level'),
        'meaning': labeled_value(soup, 'Meaning'), 'meaning_example': labeled_value(soup, 'Example', italic=True),
        'credits_raw': labeled_value(soup, 'Author', italic=True),
        'source_url': capture['original'], 'archive_url': capture['archive_url'],
        'archive_timestamp': capture['timestamp'], 'retrieved_at': retrieved_at,
        'archive_digest': capture.get('digest'),
        'response_sha256': hashlib.sha256(body).hexdigest(), 'encoding': soup.original_encoding,
        'license': LICENSE, 'license_links': license_links,
        'notes': [], 'examples': [], 'comments': [], 'related_entries': [], 'sections': [],
        'original_created_at': None, 'original_updated_at': None, 'warnings': [],
    }
    if indexed_payload_mismatch(body, capture):
        record['warnings'].append('Source payload differs from its indexed digest; retain for review')
    if decoding_segments:
        record['source_decoding_segments'] = decoding_segments
    if reviewed_grammar:
        record['membership_review'] = scope_review
    if soup.contains_replacement_characters:
        record['warnings'].append('Source contains undecodable bytes; retain original WARC/response for review')
    if soup.select('time,[datetime],[data-date],[data-timestamp]'):
        record['warnings'].append('Historical date metadata detected; inspect response before interpreting contribution dates')
    # Retain the grammar header, including category, level, creator and variations.
    header = title_node.parent
    header_html = []
    for node in header.contents:
        if getattr(node, 'name', None) in {'tr', 'table', 'script', 'form'} and header_html:
            break
        if getattr(node, 'name', None) == 'span' and 'viewOnetitle' in node.get('class', []):
            header_html.append(str(node))
        elif header_html:
            header_html.append(str(node))
    if header_html:
        header_fragment = BeautifulSoup('<div>' + ''.join(header_html) + '</div>', 'html.parser').div
        for a in header_fragment.select('a[href]'):
            if 'addGrammar.php' in a['href']:
                a.decompose()
        record['sections'].append({'kind': 'header', 'text': text(header_fragment),
                                   'html': fragment(header_fragment, capture['original'])})
    headings = {text(e).strip(' \u00a0:'): e for e in soup.select('.titleSection')}
    if len(headings) != len(soup.select('.titleSection')):
        raise LicenseReviewRequired('Repeated section headings within one entry need source-boundary review')
    note_heading = headings.get('Notes')
    if note_heading:
        table = note_heading.find_parent('table')
        for row in table.find_all('tr', recursive=False):
            cells = row.find_all('td', recursive=False)
            if len(cells) == 2 and 'bottom' in cells[0].get('class', []):
                author = cells[1].select_one('a[href*="contributions.php"]')
                record['notes'].append({'position': len(record['notes']), 'text': text(cells[0]),
                    'html': fragment(cells[0], capture['original']), 'credits_raw': text(author) or None,
                    'source_id': None, 'original_created_at': None, 'original_updated_at': None})
    for anchor in soup.select('a[name]'):
        value = anchor.get('name', '')
        if not value.isdigit() or not re.search(r'ex\s*#', anchor.get_text(), re.I):
            continue
        row = anchor.find_parent('tr')
        cells = row.find_all('td', recursive=False)
        if len(cells) != 3:
            raise ParseError(f'Unexpected archived example shape: {value}')
        japanese = next((a for a in cells[1].select('a[href]')
                         if 'wwwjdic' in a.get('href', '').lower()), None)
        author = cells[2].select_one('a[href*="contributions.php"]')
        record['examples'].append({'source_id': int(value), 'position': len(record['examples']),
            'japanese': text(japanese) if japanese else None,
            'body_text': text(cells[1]), 'body_html': fragment(cells[1], capture['original']),
            'credits_raw': text(author) or None,
            'verification_class': cells[0].get('class', []),
            'original_created_at': None, 'original_updated_at': None})
    comments_heading = headings.get('Comments')
    if comments_heading:
        table = comments_heading.find_parent('table')
        for row in table.find_all('tr', recursive=False):
            cells = row.find_all('td', recursive=False)
            if len(cells) == 3 and 'bottom' in cells[1].get('class', []):
                record['comments'].append({'position': len(record['comments']),
                    'credits_raw': text(cells[0]) or None, 'text': text(cells[1]),
                    'html': fragment(cells[1], capture['original']), 'source_id': None,
                    'original_created_at': None, 'original_updated_at': None})
    see_heading = headings.get('See Also')
    if see_heading:
        container = see_heading.parent
        # Old JGram's unclosed <li> tags nest siblings in html.parser. Exclude child
        # list items when extracting each relation to avoid duplicating annotations.
        for item in container.select('li'):
            isolated = __import__('copy').copy(item)
            for child in isolated.find_all('li'):
                child.decompose()
            link = next((a for a in isolated.select('a[href]')
                         if 'viewOne.php' in a['href']), None)
            if not link:
                continue
            label = parse_qs(urlsplit(link['href']).query).get('tagE', [None])[0]
            author = isolated.select_one('a[href*="contributions.php"]')
            record['related_entries'].append({'position': len(record['related_entries']),
                'target_label': label, 'label': text(link), 'annotation_text': text(isolated),
                'annotation_html': fragment(isolated, capture['original']), 'credits_raw': text(author) or None})
    known = {'Notes', 'Examples', 'See Also', 'Comments', 'Add Entry to Your Study List'}
    for name, heading in headings.items():
        if name not in known:
            record['sections'].append({'kind': name, 'text': text(heading.parent),
                                      'html': fragment(heading.parent, capture['original'])})
            record['warnings'].append(f'Unfamiliar historical section retained: {name}')
    # Original IDs can repeat. Position identifies each source occurrence;
    # preserving both rows avoids losing an example or its attribution.
    return record
