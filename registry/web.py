"""
TaskFlow Plugin — Web Version
Serves a live read-only web dashboard on http://localhost:PORT
Pure stdlib — no extra dependencies.
Drop into ~/.taskflow/plugins/web.py
"""
PLUGIN_NAME    = "Web Dashboard"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Live web dashboard at http://localhost:7070"

import threading, json, os
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime    import datetime
from urllib.parse import urlparse, parse_qs

# ── Shared state (updated on every save) ─────────────────────────────────────
_db_ref:   dict  = {"tasks": []}
_server:   object = None
_port:     int   = 7070

# ── HTML template ─────────────────────────────────────────────────────────────

def _build_html(db: dict) -> str:
    tasks = db.get("tasks", [])
    now   = datetime.now()

    PRIO_COLOR = {"Critical":"#e74c3c","High":"#e67e22","Medium":"#f1c40f",
                  "Low":"#2ecc71","Minimal":"#95a5a6"}
    STATUS_COLOR = {"todo":"#3498db","in_progress":"#f39c12","done":"#2ecc71","cancelled":"#95a5a6"}
    PRIO_ICON    = {"Critical":"🔴","High":"🟠","Medium":"🟡","Low":"🟢","Minimal":"⚪"}

    done = [t for t in tasks if t.get("status") == "done"]
    todo = [t for t in tasks if t.get("status") in ("todo","in_progress")]
    ovd  = [t for t in todo if t.get("due_date") and
            datetime.fromisoformat(t["due_date"]) < now]
    rate = f"{len(done)/len(tasks)*100:.1f}" if tasks else "0"

    def _due_badge(t):
        due = t.get("due_date","")
        if not due or t.get("status") in ("done","cancelled"):
            return f'<span class="due-none">—</span>'
        try:
            days = (datetime.fromisoformat(due) - now).days
            if   days < 0:  return f'<span class="due-over">⚠ {due}</span>'
            elif days == 0: return f'<span class="due-today">⏰ Today</span>'
            elif days <= 2: return f'<span class="due-soon">{due}</span>'
            else:           return f'<span class="due-ok">{due}</span>'
        except Exception:
            return f'<span class="due-none">{due}</span>'

    def _task_rows(task_list):
        rows = []
        for t in task_list:
            ps   = t.get("priority","Medium")
            st   = t.get("status","todo")
            pc   = PRIO_COLOR.get(ps, "#aaa")
            sc   = STATUS_COLOR.get(st, "#aaa")
            pi   = PRIO_ICON.get(ps, "🟡")
            name = t.get("name","")
            if st == "done":
                name = f'<s style="opacity:.5">{name}</s>'
            tags = " ".join(f'<span class="tag">{x}</span>' for x in t.get("tags",[]))
            rows.append(f"""
            <tr>
              <td><span style="color:{pc}">{pi} {ps}</span></td>
              <td class="name">{name} {tags}</td>
              <td>{t.get("category","")}</td>
              <td><span class="status" style="background:{sc}22;color:{sc}">{st}</span></td>
              <td>{_due_badge(t)}</td>
              <td style="text-align:right">{t.get("estimated_hours",1)}h</td>
            </tr>""")
        return "\n".join(rows)

    sorted_tasks = sorted(
        tasks,
        key=lambda t: (-t.get("priority_score",0), t.get("due_date","9999"))
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>TaskFlow</title>
<style>
  :root {{
    --bg:      #0b0b18;
    --bg2:     #111828;
    --border:  #1a2a44;
    --primary: #00e5ff;
    --dim:     #556688;
    --text:    #ddeeff;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:var(--bg); color:var(--text); font-family:'Segoe UI',system-ui,sans-serif;
          font-size:14px; padding:24px; }}
  h1   {{ color:var(--primary); font-size:22px; margin-bottom:4px; }}
  .sub {{ color:var(--dim); font-size:12px; margin-bottom:24px; }}
  .cards {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:24px; }}
  .card {{ background:var(--bg2); border:1px solid var(--border); border-radius:8px;
           padding:14px 20px; min-width:100px; text-align:center; }}
  .card .val {{ font-size:26px; font-weight:700; color:var(--primary); }}
  .card .lbl {{ font-size:11px; color:var(--dim); margin-top:4px; }}
  .card.warn .val {{ color:#e74c3c; }}
  .card.ok   .val {{ color:#2ecc71; }}
  table {{ width:100%; border-collapse:collapse; background:var(--bg2);
           border:1px solid var(--border); border-radius:8px; overflow:hidden; }}
  th    {{ background:#0f1635; color:var(--primary); text-align:left; padding:10px 12px;
           font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:.05em; }}
  td    {{ padding:9px 12px; border-bottom:1px solid var(--border); vertical-align:middle; }}
  tr:last-child td {{ border-bottom:none; }}
  tr:hover td {{ background:#ffffff08; }}
  .name  {{ max-width:300px; }}
  .status {{ display:inline-block; padding:2px 8px; border-radius:4px; font-size:12px; }}
  .tag    {{ display:inline-block; background:#1a2a44; color:#778899; padding:1px 6px;
             border-radius:3px; font-size:11px; margin-left:4px; }}
  .due-over  {{ color:#e74c3c; font-weight:600; }}
  .due-today {{ color:#f39c12; font-weight:600; }}
  .due-soon  {{ color:#f39c12; }}
  .due-ok    {{ color:#2ecc71; }}
  .due-none  {{ color:var(--dim); }}
  .section-title {{ color:var(--primary); font-size:14px; font-weight:600;
                    margin:24px 0 10px; padding-bottom:6px;
                    border-bottom:1px solid var(--border); }}
  .footer {{ margin-top:24px; color:var(--dim); font-size:11px; }}
  @media(max-width:600px) {{ .cards {{ flex-direction:column; }} }}
</style>
</head>
<body>
<h1>⚡ TaskFlow</h1>
<div class="sub">Auto-refreshes every 30s  ·  {now:%Y-%m-%d %H:%M}</div>

<div class="cards">
  <div class="card"><div class="val">{len(tasks)}</div><div class="lbl">Total</div></div>
  <div class="card ok"><div class="val">{len(done)}</div><div class="lbl">Completed</div></div>
  <div class="card"><div class="val">{len(todo)}</div><div class="lbl">Pending</div></div>
  <div class="card"><div class="val">{rate}%</div><div class="lbl">Done rate</div></div>
  <div class="card {'warn' if ovd else 'ok'}"><div class="val">{len(ovd)}</div><div class="lbl">Overdue</div></div>
</div>

<div class="section-title">📋 All Tasks</div>
<table>
  <thead>
    <tr>
      <th>Priority</th><th>Task</th><th>Category</th>
      <th>Status</th><th>Due</th><th>Est.</th>
    </tr>
  </thead>
  <tbody>
    {_task_rows(sorted_tasks)}
  </tbody>
</table>

<div class="footer">
  TaskFlow Web Dashboard  ·  Read-only view  ·  {len(tasks)} tasks
</div>
</body>
</html>"""


# ── HTTP handler ──────────────────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass   # silence access log

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/tasks":
            data = json.dumps(_db_ref.get("tasks", []), default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(data))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        elif path in ("/", "/index.html"):
            html = _build_html(_db_ref).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(html))
            self.end_headers()
            self.wfile.write(html)
        else:
            self.send_response(404)
            self.end_headers()


# ── Plugin interface ──────────────────────────────────────────────────────────

def _start_server(port: int):
    global _server
    try:
        _server = HTTPServer(("", port), _Handler)
        _server.serve_forever()
    except Exception:
        pass

def _stop_server():
    global _server
    if _server:
        _server.shutdown()
        _server = None

def _web_screen(api):
    from rich.prompt import Prompt
    from rich.panel  import Panel

    console = api.console
    store   = api.store
    global _port, _db_ref

    while True:
        os.system("clear")
        console.print()
        console.print("  [bold #00e5ff]⚡ TaskFlow  ·  🌐 Web Dashboard[/]\n")

        running = _server is not None
        port    = store.get("port", _port)
        console.print(Panel(
            f"  Status:  {'[green]running[/]' if running else '[yellow]stopped[/]'}\n"
            f"  URL:     [bold]http://localhost:{port}[/]\n"
            f"  API:     [dim]http://localhost:{port}/api/tasks[/]\n\n"
            "  [dim]Dashboard auto-refreshes every 30 seconds.[/]\n"
            "  [dim]Read-only — manage tasks in the terminal.[/]",
            border_style="#1a2a44", padding=(0,1)
        ))
        console.print()

        if not running:
            console.print("  [bold #00b4d8]s[/]  Start server")
        else:
            console.print("  [bold #00b4d8]x[/]  Stop server")
            console.print("  [bold #00b4d8]o[/]  Open in browser")
        console.print("  [bold #00b4d8]p[/]  Change port")
        console.print("  [bold #00b4d8]b[/]  Back\n")

        ch = Prompt.ask("  [#00b4d8]>[/]").strip().lower()
        if ch == "b":
            return
        elif ch == "s" and not running:
            _db_ref = api.db
            port = int(store.get("port", _port))
            t = threading.Thread(target=_start_server, args=(port,), daemon=True)
            t.start()
            import time; time.sleep(0.3)
            if _server:
                console.print(f"  [green]✓ Running at http://localhost:{port}[/]")
                store["port"]    = port
                store["running"] = True
                api.store_save()
            else:
                console.print(f"  [red]Failed to start (port {port} in use?)[/]")
            input("  Enter to continue...")
        elif ch == "x" and running:
            _stop_server()
            store["running"] = False
            api.store_save()
            console.print("  [dim]Server stopped.[/]")
            input("  Enter to continue...")
        elif ch == "o" and running:
            port = store.get("port", _port)
            try:
                import subprocess as sp
                sp.Popen(["xdg-open", f"http://localhost:{port}"])
            except Exception:
                console.print(f"  Open: http://localhost:{port}")
            input("  Enter to continue...")
        elif ch == "p":
            raw = Prompt.ask("  [#00b4d8]Port[/]", default=str(store.get("port", _port)))
            try:
                store["port"] = int(raw)
                _port = int(raw)
                api.store_save()
                console.print(f"  [green]Port set to {store['port']}.[/]")
            except Exception:
                console.print("  [red]Invalid port.[/]")
            input("  Enter to continue...")


def on_startup(api):
    """Keep db_ref up to date and auto-start if configured."""
    global _db_ref
    _db_ref = api.db
    store   = api.store
    if store.get("running") and _server is None:
        port = int(store.get("port", _port))
        t    = threading.Thread(target=_start_server, args=(port,), daemon=True)
        t.start()


def on_task_created(api, task):
    global _db_ref
    _db_ref = api.db


def on_task_done(api, task):
    global _db_ref
    _db_ref = api.db


def menu_items(api):
    running = _server is not None
    label   = f"🌐 Web  [dim]({'running' if running else 'stopped'})[/]"
    return [("W", label, lambda: _web_screen(api))]
