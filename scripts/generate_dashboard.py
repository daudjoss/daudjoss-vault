#!/usr/bin/env python3
"""Generate static dashboard HTML from GitHub Actions data."""
import json
import os
import subprocess
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))

def run_gh(args):
    """Run gh CLI and return output."""
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True, text=True, timeout=30
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"⚠️ gh error: {e}")
        return ""

def fetch_workflow_runs(limit=50):
    """Fetch recent workflow runs."""
    raw = run_gh([
        "run", "list",
        "--repo", "daudjoss/daudjoss-vault",
        "--limit", str(limit),
        "--json", "databaseId,name,status,conclusion,createdAt,event"
    ])
    if not raw:
        return []
    try:
        return json.loads(raw)
    except:
        return []

def fetch_releases(limit=20):
    """Fetch recent releases."""
    raw = run_gh([
        "api", "repos/daudjoss/daudjoss-vault/releases",
        "--jq", f"[.[:{limit}][] | {{tag: .tag_name, name: .name, created: .created_at, size: ([.assets[].size] | add // 0)}}]"
    ])
    if not raw:
        return []
    try:
        return json.loads(raw)
    except:
        return []

def calculate_stats(runs):
    """Calculate statistics from runs."""
    vault_runs = [r for r in runs if r.get("name") == "rusemeva-vault"]
    encode_runs = [r for r in runs if r.get("name") == "rusemeva-encode"]
    transcribe_runs = [r for r in runs if r.get("name") == "rusemeva-transcribe"]

    total = len(vault_runs)
    success = len([r for r in vault_runs if r.get("conclusion") == "success"])
    failed = len([r for r in vault_runs if r.get("conclusion") == "failure"])
    rate = (success / total * 100) if total > 0 else 0

    return {
        "total_recordings": total,
        "total_success": success,
        "total_failed": failed,
        "success_rate": round(rate, 1),
        "total_encode": len(encode_runs),
        "total_transcribe": len(transcribe_runs),
    }

def time_ago(created_str):
    """Convert ISO timestamp to 'X ago' string."""
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
    """Get status icon."""
    if conclusion == "success":
        return "✅"
    elif conclusion == "failure":
        return "❌"
    elif conclusion == "cancelled":
        return "⚪"
    else:
        return "🔄"

def generate_html(stats, runs, releases):
    """Generate HTML dashboard."""
    now = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")

    # Recent recordings (vault runs only)
    vault_runs = [r for r in runs if r.get("name") == "rusemeva-vault"][:15]

    recent_html = ""
    for r in vault_runs:
        icon = status_icon(r.get("conclusion", ""))
        ago = time_ago(r.get("createdAt", ""))
        run_id = r.get("databaseId", "")
        status = r.get("conclusion", r.get("status", "unknown"))
        recent_html += f"""
        <tr>
            <td>{icon}</td>
            <td><code>{run_id}</code></td>
            <td>{ago}</td>
            <td><span class="badge badge-{status}">{status}</span></td>
            <td><a href="https://github.com/daudjoss/daudjoss-vault/actions/runs/{run_id}" target="_blank">→</a></td>
        </tr>"""

    # Encode runs
    encode_runs = [r for r in runs if r.get("name") == "rusemeva-encode"][:10]
    encode_html = ""
    for r in encode_runs:
        icon = status_icon(r.get("conclusion", ""))
        ago = time_ago(r.get("createdAt", ""))
        run_id = r.get("databaseId", "")
        status = r.get("conclusion", r.get("status", "unknown"))
        encode_html += f"""
        <tr>
            <td>{icon}</td>
            <td><code>{run_id}</code></td>
            <td>{ago}</td>
            <td><span class="badge badge-{status}">{status}</span></td>
            <td><a href="https://github.com/daudjoss/daudjoss-vault/actions/runs/{run_id}" target="_blank">→</a></td>
        </tr>"""

    # Recent releases
    releases_html = ""
    for r in releases[:10]:
        size_mb = r.get("size", 0) / 1024 / 1024
        ago = time_ago(r.get("created", ""))
        releases_html += f"""
        <tr>
            <td><code>{r.get("tag", "")}</code></td>
            <td>{size_mb:.1f} MB</td>
            <td>{ago}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rusemeva Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{
            color: #58a6ff;
            margin-bottom: 8px;
            font-size: 24px;
        }}
        .subtitle {{
            color: #8b949e;
            margin-bottom: 24px;
            font-size: 14px;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 32px;
        }}
        .stat-card {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 16px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 32px;
            font-weight: bold;
            color: #58a6ff;
        }}
        .stat-label {{
            font-size: 12px;
            color: #8b949e;
            margin-top: 4px;
            text-transform: uppercase;
        }}
        .section {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 24px;
        }}
        .section h2 {{
            color: #c9d1d9;
            font-size: 16px;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid #30363d;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 8px 12px;
            text-align: left;
            border-bottom: 1px solid #21262d;
        }}
        th {{
            color: #8b949e;
            font-size: 12px;
            text-transform: uppercase;
        }}
        td {{ font-size: 14px; }}
        code {{
            background: #21262d;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 12px;
        }}
        a {{ color: #58a6ff; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .badge {{
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
        }}
        .badge-success {{ background: #1a4d2e; color: #3fb950; }}
        .badge-failure {{ background: #4d1a1a; color: #f85149; }}
        .badge-cancelled {{ background: #3d3d3d; color: #8b949e; }}
        .badge-in_progress {{ background: #1a3a4d; color: #58a6ff; }}
        .footer {{
            text-align: center;
            color: #484f58;
            font-size: 12px;
            margin-top: 32px;
        }}
        .grid-2 {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
        }}
        @media (max-width: 768px) {{
            .grid-2 {{ grid-template-columns: 1fr; }}
            .stats {{ grid-template-columns: repeat(2, 1fr); }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Rusemeva Dashboard</h1>
        <p class="subtitle">Last updated: {now}</p>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">{stats['total_recordings']}</div>
                <div class="stat-label">Total Rekaman</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats['total_success']}</div>
                <div class="stat-label">Sukses</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats['total_failed']}</div>
                <div class="stat-label">Gagal</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats['success_rate']}%</div>
                <div class="stat-label">Success Rate</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats['total_encode']}</div>
                <div class="stat-label">Encode</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats['total_transcribe']}</div>
                <div class="stat-label">Transcribe</div>
            </div>
        </div>

        <div class="grid-2">
            <div class="section">
                <h2>🎬 Recent Recordings</h2>
                <table>
                    <tr><th></th><th>ID</th><th>Time</th><th>Status</th><th></th></tr>
                    {recent_html}
                </table>
            </div>

            <div class="section">
                <h2>🎞 Encode Jobs</h2>
                <table>
                    <tr><th></th><th>ID</th><th>Time</th><th>Status</th><th></th></tr>
                    {encode_html}
                </table>
            </div>
        </div>

        <div class="section">
            <h2>📦 Recent Releases</h2>
            <table>
                <tr><th>Tag</th><th>Size</th><th>Time</th></tr>
                {releases_html}
            </table>
        </div>

        <div class="footer">
            Rusemeva Vault &middot; <a href="https://github.com/daudjoss/daudjoss-vault">GitHub</a>
        </div>
    </div>
</body>
</html>"""

    return html

def main():
    print("🔄 Fetching data...")
    runs = fetch_workflow_runs(50)
    releases = fetch_releases(20)
    stats = calculate_stats(runs)

    print(f"📊 Stats: {stats['total_recordings']} recordings, {stats['success_rate']}% success")

    print("🔄 Generating HTML...")
    html = generate_html(stats, runs, releases)

    # Save to gh-pages directory
    out_dir = os.environ.get("DASHBOARD_DIR", "/tmp/gh-pages")
    os.makedirs(out_dir, exist_ok=True)

    html_path = os.path.join(out_dir, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Also save raw data as JSON
    data_path = os.path.join(out_dir, "data.json")
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated": datetime.now(WIB).isoformat(),
            "stats": stats,
            "recent_runs": runs[:20],
            "recent_releases": releases[:10],
        }, f, indent=2, default=str)

    print(f"✅ Dashboard generated: {html_path}")
    print(f"✅ Data saved: {data_path}")
    print(f"📊 HTML size: {os.path.getsize(html_path) / 1024:.1f} KB")

if __name__ == "__main__":
    main()
