#!/usr/bin/env bash
# resolve_source.sh — Resolve stream source (trans7/sevenhub) to m3u8 URL.
# Exports: RESOLVED_URL, RESOLVED_REFERER to GITHUB_ENV
set -euo pipefail

SRC="${source:-}"
if [ -z "$SRC" ]; then
  echo "ℹ️ No source — using provided m3u8_url"
  exit 0
fi

echo "🔗 Resolving source: $SRC"

if [ "$SRC" = "trans7" ]; then
  # Probe token-less URL first — works without rotated WOWZA_SECRET.
  # Many trans7 endpoints expose /trans7/ (no SecureToken) in parallel to /trans7-sec/.
  UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
  REF="https://20.detik.com/watch/livestreaming-trans7"
  NOAUTH="https://video.detik.com/trans7/smil:trans7.smil/playlist.m3u8"

  PROBE=$(curl -sS -o /dev/null -m 8 -w "%{http_code}" \
    -H "User-Agent: $UA" -H "Referer: $REF" "$NOAUTH" 2>/dev/null || echo "000")
  echo "🔍 Probe no-auth URL: HTTP $PROBE"

  if [ "$PROBE" = "200" ]; then
    echo "✅ No-auth path works — using /trans7/ (skip Wowza token)"
    if [ -n "${GITHUB_ENV:-}" ]; then
      echo "RESOLVED_URL=$NOAUTH" >> "$GITHUB_ENV"
      echo "RESOLVED_REFERER=$REF" >> "$GITHUB_ENV"
    fi
    echo "URL: ${NOAUTH:0:80}..."
    exit 0
  fi

  # Fallback: use Wowza SecureToken with WOWZA_SECRET
  SECRET="${WOWZA_SECRET:-}"
  if [ -z "$SECRET" ]; then
    echo "❌ No-auth path failed (HTTP $PROBE) and WOWZA_SECRET not set"
    exit 1
  fi
  echo "🔐 No-auth probe failed, falling back to Wowza token..."
  python3 scripts/gen_token_gha.py "$SECRET"

elif [ "$SRC" = "sevenhub" ]; then
  echo "📺 Installing Playwright + browser..."
  pip install playwright 2>&1 | tail -2
  playwright install chromium 2>&1 | tail -3
  playwright install-deps chromium 2>&1 | tail -3 || true
  echo "📺 Resolving sevenhub m3u8 via browser..."
  python3 scripts/resolve_sevenhub.py

else
  echo "⚠️ Unknown source: $SRC"
fi
