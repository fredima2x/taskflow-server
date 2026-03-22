"""
TaskFlow Plugin — Tag Manager
PLUGIN_NAME    = "Tag Manager"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Bulk-tag, rename, merge, and visualize tag usage"
PLUGIN_AUTHOR  = "community"
PLUGIN_TAGS    = "tags, organization, bulk"
PLUGIN_MIN_API = "3.0"
"""
PLUGIN_NAME    = "Tag Manager"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Rename, merge, bulk-tag and visualize tags"
PLUGIN_MIN_API = "3.0"

import os
from collections import Counter
from rich.panel  import Panel
from rich.table  import Table
from rich.prompt import Prompt, Confirm
from rich        import box as rbox


def _all_tags(tasks: list) -> Counter:
    c = Counter()
    for t in tasks:
        for tag in t.get("tags", []):
            c[tag] += 1
    return c


def _screen(api):
    while True:
        os.system("clear")
        api.console.print("\n  [bold]⚡ TaskFlow  ·  🏷️ Tag Manager[/]\n")

        tasks    = api.tasks
        tag_cnt  = _all_tags(tasks)

        if not tag_cnt:
            api.console.print(Panel(
                "  No tags yet — add tags when creating or editing tasks.",
                border_style="#1a2a44", padding=(0,1)
            ))
        else:
            # Tag table with usage bars
            tbl = api.table("All Tags")
            tbl.add_column("#",      width=3,  justify="right", style="dim")
            tbl.add_column("Tag",    min_width=20)
            tbl.add_column("Tasks",  width=7,  justify="right")
            tbl.add_column("Bar",    width=24)
            tbl.add_column("Categories", min_width=20)

            max_cnt = max(tag_cnt.values(), default=1)
            for i, (tag, cnt) in enumerate(tag_cnt.most_common(), 1):
                bar  = "█" * int(cnt / max_cnt * 20) + "░" * (20 - int(cnt / max_cnt * 20))
                cats = Counter(
                    t.get("category","") for t in tasks
                    if tag in t.get("tags",[])
                )
                cat_str = ", ".join(f"{c}({n})" for c,n in cats.most_common(3))
                tbl.add_row(str(i), f"[bold]{tag}[/]", str(cnt),
                            f"[dim]{bar}[/]", f"[dim]{cat_str}[/]")
            api.console.print(tbl)
            api.console.print(f"\n  [dim]{len(tag_cnt)} unique tag(s) across {len(tasks)} tasks[/]")

        api.console.print()
        api.rule("Actions")
        api.console.print("  [bold]r[/]  Rename a tag (across all tasks)")
        api.console.print("  [bold]m[/]  Merge two tags into one")
        api.console.print("  [bold]d[/]  Delete a tag from all tasks")
        api.console.print("  [bold]a[/]  Add tag to multiple tasks at once")
        api.console.print("  [bold]f[/]  Filter view tasks by tag")
        api.console.print("  [bold]b[/]  Back\n")

        ch = api.prompt(">").lower()
        if ch == "b": return

        elif ch == "r" and tag_cnt:
            _show_tag_list(api, tag_cnt)
            old = api.prompt("Tag to rename")
            if old not in tag_cnt:
                api.console.print("  [yellow]Tag not found.[/]"); api.press_enter(); continue
            new = api.prompt(f"New name for '{old}'").strip()
            if not new: continue
            count = 0
            for t in tasks:
                if old in t.get("tags",[]):
                    t["tags"] = [new if x==old else x for x in t["tags"]]
                    count += 1
            if count:
                api.save(f"tag:rename:{old}→{new}")
                api.console.print(f"  [green]✓ Renamed '{old}' → '{new}' on {count} task(s).[/]")
            api.press_enter()

        elif ch == "m" and tag_cnt:
            _show_tag_list(api, tag_cnt)
            t1 = api.prompt("First tag (will be removed)")
            t2 = api.prompt("Second tag (will be kept)")
            if t1 not in tag_cnt or t2 not in tag_cnt:
                api.console.print("  [yellow]One or both tags not found.[/]"); api.press_enter(); continue
            count = 0
            for t in tasks:
                tags = t.get("tags",[])
                if t1 in tags:
                    tags = [x for x in tags if x != t1]
                    if t2 not in tags:
                        tags.append(t2)
                    t["tags"] = tags; count += 1
            if count:
                api.save(f"tag:merge:{t1}+{t2}")
                api.console.print(f"  [green]✓ Merged '{t1}' into '{t2}' ({count} task(s)).[/]")
            api.press_enter()

        elif ch == "d" and tag_cnt:
            _show_tag_list(api, tag_cnt)
            tag = api.prompt("Tag to delete")
            if tag not in tag_cnt:
                api.console.print("  [yellow]Tag not found.[/]"); api.press_enter(); continue
            if Confirm.ask(f"  Remove '{tag}' from all {tag_cnt[tag]} task(s)?"):
                for t in tasks:
                    t["tags"] = [x for x in t.get("tags",[]) if x != tag]
                api.save(f"tag:delete:{tag}")
                api.console.print(f"  [green]✓ Removed '{tag}'.[/]")
            api.press_enter()

        elif ch == "a":
            os.system("clear")
            api.console.print("\n  [bold]Bulk Add Tag[/]\n")
            tag = api.prompt("Tag to add").strip()
            if not tag: continue
            api.console.print()
            api.console.print("  Filter tasks to tag:")
            api.console.print("  [bold]1[/] All active  [bold]2[/] By category  [bold]3[/] By priority  [bold]4[/] Pick manually")
            sub = api.prompt("Filter").strip()
            targets = []
            if sub == "1":
                targets = [t for t in tasks if t.get("status") in ("todo","in_progress")]
            elif sub == "2":
                cat = api.pick("Category", sorted({t.get("category","Other") for t in tasks}))
                targets = [t for t in tasks if t.get("category","") == cat]
            elif sub == "3":
                prio = api.pick("Priority", ["Critical","High","Medium","Low","Minimal"])
                targets = [t for t in tasks if t.get("priority","") == prio]
            elif sub == "4":
                active = [t for t in tasks if t.get("status") in ("todo","in_progress")]
                for i, t in enumerate(active[:20], 1):
                    cur = "✓" if tag in t.get("tags",[]) else " "
                    api.console.print(f"  [{cur}] [dim]{i}.[/]  {t['name'][:50]}")
                raw = api.prompt("Numbers to tag (e.g. 1 3 5)")
                for p in raw.split():
                    try: targets.append(active[int(p)-1])
                    except Exception: pass

            added = 0
            for t in targets:
                if tag not in t.get("tags",[]):
                    t.setdefault("tags",[]).append(tag)
                    added += 1
            if added:
                api.save(f"tag:bulk-add:{tag}")
                api.console.print(f"  [green]✓ Added '{tag}' to {added} task(s).[/]")
            api.press_enter()

        elif ch == "f" and tag_cnt:
            _show_tag_list(api, tag_cnt)
            tag = api.prompt("Filter by tag")
            filtered = [t for t in tasks if tag in t.get("tags",[])]
            if not filtered:
                api.console.print("  [yellow]No tasks with that tag.[/]"); api.press_enter(); continue
            os.system("clear")
            api.console.print(f"\n  [bold]Tasks tagged '{tag}'[/]  ({len(filtered)})\n")
            tbl = api.table(f"Tag: {tag}")
            tbl.add_column("Task",   min_width=30)
            tbl.add_column("Status", width=14)
            tbl.add_column("Priority", width=12)
            tbl.add_column("Due",    width=12)
            for t in filtered:
                tbl.add_row(t["name"][:30], t.get("status",""),
                            t.get("priority",""), t.get("due_date","") or "—")
            api.console.print(tbl)
            api.press_enter()


def _show_tag_list(api, tag_cnt: Counter):
    api.console.print()
    for tag, cnt in tag_cnt.most_common():
        api.console.print(f"  [dim]·[/] [bold]{tag}[/]  [dim]({cnt})[/]")
    api.console.print()


def on_startup(api):
    def widget(api):
        cnt = len(_all_tags(api.tasks))
        return f"  🏷️ [dim]{cnt} unique tag(s)[/]" if cnt else ""
    api.register_dashboard_widget(widget)


def menu_items(api):
    n = len(_all_tags(api.tasks))
    return [("T", f"🏷️ Tag Manager [dim]({n} tags)[/]", lambda: _screen(api))]
