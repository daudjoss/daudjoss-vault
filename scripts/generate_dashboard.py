#!/usr/bin/env python3
"""Rusemeva Dashboard v10.1 — 16 new features: bingo, pet, betting, tree, pomodoro, kanban, sticky notes, cal export, data diff, story gen, 2048, snake, memory match, matrix rain, cemetery, spinning wheel."""
import json, os, subprocess, random, re
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
    raw = gh(["run","list","--repo",REPO,"--limit",str(n),"--json","databaseId,name,status,conclusion,createdAt,event,updatedAt,headBranch,headSha,number,displayTitle"])
    return json.loads(raw) if raw else []

def get_releases(n=30):
    raw = gh(["api",f"repos/{REPO}/releases","--jq",f"[.[:{n}][]|{{tag:.tag_name,name:.name,created:.created_at,size:([.assets[].size]|add//0),assets:[.assets[]|{{name:.name,size:.size}}]}}]"])
    return json.loads(raw) if raw else []


def parse_dur_sec(text):
    """Parse 1h30m / 5h38m / 43m / 2h from release name or tag."""
    if not text:
        return 0
    m = re.search(r"(?:(\d+)\s*h)?\s*(\d+)\s*m", text, re.I)
    if m:
        return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60
    m = re.search(r"(\d+)\s*h(?!\d)", text, re.I)
    if m:
        return int(m.group(1)) * 3600
    return 0

def fmt_bytes(n):
    n = float(n or 0)
    if n < 1024: return f"{n:.0f} B"
    if n < 1024**2: return f"{n/1024:.1f} KB"
    if n < 1024**3: return f"{n/1024/1024:.1f} MB"
    return f"{n/1024/1024/1024:.2f} GB"

def est_bytes_from_dur(sec, mbps=1.3):
    """Rough H264 size from duration (Telegram original ~1.3 Mbps)."""
    if sec <= 0:
        return 0
    return int(sec * mbps * 1_000_000 / 8)

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
    # GitHub only keeps small manifest .txt; MP4 goes to Telegram; encode-temp dihapus.
    # total_size = REAL bytes still on GH releases (bukan kumulatif histori video).
    # lifetime_est_gb = estimasi volume rekaman sepanjang masa (info terpisah, bukan "storage").
    gh_bytes = 0
    lifetime_est_bytes = 0
    for r in releases:
        tag = r.get("tag") or ""
        name = r.get("name") or ""
        sz = int(r.get("size") or 0)
        if "encode-" in tag or "Encode Temp" in name:
            continue  # temp should be gone; ignore if residual
        gh_bytes += sz
        dur = parse_dur_sec(name) or parse_dur_sec(tag)
        eb = est_bytes_from_dur(dur) if dur else 0
        # if asset itself is already big media, count real size toward lifetime too
        if sz >= 1 * 1024 * 1024:
            lifetime_est_bytes += sz
        elif eb:
            lifetime_est_bytes += eb
    total_size = gh_bytes / 1024 / 1024 / 1024  # GiB still on GitHub
    lifetime_est_gb = lifetime_est_bytes / 1024 / 1024 / 1024
    storage_est = False  # total_size is real GH occupancy, not estimate
    anomalies = []
    media = [r for r in releases if is_media_release(r)]
    avg_size = sum(r.get("size",0) for r in media) / len(media) if media else 0
    for r in media[:15]:
        sz = r.get("size",0)
        if avg_size > 0 and sz > 20*1024*1024 and sz < avg_size * 0.15:
            anomalies.append({"type":"small_file","tag":r.get("tag",""),"size":sz/1024/1024,"msg":"Media size unusually small vs peers"})
    quality_scores = []
    for r in v[:10]:
        c = r.get("conclusion")
        if c == "success":
            quality_scores.append({"id": r.get("databaseId"), "score": "OK", "note": "vault success"})
        elif c == "failure":
            quality_scores.append({"id": r.get("databaseId"), "score": "FAIL", "note": "vault failure"})
        elif c == "cancelled":
            quality_scores.append({"id": r.get("databaseId"), "score": "CANCEL", "note": "cancelled"})
    # Insights
    insights = []
    if top_hour: insights.append(f"Kamu paling sering rekam jam {top_hour}:00")
    if top_day: insights.append(f"Hari paling aktif: {top_day}")
    if streak >= 3: insights.append(f"Streak {streak} hari! Pertahankan!")
    if rate >= 90: insights.append(f"Success rate {rate}% — excellent!")
    # Predictions
    predictions = []
    n_cancel = len([r for r in v if r.get("conclusion") == "cancelled"])
    if lifetime_est_gb > 0:
        predictions.append(f"Volume rekaman lifetime ~{lifetime_est_gb:.1f} GB (est) — di Telegram, bukan di GitHub")
    predictions.append(f"GitHub storage aktual: {fmt_bytes(gh_bytes)} (manifest .txt; encode-temp dibersihkan)")
    if n_cancel:
        predictions.append(f"Vault cancelled: {n_cancel} (tidak dihitung sebagai failed)")
    if rn:
        predictions.append(f"Ada {rn} vault run masih running/queued")
    return {
        "total":t,"success":s,"failed":f,"cancelled":len([r for r in v if r.get("conclusion")=="cancelled"]),"running":rn,"rate":rate,
        "enc":et,"enc_ok":es,"enc_rate":erate,"today":len(tr),"today_ok":len([r for r in tr if r.get("conclusion")=="success"]),
        "daily":dict(sorted(daily.items())[-35:]),"weekly":dict(sorted(weekly.items())[-12:]),
        "errs":errs,"latest":v[0] if v else None,"streak":streak,"best":best,
        "achs":achs,"top_hour":top_hour,"top_day":top_day,"total_size":round(total_size,4),"storage_est":storage_est,"lifetime_est_gb":round(lifetime_est_gb,2),"gh_bytes":gh_bytes,
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
        sc = q.get("score")
        label = f"{sc}/100" if isinstance(sc, (int, float)) else str(sc)
        note = q.get("note") or ""
        qual_html += f'<div class="qual"><code>{q["id"]}</code><div class="qual-score">{label}</div><div style="font-size:9px;color:var(--t2)">{note}</div></div>'
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
    pct = min((S.get('lifetime_est_gb') or 0)/50*100, 100)
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
<html lang="id">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=yes">
<meta name="theme-color" content="#0d1117"><link rel="manifest" href="manifest.json">
<title>Rusemeva Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{--bg:#0d1117;--bg2:#161b22;--bg3:#21262d;--brd:#30363d;--t1:#e6edf3;--t2:#8b949e;--t3:#484f58;--bl:#58a6ff;--gn:#3fb950;--rd:#f85149;--yl:#d29922;--pr:#bc8cff;--or:#f0883e;--pn:#f778ba}
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

.src{display:flex;align-items:center;gap:8px;margin-bottom:4px}.src-label{font-size:10px;min-width:60px}.src-bar{flex:1;height:6px;background:var(--bg3);border-radius:3px;overflow:hidden}.src-fill{height:100%;background:var(--bl);border-radius:3px}.src-pct{font-size:9px;color:var(--t2);min-width:30px;text-align:right}
.time{display:flex;align-items:center;gap:6px;margin-bottom:2px}.time-label{font-size:8px;min-width:30px;color:var(--t3)}.time-bar{flex:1;height:5px;background:var(--bg3);border-radius:3px;overflow:hidden}.time-fill{height:100%;background:var(--pr);border-radius:3px}.time-cnt{font-size:8px;color:var(--t2);min-width:15px;text-align:right}
.cd{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;padding:6px 2px;background:var(--bg3);border-radius:8px;border:1px solid var(--brd);min-height:52px;text-align:center;transition:transform .15s,border-color .15s}.cd:hover{transform:translateY(-1px);border-color:var(--bl)}.cd.on{border-color:var(--bl);box-shadow:0 0 0 1px rgba(88,166,255,.35)}.cd.act{background:rgba(63,185,80,.12)}.cd-day{font-size:9px;font-weight:700;color:var(--t2);text-transform:uppercase;letter-spacing:.3px;line-height:1}.cd-num{font-size:11px;font-weight:700;color:var(--t1);line-height:1.1}.cd-cnt{font-size:10px;color:var(--gn);font-weight:600;line-height:1}.cd.c0 .cd-cnt{color:var(--t3)}


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
  
}
@media(max-width:480px){
  .sg{grid-template-columns:repeat(2,1fr)}
  .pg{grid-template-columns:repeat(2,1fr)}
  .ag{grid-template-columns:1fr 1fr}
  .ff{grid-template-columns:1fr 1fr}
  .gal{grid-template-columns:1fr 1fr}
}

/* === v8.3 visual upgrade === */
body{background:
  radial-gradient(1200px 600px at 10% -10%, rgba(88,166,255,.12), transparent 55%),
  radial-gradient(900px 500px at 100% 0%, rgba(188,140,255,.10), transparent 50%),
  radial-gradient(700px 400px at 50% 100%, rgba(63,185,80,.06), transparent 45%),
  var(--bg);padding-bottom:72px}
.hero{position:relative;overflow:hidden;border-radius:14px;padding:16px 16px 14px;margin-bottom:14px;
  background:linear-gradient(135deg,rgba(88,166,255,.14),rgba(188,140,255,.10) 45%,rgba(63,185,80,.06));
  border:1px solid var(--brd);box-shadow:0 8px 28px rgba(0,0,0,.18)}
.hero::before{content:'';position:absolute;inset:-40% -20% auto auto;width:220px;height:220px;border-radius:50%;
  background:radial-gradient(circle,rgba(88,166,255,.25),transparent 70%);pointer-events:none}
.hero-top{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;flex-wrap:wrap;position:relative;z-index:1}
.hero-brand{display:flex;flex-direction:column;gap:4px}
.hero-brand h1{font-size:22px;font-weight:800;letter-spacing:-.02em;background:linear-gradient(90deg,var(--t1),var(--bl));
  -webkit-background-clip:text;background-clip:text;color:transparent;display:flex;align-items:center;gap:8px}
.hero-sub{font-size:11px;color:var(--t2)}
.hero-actions{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.live-pill{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;
  background:rgba(63,185,80,.12);border:1px solid rgba(63,185,80,.28);font-size:10px;color:var(--gn);font-weight:600}
.btn{backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);border-radius:8px;padding:6px 10px}
.btn:active{transform:scale(.97)}
.sc{background:linear-gradient(180deg,rgba(255,255,255,.03),transparent),var(--bg2);
  border-radius:12px;box-shadow:0 4px 16px rgba(0,0,0,.12);backdrop-filter:blur(6px)}
.sc:hover{transform:translateY(-2px);box-shadow:0 8px 22px rgba(0,0,0,.18),0 0 0 1px rgba(88,166,255,.15)}
.sc::before{height:3px;opacity:.95}
.sc.bl{box-shadow:0 4px 16px rgba(0,0,0,.12),0 0 24px rgba(88,166,255,.06)}
.sc.gn{box-shadow:0 4px 16px rgba(0,0,0,.12),0 0 24px rgba(63,185,80,.06)}
.sc.rd{box-shadow:0 4px 16px rgba(0,0,0,.12),0 0 24px rgba(248,81,73,.06)}
.sc.yl{box-shadow:0 4px 16px rgba(0,0,0,.12),0 0 24px rgba(210,153,34,.06)}
.sc.pr{box-shadow:0 4px 16px rgba(0,0,0,.12),0 0 24px rgba(188,140,255,.06)}
.sc.or{box-shadow:0 4px 16px rgba(0,0,0,.12),0 0 24px rgba(240,136,62,.06)}
.sc.pn{box-shadow:0 4px 16px rgba(0,0,0,.12),0 0 24px rgba(247,120,186,.06)}
.sv{font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.sec{border-radius:12px;background:linear-gradient(180deg,rgba(255,255,255,.02),transparent),var(--bg2);
  box-shadow:0 2px 12px rgba(0,0,0,.10)}
.sh{border-bottom-color:rgba(48,54,61,.7)}
.st{letter-spacing:.01em}
.feed{max-height:240px;border-radius:8px}
.fi{border-radius:8px;margin-bottom:2px;border-bottom:none;background:rgba(255,255,255,.015)}
.fi:hover{background:rgba(88,166,255,.07)}
.fi-status{font-weight:600}
.streak{border-radius:12px;box-shadow:0 4px 18px rgba(240,136,62,.08)}
.gal-item,.widget,
.gal-item:hover,.widget:hover,.ffi:hover,.ach:hover{box-shadow:0 6px 18px rgba(0,0,0,.15)}


.nav{gap:6px;padding:6px;border-radius:12px;background:rgba(22,27,34,.85);border:1px solid var(--brd);
  backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);box-shadow:0 8px 24px rgba(0,0,0,.25)}
.nav-btn{width:32px;height:32px;border-radius:8px}
.bnav{display:none;position:fixed;left:8px;right:8px;bottom:8px;z-index:200;
  grid-template-columns:repeat(5,1fr);gap:4px;padding:8px;border-radius:16px;
  background:rgba(22,27,34,.92);border:1px solid var(--brd);
  backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
  box-shadow:0 10px 30px rgba(0,0,0,.35)}
.bnav button{appearance:none;border:none;background:transparent;color:var(--t2);font-size:11px;
  padding:6px 2px;border-radius:10px;cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:2px}
.bnav button .bi{font-size:16px;line-height:1}
.bnav button:active,.bnav button:hover{color:var(--bl);background:rgba(88,166,255,.08)}
.md{border-radius:14px;box-shadow:0 20px 50px rgba(0,0,0,.45);border:1px solid rgba(88,166,255,.15);
  background:linear-gradient(180deg,rgba(255,255,255,.03),transparent),var(--bg2)}
.mo{backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px)}
.ft{opacity:.85}
.heatmap{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;max-width:100%;overflow-x:auto}

.hm-cell.l1{background:rgba(63,185,80,.25)}.hm-cell.l2{background:rgba(63,185,80,.5)}
.hm-cell.l3{background:rgba(63,185,80,.75)}.hm-cell.l4{background:rgba(63,185,80,1)}
.spark{display:inline-block;vertical-align:middle;margin-left:6px}
.alert-chip{padding:4px 10px;border-radius:8px;background:rgba(248,81,73,.15);border:1px solid rgba(248,81,73,.4);color:#f85149;font-size:11px;animation:pulse 2s infinite}
.dur-bar{height:6px;border-radius:3px;background:var(--bg3);overflow:hidden;margin:2px 0}
.dur-fill{height:100%;border-radius:3px}
.eta-badge{font-size:10px;padding:2px 6px;border-radius:4px;background:rgba(88,166,255,.15);color:var(--bl);margin-left:4px}

.cheat-overlay{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.6);z-index:998;display:none;align-items:center;justify-content:center;padding:20px}
.cheat-overlay.on{display:flex}
.cheat-box{background:var(--bg2);border:1px solid var(--brd);border-radius:12px;padding:20px;max-width:360px;width:90%;box-shadow:0 20px 50px rgba(0,0,0,.5)}
.cheat-box h3{margin:0 0 12px;font-size:14px}
.cheat-row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--brd);font-size:12px}
.cheat-row:last-child{border:none}
.cheat-row .ky{font-family:monospace;background:var(--bg3);padding:2px 6px;border-radius:4px;font-size:11px}
.card-preview{border:1px solid var(--brd);border-radius:10px;padding:16px;background:var(--bg3);text-align:center;margin:8px 0}
.card-preview .card-stat{font-size:24px;font-weight:700}
.card-preview .card-label{font-size:10px;color:var(--t2)}
.gauge{position:relative;width:64px;height:64px;display:inline-block;vertical-align:middle}
.gauge svg{transform:rotate(-90deg)}
.gauge-bg{stroke:var(--bg3);stroke-width:6;fill:none}
.gauge-fg{stroke-width:6;fill:none;stroke-linecap:round;transition:stroke-dashoffset .5s ease}
.gauge-txt{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:14px;font-weight:700}
@keyframes slideIn{from{opacity:0;transform:translateY(-10px)}to{opacity:1;transform:translateY(0)}}
.fi-new{animation:slideIn .4s ease}
@keyframes pulseDot{0%,100%{opacity:1}50%{opacity:.3}}
.fresh-dot{display:inline-block;width:8px;height:8px;border-radius:50%;animation:pulseDot 2s infinite;margin-right:4px}
.fresh-dot.ok{background:var(--gn)}.fresh-dot.warn{background:var(--or)}.fresh-dot.stale{background:var(--rd)}
.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:var(--bg2);border:1px solid var(--brd);border-radius:8px;padding:8px 16px;font-size:12px;z-index:999;opacity:0;transition:opacity .3s;pointer-events:none}
.toast.on{opacity:1}
.qchip{display:inline-block;padding:3px 10px;border-radius:12px;border:1px solid var(--brd);background:var(--bg3);font-size:11px;cursor:pointer;margin:2px;user-select:none}
.qchip.on{background:var(--bl);color:#fff;border-color:var(--bl)}
.offline-banner{position:fixed;top:0;left:0;right:0;background:rgba(248,81,73,.9);color:#fff;text-align:center;padding:4px;font-size:12px;z-index:1000;display:none}
.offline-banner.on{display:block}
.rate-zone{padding:2px 8px;border-radius:6px;font-weight:700;font-size:13px}
.rate-zone.good{background:rgba(63,185,80,.15);color:var(--gn)}
.rate-zone.mid{background:rgba(240,136,62,.15);color:var(--or)}
.rate-zone.bad{background:rgba(248,81,73,.15);color:var(--rd)}
.shist-item{font-size:10px;color:var(--t2);cursor:pointer;padding:2px 6px;border-radius:4px;display:inline-block;margin:2px}
.shist-item:hover{background:var(--bg3)}
.counter{font-variant-numeric:tabular-nums}
.flow-diagram{display:flex;align-items:center;justify-content:center;gap:4px;padding:12px;flex-wrap:wrap}
.flow-node{padding:8px 14px;border-radius:10px;border:2px solid var(--brd);text-align:center;font-size:11px;min-width:70px}
.flow-node.vault{border-color:var(--bl);color:var(--bl)}
.flow-node.encode{border-color:var(--or);color:var(--or)}
.flow-node.telegram{border-color:var(--gn);color:var(--gn)}
.flow-arrow{font-size:16px;color:var(--t2)}
.activity-rings{position:relative;width:80px;height:80px;display:inline-block}
.activity-rings svg{transform:rotate(-90deg)}
.ring-bg{fill:none;stroke:var(--bg3);stroke-width:4}
.ring-fg{fill:none;stroke-width:4;stroke-linecap:round;transition:stroke-dashoffset .6s ease}
.gantt-wrap{overflow-x:auto;padding:4px 0}
.gantt-row{display:flex;align-items:center;height:22px;margin:1px 0;font-size:10px}
.gantt-label{width:80px;flex-shrink:0;text-align:right;padding-right:6px;color:var(--t2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gantt-bar-wrap{flex:1;position:relative;height:14px;background:var(--bg3);border-radius:3px}
.gantt-bar{position:absolute;height:100%;border-radius:3px;min-width:2px}
.fail-replay-item{padding:8px;border-radius:8px;border:1px solid var(--brd);margin:6px 0;background:var(--bg3)}
.run-note-badge{font-size:8px;cursor:pointer;padding:0 3px;border-radius:3px;background:rgba(240,136,62,.2);color:var(--or)}
.report-box{background:var(--bg3);border:1px solid var(--brd);border-radius:8px;padding:12px;font-size:11px;line-height:1.6;white-space:pre-wrap;margin:8px 0}
.threshold-input{width:40px;padding:2px 4px;border-radius:4px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);font-size:11px;text-align:center}
.embed-hide{display:none!important}
.accent-swatch{display:inline-block;width:20px;height:20px;border-radius:50%;cursor:pointer;margin:2px;border:2px solid transparent}
.accent-swatch.sel{border-color:var(--t1)}
.col-toggle{display:inline-flex;gap:4px;flex-wrap:wrap;margin:4px 0}
.col-tog-btn{font-size:10px;padding:2px 8px;border-radius:4px;border:1px solid var(--brd);background:var(--bg3);cursor:pointer;user-select:none}
.col-tog-btn.on{background:var(--bl);color:#fff;border-color:var(--bl)}
.kb-nav-hl{outline:2px solid var(--bl)!important;outline-offset:-2px}
.badge-toast{position:fixed;top:20px;left:50%;transform:translateX(-50%);background:var(--bg2);border:2px solid var(--or);border-radius:12px;padding:12px 20px;z-index:999;box-shadow:0 8px 24px rgba(0,0,0,.3);display:none;align-items:center;gap:10px;animation:badgePop .5s ease}
.badge-toast.on{display:flex}
@keyframes badgePop{from{opacity:0;transform:translateX(-50%) scale(.8)}to{opacity:1;transform:translateX(-50%) scale(1)}}
.badge-icon{font-size:28px}
.badge-info b{display:block;font-size:13px}
.badge-info span{font-size:10px;color:var(--t2)}
.badge-grid{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
.badge-item{padding:8px;border-radius:8px;border:1px solid var(--brd);background:var(--bg3);text-align:center;min-width:60px}
.badge-item.locked{opacity:.3;filter:grayscale(1)}
.badge-item .bi{font-size:20px}
.badge-item .bl{font-size:8px;color:var(--t2);margin-top:2px}
.streak-cal{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;max-width:280px}
.sc-day{aspect-ratio:1;border-radius:3px;background:var(--bg3);font-size:8px;display:flex;align-items:center;justify-content:center;color:var(--t2)}
.sc-day.ok{background:rgba(63,185,80,.3);color:var(--gn)}
.sc-day.fail{background:rgba(248,81,73,.3);color:var(--rd)}
.sc-day.empty{background:transparent;border:1px dashed var(--brd)}
.sc-day.today{outline:2px solid var(--bl)}
.freq-clock{position:relative;width:200px;height:200px;margin:8px auto}
.freq-bar{transform-origin:100px 100px;transition:height .3s ease}
.fail-pattern{padding:8px;border-radius:8px;background:rgba(248,81,73,.1);border:1px solid rgba(248,81,73,.3);margin:6px 0;font-size:11px}
.session-group{padding:6px;border-radius:8px;border:1px solid var(--brd);margin:4px 0;background:var(--bg3)}
.session-header{font-size:11px;font-weight:600;margin-bottom:4px}
.terminal{background:#0d1117;border:1px solid var(--brd);border-radius:8px;padding:8px;font-family:monospace;font-size:11px;margin:8px 0;max-height:200px;overflow:auto}
.terminal-input{background:transparent;border:none;color:var(--gn);font-family:monospace;font-size:11px;outline:none;width:100%}
.terminal-out{color:var(--t2);white-space:pre-wrap;word-break:break-all}
.terminal-prompt{color:var(--bl)}
.stat-spark{display:inline-block;width:40px;height:14px;vertical-align:middle;margin-left:4px}
.donut-legend{display:flex;flex-wrap:wrap;gap:6px;margin-top:4px;justify-content:center}
.donut-slice{cursor:pointer}
.donut-slice:hover{opacity:.8}
.flow-particle{position:absolute;width:4px;height:4px;border-radius:50%;background:var(--bl);animation:flowMove 2s linear infinite}
@keyframes flowMove{from{left:0;opacity:0}10%{opacity:1}90%{opacity:1}to{left:100%;opacity:0}}
.glass-mode .hero,.glass-mode .stat-card,.glass-mode .sec{backdrop-filter:blur(10px);background:rgba(22,27,34,.6);border:1px solid rgba(255,255,255,.08)}

.hm-matrix 
.hm-matrix 
.hm-matrix 
.hm-matrix .hm-cell2.l0{background:var(--bg3)}
.hm-matrix .hm-cell2.l1{background:rgba(88,166,255,.2)}
.hm-matrix .hm-cell2.l2{background:rgba(88,166,255,.4)}
.hm-matrix .hm-cell2.l3{background:rgba(88,166,255,.6)}
.hm-matrix .hm-cell2.l4{background:rgba(88,166,255,.9)}
.insight-box{padding:10px;border-radius:8px;border:1px solid var(--brd);background:var(--bg3);margin:6px 0;font-size:11px;line-height:1.6}
.insight-box b{color:var(--gn)}
.insight-box .bad{color:var(--rd)}
.prod-score{display:flex;align-items:center;gap:12px;padding:10px;border-radius:8px;border:1px solid var(--brd);background:var(--bg3);margin:6px 0}
.prod-ring{position:relative;width:60px;height:60px;flex-shrink:0}
.prod-bar-wrap{flex:1}
.prod-bar{height:6px;border-radius:3px;background:var(--bg3);overflow:hidden;margin:2px 0}
.prod-bar-fg{height:100%;border-radius:3px;transition:width .5s ease}
.stopwatch{display:inline-block;font-family:monospace;font-size:11px;color:var(--bl);background:var(--bg3);padding:2px 8px;border-radius:6px;margin-left:4px}
.stopwatch.live{color:var(--gn);animation:pulseDot 2s infinite}
.quick-panel{position:fixed;bottom:60px;right:20px;background:var(--bg2);border:1px solid var(--brd);border-radius:12px;padding:12px;z-index:998;box-shadow:0 8px 24px rgba(0,0,0,.3);display:none;min-width:200px}
.quick-panel.on{display:block}
.quick-panel-title{font-size:11px;font-weight:700;margin-bottom:8px;color:var(--bl)}
.quick-btn{display:block;width:100%;padding:6px 10px;border-radius:6px;border:1px solid var(--brd);background:var(--bg3);font-size:11px;cursor:pointer;margin:3px 0;text-align:left}
.quick-btn:hover{background:var(--bg2)}
.batch-sel{cursor:pointer;user-select:none}
.batch-sel.on{background:rgba(88,166,255,.15);outline:1px solid var(--bl)}
.batch-bar{position:sticky;bottom:0;background:var(--bg2);border:1px solid var(--brd);border-radius:8px;padding:8px;margin:8px 0;display:none;align-items:center;gap:8px;flex-wrap:wrap}
.batch-bar.on{display:flex}
.qr-wrap{text-align:center;margin:8px 0}
.qr-canvas{border:8px solid #fff;border-radius:8px}
.og-preview{border:1px solid var(--brd);border-radius:8px;overflow:hidden;margin:8px 0}
.embed-snippet{background:var(--bg3);border:1px solid var(--brd);border-radius:6px;padding:8px;font-size:10px;white-space:pre-wrap;word-break:break-all;margin:4px 0;position:relative}
.hc-mode{filter:contrast(1.3) saturate(1.2)}
.hc-mode .hero,.hc-mode .stat-card,.hc-mode .sec{border-width:2px}
.font-ctrl{display:inline-flex;gap:4px;align-items:center}
.font-btn{width:28px;height:28px;border-radius:6px;border:1px solid var(--brd);background:var(--bg3);cursor:pointer;font-size:13px;text-align:center;line-height:28px}
.aria-live{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}
@keyframes shimmer{0%{background-position:-200px 0}100%{background-position:calc(200px + 100%) 0}}
.skeleton{background:linear-gradient(90deg,var(--bg3) 25%,var(--bg2) 50%,var(--bg3) 75%);background-size:200px 100%;animation:shimmer 1.5s infinite;border-radius:4px}
.skeleton-line{height:12px;margin:4px 0}
.skeleton-stat{width:60px;height:40px;margin:4px}


.heatmap-wrap{padding:10px;overflow-x:auto}
.heatmap-grid{display:grid;grid-template-rows:repeat(7,1fr);grid-auto-flow:column;gap:2px;max-width:100%}
.heatmap-cell{width:10px;height:10px;border-radius:2px;background:var(--bg3)}
.heatmap-cell.l1{background:rgba(63,185,80,.25)}
.heatmap-cell.l2{background:rgba(63,185,80,.5)}
.heatmap-cell.l3{background:rgba(63,185,80,.75)}
.heatmap-cell.l4{background:var(--gn)}
.heatmap-cell.lf{background:var(--rd);opacity:.7}
.heatmap-legend{display:flex;gap:4px;align-items:center;font-size:10px;color:var(--t2);margin-top:8px;justify-content:center}
.heatmap-legend .heatmap-cell{width:10px;height:10px}
.heatmap-months{display:flex;gap:2px;font-size:8px;color:var(--t2);margin-bottom:4px}
.achv-wrap{padding:10px}
.achv-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(80px,1fr));gap:8px}
.achv-badge{text-align:center;padding:8px 4px;border-radius:8px;border:1px solid var(--brd);transition:all .3s}
.achv-badge.unlocked{border-color:var(--gn);background:rgba(63,185,80,.08)}
.achv-badge.locked{opacity:.4;filter:grayscale(1)}
.achv-icon{font-size:24px}
.achv-name{font-size:9px;color:var(--t2);margin-top:4px}
.achv-desc{font-size:8px;color:var(--t3);margin-top:2px}
.achv-progress{font-size:9px;color:var(--yl);margin-top:4px;text-align:center}
.chart-wrap{padding:10px}
.chart-canvas{max-width:100%;height:200px;margin:8px 0}
.gantt-wrap{padding:10px;overflow-x:auto}
.gantt-bar{height:16px;border-radius:3px;margin:2px 0;display:flex;align-items:center;padding:0 4px;font-size:8px;color:#fff;white-space:nowrap;overflow:hidden}
.gantt-axis{font-size:8px;color:var(--t2);border-bottom:1px solid var(--brd);padding-bottom:2px;margin-bottom:4px}
.compare-wrap{padding:10px}
.compare-select{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px}
.compare-col{font-size:10px}
.compare-col h4{font-size:11px;margin:4px 0}
.compare-row{display:flex;justify-content:space-between;padding:2px 0;border-bottom:1px solid var(--brd)}


.dash-clock{font-size:32px;font-weight:700;font-family:monospace;text-align:center;color:var(--bl);letter-spacing:2px}
.dash-clock-date{font-size:11px;color:var(--t2);text-align:center;margin-top:4px}

.trigger-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:6px;margin:8px 0}
.trigger-card{background:var(--bg3);border-radius:8px;padding:8px;text-align:center}
.trigger-icon{font-size:20px}
.trigger-name{font-size:9px;color:var(--t2);margin-top:2px}
.trigger-count{font-size:14px;font-weight:700}
.runnum-track{margin:8px 0}
.runnum-row{display:grid;grid-template-columns:40px 1fr 40px;gap:4px;padding:3px 0;border-bottom:1px solid var(--brd);font-size:10px;align-items:center}
.runnum-gap{color:var(--rd);font-size:9px}
.commit-msg{font-size:10px;color:var(--t1);padding:4px 0;border-bottom:1px solid var(--brd);line-height:1.4}
.commit-msg-sha{font-family:monospace;color:var(--bl);font-size:9px}
.trigger-bar{height:8px;border-radius:3px;background:var(--bl);margin:2px 0}


.metric-card{background:var(--bg2);border:1px solid var(--brd);border-radius:8px;padding:10px;margin:6px 0}
.metric-label{font-size:10px;color:var(--t2);text-transform:uppercase;letter-spacing:1px}
.metric-value{font-size:24px;font-weight:700;margin:4px 0}
.metric-value.ok{color:var(--gn)}
.metric-value.warn{color:var(--yl)}
.metric-value.bad{color:var(--rd)}
.metric-trend{font-size:10px;color:var(--t3);margin-top:2px}
.metric-trend.up{color:var(--gn)}
.metric-trend.down{color:var(--rd)}
.metric-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin:8px 0}
.metric-mini{background:var(--bg3);border-radius:6px;padding:8px;text-align:center}
.metric-mini-val{font-size:18px;font-weight:700}
.metric-mini-lbl{font-size:9px;color:var(--t2);margin-top:2px}
.dora-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin:8px 0}
.dora-card{background:var(--bg2);border:1px solid var(--brd);border-radius:8px;padding:10px;text-align:center}
.dora-val{font-size:20px;font-weight:700}
.dora-lbl{font-size:9px;color:var(--t2);margin-top:4px}
.pattern-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;margin:8px 0}
.pattern-cell{aspect-ratio:1;border-radius:3px;display:flex;align-items:center;justify-content:center;font-size:8px}
.pattern-cell.empty{background:var(--bg3)}
.pattern-cell.s1{background:rgba(63,185,80,.2)}
.pattern-cell.s2{background:rgba(63,185,80,.4)}
.pattern-cell.s3{background:rgba(63,185,80,.6)}
.pattern-cell.s4{background:rgba(63,185,80,.9)}
.pattern-cell.fail{background:rgba(248,81,73,.5)}
.pattern-label{font-size:8px;color:var(--t2);text-align:center;padding:2px}
.hour-bar{display:flex;align-items:end;gap:1px;height:60px;margin:8px 0}
.hour-col{flex:1;background:var(--bl);border-radius:2px 2px 0 0;min-height:2px;position:relative}
.hour-col.fail{background:var(--rd)}
.duration-trend{margin:8px 0}
.branch-bar{height:16px;border-radius:3px;margin:2px 0;display:flex;align-items:center;padding:0 4px;font-size:8px;color:#fff}
.minutes-bar{height:12px;border-radius:3px;background:var(--gn);transition:width .5s}
.minutes-bar.warn{background:var(--yl)}
.minutes-bar.bad{background:var(--rd)}
.commit-row{display:grid;grid-template-columns:60px 1fr 40px;gap:4px;padding:4px 0;border-bottom:1px solid var(--brd);font-size:10px;align-items:center}
.commit-sha{font-family:monospace;color:var(--bl);cursor:pointer}
.commit-result{font-size:9px}
.timeline-track{position:relative;height:30px;background:var(--bg3);border-radius:6px;margin:4px 0;overflow:hidden}
.timeline-dot{position:absolute;width:8px;height:8px;border-radius:50%;top:11px;transform:translateX(-50%)}
.timeline-dot.ok{background:var(--gn)}
.timeline-dot.fail{background:var(--rd)}
.retry-row{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid var(--brd);font-size:10px}
.concurrency-bar{height:20px;background:var(--bl);border-radius:3px;margin:1px 0;display:flex;align-items:center;justify-content:center;font-size:8px;color:#fff}
.workflow-row{display:grid;grid-template-columns:1fr 40px 40px;gap:4px;padding:4px 0;border-bottom:1px solid var(--brd);font-size:10px}


.md-export{padding:10px;text-align:center}


.drag-handle{cursor:move;user-select:none;opacity:.3;font-size:12px}
.drag-handle:hover{opacity:.7}
.dragging{opacity:.5}
.drop-target{border:2px dashed var(--bl)!important}
@media(max-width:768px){.swipe-section{scroll-snap-align:start}}

.curl-box{background:var(--bg3);border:1px solid var(--brd);border-radius:6px;padding:8px;font-size:10px;white-space:pre-wrap;word-break:break-all;margin:4px 0;position:relative}
.curl-copy{position:absolute;top:4px;right:4px;font-size:9px;cursor:pointer;padding:2px 6px;border-radius:4px;background:var(--bg2);border:1px solid var(--brd)}
@media print{.hero-actions,.bnav,.cmd-overlay,.cheat-overlay,.tools-panel,.sec-feed,.sec-health,.sec-week,.offline-banner,.toast,#qchips,.fb-row{display:none!important}.hero{box-shadow:none;border:none}body{background:#fff;color:#000}.stat-card{border:1px solid #ccc;box-shadow:none}}


}
}

.rsm-card{background:var(--bg3);border:1px solid var(--brd);border-radius:10px;padding:10px 12px;margin:8px 0;display:flex;align-items:center;gap:10px;font-size:12px}
.rsm-card .rsm-ico{font-size:20px}.rsm-card .rsm-id{font-weight:700;color:var(--bl)}.rsm-card .rsm-status{font-size:11px;color:var(--t2)}
.rsm-card .rsm-link{margin-left:auto;font-size:10px;text-decoration:none}


.diff-chip b{color:var(--t1)}
.storage-story{font-size:10px;color:var(--t2);padding:6px 10px;background:var(--bg3);border-radius:8px;margin:6px 0;line-height:1.5}
.storage-story b{color:var(--t1)}
.health-dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:4px}
.health-dot.ok{background:var(--gn)}.health-dot.warn{background:var(--or)}.health-dot.err{background:var(--rd)}
.health-row{display:flex;align-items:center;gap:6px;padding:4px 0;font-size:11px;border-bottom:1px solid var(--brd)}
.health-row:last-child{border:none}
.cmd-overlay{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.5);z-index:999;display:none;align-items:flex-start;justify-content:center;padding-top:60px}
.cmd-overlay.on{display:flex}
.cmd-box{background:var(--bg2);border:1px solid var(--brd);border-radius:12px;width:90%;max-width:420px;box-shadow:0 20px 50px rgba(0,0,0,.5);overflow:hidden}
.cmd-input{width:100%;padding:12px 14px;border:none;background:var(--bg3);color:var(--t1);font-size:14px;outline:none;border-bottom:1px solid var(--brd)}
.cmd-list{max-height:300px;overflow:auto}
.cmd-item{padding:10px 14px;font-size:12px;cursor:pointer;border-bottom:1px solid var(--brd)}
.cmd-item:hover,.cmd-item.sel{background:var(--bg3)}
.cmd-item .cmd-cat{font-size:9px;color:var(--t2);float:right}
.cmp-bar{display:flex;gap:4px;align-items:center;margin:4px 0;font-size:11px}
.cmp-bar button{font-size:10px;padding:3px 8px}
.compact #sec-week,.compact #sec-ach,.compact .gal,.compact .cal-scroll,.compact #sec-act .g2,.compact #sec-tools .rand,.compact #sec-tools .sched{display:none!important}
.compact .sg{display:grid!important;grid-template-columns:repeat(4,1fr)!important}
.view-btn{font-size:10px;padding:3px 8px;border-radius:6px;border:1px solid var(--brd);background:var(--bg3);color:var(--t2);cursor:pointer}
.view-btn:hover{color:var(--t1)}
.view-btn.act{border-color:var(--bl);color:var(--bl)}
.hl-row{outline:2px solid var(--bl);outline-offset:-2px;background:rgba(88,166,255,.08)!important}

.rate-ring{display:inline-flex;align-items:center;gap:8px;padding:6px 10px;border-radius:10px;background:var(--bg3);font-size:11px}
.pulse-dot{width:8px;height:8px;border-radius:50%;background:var(--gn);box-shadow:0 0 0 0 rgba(63,185,80,.5);animation:pulse 2s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(63,185,80,.45)}70%{box-shadow:0 0 0 8px rgba(63,185,80,0)}100%{box-shadow:0 0 0 0 rgba(63,185,80,0)}}
@media(max-width:768px){
  body{padding-bottom:84px}
  .hero{padding:12px}
  .hero-brand h1{font-size:18px}
  .nav{display:none!important}
  .bnav{display:grid}
  .sg{gap:8px}
  .sc{border-radius:10px


</style>
</head>
<body>
<div class="ct">
<div class="nav">
<button class="nav-btn" onclick="document.querySelector('.hero').scrollIntoView({behavior:'smooth'})" title="Home">🏠</button>
<button class="nav-btn" onclick="document.getElementById('sec-feed').scrollIntoView({behavior:'smooth'})" title="Feed">📰</button>
<button class="nav-btn" onclick="document.getElementById('sec-rec').scrollIntoView({behavior:'smooth'})" title="Recordings">🎬</button>
<button class="nav-btn" onclick="document.getElementById('sec-ach').scrollIntoView({behavior:'smooth'})" title="Achievements">🏆</button>
<button class="nav-btn" onclick="document.getElementById('sec-tools').scrollIntoView({behavior:'smooth'})" title="Tools">🛠</button>
<button class="nav-btn" onclick="document.getElementById('sec-act').scrollIntoView({behavior:'smooth'})" title="Actions">⚡</button>
</div>
<div class="aria-live" id="ariaLive" aria-live="polite" aria-atomic="true"></div>
<div class="quick-panel" id="quickPanel"><div class="quick-panel-title">⚡ Quick Actions</div><button class="quick-btn" data-action="copyRSM">📋 Copy last RSM</button><button class="quick-btn" data-action="export">📊 Export CSV</button><button class="quick-btn" data-action="terminal">⌨️ Terminal</button><button class="quick-btn" data-action="snapshot">🔗 Snapshot URL</button><button class="quick-btn" data-action="glass">🪟 Toggle glass</button><button class="quick-btn" data-action="close">✕ Close</button></div>
<div class="badge-toast" id="badgeToast"><span class="badge-icon" id="badgeIcon">🏆</span><div class="badge-info"><b id="badgeName">Achievement!</b><span id="badgeDesc"></span></div></div>
<div class="toast" id="toast">Copied!</div>
<div class="offline-banner" id="offlineBanner">⚠️ Offline — data tidak bisa refresh</div>
<div class="hero" id="sec-home">
<div class="hero-top">
<div class="hero-brand">
<h1>🎬 Rusemeva</h1>
<div class="hero-sub">Vault dashboard · live GHA · Telegram bot</div>
</div>
<div class="hero-actions">
<span class="live-pill"><span class="pulse-dot"></span> LIVE <span id="tmr">30s</span></span>
<button class="btn" onclick="softRefresh().then(function(ok){if(!ok)location.reload()})" title="Refresh">🔄</button>
<button class="pwa-btn" id="pwaInstall" style="display:none" onclick="installPWA()">📱 Install</button>
</div>
</div>
<div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;position:relative;z-index:1">
<span class="rate-ring">📊 Rate <b style="color:var(--bl)">''' + str(S['rate']) + '''%</b></span>
<span class="rate-ring">🔥 Streak <b style="color:var(--or)">''' + str(S['streak']) + '''d</b></span>
<span class="rate-ring">✅ ''' + str(S['success']) + ''' / ''' + str(S['total']) + '''</span>
<span class="rate-ring">🎞 Enc ''' + str(S['enc_ok']) + '''/''' + str(S['enc']) + '''</span>
</div>
<div id="hero-rsm"></div>
<div class="storage-story" id="hero-storage"></div>
<div class="diff-chips" id="hero-diff"></div>
<div id="hero-gauge"></div>
<div id="hero-rings"></div>
<div id="hero-fresh"></div>
<div id="hero-spark"></div>
<div id="hero-alert"></div>
</div>
<div class="sg">
<div class="sc bl"><div class="si">📹</div><div class="sv" id="st-total">''' + str(S['total']) + '''</div><div class="sl">Vault total</div></div>
<div class="sc gn"><div class="si">✅</div><div class="sv" id="st-success">''' + str(S['success']) + '''</div><div class="sl">Vault OK</div></div>
<div class="sc rd"><div class="si">❌</div><div class="sv" id="st-failed">''' + str(S['failed']) + '''</div><div class="sl">Vault fail</div></div>
<div class="sc yl"><div class="si">📊</div><div class="sv" id="st-rate">''' + str(S['rate']) + '''%</div><div class="sl">Vault rate</div></div>
<div class="sc pr"><div class="si">🎞</div><div class="sv" id="st-enc">''' + str(S['enc']) + '''</div><div class="sl">Encode</div></div>
<div class="sc or"><div class="si">📅</div><div class="sv" id="st-today">''' + str(S['today']) + '''</div><div class="sl">Today</div></div>
<div class="sc pn"><div class="si">🔥</div><div class="sv" id="st-streak">''' + str(S['streak']) + '''</div><div class="sl">Streak</div></div>
</div>
<div class="sec" id="sec-health"><div class="sh"><div class="st">🏥 Health</div><span style="font-size:9px;color:var(--t2)" id="health-ts">checking…</span></div>
<div id="health-rows"></div></div>
<div class="sec"><div class="sh"><div class="st">📡 Monitor</div></div>
<div class="monitor"><div class="monitor-dot green"></div><div class="monitor-label">Dashboard</div><div class="monitor-value">Generated OK</div></div>
<div class="monitor"><div class="monitor-dot green"></div><div class="monitor-label">RSM map</div><div class="monitor-value">''' + str(S.get('_orv_n') or 0) + ''' entries</div></div>
<div class="monitor"><div class="monitor-dot green"></div><div class="monitor-label">Vault running</div><div class="monitor-value">''' + str(S.get('running') or 0) + ''' job(s)</div></div>
<div class="monitor"><div class="monitor-dot green"></div><div class="monitor-label">GH bytes</div><div class="monitor-value">''' + fmt_bytes(S.get('gh_bytes') or 0) + '''</div></div>
</div>
<div class="streak"><div class="streak-icon">🔥</div><div style="flex:1"><div class="streak-val">''' + str(S['streak']) + ''' days</div><div class="streak-label">Streak (best: ''' + str(S['best']) + ''')</div><div class="streak-bar"><div class="streak-fill" style="width:''' + str(streak_pct) + '''%"></div></div></div></div>
<div class="sec" style="padding:6px 10px"><div style="display:flex;gap:4px;flex-wrap:wrap;align-items:center">
<span style="font-size:10px;color:var(--t2)">Views:</span>
<button class="view-btn act" onclick="applyView(this,'all')">All</button>
<button class="view-btn" onclick="applyView(this,'fail')">Fails</button>
<button class="view-btn" onclick="applyView(this,'today')">Today</button>
<button class="view-btn" onclick="applyView(this,'rsm')">Has RSM</button>
<button class="view-btn" onclick="applyView(this,'running')">Running</button>
<span style="flex:1"></span>
<button class="view-btn" onclick="saveCurrentView()">💾 Save</button>
<button class="view-btn" id="compactBtn" onclick="toggleCompact()">📐 Compact</button>
</div><div id="saved-views" style="margin-top:4px;display:flex;gap:4px;flex-wrap:wrap"></div></div>
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
<div class="sec" id="sec-donut"><div class="sh"><div class="st">🍩 Status Distribution</div></div><div id="donutWrap"></div></div>
<div class="sec" id="sec-flow"><div class="sh"><div class="st">🔄 Pipeline Flow</div></div><div id="flow-diagram"></div></div>
<div class="sec" id="sec-freqclock"><div class="sh"><div class="st">🕐 Run Frequency</div></div><div id="freqClockWrap"></div></div>
<div class="sec" id="sec-hmmatrix"><div class="sh"><div class="st">📊 Hour x Day Matrix</div></div><div id="hmMatrixWrap"></div></div>
<div class="sec" id="sec-streakcal"><div class="sh"><div class="st">📅 Streak Calendar</div></div><div id="streakCalGrid"></div></div>
<div class="sec" id="sec-heatmap"><div class="sh"><div class="st">🔥 Heatmap (30 hari)</div><span style="font-size:9px;color:var(--t2)">Intensitas rekaman</span></div><div id="heatmap-grid"></div><div style="display:flex;gap:4px;margin-top:4px;align-items:center;font-size:9px;color:var(--t2)"><span>Less</span><div class="hm-cell" style="width:10px;height:10px"></div><div class="hm-cell l1" style="width:10px;height:10px"></div><div class="hm-cell l2" style="width:10px;height:10px"></div><div class="hm-cell l3" style="width:10px;height:10px"></div><div class="hm-cell l4" style="width:10px;height:10px"></div><span>More</span></div></div>
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
<div class="ffi"><div class="ffi-icon">💾</div><div class="ffi-val">''' + fmt_bytes(S.get('gh_bytes') or 0) + '''</div><div class="ffi-label">On GitHub</div></div>
</div></div>
<div class="sec"><div class="sh"><div class="st">📊 Compare</div></div><div class="cmp">
<div class="cmp-item"><div class="cmp-val">''' + str(S['success']) + '''</div><div class="cmp-label">Success</div></div>
<div class="cmp-item"><div class="cmp-val">''' + str(S['failed']) + '''</div><div class="cmp-label">Failed</div></div>
<div class="cmp-item"><div class="cmp-val">''' + str(S['rate']) + '''%</div><div class="cmp-label">Rate</div></div>
<div class="cmp-item"><div class="cmp-val">''' + str(S['enc_rate']) + '''%</div><div class="cmp-label">Encode</div></div>
</div></div>
<div class="sec"><div class="sh"><div class="st">💾 Storage</div><span style="font-size:9px;color:var(--t2)">''' + fmt_bytes(S.get('gh_bytes') or 0) + ''' on GH · lifetime ~''' + str(S.get('lifetime_est_gb') or 0) + ''' GB est</span></div>
<div style="font-size:10px;color:var(--t2);margin:4px 0">Bar = lifetime volume est / 50GB (bukan disk GH). GH aktual: ''' + fmt_bytes(S.get('gh_bytes') or 0) + '''</div><div style="background:var(--bg3);border-radius:4px;height:16px;overflow:hidden;margin:6px 0"><div style="height:100%;width:''' + str(pct) + '''%;background:linear-gradient(90deg,var(--bl),var(--pr));border-radius:4px"></div></div><div style="font-size:10px;color:var(--t2)">Video/HEVC → Telegram; encode-temp di GH dihapus otomatis.</div></div>
<div class="sec"><div class="sh"><div class="st">💾 Backup</div></div>
<div class="backup"><div class="backup-label">Primary: GitHub (manifest only)</div><div class="backup-status">✅ ''' + fmt_bytes(S.get('gh_bytes') or 0) + ''' on GH · video di Telegram · lifetime ~''' + str(S.get('lifetime_est_gb') or 0) + ''' GB est (not stored on GH)</div></div>
<div class="backup"><div class="backup-label">Secondary</div><div class="backup-status">Telegram bot delivery (bukan mirror file di GH)</div></div>
</div>
<div class="sec"><div class="sh"><div class="st">🔍 Errors</div></div>''' + err_html + '''</div>
<div class="sec"><div class="sh"><div class="st">⚠️ Anomalies</div></div>''' + anom_html + '''</div>
<div class="sec"><div class="sh"><div class="st">📊 Quality</div></div>''' + qual_html + '''</div>
<div class="sec"><div class="sh"><div class="st">📊 Sources</div></div>''' + src_html + '''</div>
<div class="sec"><div class="sh"><div class="st">⏰ Hours</div></div>''' + time_html + '''</div>
<div class="sec" id="sec-ach"><div class="sh"><div class="st">🏆 Achievements (''' + str(len(S['achs'])) + ''')</div></div><div class="ach-grid">''' + ach_html + ach_locked + '''</div></div>
<div class="sec"><div class="sh"><div class="st">🎨 Mood</div></div><div class="mb">''' + mbi_html + '''</div></div>
<div class="sec"><div class="sh"><div class="st">🏷 Tags</div></div><div class="tc"><span class="tg">Pakai Tools → Tags (localStorage browser)</span></div></div>
<div class="sec"><div class="sh"><div class="st">🎲 Random</div></div><div class="rand"><div style="font-size:11px;color:var(--t2);margin-bottom:6px">Feeling lucky?</div><button class="rand-btn" onclick="document.getElementById('rand-result').innerHTML=randData">🎬 Surprise!</button><div id="rand-result"></div></div></div>
<div class="sec"><div class="sh"><div class="st">📋 Scheduler</div></div>
<div class="sched"><div class="sched-title">Scheduler</div><div class="sched-detail">Jadwal rekam lewat Telegram bot / GHA dispatch — bukan cron di halaman ini.</div><div class="sched-status">ℹ️ External</div></div>
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
<a class="ab" onclick="showM('compare')">🔄 Compare</a> <a class="ab" onclick="showM('search')">🔍 Search</a>
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
<div class="sec" id="sec-rec"><div class="sh"><div class="st">🎬 Recordings</div><div class="fl"><input class="si2" id="q" placeholder="🔍 Search..." oninput="srch()">
<div id="qchips" style="margin:4px 0"></div>
<div class="terminal" id="terminalBox" style="display:none"><div class="terminal-out" id="terminalOut"></div><div><span class="terminal-prompt">rusemeva@dash:~$</span> <input class="terminal-input" id="terminalInput" placeholder="type help..."></div></div><button class="fb on" onclick="filt('all',this)" data-f="all">All</button><button class="fb" onclick="filt('success',this)" data-f="success">✅</button><button class="fb" onclick="filt('failure',this)" data-f="failure">❌</button><button class="fb" onclick="filt('in_progress',this)" data-f="in_progress">🔄</button></div></div>
<div style="overflow-x:auto"><table id="rt"><thead><tr><th data-col="icon"></th><th data-col="id">ID</th><th data-col="time">Time</th><th data-col="status">Status</th><th data-col="link"></th></tr><tr><td colspan="5" style="padding:2px 0"><div class="col-toggle" id="colToggle"></div>
<div class="batch-bar" id="batchBar"><span style="font-size:11px"><b id="batchCount">0</b> selected</span><button class="btn" data-batch="tag">🏷 Tag all</button><button class="btn" data-batch="note">📝 Note all</button><button class="btn" data-batch="clear">✕ Clear</button></div></td></tr></thead><tbody>''' + rh + '''</tbody></table></div></div>
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

<div class="bnav">
<button onclick="document.getElementById('sec-home').scrollIntoView({behavior:'smooth'})"><span class="bi">🏠</span>Home</button>
<button onclick="document.getElementById('sec-feed').scrollIntoView({behavior:'smooth'})"><span class="bi">📰</span>Feed</button>
<button onclick="document.getElementById('sec-rec').scrollIntoView({behavior:'smooth'})"><span class="bi">🎬</span>Rec</button>
<button onclick="document.getElementById('sec-tools').scrollIntoView({behavior:'smooth'})"><span class="bi">🛠</span>Tools</button>
<button onclick="document.getElementById('sec-act').scrollIntoView({behavior:'smooth'})"><span class="bi">⚡</span>More</button>
</div>
<div class="ft"><p>Rusemeva · <a href="https://github.com/''' + REPO + '''">GitHub</a></p><p style="margin-top:3px"><span class="font-ctrl"><span class="font-btn" onclick="adjustFont(-1)">A-</span><span class="font-btn" onclick="adjustFont(1)">A+</span></span> v9.0 HM matrix + insights + stopwatch + quingo + Trigger Analysis + Run# Tracker + Commit Messages + Event Timeline + Gap Detection · Auto-refresh 30s</p></div>
</div>
<div class="mo" id="mo" onclick="if(event.target===this)clM()"><div class="md"><div class="mh"><h3 id="mt"></h3><button class="mc" onclick="clM()">&times;</button></div><div id="mb"></div></div></div>
<div class="cheat-overlay" id="cheatOverlay" onclick="if(event.target===this)closeCheat()">
<div class="cheat-box"><h3>⌨️ Shortcuts</h3>
<div class="cheat-row"><span>Command palette</span><span class="ky">P</span></div>
<div class="cheat-row"><span>Soft-refresh</span><span class="ky">R</span></div>
<div class="cheat-row"><span>Toggle theme</span><span class="ky">D</span></div>
<div class="cheat-row"><span>Search</span><span class="ky">S</span></div>
<div class="cheat-row"><span>Export CSV</span><span class="ky">E</span></div>
<div class="cheat-row"><span>This cheat sheet</span><span class="ky">?</span></div>
<div class="cheat-row"><span>Close modal</span><span class="ky">Esc</span></div>
<div style="margin-top:12px;font-size:10px;color:var(--t2)">Enter di search = langsung cari · ⚖ di Feed = compare</div>
</div></div>
<div class="cmd-overlay" id="cmdOverlay" onclick="if(event.target===this)closeCmd()">
<div class="cmd-box"><input class="cmd-input" id="cmdInput" placeholder="Ketik perintah atau cari RSM/run…" oninput="filterCmd()" onkeydown="cmdKey(event)">
<div class="cmd-list" id="cmdList"></div></div></div>
<script>
window.DASH = ''' + json.dumps({
        "generated": datetime.now(WIB).isoformat(),
            "build": "v10.1-max",
        "stats": {k: S[k] for k in ("total","success","failed","cancelled","running","rate","enc","enc_ok","enc_rate","today","today_ok","streak","best","top_hour","top_day","total_size","storage_est","lifetime_est_gb","gh_bytes","night") if k in S},
        "hours": S.get("hours") or {},
        "days": S.get("days") or {},
        "daily": S.get("daily") or {},
        "insights": S.get("insights") or [],
        "predictions": S.get("predictions") or [],
        "runs": [{
            "databaseId": r.get("databaseId"),
            "name": r.get("name"),
            "status": r.get("status"),
            "conclusion": r.get("conclusion"),
            "createdAt": r.get("createdAt"),
            "updatedAt": r.get("updatedAt"),
            "event": r.get("event"),
            "headBranch": r.get("headBranch") or "",
            "headSha": r.get("headSha") or "",
            "runNumber": r.get("number") or 0,
            "displayTitle": r.get("displayTitle") or "",
            "orv_id": r.get("orv_id") or "",
            "source": r.get("source") or "",
        } for r in runs[:80]],
        "releases": [{
            "tag": r.get("tag"), "name": r.get("name"),
            "created": r.get("created"), "size": r.get("size") or 0,
        } for r in releases[:20]],
    }, default=str) + ''';
function playRadio(url,name,btn){var p=document.getElementById('radioPlayer');if(p){p.src=url;p.play();var np=document.getElementById('radioNowPlaying');if(np)np.textContent='Now playing: '+name;var rl=document.getElementById('radioList');if(rl)rl.querySelectorAll('.radio-btn').forEach(function(b){b.style.background='';b.style.color=''});if(btn){btn.style.background='var(--bl)';btn.style.color='#fff'}}}


var randData=''' + "'" + rand_html.replace("'", "\\'") + "'" + ''';
var cc={b:'rgba(88,166,255,.5)',g:'#3fb950',r:'#f85149'};
new Chart(document.getElementById('c1').getContext('2d'),{type:'bar',data:{labels:''' + dl + ''',datasets:[{data:''' + dd + ''',backgroundColor:cc.b,borderRadius:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{color:'rgba(48,54,61,.4)'},ticks:{color:'#8b949e',maxTicksLimit:6,font:{size:9}}},y:{beginAtZero:true,grid:{color:'rgba(48,54,61,.4)'},ticks:{color:'#8b949e',stepSize:1,font:{size:9}}}}}});
new Chart(document.getElementById('c2').getContext('2d'),{type:'line',data:{labels:''' + wl + ''',datasets:[{label:'OK',data:''' + ws + ''',borderColor:cc.g,backgroundColor:'rgba(63,185,80,.08)',fill:true,tension:.4},{label:'Fail',data:''' + wf + ''',borderColor:cc.r,backgroundColor:'rgba(248,81,73,.08)',fill:true,tension:.4}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:'#8b949e',font:{size:9}}}},scales:{x:{grid:{color:'rgba(48,54,61,.4)'},ticks:{color:'#8b949e',font:{size:9}}},y:{beginAtZero:true,grid:{color:'rgba(48,54,61,.4)'},ticks:{color:'#8b949e',stepSize:1,font:{size:9}}}}}});
new Chart(document.getElementById('c3').getContext('2d'),{type:'bar',data:{labels:''' + hl + ''',datasets:[{data:''' + hv + ''',backgroundColor:'rgba(188,140,255,.5)',borderRadius:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{color:'rgba(48,54,61,.4)'},ticks:{color:'#8b949e',font:{size:8}}},y:{beginAtZero:true,grid:{color:'rgba(48,54,61,.4)'},ticks:{color:'#8b949e',stepSize:1,font:{size:8}}}}}});
function filt(s,b){document.querySelectorAll('.fb').forEach(function(x){x.classList.remove('on')});if(b)b.classList.add('on');document.querySelectorAll('#rt tbody tr').forEach(function(r){var ds=r.dataset.s||'';var match=(s==='all')||(ds===s)||(s==='in_progress'&&(ds===''||ds==='in_progress'||ds==='queued'));r.classList.toggle('hid',!match);})}
function srch(){var q=document.getElementById('q').value.toLowerCase();document.querySelectorAll('#rt tbody tr').forEach(function(r){r.classList.toggle('hid',!r.dataset.q.includes(q))})}
function dashRows(){var D=window.DASH||{runs:[]};return (D.runs||[]).filter(function(r){return r.name==='rusemeva-vault'||r.name==='rusemeva-encode'})}
function expCSV(){var rows=filteredRows();var nl=String.fromCharCode(10);var lines=['id,orv_id,name,status,conclusion,createdAt,source'];rows.forEach(function(r){lines.push([r.databaseId||'',r.orv_id||'',r.name||'',r.status||'',r.conclusion||'',r.createdAt||'',r.source||''].map(function(x){return '"'+String(x).replace(/"/g,'""')+'"'}).join(','))});downloadBlob(lines.join(nl),'rusemeva-runs.csv','text/csv')}
function expJSON(){var D=window.DASH||{};downloadBlob(JSON.stringify({generated:D.generated,stats:D.stats,runs:filteredRows()},null,2),'rusemeva-runs.json','application/json')}
function expTXT(){var rows=filteredRows();var nl=String.fromCharCode(10);var lines=rows.map(function(r){return [r.createdAt||'',r.orv_id||r.databaseId||'',r.name||'',r.conclusion||r.status||'',r.source||''].join(String.fromCharCode(9))});downloadBlob(lines.join(nl),'rusemeva-runs.txt','text/plain')}
function downloadBlob(text,name,type){var a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:type}));a.download=name;a.click();setTimeout(function(){URL.revokeObjectURL(a.href)},2000)}
function showM(t){
document.getElementById('mo').classList.add('on');
var h=document.getElementById('mt'),b=document.getElementById('mb');
var D=window.DASH||{stats:{},runs:[],releases:[]};
var st=D.stats||{};
function vaultRuns(){return (D.runs||[]).filter(function(r){return r.name==='rusemeva-vault'});}
function encRuns(){return (D.runs||[]).filter(function(r){return r.name==='rusemeva-encode'});}
function sk(r){return statusKeyJs(r);}
function rowRun(r){
  var id=r.orv_id||r.databaseId||'';
  var s=displayStatusJs(r);
  var link='https://github.com/daudjoss/daudjoss-vault/actions/runs/'+(r.databaseId||'');
  var dur='';
  var sw='';if(sk(r)==='in_progress'&&r.createdAt){sw='<span class="stopwatch live" id="sw-'+(r.databaseId||'')+'">0m 0s</span>'}
  if(r.createdAt&&r.updatedAt){var ms=new Date(r.updatedAt)-new Date(r.createdAt);if(ms>0){var mins=Math.round(ms/60000);var pct=Math.min(mins/120*100,100);var col=r.conclusion==='success'?'var(--gn)':(r.conclusion==='failure'?'var(--rd)':'var(--bl)');dur='<div class="dur-bar"><div class="dur-fill" style="width:'+pct+'%;background:'+col+'"></div></div>'}}
  return '<div class="fi" data-s="'+esc(sk(r))+'" data-rid="'+esc(r.databaseId||'')+'" data-orv="'+esc(r.orv_id||'')+'"><span class="fi-icon">'+icoJs(sk(r)==='in_progress'?'':(r.conclusion||''))+'</span><span class="fi-time">'+agoJs(r.createdAt||'')+'</span><span class="fi-id"><code title="'+esc(r.databaseId||'')+'">'+esc(id)+'</code></span><span class="fi-name">'+esc(r.name||'')+'</span><span class="fi-status '+clsJs(sk(r)==='in_progress'?'':(r.conclusion||''))+'">'+esc(s)+'</span> <a href="'+link+'" target="_blank" style="font-size:10px">↗</a>'+dur+'</div>';
}
function storageLabel(){
  var ghB=st.gh_bytes!=null?Number(st.gh_bytes):(Number(st.total_size||0)*1024*1024*1024);
  var ghStr = ghB>=1024*1024 ? (ghB/1024/1024).toFixed(1)+' MB' : (ghB/1024).toFixed(0)+' KB';
  var life=st.lifetime_est_gb!=null?Number(st.lifetime_est_gb):0;
  return ghStr+' on GH'+(life>0?' · lifetime rec ~'+life.toFixed(1)+' GB <span style="color:var(--t2)">(est, not stored)</span>':'');
}
function statBlock(){
  return '<div style="font-size:11px;line-height:1.7">'
    +'<b>Recordings (vault)</b><br>'
    +'• Total: <b>'+(st.total||0)+'</b><br>'
    +'• Success: <b>'+(st.success||0)+'</b> ('+(st.rate||0)+'%)<br>'
    +'• Failed: <b>'+(st.failed||0)+'</b> · Running: <b>'+(st.running||0)+'</b><br>'
    +'• Today: <b>'+(st.today||0)+'</b> (ok '+(st.today_ok||0)+') · Streak: <b>'+(st.streak||0)+'</b>d (best '+(st.best||0)+')<br>'
    +'• Storage: <b>'+storageLabel()+'</b><br>'
    +'• Peak hour: <b>'+(st.top_hour!=null?st.top_hour+':00':'—')+'</b> · Top day: <b>'+(st.top_day||'—')+'</b><br>'
    +'• Night owl runs: <b>'+(st.night||0)+'</b><br><br>'
    +'<b>Encode</b><br>'
    +'• Jobs: <b>'+(st.enc||0)+'</b> · OK: <b>'+(st.enc_ok||0)+'</b> ('+(st.enc_rate||0)+'%)<br>'
    +'</div>';
}
if(t==='keys'){h.textContent='⌨️ Keys';b.innerHTML='<div class="sh2"><div class="sk"><span class="ky">?</span> Cheat sheet overlay</div><div class="sk"><span class="ky">P</span> Command palette (navigate + search)</div><div class="sk"><span class="ky">R</span> Soft-refresh (reload data)</div><div class="sk"><span class="ky">D</span> Toggle dark/light theme</div><div class="sk"><span class="ky">S</span> Focus search box</div><div class="sk"><span class="ky">E</span> Export CSV (filtered)</div><div class="sk"><span class="ky">Esc</span> Close modal / palette</div></div><div style="margin-top:8px;font-size:11px;color:var(--t2)">Fokus input/textarea = shortcut nonaktif. Enter di search = langsung cari.</div>'}
if(t==='api'){h.textContent='📚 API';b.innerHTML='<div style="font-size:11px;line-height:1.7"><b>Worker</b> <code>rusemeva.rusemeva-vault.workers.dev</code><br><br><b>Endpoints</b><br><div class="curl-box">GET /api/status → {status, uptime, version}<span class="curl-copy" >📋</span></div><code>POST /api/record</code> → trigger vault GHA<br><code>GET /api/runs</code> → recent run list<br><div class="curl-box">GET /api/orv-map → {map:[{run_id,orv_id,source}]}<span class="curl-copy" >📋</span></div><code>GET /rtcal?preset=slow</code> → RT encode calibration<br><br><b>Dashboard (static)</b><br><code>GET data.json</code> → {build,generated,stats,runs,releases,orv_map}<br><code>GET index.html</code> → full dashboard<br><code>GET manifest.json</code> → PWA manifest<br><br><b>Contoh curl</b><br><code style="display:block;white-space:pre-wrap;padding:6px;background:var(--bg3);border-radius:4px;margin:4px 0">curl rusemeva.rusemeva-vault.workers.dev/api/orv-map</code><br><code style="display:block;white-space:pre-wrap;padding:6px;background:var(--bg3);border-radius:4px;margin:4px 0">curl daudjoss.github.io/daudjoss-vault/data.json | jq .stats</code><br><br><b>Auth</b><br>• Worker endpoints: no auth (public read)<br>• POST /api/record: requires bot token<br>• GHA API: uses github.token in Actions<br><br><b>Rate limits</b><br>• Worker: 100k req/day (CF free)<br>• GHA API: 5000 req/hr (authenticated)<br>• Pages: unlimited (CDN cached)</div>'}
if(t==='fails'){h.textContent='❌ Fail Replay';b.innerHTML=showFailReplay()+detectFailPatterns()}
if(t==='badges'){h.textContent='🏆 Badges';b.innerHTML=renderBadges()}
if(t==='terminal'){h.textContent='⌨️ Terminal';b.innerHTML='<div class="terminal" style="display:block"><div class="terminal-out" id="terminalOut2"></div><div><span class="terminal-prompt">rusemeva@dash:~$</span> <input class="terminal-input" id="terminalInput2" placeholder="type help..." data-terminal="2"></div></div><div style="margin-top:4px;font-size:10px;color:var(--t2)">Press T untuk toggle mini terminal</div>'}
if(t==='about'){h.textContent='ℹ️ About';var gen=D.generated||'—';var build=D.build||'—';var st=D.stats||{};var vaultC=vaultRuns().length;var encC=encRuns().length;var orvC=(D.runs||[]).filter(function(r){return r.orv_id}).length;b.innerHTML='<div style="font-size:11px;line-height:1.7"><b>Rusemeva Dashboard</b> v8.5.2<br>Live GHA + Worker RSM map + Telegram delivery<br><br><b>Tech stack</b><br>• Frontend: static HTML/CSS/JS (no framework)<br>• Charts: Chart.js (CDN)<br>• Data: GitHub Actions API → data.json<br>• Worker: Cloudflare (orv-map, status, notify)<br>• Hosting: GitHub Pages (free)<br>• Bot: Telegram @daudtrans_bot<br><br><b>Data sources</b><br>• GHA runs (get_runs 150) → lean 80 in data.json<br>• GH releases (get_releases 30) → storage + lifetime est<br>• Worker /api/orv-map → RSM-ID linking<br>• Soft-refresh: data.json + ORV map every 30s<br><br><b>Current snapshot</b><br>• Vault runs in payload: '+vaultC+'<br>• Encode runs in payload: '+encC+'<br>• RSM linked: '+orvC+'/'+(D.runs||[]).length+'<br>• GH storage: '+storageLabel()+'<br>• Build: <code>'+esc(build)+'</code><br>• Generated: <code>'+esc(gen)+'</code><br><br><b>Cost</b><br>• GitHub Actions: free tier (2000 min/mo)<br>• Cloudflare Worker: free tier (100k req/day)<br>• GitHub Pages: free<br>• Total: ~$0/mo<br><br><b>Links</b><br>• Repo: <a href="https://github.com/daudjoss/daudjoss-vault" target="_blank">daudjoss/daudjoss-vault</a><br>• Site: <a href="https://daudjoss.github.io/daudjoss-vault/" target="_blank">gh-pages</a><br>• Worker: <a href="https://rusemeva.rusemeva-vault.workers.dev/api/orv-map" target="_blank">orv-map</a></div>'}
if(t==='notes'){h.textContent='📝 Notes';b.innerHTML='<div><textarea class="note-area" id="noteArea" placeholder="Catatan lokal (auto-save 2s setelah berhenti ketik)..." style="width:100%;min-height:120px"></textarea><div style="margin-top:6px;display:flex;gap:6px;align-items:center"><button class="btn" onclick="saveNote()">💾 Save</button> <button class="btn" onclick="clearNote()">🗑 Clear</button> <span id="noteStatus" style="font-size:10px;color:var(--t2)"></span> <span id="noteCount" style="font-size:10px;color:var(--t2);margin-left:auto">0 chars</span></div><div style="margin-top:6px;font-size:10px;color:var(--t2)">Auto-save 2s · localStorage: rusemeva-note · last saved: <span id="noteSaved">—</span></div></div>';loadNote();var na=document.getElementById('noteArea');var ns=document.getElementById('noteStatus');var nc=document.getElementById('noteCount');var nsv=document.getElementById('noteSaved');if(na){na.addEventListener('input',function(){if(nc)nc.textContent=na.value.length+' chars';if(ns)ns.textContent='typing...';clearTimeout(window._noteTimer);window._noteTimer=setTimeout(function(){saveNote();if(ns)ns.textContent='saved';if(nsv){var d=localStorage.getItem('rusemeva-note-saved');if(d)nsv.textContent=d}},2000)})}}
if(t==='tags'){h.textContent='🏷 Tags';b.innerHTML='<div class="tag-input"><input type="text" id="tagInput" placeholder="Tag name..." style="flex:1;padding:4px 8px;border-radius:4px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);font-size:12px" onkeydown="if(event.keyCode===13)addTag()"><button class="btn" onclick="addTag()">Add</button></div><div id="tagList" style="margin-top:8px;display:flex;flex-wrap:wrap;gap:4px"></div><div id="tagCount" style="margin-top:6px;font-size:10px;color:var(--t2)">0 tags</div><div style="margin-top:6px;font-size:10px;color:var(--t2)">localStorage: rusemeva-tags · Enter untuk add · klik tag untuk hapus</div>';loadTags()}
if(t==='bookmarks'){h.textContent='🔖 Bookmarks';b.innerHTML='<div id="bookmarkList" style="margin-bottom:8px"></div><div style="display:flex;gap:4px;flex-wrap:wrap;align-items:center"><input type="text" id="bmTime" placeholder="mm:ss" style="width:60px;padding:4px 8px;border-radius:4px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);font-size:11px"> <input type="text" id="bmNote" placeholder="Note / RSM-ID / timestamp..." style="flex:1;min-width:140px;padding:4px 8px;border-radius:4px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);font-size:11px" onkeydown="if(event.keyCode===13)addBookmark()"> <button class="btn" onclick="addBookmark()">Add</button></div><div style="margin-top:6px;font-size:10px;color:var(--t2)">localStorage: rusemeva-bookmarks · Enter untuk add · × untuk hapus</div>';loadBookmarks()}
if(t==='compare'){h.textContent='🔄 Compare';b.innerHTML='<div style="font-size:11px;line-height:1.6"><b>Compare 2 runs</b><br>Klik tombol ⚖ di tiap baris Feed untuk pilih 2 run.<br>Setelah 2 terpilih, modal perbandingan muncul otomatis.</div><div style="margin-top:8px"><button class="btn" id="cmpClear">Clear picks</button></div>';var b2=document.getElementById('cmpClear');if(b2)b2.onclick=function(){cmpPick=[];clM();document.querySelectorAll('.fi').forEach(function(e){e.style.outline=''})}
}
if(t==='comparison'){
  h.textContent='🔄 Compare';
  var v=vaultRuns(),e=encRuns();
  var vs=v.filter(function(r){return r.conclusion==='success'}).length;
  var vf=v.filter(function(r){return r.conclusion==='failure'}).length;
  var vc=v.filter(function(r){return r.conclusion==='cancelled'}).length;
  var es=e.filter(function(r){return r.conclusion==='success'}).length;
  var ef=e.filter(function(r){return r.conclusion==='failure'}).length;
  var ec=e.filter(function(r){return r.conclusion==='cancelled'}).length;
  b.innerHTML='<div class="cmp">'
    +'<div class="cmp-item"><div class="cmp-val">'+vs+'</div><div class="cmp-label">Vault OK</div></div>'
    +'<div class="cmp-item"><div class="cmp-val">'+vf+'</div><div class="cmp-label">Vault Fail</div></div>'
    +'<div class="cmp-item"><div class="cmp-val">'+vc+'</div><div class="cmp-label">Vault Cancel</div></div>'
    +'<div class="cmp-item"><div class="cmp-val">'+(st.rate||0)+'%</div><div class="cmp-label">Vault Rate</div></div>'
    +'<div class="cmp-item"><div class="cmp-val">'+es+'</div><div class="cmp-label">Enc OK</div></div>'
    +'<div class="cmp-item"><div class="cmp-val">'+ef+'</div><div class="cmp-label">Enc Fail</div></div>'
    +'<div class="cmp-item"><div class="cmp-val">'+ec+'</div><div class="cmp-label">Enc Cancel</div></div>'
    +'<div class="cmp-item"><div class="cmp-val">'+(st.enc_rate||0)+'%</div><div class="cmp-label">Enc Rate</div></div>'
    +'</div><div style="margin-top:8px;font-size:10px;color:var(--t2)">Vault: '+v.length+' runs · Encode: '+e.length+' runs (live DASH)</div><div style="margin-top:4px;font-size:10px;color:var(--t2)">Cancelled tidak dihitung di rate gagal.</div>';
}
if(t==='timeline'||t==='history'){
  h.textContent=t==='timeline'?'⏱ Timeline':'📜 History';
  var list=(D.runs||[]).filter(function(r){return r.name==='rusemeva-vault'||r.name==='rusemeva-encode'});
  // group by date
  var groups={};
  list.forEach(function(r){
    var d=agoJs(r.createdAt||'');
    var date=d.replace(/[0-9]+[mjh]/,'').trim()||'baru';
    if(!groups[date])groups[date]={items:[],ok:0,fail:0,run:0,cancel:0};
    groups[date].items.push(r);
    var s=statusKeyJs(r);
    if(s==='success')groups[date].ok++;
    else if(s==='failure')groups[date].fail++;
    else if(s==='cancelled')groups[date].cancel++;
    else groups[date].run++;
  });
  var dates=Object.keys(groups).slice(0,10);
  var html='<div class="hist" style="max-height:380px;overflow:auto">';
  dates.forEach(function(dt){
    var g=groups[dt];
    html+='<div style="padding:6px 0;border-bottom:1px solid var(--brd)"><div style="font-size:11px;font-weight:600;margin-bottom:4px">'+esc(dt)+' <span style="color:var(--t2);font-weight:400">('+g.items.length+' runs: ✅'+g.ok+' ❌'+g.fail+' 🔄'+g.run+' ⚪'+g.cancel+')</span></div>';
    html+=g.items.slice(0,8).map(rowRun).join('');
    html+='</div>';
  });
  html+='</div>';
  b.innerHTML=html;
if(t==='timeline'||t==='history'){var cl=document.createElement('div');cl.style.marginTop='8px';cl.innerHTML='<div style="font-size:11px;font-weight:600;margin-bottom:4px">🗂 Sessions</div>'+renderClusters();var mb3=document.getElementById('mb');if(mb3)mb3.appendChild(cl);var gb=document.createElement('div');gb.style.marginTop='8px';gb.innerHTML='<div style="font-size:11px;font-weight:600;margin-bottom:4px">📊 Gantt View</div>'+renderGantt();var mb2=document.getElementById('mb');if(mb2)mb2.appendChild(gb)}
if(t==='timeline'||t==='history'){var gb=document.createElement('div');gb.style.marginTop='8px';gb.innerHTML='<div style="font-size:11px;font-weight:600;margin-bottom:4px">📊 Gantt View</div>'+renderGantt();var mb2=document.getElementById('mb');if(mb2)mb2.appendChild(gb)}
}
if(t==='timeline'||t==='history'){var gb=document.createElement('div');gb.style.marginTop='8px';gb.innerHTML='<div style="font-size:11px;font-weight:600;margin-bottom:4px">📊 Gantt View</div>'+renderGantt();var mb2=document.getElementById('mb');if(mb2)mb2.appendChild(gb)}
if(t==='search'){h.textContent='🔍 Search';b.innerHTML='<div class="search-filters"><div class="search-filter"><label>Source</label><select id="srcFilter"><option value="All">All</option><option value="rusemeva-vault">Vault</option><option value="rusemeva-encode">Encode</option><option value="Trans7">Trans7</option><option value="SevenHub">SevenHub</option></select></div><div class="search-filter"><label>Status</label><select id="statFilter"><option value="All">All</option><option value="success">Success</option><option value="failure">Failed</option><option value="in_progress">Running</option><option value="cancelled">Cancelled</option></select></div><div class="search-filter"><label>Sort</label><select id="sortFilter"><option value="new">Newest</option><option value="old">Oldest</option></select></div></div><div style="margin-top:6px"><input class="si2" id="qAdv" placeholder="RSM-ID / run id / text..." style="width:100%;margin-bottom:6px" onkeydown="if(event.keyCode===13)advSearch()"><button class="btn" onclick="advSearch()">Search</button> <button class="btn" onclick="clearSearch()">Clear</button> <span id="searchCount" style="font-size:10px;color:var(--t2);margin-left:4px"></span></div><div id="searchResults" style="margin-top:8px;max-height:320px;overflow:auto"></div>'}
if(t==='export'){h.textContent='📥 Export';var n=filteredRows().length;b.innerHTML='<div class="export-opts"><div class="export-opt sel" onclick="expCSV()"><div class="export-opt-icon">📊</div><div class="export-opt-label">CSV</div></div><div class="export-opt" onclick="expJSON()"><div class="export-opt-icon">📄</div><div class="export-opt-label">JSON</div></div><div class="export-opt" onclick="expTXT()"><div class="export-opt-label">TXT</div></div><div class="export-opt" onclick="expMD()"><div class="export-opt-label">MD</div></div></div><div style="margin-top:8px;font-size:10px;color:var(--t2)">'+n+' rows akan di-export (hormati filter search aktif). Data dari window.DASH.runs.</div>'}
if(t==='customize'){
  h.textContent='🎨 Customize';
  var keys=[['hideStats','Stats cards','.sg'],['hideHealth','Health','#sec-health'],['hideFeed','Live feed','#sec-feed'],['hideCharts','Charts & activity','#sec-week'],['hideStreak','Streak bar','.streak']];
  var html='<div>';
  keys.forEach(function(k){
    var on=localStorage.getItem('dash_'+k[0])!=='1';
    html+='<div class="opt"><div class="opt-label">'+k[1]+'</div><button class="opt-btn" data-k="'+k[0]+'" data-sel="'+k[2]+'" onclick="toggleCust(this)">'+(on?'ON':'OFF')+'</button></div>';
  });
  var soundOn=localStorage.getItem('dash_sound')==='1';var compactOn=document.body.classList.contains('compact');
  html+='<div class="opt"><div class="opt-label">Accent color</div><div>'+Object.keys(ACCENTS).map(function(k){return '<span class="accent-swatch'+(localStorage.getItem('dash_accent')===k?' sel':'')+'" data-accent="'+k+'" style="background:'+ACCENTS[k]+'" ></span>'}).join('')+'</div></div>';html+='<div class="opt"><div class="opt-label">Compact mode (hide charts/gallery)</div><button class="opt-btn" onclick="toggleCompact()">'+(compactOn?'ON':'OFF')+'</button></div>';html+='<div class="opt"><div class="opt-label">Alert threshold (fails)</div><input class="threshold-input" id="thresholdInput" type="number" min="1" max="20" value="'+getAlertThreshold()+'" onchange="setThreshold(this.value)"></div>';;html+='<div class="opt"><div class="opt-label">High contrast</div><button class="opt-btn" onclick="toggleHC()">'+(document.body.classList.contains('hc-mode')?'ON':'OFF')+'</button></div>';html+='<div class="opt"><div class="opt-label">Font size: '+(parseInt(localStorage.getItem('dash_fontsize')||'14',10))+'px</div><div class="font-ctrl"><span class="font-btn" onclick="adjustFont(-1)">A-</span><span class="font-btn" onclick="adjustFont(1)">A+</span></div></div>';html+='<div class="opt"><div class="opt-label">Glass morphism</div><button class="opt-btn" onclick="toggleGlass()">'+(document.body.classList.contains('glass-mode')?'ON':'OFF')+'</button></div>';html+='<div class="opt"><div class="opt-label">Sound alert on fail</div><button class="opt-btn" onclick="toggleSound()">'+(soundOn?'ON':'OFF')+'</button></div>';
  html+='</div><div style="margin-top:8px;font-size:10px;color:var(--t2)">Disimpan di localStorage · berlaku langsung. Theme: tekan D atau 🌓 di hero.</div>';
  b.innerHTML=html;
}
if(t==='help'){h.textContent='❓ Help';b.innerHTML='<div style="font-size:11px;line-height:1.7"><b>Mulai cepat</b><br>1. Lihat hero → Last RSM + storage story + 24h diff<br>2. Recordings table → filter ✅❌🔄 atau search<br>3. Tools menu → Stats, Search, Export, Player, Compare<br>4. Tekan <b>P</b> → command palette (navigate + search run)<br>5. Soft-refresh 30s otomatis (data.json + ORV map)<br><br><b>Deep link</b><br>• <code>?rsm=RSM-XXXX</code> → filter + highlight run by RSM-ID<br>• <code>?run=123456</code> → filter + highlight by GHA run ID<br>• Share dari Share menu atau copy URL<br><br><b>Saved views</b><br>• Klik view button (All/Fail/Today/RSM/Running)<br>• Save → beri nama → tersimpan di localStorage<br><br><b>Compare 2 runs</b><br>• Klik ⚖ di Feed atau Search results<br>• Pilih 2 runs → modal perbandingan otomatis<br><br><b>Compact mode</b><br>• Customize → Compact ON<br>• Sembunyikan charts/gallery, fokus tabel + feed<br><br><b>FAQ</b><br><b>Q: Kenapa Storage kecil?</b><br>A: GitHub hanya simpan manifest .txt. Video di Telegram.<br><br><b>Q: Kenapa RSM-ID tidak muncul?</b><br>A: Worker orv-map hanya terisi setelah record/encode selesai dan link terbuat.<br><br><b>Q: Kenapa angka berubah?</b><br>A: Soft-refresh 30s ambil data.json + ORV map terbaru.<br><br><b>Q: Data tidak update?</b><br>A: Hard refresh (Ctrl+Shift+R) atau cek data.json age di Status menu.<br><br><b>Shortcuts:</b> P palette · R refresh · D theme · S search · E export · Esc close</div>'}
if(t==='updates'){h.textContent='🆕 Updates';b.innerHTML='<div style="font-size:11px;line-height:1.6"><b>v10.1</b>:<br>• Trigger Analysis (push/schedule/manual/PR)<br>• Run Number Tracker (missing run detection)<br>• Commit Messages (SHA → result)<br>• Event Timeline (chronological by trigger)<br>• Run Number Gap Detection<br>• Enriched data: headBranch, headSha, runNumber, displayTitle<br><br><b>v10.0</b>:<br>• Deploy Frequency (DORA)<br>• MTTR (Mean Time To Recovery)<br>• Change Failure Rate (DORA)<br>• Lead Time estimation<br>• Failure Pattern Analysis (by hour/day)<br>• Duration Trends (slowdown detection)<br>• Success Rate by Day of Week<br>• Success Rate by Hour<br>• Branch Health (per branch)<br>• Actions Minutes Counter (free tier)<br>• Workflow Comparison<br>• Concurrency Monitor<br>• Commit Impact Tracker<br>• Deploy Timeline<br>• Retry Tracker<br>• Removed: 21 non-relevant features (games, fun, games, PWA, theme builder)<br><br><b>v10</b>:<br>• Heatmap Calendar (GitHub-style)<br>• Achievement System (12 badges)<br>• Analytics Charts (Chart.js)<br>• Gantt Timeline<br>• Run Comparison<br>• Markdown Report Export<br>• Dashboard Clock<br>• ASCII Art Header<br>• Custom Theme Builder (4 presets)<br>• Settings Import/Export (JSON)<br>• PWA Support (installable + offline)<br><br><b>v9.0</b>:<br>• Hour x Day heatmap matrix (7x24 grid)<br>• Best/worst day insight<br>• Time-to-recovery metric<br>• Productivity score (composite)<br>• Live run stopwatch (ticking)<br>• Quick actions panel (press A)<br>• Batch tag/note (select runs)<br>• QR code (scan to open)<br>• OG image generator<br>• Embed widget snippet<br>• High contrast mode<br>• Font size control (A-/A+)<br>• ARIA live announcements<br>• Loading skeleton<br><br><b>v8.9</b>:<br>• Achievement badges (milestone + toast)<br>• Streak calendar (monthly, color-coded)<br>• Run frequency clock (radial polar)<br>• Recurring failure detection<br>• Run duration prediction (confidence)<br>• Run clustering (sessions per hour)<br>• Mini terminal (type commands)<br>• Dashboard snapshot URL (hash state)<br>• Custom layout drag-drop<br>• Mobile swipe gestures<br>• Mini sparkline per stat card<br>• Status distribution donut (click filter)<br>• Animated pipeline particles<br>• Glass morphism toggle<br><br><b>v8.8</b>:<br>• Animated number counters (count up on load)<br>• Pipeline flow diagram (vault→encode→Telegram)<br>• Activity rings (daily/weekly/monthly targets)<br>• Gantt-style timeline (overlapping bars)<br>• Fail replay view (last 5 fails)<br>• Run notes per run (click row)<br>• Weekly auto-report (copy summary)<br>• Custom alert threshold<br>• Embed mode (?embed=1)<br>• Theme accent picker (4 colors)<br>• Table column toggle<br>• j/k keyboard navigation<br>• Copy as cURL (API menu)<br>• Print-friendly layout<br><br><b>v8.7</b>:<br>• Gauge/donut success rate (SVG ring di hero)<br>• Rate history 30 hari mini-chart (Stats)<br>• Animated feed slide-in (run baru)<br>• Tab title live counter (running/fail)<br>• Favicon badge (fail count red dot)<br>• Sound alert on fail (Web Audio, toggle)<br>• Data freshness dot (hijau/kuning/merah)<br>• Copy RSM on click (clipboard + toast)<br>• Search history (5 terakhir)<br>• Quick filter chips (Today/Fail/Running/RSM/Encode)<br>• Offline indicator (navigator.onLine)<br>• Confetti on streak 5/10/15/20<br>• Export as Markdown (.md table)<br>• Success rate color zone (green/yellow/red badge)<br><br><b>v8.6</b>:<br>• Activity heatmap (30 hari, GitHub-style)<br>• Sparkline trend 7 hari di hero<br>• Duration bars di Timeline<br>• Browser notification (run baru)<br>• Failure pattern alert (hero chip)<br>• ETA estimate untuk running jobs<br>• PWA install button<br>• System theme auto (prefers-color-scheme)<br>• Press ? cheat sheet<br>• Share as stats card (PNG)<br><br><b>v8.5.2</b>:<br>• About: tech stack, data sources, cost breakdown<br>• API: curl examples, response shape, rate limits<br>• Help: FAQ, deep link docs, troubleshooting<br>• Keys: all shortcuts listed<br>• Notes: auto-save 2s + char count + timestamp<br>• Tags: colored + count + Enter to add<br>• Bookmarks: RSM deep link + better UI<br>• Comments: delete + count + WIB timestamp<br>• Share: deep link builder + copy buttons<br>• Clock: date + weekday + larger display<br><br><b>v8.5.1</b>:<br>• Stats: enc breakdown, cancelled, storage, ORV<br>• Search: sort + count + Enter + ⚖ compare<br>• Timeline: grouped by date + status counts<br>• Player: vault + encode sections<br>• Compare: cancel counts<br>• Export: filter count<br>• Customize: compact toggle<br><br><b>v8.5</b>:<br>• Last RSM card + storage story + 24h diff<br>• Deep link ?rsm= / ?run=<br>• Honest client health<br>• Command palette (P)<br>• Compact mode + saved views<br>• Compare 2 runs<br>• Export filtered<br><br><b>v8.4.2</b>:<br>• window.DASH + menus data-driven<br>• Storage est dari durasi (bukan 0.0 GB)<br>• Customize beneran (hide sections)<br>• Search/Export/Player/Compare live<br>• Soft-refresh sync DASH<br><br><b>v8.3</b>: hero, glass, mobile nav<br><b>v8.2</b>: audit feed/WIB/filters<br><b>v8.0</b>: All20 features</div>'}
if(t==='stats'||t==='analytics'||t==='status'){
  h.textContent=t==='stats'?'📊 Stats':(t==='analytics'?'📊 Analytics':'📡 Status');
  var extra='';
  if(t==='stats'){
    var encList=encRuns();
    var encCanc=encList.filter(function(r){return r.conclusion==='cancelled'}).length;
    var encFail=encList.filter(function(r){return r.conclusion==='failure'}).length;
    var vaultCanc=(st.cancelled||0);
    extra='<br><br><b>Encode detail</b><br>• OK: '+(st.enc_ok||0)+' · Fail: '+encFail+' · Cancel: '+encCanc+'<br>• Rate: '+(st.enc_rate||0)+'%<br><br><b>Cancelled (excluded from fail)</b><br>• Vault: '+vaultCanc+' · Encode: '+encCanc+'<br><br><b>Storage</b><br>• '+storageLabel()+'<br><br><b>RSM map</b><br>• Linked: '+((D.runs||[]).filter(function(r){return r.orv_id}).length)+' / '+(D.runs||[]).length+' runs';
  }
  if(t==='analytics'){
    var hours=D.hours||{};
    var top=Object.keys(hours).sort(function(a,b){return (hours[b]||0)-(hours[a]||0)}).slice(0,8);
    extra='<br><b>Top jam:</b><br>'+(top.map(function(hh){return '• '+hh+':00 → '+(hours[hh]||0)+' runs'}).join('<br>')||'• —');
    var days=D.days||{};
    var topDays=Object.keys(days).sort(function(a,b){return (days[b]||0)-(days[a]||0)}).slice(0,7);
    extra+='<br><br><b>Hari:</b><br>'+(topDays.map(function(dd){return '• '+dd+': '+(days[dd]||0)+' runs'}).join('<br>')||'• —');
    var ins=(D.insights||[]).slice(0,5);
    var pred=(D.predictions||[]).slice(0,5);
    extra+='<br><br><b>Insights</b><br>'+(ins.map(function(i){return '• '+esc(i)}).join('<br>')||'• —');
    extra+='<br><br><b>Predictions</b><br>'+(pred.map(function(i){return '• '+esc(i)}).join('<br>')||'• —');
  }
  if(t==='status'){
    var gen=D.generated||'—';
    var ageMin=0;
    if(gen&&gen!=='—'){ageMin=Math.round((Date.now()-new Date(gen).getTime())/60000);}
    extra='<br><b>System</b><br>• Dashboard: gh-pages (static)<br>• Soft-refresh: 30s (data.json + ORV map)<br>• Data age: '+ageMin+'m<br>• ORV linked: '+((D.runs||[]).filter(function(r){return r.orv_id}).length)+'/'+(D.runs||[]).length+'<br><br><b>Worker</b><br>• rusemeva.rusemeva-vault.workers.dev<br>• /api/orv-map, /api/status<br><br><b>Build</b><br>• '+(D.build||'—');
  }
  b.innerHTML=statBlock()+extra;var dp=predictDuration();if(t==='stats'||t==='analytics'){var el=document.createElement('div');el.innerHTML=renderInsights()+renderRecovery()+renderProductivity();var mb0=document.getElementById('mb');if(mb0)mb0.appendChild(el);el.innerHTML=renderRateHistory();if(dp){var dpEl=document.createElement('div');dpEl.style.marginTop='8px';dpEl.innerHTML='<div style="font-size:11px;font-weight:600">⏱ Duration Prediction</div><div style="font-size:11px">Avg: '+dp.avg+'m · Median: '+dp.median+'m · Samples: '+dp.samples+'</div>'}var mb=document.getElementById('mb');if(mb)mb.appendChild(el);var rb=document.createElement('button');rb.className='btn';rb.textContent='📋 Weekly Report';rb.onclick=function(){var txt=generateReport();var box=document.createElement('div');box.className='report-box';box.textContent=txt;mb.appendChild(box);var cb=document.createElement('button');cb.className='btn';cb.textContent='Copy';cb.onclick=function(){navigator.clipboard.writeText(txt).then(function(){showToast('Report copied!')})};mb.appendChild(cb)};mb.appendChild(rb)}
if(t==='stats'||t==='analytics'){var mb3=document.getElementById('mb');if(mb3){var rb=document.createElement('button');rb.className='btn';rb.textContent='📋 Weekly Report';rb.style.margin='8px 0';rb.onclick=function(){var txt=generateReport();var box=document.createElement('div');box.className='report-box';box.textContent=txt;mb3.appendChild(box);var cb=document.createElement('button');cb.className='btn';cb.textContent='Copy';cb.onclick=function(){navigator.clipboard.writeText(txt).then(function(){showToast('Report copied!')})};mb3.appendChild(cb)};mb3.appendChild(rb)}}
}
if(t==='share'){
  h.textContent='🔗 Share';
  var base='https://daudjoss.github.io/daudjoss-vault/';
  var latest=vaultRuns()[0];var latestEnc=encRuns()[0];
  var rid=latest?(latest.orv_id||latest.databaseId||''):'';
  var runId=latest?latest.databaseId:'';
  b.innerHTML='<div style="font-size:11px;line-height:1.7"><b>Dashboard link</b><br><code id="shareDash">'+base+'</code><br><button class="btn" style="margin-top:4px" id="copyDash">📋 Copy</button><br><br><b>Deep link (latest vault)</b><br>'+(rid?'<code>?rsm='+esc(rid)+'</code><br><button class="btn" style="margin-top:4px" id="copyRsm">📋 Copy RSM link</button>':'No RSM-ID available')+'<br><br><b>Latest vault run</b><br><code>'+esc(String(rid||'—'))+'</code><br>'+(runId?'<a href="https://github.com/daudjoss/daudjoss-vault/actions/runs/'+runId+'" target="_blank">GHA ↗</a>':'')+'<br><br><b>Latest encode run</b><br>'+(latestEnc?'<code>'+esc(latestEnc.orv_id||latestEnc.databaseId||'')+'</code> <a href="https://github.com/daudjoss/daudjoss-vault/actions/runs/'+latestEnc.databaseId+'" target="_blank">GHA ↗</a>':'No encode runs')+'<br><br><b>Custom deep link</b><br><input type="text" id="customRsm" placeholder="RSM-XXXX atau run ID" style="width:100%;padding:4px 8px;border-radius:4px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);font-size:11px;margin-bottom:4px"><button class="btn" id="buildLink">Build link</button> <span id="customLink" style="font-size:10px;color:var(--t2)"></span></div>';
  var cd=document.getElementById('copyDash');if(cd)cd.onclick=function(){navigator.clipboard.writeText(base).then(function(){cd.textContent='✅ Copied';setTimeout(function(){cd.textContent='📋 Copy'},1500)})}
  var cr=document.getElementById('copyRsm');if(cr)cr.onclick=function(){var l=base+'?rsm='+rid;navigator.clipboard.writeText(l).then(function(){cr.textContent='✅ Copied';setTimeout(function(){cr.textContent='📋 Copy RSM link'},1500)})}
  var bl=document.getElementById('buildLink');if(bl)bl.onclick=function(){var v=document.getElementById('customRsm');if(!v||!v.value.trim())return;var isRsm=v.value.indexOf('RSM')>=0;var link=base+'?'+(isRsm?'rsm':'run')+'='+encodeURIComponent(v.value.trim());var cl=document.getElementById('customLink');if(cl){cl.innerHTML='<code>'+esc(link)+'</code> <button class="btn" style="font-size:9px" <button class="btn" style="font-size:9px" id="copyCustomLink">📋</button>'}};var ccl=document.getElementById('copyCustomLink');if(ccl)ccl.onclick=function(){var cv=document.getElementById('customRsm');if(!cv||!cv.value.trim())return;var isRsm=cv.value.indexOf('RSM')>=0;var l=base+'?'+(isRsm?'rsm':'run')+'='+encodeURIComponent(cv.value.trim());navigator.clipboard.writeText(l).then(function(){ccl.textContent='✅';setTimeout(function(){ccl.textContent='📋'},1500)})}

  var sc=document.createElement('button');sc.className='btn';sc.textContent='📊 Save stats card';
  var ss=document.createElement('button');ss.className='btn';ss.textContent='🔗 Snapshot URL';ss.onclick=saveSnapshot;
  var qrEl=document.createElement('div');qrEl.innerHTML=renderQR();
  var ogBtn=document.createElement('button');ogBtn.className='btn';ogBtn.textContent='🖼 OG Image';ogBtn.onclick=genOGImage;
  var embedEl=document.createElement('div');embedEl.innerHTML=renderEmbedSnippet();
  var mbS=document.getElementById('mb');if(mbS){mbS.appendChild(ss);mbS.appendChild(qrEl);mbS.appendChild(ogBtn);mbS.appendChild(embedEl)}var mb2=document.getElementById('mb');if(mb2)mb2.appendChild(ss);sc.onclick=shareCard;var mb=document.getElementById('mb');if(mb)mb.appendChild(sc)
}
if(t==='comments'){h.textContent='💬 Comments';b.innerHTML='<div id="commentList" style="margin-bottom:8px"></div><div><textarea class="note-area" id="commentArea" placeholder="Komentar lokal (tersimpan di browser)..." style="width:100%;min-height:80px"></textarea><div style="margin-top:4px;display:flex;gap:6px;align-items:center"><button class="btn" onclick="addComment()">💬 Add</button> <span id="commentCount" style="font-size:10px;color:var(--t2)"></span></div></div><div style="margin-top:6px;font-size:10px;color:var(--t2)">localStorage: rusemeva-comments · klik × untuk hapus</div>';loadComments()}
if(t==='player'){
  h.textContent='▶️ Player';
  var vList=vaultRuns();
  var eList=encRuns();
  var html='<div style="font-size:11px;color:var(--t2);margin-bottom:8px">Video/HEVC dikirim ke Telegram. GitHub hanya manifest .txt. Buka run GHA untuk detail log.</div>';
  html+='<div style="margin-bottom:8px;display:flex;gap:6px;flex-wrap:wrap"><a class="btn" href="https://github.com/daudjoss/daudjoss-vault/releases" target="_blank" style="text-decoration:none">📦 Releases</a> <a class="btn" href="https://github.com/daudjoss/daudjoss-vault/actions" target="_blank" style="text-decoration:none">🔧 All Actions</a></div>';
  html+='<div style="font-size:11px;font-weight:600;margin:8px 0 4px">📹 Vault recordings ('+vList.length+')</div>';
  html+='<div class="hist" style="max-height:200px;overflow:auto">'+vList.slice(0,15).map(function(r){
    var id=r.orv_id||r.databaseId||'';
    var c=clsJs(r.conclusion);
    return '<div class="fi"><span class="fi-icon">'+icoJs(r.conclusion||'')+'</span><span class="fi-time">'+agoJs(r.createdAt||'')+'</span><span class="fi-id"><code>'+esc(id)+'</code></span><span class="fi-status '+c+'">'+esc(displayStatusJs(r))+'</span><a class="btn" style="margin-left:auto;font-size:10px;text-decoration:none" href="https://github.com/daudjoss/daudjoss-vault/actions/runs/'+r.databaseId+'" target="_blank">Open</a></div>';
  }).join('')+'</div>';
  html+='<div style="font-size:11px;font-weight:600;margin:8px 0 4px">🎞 Encode jobs ('+eList.length+')</div>';
  html+='<div class="hist" style="max-height:180px;overflow:auto">'+eList.slice(0,10).map(function(r){
    var id=r.orv_id||r.databaseId||'';
    var c=clsJs(r.conclusion);
    return '<div class="fi"><span class="fi-icon">'+icoJs(r.conclusion||'')+'</span><span class="fi-time">'+agoJs(r.createdAt||'')+'</span><span class="fi-id"><code>'+esc(id)+'</code></span><span class="fi-status '+c+'">'+esc(displayStatusJs(r))+'</span><a class="btn" style="margin-left:auto;font-size:10px;text-decoration:none" href="https://github.com/daudjoss/daudjoss-vault/actions/runs/'+r.databaseId+'" target="_blank">Open</a></div>';
  }).join('')+'</div>';
  b.innerHTML=html;
}
if(t==='clock'){h.textContent='🕐 Clock';b.innerHTML='<div style="text-align:center;padding:16px"><div id="liveClock" style="font-size:42px;font-weight:700;letter-spacing:2px">--:--:--</div><div id="liveDate" style="font-size:13px;color:var(--t2);margin-top:6px">—</div><div style="font-size:11px;color:var(--t2);margin-top:8px">WIB · Asia/Jakarta · GMT+7</div><div id="liveUptime" style="font-size:10px;color:var(--t2);margin-top:4px"></div></div>';if(window._clk)clearInterval(window._clk);function tickClock(){var el=document.getElementById('liveClock');if(el)el.textContent=new Date().toLocaleTimeString('en-GB',{timeZone:'Asia/Jakarta',hour12:false});var dl=document.getElementById('liveDate');if(dl)dl.textContent=new Date().toLocaleDateString('en-GB',{weekday:'long',year:'numeric',month:'long',day:'numeric',timeZone:'Asia/Jakarta'})}tickClock();window._clk=setInterval(tickClock,500)}
if(t==='weather'){h.textContent='🌤 Weather';b.innerHTML='<div style="text-align:center;padding:18px"><div style="font-size:42px;margin-bottom:8px">🌤</div><div id="wxBox" style="font-size:12px;color:var(--t2)">Memuat BMKG/Open-Meteo…</div></div>';fetch('https://api.open-meteo.com/v1/forecast?latitude=-6.2&longitude=106.8&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&timezone=Asia%2FJakarta').then(function(r){return r.json()}).then(function(j){var c=j.current||{};var box=document.getElementById('wxBox');if(!box)return;box.innerHTML='<div style="font-size:28px;font-weight:700;color:var(--t1)">'+(c.temperature_2m!=null?c.temperature_2m+'°C':'—')+'</div><div style="margin-top:4px">Jakarta · RH '+(c.relative_humidity_2m!=null?c.relative_humidity_2m+'%':'—')+' · Wind '+(c.wind_speed_10m!=null?c.wind_speed_10m+' km/h':'—')+'</div><div style="margin-top:6px;font-size:10px;color:var(--t2)">Open-Meteo · code '+(c.weather_code!=null?c.weather_code:'—')+'</div>'}).catch(function(){var box=document.getElementById('wxBox');if(box)box.textContent='Gagal fetch cuaca (network).';})}
if(t==='trigger'){h.textContent='🎯 Trigger Analysis';b.innerHTML=renderTriggerAnalysis()}
if(t==='runnum'){h.textContent='🔢 Run Number Tracker';b.innerHTML=renderRunNumberTracker()}
if(t==='commitmsg'){h.textContent='💬 Commit Messages';b.innerHTML=renderCommitMessages()}
if(t==='eventtl'){h.textContent='📅 Event Timeline';b.innerHTML=renderEventTimeline()}
if(t==='rungap'){h.textContent='⚠️ Run Number Gaps';b.innerHTML=renderRunNumberGap()}
if(t==='depfreq'){h.textContent='🚀 Deploy Frequency';b.innerHTML=renderDeployFrequency()}
if(t==='mttr'){h.textContent='🔧 MTTR';b.innerHTML=renderMTTR()}
if(t==='cfr'){h.textContent='📉 Change Failure Rate';b.innerHTML=renderCFR()}
if(t==='leadtime'){h.textContent='⏱️ Lead Time';b.innerHTML=renderLeadTime()}
if(t==='failpattern'){h.textContent='🔍 Failure Patterns';b.innerHTML=renderFailurePattern()}
if(t==='durtrend'){h.textContent='📈 Duration Trends';b.innerHTML=renderDurationTrend()}
if(t==='successday'){h.textContent='📊 Success by Day';b.innerHTML=renderSuccessByDay()}
if(t==='successhour'){h.textContent='🕐 Success by Hour';b.innerHTML=renderSuccessByHour()}
if(t==='branchhealth'){h.textContent='🌿 Branch Health';b.innerHTML=renderBranchHealth()}
if(t==='minutes'){h.textContent='⏰ Actions Minutes';b.innerHTML=renderActionsMinutes()}
if(t==='workflowcomp'){h.textContent='⚙️ Workflow Comparison';b.innerHTML=renderWorkflowComparison()}
if(t==='concurrency'){h.textContent='🔄 Concurrency';b.innerHTML=renderConcurrency()}
if(t==='commitimpact'){h.textContent='📦 Commit Impact';b.innerHTML=renderCommitImpact()}
if(t==='deploymt'){h.textContent='📅 Deploy Timeline';b.innerHTML=renderDeployTimeline()}
if(t==='retry'){h.textContent='🔁 Retry Tracker';b.innerHTML=renderRetryTracker()}
if(t==='heatmap'){h.textContent='🔥 Heatmap';b.innerHTML=renderHeatmap()}
if(t==='achievements'){h.textContent='🏆 Achievements';b.innerHTML=renderAchievements()}
if(t==='analytics'){h.textContent='📊 Analytics';b.innerHTML=renderAnalytics()}
if(t==='gantt'){h.textContent='📅 Gantt Timeline';b.innerHTML=renderGantt()}
if(t==='compare2'){h.textContent='⚖️ Run Comparison';b.innerHTML=renderCompare()}
if(t==='mdexport'){h.textContent='📝 Markdown Report';b.innerHTML='<div class="md-export"><button class="btn" onclick="exportMarkdown()">📝 Export .md</button></div>'}


if(t==='clock'){h.textContent='🕐 Dashboard Clock';b.innerHTML=renderClock()}


if(t==='music'){h.textContent='🎵 Radio Indonesia';var radioStations=[{n:'Elshinta FM Jakarta',u:'https://stream-ssl.arenastreaming.com:8000/jakarta'},{n:'Mettaswara Koplo',u:'https://mettaswara.com:8700//koplo'},{n:'Campur Sari 89.2 FM',u:'https://a8.siar.us/listen/campursari/stream'},{n:'Suara Soneta',u:'https://a2.siar.us//listen//suarasoneta//radio.mp3'},{n:'Beat Radio Dangdut',u:'https://stream.beatradioid.com:8000//dangdut'},{n:'Dengerin Musik Indonesia',u:'https://stream.denger.in/'},{n:'Sunda Radio',u:'https://sundaradio.com/live/sundaradio'},{n:'Classy NetRadio',u:'https://streaming.classynetradio.com:8000/classySD'},{n:'POP FM Semarang',u:'https://i.klikhost.com:9612/stream.aac'},{n:'Style 94.6 FM Tasikmalaya',u:'https://stream.stylefmtasik.com/listen/stylefmtasik/stream'},{n:'Suara Salira',u:'https://live.suarasalira.com/listen/suarasalira/stream'},{n:'Mettaswara Dangdut',u:'https://mettaswara.com:8700/d4d'},{n:'Alternatif Radio Jakarta',u:'https://void.idserverhost.com/8016/stream'},{n:'Volcano Radio',u:'https://volcano.out.airtime.pro/volcano_a'},{n:'The Beat Radio Bali',u:'https://c1.siar.us/radio/8030/stream'},{n:'Tebet Radio Jakarta',u:'https://stream-ssl.arenastreaming.com:8066/stream'},{n:'Spirit Online',u:'https://radio.spirittoc.com:8060/spirit_online'},{n:'Radio Wisata FM',u:'https://c2.siar.us:9889/live'},{n:'Radio VOSS',u:'https://live.voss.my.id/listen/voss/voss'},{n:'Hitz 91.2 FM Belitung',u:'https://play.bilitonesefm.com/listen/radiohitzfm/stream'},{n:'Loker Musik Indonesia',u:'https://stream.lokermusik.com/listen/lokermusik/lokermusik'},{n:'Radio Kita Tasikmalaya',u:'https://stream.radiokita.my.id/listen/radiokita/radiokita'},{n:'Bellasalam 87.6 FM Tasikmalaya',u:'https://listen.bellasalamfm.com/listen/radiobellasalam/live'},{n:'Radio Sehati',u:'https://c4.siar.us:8092/autodj'},{n:'106.1 Geronimo FM',u:'https://ig.idstreamer.com:8090//live'},{n:'Bimasakti FM Kebumen',u:'https://i.klikhost.com:9622/stream'},{n:'Classy Worship',u:'https://streaming.classynetradio.com/listen/classyworship/worshipLQ'},{n:'Ada Radio Online',u:'https://adaradio.kradionews.com/listen/adaradio/stream'},{n:'ELPAS 88.6 FM Bogor',u:'https://live.elpasradio.com/listen/elpasradio/stream'},{n:'Bens Radio',u:'https://streaming.bensradio.com:8522/stream'},{n:'Damu Lumajang',u:'https://stream.radiodakwahmustofa.com:8724/damu'},{n:'Delta FM Bandung',u:'https://stream-pd-bdg.dimasalfaridzi.my.id/delta'},{n:'Firza MPC Radio',u:'https://mpc1.mediacp.eu/stream/firzaradio'},{n:'Mettaswara Indo 2000',u:'https://mettaswara.com:8700//indo00'},{n:'Mettaswara SoftRock',u:'https://mettaswara.com:8700/slowrock'},{n:'Radio CMN Hits',u:'https://stream.coolkas.com/listen/radiocmn/radiocmn'},{n:'KLCBS Fusion',u:'https://streaming.klcbsofficial.com/listen/fusion/klcbs-fusion'},{n:'KLCBS New Age',u:'https://streaming.klcbsofficial.com/listen/newage/klcbs-newage'},{n:'Yasika FM Jogja',u:'https://i.klikhost.com:9610/stream'},{n:'Fajri FM',u:'https://ars.mitradio.com:8000/radio.mp3'},{n:'Radio Kasih',u:'https://onlineradiobox.com/json/id/kasih/play'},{n:'Radio Klik FM Surabaya',u:'https://c1.alhastream.com:3210/radio'},{n:'Telkom Radio',u:'https://sukmben.radiogentara.com/radio/8140/stream'},{n:'Utaindo Radio',u:'https://streaming.classynetradio.com/listen/utaindo_radio/utaindo-aac'},{n:'ARB FM Jakarta',u:'https://void.idserverhost.com/8018/stream'},{n:'Galuh Media FM Cianjur',u:'https://stream-sg1.galuhmedia.co.id/listen/galuhmedia/stream'},{n:'KR-Radio 107.2 FM Jogja',u:'https://s1.gntr.net/listen/kr_radio/radio'},{n:'Radio Bravo 96.1 FM Kebumen',u:'https://stream.swadesifm.com/radio/8090/radio.mp3'},{n:'B 104.6 FM',u:'https://play.bilitonesefm.com/listen/radiobfm/stream'},{n:'Free FM Jakarta',u:'https://rocafmadrid.radioca.st/stream'},{n:'Galau Jikan FM',u:'https://radio.gjfm.my.id/listen/gjfm/siaran'},{n:'GCD 98.6 FM Yogyakarta',u:'https://studio1.indostreamers.com:8014/stream/1/'},{n:'Gemini 101 FM',u:'https://relay.gemini101fm.com/listen/gemini_fm/radio.mp3'},{n:'Istara FM Surabaya',u:'https://live.radioistara.com/listen/radioistara/radioistara'},{n:'R-Lisa FM',u:'https://a4.siar.us/radio/8360/radio.mp3'},{n:'Radiks FM Semarang',u:'https://i.klikhost.com:9620/;'},{n:'Radio Airmen FM 107.9',u:'https://void.idserverhost.com:8024/stream'},{n:'Mettaswara Indonesia Gold',u:'https://mettaswara.com:8700//disco'},{n:'Mettaswara Java',u:'https://mettaswara.com:8700//java'},{n:'MSTRI 104.2 FM',u:'https://c2.siar.us:8120/live'},{n:'Insania FM Indonesia',u:'https://stream-sg1.galuhmedia.co.id/listen/insaniamataram/876mataram'},{n:'Bharata Radio',u:'https://c1.siar.us:8800/live'},{n:'Braya Radio',u:'https://live.brayaradio.com/listen/brayaradio/stream'},{n:'Comfy Radio',u:'https://station.comfyradio.id/listen/comfyradio/radio.mp3'},{n:'KLCBS',u:'https://streaming.klcbs.id/listen/klcbs/klcbsfm-hd'},{n:'KLCBS Tropical',u:'https://streaming.klcbsofficial.com/listen/tropical/klcbs-tropical'},{n:'PAS FM Jakarta',u:'https://i.klikhost.com/8266/stream'},{n:'Radio Rumah Oma',u:'https://radiorumahoma.com:30443/;'},{n:'PTPN FM Solo',u:'https://ssg.streamingmurah.com:8040/stream'},{n:'Radio Andika',u:'https://r5.siar.us:1057/andikafm'},{n:'Radio Elshinta Bandung',u:'https://stream-ssl.arenastreaming.com:8005/bandung'},{n:'Radio Imelda FM',u:'https://server.radioimeldafm.co.id/listen/imeldafm/imeldafm'}];b.innerHTML='<audio id="radioPlayer" controls style="width:100%;margin-bottom:8px"></audio><div style="font-size:11px;color:var(--t2);margin-bottom:8px">Pilih stasiun radio:</div><div id="radioList"></div><div id="radioNowPlaying" style="font-size:10px;color:var(--bl);margin-top:8px"></div>';var rl=document.getElementById('radioList');if(rl){var html2='';radioStations.forEach(function(s,idx){html2+='<button class="quick-btn radio-btn" data-rurl="'+s.u+'" data-rname="'+s.n+'">📻 '+s.n+'</button>'});rl.innerHTML=html2}}
}
function toggleCust(btn){
  var k=btn.getAttribute('data-k');
  var sel=btn.getAttribute('data-sel');
  var off=localStorage.getItem('dash_'+k)==='1';
  if(off){localStorage.removeItem('dash_'+k);btn.textContent='ON';}
  else{localStorage.setItem('dash_'+k,'1');btn.textContent='OFF';}
  applyCustomize();
}
function applyCustomize(){
  var map=[['hideStats','.sg'],['hideHealth','#sec-health'],['hideFeed','#sec-feed'],['hideCharts','#sec-week'],['hideStreak','.streak']];
  map.forEach(function(m){
    var el=document.querySelector(m[1]);
    if(!el)return;
    el.style.display=localStorage.getItem('dash_'+m[0])==='1'?'none':'';
  });
}

function advSearch(){
var src=(document.getElementById('srcFilter')||{}).value||'All';
var stv=(document.getElementById('statFilter')||{}).value||'All';
var sortV=(document.getElementById('sortFilter')||{}).value||'new';
var q=((document.getElementById('qAdv')||{}).value||'').toLowerCase().trim();
var D=window.DASH||{runs:[]};
var rows=(D.runs||[]).filter(function(r){
  if(src!=='All'){var hay=((r.name||'')+' '+(r.source||'')).toLowerCase();if(hay.indexOf(src.toLowerCase())<0) return false;}
  var s=statusKeyJs(r);
  if(stv!=='All' && s!==stv && (r.conclusion||'')!==stv) return false;
  if(q){var blob=((r.orv_id||'')+' '+(r.databaseId||'')+' '+(r.name||'')+' '+(r.source||'')+' '+(r.conclusion||'')).toLowerCase();if(blob.indexOf(q)<0) return false;}
  return true;
});
rows.sort(function(a,b){
  var da=new Date(a.createdAt||0).getTime();
  var db=new Date(b.createdAt||0).getTime();
  return sortV==='old'?da-db:db-da;
});
var total=rows.length;
rows=rows.slice(0,50);
var cnt=document.getElementById('searchCount');
if(cnt)cnt.textContent=total+' result(s)';
var box=document.getElementById('searchResults');
if(!box)return;
if(!rows.length){box.innerHTML='<div class="ne">Tidak ada hasil</div>';return;}
box.innerHTML=rows.map(function(r){
  var id=r.orv_id||r.databaseId||'';
  var c=clsJs(r.conclusion);
  return '<div class="fi" data-rid="'+esc(r.databaseId)+'"><span class="fi-icon">'+icoJs(statusKeyJs(r)==='in_progress'?'':(r.conclusion||''))+'</span><span class="fi-time">'+agoJs(r.createdAt||'')+'</span><span class="fi-id"><code>'+esc(id)+'</code></span><span class="fi-name">'+esc(r.name||'')+'</span><span class="fi-status '+c+'">'+esc(displayStatusJs(r))+'</span><a href="https://github.com/daudjoss/daudjoss-vault/actions/runs/'+r.databaseId+'" target="_blank">↗</a><button data-cmp="'+r.databaseId+'" style="font-size:9px;padding:1px 4px;border:1px solid var(--brd);border-radius:4px;background:var(--bg3);color:var(--t2);cursor:pointer;margin-left:4px">⚖</button></div>';
}).join('');
box.querySelectorAll('[data-cmp]').forEach(function(b){b.onclick=function(){toggleCmpPick(b.getAttribute('data-cmp'))}});
}
function clearSearch(){var s=document.getElementById('srcFilter');if(s)s.value='All';var st=document.getElementById('statFilter');if(st)st.value='All';var r=document.getElementById('searchResults');if(r)r.innerHTML=''}
function clM(){document.getElementById('mo').classList.remove('on')}
function saveNote(){var v=document.getElementById('noteArea');if(!v)return;localStorage.setItem('rusemeva-note',v.value);var ts=new Date().toLocaleTimeString('en-GB',{timeZone:'Asia/Jakarta',hour12:false});localStorage.setItem('rusemeva-note-saved',ts);var sv=document.getElementById('noteSaved');if(sv)sv.textContent=ts;var st=document.getElementById('noteStatus');if(st)st.textContent='saved'}
function loadNote(){var n=localStorage.getItem('rusemeva-note')||'';var na=document.getElementById('noteArea');if(na)na.value=n;var nc=document.getElementById('noteCount');if(nc&&na)nc.textContent=na.value.length+' chars';var sv=document.getElementById('noteSaved');if(sv)sv.textContent=localStorage.getItem('rusemeva-note-saved')||'—'}
function clearNote(){if(document.getElementById('noteArea'))document.getElementById('noteArea').value='';localStorage.removeItem('rusemeva-note')}
function addTag(){var input=document.getElementById('tagInput');if(input.value){var tags=JSON.parse(localStorage.getItem('rusemeva-tags')||'[]');tags.push(input.value);localStorage.setItem('rusemeva-tags',JSON.stringify(tags));input.value='';loadTags()}}
function loadTags(){var tags=JSON.parse(localStorage.getItem('rusemeva-tags')||'[]');var colors=['#58a6ff','#3fb950','#f0883e','#bc8cff','#f778ba','#79c0ff'];var html='';tags.forEach(function(tg,i){var c=colors[i%colors.length];html+='<span class="tg" style="border-color:'+c+';color:'+c+'" onclick="removeTag('+i+')">'+esc(tg)+' ×</span> '});var tl=document.getElementById('tagList');if(tl)tl.innerHTML=html||'<div style="color:var(--t2);font-size:11px">No tags yet. Add one above.</div>';var tc=document.getElementById('tagCount');if(tc)tc.textContent=tags.length+' tag(s)'}
function removeTag(i){var tags=JSON.parse(localStorage.getItem('rusemeva-tags')||'[]');tags.splice(i,1);localStorage.setItem('rusemeva-tags',JSON.stringify(tags));loadTags()}
function addBookmark(){var time=document.getElementById('bmTime').value;var note=document.getElementById('bmNote').value;if(time&&note){var bms=JSON.parse(localStorage.getItem('rusemeva-bookmarks')||'[]');bms.push({time:time,note:note});localStorage.setItem('rusemeva-bookmarks',JSON.stringify(bms));document.getElementById('bmTime').value='';document.getElementById('bmNote').value='';loadBookmarks()}}
function loadBookmarks(){var bms=JSON.parse(localStorage.getItem('rusemeva-bookmarks')||'[]');var html='';if(!bms.length){html='<div style="color:var(--t2);font-size:11px;padding:8px 0">No bookmarks yet. Add timestamp + note above.</div>'}else{html='<div style="font-size:10px;color:var(--t2);margin-bottom:4px">'+bms.length+' bookmark(s)</div>'}bms.forEach(function(b,i){var isRsm=(b.note||'').indexOf('RSM')>=0;html+='<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 4px;border-bottom:1px solid var(--brd);font-size:11px"><span style="flex:1"><code style="color:var(--bl)">'+esc(b.time)+'</code> '+esc(b.note)+(isRsm?' <a href="?rsm='+esc(b.note)+'" style="font-size:9px">open ↗</a>':'')+'</span><button class="btn" style="font-size:9px;padding:2px 6px" onclick="removeBookmark('+i+')">×</button></div>'});var bl=document.getElementById('bookmarkList');if(bl)bl.innerHTML=html}
function removeBookmark(i){var bms=JSON.parse(localStorage.getItem('rusemeva-bookmarks')||'[]');bms.splice(i,1);localStorage.setItem('rusemeva-bookmarks',JSON.stringify(bms));loadBookmarks()}
function addComment(){var area=document.getElementById('commentArea');if(area&&area.value.trim()){var comments=JSON.parse(localStorage.getItem('rusemeva-comments')||'[]');comments.push({text:area.value.trim(),time:new Date().toLocaleTimeString('en-GB',{timeZone:'Asia/Jakarta',hour12:false})+' WIB'});localStorage.setItem('rusemeva-comments',JSON.stringify(comments));area.value='';loadComments()}}
function removeComment(i){var comments=JSON.parse(localStorage.getItem('rusemeva-comments')||'[]');comments.splice(i,1);localStorage.setItem('rusemeva-comments',JSON.stringify(comments));loadComments()}
function loadComments(){var comments=JSON.parse(localStorage.getItem('rusemeva-comments')||'[]');var html='';if(!comments.length){html='<div style="color:var(--t2);font-size:11px;padding:8px 0">No comments yet.</div>'}comments.forEach(function(c,i){html+='<div style="padding:6px 4px;border-bottom:1px solid var(--brd);font-size:11px"><div style="display:flex;justify-content:space-between;align-items:start"><span style="flex:1">'+esc(c.text)+'</span><button class="btn" style="font-size:9px;padding:2px 6px;flex-shrink:0" onclick="removeComment('+i+')">×</button></div><div style="font-size:9px;color:var(--t2);margin-top:2px">'+esc(c.time)+'</div></div>'});var cl=document.getElementById('commentList');if(cl)cl.innerHTML=html;var cc=document.getElementById('commentCount');if(cc)cc.textContent=comments.length+' comment(s)'}


document.addEventListener('click',function(e){var c=e.target.closest('.fi-id code');if(c){var id=c.textContent.trim();if(id)copyRSM(id)}var row=e.target.closest('#rt tbody tr');if(row&&!e.target.closest('a')){var rid=row.getAttribute('data-rid');if(rid&&e.shiftKey)saveRunNote(rid)}var rb=e.target.closest('.radio-btn');if(rb){playRadio(rb.getAttribute('data-rurl'),rb.getAttribute('data-rname'),rb);return}var br=e.target.closest('.batch-sel-off');if(br&&e.ctrlKey){toggleBatchSel(br.getAttribute('data-rid')||'');return}var as=e.target.closest('.accent-swatch');if(as){setAccent(as.getAttribute('data-accent'));return}var ds=e.target.closest('.donut-slice');if(ds){var lbl=ds.getAttribute('data-label');if(lbl)donutFilter(lbl);return}var cu=e.target.closest('.curl-copy');if(cu){var box=cu.closest('.curl-box');if(box){var txt=box.textContent.replace('📋','').trim();var url=txt.split(' ')[1]||txt;copyCurl(url)}}});
document.addEventListener('change',function(e){});
document.addEventListener('keydown',function(e){if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return;if(e.key==='p'||e.key==='P'){e.preventDefault();openCmd();return}
if(e.key==='?'||e.key==='/'){e.preventDefault();openCheat();return}
if(e.key==='t'||e.key==='T'){e.preventDefault();toggleTerminal();return}
if(e.key==='a'||e.key==='A'){e.preventDefault();toggleQuickPanel();return}
if(e.key==='h'||e.key==='H'){e.preventDefault();toggleHC();return}
if(e.key==='m'||e.key==='M'){e.preventDefault();expMD();return}
if(e.key==='j'){e.preventDefault();kbNav(1);return}
if(e.key==='k'){e.preventDefault();kbNav(-1);return}
if(e.key==='Enter'&&kbNavIdx>=0){e.preventDefault();kbNavOpen();return}switch(e.key){case'r':location.reload();break;case's':e.preventDefault();document.getElementById('q').focus();break;case'e':expCSV();break;case'Escape':clM();break}});
document.addEventListener('keydown',function(e){if(e.target&&e.target.id==='terminalInput'&&e.key==='Enter'){execTerminal(e.target.value);e.target.value=''}});
document.addEventListener('keydown',function(e){if(e.target&&e.target.id==='terminalInput2'&&e.key==='Enter'){execTerminal(e.target.value);e.target.value='';var o2=document.getElementById('terminalOut2');if(o2)o2.innerHTML='Executed: '+e.target.value}});
function agoJs(s){try{var d=Math.floor((Date.now()-new Date(s).getTime())/1000);if(d<60)return'baru';if(d<3600)return Math.floor(d/60)+'m';if(d<86400)return Math.floor(d/3600)+'j';return Math.floor(d/86400)+'h'}catch(e){return (s||'').slice(0,10)}}
function icoJs(c){return c==='success'?'✅':c==='failure'?'❌':c==='cancelled'?'⚪':'🔄'}
function clsJs(c){return c==='success'||c==='failure'||c==='cancelled'?c:'running'}
function statusKeyJs(r){var c=(r.conclusion||'').trim();if(c==='success'||c==='failure'||c==='cancelled')return c;var st=(r.status||'').trim();if(st==='in_progress'||st==='queued'||st==='waiting'||st==='pending'||st==='requested')return'in_progress';return c||st||'?';}
function displayStatusJs(r){var c=(r.conclusion||'').trim();if(c)return c;var st=(r.status||'').trim();if(st==='in_progress'||st==='queued'||st==='waiting'||st==='pending'||st==='requested')return'in_progress';return st||'?';}
function esc(s){return String(s||'').replace(/[&<>"']/g,function(ch){return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])})}
function buildFeedHtml(runs){var list=(runs||[]).slice();var pref=list.filter(function(r){return r.name==='rusemeva-vault'||r.name==='rusemeva-encode'});var skip={'Update Dashboard':1,'pages build and deployment':1,'ci-policy':1,'cleanup-temp':1};if(pref.length<8){list.forEach(function(r){if(pref.length>=15)return;if(skip[r.name])return;if(pref.indexOf(r)>=0)return;pref.push(r)})}return pref.slice(0,15).map(function(r){var sk=statusKeyJs(r);var newCls=r._isNew?' fi-new':'';var c=sk==='in_progress'?'running':clsJs(r.conclusion);var s=displayStatusJs(r);var rid=String(r.databaseId||'');var orv=(r.orv_id||'').trim();var idshow=orv||rid;return '<div class="fi'+newCls+' batch-sel-off" data-s="'+esc(sk)+'" data-rid="'+esc(rid)+'" data-orv="'+esc(orv)+'" ><span class="fi-icon">'+icoJs(sk==='in_progress'?'':r.conclusion)+'</span><span class="fi-time">'+agoJs(r.createdAt)+'</span><span class="fi-id"><code title="'+esc(rid)+'">'+esc(idshow)+'</code></span><span class="fi-name">'+esc(r.name||'')+'</span><span class="fi-status '+c+'">'+esc(s)+'</span><button data-cmp="rid" style="font-size:9px;padding:1px 4px;border:1px solid var(--brd);border-radius:4px;background:var(--bg3);color:var(--t2);cursor:pointer;margin-left:4px">⚖</button></div>';}).join('')}
function buildRecRows(runs){return (runs||[]).filter(function(r){return r.name==='rusemeva-vault'}).slice(0,25).map(function(r){var sk=statusKeyJs(r);var c=sk==='in_progress'?'running':clsJs(r.conclusion);var s=displayStatusJs(r);var rid=String(r.databaseId||'');var orv=(r.orv_id||'').trim();var idcell=orv?'<code title="'+esc(rid)+'">'+esc(orv)+'</code>':'<code>'+esc(rid)+'</code>';var q=(rid+' '+orv+' '+s).toLowerCase();return '<tr class="r-'+c+'" data-s="'+esc(sk)+'" data-q="'+esc(q)+'" data-rid="'+esc(rid)+'" data-orv="'+esc(orv)+'"><td>'+icoJs(sk==='in_progress'?'':r.conclusion)+'</td><td>'+idcell+'</td><td>'+agoJs(r.createdAt)+'</td><td><span class="b b-'+c+'">'+esc(s)+'</span></td><td><a href="https://github.com/daudjoss/daudjoss-vault/actions/runs/'+esc(rid)+'" target="_blank">↗</a></td></tr>';}).join('')}
function buildEncRows(runs){return (runs||[]).filter(function(r){return r.name==='rusemeva-encode'}).slice(0,20).map(function(r){var sk=statusKeyJs(r);var c=sk==='in_progress'?'running':clsJs(r.conclusion);var s=displayStatusJs(r);var rid=String(r.databaseId||'');var orv=(r.orv_id||'').trim();var idcell=orv?'<code title="'+esc(rid)+'">'+esc(orv)+'</code>':'<code>'+esc(rid)+'</code>';return '<tr data-s="'+esc(sk)+'" data-rid="'+esc(rid)+'" data-orv="'+esc(orv)+'"><td>'+icoJs(sk==='in_progress'?'':r.conclusion)+'</td><td>'+idcell+'</td><td>'+agoJs(r.createdAt)+'</td><td><span class="b b-'+c+'">'+esc(s)+'</span></td><td><a href="https://github.com/daudjoss/daudjoss-vault/actions/runs/'+esc(rid)+'" target="_blank">↗</a></td></tr>';}).join('')}
function applyOrvMap(data){var map=data.orv_map||[];if(!map.length)return data;var by={};map.forEach(function(x){if(x&&x.run_id&&x.orv_id)by[String(x.run_id)]={orv_id:x.orv_id,source:x.source||''}}); (data.runs||[]).forEach(function(r){var m=by[String(r.databaseId)];if(m){r.orv_id=m.orv_id;if(m.source)r.source=m.source}});return data}
function updateLiveUI(data){if(!data||!data.runs)return;data=applyOrvMap(data);window.DASH=window.DASH||{};window.DASH.generated=data.generated||window.DASH.generated;if(data.stats){window.DASH.stats=Object.assign({},window.DASH.stats||{},data.stats);if(data.stats.hours)window.DASH.hours=data.stats.hours;if(data.stats.days)window.DASH.days=data.stats.days;if(data.stats.daily)window.DASH.daily=data.stats.daily;if(data.stats.insights)window.DASH.insights=data.stats.insights;if(data.stats.predictions)window.DASH.predictions=data.stats.predictions;}window.DASH.runs=data.runs;if(data.releases)window.DASH.releases=data.releases;var feed=document.querySelector('#sec-feed .feed');if(feed){feed.innerHTML=buildFeedHtml(data.runs);feed.querySelectorAll('[data-cmp]').forEach(function(b){b.onclick=function(){toggleCmpPick(this.getAttribute('data-cmp'))}})};var rt=document.querySelector('#rt tbody');if(rt){var rows=buildRecRows(data.runs);if(rows)rt.innerHTML=rows}var encBody=document.querySelector('#et tbody');if(encBody){var erows=buildEncRows(data.runs);if(erows)encBody.innerHTML=erows}if(data.stats){var st=data.stats;function setTxt(id,val){var el=document.getElementById(id);if(el)el.textContent=val}if(st.total!=null)setTxt('st-total',st.total);if(st.success!=null)setTxt('st-success',st.success);if(st.failed!=null)setTxt('st-failed',st.failed);if(st.rate!=null){var elr=document.getElementById('st-rate');if(elr)elr.innerHTML=rateZoneHtml(st.rate)}if(st.enc!=null)setTxt('st-enc',st.enc);if(st.today!=null)setTxt('st-today',st.today);if(st.streak!=null)setTxt('st-streak',st.streak);var mon=document.querySelectorAll('.monitor-value');if(mon&&mon[2])mon[2].textContent=(st.running||0)+' running';var health=document.querySelector('#sec-health .sh span');if(health&&data.generated){try{health.textContent=new Date(data.generated).toLocaleString('sv-SE',{timeZone:'Asia/Jakarta'}).replace('T',' ')+' WIB'}catch(e){}}}var q=document.getElementById('q');if(q&&q.value)srch();var onFb=document.querySelector('.fb.on');if(onFb){var key=onFb.getAttribute('data-f')||'all';filt(key,onFb)}renderHero();checkHealth();applyDeepLink();updateTabTitle();updateFavicon();checkOffline();renderQChips();applyEmbedMode();applyAccent();renderColToggle();renderFlow();renderCounters();applyGlass();applyHC();applyFont();loadSnapshot();checkAchievements();renderStreakCal();renderFreqClock();renderDonutView();checkAchievements();renderHmMatrix();initQuickPanel();initBatchBar();hideSkeleton();checkNewRuns(data);updateTabTitle();updateFavicon();checkSoundAlert(data);checkStreakConfetti(data);markNewFeed(data);renderQChips();renderFlow();renderCounters();checkThresholdAlert();renderStreakCal();renderFreqClock();renderDonutView();checkAchievements();renderHmMatrix();startStopwatch();ariaAnnounce('Dashboard updated');checkAchievements()}

// ═══ v8.5 features ═══
function lastRsmHtml(){
  var D=window.DASH||{};var runs=D.runs||[];
  var v=runs.filter(function(r){return r.name==='rusemeva-vault'})[0];
  var e=runs.filter(function(r){return r.name==='rusemeva-encode'})[0];
  if(!v&&!e) return '<div class="rsm-card"><span class="rsm-ico">📭</span><span class="rsm-status">Belum ada run</span></div>';
  function card(r,label){if(!r)return '';var id=r.orv_id||r.databaseId||'';
    var s=displayStatusJs(r);var c=clsJs(r.conclusion);
    return '<div class="rsm-card"><span class="rsm-ico">'+icoJs(statusKeyJs(r)==='in_progress'?'':(r.conclusion||''))+'</span>'
      +'<div><span class="rsm-id">'+esc(id)+'</span> <span class="rsm-status">'+label+' · '+esc(s)+'</span></div>'
      +'<a class="rsm-link" href="https://github.com/daudjoss/daudjoss-vault/actions/runs/'+r.databaseId+'" target="_blank">GHA ↗</a></div>';}
  return card(v,'vault')+(e?card(e,'encode'):'');
}
function storageStoryHtml(){
  var st=(window.DASH||{}).stats||{};
  var gh=st.gh_bytes!=null?Number(st.gh_bytes):0;
  var life=st.lifetime_est_gb!=null?Number(st.lifetime_est_gb):0;
  var ghStr=gh>=1024*1024?(gh/1024/1024).toFixed(1)+' MB':Math.max(0,gh/1024).toFixed(0)+' KB';
  return '<b>GH:</b> '+ghStr+' (manifest .txt) · <b>Telegram:</b> ~'+life.toFixed(1)+' GB lifetime (est, video) · <b>temp:</b> 0 (dibersihkan)';
}
function diff24Html(){
  var D=window.DASH||{};var runs=D.runs||[];var st=D.stats||{};
  var now=Date.now();var h24=now-24*3600*1000;
  var v24=runs.filter(function(r){return r.name==='rusemeva-vault'&&new Date(r.createdAt||0).getTime()>=h24});
  var e24=runs.filter(function(r){return r.name==='rusemeva-encode'&&new Date(r.createdAt||0).getTime()>=h24});
  var vf=v24.filter(function(r){return r.conclusion==='failure'}).length;
  var es=e24.filter(function(r){return r.conclusion==='success'}).length;
  return '<span class="diff-chip">24h vault: <b>'+v24.length+'</b></span>'
    +'<span class="diff-chip">fail baru: <b>'+vf+'</b></span>'
    +'<span class="diff-chip">enc selesai: <b>'+es+'</b></span>'
    +'<span class="diff-chip">streak: <b>'+(st.streak||0)+'d</b></span>';
}


var lastRunId=0;
function checkNewRuns(data){
  if(!('Notification'in window)||Notification.permission!=='granted')return;
  var runs=data.runs||[];
  if(!runs.length)return;
  var latest=runs[0];
  var rid=latest.databaseId||0;
  if(lastRunId===0){lastRunId=rid;return;}
  if(rid>lastRunId){
    var id=latest.orv_id||rid;
    var s=displayStatusJs(latest);
    try{new Notification('Rusemeva: '+id,{body:latest.name+' → '+s})}catch(e){}
    lastRunId=rid;
  }
}


var deferredPrompt=null;
window.addEventListener('beforeinstallprompt',function(e){e.preventDefault();deferredPrompt=e;var b=document.getElementById('pwaInstall');if(b)b.style.display='inline-block'});
function installPWA(){if(deferredPrompt){deferredPrompt.prompt();deferredPrompt.userChoice.then(function(){deferredPrompt=null;var b=document.getElementById('pwaInstall');if(b)b.style.display='none'})}}

function openCheat(){document.getElementById('cheatOverlay').classList.add('on')}
function closeCheat(){document.getElementById('cheatOverlay').classList.remove('on')}

function shareCard(){
  var st=(window.DASH||{}).stats||{};
  var c=document.createElement('canvas');c.width=400;c.height=200;
  var ctx=c.getContext('2d');
  var bg=getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()||'#0d1117';
  var t1=getComputedStyle(document.documentElement).getPropertyValue('--t1').trim()||'#e6edf3';
  var t2=getComputedStyle(document.documentElement).getPropertyValue('--t2').trim()||'#7d8590';
  var bl=getComputedStyle(document.documentElement).getPropertyValue('--bl').trim()||'#58a6ff';
  var gn=getComputedStyle(document.documentElement).getPropertyValue('--gn').trim()||'#3fb950';
  var or=getComputedStyle(document.documentElement).getPropertyValue('--or').trim()||'#f0883e';
  ctx.fillStyle=bg;ctx.fillRect(0,0,400,200);
  ctx.fillStyle=t1;ctx.font='bold 20px sans-serif';ctx.fillText('🎬 Rusemeva',20,35);
  ctx.fillStyle=t2;ctx.font='11px sans-serif';ctx.fillText(new Date().toLocaleDateString('en-GB',{timeZone:'Asia/Jakarta',weekday:'short',day:'numeric',month:'short'}),20,52);
  // stats
  ctx.fillStyle=bl;ctx.font='bold 28px sans-serif';ctx.fillText(st.total||0,20,100);
  ctx.fillStyle=t2;ctx.font='10px sans-serif';ctx.fillText('Vault total',20,115);
  ctx.fillStyle=gn;ctx.font='bold 28px sans-serif';ctx.fillText(st.success||0,120,100);
  ctx.fillStyle=t2;ctx.font='10px sans-serif';ctx.fillText('Success',120,115);
  ctx.fillStyle=or;ctx.font='bold 28px sans-serif';ctx.fillText((st.rate||0)+'%',220,100);
  ctx.fillStyle=t2;ctx.font='10px sans-serif';ctx.fillText('Rate',220,115);
  ctx.fillStyle=bl;ctx.font='bold 28px sans-serif';ctx.fillText(st.streak||0,320,100);
  ctx.fillStyle=t2;ctx.font='10px sans-serif';ctx.fillText('Streak (d)',320,115);
  // footer
  ctx.fillStyle=t2;ctx.font='9px sans-serif';ctx.fillText('daudjoss.github.io/daudjoss-vault',20,180);
  var a=document.createElement('a');a.href=c.toDataURL('image/png');a.download='rusemeva-stats.png';a.click();
}

// ═══ v8.7 features ═══

// ═══ v8.8 features ═══
function animateCounter(el,target,suffix){
  if(!el)return;var start=0,duration=800,startTime=null;
  suffix=suffix||'';
  function step(ts){if(!startTime)startTime=ts;var prog=Math.min((ts-startTime)/duration,1);
    var val=Math.floor(prog*target);el.textContent=val+suffix;
    if(prog<1)requestAnimationFrame(step);else el.textContent=target+suffix}
  requestAnimationFrame(step);
}
function renderCounters(){
  var st=(window.DASH||{}).stats||{};
  var map={'st-total':st.total,'st-success':st.success,'st-failed':st.failed,'st-enc':st.enc,'st-today':st.today,'st-streak':st.streak};
  for(var id in map){var el=document.getElementById(id);if(el&&!el.getAttribute('data-animated')){el.setAttribute('data-animated','1');var v=map[id];if(v!=null)animateCounter(el,v)}}
}
function renderFlow(){
  var D=window.DASH||{};var runs=D.runs||[];
  var vault=runs.filter(function(r){return r.name==='rusemeva-vault'})[0];
  var enc=runs.filter(function(r){return r.name==='rusemeva-encode'})[0];
  var vs=vault?displayStatusJs(vault):'—';var es=enc?displayStatusJs(enc):'—';
  var vc=vault?(vault.conclusion==='success'?'var(--gn)':(vault.conclusion==='failure'?'var(--rd)':'var(--bl)')):'var(--t2)';
  var ec=enc?(enc.conclusion==='success'?'var(--gn)':(enc.conclusion==='failure'?'var(--rd)':'var(--bl)')):'var(--t2)';
  var html='<div class="flow-diagram">'
    +'<div class="flow-node vault" style="border-color:'+vc+'">📹 Vault<br><b style="color:'+vc+'">'+vs+'</b></div>'
    +'<div class="flow-arrow">→</div>'
    +'<div class="flow-node encode" style="border-color:'+ec+'">🎞 Encode<br><b style="color:'+ec+'">'+es+'</b></div>'
    +'<div class="flow-arrow">→</div>'
    +'<div class="flow-node telegram">📱 Telegram<br><b style="color:var(--gn)">delivery</b></div>'
    +'</div>';
  var el=document.getElementById('flow-diagram');if(el)el.innerHTML=html;
}
function renderRings(){
  var D=window.DASH||{};var st=D.stats||{};var daily=D.daily||D.stats&&D.stats.daily||{};
  var today=new Date().toLocaleDateString('sv-SE',{timeZone:'Asia/Jakarta'});
  var todayCount=daily[today]||0;var weekCount=0;var monthCount=0;
  var now=new Date();
  for(var i=0;i<7;i++){var d=new Date(now.getTime()-i*86400000);var key=d.toLocaleDateString('sv-SE',{timeZone:'Asia/Jakarta'});weekCount+=(daily[key]||0)}
  for(var i=0;i<30;i++){var d=new Date(now.getTime()-i*86400000);var key=d.toLocaleDateString('sv-SE',{timeZone:'Asia/Jakarta'});monthCount+=(daily[key]||0)}
  var dTarget=st.best||3;var wTarget=(st.best||3)*7;var mTarget=(st.best||3)*30;
  function ringPct(val,target){return Math.min(val/(target||1),1)}
  var r1=20,r2=28,r3=36;var c1=2*Math.PI*r1,c2=2*Math.PI*r2,c3=2*Math.PI*r3;
  var svg='<div class="activity-rings"><svg width="80" height="80">'
    +'<circle class="ring-bg" cx="40" cy="40" r="'+r1+'"/><circle class="ring-fg" cx="40" cy="40" r="'+r1+'" stroke="var(--rd)" stroke-dasharray="'+c1+'" stroke-dashoffset="'+(c1-ringPct(todayCount,dTarget)*c1)+'"/>'
    +'<circle class="ring-bg" cx="40" cy="40" r="'+r2+'"/><circle class="ring-fg" cx="40" cy="40" r="'+r2+'" stroke="var(--or)" stroke-dasharray="'+c2+'" stroke-dashoffset="'+(c2-ringPct(weekCount,wTarget)*c2)+'"/>'
    +'<circle class="ring-bg" cx="40" cy="40" r="'+r3+'"/><circle class="ring-fg" cx="40" cy="40" r="'+r3+'" stroke="var(--bl)" stroke-dasharray="'+c3+'" stroke-dashoffset="'+(c3-ringPct(monthCount,mTarget)*c3)+'"/>'
    +'</svg></div>';
  var el=document.getElementById('hero-rings');
  if(el)el.innerHTML=svg+'<div style="font-size:9px;color:var(--t2);text-align:center;margin-top:2px">D:'+todayCount+'/'+dTarget+' W:'+weekCount+' M:'+monthCount+'</div>';
}
function renderGantt(){
  var D=window.DASH||{};var runs=(D.runs||[]).filter(function(r){return r.name==='rusemeva-vault'||r.name==='rusemeva-encode'}).slice(0,20);
  if(!runs.length)return '<div style="color:var(--t2);font-size:11px">No runs</div>';
  var now=Date.now();var earliest=now;var latest=now;
  runs.forEach(function(r){var c=new Date(r.createdAt||0).getTime();if(c<earliest)earliest=c;var u=new Date(r.updatedAt||r.createdAt||0).getTime();if(u>latest)latest=u});
  var span=Math.max(latest-earliest,3600000);
  var html='<div class="gantt-wrap">';
  runs.forEach(function(r){
    var start=new Date(r.createdAt||0).getTime();var end=new Date(r.updatedAt||r.createdAt||0).getTime();
    if(end<=start)end=start+300000;
    var leftPct=((start-earliest)/span)*100;var widthPct=Math.max(((end-start)/span)*100,1);
    var col=r.conclusion==='success'?'var(--gn)':(r.conclusion==='failure'?'var(--rd)':(r.name==='rusemeva-encode'?'var(--or)':'var(--bl)'));
    var label=(r.orv_id||r.databaseId||'').toString().slice(0,12);
    html+='<div class="gantt-row"><div class="gantt-label">'+esc(label)+'</div><div class="gantt-bar-wrap"><div class="gantt-bar" style="left:'+leftPct+'%;width:'+widthPct+'%;background:'+col+'" title="'+esc(r.name||'')+' '+esc(displayStatusJs(r))+'"></div></div></div>';
  });
  html+='</div>';
  return html;
}
function showFailReplay(){
  var D=window.DASH||{};var runs=D.runs||[];
  var fails=runs.filter(function(r){return r.conclusion==='failure'}).slice(0,5);
  if(!fails.length)return '<div style="color:var(--t2);font-size:11px">No recent fails 🎉</div>';
  return fails.map(function(r){
    var id=r.orv_id||r.databaseId||'';
    return '<div class="fail-replay-item"><div style="display:flex;justify-content:space-between"><b style="color:var(--rd)">❌ '+esc(id)+'</b><span style="font-size:10px;color:var(--t2)">'+agoJs(r.createdAt||'')+'</span></div><div style="font-size:10px;color:var(--t2);margin-top:4px">'+esc(r.name||'')+'</div><div style="margin-top:4px"><a href="https://github.com/daudjoss/daudjoss-vault/actions/runs/'+r.databaseId+'" target="_blank" style="font-size:10px">View log ↗</a></div></div>';
  }).join('');
}
function saveRunNote(rid){
  var note=prompt('Note for '+rid+':');if(!note)return;
  var notes=JSON.parse(localStorage.getItem('dash_runnotes')||'{}');
  notes[rid]=note;localStorage.setItem('dash_runnotes',JSON.stringify(notes));
  showToast('Note saved for '+rid);
}
function getRunNote(rid){
  var notes=JSON.parse(localStorage.getItem('dash_runnotes')||'{}');
  return notes[rid]||'';
}
function generateReport(){
  var D=window.DASH||{};var st=D.stats||{};var runs=D.runs||[];
  var today=new Date().toLocaleDateString('en-GB',{weekday:'long',timeZone:'Asia/Jakarta'});
  var encOk=st.enc_ok||0;var rate=st.rate||0;
  var txt='📊 Rusemeva Weekly Report\\n';
  txt+='Tanggal: '+new Date().toLocaleDateString('en-GB',{timeZone:'Asia/Jakarta'})+'\\n\\n';
  txt+='Vault: '+st.total+' runs ('+st.success+' OK, '+st.failed+' fail)\\n';
  txt+='Rate: '+rate+'%\\n';
  txt+='Encode: '+encOk+' OK\\n';
  txt+='Streak: '+(st.streak||0)+' hari\\n';
  txt+='Today: '+(st.today||0)+' runs ('+today+')\\n\\n';
  var fails=runs.filter(function(r){return r.conclusion==='failure'}).slice(0,3);
  if(fails.length){txt+='Last fails:\\n';fails.forEach(function(r){txt+='• '+(r.orv_id||r.databaseId)+' — '+agoJs(r.createdAt||'')+'\\n'})}
  txt+='\\nDashboard: daudjoss.github.io/daudjoss-vault/';
  return txt;
}
function getAlertThreshold(){
  return parseInt(localStorage.getItem('dash_threshold')||'2',10);
}
function checkThresholdAlert(){
  var D=window.DASH||{};var st=D.stats||{};
  var fails=st.failed||0;var threshold=getAlertThreshold();
  var el=document.getElementById('hero-alert');if(!el)return;
  if(fails>=threshold){el.innerHTML='<div class="alert-chip">⚠️ '+fails+' fail ≥ threshold '+threshold+'</div>'}
  else{el.innerHTML=''}
}
function applyEmbedMode(){
  var p=new URLSearchParams(location.search);
  if(p.get('embed')==='1'){
    var hides=['.bnav','.tools-panel','.sec-feed','.sec-health','.sec-week','#sec-flow','#sec-heatmap','.hero-actions','#qchips','.fb-row'];
    hides.forEach(function(s){var els=document.querySelectorAll(s);els.forEach(function(e){e.classList.add('embed-hide')})});
    document.body.classList.add('embed-mode');
  }
}
var ACCENTS={'blue':'#58a6ff','green':'#3fb950','purple':'#bc8cff','orange':'#f0883e'};
function applyAccent(){
  var c=localStorage.getItem('dash_accent')||'blue';var col=ACCENTS[c]||ACCENTS.blue;
  document.documentElement.style.setProperty('--bl',col);
}
function setAccent(c){
  localStorage.setItem('dash_accent',c);applyAccent();
  document.querySelectorAll('.accent-swatch').forEach(function(s){s.classList.toggle('sel',s.getAttribute('data-accent')===c)});
}
function renderColToggle(){
  var cols=[['icon','✅'],['id','ID'],['time','Time'],['status','Status'],['link','↗']];
  var html=cols.map(function(c){
    var hidden=localStorage.getItem('dash_col_'+c[0])==='1';
    return '<span class="col-tog-btn'+(hidden?'':' on')+'" onclick="toggleCol(\\''+c[0]+'\\')">'+c[1]+'</span>';
  }).join('');
  var el=document.getElementById('colToggle');if(el)el.innerHTML=html;
  applyColVisibility();
}
function toggleCol(key){
  var hidden=localStorage.getItem('dash_col_'+key)==='1';
  localStorage.setItem('dash_col_'+key,hidden?'0':'1');
  renderColToggle();
}
function applyColVisibility(){
  var cols=['icon','id','time','status','link'];
  cols.forEach(function(c){
    var hidden=localStorage.getItem('dash_col_'+c)==='1';
    var idx={'icon':0,'id':1,'time':2,'status':3,'link':4}[c];
    document.querySelectorAll('#rt tr').forEach(function(tr){
      var tds=tr.querySelectorAll('td,th');if(tds[idx])tds[idx].style.display=hidden?'none':'';
    });
  });
}
var kbNavIdx=-1;
function kbNav(dir){
  var rows=document.querySelectorAll('#rt tbody tr');
  if(!rows.length)return;
  if(kbNavIdx>=0&&rows[kbNavIdx])rows[kbNavIdx].classList.remove('kb-nav-hl');
  kbNavIdx+=dir;
  if(kbNavIdx<0)kbNavIdx=0;if(kbNavIdx>=rows.length)kbNavIdx=rows.length-1;
  rows[kbNavIdx].classList.add('kb-nav-hl');
  rows[kbNavIdx].scrollIntoView({block:'nearest',behavior:'smooth'});
}
function kbNavOpen(){
  var rows=document.querySelectorAll('#rt tbody tr');
  if(kbNavIdx>=0&&rows[kbNavIdx]){
    var link=rows[kbNavIdx].querySelector('a');
    if(link)link.click();
  }
}
function genCurl(method,url){
  if(method==='GET')return 'curl '+url;
  return 'curl -X '+method+' '+url;
}
function copyCurl(url){
  navigator.clipboard.writeText('curl '+url).then(function(){showToast('cURL copied!')}).catch(function(){})
}


// ═══ v10.1 Enriched Data Features ═══
function renderTriggerAnalysis(){
  var D=window.DASH||{};var runs=D.runs||[];
  var triggers={};
  runs.forEach(function(r){
    var ev=r.event||'unknown';
    if(!triggers[ev])triggers[ev]={total:0,success:0,fail:0};
    triggers[ev].total++;
    if(r.conclusion==='success')triggers[ev].success++;
    if(r.conclusion==='failure')triggers[ev].fail++;
  });
  var icons={'push':'📤','schedule':'⏰','workflow_dispatch':'👤','pull_request':'🔀','release':'🏷️','repository_dispatch':'📡','unknown':'❓'};
  var html='<div style="padding:10px">';
  html+='<div class="trigger-grid">';
  var sorted=Object.keys(triggers).sort(function(a,b){return triggers[b].total-triggers[a].total});
  sorted.forEach(function(ev){
    var d=triggers[ev];
    var pct=d.total?Math.round(d.success/d.total*100):0;
    var col=pct>=80?'var(--gn)':pct>=50?'var(--yl)':'var(--rd)';
    html+='<div class="trigger-card"><div class="trigger-icon">'+(icons[ev]||'❓')+'</div><div class="trigger-name">'+ev+'</div><div class="trigger-count" style="color:'+col+'">'+d.total+'</div><div style="font-size:8px;color:var(--t2)">'+pct+'% ok</div></div>';
  });
  html+='</div>';
  var total=runs.length||1;
  html+='<div style="margin-top:8px;font-size:11px;color:var(--t2)">Distribution:</div>';
  sorted.forEach(function(ev){
    var d=triggers[ev];
    var pct=Math.round(d.total/total*100);
    html+='<div style="margin:4px 0"><div style="font-size:10px;display:flex;justify-content:space-between"><span>'+(icons[ev]||'')+' '+ev+'</span><span>'+d.total+' ('+pct+'%)</span></div><div class="trigger-bar" style="width:'+pct+'%"></div></div>';
  });
  html+='</div>';
  return html;
}

function renderRunNumberTracker(){
  var D=window.DASH||{};var runs=D.runs||[];
  var withNum=runs.filter(function(r){return r.runNumber}).sort(function(a,b){return (b.runNumber||0)-(a.runNumber||0)});
  if(!withNum.length)return'<div style="padding:10px;color:var(--t2)">No run numbers available</div>';
  var nums=withNum.map(function(r){return r.runNumber});
  var max=Math.max.apply(null,nums);
  var min=Math.min.apply(null,nums);
  var expected=max-min+1;
  var gaps=expected-nums.length;
  var html='<div style="padding:10px">';
  html+='<div class="metric-grid">';
  html+='<div class="metric-mini"><div class="metric-mini-val">'+max+'</div><div class="metric-mini-lbl">Latest Run #</div></div>';
  html+='<div class="metric-mini"><div class="metric-mini-val">'+min+'</div><div class="metric-mini-lbl">Oldest Run #</div></div>';
  html+='<div class="metric-mini"><div class="metric-mini-val '+(gaps>0?'warn':'ok')+'">'+gaps+'</div><div class="metric-mini-lbl">Missing Runs</div></div>';
  html+='</div>';
  if(gaps>0){
    var numSet={};
    nums.forEach(function(n){numSet[n]=true});
    var missing=[];
    for(var i=min;i<=max;i++){if(!numSet[i])missing.push(i)}
    html+='<div style="margin-top:8px;font-size:11px;color:var(--rd)">⚠️ '+missing.length+' run number(s) missing (deleted or expired):</div>';
    html+='<div style="max-height:120px;overflow:auto;margin-top:4px">';
    missing.slice(0,20).forEach(function(n){
      html+='<div class="runnum-row"><span class="runnum-gap">#'+n+'</span><span style="color:var(--t2)">missing</span><span>—</span></div>';
    });
    if(missing.length>20)html+='<div style="font-size:9px;color:var(--t2);padding:4px">+'+(missing.length-20)+' more...</div>';
    html+='</div>';
  }else{
    html+='<div style="text-align:center;color:var(--gn);padding:10px">No gaps! All '+nums.length+' runs present ✅</div>';
  }
  html+='</div>';
  return html;
}

function renderCommitMessages(){
  var D=window.DASH||{};var runs=D.runs||[];
  var withTitle=runs.filter(function(r){return r.displayTitle}).slice(0,30);
  if(!withTitle.length)return'<div style="padding:10px;color:var(--t2)">No commit messages available</div>';
  var html='<div style="padding:10px">';
  html+='<div style="font-size:12px;font-weight:700;margin-bottom:8px">📋 Commit Messages → Run Results</div>';
  withTitle.forEach(function(r){
    var sha=(r.headSha||'').substring(0,7);
    var col=r.conclusion==='success'?'var(--gn)':'var(--rd)';
    var time=r.createdAt?new Date(r.createdAt).toLocaleString('en-GB',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',timeZone:'Asia/Jakarta'}):'';
    html+='<div class="commit-msg"><span class="commit-msg-sha">'+sha+'</span> <span style="color:'+col+'">'+(r.conclusion==='success'?'✅':'❌')+'</span> '+esc(r.displayTitle||'')+'<br><span style="color:var(--t3);font-size:8px">'+time+' WIB · #'+(r.runNumber||'')+' · '+(r.headBranch||'')+'</span></div>';
  });
  html+='</div>';
  return html;
}

function renderEventTimeline(){
  var D=window.DASH||{};var runs=D.runs||[];
  if(!runs.length)return'<div style="padding:10px;color:var(--t2)">No runs</div>';
  var sorted=runs.slice().sort(function(a,b){return new Date(a.createdAt||0)-new Date(b.createdAt||0)});
  var html='<div style="padding:10px">';
  html+='<div style="font-size:12px;font-weight:700;margin-bottom:8px">📅 Event Timeline (chronological)</div>';
  var byEvent={};
  sorted.forEach(function(r){
    var ev=r.event||'unknown';
    if(!byEvent[ev])byEvent[ev]=[];
    byEvent[ev].push(r);
  });
  Object.keys(byEvent).forEach(function(ev){
    var items=byEvent[ev];
    var success=items.filter(function(r){return r.conclusion==='success'}).length;
    var pct=items.length?Math.round(success/items.length*100):0;
    html+='<div style="margin:8px 0;padding:8px;border:1px solid var(--brd);border-radius:8px">';
    html+='<div style="font-size:11px;font-weight:700;margin-bottom:4px">'+ev+' <span style="color:var(--t2)">('+items.length+' runs, '+pct+'% success)</span></div>';
    items.slice(-5).reverse().forEach(function(r){
      var time=r.createdAt?new Date(r.createdAt).toLocaleString('en-GB',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',timeZone:'Asia/Jakarta'}):'';
      var col=r.conclusion==='success'?'var(--gn)':'var(--rd)';
      html+='<div style="font-size:9px;padding:2px 0;color:var(--t2)"><span style="color:'+col+'">'+(r.conclusion==='success'?'✅':'❌')+'</span> '+time+' · #'+(r.runNumber||'')+' · '+(r.displayTitle||r.name||'').substring(0,30)+'</div>';
    });
    if(items.length>5)html+='<div style="font-size:8px;color:var(--t3);padding:2px">+'+(items.length-5)+' more...</div>';
    html+='</div>';
  });
  html+='</div>';
  return html;
}

function renderRunNumberGap(){
  var D=window.DASH||{};var runs=D.runs||[];
  var withNum=runs.filter(function(r){return r.runNumber}).sort(function(a,b){return (a.runNumber||0)-(b.runNumber||0)});
  if(withNum.length<2)return'<div style="padding:10px;color:var(--t2)">Need at least 2 runs with run numbers</div>';
  var gaps=[];
  for(var i=1;i<withNum.length;i++){
    var prev=withNum[i-1].runNumber;
    var curr=withNum[i].runNumber;
    if(curr-prev>1){
      gaps.push({from:prev+1,to:curr-1,count:curr-prev-1});
    }
  }
  var totalMissing=gaps.reduce(function(a,g){return a+g.count},0);
  var html='<div style="padding:10px">';
  html+='<div class="metric-grid">';
  html+='<div class="metric-mini"><div class="metric-mini-val">'+gaps.length+'</div><div class="metric-mini-lbl">Gap Periods</div></div>';
  html+='<div class="metric-mini"><div class="metric-mini-val '+(totalMissing>0?'warn':'ok')+'">'+totalMissing+'</div><div class="metric-mini-lbl">Total Missing</div></div>';
  html+='</div>';
  if(gaps.length===0){
    html+='<div style="text-align:center;color:var(--gn);padding:10px">No gaps! Consecutive run numbers ✅</div>';
  }else{
    html+='<div style="margin-top:8px;font-size:11px;color:var(--t2)">Gap details:</div>';
    gaps.forEach(function(g){
      html+='<div style="margin:4px 0;padding:6px;border:1px solid var(--brd);border-radius:6px;font-size:10px"><span style="color:var(--rd)">⚠️ #'+g.from;
      if(g.count>1)html+=' → #'+g.to;
      html+='</span> <span style="color:var(--t2)">'+g.count+' run(s) missing</span></div>';
    });
  }
  html+='</div>';
  return html;
}


// ═══ v10.0 CI/CD Metrics ═══
function renderDeployFrequency(){
  var D=window.DASH||{};var runs=D.runs||[];
  var success=runs.filter(function(r){return r.conclusion==='success'});
  var days={};
  success.forEach(function(r){
    if(!r.createdAt)return;
    var d=new Date(r.createdAt);
    var key=d.getFullYear()+'-'+('0'+(d.getMonth()+1)).slice(-2)+'-'+('0'+d.getDate()).slice(-2);
    days[key]=(days[key]||0)+1;
  });
  var dayCount=Object.keys(days).length||1;
  var freq=(success.length/dayCount).toFixed(1);
  var totalDays=Math.max(1,Math.ceil((Date.now()-(runs[runs.length-1]||{}).createdAt||Date.now())/86400000));
  var html='<div style="padding:10px">';
  html+='<div class="metric-grid">';
  html+='<div class="metric-mini"><div class="metric-mini-val ok">'+freq+'</div><div class="metric-mini-lbl">Deploys/Day</div></div>';
  html+='<div class="metric-mini"><div class="metric-mini-val">'+success.length+'</div><div class="metric-mini-lbl">Total Deploys</div></div>';
  html+='<div class="metric-mini"><div class="metric-mini-val">'+dayCount+'</div><div class="metric-mini-lbl">Active Days</div></div>';
  html+='</div>';
  var weekData=[];
  var now=new Date();
  for(var i=6;i>=0;i--){
    var d=new Date(now.getTime()-i*86400000);
    var key=d.getFullYear()+'-'+('0'+(d.getMonth()+1)).slice(-2)+'-'+('0'+d.getDate()).slice(-2);
    var count=days[key]||0;
    weekData.push(count);
  }
  var maxW=Math.max.apply(null,weekData)||1;
  html+='<div class="hour-bar">';
  weekData.forEach(function(c){
    var h=Math.max(2,(c/maxW*56));
    html+='<div class="hour-col" style="height:'+h+'px" title="'+c+' deploys"></div>';
  });
  html+='</div><div style="display:flex;justify-content:space-between;font-size:8px;color:var(--t2)"><span>7d ago</span><span>Today</span></div>';
  html+='</div>';
  return html;
}

function renderMTTR(){
  var D=window.DASH||{};var runs=D.runs||[];
  var fails=runs.filter(function(r){return r.conclusion==='failure'});
  var recoveries=[];
  for(var i=0;i<fails.length;i++){
    var failTime=new Date(fails[i].createdAt||0).getTime();
    for(var j=0;j<runs.length;j++){
      if(runs[j].conclusion==='success'){
        var succTime=new Date(runs[j].createdAt||0).getTime();
        if(succTime>failTime){
          recoveries.push(Math.round((succTime-failTime)/60000));
          break;
        }
      }
    }
  }
  var avgMTTR=recoveries.length?Math.round(recoveries.reduce(function(a,b){return a+b},0)/recoveries.length):0;
  var maxMTTR=recoveries.length?Math.max.apply(null,recoveries):0;
  var html='<div style="padding:10px">';
  html+='<div class="metric-grid">';
  html+='<div class="metric-mini"><div class="metric-mini-val '+(avgMTTR<30?'ok':avgMTTR<60?'warn':'bad')+'">'+avgMTTR+'m</div><div class="metric-mini-lbl">Avg MTTR</div></div>';
  html+='<div class="metric-mini"><div class="metric-mini-val">'+maxMTTR+'m</div><div class="metric-mini-lbl">Max MTTR</div></div>';
  html+='<div class="metric-mini"><div class="metric-mini-val">'+recoveries.length+'</div><div class="metric-mini-lbl">Recoveries</div></div>';
  html+='</div>';
  if(recoveries.length>0){
    html+='<div style="margin-top:8px;font-size:11px;color:var(--t2)">Recent recovery times:</div>';
    recoveries.slice(0,5).forEach(function(r,i){
      html+='<div class="retry-row"><span>Recovery #'+(i+1)+'</span><span style="color:'+(r<30?'var(--gn)':r<60?'var(--yl)':'var(--rd)')+'">'+r+' min</span></div>';
    });
  }else{
    html+='<div style="text-align:center;color:var(--gn);padding:10px">No failures detected! 🎉</div>';
  }
  html+='</div>';
  return html;
}

function renderCFR(){
  var D=window.DASH||{};var runs=D.runs||[];var st=D.stats||{};
  var total=st.total||runs.length||1;
  var failed=st.failed||0;
  var cfr=Math.round(failed/total*100);
  var html='<div style="padding:10px">';
  html+='<div class="metric-grid">';
  html+='<div class="metric-mini"><div class="metric-mini-val '+(cfr<10?'ok':cfr<25?'warn':'bad')+'">'+cfr+'%</div><div class="metric-mini-lbl">Change Fail Rate</div></div>';
  html+='<div class="metric-mini"><div class="metric-mini-val">'+failed+'</div><div class="metric-mini-lbl">Failed Runs</div></div>';
  html+='<div class="metric-mini"><div class="metric-mini-val">'+total+'</div><div class="metric-mini-lbl">Total Runs</div></div>';
  html+='</div>';
  var weeks={};
  runs.forEach(function(r){
    if(!r.createdAt)return;
    var d=new Date(r.createdAt);
    var week=Math.floor(d.getDate()/7);
    var key=d.getFullYear()+'-'+('0'+(d.getMonth()+1)).slice(-2)+'-W'+week;
    if(!weeks[key])weeks[key]={total:0,fail:0};
    weeks[key].total++;
    if(r.conclusion==='failure')weeks[key].fail++;
  });
  var wKeys=Object.keys(weeks).slice(-4);
  html+='<div style="margin-top:8px;font-size:11px;color:var(--t2)">Weekly failure rate:</div>';
  wKeys.forEach(function(k){
    var w=weeks[k];
    var pct=w.total?Math.round(w.fail/w.total*100):0;
    html+='<div style="margin:4px 0"><div style="font-size:10px;display:flex;justify-content:space-between"><span>'+k+'</span><span style="color:'+(pct<25?'var(--gn)':'var(--rd)')+'">'+pct+'% ('+w.fail+'/'+w.total+')</span></div><div style="height:6px;background:var(--bg3);border-radius:3px;margin-top:2px"><div style="height:100%;width:'+pct+'%;background:'+(pct<25?'var(--gn)':'var(--rd)')+';border-radius:3px"></div></div></div>';
  });
  html+='</div>';
  return html;
}

function renderLeadTime(){
  var D=window.DASH||{};var runs=D.runs||[];
  var durations=runs.map(function(r){return r.updatedAt&&r.createdAt?Math.round((r.updatedAt-r.createdAt)/60000):0}).filter(function(d){return d>0});
  var avg=durations.length?Math.round(durations.reduce(function(a,b){return a+b},0)/durations.length):0;
  var min=durations.length?Math.min.apply(null,durations):0;
  var max=durations.length?Math.max.apply(null,durations):0;
  var html='<div style="padding:10px">';
  html+='<div class="metric-grid">';
  html+='<div class="metric-mini"><div class="metric-mini-val '+(avg<10?'ok':avg<30?'warn':'bad')+'">'+avg+'m</div><div class="metric-mini-lbl">Avg Lead Time</div></div>';
  html+='<div class="metric-mini"><div class="metric-mini-val">'+min+'m</div><div class="metric-mini-lbl">Fastest</div></div>';
  html+='<div class="metric-mini"><div class="metric-mini-val">'+max+'m</div><div class="metric-mini-lbl">Slowest</div></div>';
  html+='</div></div>';
  return html;
}

function renderFailurePattern(){
  var D=window.DASH||{};var runs=D.runs||[];
  var fails=runs.filter(function(r){return r.conclusion==='failure'});
  var byHour={};
  var byDay={};
  fails.forEach(function(r){
    if(!r.createdAt)return;
    var d=new Date(r.createdAt);
    var h=d.getHours();
    byHour[h]=(byHour[h]||0)+1;
    var day=d.getDay();
    byDay[day]=(byDay[day]||0)+1;
  });
  var dayNames=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  var html='<div style="padding:10px">';
  html+='<div style="font-size:12px;font-weight:700;margin-bottom:8px">By Day of Week</div>';
  html+='<div class="pattern-grid">';
  for(var i=0;i<7;i++){
    var count=byDay[i]||0;
    var cls=count===0?'empty':count>=3?'fail':'s'+Math.min(4,count);
    html+='<div class="pattern-cell '+cls+'">'+dayNames[i][0]+'</div>';
  }
  html+='</div><div class="pattern-label">'+dayNames.join(' ')+'</div>';
  html+='<div style="font-size:12px;font-weight:700;margin:12px 0 8px">By Hour (WIB)</div>';
  var maxH=Math.max.apply(null,Object.values(byHour).concat([1]));
  html+='<div class="hour-bar">';
  for(var h=0;h<24;h++){
    var count=byHour[h]||0;
    var height=Math.max(2,count/maxH*56);
    html+='<div class="hour-col fail" style="height:'+height+'px" title="'+h+':00 - '+count+' fails"></div>';
  }
  html+='</div><div style="display:flex;justify-content:space-between;font-size:8px;color:var(--t2)"><span>00:00</span><span>12:00</span><span>23:00</span></div>';
  html+='</div>';
  return html;
}

function renderDurationTrend(){
  var D=window.DASH||{};var runs=D.runs||[];
  var withDur=runs.filter(function(r){return r.updatedAt&&r.createdAt}).slice(0,30).reverse();
  if(!withDur.length)return'<div style="padding:10px;color:var(--t2)">No duration data</div>';
  var durations=withDur.map(function(r){return Math.round((r.updatedAt-r.createdAt)/60000)});
  var maxD=Math.max.apply(null,durations)||1;
  var avg=Math.round(durations.reduce(function(a,b){return a+b},0)/durations.length);
  var recent=durations.slice(-5);
  var recentAvg=Math.round(recent.reduce(function(a,b){return a+b},0)/recent.length);
  var trend=recentAvg>avg*1.2?'up':recentAvg<avg*0.8?'down':'';
  var html='<div style="padding:10px">';
  html+='<div class="metric-grid">';
  html+='<div class="metric-mini"><div class="metric-mini-val">'+avg+'m</div><div class="metric-mini-lbl">Avg Duration</div></div>';
  html+='<div class="metric-mini"><div class="metric-mini-val '+(!trend?'ok':'')+'">'+recentAvg+'m</div><div class="metric-mini-lbl">Recent Avg</div></div>';
  html+='<div class="metric-mini"><div class="metric-mini-val '+(trend==='up'?'bad':'ok')+'">'+(trend==='up'?'📈':trend==='down'?'📉':'➡')+'</div><div class="metric-mini-lbl">Trend</div></div>';
  html+='</div>';
  html+='<div class="duration-trend">';
  durations.forEach(function(d,i){
    var h=Math.max(2,d/maxD*40);
    html+='<div style="display:inline-block;width:6px;height:'+h+'px;background:'+(d>avg*1.5?'var(--rd)':'var(--bl)')+';margin-right:1px;border-radius:2px 2px 0 0" title="Run '+(i+1)+': '+d+'m"></div>';
  });
  html+='</div><div style="font-size:8px;color:var(--t2)">Last '+durations.length+' runs (oldest → newest)</div>';
  html+='</div>';
  return html;
}

function renderSuccessByDay(){
  var D=window.DASH||{};var runs=D.runs||[];
  var byDay={};
  runs.forEach(function(r){
    if(!r.createdAt)return;
    var d=new Date(r.createdAt);
    var day=d.getDay();
    if(!byDay[day])byDay[day]={total:0,success:0};
    byDay[day].total++;
    if(r.conclusion==='success')byDay[day].success++;
  });
  var dayNames=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  var html='<div style="padding:10px">';
  html+='<div style="font-size:12px;font-weight:700;margin-bottom:8px">Success Rate by Day of Week</div>';
  for(var i=0;i<7;i++){
    var d=byDay[i]||{total:0,success:0};
    var pct=d.total?Math.round(d.success/d.total*100):0;
    var col=pct>=80?'var(--gn)':pct>=50?'var(--yl)':'var(--rd)';
    html+='<div style="display:flex;align-items:center;gap:8px;margin:4px 0">';
    html+='<span style="width:30px;font-size:10px;color:var(--t2)">'+dayNames[i]+'</span>';
    html+='<div style="flex:1;height:12px;background:var(--bg3);border-radius:6px;overflow:hidden"><div style="height:100%;width:'+pct+'%;background:'+col+';transition:width .5s"></div></div>';
    html+='<span style="width:50px;font-size:10px;text-align:right;color:'+col+'">'+pct+'% ('+d.success+'/'+d.total+')</span>';
    html+='</div>';
  }
  html+='</div>';
  return html;
}

function renderSuccessByHour(){
  var D=window.DASH||{};var runs=D.runs||[];
  var byHour={};
  runs.forEach(function(r){
    if(!r.createdAt)return;
    var h=new Date(r.createdAt).getHours();
    if(!byHour[h])byHour[h]={total:0,success:0};
    byHour[h].total++;
    if(r.conclusion==='success')byHour[h].success++;
  });
  var html='<div style="padding:10px">';
  html+='<div style="font-size:12px;font-weight:700;margin-bottom:8px">Success Rate by Hour (WIB)</div>';
  html+='<div class="hour-bar">';
  for(var h=0;h<24;h++){
    var d=byHour[h]||{total:0,success:0};
    var pct=d.total?Math.round(d.success/d.total*100):0;
    var height=Math.max(2,d.total/((runs.length/24)||1)*56);
    var col=pct>=80?'var(--gn)':pct>=50?'var(--yl)':'var(--rd)';
    html+='<div class="hour-col" style="height:'+height+'px;background:'+col+'" title="'+h+':00 - '+pct+'% ('+d.success+'/'+d.total+')" ></div>';
  }
  html+='</div><div style="display:flex;justify-content:space-between;font-size:8px;color:var(--t2)"><span>00:00</span><span>12:00</span><span>23:00</span></div>';
  html+='</div>';
  return html;
}

function renderBranchHealth(){
  var D=window.DASH||{};var runs=D.runs||[];
  var branches={};
  runs.forEach(function(r){
    var b=r.headBranch||'master';
    if(!branches[b])branches[b]={total:0,success:0,fail:0};
    branches[b].total++;
    if(r.conclusion==='success')branches[b].success++;
    if(r.conclusion==='failure')branches[b].fail++;
  });
  var html='<div style="padding:10px">';
  var sorted=Object.keys(branches).sort(function(a,b){return branches[b].total-branches[a].total});
  sorted.forEach(function(b){
    var d=branches[b];
    var pct=Math.round(d.success/d.total*100);
    var col=pct>=80?'var(--gn)':pct>=50?'var(--yl)':'var(--rd)';
    html+='<div style="margin:6px 0">';
    html+='<div style="font-size:10px;display:flex;justify-content:space-between"><span>'+b+'</span><span style="color:'+col+'">'+pct+'% ('+d.success+'/'+d.total+')</span></div>';
    html+='<div class="branch-bar" style="width:'+pct+'%;background:'+col+'">'+d.success+' ok / '+d.fail+' fail</div>';
    html+='</div>';
  });
  html+='</div>';
  return html;
}

function renderActionsMinutes(){
  var D=window.DASH||{};var runs=D.runs||[];var st=D.stats||{};
  var totalMinutes=0;
  runs.forEach(function(r){
    if(r.updatedAt&&r.createdAt)totalMinutes+=Math.round((r.updatedAt-r.createdAt)/60000);
  });
  var freeTier=2000;
  var used=Math.min(totalMinutes,freeTier);
  var pct=Math.round(used/freeTier*100);
  var remaining=freeTier-used;
  var col=pct<60?'var(--gn)':pct<85?'var(--yl)':'var(--rd)';
  var html='<div style="padding:10px">';
  html+='<div class="metric-grid">';
  html+='<div class="metric-mini"><div class="metric-mini-val" style="color:'+col+'">'+totalMinutes+'</div><div class="metric-mini-lbl">Minutes Used</div></div>';
  html+='<div class="metric-mini"><div class="metric-mini-val ok">'+remaining+'</div><div class="metric-mini-lbl">Remaining</div></div>';
  html+='<div class="metric-mini"><div class="metric-mini-val">'+pct+'%</div><div class="metric-mini-lbl">Used</div></div>';
  html+='</div>';
  html+='<div style="margin-top:8px"><div style="font-size:10px;color:var(--t2);margin-bottom:4px">Free Tier: 2000 min/month</div>';
  html+='<div style="height:12px;background:var(--bg3);border-radius:6px;overflow:hidden"><div class="minutes-bar '+(pct>=85?'bad':pct>=60?'warn':'')+'" style="width:'+pct+'%;background:'+col+'"></div></div></div>';
  html+='<div style="font-size:9px;color:var(--t3);margin-top:4px">Estimate based on '+runs.length+' runs (actual billing may differ)</div>';
  html+='</div>';
  return html;
}

function renderWorkflowComparison(){
  var D=window.DASH||{};var runs=D.runs||[];
  var workflows={};
  runs.forEach(function(r){
    var w=r.name||'unknown';
    if(!workflows[w])workflows[w]={total:0,success:0,fail:0};
    workflows[w].total++;
    if(r.conclusion==='success')workflows[w].success++;
    if(r.conclusion==='failure')workflows[w].fail++;
  });
  var html='<div style="padding:10px">';
  html+='<div style="font-size:10px;color:var(--t2);border-bottom:1px solid var(--brd);padding-bottom:4px;margin-bottom:4px;display:grid;grid-template-columns:1fr 40px 40px"><span>Workflow</span><span>Total</span><span>Rate</span></div>';
  var sorted=Object.keys(workflows).sort(function(a,b){return workflows[b].total-workflows[a].total});
  sorted.forEach(function(w){
    var d=workflows[w];
    var pct=d.total?Math.round(d.success/d.total*100):0;
    var col=pct>=80?'var(--gn)':pct>=50?'var(--yl)':'var(--rd)';
    html+='<div class="workflow-row"><span>'+w.substring(0,25)+'</span><span>'+d.total+'</span><span style="color:'+col+'">'+pct+'%</span></div>';
  });
  html+='</div>';
  return html;
}

function renderConcurrency(){
  var D=window.DASH||{};var runs=D.runs||[];
  var slots={};
  runs.forEach(function(r){
    if(!r.createdAt||!r.updatedAt)return;
    var s=new Date(r.createdAt).getTime();
    var e=new Date(r.updatedAt).getTime();
    if(!s||!e)return;
    var key=Math.floor(s/60000);
    if(!slots[key])slots[key]={count:0,runs:[]};
    slots[key].count++;
    slots[key].runs.push(r);
  });
  var maxConc=0;
  Object.values(slots).forEach(function(s){if(s.count>maxConc)maxConc=s.count});
  var currentRunning=runs.filter(function(r){return r.status==='in_progress'||r.conclusion===null}).length;
  var html='<div style="padding:10px">';
  html+='<div class="metric-grid">';
  html+='<div class="metric-mini"><div class="metric-mini-val" style="color:var(--bl)">'+currentRunning+'</div><div class="metric-mini-lbl">Running Now</div></div>';
  html+='<div class="metric-mini"><div class="metric-mini-val warn">'+maxConc+'</div><div class="metric-mini-lbl">Peak Concurrent</div></div>';
  html+='</div>';
  var sortedSlots=Object.keys(slots).sort(function(a,b){return slots[b].count-slots[a].count}).slice(0,10);
  html+='<div style="margin-top:8px;font-size:11px;color:var(--t2)">Top 10 concurrency moments:</div>';
  sortedSlots.forEach(function(k){
    var s=slots[k];
    var d=new Date(parseInt(k)*60000);
    var time=d.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:'Asia/Jakarta'});
    html+='<div class="concurrency-bar" style="width:100%">'+time+' — '+s.count+' parallel</div>';
  });
  html+='</div>';
  return html;
}

function renderCommitImpact(){
  var D=window.DASH||{};var runs=D.runs||[];
  var withSha=runs.filter(function(r){return r.headSha}).slice(0,20);
  if(!withSha.length){
    // Use databaseId as proxy
    withSha=runs.slice(0,20);
  }
  var html='<div style="padding:10px">';
  html+='<div style="font-size:10px;color:var(--t2);border-bottom:1px solid var(--brd);padding-bottom:4px;margin-bottom:4px;display:grid;grid-template-columns:60px 1fr 40px"><span>SHA</span><span>Workflow</span><span>Result</span></div>';
  withSha.forEach(function(r){
    var sha=(r.headSha||'').substring(0,7)||(r.databaseId||'').toString().substring(0,7);
    var col=r.conclusion==='success'?'var(--gn)':'var(--rd)';
    html+='<div class="commit-row"><span class="commit-sha">'+sha+'</span><span style="color:var(--t2)">'+(r.name||'').substring(0,20)+'</span><span class="commit-result" style="color:'+col+'">'+(r.conclusion==='success'?'✅':'❌')+'</span></div>';
  });
  html+='</div>';
  return html;
}

function renderDeployTimeline(){
  var D=window.DASH||{};var runs=D.runs||[];
  var deploys=runs.filter(function(r){return r.conclusion==='success'}).slice(0,30).reverse();
  if(!deploys.length)return'<div style="padding:10px;color:var(--t2)">No deploys</div>';
  var firstTime=new Date(deploys[0].createdAt||0).getTime();
  var lastTime=new Date(deploys[deploys.length-1].createdAt||0).getTime();
  var span=Math.max(1,lastTime-firstTime);
  var html='<div style="padding:10px">';
  html+='<div style="font-size:12px;font-weight:700;margin-bottom:8px">Deploy Timeline ('+deploys.length+' deploys)</div>';
  html+='<div class="timeline-track">';
  deploys.forEach(function(r){
    var t=new Date(r.createdAt||0).getTime();
    var pct=((t-firstTime)/span*100).toFixed(1);
    html+='<div class="timeline-dot ok" style="left:'+pct+'%" title="'+(r.orv_id||'')+' — '+new Date(t).toLocaleDateString('en-GB',{day:'numeric',month:'short',timeZone:'Asia/Jakarta'})+'"></div>';
  });
  html+='</div>';
  var fD=new Date(firstTime).toLocaleDateString('en-GB',{day:'numeric',month:'short'});
  var lD=new Date(lastTime).toLocaleDateString('en-GB',{day:'numeric',month:'short'});
  html+='<div style="display:flex;justify-content:space-between;font-size:8px;color:var(--t2)"><span>'+fD+'</span><span>'+lD+'</span></div>';
  html+='</div>';
  return html;
}

function renderRetryTracker(){
  var D=window.DASH||{};var runs=D.runs||[];
  var retried=[];
  for(var i=0;i<runs.length-1;i++){
    if(runs[i].conclusion==='failure'){
      var next=runs[i+1];
      if(next&&next.name===runs[i].name){
        var isRetry=true;
        var t1=new Date(runs[i].createdAt||0).getTime();
        var t2=new Date(next.createdAt||0).getTime();
        if(t2-t1<3600000)retried.push({fail:runs[i],retry:next,success:next.conclusion==='success'});
      }
    }
  }
  var successRate=retried.length?Math.round(retried.filter(function(r){return r.success}).length/retried.length*100):0;
  var html='<div style="padding:10px">';
  html+='<div class="metric-grid">';
  html+='<div class="metric-mini"><div class="metric-mini-val">'+retried.length+'</div><div class="metric-mini-lbl">Retries</div></div>';
  html+='<div class="metric-mini"><div class="metric-mini-val '+(successRate>=50?'ok':'warn')+'">'+successRate+'%</div><div class="metric-mini-lbl">Retry Success</div></div>';
  html+='</div>';
  if(retried.length>0){
    retried.slice(0,10).forEach(function(r,i){
      html+='<div class="retry-row"><span>'+(r.fail.orv_id||r.fail.databaseId||'')+'</span><span style="color:'+(r.success?'var(--gn)':'var(--rd)')+'">'+(r.success?'✅ Recovered':'❌ Still failing')+'</span></div>';
    });
  }else{
    html+='<div style="text-align:center;color:var(--gn);padding:10px">No retries needed! 🎉</div>';
  }
  html+='</div>';
  return html;
}


// ═══ v9.2 features ═══
function renderHeatmap(){
  var D=window.DASH||{};var runs=D.runs||[];
  var days={};
  runs.forEach(function(r){
    if(!r.createdAt)return;
    var d=new Date(r.createdAt);
    var key=d.getFullYear()+'-'+('0'+(d.getMonth()+1)).slice(-2)+'-'+('0'+d.getDate()).slice(-2);
    if(!days[key])days[key]={total:0,success:0,fail:0};
    days[key].total++;
    if(r.conclusion==='success')days[key].success++;
    if(r.conclusion==='failure')days[key].fail++;
  });
  var now=new Date();
  var start=new Date(now.getFullYear(),0,1);
  var daysArr=[];
  for(var d=new Date(start);d<=now;d=new Date(d.getTime()+86400000)){
    var key=d.getFullYear()+'-'+('0'+(d.getMonth()+1)).slice(-2)+'-'+('0'+d.getDate()).slice(-2);
    daysArr.push({key:key,date:new Date(d),data:days[key]||null});
  }
  var html='<div class="heatmap-wrap"><div class="heatmap-grid" id="heatmapGrid">';
  var months=[];
  var lastMonth=-1;
  daysArr.forEach(function(day){
    var m=day.date.getMonth();
    if(m!==lastMonth){months.push(day.date.toLocaleDateString('en',{month:'short'}));lastMonth=m}
    else months.push('');
    var cls='heatmap-cell';
    if(day.data){
      if(day.data.fail>0&&day.data.success===0)cls+=' lf';
      else if(day.data.success>=5)cls+=' l4';
      else if(day.data.success>=3)cls+=' l3';
      else if(day.data.success>=1)cls+=' l2';
      else cls+=' l1';
    }
    html+='<div class="'+cls+'" title="'+day.key+': '+(day.data?day.data.total+' runs':'0')+'"></div>';
  });
  html+='</div><div class="heatmap-legend">Less <div class="heatmap-cell"></div><div class="heatmap-cell l1"></div><div class="heatmap-cell l2"></div><div class="heatmap-cell l3"></div><div class="heatmap-cell l4"></div> More &nbsp; <div class="heatmap-cell lf"></div> Fail</div></div>';
  return html;
}

var _achvList=[
  {id:'first_run',icon:'🎯',name:'First Run',desc:'Complete 1 run',check:function(s){return s.total>=1},max:1},
  {id:'ten_runs',icon:'🔟',name:'10 Runs',desc:'Complete 10 runs',check:function(s){return s.total>=10},max:10},
  {id:'fifty_runs',icon:'5️⃣0️⃣',name:'50 Runs',desc:'Complete 50 runs',check:function(s){return s.total>=50},max:50},
  {id:'hundred_runs',icon:'💯',name:'100 Runs',desc:'Complete 100 runs',check:function(s){return s.total>=100},max:100},
  {id:'streak3',icon:'🔥',name:'3-Day Streak',desc:'3 day success streak',check:function(s){return s.streak>=3},max:3},
  {id:'streak7',icon:'📅',name:'7-Day Streak',desc:'7 day success streak',check:function(s){return s.streak>=7},max:7},
  {id:'rate80',icon:'📈',name:'80% Rate',desc:'80%+ success rate',check:function(s){return s.rate>=80},max:80},
  {id:'rate90',icon:'🏆',name:'90% Rate',desc:'90%+ success rate',check:function(s){return s.rate>=90},max:90},
  {id:'nofails',icon:'🛡️',name:'No Fails',desc:'0 failed runs',check:function(s){return s.failed===0&&s.total>=5},max:1}
];
var _achvUnlocked=JSON.parse(localStorage.getItem('dash_achv')||'{}');
function renderAchievements(){
  var st=(window.DASH||{}).stats||{};
  var html='<div class="achv-wrap"><div class="achv-grid">';
  var unlockedCount=0;
  _achvList.forEach(function(a){
    var unlocked=_achvUnlocked[a.id]||a.check(st);
    if(unlocked&&!_achvUnlocked[a.id])_achvUnlocked[a.id]=true;
    if(unlocked)unlockedCount++;
    var cls=unlocked?'unlocked':'locked';
    var progress='';
    if(!unlocked){
      var prog=0;
      if(a.id==='ten_runs')prog=Math.min(st.total,10);
      else if(a.id==='fifty_runs')prog=Math.min(st.total,50);
      else if(a.id==='hundred_runs')prog=Math.min(st.total,100);
      else if(a.id==='streak3')prog=Math.min(st.streak,3);
      else if(a.id==='streak7')prog=Math.min(st.streak,7);
      else if(a.id==='rate80')prog=Math.min(st.rate,80);
      else if(a.id==='rate90')prog=Math.min(st.rate,90);
      if(prog>0)progress='<div class="achv-progress">'+prog+'/'+a.max+'</div>';
    }
    html+='<div class="achv-badge '+cls+'"><div class="achv-icon">'+a.icon+'</div><div class="achv-name">'+a.name+'</div><div class="achv-desc">'+a.desc+'</div>'+progress+'</div>';
  });
  html+='</div><div style="text-align:center;margin-top:8px;font-size:11px;color:var(--t2)">Unlocked: '+unlockedCount+'/'+_achvList.length+'</div></div>';
  localStorage.setItem('dash_achv',JSON.stringify(_achvUnlocked));
  return html;
}
function checkAchievements(){
  var st=(window.DASH||{}).stats||{};
  _achvList.forEach(function(a){
    if(!_achvUnlocked[a.id]&&a.check(st)){_achvUnlocked[a.id]=true;showToast('🏆 Achievement: '+a.name+'!')}
  });
  localStorage.setItem('dash_achv',JSON.stringify(_achvUnlocked));
}

function renderAnalytics(){
  var D=window.DASH||{};var runs=D.runs||[];var st=D.stats||{};
  var html='<div class="chart-wrap">';
  html+='<div style="font-size:12px;font-weight:700;margin-bottom:8px">📊 Success Rate Trend (Last 14 days)</div>';
  html+='<canvas class="chart-canvas" id="chartTrend"></canvas>';
  html+='<div style="font-size:12px;font-weight:700;margin:12px 0 8px">📈 Runs Per Day (Last 14 days)</div>';
  html+='<canvas class="chart-canvas" id="chartRuns"></canvas>';
  html+='<div style="font-size:12px;font-weight:700;margin:12px 0 8px">⏱️ Duration Distribution</div>';
  html+='<canvas class="chart-canvas" id="chartDuration"></canvas>';
  html+='</div>';
  setTimeout(function(){
    var now=new Date();
    var labels=[],successData=[],totalData=[];
    for(var i=13;i>=0;i--){
      var d=new Date(now.getTime()-i*86400000);
      var key=d.getDate()+'/'+(d.getMonth()+1);
      labels.push(key);
      var dKey=d.getFullYear()+'-'+('0'+(d.getMonth()+1)).slice(-2)+'-'+('0'+d.getDate()).slice(-2);
      var dayRuns=runs.filter(function(r){if(!r.createdAt)return false;var rd=new Date(r.createdAt);return rd.getFullYear()===d.getFullYear()&&rd.getMonth()===d.getMonth()&&rd.getDate()===d.getDate()});
      totalData.push(dayRuns.length);
      successData.push(dayRuns.filter(function(r){return r.conclusion==='success'}).length);
    }
    if(typeof Chart==='undefined')return;
    var ctx1=document.getElementById('chartTrend');
    if(ctx1)new Chart(ctx1.getContext('2d'),{type:'line',data:{labels:labels,datasets:[{label:'Success',data:successData,borderColor:'#3fb950',backgroundColor:'rgba(63,185,80,.1)',fill:true}]},options:{responsive:true,scales:{y:{beginAtZero:true,ticks:{precision:0}}}}});
    var ctx2=document.getElementById('chartRuns');
    if(ctx2)new Chart(ctx2.getContext('2d'),{type:'bar',data:{labels:labels,datasets:[{label:'Total',data:totalData,backgroundColor:'#58a6ff'},{label:'Success',data:successData,backgroundColor:'#3fb950'}]},options:{responsive:true,scales:{y:{beginAtZero:true,ticks:{precision:0}}}}});
    var durations=runs.map(function(r){return r.updatedAt&&r.createdAt?Math.round((r.updatedAt-r.createdAt)/60000):0}).filter(function(d){return d>0&&d<120});
    var buckets=[0,0,0,0,0,0];
    durations.forEach(function(d){if(d<5)buckets[0]++;else if(d<10)buckets[1]++;else if(d<20)buckets[2]++;else if(d<30)buckets[3]++;else if(d<60)buckets[4]++;else buckets[5]++});
    var ctx3=document.getElementById('chartDuration');
    if(ctx3)new Chart(ctx3.getContext('2d'),{type:'bar',data:{labels:['<5m','5-10m','10-20m','20-30m','30-60m','60m+'],datasets:[{label:'Runs',data:buckets,backgroundColor:'#d29922'}]},options:{responsive:true,scales:{y:{beginAtZero:true,ticks:{precision:0}}}}});
  },50);
  return html;
}

function renderGantt(){
  var D=window.DASH||{};var runs=D.runs||[];
  var vault=runs.slice(0,20);
  if(!vault.length)return'<div class="gantt-wrap">No runs</div>';
  var minTime=Math.min.apply(null,vault.map(function(r){return new Date(r.createdAt||0).getTime()||Date.now()}));
  var maxTime=Math.max.apply(null,vault.map(function(r){return new Date(r.updatedAt||r.createdAt||0).getTime()||Date.now()}));
  var span=Math.max(1,maxTime-minTime);
  var html='<div class="gantt-wrap"><div class="gantt-axis">Timeline (last 20 runs)</div>';
  vault.forEach(function(r){
    var start=new Date(r.createdAt||0).getTime();
    var end=new Date(r.updatedAt||r.createdAt||0).getTime();
    if(!end||end<start)end=start+60000;
    var leftPct=((start-minTime)/span*100).toFixed(1);
    var widthPct=Math.max(2,((end-start)/span*100)).toFixed(1);
    var col=r.conclusion==='success'?'var(--gn)':r.conclusion==='failure'?'var(--rd)':'var(--yl)';
    var label=(r.orv_id||r.databaseId||'').toString().substring(0,12);
    html+='<div class="gantt-bar" style="margin-left:'+leftPct+'%;width:'+widthPct+'%;background:'+col+'">'+label+'</div>';
  });
  var startD=new Date(minTime).toLocaleDateString('en-GB',{day:'numeric',month:'short'});
  var endD=new Date(maxTime).toLocaleDateString('en-GB',{day:'numeric',month:'short'});
  html+='<div class="gantt-axis" style="text-align:center;margin-top:4px">'+startD+' → '+endD+'</div></div>';
  return html;
}

function renderCompare(){
  var D=window.DASH||{};var runs=D.runs||[];
  var opts=runs.slice(0,50).map(function(r){return'<option value="'+(r.databaseId||'')+'">'+(r.orv_id||r.databaseId||'')+' — '+(r.name||'').substring(0,20)+'</option>'}).join('');
  var html='<div class="compare-wrap">';
  html+='<div class="compare-select"><div><select class="inp" id="cmpA" ><option value="">Select Run A</option>'+opts+'</select></div><div><select class="inp" id="cmpB" ><option value="">Select Run B</option>'+opts+'</select></div></div>';
  html+='<div id="cmpDetail" style="font-size:10px;color:var(--t2);text-align:center">Select two runs to compare</div>';
  html+='</div>';
  return html;
}
function renderCompareDetail(){
  var D=window.DASH||{};var runs=D.runs||[];
  var aId=document.getElementById('cmpA')&&document.getElementById('cmpA').value;
  var bId=document.getElementById('cmpB')&&document.getElementById('cmpB').value;
  var el=document.getElementById('cmpDetail');
  if(!el)return;
  if(!aId||!bId){el.innerHTML='Select two runs to compare';return}
  var rA=runs.find(function(r){return String(r.databaseId)===String(aId)});
  var rB=runs.find(function(r){return String(r.databaseId)===String(bId)});
  if(!rA||!rB){el.innerHTML='Run not found';return}
  function fmtDate(ts){return ts?new Date(ts).toLocaleString('en-GB',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}):'-'}
  function dur(r){return(r.updatedAt&&r.createdAt)?Math.round((r.updatedAt-r.createdAt)/60000)+'m':'-'}
  function cmp(vA,vB){if(vA===vB)return'<span style="color:var(--gn)">=</span>';return'<span style="color:var(--rd)">≠</span>'}
  var html='<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">';
  html+='<div class="compare-col"><h4>Run A</h4>';
  html+='<div class="compare-row"><span>RSM</span><span>'+(rA.orv_id||'-')+'</span></div>';
  html+='<div class="compare-row"><span>Name</span><span>'+(rA.name||'-').substring(0,15)+'</span></div>';
  html+='<div class="compare-row"><span>Status</span><span style="color:'+(rA.conclusion==='success'?'var(--gn)':'var(--rd)')+'">'+(rA.conclusion||'-')+'</span></div>';
  html+='<div class="compare-row"><span>Created</span><span>'+fmtDate(rA.createdAt)+'</span></div>';
  html+='<div class="compare-row"><span>Duration</span><span>'+dur(rA)+'</span></div>';
  html+='</div>';
  html+='<div class="compare-col"><h4>Run B</h4>';
  html+='<div class="compare-row"><span>RSM</span><span>'+(rB.orv_id||'-')+'</span></div>';
  html+='<div class="compare-row"><span>Name</span><span>'+(rB.name||'-').substring(0,15)+'</span></div>';
  html+='<div class="compare-row"><span>Status</span><span style="color:'+(rB.conclusion==='success'?'var(--gn)':'var(--rd)')+'">'+(rB.conclusion||'-')+'</span></div>';
  html+='<div class="compare-row"><span>Created</span><span>'+fmtDate(rB.createdAt)+'</span></div>';
  html+='<div class="compare-row"><span>Duration</span><span>'+dur(rB)+'</span></div>';
  html+='</div></div>';
  html+='<div style="text-align:center;margin-top:8px">RSM '+cmp(rA.orv_id,rB.orv_id)+' | Status '+cmp(rA.conclusion,rB.conclusion)+' | Duration '+cmp(dur(rA),dur(rB))+'</div>';
  el.innerHTML=html;
}

function exportMarkdown(){
  var D=window.DASH||{};var runs=D.runs||[];var st=D.stats||{};
  var nl=String.fromCharCode(10);var md='# Rusemeva Dashboard Report'+nl;
  md+='> Generated: '+new Date().toLocaleString('en-GB')+nl+nl;
  md+='## 📊 Summary'+nl+nl;
  md+='| Metric | Value |'+nl+'|---|---|'+nl;
  md+='| Total Runs | '+st.total+' |'+nl;
  md+='| Success | '+st.success+' |'+nl;
  md+='| Failed | '+st.failed+' |'+nl;
  md+='| Success Rate | '+st.rate+'% |'+nl;
  md+='| Current Streak | '+st.streak+' days |'+nl+nl;
  md+='## 📋 Recent Runs (Last 20)'+nl+nl;
  md+='| # | RSM | Name | Status | Created | Duration |'+nl;
  md+='|---|---|---|---|---|---|'+nl;
  runs.slice(0,20).forEach(function(r,i){
    var d=r.createdAt?new Date(r.createdAt).toLocaleString('en-GB',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}):'-';
    var dur=(r.updatedAt&&r.createdAt)?Math.round((r.updatedAt-r.createdAt)/60000)+'m':'-';
    md+='| '+(i+1)+' | '+(r.orv_id||'-')+' | '+(r.name||'-')+' | '+(r.conclusion||'-')+' | '+d+' | '+dur+' |'+nl;
  });
  md+=nl+'---'+nl+'*Auto-generated by Rusemeva Dashboard v9.2*'+nl;
  downloadBlob(md,'rusemeva-report.md','text/markdown');
  showToast('Markdown exported!');
}

var _clockTimer=null;
function renderClock(){
  var html='<div style="padding:12px">';
  html+='<div class="dash-clock" id="dashClock">--:--:--</div>';
  html+='<div class="dash-clock-date" id="dashClockDate">-</div>';
  html+='<div class="dash-clock-tz" id="dashClockTz">GMT+7</div>';
  html+='</div>';
  if(_clockTimer)clearInterval(_clockTimer);
  _clockTimer=setInterval(function(){
    var el=document.getElementById('dashClock');
    if(!el)return;
    var now=new Date();
    var h=now.getHours(),m=now.getMinutes(),s=now.getSeconds();
    el.textContent=('0'+h).slice(-2)+':'+('0'+m).slice(-2)+':'+('0'+s).slice(-2);
    var el2=document.getElementById('dashClockDate');
    if(el2)el2.textContent=now.toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long',year:'numeric'});
    var el3=document.getElementById('dashClockTz');
    if(el3)el3.textContent='GMT+7 (Jakarta)';
  },1000);
  return html;
}


// ═══ v9.0 features ═══
function renderHmMatrix(){
  var D=window.DASH||{};var runs=D.runs||[];
  var matrix={};var maxVal=0;
  runs.forEach(function(r){
    var d=new Date(r.createdAt||0);
    var dow=d.getDay();var hr=d.getHours();
    var key=dow+'_'+hr;matrix[key]=(matrix[key]||0)+1;
    if(matrix[key]>maxVal)maxVal=matrix[key];
  });
  var days=['Su','Mo','Tu','We','Th','Fr','Sa'];
  var html='<div class="hm-matrix"><div></div>';
  for(var h=0;h<24;h++)html+='<div class="hm-hdr">'+h+'</div>';
  for(var d=0;d<7;d++){
    html+='<div class="hm-lbl">'+days[d]+'</div>';
    for(var h=0;h<24;h++){
      var v=matrix[d+'_'+h]||0;
      var lvl=maxVal>0?Math.ceil(v/maxVal*4):0;
      if(v===0)lvl=0;
      html+='<div class="hm-cell2 l'+lvl+'" title="'+days[d]+' '+h+':00 → '+v+' runs"></div>';
    }
  }
  html+='</div>';
  var el=document.getElementById('hmMatrixWrap');if(el)el.innerHTML=html;
}
function calcInsights(){
  var D=window.DASH||{};var runs=D.runs||[];
  var byDay={};var days=['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
  runs.forEach(function(r){
    var d=new Date(r.createdAt||0).getDay();
    if(!byDay[d])byDay[d]={ok:0,total:0};
    byDay[d].total++;if(r.conclusion==='success')byDay[d].ok++;
  });
  var best={day:'',rate:0};var worst={day:'',rate:100};
  Object.keys(byDay).forEach(function(d){
    var r=Math.round(byDay[d].ok/byDay[d].total*100);
    if(r>best.rate)best={day:days[d],rate:r};
    if(r<worst.rate)worst={day:days[d],rate:r};
  });
  return {best:best,worst:worst};
}
function renderInsights(){
  var ins=calcInsights();var st=(window.DASH||{}).stats||{};
  var html='<div class="insight-box">';
  if(ins.best.day)html+='<b>Best day: '+esc(ins.best.day)+' ('+ins.best.rate+'%)</b><br>';
  if(ins.worst.day)html+='<span class="bad">Worst day: '+esc(ins.worst.day)+' ('+ins.worst.rate+'%)</span><br>';
  html+='Streak: '+(st.streak||0)+' hari · Rate: '+(st.rate||0)+'%';
  html+='</div>';
  return html;
}
function calcRecovery(){
  var D=window.DASH||{};var runs=(D.runs||[]).filter(function(r){return r.name==='rusemeva-vault'}).sort(function(a,b){return new Date(a.createdAt||0)-new Date(b.createdAt||0)});
  var recoveries=[];var lastFail=null;
  runs.forEach(function(r){
    if(r.conclusion==='failure'){lastFail=new Date(r.createdAt||0)}
    else if(r.conclusion==='success'&&lastFail){recoveries.push(new Date(r.createdAt||0)-lastFail);lastFail=null}
  });
  if(!recoveries.length)return null;
  var avg=Math.round(recoveries.reduce(function(a,b){return a+b},0)/recoveries.length/60000);
  return {avg:avg,count:recoveries.length};
}
function renderRecovery(){
  var rc=calcRecovery();
  if(!rc)return '<div class="insight-box">No recovery data yet</div>';
  return '<div class="insight-box">Recovery time: <b>'+rc.avg+'m</b> avg ('+rc.count+' recoveries)</div>';
}
function calcProductivity(){
  var st=(window.DASH||{}).stats||{};
  var rateScore=Math.min((st.rate||0),100);
  var streakScore=Math.min((st.streak||0)*5,50);
  var freqScore=Math.min((st.total||0)*2,30);
  var total=rateScore+streakScore+freqScore;
  return {total:Math.min(total,100),rate:rateScore,streak:streakScore,freq:freqScore};
}
function renderProductivity(){
  var p=calcProductivity();
  var col=p.total>=80?'var(--gn)':(p.total>=50?'var(--or)':'var(--rd)');
  var r=26,c=2*Math.PI*r,off=c-(p.total/100*c);
  return '<div class="prod-score"><div class="prod-ring"><svg width="60" height="60" style="transform:rotate(-90deg)"><circle cx="30" cy="30" r="'+r+'" fill="none" stroke="var(--bg3)" stroke-width="4"/><circle cx="30" cy="30" r="'+r+'" fill="none" stroke="'+col+'" stroke-width="4" stroke-dasharray="'+c+'" stroke-dashoffset="'+off+'" stroke-linecap="round"/><text x="30" y="30" text-anchor="middle" dy=".3em" font-size="14" font-weight="bold" fill="'+col+'" style="transform:rotate(90deg);transform-origin:30px 30px">'+p.total+'</text></svg></div><div class="prod-bar-wrap"><div style="font-size:11px;font-weight:600">Productivity Score</div><div style="font-size:9px;color:var(--t2)">Rate: '+p.rate+' · Streak: '+p.streak+' · Freq: '+p.freq+'</div></div></div>';
}
var _stopwatchTimer=null;
function startStopwatch(){
  if(_stopwatchTimer)clearInterval(_stopwatchTimer);
  _stopwatchTimer=setInterval(function(){
    var D=window.DASH||{};var runs=D.runs||[];
    var running=runs.filter(function(r){return statusKeyJs(r)==='in_progress'});
    running.forEach(function(r){
      var el=document.getElementById('sw-'+(r.databaseId||''));
      if(el){var ms=Date.now()-new Date(r.createdAt||0).getTime();var m=Math.floor(ms/60000);var s=Math.floor((ms%60000)/1000);el.textContent=m+'m '+s+'s'}
    });
    if(!running.length&&_stopwatchTimer){clearInterval(_stopwatchTimer);_stopwatchTimer=null}
  },1000);
}
function toggleQuickPanel(){
  var el=document.getElementById('quickPanel');if(el)el.classList.toggle('on');
}
function initQuickPanel(){
  document.addEventListener('click',function(e){
    var btn=e.target.closest('.quick-btn');if(!btn)return;
    var act=btn.getAttribute('data-action');
    if(act==='copyRSM'){var D=window.DASH||{};var r=(D.runs||[])[0];if(r)copyRSM(r.orv_id||r.databaseId||'')}
    else if(act==='export')expCSV();
    
    else if(act==='terminal')toggleTerminal();
    else if(act==='snapshot')saveSnapshot();
    else if(act==='glass')toggleGlass();
    else if(act==='close')toggleQuickPanel();
  });
}
var _batchSel={};
function toggleBatchSel(rid){
  _batchSel[rid]=!_batchSel[rid];
  var el=document.querySelector('[data-rid="'+rid+'"]');if(el)el.classList.toggle('batch-sel',_batchSel[rid]);
  updateBatchBar();
}
function updateBatchBar(){
  var count=Object.keys(_batchSel).filter(function(k){return _batchSel[k]}).length;
  var bar=document.getElementById('batchBar');if(!bar)return;
  bar.classList.toggle('on',count>0);
  var cnt=document.getElementById('batchCount');if(cnt)cnt.textContent=count;
}
function initBatchBar(){
  document.addEventListener('click',function(e){
    var btn=e.target.closest('[data-batch]');if(!btn)return;
    var act=btn.getAttribute('data-batch');
    if(act==='clear'){_batchSel={};document.querySelectorAll('.batch-sel').forEach(function(el){el.classList.remove('batch-sel')});updateBatchBar();return}
    var selected=Object.keys(_batchSel).filter(function(k){return _batchSel[k]});
    if(!selected.length)return;
    if(act==='tag'){var tag=prompt('Tag for '+selected.length+' runs:');if(!tag)return;var tags=JSON.parse(localStorage.getItem('dash_tags')||'{}');selected.forEach(function(rid){tags[rid]=tags[rid]||[];tags[rid].push(tag)});localStorage.setItem('dash_tags',JSON.stringify(tags));showToast('Tagged '+selected.length+' runs')}
    else if(act==='note'){var note=prompt('Note for '+selected.length+' runs:');if(!note)return;var notes=JSON.parse(localStorage.getItem('dash_runnotes')||'{}');selected.forEach(function(rid){notes[rid]=note});localStorage.setItem('dash_runnotes',JSON.stringify(notes));showToast('Noted '+selected.length+' runs')}
  });
}
function renderQR(){
  var url='https://daudjoss.github.io/daudjoss-vault/';
  var size=120;var c=document.createElement('canvas');c.width=size;c.height=size;c.className='qr-canvas';
  var ctx=c.getContext('2d');
  // Simple QR placeholder — draw URL as barcode-like pattern
  ctx.fillStyle='#fff';ctx.fillRect(0,0,size,size);
  ctx.fillStyle='#000';
  // Draw finder patterns (corners)
  function finder(x,y){ctx.fillRect(x,y,21,21);ctx.fillStyle='#fff';ctx.fillRect(x+4,y+4,13,13);ctx.fillStyle='#000';ctx.fillRect(x+7,y+7,7,7)}
  finder(4,4);finder(size-25,4);finder(4,size-25);
  // Draw data modules from URL hash
  var data=url;var px=30;var py=30;
  for(var i=0;i<data.length&&py<size-25;i++){
    var code=data.charCodeAt(i);
    for(var bit=0;bit<8&&px<size-25;bit++){
      if(code&(1<<bit))ctx.fillRect(px,py,3,3);
      px+=4;
    }
    if(px>=size-25){px=30;py+=4}
  }
  // Timing pattern
  ctx.fillStyle='#000';
  for(var i=28;i<size-25;i+=4){ctx.fillRect(i,28,2,2);ctx.fillRect(28,i,2,2)}
  return '<div class="qr-wrap">'+c.outerHTML+'<div style="font-size:9px;color:var(--t2);margin-top:4px">Scan to open dashboard</div></div>';
}
function genOGImage(){
  var st=(window.DASH||{}).stats||{};
  var c=document.createElement('canvas');c.width=1200;c.height=630;
  var ctx=c.getContext('2d');
  ctx.fillStyle='#0d1117';ctx.fillRect(0,0,1200,630);
  ctx.fillStyle='#58a6ff';ctx.fillRect(0,0,1200,8);
  ctx.fillStyle='#fff';ctx.font='bold 48px sans-serif';ctx.fillText('Rusemeva Dashboard',60,100);
  ctx.font='20px sans-serif';ctx.fillStyle='#8b949e';ctx.fillText('github.com/daudjoss/daudjoss-vault',60,140);
  ctx.font='bold 72px sans-serif';ctx.fillStyle='#3fb950';ctx.fillText(st.total+' Runs',60,280);
  ctx.fillStyle='#58a6ff';ctx.fillText(st.rate+'% Rate',60,380);
  ctx.fillStyle='#f0883e';ctx.fillText((st.streak||0)+'d Streak',60,480);
  ctx.font='16px sans-serif';ctx.fillStyle='#8b949e';ctx.fillText(new Date().toLocaleDateString('en-GB',{timeZone:'Asia/Jakarta'}),60,560);
  var a=document.createElement('a');a.href=c.toDataURL();a.download='og-image.png';a.click();
  showToast('OG image downloaded!');
}
function renderEmbedSnippet(){
  var url='https://daudjoss.github.io/daudjoss-vault/?embed=1';
  var code='<iframe src="'+url+'" width="100%" height="400" frameborder="0" style="border-radius:12px"></iframe>';
  return '<div class="embed-snippet" id="embedSnippet">'+esc(code)+'<span class="curl-copy" style="position:absolute;top:4px;right:4px;font-size:9px;cursor:pointer;padding:2px 6px;border-radius:4px;background:var(--bg2);border:1px solid var(--brd)" onclick="copyEmbed()">📋</span></div>';
}
function copyEmbed(){
  var el=document.getElementById('embedSnippet');if(!el)return;
  var txt=el.textContent.replace('📋','').trim();
  navigator.clipboard.writeText(txt).then(function(){showToast('Embed code copied!')}).catch(function(){})
}
function toggleHC(){
  document.body.classList.toggle('hc-mode');
  var on=document.body.classList.contains('hc-mode');
  localStorage.setItem('dash_hc',on?'1':'0');
}
function applyHC(){
  if(localStorage.getItem('dash_hc')==='1')document.body.classList.add('hc-mode');
}
function adjustFont(dir){
  var cur=parseInt(localStorage.getItem('dash_fontsize')||'14',10);
  cur=Math.max(10,Math.min(22,cur+dir));
  localStorage.setItem('dash_fontsize',String(cur));
  document.documentElement.style.fontSize=cur+'px';
}
function applyFont(){
  var cur=parseInt(localStorage.getItem('dash_fontsize')||'14',10);
  document.documentElement.style.fontSize=cur+'px';
}
function ariaAnnounce(msg){
  var el=document.getElementById('ariaLive');if(el)el.textContent=msg;
}
function hideSkeleton(){
  var el=document.getElementById('skeletonWrap');if(el)el.style.display='none';
}


// ═══ v8.9 features ═══
var ACHIEVEMENTS=[
  {id:'run100',icon:'💯',name:'100 Runs',desc:'100 total vault runs',check:function(st){return (st.total||0)>=100}},
  {id:'streak10',icon:'🔥',name:'10-Day Streak',desc:'10 hari streak berturut',check:function(st){return (st.streak||0)>=10}},
  {id:'rate95',icon:'🎯',name:'95% Week',desc:'95% success rate',check:function(st){return (st.rate||0)>=95}},
  {id:'firstfail',icon:'⚡',name:'Recovery',desc:'First fail → recovery',check:function(st){return (st.failed||0)>0&&(st.rate||0)>50}},
  {id:'enc50',icon:'🎞',name:'50 Encodes',desc:'50 encode jobs OK',check:function(st){return (st.enc_ok||0)>=50}},
  {id:'today5',icon:'📅',name:'5 Today',desc:'5 runs hari ini',check:function(st){return (st.today||0)>=5}},
  {id:'streak5',icon:'🌱',name:'5-Day Streak',desc:'5 hari streak',check:function(st){return (st.streak||0)>=5}},
  {id:'rate80',icon:'📈',name:'80% Club',desc:'80%+ success rate',check:function(st){return (st.rate||0)>=80}}
];
function checkAchievements(){
  var st=(window.DASH||{}).stats||{};var unlocked=JSON.parse(localStorage.getItem('dash_badges')||'[]');
  ACHIEVEMENTS.forEach(function(a){
    if(unlocked.indexOf(a.id)<0&&a.check(st)){
      unlocked.push(a.id);localStorage.setItem('dash_badges',JSON.stringify(unlocked));
      showBadge(a);
    }
  });
}
function showBadge(a){
  var el=document.getElementById('badgeToast');if(!el)return;
  document.getElementById('badgeIcon').textContent=a.icon;
  document.getElementById('badgeName').textContent=a.name;
  document.getElementById('badgeDesc').textContent=a.desc;
  el.classList.add('on');
  setTimeout(function(){el.classList.remove('on')},3500);
}
function renderBadges(){
  var st=(window.DASH||{}).stats||{};var unlocked=JSON.parse(localStorage.getItem('dash_badges')||'[]');
  return '<div class="badge-grid">'+ACHIEVEMENTS.map(function(a){
    var on=unlocked.indexOf(a.id)>=0||a.check(st);
    return '<div class="badge-item'+(on?'':' locked')+'"><div class="bi">'+a.icon+'</div><div class="bl">'+esc(a.name)+'</div></div>';
  }).join('')+'</div><div style="font-size:10px;color:var(--t2)">'+unlocked.length+'/'+ACHIEVEMENTS.length+' unlocked</div>';
}
function renderStreakCal(){
  var D=window.DASH||{};var runs=D.runs||[];var daily=D.daily||D.stats&&D.stats.daily||{};
  var now=new Date();var year=now.getFullYear();var month=now.getMonth();
  var firstDay=new Date(year,month,1);var lastDay=new Date(year,month+1,0);
  var startDow=firstDay.getDay();var days=lastDay.getDate();
  var today=now.getDate();var html='<div class="streak-cal">';
  for(var i=0;i<startDow;i++)html+='<div class="sc-day empty"></div>';
  for(var d=1;d<=days;d++){
    var dateStr=year+'-'+String(month+1).padStart(2,'0')+'-'+String(d).padStart(2,'0');
    var count=daily[dateStr]||0;
    var fails=runs.filter(function(r){return r.conclusion==='failure'&&new Date(r.createdAt||0).toLocaleDateString('sv-SE',{timeZone:'Asia/Jakarta'})===dateStr}).length;
    var cls=count>0?(fails>0?'fail':'ok'):'';
    var isToday=d===today;
    html+='<div class="sc-day '+cls+(isToday?' today':'')+'" title="'+dateStr+': '+count+' runs">'+d+'</div>';
  }
  html+='</div>';var el=document.getElementById('streakCalGrid');if(el)el.innerHTML=html;
}
function renderFreqClock(){
  var D=window.DASH||{};var runs=D.runs||[];var hours={};
  runs.forEach(function(r){var h=new Date(r.createdAt||0).getHours();hours[h]=(hours[h]||0)+1});
  var max=Math.max.apply(null,Object.values(hours).concat([1]));var cx=100,cy=100,r=80;
  var html='<svg class="freq-clock" width="200" height="200" viewBox="0 0 200 200">';
  for(var h=0;h<24;h++){
    var count=hours[h]||0;var len=(count/max)*60;var angle=(h/24)*2*Math.PI-Math.PI/2;
    var x2=cx+Math.cos(angle)*(r+len);var y2=cy+Math.sin(angle)*(r+len);
    var x1=cx+Math.cos(angle)*r;var y1=cy+Math.sin(angle)*r;
    var col=count>0?'var(--bl)':'var(--bg3)';
    html+='<line x1="'+x1+'" y1="'+y1+'" x2="'+x2+'" y2="'+y2+'" stroke="'+col+'" stroke-width="3" stroke-linecap="round" title="'+h+':00 → '+count+' runs"/>';
  }
  html+='<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="none" stroke="var(--brd)" stroke-width="1"/>';
  html+='<text x="'+cx+'" y="'+cy+'" text-anchor="middle" dy=".3em" font-size="10" fill="var(--t2)">24h</text></svg>';
  var el=document.getElementById('freqClockWrap');if(el)el.innerHTML=html+'<div style="font-size:9px;color:var(--t2);text-align:center">Intensitas runs per jam</div>';
}
function detectFailPatterns(){
  var D=window.DASH||{};var runs=D.runs||[];var fails=runs.filter(function(r){return r.conclusion==='failure'});
  if(fails.length<2)return '';
  var byHour={};var byDay={};var byName={};
  fails.forEach(function(r){var d=new Date(r.createdAt||0);var h=d.getHours();var dw=d.getDay();var nm=r.name||'';
    byHour[h]=(byHour[h]||0)+1;byDay[dw]=(byDay[dw]||0)+1;byName[nm]=(byName[nm]||0)+1});
  var patterns=[];
  Object.keys(byHour).forEach(function(h){if(byHour[h]>=2)patterns.push('Jam '+h+':00 — '+byHour[h]+' fail')});
  Object.keys(byDay).forEach(function(d){var days=['Min','Sen','Sel','Rab','Kam','Jum','Sab'];if(byDay[d]>=2)patterns.push(days[d]+' — '+byDay[d]+' fail')});
  Object.keys(byName).forEach(function(n){if(byName[n]>=2)patterns.push(n+' — '+byName[n]+' fail')});
  if(!patterns.length)return '';
  return '<div class="fail-pattern">⚠️ <b>Pattern detected:</b><br>'+patterns.map(function(p){return '• '+p}).join('<br>')+'</div>';
}
function predictDuration(){
  var D=window.DASH||{};var runs=D.runs||[];
  var done=runs.filter(function(r){return r.conclusion==='success'&&r.name==='rusemeva-vault'&&r.createdAt&&r.updatedAt});
  if(done.length<3)return null;
  var durs=done.map(function(r){return new Date(r.updatedAt)-new Date(r.createdAt)}).sort(function(a,b){return a-b});
  var avg=durs.reduce(function(a,b){return a+b},0)/durs.length;
  var median=durs[Math.floor(durs.length/2)];
  return {avg:Math.round(avg/60000),median:Math.round(median/60000),samples:durs.length};
}
function renderClusters(){
  var D=window.DASH||{};var runs=(D.runs||[]).slice().sort(function(a,b){return new Date(b.createdAt||0)-new Date(a.createdAt||0)});
  var sessions=[];var current=null;
  runs.forEach(function(r){
    var t=new Date(r.createdAt||0).getTime();if(!t)return;
    if(current&&Math.abs(t-current.start)<3600000){current.runs.push(r);current.end=t}
    else{current={start:t,end:t,runs:[r]};sessions.push(current)}
  });
  return sessions.slice(0,10).map(function(s){
    var vault=s.runs.filter(function(r){return r.name==='rusemeva-vault'}).length;
    var enc=s.runs.filter(function(r){return r.name==='rusemeva-encode'}).length;
    var time=new Date(s.start).toLocaleTimeString('en-GB',{timeZone:'Asia/Jakarta',hour:'2-digit',minute:'2-digit'});
    return '<div class="session-group"><div class="session-header">🕐 '+time+' WIB — '+s.runs.length+' runs ('+vault+' vault, '+enc+' enc)</div>'+s.runs.slice(0,5).map(rowRun).join('')+'</div>';
  }).join('');
}
function toggleTerminal(){
  var el=document.getElementById('terminalBox');if(!el)return;
  el.style.display=el.style.display==='none'?'block':'none';
  if(el.style.display!=='none'){var inp=document.getElementById('terminalInput');if(inp)inp.focus()}
}
function execTerminal(cmd){
  var out=document.getElementById('terminalOut');if(!out)return;
  var c=cmd.trim().toLowerCase();var parts=c.split(/\s+/);var D=window.DASH||{};var st=D.stats||{};
  var nl=String.fromCharCode(10);
  var html='<span class="terminal-prompt">rusemeva@dash:~$</span> '+esc(cmd)+nl;
  if(c==='help'){html+='Commands: stats, search <query>, export csv, export md, theme, clear, fails, badges, report, about'}
  else if(c==='stats'){html+='Total: '+st.total+' | OK: '+st.success+' | Fail: '+st.failed+' | Rate: '+st.rate+'% | Streak: '+st.streak+'d'}
  else if(parts[0]==='search'&&parts[1]){var q=document.getElementById('q');if(q){q.value=parts.slice(1).join(' ');srch()}html+='Searching: '+esc(parts.slice(1).join(' '))}
  else if(c==='export csv'){html+='Exporting CSV...';expCSV()}
  else if(c==='export md'){html+='Exporting MD...';expMD()}
  
  else if(c==='clear'){html=''}
  else if(c==='fails'){html+=showFailReplay()}
  else if(c==='badges'){html+=renderBadges()}
  else if(c==='report'){html+=generateReport()}
  else if(c==='about'){html+='Rusemeva Dashboard v8.9 — github.com/daudjoss/daudjoss-vault'}
  else if(c===''){html+=''}
  else{html+='Unknown command: '+esc(cmd)+'. Type help.'}
  out.innerHTML=html+(c==='clear'?'':out.innerHTML);
}
function saveSnapshot(){
  var state={q:(document.getElementById('q')||{}).value||'',theme:document.documentElement.getAttribute('data-t')||'dark',
    accent:localStorage.getItem('dash_accent')||'blue',compact:document.body.classList.contains('compact')?'1':'0'};
  var fb=document.querySelector('.fb.on');state.filter=fb?fb.getAttribute('data-f'):'all';
  var hash=btoa(JSON.stringify(state));location.hash=hash;
  showToast('Snapshot URL copied! Share the link.');
}
function loadSnapshot(){
  if(!location.hash)return;try{var state=JSON.parse(atob(location.hash.slice(1)));
    var q=document.getElementById('q');if(q&&state.q){q.value=state.q;srch()}
    if(state.theme){document.documentElement.setAttribute('data-t',state.theme);localStorage.setItem('th',state.theme)}
    if(state.accent){localStorage.setItem('dash_accent',state.accent);applyAccent()}
    if(state.compact==='1'&&!document.body.classList.contains('compact'))toggleCompact();
    if(state.filter){var fb=document.querySelector('.fb[data-f="'+state.filter+'"]');if(fb)fb.click()}
  }catch(e){}
}
function renderStatSparkline(values,color){
  var max=Math.max.apply(null,values.concat([1]));var w=40,h=14,step=w/(values.length-1);
  var pts=values.map(function(v,i){return (i*step)+','+(h-(v/max*h))}).join(' ');
  return '<svg class="stat-spark" width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'"><polyline points="'+pts+'" fill="none" stroke="'+color+'" stroke-width="1"/></svg>';
}
function renderDonut(){
  var D=window.DASH||{};var runs=D.runs||[];
  var ok=runs.filter(function(r){return r.conclusion==='success'}).length;
  var fl=runs.filter(function(r){return r.conclusion==='failure'}).length;
  var cn=runs.filter(function(r){return r.conclusion==='cancelled'}).length;
  var rn=runs.filter(function(r){return statusKeyJs(r)==='in_progress'}).length;
  var total=ok+fl+cn+rn;if(!total)return '';
  var r=50,cx=60,cy=60,circ=2*Math.PI*r;var offset=0;
  var slices=[{val:ok,col:'var(--gn)',label:'OK'},{val:fl,col:'var(--rd)',label:'Fail'},{val:cn,col:'var(--t2)',label:'Cancel'},{val:rn,col:'var(--bl)',label:'Running'}];
  var html='<svg width="120" height="120" viewBox="0 0 120 120">';
  slices.forEach(function(s){
    var pct=s.val/total;var dash=pct*circ;
    html+='<circle class="donut-slice" cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="none" stroke="'+s.col+'" stroke-width="12" stroke-dasharray="'+dash+' '+(circ-dash)+'" stroke-dashoffset="'+(-offset)+'" transform="rotate(-90 '+cx+' '+cy+')" data-label="'+s.label+'" />';
    offset+=dash;
  });
  html+='<text x="'+cx+'" y="'+cy+'" text-anchor="middle" dy=".3em" font-size="14" font-weight="bold" fill="var(--t1)">'+total+'</text></svg>';
  html+='<div class="donut-legend">'+slices.map(function(s){return '<span style="color:'+s.col+';font-size:10px;cursor:pointer" >'+s.label+': '+s.val+'</span>'}).join(' · ')+'</div>';
  return html;
}
function donutFilter(label){
  var fb=document.querySelectorAll('.fb');
  if(label==='Fail'){fb.forEach(function(b){if(b.getAttribute('data-f')==='fail')b.click()})}
  else if(label==='Running'){fb.forEach(function(b){if(b.getAttribute('data-f')==='running')b.click()})}
  else if(label==='OK'){fb.forEach(function(b){if(b.getAttribute('data-f')==='ok')b.click()})}
  else{fb.forEach(function(b){if(b.getAttribute('data-f')==='all')b.click()})}
}
function renderFlowParticles(){
  var flow=document.getElementById('flow-diagram');if(!flow)return;
  var arrows=flow.querySelectorAll('.flow-arrow');
  arrows.forEach(function(a){
    for(var i=0;i<3;i++){
      var p=document.createElement('div');p.className='flow-particle';p.style.animationDelay=(i*0.7)+'s';
      a.style.position='relative';a.appendChild(p);
    }
  });
}
function toggleGlass(){
  document.body.classList.toggle('glass-mode');
  var on=document.body.classList.contains('glass-mode');
  localStorage.setItem('dash_glass',on?'1':'0');
}
function applyGlass(){
  if(localStorage.getItem('dash_glass')==='1')document.body.classList.add('glass-mode');
}


function renderDonutView(){var el=document.getElementById('donutWrap');if(el)el.innerHTML=renderDonut()}
function renderGauge(){
  var st=(window.DASH||{}).stats||{};var rate=st.rate||0;
  var r=28,c=2*Math.PI*r,off=c-(rate/100*c);
  var col=rate>=80?'var(--gn)':(rate>=60?'var(--or)':'var(--rd)');
  var svg='<div class="gauge"><svg width="64" height="64"><circle class="gauge-bg" cx="32" cy="32" r="'+r+'"/><circle class="gauge-fg" cx="32" cy="32" r="'+r+'" stroke="'+col+'" stroke-dasharray="'+c+'" stroke-dashoffset="'+off+'"/></svg><div class="gauge-txt" style="color:'+col+'">'+rate+'%</div></div>';
  var el=document.getElementById('hero-gauge');if(el)el.innerHTML=svg;
}
function renderFreshness(){
  var D=window.DASH||{};var gen=D.generated;var cls='ok',txt='Live';
  if(gen){var min=(Date.now()-new Date(gen).getTime())/60000;
    cls=min<5?'ok':(min<30?'warn':'stale');
    txt=min<5?'Live ('+Math.round(min)+'m)':(min<30?'Stale ('+Math.round(min)+'m)':'Stale ('+Math.round(min)+'m)');
  }
  var el=document.getElementById('hero-fresh');
  if(el)el.innerHTML='<span class="fresh-dot '+cls+'"></span><span style="font-size:10px;color:var(--t2)">'+txt+'</span>';
}
function rateZoneHtml(rate){
  var cls=rate>=80?'good':(rate>=60?'mid':'bad');
  return '<span class="rate-zone '+cls+'">'+rate+'%</span>';
}
function updateTabTitle(){
  var D=window.DASH||{};var st=D.stats||{};var runs=D.runs||[];
  var rn=st.running||0;var fl=st.failed||0;var t='';
  if(rn>0)t+='🔄'+rn+' running · ';
  if(fl>0)t+='❌'+fl+' fail · ';
  t+='Rusemeva';
  document.title=t;
}
function updateFavicon(){
  var D=window.DASH||{};var st=D.stats||{};var fl=st.failed||0;
  if(fl===0){var link=document.querySelector("link[rel='icon']");if(link)link.href='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🎬</text></svg>';return}
  var c=document.createElement('canvas');c.width=32;c.height=32;var ctx=c.getContext('2d');
  ctx.fillStyle='#0d1117';ctx.fillRect(0,0,32,32);
  ctx.font='20px sans-serif';ctx.fillText('🎬',2,24);
  ctx.fillStyle='#f85149';ctx.beginPath();ctx.arc(26,6,7,0,2*Math.PI);ctx.fill();
  ctx.fillStyle='#fff';ctx.font='bold 9px sans-serif';ctx.textAlign='center';ctx.fillText(String(fl),26,9);
  var link=document.querySelector("link[rel='icon']");if(!link){link=document.createElement('link');link.rel='icon';document.head.appendChild(link)}
  link.href=c.toDataURL();
}
var lastFailCount=0;
function checkSoundAlert(data){
  if(localStorage.getItem('dash_sound')!=='1')return;
  var st=data.stats||{};var fl=st.failed||0;
  if(lastFailCount===0){lastFailCount=fl;return}
  if(fl>lastFailCount){
    try{var ctx=new (window.AudioContext||window.webkitAudioContext)();var osc=ctx.createOscillator();var gain=ctx.createGain();
      osc.connect(gain);gain.connect(ctx.destination);osc.frequency.value=220;osc.type='sine';
      gain.gain.setValueAtTime(0,ctx.currentTime);gain.gain.linearRampToValueAtTime(0.3,ctx.currentTime+0.1);
      gain.gain.linearRampToValueAtTime(0,ctx.currentTime+0.5);osc.start();osc.stop(ctx.currentTime+0.5)}catch(e){}
  }
  lastFailCount=fl;
}
function showToast(msg){
  var t=document.getElementById('toast');if(!t)return;
  t.textContent=msg;t.classList.add('on');
  clearTimeout(window._toastTimer);window._toastTimer=setTimeout(function(){t.classList.remove('on')},1500);
}
function copyRSM(id){
  if(!id)return;
  navigator.clipboard.writeText(id).then(function(){showToast('Copied: '+id)}).catch(function(){})
}
function renderSHist(){var hist=JSON.parse(localStorage.getItem(\'dash_shist\')||\'[]\');var el=document.getElementById(\'qchips\');if(!el)return;var html=\'<div style="margin-top:2px">\';if(hist.length){html+=\'<span style="font-size:9px;color:var(--t2)">Recent:</span> \';hist.forEach(function(h,i){html+=\'<span class="shist-item" onclick="reuseSearch(\'+i+\')">\'+esc(h)+\'</span>\'})}html+=\'</div>\';el.insertAdjacentHTML(\'beforeend\',html)}\nfunction reuseSearch(i){var hist=JSON.parse(localStorage.getItem(\'dash_shist\')||\'[]\');var q=document.getElementById(\'q\');if(q&&hist[i]){q.value=hist[i];srch()}}
function renderQChips(){
  var chips=[['today','Today'],['fail','Failed'],['running','Running'],['rsm','RSM'],['enc','Encode']];
  var html=chips.map(function(c){
    var on=document.body.getAttribute('data-qchip-'+c[0])==='1';
    return '<span class="qchip'+(on?' on':'')+'" onclick="toggleQChip(this)" data-key="'+c[0]+'">'+c[1]+'</span>';
  }).join('');
  var el=document.getElementById('qchips');if(el)el.innerHTML=html;
}
function toggleQChip(el){
  var key=el.getAttribute('data-key');
  var on=document.body.getAttribute('data-qchip-'+key)==='1';
  document.body.setAttribute('data-qchip-'+key,on?'0':'1');
  renderQChips();srch();
}
function applyQChips(rows){
  var today=document.body.getAttribute('data-qchip-today')==='1';
  var fail=document.body.getAttribute('data-qchip-fail')==='1';
  var running=document.body.getAttribute('data-qchip-running')==='1';
  var rsm=document.body.getAttribute('data-qchip-rsm')==='1';
  var enc=document.body.getAttribute('data-qchip-enc')==='1';
  if(!today&&!fail&&!running&&!rsm&&!enc)return rows;
  return rows.filter(function(r){
    if(rsm&&String(r.orv_id||'').indexOf('RSM')<0)return false;
    if(enc&&r.name!=='rusemeva-encode')return false;
    if(fail&&r.conclusion!=='failure')return false;
    if(running&&statusKeyJs(r)!=='in_progress')return false;
    if(today){var d=new Date(r.createdAt||0).toLocaleDateString('sv-SE',{timeZone:'Asia/Jakarta'});var now=new Date().toLocaleDateString('sv-SE',{timeZone:'Asia/Jakarta'});if(d!==now)return false}
    return true;
  });
}
function checkOffline(){
  var el=document.getElementById('offlineBanner');
  if(!el)return;
  function update(){el.classList.toggle('on',!navigator.onLine)}
  update();
  window.addEventListener('online',update);
  window.addEventListener('offline',update);
}
function fireConfetti(){
  var c=document.createElement('canvas');c.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:9999';
  c.width=window.innerWidth;c.height=window.innerHeight;document.body.appendChild(c);
  var ctx=c.getContext('2d');var parts=[];var colors=['#58a6ff','#3fb950','#f0883e','#bc8cff','#f778ba'];
  for(var i=0;i<80;i++){parts.push({x:c.width/2,y:c.height/3,vx:(Math.random()-0.5)*8,vy:Math.random()*-8+2,color:colors[i%5],size:Math.random()*4+2,life:1})}
  var start=Date.now();
  function frame(){
    ctx.clearRect(0,0,c.width,c.height);
    parts.forEach(function(p){p.x+=p.vx;p.y+=p.vy;p.vy+=0.15;p.life-=0.012;
      ctx.globalAlpha=Math.max(0,p.life);ctx.fillStyle=p.color;ctx.fillRect(p.x,p.y,p.size,p.size)});
    if(Date.now()-start<2500)requestAnimationFrame(frame);else c.remove();
  }
  frame();
}
function checkStreakConfetti(data){
  var st=data.stats||{};var streak=st.streak||0;
  var key='confetti_streak_'+streak;
  if((streak===5||streak===10||streak===15||streak===20)&&!localStorage.getItem(key)){
    fireConfetti();localStorage.setItem(key,'1');
  }
}
function expMD(){
  var rows=filteredRows();if(!rows.length)return;
  var nl=String.fromCharCode(10);var md='| ID | Name | Status | Created | RSM-ID |'+nl+'|---|---|---|---|---|'+nl;
  md+=rows.map(function(r){
    var id=r.databaseId||'';var orv=r.orv_id||'';
    return '| '+id+' | '+esc(r.name||'')+' | '+esc(displayStatusJs(r))+' | '+agoJs(r.createdAt||'')+' | '+orv+' |';
  }).join(nl);
  downloadBlob(new Blob([md],{type:'text/markdown'}),'rusemeva-runs.md');
}
function renderRateHistory(){
  var D=window.DASH||{};var daily=D.daily||D.stats&&D.stats.daily||{};
  var days=30;var today=new Date();var vals=[];
  for(var i=days-1;i>=0;i--){
    var d=new Date(today.getTime()-i*86400000);
    var key=d.toLocaleDateString('sv-SE',{timeZone:'Asia/Jakarta'});
    vals.push({key:key,count:daily[key]||0});
  }
  var max=Math.max.apply(null,vals.map(function(v){return v.count}))||1;
  var w=280,h=40,step=w/(vals.length-1);
  var pts=vals.map(function(v,i){return (i*step)+','+(h-(v.count/max*h))}).join(' ');
  var svg='<svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'"><polyline points="'+pts+'" fill="none" stroke="var(--bl)" stroke-width="1.5"/></svg>';
  return '<div style="margin-top:8px"><div style="font-size:11px;font-weight:600;margin-bottom:4px">Rate history 30 hari</div>'+svg+'<div style="font-size:9px;color:var(--t2);margin-top:2px">Max: '+max+' runs/day</div></div>';
}
var _lastFeedIds={};
function markNewFeed(data){
  var runs=data.runs||[];
  runs.forEach(function(r){
    var rid=String(r.databaseId||'');
    if(rid&&!_lastFeedIds[rid]){
      if(Object.keys(_lastFeedIds).length>0)r._isNew=true;
      _lastFeedIds[rid]=1;
    }
  });
  setTimeout(function(){runs.forEach(function(r){r._isNew=false})},500);
}


function renderSparkline(){
  var D=window.DASH||{};var daily=D.daily||D.stats&&D.stats.daily||{};
  var days=7;var today=new Date();var vals=[];
  for(var i=days-1;i>=0;i--){
    var d=new Date(today.getTime()-i*86400000);
    var key=d.toLocaleDateString('sv-SE',{timeZone:'Asia/Jakarta'});
    vals.push(daily[key]||0);
  }
  var max=Math.max.apply(null,vals)||1;
  var w=80,h=20,step=w/(vals.length-1);
  var pts=vals.map(function(v,i){return (i*step)+','+(h-(v/max*h))}).join(' ');
  var svg='<svg class="spark" width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'">'
    +'<polyline points="'+pts+'" fill="none" stroke="var(--bl)" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>'
    +'<circle cx="'+((vals.length-1)*step)+'" cy="'+(h-(vals[vals.length-1]/max*h))+'" r="2" fill="var(--bl)"/>'
    +'</svg>';
  var el=document.getElementById('hero-spark');
  if(el)el.innerHTML='<span class="rate-ring">📈 7d '+svg+' <b style="color:var(--bl)">'+vals[vals.length-1]+'</b> today</span>';
}


function renderETA(){
  var D=window.DASH||{};var runs=D.runs||[];
  var running=runs.filter(function(r){return statusKeyJs(r)==='in_progress'&&r.name==='rusemeva-vault'});
  var done=runs.filter(function(r){return r.conclusion==='success'&&r.name==='rusemeva-vault'&&r.createdAt&&r.updatedAt});
  var avgMs=0;
  if(done.length){var total=0;done.forEach(function(r){total+=new Date(r.updatedAt)-new Date(r.createdAt)});avgMs=total/done.length}
  running.forEach(function(r){
    if(!avgMs)return;
    var elapsed=Date.now()-new Date(r.createdAt).getTime();
    var remain=Math.max(0,Math.round((avgMs-elapsed)/60000));
    var id=r.orv_id||r.databaseId;
    var badge=document.querySelector('[data-rid="'+r.databaseId+'"] .fi-status');
    if(badge&&!badge.getAttribute('data-eta')){
      badge.setAttribute('data-eta','1');
      badge.innerHTML+=' <span class="eta-badge">ETA ~'+remain+'m</span>';
    }
  });
}

function renderAlert(){
  var D=window.DASH||{};var runs=D.runs||[];
  var h24=Date.now()-24*3600*1000;
  var fails=runs.filter(function(r){return r.name==='rusemeva-vault'&&r.conclusion==='failure'&&new Date(r.createdAt||0).getTime()>=h24});
  var el=document.getElementById('hero-alert');
  if(!el)return;
  if(fails.length>=2){
    var hours={};fails.forEach(function(r){var h=new Date(r.createdAt).getHours();hours[h]=(hours[h]||0)+1});
    var pattern=Object.keys(hours).filter(function(h){return hours[h]>=2});
    var msg=pattern.length?'⚠️ Pattern: '+fails.length+' fail jam '+pattern.join(',')+'': '⚠️ '+fails.length+' vault fail dalam 24h';
    el.innerHTML='<div class="alert-chip">'+msg+'</div>';
  }else{el.innerHTML=''}
}

function renderHeatmap(){
  var D=window.DASH||{};var daily=D.daily||D.stats&&D.stats.daily||{};
  var days=30;var today=new Date();
  var html='<div class="heatmap">';
  for(var i=days-1;i>=0;i--){
    var d=new Date(today.getTime()-i*86400000);
    var key=d.toLocaleDateString('sv-SE',{timeZone:'Asia/Jakarta'});
    var count=daily[key]||0;
    var cls=count===0?'':(count<=1?'l1':(count<=2?'l2':(count<=4?'l3':'l4')));
    html+='<div class="hm-cell '+cls+'" title="'+key+': '+count+' runs"></div>';
  }
  html+='</div>';
  var el=document.getElementById('heatmap-grid');
  if(el)el.innerHTML=html;
}

function renderHero(){var r=document.getElementById('hero-rsm');if(r)r.innerHTML=lastRsmHtml();
  var s=document.getElementById('hero-storage');if(s)s.innerHTML=storageStoryHtml();
  var d=document.getElementById('hero-diff');if(d)d.innerHTML=diff24Html();renderHeatmap();renderSparkline();renderAlert();renderETA();renderGauge();renderFreshness();renderRings();renderFlow();renderCounters();checkThresholdAlert();renderStreakCal();renderFreqClock();renderDonutView();renderFlowParticles();checkAchievements();renderHmMatrix();hideSkeleton();startStopwatch();}

// ── honest client health ──
function checkHealth(){
  var rows=[];var D=window.DASH||{};var st=D.stats||{};
  // data.json age
  var gen=D.generated;var ageMin=0;
  if(gen){ageMin=(Date.now()-new Date(gen).getTime())/60000;}
  rows.push({label:'data.json age',val:ageMin<120?Math.round(ageMin)+'m':'stale',ok:ageMin<120});
  // worker orv-map
  rows.push({label:'Worker orv-map',val:((D.runs||[]).filter(function(r){return r.orv_id}).length)+' linked',ok:true});
  // vault fail 24h
  var h24=Date.now()-24*3600*1000;
  var vf=(D.runs||[]).filter(function(r){return r.name==='rusemeva-vault'&&r.conclusion==='failure'&&new Date(r.createdAt||0).getTime()>=h24}).length;
  rows.push({label:'vault fail 24h',val:vf+' run(s)',ok:vf===0,warn:vf>0&&vf<3});
  // running
  var rn=st.running||0;
  rows.push({label:'running',val:rn+' job(s)',ok:rn<=5,warn:rn>5});
  var html=rows.map(function(r){
    var cls=r.ok?'ok':(r.warn?'warn':'err');
    return '<div class="health-row"><span class="health-dot '+cls+'"></span><span>'+esc(r.label)+'</span><span style="margin-left:auto;color:var(--t2)">'+esc(r.val)+'</span></div>';
  }).join('');
  var box=document.getElementById('health-rows');if(box)box.innerHTML=html;
  var ts=document.getElementById('health-ts');if(ts)ts.textContent=new Date().toLocaleTimeString('en-GB',{timeZone:'Asia/Jakarta',hour12:false})+' WIB';
}

// ── deep link ?rsm= / ?run= ──
function applyDeepLink(){
  var p=new URLSearchParams(location.search);
  var rsm=p.get('rsm');var run=p.get('run');
  if(!rsm&&!run)return;
  var q=document.getElementById('q');
  if(q){q.value=rsm||run||'';srch();}
  // highlight in table
  setTimeout(function(){
    var sel=rsm?'[data-orv="'+rsm+'"]':(run?'[data-rid="'+run+'"]':'');
    var el=document.querySelector(sel);
    if(el){el.scrollIntoView({behavior:'smooth',block:'center'});el.classList.add('hl-row');
      if(el.tagName==='TR'){}else{var p2=el.closest('tr')||el;p2.classList.add('hl-row');}
    }
  },300);
}

// ── saved views ──
function applyView(btn,key){
  document.querySelectorAll('.view-btn').forEach(function(b){b.classList.remove('act')});
  if(btn)btn.classList.add('act');
  if(!key)return;
  var fb=document.querySelectorAll('.fb');var onFb=null;
  fb.forEach(function(b){if(b.classList.contains('on'))onFb=b;});
  if(key==='all'){if(onFb)filt(onFb.getAttribute('data-f')||'all',onFb);var q=document.getElementById('q');if(q)q.value='';srch();return;}
  if(key==='fail'){fb.forEach(function(b){if(b.getAttribute('data-f')==='fail')b.click();});return;}
  if(key==='running'){fb.forEach(function(b){if(b.getAttribute('data-f')==='running')b.click();});return;}
  if(key==='today'){var q=document.getElementById('q');if(q){var today=new Date().toLocaleDateString('sv-SE',{timeZone:'Asia/Jakarta'});q.value=today;srch();}return;}
  if(key==='rsm'){var q=document.getElementById('q');if(q){q.value='RSM';srch();}return;}
}
function saveCurrentView(){
  var q=document.getElementById('q');var qq=q?q.value:'';
  var fb=document.querySelector('.fb.on');var f=fb?fb.getAttribute('data-f'):'all';
  var name=prompt('Nama view:');if(!name)return;
  var views=JSON.parse(localStorage.getItem('dash_views')||'[]');
  views.push({name:name,q:qq,filt:f});
  localStorage.setItem('dash_views',JSON.stringify(views));
  renderSavedViews();renderHero();checkHealth();applyDeepLink();if(DATA)checkNewRuns(DATA);
}
function renderSavedViews(){
  var views=JSON.parse(localStorage.getItem('dash_views')||'[]');
  var box=document.getElementById('saved-views');if(!box)return;
  box.innerHTML=views.map(function(v,i){
    return '<button class="view-btn" onclick="loadView('+i+')">'+esc(v.name)+'</button> '
      +'<button class="view-btn" style="padding:1px 4px" onclick="delView('+i+')">×</button>';
  }).join('');
}
function loadView(i){
  var views=JSON.parse(localStorage.getItem('dash_views')||'[]');var v=views[i];if(!v)return;
  var q=document.getElementById('q');if(q&&v.q)q.value=v.q;srch();
  var fb=document.querySelector('.fb[data-f="'+v.filt+'"]');if(fb)fb.click();
}
function delView(i){
  var views=JSON.parse(localStorage.getItem('dash_views')||'[]');views.splice(i,1);
  localStorage.setItem('dash_views',JSON.stringify(views));renderSavedViews();
}

// ── compact mode ──
function setThreshold(v){v=parseInt(v||'2',10);if(v<1)v=1;if(v>20)v=20;localStorage.setItem('dash_threshold',String(v));checkThresholdAlert()}
function toggleSound(){var on=localStorage.getItem('dash_sound')==='1';localStorage.setItem('dash_sound',on?'0':'1');var btn=document.querySelector('[onclick*=toggleSound]');if(btn)btn.textContent=on?'OFF':'ON'}
function toggleCompact(){
  document.body.classList.toggle('compact');
  var on=document.body.classList.contains('compact');
  localStorage.setItem('dash_compact',on?'1':'0');
  var b=document.getElementById('compactBtn');if(b)b.textContent=on?'📐 Normal':'📐 Compact';
}

// ── compare 2 runs ──
var cmpPick=[];
function toggleCmpPick(rid){
  var i=cmpPick.indexOf(rid);
  if(i>=0){cmpPick.splice(i,1);}else{if(cmpPick.length>=2)cmpPick.shift();cmpPick.push(rid);}
  document.querySelectorAll('.fi').forEach(function(el){
    var r=el.getAttribute('data-rid');
    if(cmpPick.indexOf(r)>=0)el.style.outline='2px solid var(--or)';else el.style.outline='';
  });
  if(cmpPick.length===2)showCmpModal();
}
function showCmpModal(){
  var D=window.DASH||{};var runs=D.runs||[];
  var r1=runs.filter(function(r){return String(r.databaseId)===cmpPick[0]})[0];
  var r2=runs.filter(function(r){return String(r.databaseId)===cmpPick[1]})[0];
  if(!r1||!r2)return;
  document.getElementById('mo').classList.add('on');
  document.getElementById('mt').textContent='🔄 Compare 2 runs';
  function fmt(r){if(!r)return '—';
    return '<div style="font-size:11px;line-height:1.6">'
      +'<b>ID:</b> '+(r.orv_id||r.databaseId)+'<br>'
      +'<b>Name:</b> '+esc(r.name||'')+'<br>'
      +'<b>Status:</b> '+esc(displayStatusJs(r))+'<br>'
      +'<b>Created:</b> '+agoJs(r.createdAt||'')+'<br>'
      +'<a href="https://github.com/daudjoss/daudjoss-vault/actions/runs/'+r.databaseId+'" target="_blank">GHA ↗</a></div>';}
  document.getElementById('mb').innerHTML='<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">'
    +'<div>'+fmt(r1)+'</div><div>'+fmt(r2)+'</div></div>'
    +'<div style="margin-top:8px"><button class="btn" id="cmpClearBtn">Clear</button></div>';var cb=document.getElementById('cmpClearBtn');if(cb)cb.onclick=function(){cmpPick=[];clM();document.querySelectorAll('.fi').forEach(function(e){e.style.outline=''})}
}
var CMD_ITEMS=[
  {cat:'Navigate',label:'Home',act:"document.querySelector('.hero').scrollIntoView({behavior:'smooth'})"},
  {cat:'Navigate',label:'Feed',act:"document.getElementById('sec-feed').scrollIntoView({behavior:'smooth'})"},
  {cat:'Navigate',label:'Recordings',act:"document.getElementById('sec-rec').scrollIntoView({behavior:'smooth'})"},
  {cat:'Navigate',label:'Tools',act:"document.getElementById('sec-tools').scrollIntoView({behavior:'smooth'})"},
  {cat:'Tools',label:'Stats',act:"showM('stats')"},
  {cat:'Tools',label:'Search',act:"showM('search')"},
  {cat:'Tools',label:'Export CSV',act:"expCSV()"},
  {cat:'Tools',label:'Export JSON',act:"expJSON()"},
  {cat:'Tools',label:'Customize',act:"showM('customize')"},
  {cat:'Tools',label:'Player',act:"showM('player')"},
  {cat:'View',label:'Compact toggle',act:"toggleCompact()"},
  {cat:'View',label:'Save view',act:"saveCurrentView()"},
  {cat:'View',label:'Refresh',act:"softRefresh().then(function(ok){if(!ok)location.reload()})"},
  {cat:'Help',label:'Keys',act:"showM('keys')"},
  {cat:'Help',label:'About',act:"showM('about')"},
  {cat:'CI/CD',label:'Trigger Analysis',act:"showM('trigger')"},
  {cat:'CI/CD',label:'Run Number Tracker',act:"showM('runnum')"},
  {cat:'CI/CD',label:'Commit Messages',act:"showM('commitmsg')"},
  {cat:'CI/CD',label:'Event Timeline',act:"showM('eventtl')"},
  {cat:'CI/CD',label:'Run Number Gaps',act:"showM('rungap')"},
  {cat:'CI/CD',label:'Deploy Frequency',act:"showM('depfreq')"},
  {cat:'CI/CD',label:'MTTR',act:"showM('mttr')"},
  {cat:'CI/CD',label:'Change Failure Rate',act:"showM('cfr')"},
  {cat:'CI/CD',label:'Lead Time',act:"showM('leadtime')"},
  {cat:'CI/CD',label:'Failure Patterns',act:"showM('failpattern')"},
  {cat:'CI/CD',label:'Duration Trends',act:"showM('durtrend')"},
  {cat:'CI/CD',label:'Success by Day',act:"showM('successday')"},
  {cat:'CI/CD',label:'Success by Hour',act:"showM('successhour')"},
  {cat:'CI/CD',label:'Branch Health',act:"showM('branchhealth')"},
  {cat:'CI/CD',label:'Actions Minutes',act:"showM('minutes')"},
  {cat:'CI/CD',label:'Workflow Comparison',act:"showM('workflowcomp')"},
  {cat:'CI/CD',label:'Concurrency',act:"showM('concurrency')"},
  {cat:'CI/CD',label:'Commit Impact',act:"showM('commitimpact')"},
  {cat:'CI/CD',label:'Deploy Timeline',act:"showM('deploymt')"},
  {cat:'CI/CD',label:'Retry Tracker',act:"showM('retry')"},
  {cat:'Data',label:'Heatmap',act:"showM('heatmap')"},
  {cat:'Data',label:'Achievements',act:"showM('achievements')"},
  {cat:'Data',label:'Analytics Charts',act:"showM('analytics')"},
  {cat:'Data',label:'Gantt Timeline',act:"showM('gantt')"},
  {cat:'Data',label:'Run Comparison',act:"showM('compare2')"},
  {cat:'Data',label:'Markdown Report',act:"showM('mdexport')"},
  {cat:'Tools',label:'Dashboard Clock',act:"showM('clock')"},
  {cat:'Help',label:'Updates',act:"showM('updates')"}
];
var cmdSel=0;
function openCmd(){document.getElementById('cmdOverlay').classList.add('on');var i=document.getElementById('cmdInput');i.value='';i.focus();cmdSel=0;filterCmd()}
function closeCmd(){document.getElementById('cmdOverlay').classList.remove('on')}
function filterCmd(){
  var q=(document.getElementById('cmdInput').value||'').toLowerCase();
  var items=CMD_ITEMS.filter(function(c){return c.label.toLowerCase().indexOf(q)>=0||c.cat.toLowerCase().indexOf(q)>=0});
  // also search runs
  var D=window.DASH||{};var runs=(D.runs||[]).filter(function(r){
    var blob=((r.orv_id||'')+' '+(r.databaseId||'')+' '+(r.name||'')).toLowerCase();
    return q&&blob.indexOf(q)>=0;}).slice(0,5);
  var html=items.map(function(c,i){
    return '<div class="cmd-item'+(i===cmdSel?' sel':'')+'" data-act="'+esc(c.act)+'"><span>'+esc(c.label)+'</span><span class="cmd-cat">'+esc(c.cat)+'</span></div>';
  }).join('');
  html+=runs.map(function(r){
    var id=r.orv_id||r.databaseId;
    return '<div class="cmd-item" data-run="'+r.databaseId+'"><span>🔎 '+esc(id)+'</span><span class="cmd-cat">'+esc(r.name||'')+'</span></div>';
  }).join('');
  var box=document.getElementById('cmdList');box.innerHTML=html;box.querySelectorAll('.cmd-item').forEach(function(el){el.onclick=function(){if(el.getAttribute('data-run')){location.href='?run='+el.getAttribute('data-run')}else{closeCmd();try{eval(el.getAttribute('data-act'))}catch(e){console.warn(e)}}}})||'<div class="cmd-item" style="color:var(--t2)">Tidak ada</div>';
}
function cmdKey(e){
  if(e.key==='Escape'){closeCmd();return;}
      if(e.key==='Enter'){var items=document.querySelectorAll('.cmd-item');if(items[cmdSel])items[cmdSel].click();}
}

// ── export filtered (override dashRows to respect current filter) ──
function filteredRows(){
  var D=window.DASH||{};var rows=(D.runs||[]).filter(function(r){return r.name==='rusemeva-vault'||r.name==='rusemeva-encode'});
  var q=document.getElementById('q');var qq=q?q.value.toLowerCase().trim():'';
  if(qq){rows=rows.filter(function(r){var blob=((r.orv_id||'')+' '+(r.databaseId||'')+' '+(r.name||'')+' '+(r.conclusion||'')).toLowerCase();return blob.indexOf(qq)>=0;});}
  return rows;
}

// ── keyboard shortcut: P for palette ──

async function softRefresh(){try{var r=await fetch('data.json?ts='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error('data.json '+r.status);var data=await r.json();try{var m=await fetch('https://rusemeva.rusemeva-vault.workers.dev/api/orv-map',{cache:'no-store'});if(m.ok){var mj=await m.json();if(mj&&mj.map)data.orv_map=mj.map}}catch(e){}updateLiveUI(data);return true}catch(e){console.warn('softRefresh failed',e);return false}}
var cd=30;setInterval(async function(){cd--;var t=document.getElementById('tmr');if(t)t.textContent=cd+'s';if(cd<=0){var mo=document.getElementById('mo');if(!mo.classList.contains('on')&&document.activeElement.tagName!=='INPUT'&&document.activeElement.tagName!=='TEXTAREA'){var ok=await softRefresh();if(!ok)location.reload();cd=30}else{cd=30}}},1000);
// initial soft patch shortly after load (pick up fresher data.json / orv-map)
applyCustomize();if(localStorage.getItem('dash_compact')==='1'){document.body.classList.add('compact');var b=document.getElementById('compactBtn');if(b)b.textContent='📐 Normal'}renderSavedViews();renderHero();checkHealth();applyDeepLink();document.addEventListener('keydown',function(e){if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return;if(e.key==='p'||e.key==='P'){e.preventDefault();openCmd()}});if(localStorage.getItem('dash_compact')==='1'){document.body.classList.add('compact');var cb=document.getElementById('compactBtn');if(cb)cb.textContent='Normal'}renderSavedViews();renderHero();checkHealth();applyDeepLink();setTimeout(function(){softRefresh()},2500);
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
    S['_orv_n'] = len(orv_map or [])
    print(f"📊 {S['total']} vault, {S['rate']}% OK, streak {S['streak']}, GH {fmt_bytes(S.get('gh_bytes') or 0)}, lifetime~{S.get('lifetime_est_gb')}GB est")
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
            "headBranch": r.get("headBranch") or "",
            "headSha": r.get("headSha") or "",
            "runNumber": r.get("number") or 0,
            "displayTitle": r.get("displayTitle") or "",
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
            "build": "v10.1-max",
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
