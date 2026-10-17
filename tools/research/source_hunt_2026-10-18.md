# DOLCE EMPIRE — external real-photo sourcing notes (2026-10-18)

Source research is not limited to Wikimedia. Search Google and original photographer / videographer sources first, then verify individual photograph rights and resolution before releasing any new set.

## Rules (non-negotiable)

- NO AI-generated or altered portraits: original real photo + crop, light adjustment and card typography only.
- One full group per collection, every active member represented; one coherent photo shoot or one concert event for the entire album.
- One album has one rarity. Each new rarity requires entirely different original photographs.
- No photo duplicates, re-encodings or same-frame near duplicates in any published rarity.
- Aim for bright, sharp solo portraits; reject blur, low-light images, crowd shots, or tiny crops. Need a usable >=600x800 source region for real 3:4 crop.
- Final photo art 900x1200; banner 1600x900. Credit author, original media URL, exact license, and modifications.
- Never publish missing/incomplete sets; when licensing is unclear, keep in research rather than active photo_releases.json.
- Distinguish photo copyright licenses from possible publicity and personality-right restrictions in commercial use.

## Published: ITZY / BARRIE / 2025-11-10 / SPOTLIGHT EPIC

Original source NOT Wikipedia: [TV10 footage of all five members](https://www.youtube.com/watch?v=KHc_S_1uHsQ) from the same Seongsu-dong BARRIE photo call. The original TV10 video was reviewed for CC BY 4.0 by third-party reviewers; Wikimedia mirrors host the individual higher-resolution stills. All five source files have around 1500x1900 source resolution; publishing pipeline uses 960x1200 licensed stills and renders 900x1200 cards without upscaling.

- YEJI — video 78s — source file 251110 Hwang Yeji from ITZY.png
- LIA — 80s — 251110 Choi Jisu (Lia) from ITZY.png
- RYUJIN — 83s — 251110 Shin Ryujin from ITZY.png
- CHAERYEONG — 38s — 251110 Lee Chaeryeong from ITZY.png
- YUNA — 87s — 251110 Shin Yuna from ITZY.png

Cards and banner shipped in coll_itzy_spotlight_epic. Please do NOT recycle these frames into another rarity.

## Published: LE SSERAFIM / Easy Crazy Hot Tour Seattle / 2025-09-17 / SPOTLIGHT EPIC

Original photographer: [David Lee's Flickr photostream](https://www.flickr.com/photos/davidjlee/), not stock imagery and not AI. Five DIFFERENT photos taken at the same Climate Pledge Arena show on September 17, 2025. Each full-size file is over 1500 pixels wide and above the project's minimum photo resolution. Wikimedia Commons copies were confirmed CC BY 4.0 by FlickreviewR 2 on March 30, 2026; keep exact Flickr source links and derivative-work attribution.

Selected unique portrait sources and documented subject categories:

- CHAEWON — https://www.flickr.com/photos/davidjlee/54797154470/ — Commons photo https://commons.wikimedia.org/wiki/File:Easy_Crazy_Hot_Tour_in_Seattle_-_le_sserafim_(54797154470).jpg
- SAKURA — https://www.flickr.com/photos/davidjlee/54848411767/ — Commons photo https://commons.wikimedia.org/wiki/File:Easy_Crazy_Hot_Tour_in_Seattle_-_le_sserafim_(54848411767).jpg
- YUNJIN — https://www.flickr.com/photos/davidjlee/54849516999/ — Commons photo https://commons.wikimedia.org/wiki/File:Easy_Crazy_Hot_Tour_in_Seattle_-_le_sserafim_(54849516999).jpg
- KAZUHA — https://www.flickr.com/photos/davidjlee/54795963297/ — Commons photo https://commons.wikimedia.org/wiki/File:Easy_Crazy_Hot_Tour_in_Seattle_-_le_sserafim_(54795963297).jpg
- EUNCHAE — https://www.flickr.com/photos/davidjlee/54846344638/ — Commons photo https://commons.wikimedia.org/wiki/File:Easy_Crazy_Hot_Tour_in_Seattle_-_le_sserafim_(54846344638).jpg

Published as full `coll_lesserafim_spotlight_epic` (five 900x1200 cards and one 1600x900 banner) by successful GitHub Actions run https://github.com/CefaHub/dgemptestbot/actions/runs/39072867344. The successful release required fixing an existing new-player starter-pack bug: more than three represented artist groups must still result in EXACTLY three distinct starting cards. Regression test added.

Copyright CC BY 4.0 does not automatically settle publicity / personality-right questions for commercial endorsements or merchandise.

## Published: aespa / ROYAL HAZE MYTHIC / SYNK: PARALLEL LINE Encore, March 15–16, 2025

Four separate original solo photographs by snow plumflower from one aespa concert production. All have verified CC BY-SA 2.0 licenses on Wikimedia Commons and corresponding original Flickr pages. Each is different from the earlier aespa SPOTLIGHT/AURA/VELVET LIGHT images; the pipeline checked canonical URLs, page URLs, exact SHA-256 and perceptual dHash.

- KARINA — https://commons.wikimedia.org/wiki/File:250315-16_aespa_Karina_01.jpg — https://www.flickr.com/photos/197564772@N02/54497656356/
- WINTER — https://commons.wikimedia.org/wiki/File:250315-16_aespa_Winter_01.jpg — https://www.flickr.com/photos/197564772@N02/54497657726/
- GISELLE — https://commons.wikimedia.org/wiki/File:250315-16_aespa_Giselle_01.jpg — https://www.flickr.com/photos/197564772@N02/54498009640/
- NINGNING — https://commons.wikimedia.org/wiki/File:250315-16_aespa_Ningning_01.jpg — https://www.flickr.com/photos/197564772@N02/54498010765/

Published as `coll_aespa_royal_haze_mythic`. Complete set, all images available as PNG 900x1200, matching banner PNG 1600x900. Published commit: https://github.com/CefaHub/dgemptestbot/commit/a793dc66080. GitHub Actions: https://github.com/CefaHub/dgemptestbot/actions/runs/39076112566.

Previous research queue for a 2026 Mise-en-Scene version of MYTHIC is intentionally **superseded**, not published. Do not attempt to reuse its URLs or add a second coll_aespa_royal_haze_mythic entry.

## Preview-only: LE SSERAFIM / AURA RARE (4 of 5 cards, blocked from game)

The 2025-09-17 Seattle concert by David Lee has an additional four high-resolution, rights-reviewed, previously UNUSED source frames. They were rendered by GitHub Actions into 900x1200 DOLCE EMPIRE AURA rare artwork and saved as a temporary review artifact:

- Candidate sources: `tools/research/lesserafim_aura_rare_candidates.json`
- CHAEWON: Flickr image 54797153830
- SAKURA: Flickr image 54797069478
- KAZUHA: Flickr image 54796820566
- EUNCHAE: Flickr image 54846336944
- Remaining required member: YUNJIN. Existing published solo from Flickr 54849516999 **MUST NOT** be recycled. Other source photos show Yunjin in multi-person frames and are not reliably separable into a separately documented solo portrait without careful review.
- Source rights: CC BY 4.0, photographer David Lee, verified Flickr review on Commons.
- GitHub Actions preview successful: https://github.com/CefaHub/dgemptestbot/actions/runs/39075353449 — 48 tests passed, 1 skipped; candidate PNG archive under artifact `Dolce-Photo-Candidate-Review`. **NO catalog or playable cards were changed.**
- The completed AURA set must have all five unique high-quality portraits, consistent source concept, and must pass normal `tools/photo_release_pipeline.py build --publish` gates before releasing.

## Rejected or incomplete candidates

- [CHEN CY's IVE 2025-11-02 Seoul concert album](https://www.flickr.com/photos/196829184@N04/albums/72177720330066795/) includes separate portraits of all six IVE members, but individual photos say **All rights reserved**. Do not copy without permission.
- ILLIT Canada Goose Dec 2024 has all five members but extracted solo images measure about 460–500 × 660 pixels. Reject as too small for the 3:4 quality threshold.
- [Damon Billian's Seattle 2025 LE SSERAFIM Flickr album](https://www.flickr.com/photos/damonbillian/albums/72177720329107122/) has 123 photographs from one concert and the complete lineup, but reviewed individual images were marked **All rights reserved**. Do not redistribute in game without explicit permission.
- [ITZY G-SHOCK photo call 2024-10-23](https://www.youtube.com/watch?v=xRIHgC2ZVoM) has four confirmed distinct member pictures at only ~800x1100 and ~160-200KB per JPEG. Too compressed for the requested premium quality; no full suitable set approved. Do not force upscale.
- [IVE 40th Golden Disc Awards 2026-01-10 / TV10 footage](https://www.youtube.com/watch?v=7KfCcSxeZJU) has a licensed group recording but not yet six confirmed suitable individual high-quality portraits. Hold pending a coherent six-solo selection.
- Getty/WireImage editorial event photo galleries require separate paid licenses for resale/promotional use: do not copy watermarked or rights-managed frames as cards.
- Superseded aespa MYTHIC source research: the previously archived 2026 Mise-en-Scene candidate queue hit Wikimedia 429 and a proxy 404. An entirely separate completed 2025 Encore solo-photo set has **now been published** as MYTHIC; archive preserved only for historical evidence, never to be republished under an occupied set ID.

## Discovery strategy for remaining releases

For each of ILLIT, aespa, IVE, ITZY and LE SSERAFIM, search the internet broadly by group + exact dated shoot/event + photographer + image rights. Prefer an original Flickr album or a source-listed CC video with several different photographs. Keep a source note per candidate and release only after all group members have verified genuinely distinct clean solo frames. Never just fill quota with low-resolution or duplicated shots.
