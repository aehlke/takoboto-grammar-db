"""Pooled HTTPX GETs and one conservative request schedule per source host."""

import math
import re
import time
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from datetime import datetime, timezone

import httpx


class RequestPacer:
    def __init__(self, delay, burst_size, burst_pause):
        if not math.isfinite(delay) or delay < 0:
            raise ValueError('Request delay must be finite and nonnegative')
        if not isinstance(burst_size, int) or burst_size < 1:
            raise ValueError('Burst size must be a positive integer')
        if not math.isfinite(burst_pause) or burst_pause < 0:
            raise ValueError('Burst pause must be finite and nonnegative')
        self.delay, self.burst_size, self.burst_pause = delay, burst_size, burst_pause
        self.request_count = 0
        self.last_start = None
        self.rest_until = 0.0

    def wait(self):
        deadline = max(self.rest_until, (self.last_start + self.delay) if self.last_start is not None else 0)
        time.sleep(max(0, deadline - time.monotonic()))
        self.last_start = time.monotonic()
        self.request_count += 1

    def completed(self):
        if self.request_count % self.burst_size == 0:
            self.rest_until = time.monotonic() + self.burst_pause

    def settings(self):
        return {'request_interval_seconds': self.delay, 'burst_size': self.burst_size,
            'burst_pause_seconds': self.burst_pause, 'concurrency': 1}


class Response(BytesIO):
    """Small file-like response matching the existing cache reader interface."""
    def __init__(self, body, response):
        super().__init__(body)
        self.url, self.status, self.headers = str(response.url), response.status_code, response.headers


class HttpxOpener:
    def __init__(self, allowed_url, before_request, completed, max_bytes, on_retry_after=None):
        self.allowed_url, self.before_request, self.completed = allowed_url, before_request, completed
        self.max_bytes = max_bytes
        self.on_retry_after = on_retry_after
        self.attempts = []
        self.client = httpx.Client(follow_redirects=False,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1, keepalive_expiry=60))

    def open(self, request, timeout=30):
        if request.get_method() != 'GET':
            raise ValueError('Scraper transport permits GET only')
        url = request.full_url
        for _ in range(6):
            if not self.allowed_url(url):
                raise ValueError(f'Refusing out-of-scope URL or redirect: {url}')
            self.before_request(url)
            started = time.monotonic()
            event = {'url': url, 'started_at': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
                     'status': None, 'bytes_read': 0, 'error_type': None}
            try:
                with self.client.stream('GET', url, headers=dict(request.header_items()), timeout=timeout) as response:
                    event['status'] = response.status_code
                    if response.headers.get('Retry-After') and self.on_retry_after:
                        self.on_retry_after(str(response.url), response.status_code, response.headers['Retry-After'])
                    if response.is_redirect and response.headers.get('Location'):
                        url = urljoin(str(response.url), response.headers['Location'])
                        continue
                    if response.status_code >= 400:
                        raise HTTPError(str(response.url), response.status_code, response.reason_phrase,
                            response.headers, BytesIO())
                    requested_range = request.get_header('Range')
                    if requested_range:
                        bounds = re.fullmatch(r'bytes=(\d+)-(\d+)', requested_range)
                        returned = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                        if (response.status_code != 206 or not bounds or not returned or
                            bounds.groups() != returned.groups()[:2] or int(returned[3]) <= int(returned[2])):
                            raise ValueError('Server did not honor the exact byte range; stopped before reading the body')
                    body = bytearray()
                    for chunk in response.iter_bytes(chunk_size=65536):
                        body.extend(chunk)
                        event['bytes_read'] = len(body)
                        if len(body) > self.max_bytes:
                            raise ValueError(f'Response exceeds {self.max_bytes} bytes; stop rather than truncate')
                    if requested_range and len(body) != int(bounds[2]) - int(bounds[1]) + 1:
                        raise ValueError('Truncated byte-range response')
                    return Response(bytes(body), response)
            except httpx.TimeoutException as exc:
                event['error_type'] = type(exc).__name__
                raise TimeoutError(str(exc)) from exc
            except httpx.RequestError as exc:
                event['error_type'] = type(exc).__name__
                raise URLError(str(exc)) from exc
            except BaseException as exc:
                event['error_type'] = type(exc).__name__
                raise
            finally:
                event['duration_seconds'] = round(time.monotonic() - started, 6)
                self.attempts.append(event)
                self.completed()
        raise ValueError('Too many redirects; inspect before resuming')

    def close(self):
        self.client.close()
