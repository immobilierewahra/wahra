#!/usr/bin/env bash
# Full pipeline: voice-over -> motion graphics -> soundtrack -> final MP4 (+ SRT).
#   ./make.sh                 long version  (script.json     -> output/riadh_el_andalous_ar.mp4)
#   ./make.sh 30s             30-second cut (script_30s.json -> output/riadh_el_andalous_ar_30s.mp4)
#   ./make.sh voix            recorded voice-over (script_voix.json + assets/voix_off.mp3 -> output/..._voix.mp4)
#   SKIP_TTS=1 ./make.sh 30s  reuse the voice takes already in vo*/ (e.g. after editing visuals only)
# Voice engine: ElevenLabs when ELEVENLABS_API_KEY is set (optional ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL),
# otherwise the offline Piper voices.
set -euo pipefail
cd "$(dirname "$0")"
export VIDEO_VARIANT="${1:-}"

REL=https://github.com/k2-fsa/sherpa-onnx/releases/download
VOICE=models/vits-piper-ar_JO-kareem-medium
VOICE_FR=models/vits-piper-fr_FR-upmc-medium
ASR=models/sherpa-onnx-whisper-turbo

pip install -q sherpa-onnx soundfile scipy numpy pillow

fetch() {  # fetch <dir> <url>
  [ -d "$1" ] || { mkdir -p models; curl -sSL "$2" | tar xj -C models; }
}

if python3 -c "import sys, timeline as T; sys.exit(0 if 'voice_file' in T.read_script() else 1)"; then
  python3 import_voice.py          # recorded voice: cut it into timed phrases, no synthesis
elif [ -z "${SKIP_TTS:-}" ]; then
  fetch "$ASR" "$REL/asr-models/sherpa-onnx-whisper-turbo.tar.bz2"
  if [ -n "${ELEVENLABS_API_KEY:-}" ]; then
    python3 tts.py --engine elevenlabs --asr-dir "$ASR"
  else
    fetch "$VOICE" "$REL/tts-models/vits-piper-ar_JO-kareem-medium.tar.bz2"
    fetch "$VOICE_FR" "$REL/tts-models/vits-piper-fr_FR-upmc-medium.tar.bz2"
    python3 tts.py --voice-dir "$VOICE" --fr-voice-dir "$VOICE_FR" --asr-dir "$ASR" --takes 8
  fi
fi

python3 render.py
python3 audio.py

OUT=$(python3 -c "import timeline as T; print(T.OUTPUT)")
BUILD=$(python3 -c "import timeline as T; print(T.BUILD)")
mkdir -p output
ffmpeg -y -loglevel error -i "$BUILD/video_silent.mp4" -i "$BUILD/mix.wav" \
  -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest -movflags +faststart \
  -metadata title="رياض الأندلس – إقامة راقية" "$OUT"
cp "$BUILD/subtitles_ar.srt" "${OUT%.mp4}.srt"
echo "done -> $OUT"
