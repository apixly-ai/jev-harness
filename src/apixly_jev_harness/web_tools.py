"""Source-driven, read-only web discovery over HTTP or a named Camofox tab.

Captured text is retained in an EvidenceStore, not admitted wholesale to Jev.
Only links from the current acquisition become tool parameters. Browser origin
checks constrain targets and final observations; they are not a network firewall
for redirects or subresources inside the separate Camofox service.
"""

import copy
import hashlib
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from .engine import DecisionStop
from .task import Option, Parameter

READ_LIMIT = 1200
REDIRECT_CODES = {301, 302, 303, 307, 308}


def _origin(url):
    if type(url) is not str or any(ord(char) <= 32 for char in url):
        raise ValueError("web_http_url_required")
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("web_http_url_required")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("web_url_credentials_forbidden")
        host = parsed.hostname.lower()
        if ":" in host:
            host = "[" + host + "]"
        port = parsed.port
        suffix = f":{port}" if port and port != {"http": 80, "https": 443}[parsed.scheme] else ""
        return f"{parsed.scheme}://{host}{suffix}"
    except (ValueError, UnicodeError):
        raise ValueError("web_http_url_required") from None


def _scope(allowed_origins, url=None):
    values = [url] if allowed_origins is None and url else allowed_origins
    if not isinstance(values, (list, tuple, set)) or not values:
        raise ValueError("web_allowed_origins_required")
    return frozenset(_origin(value) for value in values)


def _check_url(url, allowed_origins):
    try:
        permitted = _origin(url) in allowed_origins
    except ValueError:
        permitted = False
    if not permitted:
        raise DecisionStop("blocked", "web_origin_not_allowed")
    return url


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def _sections(text, headings, title):
    starts, cursor = [], 0
    for heading in headings:
        if type(heading) is not str or not heading.strip():
            continue
        label = heading.strip()
        pattern = re.compile(r"(?m)^" + re.escape(label) + r"[ \t]*$")
        found = pattern.search(text, cursor)
        if found is None:
            continue
        starts.append((found.start(), label))
        cursor = found.end()
    if not starts or starts[0][0] > 0:
        starts.insert(0, (0, title or "Page text"))
    return [
        {
            "id": f"section:{index}",
            "title": label,
            "start": start,
            "end": starts[index + 1][0] if index + 1 < len(starts) else len(text),
        }
        for index, (start, label) in enumerate(starts)
        if start < len(text)
    ]


def _document(raw, allowed_origins, source):
    if type(raw) is not dict or type(raw.get("text")) is not str:
        raise ValueError("web_document_text_required")
    url = _check_url(raw.get("url"), allowed_origins)
    title = raw.get("title") if type(raw.get("title")) is str else ""
    links, excluded = [], 0
    for entry in raw.get("links", []):
        try:
            href = urllib.parse.urljoin(url, entry["url"])
            _check_url(href, allowed_origins)
        except (KeyError, TypeError, ValueError, DecisionStop):
            excluded += 1
            continue
        label = entry.get("label")
        links.append(
            {
                "id": f"link:{len(links)}",
                "label": label.strip() if type(label) is str and label.strip() else href,
                "url": href,
            }
        )
    document = {
        "url": url,
        "title": title,
        "text": raw["text"],
        "links": links,
        "sections": _sections(raw["text"], raw.get("headings", []), title),
    }
    document["fingerprint"] = _digest(document)
    document["source"] = {**source, "excluded_links": excluded}
    return document


class _TextPage(HTMLParser):
    """Server-rendered text extraction; browser rendering is a distinct source kind."""

    blocks = {
        "p",
        "div",
        "li",
        "section",
        "article",
        "main",
        "header",
        "footer",
        "nav",
        "pre",
        "br",
        "tr",
        "blockquote",
        "dt",
        "dd",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }
    ignored = {"script", "style", "noscript", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.title, self.links, self.headings = [], [], [], []
        self.skipped, self.in_title, self.in_head, self.heading, self.link = (
            [],
            False,
            False,
            None,
            None,
        )

    def handle_starttag(self, tag, attrs):
        if tag in self.ignored or self.skipped:
            self.skipped.append(tag)
            return
        if tag == "head":
            self.in_head = True
        if tag == "title":
            self.in_title = True
        if tag in self.blocks:
            self.text.append("\n")
        if re.fullmatch(r"h[1-6]", tag):
            self.heading = []
        if tag == "a" and "href" in dict(attrs):
            self.link = {"url": dict(attrs)["href"], "parts": []}

    def handle_endtag(self, tag):
        if self.skipped:
            if tag in self.skipped:
                self.skipped = self.skipped[: self.skipped.index(tag)]
            return
        if tag == "title":
            self.in_title = False
        if tag == "head":
            self.in_head = False
        if re.fullmatch(r"h[1-6]", tag) and self.heading is not None:
            self.headings.append("".join(self.heading).strip())
            self.heading = None
        if tag == "a" and self.link is not None:
            self.links.append(
                {"url": self.link["url"], "label": "".join(self.link["parts"]).strip()}
            )
            self.link = None
        if tag in self.blocks:
            self.text.append("\n")

    def handle_data(self, data):
        if self.skipped:
            return
        if self.in_title:
            self.title.append(data)
            return
        if self.in_head:
            return
        self.text.append(data)
        if self.heading is not None:
            self.heading.append(data)
        if self.link is not None:
            self.link["parts"].append(data)

    def document(self, url):
        text = "\n".join(line.strip() for line in "".join(self.text).splitlines() if line.strip())
        return {
            "url": url,
            "title": "".join(self.title).strip(),
            "text": text,
            "links": self.links,
            "headings": self.headings,
        }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _Provider:
    def _remember(self, document):
        self._latest = copy.deepcopy(document)
        return document

    def _link(self, link_id, snapshot):
        latest = getattr(self, "_latest", None)
        if latest is None or snapshot.get("fingerprint") != latest["fingerprint"]:
            raise DecisionStop("stale", "web_source_changed")
        matches = [entry for entry in latest["links"] if entry["id"] == link_id]
        if len(matches) != 1:
            raise DecisionStop("blocked", "web_link_not_observed")
        return matches[0]

    def follow(self, link_id, snapshot):
        link = self._link(link_id, snapshot)
        current = self.capture()
        if current["fingerprint"] != snapshot["fingerprint"]:
            raise DecisionStop("stale", "web_source_changed")
        _check_url(link["url"], self.allowed_origins)
        return self._navigate(link["url"])


class HttpProvider(_Provider):
    """GET-only HTML/text acquisition with bounded reads and per-hop origin checks."""

    def __init__(
        self, url, *, allowed_origins=None, timeout=10, max_bytes=2_000_000, max_redirects=4
    ):
        self.allowed_origins = _scope(allowed_origins, url)
        self.url = _check_url(url, self.allowed_origins)
        if type(timeout) not in (int, float):
            raise ValueError("positive_web_timeout_required")
        try:
            timeout = float(timeout)
        except (OverflowError, ValueError):
            raise ValueError("positive_web_timeout_required") from None
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("positive_web_timeout_required")
        if (
            type(max_bytes) is not int
            or max_bytes < 1
            or type(max_redirects) is not int
            or max_redirects < 0
        ):
            raise ValueError("invalid_web_acquisition_budget")
        self.timeout, self.max_bytes, self.max_redirects = timeout, max_bytes, max_redirects
        self._opener = urllib.request.build_opener(_NoRedirect())

    def capture(self):
        target, hops = self.url, []
        deadline = time.monotonic() + self.timeout
        for attempt in range(self.max_redirects + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DecisionStop("budget_exceeded", "web_acquisition_timeout")
            _check_url(target, self.allowed_origins)
            hops.append(target)
            request = urllib.request.Request(
                target,
                headers={
                    "Accept": "text/html, text/plain",
                    "User-Agent": "Jev-Harness/0.1 web discovery",
                },
                method="GET",
            )
            try:
                response = self._opener.open(request, timeout=remaining)
            except urllib.error.HTTPError as error:
                if error.code in REDIRECT_CODES and error.headers.get("Location"):
                    location = urllib.parse.urljoin(target, error.headers["Location"])
                    error.close()
                    _check_url(location, self.allowed_origins)
                    if attempt == self.max_redirects:
                        raise DecisionStop("blocked", "web_redirect_limit") from None
                    target = location
                    continue
                code = error.code
                error.close()
                raise DecisionStop("failed", f"web_http_{code}") from None
            except OSError:
                raise DecisionStop("failed", "web_http_unavailable") from None
            with response:
                final_url = _check_url(response.geturl(), self.allowed_origins)
                chunks, size = [], 0
                while True:
                    if time.monotonic() >= deadline:
                        raise DecisionStop("budget_exceeded", "web_acquisition_timeout")
                    chunk = response.read1(min(65536, self.max_bytes + 1 - size))
                    if time.monotonic() >= deadline:
                        raise DecisionStop("budget_exceeded", "web_acquisition_timeout")
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise DecisionStop("blocked", "web_response_too_large")
                payload = b"".join(chunks)
                content_type = response.headers.get_content_type()
                encoding = response.headers.get_content_charset() or "utf-8"
                try:
                    text = payload.decode(encoding)
                except (UnicodeError, LookupError):
                    raise DecisionStop("failed", "web_text_decode_failed") from None
            if content_type == "text/html":
                parser = _TextPage()
                parser.feed(text)
                raw = parser.document(final_url)
            elif content_type == "text/plain":
                raw = {"url": final_url, "title": "", "text": text, "links": [], "headings": []}
            else:
                raise DecisionStop("blocked", "web_text_content_required")
            document = _document(
                raw,
                self.allowed_origins,
                {
                    "kind": "http",
                    "content_type": content_type,
                    "bytes": len(payload),
                    "redirects": hops,
                },
            )
            self.url = final_url
            return self._remember(document)
        raise DecisionStop("blocked", "web_redirect_limit")  # pragma: no cover

    def _navigate(self, url):
        self.url = url
        return self.capture()

    def close(self):
        pass


_CAPTURE_JS = r"""(() => {
  const text = document.body ? document.body.innerText : '';
  if (text.length > __TEXT_LIMIT__) return {too_large: true};
  return {
    url: location.href, title: document.title, text,
    links: Array.from(document.querySelectorAll('a[href]')).map(a => ({url: a.href, label: a.innerText || a.textContent || ''})),
    headings: Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6')).map(h => h.innerText.trim())
  };
})()"""


class CamofoxProvider(_Provider):
    """Fresh DOM text from one Camofox tab; no model selectors or executable text.

    Keep the separately configured service headless with humanize:true. Targets
    and final origins are checked; service-side redirects/subresources are not
    intercepted. A borrowed tab is never closed by this provider.
    """

    def __init__(
        self,
        *,
        url=None,
        session="general",
        tab=None,
        base="http://127.0.0.1:9378",
        allowed_origins=None,
        surface=None,
        max_text_chars=2_000_000,
    ):
        if type(session) is not str or re.fullmatch(r"[A-Za-z0-9._-]+", session) is None:
            raise ValueError("invalid_named_browser_session")
        self.allowed_origins = _scope(allowed_origins, url)
        if url is not None:
            _check_url(url, self.allowed_origins)
        if type(max_text_chars) is not int or max_text_chars < 1:
            raise ValueError("positive_web_text_limit_required")
        if surface is None:
            from jev_context.act.browser import CamofoxPage

            surface = CamofoxPage(session, tab=tab, url=url, base=base)
        self.surface = surface
        self._script = _CAPTURE_JS.replace("__TEXT_LIMIT__", str(max_text_chars))
        self.max_text_chars = max_text_chars

    def capture(self):
        raw = self.surface.evaluate(self._script)
        if type(raw) is dict and raw.get("too_large"):
            raise DecisionStop("blocked", "web_response_too_large")
        if (
            type(raw) is dict
            and type(raw.get("text")) is str
            and len(raw["text"]) > self.max_text_chars
        ):
            raise DecisionStop("blocked", "web_response_too_large")
        return self._remember(
            _document(
                raw, self.allowed_origins, {"kind": "camofox", "extraction": "rendered_body_text"}
            )
        )

    def _navigate(self, url):
        if self.surface.navigate(url) is False:
            raise DecisionStop("execution_uncertain", "web_navigation_not_settled")
        return self.capture()

    def close(self):
        if getattr(self.surface, "owned", False):
            self.surface.close()


class WebTools:
    """Install dynamic link/section tools; observe returns stable evidence references.

    Construction acquires the first source. Later acquisitions occur only when
    following an observed link. ``observe`` itself performs no I/O or new put.
    Whole documents stay in the supplied store; section reads admit bounded text.
    """

    def __init__(self, provider, store, *, name="web"):
        if type(name) is not str or not name:
            raise ValueError("toolkit_name_required")
        self.name, self.provider, self.store = name, provider, store
        self._accept(provider.capture())

    def _accept(self, captured):
        self.page = copy.deepcopy(captured)
        self.ref = self.store.put(
            self.page["text"],
            source=self.page["url"],
            metadata={
                "title": self.page["title"],
                "fingerprint": self.page["fingerprint"],
                **self.page.get("source", {}),
            },
        )
        descriptor = self.store.describe(self.ref)
        self._observation = {
            "url": self.page["url"],
            "title": self.page["title"],
            "source_ref": self.ref,
            "characters": descriptor["characters"],
            "sha256": descriptor["sha256"],
            "summary": descriptor["summary"],
            "link_count": len(self.page["links"]),
            "section_count": len(self.page["sections"]),
            "source": copy.deepcopy(self.page.get("source", {})),
        }

    def observe(self):
        return copy.deepcopy(self._observation)

    def _links(self, ctx, state):
        return [
            Option(entry["id"], entry["label"][:160] + " | " + entry["url"], entry["id"])
            for entry in self.page["links"]
        ]

    def _sections(self, ctx, state):
        read_limit = min(READ_LIMIT, getattr(self.store, "read_limit", READ_LIMIT))
        return [
            Option(
                section["id"],
                f"{section['title'][:160]} | {self.page['url']} | characters {section['start']}:{section['end']}",
                {
                    "ref": self.ref,
                    "offset": section["start"],
                    "limit": min(read_limit, section["end"] - section["start"]),
                },
            )
            for section in self.page["sections"]
            if section["end"] > section["start"]
        ]

    def _open(self, link):
        self._accept(self.provider.follow(link, self.page))
        return self.observe()

    def _read(self, part):
        return self.store.read(**part)

    def install(self, task):
        task.tool(
            "Follow a currently observed link to gather a new source. The link label and URL describe its purpose.",
            name=self.name + ".open_link",
            parameters={
                "link": Parameter(
                    "An allowed observed link to inspect next. Destination contents may be unknown: choose a promising label and URL to gather information, without requiring that the destination already proves the goal.",
                    self._links,
                    selection="explore",
                )
            },
            result_context=lambda result: result,
        )(self._open)
        task.tool(
            "Read a bounded original-text slice from a current source section, with offsets and a provenance reference.",
            name=self.name + ".read_section",
            parameters={
                "part": Parameter(
                    "Observed section to inspect for information relevant to the goal",
                    self._sections,
                    selection="explore",
                )
            },
            result_context=lambda result: result,
        )(self._read)
        return task

    def close(self):
        close = getattr(self.provider, "close", None)
        if close is not None:
            close()
