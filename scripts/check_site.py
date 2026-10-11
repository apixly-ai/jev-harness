"""Verify the built bilingual site's real links, page identity and sitemap pairs."""

import argparse
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://apixly-ai.github.io/jev-harness/"


class Page(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.language = None
        self.refs = []
        self.ids = set()
        self.canonical = []
        self.alternates = {}
        self.descriptions = []
        self.schemas = []
        self.schema = False
        self.h1_count = 0
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "html":
            self.language = attrs.get("lang")
        if tag == "h1":
            self.h1_count += 1
        if "id" in attrs:
            self.ids.add(attrs["id"])
        self.refs.extend(attrs[key] for key in ("href", "src", "poster") if key in attrs)
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical.append(attrs.get("href"))
        if tag == "link" and attrs.get("rel") == "alternate":
            self.alternates[attrs.get("hreflang")] = attrs.get("href")
        if tag == "meta" and attrs.get("name") == "description":
            self.descriptions.append(attrs.get("content"))
        if tag == "script" and attrs.get("type") == "application/ld+json":
            self.schema = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.schema = False

    def handle_data(self, data):
        if self.schema:
            self.schemas.append(json.loads(data))


def audit(root):
    root = root.resolve()
    pages = {path: Page(path.read_text()) for path in root.rglob("*.html")}
    problems = []
    checked = 0
    canonical_urls = set()
    for path, page in pages.items():
        rel = path.relative_to(root).as_posix()
        zh = rel.startswith("zh/")
        en = rel.removeprefix("zh/")
        en = "" if en == "index.html" else en
        expected = BASE + ("zh/" if zh else "") + en
        pairs = {"en": BASE + en, "zh-CN": BASE + "zh/" + en, "x-default": BASE + en}
        for valid, reason in (
            (page.language == ("zh-CN" if zh else "en"), "wrong HTML language"),
            (page.h1_count == 1, "requires one H1"),
            (page.canonical == [expected], "wrong canonical URL"),
            (page.alternates == pairs, "incorrect language counterparts"),
            (len(page.descriptions) == 1 and bool(page.descriptions[0]), "missing description"),
        ):
            if not valid:
                problems.append({"page": rel, "reason": reason})
        canonical_urls.add(expected)
        graphs = [node for schema in page.schemas for node in schema.get("@graph", [])]
        webpage = next((node for node in graphs if node.get("@type") == "WebPage"), {})
        software = next((node for node in graphs if node.get("@type") == "SoftwareSourceCode"), {})
        if webpage.get("url") != expected or webpage.get("inLanguage") != page.language:
            problems.append({"page": rel, "reason": "incorrect WebPage identity"})
        if software.get("identifier") != "apixly-jev-harness":
            problems.append({"page": rel, "reason": "incorrect project identity"})
        for reference in page.refs:
            parts = urlsplit(reference)
            if parts.netloc or parts.scheme:
                if not reference.startswith(BASE):
                    continue
                destination = root / unquote(parts.path.removeprefix("/jev-harness/"))
            else:
                destination = path.parent / unquote(parts.path) if parts.path else path
            destination = destination.resolve()
            if destination.is_dir():
                destination /= "index.html"
            if not destination.is_relative_to(root) or not destination.exists():
                problems.append(
                    {"page": rel, "reason": "missing local reference", "reference": reference}
                )
                continue
            if (
                parts.fragment
                and destination in pages
                and parts.fragment not in pages[destination].ids
            ):
                problems.append({"page": rel, "reason": "missing fragment", "reference": reference})
            checked += 1
    namespaces = {
        "s": "http://www.sitemaps.org/schemas/sitemap/0.9",
        "h": "http://www.w3.org/1999/xhtml",
    }
    sitemap = ElementTree.parse(root / "sitemap.xml")
    urls = sitemap.findall("s:url", namespaces)
    listed = [entry.find("s:loc", namespaces).text for entry in urls]
    if len(set(listed)) != len(listed) or set(listed) != canonical_urls:
        problems.append({"reason": "sitemap URL set differs from canonical pages"})
    for entry in urls:
        url = entry.find("s:loc", namespaces).text
        relative = url.removeprefix(BASE).removeprefix("zh/")
        pairs = {
            "en": BASE + relative,
            "zh-CN": BASE + "zh/" + relative,
            "x-default": BASE + relative,
        }
        actual = {
            node.get("hreflang"): node.get("href") for node in entry.findall("h:link", namespaces)
        }
        if actual != pairs:
            problems.append({"url": url, "reason": "incorrect sitemap language counterparts"})
    text_sitemap = (root / "sitemap.txt").read_text().splitlines()
    if text_sitemap != listed:
        problems.append({"reason": "text and XML sitemap URL sets differ"})
    return {
        "pages": len(pages),
        "local_references_checked": checked,
        "sitemap_urls": len(listed),
        "problems": problems,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    args = parser.parse_args()
    report = audit(args.site)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
