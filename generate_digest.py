"""
Springboard Daily Digest — Generator
======================================
Runs the briefing agent, converts the markdown output to a styled HTML page,
and saves it to docs/index.html (and a dated archive file).

Run:
    python generate_digest.py

Requires ANTHROPIC_API_KEY in the environment or a .env file.
"""

import glob
import os
import re
import sys
from datetime import date, datetime

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import markdown as md

from agent import run_briefing
from send_brief import send_brief

# ── HTML wrapper template ─────────────────────────────────────────────────────

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SB Policy Brief — {date_str}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: Georgia, "Times New Roman", serif;
      font-size: 16px;
      line-height: 1.7;
      background: #f9f8f6;
      color: #1a1a1a;
    }}

    /* ── Header ── */
    .page-header {{
      background: #1a2b3c;
      color: #fff;
      padding: 1.5rem 2.5rem 1.25rem;
      border-bottom: 4px solid #c8a951;
    }}
    .page-header .org {{ font-size: 0.8rem; letter-spacing: 0.12em; text-transform: uppercase; opacity: 0.6; margin-bottom: 0.3rem; }}
    .page-header h1 {{ font-size: 1.5rem; font-weight: 700; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .page-header .dateline {{ font-size: 0.88rem; opacity: 0.7; margin-top: 0.25rem; font-family: -apple-system, sans-serif; }}
    .page-header .archive-link {{ font-size: 0.78rem; opacity: 0.55; margin-top: 0.4rem; font-family: -apple-system, sans-serif; }}
    .page-header .archive-link a {{ color: #fff; text-decoration: none; border-bottom: 1px solid rgba(255,255,255,0.3); }}
    .page-header .archive-link a:hover {{ opacity: 1; border-bottom-color: #c8a951; }}

    /* ── Layout ── */
    .content {{
      max-width: 820px;
      margin: 2rem auto;
      padding: 0 1.5rem 4rem;
    }}

    /* ── Markdown body styles ── */
    .brief h1 {{
      font-size: 1.4rem;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-weight: 700;
      color: #1a2b3c;
      margin: 2rem 0 0.5rem;
      padding-bottom: 0.4rem;
      border-bottom: 2px solid #c8a951;
    }}
    .brief h2 {{
      font-size: 1.15rem;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-weight: 700;
      color: #1a2b3c;
      margin: 2rem 0 0.75rem;
      padding-bottom: 0.3rem;
      border-bottom: 1px solid #ddd;
    }}
    .brief h3 {{
      font-size: 1rem;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-weight: 700;
      color: #333;
      margin: 1.25rem 0 0.4rem;
    }}
    .brief p {{
      margin-bottom: 0.75rem;
    }}
    .brief ol, .brief ul {{
      padding-left: 1.5rem;
      margin-bottom: 0.75rem;
    }}
    .brief li {{
      margin-bottom: 0.5rem;
    }}
    .brief ol > li {{
      padding-left: 0.25rem;
    }}
    /* Style the numbered takeaways */
    .brief ol > li > strong:first-child {{
      color: #1a2b3c;
      font-size: 1rem;
    }}
    .brief hr {{
      border: none;
      border-top: 1px solid #ddd;
      margin: 2rem 0;
    }}
    .brief a {{
      color: #1a5c9e;
      text-decoration: none;
    }}
    .brief a:hover {{
      text-decoration: underline;
    }}
    /* Paywalled label */
    .brief a + em, .brief li em:last-child {{
      font-size: 0.8rem;
      color: #888;
      font-style: normal;
    }}
    /* "What to Watch" and "Top Takeaways" labels */
    .brief p > strong:only-child {{
      display: block;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 0.75rem;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: #888;
      margin: 1.25rem 0 0.4rem;
    }}
    /* Italic "no content" notes */
    .brief em {{ color: #777; font-size: 0.95rem; }}

    /* ── Footer ── */
    .page-footer {{
      text-align: center;
      font-size: 0.78rem;
      color: #aaa;
      font-family: -apple-system, sans-serif;
      padding: 1.5rem;
      border-top: 1px solid #e0e0e0;
    }}

    @media (max-width: 600px) {{
      .page-header {{ padding: 1rem; }}
      .content {{ padding: 0 1rem 3rem; }}
    }}
  </style>
</head>
<body>

<header class="page-header">
  <div class="org">Springboard</div>
  <h1>Daily Policy Brief</h1>
  <div class="dateline">{date_long}</div>
  <div class="archive-link"><a href="archive.html">Past briefs &rarr;</a></div>
</header>

<main class="content">
  <div class="brief">
{body}
  </div>
</main>

<footer class="page-footer">
  Generated {date_str} &nbsp;&middot;&nbsp; Springboard Daily Policy Brief
</footer>

</body>
</html>
"""


# ── Markdown → HTML ───────────────────────────────────────────────────────────

def _to_html(markdown_text: str) -> str:
    """Convert the agent's markdown output to HTML."""
    # Strip the top-level H1 (we render that in the page header)
    cleaned = re.sub(r"^#\s+SB Policy Brief[^\n]*\n", "", markdown_text, flags=re.IGNORECASE).strip()

    html_body = md.markdown(
        cleaned,
        extensions=["extra", "sane_lists"],
    )
    return html_body


# ── Main ─────────────────────────────────────────────────────────────────────

def _already_ran_today(date_str: str) -> str | None:
    """Return saved markdown if today's brief already exists, else None."""
    md_path = f"brief_{date_str}.md"
    if os.path.exists(md_path):
        print(f"  Brief for {date_str} already exists — skipping agent.")
        with open(md_path, encoding="utf-8") as f:
            return f.read()
    return None


def generate() -> str:
    today = date.today()
    date_str  = today.isoformat()
    date_long = today.strftime("%A, %B %d, %Y")

    print(f"\nSpringboard Daily Digest — {date_long}")
    print("=" * 50)

    briefing_md = _already_ran_today(date_str)
    if briefing_md is None:
        try:
            briefing_md = run_briefing()
        except RuntimeError as e:
            print(f"\nERROR: {e}", file=sys.stderr)
            sys.exit(1)

    body_html = _to_html(briefing_md)

    html = HTML_TEMPLATE.format(
        date_str=date_str,
        date_long=date_long,
        body=body_html,
    )

    os.makedirs("docs", exist_ok=True)

    # Save dated archive copy and today's index
    archive_path = f"docs/{date_str}.html"
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(html)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)

    # Rebuild archive listing
    _build_archive()

    # Save the raw markdown (used as cache to skip re-running the agent)
    with open(f"brief_{date_str}.md", "w", encoding="utf-8") as f:
        f.write(briefing_md)

    # Email the brief
    send_brief(html, date_long)

    return archive_path


def _build_archive() -> None:
    """Regenerate docs/archive.html from all dated brief files in docs/."""
    dated = sorted(
        glob.glob("docs/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].html"),
        reverse=True,
    )

    rows = []
    for path in dated:
        fname    = os.path.basename(path)          # e.g. 2026-04-14.html
        date_str = fname.replace(".html", "")
        try:
            d        = datetime.strptime(date_str, "%Y-%m-%d")
            label    = d.strftime("%A, %B %d, %Y")
        except ValueError:
            label = date_str
        rows.append(f'    <li><a href="{fname}">{label}</a></li>')

    items_html = "\n".join(rows) if rows else "    <li><em>No briefs yet.</em></li>"

    archive_html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SB Policy Brief — Archive</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #f9f8f6; color: #1a1a1a; margin: 0; }}
    .page-header {{ background: #1a2b3c; color: #fff; padding: 1.5rem 2.5rem 1.25rem;
                    border-bottom: 4px solid #c8a951; }}
    .page-header .org {{ font-size: 0.8rem; letter-spacing: 0.12em;
                         text-transform: uppercase; opacity: 0.6; margin-bottom: 0.3rem; }}
    .page-header h1 {{ font-size: 1.5rem; font-weight: 700; margin: 0; }}
    .page-header .sub {{ font-size: 0.88rem; opacity: 0.7; margin-top: 0.25rem; }}
    .page-header .sub a {{ color: #fff; }}
    .content {{ max-width: 600px; margin: 2rem auto; padding: 0 1.5rem 4rem; }}
    h2 {{ font-size: 1.1rem; color: #1a2b3c; border-bottom: 2px solid #c8a951;
          padding-bottom: 0.3rem; margin-bottom: 1rem; }}
    ul {{ list-style: none; padding: 0; }}
    li {{ padding: 0.5rem 0; border-bottom: 1px solid #eee; }}
    a {{ color: #1a5c9e; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .page-footer {{ text-align: center; font-size: 0.78rem; color: #aaa;
                    padding: 1.5rem; border-top: 1px solid #e0e0e0; }}
  </style>
</head>
<body>
<header class="page-header">
  <div class="org">Springboard</div>
  <h1>Daily Policy Brief</h1>
  <div class="sub"><a href="index.html">&larr; Today's brief</a></div>
</header>
<main class="content">
  <h2>Archive</h2>
  <ul>
{items_html}
  </ul>
</main>
<footer class="page-footer">Springboard Daily Policy Brief</footer>
</body>
</html>
"""

    with open("docs/archive.html", "w", encoding="utf-8") as f:
        f.write(archive_html)
    print(f"  Archive updated: {len(dated)} brief(s) listed.")


if __name__ == "__main__":
    path = generate()
    print(f"\nDone. Saved to: {path}")
    print(f"Also written to: docs/index.html")
    print(f"Open with: start {path}")
