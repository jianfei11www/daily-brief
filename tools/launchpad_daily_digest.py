#!/usr/bin/env python3
"""
Generate a daily digest HTML snippet for "一级打新 / 空投 / 融资项目" section
based on FREE_SOURCES_WATCHLIST.yaml::launchpads_and_token_sales.

Design goals:
- No extra deps (stdlib + curl only).
- Never fabricate data: only report reachability/title and detected changes.
- If network/proxy blocks fetch, fail loudly or output "0 items" with reasons.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "tools" / ".state"
DEFAULT_WATCHLIST = ROOT.parent / "FREE_SOURCES_WATCHLIST.yaml"


@dataclass(frozen=True)
class Target:
    platform: str
    url: str


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _extract_title(html: str) -> str:
    if not html:
        return ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    if not m:
        return ""
    title = re.sub(r"\s+", " ", m.group(1)).strip()
    title = re.sub(r"&amp;", "&", title)
    title = re.sub(r"&lt;", "<", title)
    title = re.sub(r"&gt;", ">", title)
    return title[:200]


def _normalize_html_for_hash(html: str) -> str:
    html = re.sub(r"\s+", " ", html)
    html = re.sub(r"nonce=\"[^\"]+\"", 'nonce=""', html)
    html = re.sub(r"integrity=\"[^\"]+\"", 'integrity=""', html)
    html = re.sub(r"data-[a-z0-9_-]+=\"[^\"]*\"", "", html, flags=re.I)
    return html.strip()


def _curl_fetch(url: str, timeout_seconds: int = 20) -> tuple[int, str]:
    # Try with env proxies first (some sites require it), then fallback to no-proxy direct.
    # Do NOT loop too much; this runs daily once.
    attempts: list[dict[str, Any]] = [
        {"name": "env-proxy", "env": os.environ.copy(), "extra": []},
        {
            "name": "no-proxy",
            "env": {k: v for k, v in os.environ.copy().items() if k.lower() not in {"http_proxy", "https_proxy", "all_proxy"}},
            "extra": ["--noproxy", "*"],
        },
    ]
    last_err = ""
    for att in attempts:
        proc = subprocess.run(
            [
                "curl",
                "-sS",
                "--max-time",
                str(int(timeout_seconds)),
                "-L",
                *att["extra"],
                url,
            ],
            env=att["env"],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            return 0, proc.stdout
        last_err = (proc.stderr or proc.stdout or "").strip()[:200]
    return proc.returncode or 1, last_err


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse_launchpads_from_watchlist(text: str) -> list[Target]:
    # Minimal YAML parsing by regex to avoid deps:
    # - find launchpads_and_token_sales: ... platforms: ... list entries with name + official_primary urls
    # Assumes current file layout we maintain.
    block_m = re.search(r"launchpads_and_token_sales:\n(?P<body>(?:[ ]+.*\n)+)", text)
    if not block_m:
        return []
    body = block_m.group("body")
    platforms_m = re.search(r"platforms:\n(?P<plist>(?:[ ]{4,}.*\n)+)", body)
    if not platforms_m:
        return []
    plist = platforms_m.group("plist")

    targets: list[Target] = []
    cur_name = ""
    in_official = False
    for line in plist.splitlines():
        if re.match(r"^[ ]{4}- id:", line):
            # start of an entry; name may follow
            cur_name = ""
            in_official = False
            continue
        if re.match(r"^[ ]{6}name:", line):
            cur_name = line.split(":", 1)[1].strip().strip('"')
            continue
        if re.match(r"^[ ]{6}official_primary:", line):
            in_official = True
            continue
        if in_official:
            m = re.match(r'^[ ]{8}- "?(?P<url>https?://[^"\s]+)"?$', line)
            if m and cur_name:
                targets.append(Target(cur_name, m.group("url")))
            # stop official list if next key
            if re.match(r"^[ ]{6}[a-zA-Z_]+:", line):
                in_official = False
    # De-dup by (platform,url)
    seen = set()
    uniq: list[Target] = []
    for t in targets:
        k = (t.platform, t.url)
        if k in seen:
            continue
        seen.add(k)
        uniq.append(t)
    return uniq


def run_once(targets: list[Target]) -> dict[str, Any]:
    now_cst = time.strftime("%Y-%m-%d %H:%M:%S CST", time.localtime())
    today = time.strftime("%Y-%m-%d", time.localtime())

    state_path = STATE_DIR / "launchpads_state.json"
    prev = _load_json(state_path)
    prev_items = (prev.get("items") or {}) if isinstance(prev, dict) else {}

    items: dict[str, Any] = {}
    changes: list[dict[str, Any]] = []
    for t in targets:
        key = f"{t.platform}::{t.url}"
        exit_code, body = _curl_fetch(t.url)
        title = _extract_title(body if exit_code == 0 else "")
        normalized = _normalize_html_for_hash(body) if exit_code == 0 else ""
        body_hash = _sha256_text(normalized) if normalized else ""
        current = {
            "platform": t.platform,
            "url": t.url,
            "curl_exit": exit_code,
            "title": title,
            "sha256": body_hash,
            "len": len(body) if isinstance(body, str) else 0,
        }
        items[key] = current

        before = prev_items.get(key)
        if before:
            if before.get("curl_exit") != current["curl_exit"] or (
                current["sha256"] and before.get("sha256") and before.get("sha256") != current["sha256"]
            ):
                changes.append({"key": key, "before": before, "current": current})

    result = {"generated_at": now_cst, "date": today, "items": items, "changes": changes}
    _save_json(state_path, result)
    return result


def render_html_digest(results: dict[str, Any], *, max_lines: int = 10) -> str:
    date = str(results.get("date") or "")
    items: dict[str, Any] = results.get("items") or {}
    ok = [v for v in items.values() if v.get("curl_exit") == 0]
    bad = [v for v in items.values() if v.get("curl_exit") != 0]

    lines: list[str] = []
    lines.append('<div class="launchpad-digest">')
    lines.append(f"<p><strong>打新/融资平台入口监控（{date}）</strong>：覆盖 {len(items)} 个入口（可达 {len(ok)} / 异常 {len(bad)}）。</p>")
    if bad:
        lines.append("<p><strong>异常入口（需手动复核/更换镜像/稍后重试）：</strong></p>")
        lines.append("<ul>")
        for it in bad[:max_lines]:
            lines.append(
                "<li>"
                + f"{it.get('platform')}｜curl_exit={it.get('curl_exit')}｜"
                + f'<a href="{it.get("url")}">{it.get("url")}</a>'
                + "</li>"
            )
        lines.append("</ul>")
    if ok:
        lines.append("<p><strong>可达入口摘要（仅用于发现线索，不等同于项目上新确认）：</strong></p>")
        lines.append("<ul>")
        for it in ok[:max_lines]:
            title = (it.get("title") or "").strip() or "（无标题/被阻断）"
            lines.append(
                "<li>"
                + f"{it.get('platform')}｜{title}｜"
                + f'<a href="{it.get("url")}">{it.get("url")}</a>'
                + "</li>"
            )
        lines.append("</ul>")
    lines.append("</div>")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--watchlist", default=str(DEFAULT_WATCHLIST), help="Path to FREE_SOURCES_WATCHLIST.yaml")
    ap.add_argument("--out-json", default="", help="Write raw results json")
    ap.add_argument("--out-html", default="", help="Write html snippet")
    args = ap.parse_args()

    watchlist_path = Path(args.watchlist)
    watchlist_text = watchlist_path.read_text(encoding="utf-8")
    targets = _parse_launchpads_from_watchlist(watchlist_text)
    if not targets:
        raise SystemExit("No launchpad targets found in watchlist.")

    results = run_once(targets)
    html = render_html_digest(results)

    if args.out_json:
        Path(args.out_json).write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.out_html:
        Path(args.out_html).write_text(html, encoding="utf-8")

    print(html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
