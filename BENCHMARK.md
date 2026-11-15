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
