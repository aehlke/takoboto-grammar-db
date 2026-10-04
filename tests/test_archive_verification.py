"""Offline migration must establish eligibility rather than trust old records."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from takoboto_grammar.archive_audit import audit_archive
from takoboto_grammar.cli import verified_feed_labels
from takoboto_grammar.archive_parser import parse_archive
from takoboto_grammar.parser import parse_entry
from takoboto_grammar.storage import cache_response, read_archive_records, read_archive_feeds, write_json
from takoboto_grammar.archive_feeds import parse_feed

FIXTURES = Path(__file__).parent / 'fixtures'
RAW = (FIXTURES / 'archive-ageku.html').read_bytes()
CAPTURE = {'label': 'ageku', 'original': 'http://jgram.org:80/pages/viewOne.php?tagE=ageku',
           'timestamp': '20200215021200',
           'archive_url': 'https://web.archive.org/web/20200215021200id_/http://jgram.org:80/pages/viewOne.php?tagE=ageku'}
KEY = hashlib.sha256(b'ageku').hexdigest()


class VerificationTests(unittest.TestCase):
    def root(self):
        return Path(tempfile.mkdtemp(prefix='takoboto-verification-')).resolve()

    def legacy(self, root, raw=RAW):
        record = parse_archive(raw, CAPTURE, 'test', [978])
        record['latest_indexed_timestamp'] = CAPTURE['timestamp']
        record['selection_attempts'] = []
        write_json(root, 'inventory.json', {'cdx_complete': True, 'entries': [{'label': 'ageku', 'captures': [CAPTURE]}]})
        write_json(root, f'records/{KEY}.json', record)
        cache_response(root, f"cache/responses/{record['response_sha256']}.bin", raw)
        self.url_metadata(root, CAPTURE['archive_url'], record['response_sha256'])
        return record

    def url_metadata(self, root, url, digest):
        key = hashlib.sha256(url.encode()).hexdigest()
        write_json(root, f'cache/urls/{key}.json', {'url': url, 'final_url': url, 'sha256': digest})

    def current(self, root, gid=978, label='ageku'):
        raw = (FIXTURES / 'entry725.html').read_bytes().replace(b'_725', f'_{gid}'.encode()).replace(b'ga-2', label.encode())
        record = parse_entry(raw, gid, 'test')
        write_json(root, f'records/{gid}.json', record)
        cache_response(root, f"cache/responses/{record['response_sha256']}.html", raw)
        return record

    def test_legacy_export_requires_offline_verification(self):
        root = self.root()
        self.legacy(root)
        with self.assertRaisesRegex(ValueError, 'verification state'):
            read_archive_records(root)
        self.assertEqual(len(read_archive_records(root, for_export=False)), 1)

    def test_migration_writes_states_without_changing_records_or_using_network(self):
        root = self.root()
        record = self.legacy(root)
        before = (root / f'records/{KEY}.json').read_bytes()
        with patch('httpx.Client.send', side_effect=AssertionError('offline')) as network:
            report = audit_archive(root, record_verification=True)
            network.assert_not_called()
        self.assertEqual(report['verification_states_written'], {'entries': 1, 'feeds': 0})
        self.assertEqual(read_archive_records(root), [record])
        self.assertEqual((root / f'records/{KEY}.json').read_bytes(), before)
        self.assertTrue(report['export_ready'])
        again = audit_archive(root, record_verification=True)
        self.assertEqual(again['verification_states_written'], {'entries': 0, 'feeds': 0})

    def test_record_and_claimed_state_cannot_prove_id_membership(self):
        root = self.root()
        raw = RAW.replace(b'Category</b>: <i>grammar', b'Category</b>: <i>social')
        record = self.legacy(root, raw)
        write_json(root, f'states/{KEY}.json', {'label': 'ageku', 'status': 'parsed', 'eligible_ids': [978],
                   'response_sha256': record['response_sha256'], 'capture': CAPTURE})
        report = audit_archive(root)
        self.assertFalse(report['parsed_records_verified'])
        self.assertTrue(report['errors'])

    def test_captured_current_page_proves_id_membership(self):
        root, current = self.root(), self.root()
        self.current(current)
        self.legacy(root, RAW.replace(b'Category</b>: <i>grammar', b'Category</b>: <i>social'))
        report = audit_archive(root, takoboto=current, record_verification=True)
        self.assertTrue(report['parsed_records_verified'])
        self.assertTrue(report['export_ready'])
        self.assertEqual(report['current_membership']['verified_entries'], 1)

    def test_missing_or_corrupt_current_capture_prevents_migration(self):
        root, current = self.root(), self.root()
        self.legacy(root)
        record = self.current(current)
        cache = current / 'cache/responses' / (record['response_sha256'] + '.html')
        cache.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            audit_archive(root, takoboto=current, record_verification=True)
        self.assertFalse((root / 'states').exists())

    def test_migration_does_not_lift_existing_hold(self):
        root = self.root()
        self.legacy(root)
        state = {'label': 'ageku', 'status': 'review_required'}
        write_json(root, f'states/{KEY}.json', state)
        before = (root / f'states/{KEY}.json').read_bytes()
        report = audit_archive(root, record_verification=True)
        self.assertFalse(report['export_ready'])
        self.assertEqual(report['verification_states_written']['entries'], 0)
        self.assertEqual((root / f'states/{KEY}.json').read_bytes(), before)

    def test_migration_respects_remaining_legacy_hold_report(self):
        root = self.root()
        self.legacy(root)
        write_json(root, 'crawl-report.json', {'review_required': [{'label': 'ageku', 'reason': 'license'}]})
        report = audit_archive(root, record_verification=True)
        self.assertFalse(report['export_ready'])
        self.assertFalse((root / 'states').exists())

    def test_invalid_record_aborts_batch_before_any_state_is_written(self):
        root = self.root()
        self.legacy(root)
        record = json.loads((root / f'records/{KEY}.json').read_text())
        record['meaning'] = 'corrupt'
        write_json(root, f'records/{KEY}.json', record)
        report = audit_archive(root, record_verification=True)
        self.assertFalse(report['export_ready'])
        self.assertEqual(report['verification_states_written']['entries'], 0)
        self.assertFalse((root / 'states').exists())

    def test_invalid_earlier_revision_aborts_entry_and_feed_migration(self):
        root, current = self.root(), self.root()
        self.legacy(root)
        self.current(current, 123, 'madashimo')
        raw = (FIXTURES / 'archive-jlpt1.xml').read_bytes()
        capture = {'original': 'http://jgram.org/rss/jlpt1.xml', 'timestamp': '20200713231337',
                   'archive_url': 'https://web.archive.org/web/20200713231337id_/http://jgram.org/rss/jlpt1.xml'}
        feed = parse_feed(raw, capture, {'retrieved_at': 'test'}, {'madashimo': 123})
        write_json(root, 'feeds/jlpt1.json', feed)
        cache_response(root, f"cache/responses/{feed['response_sha256']}.bin", raw)
        self.url_metadata(root, capture['archive_url'], feed['response_sha256'])
        write_json(root, 'earlier-records/invalid.json', {'label': 'ageku', 'archive_timestamp': 'bad'})
        report = audit_archive(root, takoboto=current, record_verification=True)
        self.assertFalse(report['export_ready'])
        self.assertTrue(report['earlier_revisions']['errors'])
        self.assertEqual(report['verification_states_written'], {'entries': 0, 'feeds': 0})
        self.assertFalse((root / 'states').exists())
        self.assertFalse((root / 'feed-states').exists())

    def test_legacy_feed_cannot_export_or_verify_its_own_label(self):
        root = self.root()
        self.legacy(root)
        raw = (FIXTURES / 'archive-jlpt1.xml').read_bytes()
        capture = {'original': 'http://jgram.org/rss/jlpt1.xml', 'timestamp': '20200713231337',
                   'archive_url': 'https://web.archive.org/web/20200713231337id_/http://jgram.org/rss/jlpt1.xml'}
        feed = parse_feed(raw, capture, {'retrieved_at': 'test'}, {'madashimo': 123})
        write_json(root, 'feeds/jlpt1.json', feed)
        cache_response(root, f"cache/responses/{feed['response_sha256']}.bin", raw)
        self.url_metadata(root, capture['archive_url'], feed['response_sha256'])
        with self.assertRaisesRegex(ValueError, 'verification state'):
            read_archive_feeds(root)
        report = audit_archive(root, record_verification=True)
        self.assertFalse(report['rss']['captured_records_verified'])
        self.assertEqual(report['verification_states_written'], {'entries': 0, 'feeds': 0})
        current = self.root()
        self.current(current, 123, 'madashimo')
        report = audit_archive(root, takoboto=current, record_verification=True)
        self.assertTrue(report['rss']['captured_records_verified'])
        self.assertEqual(report['verification_states_written'], {'entries': 1, 'feeds': 1})
        self.assertEqual(read_archive_feeds(root), [feed])

    def test_newer_cached_response_blocks_migration_after_legacy_report_is_lost(self):
        root = self.root()
        self.legacy(root)
        conflicting = RAW + b'<a href="https://creativecommons.org/licenses/by-nc-sa/2.0/">license</a>'
        digest = hashlib.sha256(conflicting).hexdigest()
        cache_response(root, f'cache/responses/{digest}.bin', conflicting)
        self.url_metadata(root, CAPTURE['archive_url'], digest)
        report = audit_archive(root, record_verification=True)
        self.assertFalse(report['export_ready'])
        self.assertTrue(any('latest cached response' in item['error'] for item in report['errors']))
        self.assertFalse((root / 'states').exists())

    def test_edit_after_migration_invalidates_export_state(self):
        root = self.root()
        record = self.legacy(root)
        self.assertTrue(audit_archive(root, record_verification=True)['export_ready'])
        record['meaning'] = 'edited after verification'
        write_json(root, f'records/{KEY}.json', record)
        with self.assertRaisesRegex(ValueError, 'differs from verification state'):
            read_archive_records(root)

    def test_wrong_replay_in_existing_state_cannot_report_export_ready(self):
        root = self.root()
        self.legacy(root)
        self.assertTrue(audit_archive(root, record_verification=True)['export_ready'])
        state = json.loads((root / f'states/{KEY}.json').read_text())
        state['capture']['archive_url'] += '&different=1'
        write_json(root, f'states/{KEY}.json', state)
        report = audit_archive(root, record_verification=True)
        self.assertFalse(report['export_ready'])
        self.assertEqual(report['verification_states_written']['entries'], 0)

    def test_wrong_replay_state_cannot_establish_feed_eligibility(self):
        root = self.root()
        self.legacy(root)
        self.assertTrue(audit_archive(root, record_verification=True)['export_ready'])
        self.assertEqual(verified_feed_labels([], root), {'ageku': 978})
        state_path = root / f'states/{KEY}.json'
        state = json.loads(state_path.read_text())
        state['capture']['archive_url'] += '&different=1'
        write_json(root, f'states/{KEY}.json', state)
        before = state_path.read_bytes()
        self.assertEqual(verified_feed_labels([], root), {})
        with self.assertRaisesRegex(ValueError, 'not exportable'):
            read_archive_records(root)
        self.assertEqual(state_path.read_bytes(), before)
