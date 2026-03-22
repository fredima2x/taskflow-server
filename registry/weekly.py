"""
TaskFlow Plugin — Weekly Planner v2
PLUGIN_NAME    = "Weekly Planner"
PLUGIN_VERSION = "2.0"
PLUGIN_DESC    = "Mon–Sun overview with dependency graph and load view"
PLUGIN_AUTHOR  = "community"
PLUGIN_TAGS    = "weekly, planner, dependencies, visualization"
PLUGIN_MIN_API = "3.0"
"""
PLUGIN_NAME    = "Weekly Planner"
PLUGIN_VERSION = "2.0"
PLUGIN_DESC    = "Weekly calendar with dependency graph visualization"
PLUGIN_MIN_API = "3.0"

import os
from datetime import datetime, timedelta, date
from collections import defaultdict

DAY_NAMES = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
PRIO_ICON  = {5:"🔴", 4:"🟠", 3:"🟡", 2:"🟢", 1:"⚪"}


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _load_deps(api) -> dict:
    """Load dependency map from dependencies plugin store if available."""
    store_path = api.data_dir / "plugin_data" / "dependencies.json"
    if store_path.exists():
        import json
        try:
            return json.loads(store_path.read_text()).get("deps", {})
        except Exception:
            pass
    return {}


def _is_blocked(task_id: str, deps: dict, tasks: list) -> list:
    task_map = {t["id"]: t for t in tasks}
    return [
        task_map[d]["name"]
        for d in deps.get(task_id, [])
        if d in task_map and task_map[d].get("status") != "done"
    ]


def _draw_dep_graph(api, tasks: list, deps: dict):
    """
    ASCII dependency graph in the terminal.
    Shows chains: A → B → C with status indicators.
    """
    console = api.console
    task_map = {t["id"]: t for t in tasks}

    # Find root tasks (not blocked by anyone)
    all_dep_ids = {d for dep_list in deps.values() for d in dep_list}
    roots = [t for t in tasks
             if t["status"] in ("todo","in_progress")
             and t["id"] not in all_dep_ids
             and t["id"] in deps]

    if not roots:
        # Show all tasks that have deps or are depended on
        all_involved = set(deps.keys()) | all_dep_ids
        roots = [t for t in tasks if t["id"] in all_involved]

    if not roots:
        console.print(Panel(
            "  No dependency chains defined.\n"
            "  [dim]Install the Dependencies plugin and link tasks.[/]",
            border_style="#1a2a44", padding=(0,1)
        ))
        return

    STATUS_ICON = {"todo":"○","in_progress":"◐","done":"●","cancelled":"✗"}
    STATUS_CLR  = {"todo":"cyan","in_progress":"yellow","done":"green","cancelled":"dim"}
    rendered    = set()

    def _render_chain(task, indent=0, prefix=""):
        if task["id"] in rendered:
            console.print(f"  {'  '*indent}{prefix}[dim](→ {task['name'][:25]})[/]")
            return
        rendered.add(task["id"])

        st   = task.get("status","todo")
        clr  = STATUS_CLR.get(st,"white")
        icon = STATUS_ICON.get(st,"○")
        ps   = task.get("priority_score",3)
        pico = PRIO_ICON.get(ps,"🟡")

        blocking = _is_blocked(task["id"], deps, tasks)
        blk_mark = " [red](blocked)[/]" if blocking else ""

        # Draw the task line
        connector = prefix
        console.print(
            f"  {'  '*indent}{connector}[{clr}]{icon}[/] {pico} "
            f"[bold]{task['name'][:40]}[/]"
            f"  [dim]{task.get('due_date','') or ''}[/]"
            f"{blk_mark}"
        )

        # Draw children (tasks that REQUIRE this task)
        children = [t for t in tasks
                    if task["id"] in deps.get(t["id"], [])
                    and t["status"] not in ("cancelled",)]
        for j, child in enumerate(children):
            is_last = (j == len(children) - 1)
            branch  = "└─ " if is_last else "├─ "
            _render_chain(child, indent + 1, branch)

    console.print(Panel(
        "[bold]Dependency Graph[/]  [dim]○=todo  ◐=in progress  ●=done[/]",
        border_style="#1a2a44", padding=(0,0)
    ))
    console.print()

    shown_roots = set()
    for task in roots:
        if task["id"] not in shown_roots:
            shown_roots.add(task["id"])
            _render_chain(task)
            console.print()

    # Also show unconnected blocked tasks
    extra_blocked = [
        t for t in tasks
        if t["status"] in ("todo","in_progress")
        and _is_blocked(t["id"], deps, tasks)
        and t["id"] not in rendered
    ]
    if extra_blocked:
        console.print("[dim]  Additional blocked tasks:[/]")
        for t in extra_blocked:
            blocking = _is_blocked(t["id"], deps, tasks)
            console.print(f"  [red]✗[/] [bold]{t['name'][:40]}[/]  "
                          f"[dim]← waiting for: {', '.join(blocking[:2])}[/]")


def _weekly_screen(api):
    from rich.prompt import Prompt
    from rich.table  import Table
    from rich.panel  import Panel
    from rich.text   import Text
    from rich        import box as rbox
    from rich.rule   import Rule

    console = api.console
    offset  = 0
    view    = "week"   # "week" | "deps"

    while True:
        os.system("clear")
        console.print()
        console.print("  [bold]⚡ TaskFlow  ·  📅 Weekly Planner v2[/]")
        console.print()

        today  = date.today()
        ws     = _week_start(today) + timedelta(weeks=offset)
        we     = ws + timedelta(days=6)
        deps   = _load_deps(api)
        tasks  = api.tasks

        # ── Dependency Graph view ─────────────────────────────────────────────
        if view == "deps":
            console.print(Panel(
                f"  Dependency chains as of {today}",
                border_style="#1a2a44", padding=(0,0)
            ))
            console.print()
            _draw_dep_graph(api, tasks, deps)

            console.print(Rule("[dim]Navigation[/]", style="#1a2a44"))
            console.print(
                "  [bold]w[/] Week view  "
                "  [bold]b[/] Back"
            )
            console.print()
            ch = Prompt.ask("  [bold]>[/]").strip().lower()
            if   ch == "b": return
            elif ch == "w": view = "week"
            continue

        # ── Week calendar view ────────────────────────────────────────────────
        is_this = (offset == 0)
        week_label = f"{ws:%d %b} – {we:%d %b %Y}" + (" [bold](this week)[/]" if is_this else "")
        console.print(Panel(f"  {week_label}", border_style="#1a2a44", padding=(0,0)))
        console.print()

        # Build per-day task buckets
        days_tasks: dict = defaultdict(list)
        unscheduled = []

        for task in tasks:
            if task.get("status") in ("done","cancelled"):
                continue
            due = task.get("due_date","")
            blocked = bool(_is_blocked(task["id"], deps, tasks)) if deps else False
            task["_blocked"] = blocked   # temp flag for rendering
            if not due:
                unscheduled.append(task)
                continue
            try:
                d     = datetime.fromisoformat(due).date()
                delta = (d - ws).days
                if 0 <= delta <= 6:
                    days_tasks[delta].append(task)
                elif d < ws:
                    days_tasks[0].append(task)   # overdue → Monday slot
            except Exception:
                unscheduled.append(task)

        # Calendar grid
        tbl = Table(box=rbox.ROUNDED, border_style="#1a2a44",
                    header_style="bold", padding=(0,1), show_lines=True)
        for i, day in enumerate(DAY_NAMES):
            d     = ws + timedelta(days=i)
            is_td = (d == today)
            col   = f"[bold #00e5ff]{day} {d.day}[/]" if is_td else f"{day} {d.day}"
            # Add load indicator
            n     = len(days_tasks[i])
            load  = " ·"*min(n,5)
            tbl.add_column(col + f"[dim]{load}[/]", min_width=18)

        max_rows = max((len(v) for v in days_tasks.values()), default=0)
        max_rows = max(max_rows, 2)

        for row_i in range(max_rows):
            cells = []
            for col_i in range(7):
                col_tasks = sorted(days_tasks[col_i],
                                   key=lambda t: -t.get("priority_score",3))
                if row_i < len(col_tasks):
                    t    = col_tasks[row_i]
                    ps   = t.get("priority_score", 3)
                    icon = PRIO_ICON.get(ps, "🟡")
                    name = t["name"][:15]
                    d    = ws + timedelta(days=col_i)

                    # Color overdue
                    if t.get("due_date","") < today.isoformat() and t.get("status") != "done":
                        name = f"[red]{name}[/]"
                    # Mark blocked
                    if t.get("_blocked"):
                        name = f"[dim]{name} 🔒[/]"
                    cells.append(f"{icon} {name}")
                else:
                    cells.append("")
            tbl.add_row(*cells)

        console.print(tbl)

        # Unscheduled + blocked summary
        if unscheduled:
            names = "  ".join(f"[dim]{t['name'][:18]}[/]" for t in unscheduled[:4])
            extra = f" [dim]+{len(unscheduled)-4}[/]" if len(unscheduled) > 4 else ""
            console.print(Panel(
                f"  {names}{extra}",
                title="[dim]📌 Unscheduled[/]", border_style="#1a2a44", padding=(0,0)
            ))

        if deps:
            n_blocked = sum(
                1 for t in tasks
                if t.get("status") in ("todo","in_progress")
                and _is_blocked(t["id"], deps, tasks)
            )
            if n_blocked:
                console.print(f"  [red]🔒 {n_blocked} task(s) blocked by dependencies[/]")

        # Workload bar
        console.print()
        console.print("  [dim]Load:[/]  ", end="")
        for i, day in enumerate(DAY_NAMES):
            n   = len(days_tasks[i])
            clr = "red" if n >= 5 else "yellow" if n >= 3 else "#00b4d8"
            d   = ws + timedelta(days=i)
            mark = "[bold]" if d == today else ""
            console.print(f"{mark}[{clr}]{day}:{n}[/][/bold if d==today else '']  ", end="")
        console.print()

        # Navigation
        console.print()
        console.print(Rule("[dim]Navigation[/]", style="#1a2a44"))
        console.print(
            "  [bold]h[/] ← prev week   "
            "  [bold]l[/] → next week   "
            "  [bold]t[/] this week   "
            "  [bold]d[/] dependency graph   "
            "  [bold]b[/] back"
        )
        console.print()
        ch = Prompt.ask("  [bold]>[/]").strip().lower()

        if   ch == "b":     return
        elif ch in ("h","<"): offset -= 1
        elif ch in ("l",">"): offset += 1
        elif ch == "t":     offset = 0
        elif ch == "d":     view = "deps"

        # Clean temp flags
        for t in tasks:
            t.pop("_blocked", None)


def on_startup(api):
    def widget(api):
        deps    = _load_deps(api)
        tasks   = api.tasks
        today   = date.today()
        ws      = _week_start(today)
        this_week = [
            t for t in tasks
            if t.get("status") in ("todo","in_progress")
            and t.get("due_date","")
            and ws.isoformat() <= t["due_date"] <= (ws+timedelta(days=6)).isoformat()
        ]
        blocked = sum(1 for t in tasks if _is_blocked(t["id"], deps, tasks)
                      and t.get("status") in ("todo","in_progress"))
        parts = []
        if this_week:
            parts.append(f"[dim]{len(this_week)} due this week[/]")
        if blocked:
            parts.append(f"[red]{blocked} blocked[/]")
        return f"  📅 " + "   ".join(parts) if parts else ""
    api.register_dashboard_widget(widget)


def menu_items(api):
    return [("K", "📅 Weekly Planner", lambda: _weekly_screen(api))]
