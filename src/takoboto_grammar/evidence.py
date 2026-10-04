"""Private, hash-verified evidence backups for reproducible offline source audits."""

import hashlib
import io
import json
import os
import re
import tarfile
from pathlib import Path, PurePosixPath

from .storage import output_root, safe_target, write_bytes

AREAS = ('data', 'archive-data', 'archive-2015')
FOLDERS = {'records', 'earlier-records', 'earlier-states', 'feeds', 'states', 'feed-states', 'cache', 'review-records', 'request-reports', 'crawl-reports'}
FILES = {'inventory.json', 'coverage-report.json', 'crawl-report.json', 'feed-crawl-report.json',
         'dump-crawl-report.json', 'request-report.json', 'dump-request-report.json',
         'access-policy.json', 'access-cooldown.json'}
MAX_FILE = 80 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024


def allowed_path(name):
    parts = PurePosixPath(name).parts
    return (len(parts) >= 2 and parts[0] in AREAS and
            not any(part in {'.', '..'} or part.startswith('.') for part in parts) and
            (len(parts) >= 3 and parts[1] in FOLDERS or len(parts) == 2 and parts[1] in FILES) and
            str(PurePosixPath(name)) == name)


def evidence_paths(root):
    paths = []
    for area in AREAS:
        directory = root / area
        if directory.resolve(strict=True) != directory:
            raise ValueError('Evidence dataset contains a symlink')
        for path in sorted(directory.rglob('*')):
            if path.is_symlink() or not path.resolve().is_relative_to(directory):
                raise ValueError('Evidence source contains a symlink')
            if path.is_file() and allowed_path(path.relative_to(root).as_posix()):
                paths.append(path)
    return paths


def backup_evidence(root, output):
    original = Path(root).expanduser().absolute()
    root = original.resolve(strict=True)
    if original != root:
        raise ValueError('Evidence source contains a symlink')
    output = Path(output).expanduser().absolute()
    parent = output_root(output.parent)
    output = safe_target(parent, output.name)
    if output.exists() or output.is_relative_to(root / 'data') or output.is_relative_to(root / 'archive-data') or output.is_relative_to(root / 'archive-2015'):
        raise ValueError('Choose a fresh evidence filename outside source datasets')
    inputs, total = [], 0
    paths = evidence_paths(root)
    for path in paths:
        name = path.relative_to(root).as_posix()
        body = path.read_bytes()
        total += len(body)
        if len(body) > MAX_FILE or total > MAX_TOTAL:
            raise ValueError('Evidence exceeds bounded backup size')
        digest = hashlib.sha256(body).hexdigest()
        if path.parent.name in {'responses', 'warc-members', 'dump-index'} and re.fullmatch(r'[0-9a-f]{64}', path.stem) and path.stem != digest:
            raise ValueError('Evidence cache filename hash differs from its bytes')
        inputs.append((path, name, body, digest))
    manifest = {'format_version': 1, 'distribution': 'private evidence; includes unreleased third-party source material; do not publish',
                'files': [{'path': name, 'bytes': len(body), 'sha256': digest} for _, name, body, digest in inputs]}
    # Create privately from the outset; raw held sections are not release data.
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
        with tarfile.open(fileobj=stream, mode='w:gz') as archive:
            for _, name, body, _ in inputs:
                info = tarfile.TarInfo(name); info.size = len(body); info.mode = 0o600
                archive.addfile(info, io.BytesIO(body))
            body = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
            info = tarfile.TarInfo('evidence-manifest.json'); info.size = len(body); info.mode = 0o600
            archive.addfile(info, io.BytesIO(body))
    try:
        changed = evidence_paths(root) != paths or any(path.read_bytes() != body for path, _, body, _ in inputs)
    except OSError as exc:
        raise ValueError('Evidence changed while backing up; retry after the crawl stops') from exc
    if changed:
        raise ValueError('Evidence changed while backing up; retry after the crawl stops')
    return {'output': str(output), 'files': len(inputs), 'uncompressed_bytes': total,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'distribution': manifest['distribution']}


def restore_evidence(bundle, destination):
    bundle = Path(bundle).expanduser().absolute()
    if bundle.resolve(strict=True) != bundle:
        raise ValueError('Evidence bundle contains a symlink')
    destination = Path(destination).expanduser().absolute()
    if destination.resolve() != destination or destination.exists():
        raise ValueError('Evidence restore requires a fresh destination without symlinks')
    payloads, total = {}, 0
    with tarfile.open(bundle, 'r:gz') as archive:
        for member in archive:
            if not member.isfile() or member.name in payloads or not (member.name == 'evidence-manifest.json' or allowed_path(member.name)):
                raise ValueError('Unsafe or duplicate evidence archive member')
            total += member.size
            if member.size > MAX_FILE or total > MAX_TOTAL:
                raise ValueError('Evidence exceeds bounded restore size')
            payloads[member.name] = archive.extractfile(member).read()
    manifest = json.loads(payloads.pop('evidence-manifest.json'))
    expected = {item['path']: item for item in manifest['files']}
    if manifest['format_version'] != 1 or len(expected) != len(manifest['files']) or expected.keys() != payloads.keys():
        raise ValueError('Evidence manifest inventory differs from archive')
    for name, body in payloads.items():
        if len(body) != expected[name]['bytes'] or hashlib.sha256(body).hexdigest() != expected[name]['sha256']:
            raise ValueError('Evidence manifest hash or size mismatch')
    parent = output_root(destination.parent)
    root = safe_target(parent, destination.name)
    root.mkdir(mode=0o700)
    for name, body in payloads.items():
        write_bytes(root, name, body)
    return {'destination': str(root), 'files_restored': len(payloads), 'hashes_verified': True}
