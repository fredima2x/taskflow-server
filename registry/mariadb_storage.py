"""
TaskFlow Plugin — MariaDB Storage Backend
Stores tasks in a MariaDB database.
Uses the official MariaDB connector (pure C extension) when available,
falls back to pymysql which is wire-compatible.

Install:  pip install mariadb          (preferred, needs libmariadb)
       or pip install pymysql          (pure-Python fallback)
"""
PLUGIN_NAME    = "MariaDB Storage"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Persist tasks in a MariaDB database"

import json, os
from datetime import datetime

# ── Driver detection ─────────────────────────────────────────────────────────
try:
    import mariadb as _driver
    _DRIVER = "mariadb"
except ImportError:
    try:
        import pymysql as _driver        # wire-compatible fallback
        import pymysql.cursors
        _DRIVER = "pymysql"
    except ImportError:
        _driver = None
        _DRIVER = None

# ── SQL ───────────────────────────────────────────────────────────────────────

SQL_CREATE = """
CREATE TABLE IF NOT EXISTS taskflow_tasks (
    id              VARCHAR(16)  PRIMARY KEY,
    name            TEXT         NOT NULL,
    priority        VARCHAR(20),
    priority_score  INT,
    category        VARCHAR(50),
    status          VARCHAR(20),
    due_date        VARCHAR(30),
    estimated_hours FLOAT,
    actual_hours    FLOAT,
    description     TEXT,
    tags            TEXT,
    recurrence      VARCHAR(20),
    parent_id       VARCHAR(16),
    created_at      VARCHAR(40),
    completed_at    VARCHAR(40),
    started_at      VARCHAR(40),
    extra           TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

# ── Connection ────────────────────────────────────────────────────────────────

def _connect(cfg: dict):
    if _DRIVER == "mariadb":
        conn = _driver.connect(
            host     = cfg.get("host","localhost"),
            port     = int(cfg.get("port", 3306)),
            user     = cfg["user"],
            password = cfg["password"],
            database = cfg["database"],
        )
        return conn
    elif _DRIVER == "pymysql":
        return _driver.connect(
            host     = cfg.get("host","localhost"),
            port     = int(cfg.get("port", 3306)),
            user     = cfg["user"],
            password = cfg["password"],
            database = cfg["database"],
            charset  = "utf8mb4",
            cursorclass = _driver.cursors.DictCursor,
            connect_timeout = 5,
        )
    raise RuntimeError("No MariaDB driver found. Install: pip install mariadb")

def _cursor(conn):
    if _DRIVER == "mariadb":
        return conn.cursor(dictionary=True)
    return conn.cursor()

def _ensure_table(cfg):
    conn = _connect(cfg)
    cur  = _cursor(conn)
    cur.execute(SQL_CREATE)
    conn.commit()
    cur.close(); conn.close()

# ── Backend ───────────────────────────────────────────────────────────────────

COLS = ["id","name","priority","priority_score","category","status",
        "due_date","estimated_hours","actual_hours","description",
        "tags","recurrence","parent_id","created_at","completed_at","started_at"]

def _make_load(cfg):
    def _load():
        conn = _connect(cfg)
        cur  = _cursor(conn)
        cur.execute("SELECT * FROM taskflow_tasks")
        rows = cur.fetchall()
        cur.close(); conn.close()
        tasks = []
        for row in rows:
            t = dict(row)
            t["tags"] = json.loads(t.get("tags") or "[]")
            extra = json.loads(t.pop("extra") or "{}")
            t.update(extra)
            tasks.append(t)
        return {"tasks": tasks}
    return _load

def _make_save(cfg):
    def _save(db):
        tasks = db.get("tasks", [])
        conn  = _connect(cfg)
        cur   = _cursor(conn)
        ids   = []
        for t in tasks:
            row          = {c: t.get(c) for c in COLS}
            row["tags"]  = json.dumps(t.get("tags", []))
            extra        = {k: v for k, v in t.items() if k not in COLS and k != "tags"}
            row["extra"] = json.dumps(extra)
            ids.append(t["id"])
            cols_str     = ", ".join(COLS) + ", extra"
            placeholders = ", ".join(["?"] * (len(COLS)+1)) if _DRIVER == "mariadb" else \
                           ", ".join(["%s"] * (len(COLS)+1))
            updates      = ", ".join(f"{c}=VALUES({c})" for c in COLS if c != "id") + \
                           ", extra=VALUES(extra)"
            cur.execute(
                f"INSERT INTO taskflow_tasks ({cols_str}) VALUES ({placeholders}) "
                f"ON DUPLICATE KEY UPDATE {updates}",
                [row[c] for c in COLS] + [row["extra"]]
            )
        if ids:
            fmt = ",".join(["?"]*len(ids)) if _DRIVER=="mariadb" else ",".join(["%s"]*len(ids))
            cur.execute(f"DELETE FROM taskflow_tasks WHERE id NOT IN ({fmt})", ids)
        else:
            cur.execute("DELETE FROM taskflow_tasks")
        conn.commit()
        cur.close(); conn.close()
    return _save

# ── Screens ───────────────────────────────────────────────────────────────────

def _cfg_screen(api):
    from rich.prompt import Prompt, Confirm
    from rich.panel  import Panel

    console = api.console
    store   = api.store

    console.print(Panel(
        "  Configure MariaDB connection\n"
        f"  [dim]Driver: {_DRIVER or 'not found'}[/]\n"
        "  [dim]Credentials saved in ~/.taskflow/plugin_data/mariadb_storage.json[/]",
        border_style="#1a2a44", padding=(0,1)
    ))
    console.print()

    if _DRIVER is None:
        console.print("  [red]No driver found.[/]  Install one of:\n"
                      "  [dim]pip install mariadb[/]  (needs libmariadb-dev)\n"
                      "  [dim]pip install pymysql[/]  (pure Python fallback)")
        input("  Enter to go back...")
        return

    def ask(lbl, key, default=""):
        cur = store.get(key, default)
        return Prompt.ask(f"  [#00b4d8]{lbl}[/] [dim][{cur}][/]", default=cur or default).strip()

    store["host"]     = ask("Host",     "host",     "localhost")
    store["port"]     = ask("Port",     "port",     "3306")
    store["user"]     = ask("User",     "user",     "root")
    store["password"] = Prompt.ask("  [#00b4d8]Password[/]", password=True,
                                   default=store.get("password",""))
    store["database"] = ask("Database", "database", "taskflow")
    api.store_save()
    console.print()

    if Confirm.ask("  Test connection?", default=True):
        try:
            _ensure_table(store)
            console.print("  [green]✓ Connected — table ready.[/]")
        except Exception as e:
            console.print(f"  [red]Failed: {e}[/]")
            return

        if Confirm.ask("  Activate MariaDB as storage backend?", default=True):
            api.register_storage(_make_load(store), _make_save(store))
            store["active"] = True
            api.store_save()
            console.print("  [green]✓ MariaDB backend active.[/]")


def _mariadb_screen(api):
    from rich.prompt import Prompt
    from rich.panel  import Panel

    console = api.console
    store   = api.store

    while True:
        os.system("clear")
        console.print()
        console.print("  [bold #00e5ff]⚡ TaskFlow  ·  🦭 MariaDB Storage[/]\n")
        active = store.get("active", False) and _DRIVER is not None
        console.print(Panel(
            f"  Driver:   [dim]{_DRIVER or 'none'}[/]\n"
            f"  Status:   {'[green]active[/]' if active else '[yellow]inactive[/]'}\n"
            f"  Host:     [dim]{store.get('host','—')}[/]\n"
            f"  Database: [dim]{store.get('database','—')}[/]",
            border_style="#1a2a44", padding=(0,1)
        ))
        console.print()
        console.print("  [bold #00b4d8]s[/]  Configure / test")
        if active:
            console.print("  [bold #00b4d8]x[/]  Sync now")
            console.print("  [bold #00b4d8]d[/]  Deactivate")
        console.print("  [bold #00b4d8]b[/]  Back\n")

        ch = Prompt.ask("  [#00b4d8]>[/]").strip().lower()
        if ch == "b":
            return
        elif ch == "s":
            _cfg_screen(api)
            input("  Enter...")
        elif ch == "x" and active:
            try:
                _make_save(store)(api.db)
                console.print("  [green]✓ Synced.[/]")
            except Exception as e:
                console.print(f"  [red]{e}[/]")
            input("  Enter...")
        elif ch == "d" and active:
            store["active"] = False
            api.store_save()
            try:
                from taskflow import _storage_backend
                _storage_backend.clear()
            except Exception:
                pass
            console.print("  [dim]Reverted to JSON.[/]")
            input("  Enter...")


def on_startup(api):
    if _DRIVER is None:
        return
    store = api.store
    if store.get("active") and all(k in store for k in ("host","user","password","database")):
        try:
            _ensure_table(store)
            api.register_storage(_make_load(store), _make_save(store))
        except Exception as e:
            api.console.print(f"  [yellow]MariaDB: auto-connect failed: {e}[/]")


def menu_items(api):
    return [("D", "🦭 MariaDB storage", lambda: _mariadb_screen(api))]
