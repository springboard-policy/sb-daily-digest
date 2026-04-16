"""
Keyword filter audit — shows how much content the keyword filter cuts per source.

Runs against the same General sources that use keyword_filter=True in the agent.
No API key required.

By default uses a 72-hour lookback to get enough articles to be meaningful.
The agent uses 28 hours; pass --28h to match production behaviour.

Usage:
    python audit_keywords.py          # 72-hour window
    python audit_keywords.py --28h    # production 28-hour window
"""

import sys
import tools  # import the module so we can patch LOOKBACK_HOURS
from tools import _get_source, _fetch_rss, _fetch_page_articles, _fetch_scrape_module
from keywords import match_article, KEYWORDS

GENERAL_SOURCES = [
    "canada_ca_news",
    "cbc_news",
    "policy_options",
    "hill_times",
    "ipolitics",
    "toronto_star",
    "national_post",
    "globe_mail",
    "macleans",
    "afn",
    "hoc",
    "senate",
]


LOOKBACK = 72 if "--28h" not in sys.argv else 28


def fetch_raw(source_id: str) -> list[dict]:
    src = _get_source(source_id)
    if src is None or src.get("manual"):
        return []
    # Temporarily patch the lookback window in tools module
    original = tools.LOOKBACK_HOURS
    tools.LOOKBACK_HOURS = LOOKBACK
    try:
        if src.get("scrape_module"):
            return _fetch_scrape_module(src)
        elif src.get("has_rss") and src.get("rss_url"):
            return _fetch_rss(src)
        elif src.get("news_url"):
            return _fetch_page_articles(src)
        return []
    finally:
        tools.LOOKBACK_HOURS = original


def audit():
    window = LOOKBACK
    print(f"\nKeyword Filter Audit -- General Sources ({window}h lookback)")
    print("=" * 72)
    print(f"{'Source':<28} {'Total':>6} {'Pass':>6} {'Cut':>6} {'Cut%':>6}  Categories matched")
    print("-" * 72)

    total_all = 0
    total_pass = 0
    cut_articles = []  # (source_name, title, reason)

    for sid in GENERAL_SOURCES:
        src = _get_source(sid)
        name = src["name"] if src else sid
        print(f"  Fetching {name}...", end="", flush=True)

        items = fetch_raw(sid)
        total = len(items)
        passed = []
        cut = []

        for item in items:
            result = match_article(item["title"], item.get("summary", ""))
            if result:
                cats = ", ".join(
                    f"{cat} [{v['tier']}]" for cat, v in result.items()
                )
                passed.append((item["title"], cats))
            else:
                cut.append(item["title"])

        n_pass = len(passed)
        n_cut = total - n_pass
        pct = int(100 * n_cut / total) if total else 0

        # Clear the "Fetching..." line
        print(f"\r{name:<28} {total:>6} {n_pass:>6} {n_cut:>6} {pct:>5}%", end="  ")

        if passed:
            cats_preview = passed[0][1][:30] if passed[0][1] else ""
            print(cats_preview)
        else:
            print("—")

        total_all += total
        total_pass += n_pass

        # Collect details for the cut list
        for title in cut:
            cut_articles.append((name, title))

        # Show what passed (with matched categories)
        if passed:
            for title, cats in passed:
                print(f"    [pass]  {title[:65]}")
                print(f"       -> {cats}")

        if total == 0:
            print(f"    (no articles fetched - source may be down or no new content)")

        print()

    # Summary
    total_cut = total_all - total_pass
    pct_cut = int(100 * total_cut / total_all) if total_all else 0
    print("=" * 72)
    print(f"{'TOTAL':<28} {total_all:>6} {total_pass:>6} {total_cut:>6} {pct_cut:>5}%")
    print()

    if cut_articles:
        print(f"\n--- Cut articles ({len(cut_articles)} total) ---")
        current_src = None
        for src_name, title in cut_articles:
            if src_name != current_src:
                print(f"\n  {src_name}:")
                current_src = src_name
            print(f"    [cut]  {title[:80]}")

    print()


if __name__ == "__main__":
    audit()
