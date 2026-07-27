#!/usr/bin/env python3
"""Send transcript + SRT to Telegram."""
import json
import os
import urllib.request

def send_message(bot, chat, text, parse_mode="Markdown"):
    """Send text message to Telegram."""
    data = json.dumps({
        "chat_id": chat,
        "text": text,
        "parse_mode": parse_mode
    }).encode()

    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{bot}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read().decode())
            if resp.get("ok"):
                return True
            print(f"⚠️ Telegram error: {resp}")
            return False
    except Exception as e:
        print(f"⚠️ Send failed: {e}")
        return False

def send_document(bot, chat, filepath, caption=""):
    """Send file to Telegram."""
    boundary = "----FormBoundary123"
    fname = os.path.basename(filepath)
    parts = []
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat}'.encode())
    if caption:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption}'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{fname}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode())
    with open(filepath, "rb") as f:
        parts.append(f.read())
    parts.append(f'\r\n--{boundary}--\r\n'.encode())
    body = b''.join(parts)

    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{bot}/sendDocument",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read().decode())
            if resp.get("ok"):
                print(f"✅ {fname} sent to Telegram")
                return True
            print(f"⚠️ Document error: {resp}")
            return False
    except Exception as e:
        print(f"⚠️ Document send failed: {e}")
        return False

def main():
    bot = os.environ.get("BOT_TOKEN", "")
    chat = os.environ.get("CHAT_ID", "")
    orv_id = os.environ.get("ORV_ID", "unknown")

    if not bot or not chat:
        print("❌ BOT_TOKEN or CHAT_ID not set")
        return

    # Read description
    desc_path = "/tmp/transcribe_out/description.md"
    if not os.path.exists(desc_path):
        print("❌ Description file not found")
        return

    with open(desc_path, encoding="utf-8") as f:
        desc = f.read()

    # Telegram message limit: 4096 chars
    if len(desc) > 4000:
        desc = desc[:3997] + "..."

    # Try with Markdown first, fallback to plain text
    print("📤 Sending transcript message...")
    if not send_message(bot, chat, desc, "Markdown"):
        # Fallback: remove markdown formatting
        plain = desc.replace("*", "").replace("`", "").replace("_", "")
        send_message(bot, chat, plain, "")

    # Send SRT file
    srt_path = "/tmp/transcribe_out/subtitle.srt"
    if os.path.exists(srt_path):
        print("📤 Sending SRT file...")
        send_document(bot, chat, srt_path, f"Subtitle: {orv_id}")

    # Send TXT transcript
    txt_path = "/tmp/transcribe_out/transcript.txt"
    if os.path.exists(txt_path):
        print("📤 Sending TXT transcript...")
        send_document(bot, chat, txt_path, f"Transcript: {orv_id}")

    print("✅ All done!")

if __name__ == "__main__":
    main()
