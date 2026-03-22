"""
TaskFlow Plugin — Web Dashboard  v2
PLUGIN_NAME    = "Web Dashboard"
PLUGIN_VERSION = "2.0"
PLUGIN_DESC    = "Live web dashboard with charts, task management and REST API"
PLUGIN_AUTHOR  = "community"
PLUGIN_TAGS    = "web, dashboard, api, charts"
PLUGIN_MIN_API = "3.0"
"""
PLUGIN_NAME    = "Web Dashboard"
PLUGIN_VERSION = "2.0"
PLUGIN_DESC    = "Live dashboard — charts, task management, REST API"
PLUGIN_MIN_API = "3.0"

import os, json, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime    import datetime, date, timedelta
from urllib.parse import urlparse, parse_qs, unquote
from collections import Counter
from pathlib     import Path

_server    = None
_db_ref    = {"tasks": []}
_port      = 7070
_start_time = time.time()
_req_count = 0

PRIO_COLOR  = {"Critical":"#e74c3c","High":"#e67e22","Medium":"#f1c40f","Low":"#2ecc71","Minimal":"#95a5a6"}
STATUS_COLOR= {"todo":"#3498db","in_progress":"#f39c12","done":"#2ecc71","cancelled":"#95a5a6"}
PRIO_ICON   = {"Critical":"🔴","High":"🟠","Medium":"🟡","Low":"🟢","Minimal":"⚪"}


def _due_class(due: str, status: str) -> str:
    if not due or status in ("done","cancelled"): return ""
    try:
        days = (datetime.fromisoformat(due) - datetime.now()).days
        if days < 0:  return "overdue"
        if days == 0: return "due-today"
        if days <= 2: return "due-soon"
    except Exception: pass
    return ""


def _build_html(db: dict) -> str:
    tasks    = db.get("tasks",[])
    now      = datetime.now()
    today    = date.today().isoformat()
    done     = [t for t in tasks if t.get("status")=="done"]
    todo     = [t for t in tasks if t.get("status") in ("todo","in_progress")]
    overdue  = [t for t in todo if t.get("due_date","") and t["due_date"] < today]
    due_tod  = [t for t in todo if t.get("due_date","") == today]
    rate     = f"{len(done)/len(tasks)*100:.1f}" if tasks else "0"
    est_h    = sum(t.get("estimated_hours",0) for t in todo)

    # Category counts for pie
    cat_cnt   = Counter(t.get("category","Other") for t in tasks)
    prio_cnt  = Counter(t.get("priority","Medium") for t in tasks)
    status_cnt= Counter(t.get("status","todo") for t in tasks)

    # Daily completions last 14 days
    daily = []
    for i in range(13,-1,-1):
        d = (date.today()-timedelta(days=i)).isoformat()
        n = sum(1 for t in done if t.get("completed_at","")[:10]==d)
        daily.append({"date":d,"count":n})

    sorted_tasks = sorted(tasks, key=lambda t: (-t.get("priority_score",0), t.get("due_date","9999")))

    def _rows(task_list, limit=50):
        html = ""
        for t in task_list[:limit]:
            ps    = t.get("priority","Medium")
            st    = t.get("status","todo")
            due   = t.get("due_date","") or ""
            dc    = _due_class(due, st)
            tags  = " ".join(f'<span class="tag">{x}</span>' for x in t.get("tags",[])[:4])
            name  = t["name"].replace("<","&lt;")
            if st == "done": name = f"<s style='opacity:.5'>{name}</s>"
            due_d = f'<span class="due {dc}">{due or "—"}</span>'
            pclr  = PRIO_COLOR.get(ps,"#aaa")
            sclr  = STATUS_COLOR.get(st,"#aaa")
            html += f"""<tr data-id="{t['id']}" data-status="{st}">
  <td><span class="prio-dot" style="background:{pclr}"></span>{name} {tags}</td>
  <td><span class="badge" style="background:{pclr}22;color:{pclr}">{ps}</span></td>
  <td><span class="badge" style="background:{sclr}22;color:{sclr}">{st}</span></td>
  <td>{due_d}</td>
  <td style="text-align:right">{t.get('estimated_hours',1)}h</td>
  <td><span class="category">{t.get('category','')}</span></td>
  <td class="actions">
    <button onclick="toggleStatus('{t['id']}','{st}')" title="Toggle status">{"✓" if st!="done" else "↩"}</button>
    <button onclick="deleteTask('{t['id']}')" title="Delete" class="del">✕</button>
  </td>
</tr>"""
        return html

    cat_js   = json.dumps({k:v for k,v in cat_cnt.most_common(8)})
    prio_js  = json.dumps({k:v for k,v in prio_cnt.items()})
    daily_js = json.dumps(daily)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TaskFlow Dashboard</title>
<style>
  :root{{--bg:#0b0b18;--bg2:#111828;--bg3:#0f1635;--border:#1a2a44;
         --primary:#00e5ff;--dim:#556688;--text:#ddeeff;
         --green:#2ecc71;--orange:#f39c12;--red:#e74c3c;--yellow:#f1c40f}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;min-height:100vh}}
  nav{{background:var(--bg3);border-bottom:1px solid var(--border);padding:14px 28px;
       display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100}}
  nav h1{{color:var(--primary);font-size:20px}}
  .nav-right{{display:flex;gap:12px;align-items:center}}
  .live-dot{{width:8px;height:8px;background:var(--green);border-radius:50%;
             animation:pulse 2s infinite}}
  @keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
  main{{padding:24px 28px;max-width:1400px;margin:0 auto}}
  .cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;margin-bottom:24px}}
  .card{{background:var(--bg2);border:1px solid var(--border);border-radius:10px;
         padding:16px;text-align:center;transition:border-color .2s}}
  .card:hover{{border-color:var(--primary)}}
  .card-val{{font-size:28px;font-weight:700;color:var(--primary)}}
  .card-val.red{{color:var(--red)}} .card-val.green{{color:var(--green)}} .card-val.orange{{color:var(--orange)}}
  .card-lbl{{font-size:11px;color:var(--dim);margin-top:4px}}
  .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}}
  .grid3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:24px}}
  .panel{{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:20px}}
  .panel h3{{color:var(--primary);font-size:13px;margin-bottom:14px;text-transform:uppercase;letter-spacing:.05em}}
  canvas{{width:100%!important;max-height:200px}}
  .search-bar{{display:flex;gap:8px;margin-bottom:16px}}
  .search-bar input{{flex:1;background:var(--bg3);border:1px solid var(--border);
                     border-radius:6px;padding:8px 12px;color:var(--text);font-size:13px}}
  .search-bar input:focus{{outline:none;border-color:var(--primary)}}
  .filter-tabs{{display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap}}
  .tab{{padding:5px 14px;border-radius:20px;border:1px solid var(--border);cursor:pointer;
        font-size:12px;color:var(--dim);background:transparent;transition:all .15s}}
  .tab.active,.tab:hover{{background:var(--primary);color:#000;border-color:var(--primary)}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{color:var(--primary);text-align:left;padding:8px 10px;border-bottom:1px solid var(--border);
      font-size:11px;text-transform:uppercase;letter-spacing:.04em;cursor:pointer}}
  th:hover{{color:var(--text)}}
  td{{padding:8px 10px;border-bottom:1px solid #0d1020;vertical-align:middle}}
  tr:hover td{{background:#ffffff06}}
  .prio-dot{{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;flex-shrink:0}}
  .badge{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;white-space:nowrap}}
  .tag{{display:inline-block;background:#1a2a44;color:#778899;padding:1px 6px;border-radius:3px;
        font-size:10px;margin-left:3px}}
  .category{{color:var(--dim);font-size:12px}}
  .due.overdue{{color:var(--red);font-weight:600}}
  .due.due-today{{color:var(--orange);font-weight:600}}
  .due.due-soon{{color:var(--yellow)}}
  .actions button{{background:transparent;border:1px solid var(--border);color:var(--dim);
                   border-radius:4px;padding:2px 8px;cursor:pointer;font-size:11px;margin-left:3px}}
  .actions button:hover{{background:var(--bg3);color:var(--text)}}
  .actions button.del:hover{{background:#1a0a0a;color:var(--red);border-color:var(--red)}}
  .add-form{{display:flex;gap:8px;margin-top:16px;flex-wrap:wrap}}
  .add-form input,select{{background:var(--bg3);border:1px solid var(--border);
                          border-radius:6px;padding:7px 10px;color:var(--text);font-size:12px}}
  .add-form input:focus,select:focus{{outline:none;border-color:var(--primary)}}
  .btn-primary{{background:var(--primary);color:#000;border:none;border-radius:6px;
                padding:7px 16px;font-weight:600;cursor:pointer;font-size:12px}}
  .btn-primary:hover{{opacity:.85}}
  .toast{{position:fixed;bottom:24px;right:24px;background:var(--bg2);border:1px solid var(--green);
          color:var(--text);padding:10px 18px;border-radius:8px;font-size:13px;
          opacity:0;transition:opacity .3s;pointer-events:none;z-index:999}}
  .toast.show{{opacity:1}}
  .bar-chart{{display:flex;flex-direction:column;gap:5px}}
  .bar-row{{display:flex;align-items:center;gap:8px;font-size:11px}}
  .bar-row .lbl{{width:70px;color:var(--dim);text-align:right;flex-shrink:0}}
  .bar-wrap{{flex:1;background:var(--bg3);border-radius:3px;height:14px;overflow:hidden}}
  .bar{{background:var(--primary);height:100%;border-radius:3px;transition:width .4s}}
  .bar.orange{{background:var(--orange)}}
  @media(max-width:768px){{.grid2,.grid3{{grid-template-columns:1fr}}.add-form{{flex-direction:column}}}}
</style>
</head>
<body>
<nav>
  <h1>⚡ TaskFlow</h1>
  <div class="nav-right">
    <span class="live-dot" title="Live — auto-refreshes"></span>
    <span style="color:var(--dim);font-size:12px" id="last-update">{now:%H:%M:%S}</span>
    <span style="color:var(--dim);font-size:12px">{len(tasks)} tasks</span>
  </div>
</nav>

<main>
<!-- Stat cards -->
<div class="cards">
  <div class="card"><div class="card-val">{len(tasks)}</div><div class="card-lbl">Total Tasks</div></div>
  <div class="card"><div class="card-val green">{len(done)}</div><div class="card-lbl">Completed</div></div>
  <div class="card"><div class="card-val orange">{len(todo)}</div><div class="card-lbl">Pending</div></div>
  <div class="card"><div class="card-val">{rate}%</div><div class="card-lbl">Done Rate</div></div>
  <div class="card"><div class="card-val {'red' if overdue else 'green'}">{len(overdue)}</div><div class="card-lbl">Overdue</div></div>
  <div class="card"><div class="card-val {'orange' if due_tod else ''}">{len(due_tod)}</div><div class="card-lbl">Due Today</div></div>
  <div class="card"><div class="card-val">{est_h:.1f}h</div><div class="card-lbl">Hours Backlog</div></div>
</div>

<!-- Charts row -->
<div class="grid3">
  <div class="panel">
    <h3>📊 Completions — 14 Days</h3>
    <canvas id="lineChart" height="180"></canvas>
  </div>
  <div class="panel">
    <h3>🗂 By Category</h3>
    <div class="bar-chart" id="catBars"></div>
  </div>
  <div class="panel">
    <h3>⚡ By Priority</h3>
    <div class="bar-chart" id="prioBars"></div>
  </div>
</div>

<!-- Task table -->
<div class="panel">
  <h3>📋 Tasks</h3>
  <div class="search-bar">
    <input type="text" id="search" placeholder="Search tasks…" oninput="filterTable()">
  </div>
  <div class="filter-tabs">
    <button class="tab active" onclick="setFilter('all',this)">All ({len(tasks)})</button>
    <button class="tab" onclick="setFilter('todo',this)">Todo ({status_cnt.get('todo',0)})</button>
    <button class="tab" onclick="setFilter('in_progress',this)">In Progress ({status_cnt.get('in_progress',0)})</button>
    <button class="tab" onclick="setFilter('done',this)">Done ({len(done)})</button>
    <button class="tab" onclick="setFilter('overdue',this)">⚠ Overdue ({len(overdue)})</button>
  </div>
  <div style="overflow-x:auto">
    <table id="taskTable">
      <thead><tr>
        <th onclick="sortBy('name')">Task ↕</th>
        <th onclick="sortBy('priority')">Priority ↕</th>
        <th onclick="sortBy('status')">Status ↕</th>
        <th onclick="sortBy('due')">Due ↕</th>
        <th>Hours</th>
        <th>Category</th>
        <th>Actions</th>
      </tr></thead>
      <tbody id="taskBody">{_rows(sorted_tasks)}</tbody>
    </table>
  </div>

  <!-- Quick add form -->
  <div class="add-form">
    <input type="text" id="newName" placeholder="New task name…" style="flex:2;min-width:200px">
    <select id="newPrio">
      <option>Medium</option><option>High</option><option>Critical</option>
      <option>Low</option><option>Minimal</option>
    </select>
    <select id="newCat">
      <option>Work</option><option>Personal</option><option>Health</option>
      <option>Learning</option><option>Finance</option><option>Project</option><option>Other</option>
    </select>
    <input type="date" id="newDue" style="width:140px">
    <button class="btn-primary" onclick="addTask()">+ Add Task</button>
  </div>
</div>
</main>

<div class="toast" id="toast"></div>

<script>
const DAILY = {daily_js};
const CATS  = {cat_js};
const PRIOS = {prio_js};
const PRIO_COLORS = {json.dumps(PRIO_COLOR)};
const STATUS_COLORS = {json.dumps(STATUS_COLOR)};

// ── Line chart (canvas) ──────────────────────────────────────
(function() {{
  const cv = document.getElementById('lineChart');
  const ctx= cv.getContext('2d');
  const W  = cv.offsetWidth || 300;
  const H  = 180;
  cv.width = W; cv.height = H;
  const vals = DAILY.map(d=>d.count);
  const max  = Math.max(...vals,1);
  const pad  = {{l:30,r:10,t:10,b:28}};
  const W2   = W-pad.l-pad.r, H2=H-pad.t-pad.b;
  ctx.clearRect(0,0,W,H);
  // Grid
  ctx.strokeStyle='#1a2a44'; ctx.lineWidth=1;
  for(let i=0;i<=4;i++){{
    const y=pad.t+H2*(1-i/4);
    ctx.beginPath(); ctx.moveTo(pad.l,y); ctx.lineTo(W-pad.r,y); ctx.stroke();
    ctx.fillStyle='#445566'; ctx.font='9px sans-serif'; ctx.textAlign='right';
    ctx.fillText(Math.round(max*i/4),pad.l-4,y+3);
  }}
  // Gradient fill
  const pts = DAILY.map((d,i)=>{{
    return [pad.l+i/(DAILY.length-1)*W2, pad.t+H2*(1-d.count/max)];
  }});
  const grad = ctx.createLinearGradient(0,pad.t,0,H-pad.b);
  grad.addColorStop(0,'rgba(0,229,255,.35)');
  grad.addColorStop(1,'rgba(0,229,255,0)');
  ctx.beginPath();
  ctx.moveTo(pts[0][0],H-pad.b);
  pts.forEach(p=>ctx.lineTo(p[0],p[1]));
  ctx.lineTo(pts[pts.length-1][0],H-pad.b);
  ctx.closePath(); ctx.fillStyle=grad; ctx.fill();
  // Line
  ctx.beginPath(); ctx.strokeStyle='#00e5ff'; ctx.lineWidth=2;
  pts.forEach((p,i)=>i===0?ctx.moveTo(...p):ctx.lineTo(...p));
  ctx.stroke();
  // Dots
  pts.forEach((p,i)=>{{
    if(DAILY[i].count>0){{
      ctx.beginPath(); ctx.arc(p[0],p[1],3,0,Math.PI*2);
      ctx.fillStyle='#00e5ff'; ctx.fill();
    }}
  }});
  // X labels (every 2 days)
  ctx.fillStyle='#445566'; ctx.font='9px sans-serif'; ctx.textAlign='center';
  DAILY.forEach((d,i)=>{{
    if(i%2===0){{
      const x=pad.l+i/(DAILY.length-1)*W2;
      ctx.fillText(d.date.slice(5), x, H-4);
    }}
  }});
}})();

// ── Bar charts ───────────────────────────────────────────────
function renderBars(el, data, colors) {{
  const max = Math.max(...Object.values(data), 1);
  el.innerHTML = Object.entries(data).map(([k,v])=>{{
    const pct = v/max*100;
    const clr = colors?.[k] || '#00b4d8';
    return `<div class="bar-row">
      <div class="lbl">${{k.slice(0,9)}}</div>
      <div class="bar-wrap"><div class="bar" style="width:${{pct}}%;background:${{clr}}"></div></div>
      <span style="color:#778899;font-size:10px">${{v}}</span>
    </div>`;
  }}).join('');
}}
renderBars(document.getElementById('catBars'), CATS, null);
renderBars(document.getElementById('prioBars'), PRIOS, PRIO_COLORS);

// ── Filter & search ──────────────────────────────────────────
let _filter = 'all';
function setFilter(f, btn) {{
  _filter = f;
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  btn.classList.add('active');
  filterTable();
}}
function filterTable() {{
  const q = document.getElementById('search').value.toLowerCase();
  document.querySelectorAll('#taskBody tr').forEach(row => {{
    const st  = row.dataset.status;
    const txt = row.textContent.toLowerCase();
    const hasDue = row.querySelector('.due.overdue');
    const matchFilter = _filter==='all' || _filter===st || (_filter==='overdue'&&hasDue);
    const matchSearch = !q || txt.includes(q);
    row.style.display = matchFilter && matchSearch ? '' : 'none';
  }});
}}

// ── Sort ─────────────────────────────────────────────────────
let _sortDir = 1;
function sortBy(col) {{
  const tbody = document.getElementById('taskBody');
  const rows  = Array.from(tbody.querySelectorAll('tr'));
  const idx   = {{name:0,priority:1,status:2,due:3}}[col];
  rows.sort((a,b) => {{
    const av=a.cells[idx]?.textContent.trim()||'';
    const bv=b.cells[idx]?.textContent.trim()||'';
    return av.localeCompare(bv)*_sortDir;
  }});
  _sortDir *= -1;
  rows.forEach(r=>tbody.appendChild(r));
}}

// ── API helpers ───────────────────────────────────────────────
function toast(msg, err=false) {{
  const el=document.getElementById('toast');
  el.textContent=msg;
  el.style.borderColor=err?'#e74c3c':'#2ecc71';
  el.classList.add('show');
  setTimeout(()=>el.classList.remove('show'),2500);
}}

async function toggleStatus(id, currentStatus) {{
  const next = currentStatus==='todo'?'in_progress':currentStatus==='in_progress'?'done':'todo';
  const r = await fetch(`/api/tasks/${{id}}`,{{
    method:'PATCH', headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{status:next}})
  }});
  if(r.ok){{ toast(`Status → ${{next}}`); setTimeout(()=>location.reload(),800); }}
  else toast('Error', true);
}}

async function deleteTask(id) {{
  if(!confirm('Delete this task?')) return;
  const r = await fetch(`/api/tasks/${{id}}`,{{method:'DELETE'}});
  if(r.ok){{ toast('Deleted'); setTimeout(()=>location.reload(),600); }}
  else toast('Error', true);
}}

async function addTask() {{
  const name = document.getElementById('newName').value.trim();
  if(!name){{ document.getElementById('newName').focus(); return; }}
  const prio = document.getElementById('newPrio').value;
  const cat  = document.getElementById('newCat').value;
  const due  = document.getElementById('newDue').value;
  const r = await fetch('/api/tasks',{{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{name,priority:prio,category:cat,due_date:due,estimated_hours:1.0}})
  }});
  if(r.ok){{ toast(`Created: ${{name}}`); setTimeout(()=>location.reload(),600); }}
  else toast('Error creating task', true);
}}

// ── Enter key for add ────────────────────────────────────────
document.getElementById('newName').addEventListener('keydown', e=>{{
  if(e.key==='Enter') addTask();
}});

// ── Auto-refresh every 30s ────────────────────────────────────
setTimeout(()=>location.reload(), 30000);
document.getElementById('search').focus();
</script>
</body></html>"""


# ─────────────────────────────────────────────────────────────
# REST API handler
# ─────────────────────────────────────────────────────────────

def _jb(obj) -> bytes:
    return json.dumps(obj, default=str, indent=2).encode()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass   # silence

    def _send(self, code, ctype, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, "text/plain", b"")

    def _read_body(self) -> dict:
        n = int(self.headers.get("Content-Length",0))
        return json.loads(self.rfile.read(n)) if n else {}

    def do_GET(self):
        global _req_count
        _req_count += 1
        parsed = urlparse(self.path)
        p      = parsed.path.rstrip("/") or "/"
        qs     = parse_qs(parsed.query)

        if p in ("/","/index.html"):
            self._send(200, "text/html; charset=utf-8", _build_html(_db_ref).encode()); return

        if p == "/api/tasks":
            tasks = list(_db_ref.get("tasks",[]))
            # Optional filters
            status = qs.get("status",[None])[0]
            cat    = qs.get("category",[None])[0]
            q      = qs.get("q",[None])[0]
            if status: tasks=[t for t in tasks if t.get("status")==status]
            if cat:    tasks=[t for t in tasks if t.get("category")==cat]
            if q:
                q=q.lower()
                tasks=[t for t in tasks if q in t.get("name","").lower()
                        or q in " ".join(t.get("tags",[])).lower()]
            self._send(200,"application/json",_jb({"tasks":tasks,"total":len(tasks)})); return

        if p.startswith("/api/tasks/"):
            tid  = unquote(p.split("/api/tasks/",1)[1])
            task = next((t for t in _db_ref.get("tasks",[]) if t.get("id")==tid), None)
            if not task: self._send(404,"application/json",_jb({"error":"not found"})); return
            self._send(200,"application/json",_jb(task)); return

        if p == "/api/stats":
            tasks = _db_ref.get("tasks",[])
            done  = [t for t in tasks if t.get("status")=="done"]
            todo  = [t for t in tasks if t.get("status") in ("todo","in_progress")]
            self._send(200,"application/json",_jb({
                "total":len(tasks),"done":len(done),"pending":len(todo),
                "rate":round(len(done)/len(tasks)*100,1) if tasks else 0,
                "requests": _req_count,
                "uptime_s": int(time.time()-_start_time),
            })); return

        self._send(404,"application/json",_jb({"error":"not found"}))

    def do_POST(self):
        p = urlparse(self.path).path
        if p == "/api/tasks":
            import uuid as _uuid
            data = self._read_body()
            name = data.get("name","").strip()
            if not name:
                self._send(400,"application/json",_jb({"error":"name required"})); return
            PRIO_SCORE = {"Critical":5,"High":4,"Medium":3,"Low":2,"Minimal":1}
            prio = data.get("priority","Medium")
            task = {
                "id":             str(_uuid.uuid4())[:8],
                "name":           name,
                "priority":       prio,
                "priority_score": PRIO_SCORE.get(prio,3),
                "category":       data.get("category","Work"),
                "status":         "todo",
                "due_date":       data.get("due_date",""),
                "estimated_hours":float(data.get("estimated_hours",1.0)),
                "actual_hours":   None,
                "description":    data.get("description",""),
                "tags":           data.get("tags",[]),
                "recurrence":     "none",
                "parent_id":      None,
                "created_at":     datetime.now().isoformat(),
                "completed_at":   None,
                "started_at":     None,
            }
            _db_ref.setdefault("tasks",[]).append(task)
            _save_db()
            self._send(201,"application/json",_jb(task))
        else:
            self._send(404,"application/json",_jb({"error":"not found"}))

    def do_PATCH(self):
        p   = urlparse(self.path).path
        if p.startswith("/api/tasks/"):
            tid  = unquote(p.split("/api/tasks/",1)[1])
            data = self._read_body()
            for t in _db_ref.get("tasks",[]):
                if t.get("id") == tid:
                    old_status = t.get("status")
                    t.update(data)
                    if data.get("status") == "done" and old_status != "done":
                        t["completed_at"] = datetime.now().isoformat()
                    elif data.get("status") and data["status"] != "done":
                        pass
                    _save_db()
                    self._send(200,"application/json",_jb(t)); return
            self._send(404,"application/json",_jb({"error":"not found"}))
        else:
            self._send(404,"application/json",_jb({"error":"not found"}))

    def do_DELETE(self):
        p = urlparse(self.path).path
        if p.startswith("/api/tasks/"):
            tid = unquote(p.split("/api/tasks/",1)[1])
            before = len(_db_ref.get("tasks",[]))
            _db_ref["tasks"] = [t for t in _db_ref.get("tasks",[]) if t.get("id")!=tid]
            if len(_db_ref["tasks"]) < before:
                _save_db()
                self._send(200,"application/json",_jb({"ok":True}))
            else:
                self._send(404,"application/json",_jb({"error":"not found"}))
        else:
            self._send(404,"application/json",_jb({"error":"not found"}))


# ─────────────────────────────────────────────────────────────
# Save helper (write back to tasks.json)
# ─────────────────────────────────────────────────────────────

_save_fn = None   # set by on_startup

def _save_db():
    if _save_fn:
        try: _save_fn()
        except Exception: pass


# ─────────────────────────────────────────────────────────────
# Plugin interface
# ─────────────────────────────────────────────────────────────

def _start(port: int, db: dict, save_fn):
    global _server, _db_ref, _port, _save_fn
    _db_ref  = db
    _port    = port
    _save_fn = save_fn
    try:
        _server = ThreadingHTTPServer(("", port), Handler)
        _server.serve_forever()
    except Exception:
        _server = None

def _stop():
    global _server
    if _server:
        _server.shutdown()
        _server = None


def _screen(api):
    store = api.store
    console = api.console

    while True:
        os.system("clear")
        console.print()
        console.print("  [bold]⚡ TaskFlow  ·  🌐 Web Dashboard  v2[/]\n")

        port    = int(store.get("port", _port))
        running = _server is not None

        from rich.panel import Panel
        console.print(Panel(
            f"  Status:    {'[green]running[/]' if running else '[yellow]stopped[/]'}\n"
            f"  Dashboard: [bold]http://localhost:{port}/[/]\n"
            f"  REST API:  [dim]http://localhost:{port}/api/tasks[/]\n"
            f"             [dim]http://localhost:{port}/api/stats[/]\n\n"
            "  [dim]Full read/write REST API — create, update, delete tasks from any HTTP client.\n"
            "  Dashboard auto-refreshes every 30 seconds.[/]",
            border_style="#1a2a44", padding=(0,1)
        ))
        console.print()
        if not running:
            console.print("  [bold]s[/]  Start server")
        else:
            console.print("  [bold]x[/]  Stop server")
            console.print("  [bold]o[/]  Open in browser")
        console.print("  [bold]p[/]  Change port")
        console.print("  [bold]b[/]  Back\n")

        ch = api.prompt(">").strip().lower()
        if ch == "b": return
        elif ch == "s" and not running:
            port = int(store.get("port", _port))
            def save_fn():
                import json as _j
                from pathlib import Path as _P
                p = _P.home() / ".taskflow" / "tasks.json"
                p.write_text(_j.dumps(api.db, indent=2, default=str))
            t = threading.Thread(target=_start, args=(port, api.db, save_fn), daemon=True)
            t.start()
            time.sleep(0.3)
            store["port"]    = port
            store["running"] = True
            api.store_save()
            console.print(f"  [green]✓ Running at http://localhost:{port}/[/]")
            api.press_enter()
        elif ch == "x" and running:
            _stop()
            store["running"] = False
            api.store_save()
            console.print("  [dim]Stopped.[/]"); api.press_enter()
        elif ch == "o" and running:
            import subprocess
            try: subprocess.Popen(["xdg-open", f"http://localhost:{store.get('port',_port)}/"])
            except Exception: console.print(f"  Open: http://localhost:{store.get('port',_port)}/")
            api.press_enter()
        elif ch == "p":
            raw = api.prompt("Port", default=str(store.get("port", _port)))
            try:
                store["port"] = int(raw)
                api.store_save()
                console.print(f"  [green]✓ Port set to {store['port']}.[/]")
            except Exception: console.print("  [red]Invalid port.[/]")
            api.press_enter()


def on_startup(api):
    global _db_ref
    _db_ref = api.db
    store   = api.store

    def widget(api):
        if _server:
            port = store.get("port", _port)
            return f"  🌐 [dim]Web dashboard at http://localhost:{port}/[/]"
        return ""
    api.register_dashboard_widget(widget)

    if store.get("running") and _server is None:
        port = int(store.get("port", _port))
        def save_fn():
            import json as _j; from pathlib import Path as _P
            _P.home().joinpath(".taskflow","tasks.json").write_text(_j.dumps(api.db,indent=2,default=str))
        t = threading.Thread(target=_start, args=(port, api.db, save_fn), daemon=True)
        t.start()


def on_task_created(api, task):
    global _db_ref
    _db_ref = api.db

def on_task_done(api, task):
    global _db_ref
    _db_ref = api.db

def on_task_deleted(api, task):
    global _db_ref
    _db_ref = api.db


def menu_items(api):
    running = _server is not None
    port    = api.store.get("port", _port)
    label   = f"🌐 Web Dashboard [{'[green]:{port}[/]' if running else '[dim]stopped[/]'}]"
    return [("W", label, lambda: _screen(api))]
