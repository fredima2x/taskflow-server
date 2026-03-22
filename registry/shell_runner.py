"""
TaskFlow Plugin — Shell Runner
PLUGIN_NAME    = "Shell Runner"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Run shell commands when tasks are started or completed"
PLUGIN_AUTHOR  = "community"
PLUGIN_TAGS    = "automation, shell, scripting"
PLUGIN_MIN_API = "3.0"
"""
PLUGIN_NAME    = "Shell Runner"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Run shell commands when tasks start or finish"
PLUGIN_MIN_API = "3.0"

import os, subprocess, shlex
from datetime import datetime
from rich.panel  import Panel
from rich.table  import Table
from rich        import box as rbox


def _run(cmd: str, task: dict, api) -> tuple[bool, str]:
    """Execute a shell command, substituting task variables."""
    env = {
        **os.environ,
        "TASK_ID":       task.get("id",""),
        "TASK_NAME":     task.get("name",""),
        "TASK_PRIORITY": task.get("priority",""),
        "TASK_CATEGORY": task.get("category",""),
        "TASK_STATUS":   task.get("status",""),
        "TASK_DUE":      task.get("due_date",""),
    }
    try:
        result = subprocess.run(
            cmd, shell=True, env=env, capture_output=True, text=True, timeout=30
        )
        output = (result.stdout + result.stderr).strip()
        ok     = result.returncode == 0
        api.log(f"shell [{task['name'][:20]}]: {cmd[:40]} → rc={result.returncode}", "info")
        return ok, output
    except subprocess.TimeoutExpired:
        return False, "Timeout (30s)"
    except Exception as e:
        return False, str(e)


def _screen(api):
    store = api.store
    rules = store.setdefault("rules", [])
    # rule: {id, name, event, match_type, match_value, cmd, enabled}

    while True:
        os.system("clear")
        api.console.print("\n  [bold]⚡ TaskFlow  ·  🖥️ Shell Runner[/]\n")

        if not rules:
            api.console.print(Panel(
                "  No shell rules yet.\n"
                "  [dim]Rules run a shell command when a task event fires.[/]\n"
                "  [dim]Available vars: $TASK_ID $TASK_NAME $TASK_PRIORITY $TASK_CATEGORY $TASK_STATUS $TASK_DUE[/]",
                border_style="#1a2a44", padding=(0,1)
            ))
        else:
            tbl = api.table("Shell Rules")
            tbl.add_column("#",       width=3,  justify="right", style="dim")
            tbl.add_column("Name",    width=18)
            tbl.add_column("Event",   width=14)
            tbl.add_column("Match",   width=20)
            tbl.add_column("Command", min_width=24)
            tbl.add_column("",        width=8)
            for i, r in enumerate(rules, 1):
                enabled = "[green]on[/]" if r.get("enabled",True) else "[dim]off[/]"
                match = f"{r['match_type']}={r['match_value']}" if r.get("match_value") else "all tasks"
                tbl.add_row(str(i), r["name"][:16], r["event"],
                            match[:20], r["cmd"][:24], enabled)
            api.console.print(tbl)

        api.console.print()
        api.rule("Actions")
        api.console.print("  [bold]n[/]  New rule")
        if rules:
            api.console.print("  [bold]t[/]  Toggle rule on/off")
            api.console.print("  [bold]x[/]  Delete rule")
            api.console.print("  [bold]l[/]  View recent log")
        api.console.print("  [bold]b[/]  Back\n")

        ch = api.prompt(">").lower()
        if ch == "b": return

        elif ch == "n":
            os.system("clear")
            api.console.print("\n  [bold]New Shell Rule[/]\n")
            name = api.prompt("Rule name", default="My Rule")
            api.console.print()
            event = api.pick("Trigger event", [
                "on_task_done", "on_task_started", "on_task_created", "on_task_deleted"
            ])
            api.console.print()
            match_type = api.pick("Match", ["all tasks","category","priority","tag","name contains"])
            match_val  = ""
            if match_type != "all tasks":
                match_val = api.prompt(f"  Value for '{match_type}'")
            api.console.print()
            api.console.print("  [dim]Available: $TASK_ID $TASK_NAME $TASK_PRIORITY $TASK_CATEGORY $TASK_STATUS $TASK_DUE[/]")
            cmd = api.prompt("Shell command")
            if cmd:
                import uuid
                rules.append({
                    "id": str(uuid.uuid4())[:8], "name": name, "event": event,
                    "match_type": match_type, "match_value": match_val,
                    "cmd": cmd, "enabled": True,
                })
                api.store_save()
                api.console.print("  [green]✓ Rule created.[/]")
            api.press_enter()

        elif ch == "t" and rules:
            for i, r in enumerate(rules, 1):
                api.console.print(f"  [dim]{i}.[/]  {r['name']}  ({'on' if r.get('enabled',True) else 'off'})")
            raw = api.prompt("Toggle rule number")
            try:
                rules[int(raw)-1]["enabled"] = not rules[int(raw)-1].get("enabled", True)
                api.store_save()
                api.console.print("  [green]✓ Toggled.[/]")
            except Exception: pass
            api.press_enter()

        elif ch == "x" and rules:
            for i, r in enumerate(rules, 1):
                api.console.print(f"  [dim]{i}.[/]  {r['name']}")
            from rich.prompt import Confirm
            raw = api.prompt("Delete rule number")
            try:
                r = rules[int(raw)-1]
                if Confirm.ask(f"  Delete '{r['name']}'?"):
                    rules.pop(int(raw)-1)
                    api.store_save()
            except Exception: pass
            api.press_enter()

        elif ch == "l":
            os.system("clear")
            api.console.print("\n  [bold]Recent Shell Log[/]\n")
            log = [e for e in api.get_log(100) if "shell [" in e[3]][-20:]
            for ts, _, level, msg in log:
                api.console.print(f"  [dim]{ts}[/]  {msg}")
            api.press_enter()


def _fire_rules(event: str, task: dict, api):
    rules = api.store.get("rules", [])
    for r in rules:
        if not r.get("enabled", True): continue
        if r["event"] != event: continue
        # Check match
        mt, mv = r.get("match_type","all tasks"), r.get("match_value","")
        if mt == "category" and task.get("category","") != mv: continue
        if mt == "priority" and task.get("priority","") != mv: continue
        if mt == "tag" and mv not in task.get("tags",[]): continue
        if mt == "name contains" and mv.lower() not in task.get("name","").lower(): continue
        ok, out = _run(r["cmd"], task, api)
        if not ok:
            api.log(f"Rule '{r['name']}' failed: {out[:80]}", "warn")


def on_startup(api):     pass
def on_task_done(api, task):    _fire_rules("on_task_done",    task, api)
def on_task_created(api, task): _fire_rules("on_task_created", task, api)
def on_task_deleted(api, task): _fire_rules("on_task_deleted", task, api)
def on_task_started(api, task): _fire_rules("on_task_started", task, api)


def menu_items(api):
    n = len(api.store.get("rules",[]))
    return [("S", f"🖥️ Shell Runner [dim]({n} rules)[/]", lambda: _screen(api))]
