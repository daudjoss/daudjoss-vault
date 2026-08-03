#!/usr/bin/env python3
"""Rusemeva Dashboard v8.5.1 — menu upgrades: richer stats/search/timeline/player."""
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
    raw = gh(["run","list","--repo",REPO,"--limit",str(n),"--json","databaseId,name,status,conclusion,createdAt,event,updatedAt"])
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
.gal-item,.widget,.theme-opt,.ffi,.ach,.pi,.cmp-item{border-radius:10px;transition:transform .18s,box-shadow .18s,border-color .18s}
.gal-item:hover,.widget:hover,.ffi:hover,.ach:hover{box-shadow:0 6px 18px rgba(0,0,0,.15)}
.theme-opt{position:relative;overflow:hidden;min-height:64px}
.theme-swatch{height:18px;border-radius:6px;margin:0 4px 6px;border:1px solid rgba(255,255,255,.08)}
.theme-swatch.dark{background:linear-gradient(90deg,#0d1117,#21262d,#58a6ff)}
.theme-swatch.light{background:linear-gradient(90deg,#f6f8fa,#fff,#0969da)}
.theme-swatch.ocean{background:linear-gradient(90deg,#001220,#003355,#00aaff)}
.theme-swatch.forest{background:linear-gradient(90deg,#0a1a0a,#203020,#44ff44)}
.theme-opt.sel{box-shadow:0 0 0 1px var(--bl),0 6px 16px rgba(88,166,255,.15)}
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
.rsm-card{background:var(--bg3);border:1px solid var(--brd);border-radius:10px;padding:10px 12px;margin:8px 0;display:flex;align-items:center;gap:10px;font-size:12px}
.rsm-card .rsm-ico{font-size:20px}.rsm-card .rsm-id{font-weight:700;color:var(--bl)}.rsm-card .rsm-status{font-size:11px;color:var(--t2)}
.rsm-card .rsm-link{margin-left:auto;font-size:10px;text-decoration:none}
.diff-chips{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0 10px}
.diff-chip{padding:3px 8px;border-radius:6px;background:var(--bg3);font-size:10px;color:var(--t2)}
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
  .sc{border-radius:10px}
}

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
<div class="hero" id="sec-home">
<div class="hero-top">
<div class="hero-brand">
<h1>🎬 Rusemeva</h1>
<div class="hero-sub">Vault dashboard · live GHA · Telegram bot</div>
</div>
<div class="hero-actions">
<span class="live-pill"><span class="pulse-dot"></span> LIVE <span id="tmr">30s</span></span>
<button class="btn" onclick="toggleTheme()" title="Theme">🌓</button>
<button class="btn" onclick="softRefresh().then(function(ok){if(!ok)location.reload()})" title="Refresh">🔄</button>
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
<div class="sec" id="sec-themes"><div class="sh"><div class="st">🎨 Themes</div><span style="font-size:9px;color:var(--t2)">tap to apply</span></div><div class="theme">
<div class="theme-opt sel" onclick="setTheme('dark')"><div class="theme-swatch dark"></div><div class="theme-opt-icon">🌙</div><div class="theme-opt-label">Dark</div></div>
<div class="theme-opt" onclick="setTheme('light')"><div class="theme-swatch light"></div><div class="theme-opt-icon">☀️</div><div class="theme-opt-label">Light</div></div>
<div class="theme-opt" onclick="setTheme('ocean')"><div class="theme-swatch ocean"></div><div class="theme-opt-icon">🌊</div><div class="theme-opt-label">Ocean</div></div>
<div class="theme-opt" onclick="setTheme('forest')"><div class="theme-swatch forest"></div><div class="theme-opt-icon">🌲</div><div class="theme-opt-label">Forest</div></div>
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

<div class="bnav">
<button onclick="document.getElementById('sec-home').scrollIntoView({behavior:'smooth'})"><span class="bi">🏠</span>Home</button>
<button onclick="document.getElementById('sec-feed').scrollIntoView({behavior:'smooth'})"><span class="bi">📰</span>Feed</button>
<button onclick="document.getElementById('sec-rec').scrollIntoView({behavior:'smooth'})"><span class="bi">🎬</span>Rec</button>
<button onclick="document.getElementById('sec-tools').scrollIntoView({behavior:'smooth'})"><span class="bi">🛠</span>Tools</button>
<button onclick="document.getElementById('sec-act').scrollIntoView({behavior:'smooth'})"><span class="bi">⚡</span>More</button>
</div>
<div class="ft"><p>Rusemeva · <a href="https://github.com/''' + REPO + '''">GitHub</a></p><p style="margin-top:3px">v8.5.1 · Menu upgrades · richer stats/search/timeline · Auto-refresh 30s</p></div>
</div>
<div class="mo" id="mo" onclick="if(event.target===this)clM()"><div class="md"><div class="mh"><h3 id="mt"></h3><button class="mc" onclick="clM()">&times;</button></div><div id="mb"></div></div></div>
<div class="cmd-overlay" id="cmdOverlay" onclick="if(event.target===this)closeCmd()">
<div class="cmd-box"><input class="cmd-input" id="cmdInput" placeholder="Ketik perintah atau cari RSM/run…" oninput="filterCmd()" onkeydown="cmdKey(event)">
<div class="cmd-list" id="cmdList"></div></div></div>
<script>
window.DASH = ''' + json.dumps({
        "generated": datetime.now(WIB).isoformat(),
            "build": "v8.5.1-upgrade",
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
            "orv_id": r.get("orv_id") or "",
            "source": r.get("source") or "",
        } for r in runs[:80]],
        "releases": [{
            "tag": r.get("tag"), "name": r.get("name"),
            "created": r.get("created"), "size": r.get("size") or 0,
        } for r in releases[:20]],
    }, default=str) + ''';
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
  return '<div class="fi" data-s="'+esc(sk(r))+'" data-rid="'+esc(r.databaseId||'')+'" data-orv="'+esc(r.orv_id||'')+'">'
    +'<span class="fi-icon">'+icoJs(sk(r)==='in_progress'?'':(r.conclusion||''))+'</span>'
    +'<span class="fi-time">'+agoJs(r.createdAt||'')+'</span>'
    +'<span class="fi-id"><code title="'+esc(r.databaseId||'')+'">'+esc(id)+'</code></span>'
    +'<span class="fi-name">'+esc(r.name||'')+'</span>'
    +'<span class="fi-status '+clsJs(sk(r)==='in_progress'?'':(r.conclusion||''))+'">'+esc(s)+'</span>'
    +' <a href="'+link+'" target="_blank" style="font-size:10px">↗</a></div>';
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
if(t==='keys'){h.textContent='⌨️ Keys';b.innerHTML='<div class="sh2"><div class="sk"><span class="ky">R</span> Soft-refresh</div><div class="sk"><span class="ky">D</span> Theme</div><div class="sk"><span class="ky">S</span> Search</div><div class="sk"><span class="ky">E</span> Export</div><div class="sk"><span class="ky">P</span> Command palette</div><div class="sk"><span class="ky">Esc</span> Close modal</div></div><div style="margin-top:8px;font-size:11px;color:var(--t2)">Fokus input/textarea = shortcut nonaktif.</div>'}
if(t==='api'){h.textContent='📚 API';b.innerHTML='<div style="font-size:11px;line-height:1.7"><b>Worker</b> <code>rusemeva.rusemeva-vault.workers.dev</code><br><code>GET /api/status</code> Status<br><code>POST /api/record</code> Record<br><code>GET /api/runs</code> Runs<br><code>GET /api/orv-map</code> RSM map<br><code>GET /rtcal?preset=</code> RT kalibrasi<br><br><b>Dashboard static</b><br><code>GET data.json</code> Live soft-refresh payload<br><code>GET index.html</code> Full page</div>'}
if(t==='about'){h.textContent='ℹ️ About';b.innerHTML='<div style="font-size:11px;line-height:1.7"><b>Rusemeva Dashboard</b> v8.5.1<br>Live GHA + Worker RSM map + Telegram delivery<br><br>Cost infra: ~$0 (GH free + CF Worker)<br>Repo: <a href="https://github.com/daudjoss/daudjoss-vault" target="_blank">daudjoss/daudjoss-vault</a><br>Site: <a href="https://daudjoss.github.io/daudjoss-vault/" target="_blank">gh-pages</a><br><br>Generated: <code>'+esc(D.generated||'—')+'</code></div>'}
if(t==='notes'){h.textContent='📝 Notes';b.innerHTML='<div><textarea class="note-area" id="noteArea" placeholder="Catatan lokal (tersimpan di browser)..."></textarea><div style="margin-top:6px"><button class="btn" onclick="saveNote()">Save</button> <button class="btn" onclick="clearNote()">Clear</button></div><div style="margin-top:6px;font-size:10px;color:var(--t2)">localStorage key: rusemeva_notes</div></div>';loadNote()}
if(t==='tags'){h.textContent='🏷 Tags';b.innerHTML='<div class="tag-input"><input type="text" id="tagInput" placeholder="Tag..."><button onclick="addTag()">Add</button></div><div id="tagList" style="margin-top:6px"></div><div style="margin-top:6px;font-size:10px;color:var(--t2)">Disimpan lokal di browser</div>';loadTags()}
if(t==='bookmarks'){h.textContent='🔖 Bookmarks';b.innerHTML='<div><div id="bookmarkList"></div><div style="margin-top:6px;display:flex;gap:4px;flex-wrap:wrap"><input type="text" id="bmTime" placeholder="02:15" style="width:60px;padding:4px;border-radius:4px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);font-size:11px"> <input type="text" id="bmNote" placeholder="Note / RSM-ID..." style="flex:1;min-width:120px;padding:4px;border-radius:4px;border:1px solid var(--brd);background:var(--bg3);color:var(--t1);font-size:11px"> <button class="btn" onclick="addBookmark()">Add</button></div></div>';loadBookmarks()}
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
}
if(t==='search'){h.textContent='🔍 Search';b.innerHTML='<div class="search-filters"><div class="search-filter"><label>Source</label><select id="srcFilter"><option value="All">All</option><option value="rusemeva-vault">Vault</option><option value="rusemeva-encode">Encode</option><option value="Trans7">Trans7</option><option value="SevenHub">SevenHub</option></select></div><div class="search-filter"><label>Status</label><select id="statFilter"><option value="All">All</option><option value="success">Success</option><option value="failure">Failed</option><option value="in_progress">Running</option><option value="cancelled">Cancelled</option></select></div><div class="search-filter"><label>Sort</label><select id="sortFilter"><option value="new">Newest</option><option value="old">Oldest</option></select></div></div><div style="margin-top:6px"><input class="si2" id="qAdv" placeholder="RSM-ID / run id / text..." style="width:100%;margin-bottom:6px" onkeydown="if(event.keyCode===13)advSearch()"><button class="btn" onclick="advSearch()">Search</button> <button class="btn" onclick="clearSearch()">Clear</button> <span id="searchCount" style="font-size:10px;color:var(--t2);margin-left:4px"></span></div><div id="searchResults" style="margin-top:8px;max-height:320px;overflow:auto"></div>'}
if(t==='export'){h.textContent='📥 Export';var n=filteredRows().length;b.innerHTML='<div class="export-opts"><div class="export-opt sel" onclick="expCSV()"><div class="export-opt-icon">📊</div><div class="export-opt-label">CSV</div></div><div class="export-opt" onclick="expJSON()"><div class="export-opt-icon">📄</div><div class="export-opt-label">JSON</div></div><div class="export-opt" onclick="expTXT()"><div class="export-opt-label">TXT</div></div></div><div style="margin-top:8px;font-size:10px;color:var(--t2)">'+n+' rows akan di-export (hormati filter search aktif). Data dari window.DASH.runs.</div>'}
if(t==='customize'){
  h.textContent='🎨 Customize';
  var keys=[['hideStats','Stats cards','.sg'],['hideHealth','Health','#sec-health'],['hideFeed','Live feed','#sec-feed'],['hideCharts','Charts & activity','#sec-week'],['hideStreak','Streak bar','.streak']];
  var html='<div>';
  keys.forEach(function(k){
    var on=localStorage.getItem('dash_'+k[0])!=='1';
    html+='<div class="opt"><div class="opt-label">'+k[1]+'</div><button class="opt-btn" data-k="'+k[0]+'" data-sel="'+k[2]+'" onclick="toggleCust(this)">'+(on?'ON':'OFF')+'</button></div>';
  });
  var compactOn=document.body.classList.contains('compact');
  html+='<div class="opt"><div class="opt-label">Compact mode (hide charts/gallery)</div><button class="opt-btn" onclick="toggleCompact()">'+(compactOn?'ON':'OFF')+'</button></div>';
  html+='</div><div style="margin-top:8px;font-size:10px;color:var(--t2)">Disimpan di localStorage · berlaku langsung. Theme: tekan D atau 🌓 di hero.</div>';
  b.innerHTML=html;
}
if(t==='help'){h.textContent='❓ Help';b.innerHTML='<div style="font-size:11px;line-height:1.7"><b>Mulai:</b><br>1. Lihat Recordings + filter ✅❌🔄<br>2. Soft-refresh 30s / tombol 🔄 di hero<br>3. Tools → Stats/Search/Export/Player<br>4. Themes & Customize (local)<br><br><b>RSM-ID</b> muncul kalau Worker map terisi (setelah record/encode link).<br><b>Storage</b> estimasi dari durasi release (file video di Telegram).<br><br><b>Shortcuts:</b> R refresh · D theme · S search · E export · Esc close</div>'}
if(t==='updates'){h.textContent='🆕 Updates';b.innerHTML='<div style="font-size:11px;line-height:1.6"><b>v8.5.1</b>:<br>• Stats: enc breakdown, cancelled, storage, ORV<br>• Search: sort + count + Enter + ⚖ compare<br>• Timeline: grouped by date + status counts<br>• Player: vault + encode sections<br>• Compare: cancel counts<br>• Export: filter count<br>• Customize: compact toggle<br><br><b>v8.5</b>:<br>• Last RSM card + storage story + 24h diff<br>• Deep link ?rsm= / ?run=<br>• Honest client health<br>• Command palette (P)<br>• Compact mode + saved views<br>• Compare 2 runs<br>• Export filtered<br><br><b>v8.4.2</b>:<br>• window.DASH + menus data-driven<br>• Storage est dari durasi (bukan 0.0 GB)<br>• Customize beneran (hide sections)<br>• Search/Export/Player/Compare live<br>• Soft-refresh sync DASH<br><br><b>v8.3</b>: hero, glass, mobile nav<br><b>v8.2</b>: audit feed/WIB/filters<br><b>v8.0</b>: All20 features</div>'}
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
  b.innerHTML=statBlock()+extra;
}
if(t==='share'){
  h.textContent='🔗 Share';
  var url='https://daudjoss.github.io/daudjoss-vault/';
  var latest=vaultRuns()[0];
  var rid=latest?(latest.orv_id||latest.databaseId):'';
  var runLink=latest?('https://github.com/daudjoss/daudjoss-vault/actions/runs/'+latest.databaseId):'';
  b.innerHTML='<div style="font-size:11px;line-height:1.7"><b>Dashboard</b><br><a id="shareUrl" href="'+url+'" target="_blank">'+url+'</a><br><button class="btn" style="margin-top:6px" id="shareCopyBtn">Copy link</button><br><br><b>Latest vault</b><br><code>'+esc(String(rid||'—'))+'</code><br>'
    +(runLink?'<a href="'+runLink+'" target="_blank">Open run ↗</a>':'')
    +'</div>';
  var btn=document.getElementById('shareCopyBtn');
  if(btn){btn.onclick=function(){navigator.clipboard.writeText(url).then(function(){btn.textContent='Copied';setTimeout(function(){btn.textContent='Copy link'},1200)}).catch(function(){prompt('Copy:',url)})}}
}
if(t==='comments'){h.textContent='💬 Comments';b.innerHTML='<div><div id="commentList"></div><div style="margin-top:6px"><textarea class="note-area" id="commentArea" placeholder="Komentar lokal..."></textarea><div style="margin-top:4px"><button class="btn" onclick="addComment()">Add</button></div></div><div style="margin-top:6px;font-size:10px;color:var(--t2)">localStorage only</div></div>';loadComments()}
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
if(t==='clock'){h.textContent='🕐 Clock';b.innerHTML='<div style="text-align:center;padding:20px"><div id="liveClock" style="font-size:36px;font-weight:700">--:--:--</div><div style="font-size:11px;color:var(--t2);margin-top:4px">WIB (Asia/Jakarta)</div></div>';if(window._clk)clearInterval(window._clk);window._clk=setInterval(function(){var el=document.getElementById('liveClock');if(el)el.textContent=new Date().toLocaleTimeString('en-GB',{timeZone:'Asia/Jakarta',hour12:false})},250);document.getElementById('liveClock').textContent=new Date().toLocaleTimeString('en-GB',{timeZone:'Asia/Jakarta',hour12:false})}
if(t==='weather'){h.textContent='🌤 Weather';b.innerHTML='<div style="text-align:center;padding:18px"><div style="font-size:42px;margin-bottom:8px">🌤</div><div id="wxBox" style="font-size:12px;color:var(--t2)">Memuat BMKG/Open-Meteo…</div></div>';fetch('https://api.open-meteo.com/v1/forecast?latitude=-6.2&longitude=106.8&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&timezone=Asia%2FJakarta').then(function(r){return r.json()}).then(function(j){var c=j.current||{};var box=document.getElementById('wxBox');if(!box)return;box.innerHTML='<div style="font-size:28px;font-weight:700;color:var(--t1)">'+(c.temperature_2m!=null?c.temperature_2m+'°C':'—')+'</div><div style="margin-top:4px">Jakarta · RH '+(c.relative_humidity_2m!=null?c.relative_humidity_2m+'%':'—')+' · Wind '+(c.wind_speed_10m!=null?c.wind_speed_10m+' km/h':'—')+'</div><div style="margin-top:6px;font-size:10px;color:var(--t2)">Open-Meteo · code '+(c.weather_code!=null?c.weather_code:'—')+'</div>'}).catch(function(){var box=document.getElementById('wxBox');if(box)box.textContent='Gagal fetch cuaca (network).';})}
if(t==='music'){h.textContent='🎵 Music';b.innerHTML='<div style="text-align:center;padding:18px"><div style="font-size:42px;margin-bottom:8px">🎵</div><div style="font-size:12px;color:var(--t2);line-height:1.5">Tidak ada stream music di pipeline Rusemeva.<br>Fokus: rekaman vault + encode HEVC + Telegram.</div></div>'}
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


document.addEventListener('keydown',function(e){if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return;if(e.key==='p'||e.key==='P'){e.preventDefault();openCmd();return}switch(e.key){case'r':location.reload();break;case'd':toggleTheme();break;case's':e.preventDefault();document.getElementById('q').focus();break;case'e':expCSV();break;case'Escape':clM();break}});
function agoJs(s){try{var d=Math.floor((Date.now()-new Date(s).getTime())/1000);if(d<60)return'baru';if(d<3600)return Math.floor(d/60)+'m';if(d<86400)return Math.floor(d/3600)+'j';return Math.floor(d/86400)+'h'}catch(e){return (s||'').slice(0,10)}}
function icoJs(c){return c==='success'?'✅':c==='failure'?'❌':c==='cancelled'?'⚪':'🔄'}
function clsJs(c){return c==='success'||c==='failure'||c==='cancelled'?c:'running'}
function statusKeyJs(r){var c=(r.conclusion||'').trim();if(c==='success'||c==='failure'||c==='cancelled')return c;var st=(r.status||'').trim();if(st==='in_progress'||st==='queued'||st==='waiting'||st==='pending'||st==='requested')return'in_progress';return c||st||'?';}
function displayStatusJs(r){var c=(r.conclusion||'').trim();if(c)return c;var st=(r.status||'').trim();if(st==='in_progress'||st==='queued'||st==='waiting'||st==='pending'||st==='requested')return'in_progress';return st||'?';}
function esc(s){return String(s||'').replace(/[&<>"']/g,function(ch){return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])})}
function buildFeedHtml(runs){var list=(runs||[]).slice();var pref=list.filter(function(r){return r.name==='rusemeva-vault'||r.name==='rusemeva-encode'});var skip={'Update Dashboard':1,'pages build and deployment':1,'ci-policy':1,'cleanup-temp':1};if(pref.length<8){list.forEach(function(r){if(pref.length>=15)return;if(skip[r.name])return;if(pref.indexOf(r)>=0)return;pref.push(r)})}return pref.slice(0,15).map(function(r){var sk=statusKeyJs(r);var c=sk==='in_progress'?'running':clsJs(r.conclusion);var s=displayStatusJs(r);var rid=String(r.databaseId||'');var orv=(r.orv_id||'').trim();var idshow=orv||rid;return '<div class="fi" data-s="'+esc(sk)+'" data-rid="'+esc(rid)+'" data-orv="'+esc(orv)+'"><span class="fi-icon">'+icoJs(sk==='in_progress'?'':r.conclusion)+'</span><span class="fi-time">'+agoJs(r.createdAt)+'</span><span class="fi-id"><code title="'+esc(rid)+'">'+esc(idshow)+'</code></span><span class="fi-name">'+esc(r.name||'')+'</span><span class="fi-status '+c+'">'+esc(s)+'</span><button data-cmp="rid" style="font-size:9px;padding:1px 4px;border:1px solid var(--brd);border-radius:4px;background:var(--bg3);color:var(--t2);cursor:pointer;margin-left:4px">⚖</button></div>';}).join('')}
function buildRecRows(runs){return (runs||[]).filter(function(r){return r.name==='rusemeva-vault'}).slice(0,25).map(function(r){var sk=statusKeyJs(r);var c=sk==='in_progress'?'running':clsJs(r.conclusion);var s=displayStatusJs(r);var rid=String(r.databaseId||'');var orv=(r.orv_id||'').trim();var idcell=orv?'<code title="'+esc(rid)+'">'+esc(orv)+'</code>':'<code>'+esc(rid)+'</code>';var q=(rid+' '+orv+' '+s).toLowerCase();return '<tr class="r-'+c+'" data-s="'+esc(sk)+'" data-q="'+esc(q)+'" data-rid="'+esc(rid)+'" data-orv="'+esc(orv)+'"><td>'+icoJs(sk==='in_progress'?'':r.conclusion)+'</td><td>'+idcell+'</td><td>'+agoJs(r.createdAt)+'</td><td><span class="b b-'+c+'">'+esc(s)+'</span></td><td><a href="https://github.com/daudjoss/daudjoss-vault/actions/runs/'+esc(rid)+'" target="_blank">↗</a></td></tr>';}).join('')}
function buildEncRows(runs){return (runs||[]).filter(function(r){return r.name==='rusemeva-encode'}).slice(0,20).map(function(r){var sk=statusKeyJs(r);var c=sk==='in_progress'?'running':clsJs(r.conclusion);var s=displayStatusJs(r);var rid=String(r.databaseId||'');var orv=(r.orv_id||'').trim();var idcell=orv?'<code title="'+esc(rid)+'">'+esc(orv)+'</code>':'<code>'+esc(rid)+'</code>';return '<tr data-s="'+esc(sk)+'" data-rid="'+esc(rid)+'" data-orv="'+esc(orv)+'"><td>'+icoJs(sk==='in_progress'?'':r.conclusion)+'</td><td>'+idcell+'</td><td>'+agoJs(r.createdAt)+'</td><td><span class="b b-'+c+'">'+esc(s)+'</span></td><td><a href="https://github.com/daudjoss/daudjoss-vault/actions/runs/'+esc(rid)+'" target="_blank">↗</a></td></tr>';}).join('')}
function applyOrvMap(data){var map=data.orv_map||[];if(!map.length)return data;var by={};map.forEach(function(x){if(x&&x.run_id&&x.orv_id)by[String(x.run_id)]={orv_id:x.orv_id,source:x.source||''}}); (data.runs||[]).forEach(function(r){var m=by[String(r.databaseId)];if(m){r.orv_id=m.orv_id;if(m.source)r.source=m.source}});return data}
function updateLiveUI(data){if(!data||!data.runs)return;data=applyOrvMap(data);window.DASH=window.DASH||{};window.DASH.generated=data.generated||window.DASH.generated;if(data.stats){window.DASH.stats=Object.assign({},window.DASH.stats||{},data.stats);if(data.stats.hours)window.DASH.hours=data.stats.hours;if(data.stats.days)window.DASH.days=data.stats.days;if(data.stats.daily)window.DASH.daily=data.stats.daily;if(data.stats.insights)window.DASH.insights=data.stats.insights;if(data.stats.predictions)window.DASH.predictions=data.stats.predictions;}window.DASH.runs=data.runs;if(data.releases)window.DASH.releases=data.releases;var feed=document.querySelector('#sec-feed .feed');if(feed){feed.innerHTML=buildFeedHtml(data.runs);feed.querySelectorAll('[data-cmp]').forEach(function(b){b.onclick=function(){toggleCmpPick(this.getAttribute('data-cmp'))}})};var rt=document.querySelector('#rt tbody');if(rt){var rows=buildRecRows(data.runs);if(rows)rt.innerHTML=rows}var encBody=document.querySelector('#et tbody');if(encBody){var erows=buildEncRows(data.runs);if(erows)encBody.innerHTML=erows}if(data.stats){var st=data.stats;function setTxt(id,val){var el=document.getElementById(id);if(el)el.textContent=val}if(st.total!=null)setTxt('st-total',st.total);if(st.success!=null)setTxt('st-success',st.success);if(st.failed!=null)setTxt('st-failed',st.failed);if(st.rate!=null)setTxt('st-rate',st.rate+'%');if(st.enc!=null)setTxt('st-enc',st.enc);if(st.today!=null)setTxt('st-today',st.today);if(st.streak!=null)setTxt('st-streak',st.streak);var mon=document.querySelectorAll('.monitor-value');if(mon&&mon[2])mon[2].textContent=(st.running||0)+' running';var health=document.querySelector('#sec-health .sh span');if(health&&data.generated){try{health.textContent=new Date(data.generated).toLocaleString('sv-SE',{timeZone:'Asia/Jakarta'}).replace('T',' ')+' WIB'}catch(e){}}}var q=document.getElementById('q');if(q&&q.value)srch();var onFb=document.querySelector('.fb.on');if(onFb){var key=onFb.getAttribute('data-f')||'all';filt(key,onFb)}renderHero();checkHealth();applyDeepLink();}

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
function renderHero(){var r=document.getElementById('hero-rsm');if(r)r.innerHTML=lastRsmHtml();
  var s=document.getElementById('hero-storage');if(s)s.innerHTML=storageStoryHtml();
  var d=document.getElementById('hero-diff');if(d)d.innerHTML=diff24Html();}

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
  renderSavedViews();renderHero();checkHealth();applyDeepLink();
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
  {cat:'Tools',label:'Themes',act:"toggleTheme()"},
  {cat:'Tools',label:'Customize',act:"showM('customize')"},
  {cat:'Tools',label:'Player',act:"showM('player')"},
  {cat:'View',label:'Compact toggle',act:"toggleCompact()"},
  {cat:'View',label:'Save view',act:"saveCurrentView()"},
  {cat:'View',label:'Refresh',act:"softRefresh().then(function(ok){if(!ok)location.reload()})"},
  {cat:'Help',label:'Keys',act:"showM('keys')"},
  {cat:'Help',label:'About',act:"showM('about')"},
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
  if(e.key==='ArrowDown'){e.preventDefault();cmdSel++;filterCmd();}
  if(e.key==='ArrowUp'){e.preventDefault();cmdSel=Math.max(0,cmdSel-1);filterCmd();}
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
            "build": "v8.5.1-upgrade",
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
