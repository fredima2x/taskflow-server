"""
TaskFlow Plugin — Task Dependencies
PLUGIN_NAME    = "Dependencies"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Block tasks until their prerequisites are done"
PLUGIN_AUTHOR  = "community"
PLUGIN_TAGS    = "dependencies, workflow, blocking"
PLUGIN_MIN_API = "3.0"
"""
PLUGIN_NAME    = "Dependencies"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Block tasks until prerequisites are done"
PLUGIN_MIN_API = "3.0"

import os
from rich.panel  import Panel
from rich.table  import Table
from rich.prompt import Prompt, Confirm
from rich        import box as rbox


def _get_deps(store: dict) -> dict:
    """Return {task_id: [dep_task_id, ...]}"""
    return store.setdefault("deps", {})


def _is_blocked(task_id: str, deps: dict, tasks: list) -> list:
    """Return list of blocking task names (not yet done)."""
    task_map = {t["id"]: t for t in tasks}
    blocking = []
    for dep_id in deps.get(task_id, []):
        dep = task_map.get(dep_id)
        if dep and dep.get("status") != "done":
            blocking.append(dep["name"])
    return blocking


def _screen(api):
    store = api.store
    deps  = _get_deps(store)

    while True:
        os.system("clear")
        api.console.print("\n  [bold]⚡ TaskFlow  ·  🔗 Task Dependencies[/]\n")

        tasks    = api.tasks
        task_map = {t["id"]: t for t in tasks}
        active   = [t for t in tasks if t["status"] in ("todo","in_progress")]

        # Show dependency table
        linked = [(tid, dep_ids) for tid, dep_ids in deps.items()
                  if dep_ids and tid in task_map]

        if linked:
            tbl = api.table("Dependencies")
            tbl.add_column("Task",       min_width=26)
            tbl.add_column("Blocked by", min_width=26)
            tbl.add_column("Status",     width=12)
            for tid, dep_ids in linked:
                task = task_map.get(tid)
                if not task: continue
                blocking = _is_blocked(tid, deps, tasks)
                dep_names = ", ".join(
                    task_map[d]["name"][:20] for d in dep_ids if d in task_map
                )
                status = "[red]blocked[/]" if blocking else "[green]ready[/]"
                api.console.print()
                tbl.add_row(task["name"][:28], dep_names[:28], status)
            api.console.print(tbl)
        else:
            api.console.print(Panel("  No dependencies defined yet.",
                                    border_style="#1a2a44", padding=(0,1)))

        # Blocked summary
        blocked_count = sum(
            1 for t in active if _is_blocked(t["id"], deps, tasks)
        )
        if blocked_count:
            api.console.print(f"\n  [yellow]⚠ {blocked_count} task(s) currently blocked[/]")

        api.console.print()
        api.rule("Actions")
        api.console.print("  [bold]a[/]  Add dependency (A requires B)")
        api.console.print("  [bold]r[/]  Remove dependency")
        api.console.print("  [bold]v[/]  View blocked tasks")
        api.console.print("  [bold]b[/]  Back\n")

        ch = api.prompt(">").lower()
        if ch == "b": return

        elif ch == "a":
            os.system("clear")
            api.console.print("\n  [bold]Add Dependency[/]\n")
            api.console.print("  [dim]Step 1: select the task that should be BLOCKED[/]")
            for i, t in enumerate(active[:15], 1):
                blocking = _is_blocked(t["id"], deps, tasks)
                mark = " [red](blocked)[/]" if blocking else ""
                api.console.print(f"  [dim]{i}.[/]  {t['name'][:50]}{mark}")
            raw = api.prompt("Task to block")
            try:
                blocked_task = active[int(raw)-1]
            except Exception: continue

            api.console.print(f"\n  [dim]Step 2: select what '{blocked_task['name'][:30]}' depends on[/]")
            others = [t for t in active if t["id"] != blocked_task["id"]]
            for i, t in enumerate(others[:15], 1):
                api.console.print(f"  [dim]{i}.[/]  {t['name'][:50]}")
            raw2 = api.prompt("Prerequisite task")
            try:
                prereq = others[int(raw2)-1]
                dep_list = deps.setdefault(blocked_task["id"], [])
                if prereq["id"] not in dep_list:
                    dep_list.append(prereq["id"])
                    api.store_save()
                    api.console.print(
                        f"  [green]✓ '{blocked_task['name'][:30]}' now requires "
                        f"'{prereq['name'][:30]}' to be done first.[/]"
                    )
                else:
                    api.console.print("  [yellow]Already linked.[/]")
            except Exception as e:
                api.console.print(f"  [red]{e}[/]")
            api.press_enter()

        elif ch == "r":
            if not linked:
                api.console.print("  [dim]No dependencies to remove.[/]"); api.press_enter(); continue
            for i, (tid, dep_ids) in enumerate(linked, 1):
                t = task_map.get(tid, {})
                api.console.print(f"  [dim]{i}.[/]  {t.get('name','?')[:30]}  "
                                   f"→ {len(dep_ids)} dep(s)")
            raw = api.prompt("Which task's deps to edit")
            try:
                tid, dep_ids = linked[int(raw)-1]
                api.console.print()
                for j, dep_id in enumerate(dep_ids, 1):
                    api.console.print(f"  [dim]{j}.[/]  {task_map.get(dep_id,{}).get('name','?')[:50]}")
                raw2 = api.prompt("Remove dep number (or Enter to cancel)")
                if raw2:
                    removed = dep_ids.pop(int(raw2)-1)
                    deps[tid] = dep_ids
                    if not dep_ids:
                        del deps[tid]
                    api.store_save()
                    api.console.print("  [green]✓ Removed.[/]")
            except Exception: pass
            api.press_enter()

        elif ch == "v":
            os.system("clear")
            api.console.print("\n  [bold]Blocked Tasks[/]\n")
            found = False
            for t in active:
                blocking = _is_blocked(t["id"], deps, tasks)
                if blocking:
                    found = True
                    api.console.print(f"  [red]✗[/] [bold]{t['name'][:40]}[/]")
                    for b in blocking:
                        api.console.print(f"      [dim]waiting for:[/] {b[:40]}")
            if not found:
                api.console.print("  [green]No tasks are currently blocked![/]")
            api.press_enter()


def on_startup(api):
    """Register a dashboard widget showing blocked count."""
    def widget(api):
        deps  = api.store.get("deps", {})
        tasks = api.tasks
        count = sum(
            1 for t in tasks
            if t["status"] in ("todo","in_progress")
            and _is_blocked(t["id"], deps, tasks)
        )
        if count:
            return f"  🔗 [red]{count} task(s) blocked by dependencies[/]"
        return ""
    api.register_dashboard_widget(widget)

    # Register a task action to quickly add deps from task detail
    def add_dep_action(task):
        store = api.store
        deps  = _get_deps(store)
        prereqs = [t for t in api.tasks
                   if t["id"] != task["id"]
                   and t["status"] in ("todo","in_progress")]
        if not prereqs:
            api.console.print("  [yellow]No other active tasks to depend on.[/]")
            api.press_enter(); return
        api.console.print(f"\n  [bold]Add prerequisite for '{task['name'][:30]}'[/]\n")
        for i, t in enumerate(prereqs[:10], 1):
            api.console.print(f"  [dim]{i}.[/]  {t['name'][:50]}")
        raw = api.prompt("Number").strip()
        try:
            prereq   = prereqs[int(raw)-1]
            dep_list = deps.setdefault(task["id"], [])
            if prereq["id"] not in dep_list:
                dep_list.append(prereq["id"])
                store["deps"] = deps
                api.store_save()
                api.console.print(f"  [green]✓ Requires '{prereq['name'][:30]}' first.[/]")
            else:
                api.console.print("  [yellow]Already a dependency.[/]")
        except Exception: pass
        api.press_enter()

    api.register_task_action("D", "🔗 Add dependency", add_dep_action)


def on_task_started(api, task):
    """Warn if user tries to start a blocked task."""
    deps     = api.store.get("deps", {})
    blocking = _is_blocked(task["id"], deps, api.tasks)
    if blocking:
        names = ", ".join(blocking[:3])
        api.notify("⚠️ Task is blocked!",
                   f"'{task['name'][:30]}' needs: {names}")


def menu_items(api):
    deps   = api.store.get("deps",{})
    tasks  = api.tasks
    n_blocked = sum(
        1 for t in tasks
        if t["status"] in ("todo","in_progress")
        and _is_blocked(t["id"], deps, tasks)
    )
    label = f"🔗 Dependencies" + (f" [red]({n_blocked} blocked)[/]" if n_blocked else "")
    return [("Q", label, lambda: _screen(api))]
