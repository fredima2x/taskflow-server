"""
TaskFlow Plugin — File Watcher
PLUGIN_NAME    = "File Watcher"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Create tasks automatically when files appear in watched folders"
PLUGIN_AUTHOR  = "community"
PLUGIN_TAGS    = "automation, files, watcher"
PLUGIN_MIN_API = "3.0"
"""
PLUGIN_NAME    = "File Watcher"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Auto-create tasks when files appear in watched folders"
PLUGIN_MIN_API = "3.0"

import os, threading, time, shutil
from pathlib  import Path
from datetime import date
from rich.panel  import Panel
from rich.prompt import Confirm


_watcher_thread = None
_watching        = False


def _watch_loop(api, watchers: list):
    """Background thread — polls watched dirs every 5 seconds."""
    global _watching
    seen = {}   # dir -> set of filenames seen previously

    # Seed with current files so we don't create tasks for old files
    for w in watchers:
        p = Path(w["path"]).expanduser()
        if p.exists():
            pattern = w.get("pattern","*")
            seen[w["path"]] = {f.name for f in p.glob(pattern)}
        else:
            seen[w["path"]] = set()

    while _watching:
        for w in watchers:
            if not w.get("enabled", True): continue
            p = Path(w["path"]).expanduser()
            if not p.exists(): continue
            pattern = w.get("pattern","*")
            current = {f.name for f in p.glob(pattern)}
            prev    = seen.get(w["path"], set())
            new     = current - prev
            for fname in new:
                task_name = w.get("task_template", "Process: {filename}").replace(
                    "{filename}", fname
                ).replace("{dir}", p.name)
                try:
                    api.add_task(
                        name     = task_name[:80],
                        priority = w.get("priority","Medium"),
                        category = w.get("category","Work"),
                        due      = date.today().isoformat() if w.get("due_today") else "",
                        desc     = f"File: {p / fname}",
                        tags     = ["file-watcher"] + w.get("tags",[]),
                    )
                    api.log(f"File watcher: new file '{fname}' in {w['path']}")
                    api.notify("📂 New file", f"{fname}\n→ Task created")
                except Exception as e:
                    api.log(f"File watcher error: {e}", "error")
            seen[w["path"]] = current
        time.sleep(5)


def _start_watcher(api):
    global _watcher_thread, _watching
    watchers = api.store.get("watchers", [])
    active   = [w for w in watchers if w.get("enabled", True)]
    if not active: return
    _watching = True
    _watcher_thread = threading.Thread(
        target=_watch_loop, args=(api, active), daemon=True
    )
    _watcher_thread.start()
    api.log(f"File watcher started — watching {len(active)} dir(s)")


def _screen(api):
    store    = api.store
    watchers = store.setdefault("watchers", [])

    while True:
        os.system("clear")
        api.console.print("\n  [bold]⚡ TaskFlow  ·  📂 File Watcher[/]\n")

        status = "[green]running[/]" if _watching else "[yellow]stopped[/]"
        api.console.print(Panel(
            f"  Status: {status}  ·  [dim]{len(watchers)} watcher(s) configured[/]\n"
            "  [dim]Checks for new files every 5 seconds while TaskFlow is open.[/]",
            border_style="#1a2a44", padding=(0,1)
        ))
        api.console.print()

        if watchers:
            tbl = api.table("Watched Folders")
            tbl.add_column("#",        width=3, justify="right", style="dim")
            tbl.add_column("Path",     min_width=24)
            tbl.add_column("Pattern",  width=10)
            tbl.add_column("Task template", min_width=24)
            tbl.add_column("Priority", width=10)
            tbl.add_column("",         width=6)
            for i, w in enumerate(watchers, 1):
                enabled = "[green]on[/]" if w.get("enabled",True) else "[dim]off[/]"
                tbl.add_row(str(i), w["path"][:24], w.get("pattern","*"),
                            w.get("task_template","{filename}")[:24],
                            w.get("priority","Medium"), enabled)
            api.console.print(tbl)

        api.console.print()
        api.rule("Actions")
        api.console.print("  [bold]n[/]  Add watched folder")
        if watchers:
            api.console.print("  [bold]t[/]  Toggle watcher on/off")
            api.console.print("  [bold]d[/]  Delete watcher")
        if not _watching and watchers:
            api.console.print("  [bold]s[/]  Start watcher now")
        api.console.print("  [bold]b[/]  Back\n")

        ch = api.prompt(">").lower()
        if ch == "b": return

        elif ch == "n":
            os.system("clear")
            api.console.print("\n  [bold]Add Watched Folder[/]\n")
            api.console.print("  [dim]Template vars: {filename}  {dir}[/]\n")
            path     = api.prompt("Folder path (e.g. ~/Downloads)")
            pattern  = api.prompt("File pattern (e.g. *.pdf  or  *)", default="*")
            template = api.prompt("Task name template", default="Process: {filename}")
            priority = api.pick("Priority", ["Medium","High","Low","Critical"])
            category = api.pick("Category", ["Work","Personal","Project","Other"])
            due_t    = api.confirm("Set due date to today?", default=True)
            tags_raw = api.prompt("Extra tags (comma-separated, optional)", default="")
            tags     = [x.strip() for x in tags_raw.split(",") if x.strip()]
            if path:
                import uuid
                watchers.append({
                    "id": str(uuid.uuid4())[:8], "path": path,
                    "pattern": pattern, "task_template": template,
                    "priority": priority, "category": category,
                    "due_today": due_t, "tags": tags, "enabled": True,
                })
                api.store_save()
                api.console.print("  [green]✓ Watcher added.[/]")
                # Restart watcher thread
                global _watching
                _watching = False
                time.sleep(0.1)
                _start_watcher(api)
            api.press_enter()

        elif ch == "t" and watchers:
            for i, w in enumerate(watchers, 1):
                api.console.print(f"  [dim]{i}.[/]  {w['path']}  ({'on' if w.get('enabled',True) else 'off'})")
            raw = api.prompt("Toggle number")
            try:
                watchers[int(raw)-1]["enabled"] = not watchers[int(raw)-1].get("enabled",True)
                api.store_save()
            except Exception: pass
            api.press_enter()

        elif ch == "d" and watchers:
            for i, w in enumerate(watchers, 1):
                api.console.print(f"  [dim]{i}.[/]  {w['path']}")
            raw = api.prompt("Delete number")
            try:
                w = watchers[int(raw)-1]
                if Confirm.ask(f"  Delete watcher for '{w['path']}'?"):
                    watchers.pop(int(raw)-1)
                    api.store_save()
            except Exception: pass
            api.press_enter()

        elif ch == "s":
            _start_watcher(api)
            api.console.print("  [green]✓ Watcher started.[/]"); api.press_enter()


def on_startup(api):
    _start_watcher(api)


def menu_items(api):
    status = "▶" if _watching else "■"
    return [("W", f"📂 File Watcher [{status}]", lambda: _screen(api))]
