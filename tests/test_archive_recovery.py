"""Recovery must establish identical content, not just a nearby timestamp."""

import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError

from takoboto_grammar.archive import crawl_archive, latest_body_equivalent, replay_candidates
from takoboto_grammar.archive_audit import audit_archive
from takoboto_grammar.archive_parser import source_soup, parse_archive, NotGrammar
from takoboto_grammar.storage import build_sqlite
from bs4 import BeautifulSoup
import copy
import sqlite3
from contextlib import closing
from takoboto_grammar.storage import write_json, cache_response, read_archive_records
from test_archive import CAPTURE, FIXTURE


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='jgram-recovery-test-')).resolve()
        self.body = FIXTURE.read_bytes()
        digest = base64.b32encode(hashlib.sha1(self.body).digest()).decode()
        self.latest = dict(CAPTURE, digest=digest)
        self.alternate = dict(self.latest, timestamp='20190101000000',
                              archive_url=CAPTURE['archive_url'].replace('20200215021200', '20190101000000'))
        self.item = {'label': 'ageku', 'captures': [self.latest], 'alternate_captures': [self.alternate]}
        self.inventory = {'label_count': 1, 'cdx_complete': True, 'entries': [self.item]}
        write_json(self.root, 'inventory.json', self.inventory)

    def replay(self, body=None, final_url=None):
        root, latest, alternate = self.root, self.latest, self.alternate
        payload = self.body if body is None else body
        class Fetcher:
            def get(self, url):
                if url == latest['archive_url']:
                    raise HTTPError(url, 404, 'replay unavailable', {}, None)
                meta = {'url': url, 'final_url': final_url or url, 'retrieved_at': 'now',
                        'sha256': hashlib.sha256(payload).hexdigest()}
                cache_response(root, f'cache/responses/{meta["sha256"]}.bin', payload)
                write_json(root, f'cache/urls/{hashlib.sha256(url.encode()).hexdigest()}.json', meta)
                return payload, meta
        f = Fetcher()
        f.root = root
        return crawl_archive(f, self.inventory)

    def test_equivalent_capture_exports_and_audits_as_latest_content(self):
        report = self.replay()
        self.assertTrue(report['complete'])
        record = read_archive_records(self.root)[0]
        self.assertEqual(record['archive_timestamp'], self.alternate['timestamp'])
        self.assertEqual(record['latest_indexed_timestamp'], self.latest['timestamp'])
        self.assertEqual(len(record['selection_attempts']), 1)
        audit = audit_archive(self.root)
        self.assertTrue(audit['historical_coverage_complete'], audit)

    def test_changed_payload_remains_blocked_even_with_matching_index_digest(self):
        self.assertFalse(self.replay(self.body + b'<!-- changed -->')['complete'])
        self.assertEqual(read_archive_records(self.root), [])
        self.assertEqual(len(list((self.root / 'review-records').glob('*.yaml'))), 1)
        self.assertFalse(audit_archive(self.root)['historical_coverage_complete'])

    def test_unindexed_redirect_is_not_equivalence_evidence(self):
        final = self.alternate['archive_url'].replace('20190101000000', '20180101000000')
        self.assertFalse(self.replay(final_url=final)['complete'])

    def test_unknown_digest_or_unindexed_capture_never_proves_identity(self):
        self.item['captures'][0]['digest'] = '-'
        self.assertFalse(latest_body_equivalent(self.body, self.alternate, self.item))
        self.assertEqual(list(replay_candidates(self.item)), [self.latest])

    def test_candidate_order_prefers_same_revision_and_is_bounded(self):
        old = dict(self.latest, digest='B' * 32, timestamp='20070411155229')
        self.item['captures'].append(old)
        self.item['alternate_captures'] += [dict(self.alternate, timestamp=f'2018{month:02}01000000')
                                           for month in range(1, 12)]
        candidates = list(replay_candidates(self.item))
        self.assertEqual([c['digest'] for c in candidates], [self.latest['digest']] * 3 + [old['digest']])

    def test_windows_shift_jis_and_utf8_comment_preserve_source_text(self):
        prefix = b'<meta charset="shift_jis"><p>'
        windows = prefix + '①'.encode('cp932') + b'</p>'
        soup, repairs = source_soup(windows)
        self.assertEqual(soup.p.get_text(), '①')
        self.assertEqual(repairs, [])
        raw = prefix + 'Which: 関わり, 係わり, 拘らず?'.encode('utf-8') + b'</p>'
        soup, repairs = source_soup(raw)
        self.assertEqual(soup.p.get_text(), 'Which: 関わり, 係わり, 拘らず?')
        self.assertEqual(len(repairs), 1)
        offset, length = repairs[0]['byte_offset'], repairs[0]['byte_length']
        self.assertEqual(raw[offset:offset + length].decode('utf-8'), soup.p.get_text())
        broken_url = b'<meta charset="shift_jis"><a href="http://example.test/?q=\x83\x98A">word</a>'
        soup, repairs = source_soup(broken_url)
        self.assertEqual(soup.a['href'], 'http://example.test/?q=%83%98A')
        self.assertEqual(repairs[0]['encoding'], 'percent-encoded-original-url-bytes')
        self.assertFalse(soup.contains_replacement_characters)
        broken_text = b'<meta charset="shift_jis"><p>Original \x83\x98Z</p>'
        soup, repairs = source_soup(broken_text)
        self.assertEqual(repairs[0]['encoding'], 'cp932-with-undecodable-bytes')
        self.assertEqual(bytes.fromhex(repairs[0]['original_bytes_hex']), b'Original \x83\x98Z')
        self.assertIn('\ufffd', soup.p.get_text())

    def test_repeated_original_example_id_retains_both_occurrences_in_sqlite(self):
        soup = BeautifulSoup(self.body, 'html.parser')
        anchor = next(a for a in soup.select('a[name]') if a['name'].isdigit())
        row = anchor.find_parent('tr')
        row.parent.append(copy.copy(row))
        body = soup.encode('shift_jis')
        capture = dict(self.latest, digest=base64.b32encode(hashlib.sha1(body).digest()).decode())
        record = parse_archive(body, capture, 'now')
        self.assertEqual(len(record['examples']), 15)
        path = build_sqlite([], self.root / 'duplicates.sqlite', [record])
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM archive_examples WHERE source_id=?',
                                        (int(anchor['name']),)).fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT value FROM metadata WHERE key="schema_version"').fetchone()[0], '3')

    def test_absent_entry_needs_exact_label_and_license_evidence(self):
        missing = (b'<title>JGram - The Japanese Grammar database</title>'
            b'<a href="https://creativecommons.org/licenses/by-sa/2.0/">License</a>'
            b'No entry exists for ageku - click here to add one')
        capture = dict(self.latest, digest=base64.b32encode(hashlib.sha1(missing).digest()).decode())
        with self.assertRaises(NotGrammar):
            parse_archive(missing, capture, 'now')
        wrong = missing.replace(b'for ageku', b'for other')
        wrong_capture = dict(self.latest, digest=base64.b32encode(hashlib.sha1(wrong).digest()).decode())
        with self.assertRaisesRegex(ValueError, 'missing viewOnetitle'):
            parse_archive(wrong, wrong_capture, 'now')

    def test_unclassified_entry_is_held_and_reviewed_id_requires_matching_title(self):
        body = self.body.replace(b'Category</b>: <i>grammar</i>', b'')
        with self.assertRaisesRegex(ValueError, 'unclassified'):
            parse_archive(body, self.latest, 'now')
        wrong = body.replace(b'addGrammar.php?id=978', b'addGrammar.php?id=1503')
        with self.assertRaisesRegex(ValueError, 'title differs'):
            parse_archive(wrong, dict(self.latest, label='ano'), 'now')


if __name__ == '__main__':
    unittest.main()
