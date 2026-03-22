"""
TaskFlow Plugin — Task Templates
PLUGIN_NAME    = "Task Templates"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Save and instantly spawn reusable task groups"
PLUGIN_AUTHOR  = "community"
PLUGIN_TAGS    = "templates, workflow, productivity"
PLUGIN_MIN_API = "3.0"
"""
PLUGIN_NAME    = "Task Templates"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Save and spawn reusable task groups"
PLUGIN_MIN_API = "3.0"

import os, uuid
from datetime import date, timedelta
from rich.panel  import Panel
from rich.table  import Table
from rich.prompt import Prompt, Confirm
from rich        import box as rbox


def _screen(api):
    store     = api.store
    templates = store.setdefault("templates", [])

    while True:
        os.system("clear")
        api.console.print("\n  [bold]⚡ TaskFlow  ·  📝 Task Templates[/]\n")

        if not templates:
            api.console.print(Panel(
                "  No templates yet.\n"
                "  [dim]Use [bold]n[/] to save a template, or [bold]c[/] to create one manually.[/]",
                border_style="#1a2a44", padding=(0,1)
            ))
        else:
            tbl = api.table("Templates")
            tbl.add_column("#",       width=3,  justify="right", style="dim")
            tbl.add_column("Name",    min_width=22)
            tbl.add_column("Tasks",   width=7,  justify="right")
            tbl.add_column("Description", min_width=30)
            for i, tmpl in enumerate(templates, 1):
                tbl.add_row(str(i), f"[bold]{tmpl['name']}[/]",
                            str(len(tmpl.get("tasks",[]))),
                            f"[dim]{tmpl.get('desc','')}[/]")
            api.console.print(tbl)

        api.console.print()
        api.rule("Actions")
        api.console.print("  [bold]n[/]  Save current active tasks as template")
        api.console.print("  [bold]c[/]  Create template manually")
        if templates:
            api.console.print("  [bold]s[/]  Spawn template (create tasks from it)")
            api.console.print("  [bold]v[/]  View template tasks")
            api.console.print("  [bold]d[/]  Delete template")
        api.console.print("  [bold]b[/]  Back\n")

        ch = api.prompt(">").lower()
        if ch == "b": return

        elif ch == "n":
            # Save active tasks as template
            active = api.query_tasks(status="todo")
            if not active:
                api.console.print("  [yellow]No active tasks to save.[/]"); api.press_enter(); continue
            name = api.prompt("Template name", required=True)
            if not name: continue
            desc = api.prompt("Description (optional)")
            # Strip IDs, created_at etc — keep only structure
            task_defs = [{
                "name":             t["name"],
                "priority":         t.get("priority","Medium"),
                "category":         t.get("category","Work"),
                "estimated_hours":  t.get("estimated_hours",1.0),
                "description":      t.get("description",""),
                "tags":             t.get("tags",[]),
                "due_offset_days":  0,  # relative to spawn date
            } for t in active]
            templates.append({"id": str(uuid.uuid4())[:8], "name": name,
                               "desc": desc, "tasks": task_defs})
            api.store_save()
            api.console.print(f"  [green]✓ Template '{name}' saved with {len(task_defs)} tasks.[/]")
            api.press_enter()

        elif ch == "c":
            # Create template manually by adding task definitions
            os.system("clear")
            api.console.print("\n  [bold]Create Template[/]\n")
            name = api.prompt("Template name", required=True)
            if not name: continue
            desc = api.prompt("Description (optional)")
            task_defs = []
            api.console.print("\n  [dim]Add tasks (empty name to finish):[/]")
            while True:
                tname = api.prompt(f"  Task {len(task_defs)+1} name").strip()
                if not tname: break
                prio    = api.pick("  Priority", ["Medium","High","Critical","Low","Minimal"])
                cat     = api.pick("  Category", ["Work","Personal","Project","Health","Learning","Other"])
                hours   = float(api.prompt("  Estimated hours", default="1.0") or "1.0")
                due_off = int(api.prompt("  Due offset days (0 = today, 7 = +1 week)", default="0") or "0")
                task_defs.append({
                    "name": tname, "priority": prio, "category": cat,
                    "estimated_hours": hours, "description": "",
                    "tags": [], "due_offset_days": due_off,
                })
            if task_defs:
                templates.append({"id": str(uuid.uuid4())[:8], "name": name,
                                   "desc": desc, "tasks": task_defs})
                api.store_save()
                api.console.print(f"  [green]✓ Created '{name}' with {len(task_defs)} tasks.[/]")
            api.press_enter()

        elif ch == "s" and templates:
            for i, tmpl in enumerate(templates, 1):
                api.console.print(f"  [dim]{i}.[/]  {tmpl['name']}  [dim]({len(tmpl['tasks'])} tasks)[/]")
            api.console.print()
            raw = api.prompt("Spawn template number")
            try:
                tmpl   = templates[int(raw)-1]
                today  = date.today()
                prefix = api.prompt("Prefix for task names (optional, Enter to skip)")
                spawned = 0
                for td in tmpl["tasks"]:
                    due = ""
                    if td.get("due_offset_days",0) > 0:
                        due = (today + timedelta(days=td["due_offset_days"])).isoformat()
                    name = f"{prefix}: {td['name']}" if prefix else td["name"]
                    api.add_task(
                        name     = name,
                        priority = td.get("priority","Medium"),
                        category = td.get("category","Work"),
                        due      = due,
                        hours    = td.get("estimated_hours",1.0),
                        desc     = td.get("description",""),
                        tags     = td.get("tags",[]),
                    )
                    spawned += 1
                api.console.print(f"  [green]✓ Spawned {spawned} tasks from '{tmpl['name']}'.[/]")
            except Exception as e:
                api.console.print(f"  [red]{e}[/]")
            api.press_enter()

        elif ch == "v" and templates:
            for i, tmpl in enumerate(templates, 1):
                api.console.print(f"  [dim]{i}.[/]  {tmpl['name']}")
            raw = api.prompt("View template number")
            try:
                tmpl = templates[int(raw)-1]
                os.system("clear")
                api.console.print(f"\n  [bold]{tmpl['name']}[/]  [dim]{tmpl.get('desc','')}[/]\n")
                for td in tmpl["tasks"]:
                    due_info = f"  +{td['due_offset_days']}d" if td.get("due_offset_days") else ""
                    api.console.print(f"  [dim]·[/] {td['name'][:40]}  "
                                      f"[dim]{td['priority']} · {td['estimated_hours']}h{due_info}[/]")
            except Exception: pass
            api.press_enter()

        elif ch == "d" and templates:
            for i, tmpl in enumerate(templates, 1):
                api.console.print(f"  [dim]{i}.[/]  {tmpl['name']}")
            raw = api.prompt("Delete template number")
            try:
                tmpl = templates[int(raw)-1]
                if Confirm.ask(f"  Delete [bold]{tmpl['name']}[/]?"):
                    templates.pop(int(raw)-1)
                    api.store_save()
                    api.console.print("  [green]✓ Deleted.[/]")
            except Exception: pass
            api.press_enter()


def on_startup(api): pass


def menu_items(api):
    n = len(api.store.get("templates",[]))
    return [("L", f"📝 Templates [dim]({n})[/]", lambda: _screen(api))]
