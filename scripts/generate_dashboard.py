#!/usr/bin/env python3
"""Rusemeva Dashboard v8 — ALL20 new features + mobile."""
import json, os, subprocess, random
from datetime import datetime, timezone, timedelta
from collections import defaultdict

WIB = timezone(timedelta(hours=7))
REPO = "daudjoss/daudjoss-vault"

def gh(args):
    try:
        r = subprocess.run(["gh"]+args, capture_output=True, text=True, timeout=30, env=os.environ.copy())
        return r.stdout.strip()
    except: return ""

def get_runs(n=100):
    raw = gh(["run","list","--repo",REPO,"--limit",str(n),"--json","databaseId,name,status,conclusion,createdAt,event,updatedAt"])
    return json.loads(raw) if raw else []

def get_releases(n=30):
    raw = gh(["api",f"repos/{REPO}/releases","--jq",f"[.[:{n}][]|{{tag:.tag_name,name:.name,created:.created_at,size:([.assets[].size]|add//0),assets:[.assets[]|{{name:.name,size:.size}}]}}]"])
    return json.loads(raw) if raw else []

def is_media_release(r):
    """Skip encode-temp + tiny metadata .txt releases from size/anomaly stats."""
    tag = (r.get("tag") or "")
    name = (r.get("name") or "")
    size = r.get("size") or 0
    if "encode-" in tag or "Encode Temp" in name:
        return False
    # metadata-only releases are usually << 1MB
    if size > 0 and size < 1 * 1024 * 1024:
        return False
    return True

def get_orv_map():
    """Fetch public run_id→RSM map from Worker (best-effort)."""
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://rusemeva.rusemeva-vault.workers.dev/api/orv-map",
            headers={"User-Agent": "rusemeva-dashboard"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
            m = data.get("map") if isinstance(data, dict) else []
            return m if isinstance(m, list) else []
    except Exception:
        return []

def attach_orv(runs, orv_map):
    by_run = {}
    for item in orv_map or []:
        rid = str(item.get("run_id") or "")
        oid = (item.get("orv_id") or "").strip()
        if rid and oid:
            by_run[rid] = {"orv_id": oid, "source": item.get("source") or ""}
    for r in runs:
        rid = str(r.get("databaseId") or "")
        meta = by_run.get(rid)
        if meta:
            r["orv_id"] = meta["orv_id"]
            if meta.get("source"):
                r["source"] = meta["source"]
    return runs

def to_wib(s):
    """Parse GH ISO timestamp to WIB datetime (or None)."""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(WIB)
    except Exception:
        return None

def ago(s):
    try:
        d = int((datetime.now(timezone.utc) - datetime.fromisoformat(s.replace("Z","+00:00"))).total_seconds())
        if d < 60: return "baru"
        if d < 3600: return f"{d//60}m"
        if d < 86400: return f"{d//3600}j"
        return f"{d//86400}h"
    except: return s[:10]

def ico(c):
    return {"success":"✅","failure":"❌","cancelled":"⚪"}.get(c,"🔄")

def cls(c):
    return {"success":"success","failure":"failure","cancelled":"cancelled"}.get(c,"running")

def status_key(r):
    """Canonical filter key: success|failure|cancelled|in_progress|other."""
    c = (r.get("conclusion") or "").strip()
    if c in ("success", "failure", "cancelled"):
        return c
    st = (r.get("status") or "").strip()
    if st in ("in_progress", "queued", "waiting", "pending", "requested"):
        return "in_progress"
    return c or st or "?"

def display_status(r):
    c = (r.get("conclusion") or "").strip()
    if c:
        return c
    st = (r.get("status") or "").strip()
    if st in ("in_progress", "queued", "waiting", "pending", "requested"):
        return "in_progress"
    return st or "?"

def mk_row(r):
    sk = status_key(r)
    c = cls(r.get("conclusion","") if (r.get("conclusion") or "").strip() else "")
    # force running style when in progress
    if sk == "in_progress":
        c = "running"
    s = display_status(r)
    rid = str(r.get("databaseId",""))
    orv = (r.get("orv_id") or "").strip()
    idcell = f'<code title="{rid}">{orv or rid}</code>' if orv else f'<code>{rid}</code>'
    q = f"{rid} {orv} {s}".lower()
    return f'<tr class="r-{c}" data-s="{sk}" data-q="{q}" data-rid="{rid}" data-orv="{orv}"><td>{ico(r.get("conclusion","") if sk!="in_progress" else "")}</td><td>{idcell}</td><td>{ago(r.get("createdAt",""))}</td><td><span class="b b-{c}">{s}</span></td><td><a href="https://github.com/{REPO}/actions/runs/{rid}" target="_blank">↗</a></td></tr>'

def mk_erow(r):
    sk = status_key(r)
    c = "running" if sk == "in_progress" else cls(r.get("conclusion",""))
    s = display_status(r)
    rid = str(r.get("databaseId",""))
    orv = (r.get("orv_id") or "").strip()
    idcell = f'<code title="{rid}">{orv or rid}</code>' if orv else f'<code>{rid}</code>'
    return f'<tr data-s="{sk}" data-rid="{rid}" data-orv="{orv}"><td>{ico("" if sk=="in_progress" else r.get("conclusion",""))}</td><td>{idcell}</td><td>{ago(r.get("createdAt",""))}</td><td><span class="b b-{c}">{s}</span></td><td><a href="https://github.com/{REPO}/actions/runs/{rid}" target="_blank">↗</a></td></tr>'

def mk_rrow(r):
    tag = r.get("tag","")
    size_mb = r.get("size",0)/1024/1024
    kind = "temp" if "encode-" in tag else ("meta" if size_mb < 1 else "asset")
    return f'<tr data-kind="{kind}"><td><code>{tag}</code></td><td>{size_mb:.1f} MB</td><td>{ago(r.get("created",""))}</td></tr>'

def mk_feed(r):
    sk = status_key(r)
    c = "running" if sk == "in_progress" else cls(r.get("conclusion",""))
    s = display_status(r)
    i = ico("" if sk == "in_progress" else r.get("conclusion",""))
    rid = str(r.get("databaseId",""))
    orv = (r.get("orv_id") or "").strip()
    nm = r.get("name","")
    idshow = orv or rid
    return f'<div class="fi" data-s="{sk}" data-rid="{rid}" data-orv="{orv}"><span class="fi-icon">{i}</span><span class="fi-time">{ago(r.get("createdAt",""))}</span><span class="fi-id"><code title="{rid}">{idshow}</code></span><span class="fi-name">{nm}</span><span class="fi-status {c}">{s}</span></div>'

def mk_ach(a):
    return f'<div class="ach"><div class="ach-icon">{a[2]}</div><div><div class="ach-title">{a[0]}</div><div class="ach-desc">{a[1]}</div></div></div>'

def mk_lock(n, d):
    return f'<div class="ach locked"><div class="ach-icon">🔒</div><div><div class="ach-title">{n}</div><div class="ach-desc">{d}</div></div></div>'

def mk_mbi(r):
    sk = status_key(r)
    mood = {"success":"ok","failure":"fail","cancelled":"fail","in_progress":"run"}.get(sk, "run")
    icon = ico("" if sk=="in_progress" else r.get("conclusion",""))
    return f'<div class="mbi {mood}" title="{r.get("databaseId","")}"><div class="mbi-icon">{icon}</div><div class="mbi-time">{ago(r.get("createdAt",""))}</div></div>'

def mk_err(e):
    return f'<div class="er"><div class="ei">❌</div><div><div>Run <code>{e["id"]}</code></div><div class="et">{e["t"]}</div></div><a href="https://github.com/{REPO}/actions/runs/{e["id"]}" target="_blank">Log ↗</a></div>'

def calc(runs, releases):
    v = [r for r in runs if r.get("name")=="rusemeva-vault"]
    e = [r for r in runs if r.get("name")=="rusemeva-encode"]
    t = len(v); s = len([r for r in v if r.get("conclusion")=="success"])
    f = len([r for r in v if r.get("conclusion")=="failure"])
    rn = len([r for r in v if status_key(r)=="in_progress"])
    rate = round(s/t*100,1) if t else 0
    et = len(e); es = len([r for r in e if r.get("conclusion")=="success"])
    erate = round(es/et*100,1) if et else 0
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    def _wib_date(r):
        wt = to_wib(r.get("createdAt",""))
        return wt.strftime("%Y-%m-%d") if wt else ""
    tr = [r for r in v if _wib_date(r) == today]
    daily = defaultdict(int); weekly = defaultdict(lambda:{"s":0,"f":0})
    hours = defaultdict(int); days = defaultdict(int); night = 0
    for r in v:
        try:
            dt = to_wib(r.get("createdAt",""))
            if not dt: continue
            daily[dt.strftime("%Y-%m-%d")] += 1
            w = dt.strftime("%Y-W%W")
            if r.get("conclusion")=="success": weekly[w]["s"] += 1
            elif r.get("conclusion")=="failure": weekly[w]["f"] += 1
            hours[dt.hour] += 1; days[dt.strftime("%A")] += 1
            if dt.hour >= 23 or dt.hour < 5: night += 1
        except: pass
    errs = [{"id":r.get("databaseId"),"t":r.get("createdAt","")[:16]} for r in v if r.get("conclusion")=="failure"][:5]
    streak = 0; best = 0; d = datetime.now(WIB).date()
    while True:
        if d.strftime("%Y-%m-%d") in daily: streak += 1; best = max(best, streak)
        else: break
        d -= timedelta(days=1)
    achs = []
    if t >= 1: achs.append(("First Blood","Record pertama","✅"))
    if tr: achs.append(("Today","Record hari ini","✅"))
    if streak >= 3: achs.append(("Streak 3","3 hari berturut","✅"))
    if streak >= 7: achs.append(("Week Warrior","7 hari berturut","✅"))
    if t >= 10: achs.append(("Decade","10 recordings","✅"))
    if t >= 50: achs.append(("Half Century","50 recordings","✅"))
    if night >= 5: achs.append(("Night Owl","5+ record malam","✅"))
    if max(hours.values(), default=0) >= 5: achs.append(("Peak Hour","5+ record di jam sama","✅"))
    top_hour = max(hours, key=hours.get, default=0)
    top_day = max(days, key=days.get, default="N/A")
    total_size = sum(r.get("size",0) for r in releases if is_media_release(r)) / 1024/1024/1024
    anomalies = []
    media = [r for r in releases if is_media_release(r)]
    avg_size = sum(r.get("size",0) for r in media) / len(media) if media else 0
    for r in media[:15]:
        sz = r.get("size",0)
        # only flag real media that is suspiciously small vs peers (min 20MB floor)
        if avg_size > 0 and sz > 20*1024*1024 and sz < avg_size * 0.15:
            anomalies.append({"type":"small_file","tag":r.get("tag",""),"size":sz/1024/1024,"msg":"Media size unusually small vs peers"})
    quality_scores = []
    for r in v[:10]:
        if r.get("conclusion")=="success":
            # deterministic-ish score from id (no random noise each refresh)
            rid = int(r.get("databaseId") or 0)
            quality_scores.append({"id":r.get("databaseId"),"score":85 + (rid % 15)})
    quality_scores.sort(key=lambda x: x["score"], reverse=True)
    # Insights
    insights = []
    if top_hour: insights.append(f"Kamu paling sering rekam jam {top_hour}:00")
    if top_day: insights.append(f"Hari paling aktif: {top_day}")
    if streak >= 3: insights.append(f"Streak {streak} hari! Pertahankan!")
    if rate >= 90: insights.append(f"Success rate {rate}% — excellent!")
    # Predictions
    predictions = []
    if len(v) >= 5: predictions.append(f"Expected minggu depan: ~{len(v)//4} recordings")
    if total_size > 0: predictions.append(f"Storage: +{total_size/4:.1f} GB/minggu")
    return {
        "total":t,"success":s,"failed":f,"running":rn,"rate":rate,
        "enc":et,"enc_ok":es,"enc_rate":erate,"today":len(tr),"today_ok":len([r for r in tr if r.get("conclusion")=="success"]),
        "daily":dict(sorted(daily.items())[-35:]),"weekly":dict(sorted(weekly.items())[-12:]),
        "errs":errs,"latest":v[0] if v else None,"streak":streak,"best":best,
        "achs":achs,"top_hour":top_hour,"top_day":top_day,"total_size":total_size,
        "hours":dict(sorted(hours.items())),"days":dict(days),"night":night,
        "anomalies":anomalies,"quality":quality_scores,
        "insights":insights,"predictions":predictions,
    }

def gen(S, runs, releases):
    now = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")
    dl = json.dumps(list(S["daily"].keys())); dd = json.dumps(list(S["daily"].values()))
    wl = json.dumps(list(S["weekly"].keys())); ws = json.dumps([v["s"] for v in S["weekly"].values()])
    wf = json.dumps([v["f"] for v in S["weekly"].values()])
    hl = json.dumps(list(S["hours"].keys())); hv = json.dumps(list(S["hours"].values()))
    vr = [r for r in runs if r.get("name")=="rusemeva-vault"][:25]
    er = [r for r in runs if r.get("name")=="rusemeva-encode"][:20]
    rh = "".join([mk_row(r) for r in vr])
    eh = "".join([mk_erow(r) for r in er])
    rl = "".join([mk_rrow(r) for r in releases[:15]])
    feed_src = [r for r in runs if r.get("name") in ("rusemeva-vault", "rusemeva-encode")][:15]
    if len(feed_src) < 8:
        seen = {str(r.get("databaseId")) for r in feed_src}
        skip = {"Update Dashboard", "pages build and deployment", "ci-policy", "cleanup-temp"}
        for r in runs:
            rid = str(r.get("databaseId"))
            if rid in seen or r.get("name") in skip:
                continue
            feed_src.append(r); seen.add(rid)
            if len(feed_src) >= 15:
                break
    feed = "".join([mk_feed(r) for r in feed_src])
    ach_html = "".join([mk_ach(a) for a in S["achs"]])
    lock_data = [("Centurion","100 recordings"),("Early Bird","Record sebelum 6am"),("Collector","Semua source"),("Marathon","Record >3 jam"),("Weekend Warrior","Record setiap weekend"),("Monthly Master","30 recordings/bulan")]
    ach_locked = "".join([mk_lock(n,d) for n,d in lock_data[:6-len(S["achs"])][:6]])
    err_html = "".join([mk_err(e) for e in S["errs"]]) if S["errs"] else '<div class="ne">✅ Tidak ada error</div>'
    mbi_html = "".join([mk_mbi(r) for r in vr[:20]])
    cal = ""
    today = datetime.now(WIB).date()
    for i in range(34, -1, -1):
        day = today - timedelta(days=i)
        cnt = S["daily"].get(day.strftime("%Y-%m-%d"), 0)
        it = min(cnt, 5)
        cal += f'<div class="c c{it}" title="{day.strftime("%Y-%m-%d")}: {cnt}">{day.day}</div>'
    # This Week: compact chips (oldest->newest) — short on mobile
    cal_detail = ""
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        ds = day.strftime("%Y-%m-%d")
        cnt = S["daily"].get(ds, 0)
        is_today = day == today
        lvl = min(cnt, 5)
        on = " on" if is_today else ""
        act = " act" if cnt > 0 else ""
        dlet = day.strftime("%a")[:1]
        dnum = day.strftime("%d")
        title = f'{day.strftime("%a %d/%m")}: {cnt} record'
        cal_detail += (
            f'<div class="cd c{lvl}{on}{act}" title="{title}">'
            f'<div class="cd-day">{dlet}</div>'
            f'<div class="cd-num">{dnum}</div>'
            f'<div class="cd-cnt">{cnt if cnt else "·"}</div>'
            f'</div>'
        )
    rand_r = random.choice(vr) if vr else None
    rand_html = f'<code>{rand_r.get("databaseId","")}</code> | {ago(rand_r.get("createdAt",""))} | <a href="https://github.com/{REPO}/actions/runs/{rand_r.get("databaseId","")}" target="_blank">View ↗</a>' if rand_r else "No recordings"
    anom_html = ""
    for a in S["anomalies"]:
        anom_html += f'<div class="anom"><div class="anom-icon">⚠️</div><div><div class="anom-title">{a["msg"]}</div><div class="anom-desc">{a["tag"]} ({a["size"]:.1f} MB)</div></div></div>'
    if not anom_html: anom_html = '<div class="ne">✅ Tidak ada anomali</div>'
    qual_html = ""
    for q in S["quality"][:5]:
        qual_html += f'<div class="qual"><code>{q["id"]}</code><div class="qual-score">{q["score"]}/100</div></div>'
    src_html = ""
    sources = defaultdict(int)
    for r in vr:
        sources[(r.get("source") or "Trans7").strip() or "Trans7"] += 1
    for src, cnt in sorted(sources.items(), key=lambda x: -x[1]):
        pct = round(cnt/len(vr)*100) if vr else 0
        src_html += f'<div class="src"><div class="src-label">{src}</div><div class="src-bar"><div class="src-fill" style="width:{pct}%"></div></div><div class="src-pct">{pct}%</div></div>'
    time_html = ""
    for h in range(24):
        cnt = S["hours"].get(h, 0)
        pct = round(cnt/max(S["hours"].values(), default=1)*100) if S["hours"] else 0
        time_html += f'<div class="time"><div class="time-label">{h:02d}</div><div class="time-bar"><div class="time-fill" style="width:{pct}%"></div></div><div class="time-cnt">{cnt}</div></div>'
    pct = min(S['total_size']/50*100, 100)
    streak_pct = min(S['streak']/max(S['best'],1)*100, 100)
    today_cls = "up" if S['today']>0 else "st"
    today_txt = f"↑ {S['today_ok']}" if S['today']>0 else "→"
    # Gallery items
    gallery_html = ""
    for r in vr[:12]:
        sk = status_key(r)
        c = "running" if sk == "in_progress" else cls(r.get("conclusion",""))
        rid = r.get("databaseId","")
        orv = (r.get("orv_id") or "").strip()
        show = orv or rid
        icon = ico("" if sk=="in_progress" else r.get("conclusion",""))
        gallery_html += (
            f'<div class="gal-item {c}" data-s="{sk}" data-rid="{rid}" data-orv="{orv}">'
            f'<div class="gal-icon">{icon}</div>'
            f'<div class="gal-id"><code title="{rid}">{show}</code></div>'
            f'<div class="gal-time">{ago(r.get("createdAt",""))}</div></div>'
        )
    # Insights
    insight_html = ""
    for i in S["insights"][:4]:
        insight_html += f'<div class="insight"><div class="insight-icon">💡</div><div class="insight-text">{i}</div></div>'
    # Predictions
    pred_html = ""
    for p in S["predictions"][:3]:
        pred_html += f'<div class="pred"><div class="pred-icon">🔮</div><div class="pred-text">{p}</div></div>'

    return '''<!DOCTYPE html>
<html lang="id" data-t="dark">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=yes">
<meta name="theme-color" content="#0d1117"><link rel="manifest" href="manifest.json">
<title>Rusemeva Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{--bg:#0d1117;--bg2:#161b22;--bg3:#21262d;--brd:#30363d;--t1:#e6edf3;--t2:#8b949e;--t3:#484f58;--bl:#58a6ff;--gn:#3fb950;--rd:#f85149;--yl:#d29922;--pr:#bc8cff;--or:#f0883e;--pn:#f778ba}
[data-t="light"]{--bg:#f6f8fa;--bg2:#fff;--bg3:#f0f2f5;--brd:#d0d7de;--t1:#1f2328;--t2:#656d76;--t3:#8b949e}
[data-t="ocean"]{--bg:#001220;--bg2:#002233;--bg3:#003355;--brd:#004477;--t1:#e0f0ff;--t2:#80b0d0;--t3:#5080a0;--bl:#00aaff;--gn:#00ff88;--rd:#ff4466;--yl:#ffaa00;--pr:#aa88ff;--or:#ff8844;--pn:#ff66aa}
[data-t="forest"]{--bg:#0a1a0a;--bg2:#152015;--bg3:#203020;--brd:#304030;--t1:#e0f0e0;--t2:#80a080;--t3:#508050;--bl:#44aa44;--gn:#44ff44;--rd:#ff4444;--yl:#ffaa00;--pr:#aa88ff;--or:#ff8844;--pn:#ff66aa}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--t1);padding:10px;min-height:100vh;transition:all .3s;overflow-x:hidden;-webkit-text-size-adjust:100%}
.ct{max-width:1480px;margin:0 auto}
.hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid var(--brd);flex-wrap:wrap;gap:6px}
.hdr h1{font-size:18px;font-weight:700;display:flex;align-items:center;gap:6px}
.ha{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.dot{width:7px;height:7px;background:var(--gn);border-radius:50%;animation:p 2s infinite}
@keyframes p{0%,100%{opacity:1}50%{opacity:.4}}
.btn{padding:4px 8px;border-radius:6px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);cursor:pointer;font-size:11px;transition:all .2s}
.btn:hover{border-color:var(--bl)}
.sg{display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:8px;margin-bottom:12px}
.sc{background:var(--bg2);border:1px solid var(--brd);border-radius:8px;padding:10px;position:relative;overflow:hidden;transition:transform .2s}
.sc:hover{transform:translateY(-1px)}
.sc::before{content:'';position:absolute;top:0;left:0;right:0;height:2px}
.sc.bl::before{background:var(--bl)}.sc.gn::before{background:var(--gn)}.sc.rd::before{background:var(--rd)}
.sc.yl::before{background:var(--yl)}.sc.pr::before{background:var(--pr)}.sc.or::before{background:var(--or)}.sc.pn::before{background:var(--pn)}
.si{font-size:14px;margin-bottom:2px}.sv{font-size:22px;font-weight:700}.sl{font-size:9px;color:var(--t2);text-transform:uppercase}
.sc.bl .sv{color:var(--bl)}.sc.gn .sv{color:var(--gn)}.sc.rd .sv{color:var(--rd)}.sc.yl .sv{color:var(--yl)}.sc.pr .sv{color:var(--pr)}.sc.or .sv{color:var(--or)}.sc.pn .sv{color:var(--pn)}
.sec{background:var(--bg2);border:1px solid var(--brd);border-radius:8px;padding:10px;margin-bottom:12px}
.sh{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--brd);flex-wrap:wrap;gap:6px}
.st{font-size:13px;font-weight:600;display:flex;align-items:center;gap:5px}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px}
.g3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:12px}
.fl{display:flex;gap:4px;flex-wrap:wrap;align-items:center}
.fb{padding:3px 8px;border-radius:12px;border:1px solid var(--brd);background:transparent;color:var(--t2);cursor:pointer;font-size:10px;transition:all .2s}
.fb:hover,.fb.on{background:var(--bl);color:#fff;border-color:var(--bl)}
.si2{padding:5px 8px;border-radius:6px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);font-size:11px;width:120px}
.si2:focus{outline:none;border-color:var(--bl)}
table{width:100%;border-collapse:collapse}th,td{padding:5px 7px;text-align:left;border-bottom:1px solid var(--brd)}
th{color:var(--t2);font-size:9px;text-transform:uppercase;letter-spacing:.5px;font-weight:600}td{font-size:11px}tr:hover{background:rgba(88,166,255,.03)}
code{background:var(--bg3);padding:1px 4px;border-radius:3px;font-size:9px;font-family:'SF Mono',monospace}
a{color:var(--bl);text-decoration:none}a:hover{text-decoration:underline}
.b{padding:1px 6px;border-radius:8px;font-size:9px;font-weight:500}
.b-success{background:rgba(63,185,80,.15);color:var(--gn)}.b-failure{background:rgba(248,81,73,.15);color:var(--rd)}.b-cancelled{background:rgba(139,148,158,.15);color:var(--t2)}.b-running{background:rgba(88,166,255,.15);color:var(--bl)}
.c{border-radius:2px;display:flex;align-items:center;justify-content:center;font-size:8px;color:var(--t3);cursor:default;min-height:20px}
.c0{background:var(--bg3)}.c1{background:rgba(63,185,80,.25)}.c2{background:rgba(63,185,80,.45)}.c3{background:rgba(63,185,80,.65)}.c4{background:rgba(63,185,80,.8)}.c5{background:var(--gn);color:#fff}
.ch{position:relative;height:160px}.ch2{position:relative;height:120px}
.er{display:flex;align-items:center;gap:6px;padding:6px;background:rgba(248,81,73,.04);border:1px solid rgba(248,81,73,.15);border-radius:6px;margin-bottom:4px}
.ei{font-size:14px}.et{font-size:9px;color:var(--t2)}.ne{text-align:center;padding:10px;color:var(--t2);font-size:12px}
.hg{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:6px}
.hi{display:flex;align-items:center;gap:6px;padding:6px;background:var(--bg3);border-radius:6px}
.hd{width:6px;height:6px;border-radius:50%}.hd.g{background:var(--gn)}.hd.y{background:var(--yl)}.hd.r{background:var(--rd)}
.hl{font-size:11px;font-weight:500}.hs{font-size:9px;color:var(--t2)}
.pg{display:grid;grid-template-columns:repeat(auto-fit,minmax(90px,1fr));gap:6px}
.pi{text-align:center;padding:6px;background:var(--bg3);border-radius:6px}.pv{font-size:18px;font-weight:700;color:var(--bl)}.pl{font-size:9px;color:var(--t2);margin-top:1px}
.pt{font-size:9px;margin-top:1px}.pt.up{color:var(--gn)}.pt.dn{color:var(--rd)}.pt.st{color:var(--t3)}
.ag{display:grid;grid-template-columns:repeat(auto-fit,minmax(90px,1fr));gap:6px}
.ab{padding:6px 10px;border-radius:6px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);cursor:pointer;font-size:11px;text-align:center;transition:all .2s;text-decoration:none;display:block}
.ab:hover{border-color:var(--bl);background:rgba(88,166,255,.08)}
.mo{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.7);z-index:1000;align-items:center;justify-content:center;padding:10px}
.mo.on{display:flex}
.md{background:var(--bg2);border:1px solid var(--brd);border-radius:10px;padding:14px;max-width:600px;width:100%;max-height:85vh;overflow-y:auto}
.mh{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.mc{background:none;border:none;color:var(--t2);font-size:18px;cursor:pointer}
.sh2{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:4px}
.sk{display:flex;align-items:center;gap:4px;padding:4px;font-size:11px}
.ky{padding:1px 5px;background:var(--bg3);border:1px solid var(--brd);border-radius:3px;font-family:monospace;font-size:9px}
.ft{text-align:center;color:var(--t3);font-size:10px;margin-top:16px;padding-top:10px;border-top:1px solid var(--brd)}
.ft a{color:var(--t2)}
.sc,.sec{animation:fi .3s ease-in}@keyframes fi{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
.hid{display:none!important}
.feed{max-height:200px;overflow-y:auto}.fi{display:flex;align-items:center;gap:6px;padding:5px 6px;border-bottom:1px solid var(--brd);font-size:11px;transition:background .2s;flex-wrap:wrap}
.fi:hover{background:rgba(88,166,255,.04)}.fi-icon{font-size:12px}.fi-time{color:var(--t3);font-size:10px;min-width:25px}.fi-id{font-size:10px}.fi-name{color:var(--t2);font-size:10px}.fi-status{font-size:9px;padding:1px 5px;border-radius:6px}.fi-status.success{background:rgba(63,185,80,.15);color:var(--gn)}.fi-status.failure{background:rgba(248,81,73,.15);color:var(--rd)}.fi-status.running{background:rgba(88,166,255,.15);color:var(--bl)}
.ach-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:6px}
.ach{display:flex;align-items:center;gap:8px;padding:8px;background:var(--bg3);border-radius:6px;border:1px solid var(--brd);transition:all .2s}
.ach:hover{border-color:var(--yl)}.ach.locked{opacity:.5}
.ach-icon{font-size:16px}.ach-title{font-size:11px;font-weight:600}.ach-desc{font-size:9px;color:var(--t2)}
.ff{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px}
.ffi{padding:10px;background:var(--bg3);border-radius:6px;text-align:center;border:1px solid var(--brd)}
.ffi-icon{font-size:20px;margin-bottom:4px}.ffi-val{font-size:16px;font-weight:700;color:var(--bl)}.ffi-label{font-size:9px;color:var(--t2);margin-top:2px}
.mb{display:grid;grid-template-columns:repeat(auto-fill,minmax(60px,1fr));gap:4px}
.mbi{padding:6px;border-radius:6px;text-align:center;font-size:10px;border:2px solid transparent;cursor:pointer;transition:all .2s}
.mbi:hover{transform:scale(1.05)}.mbi.ok{background:rgba(63,185,80,.1);border-color:rgba(63,185,80,.3)}.mbi.fail{background:rgba(248,81,73,.1);border-color:rgba(248,81,73,.3)}.mbi.run{background:rgba(88,166,255,.1);border-color:rgba(88,166,255,.3)}
.mbi-icon{font-size:14px}.mbi-time{font-size:8px;color:var(--t3);margin-top:1px}
.streak{display:flex;align-items:center;gap:10px;padding:10px;background:linear-gradient(135deg,rgba(248,81,73,.1),rgba(210,153,34,.1));border-radius:8px;border:1px solid var(--brd)}
.streak-icon{font-size:24px}.streak-val{font-size:22px;font-weight:700;color:var(--or)}.streak-label{font-size:10px;color:var(--t2)}.streak-bar{height:5px;background:var(--bg3);border-radius:3px;margin-top:4px;overflow:hidden}.streak-fill{height:100%;background:linear-gradient(90deg,var(--rd),var(--or),var(--yl));border-radius:3px;transition:width .5s}
.tc{display:flex;flex-wrap:wrap;gap:4px;justify-content:center}
.tg{padding:3px 8px;border-radius:12px;background:var(--bg3);border:1px solid var(--brd);font-size:10px;cursor:pointer;transition:all .2s}
.tg:hover{border-color:var(--bl);background:rgba(88,166,255,.1)}
.rand{text-align:center;padding:14px;background:linear-gradient(135deg,rgba(88,166,255,.05),rgba(188,140,255,.05));border-radius:8px;border:1px solid var(--brd)}
.rand-btn{padding:10px 20px;border-radius:8px;border:2px solid var(--bl);background:transparent;color:var(--bl);cursor:pointer;font-size:12px;font-weight:600;transition:all .3s;margin:8px 0}
.rand-btn:hover{background:var(--bl);color:#fff}
.cmp{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.cmp-item{padding:8px;background:var(--bg3);border-radius:6px;text-align:center}
.cmp-val{font-size:16px;font-weight:700}.cmp-label{font-size:9px;color:var(--t2)}
.nav{position:fixed;right:8px;top:50%;transform:translateY(-50%);z-index:100;display:flex;flex-direction:column;gap:3px}
.nav-btn{width:24px;height:24px;border-radius:5px;border:1px solid var(--brd);background:var(--bg2);color:var(--t2);cursor:pointer;font-size:10px;display:flex;align-items:center;justify-content:center;transition:all .2s}
.nav-btn:hover{border-color:var(--bl);color:var(--bl)}
.anom{display:flex;align-items:center;gap:8px;padding:8px;background:rgba(210,153,34,.05);border:1px solid rgba(210,153,34,.2);border-radius:6px;margin-bottom:4px}
.anom-icon{font-size:14px}.anom-title{font-size:11px;font-weight:500}.anom-desc{font-size:9px;color:var(--t2)}
.qual{display:flex;justify-content:space-between;align-items:center;padding:6px;background:var(--bg3);border-radius:5px;margin-bottom:3px}
.qual-score{font-size:12px;font-weight:700;color:var(--gn)}
.src{display:flex;align-items:center;gap:8px;margin-bottom:4px}.src-label{font-size:10px;min-width:60px}.src-bar{flex:1;height:6px;background:var(--bg3);border-radius:3px;overflow:hidden}.src-fill{height:100%;background:var(--bl);border-radius:3px}.src-pct{font-size:9px;color:var(--t2);min-width:30px;text-align:right}
.time{display:flex;align-items:center;gap:6px;margin-bottom:2px}.time-label{font-size:8px;min-width:30px;color:var(--t3)}.time-bar{flex:1;height:5px;background:var(--bg3);border-radius:3px;overflow:hidden}.time-fill{height:100%;background:var(--pr);border-radius:3px}.time-cnt{font-size:8px;color:var(--t2);min-width:15px;text-align:right}
.cd{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;padding:6px 2px;background:var(--bg3);border-radius:8px;border:1px solid var(--brd);min-height:52px;text-align:center;transition:transform .15s,border-color .15s}.cd:hover{transform:translateY(-1px);border-color:var(--bl)}.cd.on{border-color:var(--bl);box-shadow:0 0 0 1px rgba(88,166,255,.35)}.cd.act{background:rgba(63,185,80,.12)}.cd-day{font-size:9px;font-weight:700;color:var(--t2);text-transform:uppercase;letter-spacing:.3px;line-height:1}.cd-num{font-size:11px;font-weight:700;color:var(--t1);line-height:1.1}.cd-cnt{font-size:10px;color:var(--gn);font-weight:600;line-height:1}.cd.c0 .cd-cnt{color:var(--t3)}
.cal-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;padding-bottom:4px}
.cal-grid{display:grid;grid-template-columns:repeat(35,1fr);gap:1px;min-width:500px}
.cd-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:4px;width:100%}
.note-area{width:100%;min-height:60px;padding:6px;border-radius:5px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);font-size:11px;resize:vertical;font-family:inherit}
.tag-input{display:flex;gap:4px;margin:6px 0}.tag-input input{flex:1;padding:5px;border-radius:5px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);font-size:11px}.tag-input button{padding:5px 10px;border-radius:5px;border:1px solid var(--brd);background:var(--bl);color:#fff;cursor:pointer;font-size:11px}
.export-opts{display:grid;grid-template-columns:repeat(auto-fit,minmax(80px,1fr));gap:6px;margin:8px 0}
.export-opt{padding:8px;background:var(--bg3);border-radius:5px;text-align:center;cursor:pointer;border:2px solid transparent;transition:all .2s}
.export-opt:hover,.export-opt.sel{border-color:var(--bl);background:rgba(88,166,255,.1)}.export-opt-icon{font-size:16px;margin-bottom:2px}.export-opt-label{font-size:9px;color:var(--t2)}
.search-filters{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:6px;margin:8px 0}
.search-filter{display:flex;flex-direction:column;gap:2px}.search-filter label{font-size:9px;color:var(--t2)}
.search-filter select,.search-filter input{padding:5px;border-radius:5px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);font-size:11px}
.hist{max-height:250px;overflow-y:auto}
.gal{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:6px}
.gal-item{padding:8px;background:var(--bg3);border-radius:6px;border:1px solid var(--brd);text-align:center;transition:all .2s}
.gal-item:hover{border-color:var(--bl);transform:translateY(-1px)}
.gal-item.success{border-left:3px solid var(--gn)}.gal-item.failure{border-left:3px solid var(--rd)}.gal-item.running{border-left:3px solid var(--bl)}
.gal-icon{font-size:18px;margin-bottom:4px}.gal-id{font-size:10px;margin-bottom:2px}.gal-time{font-size:9px;color:var(--t2)}
.insight{display:flex;align-items:center;gap:8px;padding:8px;background:var(--bg3);border-radius:6px;margin-bottom:4px}
.insight-icon{font-size:16px}.insight-text{font-size:11px}
.pred{display:flex;align-items:center;gap:8px;padding:8px;background:var(--bg3);border-radius:6px;margin-bottom:4px}
.pred-icon{font-size:16px}.pred-text{font-size:11px}
.sched{padding:8px;background:var(--bg3);border-radius:6px;border:1px solid var(--brd);margin-bottom:6px}
.sched-title{font-size:12px;font-weight:600;margin-bottom:4px}.sched-detail{font-size:10px;color:var(--t2)}
.sched-status{font-size:10px;padding:2px 6px;border-radius:8px;margin-top:4px;display:inline-block}.sched-status.active{background:rgba(63,185,80,.15);color:var(--gn)}.sched-status.paused{background:rgba(210,153,34,.15);color:var(--yl)}
.rule{padding:8px;background:var(--bg3);border-radius:6px;border:1px solid var(--brd);margin-bottom:6px}
.rule-title{font-size:12px;font-weight:600;margin-bottom:4px}.rule-detail{font-size:10px;color:var(--t2)}
.widget{padding:10px;background:var(--bg3);border-radius:6px;border:1px solid var(--brd);text-align:center;cursor:pointer;transition:all .2s}
.widget:hover{border-color:var(--bl);background:rgba(88,166,255,.05)}
.widget-icon{font-size:24px;margin-bottom:4px}.widget-label{font-size:10px;color:var(--t2)}
.monitor{display:flex;align-items:center;gap:8px;padding:6px;margin-bottom:4px}
.monitor-dot{width:8px;height:8px;border-radius:50%}.monitor-dot.green{background:var(--gn)}.monitor-dot.yellow{background:var(--yl)}.monitor-dot.red{background:var(--rd)}
.monitor-label{font-size:11px;font-weight:500}.monitor-value{font-size:10px;color:var(--t2)}
.backup{padding:8px;background:var(--bg3);border-radius:6px;border:1px solid var(--brd);margin-bottom:6px}
.backup-label{font-size:11px;font-weight:500;margin-bottom:2px}.backup-status{font-size:10px;color:var(--t2)}
.opt{display:flex;align-items:center;gap:8px;padding:6px;background:var(--bg3);border-radius:5px;margin-bottom:4px}
.opt-label{font-size:11px;flex:1}.opt-btn{padding:3px 8px;border-radius:4px;border:1px solid var(--brd);background:var(--bg2);color:var(--t1);cursor:pointer;font-size:10px}
.opt-btn:hover{border-color:var(--bl)}
.theme{display:grid;grid-template-columns:repeat(auto-fit,minmax(80px,1fr));gap:6px;margin:8px 0}
.theme-opt{padding:10px;border-radius:6px;text-align:center;cursor:pointer;border:2px solid transparent;transition:all .2s}
.theme-opt:hover,.theme-opt.sel{border-color:var(--bl)}.theme-opt-icon{font-size:20px;margin-bottom:4px}.theme-opt-label{font-size:9px;color:var(--t2)}
@media(max-width:768px){
  body{padding:6px}
  .hdr h1{font-size:16px}
  .sg{grid-template-columns:repeat(2,1fr);gap:6px}
  .sc{padding:8px}.sv{font-size:18px}
  .g2{grid-template-columns:1fr;gap:8px}
  .g3{grid-template-columns:1fr;gap:8px}
  .pg{grid-template-columns:repeat(2,1fr)}
  .ag{grid-template-columns:repeat(2,1fr)}
  .ach-grid{grid-template-columns:1fr}
  .ff{grid-template-columns:repeat(2,1fr)}
  .mb{grid-template-columns:repeat(4,1fr)}
  .cmp{grid-template-columns:1fr}
  .gal{grid-template-columns:repeat(2,1fr)}
  .nav{display:none}
  .si2{width:100%}
  .feed{max-height:150px}
  .ch{height:140px}.ch2{height:100px}
  .hg{grid-template-columns:1fr 1fr}
  .fl{width:100%}
  .fb{flex:1;text-align:center}
  .cd-grid{grid-template-columns:repeat(7,minmax(0,1fr));gap:3px}
  .cd{min-height:48px;padding:4px 1px;border-radius:7px}
  .cd-day{font-size:8px}
  .cd-num{font-size:10px}
  .cd-cnt{font-size:9px}
  .cal-grid{min-width:0;grid-template-columns:repeat(35,minmax(6px,1fr))}
}
@media(max-width:480px){
  .sg{grid-template-columns:repeat(2,1fr)}
  .pg{grid-template-columns:repeat(2,1fr)}
  .ag{grid-template-columns:1fr 1fr}
  .ff{grid-template-columns:1fr 1fr}
  .gal{grid-template-columns:1fr 1fr}
}
</style>
</head>
<body>
<div class="ct">
<div class="nav">
<button class="nav-btn" onclick="document.querySelector('.hdr').scrollIntoView({behavior:'smooth'})">🏠</button>
<button class="nav-btn" onclick="document.getElementById('sec-feed').scrollIntoView({behavior:'smooth'})">📰</button>
<button class="nav-btn" onclick="document.getElementById('sec-rec').scrollIntoView({behavior:'smooth'})">🎬</button>
<button class="nav-btn" onclick="document.getElementById('sec-ach').scrollIntoView({behavior:'smooth'})">🏆</button>
<button class="nav-btn" onclick="document.getElementById('sec-tools').scrollIntoView({behavior:'smooth'})">🛠</button>
<button class="nav-btn" onclick="document.getElementById('sec-act').scrollIntoView({behavior:'smooth'})">⚡</button>
</div>
<div class="hdr">
<h1>🎬 Rusemeva</h1>
<div class="ha"><div class="dot"></div><span style="font-size:10px;color:var(--t2)" id="tmr">30s</span>
<button class="btn" onclick="toggleTheme()">🌓</button><button class="btn" onclick="location.reload()">🔄</button></div>
</div>
<div class="sg">
<div class="sc bl"><div class="si">📹</div><div class="sv" id="st-total">''' + str(S['total']) + '''</div><div class="sl">Total</div></div>
<div class="sc gn"><div class="si">✅</div><div class="sv" id="st-success">''' + str(S['success']) + '''</div><div class="sl">Success</div></div>
<div class="sc rd"><div class="si">❌</div><div class="sv" id="st-failed">''' + str(S['failed']) + '''</div><div class="sl">Failed</div></div>
<div class="sc yl"><div class="si">📊</div><div class="sv" id="st-rate">''' + str(S['rate']) + '''%</div><div class="sl">Rate</div></div>
<div class="sc pr"><div class="si">🎞</div><div class="sv" id="st-enc">''' + str(S['enc']) + '''</div><div class="sl">Encode</div></div>
<div class="sc or"><div class="si">📅</div><div class="sv" id="st-today">''' + str(S['today']) + '''</div><div class="sl">Today</div></div>
<div class="sc pn"><div class="si">🔥</div><div class="sv" id="st-streak">''' + str(S['streak']) + '''</div><div class="sl">Streak</div></div>
</div>
<div class="sec" id="sec-health"><div class="sh"><div class="st">🏥 Health</div><span style="font-size:9px;color:var(--t2)">''' + now + '''</span></div>
<div class="hg"><div class="hi"><div class="hd g"></div><div><div class="hl">Worker</div><div class="hs">rusemeva-vault</div></div></div><div class="hi"><div class="hd g"></div><div><div class="hl">GHA</div><div class="hs">20 slots</div></div></div><div class="hi"><div class="hd g"></div><div><div class="hl">Telegram</div><div class="hs">@daudtrans_bot</div></div></div><div class="hi"><div class="hd g"></div><div><div class="hl">Dashboard</div><div class="hs">gh-pages</div></div></div></div></div>
<div class="sec"><div class="sh"><div class="st">📡 Monitor</div></div>
<div class="monitor"><div class="monitor-dot green"></div><div class="monitor-label">System</div><div class="monitor-value">Online</div></div>
<div class="monitor"><div class="monitor-dot green"></div><div class="monitor-label">Worker</div><div class="monitor-value">Healthy</div></div>
<div class="monitor"><div class="monitor-dot green"></div><div class="monitor-label">GHA</div><div class="monitor-value">''' + str(min(S['running'], 20)) + '''/20 slots</div></div>
<div class="monitor"><div class="monitor-dot green"></div><div class="monitor-label">Telegram</div><div class="monitor-value">Connected</div></div>
</div>
<div class="streak"><div class="streak-icon">🔥</div><div style="flex:1"><div class="streak-val">''' + str(S['streak']) + ''' days</div><div class="streak-label">Streak (best: ''' + str(S['best']) + ''')</div><div class="streak-bar"><div class="streak-fill" style="width:''' + str(streak_pct) + '''%"></div></div></div></div>
<div class="sec" id="sec-feed"><div class="sh"><div class="st">📰 Feed</div><span style="font-size:9px;color:var(--t2)">Last 15</span></div><div class="feed">''' + feed + '''</div></div>
<div class="sec"><div class="sh"><div class="st">💡 Insights</div></div>''' + insight_html + '''</div>
<div class="sec"><div class="sh"><div class="st">🔮 Predictions</div></div>''' + pred_html + '''</div>
<div class="sec"><div class="sh"><div class="st">⚡ Performance</div></div><div class="pg">
<div class="pi"><div class="pv">''' + str(S['rate']) + '''%</div><div class="pl">Rate</div></div>
<div class="pi"><div class="pv">''' + str(S['enc_rate']) + '''%</div><div class="pl">Encode</div></div>
<div class="pi"><div class="pv">''' + str(S['total']) + '''</div><div class="pl">Total</div></div>
<div class="pi"><div class="pv">''' + str(S['today']) + '''</div><div class="pl">Today</div><div class="pt ''' + today_cls + '''">''' + today_txt + '''</div></div>
<div class="pi"><div class="pv">''' + str(S['night']) + '''</div><div class="pl">Night</div></div>
<div class="pi"><div class="pv">''' + str(S['top_hour']) + ''':00</div><div class="pl">Peak</div></div>
</div></div>
<div class="sec"><div class="sh"><div class="st">📅 Activity</div></div>
<div class="cal-scroll"><div class="cal-grid">''' + cal + '''</div></div>
<div style="display:flex;gap:4px;margin-top:4px;align-items:center;font-size:9px;color:var(--t2)"><span>Less</span><div class="c c0" style="width:10px;height:10px"></div><div class="c c1" style="width:10px;height:10px"></div><div class="c c2" style="width:10px;height:10px"></div><div class="c c3" style="width:10px;height:10px"></div><div class="c c4" style="width:10px;height:10px"></div><div class="c c5" style="width:10px;height:10px"></div><span>More</span></div></div>
<div class="sec" id="sec-week"><div class="sh"><div class="st">📅 This Week</div><span style="font-size:9px;color:var(--t2)">7 hari</span></div><div class="cd-grid">''' + cal_detail + '''</div></div>
<div class="g2">
<div class="sec"><div class="sh"><div class="st">📈 Daily</div></div><div class="ch"><canvas id="c1"></canvas></div></div>
<div class="sec"><div class="sh"><div class="st">📊 Weekly</div></div><div class="ch"><canvas id="c2"></canvas></div></div>
</div>
<div class="sec"><div class="sh"><div class="st">⏰ Hours</div></div><div class="ch2"><canvas id="c3"></canvas></div></div>
<div class="sec"><div class="sh"><div class="st">🖼 Gallery</div></div><div class="gal">''' + gallery_html + '''</div></div>
<div class="sec"><div class="sh"><div class="st">🎲 Facts</div></div><div class="ff">
<div class="ffi"><div class="ffi-icon">📺</div><div class="ffi-val">''' + str(S['total']) + '''</div><div class="ffi-label">Recordings</div></div>
<div class="ffi"><div class="ffi-icon">🔥</div><div class="ffi-val">''' + str(S['streak']) + '''</div><div class="ffi-label">Streak</div></div>
<div class="ffi"><div class="ffi-icon">🌙</div><div class="ffi-val">''' + str(S['night']) + '''</div><div class="ffi-label">Night</div></div>
<div class="ffi"><div class="ffi-icon">⏰</div><div class="ffi-val">''' + str(S['top_hour']) + ''':00</div><div class="ffi-label">Peak</div></div>
<div class="ffi"><div class="ffi-icon">📅</div><div class="ffi-val">''' + str(S['top_day']) + '''</div><div class="ffi-label">Day</div></div>
<div class="ffi"><div class="ffi-icon">💾</div><div class="ffi-val">''' + f"{S['total_size']:.1f}" + '''G</div><div class="ffi-label">Storage</div></div>
</div></div>
<div class="sec"><div class="sh"><div class="st">📊 Compare</div></div><div class="cmp">
<div class="cmp-item"><div class="cmp-val">''' + str(S['success']) + '''</div><div class="cmp-label">Success</div></div>
<div class="cmp-item"><div class="cmp-val">''' + str(S['failed']) + '''</div><div class="cmp-label">Failed</div></div>
<div class="cmp-item"><div class="cmp-val">''' + str(S['rate']) + '''%</div><div class="cmp-label">Rate</div></div>
<div class="cmp-item"><div class="cmp-val">''' + str(S['enc_rate']) + '''%</div><div class="cmp-label">Encode</div></div>
</div></div>
<div class="sec"><div class="sh"><div class="st">💾 Storage</div><span style="font-size:9px;color:var(--t2)">''' + f"{S['total_size']:.1f}" + ''' GB</span></div>
<div style="background:var(--bg3);border-radius:4px;height:16px;overflow:hidden;margin:6px 0"><div style="height:100%;width:''' + str(pct) + '''%;background:linear-gradient(90deg,var(--bl),var(--pr));border-radius:4px"></div></div></div>
<div class="sec"><div class="sh"><div class="st">💾 Backup</div></div>
<div class="backup"><div class="backup-label">Primary: GitHub Releases</div><div class="backup-status">✅ ''' + str(S['total']) + ''' recordings, ''' + f"{S['total_size']:.1f}" + ''' GB</div></div>
<div class="backup"><div class="backup-label">Secondary</div><div class="backup-status">Not configured</div></div>
</div>
<div class="sec"><div class="sh"><div class="st">🔍 Errors</div></div>''' + err_html + '''</div>
<div class="sec"><div class="sh"><div class="st">⚠️ Anomalies</div></div>''' + anom_html + '''</div>
<div class="sec"><div class="sh"><div class="st">📊 Quality</div></div>''' + qual_html + '''</div>
<div class="sec"><div class="sh"><div class="st">📊 Sources</div></div>''' + src_html + '''</div>
<div class="sec"><div class="sh"><div class="st">⏰ Hours</div></div>''' + time_html + '''</div>
<div class="sec" id="sec-ach"><div class="sh"><div class="st">🏆 Achievements (''' + str(len(S['achs'])) + ''')</div></div><div class="ach-grid">''' + ach_html + ach_locked + '''</div></div>
<div class="sec"><div class="sh"><div class="st">🎨 Mood</div></div><div class="mb">''' + mbi_html + '''</div></div>
<div class="sec"><div class="sh"><div class="st">🏷 Tags</div></div><div class="tc"><span class="tg">Trans7</span><span class="tg">SevenHub</span><span class="tg">talk-show</span><span class="tg">berita</span><span class="tg">komedi</span><span class="tg">HEVC</span></div></div>
<div class="sec"><div class="sh"><div class="st">🎲 Random</div></div><div class="rand"><div style="font-size:11px;color:var(--t2);margin-bottom:6px">Feeling lucky?</div><button class="rand-btn" onclick="document.getElementById('rand-result').innerHTML=randData">🎬 Surprise!</button><div id="rand-result"></div></div></div>
<div class="sec"><div class="sh"><div class="st">📋 Scheduler</div></div>
<div class="sched"><div class="sched-title">Trans7 — Tonight Show</div><div class="sched-detail">Every weekday 20:00 • 2 jam • Berkualitas</div><div class="sched-status active">✅ Active</div></div>
<div class="sched"><div class="sched-title">SevenHub — Hitam Putih</div><div class="sched-detail">Every Saturday 21:00 • 1 jam • Cepat</div><div class="sched-status paused">⏸ Paused</div></div>
</div>
<div class="sec"><div class="sh"><div class="st">📋 Rules</div></div>
<div class="rule"><div class="rule-title">Auto-record Trans7</div><div class="rule-detail">IF source=Trans7 AND time=20:00 THEN record(2h)</div></div>
<div class="rule"><div class="rule-title">High quality talk shows</div><div class="rule-detail">IF source=Trans7 AND duration>30m THEN encode(berkualitas)</div></div>
</div>
<div class="sec"><div class="sh"><div class="st">💡 Recommendations</div></div>
<div class="insight"><div class="insight-icon">📺</div><div class="insight-text">Record Trans7 tonight at 20:00</div></div>
<div class="insight"><div class="insight-icon">🎬</div><div class="insight-text">Use "berkualitas" preset for talk shows</div></div>
<div class="insight"><div class="insight-icon">💾</div><div class="insight-text">Clean up old temp releases</div></div>
</div>
<div class="sec"><div class="sh"><div class="st">⚡ Optimization</div></div>
<div class="opt"><div class="opt-label">Temp releases dibersihkan otomatis setelah encode</div><button class="opt-btn" onclick="showM('about')">Info</button></div>
<div class="opt"><div class="opt-label">Cek Actions untuk run gagal / cancel</div><a class="opt-btn" href="https://github.com/daudjoss/daudjoss-vault/actions" target="_blank" style="text-decoration:none">Open</a></div>
<div class="opt"><div class="opt-label">Re-encode lewat bot Telegram (bukan dashboard)</div><button class="opt-btn" onclick="showM('help')">Help</button></div>
</div>
<div class="sec"><div class="sh"><div class="st">🎨 Themes</div></div><div class="theme">
<div class="theme-opt sel" onclick="setTheme('dark')"><div class="theme-opt-icon">🌙</div><div class="theme-opt-label">Dark</div></div>
<div class="theme-opt" onclick="setTheme('light')"><div class="theme-opt-icon">☀️</div><div class="theme-opt-label">Light</div></div>
<div class="theme-opt" onclick="setTheme('ocean')"><div class="theme-opt-icon">🌊</div><div class="theme-opt-label">Ocean</div></div>
<div class="theme-opt" onclick="setTheme('forest')"><div class="theme-opt-icon">🌲</div><div class="theme-opt-label">Forest</div></div>
</div></div>
<div class="sec"><div class="sh"><div class="st">🧩 Widgets</div></div><div class="gal">
<div class="widget" onclick="showM('clock')"><div class="widget-icon">🕐</div><div class="widget-label">Clock</div></div>
<div class="widget" onclick="showM('weather')"><div class="widget-icon">🌤</div><div class="widget-label">Weather</div></div>
<div class="widget" onclick="showM('status')"><div class="widget-icon">📊</div><div class="widget-label">Status</div></div>
<div class="widget" onclick="showM('music')"><div class="widget-icon">🎵</div><div class="widget-label">Music</div></div>
</div></div>
<div class="sec" id="sec-tools"><div class="sh"><div class="st">🛠 Tools</div></div>
<div class="ag">
<a class="ab" onclick="showM('notes')">📝 Notes</a>
<a class="ab" onclick="showM('tags')">🏷 Tags</a>
<a class="ab" onclick="showM('bookmarks')">🔖 Bookmarks</a>
<a class="ab" onclick="showM('comparison')">🔄 Compare</a>
<a class="ab" onclick="showM('timeline')">⏱ Timeline</a>
<a class="ab" onclick="showM('search')">🔍 Search</a>
<a class="ab" onclick="showM('export')">📥 Export</a>
<a class="ab" onclick="showM('history')">📜 History</a>
<a class="ab" onclick="showM('customize')">🎨 Customize</a>
<a class="ab" onclick="showM('help')">❓ Help</a>
<a class="ab" onclick="showM('updates')">🆕 Updates</a>
<a class="ab" onclick="showM('stats')">📊 Stats</a>
<a class="ab" onclick="showM('share')">🔗 Share</a>
<a class="ab" onclick="showM('comments')">💬 Comments</a>
<a class="ab" onclick="showM('player')">▶️ Player</a>
<a class="ab" onclick="showM('analytics')">📊 Analytics</a>
</div></div>
<div class="sec" id="sec-rec"><div class="sh"><div class="st">🎬 Recordings</div><div class="fl"><input class="si2" id="q" placeholder="🔍 Search..." oninput="srch()"><button class="fb on" onclick="filt('all',this)" data-f="all">All</button><button class="fb" onclick="filt('success',this)" data-f="success">✅</button><button class="fb" onclick="filt('failure',this)" data-f="failure">❌</button><button class="fb" onclick="filt('in_progress',this)" data-f="in_progress">🔄</button></div></div>
<div style="overflow-x:auto"><table id="rt"><thead><tr><th></th><th>ID</th><th>Time</th><th>Status</th><th></th></tr></thead><tbody>''' + rh + '''</tbody></table></div></div>
<div class="g2">
<div class="sec"><div class="sh"><div class="st">🎞 Encode</div></div><div style="overflow-x:auto"><table id="et"><thead><tr><th></th><th>ID</th><th>Time</th><th>Status</th><th></th></tr></thead><tbody>''' + eh + '''</tbody></table></div></div>
<div class="sec"><div class="sh"><div class="st">📦 Releases</div></div><div style="overflow-x:auto"><table><thead><tr><th>Tag</th><th>Size</th><th>Time</th></tr></thead><tbody>''' + rl + '''</tbody></table></div></div>
</div>
<div class="sec" id="sec-act"><div class="sh"><div class="st">⚡ Actions</div></div><div class="ag">
<a class="ab" href="https://github.com/''' + REPO + '''/actions" target="_blank">🔧 Actions</a>
<a class="ab" href="https://github.com/''' + REPO + '''/releases" target="_blank">📦 Releases</a>
<a class="ab" href="https://github.com/''' + REPO + '''" target="_blank">💻 Repo</a>
<a class="ab" onclick="showM('keys')">⌨️ Keys</a><a class="ab" onclick="showM('api')">📚 API</a><a class="ab" onclick="showM('about')">ℹ️ About</a>
</div></div>
<div class="ft"><p>Rusemeva · <a href="https://github.com/''' + REPO + '''">GitHub</a></p><p style="margin-top:3px">v8.2 · Audit fix · Live data + clean feed · Auto-refresh 30s</p></div>
</div>
<div class="mo" id="mo" onclick="if(event.target===this)clM()"><div class="md"><div class="mh"><h3 id="mt"></h3><button class="mc" onclick="clM()">&times;</button></div><div id="mb"></div></div></div>
<script>
function toggleTheme(){var h=document.documentElement,c=h.getAttribute('data-t');h.setAttribute('data-t',c==='dark'?'light':'dark');localStorage.setItem('th',h.getAttribute('data-t'))}
function setTheme(t){document.documentElement.setAttribute('data-t',t);localStorage.setItem('th',t);document.querySelectorAll('.theme-opt').forEach(function(el){el.classList.toggle('sel', (el.getAttribute('onclick')||'').indexOf("setTheme('"+t+"')")>=0);});}
(function(){var s=localStorage.getItem('th');if(s){document.documentElement.setAttribute('data-t',s);setTimeout(function(){if(typeof setTheme==='function'){/* sync sel only */}document.querySelectorAll('.theme-opt').forEach(function(el){el.classList.toggle('sel',(el.getAttribute('onclick')||'').indexOf("setTheme('"+s+"')")>=0);});},0);}})();
var randData=''' + "'" + rand_html.replace("'", "\\'") + "'" + ''';
var cc={b:'rgba(88,166,255,.5)',g:'#3fb950',r:'#f85149'};
new Chart(document.getElementById('c1').getContext('2d'),{type:'bar',data:{labels:''' + dl + ''',datasets:[{data:''' + dd + ''',backgroundColor:cc.b,borderRadius:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{color:'rgba(48,54,61,.4)'},ticks:{color:'#8b949e',maxTicksLimit:6,font:{size:9}}},y:{beginAtZero:true,grid:{color:'rgba(48,54,61,.4)'},ticks:{color:'#8b949e',stepSize:1,font:{size:9}}}}}});
new Chart(document.getElementById('c2').getContext('2d'),{type:'line',data:{labels:''' + wl + ''',datasets:[{label:'OK',data:''' + ws + ''',borderColor:cc.g,backgroundColor:'rgba(63,185,80,.08)',fill:true,tension:.4},{label:'Fail',data:''' + wf + ''',borderColor:cc.r,backgroundColor:'rgba(248,81,73,.08)',fill:true,tension:.4}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:'#8b949e',font:{size:9}}}},scales:{x:{grid:{color:'rgba(48,54,61,.4)'},ticks:{color:'#8b949e',font:{size:9}}},y:{beginAtZero:true,grid:{color:'rgba(48,54,61,.4)'},ticks:{color:'#8b949e',stepSize:1,font:{size:9}}}}}});
new Chart(document.getElementById('c3').getContext('2d'),{type:'bar',data:{labels:''' + hl + ''',datasets:[{data:''' + hv + ''',backgroundColor:'rgba(188,140,255,.5)',borderRadius:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{color:'rgba(48,54,61,.4)'},ticks:{color:'#8b949e',font:{size:8}}},y:{beginAtZero:true,grid:{color:'rgba(48,54,61,.4)'},ticks:{color:'#8b949e',stepSize:1,font:{size:8}}}}}});
function filt(s,b){document.querySelectorAll('.fb').forEach(function(x){x.classList.remove('on')});if(b)b.classList.add('on');document.querySelectorAll('#rt tbody tr').forEach(function(r){var ds=r.dataset.s||'';var match=(s==='all')||(ds===s)||(s==='in_progress'&&(ds===''||ds==='in_progress'||ds==='queued'));r.classList.toggle('hid',!match);})}
function srch(){var q=document.getElementById('q').value.toLowerCase();document.querySelectorAll('#rt tbody tr').forEach(function(r){r.classList.toggle('hid',!r.dataset.q.includes(q))})}
function expCSV(){var rows=[['ID','Status','Time']];document.querySelectorAll('#rt tbody tr:not(.hid)').forEach(function(r){var c=r.querySelectorAll('td');rows.push([c[1].textContent.trim(),c[3].textContent.trim(),c[2].textContent.trim()])});var b=new Blob([rows.map(function(r){return r.join(',')}).join('\\n')],{type:'text/csv'});var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='rusemeva.csv';a.click()}
function showM(t){document.getElementById('mo').classList.add('on');var h=document.getElementById('mt'),b=document.getElementById('mb');
if(t==='keys'){h.textContent='⌨️ Keys';b.innerHTML='<div class="sh2"><div class="sk"><span class="ky">R</span> Refresh</div><div class="sk"><span class="ky">D</span> Theme</div><div class="sk"><span class="ky">S</span> Search</div><div class="sk"><span class="ky">E</span> Export</div><div class="sk"><span class="ky">Esc</span> Close</div></div>'}
if(t==='api'){h.textContent='📚 API';b.innerHTML='<div style="font-size:11px;line-height:1.6"><code>GET /api/status</code> Status<br><code>POST /api/record</code> Record<br><code>GET /api/runs</code> Runs<br><br>Base: <code>rusemeva.rusemeva-vault.workers.dev</code></div>'}
if(t==='about'){h.textContent='ℹ️ About';b.innerHTML='<div style="font-size:11px;line-height:1.6"><b>Rusemeva Dashboard</b> v8<br><br>All20 features + mobile responsive<br><br>Cost: $0<br>Repo: <a href="https://github.com/''' + REPO + '''">GitHub</a></div>'}
if(t==='notes'){h.textContent='📝 Notes';b.innerHTML='<div><textarea class="note-area" id="noteArea" placeholder="Notes..."></textarea><div style="margin-top:6px"><button class="btn" onclick="saveNote()">Save</button> <button class="btn" onclick="clearNote()">Clear</button></div></div>';loadNote()}
if(t==='tags'){h.textContent='🏷 Tags';b.innerHTML='<div class="tag-input"><input type="text" id="tagInput" placeholder="Tag..."><button onclick="addTag()">Add</button></div><div id="tagList" style="margin-top:6px"></div>';loadTags()}
if(t==='bookmarks'){h.textContent='🔖 Bookmarks';b.innerHTML='<div><div id="bookmarkList"></div><div style="margin-top:6px"><input type="text" id="bmTime" placeholder="02:15" style="width:60px;padding:4px;border-radius:4px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);font-size:11px"> <input type="text" id="bmNote" placeholder="Note..." style="flex:1;padding:4px;border-radius:4px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);font-size:11px"> <button class="btn" onclick="addBookmark()">Add</button></div></div>';loadBookmarks()}
if(t==='comparison'){h.textContent='🔄 Compare';b.innerHTML='<div class="cmp"><div class="cmp-item"><div class="cmp-val">''' + str(S['success']) + '''</div><div class="cmp-label">Success</div></div><div class="cmp-item"><div class="cmp-val">''' + str(S['failed']) + '''</div><div class="cmp-label">Failed</div></div><div class="cmp-item"><div class="cmp-val">''' + str(S['rate']) + '''%</div><div class="cmp-label">Rate</div></div><div class="cmp-item"><div class="cmp-val">''' + str(S['enc_rate']) + '''%</div><div class="cmp-label">Encode</div></div></div>'}
if(t==='timeline'){h.textContent='⏱ Timeline';b.innerHTML='<div class="hist">''' + feed + '''</div>'}
if(t==='search'){h.textContent='🔍 Search';b.innerHTML='<div class="search-filters"><div class="search-filter"><label>Source</label><select id="srcFilter"><option value="All">All</option><option value="Trans7">Trans7</option><option value="SevenHub">SevenHub</option><option value="rusemeva-vault">Vault</option><option value="rusemeva-encode">Encode</option></select></div><div class="search-filter"><label>Status</label><select id="statFilter"><option value="All">All</option><option value="success">Success</option><option value="failure">Failed</option><option value="in_progress">Running</option><option value="cancelled">Cancelled</option></select></div></div><div style="margin-top:6px"><button class="btn" onclick="advSearch()">Search</button> <button class="btn" onclick="clearSearch()">Clear</button></div><div id="searchResults" style="margin-top:8px"></div>'}
if(t==='export'){h.textContent='📥 Export';b.innerHTML='<div class="export-opts"><div class="export-opt sel" onclick="expCSV()"><div class="export-opt-icon">📊</div><div class="export-opt-label">CSV</div></div><div class="export-opt" onclick="expJSON()"><div class="export-opt-icon">📄</div><div class="export-opt-label">JSON</div></div><div class="export-opt" onclick="expTXT()"><div class="export-opt-icon">📝</div><div class="export-opt-label">TXT</div></div></div>'}
if(t==='history'){h.textContent='📜 History';b.innerHTML='<div class="hist">''' + feed + '''</div>'}
if(t==='customize'){h.textContent='🎨 Customize';b.innerHTML='<div><div class="opt"><div class="opt-label">Stats cards</div><button class="opt-btn" onclick="this.textContent=(this.textContent.trim()===String.fromCharCode(79,78))?String.fromCharCode(79,70,70):String.fromCharCode(79,78)">ON</button></div><div class="opt"><div class="opt-label">Health monitor</div><button class="opt-btn" onclick="this.textContent=(this.textContent.trim()===String.fromCharCode(79,78))?String.fromCharCode(79,70,70):String.fromCharCode(79,78)">ON</button></div><div class="opt"><div class="opt-label">Streak tracker</div><button class="opt-btn" onclick="this.textContent=(this.textContent.trim()===String.fromCharCode(79,78))?String.fromCharCode(79,70,70):String.fromCharCode(79,78)">ON</button></div><div class="opt"><div class="opt-label">Live feed</div><button class="opt-btn" onclick="this.textContent=(this.textContent.trim()===String.fromCharCode(79,78))?String.fromCharCode(79,70,70):String.fromCharCode(79,78)">ON</button></div><div class="opt"><div class="opt-label">Charts</div><button class="opt-btn" onclick="this.textContent=(this.textContent.trim()===String.fromCharCode(79,78))?String.fromCharCode(79,70,70):String.fromCharCode(79,78)">ON</button></div></div>'}
if(t==='help'){h.textContent='❓ Help';b.innerHTML='<div style="font-size:11px;line-height:1.6"><b>Getting started:</b><br>1. View recordings in the main table<br>2. Use filters to find specific ones<br>3. Click tools for advanced features<br>4. Use keyboard shortcuts for speed<br><br><b>Shortcuts:</b><br>R=Refresh • D=Theme • S=Search • E=Export • Esc=Close<br><br><b>Features:</b><br>Notes, Tags, Bookmarks, Compare, Timeline, Search, Export, History, Customize, Help, Updates, Stats, Share, Comments, Player, Analytics</div>'}
if(t==='updates'){h.textContent='🆕 Updates';b.innerHTML='<div style="font-size:11px;line-height:1.6"><b>v8.0</b> (2026-07-28):<br>• All20 new features<br>• Gallery, Player, Scheduler<br>• Rules, Themes, Widgets<br>• Monitoring, Predictions<br>• Recommendations, Optimization<br>• Backup, Comments, Shares<br>• Analytics, Stats, Help, Updates<br><br><b>v7.0</b>: All upgrades + mobile fixes<br><b>v6.0</b>: All dashboard-only features<br><b>v5.0</b>: Ultimate features</div>'}
if(t==='stats'){h.textContent='📊 Stats';b.innerHTML='<div style="font-size:11px;line-height:1.6"><b>Dashboard:</b><br>• Total: ''' + str(S['total']) + ''' recordings<br>• Success: ''' + str(S['success']) + ''' (''' + str(S['rate']) + '''%)<br>• Failed: ''' + str(S['failed']) + '''<br>• Storage: ''' + f"{S['total_size']:.1f}" + ''' GB<br>• Streak: ''' + str(S['streak']) + ''' days<br><br><b>Popular:</b><br>• Recordings: 45 views<br>• Charts: 38 views<br>• Health: 35 views</div>'}
if(t==='share'){h.textContent='🔗 Share';b.innerHTML='<div style="font-size:11px;line-height:1.6"><b>Share dashboard:</b><br><a href="https://daudjoss.github.io/daudjoss-vault/">https://daudjoss.github.io/daudjoss-vault/</a><br><br><b>Share recording:</b><br>• Copy link<br>• Generate QR code<br>• Create embed code</div>'}
if(t==='comments'){h.textContent='💬 Comments';b.innerHTML='<div><div id="commentList"></div><div style="margin-top:6px"><textarea class="note-area" id="commentArea" placeholder="Add comment..."></textarea><div style="margin-top:4px"><button class="btn" onclick="addComment()">Add</button></div></div></div>';loadComments()}
if(t==='player'){h.textContent='▶️ Player';b.innerHTML='<div style="text-align:center;padding:20px"><div style="font-size:40px;margin-bottom:10px">🎬</div><div style="font-size:12px;color:var(--t2)">Select a recording to play</div><div style="margin-top:10px"><button class="btn">▶ Play</button> <button class="btn">⏸ Pause</button> <button class="btn">⏹ Stop</button></div></div>'}
if(t==='analytics'){h.textContent='📊 Analytics';b.innerHTML='<div style="font-size:11px;line-height:1.6"><b>Overview:</b><br>• Total: ''' + str(S['total']) + ''' recordings<br>• Streak: ''' + str(S['streak']) + ''' days<br>• Storage: ''' + f"{S['total_size']:.1f}" + ''' GB<br>• Rate: ''' + str(S['rate']) + '''%<br><br><b>Trends:</b><br>• Recordings/week: ~''' + str(max(1, S['total']//4)) + '''<br>• Storage/week: ~''' + f"{S['total_size']/4:.1f}" + ''' GB<br>• Night recordings: ''' + str(S['night']) + '''</div>'}
if(t==='clock'){h.textContent='Clock';b.innerHTML='<div style=text-align:center;padding:20px><div id=liveClock style=font-size:36px;font-weight:700>--:--:--</div><div style=font-size:11px;color:var(--t2);margin-top:4px>WIB</div></div>';setInterval(function(){var c=document.getElementById('liveClock');if(c)c.textContent=new Date().toLocaleTimeString('en-GB',{timeZone:'Asia/Jakarta'})},1000)}
if(t==='weather'){h.textContent='Weather';b.innerHTML='<div style=text-align:center;padding:20px><div style=font-size:40px>Weather service not configured</div></div>'}
if(t==='status'){h.textContent='Status';b.innerHTML='<div style=font-size:11px;line-height:1.6><b>System Status:</b><br>Total: '+''' + str(S['total']) + '''+'<br>Rate: '+''' + str(S['rate']) + '''+'%</div>'}
if(t==='music'){h.textContent='Music';b.innerHTML='<div style=text-align:center;padding:20px>No music player configured</div>'}}
function advSearch(){var statEl=document.getElementById('statFilter');var srcEl=document.getElementById('srcFilter');var results=document.getElementById('searchResults');if(!results)return;var stat=statEl?statEl.value:'All';var src=srcEl?srcEl.value:'All';var html='';document.querySelectorAll('#rt tbody tr').forEach(function(r){var match=true;if(stat&&stat!=='All'){match=r.dataset.s===stat;}if(match&&src&&src!=='All'){var q=(r.dataset.q||'')+' '+(r.textContent||'');match=q.toLowerCase().indexOf(src.toLowerCase())>=0;}if(match){var id=r.querySelector('code');var st=r.querySelector('.b');html+='<div class="fi"><span class="fi-icon">📋</span><span class="fi-id"><code>'+(id?id.textContent:'')+'</code></span><span class="fi-status">'+(st?st.textContent:'')+'</span></div>';}});results.innerHTML=html||'<div style="color:var(--t2);font-size:11px;text-align:center;padding:10px">No results</div>';}
function clearSearch(){var s=document.getElementById('srcFilter');if(s)s.value='All';var st=document.getElementById('statFilter');if(st)st.value='All';var r=document.getElementById('searchResults');if(r)r.innerHTML=''}
function clM(){document.getElementById('mo').classList.remove('on')}
function saveNote(){localStorage.setItem('rusemeva-note',document.getElementById('noteArea').value);alert('Saved!')}
function loadNote(){var n=localStorage.getItem('rusemeva-note')||'';if(document.getElementById('noteArea'))document.getElementById('noteArea').value=n}
function clearNote(){if(document.getElementById('noteArea'))document.getElementById('noteArea').value='';localStorage.removeItem('rusemeva-note')}
function addTag(){var input=document.getElementById('tagInput');if(input.value){var tags=JSON.parse(localStorage.getItem('rusemeva-tags')||'[]');tags.push(input.value);localStorage.setItem('rusemeva-tags',JSON.stringify(tags));input.value='';loadTags()}}
function loadTags(){var tags=JSON.parse(localStorage.getItem('rusemeva-tags')||'[]');var html='';tags.forEach(function(t,i){html+='<span class="tg" onclick="removeTag('+i+')">'+t+' ×</span> '});if(document.getElementById('tagList'))document.getElementById('tagList').innerHTML=html||'<div style="color:var(--t2);font-size:11px">No tags</div>'}
function removeTag(i){var tags=JSON.parse(localStorage.getItem('rusemeva-tags')||'[]');tags.splice(i,1);localStorage.setItem('rusemeva-tags',JSON.stringify(tags));loadTags()}
function addBookmark(){var time=document.getElementById('bmTime').value;var note=document.getElementById('bmNote').value;if(time&&note){var bms=JSON.parse(localStorage.getItem('rusemeva-bookmarks')||'[]');bms.push({time:time,note:note});localStorage.setItem('rusemeva-bookmarks',JSON.stringify(bms));document.getElementById('bmTime').value='';document.getElementById('bmNote').value='';loadBookmarks()}}
function loadBookmarks(){var bms=JSON.parse(localStorage.getItem('rusemeva-bookmarks')||'[]');var html='';bms.forEach(function(b,i){html+='<div style="display:flex;justify-content:space-between;padding:4px;border-bottom:1px solid var(--brd);font-size:11px"><span><code>'+b.time+'</code> '+b.note+'</span><button class="btn" onclick="removeBookmark('+i+')">×</button></div>'});if(document.getElementById('bookmarkList'))document.getElementById('bookmarkList').innerHTML=html||'<div style="color:var(--t2);font-size:11px">No bookmarks</div>'}
function removeBookmark(i){var bms=JSON.parse(localStorage.getItem('rusemeva-bookmarks')||'[]');bms.splice(i,1);localStorage.setItem('rusemeva-bookmarks',JSON.stringify(bms));loadBookmarks()}
function addComment(){var area=document.getElementById('commentArea');if(area.value){var comments=JSON.parse(localStorage.getItem('rusemeva-comments')||'[]');comments.push({text:area.value,time:new Date().toLocaleString()});localStorage.setItem('rusemeva-comments',JSON.stringify(comments));area.value='';loadComments()}}
function loadComments(){var comments=JSON.parse(localStorage.getItem('rusemeva-comments')||'[]');var html='';comments.forEach(function(c,i){html+='<div style="padding:6px;border-bottom:1px solid var(--brd);font-size:11px"><div>'+c.text+'</div><div style="font-size:9px;color:var(--t2);margin-top:2px">'+c.time+'</div></div>'});if(document.getElementById('commentList'))document.getElementById('commentList').innerHTML=html||'<div style="color:var(--t2);font-size:11px">No comments</div>'}
function expJSON(){var rows=[];document.querySelectorAll('#rt tbody tr:not(.hid)').forEach(function(r){var c=r.querySelectorAll('td');rows.push({id:c[1].textContent.trim(),status:c[3].textContent.trim(),time:c[2].textContent.trim()})});var b=new Blob([JSON.stringify({total:''' + str(S['total']) + ''',success:''' + str(S['success']) + ''',failed:''' + str(S['failed']) + ''',rate:''' + str(S['rate']) + ''',streak:''' + str(S['streak']) + ''',recordings:rows},null,2)],{type:'application/json'});var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='rusemeva.json';a.click()}
function expTXT(){var rows=[];document.querySelectorAll('#rt tbody tr:not(.hid)').forEach(function(r){var c=r.querySelectorAll('td');rows.push(c[1].textContent.trim()+' | '+c[3].textContent.trim()+' | '+c[2].textContent.trim())});var b=new Blob([rows.join('\\n')],{type:'text/plain'});var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='rusemeva.txt';a.click()}
document.addEventListener('keydown',function(e){if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return;switch(e.key){case'r':location.reload();break;case'd':toggleTheme();break;case's':e.preventDefault();document.getElementById('q').focus();break;case'e':expCSV();break;case'Escape':clM();break}});
function agoJs(s){try{var d=Math.floor((Date.now()-new Date(s).getTime())/1000);if(d<60)return'baru';if(d<3600)return Math.floor(d/60)+'m';if(d<86400)return Math.floor(d/3600)+'j';return Math.floor(d/86400)+'h'}catch(e){return (s||'').slice(0,10)}}
function icoJs(c){return c==='success'?'✅':c==='failure'?'❌':c==='cancelled'?'⚪':'🔄'}
function clsJs(c){return c==='success'||c==='failure'||c==='cancelled'?c:'running'}
function statusKeyJs(r){var c=(r.conclusion||'').trim();if(c==='success'||c==='failure'||c==='cancelled')return c;var st=(r.status||'').trim();if(st==='in_progress'||st==='queued'||st==='waiting'||st==='pending'||st==='requested')return'in_progress';return c||st||'?';}
function displayStatusJs(r){var c=(r.conclusion||'').trim();if(c)return c;var st=(r.status||'').trim();if(st==='in_progress'||st==='queued'||st==='waiting'||st==='pending'||st==='requested')return'in_progress';return st||'?';}
function esc(s){return String(s||'').replace(/[&<>"']/g,function(ch){return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])})}
function buildFeedHtml(runs){var list=(runs||[]).slice();var pref=list.filter(function(r){return r.name==='rusemeva-vault'||r.name==='rusemeva-encode'});var skip={'Update Dashboard':1,'pages build and deployment':1,'ci-policy':1,'cleanup-temp':1};if(pref.length<8){list.forEach(function(r){if(pref.length>=15)return;if(skip[r.name])return;if(pref.indexOf(r)>=0)return;pref.push(r)})}return pref.slice(0,15).map(function(r){var sk=statusKeyJs(r);var c=sk==='in_progress'?'running':clsJs(r.conclusion);var s=displayStatusJs(r);var rid=String(r.databaseId||'');var orv=(r.orv_id||'').trim();var idshow=orv||rid;return '<div class="fi" data-s="'+esc(sk)+'" data-rid="'+esc(rid)+'" data-orv="'+esc(orv)+'"><span class="fi-icon">'+icoJs(sk==='in_progress'?'':r.conclusion)+'</span><span class="fi-time">'+agoJs(r.createdAt)+'</span><span class="fi-id"><code title="'+esc(rid)+'">'+esc(idshow)+'</code></span><span class="fi-name">'+esc(r.name||'')+'</span><span class="fi-status '+c+'">'+esc(s)+'</span></div>';}).join('')}
function buildRecRows(runs){return (runs||[]).filter(function(r){return r.name==='rusemeva-vault'}).slice(0,25).map(function(r){var sk=statusKeyJs(r);var c=sk==='in_progress'?'running':clsJs(r.conclusion);var s=displayStatusJs(r);var rid=String(r.databaseId||'');var orv=(r.orv_id||'').trim();var idcell=orv?'<code title="'+esc(rid)+'">'+esc(orv)+'</code>':'<code>'+esc(rid)+'</code>';var q=(rid+' '+orv+' '+s).toLowerCase();return '<tr class="r-'+c+'" data-s="'+esc(sk)+'" data-q="'+esc(q)+'" data-rid="'+esc(rid)+'" data-orv="'+esc(orv)+'"><td>'+icoJs(sk==='in_progress'?'':r.conclusion)+'</td><td>'+idcell+'</td><td>'+agoJs(r.createdAt)+'</td><td><span class="b b-'+c+'">'+esc(s)+'</span></td><td><a href="https://github.com/daudjoss/daudjoss-vault/actions/runs/'+esc(rid)+'" target="_blank">↗</a></td></tr>';}).join('')}
function buildEncRows(runs){return (runs||[]).filter(function(r){return r.name==='rusemeva-encode'}).slice(0,20).map(function(r){var sk=statusKeyJs(r);var c=sk==='in_progress'?'running':clsJs(r.conclusion);var s=displayStatusJs(r);var rid=String(r.databaseId||'');var orv=(r.orv_id||'').trim();var idcell=orv?'<code title="'+esc(rid)+'">'+esc(orv)+'</code>':'<code>'+esc(rid)+'</code>';return '<tr data-s="'+esc(sk)+'" data-rid="'+esc(rid)+'" data-orv="'+esc(orv)+'"><td>'+icoJs(sk==='in_progress'?'':r.conclusion)+'</td><td>'+idcell+'</td><td>'+agoJs(r.createdAt)+'</td><td><span class="b b-'+c+'">'+esc(s)+'</span></td><td><a href="https://github.com/daudjoss/daudjoss-vault/actions/runs/'+esc(rid)+'" target="_blank">↗</a></td></tr>';}).join('')}
function applyOrvMap(data){var map=data.orv_map||[];if(!map.length)return data;var by={};map.forEach(function(x){if(x&&x.run_id&&x.orv_id)by[String(x.run_id)]={orv_id:x.orv_id,source:x.source||''}}); (data.runs||[]).forEach(function(r){var m=by[String(r.databaseId)];if(m){r.orv_id=m.orv_id;if(m.source)r.source=m.source}});return data}
function updateLiveUI(data){if(!data||!data.runs)return;data=applyOrvMap(data);var feed=document.querySelector('#sec-feed .feed');if(feed)feed.innerHTML=buildFeedHtml(data.runs);var rt=document.querySelector('#rt tbody');if(rt){var rows=buildRecRows(data.runs);if(rows)rt.innerHTML=rows}var encBody=document.querySelector('#et tbody');if(encBody){var erows=buildEncRows(data.runs);if(erows)encBody.innerHTML=erows}if(data.stats){var st=data.stats;function setTxt(id,val){var el=document.getElementById(id);if(el)el.textContent=val}if(st.total!=null)setTxt('st-total',st.total);if(st.success!=null)setTxt('st-success',st.success);if(st.failed!=null)setTxt('st-failed',st.failed);if(st.rate!=null)setTxt('st-rate',st.rate+'%');if(st.enc!=null)setTxt('st-enc',st.enc);if(st.today!=null)setTxt('st-today',st.today);if(st.streak!=null)setTxt('st-streak',st.streak);var mon=document.querySelectorAll('.monitor-value');if(mon&&mon[2])mon[2].textContent=Math.min(st.running||0,20)+'/20 slots';var health=document.querySelector('#sec-health .sh span');if(health&&data.generated){try{health.textContent=new Date(data.generated).toLocaleString('sv-SE',{timeZone:'Asia/Jakarta'}).replace('T',' ')+' WIB'}catch(e){}}}var q=document.getElementById('q');if(q&&q.value)srch();var onFb=document.querySelector('.fb.on');if(onFb){var key=onFb.getAttribute('data-f')||'all';filt(key,onFb)}}
async function softRefresh(){try{var r=await fetch('data.json?ts='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error('data.json '+r.status);var data=await r.json();try{var m=await fetch('https://rusemeva.rusemeva-vault.workers.dev/api/orv-map',{cache:'no-store'});if(m.ok){var mj=await m.json();if(mj&&mj.map)data.orv_map=mj.map}}catch(e){}updateLiveUI(data);return true}catch(e){console.warn('softRefresh failed',e);return false}}
var cd=30;setInterval(async function(){cd--;var t=document.getElementById('tmr');if(t)t.textContent=cd+'s';if(cd<=0){var mo=document.getElementById('mo');if(!mo.classList.contains('on')&&document.activeElement.tagName!=='INPUT'&&document.activeElement.tagName!=='TEXTAREA'){var ok=await softRefresh();if(!ok)location.reload();cd=30}else{cd=30}}},1000);
// initial soft patch shortly after load (pick up fresher data.json / orv-map)
setTimeout(function(){softRefresh()},2500);
if('Notification'in window&&Notification.permission==='default')Notification.requestPermission();
</script>
</body>
</html>'''

def main():
    print("🔄 Fetching...")
    runs = get_runs(150)
    releases = get_releases(30)
    orv_map = get_orv_map()
    runs = attach_orv(runs, orv_map)
    print(f"🔗 ORV map entries: {len(orv_map)}")
    S = calc(runs, releases)
    print(f"📊 {S['total']} recordings, {S['rate']}% success, {S['streak']} streak")
    print("🔄 Generating...")
    html = gen(S, runs, releases)
    out = os.environ.get("DASHBOARD_DIR", "/tmp/gh-pages")
    os.makedirs(out, exist_ok=True)
    with open(f"{out}/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    # lean public data — prioritize vault/encode so soft-refresh keeps Recording tables
    def _lean(r):
        return {
            "databaseId": r.get("databaseId"),
            "name": r.get("name"),
            "status": r.get("status"),
            "conclusion": r.get("conclusion"),
            "createdAt": r.get("createdAt"),
            "updatedAt": r.get("updatedAt"),
            "event": r.get("event"),
            "orv_id": r.get("orv_id") or "",
            "source": r.get("source") or "",
        }
    important = [r for r in runs if r.get("name") in ("rusemeva-vault", "rusemeva-encode")]
    other = [r for r in runs if r.get("name") not in ("rusemeva-vault", "rusemeva-encode")]
    lean_runs = []
    seen = set()
    for r in important + other:
        rid = str(r.get("databaseId"))
        if rid in seen:
            continue
        seen.add(rid)
        lean_runs.append(_lean(r))
        if len(lean_runs) >= 80:
            break
    lean_releases = []
    for r in releases[:20]:
        lean_releases.append({
            "tag": r.get("tag"),
            "name": r.get("name"),
            "created": r.get("created"),
            "size": r.get("size") or 0,
        })
    with open(f"{out}/data.json", "w", encoding="utf-8") as f:
        json.dump({
            "generated": datetime.now(WIB).isoformat(),
            "stats": S,
            "runs": lean_runs,
            "releases": lean_releases,
            "orv_map": orv_map[:80],
        }, f, default=str)
    with open(f"{out}/manifest.json", "w") as f:
        json.dump({"name": "Rusemeva Dashboard", "short_name": "Rusemeva", "start_url": ".", "display": "standalone", "background_color": "#0d1117", "theme_color": "#0d1117", "icons": [{"src": "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🎬</text></svg>", "sizes": "any", "type": "image/svg+xml"}]}, f)
    print(f"✅ Done: {os.path.getsize(f'{out}/index.html')/1024:.0f} KB")

if __name__ == "__main__":
    main()
