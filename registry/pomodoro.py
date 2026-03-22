"""
TaskFlow Plugin — Pomodoro Timer
Drop into ~/.taskflow/plugins/pomodoro.py
"""
PLUGIN_NAME    = "Pomodoro"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Focus timer with work/break cycles & task linking"

import time, sys, os, threading
from datetime import datetime

# ── helpers (don't import rich at module level so plugin is self-contained) ───

def _cls():
    os.system("clear" if os.name != "nt" else "cls")

def _bar(elapsed, total, width=36):
    filled = int(width * elapsed / max(total, 1))
    return "█" * filled + "░" * (width - filled)

def _fmt(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"

def _run_timer(api, label: str, total_sec: int, task=None) -> bool:
    """
    Blocking timer loop. Returns True if completed, False if skipped.
    Prints a live countdown using simple terminal writes.
    """
    console = api.console
    start   = time.time()

    while True:
        elapsed = time.time() - start
        remain  = total_sec - elapsed
        if remain <= 0:
            break

        bar      = _bar(elapsed, total_sec)
        time_str = _fmt(remain)
        pct      = int(elapsed / total_sec * 100)
        task_str = f"  Task: {task['name'][:40]}" if task else ""

        _cls()
        console.print()
        console.print(f"  [bold #00e5ff]⚡ TaskFlow  ·  Pomodoro[/]")
        console.print()
        console.print(f"  [bold]{label}[/]")
        console.print(f"  [bold #00b4d8]{time_str}[/]  [dim]{bar}[/]  {pct}%")
        if task_str:
            console.print(f"[dim]{task_str}[/]")
        console.print()
        console.print(f"  [dim]s  skip   q  quit[/]")

        # Non-blocking key check (Unix only)
        try:
            import select, tty, termios
            old = termios.tcgetattr(sys.stdin)
            try:
                tty.setraw(sys.stdin.fileno())
                if select.select([sys.stdin], [], [], 1)[0]:
                    ch = sys.stdin.read(1).lower()
                    if ch == "q":
                        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
                        return False
                    elif ch == "s":
                        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
                        break
                else:
                    time.sleep(0.05)
            finally:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        except Exception:
            # Fallback: just sleep 1s, no keypress support
            time.sleep(1)

    return True


def _pomodoro_screen(api):
    from rich.prompt import Prompt, Confirm
    from rich.panel import Panel
    from rich.table import Table
    from rich import box as rbox

    console = api.console
    store   = api.store

    # Load settings
    work_min   = store.get("work_min",  25)
    short_min  = store.get("short_min",  5)
    long_min   = store.get("long_min",  15)
    long_every = store.get("long_every", 4)

    def _header():
        _cls()
        console.print()
        console.print("  [bold #00e5ff]⚡ TaskFlow  ·  🍅 Pomodoro[/]")
        console.print()

    while True:
        _header()

        # Stats
        sessions_today = [s for s in store.get("sessions", [])
                          if s.get("date") == datetime.now().date().isoformat()]
        completed_today = sum(1 for s in sessions_today if s.get("completed"))
        total_focus_min = sum(s.get("duration_min", 0) for s in sessions_today
                              if s.get("completed") and s.get("type") == "work")

        console.print(Panel(
            f"  Today: [bold #00e5ff]{completed_today}[/] pomodoros  "
            f"·  [bold #2ecc71]{total_focus_min}[/] focus minutes\n"
            f"  Work: [bold]{work_min}m[/]  Short break: [bold]{short_min}m[/]  "
            f"Long break: [bold]{long_min}m[/]  (every {long_every})",
            border_style="#1a2a44", padding=(0, 1)
        ))
        console.print()

        # Recent sessions
        if sessions_today:
            tbl = Table(box=rbox.SIMPLE, show_header=False,
                        padding=(0, 2), border_style="#1a2a44")
            tbl.add_column("", style="dim")
            tbl.add_column("")
            for s in sessions_today[-5:]:
                icon  = "🍅" if s.get("type") == "work" else "☕"
                state = "[green]✓[/]" if s.get("completed") else "[dim]skipped[/]"
                task  = f"  [dim]{s.get('task','')[:30]}[/]" if s.get("task") else ""
                tbl.add_row(icon, f"{state}  {s['duration_min']}m{task}")
            console.print(tbl)
            console.print()

        console.print("  [bold #00b4d8]1[/]  Start Pomodoro (no task)")
        console.print("  [bold #00b4d8]2[/]  Start Pomodoro (link to task)")
        console.print("  [bold #00b4d8]3[/]  Settings")
        console.print("  [bold #00b4d8]b[/]  Back")
        console.print()
        ch = Prompt.ask("  [#00b4d8]>[/]").strip().lower()

        if ch == "b":
            return

        linked_task = None
        if ch == "2":
            active = [t for t in api.tasks if t["status"] in ("todo","in_progress")]
            if not active:
                console.print("  [yellow]No active tasks.[/]")
                input("  Enter...")
                continue
            _header()
            console.print("  [#00b4d8]Pick a task:[/]\n")
            for i, t in enumerate(active[:10], 1):
                console.print(f"  [dim]{i}.[/]  {t['name'][:50]}")
            console.print()
            raw = Prompt.ask("  [#00b4d8]Number[/]", default="1")
            try:
                linked_task = active[int(raw)-1]
            except Exception:
                linked_task = None

        if ch in ("1","2"):
            # Run the full work+break cycle
            pomodoro_num = completed_today + 1
            is_long = (pomodoro_num % long_every == 0)

            completed = _run_timer(
                api, f"🍅 Pomodoro #{pomodoro_num}", work_min * 60, linked_task
            )

            session = {
                "date":         datetime.now().date().isoformat(),
                "type":         "work",
                "duration_min": work_min,
                "completed":    completed,
                "task":         linked_task["name"] if linked_task else "",
            }
            store.setdefault("sessions", []).append(session)
            api.store_save()

            if completed:
                api.notify("🍅 Pomodoro done!", f"#{pomodoro_num} complete. Take a break.")
                break_label = f"☕ Long break ({long_min}m)" if is_long else f"☕ Short break ({short_min}m)"
                break_sec   = (long_min if is_long else short_min) * 60
                _run_timer(api, break_label, break_sec)
                session2 = {
                    "date":         datetime.now().date().isoformat(),
                    "type":         "long_break" if is_long else "short_break",
                    "duration_min": long_min if is_long else short_min,
                    "completed":    True,
                }
                store.setdefault("sessions", []).append(session2)
                api.store_save()

        elif ch == "3":
            _header()
            console.print("  [#00b4d8]Settings[/]\n")
            def _ask_int(label, default):
                from rich.prompt import Prompt
                raw = Prompt.ask(f"  [#00b4d8]{label}[/]", default=str(default))
                try: return int(raw)
                except Exception: return default
            work_min   = _ask_int("Work duration (minutes)", work_min)
            short_min  = _ask_int("Short break (minutes)",   short_min)
            long_min   = _ask_int("Long break (minutes)",    long_min)
            long_every = _ask_int("Long break every N pomodoros", long_every)
            store.update(work_min=work_min, short_min=short_min,
                         long_min=long_min, long_every=long_every)
            api.store_save()
            console.print("  [green]✓ Saved.[/]")
            input("  Enter...")


def on_startup(api):
    pass  # nothing on startup


def menu_items(api):
    return [("p", "🍅 Pomodoro timer", lambda: _pomodoro_screen(api))]
