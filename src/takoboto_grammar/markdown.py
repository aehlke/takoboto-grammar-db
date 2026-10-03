"""Refresh managed reader pages in place for reviewable Git diffs."""
import hashlib
import json
import re
import tempfile
from pathlib import Path

from .storage import export_markdown, write_bytes, write_json

MANIFEST = '.generated.json'
PAGE = re.compile(r'(?:README\.md|(?:n[1-5]|unclassified)/[1-9]\d*\.md|'
    r'jgram/(?:(?:[1-9]\d*|unknown)-[a-f0-9]{12}|rss-(?:updates|jlpt[1-4]))\.md)')


def destination(path):
    original = Path(path).expanduser().absolute()
    for item in (original, *original.parents):
        if item.is_symlink():
            raise ValueError(f'Markdown path is a symlink: {item}')
        if item != original and item.exists() and not item.is_dir():
            raise ValueError(f'Markdown parent is not a directory: {item}')
    root = original.resolve()
    if root.exists() and not root.is_dir():
        raise ValueError(f'Markdown output is not a directory: {root}')
    if root.exists():
        for item in root.rglob('*'):
            if item.is_symlink() or not item.resolve().is_relative_to(root):
                raise ValueError(f'Markdown contains a symlink or escaping path: {item}')
    return root


def planned_page(root, name):
    if not isinstance(name, str) or not PAGE.fullmatch(name):
        raise ValueError(f'Invalid generated page path: {name}')
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError(f'Generated page path escapes Markdown directory: {name}')
    if path.exists() and not path.is_file():
        raise ValueError(f'Generated page path is not a file: {name}')
    for parent in path.parents:
        if parent == root:
            break
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise ValueError(f'Generated page parent is not a directory: {parent}')
    return path


def update_markdown(records, directory, archive_records=(), archive_feeds=()):
    root = destination(directory)
    old = {}
    manifest_path = root / MANIFEST
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if not isinstance(manifest, dict) or manifest.get('format') != 'takoboto-grammar-markdown' or manifest.get('version') != 1:
            raise ValueError('Unsupported generated Markdown manifest')
        old = manifest['files']
        if not isinstance(old, dict):
            raise ValueError('Generated Markdown manifest files must be a mapping')
        for name, digest in old.items():
            path = planned_page(root, name)
            if not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest):
                raise ValueError(f'Invalid generated page hash: {name}')
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError(f'Generated page was edited or removed: {name}; preserve manual work before updating')
    elif root.exists() and any(root.iterdir()):
        raise ValueError('Existing Markdown directory has no generated manifest; choose a fresh destination')
    # Complete rendering and validation before changing the managed tree. Keep
    # the fresh staging directory for evidence rather than deleting it.
    stage = Path(tempfile.mkdtemp(prefix='takoboto-markdown-render-')).resolve()
    export_markdown(records, stage, archive_records, archive_feeds)
    bodies = {path.relative_to(stage).as_posix(): path.read_bytes() for path in sorted(stage.rglob('*.md'))}
    fresh = {name: hashlib.sha256(body).hexdigest() for name, body in bodies.items()}
    for name in fresh:
        path = planned_page(root, name)
        if name not in old and path.exists():
            raise ValueError(f'New generated page would overwrite an unmanaged file: {name}')
    updated = sorted(name for name in fresh if fresh[name] != old.get(name))
    obsolete = sorted(set(old) - set(fresh))
    trash = None
    if obsolete:
        parent = Path.home() / '.Trash'
        if parent.is_symlink() or parent.resolve() != parent.absolute():
            raise ValueError('Trash directory is a symlink; inspect before moving obsolete pages')
        if parent.exists() and not parent.is_dir():
            raise ValueError('Trash path is not a directory')
        parent.mkdir(parents=True, exist_ok=True)
        trash = Path(tempfile.mkdtemp(prefix='takoboto-markdown-', dir=parent)).resolve()
    root.mkdir(parents=True, exist_ok=True)
    destination(root)  # Recheck immediately before writes.
    for name in updated:
        write_bytes(root, name, bodies[name])
    for name in obsolete:
        target = trash / name
        assert target.resolve().is_relative_to(trash)
        target.parent.mkdir(parents=True, exist_ok=True)
        planned_page(root, name).rename(target)
    manifest = {'format': 'takoboto-grammar-markdown', 'version': 1, 'files': fresh}
    if not manifest_path.exists() or json.loads(manifest_path.read_text(encoding='utf-8')) != manifest:
        write_json(root, MANIFEST, manifest)
    return {'directory': str(root), 'pages': len(fresh), 'updated': updated,
            'removed': obsolete, 'unchanged': len(fresh) - len(updated),
            'obsolete_pages_moved_to': str(trash) if trash else None}
