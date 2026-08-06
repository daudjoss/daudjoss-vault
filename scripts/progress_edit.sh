#!/bin/bash
# progress_edit.sh — update progress di pesan Telegram yg sama
# Usage: progress_edit.sh <msg_id> <text>
# Dipanggil dari encode.yml untuk edit pesan HEVC estimate

set -e

MSG_ID="$1"
TEXT="$2"
CHAT_ID="${CHAT_ID:-$3}"
BOT_TOKEN="${BOT_TOKEN:-$4}"
API="${TG_API_URL:-https://api.telegram.org}"

if [ -z "$MSG_ID" ] || [ -z "$TEXT" ]; then
  echo "Usage: progress_edit.sh <msg_id> <text> [chat_id] [bot_token]"
  exit 1
fi

if [ -z "$CHAT_ID" ] || [ -z "$BOT_TOKEN" ]; then
  echo "⚠️ CHAT_ID atau BOT_TOKEN tidak diset — skip progress edit"
  exit 0
fi

# Escape text untuk JSON
JSON_TEXT=$(python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$TEXT")

RESP=$(curl -s -o /tmp/rusemeva_edit_resp.json -w "%{http_code}" \
  -X POST "${API}/bot${BOT_TOKEN}/editMessageText" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\":${CHAT_ID},\"message_id\":${MSG_ID},\"text\":${JSON_TEXT},\"parse_mode\":\"HTML\",\"disable_web_page_preview\":true}" 2>/dev/null)

if [ "$RESP" = "200" ]; then
  echo "✅ Progress updated: ${TEXT:0:60}..."
else
  echo "⚠️ editMessageText HTTP $RESP: $(head -c 200 /tmp/rusemeva_edit_resp.json)"
fi
