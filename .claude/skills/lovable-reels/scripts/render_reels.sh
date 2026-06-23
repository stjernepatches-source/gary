#!/usr/bin/env bash
# render_reels.sh — codifies the CURRENT split-screen reel pipeline.
#
# Layout per reel (1080x1920, 60fps):
#   0..SPLIT s : top = core (cropped to TOP_H) + bottom = a SEG-second hook slice (HOOK_H), stacked.
#   SPLIT..end : core full-screen "reveal".
# Audio = core only (hook audio is dropped). One SEG-second hook slice = one reel; a long hook
# is sliced into multiple reels (starts 0, SEG, 2*SEG, ...). Output files continue the numeric
# N.mp4 sequence in --outdir.
#
# NOTE: this REPLACES the older make_reels.sh geometry (1080x1008/912 top/react/final). That script
# is legacy; use this one.
set -euo pipefail

CORE=""; HOOK=""; OUTDIR="./output"
COUNT="auto"; SEG=14; SPLIT=14; TOP_H=910; HOOK_H=1010
START_INDEX="auto"; DRYRUN=0

usage() {
  cat <<EOF
Usage: render_reels.sh --hook CLIP [options]
  --core PATH         Core video (default: ./core_new4.mp4)
  --hook PATH         Hook/B-roll clip to slice (required)
  --outdir DIR        Output dir (default: ./output)
  --count N|auto      Number of SEG-second hooks to cut (default: auto = floor(hook_dur/SEG))
  --seg S             Hook slice length seconds (default: 14)
  --split-sec S       When core cuts to reveal (default: 14)
  --top-h PX          Top (core) crop height (default: 910)
  --hook-h PX         Bottom (hook) crop height (default: 1010)   [top-h + hook-h must == 1920]
  --start-index N|auto First output number (default: auto = max existing N.mp4 + 1)
  --dry-run           Print the ffmpeg commands without rendering
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --core) CORE="$2"; shift 2;;
    --hook) HOOK="$2"; shift 2;;
    --outdir) OUTDIR="$2"; shift 2;;
    --count) COUNT="$2"; shift 2;;
    --seg) SEG="$2"; shift 2;;
    --split-sec) SPLIT="$2"; shift 2;;
    --top-h) TOP_H="$2"; shift 2;;
    --hook-h) HOOK_H="$2"; shift 2;;
    --start-index) START_INDEX="$2"; shift 2;;
    --dry-run) DRYRUN=1; shift;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2;;
  esac
done

[ -z "$CORE" ] && CORE="./core_new4.mp4"
command -v ffmpeg >/dev/null  || { echo "ffmpeg not found" >&2; exit 1; }
command -v ffprobe >/dev/null || { echo "ffprobe not found" >&2; exit 1; }
[ -n "$HOOK" ] || { echo "ERROR: --hook is required" >&2; usage; exit 2; }
[ -f "$CORE" ] || { echo "ERROR: core not found: $CORE" >&2; exit 1; }
[ -f "$HOOK" ] || { echo "ERROR: hook not found: $HOOK" >&2; exit 1; }
[ $((TOP_H + HOOK_H)) -eq 1920 ] || { echo "ERROR: top-h ($TOP_H) + hook-h ($HOOK_H) must equal 1920" >&2; exit 1; }
mkdir -p "$OUTDIR"

# hook duration -> auto count
HOOK_DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$HOOK" | cut -d. -f1)
[ -n "$HOOK_DUR" ] || HOOK_DUR=0
if [ "$COUNT" = "auto" ]; then
  COUNT=$(( HOOK_DUR / SEG ))
  [ "$COUNT" -lt 1 ] && COUNT=1
fi

# start index = max existing numeric N.mp4 + 1
if [ "$START_INDEX" = "auto" ]; then
  MAX=0
  for f in "$OUTDIR"/*.mp4; do
    [ -e "$f" ] || continue
    b=$(basename "$f" .mp4)
    case "$b" in (*[!0-9]*) continue;; esac
    [ "$b" -gt "$MAX" ] && MAX="$b"
  done
  START_INDEX=$((MAX + 1))
fi

# disk guard: ~90 MB/reel
NEED_MB=$(( COUNT * 90 + 200 ))
FREE_MB=$(df -m "$OUTDIR" | awk 'NR==2{print $4}')
if [ "${FREE_MB:-0}" -lt "$NEED_MB" ]; then
  echo "ERROR: low disk. Need ~${NEED_MB}MB, have ${FREE_MB}MB free. Free space (delete old big*/uploaded output reels) and retry." >&2
  exit 1
fi

echo "core=$CORE hook=$HOOK dur=${HOOK_DUR}s -> count=$COUNT  start=$START_INDEX  outdir=$OUTDIR"

ENC=(-c:v libx264 -preset medium -b:v 21M -maxrate 21M -bufsize 42M -pix_fmt yuv420p -r 60 \
     -colorspace bt709 -color_primaries bt709 -color_trc bt709 \
     -c:a aac -b:a 160k -ar 44100 -movflags +faststart)

k=0
while [ "$k" -lt "$COUNT" ]; do
  START=$(( k * SEG )); END=$(( START + SEG )); IDX=$(( START_INDEX + k )); OUT="$OUTDIR/$IDX.mp4"
  FG="[0:v]scale=1080:1920,setsar=1,split=2[v0a][v0b];\
[v0a]trim=0:${SPLIT},setpts=PTS-STARTPTS,crop=1080:${TOP_H}:0:0,setsar=1[top];\
[1:v]trim=${START}:${END},setpts=PTS-STARTPTS,fps=60,scale=1080:${HOOK_H}:force_original_aspect_ratio=increase,crop=1080:${HOOK_H},setsar=1[hook];\
[top][hook]vstack=inputs=2,format=yuv420p[p1];\
[v0b]trim=${SPLIT},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[c2];\
[p1][c2]concat=n=2:v=1:a=0[outv]"
  if [ "$DRYRUN" -eq 1 ]; then
    echo "[dry-run] -> $OUT  (hook ${START}-${END}s)"
  else
    ffmpeg -y -hide_banner -loglevel error -i "$CORE" -i "$HOOK" -filter_complex "$FG" \
      -map "[outv]" -map 0:a "${ENC[@]}" "$OUT" && echo "OK -> $OUT" || echo "FAIL -> $OUT" >&2
  fi
  k=$(( k + 1 ))
done
