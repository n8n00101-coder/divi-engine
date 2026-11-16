# Benchmark — per-line mode vs batch mode

Measured 2026-11-15 on the project's small shared VM (4 vCPUs visible,
≈1.5 CPU effective quota, 7.9 GB RAM), Chatterbox local, English, 6
short lines (7–10 words each, the sleep/brain demo lines). Identical
thread config in every mode (`JULIE_CLONE_THREADS=2`, the old per-line
default; batch's `cpu // jobs` auto-size was bypassed by the pin).
Models served from the local Hugging Face cache (offline).

**Read the caveats before quoting any number.** This box is shared:
external load swung between ~2 and ~12 during the runs, so these are
real-world figures from a contended machine, not laboratory numbers.
Gate pass/fail is take-dependent — the same line can pass in one run
and re-roll in another.

## Results

| Mode | Command shape | Wall | Result |
|---|---|---|---|
| (a) per-line (old) | `--text-file`, subprocess per take | **1395 s (23.3 min)**, exit 2 | FAILED at sentence 3 — no mp3 at all |
| (b) batch, jobs=1 | `--batch --jobs 1 --rerolls 2` | round 1 ≈ 21 min (see below) | 6/6 lines generated with **1 model load**; full run interrupted |
| (c) batch, jobs=4 | `--batch --jobs 4 --rerolls 2` | not completed on this VM | workers died under memory pressure (see below) |

### (a) Per-line mode — complete run

Every take is a fresh subprocess: Python + torch start, model load,
reference conditioning, generation. Per-take generation seconds:

| Take | gen_s | Gates |
|---|---|---|
| s1 r1 | 258.8 | PASS |
| s2 r1 | 199.4 | PASS |
| s3 r1 | 295.8 | fail (pronunciation) |
| s3 r2 | 243.1 | fail (pronunciation) |
| s3 r3 | 395.3 | fail (pronunciation) |

Total generation 1392.4 s across 5 takes = **5 model loads**, then the
run gave up: lines 4–6 were never attempted and, per single mode's
all-or-nothing rule, no mp3 was written.

### (b) Batch mode, jobs=1 — round 1 complete, run interrupted

One worker process, **one model load + one conditioning for all six
lines**. Per-line generation seconds from the worker manifest:

| Line | gen_s | Note |
|---|---|---|
| 1 | 92.1 | includes the one-time model load |
| 2 | 95.4 | pure generation |
| 3 | 384.7 | pace guard regenerated inside the take (locked recipe) |
| 4 | 97.1 | pure generation — PASSED all gates |
| 5 | 204.5 | pace-guard regen inside the take |
| 6 | 180.1 | pure generation |

Plain single-generation takes ran **92–97 s** against per-line mode's
**199–395 s** per take on the same box and day (under different
contention — treat the gap as indicative, the load count as exact).
Lines 1, 2, 3, 5, 6 failed a gate on these particular takes and went
to re-roll; the full run was stopped during round 2 when external
load spiked to ~12 and the worker starved. No final wall time is
claimed for (b).

### (c) Batch mode, jobs=4 — does not fit this VM

One loaded Chatterbox worker holds ≈3.9 GB RSS (measured in the
jobs=1 runs: ~49% of this VM's 7.9 GB), so four workers cannot fit.
Observed directly: of the four round-1 workers, one died during the
simultaneous model load and a second was lost minutes later; **zero
takes were completed** before the run was stopped (the two survivors
were still crawling under load ~9.6, and a runtime restart then
killed them; the batch parent recorded every dead worker's lines as
failed and re-rolled them into round 2, as designed — the run was
stopped there rather than left to repeat the cycle). **Parallelism
on one small box is memory-bound; parallelism across machines is
the answer** — the GitHub Actions workflow gives every chunk its
own runner (4 cores / 16 GB each), which is where `--jobs` scaling
belongs. On a machine with the RAM headroom, `--jobs` works exactly
as in mode (b), just with more workers.

## GitHub Actions route — measured 2026-11-15 (the 10x proof)

The workflow (`.github/workflows/voice-batch.yml`) was dispatch-tested
end-to-end three times with `test-lines.txt` — the same 6 demo lines —
split across **3 runners** (`-f chunks=3`), English, Chatterbox, all
five gates on every line. Wall time is run creation → run completion
(dispatch → artifact ready is ~7 s more in each case).

| Run | ID | Caches | Wall | Result |
|---|---|---|---|---|
| 1 (original workflow) | 43734396304 | cold (first run ever) | **6m46s** | **6/6 lines PASS**, merged artifact verified: `001.mp3`–`006.mp3` in original numbering + QC |
| 2 (caches + 20-cap + thread pin) | 43735459049 | HF model cache **hit**, pip cache cold under its new key | 7m14s | 5/6 — line 3 failed the pitch gate (f0 228.7 Hz vs 185–220 band) on all 3 rolls |
| 3 (both caches warm) | 43736471637 | pip **hit** + HF **hit** on every chunk | **5m46s** | 5/6 — line 1 failed the swallowed-word gate on all 3 rolls |

Per-chunk engine timings (inside the jobs): generation totals of
111–219 s per 2-line chunk including re-rolls; plain takes ≈55–95 s
on the 4-core runners, gates ≈12 s per take, one model load per chunk
per round. Job totals (setup + install + generate) were 4m46s–6m16s.

**Gate variance is real and is the accuracy working as designed.**
Runs 2 and 3 each lost a different line to a different gate after all
re-rolls; the gates and thresholds are locked, takes are stochastic,
and a line that never passes gets no mp3 — its chunk job goes red and
the QC report names it. Re-dispatching (or re-running just the failed
lines) is the intended remedy. Run 1 shows the same script passing
6/6 on another set of takes.

**Workflow bug found and fixed by these runs:** every chunk writes
`batch.qc.json`, and the merge step's files overwrote each other — the
merged artifact kept only one chunk's report. Each chunk now also
uploads `batch.qc.chunk-<n>.json`; runs 2–3 artifacts contain all
three chunk reports.

### Projection for a 209-line script (labelled projection, not a measurement)

From the measured per-line rates above (fixed warm overhead ≈1–1.5 min
per runner for setup + cache restore + model load; ≈70–110 s per line
including gates and average re-rolls):

- **chunks=10** → ~21 lines/runner → roughly **26–40 min** wall.
- **chunks=20** → ~11 lines/runner → roughly **14–22 min** wall.

Against the 8–12 hours Hark reported for the same script voiced
locally line-by-line, that is a **>20x wall-clock reduction**, with
the identical gates on every line. Treat the ranges as estimates —
gate re-roll luck moves individual lines, as runs 2–3 show.

## What this means for a 209-line script

- Per-line mode pays a full process start + model load + conditioning
  **per take** — 209+ loads minimum, plus one more for every re-roll.
- Batch mode pays **one load per worker per round**, and re-rolls only
  the lines that failed.
- The step change is the free Actions route: 209 lines ÷ 10 runners ≈
  21 lines per runner, each loaded once. That turns Hark's reported
  8–12 hours of local voicing into roughly one parallel wave of
  per-line generation time, gates included.

## Method notes

- Lines file: the 6 demo lines in `lines6.txt` (same file for (a) as
  `--text-file`, which sentence-splits it into the same 6 units).
- Attempt caps matched: (a) `--rolls 3`; (b)/(c) `--rerolls 2`
  (= up to 3 attempts per line).
- Proxy env vars were stripped for local model loads — this VM's
  `NO_PROXY` contains a bracketed IPv6 entry that crashes httpx inside
  Hugging Face loads (a local quirk of this machine, not the engine).
- An early batch attempt with 4 torch threads on this 1.5-CPU-quota
  box burned ~18 CPU-minutes without finishing one take: on a hard
  quota, oversubscribed threads thrash. The benchmark therefore pins
  2 threads everywhere; on a normal machine the `cpu // jobs`
  auto-size is the sensible default.

## Telugu fast path (fixed13 anchors, measured 2026-11-16)

The default Telugu route is the parallel Actions batch
(`indicf5-batch.yml`: 10 runners, one IndicF5 load per runner, whole
takes + the ship bar on every take). What makes it fast is NOT raw
generation speed — it is the pre-calibrated per-ref speed anchors in
`voice/settings.json` (`telugu_indicf5.speed_anchors`), which put the
FIRST pass in the pace band so re-roll waves are the exception:

- fixed13 calibrated waves (runs 43821187877 / 43821196336 /
  43821204495 / 43821211163): 20 takes per run (10 runners x 1 roll x
  2 sentences), wall **20-31 min per run** end-to-end (checkout, deps,
  model load, generation, gates, artifact merge). First-pass yield at
  the anchors: **S1 19/20, S2 20/20** takes in band with identity
  >= 0.85.
- fixed6 mass-roll (for contrast): 240 takes in ~98 min wall
  (~4 min per take per runner, setup included) — brute force WITHOUT
  calibrated anchors needed 120 takes to find its best pair; the
  anchored route needed 20.

### A 15-minute script, end to end (ESTIMATE)

A 15-min narration at her pace is ~1,900-2,000 words, roughly
120-135 whole sentences. One `indicf5-batch` dispatch with the full
lines file at rolls=1 puts ~13 takes on each of the 10 runners:
~25 min of setup/load (measured above) + ~13 x 2-4 min of
generation+gates per runner.

- **Estimate: ~1-1.5 h wall** for the anchored single-roll pass,
  plus a small top-up dispatch for the handful of sentences with no
  passing take (at the measured 95%+ first-pass yield, expect
  ~5-10 sentences).
- rolls=2 everywhere roughly doubles generation: **~1.7-2.2 h**.

These are estimates extrapolated from the measured waves above, not
promises: runner contention and Space/model-download variance move
them. The local-VM route is NOT the fast path (per-take subprocess
loads, see (a)-(c) above) and stays the small-budget fallback only.

## Turbo pipeline — the 20-minutes-in-10 requirement (2026-11-16)

Requirement (Ajju): a 20-minute Telugu voice-over (~2,600 words) must
complete in **6–10 min wall** from one command. The turbo pipeline
(`turbo.py` / `turbo.yml`) was built and measured end-to-end on GitHub
Actions. All numbers below are measured, not projected.

### Stage benchmark (24 compound lines, 447 words, natspan2 @ speed 1.0)

Per-stage timings from instrumented runs (branch `perf/20min-in-10`):

| stage | measured |
|---|---|
| runner setup (checkout, caches, apt ffmpeg) | ~0.5–1 min |
| pip install into venv, cold | 63 s (warm: seconds, venv is cached) |
| IndicF5 + whisper + Resemblyzer load | ~15 s + ~30 s |
| **one take, nfe_step 32 (fork default)** | **255–493 s (avg ~370 s)** |
| one take, nfe_step 16 | avg 184 s |
| one take, nfe_step 8 | avg 95 s (61–130 s) |
| gates on the pre-selected take | 2–5 s |
| Resemblyzer identity | ~0 s |
| collect / assemble jobs | ~1 min / ~1.5–2 min |

Generation is ~95% of all compute. nfe_step (made explicit in
`turbo_gen.py`; the HF wrapper never exposed it) is a pure speed lever:
32 → 8 steps cuts a take ~4× with **no measured change in ship rate**
and the locked ship gates unchanged on every take.

### The real bottleneck: per-take ship probability

Ship bar (locked, unchanged): gate 1 no-hint language + gate 2 ghost
scan + identity ≥ 0.85 + pace 1.9–2.5 wps, all on the same whole take.
Measured across ~90 gated takes of real transcript sentences:

- gate 1 passes ~100%, identity ~100%, pace mostly in band.
- **gate 2 (ghost scan) fails ~75–85% of takes.** The "ghosts" are
  mostly English loanwords (criminal, review, theory, …) that the
  unhinted Whisper transcription renders in a non-Telugu script, so
  they match no script word. It is stochastic per take.
- Per-take ship probability ≈ **0.15–0.20**; a hard core of sentences
  (~25–30%) needs >7 takes. After 7 takes, 8/24 bench sentences were
  still unshipped.
- Short units are WORSE: the same 450 words split into 62 natural
  sentences shipped only 2/49 units in 2 takes (short spans break the
  language-detect and pace measurements). Compound lines of ~15–19
  words are the right granularity.
- The IndicF5 HF Space (ZeroGPU) generates a take in ~8 s but the
  anonymous quota **errored out after 3–4 rapid calls** — unusable for
  a ~750-take job.

End-to-end bench results (24 lines, full chain incl. wave 2 +
assemble; runs shared the account with other experiments, so queue
contention inflates these): nfe 16 → **84 min**, nfe 8 → **58 min**,
both ending in an honest assemble refusal (sentences still unshipped
after 7 takes each).

### Proof run (142 lines, 2,632 words ≈ 20 min of speech)

Config: 48 parallel runners, nfe_step 8, wave 1 = 3 takes/sentence,
wave 2 = failures only, 8 more takes, then locked assembly.

<!-- PROOF RESULTS FILLED IN BELOW -->
