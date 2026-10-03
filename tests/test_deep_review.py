"""Source integrity and eligibility regressions found during the deeper review."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

from takoboto_grammar.archive import crawl_archive
from takoboto_grammar.archive_audit import audit_archive
from takoboto_grammar.cli import verified_feed_labels
from takoboto_grammar.archive_parser import parse_archive
from takoboto_grammar.archive_feeds import crawl_feeds, parse_feed
from takoboto_grammar.parser import ParseError, parse_entry, segments
from takoboto_grammar.storage import cache_response, read_archive_records, read_archive_feeds, write_json

FIXTURES = Path(__file__).parent / 'fixtures'
RAW = (FIXTURES / 'archive-ageku.html').read_bytes()
CAPTURE = {'label': 'ageku', 'original': 'http://jgram.org:80/pages/viewOne.php?tagE=ageku',
           'timestamp': '20200215021200',
           'archive_url': 'https://web.archive.org/web/20200215021200id_/http://jgram.org:80/pages/viewOne.php?tagE=ageku'}
KEY = hashlib.sha256(b'ageku').hexdigest()


class Replay:
    def __init__(self, root, raw):
        self.root, self.raw = root, raw

    def get(self, url):
        digest = hashlib.sha256(self.raw).hexdigest()
        cache_response(self.root, f'cache/responses/{digest}.bin', self.raw)
        return self.raw, {'sha256': digest, 'retrieved_at': 'test', 'final_url': url}


class DeepReviewTests(unittest.TestCase):
    def root(self):
        return Path(tempfile.mkdtemp(prefix='takoboto-deep-review-')).resolve()

    def inventory(self, root):
        inventory = {'label_count': 1, 'cdx_complete': True,
                     'entries': [{'label': 'ageku', 'captures': [CAPTURE]}]}
        write_json(root, 'inventory.json', inventory)
        return inventory

    def test_license_blocked_refresh_prevents_stale_export_across_later_runs(self):
        root = self.root()
        inventory = self.inventory(root)
        crawl_archive(Replay(root, RAW), inventory)
        self.assertEqual(len(read_archive_records(root)), 1)
        conflicting = RAW + b'<a href="https://creativecommons.org/licenses/by-nc-sa/2.0/">license</a>'
        report = crawl_archive(Replay(root, conflicting), inventory)
        self.assertTrue(report['review_required'])
        self.assertTrue((root / f'records/{KEY}.json').exists(), 'keep earlier evidence')
        # Overwriting the run report must not erase the label's eligibility hold.
        write_json(root, 'crawl-report.json', {'parsed': [], 'review_required': []})
        with self.assertRaisesRegex(ValueError, 'not exportable'):
            read_archive_records(root)

    def test_verified_non_grammar_exclusion_can_complete_coverage(self):
        root = self.root()
        inventory = self.inventory(root)
        unrelated = RAW.replace(b'Category</b>: <i>grammar', b'Category</b>: <i>social')
        crawl_archive(Replay(root, unrelated), inventory)
        report = audit_archive(root)
        self.assertEqual(report['pending_labels'], [])
        self.assertTrue(report['historical_coverage_complete'])
        self.assertEqual(len(report['verified_exclusions']), 1)

    def test_fake_exclusion_report_cannot_establish_coverage(self):
        root = self.root()
        self.inventory(root)
        write_json(root, 'crawl-report.json', {'excluded': [{'label': 'ageku', 'reason': 'trust me'}]})
        report = audit_archive(root)
        self.assertEqual(report['pending_labels'], ['ageku'])
        self.assertFalse(report['historical_coverage_complete'])

    def test_archive_audit_detects_mutated_header_meaning_and_relationship(self):
        for key in ['title', 'reading', 'meaning', 'sections', 'related_entries']:
            with self.subTest(field=key):
                root = self.root()
                inventory = self.inventory(root)
                crawl_archive(Replay(root, RAW), inventory)
                path = root / f'records/{KEY}.json'
                record = json.loads(path.read_text())
                if key == 'sections':
                    record[key][0]['text'] = 'CORRUPTED'
                elif key == 'related_entries':
                    record[key][0]['annotation_text'] = 'CORRUPTED'
                else:
                    record[key] = 'CORRUPTED'
                write_json(root, f'records/{KEY}.json', record)
                self.assertFalse(audit_archive(root)['parsed_records_verified'])

    def test_incomplete_cdx_inventory_never_claims_complete_crawl(self):
        root = self.root()
        inventory = dict(self.inventory(root), cdx_complete=False)
        self.assertFalse(crawl_archive(Replay(root, RAW), inventory)['complete'])

    def test_inline_segments_preserve_breaks_and_skip_html_comments(self):
        node = BeautifulSoup('<div>前<br>後<!-- invisible --><span>続き</span></div>', 'html.parser').div
        self.assertEqual(''.join(s['text'] for s in segments(node)), '前\n後続き')

    def test_nonplaceholder_user_content_is_retained_and_warns(self):
        body = (FIXTURES / 'entry725.html').read_bytes()
        extra = b'<div id="editable_UserPhrase_987"><div class="GrammarPartDiv"><div>New contribution</div></div></div>'
        record = parse_entry(body.replace(b'</body>', extra + b'</body>'), 725, 'test')
        self.assertTrue(any(s['body_text'] == 'New contribution' for s in record['sections']))
        self.assertTrue(record['warnings'])

    def test_feed_channel_license_conflict_is_reported_before_export(self):
        raw = (FIXTURES / 'archive-jlpt1.xml').read_bytes()
        capture = {'original': 'http://jgram.org/rss/jlpt1.xml', 'timestamp': '20200713231337',
                   'archive_url': 'https://web.archive.org/web/20200713231337id_/http://jgram.org/rss/jlpt1.xml'}
        for declaration in [b'<copyright>CC BY-NC-SA 2.0</copyright>',
                            b'<copyright>All rights reserved</copyright>', b'<license>MIT</license>']:
            modified = raw.replace(b'<channel>', b'<channel>' + declaration, 1)
            feed = parse_feed(modified, capture, {'retrieved_at': 'test'}, {'madashimo': 123})
            self.assertTrue(feed['review_required'])

    def test_review_required_feed_is_auditable_without_crashing(self):
        root = self.root()
        self.inventory(root)
        raw = (FIXTURES / 'archive-jlpt1.xml').read_bytes()
        capture = {'original': 'http://jgram.org/rss/jlpt1.xml', 'timestamp': '20200713231337',
                   'archive_url': 'https://web.archive.org/web/20200713231337id_/http://jgram.org/rss/jlpt1.xml'}
        record = parse_feed(raw, capture, {'retrieved_at': 'test'}, {})
        write_json(root, 'feeds/jlpt1.json', record)
        cache_response(root, f"cache/responses/{record['response_sha256']}.bin", raw)
        report = audit_archive(root)
        self.assertFalse(report['rss']['captured_records_verified'])
        self.assertTrue(report['rss']['review_required'])

    def test_archive_audit_rejects_a_forged_exclusion_state(self):
        root = self.root()
        inventory = self.inventory(root)
        crawl_archive(Replay(root, RAW), inventory)
        state = json.loads((root / f'states/{KEY}.json').read_text())
        state['status'] = 'excluded'
        write_json(root, f'states/{KEY}.json', state)
        report = audit_archive(root)
        self.assertFalse(report['historical_coverage_complete'])
        self.assertTrue(report['errors'])
        self.assertEqual(report['verified_exclusions'], [])

    def test_pending_or_failed_archive_refresh_blocks_older_record(self):
        root = self.root()
        inventory = self.inventory(root)
        crawl_archive(Replay(root, RAW), inventory)
        state = json.loads((root / f'states/{KEY}.json').read_text())
        for status in ['pending', 'failed', 'excluded']:
            state['status'] = status
            write_json(root, f'states/{KEY}.json', state)
            with self.assertRaisesRegex(ValueError, 'not exportable'):
                read_archive_records(root)

    def test_failed_feed_refresh_blocks_older_feed(self):
        root = self.root()
        raw = (FIXTURES / 'archive-jlpt1.xml').read_bytes()
        capture = {'original': 'http://jgram.org/rss/updates.xml', 'timestamp': '20200713231337',
                   'archive_url': 'https://web.archive.org/web/20200713231337id_/http://jgram.org/rss/updates.xml'}
        feed = parse_feed(raw, capture, {'retrieved_at': 'test'}, {'madashimo': 123})
        write_json(root, 'feeds/updates.json', feed)
        class Broken:
            def get(self, url):
                raise ParseError('latest feed unavailable')
        fetcher = Broken()
        fetcher.root = root
        report = crawl_feeds(fetcher, {'madashimo': 123})
        self.assertTrue(report['failed'])
        with self.assertRaisesRegex(ValueError, 'not exportable'):
            read_archive_feeds(root)

    def test_feed_audit_detects_mutated_reader_fragment(self):
        root = self.root()
        self.inventory(root)
        raw = (FIXTURES / 'archive-jlpt1.xml').read_bytes()
        capture = {'original': 'http://jgram.org/rss/jlpt1.xml', 'timestamp': '20200713231337',
                   'archive_url': 'https://web.archive.org/web/20200713231337id_/http://jgram.org/rss/jlpt1.xml'}
        feed = parse_feed(raw, capture, {'retrieved_at': 'test'}, {'madashimo': 123})
        feed['items'][0]['body_html'] = 'CORRUPTED'
        write_json(root, 'feeds/jlpt1.json', feed)
        cache_response(root, f"cache/responses/{feed['response_sha256']}.bin", raw)
        self.assertFalse(audit_archive(root)['rss']['captured_records_verified'])

    def test_fake_creative_commons_host_is_not_license_evidence(self):
        with self.assertRaises(ParseError):
            parse_archive(RAW.replace(b'creativecommons.org/licenses/', b'creativecommons.org.example/licenses/'), CAPTURE, 'test')

    def test_feed_eligibility_includes_verified_historical_labels_and_respects_holds(self):
        root = self.root()
        crawl_archive(Replay(root, RAW), self.inventory(root))
        self.assertEqual(verified_feed_labels([], root), {'ageku': 978})
        state = json.loads((root / f'states/{KEY}.json').read_text())
        state['status'] = 'review_required'
        write_json(root, f'states/{KEY}.json', state)
        self.assertEqual(verified_feed_labels([], root), {})

    def test_latest_capture_discrepancy_is_not_hidden_by_deleting_warnings(self):
        root = self.root()
        inventory = self.inventory(root)
        crawl_archive(Replay(root, RAW), inventory)
        record = json.loads((root / f'records/{KEY}.json').read_text())
        record['archive_timestamp'] = '20070411155229'
        record['archive_url'] = CAPTURE['archive_url'].replace(CAPTURE['timestamp'], record['archive_timestamp'])
        record['warnings'] = []
        write_json(root, f'records/{KEY}.json', record)
        report = audit_archive(root)
        self.assertFalse(report['parsed_records_verified'])
        self.assertTrue(report['warnings'])
