#!/usr/bin/env bash
set -euo pipefail
# #7 mulai timer kalibrasi
ENC_START=$SECONDS
FILE="${ORIG_FILE}"
HEVC_FILE="${FILE%.mp4}-h265-10bit.mp4"
FFMPEG_STATIC="${FFMPEG_STATIC}"
HEVC_PRESET="${HEVC_PRESET}"
HEVC_CRF="${HEVC_CRF}"
CHOSEN="${CHOSEN_PRESET}"
if [ "$CHOSEN" != "$HEVC_PRESET" ]; then
  MSG="🔻 <b>Auto-downgrade</b>: request <code>$CHOSEN</code> estimasi &gt;~5j50m di runner; dipilih preset <b>paling lambat yang masih muat</b> → <code>$HEVC_PRESET</code> (CRF $HEVC_CRF)."
else
  MSG="🎚 Encode pakai preset <code>$HEVC_PRESET</code> (CRF $HEVC_CRF)."
fi
CHAT_ID="$CHAT_ID" FILENAME="$FILE" TG_API_URL="$TG_API_URL" BOT_TOKEN="$BOT_TOKEN" python3 scripts/send_message.py "$MSG" || true
echo "🎞 Encoding HEVC 10-bit (preset=${HEVC_PRESET}, CRF ${HEVC_CRF}) dari original..."
echo "📦 Original: $(ls -lh "$FILE" | awk '{print $5}')"

source scripts/encode_policy.sh
REQ_DUR="${REQUESTED_DURATION}"
SRC_DUR_INT="${DURATION_SEC}"
case "$SRC_DUR_INT" in ''|*[!0-9]*) SRC_DUR_INT=0 ;; esac
REAL_SRC_INT=$(probe_duration_int "$FILE" || true)
if [ "${REAL_SRC_INT:-0}" -gt 0 ] 2>/dev/null; then
  SRC_DUR_INT=$REAL_SRC_INT
elif [ "${SRC_DUR_INT:-0}" -le 0 ] 2>/dev/null; then
  case "$REQ_DUR" in ''|*[!0-9]*) SRC_DUR_INT=60 ;; *) SRC_DUR_INT=$REQ_DUR ;; esac
  [ "$SRC_DUR_INT" -le 0 ] 2>/dev/null && SRC_DUR_INT=60
fi
AUDIO_BPS=$(probe_audio_bps "$FILE" || echo 0)
MAXRATE_K=$(video_maxrate_k "$AUDIO_BPS")
BUFSIZE_K=$(( MAXRATE_K * 2 ))
echo "dur=${SRC_DUR_INT}s audio=${AUDIO_BPS} maxrate=${MAXRATE_K}k"

# === SKIP ENCODE if original already efficient ===
# Video stream copy, but audio gets turbo-normalized (loudnorm two-pass)
ORIG_TOTAL_BPS=$(probe_bitrate "$FILE" || echo 0)
HEVC_SKIP=0
if [ "${ORIG_TOTAL_BPS:-0}" -gt 0 ] 2>/dev/null && [ "${ORIG_TOTAL_BPS:-0}" -le 1500000 ] 2>/dev/null; then
  HEVC_SKIP=1
  ORIG_MB=$(( ORIG_TOTAL_BPS / 1000000 ))
  ORIG_TENTH=$(( (ORIG_TOTAL_BPS / 100000) % 10 ))
  echo "⏭️ Original sudah efisien (~${ORIG_MB}.${ORIG_TENTH} Mbps) — skip HEVC video encode"
  CHAT_ID="$CHAT_ID" TG_API_URL="$TG_API_URL" BOT_TOKEN="$BOT_TOKEN" python3 scripts/send_message.py \
    "⏭️ <b>HEVC skip</b> — original sudah efisien (~${ORIG_MB}.${ORIG_TENTH} Mbps). Audio tetap di-normalize." || true
  # === TURBO AUDIO NORMALIZE (stream copy video, loudnorm audio only) ===
  HEVC_FILE="${FILE%.mp4}-normalized.mp4"
  if [ "${SRC_DUR_INT:-0}" -ge 30 ] 2>/dev/null; then
    echo "🔊 Turbo audio normalize (loudnorm pass 1)..."
    LOUDNORM_PROBE="/tmp/rusemeva_loudnorm_probe.log"
    timeout 120 "$FFMPEG_STATIC" -hide_banner -nostats -i "$FILE" \
      -af "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json" \
      -f null - 2>"$LOUDNORM_PROBE" || true
    LOUDNORM_MEASURED=$(python3 - "$LOUDNORM_PROBE" <<'PYEOF'
import json, re, sys
try:
    with open(sys.argv[1]) as f:
        log = f.read()
    m = re.search(r'\{[^{}]*"input_i"[^{}]*\}', log, re.DOTALL)
    if not m:
        sys.exit(0)
    d = json.loads(m.group(0))
    i = d.get("input_i", "").strip()
    tp = d.get("input_tp", "").strip()
    lra = d.get("input_lra", "").strip()
    thresh = d.get("input_thresh", "").strip()
    ot = d.get("offset", "0").strip() or "0"
    if i and tp and lra:
        print(f"measured_I={i}:measured_TP={tp}:measured_LRA={lra}:measured_thresh={thresh}:offset={ot}:linear=true:I=-16:TP=-1.5:LRA=11")
except:
    pass
PYEOF
    )
    rm -f "$LOUDNORM_PROBE" 2>/dev/null || true
    if [ -n "$LOUDNORM_MEASURED" ]; then
      # Detect channel count for rematrixing
      CH_COUNT=$(ffprobe -v error -select_streams a:0 -show_entries stream=channels -of default=noprint_wrappers=1:nokey=1 "$FILE" 2>/dev/null | head -1)
      CH_LAYOUT=$(ffprobe -v error -select_streams a:0 -show_entries stream=channel_layout -of default=noprint_wrappers=1:nokey=1 "$FILE" 2>/dev/null | head -1)
      echo "🔊 Audio channels: ${CH_COUNT:-?} (${CH_LAYOUT:-unknown})"
      CH_PREFIX=""
      if [ "${CH_COUNT:-0}" = "1" ]; then
        CH_PREFIX="pan=stereo|FL=FC|FR=FC,"
        echo "🔊 Mono detected → upmix to stereo (center extraction)"
      elif [ "${CH_COUNT:-0}" -gt 2 ] 2>/dev/null; then
        CH_PREFIX="pan=stereo|FL=FL+0.5*FC+0.5*SL|FR=FR+0.5*FC+0.5*SR,"
        echo "🔊 Surround detected → downmix to stereo (center extraction)"
      fi
      echo "🔊 Turbo audio normalize pass 2 (loudnorm + limiter)..."
      TMP_NORM="${HEVC_FILE}.tmp"
      rm -f "$TMP_NORM"
      "$FFMPEG_STATIC" -hide_banner -y -i "$FILE" \
        -c:v copy \
        -af "${CH_PREFIX}loudnorm=$LOUDNORM_MEASURED,alimiter=limit=0.85:attack=5:release=50" \
        -c:a aac -b:a 128k \
        "$TMP_NORM" 2>/tmp/rusemeva_audio_normalize.log || true
      if [ -s "$TMP_NORM" ]; then
        mv -f "$TMP_NORM" "$HEVC_FILE"
      else
        echo "⚠️ Loudnorm gagal, fallback copy audio tanpa filter..."
        "$FFMPEG_STATIC" -hide_banner -y -i "$FILE" \
          -c:v copy \
          -c:a aac -b:a 128k \
          "$HEVC_FILE" 2>/tmp/rusemeva_audio_fallback.log || true
      fi
    fi
  fi
  # Fallback: kalau normalize gagal/hasil 0 byte, pakai original apa adanya
  if [ ! -s "$HEVC_FILE" ]; then
    echo "⚠️ Turbo normalize gagal — pakai original apa adanya"
    HEVC_FILE="$FILE"
  fi
fi
echo "HEVC_SKIP=$HEVC_SKIP" >> $GITHUB_ENV
# Set defaults untuk HEVC_SKIP path (supaya post-encode block tidak crash)
if [ "$HEVC_SKIP" = "1" ]; then
  ORIG_BYTES=$(stat -c%s "$FILE" 2>/dev/null || wc -c < "$FILE")
  HEVC_LOG="/tmp/rusemeva_hevc_encode.log"
  SCENE_LABEL="${SCENE_LABEL:-skip}"
  LIVE_MODE="${LIVE_MODE:-0}"

fi
if [ "$HEVC_SKIP" = "0" ]; then
# === SCENE-AWARE CRF ===
# Probe 5 cuplikan @8s: encode mini ultrafast di CRF basis, ukur bytes/s.
# Konten ramai/gelap (bytes/s tinggi) → CRF turun (lebih bagus).
# Konten sepi/talking-head (bytes/s rendah) → CRF naik (lebih hemat).
# Clamp final 22..28 biar tetap di sweet-spot ~1.2–1.4 Mbps @720p.
BASE_CRF=$HEVC_CRF
SCENE_DELTA=0
if [ "$SRC_DUR_INT" -ge 60 ] 2>/dev/null; then
  echo "🧠 Scene-aware probe (5x8s)..."
  SUM_BPS=0
  N_OK=0
  for frac in 10 30 50 70 90; do
    SS=$(( SRC_DUR_INT * frac / 100 ))
    # jangan mepet EOF
    MAX_SS=$(( SRC_DUR_INT - 10 ))
    [ "$SS" -gt "$MAX_SS" ] && SS=$MAX_SS
    [ "$SS" -lt 0 ] && SS=0
    SAMPLE="/tmp/rusemeva_scene_${frac}.mp4"
    "$FFMPEG_STATIC" -hide_banner -y -ss "$SS" -t 8 -i "$FILE" \
      -c:v libx265 -profile:v main10 -pix_fmt yuv420p10le \
      -crf ${BASE_CRF} -preset ultrafast -an "$SAMPLE" >/tmp/rusemeva_scene_probe.log 2>&1 || true
    if [ -s "$SAMPLE" ]; then
      BY=$(stat -c%s "$SAMPLE" 2>/dev/null || wc -c < "$SAMPLE")
      # bytes per second of sample
      BPS=$(( BY / 8 ))
      SUM_BPS=$(( SUM_BPS + BPS ))
      N_OK=$(( N_OK + 1 ))
      echo "   • t=${SS}s sample=${BY}B (~${BPS} B/s)"
    fi
    rm -f "$SAMPLE" 2>/dev/null || true
  done
  if [ "$N_OK" -gt 0 ]; then
    AVG_BPS=$(( SUM_BPS / N_OK ))
    echo "🧠 Scene avg complexity: ${AVG_BPS} B/s (n=$N_OK) base_crf=$BASE_CRF"
    # Kalibrasi kasar 720p@CRF24 ultrafast sample:
    # sepi < 40k B/s, normal 40–90k, ramai > 90k
    if [ "$AVG_BPS" -gt 90000 ]; then
      SCENE_DELTA=-2
      SCENE_LABEL="ramai/kompleks"
    elif [ "$AVG_BPS" -gt 60000 ]; then
      SCENE_DELTA=-1
      SCENE_LABEL="agak ramai"
    elif [ "$AVG_BPS" -lt 35000 ]; then
      SCENE_DELTA=1
      SCENE_LABEL="sepi/talking-head"
    else
      SCENE_DELTA=0
      SCENE_LABEL="normal"
    fi
    HEVC_CRF=$(( BASE_CRF + SCENE_DELTA ))
    [ "$HEVC_CRF" -lt "${MIN_CRF:-22}" ] && HEVC_CRF=${MIN_CRF:-22}
    [ "$HEVC_CRF" -gt "${MAX_CRF:-28}" ] && HEVC_CRF=${MAX_CRF:-28}
    echo "🧠 Scene-aware: ${SCENE_LABEL} → CRF ${BASE_CRF} + (${SCENE_DELTA}) = ${HEVC_CRF}"
    if [ "$HEVC_CRF" != "$BASE_CRF" ]; then
      CHAT_ID="$CHAT_ID" TG_API_URL="$TG_API_URL" BOT_TOKEN="$BOT_TOKEN" python3 scripts/send_message.py \
        "🧠 <b>Scene-aware:</b> konten <code>${SCENE_LABEL}</code> → CRF <code>${BASE_CRF}</code> → <code>${HEVC_CRF}</code> (jaga ~1.3 Mbps, anti-buram di bagian penting)." || true
    fi
  else
    echo "⚠️ Scene probe gagal — pakai CRF basis $BASE_CRF"
  fi
else
  echo "ℹ️ Video pendek (<60s) — skip scene-aware"
fi

# x265 adaptive quant: alokasi bit lebih pintar per-block (dalam-frame scene-aware)

# === LIVE-FRIENDLY MODE (siaran TV) ===
# Aktif jika: profil /setting live  ATAU auto-detect chrome statis (logo/ticker).
# Efek: AQ lebih agresif di detail, denoise ringan, jaga tengah, hemat area statis.
ENCODE_PROFILE="${ENCODE_PROFILE}"
LIVE_MODE=0
LIVE_REASON=""
if [ "$ENCODE_PROFILE" = "live" ]; then
  LIVE_MODE=1
  LIVE_REASON="profil /setting live"
else
  # Auto-detect: bandingkan stabilitas sudut vs tengah di 5 timestamp
  # Kalau sudut jauh lebih stabil → kemungkinan logo/ticker TV.
  if [ "${SRC_DUR_INT:-0}" -ge 120 ] 2>/dev/null; then
    echo "📺 Live-detect: cek chrome statis (logo/ticker)..."
    CORNER_DIFF=0
    CENTER_DIFF=0
    N_PAIR=0
    PREV_C=""
    PREV_M=""
    for frac in 15 35 55 75 90; do
      SS=$(( SRC_DUR_INT * frac / 100 ))
      MAX_SS=$(( SRC_DUR_INT - 2 ))
      [ "$SS" -gt "$MAX_SS" ] && SS=$MAX_SS
      FC="/tmp/rusemeva_live_c_${frac}.png"
      FM="/tmp/rusemeva_live_m_${frac}.png"
      # sudut kiri-atas 12%
      "$FFMPEG_STATIC" -hide_banner -y -ss "$SS" -i "$FILE" -vframes 1 \
        -vf "crop=iw*0.12:ih*0.12:0:0,scale=64:64,format=gray" "$FC" >/dev/null 2>&1 || true
      # tengah 30%
      "$FFMPEG_STATIC" -hide_banner -y -ss "$SS" -i "$FILE" -vframes 1 \
        -vf "crop=iw*0.30:ih*0.30:(iw-ow)/2:(ih-oh)/2,scale=64:64,format=gray" "$FM" >/dev/null 2>&1 || true
      if [ -n "$PREV_C" ] && [ -s "$FC" ] && [ -s "$PREV_C" ]; then
        # mean abs diff via ffmpeg psnr (lower=more similar/static)
        DC=$("$FFMPEG_STATIC" -hide_banner -i "$PREV_C" -i "$FC" -filter_complex "psnr" -f null - 2>&1 | sed -n 's/.*mse_avg:\([0-9.]*\).*/\1/p' | tail -1)
        DM=$("$FFMPEG_STATIC" -hide_banner -i "$PREV_M" -i "$FM" -filter_complex "psnr" -f null - 2>&1 | sed -n 's/.*mse_avg:\([0-9.]*\).*/\1/p' | tail -1)
        DC=${DC%.*}; DM=${DM%.*}
        [ -z "$DC" ] && DC=0
        [ -z "$DM" ] && DM=0
        CORNER_DIFF=$(( CORNER_DIFF + DC ))
        CENTER_DIFF=$(( CENTER_DIFF + DM ))
        N_PAIR=$(( N_PAIR + 1 ))
        echo "   • t=${SS}s corner_mse~$DC center_mse~$DM"
      fi
      PREV_C=$FC; PREV_M=$FM
    done
    rm -f /tmp/rusemeva_live_c_*.png /tmp/rusemeva_live_m_*.png 2>/dev/null || true
    if [ "$N_PAIR" -gt 0 ]; then
      AVG_C=$(( CORNER_DIFF / N_PAIR ))
      AVG_M=$(( CENTER_DIFF / N_PAIR ))
      echo "📺 Live-detect avg: corner_mse=$AVG_C center_mse=$AVG_M"
      # sudut statis (mse kecil) + tengah lebih dinamis → siaran TV
      if [ "$AVG_C" -le 25 ] && [ "$AVG_M" -ge $(( AVG_C * 3 + 5 )) ]; then
        LIVE_MODE=1
        LIVE_REASON="auto-detect chrome TV (logo/ticker)"
      fi
    fi
  fi
fi

VF_LIVE=""
if [ "$LIVE_MODE" = "1" ]; then
  echo "📺 LIVE MODE ON ($LIVE_REASON)"
  # Denoise sangat ringan (siaran sering noisy), jaga detail wajah
  VF_LIVE="hqdn3d=0.8:0.6:2:2"
  # AQ lebih kuat + lookahead lebih panjang + mild deblock (ticker/logo lebih rapi)
  X265_PARAMS="aq-mode=3:aq-strength=1.25:qcomp=0.72:rd=3:psy-rd=1.8:psy-rdoq=1.0:rc-lookahead=60:scenecut=40:deblock=-1,-1:sao=1:strong-intra-smoothing=1:bframes=6"
  CHAT_ID="$CHAT_ID" TG_API_URL="$TG_API_URL" BOT_TOKEN="$BOT_TOKEN" python3 scripts/send_message.py \
    "📺 <b>Live-friendly ON</b> — ${LIVE_REASON}.\\nJaga tengah frame, hemat logo/ticker, denoise ringan. Target tetap ~1.3 Mbps." || true
else
  echo "📺 Live mode OFF (konten general)"
  X265_PARAMS="aq-mode=3:aq-strength=1.0:rd=3:psy-rd=1.5:psy-rdoq=1.0:rc-lookahead=40:scenecut=40:colorprim=bt709:transfer=bt709:colormatrix=bt709"
fi



CHAT_ID="$CHAT_ID" FILENAME="$FILE" TG_API_URL="$TG_API_URL" BOT_TOKEN="$BOT_TOKEN" PROGRESS_MSG_FILE=/tmp/rusemeva_progress_msg_id PROGRESS_STATE_FILE=/tmp/rusemeva_progress_state SRC_DUR_SEC="$SRC_DUR_INT" python3 scripts/progress.py start || true
LAST_PCT=-1
HEVC_LOG=/tmp/rusemeva_hevc_encode.log
# FIX PROGRESS 0%: -progress pipe:1 tulis ke stdout.
# Pakai '3>&1 1>>...' supaya progress ke fd 3 (yg di-pipe ke while),
# stderr+stdout utama ke log. Tanpa ini, progress diambil log, while kosong.
# Live denoise filter (kosong kalau bukan live)
LIVE_VF_ARGS=()
if [ -n "${VF_LIVE:-}" ]; then
  LIVE_VF_ARGS=(-vf "$VF_LIVE")
fi
# === AUDIO NORMALIZATION + DYNAMIC COMPRESSION (film-quality) ===
# Chain: highpass(50Hz) → lowshelf(+3dB bass) → highshelf(+2dB treble) → de-ess → dialogue boost → adeclip → acompressor → loudnorm(two-pass) → alimiter
# - highpass: buang mains hum 50Hz
# - lowshelf: boost bass 100-200Hz +3dB biar suara warm/full kayak film
# - highshelf: boost treble 8kHz +2dB, konsonan crisp, suara tidak muffled
# - equalizer(6kHz): de-essing, buang sibilance "sss" berlebih di 5-7kHz
# - equalizer(2kHz): dialogue boost, suara manusia lebih menonjol
# - adeclip: repair audio yang sudah clipped (distorsi digital >0dBFS)
# - acompressor: kompres dynamic range, dialog lebih jelas, iklan tidak ledak
# - loudnorm: EBU R128 target -16 LUFS
# - alimiter: hard cap true peak, anti-clipping
AUDIO_AF=""
AUDIO_ENC="-c:a copy"
if [ "${SRC_DUR_INT:-0}" -ge 30 ] 2>/dev/null; then
  echo "🔊 Audio normalization probe (loudnorm pass 1)..."
  LOUDNORM_PROBE="/tmp/rusemeva_loudnorm_probe.log"
  timeout 120 "$FFMPEG_STATIC" -hide_banner -nostats -i "$FILE" \
    -af "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json" \
    -f null - 2>"$LOUDNORM_PROBE" || true
  # Parse measured values → build pass-2 filter string
  LOUDNORM_MEASURED=$(python3 - "$LOUDNORM_PROBE" <<'PYEOF'
import json, re, sys
try:
    with open(sys.argv[1]) as f:
        log = f.read()
    m = re.search(r'\{[^{}]*"input_i"[^{}]*\}', log, re.DOTALL)
    if not m:
        sys.exit(0)
    d = json.loads(m.group(0))
    i = d.get("input_i", "").strip()
    tp = d.get("input_tp", "").strip()
    lra = d.get("input_lra", "").strip()
    thresh = d.get("input_thresh", "").strip()
    ot = d.get("offset", "0").strip() or "0"
    if i and tp and lra:
        print(f"measured_I={i}:measured_TP={tp}:measured_LRA={lra}:measured_thresh={thresh}:offset={ot}:linear=true:I=-16:TP=-1.5:LRA=11")
except:
    pass
PYEOF
    )
  if [ -n "$LOUDNORM_MEASURED" ]; then
    # Detect channel count for rematrixing
    CH_COUNT=$(ffprobe -v error -select_streams a:0 -show_entries stream=channels -of default=noprint_wrappers=1:nokey=1 "$FILE" 2>/dev/null | head -1)
    CH_LAYOUT=$(ffprobe -v error -select_streams a:0 -show_entries stream=channel_layout -of default=noprint_wrappers=1:nokey=1 "$FILE" 2>/dev/null | head -1)
    echo "🔊 Audio channels: ${CH_COUNT:-?} (${CH_LAYOUT:-unknown})"
    # Build channel-aware prefix filter
    CH_PREFIX=""
    if [ "${CH_COUNT:-0}" = "1" ]; then
      CH_PREFIX="pan=stereo|FL=FC|FR=FC,"
      echo "🔊 Mono detected → upmix to stereo (center extraction)"
    elif [ "${CH_COUNT:-0}" -gt 2 ] 2>/dev/null; then
      CH_PREFIX="pan=stereo|FL=FL+0.5*FC+0.5*SL|FR=FR+0.5*FC+0.5*SR,"
      echo "🔊 Surround detected → downmix to stereo (center extraction)"
    fi
    # Simple audio chain: loudnorm + limiter (stabil di static ffmpeg, no crossover/amerge)
    AUDIO_AF="${CH_PREFIX}loudnorm=$LOUDNORM_MEASURED,alimiter=limit=0.85:attack=5:release=50"
    AUDIO_FCS=""
    AUDIO_ENC="-c:a aac -b:a 128k"
    echo "🔊 Audio chain: loudnorm(-16 LUFS) → limiter(0.85) → verify+correct"
  else
    echo "⚠️ Loudnorm probe gagal — copy audio as-is"
    AUDIO_FCS=""
  fi
  rm -f "$LOUDNORM_PROBE" 2>/dev/null || true
fi
"$FFMPEG_STATIC" -hide_banner -y -i "$FILE" \
  "${LIVE_VF_ARGS[@]}" \
  $AUDIO_FCS \
  $AUDIO_AF \
  -c:v libx265 -profile:v main10 -pix_fmt yuv420p10le \
  -crf ${HEVC_CRF} -preset ${HEVC_PRESET} -maxrate ${MAXRATE_K:-1450}k -bufsize ${BUFSIZE_K:-2900}k \
  -x265-params "${X265_PARAMS}" -tag:v hvc1 \
  $AUDIO_ENC -progress pipe:3 "$HEVC_FILE" \
  3> >(while IFS='=' read -r k v; do
    if [ "$k" = "out_time_ms" ]; then
      ms=${v%.*}
      [ "$ms" -gt 0 ] 2>/dev/null || continue
      cur=$(( ms / 1000000 ))
      [ "${SRC_DUR_INT:-0}" -gt 0 ] 2>/dev/null || continue
      pct=$(( (cur * 100) / SRC_DUR_INT )); [ "$pct" -gt 100 ] && pct=100
      if [ "$pct" != "$LAST_PCT" ]; then
        LAST_PCT=$pct
        echo "🔄 HEVC encode ${pct}%"
        CHAT_ID="$CHAT_ID" FILENAME="$FILE" TG_API_URL="$TG_API_URL" BOT_TOKEN="$BOT_TOKEN" PROGRESS_MSG_FILE=/tmp/rusemeva_progress_msg_id PROGRESS_STATE_FILE=/tmp/rusemeva_progress_state SRC_DUR_SEC="$SRC_DUR_INT" python3 scripts/progress.py progress "$pct" || true
      fi
    fi
  done) \
  > "$HEVC_LOG" 2>&1
  ENC_RC=$?
  if [ "${ENC_RC:-0}" -ne 0 ] && [ ! -s "$HEVC_FILE" ]; then
    echo "❌ First encode failed (rc=$ENC_RC)"
    tail -n 30 "$HEVC_LOG" 2>/dev/null || true
    exit 1
  fi
echo "🔄 HEVC encode 100%"
CHAT_ID="$CHAT_ID" FILENAME="$FILE" TG_API_URL="$TG_API_URL" BOT_TOKEN="$BOT_TOKEN" PROGRESS_MSG_FILE=/tmp/rusemeva_progress_msg_id python3 scripts/progress.py done || true

fi  # end HEVC_SKIP=0 (scene-aware + live-detect + encode loop)

if [ -s "$HEVC_FILE" ]; then
  echo "✅ HEVC selesai: $(ls -lh "$HEVC_FILE" | awk '{print $5}')"

  # === AUTO BITRATE/SIZE GUARD (skip if HEVC_SKIP — original already good) ===
  ORIG_BYTES=$(stat -c%s "$FILE" 2>/dev/null || wc -c < "$FILE")
  if [ "$HEVC_SKIP" = "1" ]; then
    echo "⏭️ Skip auto-size guard (HEVC_SKIP — original dipakai apa adanya)"
    echo "HEVC_CRF_FINAL=skip" >> $GITHUB_ENV
  else
  TARGET_BYTES=$(target_bytes "$SRC_DUR_INT" "$ORIG_BYTES" || echo 0)
  if [ "${TARGET_BYTES:-0}" -le 0 ]; then
    echo "target_bytes invalid dur=$SRC_DUR_INT orig=$ORIG_BYTES"
    exit 1
  fi
  echo "Size target: $TARGET_BYTES bytes | orig=$ORIG_BYTES dur=${SRC_DUR_INT}s maxrate=${MAXRATE_K:-1450}k"
  CUR_CRF="$HEVC_CRF"
  try=0
  while true; do
    HEVC_BYTES=$(stat -c%s "$HEVC_FILE" 2>/dev/null || wc -c < "$HEVC_FILE")
    HBR_CHK=$(probe_bitrate "$HEVC_FILE" || true)
    if [ -z "$HBR_CHK" ]; then
      sleep 1
      HBR_CHK=$(probe_bitrate "$HEVC_FILE" || true)
    fi
    DECISION=$(accept_hevc "$HEVC_BYTES" "$TARGET_BYTES" "${HBR_CHK:-}" || true)
    echo "size hevc=${HEVC_BYTES} target<=${TARGET_BYTES} bps=${HBR_CHK:-?} decision=${DECISION} crf=${CUR_CRF}"
    if [ "$DECISION" = "OK" ]; then
      echo "Size/bitrate OK crf=$CUR_CRF bps=$HBR_CHK"
      break
    fi
    if [ "$DECISION" = "UNKNOWN" ]; then
      CHAT_ID="$CHAT_ID" TG_API_URL="$TG_API_URL" BOT_TOKEN="$BOT_TOKEN" python3 scripts/send_message.py \
        "Auto-size: gagal baca bitrate HEVC — encode dihentikan." || true
      exit 1
    fi
    if [ "$DECISION" = "NEED_BETTER" ]; then
      NEXT_CRF=$((CUR_CRF - 2))
      [ "$NEXT_CRF" -lt "${MIN_CRF:-22}" ] && NEXT_CRF=${MIN_CRF:-22}
      if [ "$NEXT_CRF" -ge "$CUR_CRF" ]; then
        echo "Already min CRF ${MIN_CRF:-22} — keep (may be soft)"
        break
      fi
      PHASE_NOTE="anti-blur"
    else
      NEXT_CRF=$((CUR_CRF + 2))
      if [ "$NEXT_CRF" -gt "${MAX_CRF:-28}" ]; then
        CHAT_ID="$CHAT_ID" TG_API_URL="$TG_API_URL" BOT_TOKEN="$BOT_TOKEN" python3 scripts/send_message.py \
          "Auto-size: still large at CRF $CUR_CRF (cap ${MAX_CRF:-28}) bps=${HBR_CHK:-?}." || true
        break
      fi
      PHASE_NOTE="auto-size"
        try=$((try + 1))
        if [ "$try" -gt 5 ]; then
          echo "⚠️ Max auto-size retries (5) reached at CRF $CUR_CRF — accept current"
          break
        fi
    fi
    CUR_CRF=$NEXT_CRF
    HEVC_CRF=$CUR_CRF
    CHAT_ID="$CHAT_ID" TG_API_URL="$TG_API_URL" BOT_TOKEN="$BOT_TOKEN" python3 scripts/send_message.py \
      "Re-encode CRF → <code>$CUR_CRF</code> ($PHASE_NOTE)." || true
    CHAT_ID="$CHAT_ID" FILENAME="$FILE" TG_API_URL="$TG_API_URL" BOT_TOKEN="$BOT_TOKEN" \
      PROGRESS_MSG_FILE=/tmp/rusemeva_progress_msg_id PROGRESS_STATE_FILE=/tmp/rusemeva_progress_state \
      SRC_DUR_SEC="$SRC_DUR_INT" PHASE_LABEL="Re-encode CRF $CUR_CRF ($PHASE_NOTE)" \
      python3 scripts/progress.py start || true
    LAST_PCT=-1
    "$FFMPEG_STATIC" -hide_banner -y -i "$FILE" \
      ${LIVE_VF_ARGS[@]+"${LIVE_VF_ARGS[@]}"} \
      $AUDIO_FCS \
      $AUDIO_AF \
      -c:v libx265 -profile:v main10 -pix_fmt yuv420p10le \
      -crf ${CUR_CRF} -preset ${HEVC_PRESET} -maxrate ${MAXRATE_K:-1450}k -bufsize ${BUFSIZE_K:-2900}k \
      -x265-params "${X265_PARAMS:-aq-mode=3:aq-strength=1.0:colorprim=bt709:transfer=bt709:colormatrix=bt709}" -tag:v hvc1 \
      $AUDIO_ENC -progress pipe:3 "$HEVC_FILE" \
      3> >(while IFS='=' read -r k v; do
        if [ "$k" = "out_time_ms" ]; then
          ms=${v%.*}
          [ "$ms" -gt 0 ] 2>/dev/null || continue
          cur=$(( ms / 1000000 ))
          [ "${SRC_DUR_INT:-0}" -gt 0 ] 2>/dev/null || continue
          pct=$(( (cur * 100) / SRC_DUR_INT )); [ "$pct" -gt 100 ] && pct=100
          if [ "$pct" != "$LAST_PCT" ]; then
            LAST_PCT=$pct
            CHAT_ID="$CHAT_ID" FILENAME="$FILE" TG_API_URL="$TG_API_URL" BOT_TOKEN="$BOT_TOKEN" \
              PROGRESS_MSG_FILE=/tmp/rusemeva_progress_msg_id PROGRESS_STATE_FILE=/tmp/rusemeva_progress_state \
              SRC_DUR_SEC="$SRC_DUR_INT" PHASE_LABEL="Re-encode CRF $CUR_CRF ($PHASE_NOTE)" \
              python3 scripts/progress.py progress "$pct" || true
          fi
        fi
      done) \
      > "$HEVC_LOG" 2>&1
    RE_RC=$?
    CHAT_ID="$CHAT_ID" FILENAME="$FILE" TG_API_URL="$TG_API_URL" BOT_TOKEN="$BOT_TOKEN" \
      PROGRESS_MSG_FILE=/tmp/rusemeva_progress_msg_id PHASE_LABEL="Re-encode CRF $CUR_CRF ($PHASE_NOTE)" \
      python3 scripts/progress.py done || true
    if [ ! -s "$HEVC_FILE" ] || [ "${RE_RC:-0}" -ne 0 ]; then
      echo "Re-encode failed crf=$CUR_CRF rc=$RE_RC"
      tail -n 30 "$HEVC_LOG" 2>/dev/null || true
      exit 1
    fi
  done
  echo "HEVC_CRF_FINAL=$CUR_CRF" >> $GITHUB_ENV
  fi  # end else (auto-size guard only when not HEVC_SKIP)
  echo "ACT_DURATION_SEC=$SRC_DUR_INT" >> $GITHUB_ENV
  echo "REQ_DURATION_SEC=${REQ_DUR:-}" >> $GITHUB_ENV

  echo "HEVC_FILE=$HEVC_FILE" >> $GITHUB_ENV
  echo "HEVC_SIZE=$(ls -lh "$HEVC_FILE" | awk '{print $5}')" >> $GITHUB_ENV
  HDUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$HEVC_FILE" 2>/dev/null | head -1)
  HDUR_INT=${HDUR%.*}
  [ -z "$HDUR_INT" ] && HDUR_INT=0
  echo "HEVC_DUR=$(printf '%02d:%02d:%02d' $((HDUR_INT/3600)) $(((HDUR_INT%3600)/60)) $((HDUR_INT%60)))" >> $GITHUB_ENV
  HW=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of default=noprint_wrappers=1:nokey=1 "$HEVC_FILE" 2>/dev/null|head -1)
  HH=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of default=noprint_wrappers=1:nokey=1 "$HEVC_FILE" 2>/dev/null|head -1)
  [ -n "$HW" ] && [ -n "$HH" ] && echo "HEVC_RES=${HW}x${HH}" >> $GITHUB_ENV
  HCV=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of default=noprint_wrappers=1:nokey=1 "$HEVC_FILE" 2>/dev/null|head -1)
  [ -n "$HCV" ] && echo "HEVC_VCODEC=$HCV" >> $GITHUB_ENV
  HBR=$(ffprobe -v error -show_entries format=bit_rate -of default=noprint_wrappers=1:nokey=1 "$HEVC_FILE" 2>/dev/null|head -1)
  case "$HBR" in ''|*[!0-9]*) ;; *) echo "HEVC_VBITRATE=$(awk "BEGIN{printf \"%.1f Mbps\", ${HBR}/1000000}")" >> $GITHUB_ENV ;; esac
  # === #4 VERIFIKASI AUDIO: pastikan HEVC punya stream audio ===
  # x265 cuma encode video; -c:a copy harusnya salin audio. Cek biar gak ke-drop.
  AUD=$(ffprobe -v error -select_streams a -show_entries stream=index -of default=noprint_wrappers=1:nokey=1 "$HEVC_FILE" 2>/dev/null | head -1)
  if [ -z "$AUD" ]; then
    echo "🔇 HEVC TIDAK punya audio stream — re-mux dari original..."
    TMP_REMUX="${HEVC_FILE%.mp4}.remux.mp4"
    "$FFMPEG_STATIC" -hide_banner -y -i "$HEVC_FILE" -i "$FILE" \
      -map 0:v:0 -map 1:a? -c copy "$TMP_REMUX" 2>/dev/null || true
    if [ -s "$TMP_REMUX" ]; then
      AUD2=$(ffprobe -v error -select_streams a -show_entries stream=index -of default=noprint_wrappers=1:nokey=1 "$TMP_REMUX" 2>/dev/null | head -1)
      if [ -n "$AUD2" ]; then
        mv -f "$TMP_REMUX" "$HEVC_FILE"
        echo "✅ Audio berhasil di-re-mux ke HEVC."
      else
        rm -f "$TMP_REMUX"
        echo "⚠️ Original juga gak punya audio — HEVC tanpa suara (wajar kalau sumber silent)."
      fi
    else
      rm -f "$TMP_REMUX"
      echo "⚠️ Re-mux gagal — HEVC tanpa suara."
    fi
  else
    echo "🔊 HEVC punya audio stream (#$AUD) — OK."
  fi
  # === SMART THUMBNAIL (auto-pick best frame from 5 candidates by JPEG size) ===
  HEVC_THUMB="${HEVC_FILE%.mp4}.jpg"
  THUMB_SCORE=""
  if [ "${HDUR_INT:-0}" -gt 12 ] 2>/dev/null; then
    echo "🖼 Smart thumbnail probe (5 candidates)..."
    BEST_SS=0; BEST_SIZE=0
    for pct in 15 35 50 70 90; do
      SS=$(( HDUR_INT * pct / 100 ))
      [ "$SS" -ge "$HDUR_INT" ] && SS=$(( HDUR_INT - 2 ))
      [ "$SS" -lt 1 ] && SS=1
      CANDIDATE="/tmp/rusemeva_thumb_${pct}.jpg"
      "$FFMPEG_STATIC" -hide_banner -loglevel error -y -ss "$SS" -i "$HEVC_FILE" -frames:v 1 -q:v 2 -vf "scale=640:-2" "$CANDIDATE" 2>/dev/null || true
      CAND_SIZE=$(stat -c%s "$CANDIDATE" 2>/dev/null || echo 0)
      if [ "${CAND_SIZE:-0}" -gt "${BEST_SIZE:-0}" ] 2>/dev/null; then
        BEST_SIZE=$CAND_SIZE
        BEST_SS=$SS
        mv -f "$CANDIDATE" "$HEVC_THUMB" 2>/dev/null || cp "$CANDIDATE" "$HEVC_THUMB" 2>/dev/null || true
      else
        rm -f "$CANDIDATE" 2>/dev/null || true
      fi
      echo "   • t=${SS}s size=${CAND_SIZE}B"
    done
    if [ "$BEST_SS" -gt 0 ] 2>/dev/null; then
      # Score: normalize JPEG size (typical: 15-80KB for 640px, q:v 2)
      THUMB_SCORE=$(awk "BEGIN{t=($BEST_SIZE-15000)*0.0015; if(t<0)t=0; if(t>100)t=100; printf \"%.0f\", t}" 2>/dev/null || echo "0")
      echo "🖼 Best frame: t=${BEST_SS}s size=${BEST_SIZE}B score=${THUMB_SCORE}/100"
    fi
    rm -f /tmp/rusemeva_thumb_*.jpg 2>/dev/null || true
  elif [ "${HDUR_INT:-0}" -gt 0 ] 2>/dev/null; then
    # Video pendek: langsung ambil tengah
    HSEEK=$(( HDUR_INT / 2 ))
    [ "$HSEEK" -lt 1 ] && HSEEK=1
    "$FFMPEG_STATIC" -hide_banner -loglevel error -y -ss "$HSEEK" -i "$HEVC_FILE" -frames:v 1 -q:v 2 -vf "scale=640:-2" "$HEVC_THUMB" 2>/dev/null || true
  fi
  # Fallback
  [ ! -s "$HEVC_THUMB" ] && "$FFMPEG_STATIC" -hide_banner -loglevel error -y -ss 1 -i "$HEVC_FILE" -frames:v 1 -q:v 2 -vf "scale=640:-2" "$HEVC_THUMB" 2>/dev/null || true
  if [ -s "$HEVC_THUMB" ]; then echo "HEVC_THUMB_FILE=$HEVC_THUMB" >> $GITHUB_ENV; echo "HAS_HEVC_THUMB=1" >> $GITHUB_ENV; else echo "HAS_HEVC_THUMB=0" >> $GITHUB_ENV; fi
  if [ -n "$THUMB_SCORE" ]; then echo "THUMB_SCORE=$THUMB_SCORE" >> $GITHUB_ENV; fi
  # === POST-ENCODE LOUDNESS VERIFICATION (auto-correct if meleset) ===
  # Always verify for HEVC_SKIP=1 (turbo path) — no AUDIO_FCS flag available
  if [ "${HDUR_INT:-0}" -ge 60 ] 2>/dev/null && [ "${HEVC_SKIP:-0}" = "0" ] && [ -z "${AUDIO_FCS:-}" ]; then
    # Skip verification for non-turbo path without complex filter
    true
  elif [ "${HDUR_INT:-0}" -ge 60 ] 2>/dev/null; then
    echo "🔊 Post-encode loudness verification..."
    VERIFY_LOG="/tmp/rusemeva_verify.log"
    timeout 60 "$FFMPEG_STATIC" -hide_banner -nostats -i "$HEVC_FILE" \
      -af "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json" \
      -f null - 2>"$VERIFY_LOG" || true
    VERIFY_LUFS=$(python3 - "$VERIFY_LOG" <<'PYEOF'
import json, re, sys
try:
    with open(sys.argv[1]) as f:
        log = f.read()
    m = re.search(r'\{[^{}]*"input_i"[^{}]*\}', log, re.DOTALL)
    if m:
        d = json.loads(m.group(0))
        print(d.get("input_i", "").strip())
except:
    pass
PYEOF
    )
    rm -f "$VERIFY_LOG" 2>/dev/null || true
    if [ -n "$VERIFY_LUFS" ]; then
      DIFF_INFO=$(python3 - "$VERIFY_LUFS" <<'PYEOF'
import sys
try:
    v = float(sys.argv[1])
    diff_abs = abs(v - (-16))
    print(f"{diff_abs:.1f}")
except (ValueError, IndexError):
    print("0.0")
PYEOF
      )
      DIFF=$(awk "BEGIN{printf \"%.1f\", $VERIFY_LUFS - (-16)}")
      echo "🔊 Post-encode loudness: ${VERIFY_LUFS} LUFS (target -16, diff ${DIFF})"
      # If meleset >0.5 LUFS, re-normalize
      if awk "BEGIN{exit !($DIFF_INFO > 0.5)}"; then
        echo "⚠️ Loudness meleset ${DIFF} LUFS — re-normalizing..."
        RENORM_FILE="${HEVC_FILE%.mp4}-renorm.mp4"
        "$FFMPEG_STATIC" -hide_banner -y -i "$HEVC_FILE" \
          -c:v copy \
          -af "loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=$VERIFY_LUFS:measured_TP=-1.5:measured_LRA=11:measured_thresh=-26:offset=0:linear=true,alimiter=limit=0.85:attack=5:release=50" \
          -c:a aac -b:a 128k \
          "$RENORM_FILE" 2>/dev/null || true
        if [ -s "$RENORM_FILE" ]; then
          mv -f "$RENORM_FILE" "$HEVC_FILE"
          echo "✅ Re-normalized to -16 LUFS"
          # Update loudness report with verified value
          LOUDNESS_TEXT="${LOUDNESS_TEXT:-}"
          LOUDNESS_TEXT=$(echo "$LOUDNESS_TEXT" | sed "1s/-[0-9.]* LUFS/${VERIFY_LUFS} LUFS (verified)/")
          [ -z "$LOUDNESS_TEXT" ] && LOUDNESS_TEXT="✅ ${VERIFY_LUFS} LUFS (verified, target -16)"
          RENORM_DONE=1
        else
          echo "⚠️ Re-normalization failed, keeping original"
        fi
      fi
    fi
  fi
  # === ANOMALY REPORT (freeze + silence detection, decode-only) ===
  ANOMALY_LOG="/tmp/rusemeva_anomaly.log"
  : > "$ANOMALY_LOG"
  ANOMALY_TEXT=""
  if [ "${HDUR_INT:-0}" -ge 60 ] 2>/dev/null; then
    echo "🔍 Anomaly detection (freeze + silence)..."
    timeout 180 "$FFMPEG_STATIC" -hide_banner -nostats -i "$HEVC_FILE" \
      -vf "freezedetect=d=2:noise=0.003" \
      -af "silencedetect=n=-30dB:d=3" \
      -f null - 2>>"$ANOMALY_LOG" || true
    ANOMALY_TEXT=$(python3 - "$ANOMALY_LOG" "$HDUR_INT" <<'PYEOF'
import re, sys
log_path, dur_s = sys.argv[1], int(sys.argv[2]) if len(sys.argv)>2 else 0
freezes, silences = [], []
sil_start = None
try:
    with open(log_path) as f:
        for line in f:
            m = re.search(r'freeze_start:\s*([\d.]+)', line)
            if m:
                fs = float(m.group(1))
                md = re.search(r'freeze_duration:\s*([\d.]+)', line)
                freezes.append((fs, float(md.group(1)) if md else 0))
            m = re.search(r'silence_start:\s*([\d.]+)', line)
            if m: sil_start = float(m.group(1))
            m = re.search(r'silence_end:\s*([\d.]+)', line)
            if m and sil_start is not None:
                silences.append((sil_start, float(m.group(1)) - sil_start))
                sil_start = None
except: pass
def ts(s):
    s=int(s); h,r=divmod(s,3600); m,s=divmod(r,60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
out = []
if freezes:
    tot = sum(d for _,d in freezes)
    entries = ", ".join(f"{ts(t)} ({int(d)}s)" for t,d in freezes[:8])
    extra = f" +{len(freezes)-8} more" if len(freezes)>8 else ""
    out.append(f"⚠️ Freeze: {entries}{extra} (total {int(tot)}s)")
else:
    out.append("✅ No freeze")
if silences:
    entries = ", ".join(f"{ts(t)} ({int(d)}s)" for t,d in silences[:8])
    extra = f" +{len(silences)-8} more" if len(silences)>8 else ""
    out.append(f"🔇 Silence: {entries}{extra}")
else:
    out.append("✅ Audio present (no silence)")
print("\n".join(out))
PYEOF
    )
  fi
  echo "ANOMALY_TEXT<<RUSEMEVA_EOF" >> $GITHUB_ENV
  echo "$ANOMALY_TEXT" >> $GITHUB_ENV
  echo "RUSEMEVA_EOF" >> $GITHUB_ENV
  # === LOUDNESS REPORT (LUFS, 2-min sample dari tengah video) ===
  LOUDNESS_TEXT=""  # Ensure initialized even if probe skipped
  # If post-encode verification already re-normalized, skip probe — already verified
  if [ "${RENORM_DONE:-0}" != "1" ]; then
  LOUDNESS_LOG="/tmp/rusemeva_loudness.log"
  : > "$LOUDNESS_LOG"
  LOUDNESS_TEXT=""
  if [ "${HDUR_INT:-0}" -ge 60 ] 2>/dev/null; then
    echo "🔊 Loudness probe (2-min sample)..."
    MID=$(( HDUR_INT / 2 ))
    [ "$MID" -ge "$HDUR_INT" ] && MID=0
    timeout 90 "$FFMPEG_STATIC" -hide_banner -nostats -ss "$MID" -t 120 -i "$HEVC_FILE" \
      -af "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json" \
      -f null - 2>>"$LOUDNESS_LOG" || true
    LOUDNESS_TEXT=$(python3 - "$LOUDNESS_LOG" <<'PYEOF'
import json, re, sys
log_path = sys.argv[1]
try:
    with open(log_path) as f:
        log = f.read()
    m = re.search(r'\{[^{}]*"input_i"[^{}]*\}', log, re.DOTALL)
    if not m:
        sys.exit(0)
    d = json.loads(m.group(0))
    lufs = float(d.get("input_i", "0") or "0")
    tp = float(d.get("input_tp", "0") or "0")
    lra = float(d.get("input_lra", "0") or "0")
    out = []
    if lufs < -20:
        out.append(f"⚠️ {lufs:.1f} LUFS — terlalu pelan (target -16)")
    elif lufs > -12:
        out.append(f"⚠️ {lufs:.1f} LUFS — terlalu keras (target -16)")
    else:
        out.append(f"✅ {lufs:.1f} LUFS (target -16)")
    if tp > 0:
        out.append(f"⚠️ True peak {tp:.1f} dBTP — clipping")
    if lra > 15:
        out.append(f"⚠️ LRA {lra:.1f} dB — dynamic range tinggi")
    print("\n".join(out))
except:
    pass
PYEOF
    )
  fi
  fi  # RENORM_DONE guard
  # Always write LOUDNESS_TEXT (may be set by verification re-normalize)
  echo "LOUDNESS_TEXT<<RUSEMEVA_EOF" >> $GITHUB_ENV
  echo "$LOUDNESS_TEXT" >> $GITHUB_ENV
  echo "RUSEMEVA_EOF" >> $GITHUB_ENV
  # === ENCODE EFFICIENCY SCORE ===
  EFFICIENCY_TEXT=""
  HEVC_BYTES_F=$(stat -c%s "$HEVC_FILE" 2>/dev/null || wc -c < "$HEVC_FILE")
  if [ "${ORIG_BYTES:-0}" -gt 0 ] && [ "${HEVC_BYTES_F:-0}" -gt 0 ]; then
    # Jika HEVC_SKIP, utamakan info "no re-encode" agar tidak menyesatkan.
    if [ "${HEVC_SKIP:-0}" = "1" ]; then
      EFFICIENCY_TEXT=$(python3 - "$ORIG_BYTES" "$HEVC_BYTES_F" <<'PYEOF'
import sys
orig = int(sys.argv[1])
hevc = int(sys.argv[2])
ratio = (1 - hevc / orig) * 100 if orig > 0 else 0
out = []
out.append(f"⏭️ No re-encode — original already efficient")
if abs(ratio) > 5:
    out.append(f"📏 Audio normalize changed size by {ratio:+.0f}% ({orig/1048576:.0f}MB → {hevc/1048576:.0f}MB)")
else:
    out.append(f"📏 Size preserved: {hevc/1048576:.0f}MB")
print("\\n".join(out))
PYEOF
      )
    else
      EFFICIENCY_TEXT=$(python3 - "$ORIG_BYTES" "$HEVC_BYTES_F" "$HDUR_INT" "$HBR" <<'PYEOF'
import sys
orig = int(sys.argv[1])
hevc = int(sys.argv[2])
dur = int(sys.argv[3]) if len(sys.argv) > 3 else 0
bps = sys.argv[4]
out = []
ratio = (1 - hevc / orig) * 100 if orig > 0 else 0
if ratio < 0:
    out.append(f"⚠️ HEVC {abs(ratio):.0f}% LARGER ({orig/1048576:.0f}MB → {hevc/1048576:.0f}MB)")
elif ratio < 10:
    out.append(f"📉 Compression: {ratio:.0f}% smaller ({orig/1048576:.0f}MB → {hevc/1048576:.0f}MB) — minimal")
else:
    out.append(f"📊 Compression: {ratio:.0f}% smaller ({orig/1048576:.0f}MB → {hevc/1048576:.0f}MB)")
try:
    br = float(bps) / 1000000
except:
    br = 0
if dur > 0 and br > 0:
    if br < 0.8:
        out.append(f"📉 {br:.1f} Mbps — low (blur risk)")
    elif br > 2.5:
        out.append(f"📈 {br:.1f} Mbps — high (overkill)")
    else:
        out.append(f"✅ {br:.1f} Mbps — optimal for 720p10bit")
print("\\n".join(out))
PYEOF
      )
    fi
  fi
  echo "EFFICIENCY_TEXT<<RUSEMEVA_EOF" >> $GITHUB_ENV
  echo "$EFFICIENCY_TEXT" >> $GITHUB_ENV
  echo "RUSEMEVA_EOF" >> $GITHUB_ENV
  # === SOURCE QUALITY RATING (A-F grade) ===
  SOURCE_QUALITY=""
  SRC_ACODEC=$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of default=noprint_wrappers=1:nokey=1 "$FILE" 2>/dev/null | head -1)
  SRC_ABR=$(ffprobe -v error -select_streams a:0 -show_entries stream=bit_rate -of default=noprint_wrappers=1:nokey=1 "$FILE" 2>/dev/null | head -1)
  SRC_SR=$(ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate -of default=noprint_wrappers=1:nokey=1 "$FILE" 2>/dev/null | head -1)
  # Bandwidth detection via sample_rate/2 (Nyquist) — accurate for digital audio
  SRC_BW=""
  if [ "${SRC_DUR_INT:-0}" -ge 30 ] 2>/dev/null; then
    # Effective bandwidth = min(sample_rate/2, codec cutoff)
    # AAC: ~15kHz @128k, ~18kHz @192k+; AC3: ~20kHz; MP2: ~12kHz
    SRC_BW=$(python3 - "$SRC_ACODEC" "$SRC_ABR" "$SRC_SR" <<'PYEOF'
import sys
acodec = (sys.argv[1] or "").lower()
abr = int(sys.argv[2]) if sys.argv[2].isdigit() else 0
sr = int(sys.argv[3]) if sys.argv[3].isdigit() else 0
nyquist = sr / 2 if sr > 0 else 0
# Codec-specific max bandwidth (empirical, conservative)
if acodec in ("flac", "pcm_s16le", "pcm_s24le", "pcm", "wav"):
    bw = nyquist  # lossless = full Nyquist
elif acodec == "aac":
    if abr >= 192000: bw = min(18000, nyquist)
    elif abr >= 128000: bw = min(15000, nyquist)
    elif abr >= 96000: bw = min(12000, nyquist)
    else: bw = min(8000, nyquist)
elif acodec == "mp3":
    if abr >= 192000: bw = min(16000, nyquist)
    elif abr >= 128000: bw = min(14000, nyquist)
    else: bw = min(10000, nyquist)
elif acodec in ("ac3", "eac3"):
    bw = min(20000, nyquist)
elif acodec == "mp2":
    bw = min(12000, nyquist)
elif acodec == "opus":
    bw = min(20000, nyquist)
else:
    bw = nyquist  # unknown → assume full
print(f"{bw:.0f}" if bw > 0 else "0")
PYEOF
    )
  fi
  SOURCE_QUALITY=$(python3 - "$SRC_ACODEC" "$SRC_ABR" "$SRC_SR" "$SRC_BW" <<'PYEOF'
import sys
acodec = sys.argv[1] if len(sys.argv) > 1 else "?"
abr = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 0
sr = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else 0
bw_str = sys.argv[4] if len(sys.argv) > 4 else "0"
try: bw = float(bw_str) if bw_str.strip() else 0
except ValueError: bw = 0

out = []

# Codec score
codec_scores = {
    "aac": 10, "mp3": 8, "opus": 10, "vorbis": 9,
    "flac": 10, "pcm": 10, "pcm_s16le": 10, "pcm_s24le": 10,
    "ac3": 7, "eac3": 8, "dts": 8, "mp2": 5,
    "wma": 6, "wmav2": 6, "real_audio": 3,
    "": 0, "unknown": 0, "?": 0
}
codec_score = codec_scores.get(acodec.lower(), 5)

# Bitrate score (kbps)
abr_kbps = abr // 1000 if abr > 0 else 0
if abr_kbps >= 256: br_score = 10
elif abr_kbps >= 192: br_score = 9
elif abr_kbps >= 128: br_score = 8
elif abr_kbps >= 96: br_score = 6
elif abr_kbps >= 64: br_score = 4
elif abr_kbps > 0: br_score = 2
else: br_score = 5  # unknown

# Sample rate score
if sr >= 48000: sr_score = 10
elif sr >= 44100: sr_score = 9
elif sr >= 32000: sr_score = 7
elif sr >= 22050: sr_score = 5
elif sr > 0: sr_score = 2
else: sr_score = 5  # unknown

# Bandwidth score (max audio freq in Hz)
if bw >= 18000: bw_score = 10
elif bw >= 15000: bw_score = 9
elif bw >= 12000: bw_score = 7
elif bw >= 8000: bw_score = 4
elif bw > 0: bw_score = 2
else: bw_score = 5  # unknown

# Weighted total
total = (codec_score * 0.25 + br_score * 0.25 + sr_score * 0.2 + bw_score * 0.3)

# Grade
if total >= 9.5: grade = "A+"
elif total >= 9.0: grade = "A"
elif total >= 8.5: grade = "A-"
elif total >= 8.0: grade = "B+"
elif total >= 7.5: grade = "B"
elif total >= 7.0: grade = "B-"
elif total >= 6.5: grade = "C+"
elif total >= 6.0: grade = "C"
elif total >= 5.5: grade = "C-"
elif total >= 5.0: grade = "D"
else: grade = "F"

# Description
if total >= 8.5:
    desc = "excellent"
elif total >= 7.5:
    desc = "good"
elif total >= 6.5:
    desc = "acceptable"
elif total >= 5.0:
    desc = "low quality"
else:
    desc = "poor"

# Bandwidth label
if bw > 0:
    if bw >= 18000: bw_label = f"{bw/1000:.0f}kHz (hi-fi)"
    elif bw >= 15000: bw_label = f"{bw/1000:.0f}kHz (good)"
    elif bw >= 12000: bw_label = f"{bw/1000:.0f}kHz (FM radio)"
    elif bw >= 8000: bw_label = f"{bw/1000:.0f}kHz (AM radio)"
    else: bw_label = f"{bw/1000:.0f}kHz (phone quality)"
else:
    bw_label = "unknown"

# Bitrate label
if abr_kbps > 0:
    br_label = f"{abr_kbps}kbps"
else:
    br_label = "unknown"

# Build output
out.append(f"🎵 Source: {grade} ({desc})")
out.append(f"   Codec: {acodec.upper()} | Bitrate: {br_label} | SR: {sr}Hz | Bandwidth: {bw_label}")
if bw > 0 and bw < 10000:
    out.append(f"   ⚠️ Audio bandwidth rendah — kualitas terbatas")

print("\n".join(out))
PYEOF
    )
  echo "SOURCE_QUALITY<<RUSEMEVA_EOF" >> $GITHUB_ENV
  echo "$SOURCE_QUALITY" >> $GITHUB_ENV
  echo "RUSEMEVA_EOF" >> $GITHUB_ENV
  # === BITRATE VARIANCE SPARKLINE (packet metadata, no decode) ===
  BITRATE_SPARK=""
  if [ "${HDUR_INT:-0}" -ge 60 ] 2>/dev/null; then
    echo "📈 Bitrate variance probe..."
    timeout 60 ffprobe -v error -select_streams v:0 \
      -show_entries packet=pts_time,size -of json "$HEVC_FILE" \
      > /tmp/rusemeva_packets.json 2>/dev/null || true
    BITRATE_SPARK=$(python3 - /tmp/rusemeva_packets.json "$HDUR_INT" <<'PYEOF'
import json, sys
pkt_path = sys.argv[1]
dur = int(sys.argv[2]) if len(sys.argv) > 2 else 0
try:
    with open(pkt_path) as f:
        data = json.load(f)
    packets = data.get("packets", [])
    if not packets or dur <= 0:
        sys.exit(0)
    bucket_sec = max(30, dur // 40)
    n_buckets = max(1, dur // bucket_sec)
    buckets = [0.0] * n_buckets
    for p in packets:
        try:
            t = float(p.get("pts_time", 0))
            sz = int(p.get("size", 0))
        except:
            continue
        idx = int(t // bucket_sec)
        if 0 <= idx < n_buckets:
            buckets[idx] += sz
    kbuckets = [(b * 8 / bucket_sec / 1000) for b in buckets]
    if not kbuckets or max(kbuckets) == 0:
        sys.exit(0)
    blocks = "▁▂▃▄▅▆▇█"
    mn, mx = min(kbuckets), max(kbuckets)
    if mx > mn:
        spark = "".join(blocks[min(7, int((v - mn) / (mx - mn) * 7))] for v in kbuckets)
    else:
        spark = blocks[4] * len(kbuckets)
    avg = sum(kbuckets) / len(kbuckets)
    print(spark)
    print(f"min {mn:.0f}k / max {mx:.0f}k / avg {avg:.0f}k kbps")
except:
    pass
PYEOF
    )
    rm -f /tmp/rusemeva_packets.json 2>/dev/null || true
  fi
  echo "BITRATE_SPARK<<RUSEMEVA_EOF" >> $GITHUB_ENV
  echo "$BITRATE_SPARK" >> $GITHUB_ENV
  echo "RUSEMEVA_EOF" >> $GITHUB_ENV
  # === #7 KALIBRASI: hitung realtime_x aktual & kirim ke worker (KV) ===
  ENC_ELAPSED=$(( SECONDS - ENC_START ))
  echo "ENC_ELAPSED=$ENC_ELAPSED" >> $GITHUB_ENV
  echo "SCENE_LABEL=${SCENE_LABEL:-normal}" >> $GITHUB_ENV
  echo "LIVE_MODE=${LIVE_MODE:-0}" >> $GITHUB_ENV
  if [ "$HDUR_INT" -gt 0 ] && [ "$ENC_ELAPSED" -gt 0 ]; then
    ACT_RT=$(awk "BEGIN{printf \"%.4f\", $HDUR_INT / $ENC_ELAPSED}")
    echo "🎯 realtime_x aktual: ${ACT_RT}x (video ${HDUR_INT}s / encode ${ENC_ELAPSED}s)"
    # Kirim ke worker biar disimpan + di-rata-rata ke KV
    curl -fsS --retry 2 --retry-delay 3 -X POST "${WORKER_URL:-https://rusemeva.rusemeva-vault.workers.dev}/rtcal" \
      -H "Content-Type: application/json" \
      -d "{\"preset\":\"${HEVC_PRESET}\",\"rt\":${ACT_RT},\"secret\":\"${PROGRESS_SECRET}\"}" 2>/dev/null \
      || echo "⚠️ Gagal kirim kalibrasi ke worker (non-fatal)."
    true  # pastikan block ini selalu return 0
  fi
else
  echo "⚠️ Encode HEVC gagal."
  # === #5 ERROR CLASSIFICATION: deteksi penyebab gagal biar notif jujur ===
  # Cek log encode untuk kata kunci umum
  REASON="unknown"
  if grep -qiE "No space left on device|disk full|ENOSPC" "$HEVC_LOG" 2>/dev/null; then
    REASON="disk_full"
  elif grep -qiE "Codec .* not found|Unknown encoder|libx265|Unable to find a suitable output|Invalid data found|moov atom not found" "$HEVC_LOG" 2>/dev/null; then
    REASON="codec_or_corrupt"
  elif grep -qiE "Timeout|timed out|killed|Signal 9|SIGKILL" "$HEVC_LOG" 2>/dev/null; then
    REASON="timeout_or_killed"
  elif grep -qiE "Conversion failed|Error .* frames|Denominator" "$HEVC_LOG" 2>/dev/null; then
    REASON="ffmpeg_error"
  fi
  echo "FAIL_REASON=$REASON" >> $GITHUB_ENV
  echo "🔍 FAIL_REASON=$REASON"
fi

