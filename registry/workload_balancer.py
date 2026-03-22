"""
TaskFlow Plugin — Workload Balancer
PLUGIN_NAME    = "Workload Balancer"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Analyze and rebalance task due dates across the week"
PLUGIN_AUTHOR  = "community"
PLUGIN_TAGS    = "balance, workload, scheduling, planning"
PLUGIN_MIN_API = "3.0"
"""
PLUGIN_NAME    = "Workload Balancer"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Spread tasks fairly across the week"
PLUGIN_MIN_API = "3.0"

import os
from datetime import date, timedelta
from collections import defaultdict
from rich.panel  import Panel
from rich.table  import Table
from rich.prompt import Confirm
from rich        import box as rbox


DAY_NAMES = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
WORK_DAYS  = [0,1,2,3,4]   # Mon–Fri by default


def _workload_by_day(tasks: list, from_date: date, days: int = 14) -> dict:
    """Returns {date_iso: [task, ...]} for next N days."""
    buckets: dict = defaultdict(list)
    end = from_date + timedelta(days=days)
    for t in tasks:
        if t.get("status") not in ("todo","in_progress"): continue
        due = t.get("due_date","")
        if due and from_date.isoformat() <= due < end.isoformat():
            buckets[due].append(t)
    return buckets


def _suggest_rebalance(buckets: dict, work_days_only: bool,
                       from_date: date, days: int = 14) -> list[tuple]:
    """
    Returns list of (task, old_due, new_due) suggestions.
    Tries to move tasks from overloaded days to lighter days.
    """
    # Build available days
    available = []
    for i in range(days):
        d = from_date + timedelta(days=i)
        if not work_days_only or d.weekday() in WORK_DAYS:
            available.append(d.isoformat())

    if not available: return []

    # Count load per day
    load = {d: len(buckets.get(d,[])) for d in available}
    avg  = sum(load.values()) / max(len(load),1)

    suggestions = []
    # Find overloaded days (>avg+1) and move tasks to lightest days
    for day in sorted(available, key=lambda d: -load.get(d,0)):
        if load.get(day,0) <= avg + 1: break
        tasks_here = list(buckets.get(day,[]))
        # Sort by priority — move lower priority tasks first
        tasks_here.sort(key=lambda t: t.get("priority_score",3))
        excess = load[day] - int(avg) - 1
        for t in tasks_here[:excess]:
            # Find lightest day after current
            light = min((d for d in available if d > day),
                       key=lambda d: load.get(d,0), default=None)
            if light and light != day:
                suggestions.append((t, day, light))
                load[day]   -= 1
                load[light] += 1

    return suggestions


def _screen(api):
    store         = api.store
    work_days_only = store.get("work_days_only", True)

    while True:
        os.system("clear")
        api.console.print("\n  [bold]⚡ TaskFlow  ·  ⚖️ Workload Balancer[/]\n")

        today   = date.today()
        active  = [t for t in api.tasks if t.get("status") in ("todo","in_progress")]
        buckets = _workload_by_day(active, today, days=14)

        # Current load visualization
        api.console.print(Panel(
            f"  Work days only: {'[green]yes[/]' if work_days_only else '[yellow]no (incl. weekends)[/]'}\n"
            "  [dim]Showing next 14 days[/]",
            border_style="#1a2a44", padding=(0,0)
        ))
        api.console.print()

        # Show current load bar chart
        max_load = max((len(v) for v in buckets.values()), default=1)
        api.console.print("  [dim]Current load:[/]")
        for i in range(14):
            d    = today + timedelta(days=i)
            iso  = d.isoformat()
            n    = len(buckets.get(iso,[]))
            bar  = "█" * n + "░" * max(0, 8-n)
            wd   = DAY_NAMES[d.weekday()]
            ovld = "[red]" if n > 3 else "[cyan]"
            wknd = "[dim]" if d.weekday() >= 5 else ""
            api.console.print(
                f"  {wknd}[dim]{wd} {d.strftime('%d/%m')}[/]{wknd}  "
                f"{ovld}{bar}[/]  [dim]{n}[/]"
            )

        # Unscheduled count
        unscheduled = [t for t in active if not t.get("due_date")]
        if unscheduled:
            api.console.print(f"\n  [dim]{len(unscheduled)} task(s) have no due date[/]")

        api.console.print()
        api.rule("Actions")
        api.console.print("  [bold]s[/]  Suggest rebalancing")
        api.console.print("  [bold]a[/]  Auto-assign unscheduled tasks")
        api.console.print("  [bold]w[/]  Toggle work days only")
        api.console.print("  [bold]b[/]  Back\n")

        ch = api.prompt(">").lower()
        if ch == "b": return

        elif ch == "w":
            store["work_days_only"] = not work_days_only
            api.store_save()
            work_days_only = store["work_days_only"]

        elif ch == "s":
            suggestions = _suggest_rebalance(buckets, work_days_only, today)
            if not suggestions:
                api.console.print("  [green]✓ Workload looks balanced — no changes needed![/]")
                api.press_enter(); continue

            os.system("clear")
            api.console.print("\n  [bold]Suggested Changes[/]\n")
            tbl = api.table("Proposed Rebalancing")
            tbl.add_column("#",      width=3, justify="right", style="dim")
            tbl.add_column("Task",   min_width=28)
            tbl.add_column("From",   width=12)
            tbl.add_column("→ To",   width=12)
            tbl.add_column("Priority", width=10)
            for i, (t, old, new) in enumerate(suggestions, 1):
                tbl.add_row(str(i), t["name"][:28], old, new,
                            t.get("priority","Medium"))
            api.console.print(tbl)
            api.console.print()

            if Confirm.ask("  Apply all suggestions?", default=False):
                for t, old, new in suggestions:
                    api.update_task(t["id"], due_date=new)
                api.console.print(f"  [green]✓ {len(suggestions)} task(s) rescheduled.[/]")
            else:
                # Apply selectively
                raw = api.prompt("Apply which? (numbers e.g. 1 3 5, or Enter to skip)")
                for p in raw.split():
                    try:
                        task, old, new = suggestions[int(p)-1]
                        api.update_task(task["id"], due_date=new)
                        api.console.print(f"  [green]✓ Moved '{task['name'][:30]}' → {new}[/]")
                    except Exception: pass
            api.press_enter()

        elif ch == "a" and unscheduled:
            os.system("clear")
            api.console.print(f"\n  [bold]Auto-assign {len(unscheduled)} unscheduled tasks[/]\n")
            api.console.print("  [dim]Tasks will be spread across the next 7 working days by priority.[/]\n")

            if not Confirm.ask("  Proceed?", default=True):
                continue

            # Sort by priority desc
            unscheduled.sort(key=lambda t: -t.get("priority_score",3))
            avail = []
            d = today
            while len(avail) < 7:
                if not work_days_only or d.weekday() in WORK_DAYS:
                    avail.append(d)
                d += timedelta(days=1)

            # Round-robin assign
            for i, t in enumerate(unscheduled):
                new_due = avail[i % len(avail)].isoformat()
                api.update_task(t["id"], due_date=new_due)

            api.console.print(f"  [green]✓ Assigned {len(unscheduled)} task(s).[/]")
            api.press_enter()


def on_startup(api):
    def widget(api):
        today   = date.today()
        active  = [t for t in api.tasks if t.get("status") in ("todo","in_progress")]
        buckets = _workload_by_day(active, today, days=7)
        heavy   = [iso for iso, tasks in buckets.items() if len(tasks) >= 4]
        if heavy:
            return f"  ⚖️ [yellow]{len(heavy)} day(s) with heavy load this week[/]"
        return ""
    api.register_dashboard_widget(widget)


def menu_items(api):
    return [("U", "⚖️ Workload Balancer", lambda: _screen(api))]
