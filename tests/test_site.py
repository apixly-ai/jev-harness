"""Keep bilingual public documentation navigable and correctly identified."""

import importlib.util
import json
from html.parser import HTMLParser
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "build_site", Path(__file__).resolve().parents[1] / "scripts/build_site.py"
)
site = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(site)


class Metadata(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.links = []
        self.schemas = []
        self.schema = False
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("a", "link"):
            self.links.append(attrs)
        if tag == "script" and attrs.get("type") == "application/ld+json":
            self.schema = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.schema = False

    def handle_data(self, data):
        if self.schema:
            self.schemas.append(json.loads(data))


def test_chinese_doc_links_stay_in_chinese_and_switch_to_matching_english_page():
    page = Metadata(
        site.shell("上下文管理", "上下文说明", "<h1>上下文</h1>", "zh/context.html", "zh-CN")
    )
    links = {item.get("class"): item.get("href") for item in page.links if item.get("class")}
    assert links["brand"] == "index.html"
    hrefs = {item.get("href") for item in page.links if "rel" not in item}
    assert "agent-contract.html" in hrefs
    assert "../context.html" in hrefs
    alternates = {
        item.get("hreflang"): item.get("href")
        for item in page.links
        if item.get("rel") == "alternate"
    }
    assert alternates == {
        "en": site.BASE + "context.html",
        "zh-CN": site.BASE + "zh/context.html",
        "x-default": site.BASE + "context.html",
    }


def test_document_entity_is_shared_but_webpage_identity_is_localized():
    pages = [
        Metadata(site.shell("Context", "Description", "<h1>Context</h1>", "context.html")),
        Metadata(site.shell("上下文", "说明", "<h1>上下文</h1>", "zh/context.html", "zh-CN")),
    ]
    graphs = [page.schemas[0]["@graph"] for page in pages]
    software = [
        next(item for item in graph if item["@type"] == "SoftwareSourceCode") for graph in graphs
    ]
    web = [next(item for item in graph if item["@type"] == "WebPage") for graph in graphs]
    assert software[0]["@id"] == software[1]["@id"]
    assert software[0]["identifier"] == "apixly-jev-harness"
    assert software[0]["codeRepository"] == site.REPO
    assert [item["url"] for item in web] == [
        site.BASE + "context.html",
        site.BASE + "zh/context.html",
    ]
    assert [item["inLanguage"] for item in web] == ["en", "zh-CN"]


def test_chinese_doc_resolves_reports_and_sibling_docs_without_wrong_repo_paths():
    content = '<a href="context.md#completion">context</a><a href="../reports/acceptance.json">report</a><img src="../web/media/browser-poster.zh-CN.webp">'
    rewritten = site.rewrite_links(content, zh=True, source="docs/use-cases.zh-CN.md")
    assert 'href="context.html#completion"' in rewritten
    assert 'href="../acceptance.json"' in rewritten
    assert 'src="../media/browser-poster.zh-CN.webp"' in rewritten


def test_body_language_links_switch_both_ways_without_changing_ordinary_doc_links():
    en = site.rewrite_links(
        '<a href="faq.zh-CN.md">简体中文</a><a href="context.md">Context</a>',
        source="docs/faq.md",
    )
    zh = site.rewrite_links(
        '<a href="faq.md">English</a><a href="context.md">上下文</a>',
        zh=True,
        source="docs/faq.zh-CN.md",
    )
    assert 'href="zh/faq.html">简体中文' in en
    assert 'href="../faq.html">English' in zh
    assert 'href="context.html"' in en and 'href="context.html"' in zh
