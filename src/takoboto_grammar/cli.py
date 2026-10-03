import argparse
import hashlib
import json
import sys
import re
from pathlib import Path
from contextlib import ExitStack
from urllib.error import HTTPError, URLError
from urllib.parse import quote

from .crawl import Fetcher, FetchAccessError, crawl, discover
from .http import RequestPacer
from .storage import build_sqlite, export_markdown, preflight_export, read_records, read_archive_records, read_archive_feeds, read_archive_state, record_digest, write_json, cache_response, read_archive_snapshot
from .audit import audit
from .archive import ArchiveFetcher, ArchiveAccessError, original_label, crawl_archive, discover_archive
from .archive_audit import audit_archive
from .archive_feeds import crawl_feeds
from .archive_dump import DumpFetcher, INDEX, ITEM, dump_inventory, crawl_dump
from .markdown import update_markdown
from .storage import migrate_records


def main():
    try:
        with ExitStack() as resources:
            return run(resources)
    except (FetchAccessError, ArchiveAccessError, HTTPError, URLError, TimeoutError) as exc:
        print(f'Stopped: {exc}', file=sys.stderr)
        return 1


def load_inventory(path, parser, historical=False):
    """Check saved manifests completely before initiating an online invocation."""
    try:
        inventory = json.loads(Path(path).expanduser().resolve(strict=True).read_text(encoding='utf-8'))
        entries = inventory['entries']
        if not isinstance(entries, list) or not isinstance(inventory['pages'], list):
            raise ValueError('entries and pages must be lists')
        count = inventory['label_count' if historical else 'entry_count']
        if type(count) is not int or count != len(entries):
            raise ValueError('entry count does not match inventory')
        seen = set()
        for entry in entries:
            key = entry['label' if historical else 'id']
            if historical:
                if not isinstance(key, str) or not key or not entry['captures']:
                    raise ValueError('label must have captures')
                if not isinstance(entry['captures'], list):
                    raise ValueError('captures must be a list')
                if not isinstance(entry.get('alternate_captures', []), list):
                    raise ValueError('alternate captures must be a list')
                timestamps = []
                for position, capture in enumerate(entry['captures'] + entry.get('alternate_captures', [])):
                    if capture['label'] != key:
                        raise ValueError('capture label does not match inventory entry')
                    if not isinstance(capture['original'], str) or not isinstance(capture['archive_url'], str):
                        raise ValueError('capture URLs must be strings')
                    stamp = capture['timestamp']
                    if not isinstance(stamp, str) or not re.fullmatch(r'\d{14}', stamp):
                        raise ValueError('invalid archive timestamp')
                    expected = quote(f"https://web.archive.org/web/{stamp}id_/{capture['original']}", safe="/:?=&;%+@!()*,-._~'")
                    if original_label(capture['original']) != key or capture['archive_url'] != expected:
                        raise ValueError('capture URL does not match label and timestamp')
                    if position < len(entry['captures']):
                        timestamps.append(stamp)
                if timestamps != sorted(timestamps, reverse=True):
                    raise ValueError('captures must be ordered newest first')
            elif type(key) is not int or key <= 0 or entry['source_url'] not in {
                f'https://takoboto.jp/bunpo/{key}', f'https://takoboto.jp/bunpo/{key}/'}:
                raise ValueError('invalid grammar ID or URL')
            if key in seen:
                raise ValueError('duplicate inventory entry')
            seen.add(key)
        if historical and (type(inventory['capture_count']) is not int or
                           inventory['capture_count'] < sum(len(e['captures']) + len(e.get('alternate_captures', [])) for e in entries)):
            raise ValueError('invalid capture count')
        return inventory
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(f'Invalid saved inventory: {exc}')


def validate_selection(inventory, values, key, parser):
    missing = set(values or ()) - {entry[key] for entry in inventory['entries']}
    if missing:
        parser.error(f'{key} values absent from inventory: ' + ', '.join(map(str, sorted(missing))))


def load_records(path, parser):
    try:
        records = read_records(path)
        if any(not isinstance(record['romanized_label'], str) for record in records):
            raise ValueError('current record labels must be strings')
        return records
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(f'Invalid current records: {exc}')


def verified_feed_labels(current, archive_root):
    labels = {record['romanized_label']: record['id'] for record in current}
    path = Path(archive_root).expanduser()
    if path.exists():
        for record in read_archive_records(path, for_export=False):
            state = read_archive_state(path, record['label'])
            if (not state or state['status'] != 'parsed' or state.get('response_sha256') != record['response_sha256']
                or state.get('capture', {}).get('archive_url') != record['archive_url']
                or state.get('record_sha256') != record_digest(record)):
                continue
            if not record['warnings'] and record['license']['id'] == 'CC-BY-SA-2.0':
                labels.setdefault(record['label'], record['id'])
    return labels


def run(resources):
    parser = argparse.ArgumentParser(description="Archive only Takoboto's public grammar dataset")
    commands = parser.add_subparsers(dest="command", required=True)
    migrate = commands.add_parser('migrate-yaml', help='Offline lossless conversion of legacy JSON content records to YAML')
    migrate.add_argument('--input', action='append', help='Source dataset directory (repeatable; defaults to data)')
    check = commands.add_parser("audit", help="Offline comparison of every captured grammar page against extracted records")
    check.add_argument("--input", default="data")
    historical_check = commands.add_parser('archive-audit', help='Offline source and coverage checks for archived JGram records')
    historical_check.add_argument('--input', default='archive-data')
    historical_check.add_argument('--takoboto', default='data', help='Captured current records for independent ID/label eligibility checks')
    dump = commands.add_parser('archive-dump', help='Recover grammar members from the dated February 2015 ArchiveTeam backup')
    dump.add_argument('--output', default='archive-2015')
    dump.add_argument('--takoboto', default='data')
    dump.add_argument('--index', help='Reuse a previously downloaded original compressed CDX index')
    dump.add_argument('--offline', action='store_true')
    dump.add_argument('--contact')
    dump.add_argument('--label', action='append')
    dump.add_argument('--limit', type=int)
    historical_check.add_argument('--record-verification', action='store_true',
                                  help='Offline migration: persist verified states for legacy records without changing their content')
    archive = commands.add_parser('archive', help='Supplement with latest available JGram Wayback captures')
    archive.add_argument('--output', default='archive-data')
    archive.add_argument('--takoboto', default='data', help='Current records for verified ID eligibility')
    archive.add_argument('--delay', type=float, default=5)
    archive.add_argument('--contact')
    archive.add_argument('--refresh', action='store_true')
    archive.add_argument('--offline', action='store_true', help='Reparse cached CDX and replays without any network requests')
    archive.add_argument('--discover-only', action='store_true')
    archive.add_argument('--limit', type=int)
    archive.add_argument('--label', action='append', help='Retrieve specific CDX-discovered labels (repeatable)')
    archive.add_argument('--feeds', action='store_true', help='Also capture latest original grammar RSS feeds and publication metadata')
    archive.add_argument('--inventory', help='Reuse a saved CDX inventory instead of querying the entire index')
    archive.add_argument('--burst-size', type=int, default=3, help='Sequential network requests per batch (default: 3)')
    archive.add_argument('--burst-pause', type=float, default=30, help='Rest after each batch, in seconds (default: 30)')
    feeds = commands.add_parser('archive-feeds', help='Capture only the five original grammar RSS feeds')
    feeds.add_argument('--output', default='archive-data')
    feeds.add_argument('--takoboto', default='data')
    feeds.add_argument('--delay', type=float, default=5)
    feeds.add_argument('--contact')
    feeds.add_argument('--refresh', action='store_true')
    feeds.add_argument('--offline', action='store_true')
    feeds.add_argument('--burst-size', type=int, default=3)
    feeds.add_argument('--burst-pause', type=float, default=30)
    for name in ("discover", "crawl"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--output", default="data")
        cmd.add_argument("--delay", type=float, default=1.5)
        cmd.add_argument("--contact", help="Contact URL or email included in User-Agent")
        cmd.add_argument("--refresh", action="store_true", help="Fetch new snapshots instead of reusing cached HTML")
        cmd.add_argument('--burst-size', type=int, default=5, help='Sequential network requests per batch (default: 5)')
        cmd.add_argument('--burst-pause', type=float, default=15, help='Rest after each batch, in seconds (default: 15)')
        if name == "crawl":
            selection = cmd.add_mutually_exclusive_group()
            selection.add_argument("--limit", type=int, help="Pilot size; omit for the complete discovered collection")
            selection.add_argument('--id', type=int, action='append', dest='ids', help='Only these indexed grammar IDs (repeatable)')
            cmd.add_argument('--inventory', help='Reuse a saved inventory instead of fetching index pages')
    build = commands.add_parser("build", help="Offline exports from records/*.yaml (legacy JSON is readable)")
    build.add_argument("--input", default="data")
    build.add_argument("--sqlite", help="New SQLite file; existing files are never replaced")
    build.add_argument("--markdown", help="Directory for generated Markdown; prefer a fresh directory")
    build.add_argument('--archive', help='Optional directory of supplemental JGram records')
    build.add_argument('--archive-snapshot', action='append', default=[], help='Additional audited dated backup directory (repeatable)')
    readers = commands.add_parser('update-markdown', help='Offline refresh of managed Markdown pages for Git diffs')
    readers.add_argument('--input', default='data')
    readers.add_argument('--archive', help='Optional directory of supplemental JGram records')
    readers.add_argument('--archive-snapshot', action='append', default=[], help='Additional audited dated backup directory (repeatable)')
    readers.add_argument('--output', default='markdown', help='Managed reader directory (default: markdown)')
    args = parser.parse_args()
    if args.command == 'migrate-yaml':
        try:
            report = migrate_records(args.input or ['data'])
        except (OSError, ValueError, TypeError, KeyError) as exc:
            parser.error(f'Cannot migrate records: {exc}')
        print(json.dumps(report, indent=2))
        return 0
    if hasattr(args, 'delay'):
        try:
            RequestPacer(args.delay, args.burst_size, args.burst_pause)
            minimum = 3 if args.command.startswith('archive') else 1
            if args.delay < minimum:
                raise ValueError(f'--delay must be at least {minimum} seconds')
            if getattr(args, 'offline', False) and args.refresh:
                raise ValueError('--offline cannot be combined with --refresh')
        except ValueError as exc:
            parser.error(str(exc))
    if args.command == 'archive-dump':
        if args.limit is not None and args.limit <= 0:
            parser.error('--limit must be positive')
        from .archive_audit import verified_current_records
        current = verified_current_records(args.takoboto)
        fetcher = resources.enter_context(DumpFetcher(args.output, args.contact, args.offline))
        if args.index:
            path = Path(args.index).expanduser().resolve(strict=True)
            if path.stat().st_size > 80 * 1024 * 1024:
                parser.error('Backup index exceeds 80 MiB')
            body = path.read_bytes()
            metadata = {'url': f'https://archive.org/download/{ITEM}/{INDEX}',
                        'imported_local_index': True, 'sha256': hashlib.sha256(body).hexdigest()}
        else:
            body, metadata = fetcher.get(INDEX)
        inventory = dump_inventory(body, metadata)
        cache_response(fetcher.root, f'cache/dump-index/{inventory["index_sha256"]}.gz', body)
        if args.label and set(args.label) - {i['label'] for i in inventory['entries']}:
            parser.error('Requested label absent from backup index')
        write_json(fetcher.root, 'inventory.json', inventory)
        report = crawl_dump(fetcher, inventory, [r['id'] for r in current], args.label, args.limit)
        print(json.dumps({k: v for k, v in report.items() if k not in {'parsed', 'excluded'}}, ensure_ascii=False, indent=2))
        return 1 if report['failed'] or report['review_required'] else 0
    if args.command == 'archive-feeds':
        current = load_records(args.takoboto, parser)
        try:
            feed_labels = verified_feed_labels(current, args.output)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            parser.error(f'Invalid feed eligibility records: {exc}')
        fetcher = resources.enter_context(ArchiveFetcher(args.output, args.delay, args.contact, args.refresh,
            args.offline, args.burst_size, args.burst_pause))
        fetcher.check_access()
        report = crawl_feeds(fetcher, feed_labels)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['complete'] else 1
    if args.command == 'archive':
        if args.limit is not None and args.limit <= 0:
            parser.error('--limit must be positive')
        inventory = load_inventory(args.inventory, parser, historical=True) if args.inventory else None
        if inventory is not None:
            validate_selection(inventory, args.label, 'label', parser)
        current = load_records(args.takoboto, parser) if not args.discover_only else []
        fetcher = resources.enter_context(ArchiveFetcher(args.output, args.delay, args.contact, args.refresh,
            args.offline, args.burst_size, args.burst_pause))
        fetcher.check_access()
        if inventory is None:
            inventory = discover_archive(fetcher)
            validate_selection(inventory, args.label, 'label', parser)
        if args.inventory:
            write_json(fetcher.root, 'inventory.json', inventory)
        action = 'Loaded saved index:' if args.inventory else 'Indexed'
        print(f"{action} {inventory['label_count']} JGram labels from {inventory['capture_count']} captures")
        if args.discover_only:
            return 0
        eligible = [r['id'] for r in current]
        if args.label:
            wanted = set(args.label)
            inventory = dict(inventory, entries=[e for e in inventory['entries'] if e['label'] in wanted])
        else:
            verified = {r['romanized_label'] for r in current}
            inventory = dict(inventory, entries=sorted(inventory['entries'], key=lambda e: (e['label'] not in verified, e['label'])))
        report = crawl_archive(fetcher, inventory, eligible, args.limit)
        feed_report = crawl_feeds(fetcher, verified_feed_labels(current, fetcher.root)) if args.feeds and not report.get('stopped_reason') else None
        print(json.dumps({k: report[k] for k in ['selected_labels', 'review_required', 'failed', 'warnings', 'complete']}, indent=2))
        return 1 if report['failed'] or report['warnings'] or report['review_required'] or (feed_report and not feed_report['complete']) else 0
    if args.command == 'archive-audit':
        try:
            report = audit_archive(args.input, args.takoboto, args.record_verification)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            parser.error(f'Cannot verify archive inputs: {exc}')
        print(json.dumps({k: v for k, v in report.items() if k != 'pending_labels'} |
            {'pending_label_count': len(report['pending_labels'])}, ensure_ascii=False, indent=2))
        return 0 if report['export_ready'] else 1
    if args.command == "audit":
        report = audit(args.input)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["coverage_verified"] else 1
    if args.command == 'update-markdown':
        try:
            records = read_records(args.input)
            archived = read_archive_records(args.archive) if args.archive else []
            for snapshot in args.archive_snapshot:
                archived.extend(read_archive_snapshot(snapshot))
            archived_feeds = read_archive_feeds(args.archive) if args.archive else []
            if not records:
                raise ValueError('No current records found')
            report = update_markdown(records, args.output, archived, archived_feeds)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            parser.error(f'Cannot update Markdown: {exc}')
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if args.command == "build":
        if not args.sqlite and not args.markdown:
            parser.error("build needs --sqlite and/or --markdown")
        try:
            sqlite_target = preflight_export(args.sqlite) if args.sqlite else None
            markdown_target = preflight_export(args.markdown, directory=True) if args.markdown else None
            if sqlite_target and markdown_target and (sqlite_target.is_relative_to(markdown_target)
                                                      or markdown_target.is_relative_to(sqlite_target)):
                raise ValueError('SQLite and Markdown export destinations must not overlap')
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        try:
            records = read_records(args.input)
            archived = read_archive_records(args.archive) if args.archive else []
            for snapshot in args.archive_snapshot:
                archived.extend(read_archive_snapshot(snapshot))
            archived_feeds = read_archive_feeds(args.archive) if args.archive else []
        except (OSError, ValueError, KeyError, TypeError) as exc:
            parser.error(f'Cannot export input records: {exc}')
        if not records:
            parser.error("No records found")
        if args.sqlite:
            print(build_sqlite(records, args.sqlite, archived, archived_feeds))
        if args.markdown:
            print(export_markdown(records, args.markdown, archived, archived_feeds))
        return 0
    if getattr(args, "limit", None) is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if getattr(args, 'ids', None) and any(gid <= 0 for gid in args.ids):
        parser.error('--id must be a positive grammar ID')
    inventory = load_inventory(args.inventory, parser) if getattr(args, 'inventory', None) else None
    if inventory is not None:
        validate_selection(inventory, getattr(args, 'ids', None), 'id', parser)
    fetcher = resources.enter_context(Fetcher(args.output, args.delay, args.contact, args.refresh,
        args.burst_size, args.burst_pause))
    fetcher.check_robots()
    if inventory is None:
        inventory = discover(fetcher)
        validate_selection(inventory, getattr(args, 'ids', None), 'id', parser)
    if getattr(args, 'inventory', None):
        write_json(fetcher.root, 'inventory.json', inventory)
    action = 'Loaded saved inventory:' if getattr(args, 'inventory', None) else 'Discovered'
    print(f"{action} {inventory['entry_count']} entries across {len(inventory['pages'])} index pages")
    if args.command == "crawl":
        if args.ids:
            wanted = set(args.ids)
            inventory = dict(inventory, entries=[e for e in inventory['entries'] if e['id'] in wanted])
        report = crawl(fetcher, inventory, len(inventory['entries']) if args.ids else args.limit)
        print(json.dumps({k: report[k] for k in ("selected_entries", "failed", "warnings", "complete")}, indent=2))
        return 1 if report["failed"] or report["warnings"] else 0
    return 0
