"""Warnings and replay provenance must gate historical publication consistently."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from takoboto_grammar.archive import crawl_archive
from takoboto_grammar.archive_audit import audit_archive
from takoboto_grammar.archive_feeds import parse_feed
from takoboto_grammar.parser import ParseError, parse_entry
from takoboto_grammar.storage import (cache_response, export_markdown,
    read_archive_records, record_digest, write_json)

FIXTURES = Path(__file__).parent / 'fixtures'
RAW = (FIXTURES / 'archive-ageku.html').read_bytes()
CAPTURE = {'label': 'ageku', 'original': 'http://jgram.org:80/pages/viewOne.php?tagE=ageku',
    'timestamp': '20200215021200',
    'archive_url': 'https://web.archive.org/web/20200215021200id_/http://jgram.org:80/pages/viewOne.php?tagE=ageku'}
FEED_CAPTURE = {'original': 'http://jgram.org/rss/jlpt1.xml', 'timestamp': '20200713231337',
    'archive_url': 'https://web.archive.org/web/20200713231337id_/http://jgram.org/rss/jlpt1.xml'}
KEY = hashlib.sha256(b'ageku').hexdigest()


class RefinementTests(unittest.TestCase):
    def root(self):
        return Path(tempfile.mkdtemp(prefix='takoboto-refinement-')).resolve()

    def test_fallback_warning_holds_record_but_preserves_evidence(self):
        root = self.root()
        older = dict(CAPTURE, timestamp='20070411155229',
            archive_url=CAPTURE['archive_url'].replace(CAPTURE['timestamp'], '20070411155229'))
        class Replay:
            def get(self, url):
                if url == CAPTURE['archive_url']:
                    raise ParseError('latest replay unavailable')
                return RAW, {'retrieved_at': 'test', 'final_url': url}
        replay = Replay()
        replay.root = root
        report = crawl_archive(replay, {'label_count': 1, 'cdx_complete': True,
            'entries': [{'label': 'ageku', 'captures': [CAPTURE, older]}]})
        self.assertTrue(report['warnings'])
        state = json.loads((root / f'states/{KEY}.json').read_text())
        self.assertEqual(state['status'], 'review_required')
        self.assertTrue(report['review_required'])
        record = read_archive_records(root, for_export=False)[0]
        self.assertEqual(record['archive_timestamp'], older['timestamp'])
        self.assertEqual(len(record['notes']), 6)
        with self.assertRaisesRegex(ValueError, 'review'):
            read_archive_records(root)

    def test_legacy_parsed_state_cannot_export_warning_bearing_record(self):
        root = self.root()
        class Replay:
            def get(self, url):
                return RAW, {'retrieved_at': 'test', 'final_url': url}
        replay = Replay()
        replay.root = root
        crawl_archive(replay, {'label_count': 1, 'entries': [{'label': 'ageku', 'captures': [CAPTURE]}]})
        record = read_archive_records(root)[0]
        record['warnings'].append('Unfamiliar source content requires review')
        write_json(root, f'records/{KEY}.json', record)
        state = json.loads((root / f'states/{KEY}.json').read_text())
        state.update(status='parsed', record_sha256=record_digest(record))
        write_json(root, f'states/{KEY}.json', state)
        with self.assertRaisesRegex(ValueError, 'review'):
            read_archive_records(root)
        self.assertEqual(read_archive_records(root, for_export=False), [record])

    def test_exclusion_requires_consistent_replay_timestamp_and_original(self):
        for field, value in [('archive_url', CAPTURE['archive_url'].replace(CAPTURE['timestamp'], '20070411155229')),
                             ('original', CAPTURE['original'] + '&date=2019-2-15')]:
            with self.subTest(field=field):
                root = self.root()
                write_json(root, 'inventory.json', {'cdx_complete': True,
                    'entries': [{'label': 'ageku', 'captures': [CAPTURE]}]})
                raw = RAW.replace(b'Category</b>: <i>grammar', b'Category</b>: <i>social')
                digest = hashlib.sha256(raw).hexdigest()
                cache_response(root, f'cache/responses/{digest}.bin', raw)
                write_json(root, f'states/{KEY}.json', {'label': 'ageku', 'status': 'excluded',
                    'latest_indexed_timestamp': CAPTURE['timestamp'], 'capture': dict(CAPTURE, **{field: value}),
                    'response_sha256': digest, 'retrieved_at': 'test'})
                report = audit_archive(root)
                self.assertFalse(report['historical_coverage_complete'])
                self.assertEqual(report['verified_exclusions'], [])
                self.assertEqual(report['pending_labels'], ['ageku'])
                self.assertTrue(report['errors'])

    def test_feed_parser_rejects_out_of_scope_or_inconsistent_capture(self):
        raw = (FIXTURES / 'archive-jlpt1.xml').read_bytes()
        cases = [dict(FEED_CAPTURE, archive_url=FEED_CAPTURE['archive_url'].replace('http://jgram.org/', 'http://evil.example/')),
            dict(FEED_CAPTURE, timestamp='20050101000000'),
            dict(FEED_CAPTURE, original='http://evil.example/rss/jlpt1.xml'),
            dict(FEED_CAPTURE, archive_url=FEED_CAPTURE['archive_url'] + '?edit=1')]
        for capture in cases:
            with self.subTest(capture=capture), self.assertRaises(ParseError):
                parse_feed(raw, capture, {'retrieved_at': 'test'}, {'madashimo': 123})
        with self.assertRaises(ParseError):
            parse_feed(raw, FEED_CAPTURE, {'retrieved_at': 'test',
                'final_url': FEED_CAPTURE['archive_url'].replace('http://jgram.org/', 'http://evil.example/')}, {'madashimo': 123})

    def test_feed_redirect_preserves_actual_original_and_capture(self):
        raw = (FIXTURES / 'archive-jlpt1.xml').read_bytes()
        actual = FEED_CAPTURE['archive_url'].replace(FEED_CAPTURE['timestamp'], '20200714010101').replace('http://jgram.org/', 'https://www.jgram.org/')
        record = parse_feed(raw, FEED_CAPTURE, {'retrieved_at': 'test', 'final_url': actual}, {'madashimo': 123})
        self.assertEqual(record['source_url'], 'https://www.jgram.org/rss/jlpt1.xml')
        self.assertEqual(record['archive_timestamp'], '20200714010101')
        self.assertEqual(record['archive_url'], actual)
        self.assertTrue(record['warnings'])
        reparsed = parse_feed(raw, {'original': record['source_url'], 'timestamp': record['archive_timestamp'],
            'archive_url': actual}, {'retrieved_at': 'test'}, {'madashimo': 123})
        self.assertEqual(record['items'], reparsed['items'])

    def test_offline_feed_migration_rejects_out_of_scope_replay(self):
        root, current = self.root(), self.root()
        write_json(root, 'inventory.json', {'cdx_complete': True, 'entries': []})
        current_raw = (FIXTURES / 'entry725.html').read_bytes().replace(b'ga-2', b'madashimo')
        current_record = parse_entry(current_raw, 725, 'test')
        write_json(current, 'records/725.json', current_record)
        cache_response(current, f"cache/responses/{current_record['response_sha256']}.html", current_raw)
        raw = (FIXTURES / 'archive-jlpt1.xml').read_bytes()
        feed = parse_feed(raw, FEED_CAPTURE, {'retrieved_at': 'test'}, {'madashimo': 725})
        feed['archive_url'] = feed['archive_url'].replace('http://jgram.org/', 'http://evil.example/')
        write_json(root, 'feeds/jlpt1.json', feed)
        cache_response(root, f"cache/responses/{feed['response_sha256']}.bin", raw)
        url_key = hashlib.sha256(feed['archive_url'].encode()).hexdigest()
        write_json(root, f'cache/urls/{url_key}.json', {'url': feed['archive_url'],
            'final_url': feed['archive_url'], 'sha256': feed['response_sha256']})
        with patch('httpx.Client.send', side_effect=AssertionError('offline')) as network:
            report = audit_archive(root, current, record_verification=True)
            network.assert_not_called()
        self.assertFalse(report['export_ready'])
        self.assertTrue(report['rss']['errors'])
        self.assertEqual(report['verification_states_written'], {'entries': 0, 'feeds': 0})
        self.assertFalse((root / 'feed-states').exists())

    def test_rss_markdown_preserves_explicit_author_and_creator(self):
        raw = (FIXTURES / 'archive-jlpt1.xml').read_bytes().replace(b'<item>',
            b'<item><author>A &amp; B</author><dc:creator xmlns:dc="http://purl.org/dc/elements/1.1/">C*D</dc:creator>', 1)
        record = parse_feed(raw, FEED_CAPTURE, {'retrieved_at': 'test'}, {'madashimo': 123})
        root = self.root()
        export_markdown([], root / 'markdown', archive_feeds=[record])
        page = (root / 'markdown/jgram/rss-jlpt1.md').read_text()
        self.assertIn('Author: A & B', page)
        self.assertIn('Creator: C\\*D', page)

    def test_feed_license_declarations_accept_only_matching_cc_version(self):
        raw = (FIXTURES / 'archive-jlpt1.xml').read_bytes()
        for license_text in ('CC-BY-NC-SA-2.0', 'CC-BY-SA-4.0', 'CC-BY-ND-2.0',
                             'Creative-Commons-BY-NC-SA-2.0', 'CC BY-SA 3.0',
                             'CC-BY-SA-2.0 and CC-BY-NC-SA-2.0'):
            with self.subTest(license=license_text):
                modified = raw.replace(b'<channel>', b'<channel><copyright>' +
                    license_text.encode() + b'</copyright>', 1)
                record = parse_feed(modified, FEED_CAPTURE, {'retrieved_at': 'test'}, {'madashimo': 123})
                self.assertTrue(record['review_required'])
                self.assertIsNone(record['review_required'][0]['position'])
        for license_text in ('CC-BY-SA-2.0', 'CC BY-SA 2.0', 'Creative Commons BY-SA 2.0'):
            with self.subTest(license=license_text):
                modified = raw.replace(b'<channel>', b'<channel><copyright>' +
                    license_text.encode() + b'</copyright>', 1)
                self.assertFalse(parse_feed(modified, FEED_CAPTURE, {'retrieved_at': 'test'},
                    {'madashimo': 123})['review_required'])
