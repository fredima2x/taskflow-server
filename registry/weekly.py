"""
TaskFlow Plugin — Weekly Planner
Drop into ~/.taskflow/plugins/weekly.py
"""
PLUGIN_NAME    = "Weekly Planner"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Mon–Sun overview with task assignment and load view"

from datetime import datetime, timedelta, date

DAY_NAMES = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
DAY_FULL  = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _weekly_screen(api):
    from rich.prompt import Prompt
    from rich.table import Table
    from rich.panel import Panel
    from rich.text  import Text
    from rich       import box as rbox
    from rich.rule  import Rule

    console = api.console
    offset  = 0   # week offset from today

    PRIO_ICON = {5:"🔴", 4:"🟠", 3:"🟡", 2:"🟢", 1:"⚪"}

    def _cls():
        import os; os.system("clear")

    while True:
        _cls()
        console.print()
        console.print("  [bold #00e5ff]⚡ TaskFlow  ·  📅 Weekly Planner[/]")
        console.print()

        today = date.today()
        ws    = _week_start(today) + timedelta(weeks=offset)
        we    = ws + timedelta(days=6)

        week_label = (f"{ws:%d %b} – {we:%d %b %Y}"
                      + (" [bold #00e5ff](this week)[/]" if offset == 0 else ""))
        console.print(Panel(
            f"  {week_label}",
            border_style="#1a2a44", padding=(0,0)
        ))
        console.print()

        # Build per-day task lists
        days_tasks = {i: [] for i in range(7)}
        unscheduled = []

        for task in api.tasks:
            if task.get("status") in ("done","cancelled"):
                continue
            due = task.get("due_date","")
            if not due:
                unscheduled.append(task)
                continue
            try:
                d = datetime.fromisoformat(due).date()
                delta = (d - ws).days
                if 0 <= delta <= 6:
                    days_tasks[delta].append(task)
                elif d < ws:
                    days_tasks[0].append(task)  # overdue → Monday
            except Exception:
                unscheduled.append(task)

        # Render calendar grid
        tbl = Table(box=rbox.ROUNDED, border_style="#1a2a44",
                    header_style="bold #00b4d8", padding=(0,1),
                    show_lines=True)
        for i, day in enumerate(DAY_NAMES):
            d     = ws + timedelta(days=i)
            is_td = (d == today)
            hdr   = f"[bold #00e5ff]{day} {d.day}[/]" if is_td else f"{day} {d.day}"
            tbl.add_column(hdr, min_width=18)

        # Find max tasks in any day
        max_rows = max((len(v) for v in days_tasks.values()), default=0)
        max_rows = max(max_rows, 3)

        for row_i in range(max_rows):
            cells = []
            for col_i in range(7):
                tasks_day = days_tasks[col_i]
                if row_i < len(tasks_day):
                    t    = tasks_day[row_i]
                    ps   = t.get("priority_score", 3)
                    icon = PRIO_ICON.get(ps, "🟡")
                    name = t["name"][:16]
                    d    = ws + timedelta(days=col_i)
                    # mark overdue
                    if t.get("due_date"):
                        try:
                            td = datetime.fromisoformat(t["due_date"]).date()
                            if td < today and t.get("status") != "done":
                                name = f"[red]{name}[/]"
                        except Exception:
                            pass
                    cells.append(f"{icon} {name}")
                else:
                    cells.append("")
            tbl.add_row(*cells)

        console.print(tbl)

        # Unscheduled
        if unscheduled:
            names = "  ".join(f"[dim]{t['name'][:20]}[/]" for t in unscheduled[:5])
            extra = f"  [dim]+{len(unscheduled)-5} more[/]" if len(unscheduled) > 5 else ""
            console.print(Panel(
                f"  {names}{extra}",
                title="[dim]📌 Unscheduled[/]", border_style="#1a2a44", padding=(0,0)
            ))

        # Workload bar
        console.print()
        console.print("  [dim]Workload:[/]")
        for i, day in enumerate(DAY_NAMES):
            n    = len(days_tasks[i])
            bar  = "█" * n + "░" * max(0, 8 - n)
            d    = ws + timedelta(days=i)
            mark = " [bold #00e5ff]◀ today[/]" if d == today else ""
            console.print(f"  [dim]{day}[/]  [#00b4d8]{bar}[/]  {n}{mark}")

        console.print()
        console.print(Rule("[dim]Navigation[/]", style="#1a2a44"))
        console.print(
            "  [bold #00b4d8]←[/] / [bold #00b4d8]h[/]  prev week   "
            "  [bold #00b4d8]→[/] / [bold #00b4d8]l[/]  next week   "
            "  [bold #00b4d8]t[/]  this week   "
            "  [bold #00b4d8]b[/]  back"
        )
        console.print()
        ch = Prompt.ask("  [#00b4d8]>[/]").strip().lower()

        if   ch in ("b","q"):        return
        elif ch in ("h","left","<"): offset -= 1
        elif ch in ("l","right",">"): offset += 1
        elif ch == "t":               offset = 0


def menu_items(api):
    return [("w", "📅 Weekly planner", lambda: _weekly_screen(api))]
