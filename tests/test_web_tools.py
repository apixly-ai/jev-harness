"""Behavior contracts for source-driven browser/HTTP discovery (no live model calls)."""

import copy
import hashlib
import importlib
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from apixly_jev_harness import Task
from apixly_jev_harness.engine import DecisionStop


@pytest.fixture
def web_module():
    return importlib.import_module("apixly_jev_harness.web_tools")


class MemoryStore:
    """Test double for the shared EvidenceStore contract, without storage side effects."""

    def __init__(self):
        self.rows = {}

    def put(self, text, source, metadata=None):
        ref = f"evidence:{len(self.rows) + 1}"
        self.rows[ref] = (text, source, metadata or {})
        return ref

    def describe(self, ref):
        text, source, metadata = self.rows[ref]
        return {
            "ref": ref,
            "source": source,
            "characters": len(text),
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "summary": text[:100],
            "metadata": metadata,
        }

    def read(self, ref, offset=0, limit=1200):
        text, source, _ = self.rows[ref]
        end = min(len(text), offset + limit)
        return {
            "ref": ref,
            "source": source,
            "offset": offset,
            "end": end,
            "total": len(text),
            "text": text[offset:end],
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
        }

    def references(self):
        return [self.describe(ref) for ref in self.rows]


def page(url="https://example.test/start", title="Start", text="Start\nDetails", links=()):
    return {
        "url": url,
        "title": title,
        "text": text,
        "links": list(links),
        "sections": [{"id": "section:0", "title": title, "start": 0, "end": len(text)}],
        "source": {"kind": "test"},
        "fingerprint": hashlib.sha256((url + text + json.dumps(links)).encode()).hexdigest(),
    }


class FakeProvider:
    def __init__(self, pages):
        self.pages, self.index, self.captures = pages, 0, 0
        self.follows = []

    def capture(self):
        self.captures += 1
        return copy.deepcopy(self.pages[self.index])

    def follow(self, link_id, snapshot):
        assert snapshot == self.pages[self.index]
        assert any(item["id"] == link_id for item in snapshot["links"])
        self.follows.append(link_id)
        self.index += 1
        return self.capture()


def registered(tools):
    task = Task(observe=lambda ctx: tools.observe(), verify=lambda ctx, state: False)
    tools.install(task)
    return task


def execute(task, tools, name, selected=None):
    state = tools.observe()
    action = next(item for item in task.candidates(None, state) if item.id == name)

    def choose(records, goal, extra):
        match = next(item["id"] for item in records if selected in (None, item["id"]))
        return {"ok": True, "complete": True, "selected_ids": [match]}

    return task.execute(None, task.bind(None, state, action, choose))


def test_same_name_links_keep_url_semantics_and_registered_tools(web_module):
    links = (
        {"id": "link:0", "label": "Details", "url": "https://example.test/alpha"},
        {"id": "link:1", "label": "Details", "url": "https://example.test/beta"},
    )
    tools = web_module.WebTools(FakeProvider([page(links=links)]), MemoryStore())
    task = registered(tools)
    offered = task.candidates(None, tools.observe())
    assert {action.id for action in offered} == {"web.open_link", "web.read_section"}
    open_action = next(item for item in offered if item.id == "web.open_link")
    assert "https://example.test/alpha" in open_action.description
    assert "https://example.test/beta" in open_action.description
    assert "earliest unmet instruction" not in open_action.description
    assert "submit" not in open_action.description.lower()


def test_observe_stays_stable_without_reacquiring_or_creating_references(web_module):
    provider, store = FakeProvider([page(text="private-marker " * 1000)]), MemoryStore()
    tools = web_module.WebTools(provider, store)
    first, second = tools.observe(), tools.observe()
    assert first == second
    assert provider.captures == 1 and len(store.references()) == 1
    assert len(json.dumps(first)) < 3000
    assert "private-marker " * 1000 not in json.dumps(first)
    assert first["source_ref"] in store.rows


def test_follow_discovers_new_link_candidates_and_keeps_old_source(web_module):
    first = page(links=({"id": "link:0", "label": "Guide", "url": "https://example.test/guide"},))
    second = page(
        url="https://example.test/guide",
        title="Guide",
        text="Guide\nRelease details",
        links=({"id": "link:0", "label": "Release", "url": "https://example.test/release"},),
    )
    store = MemoryStore()
    tools = web_module.WebTools(FakeProvider([first, second]), store)
    task = registered(tools)
    before_ref = tools.observe()["source_ref"]
    result = execute(task, tools, "web.open_link")
    offered = task.candidates(None, tools.observe())
    assert result["url"] == "https://example.test/guide"
    assert tools.observe()["source_ref"] != before_ref
    assert len(store.references()) == 2
    assert (
        "https://example.test/release"
        in next(a for a in offered if a.id == "web.open_link").description
    )
    assert store.read(before_ref)["text"] == first["text"]


def test_read_section_is_a_bounded_source_packet_not_whole_page(web_module):
    content = "Guide\n" + "x" * 4000 + "\nEnd-of-page evidence"
    tools = web_module.WebTools(FakeProvider([page(title="Guide", text=content)]), MemoryStore())
    result = execute(registered(tools), tools, "web.read_section")
    assert len(result["text"]) <= 1200
    assert result["total"] == len(content)
    assert result["source"] == "https://example.test/start"
    assert result["sha256"] == hashlib.sha256(content.encode()).hexdigest()
    assert result["offset"] == 0


def test_large_candidate_domain_is_explicit_not_silently_truncated(web_module):
    links = tuple(
        {"id": f"link:{i}", "label": "Details", "url": f"https://example.test/{i}"}
        for i in range(254)
    )
    tools = web_module.WebTools(FakeProvider([page(links=links)]), MemoryStore())
    with pytest.raises(DecisionStop) as error:
        registered(tools).candidates(None, tools.observe())
    assert error.value.status == "needs_review"
    assert error.value.reason == "parameter_domain_too_large"


@contextmanager
def serve(routes):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            status, headers, payload = routes[self.path]
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(payload.encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def html_route(content):
    return 200, {"Content-Type": "text/html; charset=utf-8"}, content


def test_http_provider_extracts_full_text_links_and_sections(web_module):
    content = (
        "<title>Guide</title><h1>Overview</h1><p>"
        + "x" * 4000
        + '</p><h2>Compatibility</h2><p>末尾证据 😀</p><a href="/one">Details</a><a href="/two">Details</a><script>private script</script>'
    )
    with serve({"/start": html_route(content)}) as (base, requests):
        provider = web_module.HttpProvider(base + "/start", allowed_origins=[base])
        captured = provider.capture()
        assert captured["title"] == "Guide"
        assert "末尾证据 😀" in captured["text"]
        assert "private script" not in captured["text"]
        assert {x["url"] for x in captured["links"]} == {base + "/one", base + "/two"}
        section = next(x for x in captured["sections"] if x["title"] == "Compatibility")
        assert "末尾证据 😀" in captured["text"][section["start"] : section["end"]]
        assert requests == ["/start"]


def test_http_redirect_to_allowed_origin_is_captured(web_module):
    routes = {
        "/start": (302, {"Location": "/guide"}, ""),
        "/guide": html_route("<h1>Guide</h1><p>Ready</p>"),
    }
    with serve(routes) as (base, requests):
        captured = web_module.HttpProvider(base + "/start", allowed_origins=[base]).capture()
        assert captured["url"] == base + "/guide"
        assert captured["source"]["redirects"] == [base + "/start", base + "/guide"]
        assert requests == ["/start", "/guide"]


def test_http_redirect_outside_origin_is_blocked_before_request(web_module):
    with serve({"/outside": html_route("must not fetch")}) as (other, other_requests):
        with serve({"/start": (302, {"Location": other + "/outside"}, "")}) as (base, requests):
            provider = web_module.HttpProvider(base + "/start", allowed_origins=[base])
            with pytest.raises(DecisionStop, match="origin_not_allowed"):
                provider.capture()
            assert requests == ["/start"]
            assert other_requests == []


def test_http_link_freshness_blocks_changed_source_before_destination(web_module):
    routes = {
        "/start": html_route('<h1>Start</h1><a href="/one">Details</a>'),
        "/one": html_route("<h1>One</h1>"),
    }
    with serve(routes) as (base, requests):
        provider = web_module.HttpProvider(base + "/start", allowed_origins=[base])
        snapshot = provider.capture()
        routes["/start"] = html_route('<h1>Changed</h1><a href="/one">Details</a>')
        with pytest.raises(DecisionStop) as error:
            provider.follow(snapshot["links"][0]["id"], snapshot)
        assert error.value.status == "stale"
        assert requests == ["/start", "/start"]


@pytest.mark.parametrize(
    "suffix",
    [
        "javascript:alert(1)",
        "https://example.invalid/",
        "http://owner:secret@127.0.0.1/",
        "mailto:owner@example.test",
    ],
)
def test_unsupported_or_outside_links_are_not_candidates(web_module, suffix):
    with serve(
        {"/start": html_route(f'<h1>Start</h1><a href="{suffix}">Skip</a><a href="/ok">Keep</a>')}
    ) as (base, requests):
        captured = web_module.HttpProvider(base + "/start", allowed_origins=[base]).capture()
        assert len(captured["links"]) == 1
        assert captured["links"][0]["url"] == base + "/ok"
        assert captured["source"]["excluded_links"] == 1
        assert requests == ["/start"]


def test_http_size_budget_is_explicit(web_module):
    with serve({"/start": html_route("x" * 5000)}) as (base, requests):
        with pytest.raises(DecisionStop, match="response_too_large"):
            web_module.HttpProvider(
                base + "/start", allowed_origins=[base], max_bytes=100
            ).capture()
        assert requests == ["/start"]


def test_http_duplicate_section_titles_have_different_source_offsets(web_module):
    with serve(
        {
            "/start": html_route(
                "<h1>Details</h1><p>First evidence</p><h1>Details</h1><p>Second evidence</p>"
            )
        }
    ) as (base, _):
        captured = web_module.HttpProvider(base + "/start", allowed_origins=[base]).capture()
        sections = [x for x in captured["sections"] if x["title"] == "Details"]
        assert len(sections) == 2
        assert sections[0]["id"] != sections[1]["id"]
        assert sections[0]["start"] < sections[1]["start"]
        assert "First evidence" in captured["text"][sections[0]["start"] : sections[0]["end"]]
        assert "Second evidence" in captured["text"][sections[1]["start"] : sections[1]["end"]]


class FakeBrowser:
    def __init__(self, current, next_page=None, owned=True):
        self.current, self.next_page, self.owned = current, next_page, owned
        self.scripts, self.navigations, self.closed = [], [], 0

    def evaluate(self, expression):
        self.scripts.append(expression)
        assert "document.body.innerText" in expression
        return copy.deepcopy(self.current)

    def navigate(self, url):
        self.navigations.append(url)
        self.current = copy.deepcopy(self.next_page)
        return True

    def close(self):
        self.closed += 1


def browser_page(url="https://example.test/start", text="Guide\nBody", links=None):
    return {"url": url, "title": "Guide", "text": text, "links": links or [], "headings": ["Guide"]}


def test_browser_capture_uses_fixed_script_and_keeps_link_url(web_module):
    fake = FakeBrowser(
        browser_page(
            links=[
                {"label": "Details", "url": "https://example.test/one"},
                {"label": "Details", "url": "https://example.test/two"},
            ]
        )
    )
    provider = web_module.CamofoxProvider(surface=fake, allowed_origins=["https://example.test"])
    captured = provider.capture()
    assert len(captured["links"]) == 2
    assert captured["links"][0]["url"] != captured["links"][1]["url"]
    assert len(fake.scripts) == 1
    assert captured["source"]["kind"] == "camofox"


def test_browser_follow_only_observed_fresh_link(web_module):
    fake = FakeBrowser(
        browser_page(links=[{"label": "Details", "url": "https://example.test/one"}]),
        browser_page("https://example.test/one", "Next evidence"),
    )
    provider = web_module.CamofoxProvider(surface=fake, allowed_origins=["https://example.test"])
    snapshot = provider.capture()
    with pytest.raises(DecisionStop, match="link_not_observed"):
        provider.follow("https://example.test/arbitrary", snapshot)
    result = provider.follow(snapshot["links"][0]["id"], snapshot)
    assert fake.navigations == ["https://example.test/one"]
    assert result["url"] == "https://example.test/one"


def test_browser_changed_page_blocks_navigation(web_module):
    fake = FakeBrowser(
        browser_page(links=[{"label": "Details", "url": "https://example.test/one"}])
    )
    provider = web_module.CamofoxProvider(surface=fake, allowed_origins=["https://example.test"])
    snapshot = provider.capture()
    fake.current["text"] = "Changed document"
    with pytest.raises(DecisionStop) as error:
        provider.follow(snapshot["links"][0]["id"], snapshot)
    assert error.value.status == "stale"
    assert fake.navigations == []


@pytest.mark.parametrize("owned", [True, False])
def test_browser_cleanup_only_closes_owned_tab(web_module, owned):
    fake = FakeBrowser(browser_page(), owned=owned)
    provider = web_module.CamofoxProvider(surface=fake, allowed_origins=["https://example.test"])
    provider.close()
    assert fake.closed == int(owned)


def test_browser_final_origin_is_checked_after_transport_redirect(web_module):
    fake = FakeBrowser(
        browser_page(links=[{"label": "Details", "url": "https://example.test/one"}]),
        browser_page("https://outside.test/redirected", "Outside"),
    )
    provider = web_module.CamofoxProvider(surface=fake, allowed_origins=["https://example.test"])
    snapshot = provider.capture()
    with pytest.raises(DecisionStop, match="origin_not_allowed"):
        provider.follow(snapshot["links"][0]["id"], snapshot)
    assert fake.navigations == ["https://example.test/one"]


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), float("-inf"), True])
def test_http_timeout_must_be_finite_before_acquisition(web_module, timeout):
    with pytest.raises(ValueError, match="web_timeout"):
        web_module.HttpProvider("https://example.test/start", timeout=timeout)


def test_http_plain_anchor_without_href_is_not_a_link(web_module):
    with serve({"/start": html_route('<h1>Start</h1><a>Not a link</a><a href="/ok">Keep</a>')}) as (
        base,
        _,
    ):
        captured = web_module.HttpProvider(base + "/start", allowed_origins=[base]).capture()
        assert [(link["label"], link["url"]) for link in captured["links"]] == [
            ("Keep", base + "/ok")
        ]


def test_http_acquisition_deadline_is_checked_between_stream_chunks(web_module, monkeypatch):
    from email.message import Message
    from types import SimpleNamespace

    clock = {"value": 0.0}
    monkeypatch.setattr(
        web_module, "time", SimpleNamespace(monotonic=lambda: clock["value"]), raising=False
    )

    class Response:
        headers = Message()
        headers["Content-Type"] = "text/plain; charset=utf-8"

        def geturl(self):
            return "https://example.test/start"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, amount):
            return b"unbounded read ignores deadline"

        def read1(self, amount):
            clock["value"] += 0.2
            return b"x"

    class Opener:
        def open(self, request, timeout):
            return Response()

    provider = web_module.HttpProvider("https://example.test/start", timeout=0.5)
    provider._opener = Opener()
    with pytest.raises(DecisionStop, match="acquisition_timeout"):
        provider.capture()


def test_shared_evidence_store_read_limit_and_tail_reference(web_module):
    from apixly_jev_harness.evidence import EvidenceStore

    content = "Guide\n" + "source text " * 100 + "末尾 😀"
    store = EvidenceStore(read_limit=64)
    tools = web_module.WebTools(FakeProvider([page(title="Guide", text=content)]), store)
    result = execute(registered(tools), tools, "web.read_section")
    assert len(result["text"]) <= 64
    tail = store.read(tools.observe()["source_ref"], offset=len(content) - 4, limit=4)
    assert tail["text"] == "末尾 😀"
    assert tail["total"] == len(content)


def test_navigation_parameter_describes_investigation_not_a_known_answer(web_module):
    class Provider:
        def capture(self):
            return {
                "url": "https://allowed.example/start",
                "title": "Entry",
                "text": "Explore sources",
                "links": [{"id": "a", "label": "Details", "url": "https://allowed.example/next"}],
                "sections": [],
                "source": {},
                "fingerprint": "one",
            }

    from apixly_jev_harness import EvidenceStore

    pack = web_module.WebTools(Provider(), EvidenceStore())
    task = Task(observe=lambda c: {}, verify=lambda c, s: False)
    pack.install(task)
    description = task.describe()["web.open_link"]["parameters"]["link"]["description"]
    assert "unknown" in description and "inspect" in description


def test_web_link_binding_declares_discovery_mode(web_module):
    class Provider:
        def capture(self):
            return {
                "url": "https://allowed.example/start",
                "title": "Entry",
                "text": "Explore sources",
                "links": [{"id": "a", "label": "Details", "url": "https://allowed.example/next"}],
                "sections": [],
                "source": {},
                "fingerprint": "one",
            }

    from apixly_jev_harness import EvidenceStore

    pack = web_module.WebTools(Provider(), EvidenceStore())
    task = Task(observe=lambda c: {}, verify=lambda c, s: False)
    pack.install(task)
    assert task._tools["web.open_link"]["parameters"]["link"].selection == "explore"
