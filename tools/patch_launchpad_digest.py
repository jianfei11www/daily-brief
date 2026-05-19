#!/usr/bin/env python3
"""
Patch a daily-brief HTML post by inserting the launchpad digest HTML
under Section 2 -> "观察池线索".

Rules:
- No extra deps.
- Idempotent: if a previous digest exists, replace it.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


MARKER = "<h3>观察池线索</h3>"
START = "<div class=\"launchpad-digest\">"
END = "</div>"


def patch_html(html: str, digest_html: str) -> str:
    if MARKER not in html:
        raise RuntimeError("Missing marker: 观察池线索")

    # Remove previous digest if present.
    html = re.sub(
        r"\n?" + re.escape(START) + r".*?" + re.escape(END) + r"\n?",
        "\n",
        html,
        flags=re.S,
    )

    insert_at = html.find(MARKER)
    if insert_at < 0:
        raise RuntimeError("Marker not found")

    after = insert_at + len(MARKER)
    return html[:after] + "\n" + digest_html.strip() + "\n" + html[after:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--post", required=True, help="Path to posts/YYYYMMDD-brief.html")
    ap.add_argument("--digest-html", required=True, help="Path to generated digest html snippet")
    args = ap.parse_args()

    post_path = Path(args.post)
    digest_path = Path(args.digest_html)

    raw = post_path.read_text(encoding="utf-8")
    digest = digest_path.read_text(encoding="utf-8")
    patched = patch_html(raw, digest)
    if patched == raw:
        raise RuntimeError("No changes applied.")
    post_path.write_text(patched, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

