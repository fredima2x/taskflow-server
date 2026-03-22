#!/usr/bin/env python3
"""
TaskFlow Plugin Registry Server  v2
====================================
Hosts plugins AND taskflow.py with SHA-256 + HMAC-SHA256 integrity verification.

Usage:
    python3 plugin_server.py                         # port 8888
    python3 plugin_server.py --port 9000
    python3 plugin_server.py --sign-key mysecret     # enable HMAC signing
    python3 plugin_server.py --sign-all --sign-key K # sign all files + start
    python3 plugin_server.py --list                  # list registry
    python3 plugin_server.py --verify --sign-key K   # verify sigs
    python3 plugin_server.py --seed                  # seed from ./plugins/

Directory layout:
    plugin_server.py
    registry/          <- plugins (.py)
    app/
        taskflow.py    <- main app  (GET /app/taskflow.py)
        version.json   <- {"version":"3.0","changelog":"...","sha256":"..."}
    signatures/        <- <file>.sig  (HMAC-SHA256 hex, optional)
"""

import json, sys, os, re, hashlib, hmac as _hmac_mod, argparse, shutil, mimetypes, threading
from http.server  import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib      import Path
from datetime     import datetime
from urllib.parse import urlparse, parse_qs
from collections  import defaultdict

BASE_DIR     = Path(__file__).parent
REGISTRY_DIR = BASE_DIR / "registry"
APP_DIR      = BASE_DIR / "app"
SIGS_DIR     = BASE_DIR / "signatures"
LOG_FILE     = BASE_DIR / "access.log"

SERVER_VERSION = "2.0"
SIGN_KEY: str  = ""
_stats: dict   = defaultdict(int)


# ─────────────────────────────────────────────────────────────
# SHA / HMAC helpers
# ─────────────────────────────────────────────────────────────

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def sha256s(data: bytes) -> str:
    return sha256(data)[:16]

def hmac_sign(data: bytes, key: str) -> str:
    return _hmac_mod.new(key.encode(), data, hashlib.sha256).hexdigest()

def hmac_ok(data: bytes, sig: str, key: str) -> bool:
    return _hmac_mod.compare_digest(hmac_sign(data, key), sig)

def _sig_for(fname: str) -> str:
    p = SIGS_DIR / f"{fname}.sig"
    return p.read_text().strip() if p.exists() else ""


# ─────────────────────────────────────────────────────────────
# Metadata
# ─────────────────────────────────────────────────────────────

def _rx(src: str, key: str) -> str:
    for pat in (rf'^{key}\s*=\s*["\'](.+?)["\']',
                rf'^#\s*{key}\s*=\s*["\'](.+?)["\']'):
        m = re.search(pat, src, re.MULTILINE)
        if m: return m.group(1)
    return ""

def plugin_meta(path: Path) -> dict:
    try:
        raw  = path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        full = sha256(raw)
        return {
            "filename":    path.name,
            "name":        _rx(text,"PLUGIN_NAME")    or path.stem.replace("_"," ").title(),
            "version":     _rx(text,"PLUGIN_VERSION") or "1.0",
            "desc":        _rx(text,"PLUGIN_DESC")    or "",
            "author":      _rx(text,"PLUGIN_AUTHOR")  or "community",
            "tags":        [t.strip() for t in _rx(text,"PLUGIN_TAGS").split(",") if t.strip()],
            "min_api":     _rx(text,"PLUGIN_MIN_API") or "1.0",
            "sha256":      full[:16],
            "sha256_full": full,
            "hmac":        _sig_for(path.name),
            "size":        len(raw),
            "updated":     datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d"),
        }
    except Exception as e:
        return {"filename":path.name,"name":path.name,"error":str(e),
                "version":"?","desc":"","author":"","tags":[],"sha256":"",
                "sha256_full":"","hmac":"","size":0,"updated":"?"}

def all_plugins() -> list:
    REGISTRY_DIR.mkdir(exist_ok=True)
    return [plugin_meta(f) for f in sorted(REGISTRY_DIR.glob("*.py"))]

def app_info() -> dict:
    ap  = APP_DIR / "taskflow.py"
    vj  = APP_DIR / "version.json"
    out = {}
    if vj.exists():
        try: out = json.loads(vj.read_text())
        except Exception: pass
    if ap.exists():
        raw = ap.read_bytes()
        out.update(available=True, sha256=sha256(raw)[:16],
                   sha256_full=sha256(raw), size=len(raw),
                   hmac=_sig_for("taskflow.py"))
    else:
        out["available"] = False
    return out


# ─────────────────────────────────────────────────────────────
# Web UI
# ─────────────────────────────────────────────────────────────

def _html() -> str:
    plugins = all_plugins()
    ainfo   = app_info()
    now     = datetime.now()

    app_card = ""
    if ainfo.get("available"):
        signed = '<span style="color:#2ecc71;font-weight:600">✓ signed</span>' if ainfo.get("hmac") else ""
        app_card = f"""
      <div style="background:#0f1635;border:2px solid #00e5ff;border-radius:12px;padding:20px;margin-bottom:28px">
        <div style="display:flex;justify-content:space-between;font-size:18px;font-weight:700;color:#00e5ff;margin-bottom:8px">
          <span>⚡ TaskFlow</span><span style="font-size:12px;background:#1a2a44;padding:2px 10px;border-radius:4px">v{ainfo.get('version','?')}</span>
        </div>
        <div style="color:#aabbcc;font-size:13px;margin-bottom:6px">{ainfo.get('changelog','Main application')}</div>
        <div style="font-size:11px;color:#556688">SHA-256: <code style="background:#1a2a44;padding:1px 5px;border-radius:3px">{ainfo.get('sha256','?')}</code> · {ainfo.get('size',0)//1024} KB {signed}</div>
        <div style="margin-top:10px">
          <a href="/app/taskflow.py" style="display:inline-block;padding:6px 16px;background:#00e5ff;color:#000;border-radius:5px;text-decoration:none;font-weight:600;font-size:13px;margin-right:8px">⬇ Download taskflow.py</a>
          <a href="/api/app" style="display:inline-block;padding:6px 14px;background:#1a2a44;color:#ddeeff;border-radius:5px;text-decoration:none;font-size:12px">JSON info</a>
        </div>
      </div>"""

    cards = ""
    for p in plugins:
        tags  = " ".join(f'<span style="background:#1a2a44;color:#778899;padding:2px 7px;border-radius:4px;font-size:11px;margin-right:4px">{t}</span>' for t in p.get("tags",[]))
        err   = f'<div style="color:#e74c3c;font-size:12px;margin-top:4px">⚠ {p["error"]}</div>' if "error" in p else ""
        signed= '<span style="color:#2ecc71;font-size:11px">✓ signed</span>' if p.get("hmac") else ""
        cards += f"""
      <div style="background:#111828;border:1px solid #1a2a44;border-radius:10px;padding:18px;display:flex;flex-direction:column;gap:7px">
        <div style="display:flex;justify-content:space-between;align-items:baseline">
          <span style="font-weight:700;font-size:15px;color:#00e5ff">{p['name']}</span>
          <span style="font-size:11px;color:#556688;background:#1a2a44;padding:2px 8px;border-radius:4px">v{p['version']}</span>
        </div>
        <div style="color:#aabbcc;font-size:13px">{p.get('desc','')}</div>
        <div>{tags}</div>
        <div style="font-size:11px;color:#556688">by {p.get('author','?')} · {p.get('size',0)//1024} KB · {p.get('updated','?')} {signed}</div>
        <div style="font-size:11px;color:#556688">SHA: <code style="background:#1a2a44;padding:1px 5px;border-radius:3px">{p.get('sha256','?')}</code></div>
        {err}
        <div style="display:flex;gap:6px;margin-top:4px">
          <a href="/plugin/{p['filename']}" style="padding:5px 12px;background:#00e5ff;color:#000;border-radius:4px;text-decoration:none;font-size:12px;font-weight:600">⬇ Install</a>
          <a href="/raw/{p['filename']}"    style="padding:5px 12px;background:#1a2a44;color:#ddeeff;border-radius:4px;text-decoration:none;font-size:12px">Source</a>
          <a href="/api/plugins/{p['filename']}" style="padding:5px 12px;background:#1a2a44;color:#ddeeff;border-radius:4px;text-decoration:none;font-size:12px">JSON</a>
        </div>
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>TaskFlow Registry</title>
<style>
  body{{background:#0b0b18;color:#ddeeff;font-family:'Segoe UI',system-ui,sans-serif;
       padding:32px;max-width:1200px;margin:0 auto}}
  a{{color:inherit}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}}
  footer{{margin-top:40px;color:#556688;font-size:11px;text-align:center;
          padding-top:16px;border-top:1px solid #1a2a44}}
</style>
</head><body>
<h1 style="color:#00e5ff;font-size:26px;margin-bottom:4px">⚡ TaskFlow Registry</h1>
<div style="color:#556688;font-size:13px;margin-bottom:24px">
  v{SERVER_VERSION} · {len(plugins)} plugins · SHA-256 verified · auto-refresh every 60s · {now:%Y-%m-%d %H:%M}
</div>
{app_card}
<div style="color:#556688;font-size:12px;text-transform:uppercase;letter-spacing:.1em;margin-bottom:12px;border-bottom:1px solid #1a2a44;padding-bottom:6px">
  {len(plugins)} Plugin{'s' if len(plugins)!=1 else ''}
</div>
<div class="grid">{cards}</div>
<footer>TaskFlow Plugin Registry v{SERVER_VERSION} · All downloads verified with SHA-256</footer>
</body></html>"""


# ─────────────────────────────────────────────────────────────
# HTTP handler
# ─────────────────────────────────────────────────────────────

def _jb(obj: dict) -> bytes:
    return json.dumps(obj, indent=2).encode()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        ts  = datetime.now().strftime("%H:%M:%S")
        msg = f"[{ts}] {self.address_string()} {fmt % args}"
        print(f"  {msg}")
        try:
            with open(LOG_FILE, "a") as fh: fh.write(msg + "\n")
        except Exception: pass

    def _send(self, code, ctype, body: bytes, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Registry-Version", SERVER_VERSION)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers(); self.wfile.write(body)

    def _send_file(self, path: Path, attachment=False):
        if not path.exists():
            self._send(404, "text/plain", b"not found"); return
        raw  = path.read_bytes()
        full = sha256(raw)
        hdrs = {"X-SHA256": full, "X-SHA256-Short": full[:16]}
        sig  = _sig_for(path.name)
        if sig: hdrs["X-HMAC-SHA256"] = sig
        if attachment:
            hdrs["Content-Disposition"] = f'attachment; filename="{path.name}"'
        ctype = "text/x-python; charset=utf-8" if path.suffix == ".py" else \
                (mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        _stats[path.name] = _stats.get(path.name, 0) + 1
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(raw))
        for k, v in hdrs.items(): self.send_header(k, v)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        parsed = urlparse(self.path)
        p      = parsed.path.rstrip("/") or "/"
        qs     = parse_qs(parsed.query)
        _stats["requests"] = _stats.get("requests",0) + 1

        if p == "/":
            self._send(200, "text/html; charset=utf-8", _html().encode()); return

        if p == "/api/plugins":
            pl  = all_plugins()
            q   = qs.get("q",[None])[0]; tag = qs.get("tag",[None])[0]
            if q: q=q.lower(); pl=[x for x in pl if q in x["name"].lower() or q in x.get("desc","").lower()]
            if tag: pl=[x for x in pl if tag in x.get("tags",[])]
            self._send(200,"application/json",_jb({"plugins":pl,"total":len(pl)})); return

        if p.startswith("/api/plugins/"):
            fname = Path(p).name; f = REGISTRY_DIR/fname
            self._send(*(200,"application/json",_jb(plugin_meta(f))) if f.exists() and f.suffix==".py"
                       else (404,"application/json",_jb({"error":"not found"}))); return

        if p == "/api/app":
            self._send(200,"application/json",_jb(app_info())); return

        if p == "/api/stats":
            self._send(200,"application/json",_jb(dict(_stats))); return

        if p.startswith("/api/verify/"):
            fname = Path(p).name; f = REGISTRY_DIR/fname
            if not f.exists(): self._send(404,"application/json",_jb({"error":"not found"})); return
            raw=f.read_bytes(); full=sha256(raw)
            out={"filename":fname,"sha256":full[:16],"sha256_full":full,"size":len(raw)}
            if SIGN_KEY: out["hmac"]=hmac_sign(raw,SIGN_KEY)
            self._send(200,"application/json",_jb(out)); return

        if p.startswith("/plugin/"):
            fname=Path(p).name
            self._send_file(REGISTRY_DIR/fname, attachment=True); return

        if p.startswith("/raw/"):
            self._send_file(REGISTRY_DIR/Path(p).name); return

        if p == "/app/taskflow.py":
            self._send_file(APP_DIR/"taskflow.py", attachment=True); return

        if p == "/app/version.json":
            self._send_file(APP_DIR/"version.json"); return

        self._send(404,"text/plain",b"not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length",0))
        body   = self.rfile.read(length)

        if parsed.path == "/api/publish":
            if SIGN_KEY:
                if not hmac_ok(body, self.headers.get("X-HMAC-SHA256",""), SIGN_KEY):
                    self._send(401,"application/json",_jb({"error":"invalid signature"})); return
            try:
                data  = json.loads(body)
                fname = Path(data["filename"]).name
                if not fname.endswith(".py"): raise ValueError("Must be .py")
                code  = data["code"]
                (REGISTRY_DIR/fname).write_text(code, encoding="utf-8")
                meta  = plugin_meta(REGISTRY_DIR/fname)
                if SIGN_KEY:
                    SIGS_DIR.mkdir(exist_ok=True)
                    sig=(SIGS_DIR/f"{fname}.sig")
                    sig.write_text(hmac_sign(code.encode(),SIGN_KEY))
                    meta["hmac"]=sig.read_text().strip()
                self._send(200,"application/json",_jb({"ok":True,"plugin":meta}))
            except Exception as e:
                self._send(400,"application/json",_jb({"error":str(e)}))
            return

        if parsed.path == "/api/publish/app":
            if SIGN_KEY:
                if not hmac_ok(body, self.headers.get("X-HMAC-SHA256",""), SIGN_KEY):
                    self._send(401,"application/json",_jb({"error":"invalid signature"})); return
            try:
                data = json.loads(body)
                APP_DIR.mkdir(exist_ok=True)
                code = data["code"]; ver=data.get("version","?")
                (APP_DIR/"taskflow.py").write_text(code, encoding="utf-8")
                raw  = code.encode()
                vinfo= {"version":ver,"changelog":data.get("changelog",""),
                        "updated":datetime.now().isoformat(),"sha256":sha256(raw)[:16]}
                (APP_DIR/"version.json").write_text(json.dumps(vinfo,indent=2))
                if SIGN_KEY:
                    SIGS_DIR.mkdir(exist_ok=True)
                    (SIGS_DIR/"taskflow.py.sig").write_text(hmac_sign(raw,SIGN_KEY))
                self._send(200,"application/json",_jb({"ok":True,"version":ver}))
            except Exception as e:
                self._send(400,"application/json",_jb({"error":str(e)}))
            return

        self._send(404,"application/json",_jb({"error":"not found"}))


# ─────────────────────────────────────────────────────────────
# CLI management commands
# ─────────────────────────────────────────────────────────────

def cmd_sign_all(key: str):
    SIGS_DIR.mkdir(exist_ok=True)
    targets = list(REGISTRY_DIR.glob("*.py")) + [APP_DIR/"taskflow.py"]
    for f in targets:
        if not f.exists(): continue
        sig = hmac_sign(f.read_bytes(), key)
        (SIGS_DIR/f"{f.name}.sig").write_text(sig)
        print(f"  ✓ signed  {f.name:<40}  sha256:{sha256s(f.read_bytes())}  hmac:{sig[:16]}…")

def cmd_verify(key: str):
    ok = bad = no_sig = 0
    for f in list(REGISTRY_DIR.glob("*.py")) + [APP_DIR/"taskflow.py"]:
        if not f.exists(): continue
        sp = SIGS_DIR/f"{f.name}.sig"
        if not sp.exists(): print(f"  [no sig]  {f.name}"); no_sig+=1; continue
        good = hmac_ok(f.read_bytes(), sp.read_text().strip(), key)
        print(f"  [{'✓' if good else '✗ FAIL'}]  {f.name}")
        if good: ok+=1
        else:    bad+=1
    print(f"\n  OK:{ok}  FAIL:{bad}  NO_SIG:{no_sig}")

def cmd_list():
    pl = all_plugins(); ai = app_info()
    print(f"\n  ⚡ TaskFlow Registry  ({len(pl)} plugins)\n")
    if ai.get("available"):
        print(f"  [app]  taskflow.py  v{ai.get('version','?')}  sha256:{ai.get('sha256','?')}")
        print()
    for p in pl:
        sig = "✓" if p.get("hmac") else " "
        print(f"  [{sig}]  {p['filename']:<36}  v{p['version']:<8}  sha256:{p['sha256']}")


# ─────────────────────────────────────────────────────────────
# HTTP → HTTPS redirect server
# ─────────────────────────────────────────────────────────────

class RedirectHandler(BaseHTTPRequestHandler):
    """Listens on port 80, redirects every request to HTTPS."""
    https_port: int = 443

    def log_message(self, fmt, *args):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"  [{ts}] redirect {self.address_string()} {fmt % args}")

    def do_GET(self):  self._redirect()
    def do_POST(self): self._redirect()
    def do_HEAD(self): self._redirect()

    def _redirect(self):
        host = self.headers.get("Host","").split(":")[0]
        port = self.__class__.https_port
        loc  = f"https://{host}{':{}'.format(port) if port != 443 else ''}{self.path}"
        body = f"<a href='{loc}'>Redirecting to HTTPS</a>".encode()
        self.send_response(301)
        self.send_header("Location", loc)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


# ─────────────────────────────────────────────────────────────
# TLS certificate helpers
# ─────────────────────────────────────────────────────────────

def _find_letsencrypt_cert(domain: str) -> tuple[str, str]:
    """
    Try common Let's Encrypt paths for a given domain.
    Returns (cert_path, key_path) or ("","").
    """
    candidates = [
        # certbot default
        (f"/etc/letsencrypt/live/{domain}/fullchain.pem",
         f"/etc/letsencrypt/live/{domain}/privkey.pem"),
        # some distros use just the domain without www
        (f"/etc/letsencrypt/live/www.{domain}/fullchain.pem",
         f"/etc/letsencrypt/live/www.{domain}/privkey.pem"),
        # acme.sh default
        (f"/root/.acme.sh/{domain}_ecc/{domain}.cer",
         f"/root/.acme.sh/{domain}_ecc/{domain}.key"),
        (f"/root/.acme.sh/{domain}/{domain}.cer",
         f"/root/.acme.sh/{domain}/{domain}.key"),
    ]
    for cert, key in candidates:
        if Path(cert).exists() and Path(key).exists():
            return cert, key
    return "", ""


def _make_ssl_context(cert: str, key: str):
    import ssl
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=cert, keyfile=key)
    # Harden: disable old protocols
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    # HSTS-friendly cipher preference
    ctx.set_ciphers("ECDH+AESGCM:ECDH+CHACHA20:DH+AESGCM:!aNULL:!MD5:!RC4")
    return ctx


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

def main():
    global SIGN_KEY
    ap = argparse.ArgumentParser(
        description="TaskFlow Plugin Registry Server v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Plain HTTP on port 8888
  python3 plugin_server.py

  # HTTPS with Let's Encrypt cert for fredima.de (auto-detected)
  python3 plugin_server.py --https --domain fredima.de

  # HTTPS with explicit cert paths
  python3 plugin_server.py --https \\
      --cert /etc/letsencrypt/live/fredima.de/fullchain.pem \\
      --key  /etc/letsencrypt/live/fredima.de/privkey.pem

  # HTTPS on 443 + redirect HTTP 80 → 443
  python3 plugin_server.py --https --domain fredima.de --port 443 --http-redirect

  # HMAC signing + HTTPS
  python3 plugin_server.py --https --domain fredima.de --sign-key mysecret --sign-all

  # systemd: runs as root for port 443 (or use setcap)
  #   sudo setcap 'cap_net_bind_service=+ep' $(which python3)
""")
    ap.add_argument("--host",          default="0.0.0.0")
    ap.add_argument("--port",          type=int,  default=None,
                    help="Port (default: 443 if --https, else 8888)")
    ap.add_argument("--https",         action="store_true",
                    help="Enable TLS/HTTPS")
    ap.add_argument("--domain",        default="",
                    help="Domain for auto Let's Encrypt cert detection (e.g. fredima.de)")
    ap.add_argument("--cert",          default="",
                    help="Path to TLS certificate file (fullchain.pem)")
    ap.add_argument("--key",           default="",
                    help="Path to TLS private key file (privkey.pem)")
    ap.add_argument("--http-redirect", action="store_true",
                    help="Also listen on port 80 and redirect to HTTPS")
    ap.add_argument("--http-port",     type=int, default=80,
                    help="Port for HTTP→HTTPS redirect (default: 80)")
    ap.add_argument("--sign-key",      default="",
                    help="HMAC-SHA256 signing key for plugins and app")
    ap.add_argument("--sign-all",      action="store_true",
                    help="Sign all registry files before starting")
    ap.add_argument("--verify",        action="store_true",
                    help="Verify all signatures and exit")
    ap.add_argument("--list",          action="store_true",
                    help="List registry contents and exit")
    ap.add_argument("--seed",          action="store_true",
                    help="Seed registry from ./plugins/ and taskflow.py")
    args = ap.parse_args()
    SIGN_KEY = args.sign_key

    # One-shot commands
    if args.list:
        cmd_list(); return
    if args.verify and SIGN_KEY:
        cmd_verify(SIGN_KEY); return

    # Resolve port
    use_https = args.https
    port      = args.port or (443 if use_https else 8888)

    # Resolve cert/key
    cert = args.cert
    key  = args.key
    if use_https and (not cert or not key):
        domain = args.domain
        if domain:
            cert, key = _find_letsencrypt_cert(domain)
            if cert:
                print(f"  Auto-detected cert for {domain}: {cert}")
            else:
                print(f"  ✗  Could not find Let's Encrypt cert for '{domain}'")
                print(f"     Searched paths:")
                print(f"       /etc/letsencrypt/live/{domain}/fullchain.pem")
                print(f"       /root/.acme.sh/{domain}_ecc/{domain}.cer")
                print(f"     Use --cert and --key to specify paths manually.")
                sys.exit(1)
        if not cert or not key:
            print("  ✗  --https requires --cert + --key  or  --domain")
            print("     Example:")
            print("       python3 plugin_server.py --https \\")
            print("           --cert /etc/letsencrypt/live/fredima.de/fullchain.pem \\")
            print("           --key  /etc/letsencrypt/live/fredima.de/privkey.pem")
            sys.exit(1)

    # Setup dirs
    REGISTRY_DIR.mkdir(exist_ok=True)
    APP_DIR.mkdir(exist_ok=True)
    SIGS_DIR.mkdir(exist_ok=True)

    # Seed
    if args.seed or not list(REGISTRY_DIR.glob("*.py")):
        src = BASE_DIR / "plugins"
        if src.exists():
            n = sum(1 for f in src.glob("*.py")
                    if not (REGISTRY_DIR/f.name).exists()
                    and shutil.copy(f, REGISTRY_DIR/f.name) is None)
            if n: print(f"  Seeded {n} plugin(s) from ./plugins/")

    if args.seed or not (APP_DIR/"taskflow.py").exists():
        src = BASE_DIR / "taskflow.py"
        if src.exists():
            shutil.copy(src, APP_DIR/"taskflow.py")
            raw = src.read_bytes()
            vj  = APP_DIR / "version.json"
            if not vj.exists():
                vj.write_text(json.dumps({
                    "version":   "3.0",
                    "changelog": "Initial seeded release",
                    "updated":   datetime.now().isoformat(),
                    "sha256":    sha256(raw)[:16],
                }, indent=2))
            print("  Seeded taskflow.py → app/")

    # Sign
    if args.sign_all and SIGN_KEY:
        print("  Signing all files…")
        cmd_sign_all(SIGN_KEY)
        print()

    # Status output
    scheme = "https" if use_https else "http"
    domain_disp = args.domain or args.host
    pl = all_plugins(); ai = app_info()

    print(f"\n  ⚡  TaskFlow Plugin Registry  v{SERVER_VERSION}")
    print(f"  Plugins  : {len(pl)}")
    print(f"  App      : {'v'+ai.get('version','?') if ai.get('available') else 'not hosted (--seed)'}")
    print(f"  Signing  : {'HMAC-SHA256 (key: '+SIGN_KEY[:4]+'…)' if SIGN_KEY else 'disabled'}")
    print(f"  TLS      : {'✓ ' + cert if use_https else 'disabled (plain HTTP)'}")
    print(f"\n  Web UI   : {scheme}://{domain_disp}{':{}'.format(port) if port not in (80,443) else ''}/")
    print(f"  Plugins  : {scheme}://{domain_disp}{':{}'.format(port) if port not in (80,443) else ''}/api/plugins")
    print(f"  App      : {scheme}://{domain_disp}{':{}'.format(port) if port not in (80,443) else ''}/api/app")
    if args.http_redirect and use_https:
        print(f"  Redirect : http://{domain_disp}:{args.http_port}/ → {scheme}://")
    print(f"  Ctrl+C to stop\n")

    # Start HTTP → HTTPS redirect in background thread
    if args.http_redirect and use_https:
        RedirectHandler.https_port = port
        redir_server = ThreadingHTTPServer((args.host, args.http_port), RedirectHandler)
        t = threading.Thread(target=redir_server.serve_forever, daemon=True)
        t.start()
        print(f"  HTTP redirect listening on :{args.http_port}")

    # Build and start main server
    server = ThreadingHTTPServer((args.host, port), Handler)

    if use_https:
        import ssl
        try:
            ctx = _make_ssl_context(cert, key)
            server.socket = ctx.wrap_socket(server.socket, server_side=True)
            print(f"  TLS active — {cert}")
        except Exception as e:
            print(f"\n  ✗  TLS setup failed: {e}")
            print(f"     Check that cert and key files are readable.")
            sys.exit(1)

    print(f"  Listening on {args.host}:{port}  ({'HTTPS' if use_https else 'HTTP'})\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")

if __name__ == "__main__":
    main()
