#!/usr/bin/env python3
"""
Patch a generated daily-brief HTML post by filling the stablecoin table (USDT/USDC)
using the free DefiLlama Stablecoins endpoint.

Design goals:
- No extra deps (stdlib only).
- "Self-heal" typical proxy misconfig by ignoring env proxies and retrying via curl with proxies removed.
- If network/DNS is unavailable in the current runtime, fails loudly with a clear message.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from stablecoin_flows import fetch_stablecoin_rows, _fmt_change_usd, _fmt_total_usd  # noqa: E402


ROW_RE_TEMPLATE = r"(<td>{sym}</td>\\s*<td>)(?P<day>[^<]*)(</td>\\s*<td>)(?P<month>[^<]*)(</td>\\s*<td>)(?P<total>[^<]*)(</td>)"


def patch_html(html: str) -> str:
    rows = fetch_stablecoin_rows()

    for sym in ("USDT", "USDC"):
        row = rows[sym]
        day = _fmt_change_usd(row.day_change_usd)
        month = _fmt_change_usd(row.month_change_usd)
        total = _fmt_total_usd(row.current_usd)

        row_re = re.compile(ROW_RE_TEMPLATE.format(sym=re.escape(sym)))
        html, n = row_re.subn(rf"\\1{day}\\3{month}\\5{total}\\7", html, count=1)
        if n != 1:
            raise RuntimeError(f"Failed to patch {sym} row (expected 1 match, got {n})")

    # Update source meta line to reflect real source and confidence.
    html = re.sub(
        r'(<h3>稳定币资金流向（USDT / USDC）</h3>.*?<p class="source-meta"><strong>来源：</strong>)(.*?)(</p>)',
        r'\\1<a href="https://stablecoins.llama.fi/stablecoins">DeFiLlama Stablecoins</a>（current/prevDay/prevMonth 口径；月内为近 30 日替代口径）｜置信度：中\\3',
        html,
        flags=re.S,
        count=1,
    )
    return html


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--post", required=True, help="Path to posts/YYYYMMDD-brief.html")
    args = ap.parse_args()

    path = Path(args.post)
    raw = path.read_text(encoding="utf-8")
    patched = patch_html(raw)
    if patched == raw:
        raise RuntimeError("No changes applied; stablecoin table may be missing.")
    path.write_text(patched, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

