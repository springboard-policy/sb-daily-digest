"""
Senate of Canada Committees — Active Studies Fetcher

Returns Senate committee studies referred in the last RECENT_DAYS days,
formatted as standard article dicts for the digest.
"""

import re
import sys
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup

BASE_URL      = "https://sencanada.ca"
SESSION       = "45-1"
SESSION_START = date(2025, 5, 26)
STUDIES_API   = f"{BASE_URL}/umbraco/surface/CommitteesAjax/GetTablePartialView"
RECENT_DAYS   = 30

EXCLUDED_COMMITTEES = {"CIBA", "SELE", "HRRH", "LTVP", "SEBS"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; sb-digest-bot/1.0; for internal research)"
    ),
    "X-Requested-With": "XMLHttpRequest",
}


def fetch() -> list[dict]:
    """Return Senate committee studies referred in the last RECENT_DAYS days."""
    print("  Fetching: Senate of Canada Committees ...")
    try:
        resp = requests.get(
            STUDIES_API,
            params={
                "tableName":   "Studies",
                "committeeId": 0,
                "pageSize":    250,
                "fromDate":    SESSION_START.isoformat(),
                "toDate":      "",
                "session":     SESSION,
            },
            headers=HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"    [warning] Senate API error: {e}", file=sys.stderr)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    raw_items = soup.find_all("div", class_="cmt-site_v2-studybills-table-study-item")

    results = []
    today = date.today()

    for item in raw_items:
        title_tag = item.find(class_="cmt-site_v2-studybills-table-study-item-name")
        title = title_tag.get_text(" ", strip=True) if title_tag else "Untitled"

        committee_div  = item.find(class_="cmt-site_v2-studybills-table-study-item-committee")
        committee_link = committee_div.find("a") if committee_div else None
        committee_name = committee_link.get_text(strip=True) if committee_link else "Unknown"
        committee_href = committee_link["href"] if committee_link else ""

        m = re.search(r"/committees/([a-zA-Z]+)/?", committee_href)
        acronym = m.group(1).upper() if m else ""

        if acronym in EXCLUDED_COMMITTEES:
            continue

        oor_div  = item.find(class_="cmt-site_v2-studybills-table-study-item-oof")
        oor_date = None
        if oor_div:
            oor_text = oor_div.get_text(" ", strip=True)
            dm = re.search(r"\d{4}-\d{2}-\d{2}", oor_text)
            if dm:
                try:
                    oor_date = datetime.strptime(dm.group(0), "%Y-%m-%d").date()
                except ValueError:
                    pass

        if not oor_date or (today - oor_date).days > RECENT_DAYS:
            continue

        clean_href = re.sub(r"/#\?.*$", "/", committee_href)
        if not clean_href.startswith("http"):
            clean_href = BASE_URL + clean_href

        studies_url = f"{BASE_URL}/en/committees/{acronym.lower()}/studiesandbills/{SESSION}"
        days_ago = (today - oor_date).days

        results.append({
            "title":        title,
            "url":          studies_url,
            "source_name":  "Senate of Canada Committees",
            "source_type":  "Federal government",
            "article_type": "policy",
            "published_date": oor_date.strftime("%B %d, %Y"),
            "summary":      (
                f"Committee: {committee_name} ({acronym}). "
                f"Study referred {days_ago} days ago ({oor_date.strftime('%B %d, %Y')}). "
                f"Written briefs accepted at any time — email ctm@sen.parl.gc.ca."
            ),
        })

    print(f"    Senate of Canada Committees: {len(results)} item(s)")
    return results
