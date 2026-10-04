"""Source-bound section omissions; reviewed third-party material stays out of exports."""

import hashlib
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .parser import text
from .record_yaml import load_yaml

REVIEWS = load_yaml(Path(__file__).with_name('section-reviews.yaml').read_text(encoding='utf-8'))['entries']


def section_hash(scope):
    return hashlib.sha256(str(scope).encode('utf-8')).hexdigest()


def reviewed_credit(scope, review):
    if re.search(r'Copyright.*Tae Kim', text(scope), re.I):
        return True
    evidence = review.get('credit_evidence', {})
    if evidence.get('method') != 'exact-passages-in-reviewed-copyrighted-tutorial':
        return False
    references = [r for r in REVIEWS if r['response_sha256'] == evidence.get('reference_response_sha256') and
                  r['section_html_sha256'] == evidence.get('reference_section_html_sha256') and
                  r['source_url'] == evidence.get('reference_source_url') and not r.get('credit_evidence')]
    if len(references) != 1 or references[0]['credits_raw'] != 'Tae Kim':
        return False
    normalized = re.sub(r'\s+', ' ', text(scope))
    blocks = evidence.get('matching_passages', [])
    last_end, matched = 0, 0
    for block in blocks:
        start, length = block['source_text_offset'], block['text_length']
        if type(start) is not int or type(length) is not int or start < last_end or length < 200 or start + length > len(normalized):
            return False
        if hashlib.sha256(normalized[start:start + length].encode()).hexdigest() != block['text_sha256']:
            return False
        last_end, matched = start + length, matched + length
    return matched >= 1000


def review_sections(soup, body, capture):
    """Remove only exact reviewed cells, after checking independent entry boundaries."""
    digest = hashlib.sha256(body).hexdigest()
    reviews = [item for item in REVIEWS if item['response_sha256'] == digest and
               item['source_url'] == capture['original'] and item['label'] == capture['label']]
    omissions = []
    for review in reviews:
        headings = [h for h in soup.select('.titleSection') if text(h).strip(' \u00a0:') == review['section']]
        if len(headings) != 1:
            raise ValueError('Reviewed section heading is absent or ambiguous')
        scope = headings[0].parent
        identifiers = [parse_qs(urlsplit(a['href']).query).get('id', [None])[0]
                       for a in soup.select('a[href]') if urlsplit(a['href']).path.endswith('addGrammar.php')]
        identifiers = [value for value in identifiers if value and value.isdigit()]
        if not identifiers or identifiers[0] != str(review['id']):
            raise ValueError('Reviewed entry ID differs from the source')
        start, length = review['source_byte_offset'], review['source_byte_length']
        if type(start) is not int or type(length) is not int or start < 0 or length <= 0 or start + length > len(body):
            raise ValueError('Reviewed section byte range is invalid')
        if hashlib.sha256(body[start:start + length]).hexdigest() != review['section_bytes_sha256']:
            raise ValueError('Reviewed original section bytes differ')
        # Independently decode the claimed raw range before dropping repair evidence.
        from .archive_parser import source_soup
        ranged, _ = source_soup(b'<meta charset="shift_jis">' + body[start:start + length])
        if ranged.td is None or section_hash(ranged.td) != review['section_html_sha256']:
            raise ValueError('Reviewed byte range does not reproduce the omitted cell')
        titles = soup.select('.viewOnetitle')
        if (len(titles) != 1 or text(titles[0]) != review['title_raw'] or
            scope.name != 'td' or len(scope.select('.titleSection')) != 1 or
            scope.select('.viewOnetitle') or section_hash(scope) != review['section_html_sha256'] or
            hashlib.sha256(text(scope).encode('utf-8')).hexdigest() != review['section_text_sha256'] or
            not reviewed_credit(scope, review)):
            raise ValueError('Reviewed section boundary or source evidence changed')
        # Grammar contribution rows and source IDs must remain outside this cell.
        if any(re.search(r'ex\s*#', text(a), re.I) for a in scope.select('a[name]')):
            raise ValueError('Reviewed tutorial cell contains a JGram example anchor')
        omissions.append(dict(review))
        scope.decompose()
    return omissions


def validate_omissions(record):
    omissions = record.get('omitted_sections', [])
    if not isinstance(omissions, list):
        raise ValueError('Section omission metadata must be a list')
    if omissions and record.get('source_sections_complete') is not False:
        raise ValueError('Section omissions require an explicit incomplete-source marker')
    for omission in omissions:
        if omission not in REVIEWS or any(omission[key] != record[field] for key, field in
            [('response_sha256', 'response_sha256'), ('source_url', 'source_url'), ('label', 'label'), ('id', 'id')]):
            raise ValueError('Section omission lacks matching source-bound review evidence')
        if any(section['kind'] == omission['section'] for section in record['sections']):
            raise ValueError('Omitted section body is still present in the exported record')


def verify_credit_references(omissions, body_lookup):
    """Raw-source audits verify the other side of reviewed attribution matches."""
    from .archive_parser import source_soup
    for omission in omissions:
        evidence = omission.get('credit_evidence')
        if not evidence:
            continue
        body = body_lookup(evidence['reference_response_sha256'])
        if hashlib.sha256(body).hexdigest() != evidence['reference_response_sha256']:
            raise ValueError('Tutorial attribution reference response hash differs')
        soup, _ = source_soup(body)
        candidates = [h.parent for h in soup.select('.titleSection') if
                      section_hash(h.parent) == evidence['reference_section_html_sha256']]
        if len(candidates) != 1 or not re.search(r'Copyright.*Tae Kim', text(candidates[0]), re.I):
            raise ValueError('Tutorial attribution reference cell or displayed credit differs')
        normalized = re.sub(r'\s+', ' ', text(candidates[0]))
        for block in evidence['matching_passages']:
            start, length = block['reference_text_offset'], block['text_length']
            if (type(start) is not int or start < 0 or start + length > len(normalized) or
                hashlib.sha256(normalized[start:start + length].encode()).hexdigest() != block['text_sha256']):
                raise ValueError('Tutorial attribution reference passage differs')
