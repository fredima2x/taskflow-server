"""
TaskFlow Gamification Plugin
Adds XP, levels, achievements, streaks, and rewards to task completion.
"""

PLUGIN_NAME        = "Gamify"
PLUGIN_VERSION     = "1.0.0"
PLUGIN_DESC        = "Level up by completing tasks! Earn XP, unlock achievements, and track streaks."
PLUGIN_AUTHOR      = "TaskFlow Community"
PLUGIN_TAGS        = "gamification, productivity, motivation"
PLUGIN_MIN_API     = "3.0"
PLUGIN_PERMISSIONS = ["notifications", "storage_write"]

from datetime import datetime, timedelta
import math


# ══════════════════════════════════════════════════════════════
# XP & LEVEL SYSTEM
# ══════════════════════════════════════════════════════════════

XP_TABLE = {
    "Critical": 50,
    "High":     30,
    "Medium":   15,
    "Low":      8,
}

def xp_for_level(level):
    """XP needed to reach next level (exponential curve)."""
    return int(100 * (1.5 ** (level - 1)))

def level_from_xp(xp):
    """Calculate current level from total XP."""
    level = 1
    total = 0
    while total + xp_for_level(level) <= xp:
        total += xp_for_level(level)
        level += 1
    return level, xp - total, xp_for_level(level)


# ══════════════════════════════════════════════════════════════
# ACHIEVEMENTS
# ══════════════════════════════════════════════════════════════

ACHIEVEMENTS = {
    "first_blood": {
        "name": "🎯 First Blood",
        "desc": "Complete your first task",
        "check": lambda s: s.get("tasks_completed", 0) >= 1,
        "xp": 10,
    },
    "task_master_10": {
        "name": "⭐ Task Master",
        "desc": "Complete 10 tasks",
        "check": lambda s: s.get("tasks_completed", 0) >= 10,
        "xp": 50,
    },
    "task_master_50": {
        "name": "⭐⭐ Task Legend",
        "desc": "Complete 50 tasks",
        "check": lambda s: s.get("tasks_completed", 0) >= 50,
        "xp": 200,
    },
    "task_master_100": {
        "name": "⭐⭐⭐ Task Hero",
        "desc": "Complete 100 tasks",
        "check": lambda s: s.get("tasks_completed", 0) >= 100,
        "xp": 500,
    },
    "critical_crusher": {
        "name": "🔥 Critical Crusher",
        "desc": "Complete 5 Critical priority tasks",
        "check": lambda s: s.get("critical_completed", 0) >= 5,
        "xp": 100,
    },
    "speed_demon": {
        "name": "⚡ Speed Demon",
        "desc": "Complete a task in under 1 hour",
        "check": lambda s: s.get("fastest_task", 999) < 1.0,
        "xp": 30,
    },
    "week_warrior": {
        "name": "📅 Week Warrior",
        "desc": "Maintain a 7-day streak",
        "check": lambda s: s.get("current_streak", 0) >= 7,
        "xp": 150,
    },
    "month_master": {
        "name": "📆 Month Master",
        "desc": "Maintain a 30-day streak",
        "check": lambda s: s.get("current_streak", 0) >= 30,
        "xp": 500,
    },
    "early_bird": {
        "name": "🌅 Early Bird",
        "desc": "Complete a task before 8 AM",
        "check": lambda s: s.get("early_bird_unlocked", False),
        "xp": 25,
    },
    "night_owl": {
        "name": "🦉 Night Owl",
        "desc": "Complete a task after 10 PM",
        "check": lambda s: s.get("night_owl_unlocked", False),
        "xp": 25,
    },
    "perfectionist": {
        "name": "💎 Perfectionist",
        "desc": "Complete 10 tasks with estimated hours",
        "check": lambda s: s.get("estimated_tasks", 0) >= 10,
        "xp": 75,
    },
}


# ══════════════════════════════════════════════════════════════
# LIFECYCLE HOOKS
# ══════════════════════════════════════════════════════════════

def install(api):
    """First-time setup."""
    store = api.store
    store["total_xp"] = 0
    store["tasks_completed"] = 0
    store["critical_completed"] = 0
    store["high_completed"] = 0
    store["medium_completed"] = 0
    store["low_completed"] = 0
    store["estimated_tasks"] = 0
    store["fastest_task"] = 999
    store["current_streak"] = 0
    store["longest_streak"] = 0
    store["last_completion"] = None
    store["achievements"] = []
    store["early_bird_unlocked"] = False
    store["night_owl_unlocked"] = False
    store["daily_xp"] = {}
    api.store_save()
    
    api.config["show_level_in_header"] = True
    api.config["notify_on_levelup"] = True
    api.config["notify_on_achievement"] = True
    api.config_save()
    
    api.log("Gamify plugin installed")
    api.notify("🎮 Gamify", "Plugin installed! Complete tasks to earn XP and level up!")


def on_startup(api):
    """Register widgets and actions."""
    
    # Dashboard widget
    def gamify_widget(api):
        store = api.store
        xp = store.get("total_xp", 0)
        level, current_xp, needed_xp = level_from_xp(xp)
        progress = int(current_xp / needed_xp * 20) if needed_xp else 20
        bar = "█" * progress + "░" * (20 - progress)
        streak = store.get("current_streak", 0)
        
        return (
            f"  🎮 [bold]Level {level}[/]  "
            f"[{api.theme.get('secondary', 'cyan')}]{bar}[/] "
            f"{current_xp}/{needed_xp} XP  "
            f"🔥 {streak} day streak"
        )
    
    api.register_dashboard_widget(gamify_widget)
    
    # Task action: Show XP preview
    def show_xp_preview(task):
        priority = task.get("priority", "Medium")
        xp = XP_TABLE.get(priority, 15)
        api.panel(
            f"  Priority: [bold]{priority}[/]\n"
            f"  XP Reward: [green]+{xp} XP[/]\n"
            f"  \n"
            f"  Complete this task to earn experience!",
            title="🎮 XP Preview"
        )
        api.press_enter()
    
    api.register_task_action("X", "🎮 XP Preview", show_xp_preview)
    
    # Check streak on startup
    _check_streak(api)


def on_task_done(api, task):
    """Award XP and check achievements when task is completed."""
    store = api.store
    
    # Calculate XP
    priority = task.get("priority", "Medium")
    base_xp = XP_TABLE.get(priority, 15)
    
    # Bonus XP for estimated hours
    bonus_xp = 0
    if task.get("estimated_hours"):
        bonus_xp = 5
        store["estimated_tasks"] = store.get("estimated_tasks", 0) + 1
    
    total_xp = base_xp + bonus_xp
    
    # Track completion time for achievements
    hour = datetime.now().hour
    if hour < 8:
        store["early_bird_unlocked"] = True
    if hour >= 22:
        store["night_owl_unlocked"] = True
    
    # Track fastest task
    if task.get("actual_hours"):
        fastest = store.get("fastest_task", 999)
        if task["actual_hours"] < fastest:
            store["fastest_task"] = task["actual_hours"]
    
    # Update stats
    old_xp = store.get("total_xp", 0)
    store["total_xp"] = old_xp + total_xp
    store["tasks_completed"] = store.get("tasks_completed", 0) + 1
    
    # Track by priority
    priority_key = f"{priority.lower()}_completed"
    store[priority_key] = store.get(priority_key, 0) + 1
    
    # Update streak
    _update_streak(api)
    
    # Track daily XP
    today = datetime.now().strftime("%Y-%m-%d")
    daily = store.get("daily_xp", {})
    daily[today] = daily.get(today, 0) + total_xp
    store["daily_xp"] = daily
    
    api.store_save()
    
    # Check for level up
    old_level = level_from_xp(old_xp)[0]
    new_level = level_from_xp(store["total_xp"])[0]
    
    if new_level > old_level:
        _level_up(api, new_level)
    
    # Check achievements
    _check_achievements(api)
    
    # Notify
    msg = f"+{total_xp} XP"
    if bonus_xp:
        msg += f" (+{bonus_xp} bonus)"
    
    api.notify("🎮 Task Complete!", msg)
    
    # Emit event for other plugins
    api.emit("gamify:xp_gained", amount=total_xp, task=task, reason="task_done")


# ══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════

def _update_streak(api):
    """Update completion streak."""
    store = api.store
    today = datetime.now().date()
    last = store.get("last_completion")
    
    if last:
        last_date = datetime.fromisoformat(last).date()
        diff = (today - last_date).days
        
        if diff == 0:
            # Same day, no change
            pass
        elif diff == 1:
            # Consecutive day
            store["current_streak"] = store.get("current_streak", 0) + 1
        else:
            # Streak broken
            store["current_streak"] = 1
    else:
        # First completion
        store["current_streak"] = 1
    
    # Update longest streak
    current = store.get("current_streak", 0)
    longest = store.get("longest_streak", 0)
    if current > longest:
        store["longest_streak"] = current
    
    store["last_completion"] = today.isoformat()
    api.store_save()


def _check_streak(api):
    """Check if streak should be reset (called on startup)."""
    store = api.store
    last = store.get("last_completion")
    
    if not last:
        return
    
    last_date = datetime.fromisoformat(last).date()
    today = datetime.now().date()
    diff = (today - last_date).days
    
    if diff > 1:
        # Streak broken
        old_streak = store.get("current_streak", 0)
        if old_streak > 0:
            api.log(f"Streak broken: was {old_streak} days", "warn")
            store["current_streak"] = 0
            api.store_save()


def _level_up(api, new_level):
    """Handle level up."""
    if api.config.get("notify_on_levelup", True):
        api.notify("🎉 LEVEL UP!", f"You reached Level {new_level}!")
    
    api.log(f"Level up! Now level {new_level}")
    api.emit("gamify:level_up", level=new_level)


def _check_achievements(api):
    """Check and unlock achievements."""
    store = api.store
    unlocked = store.get("achievements", [])
    
    for ach_id, ach in ACHIEVEMENTS.items():
        if ach_id in unlocked:
            continue
        
        if ach["check"](store):
            # Unlock!
            unlocked.append(ach_id)
            store["achievements"] = unlocked
            
            # Award bonus XP
            store["total_xp"] = store.get("total_xp", 0) + ach["xp"]
            api.store_save()
            
            if api.config.get("notify_on_achievement", True):
                api.notify(
                    f"🏆 Achievement Unlocked!",
                    f"{ach['name']}\n{ach['desc']}\n+{ach['xp']} XP"
                )
            
            api.log(f"Achievement unlocked: {ach['name']}")
            api.emit("gamify:achievement_unlocked", achievement=ach_id, xp=ach["xp"])


# ══════════════════════════════════════════════════════════════
# PUBLIC API (for other plugins)
# ══════════════════════════════════════════════════════════════

def award_xp(api, amount, reason="manual"):
    """Award XP manually (callable by other plugins)."""
    store = api.store
    old_xp = store.get("total_xp", 0)
    store["total_xp"] = old_xp + amount
    api.store_save()
    
    old_level = level_from_xp(old_xp)[0]
    new_level = level_from_xp(store["total_xp"])[0]
    
    if new_level > old_level:
        _level_up(api, new_level)
    
    api.emit("gamify:xp_gained", amount=amount, reason=reason)
    return new_level


def get_level(api):
    """Get current level (callable by other plugins)."""
    xp = api.store.get("total_xp", 0)
    return level_from_xp(xp)[0]


def get_stats(api):
    """Get all gamification stats (callable by other plugins)."""
    store = api.store
    xp = store.get("total_xp", 0)
    level, current_xp, needed_xp = level_from_xp(xp)
    
    return {
        "level": level,
        "total_xp": xp,
        "current_xp": current_xp,
        "needed_xp": needed_xp,
        "tasks_completed": store.get("tasks_completed", 0),
        "current_streak": store.get("current_streak", 0),
        "longest_streak": store.get("longest_streak", 0),
        "achievements": len(store.get("achievements", [])),
        "total_achievements": len(ACHIEVEMENTS),
    }


# ══════════════════════════════════════════════════════════════
# UI SCREENS
# ══════════════════════════════════════════════════════════════

def _main_screen(api):
    """Main gamification dashboard."""
    while True:
        api.clear_screen()
        api.show_header("Gamification")
        
        store = api.store
        xp = store.get("total_xp", 0)
        level, current_xp, needed_xp = level_from_xp(xp)
        progress_pct = (current_xp / needed_xp * 100) if needed_xp else 100
        
        # Level & XP Panel
        progress_bar = "█" * int(progress_pct / 5) + "░" * (20 - int(progress_pct / 5))
        api.panel(
            f"  Level: [bold cyan]{level}[/]\n"
            f"  XP: [{api.theme.get('secondary', 'cyan')}]{progress_bar}[/] {current_xp}/{needed_xp}\n"
            f"  Total XP: [green]{xp:,}[/]\n"
            f"  Progress: [yellow]{progress_pct:.1f}%[/]",
            title="📊 Level & Experience"
        )
        
        # Stats Panel
        streak = store.get("current_streak", 0)
        longest = store.get("longest_streak", 0)
        completed = store.get("tasks_completed", 0)
        
        api.panel(
            f"  Tasks Completed: [green]{completed}[/]\n"
            f"  Current Streak: [yellow]🔥 {streak} days[/]\n"
            f"  Longest Streak: [cyan]⭐ {longest} days[/]\n"
            f"  Achievements: [magenta]{len(store.get('achievements', []))}/{len(ACHIEVEMENTS)}[/]",
            title="📈 Statistics"
        )
        
        # Priority Breakdown
        tbl = api.table("Task Breakdown by Priority")
        tbl.add_column("Priority", style="bold")
        tbl.add_column("Completed", justify="right")
        tbl.add_column("XP Each", justify="right")
        tbl.add_column("Total XP", justify="right", style="green")
        
        for priority in ["Critical", "High", "Medium", "Low"]:
            key = f"{priority.lower()}_completed"
            count = store.get(key, 0)
            xp_each = XP_TABLE[priority]
            total = count * xp_each
            
            color = {"Critical": "red", "High": "yellow", "Medium": "cyan", "Low": "dim"}.get(priority, "white")
            tbl.add_row(
                f"[{color}]{priority}[/]",
                str(count),
                f"+{xp_each}",
                f"{total:,}"
            )
        
        api.console.print(tbl)
        
        # Menu
        api.rule("Menu")
        api.print("  [bold]a[/]  🏆 Achievements")
        api.print("  [bold]s[/]  📊 Detailed Stats")
        api.print("  [bold]l[/]  📈 Leaderboard (XP History)")
        api.print("  [bold]c[/]  ⚙️  Settings")
        api.print("  [bold]b[/]  ← Back\n")
        
        choice = api.prompt(">").lower()
        
        if choice == "b":
            return
        elif choice == "a":
            _achievements_screen(api)
        elif choice == "s":
            _stats_screen(api)
        elif choice == "l":
            _leaderboard_screen(api)
        elif choice == "c":
            _settings_screen(api)


def _achievements_screen(api):
    """Show all achievements with unlock status."""
    api.clear_screen()
    api.show_header("Achievements")
    
    store = api.store
    unlocked = store.get("achievements", [])
    
    tbl = api.table(f"Achievements ({len(unlocked)}/{len(ACHIEVEMENTS)} unlocked)")
    tbl.add_column("Status", width=8)
    tbl.add_column("Achievement", min_width=25)
    tbl.add_column("Description", min_width=30)
    tbl.add_column("XP", justify="right", width=8)
    
    for ach_id, ach in ACHIEVEMENTS.items():
        is_unlocked = ach_id in unlocked
        status = "[green]✓[/]" if is_unlocked else "[dim]🔒[/]"
        name = ach["name"] if is_unlocked else f"[dim]{ach['name']}[/]"
        desc = ach["desc"] if is_unlocked else f"[dim]{ach['desc']}[/]"
        xp = f"[green]+{ach['xp']}[/]" if is_unlocked else f"[dim]+{ach['xp']}[/]"
        
        tbl.add_row(status, name, desc, xp)
    
    api.console.print(tbl)
    
    # Progress summary
    unlocked_xp = sum(ACHIEVEMENTS[a]["xp"] for a in unlocked)
    total_xp = sum(a["xp"] for a in ACHIEVEMENTS.values())
    
    api.print(f"\n  Total Achievement XP: [green]{unlocked_xp}[/] / {total_xp}")
    api.press_enter()


def _stats_screen(api):
    """Detailed statistics screen."""
    api.clear_screen()
    api.show_header("Detailed Statistics")
    
    store = api.store
    
    # General Stats
    api.panel(
        f"  Total Tasks Completed: [green]{store.get('tasks_completed', 0)}[/]\n"
        f"  Total XP Earned: [cyan]{store.get('total_xp', 0):,}[/]\n"
        f"  Current Level: [bold yellow]{level_from_xp(store.get('total_xp', 0))[0]}[/]\n"
        f"  Current Streak: [yellow]🔥 {store.get('current_streak', 0)} days[/]\n"
        f"  Longest Streak: [cyan]⭐ {store.get('longest_streak', 0)} days[/]\n"
        f"  Achievements Unlocked: [magenta]{len(store.get('achievements', []))}/{len(ACHIEVEMENTS)}[/]",
        title="📊 Overview"
    )
    
    # Speed Records
    fastest = store.get("fastest_task", 999)
    fastest_str = f"{fastest:.1f}h" if fastest < 999 else "N/A"
    
    api.panel(
        f"  Fastest Task Completion: [green]{fastest_str}[/]\n"
        f"  Tasks with Time Estimates: [cyan]{store.get('estimated_tasks', 0)}[/]\n"
        f"  Early Bird Tasks (before 8 AM): [yellow]{'✓' if store.get('early_bird_unlocked') else '✗'}[/]\n"
        f"  Night Owl Tasks (after 10 PM): [blue]{'✓' if store.get('night_owl_unlocked') else '✗'}[/]",
        title="⚡ Records & Milestones"
    )
    
    # XP by Priority
    tbl = api.table("XP Distribution")
    tbl.add_column("Priority", style="bold")
    tbl.add_column("Tasks", justify="right")
    tbl.add_column("XP per Task", justify="right")
    tbl.add_column("Total XP", justify="right", style="green")
    tbl.add_column("% of Total", justify="right")
    
    total_xp = store.get("total_xp", 0)
    
    for priority in ["Critical", "High", "Medium", "Low"]:
        key = f"{priority.lower()}_completed"
        count = store.get(key, 0)
        xp_each = XP_TABLE[priority]
        priority_total = count * xp_each
        percentage = (priority_total / total_xp * 100) if total_xp else 0
        
        color = {"Critical": "red", "High": "yellow", "Medium": "cyan", "Low": "dim"}.get(priority)
        tbl.add_row(
            f"[{color}]{priority}[/]",
            str(count),
            f"+{xp_each}",
            f"{priority_total:,}",
            f"{percentage:.1f}%"
        )
    
    api.console.print(tbl)
    
    # Last 7 days XP
    _show_weekly_xp(api)
    
    api.press_enter()


def _show_weekly_xp(api):
    """Show XP earned in the last 7 days."""
    store = api.store
    daily_xp = store.get("daily_xp", {})
    
    api.print("\n")
    api.rule("Last 7 Days XP")
    
    today = datetime.now().date()
    dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
    
    tbl = api.table("")
    tbl.add_column("Date", style="bold")
    tbl.add_column("Day", style="dim")
    tbl.add_column("XP Earned", justify="right", style="green")
    tbl.add_column("Graph", min_width=20)
    
    max_xp = max([daily_xp.get(d, 0) for d in dates] + [1])
    
    for date_str in dates:
        xp = daily_xp.get(date_str, 0)
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        day_name = date_obj.strftime("%a")
        
        # Visual bar
        bar_len = int(xp / max_xp * 15) if max_xp else 0
        bar = "█" * bar_len
        
        # Highlight today
        date_display = f"[bold]{date_str}[/]" if date_str == today.strftime("%Y-%m-%d") else date_str
        
        tbl.add_row(date_display, day_name, f"+{xp}", bar)
    
    api.console.print(tbl)
    
    week_total = sum(daily_xp.get(d, 0) for d in dates)
    api.print(f"\n  Weekly Total: [green bold]+{week_total} XP[/]")


def _leaderboard_screen(api):
    """Show XP history and progress over time."""
    api.clear_screen()
    api.show_header("XP History")
    
    _show_weekly_xp(api)
    
    store = api.store
    daily_xp = store.get("daily_xp", {})
    
    # All-time stats
    if daily_xp:
        dates = sorted(daily_xp.keys())
        first_date = dates[0]
        total_days = len(dates)
        avg_xp = store.get("total_xp", 0) / total_days if total_days else 0
        best_day = max(daily_xp.items(), key=lambda x: x[1])
        
        api.print("\n")
        api.panel(
            f"  First Activity: [cyan]{first_date}[/]\n"
            f"  Active Days: [green]{total_days}[/]\n"
            f"  Average XP/Day: [yellow]{avg_xp:.1f}[/]\n"
            f"  Best Day: [bold]{best_day[0]}[/] ([green]+{best_day[1]} XP[/])",
            title="📈 All-Time Stats"
        )
    
    api.press_enter()


def _settings_screen(api):
    """Plugin settings."""
    api.clear_screen()
    api.show_header("Gamification Settings")
    
    config = api.config
    
    api.panel(
        f"  Show level in header: [cyan]{'Yes' if config.get('show_level_in_header', True) else 'No'}[/]\n"
        f"  Notify on level up: [cyan]{'Yes' if config.get('notify_on_levelup', True) else 'No'}[/]\n"
        f"  Notify on achievement: [cyan]{'Yes' if config.get('notify_on_achievement', True) else 'No'}[/]",
        title="⚙️ Current Settings"
    )
    
    api.print("\n  [bold]1[/]  Toggle level in header")
    api.print("  [bold]2[/]  Toggle level-up notifications")
    api.print("  [bold]3[/]  Toggle achievement notifications")
    api.print("  [bold]r[/]  Reset all stats (WARNING!)")
    api.print("  [bold]b[/]  Back\n")
    
    choice = api.prompt(">").lower()
    
    if choice == "1":
        config["show_level_in_header"] = not config.get("show_level_in_header", True)
        api.config_save()
        api.print("  [green]✓ Updated[/]")
        api.press_enter()
    
    elif choice == "2":
        config["notify_on_levelup"] = not config.get("notify_on_levelup", True)
        api.config_save()
        api.print("  [green]✓ Updated[/]")
        api.press_enter()
    
    elif choice == "3":
        config["notify_on_achievement"] = not config.get("notify_on_achievement", True)
        api.config_save()
        api.print("  [green]✓ Updated[/]")
        api.press_enter()
    
    elif choice == "r":
        if api.confirm("⚠️  Reset ALL gamification data? This cannot be undone!", default=False):
            store = api.store
            store.clear()
            store["total_xp"] = 0
            store["tasks_completed"] = 0
            store["critical_completed"] = 0
            store["high_completed"] = 0
            store["medium_completed"] = 0
            store["low_completed"] = 0
            store["estimated_tasks"] = 0
            store["fastest_task"] = 999
            store["current_streak"] = 0
            store["longest_streak"] = 0
            store["last_completion"] = None
            store["achievements"] = []
            store["early_bird_unlocked"] = False
            store["night_owl_unlocked"] = False
            store["daily_xp"] = {}
            api.store_save()
            
            api.print("  [yellow]All stats have been reset.[/]")
            api.press_enter()
    
    elif choice == "b":
        return
    
    # Loop back to settings
    _settings_screen(api)


# ══════════════════════════════════════════════════════════════
# MENU INTEGRATION
# ══════════════════════════════════════════════════════════════

def menu_items(api):
    """Add menu entry."""
    store = api.store
    xp = store.get("total_xp", 0)
    level = level_from_xp(xp)[0]
    
    label = f"🎮 Gamify [dim](Lvl {level})[/]"
    
    return [("G", label, lambda: _main_screen(api))]


# ══════════════════════════════════════════════════════════════
# RENDER HOOKS
# ══════════════════════════════════════════════════════════════

def dashboard_widgets(api):
    """Show gamification widget on dashboard."""
    if not api.config.get("show_level_in_header", True):
        return []
    
    store = api.store
    xp = store.get("total_xp", 0)
    level, current_xp, needed_xp = level_from_xp(xp)
    progress = int(current_xp / needed_xp * 20) if needed_xp else 20
    bar = "█" * progress + "░" * (20 - progress)
    streak = store.get("current_streak", 0)
    
    # Check for new achievements
    new_achievements = []
    unlocked = store.get("achievements", [])
    for ach_id, ach in ACHIEVEMENTS.items():
        if ach_id not in unlocked and ach["check"](store):
            new_achievements.append(ach["name"])
    
    widget = (
        f"  🎮 [bold]Level {level}[/]  "
        f"[{api.theme.get('secondary', 'cyan')}]{bar}[/] "
        f"{current_xp}/{needed_xp} XP"
    )
    
    if streak > 0:
        widget += f"  🔥 {streak} day streak"
    
    if new_achievements:
        widget += f"  [yellow]⚠️ {len(new_achievements)} new achievement(s) available![/]"
    
    return [widget]
