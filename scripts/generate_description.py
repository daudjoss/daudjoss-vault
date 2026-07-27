#!/usr/bin/env python3
"""Generate video description from transcript."""
import argparse
import json
import os
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(description="Generate description from transcript")
    parser.add_argument("--transcript", required=True, help="Transcript JSON file")
    parser.add_argument("--output", required=True, help="Output description file")
    args = parser.parse_args()

    # Load transcript
    with open(args.transcript, encoding="utf-8") as f:
        segments = json.load(f)

    # Get metadata from env
    orv_id = os.environ.get("ORV_ID", "unknown")
    source = os.environ.get("SOURCE", "unknown")
    filename = os.environ.get("FILENAME", "unknown")
    human_dur = os.environ.get("HUMAN_DUR", "n/a")
    duration = os.environ.get("DURATION", "0")

    # Generate chapter markers (every ~2 minutes or at long pauses)
    chapters = []
    last_chapter_time = 0
    for seg in segments:
        if seg["start"] - last_chapter_time >= 120:  # every 2 minutes
            words = seg["text"].split()[:5]
            title = " ".join(words) + "..."
            chapters.append({"time": int(seg["start"]), "title": title})
            last_chapter_time = seg["start"]

    # Build description
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    desc = f"📝 **Transcript — {orv_id}**\n\n"
    desc += f"📺 Source: {source}\n"
    desc += f"⏱ Durasi: {human_dur}\n"
    desc += f"📦 File: {filename}\n"
    desc += f"📅 Generated: {now} WIB\n\n"

    # Chapters
    desc += "**Chapters:**\n"
    if chapters:
        for ch in chapters:
            m = ch["time"] // 60
            s = ch["time"] % 60
            desc += f"• [{m:02d}:{s:02d}] {ch['title']}\n"
    else:
        desc += "• (no chapters detected)\n"

    # Transcript (first 50 segments)
    desc += f"\n**Transcript ({len(segments)} segments):**\n"
    for seg in segments[:50]:
        m = int(seg["start"] // 60)
        s = int(seg["start"] % 60)
        desc += f"[{m:02d}:{s:02d}] {seg['text']}\n"

    if len(segments) > 50:
        desc += f"\n... dan {len(segments) - 50} segmen lagi (lihat file lengkap)\n"

    desc += f"\n📊 Total: {len(segments)} segmen, {duration} detik"

    # Save
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(desc)

    print(f"✅ Description generated: {len(desc)} chars, {len(chapters)} chapters")

if __name__ == "__main__":
    main()
