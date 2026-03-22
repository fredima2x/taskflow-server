"""
TaskFlow Plugin — E-Mail Digest
PLUGIN_NAME    = "Email Digest"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Daily task summary via SMTP (Gmail, Outlook, sendmail)"
PLUGIN_AUTHOR  = "community"
PLUGIN_TAGS    = "email, digest, notifications"
PLUGIN_MIN_API = "3.0"
"""
PLUGIN_NAME    = "Email Digest"
PLUGIN_VERSION = "1.0"
PLUGIN_DESC    = "Daily task summary via SMTP"
PLUGIN_MIN_API = "3.0"

import os, smtplib, ssl
from datetime  import datetime, date, timedelta
from email.mime.text      import MIMEText
from email.mime.multipart import MIMEMultipart


# ── Build HTML email body ─────────────────────────────────────

def _build_html(tasks: list) -> str:
    now   = datetime.now()
    today = date.today().isoformat()

    done_today = [t for t in tasks
                  if t.get("completed_at","")[:10] == today]
    overdue    = [t for t in tasks
                  if t.get("status") in ("todo","in_progress")
                  and t.get("due_date","") and t["due_date"] < today]
    due_today  = [t for t in tasks
                  if t.get("status") in ("todo","in_progress")
                  and t.get("due_date","") == today]
    high       = [t for t in tasks
                  if t.get("status") in ("todo","in_progress")
                  and t.get("priority_score",0) >= 4
                  and t.get("due_date","") > today]

    PRIO_COLOR = {"Critical":"#e74c3c","High":"#e67e22","Medium":"#f1c40f",
                  "Low":"#2ecc71","Minimal":"#95a5a6"}

    def _rows(task_list, limit=10):
        html = ""
        for t in task_list[:limit]:
            clr  = PRIO_COLOR.get(t.get("priority","Medium"),"#aaa")
            due  = t.get("due_date","—") or "—"
            html += f"""
            <tr>
              <td style="padding:6px 12px;border-bottom:1px solid #eee">
                <span style="color:{clr};font-weight:bold">●</span>
                {t['name'][:60]}
              </td>
              <td style="padding:6px 12px;border-bottom:1px solid #eee;color:#888">{t.get('priority','')}</td>
              <td style="padding:6px 12px;border-bottom:1px solid #eee;color:#888">{due}</td>
            </tr>"""
        return html

    total = len(tasks)
    done  = len([t for t in tasks if t.get("status")=="done"])
    rate  = int(done/total*100) if total else 0

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px;color:#222">
<h2 style="color:#00b4d8;border-bottom:2px solid #00b4d8;padding-bottom:8px">
  ⚡ TaskFlow Daily Digest — {today}
</h2>

<div style="display:flex;gap:16px;margin:16px 0">
  <div style="background:#f0f9ff;border-radius:8px;padding:12px 20px;text-align:center">
    <div style="font-size:24px;font-weight:bold;color:#00b4d8">{total}</div>
    <div style="color:#888;font-size:12px">Total</div>
  </div>
  <div style="background:#f0fff4;border-radius:8px;padding:12px 20px;text-align:center">
    <div style="font-size:24px;font-weight:bold;color:#2ecc71">{done}</div>
    <div style="color:#888;font-size:12px">Completed</div>
  </div>
  <div style="background:#fff5f5;border-radius:8px;padding:12px 20px;text-align:center">
    <div style="font-size:24px;font-weight:bold;color:#e74c3c">{len(overdue)}</div>
    <div style="color:#888;font-size:12px">Overdue</div>
  </div>
  <div style="background:#fffbf0;border-radius:8px;padding:12px 20px;text-align:center">
    <div style="font-size:24px;font-weight:bold;color:#f39c12">{rate}%</div>
    <div style="color:#888;font-size:12px">Done rate</div>
  </div>
</div>

{"<h3 style='color:#e74c3c'>⚠️ Overdue</h3><table width='100%'>" + _rows(overdue) + "</table>" if overdue else ""}
{"<h3 style='color:#f39c12'>⏰ Due today</h3><table width='100%'>" + _rows(due_today) + "</table>" if due_today else ""}
{"<h3 style='color:#e67e22'>🔥 High priority upcoming</h3><table width='100%'>" + _rows(high) + "</table>" if high else ""}
{"<h3 style='color:#2ecc71'>✅ Completed today</h3><table width='100%'>" + _rows(done_today) + "</table>" if done_today else ""}

<p style="color:#aaa;font-size:12px;margin-top:32px;border-top:1px solid #eee;padding-top:12px">
  Sent by TaskFlow · {now:%Y-%m-%d %H:%M}
</p>
</body></html>"""


def _send_email(cfg: dict, subject: str, html: str) -> tuple[bool, str]:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = cfg["from_addr"]
    msg["To"]      = cfg["to_addr"]
    msg.attach(MIMEText(html, "html"))

    host = cfg.get("smtp_host","smtp.gmail.com")
    port = int(cfg.get("smtp_port", 587))
    user = cfg.get("smtp_user","")
    pwd  = cfg.get("smtp_pass","")

    try:
        ctx = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ctx) as s:
                if user: s.login(user, pwd)
                s.sendmail(cfg["from_addr"], cfg["to_addr"], msg.as_string())
        else:
            with smtplib.SMTP(host, port) as s:
                s.ehlo(); s.starttls(context=ctx); s.ehlo()
                if user: s.login(user, pwd)
                s.sendmail(cfg["from_addr"], cfg["to_addr"], msg.as_string())
        return True, "OK"
    except Exception as e:
        return False, str(e)


def _screen(api):
    console = api.console
    store   = api.store
    cfg     = api.config

    while True:
        os.system("clear")
        console.print("\n  [bold]⚡ TaskFlow  ·  📧 Email Digest[/]\n")

        configured = all(cfg.get(k) for k in ("smtp_host","from_addr","to_addr"))
        console.print(api.panel(
            f"  Status:      {'[green]configured[/]' if configured else '[yellow]not configured[/]'}\n"
            f"  To:          [dim]{cfg.get('to_addr','—')}[/]\n"
            f"  SMTP:        [dim]{cfg.get('smtp_host','—')}:{cfg.get('smtp_port',587)}[/]\n"
            f"  Auto-send:   [dim]{store.get('schedule','disabled')}[/]",
            title="Email Digest"
        ) or "")
        # use api.panel directly
        from rich.panel import Panel
        console.print(Panel(
            f"  Status:      {'[green]configured[/]' if configured else '[yellow]not configured[/]'}\n"
            f"  To:          [dim]{cfg.get('to_addr','—')}[/]\n"
            f"  SMTP:        [dim]{cfg.get('smtp_host','—')}:{cfg.get('smtp_port',587)}[/]\n"
            f"  Auto-send:   [dim]{store.get('schedule','off')}[/]",
            border_style="#1a2a44", padding=(0,1)
        ))
        console.print()
        console.print("  [bold]s[/]  SMTP settings")
        if configured:
            console.print("  [bold]t[/]  Send test digest now")
            console.print("  [bold]a[/]  Toggle auto-send (daily)")
        console.print("  [bold]b[/]  Back\n")

        ch = api.prompt(">").lower()
        if ch == "b": return

        elif ch == "s":
            os.system("clear")
            console.print("\n  [bold]SMTP Configuration[/]\n")
            console.print("  [dim]Gmail: host=smtp.gmail.com port=587, use App Password[/]\n")
            cfg["smtp_host"]  = api.prompt("SMTP host",  default=cfg.get("smtp_host","smtp.gmail.com"))
            cfg["smtp_port"]  = api.prompt("SMTP port",  default=str(cfg.get("smtp_port",587)))
            cfg["smtp_user"]  = api.prompt("SMTP user",  default=cfg.get("smtp_user",""))
            cfg["smtp_pass"]  = api.prompt("SMTP password (App Password)", password=True)
            cfg["from_addr"]  = api.prompt("From address",default=cfg.get("from_addr",""))
            cfg["to_addr"]    = api.prompt("To address",  default=cfg.get("to_addr",""))
            api.config_save()
            console.print("  [green]✓ Saved.[/]"); api.press_enter()

        elif ch == "t" and configured:
            console.print("  [dim]Sending…[/]")
            html = _build_html(api.tasks)
            ok, err = _send_email(cfg, f"TaskFlow Digest — {date.today()}", html)
            console.print(f"  {'[green]✓ Sent![/]' if ok else f'[red]Failed: {err}[/]'}")
            api.press_enter()

        elif ch == "a" and configured:
            store["schedule"] = "off" if store.get("schedule") == "daily" else "daily"
            api.store_save()
            console.print(f"  [green]✓ Auto-send: {store['schedule']}[/]"); api.press_enter()


def install(api):
    api.config.setdefault("smtp_host", "smtp.gmail.com")
    api.config.setdefault("smtp_port", 587)
    api.config_save()


def on_startup(api):
    store = api.store
    cfg   = api.config
    if store.get("schedule") != "daily": return
    if not all(cfg.get(k) for k in ("smtp_host","from_addr","to_addr")): return

    today = date.today().isoformat()
    if store.get("last_sent") == today: return

    html = _build_html(api.tasks)
    ok, _ = _send_email(cfg, f"TaskFlow Digest — {today}", html)
    if ok:
        store["last_sent"] = today
        api.store_save()
        api.log("Daily digest sent")


def menu_items(api):
    return [("E", "📧 Email Digest", lambda: _screen(api))]
