#!/usr/bin/env python3
"""
fetch_brolls.py — auto-source HD, "no-text" B-roll clips for the bottom hook of split-screen reels.

Sources:
  tiktok  (default, FREE via tikwm.com) — 720-1080p no-watermark. Recommended.
  youtube (fallback)                    — 360p only (YouTube SABR-caps yt-dlp). Use only if TikTok is down.

The bottom hook panel is ~square (1080x1010), so the render script cover-crops any aspect. Hook audio
is dropped from the reel (so the clip's MUSIC never reaches the output; the visual is still reused —
prefer scenery/action, no faces). An optional RapidOCR pass auto-drops clips with burned-in text.

Pipeline: download long clips -> (optional) render each into floor(dur/SEG) reels via render_reels.sh.

Examples:
  python3 fetch_brolls.py --tiktok-search "fpv drone" --n 12 --max-clips 6
  python3 fetch_brolls.py --queries-file brolls/sources.txt --max-clips 10 --render \
      --core core_new4.mp4 --render-outdir output
  python3 fetch_brolls.py --tiktok-url https://www.tiktok.com/@joe.fpv/video/123 --render
"""
import argparse, json, os, shutil, subprocess, sys, time, glob, urllib.parse
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Missing dependency: python3 -m pip install requests")

HERE = Path(__file__).resolve().parent
RENDER_SH = HERE / "render_reels.sh"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
TIKWM = "https://www.tikwm.com"
S = requests.Session(); S.headers.update({"User-Agent": UA})

# Default clean, no-text, motion-rich TikTok search terms (used if no --tiktok-search/--queries-file).
DEFAULT_QUERIES = [
    "fpv drone", "cinematic fpv", "drone view", "pov gopro", "downhill mtb pov",
    "ski pov", "snowboard pov", "pov walk city", "surfing pov", "aerial nature",
    # food is part of the default mix (clean raw cooking b-roll, no text/talking):
    "cooking asmr no talking", "raw cooking process cinematic", "street food closeup",
    "chef plating fine dining", "satisfying food preparation closeup",
]

# ---------------- helpers ----------------
def run(cmd, **kw): return subprocess.run(cmd, **kw)

def free_gb(path="/"): return shutil.disk_usage(path).free / 1e9

def ffprobe_dim_dur(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.split()
    w = h = dur = None
    for tok in out:
        if "," in tok: w, h = (int(x) for x in tok.split(",")[:2])
        else:
            try: dur = float(tok)
            except ValueError: pass
    return w, h, dur

def download(url, dest):
    with S.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        tmp = str(dest) + ".part"
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    os.replace(tmp, dest)

# ---------------- OCR no-text gate (graceful: passes everything if RapidOCR absent) ----------------
_OCR = None
def _get_ocr():
    global _OCR
    if _OCR is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _OCR = RapidOCR()
        except Exception:
            _OCR = False
            print("  (note: rapidocr not installed -> skipping no-text filter; "
                  "pip install rapidocr-onnxruntime to enable)", file=sys.stderr)
    return _OCR

def has_burned_text(path, dur, max_chars=8):
    """True if sampled frames contain enough confident text to count as captioned.
    Samples EARLY frames too (intro captions) at decent resolution."""
    ocr = _get_ocr()
    if not ocr:
        return False  # can't tell -> don't drop
    chars = 0
    for frac in (0.02, 0.06, 0.12, 0.22, 0.35, 0.5, 0.65, 0.8, 0.92):
        t = max(0.0, (dur or 1) * frac)
        png = f"/tmp/_ocr_{os.getpid()}.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t}", "-i", str(path),
                        "-frames:v", "1", "-vf", "scale=720:-1", png], check=False)
        if not os.path.exists(png):
            continue
        try:
            res, _ = ocr(png)
        except Exception:
            res = None
        if res:
            for _box, text, conf in res:
                t2 = (text or "").strip()
                if conf and conf > 0.4 and len(t2) >= 3:
                    chars += len(t2)
        if chars > max_chars:
            return True
    return False

# ---------------- relevance gate (CLIP zero-shot: raw immersive B-roll vs showcase/talking/static) ----------------
# Catches what OCR can't: a sharp, text-free clip that's still a PRODUCT SHOWCASE / unboxing / talking
# head / static object — not the raw immersive POV/action/scenery we want behind the GaryVee clip.
_CLIP = None
KEEP_PROMPTS = [
    "first person POV action footage",
    "fpv drone flying fast through a landscape",
    "aerial drone footage flying over nature",
    "point of view mountain biking or skiing down a trail",
    "immersive scenery from a moving camera, ocean forest or city",
    "surfing snowboarding or skateboarding action footage",
    # food is part of the default mix:
    "close up of hands cooking and preparing food",
    "food being chopped fried or grilled in a kitchen",
    "cinematic slow motion of sizzling food in a pan",
    "chef plating a dish, fine dining food closeup",
]
DROP_PROMPTS = [
    "a person holding and showing a product to the camera",
    "a drone or gadget sitting still, a product shot",
    "a person talking to the camera, a vlogger or interview",
    "an unboxing, product review or advertisement",
    "a static shot of an object indoors",
    "a screenshot, phone app interface, or text graphic",
    "a person wearing FPV or VR goggles sitting indoors",
    "a person sitting in a room holding a controller",
    "a close-up of a person's face or selfie",
]

def _get_clip():
    global _CLIP
    if _CLIP is None:
        try:
            from fastembed import ImageEmbedding, TextEmbedding
            import numpy as np
            im = ImageEmbedding("Qdrant/clip-ViT-B-32-vision")
            tm = TextEmbedding("Qdrant/clip-ViT-B-32-text")
            te = np.array(list(tm.embed(KEEP_PROMPTS + DROP_PROMPTS)))
            te = te / np.linalg.norm(te, axis=1, keepdims=True)
            _CLIP = (im, te, len(KEEP_PROMPTS), np)
        except Exception as e:
            _CLIP = False
            print(f"  (note: fastembed unavailable -> skipping relevance filter: {e}; "
                  f"pip install fastembed to enable)", file=sys.stderr)
    return _CLIP

def _mean_luma(png):
    """Mean brightness 0-255 of an image, or None if it can't be read."""
    try:
        from PIL import Image
        import numpy as np
        return float(np.asarray(Image.open(png).convert("L")).mean())
    except Exception:
        return None

def is_immersive(path, dur, keep_frac=0.5, min_brightness=32):
    """True if a majority of sampled frames read as raw immersive B-roll
    (not showcase/talking/static) AND the clip isn't mostly dark/low-info."""
    clip = _get_clip()
    if not clip:
        return True  # can't tell -> don't drop
    im, te, nkeep, np = clip
    frames, lumas = [], []
    for frac in (0.1, 0.25, 0.4, 0.55, 0.7, 0.85):
        t = max(0.0, (dur or 1) * frac)
        png = f"/tmp/_rel_{os.getpid()}_{int(frac * 100)}.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t}", "-i", str(path),
                        "-frames:v", "1", "-vf", "scale=336:-1", png], check=False)
        if os.path.exists(png):
            frames.append(png)
            l = _mean_luma(png)
            if l is not None: lumas.append(l)
    if not frames:
        return True
    embs = np.nan_to_num(np.array(list(im.embed(frames)), dtype="float64"))  # kill inf/nan from degenerate frames
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0                      # avoid div-by-zero on black frames
    embs = embs / norms
    sims = np.nan_to_num(embs @ te.T)            # [n_frames, n_prompts]
    keep_votes = sum(1 for i, row in enumerate(sims)
                     if norms[i, 0] > 1e-6 and float(row[:nkeep].max()) >= float(row[nkeep:].max()))
    for f in frames:
        try: os.remove(f)
        except OSError: pass
    # brightness floor: drop clips whose median sampled frame is too dark to be useful B-roll
    if lumas:
        lumas.sort()
        if lumas[len(lumas) // 2] < min_brightness:
            return False
    return keep_votes / len(frames) >= keep_frac

# ---------------- tikwm (TikTok) ----------------
def tikwm_search(keywords, count):
    try:
        r = S.post(TIKWM + "/api/feed/search",
                   data={"keywords": keywords, "count": count, "hd": 1}, timeout=30).json()
    except Exception as e:
        print(f"  tikwm search error [{keywords}]: {e}", file=sys.stderr); return []
    return (r.get("data") or {}).get("videos") or []

def item_to_url(it):
    uid = (it.get("author") or {}).get("unique_id") or ""
    vid = it.get("video_id") or it.get("id") or it.get("aweme_id") or ""
    return (f"https://www.tiktok.com/@{uid}/video/{vid}" if uid and vid else None), str(vid)

def tikwm_hd(tiktok_url):
    """Per-URL HD (no-watermark) info. Returns dict with hdplay/play/duration/id/size."""
    r = S.get(TIKWM + "/api/", params={"url": tiktok_url, "hd": 1}, timeout=30).json()
    return r.get("data") or {}

def discover_tiktok(args):
    """Yield (tiktok_url, video_id) candidates from --tiktok-url, searches, or default queries."""
    seen_ids = set()
    for u in args.tiktok_url:
        vid = u.rstrip("/").split("/")[-1]
        if vid not in seen_ids: seen_ids.add(vid); yield u, vid
    queries = []
    if args.queries_file:
        queries = [q.strip() for q in Path(args.queries_file).read_text().splitlines()
                   if q.strip() and not q.startswith("#")]
    elif args.tiktok_search:
        queries = args.tiktok_search
    elif not args.tiktok_url:
        queries = DEFAULT_QUERIES
    for q in queries:
        for it in tikwm_search(q, args.n):
            url, vid = item_to_url(it)
            if url and vid not in seen_ids:
                seen_ids.add(vid); yield url, vid
        time.sleep(1.2)

# ---------------- youtube fallback (360p) ----------------
def fetch_youtube(args, out, archive):
    queries = (args.tiktok_search or DEFAULT_QUERIES)
    common = [sys.executable, "-m", "yt_dlp",
              "--extractor-args", "youtube:player_client=android",
              "--match-filters", f"duration>={args.min_duration} & duration<={args.max_duration}",
              "-f", "best[ext=mp4]/18/best", "--download-archive", str(archive),
              "--no-warnings", "--ignore-errors", "--sleep-requests", "1",
              "-o", str(out / "yt_%(id)s.%(ext)s")]
    got = []
    for q in queries:
        if len(got) >= args.max_clips: break
        before = set(glob.glob(str(out / "yt_*.mp4")))
        run(common + ["--max-downloads", str(args.max_clips - len(got)), f"ytsearch{args.n}:{q}"])
        got += sorted(set(glob.glob(str(out / "yt_*.mp4"))) - before)
    return got

# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser(description="Fetch HD no-text B-roll for reel hooks.")
    ap.add_argument("--source", choices=["tiktok", "youtube"], default="tiktok")
    ap.add_argument("--tiktok-search", action="append", default=[], help="TikTok search term (repeatable).")
    ap.add_argument("--tiktok-url", action="append", default=[], help="Specific TikTok video URL (repeatable).")
    ap.add_argument("--queries-file", help="File of search terms, one per line (overrides defaults).")
    ap.add_argument("--n", type=int, default=12, help="Candidates to scan per search term (default 12).")
    ap.add_argument("--out", default="./brolls", help="Download dir (default ./brolls).")
    ap.add_argument("--min-duration", type=int, default=20, help="Min clip seconds (default 20).")
    ap.add_argument("--max-duration", type=int, default=600, help="Max clip seconds (default 600).")
    ap.add_argument("--min-height", type=int, default=720, help="Skip clips shorter than this px tall (default 720).")
    ap.add_argument("--max-clips", type=int, default=8, help="Stop after N kept downloads (default 8).")
    ap.add_argument("--max-download-gb", type=float, default=4.0)
    ap.add_argument("--min-free-gb", type=float, default=3.0)
    ap.add_argument("--seg", type=int, default=14, help="Hook slice length for n_hooks math.")
    ap.add_argument("--max-hooks-per-clip", type=int, default=6, help="Cap reels per long clip (default 6).")
    ap.add_argument("--no-ocr", action="store_true", help="Disable the no-text OCR filter.")
    ap.add_argument("--no-relevance", action="store_true",
                    help="Disable the CLIP relevance filter (immersive B-roll vs showcase/talking/static).")
    ap.add_argument("--keep-prompt", action="append", default=[],
                    help="Replace the default KEEP relevance prompts (repeatable) to re-theme the filter, "
                         "e.g. food: --keep-prompt 'close up of hands cooking food'. DROP prompts "
                         "(talking-head/text/product) stay active, so 'no text / no talking' still holds.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--core", default="./core_new4.mp4")
    ap.add_argument("--render-outdir", default="./output")
    args = ap.parse_args()

    if args.keep_prompt:                      # re-theme the relevance filter (e.g. food b-roll)
        global KEEP_PROMPTS
        KEEP_PROMPTS = args.keep_prompt

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    archive = out / "archive.txt"            # youtube (yt-dlp) dedupe
    seen_file = out / "seen_tiktok.txt"      # tiktok dedupe
    manifest = out / "manifest.jsonl"
    seen = set(seen_file.read_text().split()) if seen_file.exists() else set()

    if free_gb() < args.min_free_gb:
        sys.exit(f"ABORT: only {free_gb():.1f} GB free (< --min-free-gb {args.min_free_gb}). Free space and retry.")

    if args.source == "youtube":
        files = fetch_youtube(args, out, archive)
        kept = []
        for f in files:
            w, h, dur = ffprobe_dim_dur(f)
            if not args.no_ocr and has_burned_text(f, dur):
                print(f"  drop (burned-in text): {os.path.basename(f)}"); os.remove(f); continue
            if not args.no_relevance and not is_immersive(f, dur):
                print(f"  drop (not immersive — showcase/talking/static): {os.path.basename(f)}"); os.remove(f); continue
            kept.append((f, w, h, dur))
    else:
        kept = []
        spent_gb = 0.0
        for url, vid in discover_tiktok(args):
            if len(kept) >= args.max_clips: break
            if vid in seen: continue
            if free_gb() < args.min_free_gb or spent_gb > args.max_download_gb:
                print("stop: disk/download cap reached."); break
            try:
                d = tikwm_hd(url); time.sleep(1.2)
            except Exception as e:
                print(f"  hd fetch error: {e}", file=sys.stderr); continue
            dur = d.get("duration") or 0
            link = d.get("hdplay") or d.get("play")
            if not link or dur < args.min_duration or dur > args.max_duration:
                continue
            dest = out / f"tt_{vid}.mp4"
            if args.dry_run:
                print(f"  [dry] tt_{vid}  {dur}s  {url}"); seen.add(vid); continue
            try:
                download(link, dest)
            except Exception as e:
                print(f"  download error {vid}: {e}", file=sys.stderr); continue
            spent_gb += dest.stat().st_size / 1e9
            w, h, realdur = ffprobe_dim_dur(dest)
            seen.add(vid)
            if min(w or 0, h or 0) < args.min_height:
                print(f"  skip <{args.min_height}p ({w}x{h}): {dest.name}"); dest.unlink(missing_ok=True); continue
            if not args.no_ocr and has_burned_text(dest, realdur or dur):
                print(f"  drop (burned-in text): {dest.name}"); dest.unlink(missing_ok=True); continue
            if not args.no_relevance and not is_immersive(dest, realdur or dur):
                print(f"  drop (not immersive — showcase/talking/static): {dest.name}"); dest.unlink(missing_ok=True); continue
            kept.append((str(dest), w, h, realdur or dur))
            print(f"  + {dest.name}  {w}x{h}  {round(realdur or dur,1)}s")
        seen_file.write_text(" ".join(sorted(seen)))

    # manifest + optional render
    n = 0
    for f, w, h, dur in kept:
        n_hooks = int((dur or 0) // args.seg)
        with manifest.open("a") as m:
            m.write(json.dumps({"filename": os.path.basename(f), "source": args.source,
                                "duration": round(dur or 0, 1), "width": w, "height": h,
                                "n_hooks": n_hooks, "ts": int(time.time())}) + "\n")
        n += 1
        if args.render and n_hooks >= 1:
            rc = run(["bash", str(RENDER_SH), "--core", args.core, "--hook", f,
                      "--outdir", args.render_outdir, "--count", str(min(n_hooks, args.max_hooks_per_clip))])
            if rc.returncode != 0:
                print(f"    render failed: {f}", file=sys.stderr)

    print(f"\nDone. {n} clip(s) kept -> {out}.  Manifest: {manifest}")
    if not args.render and n:
        print("Render with: render_reels.sh --hook <clip> --count <n_hooks>  (or re-run with --render)")

if __name__ == "__main__":
    main()
