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
ORIG_TOTAL_BPS=$(probe_bitrate "$FILE" || echo 0)
HEVC_SKIP=0
if [ "${ORIG_TOTAL_BPS:-0}" -gt 0 ] 2>/dev/null && [ "${ORIG_TOTAL_BPS:-0}" -le 1500000 ] 2>/dev/null; then
  HEVC_SKIP=1
  HEVC_FILE="$FILE"
  ORIG_MB=$(( ORIG_TOTAL_BPS / 125000 ))
  ORIG_TENTH=$(( (ORIG_TOTAL_BPS / 125000) % 10 ))
  echo "⏭️ Original sudah efisien (~${ORIG_MB}.${ORIG_TENTH} Mbps) — skip HEVC encode"
  CHAT_ID="$CHAT_ID" TG_API_URL="$TG_API_URL" BOT_TOKEN="$BOT_TOKEN" python3 scripts/send_message.py \
    "⏭️ <b>HEVC skip</b> — original sudah efisien (~${ORIG_MB}.${ORIG_TENTH} Mbps). Kirim original langsung." || true
fi
echo "HEVC_SKIP=$HEVC_SKIP" >> $GITHUB_ENV

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
    [ "$HEVC_CRF" -lt 22 ] && HEVC_CRF=22
    [ "$HEVC_CRF" -gt 28 ] && HEVC_CRF=28
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
  X265_PARAMS="aq-mode=3:aq-strength=1.0:rd=3:psy-rd=1.5:psy-rdoq=1.0:rc-lookahead=40:scenecut=40"
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
"$FFMPEG_STATIC" -hide_banner -y -i "$FILE" \
  "${LIVE_VF_ARGS[@]}" \
  -c:v libx265 -profile:v main10 -pix_fmt yuv420p10le \
  -crf ${HEVC_CRF} -preset ${HEVC_PRESET} -maxrate ${MAXRATE_K:-1450}k -bufsize ${BUFSIZE_K:-2900}k \
  -x265-params "${X265_PARAMS}" -tag:v hvc1 \
  -c:a copy -progress pipe:3 "$HEVC_FILE" \
  3> >(while IFS='=' read -r k v; do
    if [ "$k" = "out_time_ms" ]; then
      ms=${v%.*}
      [ "$ms" -gt 0 ] 2>/dev/null || continue
      cur=$(( ms / 1000000 ))
      pct=$(( (cur * 100) / SRC_DUR_INT )); [ "$pct" -gt 100 ] && pct=100
      if [ "$pct" != "$LAST_PCT" ]; then
        LAST_PCT=$pct
        echo "🔄 HEVC encode ${pct}%"
        CHAT_ID="$CHAT_ID" FILENAME="$FILE" TG_API_URL="$TG_API_URL" BOT_TOKEN="$BOT_TOKEN" PROGRESS_MSG_FILE=/tmp/rusemeva_progress_msg_id PROGRESS_STATE_FILE=/tmp/rusemeva_progress_state SRC_DUR_SEC="$SRC_DUR_INT" python3 scripts/progress.py progress "$pct" || true
      fi
    fi
  done) \
  > "$HEVC_LOG" 2>&1
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
      -c:v libx265 -profile:v main10 -pix_fmt yuv420p10le \
      -crf ${CUR_CRF} -preset ${HEVC_PRESET} -maxrate ${MAXRATE_K:-1450}k -bufsize ${BUFSIZE_K:-2900}k \
      -x265-params "${X265_PARAMS:-aq-mode=3:aq-strength=1.0}" -tag:v hvc1 \
      -c:a copy -progress pipe:3 "$HEVC_FILE" \
      3> >(while IFS='=' read -r k v; do
        if [ "$k" = "out_time_ms" ]; then
          ms=${v%.*}
          [ "$ms" -gt 0 ] 2>/dev/null || continue
          cur=$(( ms / 1000000 ))
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
  HEVC_THUMB="${HEVC_FILE%.mp4}.jpg"
  HSEEK=1; [ "$HDUR_INT" -gt 6 ] && HSEEK=$((HDUR_INT/2))
  "$FFMPEG_STATIC" -hide_banner -loglevel error -y -ss "$HSEEK" -i "$HEVC_FILE" -frames:v 1 -q:v 2 -vf "scale=640:-2" "$HEVC_THUMB" 2>/dev/null || true
  [ ! -s "$HEVC_THUMB" ] && "$FFMPEG_STATIC" -hide_banner -loglevel error -y -ss 1 -i "$HEVC_FILE" -frames:v 1 -q:v 2 -vf "scale=640:-2" "$HEVC_THUMB" 2>/dev/null || true
  if [ -s "$HEVC_THUMB" ]; then echo "HEVC_THUMB_FILE=$HEVC_THUMB" >> $GITHUB_ENV; echo "HAS_HEVC_THUMB=1" >> $GITHUB_ENV; else echo "HAS_HEVC_THUMB=0" >> $GITHUB_ENV; fi
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
  echo "LOUDNESS_TEXT<<RUSEMEVA_EOF" >> $GITHUB_ENV
  echo "$LOUDNESS_TEXT" >> $GITHUB_ENV
  echo "RUSEMEVA_EOF" >> $GITHUB_ENV
  # === ENCODE EFFICIENCY SCORE ===
  EFFICIENCY_TEXT=""
  HEVC_BYTES_F=$(stat -c%s "$HEVC_FILE" 2>/dev/null || wc -c < "$HEVC_FILE")
  if [ "${ORIG_BYTES:-0}" -gt 0 ] && [ "${HEVC_BYTES_F:-0}" -gt 0 ]; then
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
print("\n".join(out))
PYEOF
    )
  fi
  echo "EFFICIENCY_TEXT<<RUSEMEVA_EOF" >> $GITHUB_ENV
  echo "$EFFICIENCY_TEXT" >> $GITHUB_ENV
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

