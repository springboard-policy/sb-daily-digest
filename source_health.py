"""
Weekly source health check for the Springboard Daily Digest.

Fetches all non-manual sources with a 7-day lookback and reports which
ones are alive vs. silent/broken. Intended to be run weekly (Mondays)
and emailed via send_brief.py.

Usage:
    python source_health.py            # prints report to stdout
    python source_health.py --email    # also emails the report
"""

import sys
from datetime import date, timedelta

import tools  # patch LOOKBACK_HOURS before any fetching
from tools import _get_source, _fetch_rss, _fetch_page_articles, _fetch_scrape_module
from sources import SOURCES

LOOKBACK_DAYS = 7
tools.LOOKBACK_HOURS = LOOKBACK_DAYS * 24


def check_source(src: dict) -> dict:
    """Return {name, id, items, error} for one source."""
    sid  = src["id"]
    name = src["name"]
    try:
        if src.get("scrape_module"):
            items = _fetch_scrape_module(src)
        elif src.get("has_rss") and src.get("rss_url"):
            items = _fetch_rss(src)
        elif src.get("news_url"):
            items = _fetch_page_articles(src)
        else:
            return {"id": sid, "name": name, "items": 0, "status": "manual"}
        return {"id": sid, "name": name, "items": len(items), "status": "ok"}
    except Exception as e:
        return {"id": sid, "name": name, "items": 0, "status": f"error: {e}"}


def run_health_check() -> list[dict]:
    active = [s for s in SOURCES if not s.get("manual")]
    results = []
    for src in active:
        print(f"  Checking {src['name']}...", end="", flush=True)
        r = check_source(src)
        print(f" {r['items']} items")
        results.append(r)
    return results


def build_html_report(results: list[dict], run_date: str) -> str:
    alive  = [r for r in results if r["items"] > 0]
    silent = [r for r in results if r["items"] == 0 and r["status"] == "ok"]
    errors = [r for r in results if r["status"] not in ("ok", "manual")]

    def rows(items, colour):
        return "".join(
            f'<tr><td style="padding:4px 8px;color:{colour}">{r["name"]}</td>'
            f'<td style="padding:4px 8px;text-align:right;color:{colour}">{r["items"]}</td>'
            f'<td style="padding:4px 8px;color:#888;font-size:0.85em">{r["status"]}</td></tr>'
            for r in items
        )

    table_style = "border-collapse:collapse;width:100%;font-family:sans-serif;font-size:14px"
    th_style    = "padding:6px 8px;text-align:left;border-bottom:2px solid #c8a951;color:#1a2b3c"

    return f"""
<!DOCTYPE html><html><body style="background:#f9f8f6;font-family:sans-serif;padding:24px">
<h2 style="color:#1a2b3c;border-bottom:3px solid #c8a951;padding-bottom:6px">
  Springboard Source Health &mdash; week of {run_date}
</h2>
<p style="color:#555">Lookback: {LOOKBACK_DAYS} days &nbsp;&bull;&nbsp;
  {len(alive)} sources with content &nbsp;&bull;&nbsp;
  {len(silent)} silent &nbsp;&bull;&nbsp;
  {len(errors)} errors
</p>

<h3 style="color:#2a6;margin-top:24px">Active ({len(alive)})</h3>
<table style="{table_style}">
  <tr>
    <th style="{th_style}">Source</th>
    <th style="{th_style};text-align:right">Items</th>
    <th style="{th_style}">Status</th>
  </tr>
  {rows(alive, "#222")}
</table>

<h3 style="color:#888;margin-top:24px">Silent — no content in {LOOKBACK_DAYS} days ({len(silent)})</h3>
<table style="{table_style}">
  <tr>
    <th style="{th_style}">Source</th>
    <th style="{th_style};text-align:right">Items</th>
    <th style="{th_style}">Status</th>
  </tr>
  {rows(silent, "#888")}
</table>

{"" if not errors else f'''
<h3 style="color:#c00;margin-top:24px">Errors ({len(errors)})</h3>
<table style="{table_style}">
  <tr>
    <th style="{th_style}">Source</th>
    <th style="{th_style};text-align:right">Items</th>
    <th style="{th_style}">Status</th>
  </tr>
  {rows(errors, "#c00")}
</table>
'''}

</body></html>
"""


if __name__ == "__main__":
    today = date.today()
    run_date = today.strftime("%B %d, %Y")

    print(f"\nSource health check ({LOOKBACK_DAYS}-day window) — {run_date}")
    print("=" * 60)
    results = run_health_check()

    alive  = sum(1 for r in results if r["items"] > 0)
    silent = sum(1 for r in results if r["items"] == 0 and r["status"] == "ok")
    errors = sum(1 for r in results if "error" in r["status"])
    print(f"\n{alive} active / {silent} silent / {errors} errors")

    if "--email" in sys.argv:
        from send_brief import _smtp_send
        html = build_html_report(results, run_date)
        _smtp_send(f"SB Source Health \u2014 {run_date}", html)
