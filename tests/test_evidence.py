"""Raw evidence survives backup and restore without overwrites or unverified extraction."""

import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from takoboto_grammar.evidence import backup_evidence, restore_evidence


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='jgram-evidence-test-')).resolve()
        for area in ('data', 'archive-data', 'archive-2015'):
            (self.root / area / 'cache/responses').mkdir(parents=True)
            body = (area + ' ORIGINAL SOURCE').encode()
            (self.root / area / 'cache/responses' / (hashlib.sha256(body).hexdigest() + '.bin')).write_bytes(body)
            (self.root / area / 'inventory.json').write_text('{}')

    def test_exact_bytes_roundtrip_to_fresh_destination(self):
        report = backup_evidence(self.root, self.root / 'evidence.tar.gz')
        self.assertEqual(Path(report['output']).stat().st_mode & 0o777, 0o600)
        destination = self.root / 'restored'
        restored = restore_evidence(report['output'], destination)
        self.assertTrue(restored['hashes_verified'])
        self.assertEqual(destination.stat().st_mode & 0o777, 0o700)
        self.assertEqual(restored['files_restored'], 6)
        self.assertIn('do not publish', report['distribution'])
        for path in self.root.glob('*/cache/responses/*.bin'):
            self.assertEqual(path.read_bytes(), (destination / path.relative_to(self.root)).read_bytes())
        with self.assertRaisesRegex(ValueError, 'fresh destination'):
            restore_evidence(report['output'], destination)

    def test_corrupt_cached_source_hash_is_rejected(self):
        path = next((self.root / 'data/cache/responses').glob('*.bin'))
        path.write_bytes(b'changed source')
        with self.assertRaisesRegex(ValueError, 'cache filename hash'):
            backup_evidence(self.root, self.root / 'corrupt.tar.gz')
        self.assertFalse((self.root / 'corrupt.tar.gz').exists())

    def test_archive_traversal_and_symlink_are_rejected_before_destination_creation(self):
        for number, member in enumerate([tarfile.TarInfo('../escape'), tarfile.TarInfo('data/cache/link')]):
            path = self.root / f'bad-{number}.tar.gz'
            if number: member.type = tarfile.SYMTYPE; member.linkname = '/etc/passwd'
            with tarfile.open(path, 'x:gz') as archive:
                archive.addfile(member, io.BytesIO(b''))
            destination = self.root / f'bad-restore-{number}'
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                restore_evidence(path, destination)
            self.assertFalse(destination.exists())

    def test_manifest_hash_mismatch_is_rejected_before_writing(self):
        path = self.root / 'bad-manifest.tar.gz'
        body = b'wrong bytes'
        name = 'data/inventory.json'
        manifest = json.dumps({'format_version': 1, 'files': [{'path': name, 'bytes': len(body), 'sha256': '0' * 64}]}).encode()
        with tarfile.open(path, 'x:gz') as archive:
            for member_name, content in [(name, body), ('evidence-manifest.json', manifest)]:
                info = tarfile.TarInfo(member_name); info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        with self.assertRaisesRegex(ValueError, 'manifest hash'):
            restore_evidence(path, self.root / 'bad-restored')
        self.assertFalse((self.root / 'bad-restored').exists())
