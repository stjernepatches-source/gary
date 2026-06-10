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
