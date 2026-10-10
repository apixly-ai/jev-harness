"""Scan all publishable files, including not-yet-tracked files."""

import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
patterns = [
    re.compile(r"/Users/[A-Za-z][^/\s]*"),
    re.compile(r"/home/[A-Za-z][^/\s]*"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
]
problems = []
for path in root.rglob("*"):
    rel = path.relative_to(root)
    if not path.is_file() or any(
        p.startswith(".") or p in ("local-results", "dist", "site", "build") for p in rel.parts
    ):
        continue
    try:
        text = path.read_text()
    except (UnicodeDecodeError, OSError):
        continue
    if any(p.search(text) for p in patterns):
        problems.append(str(rel))
if problems:
    raise SystemExit("Private artifacts found: " + ", ".join(problems))
print("Public-content check passed")
