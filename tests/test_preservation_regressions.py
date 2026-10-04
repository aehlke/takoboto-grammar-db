"""Reproductions of stale exports and missed normalized-data corruption."""

import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from bs4 import BeautifulSoup
from contextlib import closing, redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

from takoboto_grammar.archive import crawl_archive
from takoboto_grammar.archive_audit import audit_archive
from takoboto_grammar.archive_parser import parse_archive
from takoboto_grammar.cli import main
from takoboto_grammar.crawl import crawl
from takoboto_grammar.parser import ParseError, parse_entry
from takoboto_grammar.sqlite_verification import sqlite_signature, verify_sqlite_signature
from takoboto_grammar.storage import (
    build_sqlite, export_markdown, output_root, read_archive_records,
    read_records, write_json, write_record,
    record_digest, expand_archive_records, annotate_archive_record,
)
from test_archive import CAPTURE, FIXTURE


class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='takoboto-preservation-test-')).resolve()
        self.raw = (Path(__file__).parent / 'fixtures/entry725.html').read_bytes()
        self.record = parse_entry(self.raw, 725, 'original observation')
        self.inventory = {'entry_count': 1, 'entries': [{'id': 725, 'source_url': self.record['source_url']}]}

    def crawl(self, failure=None):
        owner = self
        class Replay:
            root = owner.root
            def get(self, url):
                if failure is not None:
                    raise failure
                return owner.raw, {'retrieved_at': owner.record['retrieved_at'],
                                   'sha256': owner.record['response_sha256']}
        with redirect_stdout(io.StringIO()):
            return crawl(Replay(), self.inventory, limit=1)

    def test_failed_current_refresh_preserves_record_but_blocks_both_exports(self):
        self.crawl()
        original = (self.root / 'records/725.yaml').read_bytes()
        self.assertTrue(self.crawl(ParseError('latest response is broken'))['failed'])
        self.assertEqual((self.root / 'records/725.yaml').read_bytes(), original)
        self.assertEqual(read_records(self.root), [self.record])
        with self.assertRaisesRegex(ValueError, 'latest attempt'):
            read_records(self.root, for_export=True)
        for command, options in [('build', ['--sqlite', str(self.root / 'exports/grammar.sqlite')]),
                                 ('update-markdown', ['--output', str(self.root / 'markdown')])]:
            with patch('sys.argv', ['takoboto-grammar', command, '--input', str(self.root), *options]), \
                 redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main()
                self.assertEqual(error.exception.code, 2)
        self.assertFalse((self.root / 'exports').exists())
        self.assertFalse((self.root / 'markdown').exists())
        self.crawl()
        self.assertEqual(read_records(self.root, for_export=True), [self.record])

    def test_interrupted_current_refresh_persists_pending_hold(self):
        self.crawl()
        with self.assertRaises(KeyboardInterrupt):
            self.crawl(KeyboardInterrupt())
        state = json.loads((self.root / 'states/725.json').read_text())
        self.assertEqual(state['status'], 'pending')
        with self.assertRaisesRegex(ValueError, 'pending'):
            read_records(self.root, for_export=True)

    def test_current_record_edit_invalidates_capture_state(self):
        self.crawl()
        altered = dict(self.record, meaning='manual source edit')
        write_record(self.root, 'records/725.yaml', altered)
        with self.assertRaisesRegex(ValueError, 'differs from its capture state'):
            read_records(self.root, for_export=True)

    def test_repeated_cached_current_crawl_keeps_record_and_state_bytes(self):
        self.crawl()
        path = self.root / 'records/725.yaml'
        original = path.read_bytes(), path.stat().st_mtime_ns
        state = (self.root / 'states/725.json').read_bytes()
        self.crawl()
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), original)
        self.assertEqual((self.root / 'states/725.json').read_bytes(), state)

    def test_legacy_current_failure_report_blocks_export(self):
        write_record(self.root, 'records/725.yaml', self.record)
        write_json(self.root, 'crawl-report.json', {'failed': [{'id': 725, 'error': 'refresh failed'}]})
        with self.assertRaisesRegex(ValueError, 'legacy crawl hold'):
            read_records(self.root, for_export=True)

    def test_legacy_current_record_cannot_shadow_a_newer_cached_response(self):
        write_record(self.root, 'records/725.yaml', self.record)
        key = hashlib.sha256(self.record['source_url'].encode()).hexdigest()
        write_json(self.root, f'cache/urls/{key}.json', {'url': self.record['source_url'], 'sha256': '0' * 64})
        with self.assertRaisesRegex(ValueError, 'latest cached response'):
            read_records(self.root, for_export=True)

    def test_warnings_and_conflicting_license_are_rejected_before_export_creation(self):
        cases = [dict(self.record, warnings=['New source field needs review']),
                 dict(self.record, license={'id': 'MIT', 'url': 'https://example.test/license'})]
        for record in cases:
            with self.subTest(case=record['license']):
                for writer, destination in [(build_sqlite, self.root / 'exports/grammar.sqlite'),
                                            (export_markdown, self.root / 'markdown')]:
                    with self.assertRaises(ValueError):
                        writer([record], destination)
                self.assertFalse((self.root / 'exports').exists())
                self.assertFalse((self.root / 'markdown').exists())

    def test_rediscovered_archive_revision_requires_rechecking_older_record(self):
        inventory = {'label_count': 1, 'cdx_complete': True,
                     'entries': [{'label': CAPTURE['label'], 'captures': [dict(CAPTURE)]}]}
        write_json(self.root, 'inventory.json', inventory)
        owner = self
        class Replay:
            root = owner.root
            def get(self, url):
                return FIXTURE.read_bytes(), {'retrieved_at': 'test', 'final_url': url}
        with redirect_stdout(io.StringIO()):
            crawl_archive(Replay(), inventory)
        self.assertEqual(len(read_archive_records(self.root)), 1)
        latest = dict(CAPTURE, timestamp='20210101000000',
                      archive_url=CAPTURE['archive_url'].replace(CAPTURE['timestamp'], '20210101000000'))
        inventory['entries'][0]['captures'].insert(0, latest)
        write_json(self.root, 'inventory.json', inventory)
        with self.assertRaisesRegex(ValueError, 'current inventory'):
            read_archive_records(self.root)
        self.assertEqual(len(read_archive_records(self.root, for_export=False)), 1)

    def test_output_parent_symlink_is_rejected_before_directory_creation(self):
        other = self.root / 'other'
        other.mkdir()
        (self.root / 'link').symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            output_root(self.root / 'link/output')
        self.assertFalse((other / 'output').exists())

    def test_normalized_column_corruption_is_detected_with_intact_full_record(self):
        path = build_sqlite([self.record], self.root / 'grammar.sqlite')
        with closing(sqlite3.connect(path)) as db:
            expected = sqlite_signature(db)
            original = db.execute('SELECT record_json FROM entries').fetchone()[0]
            db.execute("UPDATE translations SET body_text = 'lost translation' WHERE rowid = (SELECT min(rowid) FROM translations)")
            self.assertEqual(db.execute('SELECT record_json FROM entries').fetchone()[0], original)
            with self.assertRaisesRegex(ValueError, 'normalized content.*translations'):
                verify_sqlite_signature(db, expected)

    def test_missing_normalized_rows_are_detected_with_intact_full_record(self):
        path = build_sqlite([self.record], self.root / 'grammar.sqlite')
        with closing(sqlite3.connect(path)) as db:
            expected = sqlite_signature(db)
            original = db.execute('SELECT record_json FROM entries').fetchone()[0]
            # Only this fresh disposable database is changed, modeling an omission.
            db.execute('DELETE FROM comments')
            self.assertEqual(db.execute('SELECT record_json FROM entries').fetchone()[0], original)
            with self.assertRaisesRegex(ValueError, 'normalized content.*comments'):
                verify_sqlite_signature(db, expected)

    def test_schema_changes_are_detected(self):
        path = build_sqlite([self.record], self.root / 'grammar.sqlite')
        with closing(sqlite3.connect(path)) as db:
            expected = sqlite_signature(db)
            db.execute('CREATE VIEW omitted_data AS SELECT 1')
            with self.assertRaisesRegex(ValueError, 'schema differs'):
                verify_sqlite_signature(db, expected)

    def test_json_column_layout_does_not_invalidate_normalized_baseline(self):
        path = build_sqlite([self.record], self.root / 'grammar.sqlite')
        with closing(sqlite3.connect(path)) as db:
            expected = sqlite_signature(db)
            db.execute('UPDATE entries SET record_json = ?', (json.dumps(self.record, sort_keys=True, indent=2),))
            self.assertEqual(verify_sqlite_signature(db, expected), expected)

    def multiple_entry_body(self):
        import copy
        soup = BeautifulSoup(FIXTURE.read_bytes(), 'html.parser')
        first = soup.select_one('.viewOnetitle').find_parent('table')
        second = copy.copy(first)
        second.select_one('.viewOnetitle').string = 'Second meaning [reading] (ageku)'
        link = second.select_one('a[href*="addGrammar.php?id="]')
        link['href'] = '/pages/addGrammar.php?id=1649'
        first.insert_after(second)
        return soup.encode('shift_jis')

    def test_multiple_original_ids_keep_separate_contribution_tables(self):
        raw = self.multiple_entry_body()
        record = parse_archive(raw, CAPTURE, 'test')
        self.assertEqual(record['archive_schema_version'], 2)
        entries = expand_archive_records([record])
        self.assertEqual([r['id'] for r in entries], [978, 1649])
        self.assertEqual([len(r['examples']) for r in entries], [14, 14])
        self.assertEqual([len(r['notes']) for r in entries], [6, 6])
        self.assertEqual([len(r['comments']) for r in entries], [23, 23])
        annotate_archive_record(record, latest_indexed_timestamp=CAPTURE['timestamp'], selection_attempts=[])
        path = build_sqlite([], self.root / 'multiple.sqlite', [record])
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('SELECT source_id FROM archive_entries ORDER BY source_id').fetchall(), [(978,), (1649,)])
            self.assertEqual(db.execute('SELECT count(*) FROM archive_examples').fetchone()[0], 28)
            self.assertEqual(db.execute('SELECT count(*) FROM archive_comments').fetchone()[0], 46)
        pages = export_markdown([], self.root / 'markdown', [record])
        self.assertEqual(len(list((pages / 'jgram').glob('*.md'))), 2)

    def test_source_audit_detects_omitted_additional_original_id(self):
        raw = self.multiple_entry_body()
        inventory = {'label_count': 1, 'cdx_complete': True,
                     'entries': [{'label': CAPTURE['label'], 'captures': [dict(CAPTURE)]}]}
        write_json(self.root, 'inventory.json', inventory)
        owner = self
        class Replay:
            root = owner.root
            def get(self, url):
                return raw, {'retrieved_at': 'test', 'final_url': url}
        # The audit needs the original bytes independently of the extraction.
        from takoboto_grammar.storage import cache_response
        cache_response(self.root, f'cache/responses/{hashlib.sha256(raw).hexdigest()}.bin', raw)
        with redirect_stdout(io.StringIO()):
            crawl_archive(Replay(), inventory)
        report = audit_archive(self.root)
        self.assertTrue(report['parsed_records_verified'], report['errors'])
        self.assertEqual(report['counts']['entries'], 2)
        record = read_archive_records(self.root)[0]
        record['additional_entries'] = []
        key = hashlib.sha256(CAPTURE['label'].encode()).hexdigest()
        write_record(self.root, f'records/{key}.yaml', record)
        state = json.loads((self.root / f'states/{key}.json').read_text())
        state['record_sha256'] = record_digest(record)
        write_json(self.root, f'states/{key}.json', state)
        self.assertFalse(audit_archive(self.root)['parsed_records_verified'])

    def test_secondary_entry_provenance_cannot_disagree_with_shared_capture(self):
        record = parse_archive(self.multiple_entry_body(), CAPTURE, 'test')
        record['additional_entries'][0]['response_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'shared capture provenance'):
            build_sqlite([], self.root / 'multiple.sqlite', [record])
        self.assertFalse((self.root / 'multiple.sqlite').exists())

    def test_secondary_entry_must_share_earlier_revision_selection(self):
        record = parse_archive(self.multiple_entry_body(), CAPTURE, 'test')
        fields = dict(observation_kind='earlier-indexed-revision',
                      selected_indexed_timestamp=CAPTURE['timestamp'],
                      selection_reason='Recover earlier content', selection_provenance='fixture')
        annotate_archive_record(record, **fields)
        for field in fields:
            with self.subTest(field=field):
                additional = record['additional_entries'][0]
                original = additional.pop(field)
                try:
                    destination = self.root / f'{field}.sqlite'
                    with self.assertRaisesRegex(ValueError, 'shared capture provenance'):
                        build_sqlite([], destination, [record])
                    self.assertFalse(destination.exists())
                finally:
                    additional[field] = original

    def test_latest_replay_payload_digest_mismatch_requires_review(self):
        capture = dict(CAPTURE, digest='A' * 32)
        record = parse_archive(FIXTURE.read_bytes(), capture, 'test')
        self.assertTrue(any('indexed digest' in w for w in record['warnings']))
        with self.assertRaisesRegex(ValueError, 'review'):
            build_sqlite([], self.root / 'mismatched.sqlite', [record])
        self.assertFalse((self.root / 'mismatched.sqlite').exists())

    def test_no_entry_exclusion_cannot_override_an_indexed_payload_mismatch(self):
        body = (b'<title>JGram - The Japanese Grammar database</title>'
                b'<a href="https://creativecommons.org/licenses/by-sa/2.0/">License</a>'
                b'No entry exists for ageku - click here to add one')
        with self.assertRaisesRegex(ValueError, 'Exclusion payload differs'):
            parse_archive(body, dict(CAPTURE, digest='A' * 32), 'test')
