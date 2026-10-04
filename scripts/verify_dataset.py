"""Verify the committed preservation snapshot and SQLite export offline.

Run with: uv run --locked python scripts/verify_dataset.py
Temporary exports are retained for inspection; source files are never written.
"""

import argparse
import json
import sqlite3
import tempfile
from contextlib import ExitStack, closing
from pathlib import Path
from unittest.mock import patch

from takoboto_grammar import SQLITE_SCHEMA_VERSION
from takoboto_grammar.record_yaml import load_yaml
from takoboto_grammar.sqlite_verification import verify_sqlite_signature
from takoboto_grammar.storage import (
    build_sqlite, read_archive_feeds, read_archive_records, read_archive_snapshot,
    read_records, record_digest, record_paths,
    expand_archive_records,
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(root, baseline_path=Path('recon/dataset-baseline.yaml'),
           sqlite_baseline_path=Path('recon/sqlite-baseline.yaml')):
    original = Path(root).expanduser().absolute()
    root = original.resolve(strict=True)
    require(root == original, 'Repository path contains a symlink')
    baseline = load_yaml((root / baseline_path).read_text(encoding='utf-8'))
    sqlite_baseline = load_yaml((root / sqlite_baseline_path).read_text(encoding='utf-8'))
    paths = []
    for area, folders in [('data', ('records',)),
                         ('archive-data', ('records', 'feeds', 'earlier-records')),
                         ('archive-2015', ('records',))]:
        for folder in folders:
            directory = root / area / folder
            if folder == 'earlier-records' and not directory.exists():
                continue
            require(directory.resolve(strict=True) == directory,
                    f'Unexpected source directory: {directory}')
            selected = record_paths(root / area, folder)
            require(all(p.suffix == '.yaml' for p in selected),
                    f'Canonical content must use YAML: {directory}')
            paths.extend(selected)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
    expected_files = baseline['canonical_yaml_files']
    require(len(paths) == expected_files,
            'Content file count differs from the verified preservation snapshot')

    with ExitStack() as blocked:
        for target in ('httpx.Client.send', 'httpx.AsyncClient.send',
                       'socket.socket.connect', 'socket.socket.connect_ex',
                       'socket.create_connection'):
            blocked.enter_context(patch(target, side_effect=RuntimeError('Network forbidden during dataset verification')))
        current = read_records(root / 'data', for_export=True)
        newer = read_archive_records(root / 'archive-data')
        backup = read_archive_snapshot(root / 'archive-2015')
        feeds = read_archive_feeds(root / 'archive-data')
        groups = dict(current=current, newer=newer, backup=backup, feeds=feeds)
        for name, records in groups.items():
            require(record_digest(records) == baseline['record_digests'][name],
                    f'{name} records differ from the verified provenance baseline')
            require(all(not r['warnings'] for r in records), f'{name} contains held warnings')
        inventory = json.loads((root / 'data/inventory.json').read_text(encoding='utf-8'))
        require({r['id'] for r in current} == {r['id'] for r in inventory['entries']},
                'Current records do not match the discovered inventory')
        out = Path(tempfile.mkdtemp(prefix='takoboto-dataset-verification-')).resolve(strict=True)
        db_path = build_sqlite(current, out / 'grammar.sqlite', newer + backup, feeds)
        with closing(sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)) as db:
            require(db.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'SQLite integrity failure')
            require(not db.execute('PRAGMA foreign_key_check').fetchall(), 'SQLite foreign key failure')
            require(db.execute('PRAGMA user_version').fetchone() == (SQLITE_SCHEMA_VERSION,),
                    'SQLite schema version differs')
            counts = {}
            for table, expected in baseline['counts'].items():
                require(table.isidentifier(), 'Invalid count table name')
                counts[table] = db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
                require(counts[table] == expected, f'{table} count differs from the provenance baseline')
            for table, records in [('entries', current), ('archive_entries', expand_archive_records(newer + backup)),
                                   ('archive_feeds', feeds)]:
                restored = [json.loads(row[0]) for row in db.execute(f'SELECT record_json FROM {table}')]
                require(sorted(restored, key=record_digest) == sorted(records, key=record_digest),
                        f'{table} full record roundtrip differs')
            licenses = db.execute('SELECT DISTINCT license_id, license_url FROM sources').fetchall()
            require(licenses == [('CC-BY-SA-2.0', 'https://creativecommons.org/licenses/by-sa/2.0/')],
                    'Source license differs')
            normalized = verify_sqlite_signature(db, sqlite_baseline['signature'])
    require(before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths},
            'Source files changed during verification')
    return {'canonical_yaml_files': len(paths), 'counts': counts, 'sqlite_integrity': 'ok',
            'foreign_keys': 'ok', 'full_record_roundtrips': True,
            'provenance_hashes_match': True, 'normalized_sqlite_matches_release': True,
            'normalized_tables_and_views': len(normalized['relations']), 'output': str(db_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--baseline', type=Path, default=Path('recon/dataset-baseline.yaml'),
                        help='Verified snapshot report with counts and record_digests; relative to --root')
    parser.add_argument('--sqlite-baseline', type=Path, default=Path('recon/sqlite-baseline.yaml'),
                        help='Independent table/view fingerprints from a verified release; relative to --root')
    args = parser.parse_args()
    try:
        result = verify(args.root, args.baseline, args.sqlite_baseline)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        parser.exit(1, f'Dataset verification failed: {exc}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
