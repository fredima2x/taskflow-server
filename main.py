#!/usr/bin/env python3
"""
TaskFlow Plugin Registry Server
Serves a catalogue of plugins that TaskFlow clients can browse and install.

Usage:
    python3 plugin_server.py              # start on :8888
    python3 plugin_server.py --port 9000
    python3 plugin_server.py --host 0.0.0.0 --port 8888

The server reads plugins from ./registry/ — each plugin is a .py file
with a metadata header block.  Example:

    # PLUGIN_NAME    = "My Plugin"
    # PLUGIN_VERSION = "1.2"
    # PLUGIN_DESC    = "Does something cool"
    # PLUGIN_AUTHOR  = "you"
    # PLUGIN_TAGS    = "productivity, timer"

Drop bundled plugins into ./registry/ and they appear in the catalogue.
"""

import json, sys, os, re, hashlib, argparse
from http.server     import BaseHTTPRequestHandler, HTTPServer
from pathlib         import Path
from datetime        import datetime
from urllib.parse    import urlparse, parse_qs

REGISTRY_DIR = Path(__file__).parent / "registry"
PORT_DEFAULT = 8888
SERVER_VERSION = "1.0"

# ── Metadata parser ───────────────────────────────────────────────────────────

def _parse_meta(source: str, filename: str) -> dict:
    """Extract PLUGIN_* constants from source (both comment and assignment forms)."""
    def _get(key):
        # assignment form:  PLUGIN_NAME = "value"
        m = re.search(rf'^{key}\s*=\s*["\'](.+?)["\']', source, re.MULTILINE)
        if m: return m.group(1)
        # comment form:  # PLUGIN_NAME = "value"
        m = re.search(rf'^#\s*{key}\s*=\s*["\'](.+?)["\']', source, re.MULTILINE)
        if m: return m.group(1)
        return ""

    name    = _get("PLUGIN_NAME")    or filename.replace(".py","").replace("_"," ").title()
    version = _get("PLUGIN_VERSION") or "1.0"
    desc    = _get("PLUGIN_DESC")    or ""
    author  = _get("PLUGIN_AUTHOR")  or "community"
    tags    = [t.strip() for t in _get("PLUGIN_TAGS").split(",") if t.strip()]
    sha256  = hashlib.sha256(source.encode()).hexdigest()[:16]

    return {
        "filename": filename,
        "name":     name,
        "version":  version,
        "desc":     desc,
        "author":   author,
        "tags":     tags,
        "sha256":   sha256,
        "size":     len(source),
    }

def _load_registry() -> list:
    REGISTRY_DIR.mkdir(exist_ok=True)
    plugins = []
    for f in sorted(REGISTRY_DIR.glob("*.py")):
        try:
            src  = f.read_text(encoding="utf-8")
            meta = _parse_meta(src, f.name)
            plugins.append(meta)
        except Exception as e:
            plugins.append({"filename": f.name, "name": f.name,
                            "error": str(e), "version":"?",
                            "desc":"", "author":"", "tags":[], "sha256":"", "size":0})
    return plugins

# ── HTML UI ───────────────────────────────────────────────────────────────────

def _html_index() -> str:
    plugins = _load_registry()

    cards = ""
    for p in plugins:
        tags_html = " ".join(f'<span class="tag">{t}</span>' for t in p.get("tags",[]))
        err       = f'<div class="error">{p["error"]}</div>' if "error" in p else ""
        size_kb   = f'{p["size"]/1024:.1f} KB' if p.get("size") else "?"
        cards += f"""
        <div class="card">
          <div class="card-header">
            <span class="name">{p["name"]}</span>
            <span class="version">v{p["version"]}</span>
          </div>
          <div class="desc">{p.get("desc","")}</div>
          {tags_html}
          <div class="meta">by {p.get("author","?")} · {size_kb} · sha256:{p.get("sha256","?")}</div>
          {err}
          <a class="btn" href="/plugin/{p['filename']}">⬇ Download</a>
          <a class="btn btn-raw" href="/raw/{p['filename']}">Raw</a>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>TaskFlow Plugin Registry</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root {{
    --bg:#0b0b18; --bg2:#111828; --border:#1a2a44;
    --primary:#00e5ff; --dim:#556688; --text:#ddeeff;
    --success:#2ecc71; --accent:#9b59b6;
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;
        padding:32px;max-width:1100px;margin:0 auto}}
  h1{{color:var(--primary);font-size:26px;margin-bottom:4px}}
  .sub{{color:var(--dim);font-size:13px;margin-bottom:32px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}}
  .card{{background:var(--bg2);border:1px solid var(--border);border-radius:10px;
         padding:20px;display:flex;flex-direction:column;gap:10px}}
  .card-header{{display:flex;justify-content:space-between;align-items:baseline}}
  .name{{font-weight:700;font-size:16px;color:var(--primary)}}
  .version{{font-size:12px;color:var(--dim);background:var(--border);
            padding:2px 8px;border-radius:4px}}
  .desc{{color:#aabbcc;font-size:13px;line-height:1.5}}
  .tag{{display:inline-block;background:#1a2a44;color:#778899;
        padding:2px 8px;border-radius:4px;font-size:11px;margin-right:4px}}
  .meta{{font-size:11px;color:var(--dim)}}
  .error{{color:#e74c3c;font-size:12px}}
  .btn{{display:inline-block;margin-top:4px;margin-right:8px;padding:6px 14px;
        background:var(--primary);color:#000;border-radius:5px;text-decoration:none;
        font-size:13px;font-weight:600}}
  .btn-raw{{background:var(--border);color:var(--text)}}
  .btn:hover{{opacity:.85}}
  .count{{color:var(--dim);font-size:13px;margin-bottom:16px}}
  footer{{margin-top:40px;color:var(--dim);font-size:12px;text-align:center}}
</style>
</head>
<body>
<h1>⚡ TaskFlow Plugin Registry</h1>
<div class="sub">v{SERVER_VERSION} · Install via TaskFlow → Plugins → Install from Registry</div>
<div class="count">{len(plugins)} plugin{'s' if len(plugins)!=1 else ''} available</div>
<div class="grid">{cards}</div>
<footer>TaskFlow Plugin Registry · {datetime.now():%Y-%m-%d}</footer>
</body></html>"""

# ── API responses ─────────────────────────────────────────────────────────────

def _json(obj) -> bytes:
    return json.dumps(obj, indent=2).encode()

# ── Request handler ───────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"  [{ts}] {fmt % args}")

    def _send(self, code, ctype, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/") or "/"
        qs     = parse_qs(parsed.query)

        # GET /
        if path == "/":
            self._send(200, "text/html; charset=utf-8", _html_index().encode())

        # GET /api/plugins  — list all
        elif path == "/api/plugins":
            plugins = _load_registry()
            tag     = qs.get("tag",  [None])[0]
            q       = qs.get("q",    [None])[0]
            if tag:
                plugins = [p for p in plugins if tag in p.get("tags",[])]
            if q:
                q = q.lower()
                plugins = [p for p in plugins
                           if q in p["name"].lower() or q in p.get("desc","").lower()]
            self._send(200, "application/json", _json({"plugins": plugins, "total": len(plugins)}))

        # GET /api/plugins/<filename>  — metadata only
        elif path.startswith("/api/plugins/"):
            fname = Path(path).name
            f     = REGISTRY_DIR / fname
            if not f.exists() or f.suffix != ".py":
                self._send(404, "application/json", _json({"error": "not found"}))
                return
            src  = f.read_text()
            meta = _parse_meta(src, fname)
            self._send(200, "application/json", _json(meta))

        # GET /plugin/<filename>  — download (attachment)
        elif path.startswith("/plugin/"):
            fname = Path(path).name
            f     = REGISTRY_DIR / fname
            if not f.exists() or f.suffix != ".py":
                self._send(404, "text/plain", b"not found")
                return
            body = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/x-python")
            self.send_header("Content-Length", len(body))
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        # GET /raw/<filename>  — view source
        elif path.startswith("/raw/"):
            fname = Path(path).name
            f     = REGISTRY_DIR / fname
            if not f.exists() or f.suffix != ".py":
                self._send(404, "text/plain", b"not found")
                return
            self._send(200, "text/plain; charset=utf-8", f.read_bytes())

        else:
            self._send(404, "text/plain", b"not found")

    def do_POST(self):
        """POST /api/publish — upload a plugin (for local dev use)."""
        parsed = urlparse(self.path)
        if parsed.path != "/api/publish":
            self._send(404, "application/json", _json({"error": "not found"}))
            return
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        try:
            data  = json.loads(body)
            fname = Path(data["filename"]).name
            if not fname.endswith(".py"):
                raise ValueError("Must be a .py file")
            code  = data["code"]
            REGISTRY_DIR.mkdir(exist_ok=True)
            (REGISTRY_DIR / fname).write_text(code, encoding="utf-8")
            meta  = _parse_meta(code, fname)
            self._send(200, "application/json", _json({"ok": True, "plugin": meta}))
        except Exception as e:
            self._send(400, "application/json", _json({"error": str(e)}))


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="TaskFlow Plugin Registry Server")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=PORT_DEFAULT)
    args = ap.parse_args()

    REGISTRY_DIR.mkdir(exist_ok=True)

    # Seed with bundled plugins if registry is empty
    bundled_dir = Path(__file__).parent / "plugins"
    if bundled_dir.exists() and not list(REGISTRY_DIR.glob("*.py")):
        for f in bundled_dir.glob("*.py"):
            import shutil
            shutil.copy(f, REGISTRY_DIR / f.name)
            print(f"  Seeded: {f.name}")

    plugins = _load_registry()
    print(f"\n  ⚡  TaskFlow Plugin Registry  v{SERVER_VERSION}")
    print(f"  {len(plugins)} plugin(s) in registry/")
    print(f"\n  Listening on  http://{args.host}:{args.port}")
    print(f"  API:          http://{args.host}:{args.port}/api/plugins")
    print(f"  Press Ctrl+C to stop\n")

    server = HTTPServer((args.host, args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")

if __name__ == "__main__":
    main()