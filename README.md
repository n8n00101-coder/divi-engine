# Divi Engine

A gated, self-healing voice-clone engine for one finalized house voice —
**Julie AI** (the voice's name; the tool is **Divi Engine**, renamed
2026-11-16) — in three languages: **English, Telugu, Hindi**.

You give it a script. Divi **heals the script first** (script
pre-flight), generates the voice-over with a **self-healing repair
loop** — best-of-N candidate takes per sentence, defect-specific
repairs, per-sentence route escalation — then **proves the assembled
file is clean** with a final verification pass before you get it. A
sentence that exhausts its whole escalation ladder ships nothing and
is *named* in the QC report; the rest of the job still delivers —
the work never stops, and defective audio is never a deliverable.

```
python3 divi.py --text-file script.txt --lang te --out out.mp3          # local
python3 divi.py --text-file script.txt --lang hi --out out.mp3 --cloud  # speed-law path
python3 engine.py --text "…" --lang te --out line.mp3                    # engine direct
```

Next to every mp3 the engine writes `<name>.qc.json` — the full QC report:
the Script Corrections log, per sentence, per candidate, every gate's
measurements, every repair (defect → action → result), the speed
source (LOCKED / USER-REQUESTED), and the final verification verdict.

## The speed law

**A 20-minute voice-over must be READY within 10 minutes wall-clock**
(owner's law, 2026-11-16), all three languages. The design: per-sentence
generation + gates run in parallel chunks (local workers, or the
`divi-voice-batch` Actions matrix — up to 40 free runners, one model
load each), best-of-N candidates ride the same parallel pool so
repairs cost no extra wall-clock, and assembly + final QC happen once
at the end. Failed sentences re-roll in place; nothing restarts the
job. Measured numbers (never claimed without measurement):
[`BENCHMARK-DIVI.md`](BENCHMARK-DIVI.md).

## Defaults locked — the speed law's other half

By default the tool runs **exactly** the locked settings
(`voice/settings.json` + the locked OmniVoice route). **Speed is never
adjusted by the tool on its own** — the one tempo entry point is
`speedpolicy.py`: locked recipe values (e.g. Hindi's ONE atempo 1.20)
are part of the voice definition; the English pace guard no longer
stretches a slow take — it rejects and re-rolls it. Any deviation
happens only when the user explicitly passes `--speed` for that job,
and every QC report prints the speed source: **LOCKED** or
**USER-REQUESTED**.

## Script pre-flight — heal the input

Before any generation, the whole script is analysed and auto-corrected
(`preflight.py`, deterministic — no model, no key): typos (curated
known-misspelling map + full-dictionary unique-neighbour rule),
TTS format (spelled-out percent → the `%` symbol, markdown/emoji
stripped, missing terminators supplied, duplicated lines removed),
english-mix policy compliance for Telugu scripts (banned connectives
corrected to Telugu; attested label words stay English), third-language
words (corrected where a clear equivalent exists), and over-long
sentences split only at natural clause boundaries. A correction that
could change *meaning* is applied only at high confidence — otherwise
the word is left and **flagged at the top of the QC report**. Nothing
is silently rewritten: the QC report carries the full Script
Corrections log and the corrected script is saved as
`script.corrected.txt` beside the output.

## The voice

One female Indian narration voice, measured and locked on 2026-11-14:

- **English** — zero-shot clone via [Chatterbox TTS](https://github.com/resemble-ai/chatterbox)
  (MIT), exaggeration **0.35**, phrase-by-phrase generation (pauses only
  where her phrases break: 0.66 s after a sentence, 0.06 s at commas), and
  a pace guard against her measured onset rate (5.24/s). Her profile:
  F0 median 221 Hz, controlled range 168–311 Hz, emphasis by *stretching*
  hinge words rather than pitch drama. **Status: LOCKED / owner-approved.**
- **Telugu** — [IndicF5](https://huggingface.co/spaces/ai4bharat/IndicF5)
  zero-shot clone from her Telugu reference. **Status: FIXED —
  owner ear-approved 2026-11-16 (fixed13).** The fix was the reference:
  every earlier ref had been cut from a 1.4705× time-squeezed copy of
  her narration; the canonical refs are now natspan1/2/3, cut from the
  owner-supplied natural-pace audio after Demucs music removal. Pace is
  set by the generation-side speed parameter with pre-calibrated
  per-ref anchors (see `telugu_indicf5.speed_anchors` in
  `voice/settings.json`) plus take *selection*; time-stretching Telugu
  (atempo) is banned — it stretched silences and broke the channel
  rhythm. Approved pair: `voice/samples/telugu-approved-s1-fixed13.mp3`
  + `telugu-approved-s2-fixed13.mp3`.
- **Hindi** — IndicF5 cross-lingual from the same Telugu reference, with
  the owner's approved +20% pace calibration (one atempo 1.20 per take,
  always logged). No Hindi reference sample exists yet, so Hindi is marked
  UNVERIFIED against the channel until one is supplied.

Full measurements: [`PRONUNCIATION-PROFILE.md`](PRONUNCIATION-PROFILE.md).
English-mixing rules for Telugu scripts (which word types stay English, where, and how to write them): [`docs/ENGLISH_MIX_POLICY.md`](docs/ENGLISH_MIX_POLICY.md) + [`voice/english_mix_classes.json`](voice/english_mix_classes.json).
References and locked values: [`voice/`](voice/) (`settings.json` is the
single source of truth — the gates read their thresholds from it).

## The gates — and the defect each one exists to kill

Every defect below was shipped by hand once, and caught by a human ear.
The gates are the permanent fix: they run **inside** the engine, on every
take, before anything is assembled.

| # | Gate | The defect it kills |
|---|------|---------------------|
| 1 | **No-hint language identity** — the take is transcribed with *no* language hint; the detected language must be the target (prob ≥ 0.80, Hindi ≥ 0.90) | A "Telugu" sample that detected as **Punjabi (0.486)** unhinted. Forcing the language into the checker masks between-language diction; detecting blind does not. |
| 2 | **Ghost-word scan** — the unhinted transcript is searched, in Latin *and* phonetic space, for foreign words that match no script word | The same sample's unhinted transcript literally contained **"feel safer"** four times — hallucinated English at phrase joints, invisible to any forced-language check. |
| 3 | **Pronunciation** — forced-language ASR word probabilities (every word ≥ 0.50) plus phonetic similarity per word, with missing/merged/smeared words rejected | Conjunct-heavy and long words (క్షణం, తాత్కాలికంగా) smeared or merged while a sentence-level "all words present" check passed them. |
| 4 | **PHYS — swallowed words** — per word: duration vs syllable count (absolute floor + 60% of take pace), mid-word energy collapse to the noise floor, abrupt-cut tails | Words **eaten mid-word** — ASR-readable, but audibly truncated. A sentence-level check cannot see this; acoustics can. (Validated: the owner-approved clean sample scores zero hard flags.) |
| 5 | **Pitch band** — F0 median must sit in **185–220 Hz** | Take-to-take pitch-centre wander (163–251 Hz across splices) making one voice sound like several. Out-of-band takes are re-rolled, **never pitch-shifted**. |
| 6 | **Head grunt** (2026-11-16) — the OmniVoice route prepends a short, quiet, flat low-pitched voiced grunt (~0.2 s, F0 ≈ 140–168 Hz) to nearly every generated sentence; the gate detects the signature and the engine **auto-mutes it at generation time**, recording the action in the QC report | A stray **"rey / ey orey"** heard after every sentence's last word in the owner's OmniVoice test sample. The segment is non-word phonation sitting in silence, so muting it in place cannot touch a word. Proof: `proof_omnivoice_gates.py`. |
| 7 | **Cut word** (2026-11-16) — the take's ending must be whole: no abrupt cut, no speech chopped at the file edge, no pinched final island, and no **detached weak tail** (a short, quiet, flat, low island stranded after the main final island) | The ending **"mana varaku vasthayi"** of an OmniVoice test sentence never landed — the main island ended and the final word survived only as a detached fragment. The gate judges the ending's acoustic *shape*; which words were said remains gates 1–3's job. A te/hi take failing gate 7 is blocked in `ship_decision` even when the rest of the ear-approved bar passes. |

Assembly is gated too: sentence takes are level-matched with plain gain
only (stacked processing measurably eats voice identity), joined with one
0.6 s gap, every pause is gated to **true digital silence** (the IndicF5
route leaves a ~91 Hz hum in gaps), and exactly **one** loudnorm pass
(≈ −15 LUFS) finishes the file. `--bed` adds the channel's quiet piano bed
≈ 11 dB under the voice.

## Why whole-take only (Telugu/Hindi)

Telugu and Hindi sentences are generated as **whole takes** and ship only
from a single take that passes the ear-approved bar (Ajju, 2026-11-16,
fixed13): gate 1 (no-hint language) **and** gate 2 (ghost scan) pass,
**plus** speaker identity (≥ 0.85 vs the English reference) **plus** the
pace band (1.9–2.5 words/s) — all on that one take. Gates 3/4/5 are still
computed and recorded on every take but are advisory for te/hi: the
fixed6 calibration proved the identical suite fails her own genuine
narration, and the ear-approved fixed13 takes do not pass all of them
either (S1's F0 sits 0.8 Hz under the pitch band edge). `ship_decision()`
in `engine.py` is the single implementation of the bar; a sentence with
no passing take ships **nothing** — and under the repair loop
(2026-11-16) that sentence is *named* in the QC report while every
other sentence in the job still delivers. Clause/donor assembly and every
splice-inside-a-sentence edit are hard-disabled for te/hi in code
(`forbid_inside_sentence_edit`).

The reason is the owner's ear. Three patchwork builds — fixed2, fixed3 and
fixed5 (2026-11-15) — were each rejected: every splice is a discontinuity a
native ear hears as a **cut**, and every regenerated segment carries a
slightly different voice identity, so patched sentences never sound like
one person speaking. One whole take has one identity and no joins; if no
take passes within the roll budget, the engine exits non-zero and ships
**nothing** for that sentence.

Large te/hi roll budgets (above `gates.local_roll_limit_te_hi` in
`voice/settings.json`) are the default mass-roll route: the engine writes
the sentences to `indicf5-lines.txt`, commits, and dispatches the
`indicf5-batch.yml` workflow — 10 parallel runners generating whole takes
with rotating genuine-Telugu references and gating every take with the
same suite. Exit code 3 means "dispatched"; takes and gate JSONs return as
the run's `divi-indicf5-batch-all` artifact.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
ffmpeg -version   # ffmpeg must be on PATH (assembly + loudnorm)
```

Notes:

- The English route downloads the Chatterbox model once (CPU is fine, it
  is just slow — a few minutes per take on a small machine).
- The gates use faster-whisper `base` locally; set `JULIE_WHISPER_MODEL`
  to a model name or a local model directory to override.
- Telugu/Hindi generation calls the free ai4bharat/IndicF5 Hugging Face
  Space — no API key needed. Keep your proxy env as-is for that call; the
  engine isolates it in a subprocess so it never contaminates the local
  ASR gates.

## Fast batch mode

Voicing a whole script line-by-line used to cost a full model load plus
reference conditioning **for every line** — on a small CPU that overhead
alone is minutes per line, before a single word is generated. Batch mode
removes it:

```bash
# one line per row in lines.txt; writes out/001.mp3, out/002.mp3, …
python3 engine.py --batch lines.txt --lang en --outdir out/
python3 engine.py --batch lines.txt --lang te --outdir out/ --jobs 4 --rerolls 2
```

- **Load once:** each worker process loads the model and computes the
  reference conditioning **once**, then generates all of its lines
  in-process. `--jobs N` (default `min(4, cpu count)`) runs N workers in
  parallel; lines are dealt round-robin so long and short lines spread
  evenly.
- **Self-healing waves:** every line gets best-of-N candidates per
  wave (`--candidates`, default 3), all gated and scored; the best
  passing one ships. Failures escalate per the repair playbook
  (`--rerolls` extra waves): seed re-rolls scored by completeness →
  wider best-of-N → alternate backend route → alternate reference
  span. Passing lines are never regenerated. A line that exhausts
  the ladder gets **no mp3** and is named in `out/batch.qc.json`;
  every other line ships. `--assemble-out final.mp3` additionally
  assembles the shipped lines into one file and runs the final
  assembled-file verification on it.
- Single-line mode (`--text` / `--text-file`) runs the same wave
  loop per sentence.

Realistic expectations: batch mode removes the per-line overhead, but
local generation is still CPU-bound — the words themselves take the
time they take. Measured on a small shared VM (6 short English lines,
Chatterbox): see `BENCHMARK.md`. The big lever for a full script is the
free cloud route below.

### Free cloud compute — GitHub Actions (`github` backend)

`.github/workflows/voice-batch.yml` runs batch mode on up to **40 free
GitHub-hosted runners in parallel** (this repo is public, so standard
runners cost nothing). A 209-line script becomes ~11 lines per runner
at `chunks=20`, or ~6 per runner at `chunks=40`, each loading the
model once. Pip downloads and the Hugging Face models are cached
across runs, so repeat runs skip both big downloads. The workflow
also takes `backend`, `candidates` and `speed` inputs (speed is the
user-requested tempo option; empty = LOCKED).

**Measured** (2026-11-15, three real dispatches of the 6-line
`test-lines.txt` on 3 runners): **5m46s–6m46s wall** for the whole
script, dispatch to finished artifact; the fully-green run passed 6/6
lines through all five gates. Projected from those per-line rates, a
209-line script lands in roughly **15–25 minutes at `chunks=20`** —
versus the 8–12 hours the same script took voiced locally
line-by-line. Full numbers: `BENCHMARK.md`.

1. Put your lines in a file in this repo (e.g. `lines.txt`, one line per
   row) and push it.
2. Dispatch the workflow:
   ```bash
   gh workflow run voice-batch.yml -f lines_path=lines.txt -f lang=en -f chunks=20
   gh run watch                      # wait for the run to finish
   ```
   (or: GitHub → Actions → *divi-voice-batch* → Run workflow.)
3. Download every line's mp3 plus the QC reports, merged into one
   artifact with the script's original line numbers:
   ```bash
   gh run download <run-id> -n divi-voice-batch-all
   ```
A chunk job can show red when some of its lines never pass the gates —
its artifact still uploads with every passing line and a
`batch.qc.json` naming the failures. Setting
`JULIE_TTS_BACKEND=github` locally just prints these instructions: it is
a route name, not a synthesizer.

## OmniVoice route (Telugu, locked)

Added 2026-11-16, on the owner's ear approval: in his side-by-side test
the OmniVoice clone of the house voice — from the canonical natural-pace
reference — was approved ("super bagundhi") over the earlier routes.

```bash
export JULIE_TTS_BACKEND=omnivoice
python3 engine.py --text-file script.txt --lang te --out out.mp3
```

- **Source:** [OmniVoice](https://huggingface.co/spaces/k2-fsa/OmniVoice)
  (k2-fsa) via the official Hugging Face Space's Gradio API — free,
  anonymous, no key. Generation is **per sentence** (the engine's own
  loop already splits text into sentences).
- **LOCKED settings** (owner's order: *same speed, same voice, every
  run* — enforced in `engine.py: OMNIVOICE_LOCKED`, not in editable
  config): reference = canonical **natspan2**
  (`voice/refs/natspan2.wav`, the same audio as
  `voice/telugu-reference.wav`) with its exact transcript; language
  Telugu; **speed 1.0 exactly**; steps 32; guidance 2.0. **No speed
  correction is permitted on this route** — no generation-side speed
  change, no atempo; setting `JULIE_OMNIVOICE_SPEED` to anything but
  1.0 makes the route refuse to run. Pace comes from the reference,
  as approved.
- **Its two known defects are gated, permanently** (gates 6 + 7
  above): every take is head-grunt–muted at generation time (action
  recorded per roll in the QC report), and a take whose final word is
  truncated or detached fails gate 7 and is re-rolled — a sentence
  with no whole take ships nothing (it is named in the QC report;
  the rest of the job delivers).
- ⚠️ **License:** OmniVoice model weights are **CC-BY-NC
  (non-commercial)**. That is a real constraint for monetized use —
  the route is in the tool because the owner ordered the test and
  approved the voice; weigh the license before shipping commercial
  work on it.

## Connect your own model (fast path)

The built-in routes are free, and you pay in time instead: the IndicF5
Space has a public queue and outage streaks, and Chatterbox on a local
CPU takes minutes per take. If you run a faster model yourself — or
have an ElevenLabs voice — connect it and generation stops being the
bottleneck:

1. `git pull` to get the pluggable-backend build.
2. Pick ONE backend (environment variables only — keys never go in a
   file, and never appear in QC reports):
   - **ElevenLabs:** `export JULIE_TTS_BACKEND=elevenlabs`,
     `export ELEVENLABS_API_KEY=…`, `export JULIE_EL_VOICE_ID=…`
     (optional `JULIE_EL_MODEL`, default `eleven_multilingual_v2`; the
     voice id can instead live in `voice/settings.json` under
     `backends.elevenlabs.voice_id`). The voice then comes from that
     ElevenLabs voice id — the reference wavs are not used.
   - **Meta MMS-TTS (Telugu, built-in local engine):**
     `export JULIE_TTS_BACKEND=mms` — native-diction Telugu from
     Meta's massively-multilingual VITS model (`facebook/mms-tts-tel`),
     merged into this tool on 2026-11-16 alongside the locked
     Chatterbox English route. It runs locally (no key, no server) and
     is Telugu-only. It is **not a clone** — the voice is the model's
     own Telugu speaker, chosen for diction the clone route kept
     missing.
  - **OmniVoice (Telugu clone, built-in Space route):**
     `export JULIE_TTS_BACKEND=omnivoice` — see the dedicated section
     above. Locked settings, gates 6 + 7 apply, CC-BY-NC weights.
   - **Your own model server:** `export JULIE_TTS_BACKEND=http` and
     `export JULIE_TTS_URL=http://your-server/tts` (optional
     `JULIE_TTS_KEY`, sent as `Authorization: Bearer …`). Server
     contract: accept a POST with JSON `{"text", "lang", "voice"}` and
     return audio bytes (mp3 or wav) as the response body.
3. Run the engine exactly as before — same CLI, same languages.

Nothing about quality control changes: the gates, the self-healing
repair loop and the QC report apply on top of **any** backend, each
take's backend is recorded in `<name>.qc.json`, and a take that fails
the gates is rejected no matter how fast it was generated. HTTP backends time out at
120 s per take and fail loudly, naming the backend — no silent hangs.
Leave `JULIE_TTS_BACKEND` unset to return to the default free routes.

## Honest limits

- **IndicF5 diction varies per take.** Some takes will always smear a hard
  word or sprout a ghost word. The engine's answer is not to fix them in
  post — it is to *reject and re-roll*. Expect several rolls on hard
  sentences; a sentence that exhausts its escalation ladder fails
  honestly (named in the QC report, exit 2) rather than shipping a
  defective file — the rest of the job still delivers.
- **The IndicF5 Space has outage streaks** (ZeroGPU). Generation retries
  with backoff, but a bad hour is a bad hour.
- ASR probabilities are a proxy for diction, calibrated against the human
  ear that caught these defects. The ear outranks the numbers — if a
  passing take sounds wrong to you, open an issue with the QC report.
- **Gate 7 (cut word) is an acoustic shape check, not a transcript.** It
  catches endings that are abruptly cut, chopped at the file edge,
  pinched, or stranded as a detached weak tail. It cannot tell *which*
  word was said (gates 1–3 do that), and it cannot detect a word that
  was removed from a take in post — which is why this tool never edits
  inside a sentence in the first place.
- Hindi is cross-lingual and UNVERIFIED against its channel (see above).

## Layout

```
divi.py                   the front door: pre-flight -> (local | --cloud)
                          generation -> assembly -> final verification
engine.py                 CLI: pre-flight -> generate -> gate -> heal ->
                          assemble (+ --batch waves, --assemble-out)
preflight.py              script pre-flight: heal the input (typos, TTS
                          format, english-mix, purity, sentence shape)
repair.py                 the self-healing playbook: defect classes,
                          candidate scoring, escalation ladders
speedpolicy.py            the speed law: the ONLY tempo entry point
                          (LOCKED recipe vs USER-REQUESTED --speed)
verify.py                 final assembled-file verification (completeness,
                          language, grunt/cut per window, gaps, levels,
                          duration, identity spot checks)
backends.py               pluggable TTS backends (defaults, mms, omnivoice, elevenlabs, http, github)
gates.py                  the gate suite, importable
acoustic_gates.py         gates 6 + 7 (head grunt / cut word) — self-contained
                          acoustics, no env side effects, safe in the
                          generation subprocess
proof_omnivoice_gates.py  gates 6 + 7 proof over the real Sample B evidence
                          files (+ proof_omnivoice_gates.out.txt)
indicf5_gen.py            whole-sentence IndicF5 take generator + full gates
                          (runs on the indicf5-batch runners)
requirements-indicf5.txt  deps for the IndicF5 runners
.github/workflows/
  voice-batch.yml         divi-voice-batch: free parallel batch voicing
                          on GitHub Actions (up to 40 runners)
  indicf5-batch.yml       divi-indicf5-batch: 10-runner brute-force
                          whole-sentence Telugu takes, every take fully
                          gated (gates + identity + pace)
BENCHMARK.md              measured batch-vs-per-line timings on a small VM
BENCHMARK-DIVI.md         the speed-law benchmark: per-language measured
                          wall-clock, per-sentence cost, 20-minute math
test_batch.py             offline batch-mode tests (stub generation)
phonetics.py              Telugu / Devanagari / ASR-script phonetic normalizers
voice/
  settings.json           ALL locked settings (single source of truth)
  english-reference.wav   canonical 25 s English reference (+ .m4a original)
  telugu-reference.wav    Telugu reference (+ its transcript .txt) — default is
                          natspan2, the Demucs-cleaned NATURAL-pace Telugu
                          Part 2 span (fixed13, see refs/)
  refs/                   genuine Telugu reference set: natspan1/2/3
                          (natural-pace, music-removed, canonical) +
                          span1/span2/span3 + te3 archived (cut from the
                          1.4705x time-squeezed copy), indexed by
                          refs/refs.json (incl. the ear-approved takes
                          and their measurements)
  samples/                owner-approved samples per language (Telugu pair:
                          telugu-approved-s1/s2-fixed13.mp3)
  VOICE.md                voice provenance
PRONUNCIATION-PROFILE.md  the measured delivery profile the settings encode
```

## License

MIT — see `LICENSE`. The reference voice is a real person's voice, supplied
by its owner for this project; use the engine and the voice accordingly.
