#!/usr/bin/env bash
# make_from_link.sh — paste a reel URL (Instagram / TikTok / YouTube / etc.), download it,
# and render split-screen reels from it as the hook. Replaces the manual
# "paste link into fastvideosave.net, download, then run render_reels.sh" dance.
#
#   make_from_link.sh --url "https://www.instagram.com/reel/XXXX/"
#
# Downloads to ./hooks/, then calls render_reels.sh with that file as --hook.
# Any extra flags after the known ones are passed straight through to render_reels.sh
# (e.g. --core, --count, --seg, --start-index, --dry-run).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RENDER="$HERE/render_reels.sh"

URL=""; HOOKDIR="./hooks"; OUTDIR="./output"; COOKIES=""; DOWNLOAD_ONLY=0
PASS=()   # forwarded to render_reels.sh

usage() {
  cat <<EOF
Usage: make_from_link.sh --url URL [options] [-- render_reels.sh flags]
  --url URL            Reel link to download (Instagram/TikTok/YouTube/...). Required.
  --hookdir DIR        Where to save the download (default: ./hooks)
  --outdir DIR         Reel output dir, forwarded to render_reels.sh (default: ./output)
  --cookies BROWSER    Force cookies from a browser (chrome|brave|safari|edge|firefox|chromium).
                       Default: try anonymous, then auto-fall back to browser cookies.
  --download-only      Just download the clip; skip rendering.
  -h, --help           This help.

Everything else (e.g. --core, --count, --seg, --dry-run) is forwarded to render_reels.sh.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --url) URL="$2"; shift 2;;
    --hookdir) HOOKDIR="$2"; shift 2;;
    --outdir) OUTDIR="$2"; PASS+=(--outdir "$2"); shift 2;;
    --cookies) COOKIES="$2"; shift 2;;
    --download-only) DOWNLOAD_ONLY=1; shift;;
    -h|--help) usage; exit 0;;
    --) shift; while [ $# -gt 0 ]; do PASS+=("$1"); shift; done;;
    *) PASS+=("$1"); shift;;
  esac
done

[ -n "$URL" ] || { echo "ERROR: --url is required" >&2; usage; exit 2; }
command -v ffmpeg >/dev/null || { echo "ffmpeg not found" >&2; exit 1; }
python3 -c "import yt_dlp" 2>/dev/null || { echo "ERROR: yt-dlp not installed (pip install yt-dlp)" >&2; exit 1; }
mkdir -p "$HOOKDIR"

# Download via yt-dlp. Prints the final file path on the last stdout line.
# Strategy: try anonymous first; if that fails, retry pulling login cookies from the
# user's browser(s) — Instagram usually needs this. --cookies forces one browser.
ERRDIR="$(mktemp -d)"
trap 'rm -rf "$ERRDIR"' EXIT
try_dl() {
  local cookarg="$1"
  local ydl=(python3 -m yt_dlp --no-warnings --no-playlist
             --merge-output-format mp4
             -f "best[ext=mp4]/bestvideo*+bestaudio/best"
             -o "$HOOKDIR/clip_%(id)s.%(ext)s"
             --print after_move:filepath)
  [ -n "$cookarg" ] && ydl+=(--cookies-from-browser "$cookarg")
  "${ydl[@]}" "$URL" 2>"$ERRDIR/${cookarg:-anon}.err" | tail -n1
}

# Build fallback order: --cookies overrides; otherwise anonymous, then whichever
# browsers are actually installed (Chrome/Safari on this Mac), most-likely first.
if [ -n "$COOKIES" ]; then
  STRATS=("$COOKIES")
else
  STRATS=("")
  [ -d "$HOME/Library/Application Support/Google/Chrome" ] && STRATS+=(chrome)
  [ -d "$HOME/Library/Application Support/BraveSoftware/Brave-Browser/Default" ] && STRATS+=(brave)
  [ -d "$HOME/Library/Application Support/Microsoft Edge/Default" ] && STRATS+=(edge)
  ls "$HOME/Library/Containers/com.apple.Safari/Data/Library/Cookies/" >/dev/null 2>&1 && STRATS+=(safari)
  [ -d "$HOME/Library/Application Support/Firefox/Profiles" ] && STRATS+=(firefox)
fi

FILE=""
for s in "${STRATS[@]}"; do
  label="${s:-anonymous}"
  echo "↓ downloading ($label): $URL" >&2
  if out=$(try_dl "$s") && [ -n "$out" ] && [ -f "$out" ]; then
    FILE="$out"; echo "✓ got: $FILE  (via $label)" >&2; break
  fi
done

if [ -z "$FILE" ]; then
  echo "ERROR: could not download $URL" >&2
  echo "--- yt-dlp error (anonymous attempt) ---" >&2
  grep -iv "NotOpenSSLWarning\|warnings.warn\|Deprecated\|urllib3" "$ERRDIR/anon.err" 2>/dev/null | tail -n 4 >&2 || true
  echo "Tip: log into Instagram in Chrome, or pass --cookies chrome (Chrome must be fully closed for macOS to release the cookie DB)." >&2
  exit 1
fi

if [ "$DOWNLOAD_ONLY" -eq 1 ]; then
  echo "$FILE"
  exit 0
fi

echo "→ rendering reels from $FILE" >&2
"$RENDER" --hook "$FILE" "${PASS[@]}"
