"""Polite, cached HTTP for .gov.in sources. Standard library only.

Why this file is careful:

  * Many Indian government sites sit behind NIC/Akamai WAFs that block
    datacenter IPs and non-browser user agents outright. A naive scraper gets a
    403 wall and the maintainer concludes "the data does not exist". We set a
    real UA with a contact URL, back off properly, and report WAF blocks as a
    distinct outcome so the failure is legible.
  * Every response is cached on disk keyed by URL. Re-running the pipeline
    while developing must not re-hammer a public service.
  * robots.txt is consulted and honoured by default.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from typing import Any, Dict, Optional, Tuple

# Identify honestly. Replace the URL with your fork before running at volume.
USER_AGENT = (
    "nirmaan-bot/0.1 (+https://github.com/dizzybot31/nirmaan; "
    "public infrastructure transparency project; contact via GitHub issues)"
)

DEFAULT_DELAY = 2.0          # seconds between requests to the same host
DEFAULT_TIMEOUT = 45
MAX_RETRIES = 3

CACHE_DIR = os.path.join("data", "raw", "_cache")


class FetchResult:
    __slots__ = ("url", "status", "body", "headers", "from_cache", "outcome", "note")

    def __init__(self, url: str, status: int, body: Optional[bytes],
                 headers: Optional[Dict[str, str]], from_cache: bool,
                 outcome: str, note: str = ""):
        self.url = url
        self.status = status
        self.body = body
        self.headers = headers or {}
        self.from_cache = from_cache
        self.outcome = outcome      # ok | http_error | waf_blocked | timeout | robots_denied | network_error
        self.note = note

    @property
    def ok(self) -> bool:
        return self.outcome == "ok"

    def text(self, encoding: str = "utf-8") -> str:
        if not self.body:
            return ""
        return self.body.decode(encoding, errors="replace")

    def json(self) -> Any:
        return json.loads(self.text())

    def __repr__(self) -> str:
        return "<FetchResult %s %s %s%s>" % (
            self.outcome, self.status, self.url[:70], " (cached)" if self.from_cache else "")


_last_hit: Dict[str, float] = {}
_robots: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}


def _cache_path(url: str) -> str:
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, h[:2], h + ".bin")


def _throttle(host: str, delay: float) -> None:
    last = _last_hit.get(host)
    if last is not None:
        wait = delay - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
    _last_hit[host] = time.time()


def robots_allows(url: str, user_agent: str = USER_AGENT) -> Tuple[bool, str]:
    """Consult robots.txt. Fails open with a note if robots.txt is unreachable."""
    parts = urllib.parse.urlsplit(url)
    origin = "%s://%s" % (parts.scheme, parts.netloc)
    if origin not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(origin + "/robots.txt")
        try:
            req = urllib.request.Request(origin + "/robots.txt", headers={"User-Agent": user_agent})
            with urllib.request.urlopen(req, timeout=15, context=_ssl_ctx()) as resp:
                rp.parse(resp.read().decode("utf-8", "replace").splitlines())
            _robots[origin] = rp
        except Exception:
            _robots[origin] = None
    rp = _robots[origin]
    if rp is None:
        return True, "robots.txt unreachable; proceeding with conservative delay"
    return bool(rp.can_fetch(user_agent, url)), "per robots.txt"


def _ssl_ctx() -> ssl.SSLContext:
    # A number of state government sites still serve incomplete chains. We do
    # NOT disable verification; we just use the system default explicitly so the
    # behaviour is obvious rather than accidental.
    return ssl.create_default_context()


def fetch(url: str, *, use_cache: bool = True, max_age: Optional[float] = None,
          delay: float = DEFAULT_DELAY, timeout: int = DEFAULT_TIMEOUT,
          respect_robots: bool = True, headers: Optional[Dict[str, str]] = None,
          data: Optional[bytes] = None) -> FetchResult:
    """GET (or POST if `data`) with caching, throttling and honest failure modes."""
    cp = _cache_path(url)
    if use_cache and data is None and os.path.exists(cp):
        fresh = max_age is None or (time.time() - os.path.getmtime(cp)) < max_age
        if fresh:
            with open(cp, "rb") as fh:
                body = gzip.decompress(fh.read())
            return FetchResult(url, 200, body, {}, True, "ok", "from disk cache")

    if respect_robots and data is None:
        allowed, why = robots_allows(url)
        if not allowed:
            return FetchResult(url, 0, None, {}, False, "robots_denied", why)

    host = urllib.parse.urlsplit(url).netloc
    hdrs = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
    }
    if headers:
        hdrs.update(headers)

    last_note = ""
    for attempt in range(1, MAX_RETRIES + 1):
        _throttle(host, delay)
        req = urllib.request.Request(url, headers=hdrs, data=data,
                                     method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    try:
                        raw = gzip.decompress(raw)
                    except OSError:
                        pass
                if use_cache and data is None:
                    os.makedirs(os.path.dirname(cp), exist_ok=True)
                    with open(cp, "wb") as fh:
                        fh.write(gzip.compress(raw))
                return FetchResult(url, resp.status, raw, dict(resp.headers), False, "ok")
        except urllib.error.HTTPError as e:
            body = b""
            try:
                body = e.read()
            except Exception:
                pass
            snippet = body[:2000].decode("utf-8", "replace").lower()
            waf_markers = ("access denied", "reference #", "akamai", "request blocked",
                           "incapsula", "cloudflare", "forbidden by waf", "not acceptable")
            if e.code in (403, 406, 429) and any(m in snippet for m in waf_markers):
                return FetchResult(url, e.code, body, {}, False, "waf_blocked",
                                   "WAF/edge block (HTTP %s). Datacenter IPs are commonly "
                                   "refused by NIC-hosted sites; see docs/RUNBOOK.md." % e.code)
            if e.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                last_note = "HTTP %s, retrying" % e.code
                time.sleep(delay * (2 ** attempt))
                continue
            return FetchResult(url, e.code, body, {}, False, "http_error", "HTTP %s" % e.code)
        except (urllib.error.URLError, TimeoutError, ssl.SSLError) as e:
            last_note = "%s: %s" % (type(e).__name__, e)
            if attempt < MAX_RETRIES:
                time.sleep(delay * (2 ** attempt))
                continue
            outcome = "timeout" if "timed out" in str(e).lower() else "network_error"
            return FetchResult(url, 0, None, {}, False, outcome, last_note)

    return FetchResult(url, 0, None, {}, False, "network_error", last_note or "exhausted retries")
