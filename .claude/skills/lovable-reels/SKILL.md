---
name: lovable-reels
description: Lag split-screen reels (1080x1920, 60fps) ved å stacke et topp-klipp over et utsnitt av et langt reaksjonsopptak, og lime på et fast slutt-klipp. Bruk denne når brukeren vil "lage reels", "lage split-screen-videoer", "klippe opp et reaksjonsopptak til flere reels", eller lage en batch korte vertikale videoer fra tre kildeklipp (topp + reaksjon + slutt/CTA). Brukeren oppgir alltid sine egne klipp.
---

# lovable-reels

Lager en batch vertikale reels for TikTok/Reels/Shorts. Hvert reel består av to deler limt etter hverandre:

1. **Split-screen-del:** et topp-klipp øverst (1080x1008) og et utsnitt av et langt reaksjonsopptak nederst (1080x912), stacket vertikalt.
2. **Slutt-del:** et fast slutt-klipp (f.eks. en CTA / app-demo), skalert til full 1080x1920.

Reaksjonslyden er alltid AV. Lyden kommer fra topp-klippet (del 1) og slutt-klippet (del 2).

## Viktig: brukeren oppgir egne klipp

Denne skillen inneholder **ingen videofiler**. Be alltid brukeren om de tre kildeklippene:

- **topp** — klippet som vises øverst i split-screen
- **reaksjon** — et langt opptak; hvert reel klipper ut et nytt utsnitt herfra
- **slutt** — det faste klippet som limes på til slutt

## Bruk

```bash
scripts/make_reels.sh \
  --top    /sti/til/topp.mov \
  --react  /sti/til/reaksjon.mov \
  --final  /sti/til/slutt.mov \
  --outdir ./output_reels \
  --count  10 \
  --start  2
```

Argumenter:

| Flagg | Default | Betydning |
|-------|---------|-----------|
| `--top` | (påkrevd) | Topp-klippet (skaleres til 1080x1008). |
| `--react` | (påkrevd) | Langt reaksjonsopptak; utsnitt klippes herfra. |
| `--final` | (påkrevd) | Fast slutt-klipp (skaleres 1080x1920). |
| `--outdir` | `./output_reels` | Output-mappe. |
| `--count` | `10` | Antall reels. |
| `--start` | `2` | Starttid (sek) for første reel inn i reaksjonsopptaket. |
| `--seg` | `14.033333` | Lengde (sek) på reaksjonsutsnittet per reel. |

## Unngå identiske klipp mellom batcher

Hvert reel tar et `--seg` sekunders utsnitt av reaksjonsopptaket, der utsnitt nr. *k*
starter på `start + k * seg`. For å lage flere batcher uten å gjenta nøyaktig samme
utsnitt: kjør hver batch med ulik `--start` (f.eks. 2, deretter 7, deretter 12). Da er
ingen starttid lik, og utsnittene overlapper bare delvis.

Scriptet sjekker automatisk at reaksjonsopptaket er langt nok til alle klippene, og
gir en grov diskplass-advarsel før kjøring.

## Output-spec

- 1080x1920, 60fps
- H.264, ~21 Mbps (maxrate 21M, bufsize 42M)
- SDR: bt709 colorspace/primaries/trc
- AAC 160k, 44.1 kHz
- `+faststart` for rask avspilling/opplasting

---

## Gjeldende pipeline (bruk denne) — `scripts/render_reels.sh`

`make_reels.sh` over er den **gamle** geometrien (topp 1008 / reaksjon 912, tre separate klipp).
Den nåværende arbeidsflyten bruker ett **core-klipp** (Gary-talehode + caption som topp i de
første 14 s, deretter fullskjerm app-demo "reveal") + et **hook-klipp** (B-roll) nederst:

```
render_reels.sh --core core_new4.mp4 --hook KLIPP.mp4 --count auto --outdir output
```

- Topp = core beskåret til 910 px; bunn = 14 s hook-utsnitt beskåret til 1010 px (cover-crop —
  fungerer for både liggende og stående kilder). Etter 14 s: core fullskjerm.
- Hook-lyd droppes; lyd = core. Output-nummerering fortsetter `N.mp4` (auto = høyeste + 1).
- Et langt hook-klipp deles i flere 14 s reels.

## Lime inn en reel-lenke → lag hooks — `scripts/make_from_link.sh`

Når brukeren bare gir en **Instagram/TikTok/YouTube-lenke** (i stedet for å laste ned manuelt via
fastvideosave.net e.l.): denne lager hele kjeden lenke → nedlasting → reels i ett steg.

```
scripts/make_from_link.sh --url "https://www.instagram.com/reel/XXXX/"
```

- Laster ned klippet med `yt-dlp` til `./hooks/`, og kaller deretter `render_reels.sh` med fila som `--hook`.
- Alle ekstra flagg sendes rett videre til `render_reels.sh` (f.eks. `--core`, `--count`, `--seg`, `--dry-run`).
- **Instagram krever ofte innlogging:** scriptet prøver først anonymt, og faller automatisk tilbake til
  cookies fra installert nettleser (Chrome → Safari på denne maskinen). Tving én med `--cookies chrome`
  (Chrome må være helt lukket for at macOS skal frigi cookie-DB-en). Bytt nettleser med samme flagg.
- `--download-only` for bare å hente klippet uten å rendre.
- Forutsetninger: `yt-dlp`, `ffmpeg`.

## Auto-hente HD B-roll hooks — `scripts/fetch_brolls.py`

Når brukeren går tom for egne klipp: hent **HD, tekstfri, relevant** B-roll fra **TikTok** (gratis,
uten vannmerke, via tikwm.com — 720–1080p; ingen API-nøkkel/innlogging). Automatiske kvalitetsfiltre:
innbrent tekst droppes (OCR/RapidOCR), og produkt-showcase / unboxing / talking-head / statiske klipp
droppes (CLIP-relevans via fastembed) — bare rå, immersiv POV/action/natur slipper gjennom. Pluss
≥720p- og lysstyrke-filter. Se `docs/BROLL_FETCH.md` og `sources.example.txt`.

```
python3 scripts/fetch_brolls.py --tiktok-search "fpv drone" --tiktok-search "downhill mtb pov" \
    --n 12 --max-clips 6 --render --core core_new4.mp4 --render-outdir output
```

- Lyd droppes (core-lyd brukes), så klippets musikk havner aldri i output — men *bildet* er fortsatt
  andres innhold: foretrekk natur/action (fpv, drone, mtb, ski), ikke ansikter.
- Dedupe via `brolls/seen_tiktok.txt`; manifest i `brolls/manifest.jsonl`; diskvakt + ≥720p-filter innebygd.
- Fallback: `--source youtube` (kun 360p — siste utvei hvis tikwm er nede).
- Skru av filtre ved behov: `--no-ocr`, `--no-relevance`.
- Forutsetninger installert: `requests`, `yt-dlp`, `rapidocr-onnxruntime`, `fastembed`.
