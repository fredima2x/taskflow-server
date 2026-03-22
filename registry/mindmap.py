"""
TaskFlow Plugin — Mindmap Export
PLUGIN_NAME    = "Mindmap Export"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Export tasks as Graphviz .dot mindmap (render with: dot -Tpng)"
PLUGIN_AUTHOR  = "community"
PLUGIN_TAGS    = "mindmap, graphviz, export, visualization"
PLUGIN_MIN_API = "3.0"
"""
PLUGIN_NAME    = "Mindmap Export"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Export tasks as Graphviz .dot mindmap"
PLUGIN_MIN_API = "3.0"

import os, shutil, subprocess
from pathlib import Path
from collections import defaultdict


PRIO_COLOR = {
    "Critical": "#e74c3c", "High": "#e67e22",
    "Medium":   "#f1c40f", "Low":  "#2ecc71", "Minimal": "#95a5a6",
}
STATUS_SHAPE = {
    "todo":        "ellipse",
    "in_progress": "diamond",
    "done":        "box",
    "cancelled":   "plaintext",
}


def _escape(s: str) -> str:
    return s.replace('"', '\\"').replace('\n', ' ')


def _build_dot(tasks: list, style: str = "category") -> str:
    """Build Graphviz DOT source. style = 'category' | 'priority' | 'status'"""
    lines = [
        'digraph TaskFlow {',
        '  graph [rankdir=LR bgcolor="#0b0b18" fontname="sans-serif"]',
        '  node  [fontname="sans-serif" fontcolor=white style=filled]',
        '  edge  [color="#445566"]',
        '',
        '  root [label="⚡ TaskFlow" shape=circle fillcolor="#00b4d8" '
        'fontsize=14 width=1.2]',
        '',
    ]

    if style == "category":
        # Group by category
        cats = defaultdict(list)
        for t in tasks:
            cats[t.get("category","Other")].append(t)

        CAT_COLORS = {
            "Work":"#1a3a5c","Personal":"#1a4a2c","Health":"#4a1a2c",
            "Learning":"#3a2a5c","Finance":"#4a3a1c","Project":"#1c3a4a","Other":"#2a2a2a"
        }
        for cat, task_list in cats.items():
            cat_id  = f"cat_{cat.replace(' ','_')}"
            cat_clr = CAT_COLORS.get(cat,"#2a2a2a")
            lines.append(f'  {cat_id} [label="{_escape(cat)}" shape=folder '
                         f'fillcolor="{cat_clr}" fontsize=11]')
            lines.append(f'  root -> {cat_id}')
            for t in task_list:
                tid  = f"t_{t['id']}"
                clr  = PRIO_COLOR.get(t.get("priority","Medium"),"#aaa")
                shp  = STATUS_SHAPE.get(t.get("status","todo"),"ellipse")
                name = _escape(t["name"][:35])
                due  = f"\\n📅 {t['due_date']}" if t.get("due_date") else ""
                lines.append(f'  {tid} [label="{name}{due}" shape={shp} '
                             f'fillcolor="{clr}" fontsize=9]')
                lines.append(f'  {cat_id} -> {tid}')

    elif style == "priority":
        prios = ["Critical","High","Medium","Low","Minimal"]
        for p in prios:
            p_tasks = [t for t in tasks if t.get("priority")==p]
            if not p_tasks: continue
            pid  = f"prio_{p}"
            clr  = PRIO_COLOR.get(p,"#aaa")
            lines.append(f'  {pid} [label="{p}" shape=hexagon '
                         f'fillcolor="{clr}" fontsize=11]')
            lines.append(f'  root -> {pid}')
            for t in p_tasks:
                tid  = f"t_{t['id']}"
                shp  = STATUS_SHAPE.get(t.get("status","todo"),"ellipse")
                name = _escape(t["name"][:35])
                lines.append(f'  {tid} [label="{name}" shape={shp} '
                             f'fillcolor="{clr}88" fontsize=9]')
                lines.append(f'  {pid} -> {tid}')

    elif style == "status":
        status_labels = {
            "todo":"📋 To Do","in_progress":"⚡ In Progress",
            "done":"✅ Done","cancelled":"✗ Cancelled"
        }
        status_colors = {
            "todo":"#1a3a5c","in_progress":"#4a3a00",
            "done":"#1a4a2c","cancelled":"#2a2a2a"
        }
        for st, label in status_labels.items():
            s_tasks = [t for t in tasks if t.get("status")==st]
            if not s_tasks: continue
            sid  = f"st_{st}"
            clr  = status_colors.get(st,"#2a2a2a")
            lines.append(f'  {sid} [label="{label}" shape=tab '
                         f'fillcolor="{clr}" fontsize=11]')
            lines.append(f'  root -> {sid}')
            for t in s_tasks:
                tid  = f"t_{t['id']}"
                pclr = PRIO_COLOR.get(t.get("priority","Medium"),"#aaa")
                name = _escape(t["name"][:35])
                lines.append(f'  {tid} [label="{name}" shape=ellipse '
                             f'fillcolor="{pclr}88" fontsize=9]')
                lines.append(f'  {sid} -> {tid}')

    lines.append('}')
    return '\n'.join(lines)


def _screen(api):
    os.system("clear")
    api.console.print("\n  [bold]⚡ TaskFlow  ·  🗺️ Mindmap Export[/]\n")

    has_dot = shutil.which("dot")
    if not has_dot:
        api.console.print(api.panel(
            "  [yellow]Graphviz 'dot' not found.[/]\n"
            "  Install:  [bold]sudo pacman -S graphviz[/]\n\n"
            "  You can still export .dot files and render elsewhere.",
            title="Graphviz"
        ) or "")
        from rich.panel import Panel
        api.console.print(Panel(
            "  [yellow]Graphviz 'dot' not found.[/]\n"
            "  Install:  [bold]sudo pacman -S graphviz[/]\n\n"
            "  You can still export .dot files and render them elsewhere.",
            border_style="yellow", padding=(0,1)
        ))
        api.console.print()

    api.console.print("  [bold]1[/]  Group by category")
    api.console.print("  [bold]2[/]  Group by priority")
    api.console.print("  [bold]3[/]  Group by status")
    api.console.print("  [bold]b[/]  Back\n")

    ch = api.prompt(">").lower()
    if ch == "b": return
    style = {"1":"category","2":"priority","3":"status"}.get(ch,"category")

    # Filter
    api.console.print()
    include_done   = api.confirm("Include done tasks?",      default=False)
    include_cancel = api.confirm("Include cancelled tasks?", default=False)
    tasks = [t for t in api.tasks
             if (include_done   or t.get("status") != "done")
             and (include_cancel or t.get("status") != "cancelled")]

    if not tasks:
        api.console.print("  [yellow]No tasks to export.[/]"); api.press_enter(); return

    dot_src = _build_dot(tasks, style)

    out_dir  = api.data_dir / "exports"
    out_dir.mkdir(exist_ok=True)
    dot_path = out_dir / f"mindmap_{style}.dot"
    dot_path.write_text(dot_src, encoding="utf-8")
    api.console.print(f"\n  [green]✓ DOT file:[/] {dot_path}")

    if has_dot:
        for fmt in ["png","svg"]:
            out_path = out_dir / f"mindmap_{style}.{fmt}"
            try:
                subprocess.run(
                    ["dot", f"-T{fmt}", str(dot_path), "-o", str(out_path)],
                    check=True, capture_output=True
                )
                api.console.print(f"  [green]✓ {fmt.upper()}:[/] {out_path}")
            except Exception as e:
                api.console.print(f"  [red]{fmt} render failed: {e}[/]")

        if api.confirm("\n  Open PNG in image viewer?", default=False):
            png = out_dir / f"mindmap_{style}.png"
            if png.exists():
                try: subprocess.Popen(["xdg-open", str(png)])
                except Exception: pass
    else:
        api.console.print(
            f"\n  [dim]Render manually:[/]\n"
            f"  dot -Tpng {dot_path} -o mindmap.png\n"
            f"  dot -Tsvg {dot_path} -o mindmap.svg"
        )

    api.press_enter()


def on_startup(api): pass


def menu_items(api):
    return [("N", "🗺️ Mindmap Export", lambda: _screen(api))]
