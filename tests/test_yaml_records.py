"""Canonical YAML must preserve source evidence and yield stable Git diffs."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from takoboto_grammar.parser import parse_entry
from takoboto_grammar.record_yaml import dump_yaml, load_yaml
from takoboto_grammar.storage import write_record, write_json, write_bytes, read_records, record_digest, migrate_records


class YamlRecordTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='takoboto-yaml-test-')).resolve()
        self.home = self.root / 'home'
        self.home.mkdir()
        self.record = parse_entry((Path(__file__).parent / 'fixtures/entry725.html').read_bytes(), 725, 'test')

    def test_exact_types_and_original_whitespace_survive(self):
        values = {'日本語': 'そう', 'strings': ['on', 'off', 'yes', 'false', 'null', '001', '008', '0o17', '1e3', '1_000e3',
                  '2026-10-03', '2026-10-03T17:54:08+00:00', 'a\r\nb', '\x85\u2028\u2029', '\0'],
                  'scalars': [True, False, None, 865, 2**80, 1.25],
                  'text': '\n first line \n\tsecond line\n\n', 'html': '<a href="url">it\'s Japanese: 日本語</a>'}
        body = dump_yaml(values)
        self.assertEqual(load_yaml(body), values)
        self.assertEqual(record_digest(load_yaml(body)), record_digest(values))
        self.assertIn(b'text: |', body)
        self.assertIn(b'html: |', body)

    def test_real_entry_repeats_without_rewriting_and_one_edit_stays_local(self):
        write_record(self.root, 'records/725.yaml', self.record)
        path = self.root / 'records/725.yaml'
        before = path.read_bytes(), path.stat().st_mtime_ns
        write_record(self.root, 'records/725.yaml', self.record)
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)
        self.assertEqual(read_records(self.root), [self.record])
        self.assertEqual(list((self.root / 'records').glob('*.json')), [])
        self.record['meaning'] = 'Updated explanation'
        write_record(self.root, 'records/725.yaml', self.record)
        changed = [(a, b) for a, b in zip(before[0].decode().splitlines(), path.read_text().splitlines()) if a != b]
        self.assertEqual(changed, [('meaning: but, however, still', 'meaning: Updated explanation')])

    def test_legacy_refresh_moves_json_to_trash_after_yaml_success(self):
        write_json(self.root, 'records/725.json', self.record)
        previous = (self.root / 'records/725.json').read_bytes()
        with patch('takoboto_grammar.storage.Path.home', return_value=self.home):
            write_record(self.root, 'records/725.yaml', self.record)
        self.assertFalse((self.root / 'records/725.json').exists())
        self.assertEqual(read_records(self.root), [self.record])
        saved = list((self.home / '.Trash').glob('*/725.json'))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_bytes(), previous)

    def test_failed_yaml_replacement_retains_previous_json(self):
        write_json(self.root, 'records/725.json', self.record)
        previous = (self.root / 'records/725.json').read_bytes()
        with patch('takoboto_grammar.storage.Path.replace', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                write_record(self.root, 'records/725.yaml', self.record)
        self.assertEqual((self.root / 'records/725.json').read_bytes(), previous)
        self.assertFalse((self.root / 'records/725.yaml').exists())

    def test_duplicate_formats_cannot_shadow_each_other(self):
        write_record(self.root, 'records/725.yaml', self.record)
        write_json(self.root, 'records/725.json', self.record)
        with self.assertRaisesRegex(ValueError, 'Duplicate YAML/JSON'):
            read_records(self.root)
        with self.assertRaisesRegex(ValueError, 'Duplicate YAML/JSON'):
            write_record(self.root, 'records/725.yaml', self.record)

    def test_duplicate_keys_unsafe_tags_and_non_record_scalars_fail(self):
        for body in ['id: 725\nid: 726\n', 'body: !!python/object/apply:os.system ["echo bad"]',
                     'created_at: 2026-10-03', 'value: .nan', 'value: &loop [*loop]']:
            with self.subTest(body=body), self.assertRaises(ValueError):
                load_yaml(body)

    def test_migration_preflights_all_inputs_and_is_resumable_offline(self):
        other = self.root / 'other'
        other.mkdir()
        write_json(self.root, 'records/725.json', self.record)
        write_json(other, 'records/725.json', self.record)
        (other / 'records/726.json').write_text('broken JSON')
        with self.assertRaises(ValueError):
            migrate_records([self.root, other])
        self.assertFalse((self.root / 'records/725.yaml').exists())
        with patch('takoboto_grammar.storage.Path.home', return_value=self.home):
            report = migrate_records([self.root])
            self.assertEqual(report['converted_records'], 1)
            self.assertEqual(migrate_records([self.root])['converted_records'], 0)
        self.assertEqual(read_records(self.root), [self.record])

    def test_migration_resumes_after_yaml_write_before_json_retirement(self):
        write_json(self.root, 'records/725.json', self.record)
        write_bytes(self.root, 'records/725.yaml', dump_yaml(self.record))
        p = self.root / 'records/725.yaml'
        before = p.read_bytes(), p.stat().st_mtime_ns
        with patch('takoboto_grammar.storage.Path.home', return_value=self.home):
            self.assertEqual(migrate_records([self.root])['converted_records'], 1)
        self.assertEqual((p.read_bytes(), p.stat().st_mtime_ns), before)
        self.assertFalse((self.root / 'records/725.json').exists())

    def test_migration_never_resolves_conflicting_duplicate_formats_by_guessing(self):
        write_json(self.root, 'records/725.json', self.record)
        changed = dict(self.record, meaning='Different source value')
        write_bytes(self.root, 'records/725.yaml', dump_yaml(changed))
        before = {p.name: p.read_bytes() for p in (self.root / 'records').iterdir()}
        with self.assertRaisesRegex(ValueError, 'records differ'):
            migrate_records([self.root])
        self.assertEqual({p.name: p.read_bytes() for p in (self.root / 'records').iterdir()}, before)


if __name__ == '__main__':
    unittest.main()
