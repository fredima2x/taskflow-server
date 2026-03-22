"""
TaskFlow Plugin — Annual Report
PLUGIN_NAME    = "Annual Report"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Generate a full-year statistics report as Markdown or HTML"
PLUGIN_AUTHOR  = "community"
PLUGIN_TAGS    = "report, statistics, export, yearly"
PLUGIN_MIN_API = "3.0"
"""
PLUGIN_NAME    = "Annual Report"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Personal yearly report — Markdown & HTML"
PLUGIN_MIN_API = "3.0"

import os
from datetime import datetime, date, timedelta
from collections import Counter, defaultdict
from pathlib import Path


def _build_report(tasks: list, year: int) -> tuple[str, str]:
    """Returns (markdown_str, html_str)."""

    # ── Data ─────────────────────────────────────────────────
    year_tasks = [t for t in tasks
                  if t.get("created_at","")[:4] == str(year)]
    done       = [t for t in year_tasks if t.get("status") == "done"]
    todo       = [t for t in year_tasks if t.get("status") in ("todo","in_progress")]

    # Monthly completion counts
    monthly = defaultdict(int)
    for t in done:
        ca = t.get("completed_at","")
        if ca[:4] == str(year):
            monthly[int(ca[5:7])] += 1

    # Category breakdown
    cat_all  = Counter(t.get("category","Other") for t in year_tasks)
    cat_done = Counter(t.get("category","Other") for t in done)

    # Weekday productivity
    weekday_done = Counter()
    for t in done:
        ca = t.get("completed_at","")
        if ca:
            try: weekday_done[datetime.fromisoformat(ca).weekday()] += 1
            except Exception: pass

    # Avg completion time
    times = []
    for t in done:
        try:
            c = datetime.fromisoformat(t["created_at"])
            d = datetime.fromisoformat(t["completed_at"])
            times.append((d-c).total_seconds()/3600)
        except Exception: pass
    avg_h = sum(times)/len(times) if times else 0

    total    = len(year_tasks)
    rate     = int(len(done)/total*100) if total else 0
    streak   = _max_streak(done, year)
    best_cat = cat_done.most_common(1)[0][0] if cat_done else "—"
    days     = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    best_day = days[weekday_done.most_common(1)[0][0]] if weekday_done else "—"

    # ── Markdown ─────────────────────────────────────────────
    md = f"# TaskFlow — Personal Report {year}\n\n"
    md += f"*Generated: {date.today()}*\n\n"
    md += "## Summary\n\n"
    md += f"| Metric | Value |\n|---|---|\n"
    md += f"| Tasks created | {total} |\n"
    md += f"| Tasks completed | {len(done)} |\n"
    md += f"| Completion rate | {rate}% |\n"
    md += f"| Avg time to complete | {avg_h:.1f} h |\n"
    md += f"| Longest streak | {streak} days |\n"
    md += f"| Most productive category | {best_cat} |\n"
    md += f"| Most productive day | {best_day} |\n\n"

    md += "## Monthly Completions\n\n"
    month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    max_m = max(monthly.values()) if monthly else 1
    for m in range(1, 13):
        n   = monthly.get(m, 0)
        bar = "█" * int(n/max_m*20) + "░" * (20 - int(n/max_m*20))
        md += f"`{month_names[m-1]}` `{bar}` {n}\n"
    md += "\n"

    md += "## Category Breakdown\n\n"
    md += "| Category | Created | Done | Rate |\n|---|---|---|---|\n"
    for cat, n in cat_all.most_common():
        d    = cat_done.get(cat, 0)
        r    = int(d/n*100) if n else 0
        md  += f"| {cat} | {n} | {d} | {r}% |\n"
    md += "\n"

    md += "## Top Completed Tasks\n\n"
    for t in done[-10:]:
        md += f"- ✅ {t['name'][:60]}"
        if t.get("priority") in ("Critical","High"):
            md += f" *({t['priority']})*"
        md += "\n"

    # ── HTML ─────────────────────────────────────────────────
    bar_rows = ""
    for m in range(1, 13):
        n     = monthly.get(m, 0)
        pct   = int(n/max(max_m,1)*100)
        bar_rows += f"""
        <div style="display:flex;align-items:center;gap:8px;margin:4px 0">
          <span style="width:32px;color:#888;font-size:12px">{month_names[m-1]}</span>
          <div style="background:#00b4d8;height:18px;width:{pct*2}px;border-radius:3px;min-width:2px"></div>
          <span style="color:#888;font-size:12px">{n}</span>
        </div>"""

    cat_rows = ""
    for cat, n in cat_all.most_common():
        d   = cat_done.get(cat, 0)
        r   = int(d/n*100) if n else 0
        cat_rows += f"""
        <tr>
          <td style="padding:6px 12px">{cat}</td>
          <td style="padding:6px 12px;text-align:right">{n}</td>
          <td style="padding:6px 12px;text-align:right">{d}</td>
          <td style="padding:6px 12px">
            <div style="background:#00b4d8;height:12px;width:{r}%;border-radius:2px;min-width:2px"></div>
          </td>
          <td style="padding:6px 12px;color:#888">{r}%</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>TaskFlow Report {year}</title>
<style>
  body{{font-family:sans-serif;max-width:800px;margin:0 auto;padding:32px;background:#0b0b18;color:#ddeeff}}
  h1{{color:#00e5ff;border-bottom:2px solid #00b4d8;padding-bottom:8px}}
  h2{{color:#00b4d8;margin-top:32px}}
  .cards{{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}}
  .card{{background:#111828;border:1px solid #1a2a44;border-radius:8px;padding:16px 24px;text-align:center;min-width:120px}}
  .val{{font-size:28px;font-weight:bold;color:#00e5ff}}
  .lbl{{color:#556688;font-size:12px;margin-top:4px}}
  table{{width:100%;border-collapse:collapse;background:#111828;border:1px solid #1a2a44;border-radius:8px;overflow:hidden}}
  th{{background:#0f1635;color:#00b4d8;padding:10px 12px;text-align:left;font-size:12px}}
  td{{border-bottom:1px solid #1a2a44}}
  p{{color:#556688;font-size:12px}}
</style></head><body>
<h1>⚡ TaskFlow — Personal Report {year}</h1>
<p>Generated: {date.today()}</p>
<div class="cards">
  <div class="card"><div class="val">{total}</div><div class="lbl">Created</div></div>
  <div class="card"><div class="val">{len(done)}</div><div class="lbl">Completed</div></div>
  <div class="card"><div class="val">{rate}%</div><div class="lbl">Rate</div></div>
  <div class="card"><div class="val">{avg_h:.1f}h</div><div class="lbl">Avg time</div></div>
  <div class="card"><div class="val">{streak}d</div><div class="lbl">Best streak</div></div>
  <div class="card"><div class="val">{best_day}</div><div class="lbl">Best day</div></div>
</div>
<h2>Monthly Completions</h2>
{bar_rows}
<h2>Category Breakdown</h2>
<table><thead><tr><th>Category</th><th>Created</th><th>Done</th><th>Rate</th><th>%</th></tr></thead>
<tbody>{cat_rows}</tbody></table>
</body></html>"""

    return md, html


def _max_streak(done: list, year: int) -> int:
    dates = set()
    for t in done:
        ca = t.get("completed_at","")
        if ca[:4] == str(year):
            try: dates.add(datetime.fromisoformat(ca).date())
            except Exception: pass
    max_s = 0; s = 0
    d = date(year, 1, 1)
    while d <= date(year, 12, 31):
        if d in dates: s += 1; max_s = max(max_s, s)
        else: s = 0
        d += timedelta(days=1)
    return max_s


def _screen(api):
    os.system("clear")
    api.console.print("\n  [bold]⚡ TaskFlow  ·  📈 Annual Report[/]\n")

    years = sorted({t.get("created_at","")[:4] for t in api.tasks
                    if t.get("created_at","")[:4].isdigit()}, reverse=True)
    if not years:
        api.console.print("  [dim]No task data yet.[/]"); api.press_enter(); return

    for i, y in enumerate(years, 1):
        api.console.print(f"  [dim]{i}.[/]  {y}")
    raw = api.prompt("Generate report for year", default=years[0])
    try:
        year = int(raw) if raw.isdigit() else int(years[0])
    except Exception:
        year = int(years[0])

    api.console.print(f"  [dim]Generating {year} report…[/]")
    md, html = _build_report(api.tasks, year)

    out_dir = api.data_dir / "reports"
    out_dir.mkdir(exist_ok=True)
    md_path   = out_dir / f"report_{year}.md"
    html_path = out_dir / f"report_{year}.html"
    md_path.write_text(md,   encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")

    api.console.print(f"\n  [green]✓ Report saved:[/]")
    api.console.print(f"  [dim]Markdown:[/] {md_path}")
    api.console.print(f"  [dim]HTML:    [/] {html_path}")

    if api.confirm("\n  Open HTML in browser?", default=False):
        import subprocess
        try:
            subprocess.Popen(["xdg-open", str(html_path)])
        except Exception:
            api.console.print(f"  Open: file://{html_path}")

    api.press_enter()


def on_startup(api): pass


def menu_items(api):
    return [("Y", "📈 Annual Report", lambda: _screen(api))]
