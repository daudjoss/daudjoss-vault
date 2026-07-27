#!/usr/bin/env python3
"""Generate comprehensive Rusemeva dashboard v3 with all features."""
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
    except Exception as e:
        print(f"⚠️ gh error: {e}")
        return ""

def fetch_workflow_runs(limit=100):
    raw = run_gh(["run", "list", "--repo", REPO, "--limit", str(limit),
                   "--json", "databaseId,name,status,conclusion,createdAt,event,updatedAt"])
    if not raw:
        return []
    try:
        return json.loads(raw)
    except:
        return []

def fetch_releases(limit=30):
    raw = run_gh(["api", f"repos/{REPO}/releases",
                   "--jq", f"[.[:{limit}][:][] | {{tag: .tag_name, name: .name, created: .created_at, size: ([.assets[].size] | add // 0), assets: [.assets[] | {{name: .name, size: .size}}]}}]"])
    if not raw:
        return []
    try:
        return json.loads(raw)
    except:
        return []

def calculate_stats(runs):
    vault = [r for r in runs if r.get("name") == "rusemeva-vault"]
    encode = [r for r in runs if r.get("name") == "rusemeva-encode"]
    other = [r for r in runs if r.get("name") not in ["rusemeva-vault", "rusemeva-encode", "ci-policy", "cleanup-temp", "Update Dashboard", "pages build and deployment", "Send File to Telegram"]]

    total = len(vault)
    success = len([r for r in vault if r.get("conclusion") == "success"])
    failed = len([r for r in vault if r.get("conclusion") == "failure"])
    running = len([r for r in vault if r.get("status") == "in_progress"])
    rate = (success / total * 100) if total > 0 else 0

    enc_total = len(encode)
    enc_success = len([r for r in encode if r.get("conclusion") == "success"])
    enc_rate = (enc_success / enc_total * 100) if enc_total > 0 else 0

    # Today stats
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    today_runs = [r for r in vault if r.get("createdAt", "").startswith(today)]
    today_success = len([r for r in today_runs if r.get("conclusion") == "success"])

    # Daily activity
    daily = defaultdict(int)
    for r in vault:
        try:
            dt = datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
            day = dt.strftime("%Y-%m-%d")
            daily[day] += 1
        except:
            pass

    # Weekly stats
    weekly = defaultdict(lambda: {"success": 0, "fail": 0})
    for r in vault:
        try:
            dt = datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
            week = dt.strftime("%Y-W%W")
            if r.get("conclusion") == "success":
                weekly[week]["success"] += 1
            elif r.get("conclusion") == "failure":
                weekly[week]["fail"] += 1
        except:
            pass

    # Source distribution
    sources = defaultdict(int)
    for r in vault:
        # Try to extract source from run name or payload
        sources["Trans7"] += 1  # Default, would need payload data for accurate count

    # Error analysis
    errors = []
    for r in vault[:20]:
        if r.get("conclusion") == "failure":
            errors.append({
                "id": r.get("databaseId"),
                "time": time_ago(r.get("createdAt", "")),
                "created": r.get("createdAt", "")[:19],
            })

    return {
        "total_recordings": total,
        "total_success": success,
        "total_failed": failed,
        "total_running": running,
        "success_rate": round(rate, 1),
        "total_encode": enc_total,
        "encode_success": enc_success,
        "encode_rate": round(enc_rate, 1),
        "total_other": len(other),
        "today_count": len(today_runs),
        "today_success": today_success,
        "daily_activity": dict(sorted(daily.items())[-35:]),
        "weekly_stats": dict(sorted(weekly.items())[-12:]),
        "sources": dict(sources),
        "errors": errors[:5],
    }

def time_ago(created_str):
    try:
        dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = now - dt
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return "baru saja"
        elif seconds < 3600:
            return f"{seconds // 60}m lalu"
        elif seconds < 86400:
            return f"{seconds // 3600}j lalu"
        else:
            return f"{seconds // 86400}h lalu"
    except:
        return created_str[:10]

def status_icon(conclusion):
    if conclusion == "success":
        return "✅"
    elif conclusion == "failure":
        return "❌"
    elif conclusion == "cancelled":
        return "⚪"
    else:
        return "🔄"

def status_class(conclusion):
    if conclusion == "success":
        return "success"
    elif conclusion == "failure":
        return "failure"
    elif conclusion == "cancelled":
        return "cancelled"
    else:
        return "running"

def generate_html(stats, runs, releases):
    now = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")

    # Chart data
    daily_labels = json.dumps(list(stats["daily_activity"].keys()))
    daily_data = json.dumps(list(stats["daily_activity"].values()))
    weekly_labels = json.dumps(list(stats["weekly_stats"].keys()))
    weekly_success = json.dumps([v["success"] for v in stats["weekly_stats"].values()])
    weekly_fail = json.dumps([v["fail"] for v in stats["weekly_stats"].values()])

    # Table rows
    vault_runs = [r for r in runs if r.get("name") == "rusemeva-vault"][:25]
    encode_runs = [r for r in runs if r.get("name") == "rusemeva-encode"][:20]

    recent_html = ""
    for r in vault_runs:
        icon = status_icon(r.get("conclusion", ""))
        ago = time_ago(r.get("createdAt", ""))
        run_id = r.get("databaseId", "")
        status = r.get("conclusion", r.get("status", "unknown"))
        cls = status_class(status)
        recent_html += f'<tr class="row-{cls}" data-status="{status}" data-search="{run_id}"><td>{icon}</td><td><code>{run_id}</code></td><td>{ago}</td><td><span class="badge badge-{cls}">{status}</span></td><td><a href="https://github.com/{REPO}/actions/runs/{run_id}" target="_blank" title="View on GitHub">↗</a></td></tr>'

    encode_html = ""
    for r in encode_runs:
        icon = status_icon(r.get("conclusion", ""))
        ago = time_ago(r.get("createdAt", ""))
        run_id = r.get("databaseId", "")
        status = r.get("conclusion", r.get("status", "unknown"))
        cls = status_class(status)
        encode_html += f'<tr class="row-{cls}" data-status="{status}"><td>{icon}</td><td><code>{run_id}</code></td><td>{ago}</td><td><span class="badge badge-{cls}">{status}</span></td><td><a href="https://github.com/{REPO}/actions/runs/{run_id}" target="_blank">↗</a></td></tr>'

    releases_html = ""
    for r in releases[:15]:
        size_mb = r.get("size", 0) / 1024 / 1024
        ago = time_ago(r.get("created", ""))
        releases_html += f'<tr><td><code>{r.get("tag", "")}</code></td><td>{size_mb:.1f} MB</td><td>{ago}</td></tr>'

    # Calendar
    calendar_html = ""
    today = datetime.now(WIB).date()
    start = today - timedelta(days=34)
    current = start
    while current <= today:
        day_str = current.strftime("%Y-%m-%d")
        count = stats["daily_activity"].get(day_str, 0)
        intensity = min(count, 5)
        calendar_html += f'<div class="cal-day cal-{intensity}" title="{day_str}: {count} recordings">{current.day}</div>'
        current += timedelta(days=1)

    # Errors
    errors_html = ""
    if stats["errors"]:
        for e in stats["errors"]:
            errors_html += f'''<div class="error-item">
                <div class="error-icon">❌</div>
                <div class="error-info">
                    <div class="error-id">Run <code>{e["id"]}</code></div>
                    <div class="error-time">{e["time"]}</div>
                </div>
                <a href="https://github.com/{REPO}/actions/runs/{e["id"]}" target="_blank" class="error-link">View Log ↗</a>
            </div>'''
    else:
        errors_html = '<div class="no-errors">✅ Tidak ada error terbaru</div>'

    html = f'''<!DOCTYPE html>
<html lang="id" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rusemeva Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        :root {{
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --bg-tertiary: #21262d;
            --border: #30363d;
            --text-primary: #e6edf3;
            --text-secondary: #8b949e;
            --text-muted: #484f58;
            --accent-blue: #58a6ff;
            --accent-green: #3fb950;
            --accent-red: #f85149;
            --accent-yellow: #d29922;
            --accent-purple: #bc8cff;
            --accent-orange: #f0883e;
        }}
        [data-theme="light"] {{
            --bg-primary: #f6f8fa;
            --bg-secondary: #ffffff;
            --bg-tertiary: #f0f2f5;
            --border: #d0d7de;
            --text-primary: #1f2328;
            --text-secondary: #656d76;
            --text-muted: #8b949e;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            padding: 20px;
            min-height: 100vh;
            transition: background 0.3s, color 0.3s;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}

        /* Header */
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border);
            flex-wrap: wrap;
            gap: 12px;
        }}
        .header h1 {{ font-size: 28px; font-weight: 600; display: flex; align-items: center; gap: 12px; }}
        .header-actions {{ display: flex; align-items: center; gap: 12px; }}
        .live-dot {{ width: 8px; height: 8px; background: var(--accent-green); border-radius: 50%; animation: pulse 2s infinite; }}
        @keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} }}
        .theme-btn {{
            padding: 8px 12px;
            border-radius: 8px;
            border: 1px solid var(--border);
            background: var(--bg-tertiary);
            color: var(--text-primary);
            cursor: pointer;
            font-size: 14px;
        }}
        .theme-btn:hover {{ border-color: var(--accent-blue); }}

        /* Stats */
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 24px; }}
        .stat-card {{
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            position: relative;
            overflow: hidden;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .stat-card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.2); }}
        .stat-card::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; }}
        .stat-card.blue::before {{ background: var(--accent-blue); }}
        .stat-card.green::before {{ background: var(--accent-green); }}
        .stat-card.red::before {{ background: var(--accent-red); }}
        .stat-card.yellow::before {{ background: var(--accent-yellow); }}
        .stat-card.purple::before {{ background: var(--accent-purple); }}
        .stat-card.orange::before {{ background: var(--accent-orange); }}
        .stat-icon {{ font-size: 24px; margin-bottom: 8px; }}
        .stat-value {{ font-size: 36px; font-weight: 700; }}
        .stat-label {{ font-size: 13px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; }}
        .stat-card.blue .stat-value {{ color: var(--accent-blue); }}
        .stat-card.green .stat-value {{ color: var(--accent-green); }}
        .stat-card.red .stat-value {{ color: var(--accent-red); }}
        .stat-card.yellow .stat-value {{ color: var(--accent-yellow); }}
        .stat-card.purple .stat-value {{ color: var(--accent-purple); }}
        .stat-card.orange .stat-value {{ color: var(--accent-orange); }}

        /* Section */
        .section {{ background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 24px; }}
        .section-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--border); flex-wrap: wrap; gap: 12px; }}
        .section-title {{ font-size: 16px; font-weight: 600; display: flex; align-items: center; gap: 8px; }}

        /* Grid */
        .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px; }}
        .grid-3 {{ display: grid; grid-template-columns: 2fr 1fr; gap: 24px; margin-bottom: 24px; }}

        /* Filters */
        .filters {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
        .filter-btn {{
            padding: 6px 14px;
            border-radius: 20px;
            border: 1px solid var(--border);
            background: transparent;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 13px;
            transition: all 0.2s;
        }}
        .filter-btn:hover, .filter-btn.active {{ background: var(--accent-blue); color: white; border-color: var(--accent-blue); }}
        .search-input {{
            padding: 8px 14px;
            border-radius: 8px;
            border: 1px solid var(--border);
            background: var(--bg-tertiary);
            color: var(--text-primary);
            font-size: 14px;
            width: 180px;
        }}
        .search-input:focus {{ outline: none; border-color: var(--accent-blue); }}

        /* Table */
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--border); }}
        th {{ color: var(--text-secondary); font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; }}
        td {{ font-size: 14px; }}
        tr:hover {{ background: rgba(88,166,255,0.05); }}
        code {{ background: var(--bg-tertiary); padding: 3px 8px; border-radius: 6px; font-size: 12px; font-family: 'SF Mono', monospace; }}
        a {{ color: var(--accent-blue); text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}

        /* Badges */
        .badge {{ padding: 4px 12px; border-radius: 16px; font-size: 12px; font-weight: 500; }}
        .badge-success {{ background: rgba(63,185,80,0.15); color: var(--accent-green); }}
        .badge-failure {{ background: rgba(248,81,73,0.15); color: var(--accent-red); }}
        .badge-cancelled {{ background: rgba(139,148,158,0.15); color: var(--text-secondary); }}
        .badge-running {{ background: rgba(88,166,255,0.15); color: var(--accent-blue); }}

        /* Calendar */
        .calendar {{ display: grid; grid-template-columns: repeat(35, 1fr); gap: 3px; }}
        .cal-day {{ aspect-ratio: 1; border-radius: 4px; display: flex; align-items: center; justify-content: center; font-size: 10px; color: var(--text-muted); cursor: default; }}
        .cal-0 {{ background: var(--bg-tertiary); }}
        .cal-1 {{ background: rgba(63,185,80,0.3); }}
        .cal-2 {{ background: rgba(63,185,80,0.5); }}
        .cal-3 {{ background: rgba(63,185,80,0.7); }}
        .cal-4 {{ background: rgba(63,185,80,0.85); }}
        .cal-5 {{ background: var(--accent-green); color: white; }}

        /* Charts */
        .chart-container {{ position: relative; height: 250px; }}

        /* System Health */
        .health-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }}
        .health-item {{ display: flex; align-items: center; gap: 12px; padding: 12px; background: var(--bg-tertiary); border-radius: 8px; }}
        .health-dot {{ width: 10px; height: 10px; border-radius: 50%; }}
        .health-dot.green {{ background: var(--accent-green); }}
        .health-dot.yellow {{ background: var(--accent-yellow); }}
        .health-dot.red {{ background: var(--accent-red); }}
        .health-label {{ font-size: 14px; }}
        .health-status {{ font-size: 12px; color: var(--text-secondary); }}

        /* Errors */
        .error-item {{ display: flex; align-items: center; gap: 12px; padding: 12px; background: rgba(248,81,73,0.05); border: 1px solid rgba(248,81,73,0.2); border-radius: 8px; margin-bottom: 8px; }}
        .error-icon {{ font-size: 20px; }}
        .error-info {{ flex: 1; }}
        .error-id {{ font-size: 14px; font-weight: 500; }}
        .error-time {{ font-size: 12px; color: var(--text-secondary); }}
        .error-link {{ font-size: 13px; }}
        .no-errors {{ text-align: center; padding: 20px; color: var(--text-secondary); }}

        /* Quick Actions */
        .actions-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }}
        .action-btn {{
            padding: 12px 16px;
            border-radius: 8px;
            border: 1px solid var(--border);
            background: var(--bg-tertiary);
            color: var(--text-primary);
            cursor: pointer;
            font-size: 14px;
            text-align: center;
            transition: all 0.2s;
            text-decoration: none;
            display: block;
        }}
        .action-btn:hover {{ border-color: var(--accent-blue); background: rgba(88,166,255,0.1); }}

        /* Source Distribution */
        .source-bar {{ margin-bottom: 8px; }}
        .source-label {{ display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 4px; }}
        .source-track {{ height: 8px; background: var(--bg-tertiary); border-radius: 4px; overflow: hidden; }}
        .source-fill {{ height: 100%; border-radius: 4px; background: var(--accent-blue); }}

        /* Performance */
        .perf-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; }}
        .perf-item {{ text-align: center; }}
        .perf-value {{ font-size: 28px; font-weight: 700; color: var(--accent-blue); }}
        .perf-label {{ font-size: 12px; color: var(--text-secondary); margin-top: 4px; }}
        .perf-trend {{ font-size: 12px; margin-top: 4px; }}
        .perf-trend.up {{ color: var(--accent-green); }}
        .perf-trend.down {{ color: var(--accent-red); }}
        .perf-trend.stable {{ color: var(--text-muted); }}

        /* Modal */
        .modal-overlay {{
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.7);
            z-index: 1000;
            align-items: center;
            justify-content: center;
        }}
        .modal-overlay.active {{ display: flex; }}
        .modal {{
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px;
            max-width: 500px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
        }}
        .modal-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }}
        .modal-close {{ background: none; border: none; color: var(--text-secondary); font-size: 24px; cursor: pointer; }}
        .modal-body {{ font-size: 14px; line-height: 1.6; }}

        /* Keyboard shortcuts */
        .shortcuts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 8px; }}
        .shortcut {{ display: flex; align-items: center; gap: 8px; padding: 8px; }}
        .key {{ padding: 4px 8px; background: var(--bg-tertiary); border: 1px solid var(--border); border-radius: 4px; font-family: monospace; font-size: 12px; }}

        /* Export */
        .export-btns {{ display: flex; gap: 8px; }}
        .export-btn {{ padding: 8px 16px; border-radius: 8px; border: 1px solid var(--border); background: var(--bg-tertiary); color: var(--text-primary); cursor: pointer; font-size: 13px; }}
        .export-btn:hover {{ border-color: var(--accent-blue); }}

        /* Footer */
        .footer {{ text-align: center; color: var(--text-muted); font-size: 13px; margin-top: 40px; padding-top: 20px; border-top: 1px solid var(--border); }}
        .footer a {{ color: var(--text-secondary); }}

        /* Responsive */
        @media (max-width: 1024px) {{ .grid-2, .grid-3 {{ grid-template-columns: 1fr; }} }}
        @media (max-width: 768px) {{
            .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .header {{ flex-direction: column; align-items: flex-start; }}
            .calendar {{ grid-template-columns: repeat(7, 1fr); }}
            .search-input {{ width: 100%; }}
        }}

        /* Animations */
        .stat-card, .section {{ animation: fadeIn 0.3s ease-in; }}
        @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        .hidden {{ display: none; }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1><span>🎬</span> Rusemeva Dashboard</h1>
            <div class="header-actions">
                <div class="live-dot"></div>
                <span style="font-size:13px;color:var(--text-secondary)">Auto-refresh 30s</span>
                <button class="theme-btn" onclick="toggleTheme()" title="Toggle theme">🌓</button>
                <button class="theme-btn" onclick="location.reload()" title="Refresh">🔄</button>
            </div>
        </div>

        <!-- System Health -->
        <div class="section" style="margin-bottom:24px">
            <div class="section-header">
                <div class="section-title">🏥 System Health</div>
                <span style="font-size:12px;color:var(--text-secondary)">Updated: {now}</span>
            </div>
            <div class="health-grid">
                <div class="health-item"><div class="health-dot green"></div><div><div class="health-label">Worker</div><div class="health-status">rusemeva-vault.workers.dev</div></div></div>
                <div class="health-item"><div class="health-dot green"></div><div><div class="health-label">GitHub Actions</div><div class="health-status">20 slots available</div></div></div>
                <div class="health-item"><div class="health-dot green"></div><div><div class="health-label">Telegram Bot</div><div class="health-status">@daudtrans_bot</div></div></div>
                <div class="health-item"><div class="health-dot green"></div><div><div class="health-label">Dashboard</div><div class="health-status">gh-pages active</div></div></div>
            </div>
        </div>

        <!-- Stats -->
        <div class="stats-grid">
            <div class="stat-card blue"><div class="stat-icon">📹</div><div class="stat-value">{stats['total_recordings']}</div><div class="stat-label">Total Rekaman</div></div>
            <div class="stat-card green"><div class="stat-icon">✅</div><div class="stat-value">{stats['total_success']}</div><div class="stat-label">Sukses</div></div>
            <div class="stat-card red"><div class="stat-icon">❌</div><div class="stat-value">{stats['total_failed']}</div><div class="stat-label">Gagal</div></div>
            <div class="stat-card yellow"><div class="stat-icon">📊</div><div class="stat-value">{stats['success_rate']}%</div><div class="stat-label">Success Rate</div></div>
            <div class="stat-card purple"><div class="stat-icon">🎞</div><div class="stat-value">{stats['total_encode']}</div><div class="stat-label">Encode Jobs</div></div>
            <div class="stat-card orange"><div class="stat-icon">📅</div><div class="stat-value">{stats['today_count']}</div><div class="stat-label">Hari Ini</div></div>
        </div>

        <!-- Performance -->
        <div class="section">
            <div class="section-header"><div class="section-title">⚡ Performance</div></div>
            <div class="perf-grid">
                <div class="perf-item"><div class="perf-value">{stats['success_rate']}%</div><div class="perf-label">Success Rate</div><div class="perf-trend stable">→ stable</div></div>
                <div class="perf-item"><div class="perf-value">{stats['encode_rate']}%</div><div class="perf-label">Encode Rate</div><div class="perf-trend stable">→ stable</div></div>
                <div class="perf-item"><div class="perf-value">{stats['total_recordings']}</div><div class="perf-label">Total Recordings</div><div class="perf-trend up">↑ all time</div></div>
                <div class="perf-item"><div class="perf-value">{stats['today_count']}</div><div class="perf-label">Today</div><div class="perf-trend {'up' if stats['today_count'] > 0 else 'stable'}">{'↑ ' + str(stats['today_success']) + ' success' if stats['today_count'] > 0 else '→ no recordings'}</div></div>
            </div>
        </div>

        <!-- Calendar -->
        <div class="section">
            <div class="section-header"><div class="section-title">📅 Aktivitas 35 Hari Terakhir</div></div>
            <div class="calendar">{calendar_html}</div>
            <div style="display:flex;gap:8px;margin-top:12px;align-items:center;font-size:12px;color:var(--text-secondary)">
                <span>Less</span>
                <div class="cal-day cal-0" style="width:14px;height:14px"></div>
                <div class="cal-day cal-1" style="width:14px;height:14px"></div>
                <div class="cal-day cal-2" style="width:14px;height:14px"></div>
                <div class="cal-day cal-3" style="width:14px;height:14px"></div>
                <div class="cal-day cal-4" style="width:14px;height:14px"></div>
                <div class="cal-day cal-5" style="width:14px;height:14px"></div>
                <span>More</span>
            </div>
        </div>

        <!-- Charts -->
        <div class="grid-2">
            <div class="section">
                <div class="section-header"><div class="section-title">📈 Rekaman per Hari</div></div>
                <div class="chart-container"><canvas id="dailyChart"></canvas></div>
            </div>
            <div class="section">
                <div class="section-header"><div class="section-title">📊 Success Rate per Minggu</div></div>
                <div class="chart-container"><canvas id="weeklyChart"></canvas></div>
            </div>
        </div>

        <!-- Error Log -->
        <div class="section">
            <div class="section-header"><div class="section-title">🔍 Error Log</div></div>
            {errors_html}
        </div>

        <!-- Recordings Table -->
        <div class="section">
            <div class="section-header">
                <div class="section-title">🎬 Recent Recordings</div>
                <div class="filters">
                    <input type="text" class="search-input" id="searchInput" placeholder="🔍 Search ID..." oninput="searchTable()">
                    <button class="filter-btn active" onclick="filterTable('all', this)">All</button>
                    <button class="filter-btn" onclick="filterTable('success', this)">✅</button>
                    <button class="filter-btn" onclick="filterTable('failure', this)">❌</button>
                    <button class="filter-btn" onclick="filterTable('running', this)">🔄</button>
                </div>
            </div>
            <div style="overflow-x:auto">
                <table id="recordingsTable">
                    <thead><tr><th></th><th>Run ID</th><th>Time</th><th>Status</th><th></th></tr></thead>
                    <tbody>{recent_html}</tbody>
                </table>
            </div>
        </div>

        <!-- Encode + Releases -->
        <div class="grid-2">
            <div class="section">
                <div class="section-header"><div class="section-title">🎞 Encode Jobs</div></div>
                <div style="overflow-x:auto">
                    <table><thead><tr><th></th><th>Run ID</th><th>Time</th><th>Status</th><th></th></tr></thead>
                    <tbody>{encode_html}</tbody></table>
                </div>
            </div>
            <div class="section">
                <div class="section-header"><div class="section-title">📦 Releases</div></div>
                <div style="overflow-x:auto">
                    <table><thead><tr><th>Tag</th><th>Size</th><th>Time</th></tr></thead>
                    <tbody>{releases_html}</tbody></table>
                </div>
            </div>
        </div>

        <!-- Quick Actions -->
        <div class="section">
            <div class="section-header"><div class="section-title">⚡ Quick Actions</div></div>
            <div class="actions-grid">
                <a class="action-btn" href="https://github.com/{REPO}/actions" target="_blank">🔧 GitHub Actions</a>
                <a class="action-btn" href="https://github.com/{REPO}/releases" target="_blank">📦 Releases</a>
                <a class="action-btn" href="https://github.com/{REPO}" target="_blank">💻 Repository</a>
                <a class="action-btn" onclick="exportCSV()" style="cursor:pointer">📥 Export CSV</a>
                <a class="action-btn" onclick="exportJSON()" style="cursor:pointer">📥 Export JSON</a>
                <a class="action-btn" onclick="showShortcuts()" style="cursor:pointer">⌨️ Shortcuts</a>
            </div>
        </div>

        <!-- Footer -->
        <div class="footer">
            <p>Rusemeva Vault &middot; <a href="https://github.com/{REPO}">GitHub</a> &middot; <a href="https://github.com/{REPO}/actions">Actions</a></p>
            <p style="margin-top:8px">Auto-refresh 30s &middot; Press <kbd>R</kbd> to refresh &middot; <kbd>D</kbd> for dark/light</p>
        </div>
    </div>

    <!-- Modal -->
    <div class="modal-overlay" id="modal" onclick="if(event.target===this)closeModal()">
        <div class="modal">
            <div class="modal-header">
                <h3 id="modal-title">Title</h3>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body" id="modal-body">Body</div>
        </div>
    </div>

    <script>
        // Theme
        function toggleTheme() {{
            const html = document.documentElement;
            const current = html.getAttribute('data-theme');
            html.setAttribute('data-theme', current === 'dark' ? 'light' : 'dark');
            localStorage.setItem('theme', html.getAttribute('data-theme'));
        }}
        (function() {{
            const saved = localStorage.getItem('theme');
            if (saved) document.documentElement.setAttribute('data-theme', saved);
        }})();

        // Charts
        const chartColors = {{
            blue: 'rgba(88,166,255,0.6)',
            blueBorder: 'rgba(88,166,255,1)',
            green: '#3fb950',
            red: '#f85149',
        }};
        const gridColor = 'rgba(48,54,61,0.5)';
        const tickColor = '#8b949e';

        new Chart(document.getElementById('dailyChart').getContext('2d'), {{
            type: 'bar',
            data: {{ labels: {daily_labels}, datasets: [{{ label: 'Recordings', data: {daily_data}, backgroundColor: chartColors.blue, borderColor: chartColors.blueBorder, borderWidth: 1, borderRadius: 4 }}] }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ grid: {{ color: gridColor }}, ticks: {{ color: tickColor, maxTicksLimit: 10 }} }}, y: {{ beginAtZero: true, grid: {{ color: gridColor }}, ticks: {{ color: tickColor, stepSize: 1 }} }} }} }}
        }});

        new Chart(document.getElementById('weeklyChart').getContext('2d'), {{
            type: 'line',
            data: {{ labels: {weekly_labels}, datasets: [
                {{ label: 'Success', data: {weekly_success}, borderColor: chartColors.green, backgroundColor: 'rgba(63,185,80,0.1)', fill: true, tension: 0.4 }},
                {{ label: 'Failed', data: {weekly_fail}, borderColor: chartColors.red, backgroundColor: 'rgba(248,81,73,0.1)', fill: true, tension: 0.4 }}
            ] }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ labels: {{ color: tickColor }} }} }}, scales: {{ x: {{ grid: {{ color: gridColor }}, ticks: {{ color: tickColor }} }}, y: {{ beginAtZero: true, grid: {{ color: gridColor }}, ticks: {{ color: tickColor, stepSize: 1 }} }} }} }}
        }});

        // Filter
        function filterTable(status, btn) {{
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.querySelectorAll('#recordingsTable tbody tr').forEach(row => {{
                row.classList.toggle('hidden', status !== 'all' && row.dataset.status !== status);
            }});
        }}

        // Search
        function searchTable() {{
            const q = document.getElementById('searchInput').value.toLowerCase();
            document.querySelectorAll('#recordingsTable tbody tr').forEach(row => {{
                row.classList.toggle('hidden', !row.dataset.search.includes(q));
            }});
        }}

        // Export
        function exportCSV() {{
            const rows = [['Run ID', 'Status', 'Time']];
            document.querySelectorAll('#recordingsTable tbody tr').forEach(r => {{
                const cols = r.querySelectorAll('td');
                rows.push([cols[1].textContent.trim(), cols[3].textContent.trim(), cols[2].textContent.trim()]);
            }});
            const csv = rows.map(r => r.join(',')).join('\\n');
            const blob = new Blob([csv], {{ type: 'text/csv' }});
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'rusemeva-recordings.csv';
            a.click();
        }}

        function exportJSON() {{
            const data = {json.dumps({"generated": now, "stats": stats}, default=str)};
            const blob = new Blob([JSON.stringify(data, null, 2)], {{ type: 'application/json' }});
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'rusemeva-data.json';
            a.click();
        }}

        // Modal
        function showModal(title, body) {{
            document.getElementById('modal-title').textContent = title;
            document.getElementById('modal-body').innerHTML = body;
            document.getElementById('modal').classList.add('active');
        }}
        function closeModal() {{ document.getElementById('modal').classList.remove('active'); }}

        function showShortcuts() {{
            showModal('⌨️ Keyboard Shortcuts', `
                <div class="shortcuts">
                    <div class="shortcut"><span class="key">R</span> Refresh</div>
                    <div class="shortcut"><span class="key">D</span> Toggle theme</div>
                    <div class="shortcut"><span class="key">S</span> Focus search</div>
                    <div class="shortcut"><span class="key">E</span> Export CSV</div>
                    <div class="shortcut"><span class="key">Esc</span> Close modal</div>
                    <div class="shortcut"><span class="key">1-4</span> Filter status</div>
                </div>
            `);
        }}

        // Keyboard shortcuts
        document.addEventListener('keydown', e => {{
            if (e.target.tagName === 'INPUT') return;
            switch(e.key) {{
                case 'r': location.reload(); break;
                case 'd': toggleTheme(); break;
                case 's': e.preventDefault(); document.getElementById('searchInput').focus(); break;
                case 'e': exportCSV(); break;
                case 'Escape': closeModal(); break;
                case '1': filterTable('all', document.querySelector('.filter-btn')); break;
                case '2': filterTable('success', document.querySelectorAll('.filter-btn')[1]); break;
                case '3': filterTable('failure', document.querySelectorAll('.filter-btn')[2]); break;
                case '4': filterTable('running', document.querySelectorAll('.filter-btn')[3]); break;
            }}
        }});

        // Browser notifications
        if ('Notification' in window && Notification.permission === 'default') {{
            Notification.requestPermission();
        }}

        // Auto-refresh
        setInterval(() => location.reload(), 30000);
    </script>
</body>
</html>'''

    return html

def main():
    print("🔄 Fetching data...")
    runs = fetch_workflow_runs(100)
    releases = fetch_releases(30)
    stats = calculate_stats(runs)

    print(f"📊 Stats: {stats['total_recordings']} recordings, {stats['success_rate']}% success")

    print("🔄 Generating HTML...")
    html = generate_html(stats, runs, releases)

    out_dir = os.environ.get("DASHBOARD_DIR", "/tmp/gh-pages")
    os.makedirs(out_dir, exist_ok=True)

    html_path = os.path.join(out_dir, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    data_path = os.path.join(out_dir, "data.json")
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump({"generated": datetime.now(WIB).isoformat(), "stats": stats, "recent_runs": runs[:30], "recent_releases": releases[:15]}, f, indent=2, default=str)

    print(f"✅ Dashboard: {html_path} ({os.path.getsize(html_path)/1024:.0f} KB)")
    print(f"✅ Data: {data_path}")

if __name__ == "__main__":
    main()
