"""
Test the briefing prompt against saved article fixtures.

Replays the sources fetched during a past real run so Claude writes a fresh
brief using the same articles — no HTTP source-fetching, just Claude API calls.
Useful for iterating on the system prompt without waiting for a live run.

Usage:
    python test_prompt.py                            # uses fixtures/latest.json
    python test_prompt.py fixtures/2026-04-14.json  # specific date

Output is saved to test_YYYY-MM-DD_HHMMSS.md and printed to the terminal.
Compare it against the corresponding brief_YYYY-MM-DD.md to judge the change.
"""

import sys
from datetime import datetime
from pathlib import Path

from agent import run_briefing

fixtures_path = sys.argv[1] if len(sys.argv) > 1 else "fixtures/latest.json"

if not Path(fixtures_path).exists():
    print(f"No fixture file found at {fixtures_path}")
    print("Run the daily brief once to generate fixtures automatically.")
    sys.exit(1)

print(f"\nPrompt test — replaying {fixtures_path}")
print("=" * 60)

briefing = run_briefing(fixtures_path=fixtures_path)

ts       = datetime.now().strftime("%Y-%m-%d_%H%M%S")
out_path = f"test_{ts}.md"
Path(out_path).write_text(briefing, encoding="utf-8")

print(f"\nSaved to: {out_path}")
print("Compare: brief_YYYY-MM-DD.md  (the real run for the same fixtures)")
print("\n" + "=" * 60)
print(briefing[:3000])
if len(briefing) > 3000:
    print(f"\n... ({len(briefing) - 3000} more characters — see {out_path})")
