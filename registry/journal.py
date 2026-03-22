"""
TaskFlow Plugin — Daily Journal
Drop into ~/.taskflow/plugins/journal.py
"""
PLUGIN_NAME    = "Journal"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Daily notes linked to tasks, searchable, with mood tracking"

from datetime import datetime, timedelta, date
import os

MOODS = ["😄 Great", "🙂 Good", "😐 Okay", "😔 Low", "😤 Stressed"]


def _today_key() -> str:
    return date.today().isoformat()


def _journal_screen(api):
    from rich.prompt  import Prompt, Confirm
    from rich.table   import Table
    from rich.panel   import Panel
    from rich.text    import Text
    from rich.rule    import Rule
    from rich         import box as rbox

    console = api.console
    store   = api.store   # dict persisted to ~/.taskflow/plugin_data/journal.json

    def _cls(): os.system("clear")

    def _header(sub=""):
        _cls()
        console.print()
        t = "  [bold #00e5ff]⚡ TaskFlow  ·  📝 Journal[/]"
        if sub: t += f"  [dim]·  {sub}[/]"
        console.print(t)
        console.print()

    while True:
        _header()
        entries = store.get("entries", {})
        today   = _today_key()

        # Show last 5 entry dates
        dates_sorted = sorted(entries.keys(), reverse=True)[:6]
        if dates_sorted:
            tbl = Table(box=rbox.SIMPLE, show_header=False,
                        padding=(0,2), border_style="#1a2a44")
            tbl.add_column("Date",  style="#00b4d8", width=12)
            tbl.add_column("Mood",  width=14)
            tbl.add_column("Tasks", width=6, justify="right")
            tbl.add_column("Preview", style="dim", min_width=30)
            for d in dates_sorted:
                e     = entries[d]
                mood  = e.get("mood","")
                tasks = str(len(e.get("linked_tasks",[])))
                prev  = (e.get("note","")[:40] + "…") if len(e.get("note","")) > 40 else e.get("note","")
                mark  = "[bold #00e5ff]→ today[/]" if d == today else d
                tbl.add_row(mark, mood, tasks, prev)
            console.print(tbl)
            console.print()

        # Word-count streak
        streak = 0
        check  = date.today()
        while check.isoformat() in entries and entries[check.isoformat()].get("note","").strip():
            streak += 1
            check  -= timedelta(days=1)
        if streak:
            console.print(f"  ✍️  Journal streak: [bold #00e5ff]{streak}[/] day{'s' if streak != 1 else ''}")
            console.print()

        console.print(Rule("[dim]Actions[/]", style="#1a2a44"))
        console.print("  [bold #00b4d8]t[/]  Write / edit today's entry")
        console.print("  [bold #00b4d8]v[/]  View a past entry")
        console.print("  [bold #00b4d8]s[/]  Search entries")
        console.print("  [bold #00b4d8]b[/]  Back")
        console.print()
        ch = Prompt.ask("  [#00b4d8]>[/]").strip().lower()

        if ch == "b":
            return

        elif ch == "t":
            _header(f"Today  {today}")
            entry = entries.get(today, {"note":"","mood":"","linked_tasks":[]})

            # Mood picker
            console.print("  [#00b4d8]How are you feeling?[/]\n")
            for i, m in enumerate(MOODS, 1):
                cur = " [bold #00e5ff]← current[/]" if entry.get("mood") == m else ""
                console.print(f"  [dim]{i}.[/]  {m}{cur}")
            console.print()
            raw = Prompt.ask("  [#00b4d8]Mood[/]",
                             default=str(MOODS.index(entry["mood"])+1) if entry.get("mood") in MOODS else "2")
            try:
                entry["mood"] = MOODS[int(raw)-1]
            except Exception:
                pass

            # Show done tasks today as quick-link
            done_today = [t for t in api.tasks
                          if t.get("status") == "done" and t.get("completed_at","")[:10] == today]
            if done_today:
                console.print()
                console.print("  [dim]Tasks completed today (Enter numbers to link, or Enter to skip):[/]")
                for i, t in enumerate(done_today, 1):
                    linked = "✓" if t["id"] in entry.get("linked_tasks",[]) else " "
                    console.print(f"  [{linked}] [dim]{i}.[/]  {t['name'][:50]}")
                console.print()
                raw = Prompt.ask("  [#00b4d8]Link tasks[/]  (e.g. 1 2 3)", default="")
                linked = list(entry.get("linked_tasks",[]))
                for part in raw.split():
                    try:
                        t = done_today[int(part)-1]
                        if t["id"] not in linked:
                            linked.append(t["id"])
                    except Exception:
                        pass
                entry["linked_tasks"] = linked

            # Note editor
            console.print()
            console.print("  [#00b4d8]Journal entry[/]  [dim](blank line to finish)[/]")
            if entry.get("note"):
                console.print(Panel(entry["note"], title="[dim]current[/]",
                                    border_style="#1a2a44", padding=(0,1)))
            console.print()
            lines = []
            while True:
                try:
                    line = input("  > ")
                    if line == "" and lines and lines[-1] == "":
                        break
                    lines.append(line)
                except (EOFError, KeyboardInterrupt):
                    break
            note = "\n".join(lines).strip()
            if note:
                entry["note"] = note
            elif not entry.get("note"):
                entry["note"] = ""

            entry["updated"] = datetime.now().isoformat()
            entries[today]   = entry
            store["entries"] = entries
            api.store_save()
            console.print("\n  [green]✓ Saved.[/]")
            input("  Enter to continue...")

        elif ch == "v":
            _header("View entry")
            if not entries:
                console.print("  [dim]No entries yet.[/]"); input("  Enter..."); continue

            dates_all = sorted(entries.keys(), reverse=True)
            for i, d in enumerate(dates_all[:20], 1):
                console.print(f"  [dim]{i}.[/]  {d}  [dim]{entries[d].get('mood','')}[/]")
            console.print()
            raw = Prompt.ask("  [#00b4d8]Number[/]", default="1")
            try:
                d_key = dates_all[int(raw)-1]
            except Exception:
                continue
            e = entries[d_key]
            _header(d_key)

            # Resolve linked tasks
            task_map = {t["id"]: t for t in api.tasks}
            linked   = [task_map[tid]["name"] for tid in e.get("linked_tasks",[])
                        if tid in task_map]

            console.print(Panel(
                f"  [bold]{e.get('mood','')}[/]\n\n"
                + (f"  {e['note']}\n" if e.get("note") else "  [dim](no note)[/]\n")
                + ("\n  Linked: " + ", ".join(linked) if linked else ""),
                title=f"[bold #00b4d8]{d_key}[/]",
                border_style="#1a2a44", padding=(0,1)
            ))
            input("  Enter to continue...")

        elif ch == "s":
            _header("Search")
            query = Prompt.ask("  [#00b4d8]Search term[/]").strip().lower()
            if not query:
                continue
            hits = [(d, e) for d, e in entries.items()
                    if query in e.get("note","").lower()
                    or query in e.get("mood","").lower()]
            if not hits:
                console.print("  [yellow]No results.[/]")
            else:
                for d, e in sorted(hits, reverse=True):
                    snippet = e.get("note","")
                    idx     = snippet.lower().find(query)
                    start   = max(0, idx-20)
                    end     = min(len(snippet), idx+60)
                    excerpt = "…" + snippet[start:end] + "…"
                    console.print(f"  [bold #00b4d8]{d}[/]  {e.get('mood','')}  [dim]{excerpt}[/]")
            input("\n  Enter to continue...")


def on_startup(api):
    pass


def on_task_done(api, task):
    """Remind user to journal if they haven't today."""
    today   = _today_key()
    entries = api.store.get("entries", {})
    if today not in entries:
        api.notify("📝 Journal reminder",
                   f"You completed '{task['name'][:30]}' — write today's entry!")


def menu_items(api):
    return [("j", "📝 Daily journal", lambda: _journal_screen(api))]
