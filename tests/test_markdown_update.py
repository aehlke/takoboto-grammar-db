"""Managed exports must produce small diffs while preserving manual files."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from takoboto_grammar.cli import main
from takoboto_grammar.markdown import MANIFEST, update_markdown
from takoboto_grammar.parser import parse_entry
from takoboto_grammar.archive_parser import parse_archive
from takoboto_grammar.storage import export_markdown, write_json

FIXTURE = Path(__file__).parent / 'fixtures/entry725.html'


class MarkdownUpdateTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='takoboto-markdown-test-')).resolve()
        self.output = self.root / 'markdown'
        self.record = parse_entry(FIXTURE.read_bytes(), 725, 'test')

    def test_empty_historical_contributions_keep_credits_and_source_order(self):
        capture = {'label': 'ageku', 'original': 'http://jgram.org/pages/viewOne.php?tagE=ageku',
                   'archive_url': 'https://web.archive.org/web/20200215021200id_/http://jgram.org/pages/viewOne.php?tagE=ageku',
                   'timestamp': '20200215021200'}
        record = parse_archive(FIXTURE.with_name('archive-ageku.html').read_bytes(), capture, 'test')
        record['notes'][0].update(text='', html='', credits_raw='empty-note-author')
        record['comments'][0].update(text='', html='', credits_raw='empty-comment-author')
        result = update_markdown([], self.output, [record])
        page = next((self.output / 'jgram').glob('*.md')).read_text()
        self.assertIn('empty-note-author', page)
        self.assertIn('empty-comment-author', page)
        self.assertEqual(result['pages'], 2)

    def test_repeat_is_identical_and_does_not_rewrite_files(self):
        first = update_markdown([self.record], self.output)
        self.assertEqual(first['pages'], 2)
        before = {str(p.relative_to(self.output)): (p.read_bytes(), p.stat().st_mtime_ns)
                  for p in self.output.rglob('*') if p.is_file()}
        again = update_markdown([self.record], self.output)
        self.assertEqual(again['updated'], [])
        self.assertEqual(again['removed'], [])
        self.assertEqual(again['unchanged'], 2)
        after = {str(p.relative_to(self.output)): (p.read_bytes(), p.stat().st_mtime_ns)
                 for p in self.output.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        fresh = self.root / 'fresh'
        export_markdown([self.record], fresh)
        for p in fresh.rglob('*.md'):
            self.assertEqual(p.read_bytes(), (self.output / p.relative_to(fresh)).read_bytes())

    def test_one_content_change_updates_one_page_and_manifest(self):
        update_markdown([self.record], self.output)
        index = (self.output / 'README.md').read_bytes()
        self.record['meaning'] = 'Updated explanation'
        report = update_markdown([self.record], self.output)
        self.assertEqual(report['updated'], ['n5/725.md'])
        self.assertEqual((self.output / 'README.md').read_bytes(), index)
        self.assertIn('Updated explanation', (self.output / 'n5/725.md').read_text())

    def test_level_change_moves_obsolete_page_to_trash(self):
        update_markdown([self.record], self.output)
        original = (self.output / 'n5/725.md').read_bytes()
        home = self.root / 'home'
        home.mkdir()
        self.record['jlpt_level'] = 4
        with patch('takoboto_grammar.markdown.Path.home', return_value=home):
            report = update_markdown([self.record], self.output)
        self.assertEqual(report['removed'], ['n5/725.md'])
        self.assertFalse((self.output / 'n5/725.md').exists())
        self.assertTrue((self.output / 'n4/725.md').exists())
        self.assertEqual((Path(report['obsolete_pages_moved_to']) / 'n5/725.md').read_bytes(), original)
        files = json.loads((self.output / MANIFEST).read_text())['files']
        self.assertNotIn('n5/725.md', files)
        self.assertIn('n4/725.md', files)

    def test_manual_edit_blocks_all_updates(self):
        update_markdown([self.record], self.output)
        page = self.output / 'n5/725.md'
        page.write_text('manual work')
        old_manifest = (self.output / MANIFEST).read_bytes()
        self.record['title'] = 'New title'
        with self.assertRaisesRegex(ValueError, 'edited or removed'):
            update_markdown([self.record], self.output)
        self.assertEqual(page.read_text(), 'manual work')
        self.assertEqual((self.output / MANIFEST).read_bytes(), old_manifest)
        self.assertNotIn('New title', (self.output / 'README.md').read_text())

    def test_unmanaged_files_are_preserved_and_collisions_refused(self):
        update_markdown([self.record], self.output)
        extra = self.output / 'notes.md'
        extra.write_text('keep')
        update_markdown([self.record], self.output)
        self.assertEqual(extra.read_text(), 'keep')
        (self.output / 'n4').mkdir()
        collision = self.output / 'n4/725.md'
        collision.write_text('keep this too')
        self.record['jlpt_level'] = 4
        with self.assertRaisesRegex(ValueError, 'unmanaged'):
            update_markdown([self.record], self.output)
        self.assertEqual(collision.read_text(), 'keep this too')
        self.assertTrue((self.output / 'n5/725.md').exists())

    def test_symlink_destination_and_child_are_refused(self):
        external = self.root / 'external'
        external.mkdir()
        self.output.symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            update_markdown([self.record], self.output)
        self.assertEqual(list(external.iterdir()), [])
        other = self.root / 'other-markdown'
        update_markdown([self.record], other)
        (other / 'linked').symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            update_markdown([self.record], other)

    def test_invalid_manifest_path_cannot_escape(self):
        self.output.mkdir()
        outside = self.root / 'outside.md'
        outside.write_text('keep')
        write_json(self.output, MANIFEST, {'format': 'takoboto-grammar-markdown', 'version': 1,
            'files': {'../outside.md': '0' * 64}})
        with self.assertRaisesRegex(ValueError, 'Invalid generated page path'):
            update_markdown([self.record], self.output)
        self.assertEqual(outside.read_text(), 'keep')

    def test_existing_unmanaged_directory_is_refused(self):
        self.output.mkdir()
        (self.output / 'README.md').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'no generated manifest'):
            update_markdown([self.record], self.output)
        self.assertEqual((self.output / 'README.md').read_text(), 'keep')

    def test_nonobject_manifest_fails_without_writing_pages(self):
        self.output.mkdir()
        write_json(self.output, MANIFEST, [])
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            update_markdown([self.record], self.output)
        self.assertEqual(list(self.output.iterdir()), [self.output / MANIFEST])

    def test_cli_is_offline_and_bad_input_creates_no_output(self):
        write_json(self.root, 'records/725.json', self.record)
        with patch('httpx.Client.send', side_effect=AssertionError('offline')) as network, \
             patch('sys.argv', ['takoboto-grammar', 'update-markdown', '--input', str(self.root),
                               '--output', str(self.output)]), redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 0)
            network.assert_not_called()
        invalid = self.root / 'invalid-output'
        with patch('httpx.Client.send', side_effect=AssertionError('offline')) as network, \
             patch('sys.argv', ['takoboto-grammar', 'update-markdown', '--input', str(self.root / 'missing'),
                               '--output', str(invalid)]), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main()
            self.assertEqual(error.exception.code, 2)
            network.assert_not_called()
        self.assertFalse(invalid.exists())
