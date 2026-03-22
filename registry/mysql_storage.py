"""
TaskFlow Plugin — MySQL Storage Backend
Stores tasks in a MySQL database instead of JSON.

Install driver:  pip install pymysql
Setup:           Configure in the plugin settings screen (option m → s)
"""
PLUGIN_NAME    = "MySQL Storage"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Persist tasks in a MySQL database"

import json
from datetime import datetime

try:
    import pymysql
    import pymysql.cursors
    HAS_PYMYSQL = True
except ImportError:
    HAS_PYMYSQL = False

# ── SQL ───────────────────────────────────────────────────────────────────────

SQL_CREATE = """
CREATE TABLE IF NOT EXISTS taskflow_tasks (
    id            VARCHAR(16)  PRIMARY KEY,
    name          TEXT         NOT NULL,
    priority      VARCHAR(20),
    priority_score INT,
    category      VARCHAR(50),
    status        VARCHAR(20),
    due_date      VARCHAR(30),
    estimated_hours FLOAT,
    actual_hours  FLOAT,
    description   TEXT,
    tags          TEXT,
    recurrence    VARCHAR(20),
    parent_id     VARCHAR(16),
    created_at    VARCHAR(40),
    completed_at  VARCHAR(40),
    started_at    VARCHAR(40),
    extra         TEXT
)
"""

# ── Connection ────────────────────────────────────────────────────────────────

def _connect(cfg: dict):
    return pymysql.connect(
        host     = cfg.get("host", "localhost"),
        port     = int(cfg.get("port", 3306)),
        user     = cfg["user"],
        password = cfg["password"],
        database = cfg["database"],
        charset  = "utf8mb4",
        cursorclass = pymysql.cursors.DictCursor,
        connect_timeout = 5,
    )

def _ensure_table(cfg: dict):
    with _connect(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_CREATE)
        conn.commit()

# ── Backend functions ─────────────────────────────────────────────────────────

def _make_load(cfg):
    def _load():
        with _connect(cfg) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM taskflow_tasks")
                rows = cur.fetchall()
        tasks = []
        for row in rows:
            t = dict(row)
            t["tags"]  = json.loads(t["tags"]  or "[]")
            extra = json.loads(t.pop("extra") or "{}")
            t.update(extra)
            tasks.append(t)
        return {"tasks": tasks}
    return _load

def _make_save(cfg):
    def _save(db):
        tasks = db.get("tasks", [])
        COLS  = ["id","name","priority","priority_score","category","status",
                 "due_date","estimated_hours","actual_hours","description",
                 "tags","recurrence","parent_id","created_at","completed_at","started_at"]
        with _connect(cfg) as conn:
            with conn.cursor() as cur:
                # Upsert all tasks
                ids = [t["id"] for t in tasks]
                for t in tasks:
                    row   = {c: t.get(c) for c in COLS}
                    row["tags"]  = json.dumps(t.get("tags", []))
                    extra = {k: v for k, v in t.items() if k not in COLS and k != "tags"}
                    row["extra"] = json.dumps(extra)
                    placeholders = ", ".join(["%s"] * (len(COLS) + 1))
                    updates = ", ".join(f"{c}=VALUES({c})" for c in COLS if c != "id")
                    updates += ", extra=VALUES(extra)"
                    cols_str = ", ".join(COLS) + ", extra"
                    vals = [row[c] for c in COLS] + [row["extra"]]
                    cur.execute(
                        f"INSERT INTO taskflow_tasks ({cols_str}) VALUES ({placeholders}) "
                        f"ON DUPLICATE KEY UPDATE {updates}",
                        vals
                    )
                # Delete removed tasks
                if ids:
                    fmt = ",".join(["%s"] * len(ids))
                    cur.execute(f"DELETE FROM taskflow_tasks WHERE id NOT IN ({fmt})", ids)
                else:
                    cur.execute("DELETE FROM taskflow_tasks")
            conn.commit()
    return _save


# ── Plugin screens ────────────────────────────────────────────────────────────

def _cfg_screen(api):
    from rich.prompt import Prompt, Confirm
    from rich.panel  import Panel

    console = api.console
    store   = api.store

    console.print(Panel(
        "  Configure MySQL connection\n"
        "  [dim]Credentials are stored in ~/.taskflow/plugin_data/mysql_storage.json[/]",
        border_style="#1a2a44", padding=(0,1)
    ))
    console.print()

    def ask(label, key, default=""):
        cur = store.get(key, default)
        d   = f" [dim][{cur}][/]" if cur else ""
        val = Prompt.ask(f"  [#00b4d8]{label}[/]{d}", default=cur or default)
        return val.strip()

    store["host"]     = ask("Host",     "host",     "localhost")
    store["port"]     = ask("Port",     "port",     "3306")
    store["user"]     = ask("User",     "user",     "root")
    store["password"] = Prompt.ask("  [#00b4d8]Password[/]", password=True, default=store.get("password",""))
    store["database"] = ask("Database", "database", "taskflow")
    api.store_save()
    console.print()

    if Confirm.ask("  Test connection now?", default=True):
        if not HAS_PYMYSQL:
            console.print("  [red]pymysql not installed:  pip install pymysql[/]")
            return
        try:
            _ensure_table(store)
            console.print("  [green]✓ Connected and table ready.[/]")
        except Exception as e:
            console.print(f"  [red]Connection failed: {e}[/]")
            return

        if Confirm.ask("  Activate MySQL as storage backend?", default=True):
            api.register_storage(_make_load(store), _make_save(store))
            store["active"] = True
            api.store_save()
            console.print("  [green]✓ MySQL backend active.[/]")


def _mysql_screen(api):
    from rich.prompt import Prompt
    from rich.panel  import Panel
    import os

    console = api.console
    store   = api.store

    while True:
        os.system("clear")
        console.print()
        console.print("  [bold #00e5ff]⚡ TaskFlow  ·  🐬 MySQL Storage[/]\n")

        active = store.get("active", False) and HAS_PYMYSQL
        host   = store.get("host","—")
        db_    = store.get("database","—")

        console.print(Panel(
            f"  Status:   {'[green]active[/]' if active else '[yellow]inactive[/]'}\n"
            f"  Host:     [dim]{host}[/]\n"
            f"  Database: [dim]{db_}[/]\n"
            + ("" if HAS_PYMYSQL else "\n  [yellow]pymysql not installed:  pip install pymysql[/]"),
            border_style="#1a2a44", padding=(0,1)
        ))
        console.print()
        console.print("  [bold #00b4d8]s[/]  Configure / test connection")
        if active:
            console.print("  [bold #00b4d8]x[/]  Sync now (push local JSON → MySQL)")
            console.print("  [bold #00b4d8]d[/]  Deactivate (revert to JSON)")
        console.print("  [bold #00b4d8]b[/]  Back")
        console.print()
        ch = Prompt.ask("  [#00b4d8]>[/]").strip().lower()

        if ch == "b":
            return
        elif ch == "s":
            _cfg_screen(api)
            input("  Enter to continue...")
        elif ch == "x" and active:
            try:
                _make_save(store)(api.db)
                console.print("  [green]✓ Synced.[/]")
            except Exception as e:
                console.print(f"  [red]{e}[/]")
            input("  Enter to continue...")
        elif ch == "d" and active:
            store["active"] = False
            api.store_save()
            # clear backend
            from taskflow import _storage_backend
            _storage_backend.clear()
            console.print("  [dim]Reverted to JSON storage.[/]")
            input("  Enter to continue...")


def on_startup(api):
    """Re-activate backend if it was active last session."""
    if not HAS_PYMYSQL:
        return
    store = api.store
    if store.get("active") and all(k in store for k in ("host","user","password","database")):
        try:
            _ensure_table(store)
            api.register_storage(_make_load(store), _make_save(store))
        except Exception as e:
            api.console.print(f"  [yellow]MySQL: auto-connect failed: {e}[/]")


def menu_items(api):
    return [("M", "🐬 MySQL storage", lambda: _mysql_screen(api))]
