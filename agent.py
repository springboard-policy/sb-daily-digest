"""
Springboard Daily Briefing Agent

Uses Claude with tool use to search policy sources one at a time and produce
a concise briefing note covering three topic areas:
  • Northern & Arctic Infrastructure
  • Skills Policy & Workforce Development
  • Social Assistance & Income Security
  • Client Mentions

Requires ANTHROPIC_API_KEY in the environment.
"""

import os
import sys
from datetime import date

import anthropic

from tools import search_source, fetch_article

MODEL = "claude-sonnet-4-6"

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a Canadian policy intelligence agent for Springboard, a public policy \
consulting firm. Your job is to scan policy news sources and produce a short, \
accessible briefing note suitable for a professional policy audience.

You will be given a list of sources to search. Search them ONE AT A TIME \
sequentially using the search_source tool. For the most important articles \
(typically 3–6 per topic area), use fetch_article to read the full content \
before writing your takeaways.

Output Format — produce EXACTLY this structure in Markdown:

# SB Policy Brief — [Full Date]

---

## Northern & Arctic Infrastructure

**Top Takeaways**

1. **[Headline takeaway]** — [2–3 sentences: what happened and why it matters]

2. **[Headline takeaway]** — [2–3 sentences]

(3–5 takeaways max. Only include if there is genuinely relevant news today. \
If nothing significant, write: *No significant developments today.*)

**What to Watch**
- [1–3 bullets on emerging threads worth monitoring]

---

## Skills Policy & Workforce Development

**Top Takeaways**

1. **[Headline takeaway]** — [2–3 sentences]

(3–5 max)

**What to Watch**
- [1–3 bullets]

---

## Social Assistance & Income Security

**Top Takeaways**

1. **[Headline takeaway]** — [2–3 sentences]

(3–5 max)

**What to Watch**
- [1–3 bullets]

---

## Client Mentions

List any mentions of Springboard's clients. If none, write: \
*No client mentions today.*

Clients to watch: Nunavut Tunngavik Incorporated (NTI), Prosper Canada, \
Canadian Centre for Caregiving Excellence, Future Skills Centre (FSC), \
Inuit Tapiriit Kanatami (ITK), Century Initiative, 369 Global.

---

## Sources Consulted
- [Article title — Outlet — Author if known](url) [PAYWALLED] if behind a paywall

Guidelines:
- Be selective. 3–5 takeaways per section maximum.
- Keep each takeaway to 2–3 sentences. No long paragraphs.
- Prioritize Canadian federal and provincial policy context.
- If multiple sources cover the same story, merge them into one takeaway.
- Flag paywalled sources with [PAYWALLED] in the sources list.
- Only include sources where you actually found relevant content.
"""

# ── Source list organized by topic ───────────────────────────────────────────

# These are the source IDs from sources.py, organized by primary relevance.
# The agent searches them in this order.

SOURCES_BY_TOPIC = {
    "Northern & Arctic Infrastructure": [
        "national_defence",
        "transport_canada",
        "global_affairs",
        "cannor",
        "cbc_north",
        "nunatsiaq",
        "high_north_news",
        "arctic_today",
        "the_narwhal",
        "itk",
        "nti",
        "inuvialuit",
        "yukon_govt",
        "nwt_govt",
        "nunavut_govt",
        "arctic_council",
        "arctic_institute",
        "atlantic_council",
    ],
    "Skills Policy & Workforce Development": [
        "esdc",
        "future_skills_centre",
        "lmic",
        "conference_board",
        "brookfield",
        "colleges_institutes",
        "oecd_skills",
        "ilo",
        "statcan",
        "cpp_journal",
    ],
    "Social Assistance & Income Security": [
        "canada_gazette",
        "maytree",
        "campaign2000",
        "wellesley",
        "basic_income_canada",
        "cd_howe",
        "ccpa",
        "oecd_social",
        "metis_national",
        "nwac",
        "pbo",
        "auditor_general",
    ],
    "General (all topics)": [
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
    ],
}

# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "search_source",
        "description": (
            "Fetch recent articles (last 28 hours) from a specific policy source. "
            "Pass the source ID exactly as given in the source list. "
            "Returns a list of recent article titles, URLs, and excerpts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source_id": {
                    "type": "string",
                    "description": "The source ID from the provided list, e.g. 'cbc_news'",
                }
            },
            "required": ["source_id"],
        },
    },
    {
        "name": "fetch_article",
        "description": (
            "Fetch and read the full text of a specific article by URL. "
            "Use this for the most important articles before writing takeaways. "
            "Returns up to ~5000 characters of cleaned article text."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full URL of the article to fetch.",
                }
            },
            "required": ["url"],
        },
    },
]

# ── Tool dispatcher ───────────────────────────────────────────────────────────

def _run_tool(name: str, inputs: dict) -> str:
    if name == "search_source":
        source_id = inputs.get("source_id", "")
        print(f"    → search_source({source_id})")
        return search_source(source_id)
    elif name == "fetch_article":
        url = inputs.get("url", "")
        print(f"    → fetch_article({url[:80]}...)")
        return fetch_article(url)
    else:
        return f"Unknown tool: {name}"


# ── Agent loop ────────────────────────────────────────────────────────────────

def run_briefing() -> str:
    """
    Run the full briefing agent. Returns the markdown briefing as a string.
    Raises RuntimeError if ANTHROPIC_API_KEY is not set.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to your .env file or environment variables."
        )

    client = anthropic.Anthropic(api_key=api_key)
    today_str = date.today().strftime("%A, %B %d, %Y")

    # Build the source list for the user message
    source_lines = []
    for topic, ids in SOURCES_BY_TOPIC.items():
        source_lines.append(f"\n**{topic}:**")
        for sid in ids:
            source_lines.append(f"  - {sid}")
    sources_text = "\n".join(source_lines)

    user_message = (
        f"Today is {today_str}.\n\n"
        f"Please produce the daily Springboard policy brief.\n\n"
        f"Search the following sources one at a time using search_source, "
        f"then fetch full articles for the most important items:\n"
        f"{sources_text}\n\n"
        f"After searching all sources, write the briefing note."
    )

    messages = [{"role": "user", "content": user_message}]

    print(f"\nRunning briefing agent ({MODEL}) ...")
    iteration = 0
    max_iterations = 120  # safety limit

    while iteration < max_iterations:
        iteration += 1

        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Collect any text blocks for potential early-exit inspection
        text_blocks = [b for b in response.content if b.type == "text"]
        tool_blocks = [b for b in response.content if b.type == "tool_use"]

        if response.stop_reason == "end_turn" or not tool_blocks:
            # Agent is done — return the text
            briefing = "\n\n".join(b.text for b in text_blocks).strip()
            print(f"  Agent finished after {iteration} iteration(s).")
            return briefing

        # Handle tool calls
        print(f"  Iteration {iteration}: {len(tool_blocks)} tool call(s)")
        tool_results = []
        for block in tool_blocks:
            result = _run_tool(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })

        # Append assistant turn + tool results
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return "Error: agent did not complete within the iteration limit."
