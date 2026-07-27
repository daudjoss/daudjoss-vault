#!/usr/bin/env python3
"""Transcribe audio using Whisper (tiny model)."""
import argparse
import json
import os
import sys

def main():
    parser = argparse.ArgumentParser(description="Whisper transcription")
    parser.add_argument("--input", required=True, help="Input audio file (WAV)")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--language", default="id", help="Language code (default: id)")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # Import whisper
    try:
        import whisper
    except ImportError:
        print("❌ whisper not installed. Run: pip install openai-whisper")
        sys.exit(1)

    print("🔄 Loading Whisper tiny model...")
    model = whisper.load_model("tiny")

    print(f"🔄 Transcribing: {args.input}")
    result = model.transcribe(
        args.input,
        language=args.language,
        word_timestamps=False,
        verbose=False
    )

    # Extract segments
    segments = []
    for seg in result["segments"]:
        segments.append({
            "start": round(seg["start"], 1),
            "end": round(seg["end"], 1),
            "text": seg["text"].strip()
        })

    # Save JSON transcript
    json_path = os.path.join(args.output_dir, "transcript.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON: {json_path} ({len(segments)} segments)")

    # Generate SRT subtitle
    srt_path = os.path.join(args.output_dir, "subtitle.srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            sh = int(seg["start"] // 3600)
            sm = int((seg["start"] % 3600) // 60)
            ss = int(seg["start"] % 60)
            sms = int((seg["start"] % 1) * 1000)
            eh = int(seg["end"] // 3600)
            em = int((seg["end"] % 3600) // 60)
            es = int(seg["end"] % 60)
            ems = int((seg["end"] % 1) * 1000)
            f.write(f"{i}\n")
            f.write(f"{sh:02d}:{sm:02d}:{ss:02d},{sms:03d} --> {eh:02d}:{em:02d}:{es:02d},{ems:03d}\n")
            f.write(f"{seg['text']}\n\n")
    print(f"✅ SRT: {srt_path}")

    # Generate plain text transcript
    txt_path = os.path.join(args.output_dir, "transcript.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        for seg in segments:
            m = int(seg["start"] // 60)
            s = int(seg["start"] % 60)
            f.write(f"[{m:02d}:{s:02d}] {seg['text']}\n")
    print(f"✅ TXT: {txt_path}")

    print(f"✅ Transcription complete: {len(segments)} segments")

if __name__ == "__main__":
    main()
