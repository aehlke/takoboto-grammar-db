"""Preflight regressions: bad local inputs must not create outputs or send requests."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from takoboto_grammar.cli import main
from takoboto_grammar.crawl import FetchAccessError


class CliTests(unittest.TestCase):
    def root(self):
        return Path(tempfile.mkdtemp(prefix='takoboto-cli-review-')).resolve()

    def reject(self, arguments):
        root = self.root()
        output = root / 'untouched'
        with patch('sys.argv', ['takoboto-grammar', *arguments, '--output', str(output)]), \
             patch('takoboto_grammar.cli.Fetcher') as current, \
             patch('takoboto_grammar.cli.ArchiveFetcher') as archive, \
             redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main()
            self.assertEqual(error.exception.code, 2)
            current.assert_not_called()
            archive.assert_not_called()
        self.assertFalse(output.exists())

    def manifest(self, root, historical=False):
        path = root / 'inventory.json'
        if historical:
            original = 'http://jgram.org/pages/viewOne.php?tagE=ageku'
            value = {'label_count': 1, 'capture_count': 1, 'pages': [], 'entries': [
                {'label': 'ageku', 'captures': [{'label': 'ageku', 'timestamp': '20200215021200', 'original': original,
                 'archive_url': 'https://web.archive.org/web/20200215021200id_/' + original}]}]}
        else:
            value = {'entry_count': 1, 'pages': [], 'entries': [
                {'id': 725, 'source_url': 'https://takoboto.jp/bunpo/725/'}]}
        path.write_text(json.dumps(value))
        return path

    def test_unknown_saved_selectors_fail_before_fetcher(self):
        root = self.root()
        current = self.manifest(root)
        self.reject(['crawl', '--inventory', str(current), '--id', '999999'])
        historical = self.manifest(root, True)
        self.reject(['archive', '--inventory', str(historical), '--label', 'missing'])

    def test_missing_malformed_and_invalid_manifests_fail_before_fetcher(self):
        root = self.root()
        path = root / 'bad.json'
        for command in ['crawl', 'archive']:
            self.reject([command, '--inventory', str(root / 'missing.json')])
            for value in ['{broken', '[]', '{"entries": [], "pages": [], "entry_count": 8}',
                          '{"entries": [{"id": 725, "source_url": "https://external.example/"}], "pages": [], "entry_count": 1}']:
                path.write_text(value)
                self.reject([command, '--inventory', str(path)])

    def test_bad_schedule_and_offline_refresh_fail_before_fetcher(self):
        for command in ['crawl', 'archive', 'archive-feeds']:
            for option, value in [('--delay', 'nan'), ('--delay', '0'), ('--burst-size', '0'),
                                  ('--burst-pause', 'inf')]:
                self.reject([command, option, value])
        self.reject(['archive', '--offline', '--refresh'])

    def test_missing_current_records_fail_before_archive_fetcher(self):
        root = self.root()
        self.reject(['archive-feeds', '--takoboto', str(root / 'missing')])
        self.reject(['archive', '--inventory', str(self.manifest(root, True)),
                     '--takoboto', str(root / 'missing')])

    def test_bad_historical_capture_metadata_fails_before_requests(self):
        root = self.root()
        path = self.manifest(root, True)
        valid = json.loads(path.read_text())
        for key, value in [('label', 'different'), ('timestamp', 'invalid'),
                           ('archive_url', 'https://external.example/'), ('original', []),
                           ('original', 'http://jgram.org/rss/updates.xml')]:
            malformed = json.loads(json.dumps(valid))
            malformed['entries'][0]['captures'][0][key] = value
            path.write_text(json.dumps(malformed))
            self.reject(['archive', '--inventory', str(path)])

    def test_current_record_without_label_fails_before_requests(self):
        root = self.root()
        (root / 'records').mkdir()
        (root / 'records/725.json').write_text('{"id": 725, "schema_version": 2}')
        self.reject(['archive-feeds', '--takoboto', str(root)])

    def test_export_preflight_does_not_leave_sqlite_or_markdown(self):
        root = self.root()
        occupied = root / 'occupied'
        occupied.mkdir()
        (occupied / 'existing.md').write_text('keep')
        db = root / 'new-parent/grammar.sqlite'
        for destination in [occupied, root / 'file.md', root / 'linked']:
            if destination.name == 'file.md':
                destination.write_text('keep')
            if destination.name == 'linked':
                destination.symlink_to(root / 'missing-directory')
            with patch('sys.argv', ['takoboto-grammar', 'build', '--sqlite', str(db),
                                    '--markdown', str(destination)]), \
                 patch('takoboto_grammar.cli.build_sqlite') as builder, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main()
                builder.assert_not_called()
            self.assertFalse(db.parent.exists())
        self.assertEqual((occupied / 'existing.md').read_text(), 'keep')

    def test_existing_sqlite_refuses_before_markdown_is_created(self):
        root = self.root()
        db = root / 'existing.sqlite'
        db.write_bytes(b'keep')
        markdown = root / 'new-md'
        with patch('sys.argv', ['takoboto-grammar', 'build', '--sqlite', str(db),
                                '--markdown', str(markdown)]), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main()
        self.assertEqual(db.read_bytes(), b'keep')
        self.assertFalse(markdown.exists())

    def test_overlapping_export_destinations_are_refused(self):
        root = self.root()
        with patch('sys.argv', ['takoboto-grammar', 'build', '--sqlite', str(root / 'md/grammar.sqlite'),
                                '--markdown', str(root / 'md')]), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main()
        self.assertFalse((root / 'md').exists())

    def test_invalid_evidence_bundle_is_concise_and_does_not_write(self):
        root = self.root()
        bundle = root / 'invalid.tar.gz'
        bundle.write_bytes(b'not a gzip archive')
        destination = root / 'restore'
        with patch('sys.argv', ['takoboto-grammar', 'evidence-restore',
                                '--bundle', str(bundle), '--output', str(destination)]), \
             redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as stopped:
                main()
            self.assertEqual(stopped.exception.code, 2)
            self.assertIn('Cannot preserve evidence', error.getvalue())
            self.assertNotIn('Traceback', error.getvalue())
        self.assertFalse(destination.exists())

    def test_initial_access_stop_is_concise_and_closes_fetcher(self):
        root = self.root()
        with patch('sys.argv', ['takoboto-grammar', 'crawl', '--inventory', str(self.manifest(root))]), \
             patch('takoboto_grammar.cli.Fetcher') as constructor, redirect_stderr(io.StringIO()) as error:
            constructor.return_value.__enter__.return_value.check_robots.side_effect = FetchAccessError('cooldown active')
            self.assertEqual(main(), 1)
            constructor.return_value.__exit__.assert_called_once()
            self.assertEqual(error.getvalue(), 'Stopped: cooldown active\n')
