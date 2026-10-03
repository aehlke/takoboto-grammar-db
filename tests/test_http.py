"""No-network checks for real scheduling, pooling, and redirect boundaries."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

import httpx

from takoboto_grammar.crawl import Fetcher, FetchAccessError, allowed_url
from takoboto_grammar.archive import ArchiveFetcher, ArchiveAccessError
from takoboto_grammar.archive_dump import DumpFetcher, INDEX, ITEM
from takoboto_grammar.http import HttpxOpener, RequestPacer


class Clock:
    def __init__(self):
        self.time = 100.0
    def sleep(self, seconds):
        self.time += seconds


class HttpTests(unittest.TestCase):
    def test_retry_after_stops_all_sources_before_redirect_or_body_read(self):
        sources = [(Fetcher, 'https://takoboto.jp/bunpo/725/', FetchAccessError),
                   (ArchiveFetcher, 'https://web.archive.org/web/20200215021200id_/http://jgram.org/pages/viewOne.php?tagE=ageku', ArchiveAccessError),
                   (DumpFetcher, f'https://archive.org/download/{ITEM}/{INDEX}', ArchiveAccessError)]
        for constructor, url, error_type in sources:
            for status in (200, 302, 404):
                with self.subTest(source=constructor.__name__, status=status):
                    root = Path(tempfile.mkdtemp(prefix='takoboto-retry-after-test-')).resolve()
                    seen = []
                    def respond(request):
                        seen.append(str(request.url))
                        return httpx.Response(status, headers={'Retry-After': '600', 'Location': url}, content=b'body must not be read')
                    with constructor(root) as fetcher:
                        fetcher.opener.client.close()
                        fetcher.opener.client = httpx.Client(transport=httpx.MockTransport(respond))
                        with patch.object(fetcher.opener, 'before_request'):
                            with self.assertRaises(error_type):
                                fetcher.opener.open(Request(url))
                        self.assertEqual(seen, [url])
                        self.assertEqual(fetcher.opener.attempts[0]['bytes_read'], 0)
                        self.assertEqual(fetcher.opener.attempts[0]['error_type'], error_type.__name__)
                        cooldown = json.loads((root / 'access-cooldown.json').read_text())
                        self.assertEqual(cooldown['reason'], f'HTTP {status}')

    def test_public_fetcher_cannot_send_before_robots_check(self):
        root = Path(tempfile.mkdtemp(prefix='takoboto-policy-test-')).resolve()
        with Fetcher(root) as fetcher, patch('httpx.Client.send') as send:
            with self.assertRaisesRegex(FetchAccessError, 'check_robots'):
                fetcher.get('https://takoboto.jp/bunpo/725/')
            send.assert_not_called()
            self.assertEqual(fetcher.opener.attempts, [])

    def test_attempt_reports_include_errors_retries_redirects_and_ignore_cache_hits(self):
        urls = [(Fetcher, 'https://takoboto.jp/bunpo/725/'),
                (ArchiveFetcher, 'https://web.archive.org/web/20200215021200id_/http://jgram.org/pages/viewOne.php?tagE=ageku')]
        for constructor, url in urls:
            with self.subTest(source=constructor.__name__):
                root = Path(tempfile.mkdtemp(prefix='takoboto-telemetry-test-')).resolve()
                seen = []
                def respond(request):
                    seen.append(str(request.url))
                    if len(seen) == 1:
                        raise httpx.ReadTimeout('test timeout', request=request)
                    if len(seen) == 2:
                        return httpx.Response(503)
                    if len(seen) == 3:
                        return httpx.Response(301, headers={'Location': url})
                    return httpx.Response(200, content=b'grammar', headers={'Content-Type': 'text/html'})
                with patch('takoboto_grammar.http.time.sleep'), constructor(root) as fetcher:
                    fetcher.policy_checked = True
                    fetcher.opener.client.close()
                    fetcher.opener.client = httpx.Client(transport=httpx.MockTransport(respond))
                    self.assertEqual(fetcher.get(url)[0], b'grammar')
                    self.assertEqual(fetcher.get(url)[0], b'grammar')
                report = json.loads((root / 'request-report.json').read_text())
                self.assertEqual(report['attempt_count'], 4)
                self.assertEqual([e['status'] for e in report['attempts']], [None, 503, 301, 200])
                self.assertEqual(report['attempts'][0]['error_type'], 'ReadTimeout')
                self.assertEqual(report['attempts'][1]['error_type'], 'HTTPError')
                self.assertEqual(report['attempts'][-1]['bytes_read'], 7)
                self.assertTrue(all(e['duration_seconds'] >= 0 for e in report['attempts']))
                self.assertTrue(fetcher.opener.client.is_closed)
                self.assertEqual(json.loads((root / f"request-reports/{report['run_id']}.json").read_text()), report)

    def test_report_write_failure_still_closes_transport(self):
        for constructor, module in [(Fetcher, 'crawl'), (ArchiveFetcher, 'archive')]:
            root = Path(tempfile.mkdtemp(prefix='takoboto-telemetry-test-')).resolve()
            fetcher = constructor(root)
            with patch(f'takoboto_grammar.{module}.write_json', side_effect=OSError('disk unavailable')):
                with self.assertRaises(OSError):
                    with fetcher:
                        pass
            self.assertTrue(fetcher.opener.client.is_closed)

    def test_batches_rest_after_response_and_keep_interval(self):
        clock = Clock()
        pacer = RequestPacer(1.5, 2, 15)
        starts = []
        with patch('takoboto_grammar.http.time.monotonic', side_effect=lambda: clock.time), \
             patch('takoboto_grammar.http.time.sleep', side_effect=clock.sleep):
            for _ in range(3):
                pacer.wait()
                starts.append(clock.time)
                clock.time += 0.25
                pacer.completed()
        self.assertEqual(starts, [100.0, 101.5, 116.75])

    def test_redirects_are_scheduled_and_scope_checked_before_following(self):
        seen, paced, completed = [], [], []
        def respond(request):
            seen.append(str(request.url))
            return httpx.Response(302, headers={'Location': 'https://external.example/private'})
        opener = HttpxOpener(allowed_url, paced.append, lambda: completed.append(True), 1024)
        opener.client.close()
        opener.client = httpx.Client(transport=httpx.MockTransport(respond))
        try:
            with self.assertRaisesRegex(ValueError, 'out-of-scope'):
                opener.open(Request('https://takoboto.jp/bunpo/725/'))
            self.assertEqual(seen, ['https://takoboto.jp/bunpo/725/'])
            self.assertEqual(paced, seen)
            self.assertEqual(len(completed), 1)
            self.assertEqual(len(opener.attempts), 1)
            self.assertEqual(opener.attempts[0]['status'], 302)
        finally:
            opener.close()

    def test_allowed_redirects_consume_batch_slots(self):
        seen = []
        def respond(request):
            seen.append(str(request.url))
            if len(seen) == 1:
                return httpx.Response(301, headers={'Location': '/bunpo/725/'})
            return httpx.Response(200, text='grammar', headers={'Content-Type': 'text/html'})
        pacer = RequestPacer(0, 5, 15)
        opener = HttpxOpener(allowed_url, lambda url: pacer.wait(), pacer.completed, 1024)
        opener.client.close()
        opener.client = httpx.Client(transport=httpx.MockTransport(respond))
        try:
            with opener.open(Request('https://takoboto.jp/bunpo/725')) as response:
                self.assertEqual(response.read(), b'grammar')
                self.assertEqual(response.url, 'https://takoboto.jp/bunpo/725/')
            self.assertEqual(len(seen), 2)
            self.assertEqual(pacer.request_count, 2)
            self.assertEqual([e['status'] for e in opener.attempts], [301, 200])
        finally:
            opener.close()

    def test_rate_limit_stops_once_and_cooldown_survives_new_fetcher(self):
        root = Path(tempfile.mkdtemp(prefix='takoboto-http-test-')).resolve()
        url = 'https://takoboto.jp/bunpo/725/'
        with Fetcher(root) as fetcher:
            error = HTTPError(url, 429, 'limited', {'Retry-After': '600'}, io.BytesIO())
            with patch.object(fetcher.opener, 'open', side_effect=error) as request:
                with self.assertRaises(FetchAccessError):
                    fetcher.get(url)
                self.assertEqual(request.call_count, 1)
        state = json.loads((root / 'access-cooldown.json').read_text())
        self.assertEqual(state['reason'], 'HTTP 429')
        with Fetcher(root) as fetcher, patch.object(fetcher.opener, 'open') as request:
            with self.assertRaises(FetchAccessError):
                fetcher.get(url)
            request.assert_not_called()

    def test_bad_scheduling_values_fail_without_network(self):
        for args in [(float('nan'), 5, 15), (1, 0, 15), (1, 5, float('inf'))]:
            with self.assertRaises(ValueError):
                RequestPacer(*args)

    def test_bounded_stream_and_get_only(self):
        seen = []
        def respond(request):
            seen.append(str(request.url))
            return httpx.Response(200, content=b'x' * 129)
        opener = HttpxOpener(allowed_url, lambda url: None, lambda: None, 128)
        opener.client.close()
        opener.client = httpx.Client(transport=httpx.MockTransport(respond))
        try:
            with self.assertRaisesRegex(ValueError, 'GET only'):
                opener.open(Request('https://takoboto.jp/bunpo/725/', data=b'change'))
            self.assertEqual(seen, [])
            with self.assertRaisesRegex(ValueError, 'rather than truncate'):
                opener.open(Request('https://takoboto.jp/bunpo/725/'))
            self.assertEqual(len(seen), 1)
        finally:
            opener.close()

    def test_saved_inventory_selector_never_discovers_or_follows_other_pages(self):
        from takoboto_grammar.cli import main
        from takoboto_grammar.storage import write_json
        root = Path(tempfile.mkdtemp(prefix='takoboto-cli-test-')).resolve()
        write_json(root, 'input.json', {'entry_count': 2, 'pages': [], 'entries': [
            {'id': 725, 'source_url': 'https://takoboto.jp/bunpo/725/'},
            {'id': 509, 'source_url': 'https://takoboto.jp/bunpo/509/'}]})
        body = (Path(__file__).parent / 'fixtures/entry725.html').read_bytes()
        import hashlib
        with patch('sys.argv', ['takoboto-grammar', 'crawl', '--id', '725', '--inventory', str(root / 'input.json')]), \
             patch('takoboto_grammar.cli.Fetcher') as constructor, \
             patch('takoboto_grammar.cli.discover', side_effect=AssertionError('No index crawl allowed')):
            fetcher = constructor.return_value.__enter__.return_value
            fetcher.root = root
            fetcher.get.return_value = (body, {'retrieved_at': 'now', 'sha256': hashlib.sha256(body).hexdigest()})
            self.assertEqual(main(), 0)
            fetcher.get.assert_called_once_with('https://takoboto.jp/bunpo/725/')
        report = json.loads((root / 'crawl-report.json').read_text())
        self.assertEqual(report['selected_entries'], 1)
        self.assertFalse(report['complete'])


if __name__ == '__main__':
    unittest.main()
