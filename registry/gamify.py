"""
TaskFlow Plugin — Streak & Gamification
Drop into ~/.taskflow/plugins/gamify.py
"""
PLUGIN_NAME    = "Gamify"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "XP, levels, streaks and achievement badges"

from datetime import datetime, timedelta, date

# ── XP values ────────────────────────────────────────────────────────────────
XP_DONE      = {"Critical":50, "High":30, "Medium":15, "Low":8, "Minimal":3}
XP_STREAK    = 10   # bonus per day streak
XP_ON_TIME   = 20   # bonus for completing before deadline

# ── Level thresholds ─────────────────────────────────────────────────────────
LEVELS = [
    (0,    "🌱 Seedling"),
    (100,  "⚡ Starter"),
    (300,  "🔥 Momentum"),
    (600,  "💪 Grinder"),
    (1000, "🚀 Achiever"),
    (1500, "🏆 Champion"),
    (2500, "💎 Legend"),
    (4000, "👑 Master"),
]

# ── Badges ────────────────────────────────────────────────────────────────────
BADGES = {
    "first_task":    ("🎯", "First Blood",       "Complete your first task"),
    "streak_3":      ("🔥", "On Fire",           "3-day completion streak"),
    "streak_7":      ("💥", "Week Warrior",      "7-day completion streak"),
    "streak_30":     ("🌟", "Monthly Hero",      "30-day completion streak"),
    "speed_demon":   ("⚡", "Speed Demon",       "Complete 5 tasks in one day"),
    "century":       ("💯", "Century",           "Complete 100 tasks total"),
    "critic":        ("🔴", "Critical Thinker",  "Complete 10 Critical tasks"),
    "night_owl":     ("🦉", "Night Owl",         "Complete a task after 22:00"),
    "early_bird":    ("🐦", "Early Bird",        "Complete a task before 07:00"),
    "on_time_10":    ("✅", "Punctual",          "Complete 10 tasks on time"),
    "category_5":    ("📚", "Well-Rounded",      "Use 5 different categories"),
}


def _get_level(xp: int) -> tuple[str, int, int]:
    """Returns (label, current_floor, next_floor)."""
    label, floor, nxt = LEVELS[0][1], 0, LEVELS[1][0]
    for i, (thresh, lbl) in enumerate(LEVELS):
        if xp >= thresh:
            label = lbl
            floor = thresh
            nxt   = LEVELS[i+1][0] if i+1 < len(LEVELS) else thresh + 9999
    return label, floor, nxt


def _compute_xp_and_badges(tasks: list) -> tuple[int, list, int]:
    """Recompute XP, badges earned, and current streak from task history."""
    xp       = 0
    badges   = []
    done     = [t for t in tasks if t.get("status") == "done" and t.get("completed_at")]
    done_srt = sorted(done, key=lambda t: t["completed_at"])

    # XP from tasks
    on_time_count = 0
    critical_done = 0
    for t in done_srt:
        p = t.get("priority", "Medium")
        xp += XP_DONE.get(p, 15)
        if t.get("due_date"):
            try:
                if datetime.fromisoformat(t["completed_at"]) <= datetime.fromisoformat(t["due_date"]):
                    xp += XP_ON_TIME
                    on_time_count += 1
            except Exception:
                pass
        if p == "Critical":
            critical_done += 1

    # Streak XP
    dates = set()
    for t in done_srt:
        try: dates.add(datetime.fromisoformat(t["completed_at"]).date())
        except Exception: pass
    streak = 0
    check  = date.today()
    while check in dates:
        streak += 1
        xp     += XP_STREAK
        check  -= timedelta(days=1)

    # Badge logic
    if len(done) >= 1:        badges.append("first_task")
    if streak >= 3:           badges.append("streak_3")
    if streak >= 7:           badges.append("streak_7")
    if streak >= 30:          badges.append("streak_30")
    if on_time_count >= 10:   badges.append("on_time_10")
    if len(done) >= 100:      badges.append("century")
    if critical_done >= 10:   badges.append("critic")

    # Tasks per day
    day_cnt = {}
    for t in done_srt:
        try:
            d = datetime.fromisoformat(t["completed_at"]).date().isoformat()
            day_cnt[d] = day_cnt.get(d, 0) + 1
        except Exception: pass
    if any(v >= 5 for v in day_cnt.values()):
        badges.append("speed_demon")

    # Night owl / early bird
    for t in done_srt:
        try:
            h = datetime.fromisoformat(t["completed_at"]).hour
            if h >= 22: badges.append("night_owl")
            if h < 7:   badges.append("early_bird")
        except Exception: pass

    # Categories
    cats = {t.get("category") for t in done_srt if t.get("category")}
    if len(cats) >= 5: badges.append("category_5")

    return xp, list(set(badges)), streak


def _gamify_screen(api):
    from rich.prompt import Prompt
    from rich.table  import Table
    from rich.panel  import Panel
    from rich.text   import Text
    from rich        import box as rbox
    from rich.rule   import Rule
    import os

    console = api.console
    tasks   = api.tasks

    os.system("clear")
    console.print()
    console.print("  [bold #00e5ff]⚡ TaskFlow  ·  🏆 Achievements[/]")
    console.print()

    xp, badges, streak = _compute_xp_and_badges(tasks)
    level_lbl, floor, nxt = _get_level(xp)

    # XP progress bar
    prog     = xp - floor
    prog_max = nxt - floor
    filled   = int(30 * prog / max(prog_max, 1))
    bar      = "█" * filled + "░" * (30 - filled)

    done = [t for t in tasks if t.get("status") == "done"]

    console.print(Panel(
        f"  [bold #00e5ff]{level_lbl}[/]   [bold]{xp}[/] XP\n"
        f"  [#00b4d8]{bar}[/]  {prog}/{prog_max} → next level\n"
        f"  🔥 Streak: [bold]{streak}[/] day{'s' if streak != 1 else ''}   "
        f"  ✅ Completed: [bold]{len(done)}[/] tasks",
        border_style="#00b4d8", padding=(0, 1)
    ))
    console.print()

    # Badge table
    tbl = Table(box=rbox.ROUNDED, border_style="#1a2a44",
                header_style="bold #00b4d8", padding=(0, 2),
                title="[bold #00b4d8]Badges[/]", title_justify="left")
    tbl.add_column("",      width=4)
    tbl.add_column("Name",  width=18)
    tbl.add_column("Description", min_width=28)
    tbl.add_column("",      width=8)

    for bid, (icon, name, desc) in BADGES.items():
        earned = bid in badges
        status = "[green]earned[/]" if earned else "[dim]locked[/]"
        row_icon = icon if earned else "[dim]?[/]"
        row_name = name if earned else Text(name, style="dim")
        row_desc = desc if earned else Text(desc, style="dim")
        tbl.add_row(row_icon, row_name, row_desc, status)
    console.print(tbl)

    # Next badge hint
    locked = [bid for bid in BADGES if bid not in badges]
    if locked:
        console.print()
        next_bid  = locked[0]
        icon, nm, desc = BADGES[next_bid]
        console.print(Panel(
            f"  Next: [bold]{icon} {nm}[/]  ·  [dim]{desc}[/]",
            border_style="#1a2a44", padding=(0, 0)
        ))

    console.print()
    Prompt.ask("  [dim]Press Enter to continue[/]", default="")


def on_task_done(api, task):
    """Fire a congrats notification with XP gained."""
    xp_gain = XP_DONE.get(task.get("priority","Medium"), 15)
    if task.get("due_date"):
        try:
            if (datetime.fromisoformat(task["completed_at"])
                    <= datetime.fromisoformat(task["due_date"])):
                xp_gain += XP_ON_TIME
        except Exception:
            pass
    xp_total, badges, streak = _compute_xp_and_badges(api.tasks)
    lvl, _, _ = _get_level(xp_total)
    api.notify(
        f"✅ +{xp_gain} XP",
        f"{task['name'][:40]}\n{lvl}  ·  {xp_total} XP total"
    )


def on_startup(api):
    pass


def menu_items(api):
    return [("g", "🏆 Achievements & XP", lambda: _gamify_screen(api))]
