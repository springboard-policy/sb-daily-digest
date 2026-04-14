"""
Keyword registry and article matching logic.

Tier rules:
  CORE  — always include if any CORE keyword from this category matches.
  FUZZY — include if this keyword + 2 others from this category match (3 total).
  WATCH — include if this keyword + 1 other from this category matches (2 total).
"""

KEYWORDS = {
    "Northern infrastructure": {
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
            "OW",
            "ODSP",
            "disability benefit",
            "Canada Disability Benefit",
            "CDB",
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
            "GIS",
            "CCB",
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
    combined = (title + " " + (text or "")).lower()
    results = {}

    for category, tiers in KEYWORDS.items():
        matched = {"CORE": [], "FUZZY": [], "WATCH": []}

        for tier, keywords in tiers.items():
            for kw in keywords:
                if kw.lower() in combined:
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
