"""Sequential, scoped GETs with resumable, content-addressed response caching."""

import hashlib
import json
import time
from uuid import uuid4
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request
from urllib.robotparser import RobotFileParser

from .parser import BASE, ParseError, parse_entry, parse_index
from .storage import output_root, safe_target, write_json, write_record, cache_response
from .http import HttpxOpener, RequestPacer


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def allowed_url(url):
    p = urlsplit(url)
    if p.scheme != "https" or p.netloc != "takoboto.jp" or p.fragment:
        return False
    if p.path == "/robots.txt":
        return not p.query
    if p.path == "/bunpo/":
        q = parse_qs(p.query, keep_blank_values=True)
        return (not p.query) or (bool(q) and not set(q) - {"page", "filter"}
            and ("page" not in q or (len(q["page"]) == 1 and q["page"][0].isdigit() and int(q["page"][0]) > 0))
            and ("filter" not in q or (len(q["filter"]) == 1 and q["filter"][0] in {"jlpt1", "jlpt2", "jlpt3", "jlpt4"})))
    import re
    return bool(re.fullmatch(r"/bunpo/[1-9]\d*/?", p.path)) and not p.query


class FetchAccessError(RuntimeError):
    pass


class Fetcher:
    def __init__(self, directory, delay=1.5, contact=None, refresh=False, burst_size=5, burst_pause=15):
        if delay < 1:
            raise ValueError("Delay must be at least one second")
        self.pacer = RequestPacer(delay, burst_size, burst_pause)
        self.root = output_root(directory)
        self.delay, self.refresh = delay, refresh
        self.ua = "takoboto-grammar-db/0.2 (public grammar archive" + (f"; {contact}" if contact else "") + ")"
        self.opener = HttpxOpener(allowed_url, self.before_request, self.pacer.completed, 10 * 1024 * 1024)
        self.run_id = uuid4().hex
        self.robots = None
        self.policy_checked = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        try:
            report = {'run_id': self.run_id, 'finished_at': now(), **self.pacer.settings(),
                      'attempt_count': len(self.opener.attempts), 'attempts': self.opener.attempts}
            write_json(self.root, f'request-reports/{self.run_id}.json', report)
            write_json(self.root, 'request-report.json', report)
        finally:
            self.opener.close()

    def before_request(self, url):
        if url != BASE + '/robots.txt' and not self.policy_checked:
            raise FetchAccessError('Call check_robots() before online grammar retrieval')
        if self.robots is not None and not self.robots.can_fetch(self.ua, url):
            raise FetchAccessError(f'robots.txt disallows: {url}')
        self.pacer.delay = self.delay
        self.pacer.wait()

    def stop_with_backoff(self, url, status, retry_after=None):
        wait = 300
        if retry_after:
            try:
                wait = max(wait, int(retry_after) if retry_after.isdigit() else
                    (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError, OverflowError):
                pass
        write_json(self.root, 'access-cooldown.json', {'until_epoch': time.time() + wait,
            'reason': f'HTTP {status}', 'url': url, 'recorded_at': now()})
        raise FetchAccessError(f'Server returned HTTP {status}; stopped with persisted backoff')

    def get(self, url):
        if not allowed_url(url):
            raise ValueError(f"Refusing out-of-scope URL: {url}")
        if self.robots is not None and not self.robots.can_fetch(self.ua, url):
            raise FetchAccessError(f"robots.txt disallows: {url}")
        key = hashlib.sha256(url.encode()).hexdigest()
        meta_path = safe_target(self.root, f"cache/urls/{key}.json")
        if meta_path.exists() and not self.refresh:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            raw_path = safe_target(self.root, f"cache/responses/{meta['sha256']}.html")
            body = raw_path.read_bytes()
            if hashlib.sha256(body).hexdigest() != meta["sha256"] or meta["url"] != url:
                raise ValueError(f"Corrupt cached response: {url}")
            return body, meta
        cooldown = safe_target(self.root, 'access-cooldown.json')
        if cooldown.exists() and json.loads(cooldown.read_text())['until_epoch'] > time.time():
            raise FetchAccessError('Backoff is still active; resume after access-cooldown.json time')
        for attempt in range(3):
            try:
                with self.opener.open(Request(url, headers={"User-Agent": self.ua}), timeout=30) as response:
                    body = response.read(10 * 1024 * 1024 + 1)
                    if len(body) > 10 * 1024 * 1024:
                        raise ValueError(f"Unexpectedly large response: {url}")
                    content_type = response.headers.get("Content-Type", "")
                    if url != BASE + "/robots.txt" and "text/html" not in content_type:
                        raise ValueError(f"Expected HTML, got {content_type}: {url}")
                    meta = {"url": url, "final_url": response.url, "status": response.status,
                            "retrieved_at": now(), "sha256": hashlib.sha256(body).hexdigest(),
                            "headers": {k: response.headers[k] for k in ("Content-Type", "Date", "ETag", "Last-Modified") if k in response.headers}}
                break
            except HTTPError as exc:
                exc.close()
                retry = exc.headers.get('Retry-After')
                if exc.code in {401, 403, 429} or (500 <= exc.code <= 599 and (retry or attempt == 2)):
                    self.stop_with_backoff(url, exc.code, retry)
                if exc.code not in {500, 502, 503, 504} or attempt == 2:
                    raise
                wait = 2 ** (attempt + 1)
                time.sleep(wait)
            except (URLError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(2 ** (attempt + 1))
        cache_response(self.root, f"cache/responses/{meta['sha256']}.html", body)
        stamp = meta["retrieved_at"].replace(":", "-")
        write_json(self.root, f"cache/snapshots/{key}/{stamp}-{meta['sha256']}.json", meta)
        write_json(self.root, f"cache/urls/{key}.json", meta)
        return body, meta

    def check_robots(self):
        # Check current policy once per online invocation, even when content is cached.
        refresh = self.refresh
        self.refresh = True
        try:
            body, _ = self.get(BASE + "/robots.txt")
        finally:
            self.refresh = refresh
        self.robots = RobotFileParser()
        self.robots.parse(body.decode("utf-8").splitlines())
        self.policy_checked = True
        crawl_delay = self.robots.crawl_delay(self.ua)
        if crawl_delay:
            self.delay = max(self.delay, crawl_delay)
        rate = self.robots.request_rate(self.ua)
        if rate:
            self.delay = max(self.delay, rate.seconds / rate.requests)
        self.pacer.delay = self.delay
        write_json(self.root, 'access-policy.json', {'checked_at': now(), **self.pacer.settings(),
            'requests': 'GET only; stop on denials, rate limiting, server Retry-After and exhausted server retries'})


def discover(fetcher):
    entries, pages, visited = {}, [], set()
    url = BASE + "/bunpo/"
    while url:
        if url in visited:
            raise ParseError(f"Pagination loop: {url}")
        visited.add(url)
        body, meta = fetcher.get(url)
        rows, next_pages = parse_index(body, url)
        if not rows:
            raise ParseError(f"Empty index page: {url}")
        for row in rows:
            if row["id"] in entries:
                raise ParseError(f"Duplicate entry across index pages: {row['id']}")
            entries[row["id"]] = row
        pages.append({"url": url, "entry_count": len(rows), "retrieved_at": meta["retrieved_at"], "response_sha256": meta["sha256"]})
        if next_pages:
            current = int(parse_qs(urlsplit(url).query).get("page", ["1"])[0])
            if next_pages[0][0] != current + 1:
                raise ParseError(f"Pagination gap after {url}")
        url = next_pages[0][1] if next_pages else None
    inventory = {"retrieved_at": now(), "entry_count": len(entries), "pages": pages, "entries": list(entries.values())}
    write_json(fetcher.root, "inventory.json", inventory)
    return inventory


def crawl(fetcher, inventory, limit=None):
    entries = list(inventory["entries"][:limit] if limit else inventory["entries"])
    queued = {e["id"] for e in entries}
    indexed = {e["id"] for e in inventory["entries"]}
    report = {"started_at": now(), "discovered_entries": inventory["entry_count"],
              "selected_entries": len(entries), "parsed": [], "failed": [], "warnings": [],
              "linked_entries_outside_index": [],
              "finished_at": None, "complete": False}
    for index, item in enumerate(entries, 1):
        gid = item["id"]
        try:
            body, meta = fetcher.get(item["source_url"])
            record = parse_entry(body, gid, meta["retrieved_at"], meta["sha256"])
            write_record(fetcher.root, f"records/{gid}.yaml", record)
            report["parsed"].append(gid)
            if record["warnings"]:
                report["warnings"].append({"id": gid, "messages": record["warnings"]})
            if limit is None:
                for reference in record["related_entries"]:
                    target_id = reference["target_id"]
                    if target_id not in queued:
                        queued.add(target_id)
                        item = {"id": target_id, "source_url": f"{BASE}/bunpo/{target_id}/", "discovered_from": gid}
                        entries.append(item)
                        if target_id not in indexed:
                            report["linked_entries_outside_index"].append(item)
                report["selected_entries"] = len(entries)
                report["discovered_entries"] = len(queued)
            print(f"[{index}/{len(entries)}] #{gid}: {len(record['examples'])} examples, {len(record['comments'])} comments", flush=True)
        except FetchAccessError as exc:
            report['failed'].append({'id': gid, 'error': str(exc)})
            report['stopped_reason'] = str(exc)
            break
        except (ParseError, HTTPError, URLError, TimeoutError) as exc:
            report["failed"].append({"id": gid, "error": str(exc)})
            print(f"[{index}/{len(entries)}] #{gid} FAILED: {exc}", flush=True)
            if isinstance(exc, HTTPError) and exc.code in {401, 403, 429}:
                report["stopped_reason"] = f"HTTP {exc.code}: stop and resume after resolving the server response"
                break
            if len(report["failed"]) >= 3 and all(e["id"] not in report["parsed"] for e in entries[max(0, index - 3):index]):
                report["stopped_reason"] = "Three consecutive failures; inspect cached responses before resuming"
                break
        except Exception as exc:
            report["failed"].append({"id": gid, "error": str(exc)})
            write_json(fetcher.root, "crawl-report.json", report)
            raise
        write_json(fetcher.root, "crawl-report.json", report)
    report["finished_at"] = now()
    report["complete"] = not report["failed"] and not report["warnings"] and limit is None and len(report["parsed"]) == len(queued)
    write_json(fetcher.root, "crawl-report.json", report)
    return report
