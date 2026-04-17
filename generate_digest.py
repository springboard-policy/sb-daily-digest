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
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: "Tw Cen MT", "Century Gothic", "Trebuchet MS", sans-serif;
      font-size: 16px;
      line-height: 1.7;
      background: #fff;
      color: #3A3A3D;
    }}

    /* ── SANDWICH TOP: Header ── */
    .page-header {{
      background: #29C3EC;
      color: #fff;
      padding: 1.5rem 2.5rem;
      position: relative;
      overflow: hidden;
      border-bottom: 4px solid #00698C;
    }}

    /* Decorative circles */
    .page-header::before {{
      content: '';
      position: absolute;
      width: 420px;
      height: 420px;
      border-radius: 50%;
      background: rgba(255,255,255,0.10);
      right: -130px;
      top: -140px;
      pointer-events: none;
    }}
    .page-header::after {{
      content: '';
      position: absolute;
      width: 200px;
      height: 200px;
      border-radius: 50%;
      background: rgba(255,255,255,0.07);
      left: -60px;
      bottom: -80px;
      pointer-events: none;
    }}

    /* Decorative vertical bars (bar-chart motif) */
    .hero-bars {{
      position: absolute;
      right: 5%;
      bottom: 0;
      display: flex;
      align-items: flex-end;
      gap: 7px;
      height: 100%;
      opacity: 0.15;
      pointer-events: none;
    }}
    .hero-bars span {{
      width: 13px;
      background: #fff;
      border-radius: 2px 2px 0 0;
      display: block;
    }}

    /* Left/right split layout */
    .header-inner {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: relative;
    }}
    .header-left {{ text-align: left; }}
    .header-right {{ text-align: right; }}

    .page-header .org {{
      font-size: 0.68rem;
      font-weight: 700;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      opacity: 0.85;
      margin-bottom: 0.2rem;
    }}
    .page-header h1 {{
      font-size: 1.6rem;
      font-weight: 700;
      letter-spacing: 0.01em;
    }}
    .page-header .dateline {{
      font-size: 0.9rem;
      opacity: 0.9;
      margin-bottom: 0.3rem;
    }}
    .page-header .archive-link {{
      font-size: 0.75rem;
      opacity: 0.75;
    }}
    .page-header .archive-link a {{
      color: #fff;
      text-decoration: none;
      border-bottom: 1px solid rgba(255,255,255,0.45);
    }}
    .page-header .archive-link a:hover {{ opacity: 1; border-bottom-color: #fff; }}

    /* ── SANDWICH MIDDLE: Content ── */
    .content {{
      max-width: 1050px;
      margin: 2rem auto;
      padding: 0 2.5rem 5rem;
    }}

    /* Section headings — centred per brand guidelines */
    .brief h2 {{
      font-size: 1.1rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: #000;
      margin: 3.5rem 0 0;
      padding-bottom: 0.6rem;
      border-bottom: 3px solid #29C3EC;
      text-align: center;
    }}
    .brief > h2:first-child {{ margin-top: 0.25rem; }}

    .brief hr {{ display: none; }}

    /* Numbered items */
    .brief ol {{
      list-style: none;
      padding: 0;
      margin: 0;
      counter-reset: brief-item;
    }}
    .brief ol > li {{
      counter-increment: brief-item;
      position: relative;
      padding: 1.25rem 0 1.25rem 2.5rem;
      border-bottom: 1px solid #F2F2F2;
    }}
    .brief ol > li::before {{
      content: counter(brief-item);
      position: absolute;
      left: 0;
      top: 1.4rem;
      font-size: 0.72rem;
      font-weight: 700;
      color: #29C3EC;
      width: 1.6rem;
      text-align: right;
    }}
    .brief ol > li p {{
      margin: 0 0 0.5rem;
      font-size: 0.9rem;
      text-align: left;
    }}
    .brief ol > li p:last-child {{ margin-bottom: 0; }}
    .brief ol > li em {{
      font-style: italic;
      color: #5F8699;
      font-size: 0.875rem;
      line-height: 1.65;
    }}

    /* Bullet lists (Sources Consulted) */
    .brief ul {{
      padding-left: 1.27rem;
      margin: 0.6rem 0 0;
      text-align: left;
    }}
    .brief ul li {{
      margin-bottom: 0.4rem;
      font-size: 0.875rem;
      color: #5F8699;
      padding-left: 0.2rem;
    }}

    /* Inline */
    .brief a {{ color: #00698C; text-decoration: none; }}
    .brief a:hover {{ text-decoration: underline; color: #4295AD; }}
    .brief p {{ margin-bottom: 0.5rem; text-align: left; }}
    .brief em {{ color: #5F8699; }}

    /* ── SANDWICH BOTTOM: Dark footer ── */
    .page-footer {{
      background: #00698C;
      color: #fff;
      text-align: center;
      font-size: 0.78rem;
      padding: 1.75rem 1.5rem;
    }}

    @media (max-width: 600px) {{
      .page-header {{ padding: 1.25rem; }}
      .header-inner {{ flex-direction: column; align-items: flex-start; gap: 0.5rem; }}
      .header-right {{ text-align: left; }}
      .hero-bars {{ display: none; }}
      .content {{ padding: 0 1.25rem 3rem; }}
    }}
  </style>
</head>
<body>

<header class="page-header">
  <div class="hero-bars" aria-hidden="true">
    <span style="height:30%"></span>
    <span style="height:60%"></span>
    <span style="height:45%"></span>
    <span style="height:85%"></span>
    <span style="height:55%"></span>
    <span style="height:70%"></span>
    <span style="height:40%"></span>
  </div>
  <div class="header-inner">
    <div class="header-left">
      <div class="org">Springboard</div>
      <h1>Daily Policy Brief</h1>
    </div>
    <div class="header-right">
      <div class="dateline">{date_long}</div>
      <div class="archive-link"><a href="archive.html">Past briefs &rarr;</a></div>
    </div>
  </div>
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

    # The analysis line renders as an indented <em> at the end of the same <p>
    # as the news line. Split it into its own <p> and prepend "Analysis:" label.
    html_body = re.sub(
        r'\n[ \t]+(<em>(?:(?!</em>).)*</em>)(</p>)',
        r'</p>\n<p><strong>Analysis:</strong> \1\2',
        html_body,
        flags=re.DOTALL,
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
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: "Tw Cen MT", "Century Gothic", "Trebuchet MS", sans-serif;
      font-size: 16px;
      line-height: 1.7;
      background: #fff;
      color: #3A3A3D;
    }}
    .page-header {{
      background: #29C3EC;
      color: #fff;
      padding: 3.5rem 2.5rem 3rem;
      text-align: center;
      position: relative;
      overflow: hidden;
      border-bottom: 4px solid #00698C;
    }}
    .page-header::before {{
      content: '';
      position: absolute;
      width: 420px; height: 420px;
      border-radius: 50%;
      background: rgba(255,255,255,0.10);
      right: -130px; top: -110px;
      pointer-events: none;
    }}
    .page-header::after {{
      content: '';
      position: absolute;
      width: 240px; height: 240px;
      border-radius: 50%;
      background: rgba(255,255,255,0.07);
      left: -70px; bottom: -90px;
      pointer-events: none;
    }}
    .hero-bars {{
      position: absolute; right: 5%; bottom: 0;
      display: flex; align-items: flex-end; gap: 7px;
      height: 70%; opacity: 0.18; pointer-events: none;
    }}
    .hero-bars span {{ width: 13px; background: #fff; border-radius: 2px 2px 0 0; display: block; }}
    .header-inner {{ display: flex; justify-content: space-between; align-items: center; position: relative; }}
    .header-left {{ text-align: left; }}
    .header-right {{ text-align: right; }}
    .page-header .org {{ font-size: 0.68rem; font-weight: 700; letter-spacing: 0.2em; text-transform: uppercase; opacity: 0.85; margin-bottom: 0.2rem; }}
    .page-header h1 {{ font-size: 1.6rem; font-weight: 700; }}
    .page-header .sub {{ font-size: 0.75rem; opacity: 0.75; }}
    .page-header .sub a {{ color: #fff; text-decoration: none; border-bottom: 1px solid rgba(255,255,255,0.45); }}
    .page-header .sub a:hover {{ opacity: 1; border-bottom-color: #fff; }}
    .content {{ max-width: 560px; margin: 3rem auto; padding: 0 2rem 5rem; }}
    h2 {{ font-size: 1.1rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.12em;
          color: #000; border-bottom: 3px solid #29C3EC; padding-bottom: 0.6rem; margin-bottom: 1.5rem; text-align: center; }}
    ul {{ list-style: none; padding: 0; }}
    li {{ padding: 0.75rem 0; border-bottom: 1px solid #F2F2F2; font-size: 0.95rem; }}
    a {{ color: #00698C; text-decoration: none; }}
    a:hover {{ text-decoration: underline; color: #4295AD; }}
    .page-footer {{ background: #00698C; color: #fff; text-align: center; font-size: 0.78rem; padding: 1.75rem 1.5rem; }}
    @media (max-width: 600px) {{
      .page-header {{ padding: 1.25rem; }}
      .header-inner {{ flex-direction: column; align-items: flex-start; gap: 0.5rem; }}
      .header-right {{ text-align: left; }}
      .hero-bars {{ display: none; }}
    }}
  </style>
</head>
<body>
<header class="page-header">
  <div class="hero-bars" aria-hidden="true">
    <span style="height:30%"></span>
    <span style="height:60%"></span>
    <span style="height:45%"></span>
    <span style="height:85%"></span>
    <span style="height:55%"></span>
    <span style="height:70%"></span>
    <span style="height:40%"></span>
  </div>
  <div class="header-inner">
    <div class="header-left">
      <div class="org">Springboard</div>
      <h1>Daily Policy Brief</h1>
    </div>
    <div class="header-right">
      <div class="sub"><a href="index.html">&larr; Today's brief</a></div>
    </div>
  </div>
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
