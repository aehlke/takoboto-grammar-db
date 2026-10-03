"""Independent, offline source-to-record coverage checks for captured grammar pages."""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment

from .parser import parse_entry, text
from .storage import read_records, write_json, check_current_export


def audit(directory):
    root = Path(directory).expanduser().resolve(strict=True)
    inventory = json.loads((root / "inventory.json").read_text(encoding="utf-8"))
    indexed = {e["id"] for e in inventory["entries"]}
    records = read_records(root)
    report = {"indexed_entries": len(indexed), "captured_entries": len(records),
              "missing_indexed_ids": sorted(indexed - {r["id"] for r in records}),
              "errors": [], "warnings": [], "unmapped_source_text": [],
              "nonflag_assets": [], "unexpected_links": [], "date_metadata": [],
              "external_reference_links": [],
              "additional_meaning_ids": [], "related_ids_outside_index": [],
              "counts": {}, "coverage_verified": False}
    counts = Counter()
    related_ids = set()
    for record in records:
        gid = record["id"]
        try:
            check_current_export(root, record)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            report['errors'].append({'id': gid, 'error': str(exc)})
        body = (root / "cache/responses" / (record["response_sha256"] + ".html")).read_bytes()
        if hashlib.sha256(body).hexdigest() != record["response_sha256"]:
            report["errors"].append({"id": gid, "error": "Response hash mismatch"})
            continue
        expected = parse_entry(body, gid, record["retrieved_at"], record["response_sha256"])
        if expected != record:
            report["errors"].append({"id": gid, "error": "Stored extraction differs from current parser; reparse cache"})
        report["warnings"].extend({"id": gid, "warning": w} for w in record["warnings"])
        soup = BeautifulSoup(body, "html.parser", from_encoding="utf-8")
        main = soup.select_one(f"#editable_Main_{gid}")
        area = main.parent.parent
        if not area.select_one(f"#editable_Meaning_{gid}"):
            report["errors"].append({"id": gid, "error": "Cannot identify grammar content region"})
            continue
        source_examples = area.select('[id^="editable_Phrase_"]')
        source_comments = area.select('#GrammarCommentsDiv .GrammarPartDiv')
        for kind, expected_count, actual_count in [
            ("examples", len(source_examples), len(record["examples"])),
            ("comments", len(source_comments), len(record["comments"]))]:
            if expected_count != actual_count:
                report["errors"].append({"id": gid, "error": f"{kind} count mismatch: source {expected_count}, extracted {actual_count}"})
            counts[kind] += actual_count
        for source, extracted in zip(source_examples, record["examples"]):
            for node, actual, label in [
                (source.select_one('div[lang="ja"]'), extracted["japanese"], "Japanese"),
            ]:
                if text(node) != actual:
                    report["errors"].append({"id": gid, "error": f"{label} text mismatch at example {extracted['source_id']}"})
            flags = source.select('img[src^="/flags/"]')
            if len(flags) != len(extracted["translations"]):
                report["errors"].append({"id": gid, "error": "Translation count mismatch"})
            counts["translations"] += len(extracted["translations"])
        for source, extracted in zip(source_comments, record["comments"]):
            parts = source.find_all('div', recursive=False)
            author = (text(parts[1]) or None) if len(parts) == 2 else None
            if text(parts[0]) != extracted["text"] or author != extracted["credits_raw"]:
                report["errors"].append({"id": gid, "error": "Comment text or credit mismatch"})
        meaning = area.select_one(f'#editable_Meaning_{gid} .GrammarPartDiv > div')
        fields = meaning.find_all('span', recursive=False)
        if [text(f) for f in fields[2:]] != [n["text"] for n in record.get("meaning_notes", [])]:
            report["errors"].append({"id": gid, "error": "Additional meaning fields omitted"})
        if fields[2:]:
            report["additional_meaning_ids"].append(gid)
        counts["meaning_notes"] += len(fields[2:])
        counts["formations"] += len(record["formations"])
        counts["alternate_forms"] += len(record["alternate_forms"])
        counts["relationships"] += len(record["related_entries"])
        related_ids.update(r["target_id"] for r in record["related_entries"])
        # Account for every non-empty text node outside recognized content wrappers.
        for leaf in area.find_all(string=True):
            if isinstance(leaf, Comment) or not leaf.strip():
                continue
            if any(p.name in {'script', 'style'} or p.get('id', '').startswith('editable_')
                   or p.get('id') == 'GrammarCommentsDiv' for p in leaf.parents):
                continue
            parent = leaf.parent
            if parent.name == 'a' and re.fullmatch(r'/bunpo/\d+/?', parent.get('href', '')):
                continue
            if leaf.strip() not in {'Meaning', 'Formation', 'See also', 'Phrases', 'Discussion and comments', 'Show comments >', ','}:
                report["unmapped_source_text"].append({"id": gid, "text": str(leaf)})
        for image in area.select('img'):
            if not image.get('src', '').startswith('/flags/'):
                report["nonflag_assets"].append({"id": gid, "html": str(image)})
        for link in area.select('a[href]'):
            href = link['href']
            if not (href.startswith(('#', '/?q=')) or re.fullmatch(r'/bunpo/\d+/?', href)):
                fragments = [s['body_html'] for s in record['sections']] + [c['html'] for c in record['comments']]
                retained = any(urljoin('https://takoboto.jp', href) in
                    [a.get('href') for a in BeautifulSoup(html, 'html.parser').select('a[href]')] for html in fragments)
                report['external_reference_links' if retained else 'unexpected_links'].append({'id': gid, 'url': href})
        for node in area.select('time,[datetime],[data-date],[data-timestamp],input[type="hidden"]'):
            report["date_metadata"].append({"id": gid, "html": str(node)})
    report["related_ids_outside_index"] = sorted(related_ids - indexed)
    counts["entries"] = len(records)
    report["counts"] = dict(counts)
    report["additional_meaning_ids"].sort()
    report["coverage_verified"] = not any(report[k] for k in (
        "missing_indexed_ids", "errors", "warnings", "unmapped_source_text", "nonflag_assets",
        "unexpected_links", "date_metadata")) and related_ids.issubset({r["id"] for r in records})
    write_json(root, "coverage-report.json", report)
    return report
