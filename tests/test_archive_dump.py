"""Original backup recovery, evidence validation and conservative transport."""

import base64
import gzip
import hashlib
import json
import tempfile
import sqlite3
import unittest
from pathlib import Path
from contextlib import closing
from urllib.request import Request
from unittest.mock import patch

import httpx

from takoboto_grammar.archive_dump import (ITEM, WARC, INDEX, SNAPSHOT, DumpFetcher, allowed_dump_url,
    parse_dump_index, dump_inventory, range_groups, member_body, crawl_dump, verify_dump_record)
from takoboto_grammar.archive_audit import audit_archive
from takoboto_grammar.storage import read_archive_records, archive_record_key, write_json, build_sqlite, cache_response
from takoboto_grammar.http import HttpxOpener
from test_archive import FIXTURE


class DumpTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='jgram-dump-test-')).resolve()
        self.body = FIXTURE.read_bytes()
        self.original = 'http://jgram.org/pages/viewOne.php?tagE=ageku'
        self.digest = base64.b32encode(hashlib.sha1(self.body).digest()).decode()
        block = b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: ' + str(len(self.body)).encode() + b'\r\n\r\n' + self.body
        block_digest = base64.b32encode(hashlib.sha1(block).digest()).decode()
        header = (f'WARC/1.0\r\nWARC-Type: response\r\nWARC-Target-URI: {self.original}\r\n'
                  f'WARC-Date: 2015-02-24T22:54:16Z\r\nWARC-Block-Digest: sha1:{block_digest}\r\n'
                  f'WARC-Payload-Digest: sha1:{self.digest}\r\nContent-Length: {len(block)}\r\n\r\n').encode()
        self.member = gzip.compress(header + block + b'\r\n\r\n', mtime=0)
        self.index = gzip.compress((f' CDX N b a m s k r M S V g\n'
            f'org,jgram)/pages/viewone.php 20150224225416 {self.original} text/html 200 {self.digest} - - '
            f'{len(self.member)} 10 {ITEM}/{WARC}\n').encode())
        self.inventory = dump_inventory(self.index, {'url': f'https://archive.org/download/{ITEM}/{INDEX}'})
        self.capture = self.inventory['entries'][0]['captures'][0]

    def crawl(self):
        member = self.member
        root = self.root
        class Fetcher:
            def get(self, filename, start, length):
                return member, {'final_url': f'https://archive.org/download/{ITEM}/{WARC}', 'retrieved_at': 'now'}
        fetcher = Fetcher()
        fetcher.root = root
        write_json(root, 'inventory.json', self.inventory)
        cache_response(root, f'cache/dump-index/{self.inventory["index_sha256"]}.gz', self.index)
        return crawl_dump(fetcher, self.inventory)

    def test_backup_source_round_trip_and_snapshot_identity(self):
        self.assertTrue(self.crawl()['complete'])
        record = read_archive_records(self.root)[0]
        self.assertEqual(record['snapshot'], SNAPSHOT)
        self.assertEqual(record['archive_timestamp'], '20150224225416')
        self.assertEqual(len(record['notes']), 6)
        verify_dump_record(self.root, record, self.inventory)
        self.assertTrue(audit_archive(self.root)['export_ready'])
        newer = dict(record)
        newer.pop('snapshot')
        self.assertNotEqual(archive_record_key(record), archive_record_key(newer))
        build_sqlite([], self.root / 'combined.sqlite', [record, newer])
        with closing(sqlite3.connect(self.root / 'combined.sqlite')) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone(), (3,))
            self.assertEqual(db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone(), ('3',))

    def test_backup_offline_resume_preserves_record_bytes(self):
        self.crawl()
        before = next((self.root / 'records').glob('*.yaml')).read_bytes()
        with DumpFetcher(self.root, offline=True) as fetcher, patch.object(fetcher.opener, 'open') as network:
            self.assertTrue(crawl_dump(fetcher, self.inventory)['complete'])
            network.assert_not_called()
        self.assertEqual(before, next((self.root / 'records').glob('*.yaml')).read_bytes())

    def test_offline_imported_index_reuses_verified_evidence(self):
        self.crawl()
        with DumpFetcher(self.root, offline=True) as fetcher, patch.object(fetcher.opener, 'open') as network:
            body, metadata = fetcher.get(INDEX)
            self.assertEqual(body, self.index)
            self.assertEqual(metadata, self.inventory['pages'][0])
            network.assert_not_called()
            write_json(self.root, 'inventory.json', dict(self.inventory, label_count=999))
            with self.assertRaises(ValueError):
                fetcher.get(INDEX)

    def test_changed_member_identity_and_hash_are_rejected(self):
        for field, value in [('original', self.original + 'x'), ('timestamp', '20150224225417'), ('digest', 'A' * 32)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                member_body(self.member, dict(self.capture, **{field: value}))
        with self.assertRaises((ValueError, OSError, EOFError)):
            member_body(self.member[:-1], self.capture)

    def test_conflicting_license_is_held_without_exporting_record(self):
        with patch('takoboto_grammar.archive_dump.parse_archive', side_effect=ValueError('Conflicting license')):
            report = self.crawl()
        self.assertFalse(report['complete'])
        self.assertEqual(len(report['review_required']), 1)
        self.assertEqual(read_archive_records(self.root), [])
        self.assertEqual(len(list((self.root / 'cache/warc-members').glob('*.gz'))), 1)

    def test_index_scope_and_archive_path_are_strict(self):
        rows, _ = parse_dump_index(self.index)
        self.assertEqual(len(rows), 1)
        with self.assertRaisesRegex(ValueError, 'Invalid scoped backup'):
            parse_dump_index(gzip.compress(gzip.decompress(self.index).replace(ITEM.encode(), b'other-item')))
        good = f'https://dn711100.ca.archive.org/0/items/{ITEM}/{WARC}'
        self.assertTrue(allowed_dump_url(good))
        for bad in [good.replace('.archive.org', '.archive.org.evil.test'), good + '?x=1',
                    good.replace(WARC, 'other.warc.gz'), good.replace('/0/items/', '/items/')]:
            self.assertFalse(allowed_dump_url(bad))

    def test_range_coalescing_is_bounded(self):
        a = dict(self.capture, warc_offset=0, warc_length=100)
        b = dict(a, warc_offset=200)
        c = dict(a, warc_offset=25 * 1024 * 1024)
        groups = range_groups([c, b, a])
        self.assertEqual([len(g['captures']) for g in groups], [2, 1])
        self.assertTrue(all(g['end'] - g['start'] <= 20 * 1024 * 1024 for g in groups))

    def test_range_ignored_or_truncated_fails_before_full_file_download(self):
        for status, headers, body in [(200, {}, b'large file'), (206, {'Content-Range': 'bytes 0-5/99'}, b'123'),
                                      (206, {'Content-Range': 'bytes 1-6/99'}, b'123456')]:
            with self.subTest(status=status, headers=headers):
                opener = HttpxOpener(lambda u: True, lambda u: None, lambda: None, 1024)
                opener.client.close()
                opener.client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, headers=headers, content=body)))
                try:
                    with self.assertRaises(ValueError):
                        opener.open(Request('https://archive.org/file', headers={'Range': 'bytes=0-5'}))
                    if status == 200:
                        self.assertEqual(opener.attempts[0]['bytes_read'], 0)
                finally:
                    opener.close()


if __name__ == '__main__':
    unittest.main()
