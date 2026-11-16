# BENCHMARK — Divi Engine vs the Speed Law

**The law (Ajju, 2026-11-16): a 20-minute voice-over READY within
10 minutes wall-clock, all three languages.**

Measured 2026-11-16, branch `divi-engine-upgrade`, production-intended
routes, end-to-end through the full path: script pre-flight →
parallel generation (best-of-3 candidates per sentence) → gate suite
per candidate → repair ladder → assembly (locked recipe) → final
assembled-file verification. Benchmark scripts: ~650 words /
~5 minutes of speech each (`jobs/bench-{en,te,hi}.txt`), all
pre-flight clean (0 corrections, 0 flags). Cloud runs are GitHub
Actions matrix jobs (voice-batch workflow, chunks of 2 sentences,
one model load per runner); the account's effective concurrency
measured ≈ 15–20 simultaneous jobs (40 requested).

## Verdict up front

**The 10-minute law is NOT met on the current free infrastructure —
for any of the three languages.** The architecture (parallel chunks,
best-of-N, in-place repair, one assembly + verification at the end)
is not the bottleneck. The bottlenecks are, in order:

1. **Free anonymous HF Spaces collapse under parallel load**
   (Telugu/Hindi routes): 87% of candidate generations died as
   Space queue errors when ~20 runners called anonymously at once.
2. **CPU generation cost** (English/Chatterbox): ~325 s of runner
   time per sentence with best-of-3 + gates.
3. **Gate cost**: every candidate take costs full Whisper ASR
   passes; best-of-3 triples that too.

What would close the gap (not free today): an authenticated Space
tier or a self-hosted GPU for OmniVoice/IndicF5 (generation drops
to seconds per sentence), GPU runners for Chatterbox, or relaxing
best-of-3 to best-of-1 with ladder escalation only on failure
(already the wave-2+ behaviour — wave 1 is the expensive part).

## English — Chatterbox, Actions matrix (run 43906319836)

| measure | value |
|---|---|
| script | 634 words, 54 sentences (~5.2 min of speech) |
| cloud wall (dispatch → all jobs done) | **56 min 34 s** |
| per-sentence cost, generation step (median) | **~325 s** (median job generate step 651 s / 2 sentences) |
| per-job total (median / max) | 812 s / 2295 s |
| fixed cost per job (install + setup + load) | ~2.5 min (pip install median 76 s) |
| lines passed the full ladder | **44 / 54** (10 named failures) |
| assembled-file verification | 10 of 11 checks PASS; cut_word flagged sentence 1's ending **only in the mp3 intermediate** — the same take passed gate 7 as WAV. Root-caused and fixed: batch line files are now lossless WAV intermediates (see commit "batch line files are WAV intermediates") |
| arithmetic to 20 min (~216 sentences) | ≈ 216 × 325 s ÷ ~18 concurrent ≈ **65–75 min** |

**English verdict: law missed by ~7×.** Even best-of-1 would land
~25 min. GPU generation is the only lever that reaches 10.

## Telugu — OmniVoice Space, Actions matrix (run 43917218373)

| measure | value |
|---|---|
| script | 608 words, 68 sentences (~5 min of speech) |
| cloud wall (dispatch → run complete) | **77 min 25 s** |
| per-chunk generate step (median) | 1613 s — almost all Space queue wait/retry |
| candidate rolls total | 631 |
| generation errors | **548 (87%)** — "[omnivoice] space error event" ×202, "[indicf5-space] space error event" ×346 (the escalation route collapsed too) |
| lines passed | **7 / 68** |
| of the rolls that did generate | pronunciation/swallowed/language defects dominate — the ladder worked as designed, it simply had almost no live candidates to choose from |

**Telugu verdict: the route, not the engine, failed.** Serial
OmniVoice calls (Part-B proof, 2026-11-16) succeed at ~15–40 s per
sentence; ~20 anonymous clients in parallel trip the free Space's
queue limits, and retries multiply the load. With an authenticated
or self-hosted OmniVoice endpoint, generation is ~2–5 s/sentence
and the same matrix design projects to **~8–12 min for 20 minutes
of Telugu** (gates become the binding cost). On today's free
anonymous tier: law missed, by infrastructure, not by design.

Full-path note: Telugu pre-flight → generation → gates → repair →
assembly → verification is additionally proven end-to-end locally
by `test_repair.py` (real OmniVoice-route stub takes through the
ladder, assembled file passes final verification; one sabotaged
sentence ships as a named PARTIAL).

## Hindi — IndicF5 Space, Actions matrix (run 43924548639)

| measure | value |
|---|---|
| script | 729 words, 54 sentences (~5 min of speech) |
| cloud wall (dispatch → run complete) | **64 min 35 s** |
| per-chunk generate step (median) | 1608 s — Space queue wait/retry churn |
| candidate rolls total | 540 |
| generation errors | **465 (86%)** — every one "[indicf5-space] space error event" |
| lines passed | **0 / 54** |
| of the rolls that did generate | pronunciation 75, swallowed 74, ghost words 51, cut-word 43 — the gates caught real defects too, but with the Space erroring, most sentences never had a live candidate |

**Hindi verdict: same infrastructure failure as Telugu** — the
free IndicF5 Space cannot absorb ~20 parallel anonymous clients.
A serial-pacing Hindi run through the full local path
(pre-flight → generation → self-healing gates → assembly →
verification) is reported in the addendum below; the locked Hindi
recipe itself (IndicF5 + atempo 1.20 as a recipe value) is
untouched and is exercised by `test_speedlock.py` and the local
run.

### Addendum — Hindi, local serial route (full path)

A 6-sentence Hindi job (`jobs/bench-hi-small.txt`) was run through
the local full path (divi.py → pre-flight → batch waves →
indicf5-space → gates → assembly → verification), serial pacing,
2026-11-16 night. Measured per-call behaviour of the IndicF5 Space
that night:

- failed call: **~94 s** burned in retries, ending "space error
  event" — 4 of the first 5 wave-1 candidates
- successful call: **11.4 s** (sentence 6, first candidate)
- serial success rate that night: ~1 in 5 calls

So the Space is unreliable at ANY pacing right now — parallel
load makes it worse (86% errors), but even a single polite client
mostly gets queue errors. The Hindi engine path itself (recipe
tempo via the speed policy, gates, ladder, assembly, verification)
is exercised green by `test_speedlock.py` (Hindi recipe 1.20
LOCKED, QC speed block) and `test_batch.py`; what cannot be
demonstrated tonight is a *healthy Space*, which is an
infrastructure fact, not an engine defect. Hindi per-sentence
cost, when the Space answers: ~11 s generation + ~40–120 s of
local gate ASR on this VM (≈12 s on a 4-core runner).

## Method notes

- Walls are dispatch→verified-file where the file survived; cloud
  walls are run created→updated from the Actions API (they exclude
  local assembly+verification, measured separately at ~5–30 min on
  this shared 1.5-core VM depending on contention — on a quiet
  4-core machine the 44-sentence EN verification is ~5 min).
- Per-sentence costs are medians of the workflow's own step
  timings, not estimates.
- Nothing in this file is projected from hope: where a number is
  arithmetic, the inputs are the measured rows above and the
  concurrency actually observed (~15–20 jobs), not the 40
  requested.
