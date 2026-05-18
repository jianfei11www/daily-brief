#!/usr/bin/env python3
"""
Fetch USDT/USDC supply changes from DefiLlama Stablecoins (free source).

Why this exists:
- The daily brief runtime may have broken proxy env (HTTP_PROXY -> 127.0.0.1:7890 not running)
- Some sandboxes have restricted DNS/network; this script supports a curl-based fallback.

Outputs:
- Prints a small JSON payload to stdout by default (for downstream templating).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Final


LLAMA_STABLECOINS_URL: Final[str] = "https://stablecoins.llama.fi/stablecoins"


@dataclass(frozen=True)
class StablecoinRow:
    symbol: str
    current_usd: float
    prev_day_usd: float
    prev_month_usd: float

    @property
    def day_change_usd(self) -> float:
        return self.current_usd - self.prev_day_usd

    @property
    def month_change_usd(self) -> float:
        # Note: DefiLlama field is "circulatingPrevMonth" (rolling ~30d), not strict calendar MTD.
        return self.current_usd - self.prev_month_usd


def _http_get_json_no_proxy(url: str, timeout_seconds: float) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "daily-brief/1.0 (stablecoin_flows)",
            "Accept": "application/json",
        },
        method="GET",
    )
    # Avoid using env proxies by installing a ProxyHandler with empty config.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout_seconds) as resp:
        data = resp.read()
    return json.loads(data.decode("utf-8"))


def _curl_get_json_no_proxy(url: str, timeout_seconds: float) -> Any:
    env = os.environ.copy()
    for k in [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ]:
        env.pop(k, None)
    # NOTE: keep NO_PROXY untouched; we explicitly pass --noproxy '*'
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "--max-time",
            str(int(timeout_seconds)),
            "--noproxy",
            "*",
            url,
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "").strip()[:300])
    return json.loads(proc.stdout)


def fetch_stablecoin_rows(timeout_seconds: float = 20.0) -> dict[str, StablecoinRow]:
    last_err: Exception | None = None
    payload: Any = None

    for fn in (_http_get_json_no_proxy, _curl_get_json_no_proxy):
        try:
            payload = fn(LLAMA_STABLECOINS_URL, timeout_seconds)
            last_err = None
            break
        except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
            last_err = exc

    if payload is None:
        err_txt = repr(last_err)
        hint = ""
        # Common failure mode in sandboxed runtimes: DNS blocked.
        if "Could not resolve host" in err_txt or "gaierror" in err_txt or "Name or service not known" in err_txt:
            hint = (
                " Network/DNS appears unavailable in this runtime. "
                "Run this fetch in a non-sandboxed shell (or ensure DNS is permitted) and retry."
            )
        raise RuntimeError(f"Failed to fetch DefiLlama stablecoins: {last_err!r}.{hint}")

    assets = payload.get("peggedAssets", [])
    by_symbol: dict[str, StablecoinRow] = {}
    for asset in assets:
        sym = asset.get("symbol")
        if sym not in ("USDT", "USDC"):
            continue
        current = float(asset.get("circulating", {}).get("peggedUSD", 0.0) or 0.0)
        prev_day = float(asset.get("circulatingPrevDay", {}).get("peggedUSD", 0.0) or 0.0)
        prev_month = float(asset.get("circulatingPrevMonth", {}).get("peggedUSD", 0.0) or 0.0)
        by_symbol[sym] = StablecoinRow(sym, current, prev_day, prev_month)

    missing = [s for s in ("USDT", "USDC") if s not in by_symbol]
    if missing:
        raise RuntimeError(f"Missing stablecoin rows from DefiLlama: {missing}")
    return by_symbol


def _fmt_change_usd(x: float) -> str:
    sign = "+" if x >= 0 else "-"
    x = abs(x)
    if x >= 1e9:
        return f"{sign}${x/1e9:.2f}B"
    return f"{sign}${x/1e6:.0f}M"


def _fmt_total_usd(x: float) -> str:
    return f"${x/1e9:.2f}B"


def main() -> int:
    rows = fetch_stablecoin_rows()
    out = {
        "source": LLAMA_STABLECOINS_URL,
        "note": "month_change_usd uses circulatingPrevMonth (~30d), not strict calendar MTD",
        "USDT": {
            "day_change": _fmt_change_usd(rows["USDT"].day_change_usd),
            "month_change": _fmt_change_usd(rows["USDT"].month_change_usd),
            "total": _fmt_total_usd(rows["USDT"].current_usd),
        },
        "USDC": {
            "day_change": _fmt_change_usd(rows["USDC"].day_change_usd),
            "month_change": _fmt_change_usd(rows["USDC"].month_change_usd),
            "total": _fmt_total_usd(rows["USDC"].current_usd),
        },
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
