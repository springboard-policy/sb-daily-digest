"""
Keyword registry and article matching logic.

Tier rules:
  CORE         — always include if any CORE keyword from this category matches.
  FUZZY        — include if this keyword + 2 others from this category match (3 total).
  WATCH        — include if this keyword + 1 other from this category matches (2 total).
  REQUIRED_ANY — at least one keyword from this list must be present, or the category
                 is excluded regardless of other matches. Used to anchor categories to
                 a specific geography or domain and filter out false positives.

Matching rules:
  Short all-caps acronyms (e.g. EI, ESDC) are matched as whole words using
  regex word boundaries to avoid false positives from substrings.
  All other keywords use simple substring matching (case-insensitive).
"""

import re

KEYWORDS = {
    "Northern infrastructure": {
        "REQUIRED_ANY": [
            "Arctic",
            "subarctic",
            "circumpolar",
            "Nunavut",
            "Northwest Territories",
            "Yukon",
            "Inuit",
            "permafrost",
            "icebreaker",
            "Northwest Passage",
            "Mackenzie Valley",
            "northern corridor",
        ],
        "CORE": [
            "deep-water port",
            "Northwest Passage",
            "Arctic Infrastructure Fund",
        ],
        "FUZZY": [
            "corridor",
            "resilience",
            "logistics",
            "permafrost thaw",
            "environmental assessment",
            "self-determination",
        ],
        "WATCH": [
            "Arctic",
            "subarctic",
            "northern",
            "infrastructure",
            "circumpolar",
            "sovereignty",
            "NORAD",
            "Nunavut",
            "Northwest Territories",
            "Yukon",
            "Inuit",
            "permafrost",
            "icebreaker",
            "all-season road",
            "Mackenzie Valley",
            "northern corridor",
            "remote community",
            "defence",
            "surveillance",
            "militarization",
            "climate adaptation",
            "critical infrastructure",
            "procurement",
            "coast guard",
            "search and rescue",
            "satellite communications",
            "energy security",
            "diesel replacement",
            "food security",
            "housing",
        ],
    },
    "Skills policy": {
        "CORE": [
            "upskilling",
            "reskilling",
            "apprenticeship",
            "trades",
            "labour market",
            "recognition of credentials",
            "Labour Market Development Agreement",
            "Workforce Development Agreement",
            "sectoral workforce",
            "green jobs",
            "job transition",
            "AI displacement",
            "micro-credentials",
            "stackable credentials",
            "work-integrated learning",
        ],
        "FUZZY": [
            "attachment",
            "portability",
            "capacity",
            "pathway",
            "transition",
            "adaptability",
            "sectoral",
        ],
        "WATCH": [
            "skills",
            "workforce",
            "employment insurance",
            "EI",
            "training",
            "credentials",
            "Future Skills",
            "ESDC",
            "productivity",
            "competitiveness",
            "automation",
            "prior learning recognition",
            "employment equity",
            "underemployment",
            "labour shortage",
            "temporary foreign workers",
            "co-op",
            "skills gap",
            "digital literacy",
            "journeyperson",
            "Red Seal",
        ],
    },
    "Social assistance": {
        "CORE": [
            "social assistance",
            "welfare",
            "income support",
            "Ontario Works",
            "ODSP",
            "disability benefit",
            "Canada Disability Benefit",
            "guaranteed income",
            "basic income",
            "food insecurity",
            "housing instability",
            "Canada Social Transfer",
            "benefit adequacy",
            "clawback",
            "income threshold",
            "income security",
            "Guaranteed Income Supplement",
            "Canada Child Benefit",
        ],
        "FUZZY": [
            "wraparound",
            "means-tested",
            "assets test",
            "eligibility",
        ],
        "WATCH": [
            "poverty",
            "low income",
            "adequacy",
            "transfers",
            "marginalized",
            "vulnerable populations",
            "equity-deserving",
            "disability",
            "shelter allowance",
            "top-up",
            "earned income",
            "benefit cliff",
            "deep poverty",
        ],
    },
    # Client names are treated as CORE: any mention is always surfaced.
    "Client": {
        "CORE": [
            "Nunavut Tunngavik Incorporated",
            "Prosper Canada",
            "Canadian Centre for Caregiving Excellence",
            "Future Skills Centre",
            "Inuit Tapiriit Kanatami",
            "Century Initiative",
            "369 Global",
        ],
        "FUZZY": [],
        "WATCH": [],
    },
}


def _kw_matches(kw: str, text: str, text_lower: str) -> bool:
    """
    Return True if kw appears in text.

    Short all-caps acronyms (e.g. EI, ESDC, ODSP) are matched as whole words
    to avoid false positives from substrings like 'their' matching 'EI' or
    'allowed' matching the removed 'OW'.  All other keywords use fast
    case-insensitive substring matching.
    """
    if kw.isupper() and len(kw) <= 5:
        return bool(re.search(r'\b' + re.escape(kw) + r'\b', text, re.IGNORECASE))
    return kw.lower() in text_lower


def match_article(title: str, text: str) -> dict:
    """
    Check an article against all keyword categories.

    Returns a dict mapping category name -> { tier, matched }.
    Only categories where the inclusion threshold is met are included.

    Inclusion logic:
      CORE  match -> always include
      FUZZY match -> include if 3+ total keywords from this category match
      WATCH match -> include if 2+ total keywords from this category match
    """
    combined = title + " " + (text or "")
    combined_lower = combined.lower()
    results = {}

    for category, tiers in KEYWORDS.items():
        required_any = tiers.get("REQUIRED_ANY", [])
        if required_any and not any(_kw_matches(kw, combined, combined_lower) for kw in required_any):
            continue

        matched = {"CORE": [], "FUZZY": [], "WATCH": []}

        for tier, keywords in tiers.items():
            if tier == "REQUIRED_ANY":
                continue
            for kw in keywords:
                if _kw_matches(kw, combined, combined_lower):
                    matched[tier].append(kw)

        total = sum(len(v) for v in matched.values())

        if matched["CORE"]:
            top_tier = "CORE"
        elif matched["FUZZY"] and total >= 3:
            top_tier = "FUZZY"
        elif matched["WATCH"] and total >= 2:
            top_tier = "WATCH"
        else:
            continue

        all_matched = matched["CORE"] + matched["FUZZY"] + matched["WATCH"]
        results[category] = {
            "tier": top_tier,
            "matched": all_matched,
        }

    return results
