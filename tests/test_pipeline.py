import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import closing

from takoboto_grammar.crawl import Fetcher, allowed_url, crawl, discover
from takoboto_grammar.parser import ParseError, parse_entry
from takoboto_grammar.storage import build_sqlite, cache_response, export_markdown, read_records, safe_target, write_json

FIXTURES = Path(__file__).parent / "fixtures"
TIME = "2026-10-03T00:47:30+00:00"


class FakeFetcher:
    def __init__(self, root, bodies):
        self.root, self.bodies = root, bodies

    def get(self, url):
        body = self.bodies[url]
        return body, {"retrieved_at": TIME, "sha256": hashlib.sha256(body).hexdigest()}


class PipelineTests(unittest.TestCase):
    def test_interrupted_atomic_write_preserves_previous_record(self):
        root = Path(tempfile.mkdtemp(prefix='takoboto-atomic-test-')).resolve()
        write_json(root, 'records/725.json', {'previous': True})
        with patch('takoboto_grammar.storage.Path.replace', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                write_json(root, 'records/725.json', {'replacement': True})
        self.assertEqual(json.loads((root / 'records/725.json').read_text()), {'previous': True})
        self.assertEqual(len(list((root / 'records').glob('*.json'))), 1)
        self.assertEqual(len(list((root / 'records').glob('*.tmp'))), 1)
        write_json(root, 'records/725.json', {'replacement': True})
        self.assertEqual(json.loads((root / 'records/725.json').read_text()), {'replacement': True})

    def test_atomic_write_rechecks_symlinks_before_replacement(self):
        root = Path(tempfile.mkdtemp(prefix='takoboto-atomic-test-')).resolve()
        external = root / 'external.json'
        external.write_text('keep')
        target = root / 'record.json'
        original = safe_target
        calls = []
        def swapped(directory, relative):
            calls.append(relative)
            if len(calls) == 2:
                target.symlink_to(external)
            return original(directory, relative)
        with patch('takoboto_grammar.storage.safe_target', side_effect=swapped):
            with self.assertRaisesRegex(ValueError, 'symlink'):
                write_json(root, 'record.json', {'new': True})
        self.assertEqual(external.read_text(), 'keep')

    def test_corrupt_content_addressed_body_is_never_overwritten(self):
        root = Path(tempfile.mkdtemp(prefix='takoboto-atomic-test-')).resolve()
        cache_response(root, 'cache/body.bin', b'original')
        with self.assertRaisesRegex(ValueError, 'Corrupt'):
            cache_response(root, 'cache/body.bin', b'different')
        self.assertEqual((root / 'cache/body.bin').read_bytes(), b'original')

    def test_record_sqlite_markdown_preserve_content(self):
        # Temporary artifacts deliberately live in a fresh directory and are retained.
        root = Path(tempfile.mkdtemp(prefix="takoboto-test-")).resolve()
        records = [parse_entry((FIXTURES / f"entry{gid}.html").read_bytes(), gid, TIME) for gid in [509, 725, 1784]]
        for r in records:
            write_json(root, f"records/{r['id']}.json", r)
        self.assertEqual(read_records(root), records)
        path = build_sqlite(records, root / "grammar.sqlite")
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM entries").fetchone()[0], 3)
            self.assertEqual(db.execute("SELECT count(*) FROM examples").fetchone()[0], 27)
            self.assertEqual(db.execute("SELECT count(*) FROM comments").fetchone()[0], 21)
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(json.loads(db.execute("SELECT record_json FROM entries WHERE id=725").fetchone()[0]), records[1])
        with self.assertRaises(ValueError):
            build_sqlite(records, path)
        export_markdown(records, root / "markdown")
        page = (root / "markdown/n5/725.md").read_text()
        self.assertIn("突然です**が**ボードゲーム", page)
        self.assertIn("**but** I completely", page)
        self.assertIn("Amatuka, Raza", page)
        self.assertIn("Nick", page)
        self.assertTrue((root / "markdown/unclassified/1784.md").exists())

    def test_scope_allowlist(self):
        for url in ["https://takoboto.jp/bunpo/", "https://takoboto.jp/bunpo/?page=13", "https://takoboto.jp/bunpo/725/", "https://takoboto.jp/bunpo/?filter=jlpt1&page=2"]:
            self.assertTrue(allowed_url(url))
        for url in ["https://takoboto.jp/?q=grammar", "https://takoboto.jp/bunpo/edit/", "https://takoboto.jp/bunpo/remove/", "https://takoboto.jp/bunpo/?q=test", "https://evil.example/bunpo/725/", "http://takoboto.jp/bunpo/725/", "https://takoboto.jp/bunpo/?page=0", "https://takoboto.jp/bunpo/?page=1&page=2"]:
            self.assertFalse(allowed_url(url), url)

    def test_meaning_note_exported_and_linked_discovery(self):
        root = Path(tempfile.mkdtemp(prefix="takoboto-test-")).resolve()
        record = parse_entry((FIXTURES / 'entry725.html').read_bytes(), 725, TIME)
        record['meaning_notes'] = [{'language': 'ja', 'text': '日本語の説明', 'html': '日本語の説明'}]
        path = build_sqlite([record], root / 'notes.sqlite')
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('SELECT body_text FROM meaning_notes').fetchone()[0], '日本語の説明')
        export_markdown([record], root / 'markdown')
        self.assertIn('日本語の説明', (root / 'markdown/n5/725.md').read_text())
        bodies = {'https://takoboto.jp/bunpo/725/': (FIXTURES / 'entry725.html').read_bytes()}
        for gid in [724, 726]:
            bodies[f'https://takoboto.jp/bunpo/{gid}/'] = bodies['https://takoboto.jp/bunpo/725/'].replace(b'725', str(gid).encode())
        report = crawl(FakeFetcher(root, bodies), {'entry_count': 1, 'entries': [{'id': 725, 'source_url': 'https://takoboto.jp/bunpo/725/'}]})
        self.assertEqual(set(report['parsed']), {724, 725, 726})
        self.assertEqual(len(report['linked_entries_outside_index']), 2)
        self.assertTrue(report['complete'])

    def test_write_refuses_symlink_and_path_escape(self):
        root = Path(tempfile.mkdtemp(prefix="takoboto-test-")).resolve()
        other = Path(tempfile.mkdtemp(prefix="takoboto-test-other-")).resolve()
        (root / "linked").symlink_to(other, target_is_directory=True)
        with self.assertRaises(ValueError):
            safe_target(root, "linked/test.json")
        with self.assertRaises(ValueError):
            safe_target(root, "../escape.json")

    def test_discovery_and_failure_report(self):
        root = Path(tempfile.mkdtemp(prefix="takoboto-test-")).resolve()
        body = b'<div id="GrammarContent"><div class="GrammarSummaryDiv"><input id="GrammarEntryId0" value="725"><div>ga</div><div>but</div><div>See more</div></div></div>'
        fake = FakeFetcher(root, {"https://takoboto.jp/bunpo/": body, "https://takoboto.jp/bunpo/725/": b"<html>Error</html>"})
        inventory = discover(fake)
        self.assertEqual(inventory["entry_count"], 1)
        report = crawl(fake, inventory)
        self.assertFalse(report["complete"])
        self.assertEqual(len(report["failed"]), 1)
        self.assertFalse((root / "records/725.json").exists())

    def test_cache_hash_is_verified_and_no_network_for_replay(self):
        root = Path(tempfile.mkdtemp(prefix="takoboto-test-")).resolve()
        fetcher = Fetcher(root)
        url, body = "https://takoboto.jp/bunpo/725/", b"some cached HTML"
        digest, key = hashlib.sha256(body).hexdigest(), hashlib.sha256(url.encode()).hexdigest()
        write_json(root, f"cache/urls/{key}.json", {"url": url, "sha256": digest, "retrieved_at": TIME})
        target = safe_target(root, f"cache/responses/{digest}.html")
        target.write_bytes(body)
        with patch.object(fetcher.opener, "open", side_effect=AssertionError("Network must not be used")):
            self.assertEqual(fetcher.get(url)[0], body)
            target.write_bytes(b"corrupt")
            with self.assertRaises(ValueError):
                fetcher.get(url)


if __name__ == "__main__":
    unittest.main()
