"""
TaskFlow Theming Plugin
Customize TaskFlow's appearance with beautiful color themes.
"""

PLUGIN_NAME        = "Themes"
PLUGIN_VERSION     = "1.0.0"
PLUGIN_DESC        = "Customize TaskFlow with beautiful color themes and create your own"
PLUGIN_AUTHOR      = "TaskFlow Community"
PLUGIN_TAGS        = "themes, customization, appearance, colors"
PLUGIN_MIN_API     = "3.0"
PLUGIN_PERMISSIONS = ["theme", "storage_write"]

import json
from datetime import datetime


# ══════════════════════════════════════════════════════════════
# PREDEFINED THEMES
# ══════════════════════════════════════════════════════════════

BUILTIN_THEMES = {
    "default": {
        "name": "🔵 Default Blue",
        "desc": "Classic TaskFlow blue theme",
        "colors": {
            "primary": "blue",
            "secondary": "cyan",
            "success": "green",
            "warning": "yellow",
            "error": "red",
            "info": "cyan",
            "muted": "dim white",
            "border": "blue",
            "header": "bold blue",
            "panel_border": "blue",
        }
    },
    
    "dracula": {
        "name": "🧛 Dracula",
        "desc": "Dark theme with purple accents",
        "colors": {
            "primary": "#bd93f9",
            "secondary": "#ff79c6",
            "success": "#50fa7b",
            "warning": "#f1fa8c",
            "error": "#ff5555",
            "info": "#8be9fd",
            "muted": "#6272a4",
            "border": "#bd93f9",
            "header": "bold #bd93f9",
            "panel_border": "#6272a4",
        }
    },
    
    "nord": {
        "name": "❄️ Nord",
        "desc": "Cool arctic-inspired theme",
        "colors": {
            "primary": "#88c0d0",
            "secondary": "#81a1c1",
            "success": "#a3be8c",
            "warning": "#ebcb8b",
            "error": "#bf616a",
            "info": "#5e81ac",
            "muted": "#4c566a",
            "border": "#88c0d0",
            "header": "bold #88c0d0",
            "panel_border": "#4c566a",
        }
    },
    
    "gruvbox": {
        "name": "🟤 Gruvbox",
        "desc": "Retro warm color scheme",
        "colors": {
            "primary": "#fe8019",
            "secondary": "#fabd2f",
            "success": "#b8bb26",
            "warning": "#d79921",
            "error": "#fb4934",
            "info": "#83a598",
            "muted": "#928374",
            "border": "#fe8019",
            "header": "bold #fe8019",
            "panel_border": "#504945",
        }
    },
    
    "solarized_dark": {
        "name": "🌙 Solarized Dark",
        "desc": "Precision colors for machines and people",
        "colors": {
            "primary": "#268bd2",
            "secondary": "#2aa198",
            "success": "#859900",
            "warning": "#b58900",
            "error": "#dc322f",
            "info": "#268bd2",
            "muted": "#586e75",
            "border": "#268bd2",
            "header": "bold #268bd2",
            "panel_border": "#073642",
        }
    },
    
    "solarized_light": {
        "name": "☀️ Solarized Light",
        "desc": "Light variant of Solarized",
        "colors": {
            "primary": "#268bd2",
            "secondary": "#2aa198",
            "success": "#859900",
            "warning": "#b58900",
            "error": "#dc322f",
            "info": "#268bd2",
            "muted": "#93a1a1",
            "border": "#268bd2",
            "header": "bold #268bd2",
            "panel_border": "#eee8d5",
        }
    },
    
    "monokai": {
        "name": "🎨 Monokai",
        "desc": "Vibrant colors on dark background",
        "colors": {
            "primary": "#f92672",
            "secondary": "#66d9ef",
            "success": "#a6e22e",
            "warning": "#e6db74",
            "error": "#f92672",
            "info": "#66d9ef",
            "muted": "#75715e",
            "border": "#f92672",
            "header": "bold #f92672",
            "panel_border": "#49483e",
        }
    },
    
    "tokyo_night": {
        "name": "🌃 Tokyo Night",
        "desc": "Clean dark theme inspired by Tokyo's night",
        "colors": {
            "primary": "#7aa2f7",
            "secondary": "#bb9af7",
            "success": "#9ece6a",
            "warning": "#e0af68",
            "error": "#f7768e",
            "info": "#7dcfff",
            "muted": "#565f89",
            "border": "#7aa2f7",
            "header": "bold #7aa2f7",
            "panel_border": "#3b4261",
        }
    },
    
    "catppuccin": {
        "name": "🐱 Catppuccin",
        "desc": "Soothing pastel theme",
        "colors": {
            "primary": "#89b4fa",
            "secondary": "#cba6f7",
            "success": "#a6e3a1",
            "warning": "#f9e2af",
            "error": "#f38ba8",
            "info": "#89dceb",
            "muted": "#6c7086",
            "border": "#89b4fa",
            "header": "bold #89b4fa",
            "panel_border": "#45475a",
        }
    },
    
    "github_dark": {
        "name": "🐙 GitHub Dark",
        "desc": "GitHub's dark theme",
        "colors": {
            "primary": "#58a6ff",
            "secondary": "#79c0ff",
            "success": "#3fb950",
            "warning": "#d29922",
            "error": "#f85149",
            "info": "#58a6ff",
            "muted": "#8b949e",
            "border": "#58a6ff",
            "header": "bold #58a6ff",
            "panel_border": "#30363d",
        }
    },
    
    "one_dark": {
        "name": "🌑 One Dark",
        "desc": "Atom's iconic One Dark theme",
        "colors": {
            "primary": "#61afef",
            "secondary": "#c678dd",
            "success": "#98c379",
            "warning": "#e5c07b",
            "error": "#e06c75",
            "info": "#56b6c2",
            "muted": "#5c6370",
            "border": "#61afef",
            "header": "bold #61afef",
            "panel_border": "#3e4451",
        }
    },
    
    "material": {
        "name": "🎯 Material",
        "desc": "Google Material Design colors",
        "colors": {
            "primary": "#82aaff",
            "secondary": "#c792ea",
            "success": "#c3e88d",
            "warning": "#ffcb6b",
            "error": "#f07178",
            "info": "#89ddff",
            "muted": "#546e7a",
            "border": "#82aaff",
            "header": "bold #82aaff",
            "panel_border": "#37474f",
        }
    },
    
    "rose_pine": {
        "name": "🌹 Rosé Pine",
        "desc": "All natural pine, faux fur and a bit of soho vibes",
        "colors": {
            "primary": "#c4a7e7",
            "secondary": "#ebbcba",
            "success": "#9ccfd8",
            "warning": "#f6c177",
            "error": "#eb6f92",
            "info": "#31748f",
            "muted": "#6e6a86",
            "border": "#c4a7e7",
            "header": "bold #c4a7e7",
            "panel_border": "#403d52",
        }
    },
    
    "cyberpunk": {
        "name": "🤖 Cyberpunk",
        "desc": "Neon lights and dark nights",
        "colors": {
            "primary": "#ff00ff",
            "secondary": "#00ffff",
            "success": "#00ff00",
            "warning": "#ffff00",
            "error": "#ff0080",
            "info": "#00d4ff",
            "muted": "#808080",
            "border": "#ff00ff",
            "header": "bold #ff00ff",
            "panel_border": "#1a1a2e",
        }
    },
    
    "forest": {
        "name": "🌲 Forest",
        "desc": "Natural green tones",
        "colors": {
            "primary": "#5ccc96",
            "secondary": "#6ab04c",
            "success": "#78e08f",
            "warning": "#f6b93b",
            "error": "#eb4d4b",
            "info": "#4bcffa",
            "muted": "#95a5a6",
            "border": "#5ccc96",
            "header": "bold #5ccc96",
            "panel_border": "#2d3436",
        }
    },
    
    "ocean": {
        "name": "🌊 Ocean",
        "desc": "Deep blue sea colors",
        "colors": {
            "primary": "#0984e3",
            "secondary": "#00b894",
            "success": "#00cec9",
            "warning": "#fdcb6e",
            "error": "#d63031",
            "info": "#74b9ff",
            "muted": "#636e72",
            "border": "#0984e3",
            "header": "bold #0984e3",
            "panel_border": "#2d3436",
        }
    },
    
    "sunset": {
        "name": "🌅 Sunset",
        "desc": "Warm sunset colors",
        "colors": {
            "primary": "#ff6b6b",
            "secondary": "#feca57",
            "success": "#48dbfb",
            "warning": "#ff9ff3",
            "error": "#ee5a6f",
            "info": "#54a0ff",
            "muted": "#95afc0",
            "border": "#ff6b6b",
            "header": "bold #ff6b6b",
            "panel_border": "#2f3640",
        }
    },
    
    "minimal": {
        "name": "⚪ Minimal",
        "desc": "Clean monochrome theme",
        "colors": {
            "primary": "white",
            "secondary": "bright_white",
            "success": "bright_white",
            "warning": "white",
            "error": "bright_white",
            "info": "white",
            "muted": "dim white",
            "border": "white",
            "header": "bold white",
            "panel_border": "dim white",
        }
    },
    
    "hacker": {
        "name": "💻 Hacker",
        "desc": "Classic green terminal",
        "colors": {
            "primary": "#00ff00",
            "secondary": "#00cc00",
            "success": "#00ff00",
            "warning": "#88ff00",
            "error": "#ff0000",
            "info": "#00ffff",
            "muted": "#008800",
            "border": "#00ff00",
            "header": "bold #00ff00",
            "panel_border": "#003300",
        }
    },
}


# ══════════════════════════════════════════════════════════════
# LIFECYCLE HOOKS
# ══════════════════════════════════════════════════════════════

def install(api):
    """First-time setup."""
    store = api.store
    store["active_theme"] = "default"
    store["custom_themes"] = {}
    store["favorites"] = []
    store["theme_history"] = []
    api.store_save()
    
    api.config["auto_apply"] = True
    api.config["show_preview"] = True
    api.config_save()
    
    api.log("Themes plugin installed")
    api.notify("🎨 Themes", "Plugin installed! Press T in the menu to customize.")


def on_startup(api):
    """Apply saved theme on startup."""
    store = api.store
    active = store.get("active_theme", "default")
    
    if api.config.get("auto_apply", True):
        _apply_theme(api, active)
        api.log(f"Applied theme: {active}")


# ══════════════════════════════════════════════════════════════
# THEME MANAGEMENT
# ══════════════════════════════════════════════════════════════

def _get_theme(api, theme_id):
    """Get theme by ID (builtin or custom)."""
    if theme_id in BUILTIN_THEMES:
        return BUILTIN_THEMES[theme_id]
    
    custom = api.store.get("custom_themes", {})
    if theme_id in custom:
        return custom[theme_id]
    
    return None


def _apply_theme(api, theme_id):
    """Apply a theme to TaskFlow."""
    theme = _get_theme(api, theme_id)
    if not theme:
        api.log(f"Theme not found: {theme_id}", "error")
        return False
    
    try:
        api.apply_theme(theme["colors"])
        
        store = api.store
        store["active_theme"] = theme_id
        
        # Add to history
        history = store.get("theme_history", [])
        entry = {
            "theme_id": theme_id,
            "timestamp": datetime.now().isoformat(),
        }
        history.insert(0, entry)
        store["theme_history"] = history[:20]  # Keep last 20
        
        api.store_save()
        return True
    
    except Exception as e:
        api.log(f"Failed to apply theme: {e}", "error")
        return False


def _create_custom_theme(api, theme_id, name, desc, colors):
    """Create or update a custom theme."""
    store = api.store
    custom = store.get("custom_themes", {})
    
    custom[theme_id] = {
        "name": name,
        "desc": desc,
        "colors": colors,
        "created": datetime.now().isoformat(),
    }
    
    store["custom_themes"] = custom
    api.store_save()


def _delete_custom_theme(api, theme_id):
    """Delete a custom theme."""
    store = api.store
    custom = store.get("custom_themes", {})
    
    if theme_id in custom:
        del custom[theme_id]
        store["custom_themes"] = custom
        
        # Remove from favorites
        favs = store.get("favorites", [])
        if theme_id in favs:
            favs.remove(theme_id)
            store["favorites"] = favs
        
        api.store_save()
        return True
    
    return False


def _toggle_favorite(api, theme_id):
    """Toggle theme favorite status."""
    store = api.store
    favs = store.get("favorites", [])
    
    if theme_id in favs:
        favs.remove(theme_id)
    else:
        favs.append(theme_id)
    
    store["favorites"] = favs
    api.store_save()


def _export_theme(api, theme_id):
    """Export theme to JSON file."""
    theme = _get_theme(api, theme_id)
    if not theme:
        return None
    
    export_data = {
        "theme_id": theme_id,
        "name": theme["name"],
        "desc": theme["desc"],
        "colors": theme["colors"],
        "exported": datetime.now().isoformat(),
        "plugin_version": PLUGIN_VERSION,
    }
    
    filename = f"theme_{theme_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = api.data_dir / "plugin_data" / filename
    
    api.write_file(str(filepath.relative_to(api.data_dir)), json.dumps(export_data, indent=2))
    return filepath


def _import_theme(api, filepath):
    """Import theme from JSON file."""
    try:
        content = api.read_file(filepath)
        if not content:
            return False, "File not found"
        
        data = json.loads(content)
        
        # Validate structure
        required = ["theme_id", "name", "desc", "colors"]
        if not all(k in data for k in required):
            return False, "Invalid theme file format"
        
        # Create custom theme
        theme_id = data["theme_id"]
        
        # Avoid overwriting builtins
        if theme_id in BUILTIN_THEMES:
            theme_id = f"custom_{theme_id}"
        
        _create_custom_theme(
            api,
            theme_id,
            data["name"],
            data["desc"],
            data["colors"]
        )
        
        return True, theme_id
    
    except json.JSONDecodeError:
        return False, "Invalid JSON format"
    except Exception as e:
        return False, str(e)


# ══════════════════════════════════════════════════════════════
# UI SCREENS
# ══════════════════════════════════════════════════════════════

def _main_screen(api):
    """Main theme browser."""
    while True:
        api.clear_screen()
        api.show_header("Theme Browser")
        
        store = api.store
        active = store.get("active_theme", "default")
        favs = store.get("favorites", [])
        
        # Current theme info
        current = _get_theme(api, active)
        if current:
            api.panel(
                f"  Name: [bold]{current['name']}[/]\n"
                f"  Description: {current['desc']}\n"
                f"  Theme ID: [dim]{active}[/]",
                title="🎨 Active Theme"
            )
        
        # Stats
        custom_count = len(store.get("custom_themes", {}))
        api.print(f"\n  📦 {len(BUILTIN_THEMES)} built-in themes  "
                  f"✨ {custom_count} custom themes  "
                  f"⭐ {len(favs)} favorites\n")
        
        api.rule("Menu")
        api.print("  [bold]b[/]  🎨 Browse all themes")
        api.print("  [bold]f[/]  ⭐ Favorites")
        api.print("  [bold]c[/]  ✏️  Create custom theme")
        api.print("  [bold]i[/]  📥 Import theme")
        api.print("  [bold]h[/]  📜 Theme history")
        api.print("  [bold]s[/]  ⚙️  Settings")
        api.print("  [bold]q[/]  ← Back\n")
        
        choice = api.prompt(">").lower()
        
        if choice == "q":
            return
        elif choice == "b":
            _browse_themes(api)
        elif choice == "f":
            _favorites_screen(api)
        elif choice == "c":
            _create_theme_screen(api)
        elif choice == "i":
            _import_screen(api)
        elif choice == "h":
            _history_screen(api)
        elif choice == "s":
            _settings_screen(api)


def _browse_themes(api):
    """Browse and apply themes."""
    while True:
        api.clear_screen()
        api.show_header("Browse Themes")
        
        store = api.store
        active = store.get("active_theme", "default")
        favs = store.get("favorites", [])
        custom = store.get("custom_themes", {})
        
        # Combine all themes
        all_themes = []
        
        # Built-in themes
        for theme_id, theme in BUILTIN_THEMES.items():
            all_themes.append((theme_id, theme, "builtin"))
        
        # Custom themes
        for theme_id, theme in custom.items():
            all_themes.append((theme_id, theme, "custom"))
        
        # Create table
        tbl = api.table(f"All Themes ({len(all_themes)})")
        tbl.add_column("#", width=4, style="dim")
        tbl.add_column("Name", min_width=25)
        tbl.add_column("Description", min_width=35)
        tbl.add_column("Type", width=8)
        tbl.add_column("Status", width=10)
        
        for idx, (theme_id, theme, theme_type) in enumerate(all_themes, 1):
            status_parts = []
            
            if theme_id == active:
                status_parts.append("[green]●[/]")
            
            if theme_id in favs:
                status_parts.append("⭐")
            
            status = " ".join(status_parts) if status_parts else ""
            
            type_color = "cyan" if theme_type == "builtin" else "magenta"
            
            tbl.add_row(
                str(idx),
                theme["name"],
                theme["desc"],
                f"[{type_color}]{theme_type}[/]",
                status
            )
        
        api.console.print(tbl)
        
        api.print("\n  [dim]Enter number to preview/apply, or:[/]")
        api.print("  [bold]f[/] + number  Toggle favorite")
        api.print("  [bold]e[/] + number  Export theme")
        api.print("  [bold]d[/] + number  Delete custom theme")
        api.print("  [bold]b[/]  Back\n")
        
        choice = api.prompt(">").lower()
        
        if choice == "b":
            return
        
        # Handle favorite toggle
        if choice.startswith("f"):
            try:
                num = int(choice[1:].strip())
                if 1 <= num <= len(all_themes):
                    theme_id = all_themes[num - 1][0]
                    _toggle_favorite(api, theme_id)
                    api.print("  [green]✓ Favorite toggled[/]")
                    api.press_enter()
            except ValueError:
                pass
            continue
        
        # Handle export
        if choice.startswith("e"):
            try:
                num = int(choice[1:].strip())
                if 1 <= num <= len(all_themes):
                    theme_id = all_themes[num - 1][0]
                    filepath = _export_theme(api, theme_id)
                    if filepath:
                        api.print(f"  [green]✓ Exported to:[/] {filepath}")
                    else:
                        api.print("  [red]✗ Export failed[/]")
                    api.press_enter()
            except ValueError:
                pass
            continue
        
        # Handle delete
        if choice.startswith("d"):
            try:
                num = int(choice[1:].strip())
                if 1 <= num <= len(all_themes):
                    theme_id, theme, theme_type = all_themes[num - 1]
                    
                    if theme_type == "builtin":
                        api.print("  [yellow]Cannot delete built-in themes[/]")
                        api.press_enter()
                        continue
                    
                    if api.confirm(f"Delete '{theme['name']}'?", default=False):
                        if _delete_custom_theme(api, theme_id):
                            api.print("  [green]✓ Theme deleted[/]")
                        else:
                            api.print("  [red]✗ Delete failed[/]")
                        api.press_enter()
            except ValueError:
                pass
            continue
        
        # Handle theme selection
        try:
            num = int(choice)
            if 1 <= num <= len(all_themes):
                theme_id, theme, _ = all_themes[num - 1]
                _preview_and_apply(api, theme_id, theme)
        except ValueError:
            pass


def _preview_and_apply(api, theme_id, theme):
    """Preview and optionally apply a theme."""
    api.clear_screen()
    api.show_header("Theme Preview")
    
    # Show theme info
    api.panel(
        f"  Name: [bold]{theme['name']}[/]\n"
        f"  Description: {theme['desc']}\n"
        f"  Theme ID: [dim]{theme_id}[/]",
        title="Theme Info"
    )
    
    # Show color preview
    api.print("\n")
    api.rule("Color Preview")
    
    colors = theme["colors"]
    
    # Create preview table
    tbl = api.table("")
    tbl.add_column("Color Key", style="bold", width=15)
    tbl.add_column("Value", width=20)
    tbl.add_column("Preview", width=30)
    
    for key, value in colors.items():
        # Create preview text
        preview = f"[{value}]████ Sample Text[/]"
        tbl.add_row(key, value, preview)
    
    api.console.print(tbl)
    
    # Preview in context
    api.print("\n")
    api.rule("Context Preview")
    
    # Temporarily apply for preview
    if api.config.get("show_preview", True):
        old_theme = api.theme.copy()
        api.apply_theme(colors)
        
        # Show sample UI elements
        api.panel(
            f"  [{colors.get('success', 'green')}]✓ Success message[/]\n"
            f"  [{colors.get('warning', 'yellow')}]⚠ Warning message[/]\n"
            f"  [{colors.get('error', 'red')}]✗ Error message[/]\n"
            f"  [{colors.get('info', 'cyan')}]ℹ Info message[/]\n"
            f"  [{colors.get('muted', 'dim')}]Muted text[/]",
            title="Sample Messages",
            border_style=colors.get("panel_border", "blue")
        )
        
        # Restore old theme
        api.apply_theme(old_theme)
    
    api.print("\n  [bold]a[/]  Apply this theme")
    api.print("  [bold]f[/]  Toggle favorite")
    api.print("  [bold]e[/]  Export theme")
    api.print("  [bold]b[/]  Back\n")
    
    choice = api.prompt(">").lower()
    
    if choice == "a":
        if _apply_theme(api, theme_id):
            api.print(f"  [green]✓ Applied theme: {theme['name']}[/]")
            api.notify("🎨 Theme Applied", theme["name"])
        else:
            api.print("  [red]✗ Failed to apply theme[/]")
        api.press_enter()
    
    elif choice == "f":
        _toggle_favorite(api, theme_id)
        api.print("  [green]✓ Favorite toggled[/]")
        api.press_enter()
    
    elif choice == "e":
        filepath = _export_theme(api, theme_id)
        if filepath:
            api.print(f"  [green]✓ Exported to:[/] {filepath}")
        else:
            api.print("  [red]✗ Export failed[/]")
        api.press_enter()


def _favorites_screen(api):
    """Show favorite themes."""
    while True:
        api.clear_screen()
        api.show_header("Favorite Themes")
        
        store = api.store
        favs = store.get("favorites", [])
        active = store.get("active_theme", "default")
        
        if not favs:
            api.panel("  No favorite themes yet.\n  Browse themes and press 'f' to add favorites!", 
                     title="⭐ Favorites")
            api.press_enter()
            return
        
        # Build favorites list
        fav_themes = []
        for theme_id in favs:
            theme = _get_theme(api, theme_id)
            if theme:
                fav_themes.append((theme_id, theme))
        
        # Show table
        tbl = api.table(f"⭐ Favorites ({len(fav_themes)})")
        tbl.add_column("#", width=4, style="dim")
        tbl.add_column("Name", min_width=25)
        tbl.add_column("Description", min_width=35)
        tbl.add_column("Active", width=8)
        
        for idx, (theme_id, theme) in enumerate(fav_themes, 1):
            is_active = "[green]●[/]" if theme_id == active else ""
            tbl.add_row(str(idx), theme["name"], theme["desc"], is_active)
        
        api.console.print(tbl)
        
        api.print("\n  Enter number to preview/apply, or [bold]b[/] to go back\n")
        
        choice = api.prompt(">").lower()
        
        if choice == "b":
            return
        
        try:
            num = int(choice)
            if 1 <= num <= len(fav_themes):
                theme_id, theme = fav_themes[num - 1]
                _preview_and_apply(api, theme_id, theme)
        except ValueError:
            pass


def _create_theme_screen(api):
    """Create a custom theme."""
    api.clear_screen()
    api.show_header("Create Custom Theme")
    
    api.print("  Create your own color theme!\n")
    
    # Get theme metadata
    theme_id = api.prompt("Theme ID (lowercase, no spaces)", default="my_theme").lower().replace(" ", "_")
    
    # Check if exists
    if theme_id in BUILTIN_THEMES:
        api.print("  [red]✗ Cannot use built-in theme ID[/]")
        api.press_enter()
        return
    
    custom = api.store.get("custom_themes", {})
    if theme_id in custom:
        if not api.confirm(f"Theme '{theme_id}' exists. Overwrite?", default=False):
            return
    
    name = api.prompt("Theme name", default="My Theme")
    desc = api.prompt("Description", default="My custom theme")
    
    # Color editor
    api.print("\n  [bold]Define colors:[/] (use color names or hex codes)")
    api.print("  Examples: blue, #ff0000, bright_cyan, dim white\n")
    
    colors = {}
    color_keys = [
        ("primary", "Main accent color", "blue"),
        ("secondary", "Secondary accent", "cyan"),
        ("success", "Success messages", "green"),
        ("warning", "Warning messages", "yellow"),
        ("error", "Error messages", "red"),
        ("info", "Info messages", "cyan"),
        ("muted", "Muted/dim text", "dim white"),
        ("border", "Border color", "blue"),
        ("header", "Header style", "bold blue"),
        ("panel_border", "Panel borders", "blue"),
    ]
    
    for key, label, default in color_keys:
        value = api.prompt(f"  {label} ({key})", default=default)
        colors[key] = value
    
    # Confirm
    api.print("\n")
    if api.confirm("Save this theme?", default=True):
        _create_custom_theme(api, theme_id, name, desc, colors)
        api.print(f"  [green]✓ Created theme: {name}[/]")
        
        if api.confirm("Apply now?", default=True):
            _apply_theme(api, theme_id)
    
    api.press_enter()


def _import_screen(api):
    """Import a theme from file."""
    api.clear_screen()
    api.show_header("Import Theme")
    
    api.print("  Import a theme from a JSON file.\n")
    api.print("  Enter the file path relative to ~/.taskflow/")
    api.print("  Example: plugin_data/theme_custom_20260322_120000.json\n")
    
    filepath = api.prompt("File path")
    
    if not filepath:
        return
    
    success, result = _import_theme(api, filepath)
    
    if success:
        api.print(f"  [green]✓ Imported theme: {result}[/]")
        
        if api.confirm("Apply now?", default=True):
            _apply_theme(api, result)
    else:
        api.print(f"  [red]✗ Import failed: {result}[/]")
    
    api.press_enter()


def _history_screen(api):
    """Show theme change history."""
    api.clear_screen()
    api.show_header("Theme History")
    
    history = api.store.get("theme_history", [])
    
    if not history:
        api.panel("  No theme history yet.", title="📜 History")
        api.press_enter()
        return
    
    tbl = api.table(f"Recent Theme Changes ({len(history)})")
    tbl.add_column("#", width=4, style="dim")
    tbl.add_column("Theme", min_width=25)
    tbl.add_column("Applied", width=20, style="dim")
    
    for idx, entry in enumerate(history[:20], 1):
        theme_id = entry["theme_id"]
        theme = _get_theme(api, theme_id)
        theme_name = theme["name"] if theme else f"[dim]{theme_id}[/]"
        
        timestamp = datetime.fromisoformat(entry["timestamp"])
        time_str = timestamp.strftime("%Y-%m-%d %H:%M")
        
        tbl.add_row(str(idx), theme_name, time_str)
    
    api.console.print(tbl)
    
    api.print("\n  Enter number to reapply a theme, or [bold]b[/] to go back\n")
    
    choice = api.prompt(">").lower()
    
    if choice == "b":
        return
    
    try:
        num = int(choice)
        if 1 <= num <= len(history):
            theme_id = history[num - 1]["theme_id"]
            theme = _get_theme(api, theme_id)
            
            if theme:
                if _apply_theme(api, theme_id):
                    api.print(f"  [green]✓ Reapplied: {theme['name']}[/]")
                else:
                    api.print("  [red]✗ Failed to apply[/]")
            else:
                api.print("  [red]✗ Theme not found[/]")
            
            api.press_enter()
    except ValueError:
        pass


def _settings_screen(api):
    """Plugin settings."""
    api.clear_screen()
    api.show_header("Theme Settings")
    
    config = api.config
    
    api.panel(
        f"  Auto-apply theme on startup: [cyan]{'Yes' if config.get('auto_apply', True) else 'No'}[/]\n"
        f"  Show color preview: [cyan]{'Yes' if config.get('show_preview', True) else 'No'}[/]",
        title="⚙️ Settings"
    )
    
    api.print("\n  [bold]1[/]  Toggle auto-apply on startup")
    api.print("  [bold]2[/]  Toggle color preview")
    api.print("  [bold]r[/]  Reset to default theme")
    api.print("  [bold]c[/]  Clear theme history")
    api.print("  [bold]b[/]  Back\n")
    
    choice = api.prompt(">").lower()
    
    if choice == "1":
        config["auto_apply"] = not config.get("auto_apply", True)
        api.config_save()
        api.print("  [green]✓ Updated[/]")
        api.press_enter()
        _settings_screen(api)
    
    elif choice == "2":
        config["show_preview"] = not config.get("show_preview", True)
        api.config_save()
        api.print("  [green]✓ Updated[/]")
        api.press_enter()
        _settings_screen(api)
    
    elif choice == "r":
        if api.confirm("Reset to default theme?", default=False):
            _apply_theme(api, "default")
            api.print("  [green]✓ Reset to default[/]")
            api.press_enter()
    
    elif choice == "c":
        if api.confirm("Clear all theme history?", default=False):
            api.store["theme_history"] = []
            api.store_save()
            api.print("  [green]✓ History cleared[/]")
            api.press_enter()
    
    elif choice == "b":
        return


# ══════════════════════════════════════════════════════════════
# PUBLIC API (for other plugins)
# ══════════════════════════════════════════════════════════════

def get_active_theme(api):
    """Get currently active theme ID."""
    return api.store.get("active_theme", "default")


def get_theme_colors(api, theme_id=None):
    """Get colors for a theme (active if None)."""
    if theme_id is None:
        theme_id = get_active_theme(api)
    
    theme = _get_theme(api, theme_id)
    return theme["colors"] if theme else None


def list_themes(api):
    """List all available themes."""
    themes = []
    
    # Built-in
    for theme_id, theme in BUILTIN_THEMES.items():
        themes.append({
            "id": theme_id,
            "name": theme["name"],
            "type": "builtin"
        })
    
    # Custom
    custom = api.store.get("custom_themes", {})
    for theme_id, theme in custom.items():
        themes.append({
            "id": theme_id,
            "name": theme["name"],
            "type": "custom"
        })
    
    return themes


def apply_theme_by_id(api, theme_id):
    """Apply a theme programmatically (for other plugins)."""
    return _apply_theme(api, theme_id)


# ══════════════════════════════════════════════════════════════
# MENU INTEGRATION
# ══════════════════════════════════════════════════════════════

def menu_items(api):
    """Add menu entry."""
    store = api.store
    active = store.get("active_theme", "default")
    theme = _get_theme(api, active)
    
    theme_name = theme["name"] if theme else "Unknown"
    label = f"🎨 Themes [dim]({theme_name})[/]"
    
    return [("T", label, lambda: _main_screen(api))]


# ══════════════════════════════════════════════════════════════
# DASHBOARD WIDGET
# ══════════════════════════════════════════════════════════════

def dashboard_widgets(api):
    """Show active theme in dashboard."""
    store = api.store
    active = store.get("active_theme", "default")
    theme = _get_theme(api, active)
    
    if not theme:
        return []
    
    return [f"  🎨 Theme: [{api.theme.get('primary', 'blue')}]{theme['name']}[/]"]
