#!/usr/bin/env python3
"""Rusemeva Dashboard v5 — Ultimate. All features, clean code."""
import json, os, subprocess, random
from datetime import datetime, timezone, timedelta
from collections import defaultdict

WIB = timezone(timedelta(hours=7))
REPO = "daudjoss/daudjoss-vault"

def gh(args):
    try:
        r = subprocess.run(["gh"]+args, capture_output=True, text=True, timeout=30, env=os.environ.copy())
        return r.stdout.strip()
    except:
        return ""

def get_runs(n=100):
    raw = gh(["run","list","--repo",REPO,"--limit",str(n),"--json","databaseId,name,status,conclusion,createdAt,event,updatedAt"])
    return json.loads(raw) if raw else []

def get_releases(n=30):
    raw = gh(["api",f"repos/{REPO}/releases","--jq",f"[.[:{n}][:][]|{{tag:.tag_name,name:.name,created:.created_at,size:([.assets[].size]|add//0),assets:[.assets[]|{{name:.name,size:.size}}]}}]"])
    return json.loads(raw) if raw else []

def ago(s):
    try:
        d = int((datetime.now(timezone.utc) - datetime.fromisoformat(s.replace("Z","+00:00"))).total_seconds())
        if d < 60: return "baru"
        if d < 3600: return f"{d//60}m"
        if d < 86400: return f"{d//3600}j"
        return f"{d//86400}h"
    except:
        return s[:10]

def ico(c):
    return {"success":"✅","failure":"❌","cancelled":"⚪"}.get(c,"🔄")

def cls(c):
    return {"success":"success","failure":"failure","cancelled":"cancelled"}.get(c,"running")

# ── Helper HTML generators ──

def mk_row(r):
    c = cls(r.get("conclusion",""))
    s = r.get("conclusion", r.get("status","?"))
    rid = str(r.get("databaseId",""))
    return f'<tr class="r-{c}" data-s="{s}" data-q="{rid}"><td>{ico(r.get("conclusion",""))}</td><td><code>{rid}</code></td><td>{ago(r.get("createdAt",""))}</td><td><span class="b b-{c}">{s}</span></td><td><a href="https://github.com/{REPO}/actions/runs/{rid}" target="_blank">↗</a></td></tr>'

def mk_erow(r):
    c = cls(r.get("conclusion",""))
    s = r.get("conclusion", r.get("status","?"))
    rid = str(r.get("databaseId",""))
    return f'<tr><td>{ico(r.get("conclusion",""))}</td><td><code>{rid}</code></td><td>{ago(r.get("createdAt",""))}</td><td><span class="b b-{c}">{s}</span></td><td><a href="https://github.com/{REPO}/actions/runs/{rid}" target="_blank">↗</a></td></tr>'

def mk_rrow(r):
    return f'<tr><td><code>{r.get("tag","")}</code></td><td>{r.get("size",0)/1024/1024:.1f} MB</td><td>{ago(r.get("created",""))}</td></tr>'

def mk_feed(r):
    i = ico(r.get("conclusion", r.get("status","?")))
    c = cls(r.get("conclusion",""))
    s = r.get("conclusion", r.get("status","?"))
    rid = str(r.get("databaseId",""))
    nm = r.get("name","")
    return f'<div class="fi"><span class="fi-icon">{i}</span><span class="fi-time">{ago(r.get("createdAt",""))}</span><span class="fi-id"><code>{rid}</code></span><span class="fi-name">{nm}</span><span class="fi-status {c}">{s}</span></div>'

def mk_ach(a):
    return f'<div class="ach"><div class="ach-icon">{a[2]}</div><div><div class="ach-title">{a[0]}</div><div class="ach-desc">{a[1]}</div></div></div>'

def mk_lock(n, d):
    return f'<div class="ach locked"><div class="ach-icon">🔒</div><div><div class="ach-title">{n}</div><div class="ach-desc">{d}</div></div></div>'

def mk_mbi(r):
    c = cls(r.get("conclusion",""))
    return f'<div class="mbi {c}" title="{r.get("databaseId","")}"><div class="mbi-icon">{ico(r.get("conclusion",""))}</div><div class="mbi-time">{ago(r.get("createdAt",""))}</div></div>'

def mk_err(e):
    return f'<div class="er"><div class="ei">❌</div><div><div>Run <code>{e["id"]}</code></div><div class="et">{e["t"]}</div></div><a href="https://github.com/{REPO}/actions/runs/{e["id"]}" target="_blank">Log ↗</a></div>'

# ── Calculate stats ──

def calc(runs, releases):
    v = [r for r in runs if r.get("name")=="rusemeva-vault"]
    e = [r for r in runs if r.get("name")=="rusemeva-encode"]
    t = len(v)
    s = len([r for r in v if r.get("conclusion")=="success"])
    f = len([r for r in v if r.get("conclusion")=="failure"])
    rn = len([r for r in v if r.get("status")=="in_progress"])
    rate = round(s/t*100,1) if t else 0
    et = len(e)
    es = len([r for r in e if r.get("conclusion")=="success"])
    erate = round(es/et*100,1) if et else 0
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    tr = [r for r in v if r.get("createdAt","").startswith(today)]
    daily = defaultdict(int)
    weekly = defaultdict(lambda:{"s":0,"f":0})
    hours = defaultdict(int)
    days = defaultdict(int)
    night = 0
    for r in v:
        try:
            dt = datetime.fromisoformat(r["createdAt"].replace("Z","+00:00"))
            daily[dt.strftime("%Y-%m-%d")] += 1
            w = dt.strftime("%Y-W%W")
            if r.get("conclusion")=="success": weekly[w]["s"] += 1
            elif r.get("conclusion")=="failure": weekly[w]["f"] += 1
            hours[dt.hour] += 1
            days[dt.strftime("%A")] += 1
            if dt.hour >= 23 or dt.hour < 5: night += 1
        except: pass
    errs = [{"id":r.get("databaseId"),"t":r.get("createdAt","")[:16]} for r in v[:20] if r.get("conclusion")=="failure"][:5]
    streak = 0; best = 0; d = datetime.now(WIB).date()
    while True:
        if d.strftime("%Y-%m-%d") in daily:
            streak += 1; best = max(best, streak)
        else: break
        d -= timedelta(days=1)
    achs = []
    if t >= 1: achs.append(("First Blood","Record pertama","✅"))
    if any(r.get("createdAt","").startswith(today) for r in v): achs.append(("Today","Record hari ini","✅"))
    if streak >= 3: achs.append(("Streak 3","3 hari berturut","✅"))
    if streak >= 7: achs.append(("Week Warrior","7 hari berturut","✅"))
    if t >= 10: achs.append(("Decade","10 recordings","✅"))
    if t >= 50: achs.append(("Half Century","50 recordings","✅"))
    if night >= 5: achs.append(("Night Owl","5+ record malam","✅"))
    if max(hours.values(), default=0) >= 5: achs.append(("Peak Hour","5+ record di jam sama","✅"))
    top_hour = max(hours, key=hours.get, default=0)
    top_day = max(days, key=days.get, default="N/A")
    total_size = sum(r.get("size",0) for r in releases) / 1024/1024/1024
    return {
        "total":t,"success":s,"failed":f,"running":rn,"rate":rate,
        "enc":et,"enc_ok":es,"enc_rate":erate,"today":len(tr),"today_ok":len([r for r in tr if r.get("conclusion")=="success"]),
        "daily":dict(sorted(daily.items())[-35:]),"weekly":dict(sorted(weekly.items())[-12:]),
        "errs":errs,"latest":v[0] if v else None,"streak":streak,"best":best,
        "achs":achs,"top_hour":top_hour,"top_day":top_day,"total_size":total_size,
        "hours":dict(sorted(hours.items())),"days":dict(days),"night":night,
    }

# ── Generate HTML ──

def gen(S, runs, releases):
    now = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")
    dl = json.dumps(list(S["daily"].keys()))
    dd = json.dumps(list(S["daily"].values()))
    wl = json.dumps(list(S["weekly"].keys()))
    ws = json.dumps([v["s"] for v in S["weekly"].values()])
    wf = json.dumps([v["f"] for v in S["weekly"].values()])
    hl = json.dumps(list(S["hours"].keys()))
    hv = json.dumps(list(S["hours"].values()))

    vr = [r for r in runs if r.get("name")=="rusemeva-vault"][:25]
    er = [r for r in runs if r.get("name")=="rusemeva-encode"][:20]

    rh = "".join([mk_row(r) for r in vr])
    eh = "".join([mk_erow(r) for r in er])
    rl = "".join([mk_rrow(r) for r in releases[:15]])
    feed = "".join([mk_feed(r) for r in runs[:15]])
    ach_html = "".join([mk_ach(a) for a in S["achs"]])

    lock_data = [("Centurion","100 recordings"),("Early Bird","Record sebelum 6am"),("Collector","Semua source"),("Marathon","Record >3 jam"),("Weekend Warrior","Record setiap weekend"),("Monthly Master","30 recordings/bulan")]
    ach_locked = "".join([mk_lock(n,d) for n,d in lock_data[:6-len(S["achs"])]])

    err_html = "".join([mk_err(e) for e in S["errs"]]) if S["errs"] else '<div class="ne">✅ Tidak ada error</div>'
    mbi_html = "".join([mk_mbi(r) for r in vr[:20]])

    cal = ""
    today = datetime.now(WIB).date()
    for i in range(34, -1, -1):
        day = today - timedelta(days=i)
        cnt = S["daily"].get(day.strftime("%Y-%m-%d"), 0)
        it = min(cnt, 5)
        cal += f'<div class="c c{it}" title="{day.strftime("%Y-%m-%d")}: {cnt}">{day.day}</div>'

    rand_r = random.choice(vr) if vr else None
    rand_html = f'<code>{rand_r.get("databaseId","")}</code> | {ago(rand_r.get("createdAt",""))} | <a href="https://github.com/{REPO}/actions/runs/{rand_r.get("databaseId","")}" target="_blank">View ↗</a>' if rand_r else "No recordings"

    pct = min(S['total_size']/50*100, 100)
    streak_pct = min(S['streak']/max(S['best'],1)*100, 100)
    today_cls = "up" if S['today']>0 else "st"
    today_txt = f"↑ {S['today_ok']}" if S['today']>0 else "→"

    return '''<!DOCTYPE html>
<html lang="id" data-t="dark">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="theme-color" content="#0d1117"><link rel="manifest" href="manifest.json">
<title>Rusemeva Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{--bg:#0d1117;--bg2:#161b22;--bg3:#21262d;--brd:#30363d;--t1:#e6edf3;--t2:#8b949e;--t3:#484f58;--bl:#58a6ff;--gn:#3fb950;--rd:#f85149;--yl:#d29922;--pr:#bc8cff;--or:#f0883e;--pn:#f778ba}
[data-t="light"]{--bg:#f6f8fa;--bg2:#fff;--bg3:#f0f2f5;--brd:#d0d7de;--t1:#1f2328;--t2:#656d76;--t3:#8b949e}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--t1);padding:14px;min-height:100vh;transition:all .3s;overflow-x:hidden}
.ct{max-width:1480px;margin:0 auto}
.hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid var(--brd);flex-wrap:wrap;gap:8px}
.hdr h1{font-size:22px;font-weight:700;display:flex;align-items:center;gap:8px}
.ha{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.dot{width:8px;height:8px;background:var(--gn);border-radius:50%;animation:p 2s infinite}
@keyframes p{0%,100%{opacity:1}50%{opacity:.4}}
.btn{padding:5px 10px;border-radius:7px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);cursor:pointer;font-size:12px;transition:all .2s}
.btn:hover{border-color:var(--bl)}
.sg{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:16px}
.sc{background:var(--bg2);border:1px solid var(--brd);border-radius:10px;padding:14px;position:relative;overflow:hidden;transition:transform .2s,box-shadow .2s}
.sc:hover{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,.15)}
.sc::before{content:'';position:absolute;top:0;left:0;right:0;height:3px}
.sc.bl::before{background:var(--bl)}.sc.gn::before{background:var(--gn)}.sc.rd::before{background:var(--rd)}
.sc.yl::before{background:var(--yl)}.sc.pr::before{background:var(--pr)}.sc.or::before{background:var(--or)}.sc.pn::before{background:var(--pn)}
.si{font-size:18px;margin-bottom:4px}.sv{font-size:28px;font-weight:700}.sl{font-size:11px;color:var(--t2);text-transform:uppercase}
.sc.bl .sv{color:var(--bl)}.sc.gn .sv{color:var(--gn)}.sc.rd .sv{color:var(--rd)}.sc.yl .sv{color:var(--yl)}.sc.pr .sv{color:var(--pr)}.sc.or .sv{color:var(--or)}.sc.pn .sv{color:var(--pn)}
.sec{background:var(--bg2);border:1px solid var(--brd);border-radius:10px;padding:14px;margin-bottom:16px}
.sh{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--brd);flex-wrap:wrap;gap:8px}
.st{font-size:14px;font-weight:600;display:flex;align-items:center;gap:6px}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
.fl{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.fb{padding:4px 10px;border-radius:14px;border:1px solid var(--brd);background:transparent;color:var(--t2);cursor:pointer;font-size:11px;transition:all .2s}
.fb:hover,.fb.on{background:var(--bl);color:#fff;border-color:var(--bl)}
.si2{padding:6px 10px;border-radius:7px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);font-size:12px;width:150px}
.si2:focus{outline:none;border-color:var(--bl)}
table{width:100%;border-collapse:collapse}th,td{padding:7px 10px;text-align:left;border-bottom:1px solid var(--brd)}
th{color:var(--t2);font-size:10px;text-transform:uppercase;letter-spacing:.5px;font-weight:600}td{font-size:12px}tr:hover{background:rgba(88,166,255,.03)}
code{background:var(--bg3);padding:2px 5px;border-radius:4px;font-size:10px;font-family:'SF Mono',monospace}
a{color:var(--bl);text-decoration:none}a:hover{text-decoration:underline}
.b{padding:2px 8px;border-radius:10px;font-size:10px;font-weight:500}
.b-success{background:rgba(63,185,80,.15);color:var(--gn)}.b-failure{background:rgba(248,81,73,.15);color:var(--rd)}.b-cancelled{background:rgba(139,148,158,.15);color:var(--t2)}.b-running{background:rgba(88,166,255,.15);color:var(--bl)}
.c{aspect-ratio:1;border-radius:3px;display:flex;align-items:center;justify-content:center;font-size:9px;color:var(--t3);cursor:default}
.c0{background:var(--bg3)}.c1{background:rgba(63,185,80,.25)}.c2{background:rgba(63,185,80,.45)}.c3{background:rgba(63,185,80,.65)}.c4{background:rgba(63,185,80,.8)}.c5{background:var(--gn);color:#fff}
.ch{position:relative;height:200px}.ch2{position:relative;height:150px}
.er{display:flex;align-items:center;gap:8px;padding:8px;background:rgba(248,81,73,.04);border:1px solid rgba(248,81,73,.15);border-radius:7px;margin-bottom:5px}
.ei{font-size:16px}.et{font-size:10px;color:var(--t2)}.ne{text-align:center;padding:12px;color:var(--t2);font-size:13px}
.hg{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px}
.hi{display:flex;align-items:center;gap:8px;padding:8px;background:var(--bg3);border-radius:7px}
.hd{width:7px;height:7px;border-radius:50%}.hd.g{background:var(--gn)}.hd.y{background:var(--yl)}.hd.r{background:var(--rd)}
.hl{font-size:12px;font-weight:500}.hs{font-size:10px;color:var(--t2)}
.pg{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px}
.pi{text-align:center;padding:8px;background:var(--bg3);border-radius:7px}.pv{font-size:22px;font-weight:700;color:var(--bl)}.pl{font-size:10px;color:var(--t2);margin-top:2px}
.pt{font-size:10px;margin-top:2px}.pt.up{color:var(--gn)}.pt.dn{color:var(--rd)}.pt.st{color:var(--t3)}
.ag{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px}
.ab{padding:8px 12px;border-radius:7px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);cursor:pointer;font-size:12px;text-align:center;transition:all .2s;text-decoration:none;display:block}
.ab:hover{border-color:var(--bl);background:rgba(88,166,255,.08)}
.mo{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.7);z-index:1000;align-items:center;justify-content:center}
.mo.on{display:flex}
.md{background:var(--bg2);border:1px solid var(--brd);border-radius:12px;padding:18px;max-width:520px;width:92%;max-height:80vh;overflow-y:auto}
.mh{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
.mc{background:none;border:none;color:var(--t2);font-size:20px;cursor:pointer}
.sh2{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:5px}
.sk{display:flex;align-items:center;gap:5px;padding:5px;font-size:12px}
.ky{padding:2px 6px;background:var(--bg3);border:1px solid var(--brd);border-radius:3px;font-family:monospace;font-size:10px}
.ft{text-align:center;color:var(--t3);font-size:11px;margin-top:24px;padding-top:14px;border-top:1px solid var(--brd)}
.ft a{color:var(--t2)}
@media(max-width:1024px){.g2{grid-template-columns:1fr}}
@media(max-width:768px){.sg{grid-template-columns:repeat(2,1fr)}.hdr{flex-direction:column;align-items:flex-start}.si2{width:100%}}
.sc,.sec{animation:fi .3s ease-in}@keyframes fi{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.hid{display:none!important}
.feed{max-height:250px;overflow-y:auto}.fi{display:flex;align-items:center;gap:8px;padding:6px 8px;border-bottom:1px solid var(--brd);font-size:12px;transition:background .2s}
.fi:hover{background:rgba(88,166,255,.04)}.fi-icon{font-size:14px}.fi-time{color:var(--t3);font-size:11px;min-width:30px}.fi-id{font-size:11px}.fi-name{color:var(--t2);font-size:11px}.fi-status{font-size:10px;padding:1px 6px;border-radius:8px}.fi-status.success{background:rgba(63,185,80,.15);color:var(--gn)}.fi-status.failure{background:rgba(248,81,73,.15);color:var(--rd)}.fi-status.running{background:rgba(88,166,255,.15);color:var(--bl)}
.ach-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px}
.ach{display:flex;align-items:center;gap:10px;padding:10px;background:var(--bg3);border-radius:8px;border:1px solid var(--brd);transition:all .2s}
.ach:hover{border-color:var(--yl);background:rgba(210,153,34,.05)}.ach.locked{opacity:.5}
.ach-icon{font-size:20px}.ach-title{font-size:13px;font-weight:600}.ach-desc{font-size:10px;color:var(--t2)}
.ff{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}
.ffi{padding:14px;background:var(--bg3);border-radius:8px;text-align:center;border:1px solid var(--brd)}
.ffi-icon{font-size:28px;margin-bottom:6px}.ffi-val{font-size:20px;font-weight:700;color:var(--bl)}.ffi-label{font-size:11px;color:var(--t2);margin-top:4px}
.mb{display:grid;grid-template-columns:repeat(auto-fill,minmax(80px,1fr));gap:6px}
.mbi{padding:10px;border-radius:8px;text-align:center;font-size:11px;border:2px solid transparent;cursor:pointer;transition:all .2s}
.mbi:hover{transform:scale(1.05)}.mbi.ok{background:rgba(63,185,80,.1);border-color:rgba(63,185,80,.3)}.mbi.fail{background:rgba(248,81,73,.1);border-color:rgba(248,81,73,.3)}.mbi.run{background:rgba(88,166,255,.1);border-color:rgba(88,166,255,.3)}
.mbi-icon{font-size:18px}.mbi-time{font-size:9px;color:var(--t3);margin-top:2px}
.streak{display:flex;align-items:center;gap:12px;padding:14px;background:linear-gradient(135deg,rgba(248,81,73,.1),rgba(210,153,34,.1));border-radius:10px;border:1px solid var(--brd)}
.streak-icon{font-size:32px}.streak-val{font-size:28px;font-weight:700;color:var(--or)}.streak-label{font-size:12px;color:var(--t2)}.streak-bar{height:6px;background:var(--bg3);border-radius:3px;margin-top:6px;overflow:hidden}.streak-fill{height:100%;background:linear-gradient(90deg,var(--rd),var(--or),var(--yl));border-radius:3px;transition:width .5s}
.tc{display:flex;flex-wrap:wrap;gap:6px;justify-content:center}
.tg{padding:4px 10px;border-radius:14px;background:var(--bg3);border:1px solid var(--brd);font-size:11px;cursor:pointer;transition:all .2s}
.tg:hover{border-color:var(--bl);background:rgba(88,166,255,.1)}
.rand{text-align:center;padding:20px;background:linear-gradient(135deg,rgba(88,166,255,.05),rgba(188,140,255,.05));border-radius:10px;border:1px solid var(--brd)}
.rand-btn{padding:12px 24px;border-radius:10px;border:2px solid var(--bl);background:transparent;color:var(--bl);cursor:pointer;font-size:14px;font-weight:600;transition:all .3s;margin:10px 0}
.rand-btn:hover{background:var(--bl);color:#fff}
.cmp{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.cmp-item{padding:12px;background:var(--bg3);border-radius:8px;text-align:center}
.cmp-val{font-size:20px;font-weight:700}.cmp-label{font-size:11px;color:var(--t2)}
.nav{position:fixed;right:14px;top:50%;transform:translateY(-50%);z-index:100;display:flex;flex-direction:column;gap:4px}
.nav-btn{width:28px;height:28px;border-radius:6px;border:1px solid var(--brd);background:var(--bg2);color:var(--t2);cursor:pointer;font-size:12px;display:flex;align-items:center;justify-content:center;transition:all .2s}
.nav-btn:hover{border-color:var(--bl);color:var(--bl)}
@media(max-width:768px){.nav{display:none}}
</style>
</head>
<body>
<div class="ct">
<div class="nav">
<button class="nav-btn" onclick="document.querySelector('.hdr').scrollIntoView({behavior:'smooth'})" title="Top">🏠</button>
<button class="nav-btn" onclick="document.getElementById('sec-feed').scrollIntoView({behavior:'smooth'})" title="Feed">📰</button>
<button class="nav-btn" onclick="document.getElementById('sec-rec').scrollIntoView({behavior:'smooth'})" title="Rec">🎬</button>
<button class="nav-btn" onclick="document.getElementById('sec-ach').scrollIntoView({behavior:'smooth'})" title="Ach">🏆</button>
<button class="nav-btn" onclick="document.getElementById('sec-act').scrollIntoView({behavior:'smooth'})" title="Act">⚡</button>
</div>
<div class="hdr">
<h1>🎬 Rusemeva</h1>
<div class="ha"><div class="dot"></div><span style="font-size:11px;color:var(--t2)" id="tmr">30s</span>
<button class="btn" onclick="toggleTheme()">🌓</button><button class="btn" onclick="location.reload()">🔄</button></div>
</div>
<div class="sg">
<div class="sc bl"><div class="si">📹</div><div class="sv">''' + str(S['total']) + '''</div><div class="sl">Total</div></div>
<div class="sc gn"><div class="si">✅</div><div class="sv">''' + str(S['success']) + '''</div><div class="sl">Success</div></div>
<div class="sc rd"><div class="si">❌</div><div class="sv">''' + str(S['failed']) + '''</div><div class="sl">Failed</div></div>
<div class="sc yl"><div class="si">📊</div><div class="sv">''' + str(S['rate']) + '''%</div><div class="sl">Rate</div></div>
<div class="sc pr"><div class="si">🎞</div><div class="sv">''' + str(S['enc']) + '''</div><div class="sl">Encode</div></div>
<div class="sc or"><div class="si">📅</div><div class="sv">''' + str(S['today']) + '''</div><div class="sl">Today</div></div>
<div class="sc pn"><div class="si">🔥</div><div class="sv">''' + str(S['streak']) + '''</div><div class="sl">Streak</div></div>
</div>
<div class="sec" id="sec-health"><div class="sh"><div class="st">🏥 System Health</div><span style="font-size:10px;color:var(--t2)">''' + now + '''</span></div>
<div class="hg"><div class="hi"><div class="hd g"></div><div><div class="hl">Worker</div><div class="hs">rusemeva-vault</div></div></div><div class="hi"><div class="hd g"></div><div><div class="hl">GitHub Actions</div><div class="hs">20 slots</div></div></div><div class="hi"><div class="hd g"></div><div><div class="hl">Telegram</div><div class="hs">@daudtrans_bot</div></div></div><div class="hi"><div class="hd g"></div><div><div class="hl">Dashboard</div><div class="hs">gh-pages</div></div></div></div></div>
<div class="streak"><div class="streak-icon">🔥</div><div style="flex:1"><div class="streak-val">''' + str(S['streak']) + ''' days</div><div class="streak-label">Current streak (best: ''' + str(S['best']) + ''' days)</div><div class="streak-bar"><div class="streak-fill" style="width:''' + str(streak_pct) + '''%"></div></div></div></div>
<div class="sec" id="sec-feed"><div class="sh"><div class="st">📰 Live Feed</div><span style="font-size:10px;color:var(--t2)">Last 15</span></div><div class="feed">''' + feed + '''</div></div>
<div class="sec"><div class="sh"><div class="st">⚡ Performance</div></div><div class="pg">
<div class="pi"><div class="pv">''' + str(S['rate']) + '''%</div><div class="pl">Success Rate</div></div>
<div class="pi"><div class="pv">''' + str(S['enc_rate']) + '''%</div><div class="pl">Encode Rate</div></div>
<div class="pi"><div class="pv">''' + str(S['total']) + '''</div><div class="pl">All Time</div></div>
<div class="pi"><div class="pv">''' + str(S['today']) + '''</div><div class="pl">Today</div><div class="pt ''' + today_cls + '''">''' + today_txt + '''</div></div>
<div class="pi"><div class="pv">''' + str(S['night']) + '''</div><div class="pl">Night</div></div>
<div class="pi"><div class="pv">''' + str(S['top_hour']) + ''':00</div><div class="pl">Peak Hour</div></div>
</div></div>
<div class="sec"><div class="sh"><div class="st">📅 Activity (35 days)</div></div>
<div style="display:grid;grid-template-columns:repeat(35,1fr);gap:2px">''' + cal + '''</div>
<div style="display:flex;gap:5px;margin-top:6px;align-items:center;font-size:10px;color:var(--t2)"><span>Less</span><div class="c c0" style="width:10px;height:10px"></div><div class="c c1" style="width:10px;height:10px"></div><div class="c c2" style="width:10px;height:10px"></div><div class="c c3" style="width:10px;height:10px"></div><div class="c c4" style="width:10px;height:10px"></div><div class="c c5" style="width:10px;height:10px"></div><span>More</span></div></div>
<div class="g2">
<div class="sec"><div class="sh"><div class="st">📈 Daily</div></div><div class="ch"><canvas id="c1"></canvas></div></div>
<div class="sec"><div class="sh"><div class="st">📊 Weekly</div></div><div class="ch"><canvas id="c2"></canvas></div></div>
</div>
<div class="sec"><div class="sh"><div class="st">⏰ Recording Hours</div></div><div class="ch2"><canvas id="c3"></canvas></div></div>
<div class="sec"><div class="sh"><div class="st">🎲 Fun Facts</div></div><div class="ff">
<div class="ffi"><div class="ffi-icon">📺</div><div class="ffi-val">''' + str(S['total']) + '''</div><div class="ffi-label">Recordings</div></div>
<div class="ffi"><div class="ffi-icon">🔥</div><div class="ffi-val">''' + str(S['streak']) + '''</div><div class="ffi-label">Streak</div></div>
<div class="ffi"><div class="ffi-icon">🌙</div><div class="ffi-val">''' + str(S['night']) + '''</div><div class="ffi-label">Night</div></div>
<div class="ffi"><div class="ffi-icon">⏰</div><div class="ffi-val">''' + str(S['top_hour']) + ''':00</div><div class="ffi-label">Peak</div></div>
<div class="ffi"><div class="ffi-icon">📅</div><div class="ffi-val">''' + str(S['top_day']) + '''</div><div class="ffi-label">Top Day</div></div>
<div class="ffi"><div class="ffi-icon">💾</div><div class="ffi-val">''' + f"{S['total_size']:.1f}" + ''' GB</div><div class="ffi-label">Storage</div></div>
</div></div>
<div class="sec"><div class="sh"><div class="st">📊 This Week vs Last</div></div><div class="cmp">
<div class="cmp-item"><div class="cmp-val">''' + str(S['success']) + '''</div><div class="cmp-label">Success</div></div>
<div class="cmp-item"><div class="cmp-val">''' + str(S['failed']) + '''</div><div class="cmp-label">Failed</div></div>
<div class="cmp-item"><div class="cmp-val">''' + str(S['rate']) + '''%</div><div class="cmp-label">Rate</div></div>
<div class="cmp-item"><div class="cmp-val">''' + str(S['enc_rate']) + '''%</div><div class="cmp-label">Encode</div></div>
</div></div>
<div class="sec"><div class="sh"><div class="st">💾 Storage</div><span style="font-size:11px;color:var(--t2)">''' + f"{S['total_size']:.1f}" + ''' GB</span></div>
<div style="background:var(--bg3);border-radius:5px;height:20px;overflow:hidden;margin:8px 0"><div style="height:100%;width:''' + str(pct) + '''%;background:linear-gradient(90deg,var(--bl),var(--pr));border-radius:5px"></div></div></div>
<div class="sec"><div class="sh"><div class="st">🔍 Errors</div></div>''' + err_html + '''</div>
<div class="sec" id="sec-ach"><div class="sh"><div class="st">🏆 Achievements (''' + str(len(S['achs'])) + ''')</div></div><div class="ach-grid">''' + ach_html + ach_locked + '''</div></div>
<div class="sec"><div class="sh"><div class="st">🎨 Mood Board</div></div><div class="mb">''' + mbi_html + '''</div></div>
<div class="sec"><div class="sh"><div class="st">🏷 Tags</div></div><div class="tc"><span class="tg">Trans7</span><span class="tg">SevenHub</span><span class="tg">talk-show</span><span class="tg">berita</span><span class="tg">komedi</span><span class="tg">HEVC</span><span class="tg">encode</span><span class="tg">malam</span><span class="tg">pagi</span><span class="tg">weekend</span></div></div>
<div class="sec"><div class="sh"><div class="st">🎲 Random</div></div><div class="rand"><div style="font-size:13px;color:var(--t2);margin-bottom:8px">Feeling lucky?</div><button class="rand-btn" onclick="this.nextElementSibling.innerHTML=''' + "'" + rand_html + "'" + '''">🎬 Surprise Me!</button><div></div></div></div>
<div class="sec" id="sec-rec"><div class="sh"><div class="st">🎬 Recordings</div><div class="fl"><input class="si2" id="q" placeholder="🔍 Search..." oninput="srch()"><button class="fb on" onclick="filt('all',this)">All</button><button class="fb" onclick="filt('success',this)">✅</button><button class="fb" onclick="filt('failure',this)">❌</button><button class="fb" onclick="filt('in_progress',this)">🔄</button></div></div>
<div style="overflow-x:auto"><table id="rt"><thead><tr><th></th><th>ID</th><th>Time</th><th>Status</th><th></th></tr></thead><tbody>''' + rh + '''</tbody></table></div></div>
<div class="g2">
<div class="sec"><div class="sh"><div class="st">🎞 Encode</div></div><div style="overflow-x:auto"><table><thead><tr><th></th><th>ID</th><th>Time</th><th>Status</th><th></th></tr></thead><tbody>''' + eh + '''</tbody></table></div></div>
<div class="sec"><div class="sh"><div class="st">📦 Releases</div></div><div style="overflow-x:auto"><table><thead><tr><th>Tag</th><th>Size</th><th>Time</th></tr></thead><tbody>''' + rl + '''</tbody></table></div></div>
</div>
<div class="sec" id="sec-act"><div class="sh"><div class="st">⚡ Actions</div></div><div class="ag">
<a class="ab" href="https://github.com/''' + REPO + '''/actions" target="_blank">🔧 Actions</a>
<a class="ab" href="https://github.com/''' + REPO + '''/releases" target="_blank">📦 Releases</a>
<a class="ab" href="https://github.com/''' + REPO + '''" target="_blank">💻 Repo</a>
<a class="ab" onclick="expCSV()">📥 CSV</a><a class="ab" onclick="expJSON()">📥 JSON</a>
<a class="ab" onclick="showM('keys')">⌨️ Keys</a><a class="ab" onclick="showM('api')">📚 API</a><a class="ab" onclick="showM('about')">ℹ️ About</a>
</div></div>
<div class="ft"><p>Rusemeva · <a href="https://github.com/''' + REPO + '''">GitHub</a></p><p style="margin-top:4px">Auto-refresh 30s · <kbd>R</kbd> refresh · <kbd>D</kbd> theme</p></div>
</div>
<div class="mo" id="mo" onclick="if(event.target===this)clM()"><div class="md"><div class="mh"><h3 id="mt"></h3><button class="mc" onclick="clM()">&times;</button></div><div id="mb"></div></div></div>
<script>
function toggleTheme(){var h=document.documentElement,c=h.getAttribute('data-t');h.setAttribute('data-t',c==='dark'?'light':'dark');localStorage.setItem('th',h.getAttribute('data-t'))}
(function(){var s=localStorage.getItem('th');if(s)document.documentElement.setAttribute('data-t',s)})();
var cc={b:'rgba(88,166,255,.5)',g:'#3fb950',r:'#f85149'};
new Chart(document.getElementById('c1').getContext('2d'),{type:'bar',data:{labels:''' + dl + ''',datasets:[{data:''' + dd + ''',backgroundColor:cc.b,borderRadius:3}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{color:'rgba(48,54,61,.4)'},ticks:{color:'#8b949e',maxTicksLimit:7}},y:{beginAtZero:true,grid:{color:'rgba(48,54,61,.4)'},ticks:{color:'#8b949e',stepSize:1}}}}});
new Chart(document.getElementById('c2').getContext('2d'),{type:'line',data:{labels:''' + wl + ''',datasets:[{label:'OK',data:''' + ws + ''',borderColor:cc.g,backgroundColor:'rgba(63,185,80,.08)',fill:true,tension:.4},{label:'Fail',data:''' + wf + ''',borderColor:cc.r,backgroundColor:'rgba(248,81,73,.08)',fill:true,tension:.4}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:'#8b949e'}}},scales:{x:{grid:{color:'rgba(48,54,61,.4)'},ticks:{color:'#8b949e'}},y:{beginAtZero:true,grid:{color:'rgba(48,54,61,.4)'},ticks:{color:'#8b949e',stepSize:1}}}}});
new Chart(document.getElementById('c3').getContext('2d'),{type:'bar',data:{labels:''' + hl + ''',datasets:[{data:''' + hv + ''',backgroundColor:'rgba(188,140,255,.5)',borderRadius:3}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{color:'rgba(48,54,61,.4)'},ticks:{color:'#8b949e'}},y:{beginAtZero:true,grid:{color:'rgba(48,54,61,.4)'},ticks:{color:'#8b949e',stepSize:1}}}}});
function filt(s,b){document.querySelectorAll('.fb').forEach(function(x){x.classList.remove('on')});b.classList.add('on');document.querySelectorAll('#rt tbody tr').forEach(function(r){r.classList.toggle('hid',s!=='all'&&r.dataset.s!==s)})}
function srch(){var q=document.getElementById('q').value.toLowerCase();document.querySelectorAll('#rt tbody tr').forEach(function(r){r.classList.toggle('hid',!r.dataset.q.includes(q))})}
function expCSV(){var rows=[['ID','Status','Time']];document.querySelectorAll('#rt tbody tr:not(.hid)').forEach(function(r){var c=r.querySelectorAll('td');rows.push([c[1].textContent.trim(),c[3].textContent.trim(),c[2].textContent.trim()])});var b=new Blob([rows.map(function(r){return r.join(',')}).join('\\n')],{type:'text/csv'});var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='rusemeva.csv';a.click()}
function expJSON(){var b=new Blob([JSON.stringify({stats:''}],null,2)],{type:'application/json'});var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='rusemeva.json';a.click()}
function showM(t){document.getElementById('mo').classList.add('on');var h=document.getElementById('mt'),b=document.getElementById('mb');
if(t==='keys'){h.textContent='⌨️ Shortcuts';b.innerHTML='<div class="sh2"><div class="sk"><span class="ky">R</span> Refresh</div><div class="sk"><span class="ky">D</span> Theme</div><div class="sk"><span class="ky">S</span> Search</div><div class="sk"><span class="ky">E</span> Export</div><div class="sk"><span class="ky">Esc</span> Close</div></div>'}
if(t==='api'){h.textContent='📚 API';b.innerHTML='<div style="font-size:12px;line-height:1.8"><code>GET /api/status</code> System status<br><code>POST /api/record</code> Start recording<br><code>GET /api/runs</code> List runs<br><br>Base: <code>rusemeva.rusemeva-vault.workers.dev</code></div>'}
if(t==='about'){h.textContent='ℹ️ About';b.innerHTML='<div style="font-size:12px;line-height:1.8"><b>Rusemeva Dashboard</b> v5 Ultimate<br><br>Features: Charts, Calendar, Search, Filter, Export, Theme, Live Feed, Achievements, Fun Facts, Mood Board, Streak, Random, Tags<br><br>Built: Python + Chart.js + GitHub Pages<br>Cost: $0 (100% free)<br>Repo: <a href="https://github.com/''' + REPO + '''">GitHub</a></div>'}}
function clM(){document.getElementById('mo').classList.remove('on')}
document.addEventListener('keydown',function(e){if(e.target.tagName==='INPUT')return;switch(e.key){case'r':location.reload();break;case'd':toggleTheme();break;case's':e.preventDefault();document.getElementById('q').focus();break;case'e':expCSV();break;case'Escape':clM();break}});
var cd=30;setInterval(function(){cd--;document.getElementById('tmr').textContent=cd+'s';if(cd<=0)location.reload()},1000);
if('Notification'in window&&Notification.permission==='default')Notification.requestPermission();
</script>
</body>
</html>'''

def main():
    print("🔄 Fetching...")
    runs = get_runs(100)
    releases = get_releases(30)
    S = calc(runs, releases)
    print(f"📊 {S['total']} recordings, {S['rate']}% success, {S['streak']} streak")
    print("🔄 Generating...")
    html = gen(S, runs, releases)
    out = os.environ.get("DASHBOARD_DIR", "/tmp/gh-pages")
    os.makedirs(out, exist_ok=True)
    with open(f"{out}/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    with open(f"{out}/data.json", "w", encoding="utf-8") as f:
        json.dump({"generated": datetime.now(WIB).isoformat(), "stats": S, "runs": runs[:30], "releases": releases[:15]}, f, default=str)
    with open(f"{out}/manifest.json", "w") as f:
        json.dump({"name": "Rusemeva Dashboard", "short_name": "Rusemeva", "start_url": ".", "display": "standalone", "background_color": "#0d1117", "theme_color": "#0d1117", "icons": [{"src": "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🎬</text></svg>", "sizes": "any", "type": "image/svg+xml"}]}, f)
    print(f"✅ Done: {os.path.getsize(f'{out}/index.html')/1024:.0f} KB")

if __name__ == "__main__":
    main()
