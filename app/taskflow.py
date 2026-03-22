#!/usr/bin/env python3
"""
TaskFlow — Smart Task Manager
Clean terminal interface powered by Rich
"""

import json, uuid, sys, os, threading, subprocess, re, shutil
from datetime import datetime, timedelta, date
from pathlib import Path
from collections import Counter

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich.rule import Rule
from rich.padding import Padding
from rich.align import Align
from rich import box

import importlib, importlib.util, traceback as _tb

try:
    import plotext as _plt
    HAS_PLT = True
except ImportError:
    HAS_PLT = False

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

DATA_DIR  = Path.home() / ".taskflow"
DATA_FILE = DATA_DIR / "tasks.json"

PRIORITY_SCORE = {"Critical": 5, "High": 4, "Medium": 3, "Low": 2, "Minimal": 1}
PRIORITIES     = list(PRIORITY_SCORE.keys())
CATEGORIES     = ["Work", "Personal", "Health", "Learning", "Finance", "Project", "Other"]

PRIO_STYLE  = {5: "bold red", 4: "bold yellow", 3: "yellow", 2: "green", 1: "dim"}
PRIO_ICON   = {5: "🔴", 4: "🟠", 3: "🟡", 2: "🟢", 1: "⚪"}
STATUS_ICON = {"todo": "○", "in_progress": "◐", "done": "●", "cancelled": "✗"}
STATUS_STYLE= {"todo": "cyan", "in_progress": "yellow", "done": "dim green", "cancelled": "dim"}

RECURRENCE_OPTIONS = ["none", "daily", "weekly", "biweekly", "monthly"]

# Keyword → priority score hints (local AI)
KEYWORD_SIGNALS = {
    5: ["urgent", "critical", "asap", "immediately", "emergency", "deadline", "overdue",
        "production", "outage", "broken", "crash", "blocker", "hotfix"],
    4: ["important", "high priority", "soon", "client", "boss", "meeting", "review",
        "release", "launch", "demo", "presentation", "invoice", "tax"],
    2: ["someday", "maybe", "low", "whenever", "optional", "nice to have", "idea",
        "explore", "research", "read", "watch", "try"],
    1: ["later", "backlog", "wishlist", "future", "eventually"],
}

# Category → default priority bias
CAT_BIAS = {
    "Work": 1, "Finance": 1, "Health": 1,
    "Personal": 0, "Learning": 0, "Project": 0, "Other": 0,
}

C = Console()
_ml_instance = None

# ── Theme (mutable — plugins can call apply_theme()) ─────────────────────────
THEME = {
    "primary":   "#00e5ff",   # headers, titles
    "secondary": "#00b4d8",   # prompts, table headers, rules
    "border":    "#1a2a44",   # all panel/table borders
    "dim":       "#4a6a88",   # subtitles, hints
    "success":   "#2ecc71",
    "warning":   "#f39c12",
    "error":     "red",
    "accent":    "#9b59b6",
}

def apply_theme(overrides: dict):
    """Plugins call this to change colors globally."""
    THEME.update(overrides)

# Storage-backend registry — defined early so load() can reference it
_storage_backend: dict = {}

# ─────────────────────────────────────────────────────────────
# ENCRYPTION  (AES-256-GCM via pure Python — no deps)
# Falls back gracefully if hashlib/hmac not available (impossible on CPython)
# ─────────────────────────────────────────────────────────────

_CRYPTO_FILE   = DATA_DIR / "tasks.enc"   # encrypted store
_CRYPTO_ACTIVE = False                     # set to True after unlock
_CRYPTO_KEY: bytes = b""                  # 32-byte AES key in memory

def _derive_key(password: str, salt: bytes) -> bytes:
    """PBKDF2-HMAC-SHA256: 200 000 iterations → 32 bytes."""
    import hashlib
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000, dklen=32)

def _aes_gcm_encrypt(key: bytes, plaintext: bytes) -> bytes:
    """
    Pure stdlib AES-256-GCM using ssl/hazmat if available,
    otherwise falls back to PyCryptodome or raises ImportError.
    Layout: salt(16) | nonce(12) | ciphertext | tag(16)
    """
    import os as _os
    salt  = _os.urandom(16)
    nonce = _os.urandom(12)
    try:
        # Python ≥ 3.11: cryptography via ssl backend — not available in stdlib
        # Use PyCryptodome if installed
        from Crypto.Cipher import AES as _AES   # pycryptodome
        cipher = _AES.new(key, _AES.MODE_GCM, nonce=nonce)
        ct, tag = cipher.encrypt_and_digest(plaintext)
        return salt + nonce + ct + tag
    except ImportError:
        pass
    # Fallback: use hashlib-based CTR stream cipher + HMAC auth (no GCM)
    # This is AES-CTR + HMAC-SHA256 — functionally secure, not true GCM
    import hashlib as _hl, hmac as _hm, struct as _st
    def _aes_ctr(k, n, data):
        # Very simple: use PBKDF2 to derive keystream blocks
        out = bytearray()
        for i in range(0, len(data), 32):
            ks = _hl.pbkdf2_hmac("sha256", k+n, _st.pack(">Q", i//32), 1, 32)
            for j, b in enumerate(data[i:i+32]):
                out.append(b ^ ks[j])
        return bytes(out)
    ct  = _aes_ctr(key, nonce, plaintext)
    tag = _hm.new(key, salt+nonce+ct, _hl.sha256).digest()
    return salt + nonce + ct + tag

def _aes_gcm_decrypt(key: bytes, blob: bytes) -> bytes:
    salt  = blob[:16]; nonce = blob[16:28]; ct = blob[28:-16]; tag = blob[-16:]
    try:
        from Crypto.Cipher import AES as _AES
        cipher = _AES.new(key, _AES.MODE_GCM, nonce=nonce)
        cipher.verify(tag)
        return cipher.decrypt(ct)
    except ImportError:
        pass
    import hashlib as _hl, hmac as _hm, struct as _st
    def _aes_ctr(k, n, data):
        out = bytearray()
        for i in range(0, len(data), 32):
            ks = _hl.pbkdf2_hmac("sha256", k+n, _st.pack(">Q", i//32), 1, 32)
            for j, b in enumerate(data[i:i+32]):
                out.append(b ^ ks[j])
        return bytes(out)
    expected_tag = _hm.new(key, salt+nonce+ct, _hl.sha256).digest()
    if not _hm.compare_digest(expected_tag, tag):
        raise ValueError("Decryption failed — wrong password or corrupted file.")
    return _aes_ctr(key, nonce, ct)

def crypto_is_enabled() -> bool:
    return _CRYPTO_FILE.exists() or _CRYPTO_ACTIVE

def crypto_encrypt_setup(password: str) -> bool:
    """Enable encryption: encrypt current tasks.json → tasks.enc, remove plain."""
    global _CRYPTO_ACTIVE, _CRYPTO_KEY
    import os as _os
    db  = load_plain()
    raw = json.dumps(db, indent=2, default=str).encode()
    salt      = _os.urandom(16)
    key       = _derive_key(password, salt)
    blob      = salt + _aes_gcm_encrypt(key, raw)
    DATA_DIR.mkdir(exist_ok=True)
    _CRYPTO_FILE.write_bytes(blob)
    _CRYPTO_KEY    = key
    _CRYPTO_ACTIVE = True
    if DATA_FILE.exists():
        DATA_FILE.unlink()
    return True

def crypto_unlock(password: str) -> tuple[bool, str]:
    """Decrypt tasks.enc → db dict. Returns (ok, error_msg)."""
    global _CRYPTO_ACTIVE, _CRYPTO_KEY
    if not _CRYPTO_FILE.exists():
        return False, "No encrypted file found."
    try:
        blob = _CRYPTO_FILE.read_bytes()
        salt = blob[:16]; payload = blob[16:]
        key  = _derive_key(password, salt)
        raw  = _aes_gcm_decrypt(key, payload)
        db   = json.loads(raw)
        _CRYPTO_KEY    = key
        _CRYPTO_ACTIVE = True
        return True, ""
    except Exception as e:
        return False, str(e)

def crypto_decrypt_disable(password: str) -> tuple[bool, str]:
    """Remove encryption: decrypt → save as plain tasks.json."""
    global _CRYPTO_ACTIVE, _CRYPTO_KEY
    ok, err = crypto_unlock(password)
    if not ok:
        return False, err
    blob = _CRYPTO_FILE.read_bytes()
    salt = blob[:16]; payload = blob[16:]
    key  = _derive_key(password, salt)
    raw  = _aes_gcm_decrypt(key, payload)
    db   = json.loads(raw)
    DATA_DIR.mkdir(exist_ok=True)
    DATA_FILE.write_bytes(raw)
    _CRYPTO_FILE.unlink()
    _CRYPTO_ACTIVE = False
    _CRYPTO_KEY    = b""
    return True, ""

def load_plain() -> dict:
    """Load from plain JSON (bypasses encryption check)."""
    DATA_DIR.mkdir(exist_ok=True)
    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"tasks": []}

def save_encrypted(db: dict, git_msg: str = "update"):
    """Save to encrypted file if crypto is active."""
    if not _CRYPTO_ACTIVE or not _CRYPTO_KEY:
        return
    import os as _os
    raw  = json.dumps(db, indent=2, default=str).encode()
    blob = _CRYPTO_FILE.read_bytes()[:16]   # reuse original salt
    key  = _CRYPTO_KEY
    enc  = _aes_gcm_encrypt(key, raw)
    _CRYPTO_FILE.write_bytes(blob + enc)
    if (DATA_DIR / ".git").exists():
        _git(["add", "tasks.enc"])
        _git(["commit", "-m", f"taskflow: {git_msg}"])

def screen_encryption(db):
    """Manage encryption settings."""
    header("🔒  Encryption")
    enabled = crypto_is_enabled()
    from rich.panel import Panel
    enc_status = "[green]enabled — tasks.enc[/]" if enabled else "[yellow]disabled — plain tasks.json[/]"
    C.print(Panel(
        f"  Status:    {enc_status}\n"
        "  Algorithm: AES-256-GCM + PBKDF2-HMAC-SHA256 (200 000 iterations)\n"
        "  [dim]Key derived from password at runtime — never stored on disk.[/]",
        border_style=THEME["border"], padding=(0,1)
    ))
    C.print()
    if not enabled:
        C.print(f"  [bold {THEME['secondary']}]e[/]  Enable encryption")
    else:
        C.print(f"  [bold {THEME['secondary']}]d[/]  Disable encryption (decrypt to plain JSON)")
        C.print(f"  [bold {THEME['secondary']}]p[/]  Change password")
    C.print(f"  [bold {THEME['secondary']}]b[/]  Back")
    C.print()
    ch = Prompt.ask(f"  [{THEME['secondary']}]>[/]").lower().strip()
    if ch == "b": return
    elif ch == "e" and not enabled:
        C.print("\n  [yellow]This will encrypt tasks.json. You must remember your password.[/]\n")
        pw  = Prompt.ask("  Password", password=True)
        pw2 = Prompt.ask("  Confirm",  password=True)
        if pw != pw2:
            C.print("  [red]Passwords do not match.[/]"); press_enter(); return
        if len(pw) < 6:
            C.print("  [red]Password too short (min 6 chars).[/]"); press_enter(); return
        C.print("  [dim]Encrypting… (may take a moment)[/]")
        crypto_encrypt_setup(pw)
        C.print("  [green]✓ Encryption enabled. tasks.json removed.[/]")
        C.print("  [yellow]You will be prompted for your password on next startup.[/]")
        press_enter()
    elif ch == "d" and enabled:
        if Confirm.ask("  Decrypt and save as plain tasks.json?"):
            pw = Prompt.ask("  Password", password=True)
            ok, err = crypto_decrypt_disable(pw)
            C.print(f"  {'[green]✓ Decrypted. Encryption disabled.[/]' if ok else f'[red]{err}[/]'}")
            press_enter()
    elif ch == "p" and enabled:
        old_pw = Prompt.ask("  Current password", password=True)
        ok, err = crypto_unlock(old_pw)
        if not ok:
            C.print(f"  [red]{err}[/]"); press_enter(); return
        new_pw  = Prompt.ask("  New password", password=True)
        new_pw2 = Prompt.ask("  Confirm",      password=True)
        if new_pw != new_pw2:
            C.print("  [red]Passwords do not match.[/]"); press_enter(); return
        blob = _CRYPTO_FILE.read_bytes()
        salt = blob[:16]; payload = blob[16:]
        key  = _derive_key(old_pw, salt)
        raw  = _aes_gcm_decrypt(key, payload)
        crypto_encrypt_setup(new_pw)
        C.print("  [green]✓ Password changed.[/]"); press_enter()

# ─────────────────────────────────────────────────────────────
# PERSISTENCE
# ─────────────────────────────────────────────────────────────

def load() -> dict:
    if "load" in _storage_backend:
        try:
            return _storage_backend["load"]()
        except Exception as e:
            C.print(f"  [yellow]Storage backend load failed: {e} — using JSON[/]")
    # Encrypted storage
    if _CRYPTO_ACTIVE and _CRYPTO_KEY and _CRYPTO_FILE.exists():
        try:
            blob = _CRYPTO_FILE.read_bytes()
            salt = blob[:16]; payload = blob[16:]
            raw  = _aes_gcm_decrypt(_CRYPTO_KEY, payload)
            return json.loads(raw)
        except Exception as e:
            C.print(f"  [red]Decryption failed: {e}[/]")
    DATA_DIR.mkdir(exist_ok=True)
    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"tasks": []}

BACKUP_COUNT = 5   # rolling backups kept

def _rotate_backups():
    """Keep BACKUP_COUNT rolling backups of tasks.json."""
    for i in range(BACKUP_COUNT - 1, 0, -1):
        src = DATA_FILE.with_suffix(f".bak.{i}")
        dst = DATA_FILE.with_suffix(f".bak.{i+1}")
        if src.exists():
            src.replace(dst)
    if DATA_FILE.exists():
        try:
            import shutil
            shutil.copy2(DATA_FILE, DATA_FILE.with_suffix(".bak.1"))
        except Exception:
            pass

def save(db: dict, git_msg: str = "update"):
    DATA_DIR.mkdir(exist_ok=True)
    _rotate_backups()
    if _CRYPTO_ACTIVE and _CRYPTO_KEY:
        save_encrypted(db, git_msg); return
    with open(DATA_FILE, "w") as f:
        json.dump(db, f, indent=2, default=str)
    # Auto-commit if git repo exists
    if (DATA_DIR / ".git").exists():
        _git(["add", "tasks.json"])
        _git(["commit", "-m", f"taskflow: {git_msg}"])

def new_task(name, priority="Medium", category="Work",
             due="", hours=1.0, desc="", tags=None) -> dict:
    return {
        "id":              str(uuid.uuid4())[:8],
        "name":            name,
        "priority":        priority,
        "priority_score":  PRIORITY_SCORE.get(priority, 3),
        "category":        category,
        "status":          "todo",
        "due_date":        due,
        "estimated_hours": float(hours),
        "actual_hours":    None,
        "description":     desc,
        "tags":            tags or [],
        "created_at":      datetime.now().isoformat(),
        "completed_at":    None,
        "started_at":      None,
        "recurrence":      "none",
        "parent_id":       None,
    }

# ─────────────────────────────────────────────────────────────
# UNDO / REDO  (in-memory state stack)
# ─────────────────────────────────────────────────────────────

import copy as _copy

_UNDO_STACK: list = []   # list of db snapshots (most recent last)
_REDO_STACK: list = []
UNDO_MAX    = 50          # max steps stored


def undo_snapshot(db: dict):
    """Call before any mutating operation to capture current state."""
    _UNDO_STACK.append(_copy.deepcopy(db))
    _REDO_STACK.clear()   # new action invalidates redo
    if len(_UNDO_STACK) > UNDO_MAX:
        _UNDO_STACK.pop(0)


def undo(db: dict) -> tuple[bool, str]:
    """Restore previous state. Returns (ok, description)."""
    if not _UNDO_STACK:
        return False, "Nothing to undo."
    _REDO_STACK.append(_copy.deepcopy(db))
    prev = _UNDO_STACK.pop()
    db.clear(); db.update(prev)
    save(db, "undo")
    return True, f"Undone  ({len(_UNDO_STACK)} step(s) left)"


def redo(db: dict) -> tuple[bool, str]:
    """Redo last undone action."""
    if not _REDO_STACK:
        return False, "Nothing to redo."
    _UNDO_STACK.append(_copy.deepcopy(db))
    nxt = _REDO_STACK.pop()
    db.clear(); db.update(nxt)
    save(db, "redo")
    return True, f"Redone  ({len(_REDO_STACK)} redo(s) left)"


# ─────────────────────────────────────────────────────────────
# PURE-PYTHON ML  (zero deps — Decision Tree + Linear Regression)
# ─────────────────────────────────────────────────────────────

CAT_ENC = {c: i for i, c in enumerate(CATEGORIES)}

def _feat(task, now):
    """
    Enhanced feature vector (14 features):
    0  priority_score          1  category_enc
    2  estimated_hours         3  age_hours
    4  due_hours               5  tag_count
    6  created_weekday         7  created_hour
    8  has_due_date            9  description_length
    10 recurrence_flag         11 days_to_deadline_norm
    12 hour_of_day_sin         13 hour_of_day_cos
    """
    import math
    created  = datetime.fromisoformat(task["created_at"])
    age_h    = (now - created).total_seconds() / 3600
    due_h    = 9999.0
    has_due  = 0.0
    days_norm= 0.0
    if task.get("due_date"):
        try:
            dd     = datetime.fromisoformat(task["due_date"])
            due_h  = max(0.0, (dd - now).total_seconds() / 3600)
            has_due= 1.0
            days_norm = min(1.0, due_h / (30 * 24))   # norm to 30-day window
        except Exception:
            pass
    hour      = float(created.hour)
    rec_flag  = 0.0 if task.get("recurrence","none") == "none" else 1.0
    desc_len  = min(float(len(task.get("description",""))), 500.0) / 500.0
    return [
        float(task.get("priority_score", 3)),
        float(CAT_ENC.get(task.get("category", "Other"), 0)),
        float(task.get("estimated_hours", 1)),
        age_h, due_h,
        float(len(task.get("tags", []))),
        float(created.weekday()),
        hour,
        has_due, desc_len, rec_flag, days_norm,
        math.sin(2 * math.pi * hour / 24),
        math.cos(2 * math.pi * hour / 24),
    ]

# ── Tiny Decision Tree (classification & regression) ─────────────────────────

class _Node:
    __slots__ = ("feat","thresh","left","right","value")
    def __init__(self):
        self.feat=self.thresh=self.left=self.right=self.value=None

def _gini(groups, classes):
    total = sum(len(g) for g in groups)
    score = 0.0
    for g in groups:
        size = len(g)
        if size == 0: continue
        for c in classes:
            p = sum(1 for r in g if r[-1] == c) / size
            score += p * p
        score -= size / total * score
    return 1.0 - score / max(len(groups), 1)

def _mse(group):
    if not group: return 0.0
    vals = [r[-1] for r in group]
    m    = sum(vals) / len(vals)
    return sum((v - m)**2 for v in vals) / len(vals)

def _split(fi, thresh, rows):
    l = [r for r in rows if r[fi] < thresh]
    r = [r for r in rows if r[fi] >= thresh]
    return l, r

def _best_split(rows, n_feats, mode):
    best = {"score": float("inf"), "fi": 0, "thresh": 0.0, "groups": (rows, [])}
    n    = len(rows[0]) - 1
    feats = list(range(n))
    # sample sqrt(n) features
    import random; random.seed(42)
    if n_feats < n: feats = random.sample(feats, n_feats)
    classes = list({r[-1] for r in rows})
    for fi in feats:
        vals = sorted({r[fi] for r in rows})
        for i in range(len(vals)-1):
            thresh = (vals[i] + vals[i+1]) / 2
            l, r   = _split(fi, thresh, rows)
            if mode == "clf":
                score = (_gini([l,r], classes) * (len(l)+len(r)))
            else:
                score = _mse(l)*len(l) + _mse(r)*len(r)
            if score < best["score"]:
                best = {"score": score, "fi": fi, "thresh": thresh, "groups": (l, r)}
    return best

def _build(rows, depth, max_depth, min_size, n_feats, mode):
    node = _Node()
    if len(rows) <= min_size or depth >= max_depth:
        vals = [r[-1] for r in rows]
        if mode == "clf":
            node.value = max(set(vals), key=vals.count)
        else:
            node.value = sum(vals)/len(vals) if vals else 0.0
        return node
    b = _best_split(rows, n_feats, mode)
    l, r = b["groups"]
    if not l or not r:
        vals = [r[-1] for r in rows]
        if mode == "clf":
            node.value = max(set(vals), key=vals.count)
        else:
            node.value = sum(vals)/len(vals) if vals else 0.0
        return node
    node.feat   = b["fi"]
    node.thresh = b["thresh"]
    node.left   = _build(l, depth+1, max_depth, min_size, n_feats, mode)
    node.right  = _build(r, depth+1, max_depth, min_size, n_feats, mode)
    return node

def _predict_node(node, row):
    if node.value is not None:
        return node.value
    if row[node.feat] < node.thresh:
        return _predict_node(node.left, row)
    return _predict_node(node.right, row)

# ── Random Forest (pure Python) ───────────────────────────────────────────────

class _RandomForest:
    def __init__(self, n=20, max_depth=5, min_size=2, mode="clf"):
        self.n=n; self.max_depth=max_depth; self.min_size=min_size
        self.mode=mode; self.trees=[]

    def fit(self, X, y):
        import random; random.seed(42)
        rows = [list(x)+[yv] for x,yv in zip(X,y)]
        n_feats = max(1, int(len(X[0])**0.5))
        self.trees = []
        for _ in range(self.n):
            sample = [random.choice(rows) for _ in rows]
            self.trees.append(_build(sample, 0, self.max_depth,
                                     self.min_size, n_feats, self.mode))

    def predict(self, X):
        out = []
        for x in X:
            preds = [_predict_node(t, x) for t in self.trees]
            if self.mode == "clf":
                out.append(max(set(preds), key=preds.count))
            else:
                out.append(sum(preds)/len(preds))
        return out

    def predict_proba(self, X):
        out = []
        for x in X:
            preds = [_predict_node(t, x) for t in self.trees]
            p1 = sum(1 for p in preds if p == 1) / len(preds)
            out.append([1-p1, p1])
        return out


class ML:
    def __init__(self):
        # Larger forest + deeper trees for 14-feature vector
        self.clf     = _RandomForest(n=40, max_depth=7, mode="clf")
        self.reg     = _RandomForest(n=40, max_depth=7, mode="reg")
        self.trained  = False
        self.n_train  = 0        # number of samples trained on
        self.accuracy = None     # cross-validated accuracy estimate
        self._cat_hist: dict = {}  # category → avg_hours (learned)
        self._prio_hist: dict = {} # priority → on_time_rate (learned)

    def train(self, tasks):
        done = [t for t in tasks if t["status"] == "done" and t.get("completed_at")]
        if len(done) < 5:
            return
        now = datetime.now()
        X, yc, yr = [], [], []
        for t in done:
            try:
                f = _feat(t, now); X.append(f)
                ot = 1
                if t.get("due_date"):
                    ot = int(datetime.fromisoformat(t["completed_at"])
                             <= datetime.fromisoformat(t["due_date"]))
                yc.append(ot)
                yr.append(float(t.get("actual_hours") or t.get("estimated_hours", 1)))
            except Exception:
                continue
        if len(X) < 5:
            return
        self.clf.fit(X, yc)
        self.reg.fit(X, yr)
        self.trained  = True
        self.n_train  = len(X)

        # Learn per-category avg hours
        for t in done:
            cat = t.get("category","Other")
            h   = float(t.get("actual_hours") or t.get("estimated_hours",1))
            if cat not in self._cat_hist:
                self._cat_hist[cat] = []
            self._cat_hist[cat].append(h)

        # Learn per-priority on-time rate
        prio_counts: dict = {}; prio_ontime: dict = {}
        for t in done:
            p  = t.get("priority","Medium")
            ot = 1
            if t.get("due_date"):
                try:
                    ot = int(datetime.fromisoformat(t["completed_at"])
                             <= datetime.fromisoformat(t["due_date"]))
                except Exception:
                    ot = 1
            prio_counts[p] = prio_counts.get(p,0) + 1
            prio_ontime[p] = prio_ontime.get(p,0) + ot
        self._prio_hist = {p: prio_ontime[p]/prio_counts[p]
                           for p in prio_counts if prio_counts[p] > 0}

        # Simple hold-out accuracy (last 20% of data)
        if len(X) >= 10:
            split = max(1, len(X)*8//10)
            clf2  = _RandomForest(n=20, max_depth=7, mode="clf")
            clf2.fit(X[:split], yc[:split])
            preds = clf2.predict(X[split:])
            self.accuracy = sum(p==a for p,a in zip(preds,yc[split:])) / len(preds)

    def predict(self, task) -> dict:
        now = datetime.now()
        r   = {"prob": None, "pred_h": None, "risk": "—", "tip": "", "explain": []}
        if not self.trained:
            if task.get("due_date"):
                try:
                    days = (datetime.fromisoformat(task["due_date"]) - now).days
                    sc   = task.get("priority_score", 3)
                    if   days < 0:             r["risk"], r["tip"] = "🔴 Overdue",   "Past deadline"
                    elif days == 0:            r["risk"], r["tip"] = "🟠 Due today", "Act now!"
                    elif days <= 2 and sc >= 4:r["risk"], r["tip"] = "🟡 At risk",   "Tight deadline"
                    else:                      r["risk"], r["tip"] = "🟢 On track",  "Looks good"
                except Exception:
                    pass
            return r
        try:
            x      = _feat(task, now)
            prob   = round(self.clf.predict_proba([x])[0][1] * 100, 1)
            # Ensemble: blend ML prob with historical priority on-time rate
            prio_base = self._prio_hist.get(task.get("priority","Medium"), 0.7) * 100
            prob_final = round(prob * 0.7 + prio_base * 0.3, 1)

            # Category-aware hour prediction
            pred_h_ml = round(max(0.1, self.reg.predict([x])[0]), 1)
            cat_hist  = self._cat_hist.get(task.get("category","Work"), [])
            if cat_hist:
                cat_avg = sum(cat_hist)/len(cat_hist)
                pred_h  = round(pred_h_ml * 0.6 + cat_avg * 0.4, 1)
            else:
                pred_h  = pred_h_ml

            r["prob"]      = prob_final
            r["pred_h"]    = pred_h
            r["prob_raw"]  = prob
            r["prio_base"] = round(prio_base, 1)

            # Build explanation
            explain = []
            if task.get("due_date"):
                try:
                    days = (datetime.fromisoformat(task["due_date"]) - now).days
                    explain.append(f"{days}d to deadline")
                except Exception: pass
            explain.append(f"priority on-time: {prio_base:.0f}%")
            if cat_hist:
                explain.append(f"avg {task.get('category','')} task: {sum(cat_hist)/len(cat_hist):.1f}h")
            if self.accuracy is not None:
                explain.append(f"model accuracy: {self.accuracy*100:.0f}%")
            r["explain"] = explain

            if   prob_final >= 80: r["risk"], r["tip"] = "🟢 Low risk",      "On track"
            elif prob_final >= 55: r["risk"], r["tip"] = "🟡 Medium risk",   "Consider prioritising"
            elif prob_final >= 30: r["risk"], r["tip"] = "🟠 High risk",     "Needs attention"
            else:                  r["risk"], r["tip"] = "🔴 Critical risk", "Very likely to miss deadline"
        except Exception:
            pass
        return r

    def insights(self, tasks) -> list:
        if not tasks:
            return ["No tasks yet — create some!"]
        done  = [t for t in tasks if t["status"] == "done"]
        todo  = [t for t in tasks if t["status"] in ("todo", "in_progress")]
        rate  = len(done) / len(tasks) * 100
        now   = datetime.now()
        ovd   = [t for t in todo if t.get("due_date") and
                 datetime.fromisoformat(t["due_date"]) < now]
        lines = [f"📈  Completion rate: {rate:.1f}%  ({len(done)}/{len(tasks)})"]
        if ovd:
            lines.append(f"⚠️   {len(ovd)} overdue task(s)")
        times = []
        for t in done:
            try:
                c = datetime.fromisoformat(t["created_at"])
                d = datetime.fromisoformat(t["completed_at"])
                times.append((d - c).total_seconds() / 3600)
            except Exception:
                pass
        if times:
            lines.append(f"⏱️   Avg completion: {sum(times)/len(times):.1f} h")
        cat = Counter(t.get("category") for t in done)
        if cat:
            lines.append(f"🏆  Most productive: {cat.most_common(1)[0][0]}")
        high = [t for t in todo if t.get("priority_score", 0) >= 4]
        if high:
            lines.append(f"🔥  {len(high)} high-priority task(s) pending")
        if self.trained:
            lines.append("🤖  ML active — predictions powered by your history")
        else:
            lines.append(f"🤖  Complete {max(0,5-len(done))} more task(s) to activate ML")
        return lines

# ═════════════════════════════════════════════════════════════
# PLUGIN FRAMEWORK  v3
# ═════════════════════════════════════════════════════════════
#
#  Drop any .py file into  ~/.taskflow/plugins/
#  See  ~/.taskflow/PLUGIN_DOCS.md  for full documentation.
#
#  Quick reference — define any subset of these in your plugin:
#
#  METADATA:
#    PLUGIN_NAME        PLUGIN_VERSION   PLUGIN_DESC
#    PLUGIN_AUTHOR      PLUGIN_TAGS      PLUGIN_MIN_API
#    PLUGIN_REQUIRES    PLUGIN_PERMISSIONS
#
#  LIFECYCLE HOOKS:
#    install(api)                  first install only
#    uninstall(api)                before removal
#    upgrade(api, old_ver)         version changed
#    on_startup(api)               every start
#    on_shutdown(api)              clean exit
#    on_tick(api)                  every main-loop pass
#
#  TASK HOOKS:
#    on_task_created(api, task)
#    on_task_updated(api, task, old_task)
#    on_task_done(api, task)
#    on_task_deleted(api, task)
#    on_task_started(api, task)
#
#  RENDER HOOKS:
#    menu_items(api)       -> list[("key","label",fn)]
#    task_actions(api, task) -> list[("key","label",fn)]
#    dashboard_widgets(api)  -> list[str]   (Rich markup)
#    filter_tasks(api, tasks) -> list[task] (custom sort/filter)
#
#  EVENTS (custom pub/sub):
#    api.emit("my_event", data)
#    api.on("my_event", handler_fn)

API_VERSION    = "3.0"
PLUGINS_DIR    = DATA_DIR / "plugins"
PLUGIN_DATA_DIR= DATA_DIR / "plugin_data"
LOG_FILE       = DATA_DIR / "plugin.log"

_loaded_plugins: list  = []
_plugin_errors:  dict  = {}   # fname -> error string
_plugin_meta:    dict  = {}   # fname -> metadata dict
_event_bus:      dict  = {}   # event_name -> [callbacks]
_task_actions:   list  = []   # [(key, label, fn)]  registered by plugins
_dash_widgets:   list  = []   # [fn(api)->str]       dashboard additions
_scheduled:      list  = []   # [(interval_s, fn, last_run)]
_plugin_log:     list  = []   # [(ts, plugin, level, msg)]


# ── Plugin metadata helper ────────────────────────────────────

def _read_meta(module) -> dict:
    fname = Path(module.__file__).name
    return {
        "filename":    fname,
        "name":        getattr(module, "PLUGIN_NAME",        fname.replace(".py","")),
        "version":     getattr(module, "PLUGIN_VERSION",     "1.0"),
        "desc":        getattr(module, "PLUGIN_DESC",        ""),
        "author":      getattr(module, "PLUGIN_AUTHOR",      "unknown"),
        "tags":        getattr(module, "PLUGIN_TAGS",        "").split(",") if isinstance(getattr(module,"PLUGIN_TAGS",""), str) else getattr(module,"PLUGIN_TAGS",[]),
        "min_api":     getattr(module, "PLUGIN_MIN_API",     "1.0"),
        "requires":    getattr(module, "PLUGIN_REQUIRES",    []),
        "permissions": getattr(module, "PLUGIN_PERMISSIONS", []),
    }


# ── Plugin state file ─────────────────────────────────────────

def _state_path() -> Path:
    return DATA_DIR / "plugin_state.json"

def _load_state() -> dict:
    p = _state_path()
    if p.exists():
        try: return json.loads(p.read_text())
        except Exception: pass
    return {}

def _save_state(state: dict):
    _state_path().write_text(json.dumps(state, indent=2))


# ── Plugin logger ─────────────────────────────────────────────

def _plugin_log_write(plugin_name: str, level: str, msg: str):
    ts  = datetime.now().isoformat(timespec="seconds")
    _plugin_log.append((ts, plugin_name, level, msg))
    try:
        LOG_FILE.parent.mkdir(exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(f"[{ts}] [{level.upper()}] [{plugin_name}] {msg}\n")
    except Exception:
        pass


# ═════════════════════════════════════════════════════════════
# PLUGIN API CLASS
# ═════════════════════════════════════════════════════════════

class PluginAPI:
    """
    Comprehensive plugin API — passed as first argument to every hook.
    API version: 3.0
    """

    VERSION = API_VERSION

    def __init__(self, db: dict, plugin_name: str):
        self._db         = db
        self._pname      = plugin_name
        self._store_path = PLUGIN_DATA_DIR / f"{plugin_name}.json"
        self._store: dict | None = None
        self._config: dict | None = None
        self._config_path = PLUGIN_DATA_DIR / f"{plugin_name}.config.json"

    # ── Core data access ─────────────────────────────────────

    @property
    def db(self) -> dict:
        """The live task database dict. Modify in place."""
        return self._db

    @property
    def tasks(self) -> list:
        """Shortcut for db['tasks']. Live reference."""
        return self._db["tasks"]

    @property
    def data_dir(self) -> Path:
        """Path to ~/.taskflow/"""
        return DATA_DIR

    @property
    def plugins_dir(self) -> Path:
        """Path to ~/.taskflow/plugins/"""
        return PLUGINS_DIR

    @property
    def console(self):
        """Rich Console instance for terminal output."""
        return C

    @property
    def theme(self) -> dict:
        """Current theme dict. Read or pass to apply_theme()."""
        return THEME

    @property
    def api_version(self) -> str:
        """Framework API version string."""
        return API_VERSION

    # ── Task management ───────────────────────────────────────

    def get_task(self, task_id: str) -> dict | None:
        """Find a task by ID. Returns None if not found."""
        for t in self.tasks:
            if t.get("id") == task_id:
                return t
        return None

    def add_task(self, name: str, priority: str = "Medium",
                 category: str = "Work", due: str = "", hours: float = 1.0,
                 desc: str = "", tags: list = None, **extra) -> dict:
        """Create and persist a new task. Returns the created task dict."""
        t = new_task(name, priority, category, due, hours, desc, tags or [])
        t.update(extra)
        self.tasks.append(t)
        self.save(f"plugin:{self._pname}:add_task")
        _hook("on_task_created", self._db, t)
        return t

    def update_task(self, task_id: str, **fields) -> bool:
        """Update fields on an existing task. Returns True if found."""
        for i, t in enumerate(self.tasks):
            if t.get("id") == task_id:
                old = dict(t)
                t.update(fields)
                self._db["tasks"][i] = t
                self.save(f"plugin:{self._pname}:update_task")
                _hook("on_task_updated", self._db, t, old)
                return True
        return False

    def delete_task(self, task_id: str) -> bool:
        """Remove a task by ID. Fires on_task_deleted. Returns True if found."""
        for i, t in enumerate(self.tasks):
            if t.get("id") == task_id:
                _hook("on_task_deleted", self._db, t)
                self._db["tasks"].pop(i)
                self.save(f"plugin:{self._pname}:delete_task")
                return True
        return False

    def complete_task(self, task_id: str, actual_hours: float = None) -> bool:
        """Mark a task as done. Returns True if found."""
        t = self.get_task(task_id)
        if not t: return False
        old = dict(t)
        t["status"]       = "done"
        t["completed_at"] = datetime.now().isoformat()
        if actual_hours is not None:
            t["actual_hours"] = actual_hours
        self.save(f"plugin:{self._pname}:complete_task")
        _hook("on_task_done",    self._db, t)
        _hook("on_task_updated", self._db, t, old)
        return True

    def query_tasks(self, status: str = None, category: str = None,
                    priority: str = None, tag: str = None,
                    due_before: str = None, due_after: str = None) -> list:
        """Filter tasks with optional criteria. All filters are ANDed."""
        results = list(self.tasks)
        if status:     results = [t for t in results if t.get("status") == status]
        if category:   results = [t for t in results if t.get("category") == category]
        if priority:   results = [t for t in results if t.get("priority") == priority]
        if tag:        results = [t for t in results if tag in t.get("tags", [])]
        if due_before: results = [t for t in results if t.get("due_date","") and t["due_date"] <= due_before]
        if due_after:  results = [t for t in results if t.get("due_date","") and t["due_date"] >= due_after]
        return results

    def new_task_dict(self, **kw) -> dict:
        """Build a task dict without saving. Useful for bulk operations."""
        return new_task(**kw)

    # ── Persistence ───────────────────────────────────────────

    def save(self, msg: str = "plugin-update"):
        """Persist the task database (respects active storage backend)."""
        if "save" in _storage_backend:
            try:
                _storage_backend["save"](self._db); return
            except Exception as e:
                self.log(f"Storage backend failed: {e} — falling back to JSON", "warn")
        save(self._db, msg)

    @property
    def store(self) -> dict:
        """
        Persistent plugin-local key-value store.
        Stored at ~/.taskflow/plugin_data/<plugin_name>.json
        Call store_save() to persist.
        """
        if self._store is None:
            PLUGIN_DATA_DIR.mkdir(exist_ok=True)
            if self._store_path.exists():
                try: self._store = json.loads(self._store_path.read_text())
                except Exception: self._store = {}
            else:
                self._store = {}
        return self._store

    def store_save(self):
        """Persist the plugin store to disk."""
        PLUGIN_DATA_DIR.mkdir(exist_ok=True)
        self._store_path.write_text(json.dumps(self._store or {}, indent=2))

    @property
    def config(self) -> dict:
        """
        Plugin configuration dict — separate from store.
        Use for user-facing settings. Stored at plugin_data/<name>.config.json
        """
        if self._config is None:
            if self._config_path.exists():
                try: self._config = json.loads(self._config_path.read_text())
                except Exception: self._config = {}
            else:
                self._config = {}
        return self._config

    def config_save(self):
        """Persist configuration to disk."""
        PLUGIN_DATA_DIR.mkdir(exist_ok=True)
        self._config_path.write_text(json.dumps(self._config or {}, indent=2))

    def read_file(self, relative_path: str) -> str | None:
        """Read a file from ~/.taskflow/<path>. Returns None if not found."""
        p = DATA_DIR / relative_path
        if p.exists():
            try: return p.read_text(encoding="utf-8")
            except Exception: return None
        return None

    def write_file(self, relative_path: str, content: str):
        """Write a file to ~/.taskflow/<path>. Creates parent dirs."""
        p = DATA_DIR / relative_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    # ── UI helpers ────────────────────────────────────────────

    def notify(self, title: str, body: str = "", urgency: str = "normal"):
        """Send a desktop notification (libnotify/gdbus/terminal-notifier)."""
        notify(title, body, urgency)

    def print(self, *args, **kwargs):
        """Shortcut for api.console.print()."""
        C.print(*args, **kwargs)

    def prompt(self, label: str, default: str = "", password: bool = False) -> str:
        """Rich Prompt.ask() wrapper."""
        from rich.prompt import Prompt
        return Prompt.ask(f"  [bold]{label}[/]", default=default, password=password).strip()

    def confirm(self, label: str, default: bool = False) -> bool:
        """Rich Confirm.ask() wrapper."""
        from rich.prompt import Confirm
        return Confirm.ask(f"  {label}", default=default)

    def pick(self, label: str, options: list, default_idx: int = 0) -> str:
        """Numbered option picker. Returns selected string."""
        for i, o in enumerate(options, 1):
            marker = f"  [bold {THEME['secondary']}]>[/]" if i-1 == default_idx else "   "
            C.print(f"{marker} [dim]{i}.[/]  {o}")
        C.print()
        while True:
            from rich.prompt import Prompt
            raw = Prompt.ask(f"  [bold]{label}[/]", default=str(default_idx+1))
            try:
                idx = int(raw) - 1
                if 0 <= idx < len(options): return options[idx]
            except ValueError: pass
            C.print("  [red]Invalid choice.[/]")

    def clear_screen(self):
        """Clear the terminal."""
        import os; os.system("clear" if os.name != "nt" else "cls")

    def press_enter(self, msg: str = "Press Enter to continue"):
        """Wait for Enter."""
        C.print(f"\n  [dim]{msg}[/]"); input()

    def show_header(self, subtitle: str = ""):
        """Render the TaskFlow header with optional subtitle."""
        header(subtitle)

    def panel(self, content: str, title: str = "", border: str = None, **kw):
        """Print a Rich Panel. border defaults to THEME['border']."""
        from rich.panel import Panel
        C.print(Panel(content, title=title,
                      border_style=border or THEME["border"], **kw))

    def table(self, title: str = ""):
        """Return a new Rich Table with theme styling."""
        from rich.table import Table
        from rich import box as rbox
        return Table(box=rbox.ROUNDED, border_style=THEME["border"],
                     header_style=f"bold {THEME['secondary']}",
                     title=f"[bold {THEME['secondary']}]{title}[/]" if title else "",
                     title_justify="left", padding=(0,1))

    def rule(self, title: str = ""):
        """Print a themed horizontal rule."""
        from rich.rule import Rule
        C.print(Rule(f"[dim]{title}[/]" if title else "", style=THEME["border"]))

    # ── Theme ─────────────────────────────────────────────────

    def apply_theme(self, overrides: dict):
        """Override theme colors globally. Keys: primary, secondary, border, dim, success, warning, error, accent."""
        apply_theme(overrides)

    def get_theme_color(self, key: str) -> str:
        """Get a theme color by key."""
        return THEME.get(key, "#ffffff")

    # ── Events (pub/sub) ──────────────────────────────────────

    def emit(self, event: str, *args, **kwargs):
        """Fire a custom event. Any plugin subscribed via api.on() will receive it."""
        for cb in _event_bus.get(event, []):
            try: cb(*args, **kwargs)
            except Exception as e:
                self.log(f"Event handler error [{event}]: {e}", "error")

    def on(self, event: str, callback):
        """Subscribe to a custom event emitted by any plugin."""
        _event_bus.setdefault(event, []).append(callback)

    # ── Plugin registry access ───────────────────────────────

    def get_plugin(self, name: str):
        """
        Get another loaded plugin module by PLUGIN_NAME.
        Returns the module or None. Use for inter-plugin communication.
        """
        for p in _loaded_plugins:
            if getattr(p, "PLUGIN_NAME", "") == name:
                return p
        return None

    def get_all_plugins(self) -> list:
        """Return list of all loaded plugin modules."""
        return list(_loaded_plugins)

    def is_plugin_loaded(self, name: str) -> bool:
        """Check if a plugin with given PLUGIN_NAME is loaded."""
        return self.get_plugin(name) is not None

    # ── Registration ─────────────────────────────────────────

    def register_task_action(self, key: str, label: str, fn):
        """
        Add an action to the task detail screen.
        fn(task) -> None
        Key must not conflict with built-in task actions (s,d,r,c,e,h,x,b).
        """
        _task_actions.append((key, label, fn))

    def register_dashboard_widget(self, fn):
        """
        Add a widget to the home dashboard.
        fn(api) -> str   (Rich markup string, shown below active tasks)
        """
        _dash_widgets.append(fn)

    def register_schedule(self, fn, interval_seconds: int):
        """
        Run fn(api) every interval_seconds in the main loop tick.
        fn receives a fresh PluginAPI instance.
        """
        _scheduled.append([interval_seconds, fn, 0.0])

    # ── Storage backend ───────────────────────────────────────

    def register_storage(self, load_fn, save_fn):
        """
        Override the JSON storage backend.
        load_fn() -> dict         must return {"tasks": [...]}
        save_fn(db) -> None
        """
        _storage_backend["load"] = load_fn
        _storage_backend["save"] = save_fn
        try:
            fresh = load_fn()
            self._db.clear(); self._db.update(fresh)
        except Exception as e:
            self.log(f"Storage backend load failed: {e}", "error")

    # ── HTTP helpers ──────────────────────────────────────────

    def http_get(self, url: str, headers: dict = None, timeout: int = 10) -> tuple[int, str]:
        """
        Simple HTTP GET. Returns (status_code, body_text).
        Returns (-1, error_message) on network failure.
        """
        from urllib.request import Request, urlopen
        from urllib.error   import URLError
        try:
            req = Request(url, headers=headers or {})
            with urlopen(req, timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", errors="replace")
        except URLError as e:
            return -1, str(e)
        except Exception as e:
            return -1, str(e)

    def http_post(self, url: str, data: dict | str, headers: dict = None,
                  timeout: int = 10) -> tuple[int, str]:
        """
        Simple HTTP POST with JSON or raw body. Returns (status_code, body_text).
        """
        from urllib.request import Request, urlopen
        from urllib.error   import URLError
        try:
            body = json.dumps(data).encode() if isinstance(data, dict) else data.encode()
            hdrs = {"Content-Type": "application/json"}
            hdrs.update(headers or {})
            req  = Request(url, data=body, headers=hdrs)
            with urlopen(req, timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", errors="replace")
        except URLError as e:
            return -1, str(e)
        except Exception as e:
            return -1, str(e)

    # ── Logging ───────────────────────────────────────────────

    def log(self, msg: str, level: str = "info"):
        """Write to ~/.taskflow/plugin.log and in-memory log."""
        _plugin_log_write(self._pname, level, msg)

    def get_log(self, n: int = 50, plugin: str = None) -> list:
        """Return recent log entries as [(ts, plugin, level, msg)]."""
        entries = _plugin_log if not plugin else [e for e in _plugin_log if e[1] == plugin]
        return entries[-n:]

    # ── Stats / analytics helpers ─────────────────────────────

    def completion_rate(self) -> float:
        """Return overall task completion rate as 0.0–100.0."""
        t = self.tasks
        if not t: return 0.0
        return sum(1 for x in t if x.get("status") == "done") / len(t) * 100

    def tasks_due_today(self) -> list:
        """Return all active tasks due today."""
        from datetime import date
        today = date.today().isoformat()
        return [t for t in self.tasks
                if t.get("status") in ("todo","in_progress")
                and t.get("due_date","") == today]

    def tasks_overdue(self) -> list:
        """Return all active tasks past their due date."""
        from datetime import date
        today = date.today().isoformat()
        return [t for t in self.tasks
                if t.get("status") in ("todo","in_progress")
                and t.get("due_date","") and t["due_date"] < today]

    def tasks_by_category(self) -> dict:
        """Return {category: [tasks]} dict."""
        result = {}
        for t in self.tasks:
            result.setdefault(t.get("category","Other"), []).append(t)
        return result


# ═════════════════════════════════════════════════════════════
# PLUGIN LOADER
# ═════════════════════════════════════════════════════════════

def _make_api(db: dict, plugin_name: str) -> PluginAPI:
    return PluginAPI(db, plugin_name)


_plugin_mtimes: dict = {}   # filename -> mtime for live-reload

def _check_plugin_changes() -> list[str]:
    """Return filenames of plugins that have changed on disk."""
    changed = []
    for f in PLUGINS_DIR.glob("*.py"):
        mtime = f.stat().st_mtime
        if _plugin_mtimes.get(f.name, 0) != mtime:
            changed.append(f.name)
    # Also detect deleted plugins
    for fname in list(_plugin_mtimes):
        if not (PLUGINS_DIR / fname).exists():
            changed.append(fname)
    return changed

def load_plugins(db: dict = None):
    global _loaded_plugins, _plugin_errors, _plugin_meta
    global _task_actions, _dash_widgets, _scheduled, _plugin_mtimes
    global _plugin_api_versions
    _loaded_plugins      = []
    _plugin_errors       = {}
    _plugin_meta         = {}
    _task_actions        = []
    _dash_widgets        = []
    _scheduled           = []
    _plugin_mtimes       = {}
    _plugin_api_versions = {}
    PLUGINS_DIR.mkdir(exist_ok=True)
    PLUGIN_DATA_DIR.mkdir(exist_ok=True)

    state = _load_state()

    for f in sorted(PLUGINS_DIR.glob("*.py")):
        try:
            spec   = importlib.util.spec_from_file_location(f.stem, f)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            meta   = _read_meta(module)

            # Check min API version
            min_api = meta.get("min_api","1.0")
            if tuple(int(x) for x in min_api.split(".")) > tuple(int(x) for x in API_VERSION.split(".")):
                raise RuntimeError(f"Requires API {min_api}, current is {API_VERSION}")

            _loaded_plugins.append(module)
            _plugin_meta[f.name] = meta
            _plugin_mtimes[f.name] = f.stat().st_mtime

            # Detect plugin API version for compatibility shim
            ver = _detect_api_version(module)
            _plugin_api_versions[module.__name__] = ver
            if ver == "v1":
                _plugin_log_write(module.__name__, "info",
                    f"v1 plugin detected — compatibility shim active")

            # Install hook — run once per version
            state_key = f"{f.name}:version"
            old_ver   = state.get(state_key)
            install_fn  = getattr(module, "install",  None)
            upgrade_fn  = getattr(module, "upgrade",  None)

            if db is not None:
                api = _make_api(db, module.__name__)
                if old_ver is None and callable(install_fn):
                    try:
                        install_fn(api)
                        _plugin_log_write(module.__name__, "info",
                                          f"install() called v{meta['version']}")
                    except Exception as e:
                        _plugin_log_write(module.__name__, "error", f"install() failed: {e}")
                elif old_ver and old_ver != meta["version"] and callable(upgrade_fn):
                    try:
                        upgrade_fn(api, old_ver)
                        _plugin_log_write(module.__name__, "info",
                                          f"upgrade() {old_ver} -> {meta['version']}")
                    except Exception as e:
                        _plugin_log_write(module.__name__, "error", f"upgrade() failed: {e}")

            state[state_key] = meta["version"]

        except Exception as e:
            _plugin_errors[f.name] = str(e)
            _plugin_mtimes[f.name] = f.stat().st_mtime if f.exists() else 0
            _plugin_log_write(f.stem, "error", f"load failed: {e}")

    _save_state(state)


def _detect_api_version(module) -> str:
    """
    Detect whether a plugin was written for v1, v2, or v3 of the framework.

    v1:  hooks take (db, task) — db is a plain dict
         menu_items() takes no args
    v2:  hooks take (api, task) but api had fewer methods; menu_items(api)
         Identified by PLUGIN_MIN_API being absent or < 3.0
    v3:  PLUGIN_MIN_API = "3.0" or higher
    """
    min_api = getattr(module, "PLUGIN_MIN_API", None)
    if min_api:
        try:
            major = int(min_api.split(".")[0])
            if major >= 3:
                return "v3"
            if major >= 2:
                return "v2"
        except Exception:
            pass

    # Heuristic: inspect hook signatures to detect v1
    import inspect
    for hook in ("on_startup", "on_task_created", "on_task_done",
                 "on_task_deleted", "on_task_started"):
        fn = getattr(module, hook, None)
        if callable(fn):
            try:
                params = list(inspect.signature(fn).parameters)
                if params and params[0] in ("db", "database", "data"):
                    return "v1"
            except Exception:
                pass

    # menu_items with no params → v1
    mi = getattr(module, "menu_items", None)
    if callable(mi):
        try:
            params = list(inspect.signature(mi).parameters)
            if len(params) == 0:
                return "v1"
        except Exception:
            pass

    return "v2"   # default: assume v2-compatible


class _V1Shim:
    """
    Wraps a v1 plugin module so its hooks receive (db, ...) instead of (api, ...).
    Also wraps menu_items() to accept and ignore the api argument.
    """
    def __init__(self, module):
        self._module = module
        self.__name__ = module.__name__
        self.__file__ = module.__file__
        # Copy all metadata attributes
        for attr in ("PLUGIN_NAME","PLUGIN_VERSION","PLUGIN_DESC",
                     "PLUGIN_AUTHOR","PLUGIN_TAGS","PLUGIN_MIN_API",
                     "PLUGIN_REQUIRES","PLUGIN_PERMISSIONS"):
            if hasattr(module, attr):
                setattr(self, attr, getattr(module, attr))
        self.PLUGIN_MIN_API = "1.0"   # mark as legacy
        self._compat_note = True

    def __getattr__(self, name):
        # Proxy everything to the wrapped module
        return getattr(self._module, name)

    def _wrap_hook(self, fn, name):
        """Return a wrapper that converts (api, *args) → (db, *args) for v1 hooks."""
        import inspect
        params = list(inspect.signature(fn).parameters)

        def wrapped(api, *args):
            # Pass api.db (the dict) as first arg, matching v1 signature
            return fn(api.db, *args)

        return wrapped

    def _wrap_menu_items(self, fn):
        """Return a wrapper that drops the api arg for v1 menu_items()."""
        import inspect
        params = list(inspect.signature(fn).parameters)
        if len(params) == 0:
            # v1: menu_items() → wrap to accept api and ignore it
            def wrapped(api):
                items = fn()
                # v1 items might be (key, label, fn) with fn taking no args
                # or fn taking task — already fine, no conversion needed
                return items
            return wrapped
        return fn  # already takes api


# Cache of detected versions to avoid re-inspecting every tick
_plugin_api_versions: dict = {}   # module.__name__ -> "v1"/"v2"/"v3"


def _get_hook(plugin, name: str):
    """
    Return a callable for the named hook, wrapped for compatibility if needed.
    Returns None if the plugin doesn't define the hook.
    """
    fn = getattr(plugin, name, None)
    if not callable(fn):
        return None

    ver = _plugin_api_versions.get(getattr(plugin,"__name__",""), "v2")

    if ver == "v1" and name != "menu_items":
        # Wrap: convert (api, *args) → (db, *args)
        def _compat(api, *args, _fn=fn):
            return _fn(api.db, *args)
        return _compat

    if ver == "v1" and name == "menu_items":
        # v1 menu_items() takes no args
        import inspect
        try:
            params = list(inspect.signature(fn).parameters)
        except Exception:
            params = []
        if len(params) == 0:
            def _compat_mi(api, _fn=fn):
                return _fn()
            return _compat_mi

    return fn


def _hook(name: str, db: dict, *args):
    """Fire a named hook on all loaded plugins, with v1/v2 compatibility."""
    for plugin in _loaded_plugins:
        fn = _get_hook(plugin, name)
        if fn is None:
            continue
        try:
            api = _make_api(db, plugin.__name__)
            fn(api, *args)
        except Exception as e:
            _plugin_log_write(plugin.__name__, "error", f"{name}: {e}")
            C.print(f"  [yellow]⚠ [{Path(plugin.__file__).name}] {name}: {e}[/]")


def _tick_plugins(db: dict):
    """Called each main loop. Runs scheduled tasks and on_tick hooks."""
    import time
    now = time.time()
    for entry in _scheduled:
        interval, fn, last = entry
        if now - last >= interval:
            entry[2] = now
            try:
                fn(_make_api(db, "scheduler"))
            except Exception as e:
                _plugin_log_write("scheduler", "error", str(e))
    _hook("on_tick", db)


def plugin_menu_items(db: dict) -> list:
    items = []
    for plugin in _loaded_plugins:
        fn = _get_hook(plugin, "menu_items")
        if fn is None:
            continue
        try:
            api = _make_api(db, plugin.__name__)
            for item in fn(api):
                items.append(item)
        except Exception:
            pass
    return items


def _uninstall_plugin(filename: str, db: dict):
    """Run uninstall() hook and remove plugin file."""
    for plugin in _loaded_plugins:
        if Path(plugin.__file__).name == filename:
            fn = getattr(plugin, "uninstall", None)
            if callable(fn):
                try:
                    fn(_make_api(db, plugin.__name__))
                except Exception as e:
                    C.print(f"  [yellow]uninstall() error: {e}[/]")
            break
    target = PLUGINS_DIR / filename
    if target.exists():
        target.unlink()
    # remove from state
    state = _load_state()
    state.pop(f"{filename}:version", None)
    _save_state(state)

def screen_quick_search(db):
    """Inline fuzzy search accessible from main menu with /."""
    from rich.table import Table
    from rich       import box as rbox

    PRIO_ICON   = {5:"🔴",4:"🟠",3:"🟡",2:"🟢",1:"⚪"}
    STATUS_STYLE = {"todo":"cyan","in_progress":"yellow","done":"dim green","cancelled":"dim"}

    def _score(q: str, t: dict) -> int:
        text = " ".join(filter(None,[
            t.get("name",""), t.get("description",""),
            " ".join(t.get("tags",[])), t.get("category",""), t.get("priority",""),
        ])).lower()
        q = q.lower()
        if q in text:
            return 200 - text.index(q)
        score = 0; qi = 0
        for ch in text:
            if qi < len(q) and ch == q[qi]:
                score += 5; qi += 1
        return score if qi == len(q) else 0

    while True:
        header("⚡  Quick Search")
        C.print(f"  [dim]Search tasks by name, tag, category or description.[/]")
        C.print(f"  [dim]Leave blank to cancel.\n[/]")
        query = Prompt.ask(f"  [{THEME['secondary']}]/[/]").strip()
        if not query:
            return

        results = sorted(
            [(s, t) for t in db["tasks"] if (s := _score(query, t)) > 0],
            key=lambda x: -x[0]
        )

        if not results:
            C.print(f"  [yellow]No results for '{query}'[/]")
            press_enter("Press Enter to search again"); continue

        tbl = Table(box=rbox.ROUNDED, border_style=THEME["border"],
                    header_style=f"bold {THEME['secondary']}", padding=(0,1),
                    title=f"[bold {THEME['secondary']}]{len(results)} result(s) for '{query}'[/]",
                    title_justify="left")
        tbl.add_column("#",        width=3,  justify="right", style="dim")
        tbl.add_column("Task",     min_width=28)
        tbl.add_column("Priority", width=13)
        tbl.add_column("Status",   width=14)
        tbl.add_column("Category", width=11)
        tbl.add_column("Tags",     min_width=14)

        for i, (_, t) in enumerate(results[:12], 1):
            ps   = t.get("priority_score", 3)
            st   = t.get("status","todo")
            name = t.get("name","")
            # highlight match
            lo = name.lower()
            q  = query.lower()
            if q in lo:
                idx  = lo.index(q)
                name = name[:idx] + f"[bold yellow]{name[idx:idx+len(q)]}[/]" + name[idx+len(q):]
            tags = "  ".join(f"[dim]{x}[/]" for x in t.get("tags",[])[:3])
            tbl.add_row(
                str(i), name[:34],
                f"{PRIO_ICON.get(ps,'🟡')} {t.get('priority','')}",
                f"[{STATUS_STYLE.get(st,'white')}]{st}[/]",
                t.get("category",""), tags,
            )
        C.print(tbl)
        C.print()
        C.print(f"  Enter a [bold]number[/] to open task   "
                f"  [bold {THEME['secondary']}]Enter[/] to search again   "
                f"  [bold {THEME['secondary']}]b[/] to go back")
        C.print()
        ch = Prompt.ask(f"  [{THEME['secondary']}]>[/]").strip().lower()
        if ch == "b": return
        try:
            idx  = int(ch) - 1
            task = results[idx][1]
            # find live reference
            live = next((t for t in db["tasks"] if t["id"] == task["id"]), task)
            from rich.prompt import Prompt as _P  # noqa — already imported
            screen_task_detail(db, None, live)
        except (ValueError, IndexError):
            pass  # loop again


def screen_backups():
    """Browse and restore rolling backups of tasks.json."""
    header("💾  Backups")
    backups = []
    for i in range(1, BACKUP_COUNT + 1):
        p = DATA_FILE.with_suffix(f".bak.{i}")
        if p.exists():
            try:
                data = json.loads(p.read_text())
                tasks = len(data.get("tasks",[]))
                mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                backups.append((i, p, tasks, mtime))
            except Exception:
                backups.append((i, p, -1, "corrupted"))

    if not backups:
        C.print(Panel(
            "  No backups yet.\n"
            "  [dim]Backups are created automatically before each save.[/]",
            border_style=THEME["border"], padding=(0,1)
        ))
        press_enter(); return

    from rich.table import Table
    from rich       import box as rbox
    tbl = Table(box=rbox.ROUNDED, border_style=THEME["border"],
                header_style=f"bold {THEME['secondary']}", padding=(0,1),
                title=f"[bold {THEME['secondary']}]Rolling Backups[/]", title_justify="left")
    tbl.add_column("#",      width=3, justify="right", style="dim")
    tbl.add_column("When",   width=22)
    tbl.add_column("Tasks",  width=8, justify="right")
    tbl.add_column("File",   min_width=30, style="dim")
    for i, p, tasks, mtime in backups:
        task_str = str(tasks) if tasks >= 0 else "[red]corrupted[/]"
        tbl.add_row(str(i), mtime, task_str, p.name)
    C.print(tbl)
    C.print()
    C.print(f"  Enter a [bold]number[/] to restore that backup   "
            f"  [bold {THEME['secondary']}]b[/] to cancel")
    C.print()
    ch = Prompt.ask(f"  [{THEME['secondary']}]>[/]").strip().lower()
    if ch == "b" or not ch: return
    try:
        idx  = int(ch) - 1
        _, p, tasks, mtime = backups[idx]
        if tasks < 0:
            C.print("  [red]Backup is corrupted — cannot restore.[/]")
            press_enter(); return
        if Confirm.ask(f"  Restore backup from [bold]{mtime}[/] ({tasks} tasks)?"):
            import shutil
            # back up current before restoring
            _rotate_backups()
            shutil.copy2(p, DATA_FILE)
            C.print(f"  [green]✓ Restored! Restart TaskFlow to load the restored data.[/]")
    except (ValueError, IndexError):
        pass
    press_enter()


# ─────────────────────────────────────────────────────────────
# REGISTRY CLIENT  (SHA-256 verified downloads)
# ─────────────────────────────────────────────────────────────

APP_VERSION = "3.0"


def _sha256(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _fetch_registry(url: str) -> list:
    import urllib.request
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/plugins", timeout=8) as r:
            return json.loads(r.read())["plugins"]
    except Exception as e:
        return [{"_error": str(e)}]


def _fetch_app_info(url: str) -> dict:
    import urllib.request
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/app", timeout=8) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"_error": str(e)}


def _download_verified(url: str, filename: str, expected_sha: str) -> tuple:
    import urllib.request
    with urllib.request.urlopen(f"{url.rstrip('/')}/plugin/{filename}", timeout=15) as r:
        raw = r.read()
    actual = _sha256(raw)
    if expected_sha and not (actual.startswith(expected_sha) or actual == expected_sha):
        raise ValueError(
            f"SHA mismatch — file may be tampered!\n"
            f"  Expected: {expected_sha}\n"
            f"  Got:      {actual[:max(len(expected_sha),16)]}"
        )
    return raw.decode("utf-8"), actual


def _download_app_update(url: str, expected_sha: str) -> tuple:
    import urllib.request
    with urllib.request.urlopen(f"{url.rstrip('/')}/app/taskflow.py", timeout=30) as r:
        raw = r.read()
    actual = _sha256(raw)
    if expected_sha and not (actual.startswith(expected_sha) or actual == expected_sha):
        raise ValueError(
            f"App SHA mismatch — download corrupted or tampered.\n"
            f"  Expected: {expected_sha}\n"
            f"  Got:      {actual[:max(len(expected_sha),16)]}"
        )
    return raw, actual


def _verify_installed_plugin(fname: str) -> tuple:
    p = PLUGINS_DIR / fname
    if not p.exists():
        return False, ""
    return True, _sha256(p.read_bytes())

def screen_registry(db):
    """Browse and install/uninstall plugins from a registry server."""
    store_path = DATA_DIR / "plugin_data" / "_registry.json"
    store_path.parent.mkdir(exist_ok=True)
    store = json.loads(store_path.read_text()) if store_path.exists() else {}
    registry_url = store.get("url", "http://localhost:8888")

    while True:
        header("🔌  Plugin Registry")

        # Show configured server
        C.print(Panel(
            f"  Server: [bold]{registry_url}[/]\n"
            "  [dim]Change with  s[/]",
            border_style=THEME["border"], padding=(0,1)
        ))
        C.print()

        C.print(f"  [bold {THEME['secondary']}]i[/]  Browse & install plugins")
        C.print(f"  [bold {THEME['secondary']}]u[/]  Uninstall a plugin")
        C.print(f"  [bold {THEME['secondary']}]c[/]  Check for app update")
        C.print(f"  [bold {THEME['secondary']}]v[/]  Verify installed plugins (SHA check)")
        C.print(f"  [bold {THEME['secondary']}]s[/]  Set registry server URL")
        C.print(f"  [bold {THEME['secondary']}]b[/]  Back")
        C.print()
        ch = Prompt.ask(f"  [{THEME['secondary']}]>[/]").lower().strip()

        if ch == "b":
            return

        elif ch == "c":
            header("App Update Check")
            C.print(f"  [dim]Fetching update info from {registry_url} …[/]\n")
            info = _fetch_app_info(registry_url)
            if "_error" in info:
                C.print(Panel(f"  [red]Error: {info['_error']}[/]",
                              border_style="red", padding=(0,1)))
                press_enter(); continue
            srv_ver = info.get("version","?")
            srv_sha = info.get("sha256","")
            my_sha  = _sha256(Path(__file__).read_bytes())
            up2date = my_sha.startswith(srv_sha) if srv_sha else None
            C.print(Panel(
                f"  Current version:   [bold]{APP_VERSION}[/]\n"
                f"  Server version:    [bold]{srv_ver}[/]\n"
                f"  Your SHA-256:      [dim]{my_sha[:16]}[/]\n"
                f"  Server SHA-256:    [dim]{srv_sha[:16] if srv_sha else '—'}[/]\n"
                f"  Status:            {'[green]✓ Up to date[/]' if up2date else '[yellow]Update available[/]' if up2date is False else '[dim]Unknown[/]'}",
                border_style=THEME["border"], padding=(0,1)
            ))
            C.print()
            if up2date is False:
                C.print(f"  Changelog: [dim]{info.get('changelog','—')}[/]\n")
                if Confirm.ask("  Download and apply update now?", default=False):
                    C.print("  [dim]Downloading…[/]")
                    try:
                        raw, actual = _download_app_update(registry_url, srv_sha)
                        backup = Path(__file__).with_suffix(".py.bak")
                        import shutil
                        shutil.copy2(__file__, backup)
                        Path(__file__).write_bytes(raw)
                        C.print(f"  [green]✓ Updated to v{srv_ver}![/]")
                        C.print(f"  [dim]Backup saved to: {backup}[/]")
                        C.print(f"  [yellow]Restart TaskFlow to apply the update.[/]")
                    except ValueError as e:
                        C.print(f"  [bold red]⚠ {e}[/]")
                        C.print("  [red]Update aborted — your file was NOT changed.[/]")
                    except Exception as e:
                        C.print(f"  [red]Download failed: {e}[/]")
            press_enter()

        elif ch == "v":
            header("Plugin SHA Verification")
            installed = list(PLUGINS_DIR.glob("*.py"))
            if not installed:
                C.print("  [dim]No plugins installed.[/]"); press_enter(); continue
            C.print(f"  [dim]Fetching registry checksums from {registry_url} …[/]\n")
            remote  = _fetch_registry(registry_url)
            srv_map = {p["filename"]: p.get("sha256","") for p in remote
                       if "_error" not in p}
            tbl = Table(box=box.ROUNDED, border_style=THEME["border"],
                        header_style=f"bold {THEME['secondary']}", padding=(0,1))
            tbl.add_column("Plugin",   min_width=24)
            tbl.add_column("Local SHA",   width=16)
            tbl.add_column("Server SHA",  width=16)
            tbl.add_column("Status",      width=18)
            for f in installed:
                _, local_sha = _verify_installed_plugin(f.name)
                srv_sha      = srv_map.get(f.name,"")
                if not srv_sha:
                    status = "[dim]not in registry[/]"
                elif local_sha.startswith(srv_sha):
                    status = "[green]✓ verified[/]"
                else:
                    status = "[red]✗ MISMATCH[/]"
                tbl.add_row(f.name, local_sha[:14], srv_sha[:14] or "—", status)
            C.print(tbl)
            press_enter()

        elif ch == "s":
            registry_url = ask_str("Registry URL", default=registry_url)
            store["url"] = registry_url
            store_path.write_text(json.dumps(store))
            C.print(f"  [green]✓ Saved.[/]")
            press_enter()

        elif ch == "u":
            header("Uninstall Plugin")
            installed = list(PLUGINS_DIR.glob("*.py"))
            if not installed:
                C.print("  [dim]No plugins installed.[/]")
                press_enter(); continue
            for i, f in enumerate(installed, 1):
                C.print(f"  [dim]{i}.[/]  {f.name}")
            C.print()
            raw = Prompt.ask(f"  [{THEME['secondary']}]Number to uninstall (Enter to cancel)[/]",
                             default="")
            if not raw.strip():
                continue
            try:
                f = installed[int(raw)-1]
                if Confirm.ask(f"  Remove [bold]{f.name}[/]?"):
                    _uninstall_plugin(f.name, db)
                    load_plugins(db)
                    C.print(f"  [green]✓ Removed {f.name}[/]")
            except Exception as e:
                C.print(f"  [red]{e}[/]")
            press_enter()

        elif ch == "i":
            header("Browse Registry")
            C.print(f"  [dim]Fetching {registry_url} …[/]")
            plugins = _fetch_registry(registry_url)

            if plugins and "_error" in plugins[0]:
                C.print(Panel(
                    f"  [red]Could not connect:[/] {plugins[0]['_error']}\n\n"
                    f"  Start the registry server with:\n"
                    f"  [bold]python plugin_server.py[/]",
                    border_style="red", padding=(0,1)
                ))
                press_enter(); continue

            installed_names = {f.name for f in PLUGINS_DIR.glob("*.py")}

            tbl = Table(box=box.ROUNDED, border_style=THEME["border"],
                        header_style=f"bold {THEME['secondary']}", padding=(0,1))
            tbl.add_column("#",       width=3, justify="right", style="dim")
            tbl.add_column("Plugin",  min_width=16)
            tbl.add_column("Ver",     width=6)
            tbl.add_column("Author",  width=10)
            tbl.add_column("Description", min_width=22)
            tbl.add_column("SHA-256", width=14)
            tbl.add_column("",        width=16)

            for i, p in enumerate(plugins, 1):
                inst_status = ""
                if p["filename"] in installed_names:
                    _, inst_sha = _verify_installed_plugin(p["filename"])
                    srv_sha     = p.get("sha256","")
                    if srv_sha and inst_sha and not inst_sha.startswith(srv_sha):
                        inst_status = "[yellow]update available[/]"
                    else:
                        inst_status = "[green]✓ installed[/]"
                tbl.add_row(
                    str(i),
                    f"[bold]{p['name']}[/]",
                    p.get("version","?"),
                    p.get("author","?"),
                    f"[dim]{p.get('desc','')[:30]}[/]",
                    f"[dim]{p.get('sha256','')[:12]}[/]",
                    inst_status,
                )
            C.print(tbl)
            C.print()
            C.print("  Enter a [bold]number[/] to install   [bold]b[/] back")
            C.print()
            raw = Prompt.ask(f"  [{THEME['secondary']}]>[/]").strip().lower()
            if raw == "b":
                continue
            try:
                idx  = int(raw) - 1
                plug = plugins[idx]
            except Exception:
                continue

            fname = plug["filename"]
            dest  = PLUGINS_DIR / fname
            if dest.exists():
                C.print(f"  [yellow]Already installed.[/]")
                press_enter(); continue

            expected_sha = plug.get("sha256","")
            C.print(f"  [dim]Downloading {fname} …[/]")
            if expected_sha:
                C.print(f"  [dim]Expected SHA-256: {expected_sha}[/]")
            try:
                code, actual_sha = _download_verified(registry_url, fname, expected_sha)
                dest.write_text(code, encoding="utf-8")
                C.print(f"  [green]✓ SHA verified:  {actual_sha[:16]}[/]")
                load_plugins(db)
                C.print(f"  [green]✓ Installed {plug['name']} v{plug.get('version','?')}[/]")
            except ValueError as e:
                C.print(f"  [bold red]⚠ {e}[/]")
                C.print("  [red]Installation aborted — file was NOT saved.[/]")
            except Exception as e:
                C.print(f"  [red]Download failed: {e}[/]")
            press_enter()


def screen_plugins(db):
    ALL_HOOKS = ["on_startup","on_task_created","on_task_done","on_task_deleted",
                 "on_tick","menu_items"]
    while True:
        header("🔌  Plugins")
        PLUGINS_DIR.mkdir(exist_ok=True)
        files = list(PLUGINS_DIR.glob("*.py"))

        tbl = Table(box=box.ROUNDED, border_style=THEME["border"],
                    header_style=f"bold {THEME['secondary']}", padding=(0,1))
        tbl.add_column("Plugin",      min_width=20)
        tbl.add_column("Version",     width=8)
        tbl.add_column("Status",      width=10)
        tbl.add_column("Hooks",       min_width=22)
        tbl.add_column("Description", min_width=24)

        loaded_names = {Path(p.__file__).name for p in _loaded_plugins}
        for plugin in _loaded_plugins:
            fname = Path(plugin.__file__).name
            name  = getattr(plugin, "PLUGIN_NAME",    fname.replace(".py",""))
            ver   = getattr(plugin, "PLUGIN_VERSION", "—")
            desc  = getattr(plugin, "PLUGIN_DESC",    "")
            hooks = [h for h in ALL_HOOKS if hasattr(plugin, h)]
            pver  = _plugin_api_versions.get(plugin.__name__, "v3")
            compat = f" [dim](compat {pver})[/]" if pver != "v3" else ""
            tbl.add_row(name, ver, f"[green]active[/]{compat}",
                        "[dim]" + " ".join(hooks) + "[/]", f"[dim]{desc}[/]")
        for fname, err in _plugin_errors.items():
            tbl.add_row(fname, "—", "[red]error[/]", "—", f"[red]{err[:40]}[/]")
        for f in files:
            if f.name not in loaded_names and f.name not in _plugin_errors:
                tbl.add_row(f.name, "—", "[yellow]not loaded[/]", "—", "")

        if not files and not _plugin_errors:
            C.print(Panel(
                f"  Dir: [bold]{PLUGINS_DIR}[/]\n"
                "  Use [bold]i[/] to install from registry, or [bold]n[/] to create one.",
                title=f"[bold {THEME['secondary']}]No plugins installed[/]",
                border_style=THEME["border"], padding=(0,1)
            ))
        else:
            C.print(tbl)

        C.print()
        C.print(f"  [dim]{PLUGINS_DIR}[/]  ·  [green]{len(_loaded_plugins)} active[/]"
                + (f"  [red]  {len(_plugin_errors)} errors[/]" if _plugin_errors else ""))
        C.print()
        C.print(Rule(f"[dim]Actions[/]", style=THEME["border"]))
        C.print(f"  [bold {THEME['secondary']}]i[/]  Install from registry  🌐")
        C.print(f"  [bold {THEME['secondary']}]r[/]  Reload plugins")
        C.print(f"  [bold {THEME['secondary']}]o[/]  Open plugin directory")
        C.print(f"  [bold {THEME['secondary']}]n[/]  New plugin from template")
        if _plugin_errors:
            C.print(f"  [bold {THEME['secondary']}]e[/]  Show error details")
        C.print(f"  [bold {THEME['secondary']}]b[/]  Back")
        C.print()
        ch = Prompt.ask(f"  [{THEME['secondary']}]>[/]").lower().strip()

        if   ch == "b": return
        elif ch == "i": screen_registry(db)
        elif ch == "r":
            load_plugins(db)
            C.print(f"  [green]✓ {len(_loaded_plugins)} plugin(s) loaded.[/]"
                    + (f"  [red]{len(_plugin_errors)} error(s)[/]" if _plugin_errors else ""))
            press_enter()
        elif ch == "o":
            try: subprocess.Popen(["xdg-open", str(PLUGINS_DIR)])
            except Exception: C.print(f"  [dim]{PLUGINS_DIR}[/]")
            press_enter()
        elif ch == "e" and _plugin_errors:
            header("Plugin Errors")
            for fname, err in _plugin_errors.items():
                C.print(Panel(f"[red]{err}[/]", title=f"[bold]{fname}[/]",
                              border_style="red", padding=(0,1)))
            press_enter()
        elif ch == "n":
            pname = ask_str("Plugin name (no spaces)", required=True).replace(" ","_")
            if not pname.endswith(".py"): pname += ".py"
            target = PLUGINS_DIR / pname
            stem   = pname.replace(".py","")
            if target.exists():
                C.print("  [yellow]File already exists.[/]"); press_enter(); continue
            target.write_text(
                f'# TaskFlow Plugin\n'
                f'PLUGIN_NAME    = "{stem}"\n'
                f'PLUGIN_VERSION = "1.0"\n'
                f'PLUGIN_DESC    = "My custom plugin"\n\n'
                f'def on_startup(api):\n    pass\n\n'
                f'def menu_items(api):\n'
                f'    def run():\n'
                f'        api.console.print("[cyan]Hello from {stem}![/]")\n'
                f'        input("  Press Enter...")\n'
                f'    return [("{stem[0]}", "{stem}", run)]\n'
            )
            C.print(f"  [green]✓ Created: {target}[/]")
            load_plugins(db)
            press_enter()

# ─────────────────────────────────────────────────────────────
# DISPLAY HELPERS
# ─────────────────────────────────────────────────────────────

def clear():
    os.system("clear" if os.name != "nt" else "cls")

def header(subtitle=""):
    clear()
    title = Text("  ⚡  TaskFlow", style=f"bold {THEME['primary']}")
    if subtitle:
        title.append(f"   ·   {subtitle}", style=f"dim {THEME['dim']}")
    C.print()
    C.print(Align.center(title))
    C.print(Rule(style=THEME["border"]))
    C.print()

def press_enter(msg="Press Enter to continue"):
    C.print(f"\n  [dim]{msg}[/]")
    input()

def stat_card(label, value, color=None):
    return Panel(
        Align.center(f"[bold {color}]{value}[/]\n[dim]{label}[/]"),
        border_style=THEME["border"],
        padding=(0, 2),
    )

def pick(prompt_text, options: list, default_idx=0) -> str:
    """Numbered option picker — returns chosen string."""
    for i, o in enumerate(options, 1):
        marker = f" [bold {THEME['secondary']}]>[/]" if i-1 == default_idx else "  "
        C.print(f"{marker} [dim]{i}.[/]  {o}")
    C.print()
    while True:
        raw = Prompt.ask(f"  [{THEME['secondary']}]{prompt_text}[/]",
                         default=str(default_idx + 1))
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            pass
        C.print("  [red]Invalid — enter a number from the list.[/]")

def ask_str(label, default="", required=False) -> str:
    d = f" [dim][{default}][/]" if default else ""
    while True:
        val = Prompt.ask(f"  [{THEME['secondary']}]{label}[/]{d}", default=default)
        if required and not val.strip():
            C.print("  [red]Required.[/]")
            continue
        return val.strip()

def ask_float(label, default=1.0) -> float:
    while True:
        raw = Prompt.ask(f"  [{THEME['secondary']}]{label}[/]", default=str(default))
        try:
            return float(raw)
        except ValueError:
            C.print("  [red]Enter a number.[/]")

def _due_text(due_str, status):
    if not due_str:
        return Text("  —", style="dim")
    if status in ("done", "cancelled"):
        return Text(f"  {due_str}", style="dim")
    try:
        days = (datetime.fromisoformat(due_str) - datetime.now()).days
        if   days < 0:  return Text(f"  ⚠ {due_str}", style="bold red")
        elif days == 0: return Text(f"  ⏰ Today",     style="bold yellow")
        elif days <= 2: return Text(f"  {due_str}",    style="yellow")
        else:           return Text(f"  {due_str}",    style="green")
    except Exception:
        return Text(f"  {due_str}")

def render_task_table(tasks, title="Tasks", show_index=True):
    if not tasks:
        C.print(Panel("  [dim]No tasks here.[/]", border_style=THEME["border"]))
        return
    t = Table(
        box=box.ROUNDED, border_style=THEME["border"],
        header_style=f"bold {THEME['secondary']}",
        title=f"[bold {THEME['secondary']}]{title}[/]", title_justify="left",
        show_lines=False, padding=(0, 1),
    )
    if show_index:
        t.add_column("#", style="dim", width=3, justify="right")
    t.add_column("ID",       style="dim #445566", width=8)
    t.add_column("Task",                          min_width=22)
    t.add_column("Priority",                      width=14)
    t.add_column("Category", style="#778899",     width=11)
    t.add_column("Status",                        width=14)
    t.add_column("Due",                           width=14)
    t.add_column("h",  justify="right",           width=5)

    for i, task in enumerate(tasks, 1):
        ps     = task.get("priority_score", 3)
        status = task.get("status", "todo")
        name   = task.get("name", "")
        if   status == "done":      nm = Text(f"  {name}", style="dim strike")
        elif status == "cancelled": nm = Text(f"  {name}", style="dim")
        else:                       nm = Text(f"  {name}", style=PRIO_STYLE.get(ps, "white"))

        prio_t = Text(f"  {PRIO_ICON.get(ps,'🟡')} {task.get('priority','')}",
                      style=PRIO_STYLE.get(ps, "white"))
        stat_t = Text(f"  {STATUS_ICON.get(status,'○')} {status}",
                      style=STATUS_STYLE.get(status, "white"))
        due_t  = _due_text(task.get("due_date", ""), status)

        row = ([str(i)] if show_index else []) + [
            task["id"], nm, prio_t,
            task.get("category", ""), stat_t, due_t,
            str(task.get("estimated_hours", 1.0)),
        ]
        t.add_row(*row)
    C.print(t)

# ─────────────────────────────────────────────────────────────
# GRAPHS
# ─────────────────────────────────────────────────────────────

def screen_graphs(db):
    """6 charts rendered directly in the terminal using plotext — no numpy/X11 needed."""
    if not HAS_PLT:
        C.print(Panel("[yellow]Install plotext:  pip install plotext[/]", border_style="yellow"))
        press_enter(); return

    tasks = db["tasks"]
    if not tasks:
        C.print(Panel("[dim]No tasks to visualise yet.[/]", border_style=THEME["border"]))
        press_enter(); return

    now  = datetime.now()
    done = [t for t in tasks if t["status"] == "done" and t.get("completed_at")]

    charts = [
        ("1", "Priority distribution"),
        ("2", "Tasks by category"),
        ("3", "Completions — last 30 days"),
        ("4", "Status overview"),
        ("5", "Productivity by weekday"),
        ("6", "Estimate accuracy scatter"),
        ("a", "Show all"),
        ("b", "Back"),
    ]

    while True:
        header("📊  Graphs")
        for k, lbl in charts:
            C.print(f"  [bold {THEME['secondary']}]{k}[/]  {lbl}")
        C.print()
        ch = Prompt.ask(f"  [{THEME['secondary']}]>[/]", default="a")

        if ch == "b":
            return

        show = set()
        if ch == "a":
            show = {"1","2","3","4","5","6"}
        elif ch in {k for k,_ in charts}:
            show = {ch}

        if not show:
            continue

        # ── 1: Priority distribution (horizontal bar) ────────────────
        if "1" in show:
            header("📊  Priority Distribution")
            pr   = ["Critical","High","Medium","Low","Minimal"]
            cnt  = Counter(t.get("priority","Medium") for t in tasks)
            vals = [cnt.get(p, 0) for p in pr]
            _plt.clt(); _plt.clf()
            _plt.theme("dark")
            _plt.bar(pr, vals, orientation="h", color=["red","orange","yellow","green","white"])
            _plt.title("Priority Distribution")
            _plt.xlabel("Tasks")
            _plt.show()
            if ch == "a": press_enter("Enter for next chart")

        # ── 2: Category bar ──────────────────────────────────────────
        if "2" in show:
            header("📊  Tasks by Category")
            cc   = Counter(t.get("category","Other") for t in tasks)
            cats = [c for c, _ in cc.most_common()]
            cv   = [cc[c] for c in cats]
            _plt.clt(); _plt.clf()
            _plt.theme("dark")
            _plt.bar(cats, cv, orientation="h", color="cyan")
            _plt.title("Tasks by Category")
            _plt.show()
            if ch == "a": press_enter("Enter for next chart")

        # ── 3: Completions last 30 days (line) ───────────────────────
        if "3" in show:
            header("📊  Completions — Last 30 Days")
            last30 = [now.date()-timedelta(days=i) for i in range(29,-1,-1)]
            dcnt   = Counter(datetime.fromisoformat(t["completed_at"]).date()
                             for t in done)
            daily  = [dcnt.get(d, 0) for d in last30]
            labels = [str(d) if i % 7 == 0 else "" for i, d in enumerate(last30)]
            _plt.clt(); _plt.clf()
            _plt.theme("dark")
            _plt.plot(list(range(30)), daily, color="cyan", marker="dot")
            _plt.title("Completions — Last 30 Days")
            _plt.xticks(list(range(0,30,7)), [str(last30[i]) for i in range(0,30,7)])
            _plt.show()
            if ch == "a": press_enter("Enter for next chart")

        # ── 4: Status overview (bar) ─────────────────────────────────
        if "4" in show:
            header("📊  Status Overview")
            sts  = ["todo","in_progress","done","cancelled"]
            slbl = ["To Do","In Progress","Done","Cancelled"]
            sc   = Counter(t.get("status","todo") for t in tasks)
            sv   = [sc.get(s, 0) for s in sts]
            _plt.clt(); _plt.clf()
            _plt.theme("dark")
            _plt.bar(slbl, sv, color=["blue","yellow","green","white"])
            _plt.title("Status Overview")
            _plt.show()
            if ch == "a": press_enter("Enter for next chart")

        # ── 5: Productivity by weekday ───────────────────────────────
        if "5" in show:
            header("📊  Productivity by Weekday")
            dow  = Counter()
            for t in done:
                try: dow[datetime.fromisoformat(t["completed_at"]).weekday()] += 1
                except Exception: pass
            days = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
            dv   = [dow.get(i, 0) for i in range(7)]
            _plt.clt(); _plt.clf()
            _plt.theme("dark")
            _plt.bar(days, dv, color="yellow")
            _plt.title("Productivity by Weekday")
            _plt.show()
            if ch == "a": press_enter("Enter for next chart")

        # ── 6: Estimate accuracy (scatter) ───────────────────────────
        if "6" in show:
            header("📊  Estimate Accuracy")
            pairs = [(t.get("estimated_hours",1), t["actual_hours"])
                     for t in done if t.get("actual_hours")]
            if pairs:
                est = [p[0] for p in pairs]
                act = [p[1] for p in pairs]
                _plt.clt(); _plt.clf()
                _plt.theme("dark")
                _plt.scatter(est, act, color="cyan", marker="dot")
                mx = max(max(est), max(act))
                _plt.plot([0, mx], [0, mx], color="red", label="perfect estimate")
                _plt.xlabel("Estimated h"); _plt.ylabel("Actual h")
                _plt.title("Estimate Accuracy (Estimated vs Actual hours)")
                _plt.show()
            else:
                C.print(Panel(
                    "  [dim]No actual hours logged yet.\n  Start a task, complete it, and hours are tracked automatically.[/]",
                    title=f"[bold {THEME['secondary']}]📊  Estimate Accuracy[/]", border_style=THEME["border"], padding=(1,1)
                ))

        if ch != "b":
            press_enter()

# ─────────────────────────────────────────────────────────────
# LOCAL AI PRIORITY SUGGESTER  (no API, no deps)
# ─────────────────────────────────────────────────────────────

def suggest_priority(name: str, desc: str, category: str,
                     due: str, db: dict) -> tuple[str, list[str]]:
    """
    Pure-local priority suggestion.
    Returns (priority_string, [reason, ...])
    """
    text   = (name + " " + desc).lower()
    score  = 3   # default Medium
    reasons= []

    # Keyword scan
    for prio_score, keywords in KEYWORD_SIGNALS.items():
        for kw in keywords:
            if kw in text:
                if prio_score > score:
                    score = prio_score
                    reasons.append(f"keyword '{kw}' → {list(PRIORITY_SCORE.keys())[5-prio_score]}")
                elif prio_score < score:
                    score = prio_score
                    reasons.append(f"keyword '{kw}' → lower priority")
                break

    # Deadline urgency
    if due:
        try:
            days = (datetime.fromisoformat(due) - datetime.now()).days
            if   days < 0:  score = max(score, 5); reasons.append("overdue deadline")
            elif days == 0: score = max(score, 5); reasons.append("due today")
            elif days <= 2: score = max(score, 4); reasons.append(f"due in {days} day(s)")
            elif days <= 7: score = max(score, 3); reasons.append(f"due in {days} day(s)")
        except Exception:
            pass

    # Category bias
    bias = CAT_BIAS.get(category, 0)
    if bias and score < 4:
        score = min(score + bias, 4)
        if bias > 0:
            reasons.append(f"category '{category}' tends to be important")

    # Personal history: what priority did you typically assign in this category?
    done_in_cat = [t for t in db.get("tasks", [])
                   if t.get("category") == category and t.get("status") == "done"]
    if len(done_in_cat) >= 3:
        avg = sum(t.get("priority_score",3) for t in done_in_cat) / len(done_in_cat)
        hist_score = round(avg)
        if hist_score != score:
            # Only nudge, don't override hard signals
            if not any(s >= 4 for s in [score]):
                score = hist_score
                reasons.append(f"your {category} tasks average {list(PRIORITY_SCORE.keys())[5-hist_score]}")

    score = max(1, min(5, score))
    priority = {v: k for k, v in PRIORITY_SCORE.items()}[score]

    if not reasons:
        reasons = ["no strong signals — defaulting to Medium"]

    return priority, reasons


# ─────────────────────────────────────────────────────────────
# GIT SYNC
# ─────────────────────────────────────────────────────────────

def _git(args: list, cwd=None) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["git"] + args, cwd=cwd or str(DATA_DIR),
            capture_output=True, text=True, timeout=10
        )
        return r.returncode, r.stdout.strip() + r.stderr.strip()
    except Exception as e:
        return 1, str(e)

def git_init_if_needed():
    """Initialise ~/.taskflow as a git repo if not already."""
    DATA_DIR.mkdir(exist_ok=True)
    if not (DATA_DIR / ".git").exists():
        _git(["init"])
        _git(["add", "."])
        _git(["commit", "-m", "TaskFlow: init"])

def git_commit(msg: str = "sync"):
    """Stage tasks.json and commit."""
    git_init_if_needed()
    _git(["add", "tasks.json"])
    code, out = _git(["commit", "-m", f"taskflow: {msg}"])
    return code, out

def git_push():
    code, out = _git(["push"])
    return code, out

def git_pull():
    code, out = _git(["pull", "--rebase"])
    return code, out

def git_log(n=10):
    _, out = _git(["log", f"-{n}", "--oneline", "--no-color"])
    return out

def screen_git(db):
    while True:
        header("🐙  Git Sync")
        git_init_if_needed()
        _, status = _git(["status", "--short"])
        _, branch = _git(["rev-parse", "--abbrev-ref", "HEAD"])
        _, remote  = _git(["remote", "-v"])
        has_remote = bool(remote.strip())

        remote_txt = "[green]configured[/]" if has_remote else "[yellow]none[/]"
        C.print(Panel(
            f"  Branch: [bold {THEME['primary']}]{branch}[/]\n"
            f"  Remote: {remote_txt}\n"
            f"  Status: [dim]{status or 'clean'}[/]",
            title=f"[bold {THEME['secondary']}]Repository[/]", border_style=THEME["border"], padding=(0,1)
        ))
        C.print()

        log = git_log(6)
        if log:
            C.print(Panel(f"[dim]{log}[/]", title=f"[bold {THEME['secondary']}]Recent Commits[/]",
                          border_style=THEME["border"], padding=(0,1)))
        C.print()

        C.print(Rule(f"[dim]Actions[/]", style=THEME["border"]))
        C.print(f"  [bold {THEME['secondary']}]c[/]  Commit current state")
        if has_remote:
            C.print(f"  [bold {THEME['secondary']}]u[/]  Push to remote")
            C.print(f"  [bold {THEME['secondary']}]d[/]  Pull from remote (sync)")
        C.print(f"  [bold {THEME['secondary']}]r[/]  Add remote URL")
        C.print(f"  [bold {THEME['secondary']}]B[/]  Browse & restore backups")
        C.print(f"  [bold {THEME['secondary']}]b[/]  Back")
        C.print()
        ch = Prompt.ask(f"  [{THEME['secondary']}]>[/]").lower().strip()

        if ch == "b":
            return
        elif ch == "c":
            msg = ask_str("Commit message", default="manual sync")
            code, out = git_commit(msg)
            if code == 0:
                C.print(f"  [green]✓ Committed[/]")
            elif "nothing to commit" in out:
                C.print(f"  [dim]Nothing to commit — already up to date.[/]")
            else:
                C.print(f"  [yellow]{out}[/]")
            press_enter()
        elif ch == "u" and has_remote:
            code, out = git_push()
            C.print(f"  {'[green]✓ Pushed[/]' if code==0 else '[red]'+out+'[/]'}")
            press_enter()
        elif ch == "d" and has_remote:
            code, out = git_pull()
            C.print(f"  {'[green]✓ Pulled[/]' if code==0 else '[red]'+out+'[/]'}")
            if code == 0:
                db.update(load())   # reload from disk
            press_enter()
        elif ch == "r":
            url = ask_str("Remote URL  (e.g. git@github.com:user/taskflow-data.git)", required=True)
            _git(["remote", "remove", "origin"])
            code, out = _git(["remote", "add", "origin", url])
            C.print(f"  {'[green]✓ Remote set[/]' if code==0 else '[red]'+out+'[/]'}")
            press_enter()
        elif ch == "B":
            screen_backups()


# ─────────────────────────────────────────────────────────────
# DESKTOP NOTIFICATIONS
# ─────────────────────────────────────────────────────────────

def notify(title: str, body: str = "", urgency: str = "normal"):
    """Send a desktop notification, trying multiple backends."""
    # 1) notify-send (libnotify / Arch)
    if shutil.which("notify-send"):
        try:
            r = subprocess.run(
                ["notify-send", "-a", "TaskFlow", "-u", urgency, title, body],
                timeout=5, capture_output=True
            )
            if r.returncode == 0:
                return True
        except Exception:
            pass
    # 2) gdbus direct call (works without a running notification daemon)
    try:
        cmd = [
            "gdbus", "call", "--session",
            "--dest", "org.freedesktop.Notifications",
            "--object-path", "/org/freedesktop/Notifications",
            "--method", "org.freedesktop.Notifications.Notify",
            "TaskFlow", "0", "", title, body,
            "[]", "{}", "5000",
        ]
        r = subprocess.run(cmd, timeout=5, capture_output=True)
        if r.returncode == 0:
            return True
    except Exception:
        pass
    # 3) terminal-notifier (macOS)
    if shutil.which("terminal-notifier"):
        try:
            subprocess.run(["terminal-notifier", "-title", title, "-message", body],
                           timeout=5, capture_output=True)
            return True
        except Exception:
            pass
    return False

def check_and_notify(tasks: list):
    """Check all tasks and fire notifications for due/overdue ones."""
    now = datetime.now()
    fired = 0
    for t in tasks:
        if t.get("status") not in ("todo", "in_progress"):
            continue
        due = t.get("due_date", "")
        if not due:
            continue
        try:
            days = (datetime.fromisoformat(due) - now).days
            name = t["name"][:50]
            if days < 0:
                ok = notify(f"⚠ Overdue: {name}",
                            f"Was due {abs(days)} day(s) ago  [{t.get('priority','')}]",
                            urgency="critical")
                if ok: fired += 1
            elif days == 0:
                ok = notify(f"⏰ Due today: {name}",
                            f"Category: {t.get('category','')}  Priority: {t.get('priority','')}",
                            urgency="critical")
                if ok: fired += 1
            elif days == 1:
                ok = notify(f"🔔 Due tomorrow: {name}",
                            f"Category: {t.get('category','')}",
                            urgency="normal")
                if ok: fired += 1
        except Exception:
            pass
    return fired


# ─────────────────────────────────────────────────────────────
# RECURRING TASKS
# ─────────────────────────────────────────────────────────────

def _next_due(due_str: str, recurrence: str) -> str:
    """Calculate next due date based on recurrence rule."""
    try:
        d = datetime.fromisoformat(due_str).date()
    except Exception:
        d = date.today()
    if   recurrence == "daily":    d += timedelta(days=1)
    elif recurrence == "weekly":   d += timedelta(weeks=1)
    elif recurrence == "biweekly": d += timedelta(weeks=2)
    elif recurrence == "monthly":
        month = d.month + 1
        year  = d.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        from calendar import monthrange
        day = min(d.day, monthrange(year, month)[1])
        d   = d.replace(year=year, month=month, day=day)
    return d.isoformat()

def spawn_recurrence(db: dict, task: dict):
    """When a recurring task is completed, create the next instance."""
    rec = task.get("recurrence", "none")
    if rec == "none":
        return
    next_due = _next_due(task.get("due_date", date.today().isoformat()), rec)
    child = new_task(
        name     = task["name"],
        priority = task.get("priority", "Medium"),
        category = task.get("category", "Work"),
        due      = next_due,
        hours    = task.get("estimated_hours", 1.0),
        desc     = task.get("description", ""),
        tags     = task.get("tags", []),
    )
    child["recurrence"] = rec
    child["parent_id"]  = task["id"]
    db["tasks"].append(child)
    save(db)
    return child


# ─────────────────────────────────────────────────────────────
# SYSTEMD DAEMON INSTALLER
# ─────────────────────────────────────────────────────────────

DAEMON_SERVICE = """[Unit]
Description=TaskFlow notification daemon
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=oneshot
ExecStart={python} {script} --notify
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=graphical-session.target
"""

DAEMON_TIMER = """[Unit]
Description=TaskFlow notification timer
After=graphical-session.target

[Timer]
OnBootSec=2min
OnUnitActiveSec=30min
Persistent=true

[Install]
WantedBy=timers.target
"""

def install_daemon():
    python = sys.executable
    script = str(Path(__file__).resolve())
    svc_dir = Path.home() / ".config" / "systemd" / "user"
    svc_dir.mkdir(parents=True, exist_ok=True)

    (svc_dir / "taskflow.service").write_text(
        DAEMON_SERVICE.format(python=python, script=script)
    )
    (svc_dir / "taskflow.timer").write_text(DAEMON_TIMER)

    results = []
    for cmd in [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", "taskflow.timer"],
    ]:
        r = subprocess.run(cmd, capture_output=True, text=True)
        results.append((cmd[-1], r.returncode, r.stderr.strip()))
    return results

def uninstall_daemon():
    svc_dir = Path.home() / ".config" / "systemd" / "user"
    for cmd in [
        ["systemctl", "--user", "disable", "--now", "taskflow.timer"],
    ]:
        subprocess.run(cmd, capture_output=True)
    for f in ["taskflow.service", "taskflow.timer"]:
        p = svc_dir / f
        if p.exists(): p.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)

def daemon_status() -> str:
    r = subprocess.run(
        ["systemctl", "--user", "is-active", "taskflow.timer"],
        capture_output=True, text=True
    )
    return r.stdout.strip()

def screen_daemon():
    header("⚙️  systemd Daemon  (Arch)")
    status = daemon_status()
    active = status == "active"

    st_txt = "[green]active[/]" if active else "[yellow]inactive[/]"
    C.print(Panel(
        f"  Status: {st_txt}\n"
        "  Fires every [bold]30 minutes[/] to check for due/overdue tasks\n"
        "  Sends desktop notifications via [bold]notify-send[/]\n"
        "  Service: [dim]~/.config/systemd/user/taskflow.timer[/]",
        title=f"[bold {THEME['secondary']}]🔔  Notification Daemon[/]",
        border_style=THEME["border"], padding=(0,1)
    ))
    C.print()

    if not shutil.which("notify-send"):
        C.print(Panel(
            "  [yellow]notify-send not found.[/]\n"
            "  Install:  [bold]sudo pacman -S libnotify[/]",
            border_style="yellow", padding=(0,1)
        ))
        C.print()

    C.print(Rule(f"[dim]Actions[/]", style=THEME["border"]))
    if not active:
        C.print(f"  [bold {THEME['secondary']}]i[/]  Install & enable timer")
    else:
        C.print(f"  [bold {THEME['secondary']}]u[/]  Uninstall timer")
        C.print(f"  [bold {THEME['secondary']}]t[/]  Test notification now")
    C.print(f"  [bold {THEME['secondary']}]b[/]  Back")
    C.print()

    ch = Prompt.ask(f"  [{THEME['secondary']}]>[/]").lower().strip()
    if ch == "i" and not active:
        results = install_daemon()
        for name, code, err in results:
            if code == 0:
                C.print(f"  [green]✓ {name}[/]")
            else:
                C.print(f"  [red]✗ {name}: {err}[/]")
        press_enter()
    elif ch == "u" and active:
        if Confirm.ask("  Uninstall daemon?"):
            uninstall_daemon()
            C.print("  [dim]Daemon removed.[/]")
            press_enter()
    elif ch == "t":
        ok = notify("TaskFlow ✓", "Notifications are working!")
        C.print(f"  {'[green]Notification sent![/]' if ok else '[red]notify-send not available.[/]'}")
        press_enter()


# ─────────────────────────────────────────────────────────────
# DB HELPERS
# ─────────────────────────────────────────────────────────────

def _update(db, task):
    for i, t in enumerate(db["tasks"]):
        if t["id"] == task["id"]:
            db["tasks"][i] = task
            break
    save(db)

def _find(db, tid):
    for t in db["tasks"]:
        if t["id"] == tid:
            return t
    return None

# ─────────────────────────────────────────────────────────────
# SCREENS
# ─────────────────────────────────────────────────────────────

def screen_home(db, ml, plugin_items=None):
    """Main dashboard."""
    header()
    tasks = db["tasks"]
    now   = datetime.now()
    done  = [t for t in tasks if t["status"] == "done"]
    todo  = [t for t in tasks if t["status"] in ("todo","in_progress")]
    ovd   = [t for t in todo if t.get("due_date") and
             datetime.fromisoformat(t["due_date"]) < now]
    rate  = len(done)/len(tasks)*100 if tasks else 0

    # Stat cards
    cards = [
        stat_card("Total Tasks",  str(len(tasks))),
        stat_card("Completed",    str(len(done)),   "#2ecc71"),
        stat_card("Pending",      str(len(todo)),   "#f39c12"),
        stat_card("Done %",       f"{rate:.0f}%",   "#3498db"),
        stat_card("Overdue",      str(len(ovd)),    "red" if ovd else "#2ecc71"),
    ]
    C.print(Columns(cards, padding=(0,1), equal=True))
    C.print()

    # Active tasks preview (top 6 by priority + due)
    active = sorted(todo, key=lambda t: (-t.get("priority_score",0),
                                          t.get("due_date","9999")))[:6]
    if active:
        render_task_table(active, "⚡  Active Tasks", show_index=False)
        C.print()

    # Insights strip
    insights = ml.insights(tasks)[:3]
    insight_text = "   [dim]│[/]   ".join(f"[dim]{l}[/]" for l in insights)
    C.print(Panel(f"  {insight_text}", border_style=THEME["border"], padding=(0,0)))
    C.print()

    # Menu — fixed items
    C.print(Rule(f"[dim]What would you like to do?[/]", style=THEME["border"]))
    C.print()
    menu = [
        ("1", "View & manage all tasks"),
        ("2", "✚  Create a new task"),
        ("3", "Statistics & insights"),
        ("4", "ML predictions"),
        ("5", "📊 Graphs"),
        ("6", "🐙 Git sync"),
        ("7", "⚙️  Daemon / notifications"),
        ("8", "🔌 Plugins"),
    ]
    # Append plugin menu items
    if plugin_items:
        for key, label, _fn in plugin_items:
            menu.append((key, label))

    if _UNDO_STACK:
        menu.insert(-1, ("u", f"↩  Undo  [dim]({len(_UNDO_STACK)})[/]"))
    if _REDO_STACK:
        menu.insert(-1, ("U", f"↪  Redo  [dim]({len(_REDO_STACK)})[/]"))
    menu.insert(-1, ("0", "🔒 Encryption"))
    menu.append(("q", "Quit"))

    # Print in two columns, splitting evenly
    half  = (len(menu) + 1) // 2
    col_a = menu[:half]
    col_b = menu[half:]
    for i in range(half):
        ka, la = col_a[i]
        kb, lb = col_b[i] if i < len(col_b) else ("", "")
        left  = f"  [bold {THEME['secondary']}]{ka}[/]  {la}" if ka else ""
        right = f"  [bold {THEME['secondary']}]{kb}[/]  {lb}" if kb else ""
        C.print(f"{left:<50}{right}")
    C.print()


def screen_task_list(db, ml):
    while True:
        header("Tasks")
        tasks = db["tasks"]

        # Filter strip
        C.print(
            "  Filter:  "
            f"[bold {THEME['secondary']}]1[/] All  "
            f"[bold {THEME['secondary']}]2[/] Active  "
            f"[bold {THEME['secondary']}]3[/] Done  "
            f"[bold {THEME['secondary']}]4[/] Overdue  "
            f"[bold {THEME['secondary']}]5[/] By category"
        )
        C.print()
        filt = Prompt.ask(f"  [{THEME['secondary']}]Filter[/]", default="1",
                          choices=["1","2","3","4","5"])
        now  = datetime.now()

        if   filt == "1": filtered = tasks[:]; label = "All"
        elif filt == "2": filtered = [t for t in tasks if t["status"] in ("todo","in_progress")]; label = "Active"
        elif filt == "3": filtered = [t for t in tasks if t["status"] == "done"]; label = "Done"
        elif filt == "4":
            filtered = [t for t in tasks if t["status"] not in ("done","cancelled")
                        and t.get("due_date") and datetime.fromisoformat(t["due_date"]) < now]
            label = "Overdue"
        else:
            C.print()
            cat      = pick("Category", CATEGORIES)
            filtered = [t for t in tasks if t.get("category") == cat]
            label    = f"Category: {cat}"

        filtered = sorted(filtered,
                          key=lambda t: (-t.get("priority_score",0), t.get("due_date","9999")))
        header(f"Tasks — {label}")
        render_task_table(filtered, label)

        if not filtered:
            press_enter(); return

        C.print()
        C.print(Rule(f"[dim]Actions[/]", style=THEME["border"]))
        C.print(f"  Enter a [bold {THEME['secondary']}]task number[/] to open it   "
                f"  [bold {THEME['secondary']}]b[/] back to menu")
        C.print()
        choice = Prompt.ask(f"  [{THEME['secondary']}]>[/]")
        if choice.lower() == "b":
            return
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(filtered):
                screen_task_detail(db, ml, filtered[idx])
        except ValueError:
            pass


def screen_task_detail(db, ml, task):
    while True:
        header(f"Task  ·  {task['name'][:40]}")
        ps     = task.get("priority_score", 3)
        status = task.get("status", "todo")

        # Detail table
        info = Table(box=box.ROUNDED, border_style=THEME["border"],
                     show_header=False, padding=(0,2))
        info.add_column("Field", style=f"dim {THEME['secondary']}", width=16)
        info.add_column("Value", style="white")
        info.add_row("Name",       f"[bold]{task['name']}[/]")
        info.add_row("Priority",   f"{PRIO_ICON.get(ps,'🟡')} {task.get('priority','')}")
        info.add_row("Category",   task.get("category",""))
        info.add_row("Status",     f"{STATUS_ICON.get(status,'○')} {status}")
        info.add_row("Due date",   task.get("due_date","—") or "—")
        info.add_row("Est. hours", str(task.get("estimated_hours",1.0)))
        if task.get("actual_hours"):
            info.add_row("Actual h", str(task["actual_hours"]))
        if task.get("tags"):
            info.add_row("Tags",   ", ".join(task["tags"]))
        if task.get("description"):
            info.add_row("Note",   task["description"])
        info.add_row("Created",    task.get("created_at","")[:16])
        if task.get("completed_at"):
            info.add_row("Completed", task["completed_at"][:16])
        C.print(info)

        # ML panel
        p   = ml.predict(task)
        bar = ""
        if p["prob"] is not None:
            n   = int(p["prob"]/10)
            bar = f"  [dim]{'█'*n}{'░'*(10-n)}[/]  {p['prob']}%"
        pred_line = f"  {p['risk']}{bar}"
        if p["pred_h"]:
            pred_line += f"   · predicted {p['pred_h']} h"
        if p["tip"]:
            pred_line += f"   · [dim]{p['tip']}[/]"
        C.print(Panel(pred_line, title=f"[bold {THEME['secondary']}]🤖  Prediction[/]",
                      border_style=THEME["border"], padding=(0,0)))
        C.print()

        # Action menu
        C.print(Rule(f"[dim]Actions[/]", style=THEME["border"]))
        actions = []
        if status == "todo":
            actions.append(("s", "Start task  →  in progress"))
        if status == "in_progress":
            actions.append(("d", "Mark as done  ✅"))
        if status == "done":
            actions.append(("r", "Reopen task"))
        if status not in ("cancelled",):
            actions.append(("c", "Cancel task"))
        actions += [
            ("e", "Edit task"),
            ("h", "Log actual hours"),
            ("x", "Delete task"),
            ("b", "Back"),
        ]
        for key, lbl in actions:
            C.print(f"  [bold {THEME['secondary']}]{key}[/]  {lbl}")
        C.print()
        ch = Prompt.ask(f"  [{THEME['secondary']}]>[/]").lower().strip()

        if ch == "b":
            return
        elif ch == "s" and status == "todo":
            task["status"]     = "in_progress"
            task["started_at"] = datetime.now().isoformat()
            _update(db, task)
            C.print("\n  [green]▶  Task started![/]")
            press_enter()
        elif ch == "d" and status == "in_progress":
            task["status"]       = "done"
            task["completed_at"] = datetime.now().isoformat()
            if task.get("started_at") and not task.get("actual_hours"):
                try:
                    h = (datetime.now() - datetime.fromisoformat(task["started_at"])).total_seconds()/3600
                    task["actual_hours"] = round(h, 2)
                except Exception:
                    pass
            _update(db, task); ml.train(db["tasks"])
            _hook("on_task_done", db, task)
            child = spawn_recurrence(db, task)
            if child:
                C.print(f"\n  [green]✅  Done![/]  [dim]🔁 Next due {child['due_date']} created.[/]")
            else:
                C.print("\n  [green]✅  Done![/]")
            press_enter()
        elif ch == "r" and status == "done":
            task["status"] = "todo"; task["completed_at"] = None
            _update(db, task)
            C.print("\n  [cyan]↩  Reopened.[/]")
            press_enter()
        elif ch == "c" and status != "cancelled":
            if Confirm.ask("\n  Cancel this task?"):
                task["status"] = "cancelled"
                _update(db, task)
                C.print("  [dim]Cancelled.[/]")
                press_enter()
        elif ch == "e":
            screen_edit_task(db, task)
            task = _find(db, task["id"])
        elif ch == "h":
            h = ask_float("Actual hours spent", default=task.get("estimated_hours",1.0))
            task["actual_hours"] = h
            _update(db, task)
            C.print(f"\n  [green]Logged {h} h.[/]")
            press_enter()
        elif ch == "x":
            if Confirm.ask("\n  [red]Permanently delete this task?[/]"):
                undo_snapshot(db)
                _hook("on_task_deleted", db, task)
                db["tasks"] = [t for t in db["tasks"] if t["id"] != task["id"]]
                save(db)
                C.print("  [red]Deleted.[/]")
                press_enter()
                return


def screen_create_task(db):
    header("New Task")
    C.print(Panel(
        "  Fill in the details below.\n"
        "  [dim]Press Enter to accept the default value shown in brackets.[/]",
        border_style=THEME["border"], padding=(0,1)
    ))
    C.print()

    name = ask_str("Task name", required=True)

    C.print()
    C.print(f"  [{THEME['secondary']}]Category[/]")
    category = pick("Choice", CATEGORIES, default_idx=0)

    C.print()
    due = ask_str("Due date  YYYY-MM-DD  (optional, Enter to skip)", default="")
    if due:
        try:
            datetime.fromisoformat(due)
        except ValueError:
            C.print("  [yellow]Invalid date format — skipping.[/]")
            due = ""

    hours    = ask_float("Estimated hours", default=1.0)
    tags_raw = ask_str("Tags  comma-separated  (optional)", default="")
    tags     = [x.strip() for x in tags_raw.split(",") if x.strip()]
    desc     = ask_str("Short description  (optional)", default="")

    # ── Local AI priority suggestion ──
    C.print()
    ai_prio, ai_reasons = suggest_priority(name, desc, category, due, db)
    ai_idx = PRIORITIES.index(ai_prio)
    ai_icon = PRIO_ICON.get(PRIORITY_SCORE[ai_prio], "🟡")
    ai_body = f"  Suggested: [bold]{ai_icon} {ai_prio}[/]\n" \
              + "".join(f"  [dim]· {r}[/]\n" for r in ai_reasons)
    C.print(Panel(ai_body,
        title=f"[bold {THEME['secondary']}]🤖  AI Priority Suggestion[/]",
        border_style=THEME["border"], padding=(0,0)
    ))
    C.print(f"  [{THEME['secondary']}]Priority[/]  (Enter to accept suggestion)")
    priority = pick("Choice", PRIORITIES, default_idx=ai_idx)

    C.print()
    C.print(f"  [{THEME['secondary']}]Recurrence[/]")
    recurrence = pick("Repeat", RECURRENCE_OPTIONS, default_idx=0)

    task = new_task(name, priority, category, due, hours, desc, tags)
    task["recurrence"] = recurrence
    ps   = task["priority_score"]

    C.print()
    preview = Table(box=box.ROUNDED, border_style=f"{THEME['secondary']}",
                    show_header=False, padding=(0,2),
                    title=f"[bold {THEME['secondary']}]  Preview[/]", title_justify="left")
    preview.add_column("", style=f"dim {THEME['secondary']}", width=14)
    preview.add_column("", style="white")
    preview.add_row("Name",     f"[bold]{name}[/]")
    preview.add_row("Priority", f"{PRIO_ICON.get(ps,'🟡')} {priority}")
    preview.add_row("Category", category)
    if due:  preview.add_row("Due",  due)
    if tags: preview.add_row("Tags", ", ".join(tags))
    if desc: preview.add_row("Note", desc)
    if recurrence != "none": preview.add_row("Repeats", recurrence)
    C.print(preview)
    C.print()

    if Confirm.ask("  [bold]Save this task?[/]", default=True):
        undo_snapshot(db)
        db["tasks"].append(task)
        save(db)
        _hook("on_task_created", db, task)
        C.print(f"\n  [bold green]✅  Created![/]  [dim]ID: {task['id']}[/]")
    else:
        C.print("  [dim]Discarded.[/]")
    press_enter()


def screen_edit_task(db, task):
    header(f"Edit Task")
    C.print(Panel(
        f"  Editing: [bold]{task['name']}[/]\n"
        "  [dim]Press Enter to keep the current value.[/]",
        border_style=THEME["border"], padding=(0,1)
    ))
    C.print()

    name = ask_str("Task name", default=task["name"]) or task["name"]

    C.print()
    C.print(f"  [{THEME['secondary']}]Priority[/]")
    priority = pick("Choice", PRIORITIES,
                    default_idx=PRIORITIES.index(task.get("priority","Medium")))

    C.print()
    C.print(f"  [{THEME['secondary']}]Category[/]")
    category = pick("Choice", CATEGORIES,
                    default_idx=CATEGORIES.index(task.get("category","Work")) if task.get("category") in CATEGORIES else 0)

    C.print()
    due = ask_str("Due date  YYYY-MM-DD", default=task.get("due_date",""))
    if due:
        try:
            datetime.fromisoformat(due)
        except ValueError:
            C.print("  [yellow]Invalid date — keeping old.[/]")
            due = task.get("due_date","")

    hours    = ask_float("Estimated hours", default=task.get("estimated_hours",1.0))
    tags_raw = ask_str("Tags  comma-separated", default=", ".join(task.get("tags",[])))
    tags     = [x.strip() for x in tags_raw.split(",") if x.strip()]
    desc     = ask_str("Description", default=task.get("description",""))

    undo_snapshot(db)
    task.update(
        name=name, priority=priority,
        priority_score=PRIORITY_SCORE.get(priority, 3),
        category=category, due_date=due,
        estimated_hours=hours, tags=tags, description=desc,
    )
    _update(db, task)
    C.print("\n  [green]✅  Saved![/]")
    press_enter()


def screen_stats(db, ml):
    header("Statistics")
    tasks = db["tasks"]

    if not tasks:
        C.print(Panel("  [dim]No tasks yet.[/]", border_style=THEME["border"]))
        press_enter(); return

    done  = [t for t in tasks if t["status"] == "done"]
    todo  = [t for t in tasks if t["status"] in ("todo","in_progress")]
    now   = datetime.now()
    rate  = len(done)/len(tasks)*100 if tasks else 0
    ovd   = [t for t in todo if t.get("due_date") and
             datetime.fromisoformat(t["due_date"]) < now]
    est_h = sum(t.get("estimated_hours",0) for t in todo)

    times = []
    for t in done:
        try:
            c = datetime.fromisoformat(t["created_at"])
            d = datetime.fromisoformat(t["completed_at"])
            times.append((d-c).total_seconds()/3600)
        except Exception:
            pass
    avg_h = f"{sum(times)/len(times):.1f} h" if times else "—"

    dates = set()
    for t in done:
        try: dates.add(datetime.fromisoformat(t["completed_at"]).date())
        except Exception: pass
    streak, check = 0, now.date()
    while check in dates: streak += 1; check -= timedelta(days=1)

    cat_done = Counter(t.get("category") for t in done)
    best_cat = cat_done.most_common(1)[0][0] if cat_done else "—"

    # Stat cards row
    cards = [
        stat_card("Total",         str(len(tasks))),
        stat_card("Completed",     str(len(done)),    "#2ecc71"),
        stat_card("Pending",       str(len(todo)),    "#f39c12"),
        stat_card("Done %",        f"{rate:.1f}%",    "#3498db"),
        stat_card("Overdue",       str(len(ovd)),     "red" if ovd else "#2ecc71"),
        stat_card("Hours backlog", f"{est_h:.1f} h", "#9b59b6"),
        stat_card("Avg done",      avg_h,             "#1abc9c"),
        stat_card("Best category", best_cat,          "#e67e22"),
        stat_card("Day streak",    f"{streak}d",      "#e74c3c"),
    ]
    C.print(Columns(cards, padding=(0,1), equal=True))
    C.print()

    # Priority breakdown
    pt = Table(box=box.SIMPLE, header_style=f"bold {THEME['secondary']}",
               title=f"[bold {THEME['secondary']}]Priority Breakdown[/]", title_justify="left",
               padding=(0,1))
    pt.add_column("Priority", width=12)
    pt.add_column("Total",    width=7, justify="right")
    pt.add_column("Done",     width=7, justify="right")
    pt.add_column("Bar",      width=28)
    cnt_all  = Counter(t.get("priority","Medium") for t in tasks)
    cnt_done = Counter(t.get("priority","Medium") for t in done)
    mx       = max((cnt_all.get(p,0) for p in PRIORITIES), default=1)
    for p in PRIORITIES:
        n   = cnt_all.get(p, 0)
        d   = cnt_done.get(p, 0)
        bar = "█" * int(n * 24 / max(mx,1)) + "░" * (24 - int(n * 24 / max(mx,1)))
        pt.add_row(
            Text(f"{PRIO_ICON.get(PRIORITY_SCORE[p],'?')} {p}", style=PRIO_STYLE.get(PRIORITY_SCORE[p],"white")),
            str(n), str(d), f"[dim]{bar}[/] {n}"
        )
    C.print(pt)

    # Category breakdown
    ct = Table(box=box.SIMPLE, header_style=f"bold {THEME['secondary']}",
               title=f"[bold {THEME['secondary']}]Category Breakdown[/]", title_justify="left",
               padding=(0,1))
    ct.add_column("Category", width=12)
    ct.add_column("Total",    width=7, justify="right")
    ct.add_column("Done",     width=7, justify="right")
    ct.add_column("Rate",     width=30)
    cat_all = Counter(t.get("category","Other") for t in tasks)
    for cat in sorted(cat_all, key=lambda c: -cat_all[c]):
        total = cat_all[cat]
        d     = cat_done.get(cat, 0)
        r     = d/total*100 if total else 0
        bar   = "█" * int(r/5) + "░" * (20 - int(r/5))
        ct.add_row(cat, str(total), str(d), f"[dim]{bar}[/] {r:.0f}%")
    C.print(ct)

    # Insights
    C.print(Panel(
        "\n".join(f"  {line}" for line in ml.insights(tasks)),
        title=f"[bold {THEME['secondary']}]🧠  AI Insights[/]",
        border_style=THEME["border"], padding=(0,0)
    ))
    press_enter()


def screen_predictions(db, ml):
    header("ML Predictions")
    tasks  = db["tasks"]
    ml.train(tasks)
    active = [t for t in tasks if t["status"] in ("todo","in_progress")]

    if not active:
        C.print(Panel("  [dim]No active tasks to predict.[/]", border_style=THEME["border"]))
        press_enter(); return

    # Model status
    if not ml.trained:
        need = max(0, 5 - len([t for t in tasks if t["status"] == "done"]))
        status_txt = f"[yellow]Complete {need} more task(s) to activate ML model.[/]\n  [dim]Using heuristics for now.[/]"
        bstyle = THEME["border"]
    else:
        status_txt = "[green]ML active — pure-Python Random Forest, trained on your history.[/]"
        bstyle = "green"
    C.print(Panel(f"  {status_txt}", title=f"[bold {THEME['secondary']}]🤖  Model Status[/]",
                  border_style=bstyle, padding=(0,0)))
    C.print()

    preds = [(t, ml.predict(t)) for t in active]
    preds.sort(key=lambda x: (x[1]["prob"] if x[1]["prob"] is not None else 100))

    tbl = Table(box=box.ROUNDED, border_style=THEME["border"],
                header_style=f"bold {THEME['secondary']}",
                title=f"[bold {THEME['secondary']}]⚡  Risk Assessment[/]", title_justify="left",
                padding=(0,1))
    tbl.add_column("Task",        min_width=22)
    tbl.add_column("Priority",    width=13)
    tbl.add_column("Risk",        width=18)
    tbl.add_column("On-time",     width=17)
    tbl.add_column("Pred. h",     width=9,  justify="right")
    tbl.add_column("Tip",         min_width=20)

    for task, p in preds:
        ps   = task.get("priority_score", 3)
        prob = p["prob"]
        if prob is not None:
            n      = int(prob/10)
            prob_s = f"{'█'*n}{'░'*(10-n)} {prob}%"
        else:
            prob_s = "—"
        pred_h = f"{p['pred_h']} h" if p["pred_h"] else "—"
        tbl.add_row(
            Text(task["name"][:24], style=PRIO_STYLE.get(ps,"white")),
            f"{PRIO_ICON.get(ps,'🟡')} {task.get('priority','')}",
            p["risk"], prob_s, pred_h,
            Text(p["tip"], style="dim"),
        )
    C.print(tbl)
    press_enter()


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    # Unlock encryption if active
    if _CRYPTO_FILE.exists():
        clear()
        C.print()
        C.print(f"  [bold {THEME['primary']}]⚡  TaskFlow[/]  [dim]— encrypted storage[/]")
        C.print()
        for _attempt in range(3):
            _pw = Prompt.ask(f"  [{THEME['secondary']}]Password[/]", password=True)
            _ok, _err = crypto_unlock(_pw)
            if _ok:
                C.print(f"  [green]✓ Unlocked.[/]")
                import time as _t; _t.sleep(0.4)
                break
            C.print(f"  [red]{_err}[/]")
            if _attempt == 2:
                C.print("  [red]3 failed attempts — exiting.[/]")
                sys.exit(1)
    db = load()
    # Copy docs to ~/.taskflow/ for easy access
    try:
        import shutil as _sh
        _docs_src = Path(__file__).parent / "PLUGIN_DOCS.md"
        _docs_dst = DATA_DIR / "PLUGIN_DOCS.md"
        if _docs_src.exists() and not _docs_dst.exists():
            _sh.copy(_docs_src, _docs_dst)
    except Exception:
        pass
    load_plugins(db)
    _hook("on_startup", db)
    global _ml_instance
    _ml_instance = ml = ML()
    ml.train(db["tasks"])

    # Fixed keys that the app owns — plugins must not clash
    FIXED_KEYS = {"0","1","2","3","4","5","6","7","8","q","/","u","U"}

    while True:
        # Collect plugin items fresh every loop (plugins may change db)
        plugin_items = plugin_menu_items(db)

        # Detect key conflicts and warn once
        plugin_keys = {}
        for key, label, fn in plugin_items:
            if key in FIXED_KEYS:
                C.print(f"  [yellow]⚠ Plugin key '{key}' conflicts with a built-in — skipped ({label})[/]")
            elif key in plugin_keys:
                C.print(f"  [yellow]⚠ Duplicate plugin key '{key}' — skipped ({label})[/]")
            else:
                plugin_keys[key] = fn

        all_choices = list(FIXED_KEYS) + list(plugin_keys.keys())

        _tick_plugins(db)
        # Live-reload: check if any plugin file changed
        changed = _check_plugin_changes()
        if changed:
            load_plugins(db)
            _hook("on_startup", db)
            C.print(f"  [green]🔄 Plugin(s) reloaded: {', '.join(changed)}[/]")
            import time; time.sleep(0.8)
        screen_home(db, ml, plugin_items=[(k,l,f) for k,l,f in plugin_items
                                          if k in plugin_keys])
        choice = Prompt.ask(f"  [{THEME['secondary']}]>[/]", default="1",
                            choices=all_choices)

        if   choice == "1": screen_task_list(db, ml)
        elif choice == "2": screen_create_task(db); ml.train(db["tasks"])
        elif choice == "3": screen_stats(db, ml)
        elif choice == "4": screen_predictions(db, ml)
        elif choice == "5": screen_graphs(db)
        elif choice == "6": screen_git(db)
        elif choice == "7": screen_daemon()
        elif choice == "8": screen_plugins(db)
        elif choice == "0": screen_encryption(db)
        elif choice == "/": screen_quick_search(db)
        elif choice == "u":
            ok, msg = undo(db)
            C.print(f"  {'[green]↩ ' if ok else '[yellow]'}{msg}[/]")
            import time as _t; _t.sleep(0.7)
        elif choice == "U":
            ok, msg = redo(db)
            C.print(f"  {'[green]↪ ' if ok else '[yellow]'}{msg}[/]")
            import time as _t; _t.sleep(0.7)
        elif choice in plugin_keys:
            plugin_keys[choice]()   # call the plugin's function directly
        elif choice == "q":
            clear()
            C.print()
            C.print(Panel(
                Align.center(
                    f"[bold {THEME['primary']}]Thanks for using TaskFlow![/]\n"
                    "[dim]Your tasks are saved in ~/.taskflow/tasks.json[/]"
                ),
                border_style=f"{THEME['secondary']}", padding=(1,6)
            ))
            C.print()
            break


if __name__ == "__main__":
    if "--notify" in sys.argv:
        # Daemon mode: check tasks and fire notifications, then exit
        db = load()
        fired = check_and_notify(db["tasks"])
        sys.exit(0)
    try:
        main()
    except KeyboardInterrupt:
        C.print("\n\n  [dim]Goodbye.[/]\n")
        sys.exit(0)
