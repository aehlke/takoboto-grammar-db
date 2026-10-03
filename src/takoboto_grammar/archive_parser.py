"""JGram source observations, kept separate from current Takoboto records."""

import hashlib
import re
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from .parser import LICENSE, ParseError, cc_license_links, is_data_license, fragment, text


class NotGrammar(ParseError):
    """A valid archived page outside the requested grammar collection."""


class LicenseReviewRequired(ParseError):
    """Do not substitute an older capture to sidestep a source license notice."""


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
    soup = BeautifulSoup(body, 'html.parser')
    title_node = soup.select_one('.viewOnetitle')
    if title_node is None:
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
    if category not in {'grammar', 'lesson'} and identifier not in set(eligible_ids):
        raise NotGrammar(f'Outside collection: category {category!r}, ID {identifier}')
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
    if len({e['source_id'] for e in record['examples']}) != len(record['examples']):
        raise ParseError('Duplicate archived example ID')
    return record
