# Auto-sourcing HD B-roll hooks (VA guide)

Pulls **HD, no-text** B-roll clips from **TikTok** (free, no watermark) and renders them straight into
reels, so you don't have to record every hook yourself.

## One-time setup
Already installed: `requests`, `yt-dlp`, `rapidocr-onnxruntime` (no-text OCR), `fastembed` (relevance/CLIP).
If you ever need them again: `python3 -m pip install -U requests yt-dlp rapidocr-onnxruntime fastembed`.
**No API key, no login, no account.** Source = the free `tikwm.com` TikTok API.

> **Quality:** TikTok clips come down at **720–1080p** (no watermark) — sharp, unlike YouTube's 360p.
> The clip's audio is dropped from the reel, so its music never triggers copyright. The **visual** is
> still someone's content, so prefer scenery/action (fpv, drone, mtb, ski, scenery), not faces.

### Automatic quality gates (every clip is checked before it's kept)
1. **No-text (OCR):** clips with burned-in captions/CTAs are detected and dropped (samples early frames too, to catch intro titles).
2. **Relevance (CLIP):** clips that are product showcases / unboxings / talking-head / static-object / goggles-indoors are dropped — only **raw immersive POV/action/scenery** passes.
3. **Resolution:** anything under 720p on its smaller side is skipped.
4. **Brightness:** near-black/unusable clips are skipped.

Turn gates off if needed: `--no-ocr`, `--no-relevance`. No filter is perfect, so still glance at new clips before posting.

## Everyday use
Run everything from the `reels_work/` folder.

**Fetch + render in one go** (reels continue your normal `output/` numbering):
```
python3 ../.claude/skills/lovable-reels/scripts/fetch_brolls.py \
  --tiktok-search "fpv drone" --tiktok-search "downhill mtb pov" \
  --n 12 --max-clips 6 --render --core core_new4.mp4 --render-outdir output
```

**Fetch only** (clips land in `reels_work/brolls/`, render later):
```
python3 ../.claude/skills/lovable-reels/scripts/fetch_brolls.py --tiktok-search "ski pov" --n 12 --max-clips 4
```

**Use the curated search list** instead of typing terms:
```
cp ../.claude/skills/lovable-reels/sources.example.txt brolls/sources.txt   # first time; edit freely
python3 ../.claude/skills/lovable-reels/scripts/fetch_brolls.py --queries-file brolls/sources.txt --max-clips 8 --render
```

**A specific TikTok you found** (best quality control — you pick the clip):
```
python3 ../.claude/skills/lovable-reels/scripts/fetch_brolls.py --tiktok-url "https://www.tiktok.com/@joe.fpv/video/123..." --render
```

Useful flags:
- `--min-duration 56` — only clips long enough for ≥4 hooks (default 20 = ≥1).
- `--max-hooks-per-clip 6` — cap reels per long clip so one video doesn't make 40 near-identical reels.
- `--max-clips N` — stop after N kept downloads.
- `--min-height 720` — skip anything below 720p (default).
- `--no-ocr` — turn the text filter off (faster, but captioned clips can slip through).
- `--dry-run` — list what it WOULD grab, download nothing.
- `--source youtube` — fallback to YouTube (360p only) if TikTok/tikwm is down.

## What you get
- Source clips: `reels_work/brolls/tt_<id>.mp4` (HD, no watermark).
- `manifest.jsonl` — one line per kept clip (resolution, duration, # hooks).
- `seen_tiktok.txt` — remembers what's been downloaded so re-runs never grab the same clip twice.
- Rendered reels (with `--render`): the next numbers in `reels_work/output/` (e.g. 180.mp4, 181.mp4 …).

## Finding clean, no-text clips
Best search terms / hashtags (the footage IS the content, so naturally caption-light):
`fpv`, `cinematic fpv`, `drone view`, `pov gopro`, `downhill mtb pov`, `ski pov`, `snowboard pov`,
`pov walk city`, `surfing pov`, `aerial nature`. See `sources.example.txt`.
**Avoid:** talking-head/storytime, CapCut templates, memes/green-screen, compilation/repost accounts
(text-heavy). The OCR filter catches most captioned clips, but good search terms mean fewer wasted downloads.

## Disk space (important — drive runs near-full)
Each finished reel ≈ 85 MB; the fetcher refuses to start under ~3 GB free. Reclaim space by deleting old
source clips (`reels_work/big*.*`, `brolls/tt_*.mp4`) and reels you've already posted (`output/N.mp4`).
AirDrop reels to your phone, then delete them here.

## When it stops working
tikwm is a free third-party service and can have downtime. If fetches start failing:
1. Wait a bit and retry (usually transient).
2. Try `--tiktok-url` with a specific TikTok link (more reliable than search).
3. Last resort: `--source youtube` (360p) to keep producing while tikwm recovers.
