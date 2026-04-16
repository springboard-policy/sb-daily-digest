"""
Springboard Daily Digest — Generator
======================================
Runs the briefing agent, converts the markdown output to a styled HTML page,
and saves it to docs/index.html (and a dated archive file).

Run:
    python generate_digest.py           # normal run (skips if today's brief exists)
    python generate_digest.py --force   # re-run even if today's brief already exists

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

from agent import run_briefing, get_last_run_cost

# ── HTML wrapper template ─────────────────────────────────────────────────────

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SB Policy Brief — {date_str}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: "Inter", system-ui, -apple-system, sans-serif;
      font-size: 15px;
      line-height: 1.65;
      background: #f4f3f0;
      color: #1c1c1c;
    }}

    /* ── Header ── */
    .page-header {{
      background: #1a2b3c;
      color: #fff;
      padding: 1.5rem 2.5rem 1.25rem;
      border-bottom: 3px solid #c8a951;
    }}
    .page-header .org {{
      font-size: 0.68rem;
      font-weight: 600;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      opacity: 0.5;
      margin-bottom: 0.3rem;
    }}
    .page-header h1 {{
      font-size: 1.35rem;
      font-weight: 700;
      letter-spacing: -0.01em;
    }}
    .page-header .dateline {{
      font-size: 0.85rem;
      font-weight: 400;
      opacity: 0.6;
      margin-top: 0.2rem;
    }}
    .page-header .archive-link {{
      font-size: 0.75rem;
      opacity: 0.45;
      margin-top: 0.4rem;
    }}
    .page-header .archive-link a {{
      color: #fff;
      text-decoration: none;
      border-bottom: 1px solid rgba(255,255,255,0.25);
    }}
    .page-header .archive-link a:hover {{ opacity: 1; border-bottom-color: #c8a951; }}

    /* ── Layout ── */
    .content {{
      max-width: 760px;
      margin: 2.5rem auto;
      padding: 0 1.5rem 5rem;
    }}

    /* ── Section headings ── */
    .brief h2 {{
      font-size: 0.7rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: #1a2b3c;
      margin: 3rem 0 0;
      padding-bottom: 0.5rem;
      border-bottom: 2px solid #c8a951;
    }}

    .brief hr {{ display: none; }}

    /* ── Numbered items ── */
    .brief ol {{
      list-style: none;
      padding: 0;
      margin: 0;
      counter-reset: brief-item;
    }}
    .brief ol > li {{
      counter-increment: brief-item;
      position: relative;
      padding: 1rem 0 1rem 2.25rem;
      border-bottom: 1px solid #e5e3de;
    }}
    .brief ol > li::before {{
      content: counter(brief-item);
      position: absolute;
      left: 0;
      top: 1.1rem;
      font-size: 0.7rem;
      font-weight: 700;
      color: #c8a951;
      width: 1.5rem;
      text-align: right;
    }}
    .brief ol > li p {{
      margin: 0 0 0.3rem;
    }}
    .brief ol > li p:last-child {{ margin-bottom: 0; }}
    .brief ol > li em {{
      font-style: italic;
      color: #555;
      font-size: 0.925rem;
      line-height: 1.55;
    }}

    /* ── Bullet lists (Sources Consulted) ── */
    .brief ul {{
      padding-left: 1rem;
      margin: 0.5rem 0 0;
    }}
    .brief ul li {{
      margin-bottom: 0.35rem;
      font-size: 0.875rem;
      color: #555;
    }}

    /* ── Inline ── */
    .brief a {{ color: #1a5c9e; text-decoration: none; }}
    .brief a:hover {{ text-decoration: underline; }}
    .brief p {{ margin-bottom: 0.5rem; }}
    .brief em {{ color: #777; }}

    /* ── Footer ── */
    .page-footer {{
      text-align: center;
      font-size: 0.75rem;
      color: #b0b0b0;
      padding: 1.5rem;
      border-top: 1px solid #e0ded9;
    }}

    @media (max-width: 600px) {{
      .page-header {{ padding: 1.25rem 1rem; }}
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
  Generated {date_str} &nbsp;&middot;&nbsp; Springboard Daily Policy Brief{cost_info}
</footer>

</body>
</html>
"""


# ── Markdown → HTML ───────────────────────────────────────────────────────────

def _to_html(markdown_text: str) -> str:
    """Convert the agent's markdown output to HTML."""
    # Drop any agent preamble before the brief heading
    markdown_text = re.sub(r"^.*?(#\s+SB Policy Brief)", r"\1", markdown_text, flags=re.IGNORECASE | re.DOTALL)
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


def generate(force: bool = False) -> str:
    today = date.today()
    date_str  = today.isoformat()
    date_long = today.strftime("%A, %B %d, %Y")

    print(f"\nSpringboard Daily Digest — {date_long}")
    print("=" * 50)

    briefing_md = None if force else _already_ran_today(date_str)
    if briefing_md is None:
        try:
            briefing_md = run_briefing()
        except RuntimeError as e:
            print(f"\nERROR: {e}", file=sys.stderr)
            sys.exit(1)

    body_html = _to_html(briefing_md)

    cost = get_last_run_cost()
    cost_info = f" &nbsp;&middot;&nbsp; {cost}" if cost else ""

    html = HTML_TEMPLATE.format(
        date_str=date_str,
        date_long=date_long,
        body=body_html,
        cost_info=cost_info,
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
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: "Inter", system-ui, -apple-system, sans-serif;
      font-size: 15px;
      line-height: 1.65;
      background: #f4f3f0;
      color: #1c1c1c;
    }}
    .page-header {{ background: #1a2b3c; color: #fff; padding: 1.5rem 2.5rem 1.25rem; border-bottom: 3px solid #c8a951; }}
    .page-header .org {{ font-size: 0.68rem; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; opacity: 0.5; margin-bottom: 0.3rem; }}
    .page-header h1 {{ font-size: 1.35rem; font-weight: 700; letter-spacing: -0.01em; }}
    .page-header .sub {{ font-size: 0.85rem; opacity: 0.6; margin-top: 0.2rem; }}
    .page-header .sub a {{ color: #fff; text-decoration: none; }}
    .content {{ max-width: 560px; margin: 2.5rem auto; padding: 0 1.5rem 4rem; }}
    h2 {{ font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em;
          color: #1a2b3c; border-bottom: 2px solid #c8a951; padding-bottom: 0.5rem; margin-bottom: 1.25rem; }}
    ul {{ list-style: none; padding: 0; }}
    li {{ padding: 0.65rem 0; border-bottom: 1px solid #e5e3de; font-size: 0.95rem; }}
    a {{ color: #1a5c9e; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .page-footer {{ text-align: center; font-size: 0.75rem; color: #b0b0b0; padding: 1.5rem; border-top: 1px solid #e0ded9; }}
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
    force = "--force" in sys.argv
    if force:
        print("  [--force] Skipping cache check — re-running agent.")
    path = generate(force=force)
    print(f"\nDone. Saved to: {path}")
    print(f"Also written to: docs/index.html")
    print(f"Open with: start {path}")
