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
import time
from datetime import date

import anthropic

from tools import search_source, fetch_article

MODEL = "claude-sonnet-4-6"

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a Canadian policy intelligence agent for Springboard, a public policy \
consulting firm. Your job is to scan policy news sources and produce a concise \
briefing note suitable for a professional policy audience.

You will be given a list of sources to search. Search them ONE AT A TIME \
sequentially using the search_source tool. For the most important articles \
(typically 3–6 per topic area), use fetch_article to read the full content \
before writing your takeaways.

Begin your response DIRECTLY with the line "# SB Policy Brief — [Full Date]". \
Do not include any preamble, commentary, or self-narration before the brief.

Output Format — produce EXACTLY this structure in Markdown:

# SB Policy Brief — [Full Date]

---

## Northern & Arctic Infrastructure

**Top Takeaways**

1. **[Headline takeaway]** — [1–2 sentences: what happened and why it matters]

2. **[Headline takeaway]** — [1–2 sentences]

(3–5 takeaways max. Only include if there is genuinely relevant news today. \
If nothing significant, write: *No significant developments today.* \
Do NOT list which sources had no content.)

**What to Watch**

- [1–3 bullets on emerging threads worth monitoring]

---

## Skills Policy & Workforce Development

**Top Takeaways**

1. **[Headline takeaway]** — [1–2 sentences]

(3–5 max. If nothing significant, write: *No significant developments today.* \
Do NOT list which sources had no content.)

**What to Watch**

- [1–3 bullets]

---

## Social Assistance & Income Security

**Top Takeaways**

1. **[Headline takeaway]** — [1–2 sentences]

(3–5 max. If nothing significant, write: *No significant developments today.* \
Do NOT list which sources had no content.)

**What to Watch**

- [1–3 bullets]

---

## Client Mentions

List any articles or announcements that mention one of Springboard's clients \
by name. Format: **Client name** — one sentence summary with an inline link.

If no clients were mentioned in any source today, write only: \
*No client mentions today.*

IMPORTANT: Do NOT list clients individually. Do NOT write "no mentions found" \
for any client. Do NOT distinguish between clients that are also source feeds \
(ITK, NTI, FSC) and those that are not — treat all clients the same way. \
Either a client was mentioned in an article today, or it was not. \
If none were mentioned, use only the single line above.

Clients to watch: Nunavut Tunngavik Incorporated (NTI), Prosper Canada, \
Canadian Centre for Caregiving Excellence, Future Skills Centre (FSC), \
Inuit Tapiriit Kanatami (ITK), Century Initiative, 369 Global.

---

## Sources Consulted
- [Article title — Outlet — Author if known](url) [PAYWALLED] if behind a paywall

Guidelines:
- Be selective. 3–5 takeaways per section maximum.
- Keep each takeaway to 1–2 sentences. Be direct — cut throat-clearing and \
  context that a policy professional already knows.
- Prioritize Canadian federal and provincial policy context.
- If multiple sources cover the same story, merge them into one takeaway.
- For committee submission deadlines, one line only: committee name + date.
- Flag paywalled sources with [PAYWALLED] in the sources list.
- Only include sources where you actually found relevant content.
- Links: include inline hyperlinks within takeaway text whenever you are \
  citing a specific article, document, or announcement. Link the most \
  relevant phrase (e.g. the bill name, headline, or org name), not the whole \
  sentence. If a takeaway synthesizes multiple articles, link the primary \
  source inline and list the rest in Sources Consulted.
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
        "norad",
        "cbc_north",
        "nunatsiaq",
        "high_north_news",
        "arctic_today",
        "the_narwhal",
        "itk",
        "nti",
        "inuvialuit",
        "makivik",
        "nunatsiavut",
        "dehcho",
        "yukon_govt",
        "nwt_govt",
        "nunavut_govt",
        "nunavut_housing",
        "arctic_council",
        "arctic_institute",
        "arctic_journal",
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
        "ontario_newsroom",
        "bc_newsroom",
        "alberta_govt",
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
        "cap",
        "pbo",
        "auditor_general",
        "ontario_newsroom",
        "bc_newsroom",
        "alberta_govt",
    ],
    "General (all topics)": [
        "canada_ca_news",
        "cbc_news",
        "canadian_press",
        "policy_options",
        "hill_times",
        "ipolitics",
        "toronto_star",
        "national_post",
        "globe_mail",
        "macleans",
        "the_tyee",
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

GENERAL_SOURCES = set(SOURCES_BY_TOPIC["General (all topics)"])

_stats: dict = {"searched": 0, "with_content": 0}


def _run_tool(name: str, inputs: dict) -> str:
    if name == "search_source":
        source_id = inputs.get("source_id", "")
        print(f"    -> search_source({source_id})")
        keyword_filter = source_id in GENERAL_SOURCES
        result = search_source(source_id, keyword_filter=keyword_filter)
        _stats["searched"] += 1
        if "No recent articles found" not in result:
            _stats["with_content"] += 1
        return result
    elif name == "fetch_article":
        url = inputs.get("url", "")
        print(f"    -> fetch_article({url[:80]}...)")
        return fetch_article(url)
    else:
        return f"Unknown tool: {name}"


# ── Agent loop ────────────────────────────────────────────────────────────────

def run_briefing() -> str:
    """
    Run the full briefing agent. Returns the markdown briefing as a string.
    Raises RuntimeError if ANTHROPIC_API_KEY is not set.
    """
    global _stats
    _stats = {"searched": 0, "with_content": 0}

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

        for attempt in range(5):
            try:
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=messages,
                )
                break
            except anthropic.RateLimitError:
                wait = 60 * (attempt + 1)
                print(f"  Rate limit hit — waiting {wait}s before retry...")
                time.sleep(wait)
        else:
            return "Error: rate limit retries exhausted."

        # Collect any text blocks for potential early-exit inspection
        text_blocks = [b for b in response.content if b.type == "text"]
        tool_blocks = [b for b in response.content if b.type == "tool_use"]

        if response.stop_reason == "end_turn" or not tool_blocks:
            # Agent is done — return the text
            briefing = "\n\n".join(b.text for b in text_blocks).strip()
            print(f"  Agent finished after {iteration} iteration(s).")
            # Append source volume stat
            briefing += (
                f"\n\n---\n*{_stats['with_content']} of {_stats['searched']} "
                f"sources had new content today.*"
            )
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
