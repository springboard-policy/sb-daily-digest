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

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import anthropic

from tools import search_source, fetch_article

# ── Cost constants ────────────────────────────────────────────────────────────
# Verify current pricing at https://anthropic.com/pricing
_COST_PER_M_INPUT  = 3.00   # USD per million input tokens  (claude-sonnet-4-6)
_COST_PER_M_OUTPUT = 15.00  # USD per million output tokens (claude-sonnet-4-6)

MODEL = "claude-sonnet-4-6"

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a Canadian policy intelligence agent for Springboard, a public policy \
consulting firm. Your job is to scan policy news sources and produce a concise \
analytical briefing suitable for a professional policy audience.

You will be given a list of sources to search. Use the search_source tool \
to fetch them — you may call multiple search_source tools in a single turn \
to search several sources in parallel. A good batch size is 6–10 sources \
per turn, grouped by topic. For each article you plan to include, call \
fetch_article first to verify the content and confirm the URL is correct. \
If fetch_article fails or returns no content (e.g. paywalled or server \
blocked), you may still include the article using the title and excerpt \
from search_source — do not discard it solely because full text is unavailable.

You will also receive recent past briefs as context. Use them to identify \
continuing stories and trends — if today's news connects to or develops \
something from the past few weeks, say so explicitly in the analysis line. \
Do NOT repeat content from past briefs; focus only on what is new today.

Begin your response DIRECTLY with the line "# SB Policy Brief — [Full Date]". \
Do not include any preamble, commentary, or self-narration before the brief.

Output Format — produce EXACTLY this structure in Markdown:

# SB Policy Brief — [Full Date]

---

## Skills Policy & Workforce Development

1. **[Headline as a hyperlink](url)** — [One sentence: what happened, no link needed here]
   *[One sentence: why it matters, what it signals, or how it develops a recent trend]*

2. **[Headline as a hyperlink](url)** — ...
   *...*

(4–5 items. Only include genuinely relevant developments. \
If nothing significant: write only the single line \
*No significant developments today.* — do not explain why, \
do not describe what sources returned, do not comment on content \
that was not relevant. Just the single line, nothing else.)

---

## Northern & Arctic Infrastructure

1. **[Headline as a hyperlink](url)** — [One sentence: what happened, no link needed here]
   *[One sentence: significance or connection to recent context]*

(4–5 items. ONLY include stories that are primarily ABOUT infrastructure — \
transportation, energy, housing, telecommunications networks, military/defence \
installations, resource extraction, or built environment — in a territory \
(Yukon, NWT, Nunavut) or the broader Arctic/circumpolar region. \
A story that is merely geographically set in the North but is about education, \
health, social policy, or governance does NOT belong here — place it in \
whichever thematic section fits, or drop it entirely if it does not fit \
Skills Policy or Social Assistance either. Do NOT include provincial stories unless \
they have direct Arctic/circumpolar infrastructure implications. \
If nothing significant: write only the single line \
*No significant developments today.* — do not explain why, \
do not describe what sources returned, do not comment on content \
that was not relevant. Just the single line, nothing else.)

---

## Social Assistance & Income Security

1. **[Headline as a hyperlink](url)** — [One sentence: what happened, no link needed here]
   *[One sentence: significance or connection to recent context]*

(4–5 items. If nothing significant: write only the single line \
*No significant developments today.* — do not explain why, \
do not describe what sources returned, do not comment on content \
that was not relevant. Just the single line, nothing else.)

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
- Each item is exactly two lines: a news line and an analysis line.
- News line: the headline itself is the hyperlink (bold linked text), followed \
  by a dash and one sentence stating what happened. Do not add a second link \
  in the sentence (e.g. no "read the report" or "see here" links). \
  IMPORTANT: use only the exact URL returned by search_source for that article. \
  Never guess, construct, or reuse a URL from a different article or source.
- Analysis line (italicised): one sentence on significance, policy implication, \
  or broader context — draw on your knowledge of Canadian policy, relevant \
  research, historical precedents, institutional dynamics, or recent trends \
  from the past briefs. This line should add something the news line does not \
  — do not just restate the news.
- 4–5 items per section; include 5 only if all are genuinely important.
- Be direct. Cut throat-clearing and context a policy professional already knows.
- If multiple sources cover the same story, merge into one item.
- Section placement: put each story in the section that matches its primary \
  subject matter. An environmental or resource development story belongs in \
  Northern & Arctic Infrastructure even if it has secondary social consequences. \
  A story does not belong in Social Assistance unless it directly concerns \
  income support, benefits, poverty, housing assistance, or social services. \
  CPI and inflation data belong in Social Assistance (cost-of-living and \
  income adequacy implications), not Skills Policy. \
  If your own analysis says "this is primarily an X story," place it in X.
- Exclude procedural stories: do NOT include Access to Information requests, \
  routine government appointments, administrative decisions, or process stories \
  unless they directly reveal substantive new policy content relevant to the \
  three topic areas.
- Committee submission deadlines: news line only (committee + deadline date), \
  analysis line explains why it is relevant to Springboard's clients or topics.
- Flag paywalled sources with [PAYWALLED] in the Sources Consulted list.
- Only list sources where you found relevant content.
"""

# ── Source list organized by topic ───────────────────────────────────────────

# These are the source IDs from sources.py, organized by primary relevance.
# The agent searches them in this order.

SOURCES_BY_TOPIC = {
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
        "diversity_institute",  # keyword-filtered
        "workbc",               # keyword-filtered
    ],
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
        "cipser",               # keyword-filtered
    ],
    "Social Assistance & Income Security": [
        "maytree",
        "campaign2000",
        "wellesley",
        "basic_income_canada",
        "oecd_social",
        "metis_national",
        "nwac",
        "cap",
        "pbo",
        "auditor_general",
        "canadian_review_social_policy",  # keyword-filtered
    ],
    "General (all topics)": [
        # National news
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
        "the_narwhal",
        "canada_gazette",
        "ccpa",
        "cd_howe",
        "afn",
        "hoc",
        "senate",
        # Provincial / territorial newsrooms (keyword-filtered)
        "ontario_newsroom",
        "quebec_govt",
        "bc_newsroom",
        "alberta_govt",
        "manitoba_govt",
        "saskatchewan_govt",
        "nova_scotia_govt",
        "new_brunswick_govt",
        "pei_govt",
        "newfoundland_govt",
    ],
}

# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "search_source",
        "description": (
            "Fetch recent articles from a specific policy source. "
            "On most days covers the last 24 hours; on Mondays covers 72 hours (Fri–Sun). "
            "Pass the source ID exactly as given in the source list. "
            "Returns a list of recent article titles, URLs, and excerpts. "
            "On Mondays, each article includes its publication day in brackets."
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

GENERAL_SOURCES  = set(SOURCES_BY_TOPIC["General (all topics)"]) | {
    "diversity_institute",
    "workbc",
    "cipser",
    "canadian_review_social_policy",
}
ALL_SOURCE_IDS   = [sid for ids in SOURCES_BY_TOPIC.values() for sid in ids]

_stats:           dict       = {"searched": 0, "with_content": 0, "errors": 0, "error_sources": []}
_usage:           dict       = {"input_tokens": 0, "output_tokens": 0}
_fixtures:        dict|None  = None   # None = live mode; dict = replay mode
_fixture_capture: dict       = {}     # populated during every run


def _run_tool(name: str, inputs: dict) -> str:
    if name == "search_source":
        source_id = inputs.get("source_id", "")
        print(f"    -> search_source({source_id})")

        if _fixtures is not None:
            # Replay mode: return saved result, skip live fetch
            result = _fixtures.get(source_id, f"=== {source_id} ===\nNo data in fixture.\n")
            print(f"       [fixture]")
        else:
            keyword_filter = source_id in GENERAL_SOURCES
            result = search_source(source_id, keyword_filter=keyword_filter)
            _stats["searched"] += 1
            if "Fetch error" in result:
                _stats["errors"] += 1
                _stats["error_sources"].append(source_id)
            elif "No recent articles found" not in result:
                _stats["with_content"] += 1

        _fixture_capture[source_id] = result
        return result
    elif name == "fetch_article":
        url = inputs.get("url", "")
        print(f"    -> fetch_article({url[:80]}...)")
        return fetch_article(url)
    else:
        return f"Unknown tool: {name}"


# ── Recent context ───────────────────────────────────────────────────────────

def _load_recent_briefs(n: int = 5) -> list[tuple[str, str]]:
    """
    Return the last n completed briefs as (human_date, content) pairs,
    in chronological order, excluding today.
    """
    today = date.today().isoformat()
    paths = sorted(
        [p for p in Path(".").glob("brief_*.md")
         if p.stem.replace("brief_", "") < today],
        reverse=True,
    )[:n]
    result = []
    for p in reversed(paths):
        date_str = p.stem.replace("brief_", "")
        try:
            label = date.fromisoformat(date_str).strftime("%A, %B %d, %Y")
        except ValueError:
            label = date_str
        result.append((label, p.read_text(encoding="utf-8")))
    return result


# ── Public accessors ─────────────────────────────────────────────────────────

def _calc_cost() -> float:
    """Compute USD cost for the current run, accounting for cache-read discount."""
    return (
        _usage["input_tokens"]        / 1_000_000 * _COST_PER_M_INPUT
        + _usage["output_tokens"]     / 1_000_000 * _COST_PER_M_OUTPUT
        + _usage["cache_read_tokens"] / 1_000_000 * (_COST_PER_M_INPUT * 0.1)
        # cache_create tokens are billed at 1.25× input; already counted in input_tokens
    )


def get_last_run_cost() -> str:
    """
    Return a short cost string for the most recent run_briefing() call,
    e.g. '127,430 tokens · ~$0.43'.  Returns '' if no tokens were used
    (e.g. brief was loaded from cache).
    """
    total = _usage["input_tokens"] + _usage["output_tokens"]
    if total == 0:
        return ""
    cost = _calc_cost()
    return f"{total:,} tokens &middot; ~${cost:.2f}"


# ── Logging helpers ───────────────────────────────────────────────────────────

def _log_run(date_str: str, iterations: int) -> None:
    """Save fixtures and log token/cost data after a completed run."""
    # Auto-save fixtures (live runs only — skip if replaying)
    if _fixtures is None and _fixture_capture:
        Path("fixtures").mkdir(exist_ok=True)
        payload = {"date": date_str, "sources": _fixture_capture}
        for path in (f"fixtures/{date_str}.json", "fixtures/latest.json"):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)

    # Calculate and log cost
    cost = _calc_cost()
    entry = {
        "date":                 date_str,
        "model":                MODEL,
        "input_tokens":         _usage["input_tokens"],
        "output_tokens":        _usage["output_tokens"],
        "iterations":           iterations,
        "sources_searched":     _stats["searched"],
        "sources_with_content": _stats["with_content"],
        "sources_errors":       _stats["errors"],
        "approx_cost_usd":      round(cost, 4),
        "test_mode":            _fixtures is not None,
    }
    with open("costs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    flag = " [test mode]" if _fixtures is not None else ""
    print(
        f"  Tokens: {_usage['input_tokens']:,} in / {_usage['output_tokens']:,} out"
        f"  (~${cost:.3f}){flag}"
    )


# ── Agent loop ────────────────────────────────────────────────────────────────

def run_briefing(fixtures_path: str | None = None) -> str:
    """
    Run the full briefing agent. Returns the markdown briefing as a string.
    Raises RuntimeError if ANTHROPIC_API_KEY is not set.

    Pass fixtures_path to replay a saved fixture file instead of fetching
    live sources (useful for prompt testing without spending on HTTP calls).
    """
    global _stats, _usage, _fixtures, _fixture_capture
    _stats           = {"searched": 0, "with_content": 0, "errors": 0, "error_sources": []}
    _usage           = {"input_tokens": 0, "output_tokens": 0,
                        "cache_read_tokens": 0, "cache_create_tokens": 0}
    _fixture_capture = {}

    if fixtures_path:
        with open(fixtures_path, encoding="utf-8") as f:
            data = json.load(f)
        _fixtures = data.get("sources", data)  # support both wrapped and bare formats
        print(f"  [test mode] Replaying fixtures from {fixtures_path}")
    else:
        _fixtures = None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to your .env file or environment variables."
        )

    client   = anthropic.Anthropic(api_key=api_key)
    date_str  = date.today().isoformat()
    today_str = date.today().strftime("%A, %B %d, %Y")

    # Build the source list for the user message
    source_lines = []
    for topic, ids in SOURCES_BY_TOPIC.items():
        source_lines.append(f"\n**{topic}:**")
        for sid in ids:
            source_lines.append(f"  - {sid}")
    sources_text = "\n".join(source_lines)

    # Load recent briefs for trend/context awareness (up to 30 days)
    recent = _load_recent_briefs(n=30) if _fixtures is None else []
    if recent:
        context_parts = [
            f"=== {label} ===\n{content.strip()}"
            for label, content in recent
        ]
        context_block = (
            "Recent briefs for context — use these to identify continuing "
            "stories and developing trends. Do NOT repeat their content; "
            "focus only on what is new today.\n\n"
            + "\n\n".join(context_parts)
            + "\n\n---\n\n"
        )
    else:
        context_block = ""

    is_monday = date.today().weekday() == 0

    task_message = (
        f"Today is {today_str}.\n\n"
        f"Please produce the daily Springboard policy brief.\n\n"
        f"Search the following sources using search_source "
        f"(parallel batches of 6–10 per turn), "
        f"then fetch full articles for the most important items:\n"
        f"{sources_text}\n\n"
        f"After searching all sources, write the briefing note."
    )

    if is_monday:
        task_message += (
            "\n\nIMPORTANT: Today is Monday. The sources cover the past 72 hours "
            "(Friday through Sunday). Each article result includes its publication "
            "day in brackets — e.g. [Friday], [Saturday], [Sunday]. "
            "Include the day in the news line for each item. "
            "Put the day label BEFORE the hyperlink, not inside it, to avoid "
            "breaking markdown — like this: "
            "[Friday] **[Headline](url)** — one sentence."
        )

    # Structure messages so the stable context block and system prompt are
    # cached — saves ~90% on their tokens for iterations 2–N of the agent loop.
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": context_block + task_message,
                    **({"cache_control": {"type": "ephemeral"}} if context_block else {}),
                }
            ],
        }
    ]

    system_param = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    print(f"\nRunning briefing agent ({MODEL}) ...")
    iteration = 0
    max_iterations = 120  # safety limit

    while iteration < max_iterations:
        iteration += 1

        for attempt in range(5):
            try:
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=8192,
                    system=system_param,
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

        # Accumulate token usage (cache_read tokens billed at 10% of input rate)
        _usage["input_tokens"]        += response.usage.input_tokens
        _usage["output_tokens"]       += response.usage.output_tokens
        _usage["cache_read_tokens"]   += getattr(response.usage, "cache_read_input_tokens",  0)
        _usage["cache_create_tokens"] += getattr(response.usage, "cache_creation_input_tokens", 0)

        # Collect any text blocks for potential early-exit inspection
        text_blocks = [b for b in response.content if b.type == "text"]
        tool_blocks = [b for b in response.content if b.type == "tool_use"]

        if response.stop_reason == "end_turn" or not tool_blocks:
            # Before accepting the brief, check all sources were searched
            if _fixtures is None:
                unsearched = [sid for sid in ALL_SOURCE_IDS if sid not in _fixture_capture]
                if unsearched:
                    print(f"  Coverage check: {len(unsearched)} source(s) not yet searched — continuing.")
                    nudge = (
                        "Before finishing, you still need to search these sources:\n"
                        + "\n".join(f"  - {sid}" for sid in unsearched)
                        + "\n\nPlease search them now, then produce the final brief."
                    )
                    messages.append({"role": "assistant", "content": response.content})
                    messages.append({"role": "user", "content": [{"type": "text", "text": nudge}]})
                    continue

            # All sources searched — finalise
            briefing = "\n\n".join(b.text for b in text_blocks).strip()
            print(f"  Agent finished after {iteration} iteration(s).")

            # Append source volume stat
            if _stats["errors"]:
                error_list = ", ".join(_stats["error_sources"])
                error_note = f" · {_stats['errors']} fetch errors ({error_list})"
            else:
                error_note = ""
            briefing += (
                f"\n\n---\n*{_stats['with_content']} of {_stats['searched']} "
                f"sources had new content today{error_note}.*"
            )

            _log_run(date_str, iteration)
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
