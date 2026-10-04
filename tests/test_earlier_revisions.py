"""Earlier recovery must not replace or impersonate the latest label response."""

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
from takoboto_grammar.earlier_revisions import read_earlier_records, audit_earlier_records
from takoboto_grammar.storage import (write_record, write_json, cache_response, record_digest,
    annotate_archive_record, read_archive_records, build_sqlite, export_markdown)
from test_archive import CAPTURE, FIXTURE


class EarlierRevisionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='jgram-earlier-test-')).resolve() / 'archive-data'
        self.root.mkdir()
        self.retain_source(FIXTURE.read_bytes())

    def retain_source(self, body):
        self.body = body
        digest = base64.b32encode(hashlib.sha1(self.body).digest()).decode()
        self.capture = dict(CAPTURE, timestamp='20140327015231', digest=digest,
                            archive_url=CAPTURE['archive_url'].replace('20200215021200', '20140327015231'))
        self.latest = dict(CAPTURE, digest='B' * 32)
        self.inventory = {'entries': [{'label': CAPTURE['label'], 'captures': [self.latest, self.capture]}]}
        write_json(self.root, 'inventory.json', self.inventory)
        self.record = parse_archive(self.body, self.capture, 'now')
        annotate_archive_record(self.record, observation_kind='earlier-indexed-revision',
            selected_indexed_timestamp=self.capture['timestamp'], latest_indexed_timestamp=self.latest['timestamp'],
            selection_reason='Latest label has no entry; retain earlier source.', selection_provenance='fixture')
        self.key = hashlib.sha256(CAPTURE['label'].encode()).hexdigest() + '-' + self.capture['timestamp']
        self.state = {'label': CAPTURE['label'], 'status': 'parsed', 'capture': self.capture,
            'response_sha256': self.record['response_sha256'], 'record_sha256': record_digest(self.record),
            'latest_indexed_timestamp': self.latest['timestamp']}
        write_record(self.root, f'earlier-records/{self.key}.yaml', self.record)
        write_json(self.root, f'earlier-states/{self.key}.json', self.state)
        self.latest_key = hashlib.sha256(CAPTURE['label'].encode()).hexdigest()
        write_json(self.root, f'states/{self.latest_key}.json', {'label': CAPTURE['label'], 'status': 'excluded'})
        cache_response(self.root, f'cache/responses/{self.record["response_sha256"]}.bin', self.body)
        write_json(self.root, f'cache/urls/{hashlib.sha256(self.capture["archive_url"].encode()).hexdigest()}.json',
                   {'url': self.capture['archive_url'], 'final_url': self.capture['archive_url'],
                    'sha256': self.record['response_sha256']})

    def test_source_audit_and_exports_preserve_latest_state_and_distinguish_revision(self):
        latest_path = self.root / 'states' / (self.latest_key + '.json')
        before = latest_path.read_bytes()
        self.assertTrue(audit_earlier_records(self.root, [])['source_verified'])
        self.assertEqual(read_archive_records(self.root), [self.record])
        self.assertEqual(read_archive_records(self.root, include_earlier=False), [])
        latest_record = parse_archive(self.body, CAPTURE, 'now')
        dbpath = build_sqlite([], self.root / 'grammar.sqlite', [self.record, latest_record])
        with closing(sqlite3.connect(dbpath)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM archive_entries').fetchone()[0], 2)
        out = export_markdown([], self.root / 'reader', [self.record])
        self.assertIn('Earlier indexed revision', next((out / 'jgram').glob('*.md')).read_text())
        self.assertEqual(before, latest_path.read_bytes())

    def test_changed_inventory_or_selected_digest_blocks_export(self):
        self.inventory['entries'][0]['captures'][1]['digest'] = 'C' * 32
        write_json(self.root, 'inventory.json', self.inventory)
        with self.assertRaisesRegex(ValueError, 'indexed source'):
            read_earlier_records(self.root)

    def test_changed_or_failed_earlier_state_blocks_export(self):
        self.state['status'] = 'failed'
        write_json(self.root, f'earlier-states/{self.key}.json', self.state)
        with self.assertRaisesRegex(ValueError, 'verification state'):
            read_archive_records(self.root)

    def test_verified_hash_cannot_replace_required_selection_provenance(self):
        for field in ('selection_reason', 'selection_provenance'):
            original = self.record[field]
            for value in (None, '', '   ', {'unsupported': 'structure'}):
                with self.subTest(field=field, value=value):
                    self.record[field] = value
                    self.state['record_sha256'] = record_digest(self.record)
                    write_record(self.root, f'earlier-records/{self.key}.yaml', self.record)
                    write_json(self.root, f'earlier-states/{self.key}.json', self.state)
                    with self.assertRaisesRegex(ValueError, 'selection provenance'):
                        read_earlier_records(self.root)
            self.record[field] = original

    def test_latest_timestamp_cannot_be_impersonated_by_earlier_record(self):
        self.record['latest_indexed_timestamp'] = self.capture['timestamp']
        write_record(self.root, f'earlier-records/{self.key}.yaml', self.record)
        with self.assertRaisesRegex(ValueError, 'full latest inventory'):
            read_earlier_records(self.root)

    def test_source_hash_corruption_fails_audit(self):
        path = self.root / 'cache/responses' / (self.record['response_sha256'] + '.bin')
        path.write_bytes(self.body + b'changed')
        report = audit_earlier_records(self.root, [])
        self.assertFalse(report['source_verified'])
        self.assertIn('hash mismatch', report['errors'][0])

    def test_earlier_omissions_require_retained_attribution_reference(self):
        soup, _ = source_soup(FIXTURE.read_bytes())
        soup.body.append(BeautifulSoup('<table><tr><td><span class="titleSection">Tutorial:</span>'
            '<p>Shared tutorial passage. Copyright Tae Kim</p></td></tr></table>', 'html.parser').table)
        body = soup.encode('shift_jis')
        parsed, _ = source_soup(body)
        scope = parsed.select('.titleSection')[-1].parent
        start = body.index(b'<td><span class="titleSection">Tutorial:')
        length = body.index(b'</td>', start) + len(b'</td>') - start
        reference = b'<meta charset="utf-8"><td><span class="titleSection">Tutorial:</span><p>Shared tutorial passage. Copyright Tae Kim</p></td>'
        reference_soup, _ = source_soup(reference)
        normalized = text(reference_soup.td)
        digest = hashlib.sha256(reference).hexdigest()
        review = {'label': CAPTURE['label'], 'id': 978, 'title_raw': text(parsed.select_one('.viewOnetitle')),
            'source_url': CAPTURE['original'], 'response_sha256': hashlib.sha256(body).hexdigest(),
            'section': 'Tutorial', 'section_html_sha256': section_reviews.section_hash(scope),
            'section_text_sha256': hashlib.sha256(text(scope).encode()).hexdigest(),
            'source_byte_offset': start, 'source_byte_length': length,
            'section_bytes_sha256': hashlib.sha256(body[start:start + length]).hexdigest(),
            'credits_raw': 'Tae Kim', 'decision': 'omit-from-CC-BY-SA-2.0-export', 'basis': 'Fixture review',
            'credit_evidence': {'reference_response_sha256': digest,
                'reference_section_html_sha256': section_reviews.section_hash(reference_soup.td),
                'matching_passages': [{'reference_text_offset': 0, 'text_length': len(normalized),
                                      'text_sha256': hashlib.sha256(normalized.encode()).hexdigest()}]}}
        with patch.object(section_reviews, 'REVIEWS', [review]):
            self.retain_source(body)
            report = audit_earlier_records(self.root, [])
            self.assertFalse(report['source_verified'], 'Missing attribution source must fail audit')
            backup = self.root.parent / 'archive-2015'
            backup.mkdir()
            cache_response(backup, f'cache/responses/{digest}.bin', reference)
            self.assertTrue(audit_earlier_records(self.root, [])['source_verified'])
            (backup / f'cache/responses/{digest}.bin').write_bytes(reference + b'changed')
            report = audit_earlier_records(self.root, [])
            self.assertFalse(report['source_verified'])
            self.assertIn('hash mismatch', report['errors'][0])
