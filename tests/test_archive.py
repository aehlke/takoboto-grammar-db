import hashlib
import json
import sqlite3
import tempfile
import unittest
import io
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from takoboto_grammar.archive import ArchiveAccessError, ArchiveFetcher, allowed_archive_url, parse_cdx, crawl_archive, discover_archive, original_label
from takoboto_grammar.archive_parser import NotGrammar, parse_archive
from takoboto_grammar.storage import build_sqlite, export_markdown
from takoboto_grammar.storage import write_json
from takoboto_grammar.archive_audit import audit_archive
from takoboto_grammar.archive_feeds import parse_feed

FIXTURE = Path(__file__).parent / 'fixtures/archive-ageku.html'
CAPTURE = {'label': 'ageku', 'original': 'http://jgram.org:80/pages/viewOne.php?tagE=ageku',
    'timestamp': '20200215021200', 'archive_url': 'https://web.archive.org/web/20200215021200id_/http://jgram.org:80/pages/viewOne.php?tagE=ageku'}


class ArchiveTests(unittest.TestCase):
    def record(self):
        return parse_archive(FIXTURE.read_bytes(), CAPTURE, '2026-10-03T05:40:00Z')

    def test_original_jgram_notes_and_annotations(self):
        r = self.record()
        self.assertEqual(r['id'], 978)
        self.assertEqual(r['title'], '挙げ句')
        self.assertEqual(r['jlpt_level_original'], '0')
        self.assertEqual(r['encoding'], 'shift_jis')
        self.assertEqual(len(r['notes']), 6)
        self.assertEqual(len(r['examples']), 14)
        self.assertEqual(len(r['comments']), 23)
        self.assertEqual(len(r['related_entries']), 3)
        self.assertEqual(r['notes'][3]['credits_raw'], 'MightyAtom')
        self.assertEqual(r['notes'][3]['text'], 'Often used with さんざん')
        self.assertIn('usually used for bad outcomes', r['related_entries'][0]['annotation_text'])
        self.assertNotIn('yatto', r['related_entries'][0]['annotation_text'])
        self.assertIn('http://jgram.org:80/pages/viewOne.php?tagE=kekkyoku', r['related_entries'][0]['annotation_html'])
        self.assertIsNone(r['original_created_at'])

    def test_scope_category_license_and_replay_shape(self):
        body = FIXTURE.read_bytes()
        with self.assertRaises(NotGrammar):
            parse_archive(body.replace(b'Category</b>: <i>grammar', b'Category</b>: <i>social'), CAPTURE, 'now')
        with self.assertRaises(ValueError):
            parse_archive(body.replace(b'/by-sa/2.0/', b'/by-nc/3.0/'), CAPTURE, 'now')
        with self.assertRaises(ValueError):
            parse_archive(b'<html>Archive unavailable</html>', CAPTURE, 'now')
        lesson = body.replace(b'Category</b>: <i>grammar', b'Category</b>: <i>lesson')
        self.assertEqual(parse_archive(lesson, CAPTURE, 'now')['category'], 'lesson')
        with self.assertRaisesRegex(ValueError, 'conflicting license'):
            parse_archive(lesson + b'<a href="https://creativecommons.org/licenses/by-nc-sa/2.0/">lesson license</a>', CAPTURE, 'now')
        self.assertIn('<strong>', self.record()['examples'][0]['body_html'])

    def test_latest_selection_and_safe_date_variant(self):
        root = Path(tempfile.mkdtemp(prefix='takoboto-archive-test-')).resolve()
        dated = CAPTURE['original'] + '&date=2019-2-15'
        self.assertEqual(original_label(dated), 'ageku')
        self.assertIsNone(original_label(CAPTURE['original'] + '&delete=Y'))
        rows = [['timestamp', 'original', 'mimetype', 'digest'],
            ['20070411155229', CAPTURE['original'], 'text/html', 'OLD'],
            ['20200215021200', dated, 'text/html', 'NEW'],
            ['20190101000000', CAPTURE['original'], 'text/html', 'NEW']]
        class CachedCDX:
            def get(self, url):
                return json.dumps(rows).encode(), {'sha256': 'test', 'retrieved_at': 'now'}
        fetcher = CachedCDX()
        fetcher.root = root
        inventory = discover_archive(fetcher)
        self.assertEqual(inventory['label_count'], 1)
        captures = inventory['entries'][0]['captures']
        self.assertEqual([r['timestamp'] for r in captures], ['20200215021200', '20070411155229'])

    def test_cdx_resume_key_and_capture_metadata(self):
        body = json.dumps([['timestamp', 'original', 'mimetype', 'digest'],
            ['20200215021200', CAPTURE['original'], 'text/html', 'DIGEST'], [], ['opaque+resume/key']]).encode()
        rows, resume = parse_cdx(body)
        self.assertEqual(resume, 'opaque+resume/key')
        self.assertEqual(rows[0]['label'], 'ageku')
        self.assertEqual(rows[0]['archive_url'], CAPTURE['archive_url'])

    def test_scope_and_slow_default(self):
        root = Path(tempfile.mkdtemp(prefix='takoboto-archive-test-')).resolve()
        f = ArchiveFetcher(root)
        self.assertEqual(f.delay, 5)
        self.assertTrue(allowed_archive_url(CAPTURE['archive_url']))
        for url in ['https://web.archive.org/save/http://jgram.org/',
            'http://jgram.org/pages/viewOne.php?tagE=ageku',
            'https://web.archive.org/web/20200215021200id_/http://evil.example/pages/viewOne.php?tagE=ageku',
            'https://web.archive.org/web/20200215021200id_/http://jgram.org/pages/addNote.php?tagE=ageku']:
            self.assertFalse(allowed_archive_url(url), url)
        with self.assertRaises(ValueError):
            ArchiveFetcher(root, delay=0)
        with self.assertRaises(ArchiveAccessError):
            f.get(CAPTURE['archive_url'])

    def test_rate_limit_stops_and_persists_backoff(self):
        root = Path(tempfile.mkdtemp(prefix='takoboto-archive-test-')).resolve()
        f = ArchiveFetcher(root)
        f.policy_checked = True
        error = HTTPError(CAPTURE['archive_url'], 429, 'limited', {'Retry-After': '600'}, io.BytesIO())
        with patch.object(f.opener, 'open', side_effect=error) as request:
            with self.assertRaises(ArchiveAccessError):
                f.get(CAPTURE['archive_url'])
            self.assertEqual(request.call_count, 1)
        state = json.loads((root / 'access-cooldown.json').read_text())
        self.assertEqual(state['reason'], 'HTTP 429')
        with patch.object(f.opener, 'open') as request:
            with self.assertRaises(ArchiveAccessError):
                f.get(CAPTURE['archive_url'])
            request.assert_not_called()

    def test_server_retry_after_and_robots_denial_stop_requests(self):
        root = Path(tempfile.mkdtemp(prefix='takoboto-archive-test-')).resolve()
        f = ArchiveFetcher(root)
        f.policy_checked = True
        error = HTTPError(CAPTURE['archive_url'], 503, 'busy', {'Retry-After': '900'}, io.BytesIO())
        with patch.object(f.opener, 'open', side_effect=error) as request:
            with self.assertRaises(ArchiveAccessError):
                f.get(CAPTURE['archive_url'])
            self.assertEqual(request.call_count, 1)
        state = json.loads((root / 'access-cooldown.json').read_text())
        self.assertEqual(state['reason'], 'HTTP 503')
        from urllib.robotparser import RobotFileParser
        f.robots = RobotFileParser()
        f.robots.parse(['User-agent: *', 'Disallow: /web/'])
        with patch.object(f.opener, 'open') as request:
            with self.assertRaisesRegex(ArchiveAccessError, 'robots.txt disallows'):
                f.get(CAPTURE['archive_url'])
            request.assert_not_called()

    def test_supplement_export_round_trip(self):
        root = Path(tempfile.mkdtemp(prefix='takoboto-archive-test-')).resolve()
        record = self.record()
        path = build_sqlite([], root / 'archive.sqlite', [record])
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM archive_notes').fetchone()[0], 6)
            self.assertEqual(db.execute('SELECT count(*) FROM archive_relationships').fetchone()[0], 3)
            self.assertEqual(json.loads(db.execute('SELECT record_json FROM archive_entries').fetchone()[0]), record)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        export_markdown([], root / 'markdown', [record])
        page = next((root / 'markdown/jgram').glob('*.md')).read_text()
        self.assertIn('MightyAtom', page)
        self.assertIn('Often used with さんざん', page)
        self.assertIn('20200215021200', page)

    def test_offline_source_audit_detects_dropped_notes(self):
        root = Path(tempfile.mkdtemp(prefix='takoboto-archive-test-')).resolve()
        record = self.record()
        key = hashlib.sha256(record['label'].encode()).hexdigest()
        write_json(root, 'inventory.json', {'cdx_complete': True, 'entries': [{'label': 'ageku'}, {'label': 'unfetched'}]})
        write_json(root, f'records/{key}.json', record)
        (root / 'cache/responses').mkdir(parents=True)
        (root / 'cache/responses' / (record['response_sha256'] + '.bin')).write_bytes(FIXTURE.read_bytes())
        report = audit_archive(root)
        self.assertTrue(report['parsed_records_verified'])
        self.assertFalse(report['historical_coverage_complete'])
        self.assertEqual(report['pending_labels'], ['unfetched'])
        record['notes'].pop()
        write_json(root, f'records/{key}.json', record)
        self.assertFalse(audit_archive(root)['parsed_records_verified'])
        fetcher = ArchiveFetcher(root, offline=True)
        with patch.object(fetcher.opener, 'open') as request:
            with self.assertRaisesRegex(ArchiveAccessError, 'Offline mode'):
                fetcher.get(CAPTURE['archive_url'])
            request.assert_not_called()

    def test_license_review_never_substitutes_older_capture(self):
        root = Path(tempfile.mkdtemp(prefix='takoboto-archive-test-')).resolve()
        calls = []
        conflicting = FIXTURE.read_bytes() + b'<a href="https://creativecommons.org/licenses/by-nc-sa/2.0/">license</a>'
        class Replay:
            def get(self, url):
                calls.append(url)
                return conflicting, {'retrieved_at': 'now', 'final_url': url}
        fetcher = Replay()
        fetcher.root = root
        older = dict(CAPTURE, timestamp='20070411155229', archive_url=CAPTURE['archive_url'].replace('20200215021200', '20070411155229'))
        report = crawl_archive(fetcher, {'label_count': 1, 'entries': [{'label': 'ageku', 'captures': [CAPTURE, older]}]})
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(report['review_required']), 1)
        self.assertFalse(report['complete'])
        self.assertEqual(report['parsed'], [])

    def test_rss_dates_and_full_grammar_body_round_trip(self):
        root = Path(tempfile.mkdtemp(prefix='takoboto-rss-test-')).resolve()
        raw = (FIXTURE.parent / 'archive-jlpt1.xml').read_bytes()
        capture = {'original': 'http://www.jgram.org:80/rss/jlpt1.xml', 'timestamp': '20200713231337',
            'archive_url': 'https://web.archive.org/web/20200713231337id_/http://www.jgram.org:80/rss/jlpt1.xml'}
        self.assertTrue(allowed_archive_url(capture['archive_url']))
        feed = parse_feed(raw, capture, {'retrieved_at': 'now'}, {'madashimo': 123})
        self.assertEqual(len(feed['items']), 1)
        item = feed['items'][0]
        self.assertEqual(item['pub_date_raw'], 'Wed, 20 Nov 2019 01:04:01 PST')
        self.assertIn('6242', item['body_html'])
        self.assertNotIn('addNote.php', item['body_html'])
        self.assertIn('addNote.php', item['description_raw_html'])
        self.assertNotIn('original_created_at', item)
        path = build_sqlite([], root / 'rss.sqlite', archive_feeds=[feed])
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('SELECT pub_date_raw FROM archive_feed_items').fetchone()[0], item['pub_date_raw'])
            self.assertEqual(json.loads(db.execute('SELECT record_json FROM archive_feeds').fetchone()[0]), feed)
        export_markdown([], root / 'markdown', archive_feeds=[feed])
        self.assertIn('2019', (root / 'markdown/jgram/rss-jlpt1.md').read_text())
        self.assertEqual(parse_feed(raw, capture, {'retrieved_at': 'now'}, {})['items'], [])


if __name__ == '__main__':
    unittest.main()
