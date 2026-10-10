#!/usr/bin/env bash
# Full pipeline: voice-over -> motion graphics -> soundtrack -> final MP4 (+ SRT).
#   ./make.sh            build everything
#   SKIP_TTS=1 ./make.sh reuse the voice takes in vo/ (e.g. after editing visuals only)
set -euo pipefail
cd "$(dirname "$0")"

REL=https://github.com/k2-fsa/sherpa-onnx/releases/download
VOICE=models/vits-piper-ar_JO-kareem-medium
VOICE_FR=models/vits-piper-fr_FR-upmc-medium
ASR=models/sherpa-onnx-whisper-turbo
OUT=output/riadh_el_andalous_ar.mp4

pip install -q sherpa-onnx soundfile scipy numpy pillow

fetch() {  # fetch <dir> <url>
  [ -d "$1" ] || { mkdir -p models; curl -sSL "$2" | tar xj -C models; }
}

if [ -z "${SKIP_TTS:-}" ]; then
  fetch "$VOICE" "$REL/tts-models/vits-piper-ar_JO-kareem-medium.tar.bz2"
  fetch "$VOICE_FR" "$REL/tts-models/vits-piper-fr_FR-upmc-medium.tar.bz2"
  fetch "$ASR" "$REL/asr-models/sherpa-onnx-whisper-turbo.tar.bz2"
  python3 tts.py --voice-dir "$VOICE" --fr-voice-dir "$VOICE_FR" --asr-dir "$ASR" --takes 6
fi

python3 render.py
python3 audio.py

mkdir -p output
ffmpeg -y -loglevel error -i build/video_silent.mp4 -i build/mix.wav \
  -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest -movflags +faststart \
  -metadata title="رياض الأندلس – إقامة راقية" "$OUT"
cp build/subtitles_ar.srt output/riadh_el_andalous_ar.srt
echo "done -> $OUT"
