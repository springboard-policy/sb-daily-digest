"""
House of Commons Committees — Active Studies Fetcher

Returns all committee studies that currently have an open call for briefs,
formatted as standard article dicts for the digest.
"""

import re
import sys
from datetime import date

import requests
from bs4 import BeautifulSoup

BASE_URL    = "https://www.ourcommons.ca"
PARTICIPATE = f"{BASE_URL}/Committees/en/Participate"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; sb-digest-bot/1.0; for internal research)"
    )
}


def _get_soup(url: str) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        print(f"    [warning] Could not fetch {url}: {e}", file=sys.stderr)
        return None


def _get_study_links() -> list[dict]:
    soup = _get_soup(PARTICIPATE)
    if soup is None:
        return []

    studies = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.search(
            r"/committees/en/([A-Z]+)/StudyActivity\?studyActivityId=(\d+)",
            href, re.IGNORECASE,
        )
        if not m:
            continue
        committee = m.group(1).upper()
        activity_id = m.group(2)
        full_url = BASE_URL + href if href.startswith("/") else href
        if full_url in seen:
            continue
        seen.add(full_url)
        title = a.get_text(" ", strip=True) or f"{committee} study"
        studies.append({
            "committee":   committee,
            "activity_id": activity_id,
            "study_url":   full_url,
            "title":       title,
        })
    return studies


def _get_brief_details(study: dict) -> dict | None:
    soup = _get_soup(study["study_url"])
    if soup is None:
        return None

    participate_text = ""
    for heading in soup.find_all(["h2", "h3", "h4"]):
        if "participate" in heading.get_text(strip=True).lower():
            for sibling in heading.find_next_siblings():
                if sibling.name in ("h2", "h3", "h4"):
                    break
                participate_text += sibling.get_text(" ", strip=True) + " "
            break

    if not participate_text:
        return None

    # Check for a deadline and skip if already passed
    date_m = re.search(
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{1,2},?\s+\d{4}",
        participate_text, re.IGNORECASE,
    )
    if date_m:
        from dateutil.parser import parse as parse_date
        try:
            d = parse_date(date_m.group(0).replace(",", "")).date()
            if d < date.today():
                return None
            deadline_note = f" — brief deadline {d.strftime('%B %d, %Y')}"
        except (ValueError, OverflowError):
            deadline_note = ""
    else:
        deadline_note = ""

    page_title = soup.find("h1")
    full_title = page_title.get_text(" ", strip=True) if page_title else study["title"]

    committee_name = study["committee"]
    title_tag = soup.find("title")
    if title_tag:
        parts = [p.strip() for p in title_tag.get_text().split(" - ")]
        for part in reversed(parts):
            if "committee" in part.lower() and len(part) < 100:
                committee_name = part
                break

    submit_url = (
        f"{BASE_URL}/committee-participation/en/submit-brief/"
        f"{study['committee'].lower()}/{study['activity_id']}"
    )

    return {
        "title":        full_title + deadline_note,
        "url":          submit_url,
        "source_name":  "House of Commons Committees",
        "source_type":  "Federal government",
        "article_type": "policy",
        "published_date": date.today().strftime("%B %d, %Y"),
        "summary":      (
            f"Committee: {committee_name}. "
            + participate_text.strip()[:300]
            + ("..." if len(participate_text) > 300 else "")
        ),
    }


def fetch() -> list[dict]:
    """Return open calls for briefs from House of Commons committees."""
    print("  Fetching: House of Commons Committees ...")
    studies = _get_study_links()
    results = []
    for study in studies:
        item = _get_brief_details(study)
        if item:
            results.append(item)
    print(f"    House of Commons Committees: {len(results)} item(s)")
    return results
