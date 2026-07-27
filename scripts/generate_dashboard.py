#!/usr/bin/env python3
"""Rusemeva Dashboard v4 — Ultimate with all features."""
import json
import os
import subprocess
from datetime import datetime, timezone, timedelta
from collections import defaultdict

WIB = timezone(timedelta(hours=7))
REPO = "daudjoss/daudjoss-vault"

def run_gh(args):
    try:
        env = os.environ.copy()
        result = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=30, env=env)
        return result.stdout.strip()
    except:
        return ""

def fetch_runs(limit=100):
    raw = run_gh(["run", "list", "--repo", REPO, "--limit", str(limit),
                   "--json", "databaseId,name,status,conclusion,createdAt,event,updatedAt"])
    return json.loads(raw) if raw else []

def fetch_releases(limit=30):
    raw = run_gh(["api", f"repos/{REPO}/releases",
                   "--jq", f"[.[:{limit}][:][] | {{tag: .tag_name, name: .name, created: .created_at, size: ([.assets[].size] | add // 0), assets: [.assets[] | {{name: .name, size: .size, url: .browser_download_url}}]}}]"])
    return json.loads(raw) if raw else []

def calc_stats(runs):
    vault = [r for r in runs if r.get("name") == "rusemeva-vault"]
    encode = [r for r in runs if r.get("name") == "rusemeva-encode"]
    total = len(vault)
    success = len([r for r in vault if r.get("conclusion") == "success"])
    failed = len([r for r in vault if r.get("conclusion") == "failure"])
    running = len([r for r in vault if r.get("status") == "in_progress"])
    rate = (success / total * 100) if total > 0 else 0
    enc_total = len(encode)
    enc_success = len([r for r in encode if r.get("conclusion") == "success"])
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    today_runs = [r for r in vault if r.get("createdAt", "").startswith(today)]
    daily = defaultdict(int)
    for r in vault:
        try:
            dt = datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
            daily[dt.strftime("%Y-%m-%d")] += 1
        except: pass
    weekly = defaultdict(lambda: {"s": 0, "f": 0})
    for r in vault:
        try:
            dt = datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
            w = dt.strftime("%Y-W%W")
            if r.get("conclusion") == "success": weekly[w]["s"] += 1
            elif r.get("conclusion") == "failure": weekly[w]["f"] += 1
        except: pass
    errors = [{"id": r.get("databaseId"), "time": r.get("createdAt", "")[:16]} for r in vault[:20] if r.get("conclusion") == "failure"][:5]
    return {
        "total": total, "success": success, "failed": failed, "running": running,
        "rate": round(rate, 1), "enc_total": enc_total, "enc_success": enc_success,
        "enc_rate": round((enc_success / enc_total * 100) if enc_total > 0 else 0, 1),
        "today": len(today_runs), "today_ok": len([r for r in today_runs if r.get("conclusion") == "success"]),
        "daily": dict(sorted(daily.items())[-35:]), "weekly": dict(sorted(weekly.items())[-12:]),
        "errors": errors, "latest_run": vault[0] if vault else None,
    }

def ago(s):
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        d = int((datetime.now(timezone.utc) - dt).total_seconds())
        if d < 60: return "baru saja"
        if d < 3600: return f"{d//60}m"
        if d < 86400: return f"{d//3600}j"
        return f"{d//86400}h"
    except: return s[:10]

def icon(c):
    return {"success": "✅", "failure": "❌", "cancelled": "⚪"}.get(c, "🔄")

def cls(c):
    return {"success": "success", "failure": "failure", "cancelled": "cancelled"}.get(c, "running")

def gen_html(stats, runs, releases):
    now = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")
    dl = json.dumps(list(stats["daily"].keys()))
    dd = json.dumps(list(stats["daily"].values()))
    wl = json.dumps(list(stats["weekly"].keys()))
    ws = json.dumps([v["s"] for v in stats["weekly"].values()])
    wf = json.dumps([v["f"] for v in stats["weekly"].values()])

    # Tables
    vr = [r for r in runs if r.get("name") == "rusemeva-vault"][:25]
    er = [r for r in runs if r.get("name") == "rusemeva-encode"][:20]
    rh = ""
    for r in vr:
        i = icon(r.get("conclusion","")); a = ago(r.get("createdAt","")); rid = r.get("databaseId","")
        s = r.get("conclusion", r.get("status","?")); c = cls(s)
        rh += f'<tr class="row-{c}" data-status="{s}" data-search="{rid}"><td>{i}</td><td><code>{rid}</code></td><td>{a}</td><td><span class="badge badge-{c}">{s}</span></td><td><a href="https://github.com/{REPO}/actions/runs/{rid}" target="_blank">↗</a></td></tr>'
    eh = ""
    for r in er:
        i = icon(r.get("conclusion","")); a = ago(r.get("createdAt","")); rid = r.get("databaseId","")
        s = r.get("conclusion", r.get("status","?")); c = cls(s)
        eh += f'<tr><td>{i}</td><td><code>{rid}</code></td><td>{a}</td><td><span class="badge badge-{c}">{s}</span></td><td><a href="https://github.com/{REPO}/actions/runs/{rid}" target="_blank">↗</a></td></tr>'
    rlh = ""
    for r in releases[:15]:
        sz = r.get("size",0)/1024/1024; a = ago(r.get("created",""))
        assets = ", ".join([x["name"] for x in r.get("assets",[])[:3]])
        rlh += f'<tr><td><code>{r.get("tag","")}</code></td><td>{sz:.1f} MB</td><td>{a}</td><td style="font-size:12px;color:var(--text-secondary)">{assets[:40]}</td></tr>'

    # Calendar
    cal = ""
    today = datetime.now(WIB).date()
    for d in range(34, -1, -1):
        day = today - timedelta(days=d)
        ds = day.strftime("%Y-%m-%d")
        cnt = stats["daily"].get(ds, 0)
        it = min(cnt, 5)
        cal += f'<div class="cal cal-{it}" title="{ds}: {cnt}">{day.day}</div>'

    # Errors
    if stats["errors"]:
        eh2 = "".join([f'<div class="err"><div class="err-icon">❌</div><div><div class="err-id">Run <code>{e["id"]}</code></div><div class="err-time">{e["time"]}</div></div><a href="https://github.com/{REPO}/actions/runs/{e["id"]}" target="_blank">Log ↗</a></div>' for e in stats["errors"]])
    else:
        eh2 = '<div class="no-err">✅ Tidak ada error</div>'

    # Storage estimate (from releases)
    total_size = sum([r.get("size",0) for r in releases]) / 1024 / 1024 / 1024
    releases_json = json.dumps([{"tag": r.get("tag",""), "size": r.get("size",0), "created": r.get("created","")} for r in releases])

    return f'''<!DOCTYPE html>
<html lang="id" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="Rusemeva Vault Dashboard">
<meta name="theme-color" content="#0d1117">
<link rel="manifest" href="manifest.json">
<title>Rusemeva Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{{--bg:#0d1117;--bg2:#161b22;--bg3:#21262d;--brd:#30363d;--t1:#e6edf3;--t2:#8b949e;--t3:#484f58;--bl:#58a6ff;--gn:#3fb950;--rd:#f85149;--yl:#d29922;--pr:#bc8cff;--or:#f0883e}}
[data-theme="light"]{{--bg:#f6f8fa;--bg2:#fff;--bg3:#f0f2f5;--brd:#d0d7de;--t1:#1f2328;--t2:#656d76;--t3:#8b949e}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--t1);padding:16px;min-height:100vh;transition:all .3s}}
.ct{{max-width:1440px;margin:0 auto}}
.hdr{{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;padding-bottom:14px;border-bottom:1px solid var(--brd);flex-wrap:wrap;gap:10px}}
.hdr h1{{font-size:24px;font-weight:600;display:flex;align-items:center;gap:10px}}
.hdr-act{{display:flex;align-items:center;gap:10px}}
.dot{{width:8px;height:8px;background:var(--gn);border-radius:50%;animation:pulse 2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.5}}}}
.btn{{padding:6px 12px;border-radius:8px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);cursor:pointer;font-size:13px;transition:all .2s}}
.btn:hover{{border-color:var(--bl)}}
.sg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px}}
.sc{{background:var(--bg2);border:1px solid var(--brd);border-radius:12px;padding:16px;position:relative;overflow:hidden;cursor:pointer;transition:transform .2s,box-shadow .2s}}
.sc:hover{{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,.2)}}
.sc::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px}}
.sc.bl::before{{background:var(--bl)}}.sc.gn::before{{background:var(--gn)}}.sc.rd::before{{background:var(--rd)}}
.sc.yl::before{{background:var(--yl)}}.sc.pr::before{{background:var(--pr)}}.sc.or::before{{background:var(--or)}}
.si{{font-size:20px;margin-bottom:6px}}.sv{{font-size:32px;font-weight:700}}.sl{{font-size:12px;color:var(--t2);text-transform:uppercase;letter-spacing:.5px}}
.sc.bl .sv{{color:var(--bl)}}.sc.gn .sv{{color:var(--gn)}}.sc.rd .sv{{color:var(--rd)}}
.sc.yl .sv{{color:var(--yl)}}.sc.pr .sv{{color:var(--pr)}}.sc.or .sv{{color:var(--or)}}
.sec{{background:var(--bg2);border:1px solid var(--brd);border-radius:12px;padding:16px;margin-bottom:20px}}
.sh{{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid var(--brd);flex-wrap:wrap;gap:10px}}
.st{{font-size:15px;font-weight:600;display:flex;align-items:center;gap:8px}}
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}}
.g3{{display:grid;grid-template-columns:2fr 1fr;gap:20px;margin-bottom:20px}}
.fl{{display:flex;gap:6px;flex-wrap:wrap;align-items:center}}
.fb{{padding:5px 12px;border-radius:16px;border:1px solid var(--brd);background:transparent;color:var(--t2);cursor:pointer;font-size:12px;transition:all .2s}}
.fb:hover,.fb.on{{background:var(--bl);color:#fff;border-color:var(--bl)}}
.si2{{padding:7px 12px;border-radius:8px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);font-size:13px;width:160px}}
.si2:focus{{outline:none;border-color:var(--bl)}}
table{{width:100%;border-collapse:collapse}}
th,td{{padding:8px 12px;text-align:left;border-bottom:1px solid var(--brd)}}
th{{color:var(--t2);font-size:11px;text-transform:uppercase;letter-spacing:.5px;font-weight:600}}
td{{font-size:13px}}tr:hover{{background:rgba(88,166,255,.04)}}
code{{background:var(--bg3);padding:2px 6px;border-radius:4px;font-size:11px;font-family:'SF Mono',monospace}}
a{{color:var(--bl);text-decoration:none}}a:hover{{text-decoration:underline}}
.bd{{padding:3px 10px;border-radius:12px;font-size:11px;font-weight:500}}
.bd-success{{background:rgba(63,185,80,.15);color:var(--gn)}}
.bd-failure{{background:rgba(248,81,73,.15);color:var(--rd)}}
.bd-cancelled{{background:rgba(139,148,158,.15);color:var(--t2)}}
.bd-running{{background:rgba(88,166,255,.15);color:var(--bl)}}
.cal{{aspect-ratio:1;border-radius:3px;display:flex;align-items:center;justify-content:center;font-size:9px;color:var(--t3);cursor:default}}
.c0{{background:var(--bg3)}}.c1{{background:rgba(63,185,80,.3)}}.c2{{background:rgba(63,185,80,.5)}}
.c3{{background:rgba(63,185,80,.7)}}.c4{{background:rgba(63,185,80,.85)}}.c5{{background:var(--gn);color:#fff}}
.ch{{position:relative;height:220px}}
.err{{display:flex;align-items:center;gap:10px;padding:10px;background:rgba(248,81,73,.05);border:1px solid rgba(248,81,73,.2);border-radius:8px;margin-bottom:6px}}
.err-icon{{font-size:18px}}.err-id{{font-size:13px;font-weight:500}}.err-time{{font-size:11px;color:var(--t2)}}
.no-err{{text-align:center;padding:16px;color:var(--t2)}}
.hg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}}
.hi{{display:flex;align-items:center;gap:10px;padding:10px;background:var(--bg3);border-radius:8px}}
.hd{{width:8px;height:8px;border-radius:50%}}.hd.g{{background:var(--gn)}}.hd.y{{background:var(--yl)}}.hd.r{{background:var(--rd)}}
.hl{{font-size:13px}}.hs{{font-size:11px;color:var(--t2)}}
.pg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px}}
.pi{{text-align:center}}.pv{{font-size:24px;font-weight:700;color:var(--bl)}}.pl{{font-size:11px;color:var(--t2);margin-top:2px}}
.pt{{font-size:11px;margin-top:2px}}.pt.up{{color:var(--gn)}}.pt.dn{{color:var(--rd)}}.pt.st{{color:var(--t3)}}
.ag{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px}}
.ab{{padding:10px 14px;border-radius:8px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);cursor:pointer;font-size:13px;text-align:center;transition:all .2s;text-decoration:none;display:block}}
.ab:hover{{border-color:var(--bl);background:rgba(88,166,255,.1)}}
.mo{{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.7);z-index:1000;align-items:center;justify-content:center}}
.mo.on{{display:flex}}
.md{{background:var(--bg2);border:1px solid var(--brd);border-radius:14px;padding:20px;max-width:500px;width:90%;max-height:80vh;overflow-y:auto}}
.mh{{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}}
.mc{{background:none;border:none;color:var(--t2);font-size:22px;cursor:pointer}}
.sh2{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:6px}}
.sk{{display:flex;align-items:center;gap:6px;padding:6px}}
.ky{{padding:3px 7px;background:var(--bg3);border:1px solid var(--brd);border-radius:4px;font-family:monospace;font-size:11px}}
.ft{{text-align:center;color:var(--t3);font-size:12px;margin-top:30px;padding-top:16px;border-top:1px solid var(--brd)}}
.ft a{{color:var(--t2)}}
@media(max-width:1024px){{.g2,.g3{{grid-template-columns:1fr}}}}
@media(max-width:768px){{.sg{{grid-template-columns:repeat(2,1fr)}}.hdr{{flex-direction:column;align-items:flex-start}}.si2{{width:100%}}}}
.sc,.sec{{animation:fi .3s ease-in}}
@keyframes fi{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:translateY(0)}}}}
.hid{{display:none!important}}
.ot{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin-top:10px}}
.oi{{background:var(--bg3);padding:8px;border-radius:6px;text-align:center;cursor:pointer;transition:all .2s}}
.oi:hover{{background:rgba(88,166,255,.15)}}.oi.sel{{border:2px solid var(--bl)}}
.oi-img{{width:100%;height:60px;background:var(--bg2);border-radius:4px;margin-bottom:4px;display:flex;align-items:center;justify-content:center;font-size:20px}}
.oi-txt{{font-size:10px;color:var(--t2)}}
.tag{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;background:var(--bg3);border:1px solid var(--brd);margin:2px}}
.tag-add{{cursor:pointer;color:var(--bl)}}
.note{{padding:8px;background:var(--bg3);border-radius:6px;font-size:12px;margin-top:6px;min-height:40px}}
.note-edit{{width:100%;background:var(--bg);border:1px solid var(--brd);border-radius:4px;color:var(--t1);padding:6px;font-size:12px;resize:vertical;min-height:60px}}
.lang-btn{{padding:4px 8px;border-radius:4px;border:1px solid var(--brd);background:transparent;color:var(--t2);cursor:pointer;font-size:11px}}
.lang-btn.on{{background:var(--bl);color:#fff;border-color:var(--bl)}}
</style>
</head>
<body>
<div class="ct">
<!-- Header -->
<div class="hdr">
<h1>🎬 Rusemeva</h1>
<div class="hdr-act">
<div class="dot"></div>
<span style="font-size:12px;color:var(--t2)" id="timer">30s</span>
<div class="fl">
<button class="lang-btn on" onclick="setLang('id')">🇮🇩</button>
<button class="lang-btn" onclick="setLang('en')">🇺🇸</button>
</div>
<button class="btn" onclick="toggleTheme()" title="Toggle theme">🌓</button>
<button class="btn" onclick="location.reload()" title="Refresh">🔄</button>
</div>
</div>

<!-- Health -->
<div class="sec" style="margin-bottom:20px">
<div class="sh"><div class="st">🏥 <span data-i18n="health">System Health</span></div><span style="font-size:11px;color:var(--t2)">{now}</span></div>
<div class="hg">
<div class="hi"><div class="hd g"></div><div><div class="hl">Worker</div><div class="hs">rusemeva-vault</div></div></div>
<div class="hi"><div class="hd g"></div><div><div class="hl">GitHub Actions</div><div class="hs">20 slots</div></div></div>
<div class="hi"><div class="hd g"></div><div><div class="hl">Telegram</div><div class="hs">@daudtrans_bot</div></div></div>
<div class="hi"><div class="hd g"></div><div><div class="hl">Dashboard</div><div class="hs">gh-pages</div></div></div>
</div>
</div>

<!-- Stats -->
<div class="sg">
<div class="sc bl"><div class="si">📹</div><div class="sv">{stats['total']}</div><div class="sl" data-i18n="total">Total</div></div>
<div class="sc gn"><div class="si">✅</div><div class="sv">{stats['success']}</div><div class="sl" data-i18n="success">Success</div></div>
<div class="sc rd"><div class="si">❌</div><div class="sv">{stats['failed']}</div><div class="sl" data-i18n="failed">Failed</div></div>
<div class="sc yl"><div class="si">📊</div><div class="sv">{stats['rate']}%</div><div class="sl">Rate</div></div>
<div class="sc pr"><div class="si">🎞</div><div class="sv">{stats['enc_total']}</div><div class="sl">Encode</div></div>
<div class="sc or"><div class="si">📅</div><div class="sv">{stats['today']}</div><div class="sl" data-i18n="today">Today</div></div>
</div>

<!-- Performance -->
<div class="sec">
<div class="sh"><div class="st">⚡ Performance</div></div>
<div class="pg">
<div class="pi"><div class="pv">{stats['rate']}%</div><div class="pl">Success Rate</div><div class="pt st">→</div></div>
<div class="pi"><div class="pv">{stats['enc_rate']}%</div><div class="pl">Encode Rate</div><div class="pt st">→</div></div>
<div class="pi"><div class="pv">{stats['total']}</div><div class="pl">All Time</div><div class="pt up">↑</div></div>
<div class="pi"><div class="pv">{stats['today']}</div><div class="pl">Today</div><div class="pt {'up' if stats['today']>0 else 'st'}">{'↑ '+str(stats['today_ok']) if stats['today']>0 else '→'}</div></div>
</div>
</div>

<!-- Calendar -->
<div class="sec">
<div class="sh"><div class="st">📅 <span data-i18n="activity">Activity 35 Days</span></div></div>
<div style="display:grid;grid-template-columns:repeat(35,1fr);gap:2px">{cal}</div>
<div style="display:flex;gap:6px;margin-top:8px;align-items:center;font-size:11px;color:var(--t2)">
<span>Less</span><div class="cal c0" style="width:12px;height:12px"></div><div class="cal c1" style="width:12px;height:12px"></div><div class="cal c2" style="width:12px;height:12px"></div><div class="cal c3" style="width:12px;height:12px"></div><div class="cal c4" style="width:12px;height:12px"></div><div class="cal c5" style="width:12px;height:12px"></div><span>More</span>
</div>
</div>

<!-- Charts -->
<div class="g2">
<div class="sec"><div class="sh"><div class="st">📈 <span data-i18n="daily">Daily</span></div></div><div class="ch"><canvas id="c1"></canvas></div></div>
<div class="sec"><div class="sh"><div class="st">📊 <span data-i18n="weekly">Weekly</span></div></div><div class="ch"><canvas id="c2"></canvas></div></div>
</div>

<!-- Storage -->
<div class="sec">
<div class="sh"><div class="st">💾 <span data-i18n="storage">Storage</span></div><span style="font-size:12px;color:var(--t2)">{total_size:.1f} GB in releases</span></div>
<div style="background:var(--bg3);border-radius:6px;height:24px;overflow:hidden;margin:10px 0">
<div style="height:100%;width:{min(total_size/50*100, 100):.0f}%;background:linear-gradient(90deg,var(--bl),var(--pr));border-radius:6px;transition:width .5s"></div>
</div>
<div style="display:flex;justify-content:space-between;font-size:12px;color:var(--t2)">
<span>{total_size:.1f} GB used</span><span>∞ (GitHub unlimited)</span>
</div>
</div>

<!-- Errors -->
<div class="sec">
<div class="sh"><div class="st">🔍 <span data-i18n="errors">Errors</span></div></div>
{eh2}
</div>

<!-- Recordings -->
<div class="sec">
<div class="sh">
<div class="st">🎬 <span data-i18n="recordings">Recordings</span></div>
<div class="fl">
<input class="si2" id="q" placeholder="🔍 Search..." oninput="srch()">
<button class="fb on" onclick="filt('all',this)" data-i18n="all">All</button>
<button class="fb" onclick="filt('success',this)">✅</button>
<button class="fb" onclick="filt('failure',this)">❌</button>
<button class="fb" onclick="filt('in_progress',this)">🔄</button>
</div>
</div>
<div style="overflow-x:auto"><table id="rt"><thead><tr><th></th><th>ID</th><th>Time</th><th>Status</th><th></th></tr></thead><tbody>{rh}</tbody></table></div>
</div>

<!-- Encode + Releases -->
<div class="g2">
<div class="sec">
<div class="sh"><div class="st">🎞 Encode</div></div>
<div style="overflow-x:auto"><table><thead><tr><th></th><th>ID</th><th>Time</th><th>Status</th><th></th></tr></thead><tbody>{eh}</tbody></table></div>
</div>
<div class="sec">
<div class="sh"><div class="st">📦 Releases</div></div>
<div style="overflow-x:auto"><table><thead><tr><th>Tag</th><th>Size</th><th>Time</th><th>Files</th></tr></thead><tbody>{rlh}</tbody></table></div>
</div>
</div>

<!-- Quick Actions -->
<div class="sec">
<div class="sh"><div class="st">⚡ <span data-i18n="actions">Actions</span></div></div>
<div class="ag">
<a class="ab" href="https://github.com/{REPO}/actions" target="_blank">🔧 Actions</a>
<a class="ab" href="https://github.com/{REPO}/releases" target="_blank">📦 Releases</a>
<a class="ab" href="https://github.com/{REPO}" target="_blank">💻 Repo</a>
<a class="ab" onclick="expCSV()">📥 CSV</a>
<a class="ab" onclick="expJSON()">📥 JSON</a>
<a class="ab" onclick="showM('shortcuts')">⌨️ Keys</a>
<a class="ab" onclick="showM('api')">📚 API</a>
<a class="ab" onclick="showM('about')">ℹ️ About</a>
</div>
</div>

<!-- Footer -->
<div class="ft">
<p>Rusemeva Vault · <a href="https://github.com/{REPO}">GitHub</a> · <a href="https://github.com/{REPO}/actions">Actions</a></p>
<p style="margin-top:6px">Auto-refresh 30s · <kbd>R</kbd> refresh · <kbd>D</kbd> theme · <kbd>S</kbd> search</p>
</div>
</div>

<!-- Modal -->
<div class="mo" id="mo" onclick="if(event.target===this)clM()">
<div class="md"><div class="mh"><h3 id="mt">Title</h3><button class="mc" onclick="clM()">&times;</button></div><div id="mb"></div></div>
</div>

<script>
// Theme
function toggleTheme(){{const h=document.documentElement,c=h.getAttribute('data-theme');h.setAttribute('data-theme',c==='dark'?'light':'dark');localStorage.setItem('th',h.getAttribute('data-theme'))}}
(function(){{const s=localStorage.getItem('th');if(s)document.documentElement.setAttribute('data-theme',s)}})();

// Lang
let lang=localStorage.getItem('lang')||'id';
const i18n={{id:{{health:'System Health',total:'Total',success:'Sukses',failed:'Gagal',today:'Hari Ini',activity:'Aktivitas 35 Hari',daily:'Harian',weekly:'Mingguan',storage:'Storage',errors:'Error',recordings:'Rekaman',all:'Semua',actions:'Aksi'}},en:{{health:'System Health',total:'Total',success:'Success',failed:'Failed',today:'Today',activity:'35 Day Activity',daily:'Daily',weekly:'Weekly',storage:'Storage',errors:'Errors',recordings:'Recordings',all:'All',actions:'Actions'}}}};
function setLang(l){{lang=l;localStorage.setItem('lang',l);document.querySelectorAll('.lang-btn').forEach(b=>b.classList.remove('on'));event.target.classList.add('on');document.querySelectorAll('[data-i18n]').forEach(e=>{{const k=e.getAttribute('data-i18n');if(i18n[l]&&i18n[l][k])e.textContent=i18n[l][k]}})}}

// Charts
const cc={{b:'rgba(88,166,255,.6)',bb:'rgba(88,166,255,1)',g:'#3fb950',r:'#f85149'}};
new Chart(document.getElementById('c1').getContext('2d'),{{type:'bar',data:{{labels:{dl},datasets:[{{data:{dd},backgroundColor:cc.b,borderColor:cc.bb,borderWidth:1,borderRadius:3}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{x:{{grid:{{color:'rgba(48,54,61,.5)'}},ticks:{{color:'#8b949e',maxTicksLimit:8}}}},y:{{beginAtZero:true,grid:{{color:'rgba(48,54,61,.5)'}},ticks:{{color:'#8b949e',stepSize:1}}}}}}}}}});
new Chart(document.getElementById('c2').getContext('2d'),{{type:'line',data:{{labels:{wl},datasets:[{{label:'OK',data:{ws},borderColor:cc.g,backgroundColor:'rgba(63,185,80,.1)',fill:true,tension:.4}},{{label:'Fail',data:{wf},borderColor:cc.r,backgroundColor:'rgba(248,81,73,.1)',fill:true,tension:.4}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{labels:{{color:'#8b949e'}}}}}},scales:{{x:{{grid:{{color:'rgba(48,54,61,.5)'}},ticks:{{color:'#8b949e'}}}},y:{{beginAtZero:true,grid:{{color:'rgba(48,54,61,.5)'}},ticks:{{color:'#8b949e',stepSize:1}}}}}}}}}});

// Filter
function filt(s,b){{document.querySelectorAll('.fb').forEach(x=>x.classList.remove('on'));b.classList.add('on');document.querySelectorAll('#rt tbody tr').forEach(r=>r.classList.toggle('hid',s!=='all'&&r.dataset.status!==s))}}
function srch(){{const q=document.getElementById('q').value.toLowerCase();document.querySelectorAll('#rt tbody tr').forEach(r=>r.classList.toggle('hid',!r.dataset.search.includes(q)))}}

// Export
function expCSV(){{const rows=[['ID','Status','Time']];document.querySelectorAll('#rt tbody tr:not(.hid)').forEach(r=>{{const c=r.querySelectorAll('td');rows.push([c[1].textContent.trim(),c[3].textContent.trim(),c[2].textContent.trim()])}});const b=new Blob([rows.map(r=>r.join(',')).join('\\n')],{{type:'text/csv'}});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='rusemeva.csv';a.click()}}
function expJSON(){{const b=new Blob([JSON.stringify({{generated:'{now}',stats:{json.dumps(stats)}}},null,2)],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='rusemeva.json';a.click()}}

// Modal
function showM(t){{const m=document.getElementById('mo');m.classList.add('on');const h=document.getElementById('mt'),b=document.getElementById('mb');
if(t==='shortcuts'){{h.textContent='⌨️ Shortcuts';b.innerHTML='<div class="sh2"><div class="sk"><span class="ky">R</span> Refresh</div><div class="sk"><span class="ky">D</span> Theme</div><div class="sk"><span class="ky">S</span> Search</div><div class="sk"><span class="ky">E</span> Export</div><div class="sk"><span class="ky">Esc</span> Close</div><div class="sk"><span class="ky">1-4</span> Filter</div></div>'}}
if(t==='api'){{h.textContent='📚 API';b.innerHTML='<div style="font-size:13px;line-height:1.8"><code>GET /api/status</code> — System status<br><code>POST /api/record</code> — Start recording<br><code>GET /api/runs</code> — List runs<br><code>GET /api/releases</code> — List releases<br><code>GET /api/stats</code> — Statistics<br><br>Base: <code>rusemeva.rusemeva-vault.workers.dev</code></div>'}}
if(t==='about'){{h.textContent='ℹ️ About';b.innerHTML='<div style="font-size:13px;line-height:1.8"><b>Rusemeva Dashboard</b> v4<br><br>Features: Charts, Calendar, Search, Filter, Export, Theme, Multi-lang, PWA<br><br>Built with: Python + Chart.js + GitHub Pages<br>Repo: <a href="https://github.com/{REPO}" target="_blank">GitHub</a></div>'}}
}}
function clM(){{document.getElementById('mo').classList.remove('on')}}

// Keys
document.addEventListener('keydown',e=>{{if(e.target.tagName==='INPUT')return;switch(e.key){{case'r':location.reload();break;case'd':toggleTheme();break;case's':e.preventDefault();document.getElementById('q').focus();break;case'e':expCSV();break;case'Escape':clM();break;case'1':filt('all',document.querySelector('.fb'));break;case'2':filt('success',document.querySelectorAll('.fb')[1]);break;case'3':filt('failure',document.querySelectorAll('.fb')[2]);break;case'4':filt('in_progress',document.querySelectorAll('.fb')[3]);break}}}});

// Auto-refresh with countdown
let cd=30;setInterval(()=>{{cd--;document.getElementById('timer').textContent=cd+'s';if(cd<=0)location.reload()}},1000);

// Notifications
if('Notification'in window&&Notification.permission==='default')Notification.requestPermission();
</script>
</body>
</html>'''

def main():
    print("🔄 Fetching...")
    runs = fetch_runs(100)
    releases = fetch_releases(30)
    stats = calc_stats(runs)
    print(f"📊 {stats['total']} recordings, {stats['rate']}% success")
    print("🔄 Generating...")
    html = gen_html(stats, runs, releases)
    out = os.environ.get("DASHBOARD_DIR", "/tmp/gh-pages")
    os.makedirs(out, exist_ok=True)
    with open(f"{out}/index.html", "w", encoding="utf-8") as f: f.write(html)
    with open(f"{out}/data.json", "w", encoding="utf-8") as f:
        json.dump({"generated": datetime.now(WIB).isoformat(), "stats": stats, "runs": runs[:30], "releases": releases[:15]}, f, default=str)
    # PWA manifest
    with open(f"{out}/manifest.json", "w") as f:
        json.dump({"name":"Rusemeva Dashboard","short_name":"Rusemeva","start_url":".","display":"standalone","background_color":"#0d1117","theme_color":"#0d1117","icons":[{"src":"data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🎬</text></svg>","sizes":"any","type":"image/svg+xml"}]}, f)
    print(f"✅ Done: {os.path.getsize(f'{out}/index.html')/1024:.0f} KB")

if __name__ == "__main__":
    main()
