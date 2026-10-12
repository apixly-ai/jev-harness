"""Notify IndexNow once after independently checking published pages and key proof."""

import argparse
import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://apixly-ai.github.io/jev-harness/"
ENDPOINT = "https://api.indexnow.org/indexnow"


def fetch(url):
    request = urllib.request.Request(
        url, headers={"User-Agent": "JevHarness-publication-check/1.0"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.url != url or response.status != 200:
            raise RuntimeError("unexpected_public_response")
        return response.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--submit", action="store_true", help="Send one URL notification after verification"
    )
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Use a new output path; preserve any previous or uncertain receipt.")
    key = (ROOT / "web/indexnow-key.txt").read_text(encoding="utf-8").strip()
    proof = BASE + key + ".txt"
    if fetch(proof).decode().strip() != key:
        raise RuntimeError("public_key_proof_mismatch")
    sitemap = ElementTree.fromstring(fetch(BASE + "sitemap.xml"))
    urls = [
        node.text
        for node in sitemap.findall(
            "{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
        )
    ]
    if not urls or len(urls) > 30 or len(set(urls)) != len(urls):
        raise RuntimeError("invalid_url_scope")
    if any(
        not url.startswith(BASE) or urlsplit(url).query or urlsplit(url).fragment for url in urls
    ):
        raise RuntimeError("url_outside_project_scope")
    with ThreadPoolExecutor(max_workers=4) as pool:
        pages = list(pool.map(fetch, urls))
    for url, body in zip(urls, pages, strict=True):
        if f'<link rel="canonical" href="{url}">'.encode() not in body:
            raise RuntimeError("public_canonical_mismatch")
    receipt = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "url_count": len(urls),
        "urls": urls,
        "proof_verified": True,
        "published_pages_verified": True,
        "notification_sent": False,
        "http_status": None,
        "disposition": "verified_not_submitted",
        "indexing": "unknown",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    if args.submit:
        receipt.update(notification_sent=True, disposition="attempt_started_outcome_unknown")
        args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
        request = urllib.request.Request(
            ENDPOINT,
            data=json.dumps(
                {"host": urlsplit(BASE).netloc, "key": key, "keyLocation": proof, "urlList": urls}
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                receipt["http_status"] = response.status
            receipt["disposition"] = {
                200: "received",
                202: "received_key_validation_pending",
            }.get(receipt["http_status"], "unexpected_status")
        except urllib.error.HTTPError as error:
            receipt.update(http_status=error.code, disposition="rejected")
        except (urllib.error.URLError, TimeoutError):
            receipt["disposition"] = "uncertain_no_automatic_retry"
        args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: value for key, value in receipt.items() if key != "urls"}, indent=2))
    return (
        0
        if receipt["disposition"]
        in ("verified_not_submitted", "received", "received_key_validation_pending")
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
