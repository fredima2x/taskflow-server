"""
TaskFlow Plugin — Color Themes
Drop into ~/.taskflow/plugins/themes.py
"""
PLUGIN_NAME    = "Themes"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Switch color themes — Dracula, Nord, Gruvbox, Solarized, and more"

import os

THEMES = {
    "default": {
        "primary":   "#00e5ff",
        "secondary": "#00b4d8",
        "border":    "#1a2a44",
        "dim":       "#4a6a88",
        "success":   "#2ecc71",
        "warning":   "#f39c12",
        "error":     "red",
        "accent":    "#9b59b6",
    },
    "dracula": {
        "primary":   "#bd93f9",   # purple
        "secondary": "#ff79c6",   # pink
        "border":    "#44475a",
        "dim":       "#6272a4",
        "success":   "#50fa7b",
        "warning":   "#ffb86c",
        "error":     "#ff5555",
        "accent":    "#8be9fd",
    },
    "nord": {
        "primary":   "#88c0d0",   # frost blue
        "secondary": "#81a1c1",
        "border":    "#3b4252",
        "dim":       "#4c566a",
        "success":   "#a3be8c",
        "warning":   "#ebcb8b",
        "error":     "#bf616a",
        "accent":    "#b48ead",
    },
    "gruvbox": {
        "primary":   "#fabd2f",   # yellow
        "secondary": "#fe8019",   # orange
        "border":    "#3c3836",
        "dim":       "#665c54",
        "success":   "#b8bb26",
        "warning":   "#fabd2f",
        "error":     "#fb4934",
        "accent":    "#d3869b",
    },
    "solarized": {
        "primary":   "#268bd2",   # blue
        "secondary": "#2aa198",   # cyan
        "border":    "#073642",
        "dim":       "#586e75",
        "success":   "#859900",
        "warning":   "#b58900",
        "error":     "#dc322f",
        "accent":    "#6c71c4",
    },
    "monokai": {
        "primary":   "#a6e22e",   # green
        "secondary": "#66d9e8",   # cyan
        "border":    "#272822",
        "dim":       "#75715e",
        "success":   "#a6e22e",
        "warning":   "#e6db74",
        "error":     "#f92672",
        "accent":    "#ae81ff",
    },
    "tokyo_night": {
        "primary":   "#7aa2f7",   # blue
        "secondary": "#bb9af7",   # purple
        "border":    "#1a1b26",
        "dim":       "#565f89",
        "success":   "#9ece6a",
        "warning":   "#e0af68",
        "error":     "#f7768e",
        "accent":    "#73daca",
    },
    "catppuccin": {
        "primary":   "#cba6f7",   # mauve
        "secondary": "#89dceb",   # sky
        "border":    "#313244",
        "dim":       "#585b70",
        "success":   "#a6e3a1",
        "warning":   "#fab387",
        "error":     "#f38ba8",
        "accent":    "#f5c2e7",
    },
    "matrix": {
        "primary":   "#00ff41",
        "secondary": "#008f11",
        "border":    "#003b00",
        "dim":       "#005400",
        "success":   "#00ff41",
        "warning":   "#39ff14",
        "error":     "#ff0000",
        "accent":    "#00cc33",
    },
}

PREVIEW_CHARS = "██████████"


def _themes_screen(api):
    from rich.prompt import Prompt
    from rich.panel  import Panel
    from rich.table  import Table
    from rich.text   import Text
    from rich        import box as rbox
    from rich.rule   import Rule

    console = api.console
    store   = api.store
    current = store.get("theme", "default")

    while True:
        os.system("clear")
        console.print()
        console.print("  [bold]⚡ TaskFlow  ·  🎨 Themes[/]\n")

        tbl = Table(box=rbox.ROUNDED, border_style="#1a2a44",
                    header_style="bold", padding=(0,2))
        tbl.add_column("#",       width=3,  justify="right", style="dim")
        tbl.add_column("Theme",   width=14)
        tbl.add_column("Primary", width=12)
        tbl.add_column("Preview", width=32)
        tbl.add_column("",        width=10)

        names = list(THEMES.keys())
        for i, name in enumerate(names, 1):
            t         = THEMES[name]
            active_mk = "[bold green]← active[/]" if name == current else ""
            preview   = (
                Text("██", style=t["primary"])
                + Text("██", style=t["secondary"])
                + Text("██", style=t["success"])
                + Text("██", style=t["warning"])
                + Text("██", style=t["error"])
            )
            tbl.add_row(str(i), name, t["primary"], preview, active_mk)

        console.print(tbl)
        console.print()
        console.print(Rule("[dim]Actions[/]", style="#1a2a44"))
        console.print("  Enter a [bold]number[/] to apply theme   "
                      "  [bold #00b4d8]c[/] custom   [bold #00b4d8]b[/] back")
        console.print()
        ch = Prompt.ask("  [#00b4d8]>[/]").strip().lower()

        if ch == "b":
            return
        elif ch == "c":
            _custom_theme_screen(api)
            current = store.get("theme", "default")
            continue

        try:
            idx  = int(ch) - 1
            name = names[idx]
        except Exception:
            continue

        api.apply_theme(THEMES[name])
        store["theme"]       = name
        store["theme_colors"] = THEMES[name]
        api.store_save()
        current = name
        console.print(f"\n  [green]✓ Theme '{name}' applied![/]")
        input("  Enter to continue...")


def _custom_theme_screen(api):
    from rich.prompt import Prompt
    from rich.panel  import Panel

    console = api.console
    store   = api.store
    current = store.get("theme_colors", THEMES["default"]).copy()

    console.print("\n  [bold]Custom Theme[/]  [dim](Enter hex color or leave blank to keep)[/]\n")
    keys = ["primary","secondary","border","dim","success","warning","error","accent"]
    for k in keys:
        val = Prompt.ask(f"  [#00b4d8]{k:<12}[/] [dim][{current[k]}][/]",
                         default=current[k]).strip()
        if val:
            current[k] = val

    api.apply_theme(current)
    store["theme"]        = "custom"
    store["theme_colors"] = current
    api.store_save()
    console.print("\n  [green]✓ Custom theme applied![/]")
    input("  Enter...")


def on_startup(api):
    """Re-apply saved theme on startup."""
    store  = api.store
    colors = store.get("theme_colors")
    if colors:
        api.apply_theme(colors)


def menu_items(api):
    current = api.store.get("theme", "default")
    return [("T", f"🎨 Themes  [dim]({current})[/]", lambda: _themes_screen(api))]
