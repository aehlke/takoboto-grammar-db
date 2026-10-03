"""Text interchange records, normalized SQLite, and Markdown derived from the same data."""

import json
import re
import sqlite3
import hashlib
import tempfile
from contextlib import closing
from pathlib import Path

from . import SCHEMA_VERSION, SQLITE_SCHEMA_VERSION


def output_root(path):
    path = Path(path).expanduser()
    if path.is_symlink():
        raise ValueError(f"Output directory is a symlink: {path}")
    resolved = path.resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def safe_target(root, relative):
    root = Path(root).resolve(strict=True)
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError(f"Output escapes intended directory or is a symlink: {path}")
    current = path.parent
    while current != root:
        if current.is_symlink():
            raise ValueError(f"Output parent is a symlink: {current}")
        current = current.parent
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_json(root, relative, value):
    body = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode('utf-8')
    write_bytes(root, relative, body)


def write_bytes(root, relative, body):
    """Replace atomically; failed temporary files remain available for inspection."""
    path = safe_target(root, relative)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '.',
                                    suffix='.tmp', delete=False) as temporary:
        temporary.write(body)
        temporary.flush()
        pending = Path(temporary.name)
    # Recheck after writing, before replacing any existing artifact.
    if safe_target(root, relative) != path or path.parent.resolve() != pending.parent:
        raise ValueError(f'Output path changed during write: {path}')
    pending.replace(path)


def cache_response(root, relative, body):
    path = safe_target(root, relative)
    if path.exists():
        if path.read_bytes() != body:
            raise ValueError(f'Corrupt content-addressed response: {path}')
    else:
        write_bytes(root, relative, body)


def preflight_export(path, directory=False):
    """Validate a fresh export destination without creating files or directories."""
    original = Path(path).expanduser().absolute()
    for item in (original, *original.parents):
        if item.is_symlink():
            raise ValueError(f'Export path is a symlink: {item}')
    target = original.resolve()
    for parent in target.parents:
        if parent.exists() and not parent.is_dir():
            raise ValueError(f'Export parent is not a directory: {parent}')
    if directory:
        if target.exists() and (not target.is_dir() or any(target.iterdir())):
            raise ValueError('Markdown output directory must be fresh/empty (avoid stale pages)')
    elif target.exists():
        raise ValueError(f'Database already exists; choose a fresh export path: {target}')
    return target


def read_records(root):
    root = Path(root).resolve(strict=True)
    records = []
    for path in sorted((root / "records").glob("*.json"), key=lambda p: int(p.stem)):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f"Unexpected record path: {path}")
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["schema_version"] not in {1, SCHEMA_VERSION} or record["id"] != int(path.stem):
            raise ValueError(f"Unsupported schema or mismatched record ID: {path}")
        records.append(record)
    return records


def read_archive_records(directory, for_export=True):
    root = Path(directory).expanduser().resolve(strict=True)
    records = []
    for path in sorted((root / 'records').glob('*.json')):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f'Unexpected archive record path: {path}')
        record = json.loads(path.read_text(encoding='utf-8'))
        if record['archive_schema_version'] != 1 or hashlib.sha256(record['label'].encode()).hexdigest() != path.stem:
            raise ValueError(f'Unsupported or mismatched archive record: {path}')
        if for_export:
            if record['warnings']:
                raise ValueError(f"Historical record needs review before export: {record['label']}")
            state = read_archive_state(root, record['label'])
            if state is None:
                raise ValueError(f"Missing verification state for {record['label']}; run archive-audit --record-verification")
            if state and (state['status'] != 'parsed' or state.get('response_sha256') != record['response_sha256']
                          or state.get('capture', {}).get('archive_url') != record['archive_url']):
                raise ValueError(f"Historical record not exportable after latest attempt ({state['status']}): {record['label']}")
            if state.get('record_sha256') != record_digest(record):
                raise ValueError(f"Historical record differs from verification state: {record['label']}; rerun archive-audit --record-verification")
        records.append(record)
    return records


def read_observation_state(root, identity, folder, field):
    root = Path(root).resolve(strict=True)
    key = hashlib.sha256(identity.encode()).hexdigest()
    path = root / folder / f'{key}.json'
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError(f'Unexpected historical state path: {path}')
    if not path.exists():
        return None
    state = json.loads(path.read_text(encoding='utf-8'))
    if state[field] != identity:
        raise ValueError(f'Mismatched historical state label: {path}')
    return state


def read_archive_state(root, label):
    return read_observation_state(root, label, 'states', 'label')


def read_feed_state(root, path):
    return read_observation_state(root, path, 'feed-states', 'feed_path')


def record_digest(record):
    body = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(body).hexdigest()


def archive_record_key(record):
    identity = record['label']
    if record.get('snapshot'):
        identity = record['snapshot'] + ':' + identity
    return hashlib.sha256(identity.encode()).hexdigest()


def read_archive_snapshot(directory):
    root = Path(directory).expanduser().resolve(strict=True)
    inventory = json.loads((root / 'inventory.json').read_text(encoding='utf-8'))
    records = read_archive_records(root)
    if not inventory.get('snapshot'):
        raise ValueError('Dated archive requires a snapshot inventory')
    for record in records:
        if (record.get('snapshot') != inventory['snapshot'] or
            record.get('retrieval', {}).get('index_sha256') != inventory.get('index_sha256')):
            raise ValueError('Record snapshot provenance differs from its inventory')
    return records


def read_archive_feeds(directory, for_export=True):
    root = Path(directory).expanduser().resolve(strict=True)
    feeds = []
    for path in sorted((root / 'feeds').glob('*.json')):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f'Unexpected feed record path: {path}')
        record = json.loads(path.read_text(encoding='utf-8'))
        if record['feed_schema_version'] != 1 or record['feed_path'] != '/rss/' + path.stem + '.xml':
            raise ValueError(f'Unsupported or mismatched RSS record: {path}')
        if for_export and (record['review_required'] or record['warnings']):
            raise ValueError(f'RSS record needs review before export: {path}')
        state = read_feed_state(root, record['feed_path']) if for_export else None
        if for_export and state is None:
            raise ValueError(f"Missing verification state for {record['feed_path']}; run archive-audit --record-verification")
        if state and (state['status'] != 'parsed' or state.get('response_sha256') != record['response_sha256']
                      or state.get('archive_url') != record['archive_url']):
            raise ValueError(f"RSS record not exportable after latest attempt ({state['status']}): {record['feed_path']}")
        if for_export and state.get('record_sha256') != record_digest(record):
            raise ValueError(f"RSS record differs from verification state: {record['feed_path']}; rerun archive-audit --record-verification")
        feeds.append(record)
    return feeds


def build_sqlite(records, path, archive_records=(), archive_feeds=()):
    path = Path(path).expanduser()
    parent = output_root(path.parent)
    path = safe_target(parent, path.name)
    if path.exists():
        raise ValueError(f"Database already exists; choose a fresh export path: {path}")
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
        db.execute("INSERT INTO metadata VALUES (?,?)", ("schema_version", str(SQLITE_SCHEMA_VERSION)))
        db.execute("INSERT INTO metadata VALUES (?,?)", ("entry_count", str(len(records))))
        db.execute("INSERT INTO metadata VALUES (?,?)", ("archive_entry_count", str(len(archive_records))))
        db.execute('INSERT INTO metadata VALUES (?,?)', ('archive_feed_count', str(len(archive_feeds))))
        db.execute("INSERT INTO sources VALUES (?,?,?,?,?,?,?)", (
            "takoboto", "Takoboto grammar", "https://takoboto.jp/bunpo/",
            "JGram and its contributors", "http://www.jgram.org/",
            "CC-BY-SA-2.0", "https://creativecommons.org/licenses/by-sa/2.0/"))
        if archive_records or archive_feeds:
            db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?)', (
                'jgram-wayback', 'JGram preserved by Internet Archive and ArchiveTeam', 'https://web.archive.org/',
                'JGram and its contributors', 'http://www.jgram.org/', 'CC-BY-SA-2.0',
                'https://creativecommons.org/licenses/by-sa/2.0/'))
        for r in records:
            gid = r["id"]
            db.execute("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                gid, "takoboto", r["source_url"], r["title"], r["romanized_label"],
                r["jlpt_level"], r["meaning"], r["meaning_example"], r["credits_raw"],
                r["original_created_at"], r["original_updated_at"], r["retrieved_at"],
                r["response_sha256"], json.dumps(r, ensure_ascii=False)))
            for position, value in enumerate(r["alternate_forms"]):
                db.execute("INSERT INTO entry_forms VALUES (?,?,?)", (gid, position, value))
            for position, value in enumerate(r.get("meaning_notes", [])):
                db.execute("INSERT INTO meaning_notes VALUES (?,?,?,?,?)", (
                    gid, position, value["language"], value["text"], value["html"]))
            for position, value in enumerate(r["sections"]):
                db.execute("INSERT INTO sections VALUES (?,?,?,?,?,?,?)", (
                    gid, position, value["kind"], value["source_dom_id"], value["body_text"],
                    value["body_html"], value["credits_raw"]))
            for position, value in enumerate(r["formations"]):
                db.execute("INSERT INTO formations VALUES (?,?,?)", (gid, position, value))
            for e in r["examples"]:
                db.execute("INSERT INTO examples VALUES (?,?,?,?,?,?,?,?,?,?)", (
                    gid, e["source_id"], e["position"], e["japanese"], e["reading"],
                    e["japanese_html"], json.dumps(e["segments"], ensure_ascii=False),
                    e["credits_raw"], e["original_created_at"], e["original_updated_at"]))
                for position, t in enumerate(e["translations"]):
                    db.execute("INSERT INTO translations VALUES (?,?,?,?,?,?,?)", (
                        gid, e["source_id"], position, t["language"], t["text"], t["html"],
                        json.dumps(t["segments"], ensure_ascii=False)))
            for c in r["comments"]:
                db.execute("INSERT INTO comments VALUES (?,?,?,?,?,?,?,?,?)", (
                    gid, c["position"], c["source_id"], c["text"], c["html"], c["credits_raw"],
                    c["content_sha256"], c["original_created_at"], c["original_updated_at"]))
            for position, value in enumerate(r["related_entries"]):
                db.execute("INSERT INTO related_entries VALUES (?,?,?,?,?)", (
                    gid, position, value["target_id"], value["label"], value["source_url"]))
        for r in archive_records:
            key = archive_record_key(r)
            db.execute('INSERT INTO archive_entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (
                key, r['id'], r['label'], r['title'], r['source_url'], r['archive_url'], r['archive_timestamp'],
                r['retrieved_at'], r['category'], r['jlpt_level_original'], r['meaning'], r['credits_raw'],
                r['response_sha256'], json.dumps(r, ensure_ascii=False)))
            for note in r['notes']:
                db.execute('INSERT INTO archive_notes VALUES (?,?,?,?,?)', (
                    key, note['position'], note['text'], note['html'], note['credits_raw']))
            for example in r['examples']:
                db.execute('INSERT INTO archive_examples VALUES (?,?,?,?,?,?,?,?)', (
                    key, example['source_id'], example['position'], example['japanese'], example['body_text'],
                    example['body_html'], example['credits_raw'], json.dumps(example['verification_class'])))
            for comment in r['comments']:
                db.execute('INSERT INTO archive_comments VALUES (?,?,?,?,?)', (
                    key, comment['position'], comment['text'], comment['html'], comment['credits_raw']))
            for link in r['related_entries']:
                db.execute('INSERT INTO archive_relationships VALUES (?,?,?,?,?,?,?)', (
                    key, link['position'], link['target_label'], link['label'], link['annotation_text'],
                    link['annotation_html'], link['credits_raw']))
        for feed in archive_feeds:
            db.execute('INSERT INTO archive_feeds VALUES (?,?,?,?,?,?,?)', (
                feed['feed_path'], feed['source_url'], feed['archive_url'], feed['archive_timestamp'],
                feed['retrieved_at'], feed['response_sha256'], json.dumps(feed, ensure_ascii=False)))
            for item in feed['items']:
                db.execute('INSERT INTO archive_feed_items VALUES (?,?,?,?,?,?,?,?,?,?,?)', (
                    feed['feed_path'], item['position'], item['entry_id'], item['label'], item['title'],
                    item['source_url'], item['pub_date_raw'], item['author_raw'], item['creator_raw'],
                    item['body_text'], item['body_html']))
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign key verification failed")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity verification failed")
    return path


def escape_md(value):
    return re.sub(r"([\\`*_{}\[\]<>#|!])", r"\\\1", value or "")


def highlighted(parts):
    out = []
    for part in parts:
        raw = part["text"]
        value = escape_md(raw.strip())
        if part["grammar_highlight"] and value:
            value = f"**{value}**"
        # Keep source boundary spaces: English words cannot be glued together.
        leading = raw[:len(raw) - len(raw.lstrip())]
        trailing = raw[len(raw.rstrip()):] if raw.rstrip() else ""
        out.append(leading + value + trailing)
    return "".join(out).strip()


def relative_page(record):
    level = f"n{record['jlpt_level']}" if record["jlpt_level"] else "unclassified"
    return f"{level}/{record['id']}.md"


def export_markdown(records, directory, archive_records=(), archive_feeds=()):
    root = output_root(directory)
    pages = {r["id"]: relative_page(r) for r in records}
    index = ["# Takoboto grammar\n", "Derived from JGram and Takoboto contributors. "
             "[CC BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0/).\n",
             f"This export contains {len(records)} entries.\n"]
    for r in records:
        lines = [f"# {escape_md(r['title'])}\n",
                 f"Source: [Takoboto #{r['id']}]({r['source_url']})  ",
                 f"Label: {escape_md(r['romanized_label'])}  ",
                 f"JLPT: {'N' + str(r['jlpt_level']) if r['jlpt_level'] else 'unclassified'}  ",
                 f"Credits: {escape_md(r['credits_raw']) or '(not displayed)'}  ",
                 f"Retrieved: {r['retrieved_at']}  ",
                 "License: [CC BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0/)\n"]
        if r["alternate_forms"]:
            lines.append("Other forms: " + ", ".join(escape_md(v) for v in r["alternate_forms"]) + "\n")
        lines.extend(["## Meaning\n", escape_md(r["meaning"]) + "\n"])
        if r["meaning_example"]:
            lines.append(escape_md(r["meaning_example"]) + "\n")
        for note in r.get("meaning_notes", []):
            lines.append((escape_md(note["language"]) or "Additional explanation") + ": " + note["html"] + "\n")
        # Legacy v1 records can have extra meaning fields only in the retained section.
        if r.get("schema_version") == 1:
            section = next((s for s in r["sections"] if s["kind"] == "meaning"), None)
            if section:
                lines.append(section["body_html"] + "\n")
        meaning = next((s for s in r["sections"] if s["kind"] == "meaning"), None)
        if meaning and meaning["credits_raw"]:
            lines.append("Meaning credits: " + escape_md(meaning["credits_raw"]) + "\n")
        if r["formations"]:
            lines.append("## Formation\n")
            lines.extend("- " + escape_md(f) for f in r["formations"])
            lines.append("")
        for section in r["sections"]:
            if section["kind"] == "meaning" or (section["kind"] == "formation" and r["formations"]):
                if section["kind"] == "formation" and section["credits_raw"]:
                    lines.append("Formation credits: " + escape_md(section["credits_raw"]) + "\n")
                continue
            lines.extend([f"## {escape_md(section['kind'].capitalize())}\n", section["body_html"] + "\n",
                          "Credits: " + escape_md(section["credits_raw"]) + "\n"])
        if r["related_entries"]:
            lines.append("## See also\n")
            for target in r["related_entries"]:
                dest = "../" + pages[target["target_id"]] if target["target_id"] in pages else target["source_url"]
                lines.append(f"- [{escape_md(target['label'])}]({dest})")
            lines.append("")
        if r["examples"]:
            lines.append("## Examples\n")
            for e in r["examples"]:
                lines.extend([f"### Example {e['source_id']}\n", highlighted(e["segments"]) + "\n"])
                if e["reading"]:
                    lines.append(escape_md(e["reading"]) + "\n")
                for t in e["translations"]:
                    lines.append(f"{escape_md(t['language']) or 'unknown language'}: {highlighted(t['segments'])}\n")
                lines.append("Credits: " + (escape_md(e["credits_raw"]) or "(not displayed)") + "\n")
        if r["comments"]:
            lines.append("## Discussion\n")
            for c in r["comments"]:
                lines.extend([f"### Comment {c['position'] + 1} — {escape_md(c['credits_raw'])}\n",
                              c["html"] + "\n"])
        lines.append("Original contribution dates are not exposed by the captured public page. "
                     "Comment numbers indicate source order, not permanent IDs.\n")
        safe_target(root, pages[r["id"]]).write_text("\n".join(lines), encoding="utf-8")
        index.append(f"- [{escape_md(r['title'])} (#{r['id']})]({pages[r['id']]})")
    if archive_records:
        index.extend(['', '## Historical JGram observations', '',
                      f'This build contains {len(archive_records)} historical source observations and may cover only part of the archive inventory.', '',
                      'Captures are selected separately per entry; dates below are archive timestamps, not contribution dates.', ''])
    for r in archive_records:
        key = archive_record_key(r)
        name = f"jgram/{r['id'] or 'unknown'}-{key[:12]}.md"
        lines = [f"# {escape_md(r['title'])} — historical JGram", '',
            f"[Archived source]({r['archive_url']})  ", f"Original: {r['source_url']}  ",
            f"Archive timestamp: {r['archive_timestamp']}  ", f"Retrieved: {r['retrieved_at']}  ",
            f"Original JLPT level: {escape_md(r['jlpt_level_original'])} (historical classification)  ",
            f"Credits: {escape_md(r['credits_raw']) or '(not displayed)'}  ",
            'License: [CC BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0/)', '',
            '## Meaning', '', escape_md(r['meaning']), '', escape_md(r['meaning_example']), '']
        if r.get('snapshot'):
            lines[2:2] = [f"Dated backup: {escape_md(r['snapshot'])}. This observation is from the backup, not the final live version.", '',
                f"Recovery: [original WARC]({r['retrieval']['url']}), bytes {r['retrieval']['offset']}–{r['retrieval']['offset'] + r['retrieval']['length'] - 1}.", '']
        if any(s['encoding'] == 'cp932-with-undecodable-bytes' for s in r.get('source_decoding_segments', [])):
            lines[2:2] = ['The original source contains invalid character bytes. Display uses U+FFFD; the exact original bytes and offsets are preserved in the JSON/SQLite record.', '']
        for kind, title in [('notes', 'Notes'), ('examples', 'Examples'), ('comments', 'Discussion'), ('related_entries', 'See also')]:
            if not r[kind]:
                continue
            lines.extend([f'## {title}', ''])
            for item in r[kind]:
                item_name = str(item.get('source_id') or item['position'] + 1)
                lines.extend([f"### {item_name} — {escape_md(item['credits_raw']) or '(not displayed)'}", '',
                    next(item[field] for field in ('html', 'body_html', 'annotation_html') if field in item), ''])
        for section in r['sections']:
            lines.extend([f"## Source section: {escape_md(section['kind'])}", '', section['html'], ''])
        safe_target(root, name).write_text('\n'.join(lines), encoding='utf-8')
        index.append(f"- [{escape_md(r['title'])} ({escape_md(r['label'])})]({name}) — {r['archive_timestamp']}")
    if archive_feeds:
        index.extend(['', '## Original grammar RSS observations', '',
            'Publication dates identify feed events, not individual contribution dates.', ''])
    for feed in archive_feeds:
        name = 'jgram/rss-' + feed['feed_path'].rsplit('/', 1)[-1][:-4] + '.md'
        lines = [f"# {escape_md(feed['title'])}", '', f"[Archived RSS source]({feed['archive_url']})", '',
            f"Archive timestamp: {feed['archive_timestamp']}", f"Retrieved: {feed['retrieved_at']}", '',
            '[CC BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0/). JGram and its contributors.', '',
            'Publication dates are RSS events; they do not date individual examples or comments.', '']
        for item in feed['items']:
            lines.extend([f"## {escape_md(item['title'])}", '',
                f"Publication date as displayed: {escape_md(item['pub_date_raw'])}", ''])
            for field, label in [('author_raw', 'Author'), ('creator_raw', 'Creator')]:
                if item.get(field):
                    lines.extend([f"{label}: {escape_md(item[field])}", ''])
            lines.extend([f"[Original entry]({item['source_url']})", '', item['body_html'], ''])
        if not feed['items']:
            lines.append('This latest captured feed contains no items.')
        safe_target(root, name).write_text('\n'.join(lines), encoding='utf-8')
        index.append(f"- [{escape_md(feed['title'])}]({name}) — {len(feed['items'])} items")
    safe_target(root, "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    return root
