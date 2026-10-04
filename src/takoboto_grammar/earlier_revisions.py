"""Explicit earlier indexed observations, independent of latest-label states."""

import hashlib
import json
import re
from pathlib import Path

from .archive_parser import indexed_payload_mismatch, parse_archive
from .section_reviews import verify_credit_references
from .storage import load_record, record_paths, record_digest, require_exportable, annotate_archive_record

KIND = 'earlier-indexed-revision'


def read_earlier_records(directory, for_export=True):
    root = Path(directory).resolve(strict=True)
    records = []
    folder = root / 'earlier-records'
    if folder.is_symlink() or not folder.resolve().is_relative_to(root):
        raise ValueError('Earlier records path escapes dataset')
    if not folder.exists():
        return records
    inventory_path = root / 'inventory.json'
    if inventory_path.is_symlink() or not inventory_path.resolve().is_relative_to(root):
        raise ValueError('Earlier inventory path escapes dataset')
    inventory = json.loads(inventory_path.read_text())
    indexed = {item['label']: item for item in inventory['entries']}
    for path in record_paths(root, 'earlier-records'):
        record = load_record(path)
        label, timestamp = record['label'], record['archive_timestamp']
        key = hashlib.sha256(label.encode()).hexdigest() + '-' + timestamp
        if (not re.fullmatch(r'\d{14}', timestamp) or path.stem != key or
            record.get('observation_kind') != KIND or record.get('archive_schema_version') not in {1, 2} or
            not re.fullmatch(r'[A-Z2-7]{32}', record.get('archive_digest', '')) or record.get('snapshot') or
            record.get('selected_indexed_timestamp') != timestamp):
            raise ValueError('Invalid earlier-revision identity')
        item = indexed[label]
        latest = item['captures'][0]['timestamp']
        if timestamp >= latest or record.get('latest_indexed_timestamp') != latest:
            raise ValueError('Earlier revision is not bound to the full latest inventory')
        matches = [c for c in item['captures'] + item.get('alternate_captures', []) if
                   c['timestamp'] == timestamp and c['original'] == record['source_url'] and
                   c['archive_url'] == record['archive_url'] and c.get('digest') == record['archive_digest']]
        if not matches or any(not isinstance(record.get(field), str) or not record[field].strip()
                              for field in ('selection_reason', 'selection_provenance')):
            raise ValueError('Earlier revision lacks indexed source or selection provenance')
        state_path = root / 'earlier-states' / (key + '.json')
        if state_path.is_symlink() or not state_path.resolve().is_relative_to(root):
            raise ValueError('Earlier state path escapes dataset')
        if for_export:
            require_exportable(record)
            state = json.loads(state_path.read_text())
            if (state.get('status') != 'parsed' or state.get('record_sha256') != record_digest(record) or
                state.get('response_sha256') != record['response_sha256'] or
                state.get('capture') not in matches or state.get('label') != label or
                state.get('latest_indexed_timestamp') != latest):
                raise ValueError('Earlier revision differs from its verification state')
        records.append(record)
    return records


def audit_earlier_records(root, eligible_ids):
    root = Path(root).resolve(strict=True)
    from .archive_audit import cached_body, verify_entry_replay, check_latest_cached_response
    report = {'captured_pages': 0, 'entry_observations': 0, 'errors': [], 'source_verified': False}
    try:
        records = read_earlier_records(root)
        report['captured_pages'] = len(records)
        from .storage import expand_archive_records
        report['entry_observations'] = len(expand_archive_records(records))
        for record in records:
            capture = {'label': record['label'], 'timestamp': record['archive_timestamp'],
                       'original': record['source_url'], 'archive_url': record['archive_url'],
                       'digest': record['archive_digest']}
            verify_entry_replay(capture, record['label'])
            body = cached_body(root, record['response_sha256'])
            if indexed_payload_mismatch(body, capture):
                raise ValueError('Earlier payload differs from selected index digest')
            check_latest_cached_response(root, record['archive_url'], record['response_sha256'], record['archive_url'])
            expected = parse_archive(body, capture, record['retrieved_at'], eligible_ids)
            annotate_archive_record(expected, **{key: record[key] for key in (
                'observation_kind', 'selected_indexed_timestamp', 'latest_indexed_timestamp',
                'selection_reason', 'selection_provenance')})
            if expected != record:
                raise ValueError('Earlier extraction differs from retained source')
            verify_credit_references(record.get('omitted_sections', []),
                                     lambda digest: cached_body(root.parent / 'archive-2015', digest))
        report['source_verified'] = True
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report['errors'].append(str(exc))
    return report
