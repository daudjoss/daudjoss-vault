#!/usr/bin/env python3
"""Generate dashboard with dummy data for JS validation."""
import json, sys
sys.path.insert(0, '.')
from generate_dashboard import gen, calc

# Minimal dummy runs/releases for calc() to work
runs = [
    {"databaseId": 1, "name": "rusemeva-vault", "status": "completed", "conclusion": "success",
     "createdAt": "2025-01-01T10:00:00Z", "updatedAt": "2025-01-01T10:05:00Z",
     "event": "push", "headBranch": "main", "headSha": "abc123", "number": 1, "displayTitle": "test"},
    {"databaseId": 2, "name": "rusemeva-encode", "status": "completed", "conclusion": "failure",
     "createdAt": "2025-01-01T11:00:00Z", "updatedAt": "2025-01-01T11:03:00Z",
     "event": "push", "headBranch": "main", "headSha": "def456", "number": 2, "displayTitle": "test2"},
]
releases = [
    {"tag": "v1.0", "name": "Release 1h30m", "created": "2025-01-01T12:00:00Z", "size": 1000000, "assets": []}
]

S = calc(runs, releases)
html = gen(S, runs, releases)

import os
out_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(out_dir, "test_dashboard.html"), "w", encoding="utf-8", errors="surrogatepass") as f:
    f.write(html)
print(f"Generated {len(html)} bytes")
