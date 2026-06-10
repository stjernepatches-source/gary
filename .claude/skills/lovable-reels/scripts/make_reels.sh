#!/usr/bin/env bash
#
# make_reels.sh — Lag split-screen reels: topp-klipp + reaksjonsopptak (øverst/nederst)
# etterfulgt av et fast slutt-klipp (Lovable/CTA).
#
# Output: 1080x1920, 60fps, ~21 Mbps, SDR (bt709), AAC 160k. Reaksjonslyd er AV.
#
# Bruk:
#   make_reels.sh --top TOP.mov --react REACT.mov --final FINAL.mov \
#                 [--outdir DIR] [--count N] [--start SEK] [--seg SEK] [--react-mute]
#
# Argumenter:
#   --top        Klippet som vises ØVERST i split-screen (skaleres til 1080x1008).
#   --react      Reaksjonsopptaket (langt). Hvert reel klipper ut et SEG-sekunders
#                utsnitt herfra, øverst-ned vstacket under toppen (1080x912).
#   --final      Fast slutt-klipp som limes på etter split-delen (skaleres 1080x1920).
#   --outdir     Output-mappe (default: ./output_reels).
#   --count      Antall reels (default: 10).
#   --start      Starttid (sek) for FØRSTE reel inn i reaksjonsopptaket (default: 2).
#   --seg        Lengde (sek) på reaksjonsutsnittet per reel (default: 14.033333).
#   --react-mute Sett reaksjonslyd av (default PÅ-av; reaksjonslyd er alltid av her).
#
# TIPS for å unngå identiske klipp mellom batcher:
#   Kjør hver batch med ulik --start (f.eks. 2, så 7, så 12). Da starter ingen klipp
#   på samme tid, og hvert utsnitt overlapper bare delvis med tidligere batcher.

set -euo pipefail

TOP="" ; REACT="" ; FINAL=""
OUTDIR="./output_reels"
COUNT=10
START=2
SEG=14.033333

while [[ $# -gt 0 ]]; do
  case "$1" in
    --top)    TOP="$2"; shift 2;;
    --react)  REACT="$2"; shift 2;;
    --final)  FINAL="$2"; shift 2;;
    --outdir) OUTDIR="$2"; shift 2;;
    --count)  COUNT="$2"; shift 2;;
    --start)  START="$2"; shift 2;;
    --seg)    SEG="$2"; shift 2;;
    --react-mute) shift 1;;   # reaksjonslyd er alltid av; flagget tas for kompatibilitet
    -h|--help) sed -n '2,30p' "$0"; exit 0;;
    *) echo "Ukjent argument: $1" >&2; exit 1;;
  esac
done

# --- Validering ---
for v in TOP REACT FINAL; do
  if [[ -z "${!v}" ]]; then echo "Mangler --${v,,}" >&2; exit 1; fi
done
for f in "$TOP" "$REACT" "$FINAL"; do
  if [[ ! -f "$f" ]]; then echo "Finner ikke fil: $f" >&2; exit 1; fi
done
command -v ffmpeg >/dev/null || { echo "ffmpeg er ikke installert" >&2; exit 1; }
command -v ffprobe >/dev/null || { echo "ffprobe er ikke installert" >&2; exit 1; }

# --- Sjekk at reaksjonsopptaket er langt nok ---
RDUR=$(ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 "$REACT")
LAST_END=$(echo "$START + ($COUNT - 1) * $SEG + $SEG" | bc -l)
if (( $(echo "$LAST_END > $RDUR" | bc -l) )); then
  echo "ADVARSEL: siste klipp slutter på ${LAST_END}s men reaksjonsopptaket er bare ${RDUR}s." >&2
  echo "Reduser --count, --start eller --seg." >&2
  exit 1
fi

# --- Diskplass-sjekk (grovt: ~85 MB per reel) ---
NEED=$(( COUNT * 90 ))
FREE=$(df -m / | tail -1 | awk '{print $4}')
echo "Diskplass: ${FREE}MB ledig, trenger ca ${NEED}MB for $COUNT reels."
if (( FREE < NEED )); then
  echo "ADVARSEL: kan være for lite diskplass. Frigjør plass eller senk --count." >&2
fi

mkdir -p "$OUTDIR"

FILT="[1:v]trim=duration=${SEG},setpts=PTS-STARTPTS,scale=1080:912:force_original_aspect_ratio=increase,crop=1080:912:(iw-1080)/2:(ih-912)/2,setpts=PTS-STARTPTS[react];[0:v]scale=1080:1008,setpts=PTS-STARTPTS[top];[top][react]vstack=inputs=2[split];[split]fps=60,format=yuv420p,setsar=1[splitv];[2:v]scale=1080:1920,fps=60,format=yuv420p,setsar=1[hf];[splitv][0:a][hf][2:a]concat=n=2:v=1:a=1[outv][outa]"

echo "Lager $COUNT reels -> $OUTDIR (start=${START}s, seg=${SEG}s)"
i=1
while (( i <= COUNT )); do
  st=$(echo "$START + ($i - 1) * $SEG" | bc -l)
  tag=$(printf "%.0f" "$st")
  out=$(printf "%s/reel_%03d_t%s.mp4" "$OUTDIR" "$i" "$tag")
  echo "[$i/$COUNT] reaksjon-start=${st}s -> $out"
  ffmpeg -y -hide_banner -loglevel error \
    -i "$TOP" -ss "$st" -i "$REACT" -i "$FINAL" \
    -filter_complex "$FILT" -map "[outv]" -map "[outa]" \
    -c:v libx264 -preset medium -b:v 21M -maxrate 21M -bufsize 42M \
    -pix_fmt yuv420p -colorspace bt709 -color_primaries bt709 -color_trc bt709 -r 60 \
    -c:a aac -b:a 160k -ar 44100 -movflags +faststart "$out"
  echo "   ferdig: $(ls -la "$out" | awk '{printf "%.0fMB\n", $5/1048576}')"
  i=$((i+1))
done

echo "FERDIG. $(ls "$OUTDIR"/reel_*.mp4 2>/dev/null | wc -l | tr -d ' ') reels i $OUTDIR"
