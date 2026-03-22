"""
TaskFlow Plugin — Mood Heatmap
PLUGIN_NAME    = "Mood Heatmap"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "GitHub-style yearly mood + productivity heatmap in the terminal"
PLUGIN_AUTHOR  = "community"
PLUGIN_TAGS    = "mood, heatmap, visualization"
PLUGIN_MIN_API = "3.0"
"""
PLUGIN_NAME    = "Mood Heatmap"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Yearly mood and productivity heatmap"
PLUGIN_MIN_API = "3.0"

import os
from datetime import date, timedelta
from collections import defaultdict
from rich.panel import Panel

MOOD_SCORE = {
    "😄 Great":   5, "🙂 Good":  4, "😐 Okay": 3,
    "😔 Low":     2, "😤 Stressed": 1,
}
MOOD_LIST = list(MOOD_SCORE.keys())

# Heat chars and colors (dark→bright)
HEAT_CHARS  = ["░","▒","▓","█"]
HEAT_COLORS = ["#2d333b","#0e4429","#006d32","#26a641","#39d353"]


def _color_for(value: float, max_val: float) -> str:
    if max_val == 0 or value == 0: return HEAT_COLORS[0]
    idx = min(4, 1 + int(value / max_val * 3.99))
    return HEAT_COLORS[idx]


def _screen(api):
    os.system("clear")
    api.console.print("\n  [bold]⚡ TaskFlow  ·  🌡️ Mood Heatmap[/]\n")

    # Load journal moods
    journal_store = {}
    try:
        journal_api = api.get_plugin("Journal")
        if journal_api:
            journal_store = api.store  # won't work cross-plugin easily
    except Exception:
        pass

    # Try to load journal data directly from file
    from pathlib import Path
    journal_path = api.data_dir / "plugin_data" / "journal.json"
    mood_by_day  = {}
    if journal_path.exists():
        import json
        try:
            j = json.loads(journal_path.read_text())
            for d, entry in j.get("entries", {}).items():
                mood_str = entry.get("mood","")
                if mood_str in MOOD_SCORE:
                    mood_by_day[d] = MOOD_SCORE[mood_str]
        except Exception:
            pass

    # Completion count by day
    done_by_day: dict = defaultdict(int)
    for t in api.tasks:
        ca = t.get("completed_at","")
        if ca:
            done_by_day[ca[:10]] += 1

    # Build 52-week grid
    today  = date.today()
    start  = today - timedelta(weeks=52)
    # Align to Monday
    start -= timedelta(days=start.weekday())

    max_done = max(done_by_day.values()) if done_by_day else 1
    max_mood = 5

    day_names = ["Mon","   ","Wed","   ","Fri","   ","Sun"]
    weeks     = 52

    console = api.console

    # ── Productivity heatmap ──────────────────────────────────
    console.print(Panel(
        "  Tasks completed per day — darker = more done",
        border_style="#1a2a44", padding=(0,0)
    ))
    console.print()
    console.print("       " + "".join(
        f"[dim]{(start+timedelta(weeks=w)).strftime('%b'):<4}[/]"
        if (start+timedelta(weeks=w)).day <= 7 else "    "
        for w in range(0, weeks, 2)
    ))

    for dow in range(7):
        row = f"  [dim]{day_names[dow]}[/] "
        for w in range(weeks):
            d   = start + timedelta(weeks=w, days=dow)
            iso = d.isoformat()
            n   = done_by_day.get(iso, 0)
            clr = _color_for(n, max_done)
            ch  = HEAT_CHARS[min(3, int(n/max(max_done,1)*3.99))] if n else "·"
            if d == today:
                row += f"[bold white]{ch}[/]"
            else:
                row += f"[{clr}]{ch}[/]"
        console.print(row)

    console.print()
    done_total = sum(done_by_day.values())
    console.print(f"  [dim]Total completions in 52 weeks: [bold]{done_total}[/][/]")
    console.print()

    # ── Mood heatmap ─────────────────────────────────────────
    if mood_by_day:
        console.print(Panel(
            "  Mood per day (from Journal) — darker = better mood",
            border_style="#1a2a44", padding=(0,0)
        ))
        console.print()
        for dow in range(7):
            row = f"  [dim]{day_names[dow]}[/] "
            for w in range(weeks):
                d   = start + timedelta(weeks=w, days=dow)
                iso = d.isoformat()
                mood = mood_by_day.get(iso, 0)
                clr  = _color_for(mood, max_mood)
                ch   = HEAT_CHARS[min(3, int(mood/max_mood*3.99))] if mood else "·"
                row += f"[{clr}]{ch}[/]"
            console.print(row)

        avg = sum(mood_by_day.values())/len(mood_by_day)
        best_day = max(mood_by_day, key=mood_by_day.get)
        console.print(f"\n  [dim]Average mood: [bold]{avg:.1f}/5[/]  ·  Best day: [bold]{best_day}[/][/]")
    else:
        console.print(Panel(
            "  [dim]No mood data yet — install the [bold]Journal[/] plugin\n"
            "  and log entries with mood to see mood heatmap.[/]",
            border_style="#1a2a44", padding=(0,1)
        ))

    console.print()

    # ── Streak ───────────────────────────────────────────────
    streak = 0
    check  = today
    while done_by_day.get(check.isoformat(), 0) > 0:
        streak += 1; check -= timedelta(days=1)

    console.print(f"  🔥 Current streak: [bold cyan]{streak}[/] day(s) with completed tasks")
    api.press_enter()


def on_startup(api): pass


def menu_items(api):
    return [("M", "🌡️ Mood Heatmap", lambda: _screen(api))]
