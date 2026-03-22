"""
TaskFlow Plugin — Voice Notes
PLUGIN_NAME    = "Voice Notes"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Record and play audio notes linked to tasks (arecord/aplay)"
PLUGIN_AUTHOR  = "community"
PLUGIN_TAGS    = "audio, notes, voice"
PLUGIN_MIN_API = "3.0"
"""
PLUGIN_NAME    = "Voice Notes"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Record/play audio notes for tasks via arecord/aplay"
PLUGIN_MIN_API = "3.0"

import os, subprocess, shutil
from datetime import datetime
from pathlib  import Path
from rich.panel  import Panel
from rich.table  import Table
from rich        import box as rbox


def _audio_dir(api) -> Path:
    p = api.data_dir / "voice_notes"
    p.mkdir(exist_ok=True)
    return p


def _notes_for(task_id: str, api) -> list[Path]:
    return sorted((_audio_dir(api)).glob(f"{task_id}_*.wav"))


def _record(path: Path, seconds: int = 30) -> bool:
    if not shutil.which("arecord"):
        return False
    try:
        subprocess.run(
            ["arecord", "-f", "cd", "-t", "wav", "-d", str(seconds), str(path)],
            check=True
        )
        return True
    except Exception:
        return False


def _play(path: Path) -> bool:
    player = shutil.which("aplay") or shutil.which("ffplay") or shutil.which("mpv")
    if not player:
        return False
    try:
        cmd = [player, str(path)]
        if "ffplay" in player:
            cmd += ["-nodisp", "-autoexit"]
        elif "mpv" in player:
            cmd += ["--no-video"]
        subprocess.run(cmd, check=True,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def _voice_screen_for_task(api, task):
    """Called from task action — manage notes for a specific task."""
    console = api.console

    while True:
        os.system("clear")
        console.print(f"\n  [bold]⚡ Voice Notes  ·  {task['name'][:40]}[/]\n")

        notes = _notes_for(task["id"], api)
        if notes:
            tbl = api.table("Recordings")
            tbl.add_column("#",    width=3, justify="right", style="dim")
            tbl.add_column("File", min_width=30)
            tbl.add_column("Size", width=10, justify="right")
            for i, p in enumerate(notes, 1):
                size = f"{p.stat().st_size/1024:.1f} KB"
                tbl.add_row(str(i), p.name, size)
            console.print(tbl)
        else:
            console.print(Panel("  No voice notes yet.", border_style="#1a2a44", padding=(0,1)))

        console.print()
        if not shutil.which("arecord"):
            console.print(Panel(
                "  [yellow]arecord not found.[/]\n  Install: [bold]sudo pacman -S alsa-utils[/]",
                border_style="yellow", padding=(0,1)
            ))
        else:
            console.print("  [bold]r[/]  Record new note (30s max)")
            console.print("  [bold]R[/]  Record with custom duration")
        if notes:
            console.print("  [bold]p[/]  Play a recording")
            console.print("  [bold]x[/]  Delete a recording")
        console.print("  [bold]b[/]  Back\n")

        ch = api.prompt(">")
        if ch.lower() == "b": return

        elif ch.lower() == "r" and shutil.which("arecord"):
            dur = 30
            if ch == "R":
                raw = api.prompt("Duration in seconds", default="30")
                try: dur = int(raw)
                except Exception: dur = 30
            ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = _audio_dir(api) / f"{task['id']}_{ts}.wav"
            console.print(f"  [red]● Recording {dur}s… press Ctrl+C to stop early[/]")
            try:
                ok = _record(path, dur)
                if ok and path.exists():
                    console.print(f"  [green]✓ Saved: {path.name}[/]")
                else:
                    console.print("  [yellow]Recording failed or empty.[/]")
            except KeyboardInterrupt:
                console.print("  [dim]Stopped.[/]")
            api.press_enter()

        elif ch.lower() == "p" and notes:
            for i, p in enumerate(notes, 1):
                console.print(f"  [dim]{i}.[/]  {p.name}")
            raw = api.prompt("Play number")
            try:
                p  = notes[int(raw)-1]
                ok = _play(p)
                if not ok:
                    console.print("  [red]No player found (aplay/ffplay/mpv).[/]")
            except Exception: pass
            api.press_enter()

        elif ch.lower() == "x" and notes:
            for i, p in enumerate(notes, 1):
                console.print(f"  [dim]{i}.[/]  {p.name}")
            raw = api.prompt("Delete number")
            try:
                from rich.prompt import Confirm
                p = notes[int(raw)-1]
                if Confirm.ask(f"  Delete [bold]{p.name}[/]?"):
                    p.unlink()
                    console.print("  [green]✓ Deleted.[/]")
            except Exception: pass
            api.press_enter()


def _overview_screen(api):
    """Show all tasks that have voice notes."""
    os.system("clear")
    api.console.print("\n  [bold]⚡ TaskFlow  ·  🎙️ Voice Notes Overview[/]\n")

    audio_dir = _audio_dir(api)
    task_map  = {t["id"]: t for t in api.tasks}

    # Group files by task_id
    groups: dict = {}
    for f in sorted(audio_dir.glob("*.wav")):
        tid = f.stem.split("_")[0]
        groups.setdefault(tid, []).append(f)

    if not groups:
        api.console.print(Panel("  No voice notes recorded yet.",
                                border_style="#1a2a44", padding=(0,1)))
        api.press_enter(); return

    tbl = api.table("Voice Notes by Task")
    tbl.add_column("#",        width=3, justify="right", style="dim")
    tbl.add_column("Task",     min_width=30)
    tbl.add_column("Notes",    width=7, justify="right")
    tbl.add_column("Total size", width=12, justify="right")

    entries = []
    for tid, files in groups.items():
        task = task_map.get(tid)
        name = task["name"][:30] if task else f"[dim]deleted ({tid})[/]"
        size = sum(f.stat().st_size for f in files)
        entries.append((tid, name, files, size))
        tbl.add_row(str(len(entries)), name, str(len(files)), f"{size/1024:.1f} KB")

    api.console.print(tbl)
    api.console.print()
    raw = api.prompt("Open task notes (number) or b to back")
    if raw.lower() == "b": return
    try:
        tid, name, files, _ = entries[int(raw)-1]
        task = task_map.get(tid)
        if task:
            _voice_screen_for_task(api, task)
    except Exception: pass


def on_startup(api):
    # Register task action
    def voice_action(task):
        _voice_screen_for_task(api, task)
    api.register_task_action("V", "🎙️ Voice notes", voice_action)

    # Dashboard widget
    def widget(api):
        n = len(list((_audio_dir(api)).glob("*.wav")))
        return f"  🎙️ [dim]{n} voice note(s)[/]" if n else ""
    api.register_dashboard_widget(widget)


def menu_items(api):
    n = len(list(_audio_dir(api).glob("*.wav")))
    return [("V", f"🎙️ Voice Notes [dim]({n})[/]", lambda: _overview_screen(api))]
