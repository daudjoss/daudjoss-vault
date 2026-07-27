#!/usr/bin/env python3
"""Generate comprehensive Rusemeva dashboard with all features."""
import json
import os
import subprocess
from datetime import datetime, timezone, timedelta
from collections import defaultdict

WIB = timezone(timedelta(hours=7))
REPO = "daudjoss/daudjoss-vault"

def run_gh(args):
    try:
        result = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=30)
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
    other = [r for r in runs if r.get("name") not in ["rusemeva-vault", "rusemeva-encode", "ci-policy", "cleanup-temp", "Update Dashboard"]]

    total = len(vault)
    success = len([r for r in vault if r.get("conclusion") == "success"])
    failed = len([r for r in vault if r.get("conclusion") == "failure"])
    rate = (success / total * 100) if total > 0 else 0

    # Encode stats
    enc_total = len(encode)
    enc_success = len([r for r in encode if r.get("conclusion") == "success"])
    enc_rate = (enc_success / enc_total * 100) if enc_total > 0 else 0

    # Daily activity (last 30 days)
    daily = defaultdict(int)
    for r in vault:
        try:
            dt = datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
            day = dt.strftime("%Y-%m-%d")
            daily[day] += 1
        except:
            pass

    # Success rate over time
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

    return {
        "total_recordings": total,
        "total_success": success,
        "total_failed": failed,
        "success_rate": round(rate, 1),
        "total_encode": enc_total,
        "encode_success": enc_success,
        "encode_rate": round(enc_rate, 1),
        "total_other": len(other),
        "daily_activity": dict(sorted(daily.items())[-30:]),
        "weekly_stats": dict(sorted(weekly.items())[-12:]),
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

    # Prepare data for charts
    daily_labels = json.dumps(list(stats["daily_activity"].keys()))
    daily_data = json.dumps(list(stats["daily_activity"].values()))

    weekly_labels = json.dumps(list(stats["weekly_stats"].keys()))
    weekly_success = json.dumps([v["success"] for v in stats["weekly_stats"].values()])
    weekly_fail = json.dumps([v["fail"] for v in stats["weekly_stats"].values()])

    # Recent recordings
    vault_runs = [r for r in runs if r.get("name") == "rusemeva-vault"][:20]
    encode_runs = [r for r in runs if r.get("name") == "rusemeva-encode"][:15]

    recent_html = ""
    for r in vault_runs:
        icon = status_icon(r.get("conclusion", ""))
        ago = time_ago(r.get("createdAt", ""))
        run_id = r.get("databaseId", "")
        status = r.get("conclusion", r.get("status", "unknown"))
        cls = status_class(status)
        recent_html += f'<tr class="row-{cls}" data-status="{status}" data-source="vault"><td>{icon}</td><td><code>{run_id}</code></td><td>{ago}</td><td><span class="badge badge-{cls}">{status}</span></td><td><a href="https://github.com/{REPO}/actions/runs/{run_id}" target="_blank">→</a></td></tr>'

    encode_html = ""
    for r in encode_runs:
        icon = status_icon(r.get("conclusion", ""))
        ago = time_ago(r.get("createdAt", ""))
        run_id = r.get("databaseId", "")
        status = r.get("conclusion", r.get("status", "unknown"))
        cls = status_class(status)
        encode_html += f'<tr class="row-{cls}" data-status="{status}" data-source="encode"><td>{icon}</td><td><code>{run_id}</code></td><td>{ago}</td><td><span class="badge badge-{cls}">{status}</span></td><td><a href="https://github.com/{REPO}/actions/runs/{run_id}" target="_blank">→</a></td></tr>'

    releases_html = ""
    for r in releases[:15]:
        size_mb = r.get("size", 0) / 1024 / 1024
        ago = time_ago(r.get("created", ""))
        releases_html += f'<tr><td><code>{r.get("tag", "")}</code></td><td>{size_mb:.1f} MB</td><td>{ago}</td></tr>'

    # Calendar data (last 35 days)
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

    html = f"""<!DOCTYPE html>
<html lang="id">
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
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            padding: 20px;
            min-height: 100vh;
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
        }}
        .header h1 {{
            font-size: 28px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .header h1 .logo {{ font-size: 32px; }}
        .header-meta {{
            display: flex;
            align-items: center;
            gap: 16px;
            color: var(--text-secondary);
            font-size: 14px;
        }}
        .live-dot {{
            width: 8px;
            height: 8px;
            background: var(--accent-green);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
        }}
        
        /* Stats Cards */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .stat-card {{
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            position: relative;
            overflow: hidden;
        }}
        .stat-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
        }}
        .stat-card.blue::before {{ background: var(--accent-blue); }}
        .stat-card.green::before {{ background: var(--accent-green); }}
        .stat-card.red::before {{ background: var(--accent-red); }}
        .stat-card.yellow::before {{ background: var(--accent-yellow); }}
        .stat-card.purple::before {{ background: var(--accent-purple); }}
        .stat-icon {{ font-size: 24px; margin-bottom: 8px; }}
        .stat-value {{ font-size: 36px; font-weight: 700; margin-bottom: 4px; }}
        .stat-label {{ font-size: 13px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; }}
        .stat-card.blue .stat-value {{ color: var(--accent-blue); }}
        .stat-card.green .stat-value {{ color: var(--accent-green); }}
        .stat-card.red .stat-value {{ color: var(--accent-red); }}
        .stat-card.yellow .stat-value {{ color: var(--accent-yellow); }}
        .stat-card.purple .stat-value {{ color: var(--accent-purple); }}
        
        /* Grid Layout */
        .grid-2 {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
            margin-bottom: 24px;
        }}
        .grid-3 {{
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 24px;
            margin-bottom: 24px;
        }}
        
        /* Section Card */
        .section {{
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 24px;
        }}
        .section-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--border);
        }}
        .section-title {{
            font-size: 16px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        /* Filters */
        .filters {{
            display: flex;
            gap: 12px;
            margin-bottom: 16px;
            flex-wrap: wrap;
        }}
        .filter-btn {{
            padding: 6px 16px;
            border-radius: 20px;
            border: 1px solid var(--border);
            background: transparent;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 13px;
            transition: all 0.2s;
        }}
        .filter-btn:hover, .filter-btn.active {{
            background: var(--accent-blue);
            color: white;
            border-color: var(--accent-blue);
        }}
        .search-input {{
            padding: 8px 16px;
            border-radius: 8px;
            border: 1px solid var(--border);
            background: var(--bg-tertiary);
            color: var(--text-primary);
            font-size: 14px;
            width: 200px;
        }}
        .search-input:focus {{
            outline: none;
            border-color: var(--accent-blue);
        }}
        
        /* Table */
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 10px 14px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        th {{
            color: var(--text-secondary);
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 600;
        }}
        td {{ font-size: 14px; }}
        tr:hover {{ background: rgba(88, 166, 255, 0.05); }}
        code {{
            background: var(--bg-tertiary);
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 12px;
            font-family: 'SF Mono', 'Fira Code', monospace;
        }}
        a {{ color: var(--accent-blue); text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        
        /* Badges */
        .badge {{
            padding: 4px 12px;
            border-radius: 16px;
            font-size: 12px;
            font-weight: 500;
        }}
        .badge-success {{ background: rgba(63, 185, 80, 0.15); color: var(--accent-green); }}
        .badge-failure {{ background: rgba(248, 81, 73, 0.15); color: var(--accent-red); }}
        .badge-cancelled {{ background: rgba(139, 148, 158, 0.15); color: var(--text-secondary); }}
        .badge-running {{ background: rgba(88, 166, 255, 0.15); color: var(--accent-blue); }}
        
        /* Calendar */
        .calendar {{
            display: grid;
            grid-template-columns: repeat(35, 1fr);
            gap: 3px;
            margin-top: 12px;
        }}
        .cal-day {{
            width: 100%;
            aspect-ratio: 1;
            border-radius: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 10px;
            color: var(--text-muted);
            cursor: default;
            position: relative;
        }}
        .cal-0 {{ background: var(--bg-tertiary); }}
        .cal-1 {{ background: rgba(63, 185, 80, 0.3); }}
        .cal-2 {{ background: rgba(63, 185, 80, 0.5); }}
        .cal-3 {{ background: rgba(63, 185, 80, 0.7); }}
        .cal-4 {{ background: rgba(63, 185, 80, 0.85); }}
        .cal-5 {{ background: var(--accent-green); color: white; }}
        
        /* Charts */
        .chart-container {{
            position: relative;
            height: 250px;
            margin-top: 12px;
        }}
        
        /* Status indicator */
        .status-bar {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 12px 16px;
            background: rgba(63, 185, 80, 0.1);
            border: 1px solid rgba(63, 185, 80, 0.3);
            border-radius: 8px;
            margin-bottom: 16px;
        }}
        .status-bar.error {{
            background: rgba(248, 81, 73, 0.1);
            border-color: rgba(248, 81, 73, 0.3);
        }}
        
        /* Footer */
        .footer {{
            text-align: center;
            color: var(--text-muted);
            font-size: 13px;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid var(--border);
        }}
        .footer a {{ color: var(--text-secondary); }}
        
        /* Responsive */
        @media (max-width: 1024px) {{
            .grid-2, .grid-3 {{ grid-template-columns: 1fr; }}
        }}
        @media (max-width: 768px) {{
            .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .header {{ flex-direction: column; gap: 12px; }}
            .filters {{ flex-direction: column; }}
            .search-input {{ width: 100%; }}
            .calendar {{ grid-template-columns: repeat(7, 1fr); }}
        }}
        
        /* Animations */
        .stat-card, .section {{
            animation: fadeIn 0.3s ease-in;
        }}
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        /* Hidden rows for filter */
        .hidden {{ display: none; }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1><span class="logo">🎬</span> Rusemeva Dashboard</h1>
            <div class="header-meta">
                <div class="live-dot"></div>
                <span>Auto-refresh 30s</span>
                <span>|</span>
                <span id="last-update">{now}</span>
            </div>
        </div>
        
        <!-- Stats -->
        <div class="stats-grid">
            <div class="stat-card blue">
                <div class="stat-icon">📹</div>
                <div class="stat-value">{stats['total_recordings']}</div>
                <div class="stat-label">Total Rekaman</div>
            </div>
            <div class="stat-card green">
                <div class="stat-icon">✅</div>
                <div class="stat-value">{stats['total_success']}</div>
                <div class="stat-label">Sukses</div>
            </div>
            <div class="stat-card red">
                <div class="stat-icon">❌</div>
                <div class="stat-value">{stats['total_failed']}</div>
                <div class="stat-label">Gagal</div>
            </div>
            <div class="stat-card yellow">
                <div class="stat-icon">📊</div>
                <div class="stat-value">{stats['success_rate']}%</div>
                <div class="stat-label">Success Rate</div>
            </div>
            <div class="stat-card purple">
                <div class="stat-icon">🎞</div>
                <div class="stat-value">{stats['total_encode']}</div>
                <div class="stat-label">Encode Jobs</div>
            </div>
        </div>
        
        <!-- Activity Calendar -->
        <div class="section">
            <div class="section-header">
                <div class="section-title">📅 Aktivitas 35 Hari Terakhir</div>
            </div>
            <div class="calendar">
                {calendar_html}
            </div>
            <div style="display:flex; gap:8px; margin-top:12px; align-items:center; font-size:12px; color:var(--text-secondary)">
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
                <div class="section-header">
                    <div class="section-title">📈 Rekaman per Hari</div>
                </div>
                <div class="chart-container">
                    <canvas id="dailyChart"></canvas>
                </div>
            </div>
            <div class="section">
                <div class="section-header">
                    <div class="section-title">📊 Success Rate per Minggu</div>
                </div>
                <div class="chart-container">
                    <canvas id="weeklyChart"></canvas>
                </div>
            </div>
        </div>
        
        <!-- Recordings Table -->
        <div class="section">
            <div class="section-header">
                <div class="section-title">🎬 Recent Recordings</div>
                <div class="filters">
                    <input type="text" class="search-input" id="searchInput" placeholder="🔍 Search ID...">
                    <button class="filter-btn active" onclick="filterTable('all')">All</button>
                    <button class="filter-btn" onclick="filterTable('success')">✅ Success</button>
                    <button class="filter-btn" onclick="filterTable('failure')">❌ Failed</button>
                    <button class="filter-btn" onclick="filterTable('running')">🔄 Running</button>
                </div>
            </div>
            <table id="recordingsTable">
                <thead>
                    <tr>
                        <th></th>
                        <th>Run ID</th>
                        <th>Time</th>
                        <th>Status</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    {recent_html}
                </tbody>
            </table>
        </div>
        
        <!-- Encode Jobs -->
        <div class="section">
            <div class="section-header">
                <div class="section-title">🎞 Encode Jobs</div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th></th>
                        <th>Run ID</th>
                        <th>Time</th>
                        <th>Status</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    {encode_html}
                </tbody>
            </table>
        </div>
        
        <!-- Releases -->
        <div class="section">
            <div class="section-header">
                <div class="section-title">📦 Recent Releases</div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Tag</th>
                        <th>Size</th>
                        <th>Time</th>
                    </tr>
                </thead>
                <tbody>
                    {releases_html}
                </tbody>
            </table>
        </div>
        
        <!-- Footer -->
        <div class="footer">
            <p>Rusemeva Vault &middot; <a href="https://github.com/{REPO}">GitHub</a> &middot; <a href="https://github.com/{REPO}/actions">Actions</a></p>
            <p style="margin-top:8px">Auto-refresh setiap 30 detik &middot; Data dari GitHub API</p>
        </div>
    </div>
    
    <script>
        // Charts
        const dailyCtx = document.getElementById('dailyChart').getContext('2d');
        new Chart(dailyCtx, {{
            type: 'bar',
            data: {{
                labels: {daily_labels},
                datasets: [{{
                    label: 'Recordings',
                    data: {daily_data},
                    backgroundColor: 'rgba(88, 166, 255, 0.6)',
                    borderColor: 'rgba(88, 166, 255, 1)',
                    borderWidth: 1,
                    borderRadius: 4,
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }},
                }},
                scales: {{
                    x: {{
                        grid: {{ color: 'rgba(48, 54, 61, 0.5)' }},
                        ticks: {{ color: '#8b949e', maxTicksLimit: 10 }}
                    }},
                    y: {{
                        beginAtZero: true,
                        grid: {{ color: 'rgba(48, 54, 61, 0.5)' }},
                        ticks: {{ color: '#8b949e', stepSize: 1 }}
                    }}
                }}
            }}
        }});
        
        const weeklyCtx = document.getElementById('weeklyChart').getContext('2d');
        new Chart(weeklyCtx, {{
            type: 'line',
            data: {{
                labels: {weekly_labels},
                datasets: [
                    {{
                        label: 'Success',
                        data: {weekly_success},
                        borderColor: '#3fb950',
                        backgroundColor: 'rgba(63, 185, 80, 0.1)',
                        fill: true,
                        tension: 0.4,
                    }},
                    {{
                        label: 'Failed',
                        data: {weekly_fail},
                        borderColor: '#f85149',
                        backgroundColor: 'rgba(248, 81, 73, 0.1)',
                        fill: true,
                        tension: 0.4,
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        labels: {{ color: '#8b949e' }}
                    }}
                }},
                scales: {{
                    x: {{
                        grid: {{ color: 'rgba(48, 54, 61, 0.5)' }},
                        ticks: {{ color: '#8b949e' }}
                    }},
                    y: {{
                        beginAtZero: true,
                        grid: {{ color: 'rgba(48, 54, 61, 0.5)' }},
                        ticks: {{ color: '#8b949e', stepSize: 1 }}
                    }}
                }}
            }}
        }});
        
        // Filter functions
        function filterTable(status) {{
            const rows = document.querySelectorAll('#recordingsTable tbody tr');
            const btns = document.querySelectorAll('.filter-btn');
            
            btns.forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            rows.forEach(row => {{
                if (status === 'all' || row.dataset.status === status) {{
                    row.classList.remove('hidden');
                }} else {{
                    row.classList.add('hidden');
                }}
            }});
        }}
        
        // Search
        document.getElementById('searchInput').addEventListener('input', function(e) {{
            const search = e.target.value.toLowerCase();
            const rows = document.querySelectorAll('#recordingsTable tbody tr');
            rows.forEach(row => {{
                const id = row.querySelector('code').textContent.toLowerCase();
                row.classList.toggle('hidden', !id.includes(search));
            }});
        }});
        
        // Auto-refresh
        setInterval(() => {{
            location.reload();
        }}, 30000);
    </script>
</body>
</html>"""

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
        json.dump({
            "generated": datetime.now(WIB).isoformat(),
            "stats": stats,
            "recent_runs": runs[:30],
            "recent_releases": releases[:15],
        }, f, indent=2, default=str)

    print(f"✅ Dashboard: {html_path} ({os.path.getsize(html_path)/1024:.0f} KB)")
    print(f"✅ Data: {data_path}")

if __name__ == "__main__":
    main()
