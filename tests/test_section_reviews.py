"""Section-level recovery must preserve JGram content and exclude third-party bodies."""

import base64
import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup
from takoboto_grammar import section_reviews
from takoboto_grammar.archive_parser import parse_archive, source_soup
from takoboto_grammar.parser import text
from takoboto_grammar.storage import build_sqlite, export_markdown
from test_archive import CAPTURE, FIXTURE


class SectionReviewTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='jgram-section-review-test-')).resolve()
        soup, _ = source_soup(FIXTURE.read_bytes())
        table = BeautifulSoup('<table><tr><td><span class="titleSection">Tutorial:</span><p>SECRET THIRD PARTY BODY Copyright © 2003-2006 Tae Kim</p><a href="https://creativecommons.org/licenses/by-nc-sa/2.0/">Tutorial license</a></td></tr></table>', 'html.parser').table
        soup.body.append(table)
        self.body = soup.encode('shift_jis')
        self.capture = dict(CAPTURE, digest=base64.b32encode(hashlib.sha1(self.body).digest()).decode())
        parsed, _ = source_soup(self.body)
        scope = parsed.select('.titleSection')[-1].parent
        raw_scope = BeautifulSoup(self.body.decode('latin1'), 'html.parser').select('.titleSection')[-1].parent
        offsets = [0] + [i + 1 for i, byte in enumerate(self.body) if byte == 10]
        start = offsets[raw_scope.sourceline - 1] + raw_scope.sourcepos
        # This synthetic final cell is followed only by closing page markup.
        length = len(self.body) - start
        self.review = {'label': CAPTURE['label'], 'id': 978, 'title_raw': text(parsed.select_one('.viewOnetitle')),
            'source_url': CAPTURE['original'], 'response_sha256': hashlib.sha256(self.body).hexdigest(),
            'section': 'Tutorial', 'section_html_sha256': section_reviews.section_hash(scope),
            'section_text_sha256': hashlib.sha256(text(scope).encode()).hexdigest(),
            'source_byte_offset': start, 'source_byte_length': length,
            'section_bytes_sha256': hashlib.sha256(self.body[start:]).hexdigest(),
            'credits_raw': 'Tae Kim', 'decision': 'omit-from-CC-BY-SA-2.0-export', 'basis': 'Fixture review'}

    def parse(self):
        return parse_archive(self.body, self.capture, 'fixture retrieval')

    def test_reviewed_cell_preserves_all_jgram_contributions_and_marks_partial(self):
        original = parse_archive(FIXTURE.read_bytes(), CAPTURE, 'fixture retrieval')
        with patch.object(section_reviews, 'REVIEWS', [self.review]):
            record = self.parse()
            self.assertFalse(record['source_sections_complete'])
            self.assertEqual(record['omitted_sections'], [self.review])
            self.assertEqual(record['warnings'], [])
            for field in ('notes', 'examples', 'comments', 'related_entries'):
                self.assertEqual(record[field], original[field])
            path = build_sqlite([], self.root / 'grammar.sqlite', [record])
            with closing(sqlite3.connect(path)) as db:
                content = db.execute('SELECT record_json FROM archive_entries').fetchone()[0]
                self.assertNotIn('SECRET THIRD PARTY BODY', content)
                self.assertFalse(json.loads(content)['source_sections_complete'])
            pages = export_markdown([], self.root / 'markdown', [record])
            page = next((pages / 'jgram').glob('*.md')).read_text()
            self.assertIn('partial source observation', page)
            self.assertNotIn('SECRET THIRD PARTY BODY', page)

    def test_unreviewed_or_changed_tutorial_stays_held(self):
        with self.assertRaisesRegex(ValueError, 'conflicting license'):
            self.parse()
        with patch.object(section_reviews, 'REVIEWS', [dict(self.review, response_sha256='0' * 64)]):
            with self.assertRaisesRegex(ValueError, 'conflicting license'):
                self.parse()

    def test_wrong_cell_hash_or_entry_id_cannot_authorize_omission(self):
        for field, value in [('section_html_sha256', '0' * 64), ('id', 1649), ('section_bytes_sha256', '0' * 64)]:
            with self.subTest(field=field), patch.object(section_reviews, 'REVIEWS', [dict(self.review, **{field: value})]):
                with self.assertRaises(ValueError):
                    self.parse()

    def test_valid_hash_of_wrong_source_range_does_not_authorize_omission(self):
        unrelated_range = dict(self.review, source_byte_offset=0,
                               source_byte_length=len(self.body),
                               section_bytes_sha256=hashlib.sha256(self.body).hexdigest())
        with patch.object(section_reviews, 'REVIEWS', [unrelated_range]):
            with self.assertRaisesRegex(ValueError, 'does not reproduce'):
                self.parse()

    def test_absent_displayed_credit_requires_verified_matching_passages(self):
        scope = BeautifulSoup('<td>' + 'Shared tutorial passage. ' * 70 + '</td>', 'html.parser').td
        normalized = text(scope)
        evidence = {'method': 'exact-passages-in-reviewed-copyrighted-tutorial',
                    'reference_response_sha256': self.review['response_sha256'],
                    'reference_section_html_sha256': self.review['section_html_sha256'],
                    'reference_source_url': self.review['source_url'],
                    'matching_passages': [{'source_text_offset': 0, 'text_length': len(normalized),
                                          'text_sha256': hashlib.sha256(normalized.encode()).hexdigest()}]}
        reviewed = dict(self.review, credit_evidence=evidence)
        with patch.object(section_reviews, 'REVIEWS', [self.review]):
            self.assertTrue(section_reviews.reviewed_credit(scope, reviewed))
            self.assertFalse(section_reviews.reviewed_credit(scope, self.review))
            evidence['matching_passages'][0]['text_sha256'] = '0' * 64
            self.assertFalse(section_reviews.reviewed_credit(scope, reviewed))
        with patch.object(section_reviews, 'REVIEWS', []):
            self.assertFalse(section_reviews.reviewed_credit(scope, reviewed))

    def test_attribution_reference_raw_source_and_offsets_are_audited(self):
        body = b'<meta charset="utf-8"><td><span class="titleSection">Tutorial:</span>' + b'Shared tutorial passage. ' * 70 + b'Copyright Tae Kim</td>'
        soup, _ = source_soup(body)
        normalized = text(soup.td)
        review = {'credit_evidence': {
            'reference_response_sha256': hashlib.sha256(body).hexdigest(),
            'reference_section_html_sha256': section_reviews.section_hash(soup.td),
            'matching_passages': [{'reference_text_offset': 0, 'text_length': len(normalized),
                                  'text_sha256': hashlib.sha256(normalized.encode()).hexdigest()}]}}
        section_reviews.verify_credit_references([review], lambda digest: body)
        with self.assertRaisesRegex(ValueError, 'response hash'):
            section_reviews.verify_credit_references([review], lambda digest: body + b'changed')
        review['credit_evidence']['matching_passages'][0]['reference_text_offset'] = 1
        with self.assertRaisesRegex(ValueError, 'passage differs'):
            section_reviews.verify_credit_references([review], lambda digest: body)

    def test_unmatched_omission_metadata_is_rejected_before_output_creation(self):
        with patch.object(section_reviews, 'REVIEWS', [self.review]):
            record = self.parse()
        with self.assertRaisesRegex(ValueError, 'source-bound review'):
            build_sqlite([], self.root / 'held.sqlite', [record])
        self.assertFalse((self.root / 'held.sqlite').exists())

    def test_incomplete_marker_and_retained_tutorial_body_are_enforced(self):
        with patch.object(section_reviews, 'REVIEWS', [self.review]):
            record = self.parse()
            record['source_sections_complete'] = True
            with self.assertRaisesRegex(ValueError, 'incomplete-source'):
                build_sqlite([], self.root / 'complete.sqlite', [record])
            record['source_sections_complete'] = False
            record['sections'].append({'kind': 'Tutorial', 'text': 'SECRET THIRD PARTY BODY'})
            with self.assertRaisesRegex(ValueError, 'still present'):
                build_sqlite([], self.root / 'leaked.sqlite', [record])

    def test_excluded_encoding_repairs_do_not_leak_original_tutorial_bytes(self):
        secret = 'Which: 関わり, 係わり, 拘らず?'.encode('utf-8')
        self.body = self.body.replace(b'SECRET THIRD PARTY BODY', secret)
        self.capture['digest'] = base64.b32encode(hashlib.sha1(self.body).digest()).decode()
        soup, repairs = source_soup(self.body)
        self.assertTrue(repairs)
        scope = soup.select('.titleSection')[-1].parent
        start = self.review['source_byte_offset']
        self.review.update(response_sha256=hashlib.sha256(self.body).hexdigest(),
            section_html_sha256=section_reviews.section_hash(scope),
            section_text_sha256=hashlib.sha256(text(scope).encode()).hexdigest(),
            source_byte_length=len(self.body) - start,
            section_bytes_sha256=hashlib.sha256(self.body[start:]).hexdigest())
        with patch.object(section_reviews, 'REVIEWS', [self.review]):
            record = self.parse()
            self.assertGreater(record['omitted_source_decoding_segment_count'], 0)
            for repair in record.get('source_decoding_segments', []):
                self.assertNotIn(secret, bytes.fromhex(repair['original_bytes_hex']))
            self.assertNotIn(secret.hex(), json.dumps(record))
