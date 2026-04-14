# Springboard Daily Digest — Project Context

## What this is
An AI-powered daily policy briefing tool for Springboard (a Canadian public policy consulting firm). Each weekday at 10 AM EST, a Claude agent searches ~40 policy sources and produces a concise briefing note covering three topic areas.

## Status
**Code is complete. Pending: API key setup.**

## What's built
- `agent.py` — Claude agent with tool use (search_source + fetch_article tools)
- `tools.py` — tool implementations: RSS fetching, page scraping, full article fetching
- `generate_digest.py` — orchestrates agent, converts markdown → HTML, saves to docs/index.html
- `sources.py` — ~75 sources with RSS URLs and paywalled flags (Globe, iPolitics, Hill Times)
- `fetch_hoc.py` / `fetch_senate.py` — HoC and Senate committee scrapers
- `.github/workflows/daily_digest.yml` — runs weekdays at 15:00 UTC (10 AM EST)
- `run_digest.bat` — local runner (activates venv, runs generate_digest.py)
- `venv/` — Python venv with all dependencies installed

## Output format
One HTML briefing note per day covering:
1. Northern & Arctic Infrastructure — Top Takeaways + What to Watch
2. Skills Policy & Workforce Development — Top Takeaways + What to Watch
3. Social Assistance & Income Security — Top Takeaways + What to Watch
4. Client Mentions (NTI, Prosper Canada, FSC, ITK, Century Initiative, etc.)
5. Sources Consulted (with [PAYWALLED] flags)

## What still needs to be done
1. **Get an Anthropic API key** — go to console.anthropic.com (use work email)
2. **Create `.env` file** — add `ANTHROPIC_API_KEY=sk-ant-...` to project root
3. **Add GitHub Actions secret** — go to github.com/khiran-oneill/sb-daily-digest → Settings → Secrets and variables → Actions → New repository secret → Name: `ANTHROPIC_API_KEY`
4. **Push code to GitHub** — not yet committed/pushed

## Related project
`C:\Users\khira\policy-monitoring` — the original RSS card-based digest (already running on GitHub Actions). Different tool: shows all matching articles as cards rather than synthesizing into a brief.

## Key files / paths
- Project: `C:\Users\khira\sb-daily-digest`
- GitHub: `https://github.com/khiran-oneill/sb-daily-digest`
- Keywords/sources spreadsheet: `G:\.shortcut-targets-by-id\1SDcA6RUAjb629Bh027FAHeE92BC6xwuY\Non-Client Projects\General policy monitoring\AI policy monitoring\2026.03.05 policy monitoring worksheet.xlsx`

## Architecture decisions made
- Agent approach (not card-based) — Claude searches and synthesizes, not keyword matching
- One combined brief covering all topic areas per run (not separate briefs per topic)
- Sources searched sequentially by topic group: Northern Infrastructure → Skills Policy → Social Assistance → General
- Paywalled sources flagged in output (Globe & Mail, iPolitics, Hill Times)
- Falls back gracefully if a source times out or has no recent content
